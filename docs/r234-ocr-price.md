# R234 · 截图识别价格（OCR · A 路线完整复现）

## 用户原话（2026-11-11 12:11）

> 「走A 然后项目不是网页啊 是独立的程序 只不过现在没有打包 所以测试是用网页
> 然后价格就能使用市场界面里的数据了」

即：按上一轮三选一的 **A（完整复现 ONNX OCR）** 落地；UI 按独立程序形态做
（打包后同款入口，现阶段网页里可用）；价格直接用市场界面同一数据源。

## 管线（复刻 docs/r32-xiaomeow-re/REPORT.md §3，XiaoMeowToolbox）

```
截图 → OcrPreprocess 小图放大（≤1.6×，目标 1100px）
→ det.onnx（960 边长 32 对齐、ImageNet mean/std、CHW、输入名 "x"）
→ DB 后处理（thresh 0.30 / boxThresh 0.60 / unclip 1.5 / minSize 3、minAreaRect）
→ SortBoxes（先 y 后 x，同行 |Δy|<10 冒泡一趟）
→ CropRotate（透视校正；h≥1.5w 顺时针转正）
→ rec.onnx（48×320 右零填充、(x/255-0.5)/0.5、batch 8、输入名 "x"）
→ CTC 贪心解码（blank=0，重复折叠，均分作 score）+ ppocr_keys_v1.txt（6623 字 + 空格 = 6625 类）
→ ItemMatcher（OcrTextNorm → 精确/去空格/模糊三级；BlockList；置信度 0.35；
   模糊阈值 len>4?0.60:0.72；次名差 <0.06 歧义丢弃；跨 token 0.05 窗口；
   ⑥数字守卫；⑦小字串守卫；⑧24px 栅格去重）
→ 价格（市场同源 prices_source.snapshot_for，免费=内置快照 / 会员=云端）+ 标注 PNG
```

## 改动清单

| 文件 | 内容 |
| --- | --- |
| `assets/ocr/` | **新增**：det.onnx 4,729,474 B + rec.onnx 10,812,334 B + ppocr_keys_v1.txt 26,250 B（自逆向参考复制，SHA-256 逐一核对一致） |
| `tools/ocr.py` | **新增**：引擎 + 匹配 + 解码。纯 stdlib 部分可无依赖导入/单测；numpy/cv2/onnxruntime 全部懒加载，缺失时引擎抛 `OcrUnavailable` |
| `tools/serve.py` | `POST /api/ocr/recognize`（`MAX_OCR_BODY=24MB`，base64/dataURL 入参；引擎缺失回 **503 ocr-unavailable**）；`/api/health` 增加 `ocr.available/hint`；物品目录与匹配器进程级缓存（items.json 按 mtime 失效） |
| `js/market.js` | 市场工具栏「截图识别」按钮 + 识别面板（文件/拖拽/**Ctrl+V 粘贴**/画布拖拽框选 ROI）+ 结果表（图标/名称/匹配层级/最新价/每格价，行点击开物品详情弹窗） |
| `market.css` | 识别面板样式（`.mk-ocr*`） |
| `tests/test_r234_ocr.py` | **新增 24 条**：归一化/短名 parity/匹配四级/守卫/去重/CTC/字典/排序/unclip 数学/服务端契约/模型哈希/引擎级识别 |
| `tests/test_r97_market.py` | fetch 护栏从「只许 1 个」升级为「恰好 2 个且都为本机相对 `api/` 路径」（R218 历史曲线 + R234 识别） |

依赖（经用户拍板突破「零新增依赖」）：服务端 Python（C:\Python314，即 BFF 运行时）
安装 `onnxruntime 1.31.1 + opencv-python-headless 5.0.0.93 + numpy 2.5.4`（走 Clash 代理 pip）。
测试用 bundled Python 无这些包 → 引擎级用例自动 `skip`（`ocr.check_available()` 探测）。

## 调试中抓出的四个真 bug（都有单测/实测背书）

1. **`_unclip` 交点公式符号错**（关键）：外扩没生效，det 框只框到字形中段
   （30px 字 crop 出 16-20px），rec 系统性误读（'工厂'→'十广'、'马卡洛夫'→'瓦上没关'）。
   修复后同一张图 3/3 物品名 **0.98+ 置信一字不差**。
