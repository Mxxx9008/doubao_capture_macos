#!/usr/bin/env python3
"""
Capture Doubao chat — fully automated.
Send a message → wait for AI reply → save structured JSON.

Usage:
  python3 doubao_capture.py "你的问题"
  python3 doubao_capture.py "What's the weather?"
  python3 doubao_capture.py "问题" /path/to/output.json

Setup (one-time):
  /tmp/u2env/bin/pip install uiautomator2
  /tmp/u2env/bin/python3 -m uiautomator2 init
"""

import subprocess
import time
import json
import os
import re
import sys
import secrets
import html as _html

# ── uiautomator2 (required for text input on physical devices) ──
try:
    import uiautomator2 as u2
    _HAS_U2 = True
except ImportError:
    _HAS_U2 = False

# ── Configuration ──────────────────────────────────────────────
ADB = os.path.expanduser("~/Library/Android/sdk/platform-tools/adb")
OUTPUT = os.path.expanduser("~/Desktop/doubao_capture.json")
TIMEOUT = 120
PACKAGE = "com.larus.nova"

# ── uiautomator2 device handle ─────────────────────────────────
_d = None


def _get_d():
    global _d
    if _d is None:
        if not _HAS_U2:
            print("[!] uiautomator2 not installed. See script header for setup.")
            sys.exit(1)
        _d = u2.connect()
    return _d


# ── App lifecycle ──────────────────────────────────────────────

def restart_app():
    """Restart Doubao to ensure a clean RecyclerView state."""
    subprocess.run([ADB, "shell", "am", "force-stop", PACKAGE],
                   capture_output=True, text=True)
    time.sleep(1.5)
    subprocess.run([ADB, "shell", "monkey", "-p", PACKAGE,
                    "-c", "android.intent.category.LAUNCHER", "1"],
                   capture_output=True, text=True)
    time.sleep(5)
    global _d
    _d = None


# ── UI helpers ─────────────────────────────────────────────────

def get_texts():
    """Extract visible text from uiautomator2 hierarchy dump.

    Uses uiautomator2.dump_hierarchy() rather than ADB uiautomator dump
    because the ADB method returns stale/cached data on some devices.
    """
    d = _get_d()
    raw = d.dump_hierarchy()
    texts = re.findall(r'text="([^"]*)"', raw)
    descs = re.findall(r'content-desc="([^"]*)"', raw)
    result = []
    seen = set()
    for t in texts:
        t = _html.unescape(t).strip()
        if t and t not in seen:
            seen.add(t)
            result.append(t)
    for desc in descs:
        desc = _html.unescape(desc).strip()
        if desc and desc not in seen:
            seen.add(desc)
            result.append(desc)
    return result


def find_answer(before, after, question=""):
    before_set = set(before)
    skip_words = [
        "豆包", "快速", "打电话", "AI 创作", "视频通话", "相机", "返回",
        "反馈", "深度思考", "Seedance", "帮我写作", "聊聊新话题",
        "停止生成", "重新生成", "复制", "点赞", "点踩", "分享",
        "继续问", "上传", "文件", "发消息", "按住说话",
        "中国电信", "信号满格", "已连接到",
    ]
    candidates = []
    for t in after:
        t = t.strip()
        if not t or t in before_set or len(t) < 5:
            continue
        if t == question or (len(t) < 30 and t in question):
            continue
        if len(t) < 30 and any(w in t for w in skip_words):
            continue
        # Skip streaming fragments (⚫ = Doubao's streaming cursor)
        if '⚫' in t:
            continue
        # Skip search status text ("搜索 N 个关键词，参考 N 篇资料")
        if re.match(r'^搜索\s+\d+\s*个关键词', t):
            continue
        # Skip clock / time patterns
        if re.match(r'^\d{1,2}:\d{2}$', t):
            continue
        candidates.append(t)
    return max(candidates, key=len) if candidates else None


