# 豆包抓包项目进度总结

> 更新时间: 2026-05-29

## 总体进度

```
███████████████████░  90%

已解决 ✅                              
├── UI 文本提取 ✅                    
├── 参考来源标题 + sitename ✅        
├── Frida WebView.loadUrl Hook ✅      
├── Frida PID 挂载 (Android 16) ✅
├── uiautomator2 自动化 ✅
├── 搜索关键词 + 参考资料数 ✅
├── 手机锁屏自动解除 ✅
└── 手机 URL 抓取 ✅ (90-100%)

部分解决 ⚠️
└── 参考内容 summary ❌
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

### 2. 参考来源标题 + sitename ✅
- 点击 `ll_reference_title` 展开参考卡片
- 读取 `tv_reference_content` 获取每条参考的标题
- 从标题解析 `sitename`（如"新华网"、"环球网"等）

### 3. Frida WebView.loadUrl Hook ✅
- Hook `android.webkit.WebView.loadUrl(String)` + `loadUrl(String, Map)`
- 点击参考卡片 → `WebActivity` 打开 → hook 捕获真实 URL
- 过滤规则：排除 `javascript:` 和 `seclink.bytedance.com` 重定向

### 4. Frida PID 挂载 (Android 16) ✅
- Pixel 6 Pro + Magisk 27.0 root
- `frida -D DEVICE -p PID` 按 PID 挂载（`-n` / `-f` 在 Android 16 上不可用）
- 所有 5 个 hook 正常安装运行

### 5. 手机 URL 抓取 ✅ (90-100%)
- **所有参考卡片均可被找到并点击**（UI 导航稳定）
- **URL 捕获率 90-100%**（偶尔 Frida 时序导致漏抓 1-2 个）
- **关键突破**:
  - 使用 ADB `input swipe` 替代 uiautomator2 `d.swipe()`（后者在 Doubao 上不可靠）
  - 使用 ADB `input keyevent 4` 替代 `d.press("back")` 进行返回导航
  - `_click_toggle_safe()`: 获取 toggle 坐标后用 ADB tap 点击，避免 RecyclerView 回收
  - **HOME + monkey 恢复**: 从 WebView 返回后若找不到参考卡片，按 HOME 键回到桌面，再用 `monkey -p com.larus.nova 1` 恢复到 ChatActivity（Frida 保持挂载）
  - 恢复后滚动 30 次查找 toggle，支持双重试

### 6. 手机物理设备适配 ✅
- 锁屏自动解除
- 不同 Doubao 版本 UI 差异兼容（`input_text` / `action_send` 等 resource ID）
- Magisk Superuser 授权 Shell

## 二、部分解决

### 参考内容 Summary ❌
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
| `/tmp/frida_webview_url_v2.js` | Frida WebView URL hook |
| `~/Desktop/doubao_capture.json` | 默认输出 |

## 五、命令行

```bash
# 文本抓取 (Level A)
cd ~/Desktop/doubao_capture && python3 doubao_capture.py "你的问题"

# URL 抓取 (Level B) — 手机 + 模拟器通用
cd ~/Desktop/doubao_capture && python3 doubao_capture.py "你的问题" --frida
```

## 六、下一步

1. **Summary 提取**: 点击参考卡片后抓 WebView 内容 或 解析 API 响应
2. **URL 捕获率提升到 100%**: 优化 Frida 时序，增加 WebView 等待时间或重试机制
3. **手机 vs 模拟器自动检测**: `--frida` 模式自动识别设备类型
