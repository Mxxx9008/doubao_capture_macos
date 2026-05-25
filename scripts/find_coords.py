#!/usr/bin/env python3
"""
Discover tap coordinates for Doubao UI on any device.
Run AFTER Doubao is open on the conversation screen.

Usage:
  python3 find_coords.py
"""

import subprocess
import os
import re
import html as _html
import json

ADB = os.path.expanduser("~/Library/Android/sdk/platform-tools/adb")


def adb_stdout(*args):
    r = subprocess.run([ADB] + list(args), capture_output=True, text=True)
    return r.stdout


def adb_shell(cmd_str):
    subprocess.run(f"{ADB} shell {cmd_str}", shell=True,
                   capture_output=True, text=True)


def dump_xml():
    """Dump screen and return raw XML."""
    subprocess.run([ADB, "shell", "uiautomator", "dump", "/sdcard/ui.xml"],
                   capture_output=True, text=True)
    return adb_stdout("shell", "cat", "/sdcard/ui.xml")


def parse_nodes(raw):
    """Parse XML, return list of (y, x_center, text, bounds, attrs)."""
    # Match full node blocks
    nodes = re.findall(
        r'<node[^>]*?text="([^"]*)"[^>]*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\][^>]*?(?:content-desc="([^"]*)")?[^>]*?(?:resource-id="([^"]*)")?[^>]*?>',
        raw
    )
    results = []
    for m in re.finditer(
        r'<node[^>]*?>',
        raw
    ):
        pass

    # Simpler approach: just get all elements with text/bounds
    elements = re.findall(
        r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]".*?text="([^"]*)"',
        raw
    )
    results = []
    for x1, y1, x2, y2, text in elements:
        t = _html.unescape(text)
        if t.strip():
            cx = (int(x1) + int(x2)) // 2
            cy = (int(y1) + int(y2)) // 2
            results.append({
                "text": t,
                "center_x": cx,
                "center_y": cy,
                "bounds": f"[{x1},{y1}][{x2},{y2}]",
                "width": int(x2) - int(x1),
                "height": int(y2) - int(y1),
            })

    # Also find elements with content-desc
    desc_elements = re.findall(
        r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]".*?content-desc="([^"]+)"',
        raw
    )
    for x1, y1, x2, y2, desc in desc_elements:
        d = _html.unescape(desc)
        if d.strip():
            cx = (int(x1) + int(x2)) // 2
            cy = (int(y1) + int(y2)) // 2
            results.append({
                "text": f"[desc] {d}",
                "center_x": cx,
                "center_y": cy,
                "bounds": f"[{x1},{y1}][{x2},{y2}]",
                "width": int(x2) - int(x1),
                "height": int(y2) - int(y1),
            })

    # Also find clickable elements (which might have empty text)
    clickable = re.findall(
        r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"[^>]*?clickable="true"[^>]*?(?:text="([^"]*)")?[^>]*?(?:content-desc="([^"]*)")?[^>]*?',
        raw
    )
    for x1, y1, x2, y2, text, desc in clickable:
        t = _html.unescape(text or "")
        d = _html.unescape(desc or "")
        label = t or d or "(no label)"
        if label.strip():
            cx = (int(x1) + int(x2)) // 2
            cy = (int(y1) + int(y2)) // 2
            results.append({
                "text": label,
                "center_x": cx,
                "center_y": cy,
                "bounds": f"[{x1},{y1}][{x2},{y2}]",
                "width": int(x2) - int(x1),
                "height": int(y2) - int(y1),
            })

    # Deduplicate by bounds
    seen = set()
    unique = []
    for r in results:
        key = r["bounds"]
        if key not in seen:
            seen.add(key)
            unique.append(r)

    return sorted(unique, key=lambda r: (r["center_y"], r["center_x"]))


def main():
    print("=" * 60)
    print("  Doubao UI Coordinate Finder")
    print("  Make sure Doubao is open on the conversation screen!")
    print("=" * 60)

    # Get screen size
    size_raw = subprocess.run([ADB, "shell", "wm", "size"],
                              capture_output=True, text=True).stdout
    print(f"\n  Screen: {size_raw.strip()}")

    raw = dump_xml()
    nodes = parse_nodes(raw)

    print(f"\n  Found {len(nodes)} labeled elements:\n")
    print(f"  {'#':<4} {'Y':<6} {'X':<6} {'W':<5} {'H':<5} {'Text'}")
    print(f"  {'-'*4} {'-'*6} {'-'*6} {'-'*5} {'-'*5} {'-'*40}")

    for i, n in enumerate(nodes):
        t = n["text"][:50]
        print(f"  {i:<4} {n['center_y']:<6} {n['center_x']:<6} "
              f"{n['width']:<5} {n['height']:<5} {t}")

    print(f"\n  {'─' * 60}")
    print("  Look for elements like:")
    print("    - '发消息' or '按住说话'  → TAP_INPUT (input field)")
    print("    - A button near the input field → TAP_SEND (send button)")
    print("    - 'Paste' or '粘贴'       → TAP_PASTE (paste popup)")
    print(f"  {'─' * 60}")

    # Save for reference
    out_path = os.path.expanduser("~/Desktop/doubao_capture/coords_debug.json")
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(nodes, f, ensure_ascii=False, indent=2)
    print(f"\n  Full dump saved → {out_path}")


if __name__ == "__main__":
    main()
