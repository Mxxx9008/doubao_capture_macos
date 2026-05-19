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

# UI tap targets (calibrated for 1080×1920 emulator)
TAP_INPUT  = (540, 1380)   # message input field
TAP_SEND   = (986, 1410)   # send button
TAP_PASTE  = (480, 1280)   # "Paste" popup after long-press


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
    # Prefer longest (AI responses are multi-paragraph)
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
    """Send ASCII text via `input text`."""
    safe = shlex.quote(text)
    _adb_shell(f"input text {safe}")


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
    """Poll UI until new AI response appears."""
    for i in range(timeout):
        time.sleep(1)
        after = get_texts()
        ans = find_answer(before, after)
        if ans:
            return ans
        if i % 10 == 0 and i > 0:
            print(f"    ... {i}s")
    return None


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
        print(f"Usage: python3 {sys.argv[0]} \"your question\" [output.json]")
        sys.exit(1)

    msg = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else OUTPUT

    print("=" * 55)
    print(f"  Message: {msg}")
    print(f"  Output:  {out}")
    print("=" * 55)

    print("[1/4] Snapshot UI...")
    before = get_texts()

    print("[2/4] Send message...")
    send_message(msg)

    print("[3/4] Wait for AI reply...")
    answer = wait_for_response(before)

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
