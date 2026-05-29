#!/usr/bin/env python3
"""
Capture Doubao chat — fully automated.
Send a message → wait for AI reply → save structured JSON.

Usage:
  python3 doubao_capture.py "你的问题"
  python3 doubao_capture.py "问题" --frida          # with URL capture
  python3 doubao_capture.py "问题" /path/to/out.json --frida
  python3 doubao_capture.py --frida                  # manual capture + URLs

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
DEVICE = "19161FDEE0J82D"  # Android device/emulator serial
OUTPUT = os.path.expanduser("~/Desktop/doubao_capture.json")
TIMEOUT = 120
PACKAGE = "com.larus.nova"

# ── Frida WebView URL hook ─────────────────────────────────────
FRIDA_SCRIPT = "/tmp/frida_webview_url_v2.js"
_frida_proc = None
_frida_output = "/tmp/frida_capture_output.txt"


def _start_frida():
    """Launch Frida with WebView hook script against Doubao."""
    global _frida_proc
    subprocess.run(["pkill", "-f", "frida.*larus"],
                   capture_output=True)
    subprocess.run([ADB, "-s", DEVICE, "shell", "am", "force-stop", PACKAGE],
                   capture_output=True)
    time.sleep(1)
    # Start app via monkey, then attach by PID (more reliable than -n on Android 16)
    subprocess.run([ADB, "-s", DEVICE, "shell", "monkey", "-p", PACKAGE, "1"],
                   capture_output=True)
    time.sleep(4)
    _ensure_unlocked()
    result = subprocess.run([ADB, "-s", DEVICE, "shell", "pidof", PACKAGE],
                            capture_output=True, text=True)
    pid = result.stdout.strip()
    if not pid:
        print("  [!] App didn't start")
        return False
    with open(_frida_output, 'w') as f:
        _frida_proc = subprocess.Popen(
            ["frida", "-D", DEVICE, "-p", pid, "-l", FRIDA_SCRIPT],
            stdout=f, stderr=subprocess.STDOUT
        )
    # Wait for hooks to install
    for _ in range(15):
        time.sleep(1)
        try:
            with open(_frida_output) as f:
                content = f.read()
                if 'All hooks installed' in content:
                    return True
                if 'Process terminated' in content:
                    print("  [!] Process died — app may have anti-Frida protection")
                    return False
        except Exception:
            pass
    return False


def _stop_frida():
    """Kill the Frida subprocess."""
    global _frida_proc
    if _frida_proc:
        _frida_proc.terminate()
        try:
            _frida_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _frida_proc.kill()
        _frida_proc = None


def _read_frida_output():
    """Read current Frida output file."""
    try:
        with open(_frida_output) as f:
            return f.read()
    except Exception:
        return ""


def _parse_new_urls(baseline_text, new_text):
    """Extract newly captured non-js, non-seclink WebView.loadUrl lines."""
    old_urls = set(re.findall(
        r'\[WebView\.loadUrl\] (?!javascript:)(.+?)(?:\n|$)',
        baseline_text
    ))
    new_urls = re.findall(
        r'\[WebView\.loadUrl\] (?!javascript:)(.+?)(?:\n|$)',
        new_text
    )
    return [u for u in new_urls
            if u not in old_urls and 'seclink.bytedance.com' not in u]


# ── uiautomator2 device handle ─────────────────────────────────
_d = None


def _get_d():
    global _d
    if _d is None:
        if not _HAS_U2:
            print("[!] uiautomator2 not installed. See script header for setup.")
            sys.exit(1)
        _d = u2.connect(DEVICE)
    return _d


# ── App lifecycle ──────────────────────────────────────────────

def _ensure_unlocked():
    """Dismiss Android lock screen if present."""
    subprocess.run([ADB, "-s", DEVICE, "shell", "wm", "dismiss-keyguard"],
                   capture_output=True)
    subprocess.run([ADB, "-s", DEVICE, "shell", "input", "swipe", "540", "2900", "540", "100", "500"],
                   capture_output=True)
    time.sleep(1)


def restart_app():
    """Restart Doubao to ensure a clean RecyclerView state."""
    subprocess.run([ADB, "-s", DEVICE, "shell", "am", "force-stop", PACKAGE],
                   capture_output=True, text=True)
    time.sleep(1.5)
    subprocess.run([ADB, "-s", DEVICE, "shell", "monkey", "-p", PACKAGE,
                    "-c", "android.intent.category.LAUNCHER", "1"],
                   capture_output=True, text=True)
    time.sleep(5)
    _ensure_unlocked()
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
        "正在充电", "已充满电", "点按即可", "USB 调试",
    ]
    candidates = []
    for t in after:
        t = t.strip()
        if not t or t in before_set or len(t) < 80:
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
    Uses uiautomator2 selectors + text parsing."""

    search_summary = ""
    total_refs = 0
    keywords = []
    sources = []

    try:
        d = _get_d()

        # 1. Get reference title via uiautomator2 selector
        ref_title = d(resourceId="com.larus.nova:id/tv_reference_title")
        if ref_title.exists:
            search_summary = (ref_title.info.get("text") or "").strip()
            m = re.match(r'^搜索\s+(\d+)\s*个关键词[,，]\s*参考\s+(\d+)\s*篇资料',
                         search_summary)
            if m:
                total_refs = int(m.group(2))
    except Exception:
        pass

    # 2. Fallback: parse from text dump
    if not search_summary:
        for i, t in enumerate(texts):
            m = re.match(r'^搜索\s+(\d+)\s*个关键词[,，]\s*参考\s+(\d+)\s*篇资料', t)
            if m:
                search_summary = t
                total_refs = int(m.group(2))
                break

    # 3. Parse keywords from text list (adjacent to search summary)
    for i, t in enumerate(texts):
        if t == search_summary:
            for j in range(i + 1, min(i + 15, len(texts))):
                candidate = texts[j]
                if candidate and ('“' in candidate or '”' in candidate) and '、' in candidate:
                    kws = re.findall(r'[“”]([^“”]+?)[“”]', candidate)
                    if kws and len(kws) >= 1:
                        keywords = kws
                        break
            break

    # 4. Extract reference titles via uiautomator2 selector
    if search_summary:
        try:
            d = _get_d()
            # Only expand if references aren't already visible
            refs = d(resourceId="com.larus.nova:id/tv_reference_content")
            if not refs.exists:
                ref_clickable = d(resourceId="com.larus.nova:id/ll_reference_title")
                # Scroll up if reference toggle is off-screen (RecyclerView may have recycled it)
                for _ in range(8):
                    if ref_clickable.exists:
                        break
                    d.swipe(540, 800, 540, 1800, 0.2)
                    time.sleep(0.3)
                if ref_clickable.exists:
                    ref_clickable.click()
                    # Wait for expansion animation
                    for _ in range(10):
                        time.sleep(0.3)
                        refs = d(resourceId="com.larus.nova:id/tv_reference_content")
                        if refs.exists:
                            break

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
    # Find EditText by class (resourceId varies across Doubao versions)
    for attempt in range(5):
        el = d(className="android.widget.EditText")
        if el.exists:
            break
        # Try phone-version resource ID
        el = d(resourceId="com.larus.nova:id/input_text")
        if el.exists:
            break
        # Switch from voice mode to text input mode
        toggle = d(resourceId="com.larus.nova:id/action_input")
        if toggle.exists:
            toggle.click()
            time.sleep(0.5)
        time.sleep(1.5)
    el = d(className="android.widget.EditText")
    if not el.exists:
        el = d(resourceId="com.larus.nova:id/input_text")
    el.set_text(text)
    time.sleep(0.2)


