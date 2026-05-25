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
    """Extract search summary, keywords, and reference titles from UI texts."""
    search_summary = ""
    total_refs = 0
    keywords = []
    sources = []

    for i, t in enumerate(texts):
        m = re.match(r'^搜索\s+(\d+)\s*个关键词[,，]\s*参考\s+(\d+)\s*篇资料', t)
        if m:
            search_summary = t
            total_refs = int(m.group(2))
            # Keywords are typically in the next text nodes after the summary
            # They appear as: "keyword1"、"keyword2" in a single text node
            for j in range(i + 1, min(i + 10, len(texts))):
                candidate = texts[j]
                if candidate and '“' in candidate or '"' in candidate:
                    # Extract quoted keywords: "xxx" or “xxx”
                    kws = re.findall(r'[“"]([^”"]+)[”"]', candidate)
                    if kws:
                        keywords = kws
                        break
            # Reference titles: numbered items after keywords
            # Pattern: "1." "Title text" "2." "Title text" ...
            for j in range(i + 1, len(texts)):
                t2 = texts[j]
                # Numbered marker like "1.", "12."
                if re.match(r'^\d+\.\s*$', t2):
                    # Next text node should be the title
                    if j + 1 < len(texts):
                        title = texts[j + 1].strip()
                        if len(title) >= 5:
                            sources.append({
                                "title": title,
                                "url": "",
                                "sitename": "",
                                "summary": ""
                            })
            break

    return search_summary, total_refs, keywords, sources


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
        # Capture search info early — it appears before the answer
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
        print("[5/5] Save JSON...")
        save(msg, answer, out, search_summary, total_refs, keywords, sources)
        print("Done ✓")
    else:
        print("[!] Timeout — no AI response detected.")


if __name__ == "__main__":
    main()
