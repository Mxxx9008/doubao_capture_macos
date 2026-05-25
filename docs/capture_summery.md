# 豆包抓包项目进度总结

> 更新时间: 2026-05-19 15:50

## 总体进度

```
████████░░░░░░░░░░░  40%

已解决 ✅                          未解决 ❌
├── Frida 注入 ✅                  ├── Chat API 明文抓取 ❌ ← 当前卡点
├── Java SSL Pinning 绕过 ✅       
├── TNC 配置 API 抓取 ✅          
├── mitmproxy 中间人代理 ✅        
├── 原生 SSL hook 安装 ✅          
└── 网络层 UDP/QUIC 阻断 ✅        
```

## 一、已解决的问题

### 1. Frida 注入 ✅
- **状态**: 完全正常
- **方案**: `frida -U -f com.larus.nova` spawn 模式，配合 `frida-server` 在模拟器内运行
- **版本**: frida 16.5.9, Android ARM64 模拟器

### 2. Java 层 SSL Pinning 绕过 ✅
- **状态**: 完全正常
- **脚本**: `frida_ssl_bypass_v2.js`
- **原理**: Hook `com.android.org.conscrypt.TrustManagerImpl.verifyChain` — 直接返回 untrustedChain，不验证证书
- **验证**: 日志显示 `verifyChain bypassed for: tnc0-alisc1.zijieapi.com`

### 3. TNC 配置 API 抓取 ✅
- **状态**: 完全正常
- **路径**: `tnc0-alisc1.zijieapi.com:443` → 标准 `libssl.so` (Android 系统 OpenSSL)
- **明文内容**: HTTP/1.1 GET/POST 请求和响应，JSON 格式的 TNC 配置数据
- **捕获方式**: Native hook `SSL_read`/`SSL_write` 在 `libssl.so`

### 4. mitmproxy 代理 ✅
- **状态**: 正常运行在 Mac 上，端口 8081
- **CA 证书**: 已安装到模拟器 `/system/etc/security/cacerts/c8750f0d.0`

### 5. Native SSL Hook 安装 ✅
- **状态**: 所有三个 SSL 库均已成功 hook
  - `libssl.so`: 2 个函数 (SSL_read, SSL_write) — **可捕获明文**
  - `libttboringssl.so`: 2 个函数 (SSL_read, SSL_write) — **捕获到数据但全为零**
  - `libsscronet.so`: 0 个函数 — 不使用标准 SSL API

### 6. 网络层阻断 ✅
- **iptables 规则已生效**:
  - IPv4 UDP 443 → DROP（阻断 QUIC/UDP）
  - IPv6 TCP 443 → DROP（强制走 IPv4）
  - IPv6 UDP 443 → DROP（阻断 IPv6 QUIC）

---

## 二、当前卡点：Chat API 明文抓取 ❌

### 问题描述

豆包的 Chat API (`frontier-audio-q-lq.doubao.com`) 使用了**字节跳动自研的网络栈**，不走标准 TLS：

```
┌─────────────────────────────────────────────────┐
│ 豆包网络架构                                      │
├─────────────────────────────────────────────────┤
│ TNC 配置 API  ──► libssl.so ──► 可抓取 ✅        │
│ Chat API      ──► libttboringssl.so + libsscronet.so │
│                  └── QUIC/HTTP3 协议 ❌            │
└─────────────────────────────────────────────────┘
```

### 深入分析

#### libttboringssl.so 导出符号分析
这个库是字节跳动 fork 的 BoringSSL，包含大量 QUIC 相关函数：

```
SSL_provide_quic_data          ← 向 QUIC 连接喂入数据
SSL_set_quic_method             ← 设置 QUIC 方法表
SSL_quic_read_level             ← QUIC 读级别
SSL_quic_write_level            ← QUIC 写级别
SSL_process_quic_post_handshake ← QUIC 握手后处理
_ZN4bssl17SSL_apply_handoffE... ← bssl 命名空间的自定义函数
```

**关键发现**: `SSL_read` 和 `SSL_write` 在 QUIC 模式下只处理握手阶段的 CRYPTO 帧，**不处理应用数据**。

#### 捕获到的 libttboringssl.so 数据
```
SSL_write  1729 bytes → [全零]  ← QUIC Initial 包（ClientHello 嵌入在 CRYPTO 帧中）
SSL_read   337 bytes  → [全零]  ← QUIC Handshake 包（ServerHello）
SSL_write  175 bytes  → [全零]  ← QUIC Handshake 包（Client Finished）
SSL_read   248 bytes  → [全零]  ← QUIC Handshake 包（Server Finished）
```