def _click_send():
    d = _get_d()
    btn = d(resourceId="com.larus.nova:id/action_send")
    if btn.exists:
        btn.click()
    else:
        try:
            d(description="发送").click()
        except Exception:
            subprocess.run([ADB, "-s", DEVICE, "shell", "input", "keyevent", "66"], capture_output=True)


# ── Core flow ──────────────────────────────────────────────────

def send_message(text):
    print(f"[*] Sending: {text[:80]}{'...' if len(text) > 80 else ''}")
    _ensure_unlocked()
    d = _get_d()

    # Ensure we're in ChatActivity, not on the main conversation list
    cur = d.app_current()
    if 'ChatActivity' not in cur.get('activity', ''):
        # Click on an existing conversation to enter chat
        for conv_text in ['doubao.com', '豆包']:
            conv = d(text=conv_text)
            if conv.exists:
                x, y = conv.center()
                d.click(x, y)
                time.sleep(1.5)
                break
        else:
            # Tap the first visible text area as fallback
            d.click(540, 400)
            time.sleep(1.5)

    # Wait a moment for UI to settle after navigation
    time.sleep(1)
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
    time.sleep(1)
    _ensure_refs_visible()
    _, _, keywords, sources = extract_search_info(get_texts())
    if sources:
        return keywords, sources
    _, _, kw2, src2 = extract_search_info(get_texts())
    return kw2, src2


def _adb_swipe(x1, y1, x2, y2, duration_ms=200):
    """Use ADB input swipe (more reliable than uiautomator2 on some devices)."""
    subprocess.run(
        [ADB, "-s", DEVICE, "shell", "input", "swipe",
         str(x1), str(y1), str(x2), str(y2), str(duration_ms)],
        capture_output=True)


def _adb_tap(x, y):
    subprocess.run(
        [ADB, "-s", DEVICE, "shell", "input", "tap", str(x), str(y)],
        capture_output=True)