2. **rec 通道序**：PaddleOCR 惯例 det 用 RGB、rec 保持 BGR；首版 rec 也转了 RGB。
   （灰度合成图上两者输出恰好相同，用彩色图才可分辨——保留正确实现并注释。）
3. **标注徽章半径**：误用整行包围盒尺寸（300px 行 → 半径 150 巨圆盘），
   规格是**标签文字**尺寸 → `r = max(8, max(tw,th)/2+4)`。
4. **纯数字价格标签误匹配**：'53,548' 被模糊层配到 '5.56x45mm M855'（参考实现靠
   AmmoBlockedKeys 挡，本项目无该数据）→ 新增 **⑨ 纯数字串守卫**
   （`^\d+(\.\d{3})*\.?\d*$`，整串与 token 两级都拦）。

## 匹配器的两个本地化扩展（与参考的偏差，均如实标注在 docstring）

- **索引源**：XiaoMeow 索引紧凑短名；本项目 items.json 的 `sn` 是占位符
  （"xxx ShortName"），改索引 `n` 真名 + 复刻 `shortNameOf(n)` 的短名。
- **整串模糊层**：OCR 吞空格/首字写错时 token 层拿不到候选（首字符倒排整组丢失），
  增加整串（两侧都去空格）对「长度 ±4 全部候选键」的 difflib 兜底，
  阈值与歧义判定沿用规格；数字段守卫 + real_quick_ratio 剪枝控成本。
- AmmoBlockedKeys（同名弹药按价格比拉黑）未复刻：同名多 id 时由接口按
  perSlot↓ 择优（对应规格 PickBest）。

## 价格（与市场界面同源，无新数据层）

- 服务端复用 `prices_source.snapshot_for(root, mode, cloud_client, member)`——
  免费=内置快照 / 会员=云端近实时 / 云端断线自动回退并标注，与 `/api/price-snapshot` 一字不差。
- 快照条目两种形状都兼容：压缩键 `l`/`a`（快照载荷）与全名键 `lastLowPrice`/`avg24hPrice`（原始文件）。
- 每格价 = 基准价 ÷ (gw×gh)，基准价 = 最新低价缺失时用 24h 均价（与 `js/market.js` buildRows 同口径）。
- 前端展示优先 `GWMarketData.quote(id)`（随模式/会员态实时），缺失时回退服务端返回值。

## 验收

- **HTTP 端到端**（对真实 8787 服务，`build/_ocr_http_test.png` = 3 个真实物品名 +
  1 个纯数字价格标签，微软雅黑粗体 28px 暗底）：3/3 匹配（精确×2 + 模糊×1）、
  云端快照价格 431400 / 12600 / 90000 全对、每格价正确、价格行被 ⑨ 拦下、标注图返回；
  真实战局截图（1080p 野外）0 误报 276ms；坏 base64 / 缺字段 → 400；
  `/api/health` → `ocr.available=true`。
- **浏览器验收** `tools/r234_accept.py` **17/17**：市场视图 → 按钮 → 面板 →
  DataTransfer 灌图 → 画布预览 → 识别 → 结果表 3 行（名称/层级/`431 400 ₽`/每格价，
  市场格式化）→ 标注图 → Escape 关闭 → 无 JS 异常。截图 `docs/r234/01-ocr-panel.png`。
- 识别耗时：整图 det+rec 约 **0.3-0.4 s**（不含首跑 1.3s 模型装载，进程内复用）。
- 全量 pytest：见 `AGENT_HANDOFF.md`（`build/_pytest_r234.xml`）。

## 边界与后续（如实）

- 现有截图库全是战局画面（只有倒计时文字），没有仓库/跳蚤界面的真实样本；
  游戏内实拍效果待用户下次进游戏后用面板实测（小字建议配合框选 ROI——
  这正是参考实现的工作方式，全图 1080p 下 14px 小字会经 960 缩放损失精度）。
- 未做 RecognizeChunked 分块（超大图仅靠 960 缩放兜底）；未做独立浮层窗口
  （`tools/overlay.py` 可作为后续宿主）；打包（PyInstaller spec）未包含
  assets/ocr 的处理验证。
- 模型许可：PaddleOCR det/rec 为 Apache-2.0 官方模型导出；随安装包分发前
  建议在 README/关于页标注（本轮未动打包脚本）。
- 未 commit / push / 打包 / 改四个契约 JSON。
