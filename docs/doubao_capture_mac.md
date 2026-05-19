# 豆包抓包项目 — Mac 端总结

> 更新时间: 2026-05-19 17:10

## 一、项目目标

在 Mac + Android 模拟器上抓取豆包 App 的 Chat API 明文数据，生成结构化 JSON 文件。

## 二、环境

| 组件 | 版本/配置 |
|------|----------|
| 系统 | macOS (Apple Silicon) |
| 模拟器 | Android Studio AVD — `doubao13` (Pixel 6 Pro, Android 13, ARM64) |
| ADB | `~/Library/Android/sdk/platform-tools/adb` |
| Frida | 16.5.9 (Python + frida-server) |
| mitmproxy | mitmdump 8081 |
| 豆包 App | com.larus.nova v13.3.0 |

## 三、整体进度

```
████████████████░░  80%

已完成 ✅                          未解决 ❌
├── 环境搭建 ✅                    ├── 原生 QUIC 层明文抓取 ❌
├── Frida 注入 ✅                  └── 中文输入自动化 ❌（手动输入解决）
├── Java SSL Pinning 绕过 ✅
├── TNC 配置 API 抓取 ✅
├── Chat API 通路确认 ✅
├── AI 回复文本抓取 ✅
├── JSON 文件生成 ✅
└── 端到端流程 ✅
```

## 四、已解决的关键问题

### 4.1 模拟器无窗口（Headless）
- **问题**: 模拟器以 `-no-window` 启动，看不到界面
- **解决**: 安装 scrcpy (`brew install scrcpy`) 投屏；或从 Android Studio Device Manager 启动 GUI 版本

### 4.2 代理残留导致网络不通
- **问题**: 模拟器设了代理 `10.0.2.2:8080` 但代理服务没运行，登录/请求全部卡住
- **解决**: `adb shell settings put global http_proxy :0` 清除代理

### 4.3 豆包网络架构分析
```
TNC 配置 API  ──► libssl.so (系统 OpenSSL) ──► TCP+TLS ──► 可直接抓明文 ✅
Chat API      ──► libttboringssl.so + libsscronet.so ──► QUIC/HTTP3 ──► 抓取受阻 ❌
```

关键发现：
- **libttboringssl.so**: 字节跳动 fork 的 BoringSSL，内置 QUIC 支持（`SSL_provide_quic_data`、`SSL_set_quic_method` 等）
- **libsscronet.so**: 字节跳动 fork 的 Cronet，0 个标准 SSL 函数，使用 `TTQuicHe_*` 系列 QUIC HTTP 接口
- Java 层 Cronet 类位于 `com.ttnet.org.chromium.net.*`（非标准 `org.chromium.net.*`）

### 4.4 原生 SSL 层抓取失败
- **尝试**: Hook `libttboringssl.so` 的 `SSL_read`/`SSL_write`
- **结果**: 能捕获到 QUIC 流量（1603 次事件），但 buffer 数据全为零
- **原因**: 字节跳动 BoringSSL fork 的 QUIC 模式下，`SSL_read`/`SSL_write` 只处理握手 CRYPTO 帧，应用数据走不同的内存路径，Frida 无法通过标准 API 读取

已尝试的 hook 方案：
| 版本 | 方法 | 结果 |
|------|------|------|
| v1-v3 | SSL_read/SSL_write onLeave | 部分可读，大部分零 |
| v4 | 添加可读性过滤 | libttboringssl 无输出 |
| v5 | 取消过滤，全量输出 | 零值数据 |
| v6 | SSL_write onEnter + SSL_read onLeave | 仍然全零 |
| Cronet v1-v6 | onReadCompleted / UrlRequest.read / CronetInputStream | 均未触发 |

### 4.5 Java Cronet 层 hook 未触发
- 尝试 hook `CronetBidirectionalStream.onReadCompleted(ByteBuffer, int, int, int, long)`
- 尝试 hook `UrlRequest.read(ByteBuffer)`
- 尝试 hook `CronetHttpURLConnection.getInputStream()`
- 尝试 hook `okhttp3.ResponseBody.string()`
- **结果**: 所有 hook 均未触发，chat API 不走这些 Java 层路径