def _click_toggle_safe():
    """Click the reference toggle using coordinates (avoids RecyclerView
    recycling between exists check and click)."""
    d = _get_d()
    toggle = d(resourceId="com.larus.nova:id/ll_reference_title")
    if not toggle.exists:
        return False
    info = toggle.info
    bounds = info.get('bounds', {})
    cx = (bounds.get('left', 0) + bounds.get('right', 0)) // 2
    cy = (bounds.get('top', 0) + bounds.get('bottom', 0)) // 2
    _adb_tap(cx, cy)
    return True


def _ensure_refs_visible():
    """Make reference cards visible. Returns count of visible cards, or 0."""
    d = _get_d()

    # Already expanded?
    refs = d(resourceId="com.larus.nova:id/tv_reference_content")
    if refs.exists:
        return refs.count

    # Check if toggle is immediately visible — use ADB tap to avoid
    # RecyclerView recycling between the exists check and click
    if _click_toggle_safe():
        for _ in range(15):
            time.sleep(0.3)
            refs = d(resourceId="com.larus.nova:id/tv_reference_content")
            if refs.exists:
                time.sleep(0.3)
                return refs.count
        return 0

    # Scroll up using ADB swipe (finger top→bottom, content moves DOWN,
    # revealing content ABOVE where the reference toggle sits)
    for _ in range(30):
        _adb_swipe(540, 400, 540, 1800, 200)
        time.sleep(0.3)
        refs = d(resourceId="com.larus.nova:id/tv_reference_content")
        if refs.exists:
            return refs.count
        if _click_toggle_safe():
            for _ in range(15):
                time.sleep(0.3)
                refs = d(resourceId="com.larus.nova:id/tv_reference_content")
                if refs.exists:
                    time.sleep(0.3)
                    return refs.count
            return 0

    # Recovery: close any lingering WebView, go home, then monkey-launch
    # Doubao back to foreground. Frida stays attached (no force-stop).
    subprocess.run([ADB, "-s", DEVICE, "shell", "input", "keyevent", "4"],
                   capture_output=True)
    time.sleep(0.5)
    for recovery_attempt in range(2):
        subprocess.run([ADB, "-s", DEVICE, "shell", "input", "keyevent", "3"],
                       capture_output=True)
        time.sleep(0.5)
        subprocess.run([ADB, "-s", DEVICE, "shell", "monkey", "-p", PACKAGE, "1"],
                       capture_output=True)
        time.sleep(6)
        _ensure_unlocked()
        global _d
        _d = None
        d = _get_d()

        for _ in range(30):
            _adb_swipe(540, 400, 540, 1800, 200)
            time.sleep(0.3)
            if _click_toggle_safe():
                for _ in range(15):
                    time.sleep(0.3)
                    refs = d(resourceId="com.larus.nova:id/tv_reference_content")
                    if refs.exists:
                        time.sleep(0.3)
                        return refs.count
                break  # Toggle clicked but no cards — try recovery again
            refs = d(resourceId="com.larus.nova:id/tv_reference_content")
            if refs.exists:
                return refs.count

    return 0


def _capture_urls(source_count):
    """Click each reference card and capture URLs from Frida output."""
    d = _get_d()
    urls = []

    visible = _ensure_refs_visible()
    if not visible:
        print("  [!] Cannot find reference cards")
        return urls

    baseline = _read_frida_output()

    for i in range(source_count):
        d = _get_d()  # Refresh — _ensure_refs_visible may have reset connection
        refs = d(resourceId="com.larus.nova:id/tv_reference_content")
        # Scroll within the reference list to reveal card [i]
        # Finger from bottom→top, content moves UP, revealing cards BELOW
        for _ in range(20):
            if i < refs.count:
                break
            _adb_swipe(540, 1700, 540, 600, 200)
            time.sleep(0.3)
            refs = d(resourceId="com.larus.nova:id/tv_reference_content")

        if i >= refs.count:
            print(f"  [!] Card [{i}] not found (have {refs.count})")
            urls.append("")
            continue

        title = refs[i].get_text()
        short = title[:55] + ("..." if len(title) > 55 else "")
        print(f"  [{i}] {short}")
        refs[i].click()
        time.sleep(2.5)

        new_output = _read_frida_output()
        new_urls = _parse_new_urls(baseline, new_output)
        urls.append(new_urls[0] if new_urls else "")
        baseline = new_output

        # Back via ADB keyevent, then wait for UI to settle
        subprocess.run([ADB, "-s", DEVICE, "shell", "input", "keyevent", "4"],
                       capture_output=True)
        time.sleep(3)
        _ensure_unlocked()

        # Re-establish reference visibility for next card
        if i + 1 < source_count:
            _ensure_refs_visible()

    return urls


