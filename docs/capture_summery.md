# 豆包抓包项目进度总结

> 更新时间: 2026-05-29

## 总体进度

```
████████████████░░░░  80%

已解决 ✅                              部分解决 ⚠️
├── UI 文本提取 ✅                    ├── URL 抓取（模拟器 ✅ / 手机 ❌）
├── 参考来源标题 + sitename ✅        ├── 参考内容 summary ❌
├── Frida WebView.loadUrl Hook ✅      └── 手机物理设备 Frida 挂载 ✅
├── Frida PID 挂载 (Android 16) ✅
├── uiautomator2 自动化 ✅
├── 搜索关键词 + 参考资料数 ✅
└── 手机锁屏自动解除 ✅
```

## 一、已解决

### 1. UI 文本提取 (Level A) ✅
- **手机 Pixel 6 Pro**: 完整 AI 回答 + `search_summary` + `search_sources[].title` + `sitename`
- **模拟器**: 同上
- **原理**: `uiautomator2.dump_hierarchy()` → 过滤 → 检测新文本 → 展开参考卡片 → 读取标题
- **关键修复**:
  - 锁屏自动解除 (`wm dismiss-keyguard` + 上滑)
  - 参考区 RecyclerView 回收问题（先抓参考再打印长文本）
  - EditText 选择器兼容（className + `input_text` 双回退）
  - 系统通知过滤（正在充电、USB 调试等）
  - 短文本过滤（min 80 chars 防止误判）

### 2. 参考来源标题 ✅
- 点击 `ll_reference_title` 展开参考卡片
- 读取 `tv_reference_content` 获取每条参考的标题
- 从标题解析 `sitename`（如"新京报"、"环球网"等）

### 3. Frida WebView.loadUrl Hook ✅ (模拟器)
- Hook `android.webkit.WebView.loadUrl(String)` + `loadUrl(String, Map)`
- 点击参考卡片 → `WebActivity` 打开 → hook 捕获真实 URL
- **模拟器上 24/24 URL 捕获，100% 稳定**
- 过滤规则：排除 `javascript:` 和 `seclink.bytedance.com` 重定向

### 4. Frida PID 挂载 (Android 16) ✅
- Pixel 6 Pro + Magisk 27.0 root
- `frida -D DEVICE -p PID` 按 PID 挂载（`-n` 在 Android 16 上不可用）
- 所有 5 个 hook 正常安装运行

### 5. 手机物理设备适配 ✅
- 锁屏自动解除
- 不同 Doubao 版本 UI 差异兼容（`input_text` / `action_send` 等 resource ID）
- Magisk Superuser 授权 Shell

## 二、部分解决

### 1. URL 抓取 ⚠️

| 环境 | 状态 |
|------|------|
| 模拟器 + `--frida` | ✅ 100% 可靠 |
| Pixel 6 Pro 真机 | ❌ 手机版 Doubao UI 不同，`[__LINK_ICON]` 为纯文本，不触发 WebActivity |

**分析**: 手机版 Doubao 使用不同 UI 版本，参考卡片以 `[__LINK_ICON]` 内联标记展示，但 ClickableSpan 和 WebView.loadUrl 均未触发。模拟器版则有独立的 `ll_reference_title` 切换 + `tv_reference_content` 卡片。

### 2. 参考内容 Summary ⚠️
- `q01-quick.json` 中的详细 summary 内容需要额外实现
- 可能的方案：点击参考卡片后抓取 WebView 内容，或解析 SSE API 响应中的参考数据

## 三、环境

| 组件 | 状态 |
|------|------|
| Pixel 6 Pro (Android 16) | ✅ 主力测试设备，Magisk root |
| Android 模拟器 (API 35) | ✅ URL 抓取验证 |
| ADB | ✅ `~/Library/Android/sdk/platform-tools/adb` |
| Frida 17.9.11 | ✅ host + server 版本一致 |
| uiautomator2 | ✅ Python 包 |
| Magisk 27.0 | ✅ 手机 root |

## 四、关键文件

| 文件 | 用途 |
|------|------|
| `doubao_capture.py` | 主脚本 (Level A + Level B) |
| `/tmp/frida_webview_url_v2.js` | Frida WebView URL hook (模拟器) |
| `~/Desktop/doubao_capture.json` | 默认输出 |
| `q01-quick.json` | 期望的输出格式参考 |

## 五、命令行

```bash
# 手机文本抓取 (Level A) — 当前可用
cd ~/Desktop/doubao_capture && python3 doubao_capture.py "你的问题"

# 模拟器 URL 抓取 (Level B) — 需要先切 DEVICE
cd ~/Desktop/doubao_capture && python3 doubao_capture.py "你的问题" --frida
```

## 六、下一步

1. **手机 URL 抓取**: 深入分析手机版 Doubao 的参考链接机制（SSE 响应解析 或 不同 UI 路径）
2. **Summary 提取**: 点击参考卡片后抓 WebView 内容 或 解析 API 响应
3. **`--frida` 模式完善**: 手机 vs 模拟器自动检测
