# Doubao Capture macOS

Mac + Android 模拟器环境下，抓取豆包 App Chat API 数据并生成结构化 JSON。

## 快速开始

```bash
# 1. 确保模拟器已启动、豆包已登录
adb devices  # 确认 emulator-5554 已连接

# 2. 启动 frida-server
adb root && adb shell "/data/local/tmp/frida-server &"

# 3. 清除代理残留
adb shell "settings put global http_proxy :0"

# 4. 在模拟器中输入问题并发送（支持中文，手动输入）

# 5. 抓取回复
cd scripts
python3 capture_and_json.py "你今天问了什么问题"
```

## 目录结构

```
doubao_capture_macos/
├── README.md
├── scripts/
│   ├── frida_ssl_bypass_v2.js    # Java SSL Pinning 绕过（必须）
│   ├── frida_native_ssl_v6.js    # 原生 SSL 层监控（诊断用）
│   ├── frida_cronet_hook_v6.js   # Cronet Java 层 hook（实验性）
│   ├── capture_and_json.py       # 主抓包脚本
│   └── extract_references.py     # 从 mitmproxy 数据提取引用
├── docs/
│   ├── doubao_capture_mac.md     # 项目总结
│   └── doubao_capture_usage.md   # 使用说明
└── output/
    └── doubao_news_capture.json  # 抓取结果示例
```

## 环境要求

- macOS (Apple Silicon)
- Android 模拟器 (Android 13+, ARM64)
- Frida 16.5.9
- Python 3.10+
- ADB

## 工作原理

豆包使用字节跳动自研网络栈（`libttboringssl.so` + `libsscronet.so`）走 QUIC/HTTP3 协议。传统 TLS 中间人方案无法解密。

本项目采用 **UI 文本抓取** 方案：通过 `uiautomator dump` 定期读取屏幕 UI 树，检测并提取 AI 回复文本，生成 JSON 文件。

详细技术分析见 `docs/doubao_capture_mac.md`。