def save(question, answer, path=OUTPUT, search_summary="", total_references=0,
         search_keywords=None, search_sources=None, captured_urls=None):
    if search_keywords is None:
        search_keywords = []
    if search_sources is None:
        search_sources = []
    if captured_urls is None:
        captured_urls = []

    # Populate URLs into sources
    for i, src in enumerate(search_sources):
        if i < len(captured_urls) and captured_urls[i]:
            src["url"] = captured_urls[i]

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
    url_count = len([s for s in search_sources if s.get("url")])
    print(f"[*] Saved → {path}  ({url_count}/{len(search_sources)} URLs captured)")


# ── CLI ────────────────────────────────────────────────────────

def main():
    # Parse --frida flag and positional args
    use_frida = False
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--frida" in sys.argv:
        use_frida = True

    msg = args[0] if len(args) > 0 else None
    out = args[1] if len(args) > 1 else OUTPUT

    # ── Mode: no message → manual capture from current screen ──
    if msg is None:
        print("=" * 55)
        mode_label = "Frida" if use_frida else "Text-only"
        print(f"  Mode: Capture only ({mode_label})")
        print(f"  Output: {out}")
        print("=" * 55)

        if use_frida:
            print("[*] Starting Frida...")
            if not _start_frida():
                print("[!] Frida failed to start, falling back to text-only")
                use_frida = False
            else:
                print("[*] Frida ready, hooks active")
                # Need to wait for app to settle
                time.sleep(3)

        texts = get_texts()
        answer = check_already_responded(texts)
        if answer:
            print(f"\n{'─' * 50}")
            print(answer)
            print(f"{'─' * 50}\n")
            # Try to expand references and capture details
            kw2, src2 = capture_references_post(answer)
            if src2:
                keywords, sources = kw2, src2
                search_summary, total_refs, _, _ = extract_search_info(get_texts())
            else:
                search_summary, total_refs, keywords, sources = extract_search_info(texts)
            captured_urls = []
            if use_frida and sources:
                print(f"[*] Capturing URLs for {len(sources)} references...")
                captured_urls = _capture_urls(len(sources))
            save("(manual)", answer, out, search_summary, total_refs,
                 keywords, sources, captured_urls)
            print("Done ✓")
        else:
            print("[!] No AI response visible on screen yet.")
        if use_frida:
            _stop_frida()
        return

    # ── Mode: automated send + capture ──
    print("=" * 55)
    mode_label = "Frida" if use_frida else "Text-only"
    print(f"  Message: {msg}")
    print(f"  Output:  {out}")
    print(f"  Mode:    {mode_label}")
    print("=" * 55)

    if use_frida:
        print("[1/6] Start Frida + Doubao...")
        if not _start_frida():
            print("[!] Frida failed — falling back to text-only")
            use_frida = False
            print("[1/5] Restart app (clean state)...")
            restart_app()
        else:
            print("[*] Frida ready, hooks active")
            # App is already spawned by Frida, just wait for UI
            time.sleep(3)
            global _d
            _d = None
    else:
        print("[1/5] Restart app (clean state)...")
        restart_app()

    print("[2/5] Snapshot...")
    before = get_texts()

    print("[3/5] Send message...")
    send_message(msg)

    step = "5" if use_frida else "4"
    print(f"[4/{step}] Wait for AI reply...")
    answer, search_summary, total_refs, keywords, sources = wait_for_response(
        set(before), question=msg
    )

    if answer:
        # Capture references BEFORE printing (printing long answers
        # takes seconds; RecyclerView may recycle the reference section)
        if not sources:
            kw2, src2 = capture_references_post(answer)
            if src2:
                keywords, sources = kw2, src2
                total_refs = len(src2) if src2 else total_refs
        # Re-extract search_summary if missing (may have been missed during streaming)
        if not search_summary:
            s2, tr2, kw2, src2 = extract_search_info(get_texts())
            if s2:
                search_summary = s2
                total_refs = tr2 if tr2 else total_refs
                if src2:
                    keywords, sources = kw2, src2
        print(f"\n{'─' * 50}")
        print(answer)
        print(f"{'─' * 50}\n")

        captured_urls = []
        if use_frida and sources:
            print(f"[5/6] Capture URLs for {len(sources)} references...")
            captured_urls = _capture_urls(len(sources))
            captured = len([u for u in captured_urls if u])
            print(f"  Captured {captured}/{len(sources)} URLs")

        final_step = "6" if use_frida else "5"
        print(f"[{final_step}/{final_step}] Save JSON...")
        save(msg, answer, out, search_summary, total_refs,
             keywords, sources, captured_urls)
        print("Done ✓")
    else:
        print("[!] Timeout — no AI response detected.")

    if use_frida:
        _stop_frida()


if __name__ == "__main__":
    main()