def extract_search_info(texts):
    """Extract search summary, keywords, and reference sources from UI.
    Uses uiautomator2 selectors for titles, text parsing for keywords/summary.
    URL cannot be extracted at Level A (embedded in link properties)."""

    search_summary = ""
    total_refs = 0
    keywords = []
    sources = []

    # 1. Parse search summary and keywords from text list
    for i, t in enumerate(texts):
        m = re.match(r'^搜索\s+(\d+)\s*个关键词[,，]\s*参考\s+(\d+)\s*篇资料', t)
        if m:
            search_summary = t
            total_refs = int(m.group(2))
            for j in range(i + 1, min(i + 15, len(texts))):
                candidate = texts[j]
                # Keywords appear as “kw1”、”kw2” — must have quotes AND 、 separator
                if candidate and ('”' in candidate or '”' in candidate) and '、' in candidate:
                    kws = re.findall(r'[“\”]([^”\”]+?)[“\”]', candidate)
                    if kws and len(kws) >= 1:
                        keywords = kws
                        break
            break

    # 2. Extract reference titles via uiautomator2 selector
    if search_summary:
        try:
            d = _get_d()
            refs = d(resourceId="com.larus.nova:id/tv_reference_content")
            if refs.exists:
                for ref in refs:
                    title = (ref.info.get("text") or "").strip()
                    if title and len(title) >= 3:
                        sitename = _parse_sitename(title)
                        sources.append({
                            "title": title,
                            "url": "",
                            "sitename": sitename,
                            "summary": ""
                        })
        except Exception:
            pass

    return search_summary, total_refs, keywords, sources


def _parse_sitename(title):
    """Try to extract sitename from title.
    Common patterns: 'title_sitename', 'title-sitename', 'title|sitename'.
    Only returns sitename if it looks like a known source."""
    known_sources = [
        "新京报", "北京日报", "京报网", "证券日报", "金台资讯", "北青热点",
        "千龙网", "今日头条", "手机搜狐网", "抖音", "知乎", "澎湃新闻",
        "新浪", "凤凰网", "腾讯新闻", "网易新闻", "哔哩哔哩", "人民日报",
        "新华网", "光明网", "环球网", "中国新闻网", "中国青年网",
        "广东能飞航空", "全国团体标准信息平台", "中国民航无人机执照",
    ]
    for sep in ["_", "-", "|"]:
        if sep in title:
            last_part = title.rsplit(sep, 1)[-1].strip()
            for src in known_sources:
                if src in last_part:
                    return src
    return ""


def check_already_responded(texts):
    """Check if an AI response is visible (for manual capture mode)."""
    has_input = any("发消息" in t or "按住说话" in t for t in texts)
    if not has_input:
        return None
    skip_words = [
        "豆包", "快速", "打电话", "AI 创作", "视频通话", "相机", "返回",
        "反馈", "深度思考", "Seedance", "帮我写作", "聊聊新话题",
        "停止生成", "重新生成", "复制", "点赞", "点踩", "分享",
        "继续问", "上传", "文件", "内容由 AI 生成",
    ]
    candidates = []
    for t in texts:
        t = t.strip()
        if len(t) < 5:
            continue
        if any(w in t for w in skip_words):
            continue
        candidates.append(t)
    return max(candidates, key=len) if candidates else None


# ── Input methods ──────────────────────────────────────────────

def _set_text(text):
    d = _get_d()
    el = d(resourceId="com.larus.nova:id/input_text")
    if not el.exists:
        # Switch from voice mode to text input mode
        toggle = d(resourceId="com.larus.nova:id/action_input")
        if toggle.exists:
            toggle.click()
            time.sleep(0.5)
    el = d(resourceId="com.larus.nova:id/input_text")
    el.set_text(text)
    time.sleep(0.2)


def _click_send():
    d = _get_d()
    btn = d(resourceId="com.larus.nova:id/action_send")
    if btn.exists:
        btn.click()
    else:
        d(description="发送").click()


# ── Core flow ──────────────────────────────────────────────────

def send_message(text):
    print(f"[*] Sending: {text[:80]}{'...' if len(text) > 80 else ''}")
    _set_text(text)
    time.sleep(0.3)
    _click_send()
    time.sleep(0.3)
    print("[*] Sent ✓")


