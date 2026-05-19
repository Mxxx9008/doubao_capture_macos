#!/usr/bin/env python3
"""
Capture Doubao chat — fully automated.
Send a message → wait for AI reply → save structured JSON.

Usage:
  python3 capture_and_json.py "你的问题"
  python3 capture_and_json.py "What's the weather?"
  python3 capture_and_json.py "问题" /path/to/output.json
"""

import subprocess
import time
import json
import os
import re
import sys
import html as _html
import shlex

# ── Configuration ──────────────────────────────────────────────
ADB = os.path.expanduser("~/Library/Android/sdk/platform-tools/adb")
OUTPUT = os.path.expanduser("~/Desktop/doubao_capture.json")
TIMEOUT = 60

# UI tap targets (1080px wide emulator, density 420)
TAP_INPUT  = (540, 1400)   # message input field
TAP_SEND   = (986, 1406)   # send button (appears after typing)
TAP_PASTE  = (480, 1250)   # "Paste" popup after long-press (above input)


# ── ADB helpers ────────────────────────────────────────────────

def _adb(*args):
    """Run adb command with list args — avoids shell escaping issues."""
    subprocess.run([ADB] + list(args), capture_output=True, text=True)


def _adb_stdout(*args):
    """Run adb and return stdout string."""
    r = subprocess.run([ADB] + list(args), capture_output=True, text=True)
    return r.stdout


def _adb_shell(cmd_str):
    """Run via shell string when pipes/redirects needed."""
    subprocess.run(f"{ADB} shell {cmd_str}", shell=True,
                   capture_output=True, text=True)


def _adb_pipe(text, *shell_args):
    """Pipe Python string to adb shell command via stdin."""
    p = subprocess.Popen(
        [ADB, "shell"] + list(shell_args),
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True
    )
    p.communicate(input=text)


# ── UI helpers ─────────────────────────────────────────────────

def _dump_xml():
    """Dump current screen XML, return raw string."""
    _adb("shell", "uiautomator", "dump", "/sdcard/ui.xml")
    return _adb_stdout("shell", "cat", "/sdcard/ui.xml")


def get_texts():
    """Extract all visible text elements from screen."""
    raw = _dump_xml()
    texts = re.findall(r'text="([^"]*)"', raw)
    return [_html.unescape(t) for t in texts if t.strip()]


