# Doubao Capture macOS

Mac + Android 设备环境下，抓取豆包 App 聊天内容并生成结构化 JSON。

**Level A (UI 文本提取)** — 已适配 Pixel 6 Pro 真机，稳定运行。

## 快速开始

```bash
# 1. 一次性初始化 uiautomator2
/tmp/u2env/bin/pip install uiautomator2
/tmp/u2env/bin/python3 -m uiautomator2 init

# 2. 确保手机已连接、豆包已打开
adb devices  # 确认设备已连接

# 3. 运行抓取
cd scripts
/tmp/u2env/bin/python3 doubao_capture.py "你的问题"

# 输出文件: ~/Desktop/doubao_capture.json
```

## 目录结构

```
doubao_capture_macos/
├── README.md
├── scripts/
│   ├── doubao_capture.py          # 主抓取脚本 (Level A, uiautomator2)
│   ├── find_coords.py             # UI 坐标探测工具
│   ├── frida_ssl_bypass_v2.js     # Java SSL Pinning 绕过 (Level B)
│   ├── frida_native_ssl_v6.js     # 原生 SSL 层监控 (Level B)
│   ├── frida_cronet_hook_v6.js    # Cronet Java 层 hook (Level B, 实验)
│   └── extract_references.py      # 从 mitmproxy 数据提取引用
├── docs/
│   ├── capture_summery.md         # 项目进度总结
│   ├── doubao_capture_mac.md      # 技术分析文档
│   └── doubao_capture_usage.md    # 详细使用说明
└── output/
    └── doubao_news_capture.json   # 抓取结果示例
```

## 已支持的设备

| 设备 | 状态 | 备注 |
|------|------|------|
| Pixel 6 Pro (Android 16) | 已验证 | 真机，主力测试设备 |
| Android 模拟器 | 已验证 | ARM64, Android 13+ |

## 已验证的问答类型

| 类型 | 示例 | 输出 |
|------|------|------|
| 短回答 | `7乘8等于几` | `7×8=56` |
| 英文 | `What is the capital of Japan?` | `Tokyo` |
| 知识问答 | `地球的直径是多少` | 详细数据 |
| 搜索模式 | `2025年诺贝尔物理学奖得主是谁` | 完整信息+来源 |

## 环境要求

- macOS
- Android 设备 (真机或模拟器)
- Python 3.10+
- uiautomator2
- ADB

## 工作原理

### Level A: UI 文本提取 (当前方案)

通过 `uiautomator2.dump_hierarchy()` 实时读取屏幕 UI 树，检测新出现的 AI 回复文本。每次运行前重启 App 确保视图状态干净，过滤流式输出光标 ⚫ 和搜索状态文字。

### Level B: 网络层抓取 (进行中)

豆包使用字节跳动自研网络栈（`libttboringssl.so` + `libsscronet.so`）走 QUIC/HTTP3 协议，传统 TLS 中间人方案无法解密 Chat API。详见 `docs/capture_summery.md`。

## 踩坑记录

1. **ADB `uiautomator dump` 数据过期** — Pixel 6 Pro 上返回缓存数据，切到 uiautomator2 API 解决
2. **RecyclerView 不刷新** — 多次运行后视图卡死，每次捕获前 `force-stop` + 重启 App
3. **自定义 ChatInputText** — 标准 `adb input text` 无效，必须用 uiautomator2 的 `set_text`
