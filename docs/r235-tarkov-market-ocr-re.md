# R235 · tarkov-market.com items-tracker 的 OCR 实现（逆向研究）

> 取证时间 2026-11-11 14:15–14:30（UTC+8，Clash 代理直抓）
> 方法：curl 抓页面 HTML + 全部 26 个 Nuxt3 chunk（3.74 MB，SHA-256 `b4cb4886…`）
> + `mcp__rea__analyze_javascript_application` 结构化分析（12,397 findings）。
> 证据：`build/_tm_re/`（page.html + chunks/ + urls.txt）。
> 边界：未登录（OCR 是 Pro 功能，无法实跑识别），结论全部来自静态 bundle。

## 结论一句话

**tarkov-market 的 OCR 是纯服务端实现**：客户端只做「采集 → 降采样 → 无损压缩 →
上传」，识别跑在**专用 OCR 节点集群**上，物品解析在后端（CNN 参与匹配），
并有用户纠错回路持续喂数据。客户端 26 个 chunk 里**没有任何** tesseract /
paddle / onnx / wasm OCR 引擎。

## 一、客户端管线（`chunks/D8NzgenD.js`，items-tracker 页组件）

```
选文件 / Ctrl+V 粘贴（lo(t,"image") → {file, formData}）
→ 降采样：as=2000, ut=1440 —— 高度 ≥2000 才缩到 1440 高
   （canvas，imageSmoothingEnabled=false）
→ 编码：canvas.toBlob 优先 image/webp quality=1，
   且校验前 64 字节含 "VP8L"（真无损 WebP）才采用，否则回退 PNG
   （us()：is() 检查 VP8L 魔数；FileReader.readAsDataURL 出 base64）
→ recognize(base64, file)：
   ① POST /api/be/items-ocr/ticket
        → {ticket, nodeUrl, host, isLimitExceeded, notAllowed}
      （服务端门禁：Pro 校验 + feature_ocr_rate_limit 限流，一次性票据）
   ② POST {nodeUrl}/api/ocr/upload
        headers: x-ocr-ticket + content-type: application/octet-stream
        body: 原始图片字节（ls(u,y)=y||fetch(u).blob()）
        timeout: ns=60000（60 s）
      → 专用 OCR 节点识别，返回裸 ocrResult
   ②' 节点直传失败 → 回退 POST /api/be/items-ocr/process-ext
        {base64, failedHost}（主后端代理识别）
   ③ POST /api/be/items-ocr/resolve {ticket, ocrResult}
      → 后端把 OCR 文本解析成物品（method:"cnn"、recovered、auto 标记）
→ 结果合并到追踪清单（ocrResult.items[]）
→ 用户纠错：选格子改物品 → POST /api/be/items-ocr/report
     {base64, comment, cells:[{uid, confidence, method, recovered, auto,
      correctUid, correctBsgId, correctShortName}], ocrResult}
   （纠错 + 原图 + 原始 OCR 一起喂回后端 → 样本库/训练数据）
```

## 二、服务端架构证据

| 证据 | 位置 | 说明 |
| --- | --- | --- |
| `feature_ocr` / `feature_ocr_rate_limit` | 页面 SSR 载荷 | 全局开关 + 限流值 |
| `/api/be/items-ocr/{ticket,process-ext,resolve,report}` | D8NzgenD.js | 四个后端接口 |
| `{nodeUrl}/api/ocr/upload` | 同上 | **独立 OCR 节点**直传端点 |
| 路由 `admin-ocr-hosts` → `/admin/ocr-hosts` | DxW504M9.js 路由表 | OCR 节点集群管理页 |
| 路由组件 `AdminOcrDisk`、`ocr-samples` | 同上 | 节点磁盘 + 样本库管理页 |
| `canSeeOcrBtn` / `canUseOcr` | D8NzgenD.js | 前端门禁（admin ∨ feature_ocr；使用还要求 **Pro**），服务端 ticket 二次校验 |
| items-tracker 页 `ve()`：非 Pro → showProPopup | nkN3bX_W.js | Pro 弹窗拦截 |

## 三、与本项目 R234 的对照

| 维度 | tarkov-market | 我们 R234 |
| --- | --- | --- |
| 识别位置 | 云端专用节点集群（不可见实现） | 本机 BFF 内嵌 PaddleOCR ONNX |
| 匹配 | 后端 resolve（items[].method="cnn"） | difflib 四级匹配（本机 7433 键索引） |
| 客户端预处理 | 高度 ≥2000 → 1440、无损 WebP 优先 | 原图直传（24MB 上限）+ 画布框选 ROI |
| 门禁/限流 | Pro + ticket + rate_limit | 本机单用户，无需 |
| 质量回路 | 用户纠错 report → 样本库（可能训练用） | 无（可借鉴：本地记住用户纠正） |

可借鉴（如后续迭代）：① 无损 WebP 压缩上传体（同等画质体积更小）；② 把用户
在结果表里的纠正记录下来，下次优先匹配（本地版"resolve 学习"）；③ 60s 超时
区分 AbortError/TimeoutError 的错误分类。

## 四、不可判定项（如实）

- 节点上的**文字识别引擎本体**不可见（服务端实现）：可能是 PaddleOCR/Tesseract
  服务端部署或自训模型，客户端无法证实；`method:"cnn"` 只能证明 **resolve 阶段
  的物品匹配**用了 CNN。
- OCR 节点返回的裸 ocrResult 结构（resolve 之前）未观察到——需要登录 Pro 实跑。