- 数据大小（1729→337→175→248）是典型的 TLS 1.3 握手大小
- 数据全为零：因为 BoringSSL 的 QUIC 模式下，缓冲区管理方式不同，应用层明文不经过 SSL_read/SSL_write
- 握手重复 3 次：说明连接在重试（可能是因为 UDP 被阻断后不断重试 QUIC 连接）

#### libsscronet.so 分析
- 0 个 SSL_read/SSL_write 函数——完全不使用标准 SSL API
- 包含 `TTQuicHe_HttpInfo_*` 系列函数：这是字节跳动在 Cronet 基础上的 QUIC HTTP 层封装
- Chat 的实际 HTTP 数据走的是 Cronet → QUIC stream 路径

### 为什么阻断 QUIC 没有用

即使阻断了 UDP 443 和 IPv6 443，`libttboringssl.so` 的行为仍然是：
- 不断尝试 QUIC 握手（日志中 3 次重复的 1729→337→175→248 模式）
- **没有回退到 TCP+TLS**：字节跳动的 Cronet fork 可能不支持或未启用 TCP 回退
- 或者回退后的路径仍然使用了 QUIC-over-TCP（谷歌 QUIC 确实支持 TCP fallback）

---

## 三、可能的解决方案

### 方案 A: Hook Cronet Java 回调层 ⭐ 推荐

Cronet 的 `UrlRequest.Callback` 在 Java 层暴露了 `onReadCompleted(ByteBuffer)` 回调，此时数据已是**明文**。

```
需要 Hook 的类:
- org.chromium.net.impl.CronetUrlRequest
- org.chromium.net.UrlRequest.Callback
  - onReadCompleted(UrlRequest, UrlResponseInfo, ByteBuffer) ← 明文在这里
  - onSucceeded(UrlRequest, UrlResponseInfo)
```

**优点**: 不需要管 QUIC/TLS 底层，直接在应用层拿明文
**风险**: 字节跳动可能自定义了 Cronet 的 Java 类名

### 方案 B: Frida Gadget 注入 + 重打包 APK

将 frida-gadget.so 注入豆包 APK，重打包后安装。这样可以：
- 获得更早的注入时机
- 使用 `Java.registerClass()` 创建自定义 TrustManager
- Watcher 方式更稳定

**优点**: 注入时机更早，可能捕获更多数据
**风险**: 豆包可能有签名校验/反篡改；重打包复杂

### 方案 C: 分析 libsscronet.so 内部函数

找到 `TTQuicHe_HttpInfo_resp_recv_get` 等函数的调用链，hook 内部的 HTTP response body 处理函数。

**优点**: 不依赖 Java 层，更底层
**风险**: 逆向工程工作量大，需要分析 ARM64 汇编

### 方案 D: 魔改 mitmproxy 支持 QUIC

使用支持 QUIC/HTTP3 的代理（如 mitmproxy 11+ 实验性支持），直接中间人解密 QUIC 流量。

**风险**: mitmproxy 的 QUIC 支持不成熟；需要处理证书信任问题

---

## 四、当前环境状态

| 组件 | 状态 | 位置 |
|------|------|------|
| ADB 连接 | ✅ emulator-5554 | `~/Library/Android/sdk/platform-tools/adb` |
| frida-server | ✅ 运行中 | 模拟器 `/data/local/tmp/frida-server` |
| mitmdump | ✅ 端口 8081 | Mac 本地 |
| Frida 注入 | ✅ spawn 模式 | `frida_ssl_bypass_v2.js` + `frida_native_ssl_v6.js` |
| iptables | ✅ UDP 443 DROP | IPv4 + IPv6 |

## 五、关键文件

| 文件 | 用途 |
|------|------|
| `frida_ssl_bypass_v2.js` | Java SSL Pinning 绕过（稳定） |
| `frida_native_ssl_v6.js` | Native SSL_read/SSL_write hook（当前版本） |
| `capture.mitm` | mitmproxy 捕获文件 |
| `doubao_conv_*.json` | 已提取的对话 JSON（来自之前的会话） |

---

## 六、下一步行动

1. **立即执行**：尝试方案 A — 编写 Java 层 Cronet `onReadCompleted` hook
2. **备选**：如果 Java hook 找不到 Cronet 类，尝试方案 B（Gadget 注入）
3. **长期**：方案 C 需要独立逆向分析