def _get_texts_with_pos():
    """Extract visible texts with their Y positions."""
    raw = _dump_xml()
    nodes = re.findall(
        r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]".*?text="([^"]*)"', raw
    )
    results = []
    for x1, y1, x2, y2, txt in nodes:
        t = _html.unescape(txt).strip()
        if t:
            results.append((int(y1), t))
    return sorted(results)


def scroll_to_bottom():
    """Scroll to the bottom of the conversation with rapid flings."""
    for _ in range(15):
        _adb("shell", "input", "swipe", "540", "1800", "540", "400", "30")
        time.sleep(0.08)
    time.sleep(0.6)


def find_answer(before, after):
    """Return the new AI response text, or None."""
    before_set = set(before)
    skip_words = [
        "豆包", "快速", "打电话", "AI 创作", "视频通话", "相机", "返回",
        "反馈", "深度思考", "Seedance", "帮我写作", "聊聊新话题",
        "停止生成", "重新生成", "复制", "点赞", "点踩", "分享",
        "继续问", "上传", "文件",
    ]
    candidates = []
    for t in after:
        t = t.strip()
        if not t or t in before_set or len(t) < 10:
            continue
        if any(w in t for w in skip_words):
            continue
        candidates.append(t)
    return max(candidates, key=len) if candidates else None


# ── Input methods ──────────────────────────────────────────────

def _clear_field():
    for _ in range(5):
        _adb("shell", "input", "keyevent", "123")   # SELECT_ALL
        time.sleep(0.04)
        _adb("shell", "input", "keyevent", "67")    # DELETE
        time.sleep(0.04)


def _has_cjk(text):
    return any('一' <= c <= '鿿' for c in text)


def _send_ascii(text):
    """Send ASCII text via `input text`.
    Spaces must be encoded as %s; other special chars escaped."""
    safe = text.replace('%', '\\%').replace(' ', '%s')
    # Use list-based adb call to avoid local shell quote stripping
    _adb("shell", "input", "text", safe)


def _send_chinese(text):
    """Send Chinese via clipboard paste.

    Pipeline: write text to device file → load into clipboard → paste.
    Tries KEYCODE_PASTE first, then long-press + tap paste popup.
    """
    # Write text to device file via stdin pipe (no shell escaping)
    _adb_pipe(text, "cat", ">", "/sdcard/clip.txt")

    # Load from file into clipboard (two methods, one should work)
    _adb_shell("cat /sdcard/clip.txt | cmd clipboard set 2>/dev/null")
    _adb_shell('cmd clipboard set "$(cat /sdcard/clip.txt)" 2>/dev/null')
    time.sleep(0.4)

    # Method 1: KEYCODE_PASTE
    _adb("shell", "input", "keyevent", "279")
    time.sleep(0.4)

    # Quick verify — did text appear in UI?
    visible = "".join(get_texts())
    if text[:4] in visible or text[-4:] in visible:
        return

    # Method 2: long-press input field → tap "Paste" chip
    x, y = TAP_INPUT
    _adb("shell", "input", "swipe", str(x), str(y), str(x), str(y), "800")
    time.sleep(0.6)
    px, py = TAP_PASTE
    _adb("shell", "input", "tap", str(px), str(py))
    time.sleep(0.3)


# ── Core flow ──────────────────────────────────────────────────

def send_message(text):
    """Type text into Doubao and click send."""
    print(f"[*] Sending: {text[:80]}{'...' if len(text) > 80 else ''}")

    # Focus input field
    _adb("shell", "input", "tap", str(TAP_INPUT[0]), str(TAP_INPUT[1]))
    time.sleep(0.3)

    _clear_field()
    time.sleep(0.2)

    if _has_cjk(text):
        _send_chinese(text)
    else:
        _send_ascii(text)

    time.sleep(0.5)
    _adb("shell", "input", "tap", str(TAP_SEND[0]), str(TAP_SEND[1]))
    print("[*] Sent ✓")


def wait_for_response(before, timeout=TIMEOUT):
    """Poll UI until new AI response appears. Scrolls to bottom regularly."""
    for i in range(timeout):
        time.sleep(1)
        after = get_texts()
        ans = find_answer(before, after)
        if ans:
            return ans
        # Scroll to bottom every 3s so streaming content stays visible
        if i % 3 == 0 and i > 0:
            scroll_to_bottom()
            # Update baseline so scrolled-in old content isn't a false positive
            before = set(after)
        if i % 10 == 0 and i > 0:
            print(f"    ... {i}s")
    return None


def check_already_responded(texts):
    """If the message was already sent and AI responded, return the answer.

    Detects this by checking: input field empty (message sent) + long
    text node present in the message area (AI response visible).
    """
    # Check if input field is empty (hint text means no input)
    has_input = any("发消息" in t or "按住说话" in t for t in texts)
    if not has_input:
        return None  # message still being typed, not sent yet

    # Look for a long text that's likely an AI response
    skip_words = [
        "豆包", "快速", "打电话", "AI 创作", "视频通话", "相机", "返回",
        "反馈", "深度思考", "Seedance", "帮我写作", "聊聊新话题",
        "停止生成", "重新生成", "复制", "点赞", "点踩", "分享",
        "继续问", "上传", "文件", "内容由 AI 生成",
    ]
    candidates = []
    for t in texts:
        t = t.strip()
        if len(t) < 100:
            continue
        if any(w in t for w in skip_words):
            continue
        candidates.append(t)
    return max(candidates, key=len) if candidates else None


def save(question, answer, path=OUTPUT):
    data = {
        "code": 0,
        "msg": "success",
        "data": {
            "conversation_id": f"ui_cap_{int(time.time())}",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "capture_method": "ui_text_extraction",
            "conversations": [{
                "task_id": "ui_capture_task",
                "question": question,
                "mode": "browsing" if "搜索" in answer else "chat",
                "answer": answer,
            }]
        }
    }
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[*] Saved → {path}")


# ── CLI ────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        # Capture-only mode: no message arg, just grab what's on screen
        out = OUTPUT
        print("=" * 55)
        print("  Mode: Capture only (manual send)")
        print(f"  Output: {out}")
        print("=" * 55)

        print("[*] Scroll to bottom...")
        scroll_to_bottom()
        texts = get_texts()

        answer = check_already_responded(texts)
        if answer:
            print(f"\n{'─' * 50}")
            print(answer)
            print(f"{'─' * 50}\n")
            save("(manual)", answer, out)
            print("Done ✓")
        else:
            print("[!] No AI response visible on screen yet.")
            print("[!] Wait for the AI to finish replying, then re-run without args.")
        return

    msg = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else OUTPUT

    print("=" * 55)
    print(f"  Message: {msg}")
    print(f"  Output:  {out}")
    print("=" * 55)

    print("[1/4] Scroll to bottom + snapshot...")
    scroll_to_bottom()
    before = get_texts()

    # Check if message was already sent (manual mode) and AI responded
    answer = check_already_responded(before)
    if answer:
        print("\n  (AI already responded — capturing directly)\n")
        print(f"{'─' * 50}")
        print(answer)
        print(f"{'─' * 50}\n")
        save(msg, answer, out)
        print("Done ✓")
        return

    print("[2/4] Send message...")
    send_message(msg)

    print("[3/4] Wait for AI reply...")
    answer = wait_for_response(set(before))

    if answer:
        print(f"\n{'─' * 50}")
        print(answer)
        print(f"{'─' * 50}\n")
        print("[4/4] Save JSON...")
        save(msg, answer, out)
        print("Done ✓")
    else:
        print("[!] Timeout — no AI response detected.")
        print("[!] Try scrolling up in the app and re-running.")


if __name__ == "__main__":
    main()
