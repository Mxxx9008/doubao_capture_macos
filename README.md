# Doubao Capture macOS

Mac + Android 设备环境下，抓取豆包 App 聊天内容并生成结构化 JSON。

## 快速开始

```bash
# 1. 一次性初始化
pip install uiautomator2
python3 -m uiautomator2 init

# 2. 手机已连接 + USB 调试开启
adb devices

# 3. 文本抓取
cd ~/Desktop/doubao_capture
python3 doubao_capture.py "你的问题"

# 4. 文本 + URL 抓取 (需要 Frida + root)
python3 doubao_capture.py "你的问题" --frida

# 输出: ~/Desktop/doubao_capture.json
```

## 功能矩阵

| 功能 | 手机 (Pixel 6 Pro) | 模拟器 |
|------|-------------------|--------|
| AI 回答文本 | ✅ | ✅ |
| 搜索关键词 | ✅ | ✅ |
| 参考来源标题 + 站点名 | ✅ | ✅ |
| 参考来源 URL | ✅ (`--frida`) | ✅ (`--frida`) |
| 参考内容 Summary | ❌ | ❌ |

## 目录结构

```
doubao_capture/
├── README.md
├── doubao_capture.py              # 主抓取脚本
├── find_coords.py                 # UI 坐标探测工具
├── extract_references.py          # 参考数据提取
├── frida_ssl_bypass_v2.js         # Java SSL Pinning 绕过
├── frida_native_ssl_v6.js         # 原生 SSL 层监控
├── frida_cronet_hook_v6.js        # Cronet Java 层 hook
├── docs/
│   ├── capture_summery.md         # 项目进度总结
│   ├── doubao_capture_usage.md    # 详细使用说明
│   └── doubao_capture_mac.md      # 技术分析文档
└── output/
    └── doubao_news_capture.json   # 抓取结果示例
```

## CLI

```bash
# 文本抓取 (Level A) — 手机/模拟器通用
python3 doubao_capture.py "你的问题"

# URL 抓取 (Level B) — 手机/模拟器通用，需 Frida
python3 doubao_capture.py "你的问题" --frida

# 仅抓取当前屏幕（不发消息）
python3 doubao_capture.py
```

## 输出格式

```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "question": "今天科技圈有什么大新闻",
    "search_summary": "搜索 2 个关键词，参考 12 篇资料",
    "search_keywords": ["AI芯片", "科技新闻"],
    "search_sources": [
      {
        "title": "估值近万亿，AI 巨头 Anthropic 完成最后一轮私募融资_环球网",
        "url": "",
        "sitename": "环球网",
        "summary": ""
      }
    ],
    "answer": "5月29日 科技圈重磅大新闻...",
    "total_references": 12
  }
}
```

## 环境要求

- macOS
- Python 3.10+
- ADB + uiautomator2
- Android 设备 (真机或模拟器)

## 工作原理

### Level A: UI 文本提取

通过 `uiautomator2.dump_hierarchy()` 读取屏幕 UI 树，检测 AI 回复文本，展开参考卡片获取标题和站点名。每次运行前重启 App 确保干净状态。

### Level B: Frida WebView URL 抓取

Frida hook `android.webkit.WebView.loadUrl()` 拦截参考链接的 URL。模拟器上已验证 100% 可靠。手机版 Doubao UI 不同，参考卡片为内联 `[__LINK_ICON]` 标记，暂不支持。

## 踩坑记录

1. **ADB `uiautomator dump` 数据过期** — Pixel 6 Pro 上返回缓存数据，切 uiautomator2 API 解决
2. **RecyclerView 回收** — 参考区被回收导致 `search_sources` 为空，修复为先抓参考再打印长文本
3. **锁屏干扰** — 抓取过程手机自动锁屏，加入 `wm dismiss-keyguard` 自动解除
4. **系统通知误判** — "正在充电"等通知被误认为 AI 回复，加最小 80 字符过滤
5. **手机/模拟器 UI 差异** — 不同版本 Doubao 的 resource ID 和参考区布局不同
6. **Frida spawn 被反检测** — 改用 monkey 启动 + PID attach 方式挂载
7. **uiautomator2 swipe 不可靠** — Doubao 上 `d.swipe()` 经常不生效，改用 `adb shell input swipe`
8. **uiautomator2 press("back") 不可靠** — 改用 `adb shell input keyevent 4`
9. **RecyclerView exists/click 竞态** — 检查元素存在后点击时已被回收，改为先读坐标再用 ADB tap
10. **WebView 返回后参考区丢失** — HOME + monkey 恢复 ChatActivity，不杀进程保持 Frida 挂载
