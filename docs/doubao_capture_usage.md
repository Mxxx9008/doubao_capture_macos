# 豆包抓包工具 — 使用说明

> 适用环境: Mac + Android 模拟器

## 一、初次配置

### 1.1 安装依赖

```bash
# ADB（如未安装）
brew install --cask android-platform-tools

# Frida
pip install frida-tools

# scrcpy（投屏工具，可选）
brew install scrcpy
```

### 1.2 模拟器

在 Android Studio → Device Manager 中创建或导入 AVD（Android 13+，ARM64）。

### 1.3 推送 frida-server

```bash
# 下载对应架构的 frida-server（版本必须和 pip show frida 一致）
# 以 frida 16.5.9 + android-arm64 为例
unxz frida-server-16.5.9-android-arm64.xz
adb push frida-server-16.5.9-android-arm64 /data/local/tmp/frida-server
adb shell "chmod 755 /data/local/tmp/frida-server"
```

### 1.4 安装豆包 App

将豆包 APK 拖入模拟器窗口安装，或：

```bash
adb install doubao.apk
```

## 二、每次抓包流程

### 步骤 1: 启动模拟器

Android Studio → Device Manager → 找到 `doubao13` → 点 ▶️ 启动。

### 步骤 2: 确认连接 + 清理环境

```bash
# 确认设备已连接
adb devices
# 应显示: emulator-5554  device

# 清除可能残留的代理
adb shell "settings put global http_proxy :0"

# 清除可能残留的防火墙规则
adb root
adb shell "iptables -F OUTPUT; ip6tables -F OUTPUT"
```

### 步骤 3: 启动 frida-server

```bash
adb root
adb shell "/data/local/tmp/frida-server &"
```

### 步骤 4: 启动豆包并登录

在模拟器中打开豆包 App，完成登录（首次使用需要手机号 + 验证码）。

### 步骤 5: 附加 Frida（可选，监控用）

```bash
cd /tmp/mobile-doubao-capture
frida -U com.larus.nova -l frida_ssl_bypass_v2.js -l frida_native_ssl_v6.js
```

按 `Ctrl+C` 停止监控。

### 步骤 6: 发送问题并抓取回复

**方式一: 手动输入（推荐，支持中文）**

在模拟器豆包输入框中输入问题 → 点击发送 → 运行：

```bash
cd /tmp/mobile-doubao-capture
python3 capture_and_json.py "你的问题（此处仅作标识用）"
```

脚本会轮询屏幕 UI 变化，检测到 AI 回复后生成 JSON 到桌面。

**方式二: 自动输入英文**

```bash
cd /tmp/mobile-doubao-capture
python3 capture_and_json.py "What is the latest tech news today"
```

### 步骤 7: 获取结果

JSON 文件默认生成在 `~/Desktop/doubao_capture.json`。

如需自定义输出路径：

```bash
python3 capture_and_json.py "你的问题" > output.json
```

或者修改脚本中的 `output` 变量。

## 三、工具脚本说明

| 脚本 | 作用 |
|------|------|
| `frida_ssl_bypass_v2.js` | 绕过 Java 层 SSL 证书校验（必须加载） |
| `frida_native_ssl_v6.js` | 监控原生 SSL 层流量（可选，诊断用） |
| `capture_and_json.py` | 主抓包脚本：发送消息 + 抓取回复 + 生成 JSON |

## 四、常见问题

### Q1: 模拟器没有窗口？

模拟器可能以 headless 模式启动。两种解决方式：

```bash
# 方式 A: 用 scrcpy 投屏
scrcpy

# 方式 B: 从 Android Studio Device Manager 重新启动（GUI 模式）
```

### Q2: 豆包登录一直转圈 / 网络不可用？

代理残留导致：

```bash
adb shell "settings put global http_proxy :0"
```

### Q3: 中文输入不了？

`adb shell input text` 不支持中文。目前需要手动在模拟器输入中文。

### Q4: 抓到的回复被截断？

UI XML 只能抓到屏幕可见范围内的文本。长回复需要滚动：

```bash
# 向上滚动查看更多
adb shell input swipe 540 1000 540 400 500
# 再次 dump 获取
adb shell uiautomator dump /sdcard/ui.xml
adb shell cat /sdcard/ui.xml
```

### Q5: Frida 附加时报 "unable to find process"？

```bash
# 确认进程名
adb shell "ps -A | grep larus"
# 应该看到 com.larus.nova

# 如果进程不存在，先手动打开豆包 App

# 如果进程存在，尝试通过 PID 附加
adb shell "pidof com.larus.nova"
frida -U -p <PID> -l frida_ssl_bypass_v2.js
```

### Q6: Frida spawn 模式报错 "timed out"？

spawn 模式（`-f` 参数）在部分 Android 版本不稳定，改用 attach 模式（不加 `-f`）：

```bash
# 先手动打开豆包 App，然后：
frida -U com.larus.nova -l frida_ssl_bypass_v2.js
```

## 五、生成 JSON 格式

```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "conversation_id": "ui_capture_1747645200",
    "created_at": "2026-05-19T17:00:00",
    "capture_method": "ui_text_extraction",
    "conversations": [
      {
        "task_id": "ui_capture_task",
        "question": "今天有哪些大新闻",
        "mode": "browsing",
        "answer": "AI 回复的完整文本..."
      }
    ]
  }
}
```

> 注意: 当前方案抓取的是 UI 层的渲染文本，不包含原始 API 返回的 search_sources、keywords 等结构化字段。如需完整 API JSON，需要攻克 QUIC 层抓包（见项目总结文档）。