### 4.6 adb 中文输入限制
- `adb shell input text` 不支持中文
- 剪贴板粘贴 (`KEYCODE_PASTE`) 不生效
- **当前方案**: 手动在模拟器输入中文

## 五、当前可用的抓包方案

### 方案 A: UI 文本抓取（当前使用）

**原理**: 通过 `uiautomator dump` 读取屏幕上显示的 AI 回复文本

**流程**:
1. 启动模拟器和豆包 App
2. 手动在输入框输入问题并发送
3. Python 脚本轮询 UI XML，检测新的 AI 回复
4. 解析 HTML entities，生成 JSON

**优点**: 可靠，不受 QUIC/SSL 层限制
**缺点**: 
- 只能抓到屏幕上可见的文本（需滚动）
- 无法获取原始 API 结构化数据（search_sources、keywords 等）
- 依赖 UI 渲染，非实时流式

**脚本**: `/tmp/mobile-doubao-capture/capture_and_json.py`

### 方案 B: mitmproxy 中间人（仅 TNC 配置 API）

**原理**: 对走标准 TLS 的 API（如 tnc0-alisc1.zijieapi.com），mitmproxy 可以直接解密

**适用于**: TNC 配置同步等非聊天 API
**不适用于**: 聊天 API（走 QUIC/HTTP3）

## 六、关键文件

| 文件 | 用途 |
|------|------|
| `frida_ssl_bypass_v2.js` | Java SSL Pinning 绕过（稳定，必用） |
| `frida_native_ssl_v6.js` | 原生 SSL_read/SSL_write hook（监控用） |
| `frida_cronet_hook_v6.js` | Cronet Java 层 hook（未成功触发） |
| `frida_dump_exports.js` | 导出符号分析（一次性诊断） |
| `capture_and_json.py` | UI 文本抓取 + JSON 生成 |
| `doubao_news_capture.json` | 最新抓取结果（桌面） |

## 七、环境维护

```bash
# 启动模拟器（Android Studio Device Manager → doubao13 ▶️）

# 确认连接
~/Library/Android/sdk/platform-tools/adb devices

# 启动 frida-server
~/Library/Android/sdk/platform-tools/adb root
~/Library/Android/sdk/platform-tools/adb shell "/data/local/tmp/frida-server &"

# 确保无代理残留
~/Library/Android/sdk/platform-tools/adb shell "settings put global http_proxy :0"

# 确保无 iptables 阻断
~/Library/Android/sdk/platform-tools/adb shell "iptables -F OUTPUT; ip6tables -F OUTPUT"

# Attach Frida（监控用）
cd /tmp/mobile-doubao-capture
frida -U com.larus.nova -l frida_ssl_bypass_v2.js -l frida_native_ssl_v6.js

# 运行抓包脚本
python3 capture_and_json.py "你的问题"
```

## 八、后续可能的改进方向

1. **ProtoBuf 反序列化层 hook**: 找到豆包内部 protobuf 反序列化类，hook 后直接拿结构化数据
2. **Frida Gadget 注入重打包**: 获取更早的注入时机，可能绕过 QUIC 限制
3. **Charles/Burp + HTTP3 代理**: 等工具成熟后直接中间人 QUIC
4. **模拟器网络层抓包**: 在 emulator 的 qemu 网卡层 tcpdump，配合 QUIC 解密工具
5. **自动化中文输入**: 使用 `am broadcast` 或自定义 IME 实现中文自动输入

## 九、关键教训

- **字节跳动的网络栈高度定制**: BoringSSL fork、Cronet fork、QUIC/HTTP3，标准 Android 抓包手段全部失效
- **Java 层 hook 不一定覆盖原生网络栈**: Chat API 从网络到 UI 可能几乎全在 native 层，Java 回调仅用于最终渲染
- **adb input text 局限性**: 不支持中文、空格需 `%s` 编码、不同 Android 版本表现不一致
- **模拟器状态管理**: 代理残留、iptables 规则会累积，每次测试前最好确认环境干净