def wait_for_response(before, timeout=TIMEOUT, question=""):
    search_summary = ""
    total_refs = 0
    keywords = []
    sources = []
    for i in range(timeout):
        time.sleep(1)
        after = get_texts()
        # Capture search summary early (keywords/sources may be collapsed)
        s, tr, kw, src = extract_search_info(after)
        if s and not search_summary:
            search_summary, total_refs, keywords, sources = s, tr, kw, src
        ans = find_answer(before, after, question=question)
        if ans:
            if not search_summary:
                search_summary, total_refs, keywords, sources = extract_search_info(after)
            return ans, search_summary, total_refs, keywords, sources
        if i % 10 == 0 and i > 0:
            print(f"    ... {i}s")
    return None, "", 0, [], []


def capture_references_post(answer):
    """After answer is captured, try to expand and capture reference cards."""
    time.sleep(1)  # Let UI settle
    _expand_references()
    _, _, keywords, sources = extract_search_info(get_texts())
    if sources:
        return keywords, sources
    # If expand+extract didn't get sources, try extracting from current text
    _, _, kw2, src2 = extract_search_info(get_texts())
    return kw2, src2


def _expand_references():
    """Tap the reference title to expand the collapsed reference card list."""
    try:
        d = _get_d()
        # The search summary has resourceId tv_reference_title and is tappable
        title = d(resourceId="com.larus.nova:id/tv_reference_title")
        if title.exists:
            x, y = title.center()
            d.click(x, y)
            time.sleep(0.5)
    except Exception:
        pass


def save(question, answer, path=OUTPUT, search_summary="", total_references=0,
         search_keywords=None, search_sources=None):
    if search_keywords is None:
        search_keywords = []
    if search_sources is None:
        search_sources = []
    task_id = secrets.token_hex(6)
    mode = "quick" if search_summary else "chat"

    data = {
        "code": 0,
        "msg": "success",
        "data": {
            "task_id": task_id,
            "question": question,
            "mode": mode,
            "search_keywords": search_keywords,
            "search_sources": search_sources,
            "search_summary": search_summary,
            "thinking_process": "",
            "answer": answer,
            "total_references": total_references,
            "statistics": {
                "sitename_counts": {},
                "brands": [],
                "token_usage": {
                    "total_input_tokens": 0,
                    "total_output_tokens": 0,
                    "total_tokens": 0
                }
            }
        }
    }
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[*] Saved → {path}")


# ── CLI ────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        out = OUTPUT
        print("=" * 55)
        print("  Mode: Capture only (manual send)")
        print(f"  Output: {out}")
        print("=" * 55)
        texts = get_texts()
        answer = check_already_responded(texts)
        if answer:
            print(f"\n{'─' * 50}")
            print(answer)
            print(f"{'─' * 50}\n")
            search_summary, total_refs, keywords, sources = extract_search_info(texts)
            save("(manual)", answer, out, search_summary, total_refs, keywords, sources)
            print("Done ✓")
        else:
            print("[!] No AI response visible on screen yet.")
        return

    msg = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else OUTPUT

    print("=" * 55)
    print(f"  Message: {msg}")
    print(f"  Output:  {out}")
    print("=" * 55)

    print("[1/5] Restart app (clean state)...")
    restart_app()

    print("[2/5] Snapshot...")
    before = get_texts()

    print("[3/5] Send message...")
    send_message(msg)

    print("[4/5] Wait for AI reply...")
    answer, search_summary, total_refs, keywords, sources = wait_for_response(set(before), question=msg)

    if answer:
        print(f"\n{'─' * 50}")
        print(answer)
        print(f"{'─' * 50}\n")
        # After answer, try to expand and capture reference details
        if search_summary and not sources:
            kw2, src2 = capture_references_post(answer)
            if src2:
                keywords, sources = kw2, src2
                total_refs = len(src2) if src2 else total_refs
        print("[5/5] Save JSON...")
        save(msg, answer, out, search_summary, total_refs, keywords, sources)
        print("Done ✓")
    else:
        print("[!] Timeout — no AI response detected.")


if __name__ == "__main__":
    main()
