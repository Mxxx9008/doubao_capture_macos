# 豆包抓包工具 — 使用说明

> 适用环境: Mac + Android 真机 或 模拟器

## 一、初次配置

### 1.1 安装依赖

```bash
# uiautomator2 (Python 自动化)
pip install uiautomator2

# ADB (如未安装)
brew install --cask android-platform-tools

# Frida (可选，仅 URL 抓取需要)
pip install frida-tools
```

### 1.2 初始化 uiautomator2

```bash
python3 -m uiautomator2 init
```

### 1.3 设备准备

**真机 (Pixel 6 Pro)**:
- 已 root (Magisk)，frida-server 已在 `/data/local/tmp/frida-server-17`
- USB 调试已开启，`adb devices` 可识别

**模拟器**:
- Android Studio AVD，ARM64，Android 13+

## 二、抓取流程

### 文本抓取 (Level A) — 手机/模拟器通用

```bash
cd ~/Desktop/doubao_capture
python3 doubao_capture.py "你的问题"
```

输出: `~/Desktop/doubao_capture.json`

抓取内容:
- `answer` — AI 回答全文
- `search_summary` — "搜索 X 个关键词，参考 Y 篇资料"
- `search_sources[].title` — 参考来源标题
- `search_sources[].sitename` — 来源站点名
- `total_references` — 参考资料总数
- `search_keywords` — 搜索关键词

### URL 抓取 (Level B) — 仅模拟器

```bash
# 1. 修改 DEVICE 为模拟器
# 编辑 doubao_capture.py: DEVICE = "emulator-5554"

# 2. 运行
python3 doubao_capture.py "你的问题" --frida
```

`--frida` 模式会额外填充 `search_sources[].url`。

### 仅抓取当前屏幕（不发消息）

```bash
python3 doubao_capture.py
```

读取当前屏幕已有的 AI 回复。

## 三、输出格式

```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "task_id": "9f93cea9a807",
    "question": "今天科技圈有什么大新闻",
    "mode": "quick",
    "search_keywords": ["AI芯片", "科技新闻"],
    "search_sources": [
      {
        "title": "估值近万亿，AI 巨头 Anthropic 完成最后一轮私募融资_环球网",
        "url": "",
        "sitename": "环球网",
        "summary": ""
      }
    ],
    "search_summary": "搜索 2 个关键词，参考 12 篇资料",
    "answer": "5月29日 科技圈重磅大新闻...",
    "total_references": 12
  }
}
```

## 四、常见问题

### Q1: 报错 "EditText not found"

手机锁屏了。脚本已内置自动解锁，如果仍失败：

```bash
adb -s DEVICE_ID shell wm dismiss-keyguard
adb -s DEVICE_ID shell input swipe 540 2900 540 100 500
```

### Q2: 抓到的 search_sources 为空

参考区被 RecyclerView 回收了。已修复（先抓参考再打印长文本）。如果仍出现，可能是网络慢导致参考还没加载完。

### Q3: Frida 挂载失败 "Process terminated"

手机版 Doubao 可能有反 Frida 检测。已改用 PID 挂载方式（`-p PID` 而非 `-f` 或 `-n`）。

### Q4: 切换到不同设备

编辑 `doubao_capture.py` 第 35 行:
```python
DEVICE = "19161FDEE0J82D"   # Pixel 6 Pro
# DEVICE = "emulator-5554"  # 模拟器
```

## 五、脚本说明

| 脚本 | 作用 |
|------|------|
| `doubao_capture.py` | 主脚本：发消息 + 等回复 + 展开参考 + 生成 JSON |
| `/tmp/frida_webview_url_v2.js` | Frida WebView URL hook（Level B 使用） |

## 六、设备兼容性

| 功能 | Pixel 6 Pro | 模拟器 |
|------|------------|--------|
| 文本提取 | ✅ | ✅ |
| 参考标题 + sitename | ✅ | ✅ |
| URL 抓取 (--frida) | ❌ | ✅ |
| Frida 挂载 | ✅ (PID) | ✅ (spawn) |
