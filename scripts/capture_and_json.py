#!/usr/bin/env python3
"""Capture Doubao chat by reading UI + extract JSON."""
import subprocess, time, json, os, re, sys

ADB = os.path.expanduser("~/Library/Android/sdk/platform-tools/adb")

def adb(cmd):
    return subprocess.run(f"{ADB} {cmd}", shell=True, capture_output=True, text=True)

def get_ui_text():
    """Dump UI XML and extract all text content."""
    adb("shell uiautomator dump /sdcard/ui.xml")
    result = adb("shell cat /sdcard/ui.xml")
    texts = re.findall(r'text="([^"]*)"', result.stdout)
    return [t for t in texts if t]

def find_new_response(prev_texts, new_texts):
    """Find AI response that wasn't in previous texts."""
    prev_set = set(prev_texts)
    for t in new_texts:
        t_clean = t.strip()
        if t_clean and t_clean not in prev_set and len(t_clean) > 3:
            # Skip known UI elements
            skip = ["豆包", "内容由 AI 生成", "快速", "打电话", "AI 创作", "视频通话",
                    "发消息或按住说话...", "相机", "返回", "反馈", "深度思考",
                    "Seedance", "帮我写作", "聊聊新话题"]
            if any(s in t_clean for s in skip):
                continue
            # Skip suggestions (short phrases)
            if len(t_clean) < 10 and "问" not in t_clean:
                continue
            return t_clean
    return None

def send_message(text):
    """Send a message through the Doubao chat UI."""
    # Tap input field
    adb(f"shell input tap 540 1400")
    time.sleep(0.3)
    # Clear
    for _ in range(5):
        adb("shell input keyevent 123")
        time.sleep(0.1)
        adb("shell input keyevent 67")
        time.sleep(0.1)
    time.sleep(0.3)
    # Use clipboard for Chinese, input text for English
    if any('一' <= c <= '鿿' for c in text):
        # Chinese - use clipboard
        escaped = text.replace("'", "'\\''")
        adb(f"shell 'cmd clipboard set \"{escaped}\"'")
        time.sleep(0.3)
        adb("shell input keyevent 279")  # PASTE
    else:
        # English
        adb(f"shell input text '{text}'")
    time.sleep(0.5)
    # Tap send button
    adb("shell input tap 986 1406")
    print(f"[*] Sent: {text}")

def wait_for_response(texts_before, timeout=30):
    """Wait for AI response to appear."""
    for _ in range(timeout):
        time.sleep(1)
        current = get_ui_text()
        resp = find_new_response(texts_before, current)
        if resp:
            return resp
    return None

def save_json(user_msg, ai_response, output_path):
    """Save conversation as JSON."""
    data = {
        "conversation": [{
            "user": user_msg,
            "assistant": ai_response
        }],
        "captured_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "method": "ui_text_capture"
    }
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[*] Saved to {output_path}")

if __name__ == "__main__":
    msg = sys.argv[1] if len(sys.argv) > 1 else "今天有哪些大新闻"
    output = os.path.expanduser("~/Desktop/doubao_capture.json")

    print(f"[*] Message: {msg}")
    before = get_ui_text()
    send_message(msg)
    print("[*] Waiting for response...")
    response = wait_for_response(before, timeout=30)

    if response:
        # Clean HTML entities
        response = response.replace("&#10;", "\n").replace("&#128518;", "😆")
        response = response.replace("&#128512;", "😀").replace("&#128513;", "😁")
        print(f"[*] Response:\n{response}")
        save_json(msg, response, output)
    else:
        print("[!] No response captured within timeout")
