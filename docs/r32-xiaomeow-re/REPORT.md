# XiaoMeow 工具箱 1.5.3 逆向报告（自动截图 / 价格 OCR / 小地图）

> 目标：`D:\personal\trae\02-塔科夫\逆向参考\XiaoMeowToolbox-win-Setup-1.5.3 (1).exe`
> 方法：`rea` 托管元数据 + CIL anchor 反汇编（本机无 .NET SDK、无 Ghidra/IDA，全部走元数据路线）
> 产物目录：`D:\personal\trae\02-塔科夫\逆向参考\build-re-xiaomeow\`
> 本文只记录**观测到的事实**与**可复现的参数**；推断部分单独标注「推断」。

---

## 0. 一句话结论

| 功能 | 他们的做法 | 能不能直接搬到本项目 |
| --- | --- | --- |
| 游戏内自动截图 | 定时 `SendInput` 拍一下游戏的截图键，**只要求游戏在前台**；不做屏幕抓取 | ✅ 能，纯标准库；我们的实现只差几处细节 |
| 截图识别价格 | 自研 PaddleOCR（ONNX 前向 + DB 后处理 + CTC 解码）+ 自研模糊匹配 + OpenCV 标注 | ⚠️ 算法全部可复刻，但**需要 onnxruntime 与 15.5 MB 模型**，与「零新增依赖」铁律冲突 |
| 游戏内小地图 | 一个**置顶 + 点击穿透的 WebView2 窗口**，加载自家网页 `…/minimap?size=&opacity=&shape=` | ✅ 思路完全可搬（我们本来就是网页），但「全局置顶 + 点击穿透」必须靠 Win32 |

---

## 1. 包结构与技术栈

```
XiaoMeowToolbox-win-Setup-1.5.3 (1).exe   54 587 033 B
└─ Velopack 1.2.161 安装器
   └─ 内嵌 XiaoMeowToolbox.nupkg（41 627 169 B，从 exe 尾部切出）
      └─ lib/app/ 512 个文件
```

- 注意：切出来的 `.nupkg` 里 ZIP 中央目录的偏移量是**相对原 exe** 的，所以那个文件不能直接 `ZipFile` 打开；必须 `zipfile.ZipFile(exe)` 直接读 exe。本报告的所有文件都是从 exe 里读出来的。
- 运行时：**.NET 10 / NETCoreApp v10.0 / WPF**
- 主要依赖（`AssemblyRef` 实测）：`OpenCvSharp`、`Microsoft.ML.OnnxRuntime`、`Microsoft.Web.WebView2.Wpf`、`SkiaSharp`、`System.Text.Json`

| 程序集 | 大小 | 类型 | 方法 | 角色 |
| --- | ---: | ---: | ---: | --- |
| `XiaoMeowToolbox.dll` | 8 521 216 B | 322 | 2215 | 界面 / 服务 / Win32 互操作 |
| `XiaoMeowToolbox.Core.dll` | 90 624 B | 59 | 441 | 纯算法（OCR、匹配、价格、任务） |

- `XiaoMeowToolbox.dll` sha256 `52b882a8d4f579aec636e7d3ed7cfd9a2fe87acf1a7ce3061f9e42527c8795c0`，MVID `032a85d3-3b43-473e-b687-ee4c39adfd0a`，AssemblyVersion `1.5.3.0`
- `XiaoMeowToolbox.Core.dll` sha256 `fffc3d42…`（完整值见 `逆向参考/build-re-xiaomeow/`；rea 报 `architecture: x86`，与外壳的 x86_64 不同，属 AnyCPU/ILOnly 标记差异，不影响分析）

---

## 2. 游戏内自动截图

### 2.1 三个类

| 类 | 职责 |
| --- | --- |
| `App.Services.AutoShot` | 定时器 + 前台判定 + 调 Tap |
| `App.Services.InputSender` | 键名解析 + `SendInput` 注入 |
| `App.Services.ScreenGrab` | GDI 抓屏（**给价格 OCR 用**，与游戏截图无关） |

### 2.2 `AutoShot` 规格

```csharp
bool _enabled; string _key = "PrintScreen"; int _seconds;      // Clamp(1, 600)
DispatcherTimer _timer;  bool? _lastForeground;
static bool ForceSend = (Environment.GetEnvironmentVariable("XM_SHOT_FORCE") == "1");
```

`Apply(enabled, key, seconds)`：

```
_key     = string.IsNullOrWhiteSpace(key) ? "PrintScreen" : key.Trim()
_seconds = Math.Clamp(seconds, 1, 600)
_timer.Stop()
if (!_enabled) return
_timer.Interval = TimeSpan.FromSeconds(_seconds)
_timer.Start()
log($"自动截图已开启：每 {_seconds}s 一次（仅游戏前台）；键 {_key}")
```

`Tick()`（定时器回调）：

```
bool fg = ForceSend || IsGameForeground();
if (fg != _lastForeground) {                 // 只在翻转时写日志，避免刷屏
    log(fg ? $"检测到游戏在前台（开始发截图键）｜前台：{DescribeForeground()}"
           : $"游戏不在前台（暂停发键）｜当时前台：{DescribeForeground()}");
    _lastForeground = fg;
}
if (!fg) return;
if (!InputSender.Tap(_key)) {
    if (InputSender.LastError != -1) log($"⚠️ 截图键发送失败：{_key}（Win32 错误 {LastError}）");
    else                             log($"⚠️ 截图键解析不了：{_key}（设置里换一个）");
    return;
}
log($"已发送截图键 {_key}");
```

**`LastError == -1` 专门表示「键名解析失败」**，与 Win32 错误码分开 —— 这样界面能给出「换个键」这种可执行的建议。

前台判定：

```
IsGameForeground() = IsGameRunning() && IsGameWindow(GetForegroundWindow())

IsGameRunning()            // 结果缓存 3 秒
    遍历 Process.GetProcesses()，ProcessName.Contains("EscapeFromTarkov")

IsGameWindow(hwnd)
    if (hwnd == 0) return false
    name = WindowProcessName(hwnd)                 // GetWindowThreadProcessId → Process.GetProcessById(pid).ProcessName
    if (name.Length > 0) return name.Contains("EscapeFromTarkov")
    // 进程名取不到（权限不足）时退化到窗口标题
    return GetWindowText(hwnd).Replace(" ", "") == "EscapeFromTarkov"
```

要点：**只要求「游戏进程在跑 + 前台窗口属于游戏」**，不要求知道当前是不是在战局里。

### 2.3 `InputSender` 规格

`Parse(string) -> (ushort vk, ushort[] modifiers)?`

```
s = key.Trim().Replace(" ", "")       // 先把所有空格干掉，"Left Ctrl" → "LeftCtrl"
"ctrl"  → (0x11, [])     // 单独 Ctrl
"shift" → (0x10, [])
"alt"   → (0x12, [])
parts = s.Split('+')
mods = []
for p in parts[0 .. n-2]:             // 除最后一段都是修饰键
    "ctrl"|"control" → mods.Add(0x11)
    "shift"          → mods.Add(0x10)
    "alt"            → mods.Add(0x12)
    其它              → return null   // 解析失败
main = parts[n-1]  → VkKeyScan / 内置表 → vk
```

`Tap(key)`：

```
parsed = Parse(key)
if (parsed == null) { LastError = -1; return false; }
(vk, mods) = parsed

if (IsMouseKey(vk)) {
    flags = (vk == 0xFF01) ? 1 : 2               // 滚轮 / 其它键
    list = [ MouseInput(flags, down:true), MouseInput(flags, down:false) ]
    return SendInputBatch(list)
}

list = []
foreach (m in mods)      list.Add(KeyInput(m, up:false));   // 修饰键按顺序按下
list.Add(KeyInput(vk, up:false));
list.Add(KeyInput(vk, up:true));
for (i = mods.Length-1; i >= 0; i--) list.Add(KeyInput(mods[i], up:true));  // 逆序抬起
return SendInputBatch(list)

SendInputBatch(list):
    sent = SendInput((uint)list.Length, list.ToArray(), Marshal.SizeOf<INPUT>())
    if (sent != list.Length) { LastError = Marshal.GetLastWin32Error(); return false; }
    LastError = 0; return true;
```

`KeyInput(vk, up)` —— **关键**：

| 字段 | 值 |
| --- | --- |
| `type` | `1`（`INPUT_KEYBOARD`） |
| `ki.wVk` | **`vk`** |
| `ki.wScan` | **`0`** |
| `ki.dwFlags` | `up ? 0x0002 : 0x0000` |

即 **纯虚拟键码模式**，不设 `KEYEVENTF_SCANCODE`。

### 2.4 `ScreenGrab`（与「游戏内截图」无关，供 §3 使用）

```
VirtualLeft   = GetSystemMetrics(76)   // SM_XVIRTUALSCREEN
VirtualTop    = GetSystemMetrics(77)   // SM_YVIRTUALSCREEN
VirtualWidth  = GetSystemMetrics(78)   // SM_CXVIRTUALSCREEN
VirtualHeight = GetSystemMetrics(79)   // SM_CYVIRTUALSCREEN

CaptureRegion(x, y, w, h):
    hdcScreen = GetDC(0)
    hdcMem    = CreateCompatibleDC(hdcScreen)
    hBmp      = CreateDIBSection(hdcMem, BITMAPINFO{32bpp, BI_RGB, top-down}, DIB_RGB_COLORS, out bits, 0, 0)
    SelectObject(hdcMem, hBmp)
    BitBlt(hdcMem, 0, 0, w, h, hdcScreen, x, y, SRCCOPY)
    → Mat.FromPixelData(h, w, MatType.CV_8UC4, bits)   （随后 CvtColor 去 alpha）
```

这是**整屏/区域抓图**，不是向游戏发按键。价格 OCR 的 ROI 就走这里。

### 2.5 与我们现有实现（`tools/serve.py::AutoShotter` + `tools/keyinput.py`）的逐条差异

| # | 维度 | 他们 | 我们 | 影响 |
| --- | --- | --- | --- | --- |
| 1 | 门条件 | 游戏进程在跑 **且** 前台是游戏 | 额外要求 `phase == "start"`（来自日志跟随） | ⚠️ **日志跟丢了就一发不发**，且页面只显示「不在战局中（当前阶段：xxx）」 |
| 2 | 键模式 | `wVk=vk, wScan=0`（虚拟键） | `wVk=0, wScan=scan + SCANCODE`（扫描码） | 两种都有先例能通；但**出问题时我们没有任何切换手段** |
| 3 | 修饰键 | 支持 `Ctrl+Shift+F10` | 明确拒绝（`unsupported_reason` 返回「不认识这个按键」） | ⚠️ 用户把截图键改成带修饰的组合就直接失效 |
| 4 | 投递批次 | 1 次 `SendInput` 投递「修饰+主键」全部事件 | 1 次投递 2 条（只有按下/抬起） | 差别不大 |
| 5 | 错误区分 | `LastError = -1` 表示「键名解析不了」，其它是 Win32 码 | 只有一段字符串 | 界面提示精度 |
| 6 | 发送后的验证 | **没有** | **没有** | 双方都只能证明「按键送出去了」，证明不了「截图产生了」 |
| 7 | 间隔 | 秒（1..600） | 毫秒（200..60000） | 无所谓 |

> **推断（未在实机验证）**：#1 与 #3 是我们这边最可能「一直没做好」的两个原因。#1 尤其可疑 —— 自动截图的唯一目的是拿截图里的坐标，而我们的门条件把它绑在了「日志判定已进战局」上，日志一旦没跟上（换目录、日志被清、版本改了字段），整条链路就静默停摆，而页面上仍然是一片「已发送 0 张」。
>
> 另一个所有人都缺的环节是 **到货校验**：发键 → 截图目录出现新文件，才算真的成功。加上这一步，用户才能区分「没发」/「发了游戏没理」/「截图目录配错了」。

---

## 3. 截图识别价格（OCR）

### 3.1 分层

```
Core.Ocr      : OcrEngine  ImageOps  DbPostProcess  CtcDecode  DetBox  OcrLine
Core.Price    : ItemMatcher  ItemEntry  ItemMatch  SequenceMatcherRatio
                PriceFormat  PriceService  ResultAnnotator
App.Services  : OcrHost（单例）  PriceScanner  PriceRoi  ScanResult  OcrSelfTest
```

`OcrHost`：静态单例，`Monitor` 双检锁；模型目录 = `AppContext.BaseDirectory/Assets/ocr`；`Available` = 三个文件都在。日志 `[ocr] 引擎装载（共享单例；推理线程 N，CPU 内存池关）`。

### 3.2 `ImageOps` —— 预处理

**`DetPreprocess(Mat src, int maxSide) -> (float[] data, int h, int w)`**

```
maxLen = max(rows, cols)
scale  = maxLen > maxSide ? (double)maxSide / maxLen : 1.0
w = (int)(cols * scale);  h = (int)(rows * scale)
w = max(32, (int)(Math.Round(w / 32.0) * 32))     // 32 对齐
h = max(32, (int)(Math.Round(h / 32.0) * 32))
Cv2.Resize(src, dst, new Size(w, h), 0, 0, INTER_LINEAR)

mean = { 0.485, 0.456, 0.406 }                    // 字节级核对：Core.dll @ 0x15bd0
std  = { 0.229, 0.224, 0.225 }                    // 字节级核对：Core.dll @ 0x15bb8

out = new float[3 * h * w]                        // **CHW，不是 HWC**
for y in 0..h-1, for x in 0..w-1:
    (b, g, r) = pixel(y, x)                       // OpenCV 的 BGR 序
    out[0 * h*w + y*w + x] = (float)((r / 255.0 - mean[0]) / std[0])
    out[1 * h*w + y*w + x] = (float)((g / 255.0 - mean[1]) / std[1])
    out[2 * h*w + y*w + x] = (float)((b / 255.0 - mean[2]) / std[2])
```

调用方传 `maxSide = 960`。

**`RecPreprocess(Mat src, int imgH, int imgW) -> float[]`**

```
aspect = (double)cols / rows
w = (int)Math.Ceiling(imgH * aspect)
if (w > imgW) w = imgW
Cv2.Resize(src, dst, new Size(w, imgH), 0, 0, INTER_LINEAR)

out = new float[3 * imgH * imgW]                  // 右侧零填充
out[c * (imgH*imgW) + y*imgW + x] = (float)((px / 255.0 - 0.5) / 0.5)
```

调用方传 `imgH = 48, imgW = 320`。

**`CropRotate(Mat src, Point2f[] box) -> Mat`**

```
w = (int)max(Dist(p0,p1), Dist(p2,p3))
h = (int)max(Dist(p0,p3), Dist(p1,p2))
w = max(1, w); h = max(1, h)
dstQuad = { (0,0), (w,0), (w,h), (0,h) }
M = Cv2.GetPerspectiveTransform(box, dstQuad)
Cv2.WarpPerspective(src, out, M, new Size(w, h), INTER_CUBIC=2, BORDER_REPLICATE=1)
if (h / (double)w >= 1.5)  out = Cv2.Rotate(out, ROTATE_90_CLOCKWISE=2)   // 竖排文字转正
```

**`OcrPreprocess(Mat src) -> (Mat, double scale)`** —— 小图放大

```
maxLen = max(h, w)
scale  = 1.0
if (maxLen < 1100) {
    scale = min(1.6, 1100.0 / maxLen)
    if (scale > 1.05) { Resize(INTER_CUBIC=4); return (dst, scale); }
}
return (src, scale)
```

**`TilePlan(int w, int h, int tile, double overlap) -> List<(x, y, tw, th)>`**

```
step = max(1, (int)(tile * (1 - overlap)))
xs = 0..<w step step;   if (xs.Last() + tile < w) xs.Add(w - tile)
ys 同理
→ 每个 (x, y) 产出 (x, y, min(w, x+tile) - x, min(h, y+tile) - y)
```

`RecognizeChunked` 传 `overlap = 0`，即 `step = tile`。

### 3.3 `DbPostProcess` —— 检测后处理

`Process(float[] pred, int predH, int predW, int destH, int destW, float thresh, float boxThresh, int maxCands, float unclipRatio, int minSize)`

```
mask = pred[i] > thresh ? 255 : 0
Cv2.FindContours(mask, out contours, out _, RETR_LIST=1, CHAIN_APPROX_SIMPLE=2)

n = min(contours.Length, maxCands)
foreach (contour in contours[0..n-1]):
    (box, sside) = GetMiniBoxes(contour)
    if (sside < minSize) continue
    score = BoxScoreFast(predMat, box)                 // 二值外接矩形内取均值
    if (score < boxThresh) continue
    pts = Unclip(box, unclipRatio)                     // pyclipper 式外扩
    if (pts == null || pts.Count != 1) continue
    (box2, sside2) = GetMiniBoxes(pts[0])
    if (sside2 < minSize + 2) continue
    for i in 0..3:
        x = Round(box2[i].X / predW * destW)  clamped to [0, destW]
        y = Round(box2[i].Y / predH * destH)  clamped to [0, destH]
    result.Add(new DetBox(pts4, score))
```

`GetMiniBoxes` 的四点顺序：先按 `x` 排序取 0/1、再按 `y` 分左右上角 → 标准 PaddleOCR 的 (左上, 右上, 右下, 左下)；`sside = min(宽, 高)`。

**调用参数（`OcrEngine.Recognize` → `Process`）**

| 参数 | 值 |
| --- | --- |
| thresh（二值化） | **0.30** |
| boxThresh（框均分） | **0.60** |
| maxCands | **1000** |
| unclipRatio | **1.5** |
| minSize | **3** |

### 3.4 `OcrEngine` —— 前向与解码

```
字段：_det, _rec（都是 Lazy<InferenceSession>）；_detPath, _recPath, _character[]
ctor(detPath, recPath, dictPath, addSpace)
    _character = CtcDecode.LoadDict(dictPath, addSpace)
DefaultThreads = Clamp(Environment.ProcessorCount / 2, 1, 4)      // 静态属性
CreateOptions()
    if (env XM_OCR_LEGACY == "1") return new SessionOptions()      // 逃生阀：全默认
    o.IntraOpNumThreads = DefaultThreads
    o.InterOpNumThreads = 1
    o.ExecutionMode     = Sequential
    o.EnableCpuMemArena = false
```

`Recognize(Mat img, int batchSize, float minScore)`

```
det:  (data, dh, dw) = ImageOps.DetPreprocess(img, 960)
      tensor = DenseTensor<float>(data, [1, 3, dh, dw])
      outs   = _det.Run(new[] { NamedOnnxValue("x", tensor) })        // 输入名固定 "x"
      pred   = outs[0].AsTensor<float>(); dims = pred.Dimensions
      boxes  = DbPostProcess.Process(pred, dims[2], dims[3], img.Rows, img.Cols,
                                     0.30f, 0.60f, 1000, 1.5f, 3)
      boxes  = SortBoxes(boxes)

rec:  for (start = 0; start < boxes.Count; start += batchSize):
          chunk = boxes.GetRange(start, Min(batchSize, boxes.Count - start))
          buf   = new float[chunk.Count * 3 * 48 * 320]
          for (i, b) in chunk:
              crop = CropRotate(img, b.Points)
              rec  = RecPreprocess(crop, 48, 320)
              Array.Copy(rec, 0, buf, i * 3 * 48 * 320, rec.Length)
          tensor = DenseTensor<float>(buf, [chunk.Count, 3, 48, 320])
          outs   = _rec.Run(new[] { NamedOnnxValue("x", tensor) })
          pred   = outs[0].AsTensor<float>(); T = dims[1]; C = dims[2]
          for (i in 0..chunk.Count-1):
              seq = pred[i * T * C .. +T*C]
              (text, score) = CtcDecode.Decode(seq, T, C, _character)
              if (score >= minScore) lines.Add(new OcrLine(text, score, chunk[i].Points))
```

`RecognizeChunked(img, tile, ...)` 用 `TilePlan` 切成 256 像素块分别识别，再把每块内的框按 `(x*scale + tileX, y*scale + tileY)` 平移回全图坐标。`Recognize` 里 `batchSize = 8`。

**`CtcDecode`**

```
LoadDict(path, addSpace):
    dict = ["blank"]
    dict.AddRange(File.ReadAllLines(path).Select(l => l.Trim('\n', '\r')))
    if (addSpace) dict.Add(" ")          // 模型输出比字典多一类时补空格
    return dict

Decode(float[] seq, int T, int C, string[] dict):
    sb = ""; scoreSum = 0; count = 0; prev = -1
    for t in 0..T-1:
        best = 0; bestIdx = 0
        for c in 1..C-1: if (seq[t*C + c] > best) { best = seq[t*C+c]; bestIdx = c }
        if (bestIdx != prev) {
            prev = bestIdx
            if (bestIdx != 0) {                       // 0 = blank
                if (bestIdx < dict.Length) sb += dict[bestIdx]
                scoreSum += best; count++
            }
        }
    return (sb, count > 0 ? scoreSum / count : 0)
```

**`SortBoxes`**：先 `OrderBy(b => b.Points[0].Y).ThenBy(b => b.Points[0].X)`；再做一趟冒泡：若相邻两个框 `|Δy| < 10` 且后一个的 `x` 更小，就交换（把同一行里靠左的提到前面）。

### 3.5 `ItemMatcher` —— OCR 文本 → 物品

**索引构建（ctor）**

```
foreach (e in entries):
    key = OcrTextNorm(e.ShortName.Trim())
    if (key.Length == 0) continue
    if (IsAmmoBox(e)) continue                      // Category=="弹药" && AmmoKind=="box"
    if (e.Category == "弹药" && ammoBlocked.Contains(key)) continue
    _dlist[key].Add(e)                               // key → List<ItemEntry>
    _byFl[key[0]][key.Length].Add(key)               // 首字符 → 长度 → key 列表

OcrTextNorm(s):
    s = s.ToLowerInvariant()
    s = Regex.Replace(s, @"[^a-zа-я0-9\u4e00-\u9fff.,\-]+", " ")     // 保留西里尔、汉字、数字、点、逗号、横线
    s = s.Trim()
    s = s.Replace(',', '.')
    return s
```

`AmmoBlockedKeys`：弹药里同名（短名规范化后相同）但**最高价 / 最低价 > 3** 的短名整体拉黑 —— 那些短名指的是不同口径的子弹，不能模糊匹配。

`BlockList`（静态，参与匹配前先丢掉的 token）：

```
cpu  bear  items  pve  pvp  stash  search  filter  scav  junk
```

**`Match(lines, offX, offY, scale)`**

```
foreach ((box, text, score) in lines):
    if (score < 0.35) continue                                  // ① 置信度下限
    norm = OcrTextNorm(text)
    key = null; path = ""

    if (_dlist.ContainsKey(norm))                       { key = norm;                     path = "精确";   }
    else if (_dlist.ContainsKey(norm.Replace(" ","")))   { key = norm.Replace(" ","");     path = "去空格"; }
    else {
        (string, double)? best = null;
        foreach (tok in norm.Split(' ', RemoveEmptyEntries)):
            if (tok.Length == 0) continue
            if (BlockList.Contains(tok)) continue
            f = tok[0]
            cands = []
            foreach (L in { tok.Length-2, -1, 0, +1, +2 }):
                if (_byFl[f].TryGetValue(L, out lst)) cands.AddRange(lst)
            if (tok.Length >= 4 && _byFl.TryGetValue(f, out all))
                foreach ((len, lst) in all)
                    if (len <= tok.Length + 1)               // 补「以 token 开头、长度 ≤ len+1」的
                        cands.AddRange(lst.Where(s => s.StartsWith(tok)))
            cands = cands.Distinct().ToList()
            if (cands.Count == 0) continue

            thr = tok.Length > 4 ? 0.60 : 0.72                   // ② 模糊阈值（长词更宽容）
            ranked = cands.Select(c => (Ratio(tok, c), c))
                           .OrderByDescending(x => x.Item1).ThenBy(x => x.Item2, Ordinal).ToList()
            if (ranked[0].Item1 < thr) continue
            if (ranked.Count >= 2 && ranked[1].Item1 > ranked[0].Item1 - 0.06) continue   // ③ 歧义就丢
            if (best != null) {
                if (ranked[0].Item1 > best.Item2 + 0.05) { /* 更好，替换 */ }
                else if (Math.Abs(ranked[0].Item1 - best.Item2) > 0.05) continue;         // ④ 更差就丢
                else if (ranked[0].Item2.Length <= best.Item1.Length) continue;           // ⑤ 打平取更长的
            }
            best = (ranked[0].Item2, ranked[0].Item1)
        if (best != null) { key = best.Item1; path = $"模糊({best.Item2:F2})"; }
    }
    if (key == null) continue

    // 几何：右下角取 box[2]，左上角取 box[0]
    x  = (int)(box[0].X / scale) + offX;   y  = (int)(box[0].Y / scale) + offY
    x2 = (int)(box[2].X / scale) + offX;   y2 = (int)(box[2].Y / scale) + offY

    if (Regex.IsMatch(key, "[0-9.,]") && !Regex.IsMatch(norm, "[0-9.,]")) continue;   // ⑥ 防把纯数字当物品名

    area = max(1, x2-x) * max(1, y2-y)
    if (score < 0.85 && area < 800 && norm.Length > 5
        && !Regex.IsMatch(norm, "[0-9.,]") && Regex.IsMatch(norm, "^[a-z]+$")) continue;  // ⑦ 小字串扰

    items = _dlist[key]
    item  = items.Count > 1 ? PickBest(items) : items[0]        // PickBest: PerSlot↓ 再 Price↓ 取第一
    dedup = (key, FloorDiv(x, 24), FloorDiv(y, 24))              // ⑧ 24 像素栅格去重
    if (!seen.Add(dedup)) continue

    results.Add(new ItemMatch(norm, box, x, y, max(1,x2-x), max(1,y2-y), score, item, path))
```

`SequenceMatcherRatio.Ratio(a, b)` = 完全复刻 Python `difflib.SequenceMatcher.ratio()`：
`GetMatchingBlocks` 用队列 + `find_longest_match`（`b2j` 倒排 + `j2len` 动态规划），
`ratio = 2 * 匹配总长 / (len(a) + len(b))`。

### 3.6 输出与格式化

`ResultAnnotator`（`BoxColor = Scalar(105, 182, 225)` BGR，`BadgeTextColor = Scalar(24, 35, 36)`）：

```
Clone(src)
foreach ((i, m) in matches):
    rect = Rect(m.X - offX, m.Y - offY, max(2, m.W), max(2, m.H))
    Cv2.Rectangle(dst, rect, BoxColor, thickness: 2, LineTypes.AntiAlias)
    label = (i + 1).ToString()
    (tw, th) = Cv2.GetTextSize(label, HersheyFont, 0.4, 1)
    r = max(8, max(tw, th) / 2 + 4)
    cx = Clamp(rect.X - r - 2, r + 1, dst.Width  - r - 1)
    cy = Clamp(rect.Y + rect.Height / 2, r + 1, dst.Height - r - 1)
    Cv2.Circle(dst, (cx, cy), r, BoxColor, thickness: -1, AntiAlias)
    Cv2.PutText(dst, label, (cx - tw/2, cy + th/2), HersheyFont, 0.4, BadgeTextColor, 1, AntiAlias)
```

`AnnotatePng` → `Cv2.ImEncode(".png")`；`PriceScanner.Annotate` 把 PNG 写到 `price-cache/last_ocr_result.png`（`LastResultPath`）。

`PriceFormat.Fmt(long v, bool wan)`：

```
v <= 0   → "—"
!wan     → v.ToString("N0")
v < 500  → "<0.1万"
else     → (v / 10000.0).ToString("0.0") + "万"
```

`PriceService`：缓存 `price-cache/<mode>.json.gz` + `price-cache/<mode>.ver`；`ModeKey(pve/pvp → pve/pvp，season 单列)`；条目字段 `name / id / lastLowPrice / width / height / shortName`，价格来源 `trader` 取 `traderPrices[].priceRUB`（回退 `basePrice`）、`flea` 取 `lastLowPrice`；分类走 `handbookCategories`，未知归「其他」。

### 3.7 移植判断

**算法层全部可复刻**（本文已把全部常量、阈值、顺序写全）。**卡点在运行时**：

| 需要的东西 | 体积 | 与本项目铁律的关系 |
| --- | ---: | --- |
| `onnxruntime`（Python `onnxruntime` 或 C# `Microsoft.ML.OnnxRuntime`） | ~15 MB | ❌ 「零新增依赖」 |
| `det.onnx` | 4 729 474 B | ❌ 仓库会多 15 MB 二进制 |
| `rec.onnx` | 10 812 334 B | ❌ |
| `ppocr_keys_v1.txt` | 26 250 B | ✅ 无压力 |

→ 见 §5 的三条路径。

---

## 4. 游戏内小地图

### 4.1 本质：**它不是自己画的，是一个加载网页的置顶穿透窗口**

```
MiniMapWindow : Window
    Web : Microsoft.Web.WebView2.Wpf.WebView2
    → CoreWebView2.Navigate("https://tkf.xiaomeow.cn/minimap?size=260&opacity=0.85&shape=circle")
```

`BuildMiniUrl()`：

```
$"https://tkf.xiaomeow.cn/minimap?size={cfg.Size}&opacity={cfg.Opacity.ToString(InvariantCulture)}&shape={cfg.Shape}"
```

`MiniConfig`（8 个持久化字段）：`Enabled / Size / Corner / OffsetX / OffsetY / Opacity / Shape / IgnoreMouse`。

`ApplyBounds()`：

```
S = cfg.Size
isLeft  = (Corner == "top-left"  || Corner == "bottom-left")
isTop   = (Corner == "top-left"  || Corner == "top-right")
Width = Height = S
Left = (isLeft  ? workArea.Left + 16 : workArea.Right  - S - 16) + cfg.OffsetX
Top  = (isTop   ? workArea.Top  + 16 : workArea.Bottom - S - 16) + cfg.OffsetY
```

即四角吸附 + 固定 16 DIP 边距 + 偏移微调，边长 = `Size`（正方形）。

### 4.2 点击穿透与置顶（`OverlayScheduler`）

```
GWL_EXSTYLE = -20
WS_EX_LAYERED      = 0x00080000
WS_EX_TRANSPARENT  = 0x00000020
WS_EX_NOACTIVATE   = 0x00080000 | 0x08000000 | ...
WS_EX_TOOLWINDOW   = 0x00000080

ApplyOverlayStyles(hwnd, clickThrough):
    style = GetWindowLong(hwnd, GWL_EXSTYLE)
    style |= WS_EX_LAYERED | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
    if (clickThrough) style |= WS_EX_TRANSPARENT  else style &= ~WS_EX_TRANSPARENT
    SetWindowLong(hwnd, GWL_EXSTYLE, style)
    SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
```

`OverlayScheduler` 还负责：

- **Reassert**：定时把登记过的窗口重新提到 `HWND_TOPMOST`（别的置顶窗口会把它压下去）；
- **HideWhenIntersecting / WithoutOverlaysAsync**：抓图前把与自己重叠的浮层临时藏掉，抓完恢复 —— 免得 OCR 把浮层自己也识别进去；
- `PhysicalToDip`：多显示器 / 缩放比换算。

### 4.3 全图模式

```
EnterFull(): 保存 bounds → 居中放大到屏幕 → SetClickThrough(false) → 页面 ExecuteScript("window.__xmMiniFull('on')")
ExitFull():  还原 bounds → SetClickThrough(true) → ExecuteScript("window.__xmMiniFull('off')")
SendFullToPage(b): Web.CoreWebView2?.ExecuteScriptAsync($"window.__xmMiniFull && window.__xmMiniFull('{(b?"on":"off")}')")
```

日志：`[mini] 全图模式 开（{n}px，居中；穿透已关；过渡 {t}ms）` / `[mini] 全图模式 关（已还原角落与穿透）`。

### 4.4 登录态

`SyncLoginCookie()` 从 `Core.XiaomeowApi.GetToken()` 取 token，通过 `CoreWebView2.CookieManager` 写 cookie
`xiaomeow_token` @ `https://tkf.xiaomeow.cn/`（同时按 `.xiaomeow.cn` 域写一份）。

### 4.5 数据

- `Assets/key_locations.json`（27 663 B）= `itemId → { map, usage }`。**只有「这把钥匙在哪张图、开什么门」，没有坐标。**
- 玩家位置**不来自小地图自身**，而是和自动截图同一条链路（截图文件名里的 x/y/z + 四元数）。

### 4.6 移植判断

我们本来就是网页，**「mini 模式」这层几乎是白送的**：加一个 `?mini=1&size=&opacity=&shape=` 入口，隐藏全部面板、只留地图 + 玩家箭头 + 指北。难点只在「**全局置顶 + 点击穿透**」——浏览器窗口做不到，需要 Win32 改扩展样式（Python `ctypes` 足够，零依赖）。

---

## 5. 移植方案

### 第 1 步：零依赖，可以直接做

**5.1 自动截图修复**（`tools/keyinput.py` + `tools/serve.py`）

1. 键注入支持两种模式：`vk`（对齐他们）与 `scan`（现有默认，保持向后兼容）
2. 支持修饰键 `Ctrl+Shift+F10`，一次 `SendInput` 投递全部事件
3. 错误区分：`-1` = 键名解析失败 / 其它 = Win32 错误码
4. **到货校验**：发键后 N 毫秒内截图目录是否出现新文件 → 状态里给出 `arrived / pending / missing`
5. **「试拍一张」**：手工触发一次 + 立刻回读到货结果（不用等定时器、不用进战局）
6. 门条件可切：`require_raid`（默认开 = 现有行为；关掉后只要求游戏前台，对齐他们）

**5.2 小地图（页面内 mini 模式）**

`?mini=1&size=260&opacity=0.85&shape=circle` → 只渲染「地图 + 定位箭头 + 指北 + 比例尺」，背景透明，随截图位置实时更新。

### 第 2 步：可选宿主（需要一个原生窗口）

`tools/overlay.py`：用 `ctypes` 起一个无边框 Edge `--app=` 窗口，`SetWindowLong` 加 `WS_EX_LAYERED|WS_EX_TRANSPARENT|WS_EX_TOOLWINDOW|WS_EX_NOACTIVATE`，`SetWindowPos` 置顶，四角吸附。默认关。

### 第 3 步：价格 OCR（**需要拍板**）

| 方案 | 依赖 | 效果 | 代价 |
| --- | --- | --- | --- |
| A. 原样搬 ONNX | `onnxruntime` + 15.5 MB 模型 | 与对方一致（中文物品名全量识别） | 破坏「零新增依赖」，仓库 +15 MB |
| B. 只识别数字/价格 | 零依赖（自写模板匹配或七段式） | 只能读价格与数量，读不了物品名 | 价格仍需人工对照 |
| C. 只搬匹配与标注层 | 零依赖 | 有 OCR 结果就能匹配/去重/标注/算 PerSlot | 需要外部提供文本 |
| D. 不做 | — | — | — |

---

## 6. 可复现路径

| 用途 | 文件 |
| --- | --- |
| CIL → 伪代码渲染器 | `逆向参考/build-re-xiaomeow/dump_il.py` |
| AutoShot / InputSender / ScreenGrab 反汇编 | `逆向参考/build-re-xiaomeow/il_autoshot.txt` |
| OcrEngine / ImageOps / DbPostProcess / CtcDecode / ItemMatcher / ResultAnnotator | `逆向参考/build-re-xiaomeow/il_dump.txt`（Core.dll） |
| MiniMapWindow / OverlayScheduler | `逆向参考/build-re-xiaomeow/il_minimapwin.txt` |
| OcrHost / PriceScanner / PriceRoi / ScanResult | `逆向参考/build-re-xiaomeow/ocr_summary.txt` |

`dump_il.py` 用法：

```
python dump_il.py <rea inspect_managed_members 的 JSON 转储> <类型前缀...>
```

---

## 7. 实测：我们这边「自动截图一直没做好」的真正原因

**不是一个原因，是两层，第二层是物理限制。**

### 7.1 第一层：配置链路断了

读本机实际配置 `%APPDATA%\EFTMap\eftmap.config.json`：

```json
{ "game_dir": null, "screenshots_dir": null,
  "auto_screenshot": {"enabled": true, "interval_ms": 1000, "key": null} }
```

`/api/logstate` 的返回：

```json
{"enabled": true, "intervalMs": 1000, "key": null, "sent": 0,
 "available": false, "reason": "未取得截图按键：请在启动器里从日志同步或手动填写"}
```

链路是：`game_dir` 取不到 → `LogFollower` 没有日志可读 → `screenshot_key()` 返回 `None`
→ `key == null` → 门条件第一关就拦住 → **`sent` 永远是 0**。
开关是开着的，但一次都没发出去过。

> 对照：参考实现 `AutoShot.Apply` 在键名为空时**直接回落 `"PrintScreen"`**，绝不会因为
> 「还没配置」就永久停摆；它把配置问题交给用户改，而不是静默不发。

### 7.2 第二层：游戏在**另一台电脑**上（这是物理限制）

`/api/health` 实际返回 `"gameDir": "\\\\JJPC\\EFT"` —— 游戏目录是 **UNC 网络路径**，
说明游戏跑在另一台机器（JJPC）上，本机只是通过共享访问它的目录。

这直接判死自动截图：**`SendInput` 只能打进本机的前台窗口**，按键永远到不了 JJPC 上的游戏。
`launcher.py` 原本就有这条提示（`_refresh_remote_warning`），但它只在启动器界面里出现，
服务端的 `AutoShotter` 完全不知道这件事，于是照样每 100ms 空跑一次门检查、
报告一句「未取得截图按键」，把真正的原因盖住了。

本轮据此补的：`AutoShotter._remote_reason()` —— 游戏目录是 UNC 就直接拒绝发键并说明原因，
**`poll_once` 与 `shoot_once` 都会走这条判断**。顺带修了一个更隐蔽的坑：
`game_dir` 在配置文件里常常是空的（真正的路径来自命令行或 `default_game_dir()` 探测），
所以 `AutoShotter` 现在接收**注入的** `game_dir`，而不是只读 config —— 否则这条判断永远不触发。

> 结论：**在这台机器上，自动截图永远不可能生效**，无论怎么改注入方式。
> 要用它，得把本工具放到 JJPC 那台机器上跑；本机只做「看图」用（定位走共享目录照样能用）。

### 7.3 本轮据此做的修改（`R32`，全部向后兼容）

| 改动 | 位置 | 为什么 |
| --- | --- | --- |
| 键注入支持 `Ctrl+Shift+F10` 组合，一次 `SendInput` 投递全部事件 | `tools/keyinput.py` `parse_combo` / `build_inputs` | 原来组合键会直接被拒（「不认识这个按键」） |
| 键注入支持 `scan` / `vk` 两种模式，默认仍是 `scan` | `tools/keyinput.py` `_make_input(mode=)` | 参考实现走 vk；两种在不同机器上成功率不同 |
| **到货校验**：发键后看截图目录有没有出现新文件 | `tools/serve.py` `_arm_arrival` / `_check_arrival` | 「发出去了」和「拍到了」是两件事，以前分不清 |
| 连续 2 次没到货 → 自动改用 `vk` 再试 | `tools/serve.py` `MISSES_BEFORE_SWITCH` | 与其让用户猜，不如自己换一次 |
| **「试拍一张」**：一键发送 + 1200ms 后给结论，失败自动换 vk 再试 | `tools/launcher.py` `_try_shot` | 不用开自动截图、不用进战局就能定位卡在哪 |
| `POST /api/shot/now` | `tools/serve.py` | 供页面 / 调试一键触发 |
| 没有截图目录 / 目录不存在时**不校验**（`arrived` 保持 `null`） | `tools/serve.py` `_can_verify` | 把「目录配错」误报成「游戏没截图」比不校验更糟 |
| 缺键时的提示改成**指名到具体设置项**（游戏目录 / Logs / 手填 V） | `tools/serve.py` `_missing_key_reason` | 原来那句提示看不出该改哪里 |
| **网络路径的游戏目录直接拒绝发键**并说明「游戏在另一台电脑」 | `tools/serve.py` `_remote_reason` | 跨机器打不到；硬发只会把按键打进本机前台 |
| `AutoShotter` 接收注入的 `game_dir` | `tools/serve.py` `__init__` / `create_server` | config 里常常是空的，只读 config 会让上面那条判断失效 |
| 页面状态行显示注入方式与到货结果 | `app.js` `renderShotStatus` | 状态栏以前只显示「已发送 N 张」 |

新增测试 30 条（`tests/test_keyinput.py`、`tests/test_autoshot.py`、`tests/test_screenshot_parse.py`）。

### 7.4 附带：离线判据升级（任务栏外链转正）

`tasks.js` 里有一句 `guide.href = "https://tarkov.dev/task/" + id;`（任务栏「查看攻略」，
用户点击后新标签打开）。这条被两个老测试判成违规：

```python
assert "https://" not in body and "http://fonts" not in body, path
```

按项目约定「旧测试不删不弱化、冲突断言在原文件里升级」，判据改成两步
（`tests/_offline_guard.py`）：

1. **加载型写法一律失败** —— `fetch` / 动态 `import` / `new Worker|EventSource|WebSocket` /
   `<script src>` / `<link href>` / `<img src>` / CSS `url()` / `@import` 只要指向外部地址就拦；
2. **每一个外部地址都要过白名单**，没登记的照样失败。

白名单每条必须写明理由，且由测试校验（理由为空或过短会失败）：

| 前缀 | 为什么不算运行期联网 |
| --- | --- |
| `https://tarkov.dev/task/` | 只给 `<a>` 设 `href`，用户点击后新标签打开，页面自身不加载 |
| `http://www.w3.org/` | SVG / XML 命名空间，只是标识符，不发起请求 |
| `http://127.0.0.1`、`http://localhost` | 提示文本里的本机地址，指向本服务自己 |

刻意**不**收 `XMLHttpRequest` 与 `new Image()`：它们是通用 API，常用来请求本地接口、
预载本地图标，与「外部资源」无关。

新判据比旧的更严（旧判据根本不管 `fetch`），`tests/test_offline_guard.py` 18 条测试专门证明这件事：
9 种加载写法逐个拦、**白名单域名下的 `fetch` 也拦**、未登记域名照样失败，
只有纯跳转 / 命名空间 / 本机地址放行。

### 还没解决的

- **价格 OCR**：见 §5 第 3 步，尚未动工。

---

## 9. 自检工具：`tools/shot_selftest.py`（R32.5）

用户反馈：**网络路径不是根因**——他在游戏所在的那台电脑上跑过，自动截图同样不工作。
所以 §7.2 那条只是「顺带发现的另一个坑」，真正的原因还没定位。

而「自动截图没反应」有六七种彼此独立的原因，在旧实现里**表现完全一样**：
要么页面显示「已发送 0 张」，要么更糟——显示「已发送 N 张」但一个键都没进游戏。
所以与其继续猜，不如把整条链路做成可执行的自检。

```
python tools/shot_selftest.py                # 只读检查，不发任何按键
python tools/shot_selftest.py --send         # 本脚本真的按一次，并等到货结果
python tools/shot_selftest.py --manual       # 你自己在游戏里按一次，只看目录（最权威）
```

### 9.1 九步检查

| # | 检查 | 判定 | 失败意味着 |
| --- | --- | --- | --- |
| 1 | 平台 | 非 Windows 直接退出 | 模拟输入不可用 |
| 2 | 本工具是否管理员 | 读自己的 TokenElevation | 决定第 5 步怎么判 |
| 3 | 游戏目录 / 游戏进程 | 目录可达 + `tasklist` 查进程 | 游戏没开，或目录指错 |
| 4 | 前台窗口 | `GetForegroundWindow` → 进程名 | 模拟按键只能打进前台窗口 |
| 5 | **权限对等** | 目标 TokenElevation vs 自己 | 游戏管理员 + 工具普通 = UIPI **静默丢弃** `SendInput` |
| 6 | **日志 / 战局阶段** | 回放日志尾 512 KB 推 phase | 这道门是**我方独有**的，判错就永远不发 |
| 7 | 截图键解析 | `parse_combo` | 键名认不出 / 修饰键写法不对 |
| 8 | 注入方式 | `preferred_mode` | PrintScreen 家族强制虚拟键码 |
| 9 | 截图目录 | 存在 + 可枚举 | 不存在就没法判断「到底拍到没有」 |

结论只报**第一个 FAIL**：后面的失败大多是它的连锁反应，先说根因才有用。

### 9.2 `--manual`：一刀切开两类完全不同的故障

这是最值得加的一步。让**人自己**按一次游戏内的截图键，只盯目录：

| 手动按的结果 | 结论 |
| --- | --- |
| 有图 | 游戏截图本身是好的 → 问题在**注入层**（权限 / 合成输入被拒 / 反作弊） |
| 没图 | 问题在**游戏侧**（键位没绑、目录不对、截图功能关了）→ 再怎么调注入方式都没用 |

没有这一步，两种故障在日志和界面上长得一模一样，只能靠猜。

### 9.3 本轮同时修的两个真问题

**（1）`SendInput` 会被 UIPI 静默丢弃。** 游戏以管理员运行、工具是普通权限时，
Windows 会丢掉这条注入输入，而 `SendInput` **返回成功**——于是页面显示「已发送 N 张」，
游戏一个键都没收到。现在 `keyinput.injection_blocked()` 比较两边的 TokenElevation，
不对等就直接拦下并提示「请右键以管理员身份运行」。

**（2）PrintScreen / SysRq 用扫描码注入无效。** 这一族键（`VK_SNAPSHOT`，scan 0x37 + 扩展位）
用 `KEYEVENTF_SCANCODE` 注入时，系统按「截屏到剪贴板」处理，游戏侧收不到。
`keyinput.preferred_mode()` 现在对它们**强制虚拟键码**（参考实现全程走 VK，不受此影响）。

> 顺带修掉一个 ctypes 坑：64 位下进程/令牌句柄是 8 字节指针，必须显式声明
> `c_void_p` 的 `argtypes`，否则传伪句柄 `-1` 会 `OverflowError`。

### 9.4 本机实测输出（连的是 `\\JJPC\EFT`）

```
[ OK ] 平台：Windows-2022Server-10.0.20348-SP0
[ OK ] 本工具权限：管理员
[ OK ] 游戏目录：\\JJPC\EFT
[WARN] 游戏进程：没检测到 escapefromtarkov.exe（没开游戏时属正常）
[WARN] 前台窗口：chrome.exe (pid 44084)（不是游戏）
[ -- ] 权限对等：游戏不在前台，跳过
[ OK ] 日志 / 战局阶段：start（会话 log_2026.11.01_21-07-35…）—— 日志门是开的
[ OK ] 截图键：V（vk 0x56 / scan 0x2F）
[ OK ] 注入方式：scan
[FAIL] 截图目录：C:\Users\…\Documents\Escape from Tarkov\Screenshots（不存在）
```

**两个有用的结论**：
1. 从这台机器读 `\\JJPC\EFT` 的日志**是通的**，phase 一路解析到 `start` —— 所以「日志门」不像主因；
2. 截图键是 **`V`**（不是 PrintScreen），所以 9.3（2）那条也不像主因。
   那么剩下的重点就是：**权限对等**（第 5 步，必须等游戏在前台时再看）
   与 **游戏到底认不认合成输入**（用 `--manual` 一次切开）。

> 这两条当时都被推翻了：换到本机 `D:\Games\EFT` 后，截图键是 `SysReq`，
> 而真因正是「PrtSc 被系统截屏工具吃掉」。见 §10。

---

## 8. 小地图：已落地（R32.2）

按 §4 的结论分两层做，**都不新增任何依赖**。

### 8.1 页面 mini 模式：`?mini=1`

| 参数 | 默认 | 作用 |
| --- | --- | --- |
| `mini` | 关 | `1` / `true` / 空值 = 开启；**不带就是普通页面，行为完全不变** |
| `size` | `260` | 期望边长 px（钳 120..1200），写进 `data-mini-size` 供宿主读；页面本身自适应窗口 |
| `opacity` | `0.9` | 地图不透明度（钳 0.3..1） |
| `shape` | `circle` | `circle`（圆形裁剪）/ `square` |
| `labels` | `0` | 是否显示地图标签；260px 里铺整图时文字会糊成一团，默认关 |

实现刻意做得**极窄**：

- `app.js` 的 `applyMiniMode()` 只做三件事：给 `body` 挂 `tk-mini`、给 `html` 挂 `tk-mini-root`、
  在 `:root` 上写 `--mini-opacity`；再加 `data-mini-size / shape / labels` 三个属性。**不碰任何布局逻辑。**
- `style.css` 末尾一整段都挂在 `body.tk-mini…` / `html.tk-mini-root` 下（有测试逐条校验这一点），
  不带参数时**一条都不成立**，所以主页面零影响。
- 隐藏的东西：`#menubar`、`#sidebar`、`#task-panel`、`#sidebar-expand`、`#task-panel-expand`、`#hud`、`.statusbar`、`#error`。
- 地图用 `#map-view { position: fixed; inset: 0 }` 铺满，绕开 `.workspace` 原有的 flex 高度计算。

两个实测踩到的坑（都已修）：

1. **只把 `body` 设透明不够** —— `html, body` 都铺了 `--xp-face`，圆形裁剪外面会露出一圈米色；
   必须连 `html` 一起透明（所以多了一个 `tk-mini-root` class）。
2. **别在 `body.tk-mini` 里再声明 `--mini-opacity`** —— 那会盖掉 `:root` 上的值，让 `?opacity=` 静默失效。
   改成 `opacity: var(--mini-opacity, 0.9)` 用回落值。

验收（headless Chrome 实测，未弹窗）：

| 场景 | body class | 面板 display | clip-path | #viewport opacity | 标题 |
| --- | --- | --- | --- | --- | --- |
| 普通页面 | （空） | flex / flex / flex | none | 1 | EFT 互动地图 · 离线免费版 |
| `?mini=1` | `tk-mini` | none / none / none | `circle(closest-side at 50% 50%)` | 0.9 | EFT 小地图 |
| `?mini=1&shape=square&opacity=0.5` | `tk-mini` | none / none / none | none | 0.5 | EFT 小地图 |

截图确认：圆形裁剪正常、地图居中铺满、四角切掉、无任何菜单/侧栏/HUD 残留。

### 8.2 置顶宿主窗：`tools/overlay.py`

```
python tools/overlay.py                      # 右下角 260px 圆形 90%
python tools/overlay.py --corner top-left --size 300 --opacity 0.8 --shape square
python tools/overlay.py --dry-run            # 只打印计划，不起窗口
```

- 用 Edge `--app=<mini url>` 起一个无边框窗口，`--window-size` / `--window-position` 直接给定位置；
- 再用 `SetWindowLong` 去掉 `WS_CAPTION|WS_THICKFRAME|WS_SYSMENU|WS_MINIMIZEBOX|WS_MAXIMIZEBOX`，
  加 `WS_EX_LAYERED|WS_EX_TRANSPARENT|WS_EX_NOACTIVATE|WS_EX_TOOLWINDOW`，
  最后 `SetWindowPos(HWND_TOPMOST, SWP_NOMOVE|SWP_NOSIZE|SWP_NOACTIVATE|SWP_SHOWWINDOW)`；
- 四角吸附由 `plan_window()` 算（边距 16，`right - size - 16`），与参考实现 `ApplyBounds` 逐字对齐，
  已用 1920×1040 / 负原点工作区 / 越界尺寸三种输入验证；
- 独立 `--user-data-dir`，不污染用户日常浏览器；找不到 Edge 就明确报错，不下载、不换浏览器。

> 未验证的部分：真起窗口那一段（`launch` + `make_overlay`）没法在无人值守时跑——
> 它会在用户屏幕上弹窗。逻辑与参数都按参考实现写好，`--dry-run` 可先核对计划。

### 8.3 怎么用

1. 先正常启动 `python tools/serve.py --port 8810`（或直接跑启动器）；
2. 想要小窗：`python tools/overlay.py --corner bottom-right`；
3. 想先看效果：浏览器直接开 `http://127.0.0.1:8810/index.html?mini=1`。

---

## 10. 真因确认：`Print Screen` 被 Windows 抢走了（R32.8，2026-11-02 实测）

用户把 EFT 装到本机 `D:\Games\EFT` 之后，按 §9 的流程一次定位到了根因。**跟注入方式、
权限、日志门都无关** —— 是截图键本身到不了游戏。

### 10.1 定位过程（三次实验，每次只改一个变量）

| 实验 | 操作 | 结果 | 排除了什么 |
| --- | --- | --- | --- |
| A | 游戏启动后跑只读自检 | 九项里八项 `OK`，只有「截图目录」因游戏还没运行过而缺 | 不是环境 / 配置问题 |
| B | `--send` 由脚本按 PrtSc（游戏内绑定 = `SysReq`） | 按键送出去了，目录**没有**新文件 | 不是「没发出去」 |
| C | `--manual` 让人**自己**按一次 PrtSc | 同样没有新文件 | **不是模拟输入的问题** |

C 是关键：人手按也不出图，说明问题在**游戏以外** —— 键盘事件根本没到达游戏。

再查系统设置（注册表项 `HKCU:\Control Panel\Keyboard` 下的
`PrintScreenKeyForSnippingEnabled`）**未设置 = 系统默认开启**。

Windows 11 默认「按 **PrtSc** 打开截屏工具」。这个键在**到达焦点窗口之前**就被系统吃掉了，
所以游戏永远收不到。这也解释了用户那句「在游戏电脑上跑过也不行」——**换机器一样**，
只要那台 Windows 的开箱默认没改。

### 10.2 修复：把游戏内截图键换成普通功能键

游戏 → 设置 → 控制 → 界面 → 截图，从 `SysReq` 改成 **`F10`**。改完立刻验证：

```
python tools/shot_selftest.py --send --key F10 --wait-foreground 30

[ OK ] 截图键：F10（vk 0x79 / scan 0x44）
[ OK ] 注入方式：scan
[ OK ] 到货：目录里出现了新截图，自动截图这条链路是通的。
```

新图 `2026-11-02[14-28]_28.98, 2.51, 37.98_…` 带坐标 → 确实是战局内的真实截图。

再跑**真实服务**的自动截图循环（不是自检脚本）：

```
0s  sent=0 arrived=None mode=scan reason=游戏窗口不在前台（当前前台：WorkBuddy.exe）
2s  sent=1 arrived=True  mode=scan      [图片 9]
3s  sent=2 arrived=True  mode=scan      [图片 10]
4s  sent=3 arrived=True  mode=scan      [图片 11]
5s  sent=4 arrived=True  mode=scan      [图片 12]
6s  sent=5 arrived=True  mode=scan      [图片 13]
---- 结果 ----
已发送 = 5 | 到货 = True | 注入方式 = scan | 新增图片 = 5
```

**每一拍都到货**，`arrived` 一直是 `True`，没有触发 `vk` 回退。

### 10.3 代码改动

| 改动 | 位置 | 理由 |
| --- | --- | --- |
| 新增第三种注入方式 `MODE_POST`：`PostMessage(WM_KEYDOWN/UP)` 直接写目标窗口消息队列 | `tools/keyinput.py` `post_key` / `_post_lparam` / `foreground_hwnd` | `SendInput` 是系统级输入，要先过全局键盘钩子与热键注册；`PostMessage` 绕开这条链路 |
| `send_key(name, MODE_POST)` 分派到 `post_key`；`MODES` 变成 `("scan","vk","post")` | `tools/keyinput.py` | 让 `AutoShotter` 的回退链也能用到它 |
| 默认截图间隔 `1000 → 5000` ms | `tools/config.py` `SHOT_INTERVAL_DEFAULT` | 一张图约 600 KB，1 秒一张 = **每小时约 2 GB**，40 分钟战局能吃掉 1.6 GB |
| 两条断言改为盯常量（不再硬编码 1000） | `tests/test_config.py` | 迁移而非删除，语义仍是「默认值符合预期」 |

`post` 目前**不是默认方式**：它只对「按窗口消息读键盘」的程序有效，通用性不如 `SendInput`。
留着它是为了「PrtSc 被系统吃掉、又不想改键位」这种情况下的兜底。

### 10.4 结论

- **自动截图功能一直是好的**，坏的是「用 PrtSc 当截图键」这个前提；
- 诊断顺序应当是 **手动按 → 有图没图**（`--manual`），而不是先怀疑注入；
- 本机 `%APPDATA%\EFTMap\eftmap.config.json` 现已写入
  `game_dir=D:/Games/EFT`、`screenshots_dir=…\Screenshots`、
  `auto_screenshot={enabled:true, interval_ms:5000, key:F10}`，启动器 / 服务不需要再配一次。

---

## 11. 小浮窗：设置面板 + 实时生效（R32.9，2026-11-02）

用户反馈两条：**小窗不能调大小和位置**、**不能设透明度**，要求把这些选项放进地图界面的
「设置」按钮里。于是小浮窗从「命令行一把梭」改成「设置面板驱动」。

### 11.1 设置面板（菜单栏「设置」）

| 选项 | 范围 | 作用 |
| --- | --- | --- |
| 显示小浮窗 | 开 / 关 | 起停宿主进程（`POST /api/overlay`） |
| 大小 | 120~600 px | 小窗客户区边长 |
| 透明度 | 30%~100% | **窗口整体不透明度**（能透出游戏画面） |
| 位置 | 四角 | 吸附角落 |
| 偏移 X / Y | ±200 px | 在角落基础上再挪 |
| 形状 | 方 / 圆 | 圆形时四角用 `--bg` 涂色 |
| 跟随玩家 | 开 / 关 | 视野固定在玩家周围 |
| 显示标签 | 开 / 关 | 小尺寸下默认关 |
| 点击穿透 | 开 / 关 | 关掉后可以点小窗里的东西 |

**改完立刻生效**：宿主每 0.5 秒读一次 `eftmap.config.json` 的 `overlay` 段，
位置 / 大小 / 透明度 / 点击穿透直接套到窗口上，不用重启小窗。

### 11.2 透明度怎么做的（实测可用）

`SetLayeredWindowAttributes(hwnd, 0, alpha, LWA_ALPHA)` 对 Chromium 窗口**有效**：
设 47% 时能明显透出后面的游戏画面。因为窗口本来就带 `WS_EX_LAYERED`（点击穿透要用），
这一步零额外代价。

透明度由**宿主**统一控制，所以页面里的地图不再压暗一次（URL 带 `ha=1`）——
否则「窗口 50% × 地图 50%」叠成 25%，观感发灰。

### 11.3 尺寸收敛的坑（第一版是错的）

目标是「客户区」正好 260×260（Chromium 自绘的标题栏会吃掉一截高度，要补回来）。

第一版公式 `fw = w + (w - cw)`（`w` 是**目标**、`cw` 是**当前客户区**）是错的：
它把目标值当成当前窗口值，会在两个尺寸之间来回振荡——实测窗口卡在 237×340。

正确做法是量**边框增量**：

```
dw, dh = 当前窗口尺寸 - 当前客户区尺寸      # 标题栏 / 边框吃掉的部分
新窗口 = 目标客户区 + (dw, dh)
```

改完实测：请求 200 → 客户区精确 200×200（窗口 214×207）；请求 420 → 客户区 420×420。

### 11.4 起停链路

```
设置面板「显示小浮窗」 → POST /api/overlay {enabled} → 服务端拉起/关闭 tools/overlay.py
                      ↘ 同时写进 config.overlay.enabled（宿主每 0.5s 读这份配置）
```

宿主自己也会在 `enabled=false` 时退出——即使服务端没来得及关，设置里一取消就消失。

### 11.5 已知限制

- **标题栏去不掉**：那条「EFT 小地图」是 Chromium **自绘**的（不是系统边框），
  改 Win32 样式、`WS_POPUP`、`SWP_FRAMECHANGED`、`RedrawWindow` 都试过，无效。
  参考实现没有这个问题，是因为它用 **WebView2**（内嵌控件，无浏览器 UI），
  而那要引入新依赖。宿主用 `fit_client` 把标题栏吃掉的高度补回来，地图本体仍是请求的尺寸。
- **独占全屏**的游戏会把置顶窗挤下去；宿主每轮都重新钉一次 `HWND_TOPMOST` 缓解，
  但建议游戏用「无边框窗口化」。



---

## 12. 自动截图的门条件：阶段判定的两个真 bug（R32.10，2026-11-02）

用户反馈：**战局还没开始就在自动截图**。设计上自动截图有三道门：

1. 配置里开了「自动截图」；
2. **日志阶段 == `start`**（`PlayerSpawnEvent` 之后才算战局开始）；
3. 游戏窗口在前台（切出去就停）。

排查结果：第 2 道门**判定本身是错的**——不是门没写，是喂给它的阶段是脏的。

### 12.1 bug 一：两条日志流没按时间合并

`application` 与 `backend` 是两条独立的日志文件，`poll_once` 一轮把两条都读出来，
但**按通道顺序**合并（先 application 后 backend），不看时间戳。

实测回放时的状态：

| 时间 | 通道 | 事件 | 相位 |
| --- | --- | --- | --- |
| 15:39:19 | application | `PlayerSpawnEvent` | **start** |
| 15:35:37 | backend | `client/match/local/end` | **end** |

按到达顺序合并 → 最终相位 = `end`（15:35 的旧事件盖掉了 15:39 的新状态）。
人已经在第 3 局里（15:50:30 还拍出了带坐标的图），快照却说「不在战局中」；
反过来，若 start 恰好排在后面，就会**在菜单里乱拍**。

修法两处：

1. `poll_once` 把两条通道的事件**按时间戳排序**后再合并/广播；
2. `merge_raid` 加时间戳守卫：**旧事件一律不许覆盖新状态**（`ts < prev.ts` 直接丢弃）。

### 12.2 bug 二：换会话没清战局状态

`LogFollower` 在切换到新会话时清了偏移、解析器、reason，**但没清 `_last_raid`**。
游戏崩过 / 被强退时没有 `end` 行，旧的 `start` 会带进新会话，自动截图在菜单里继续拍。
现在换会话一律回到干净状态。

### 12.3 加固：`CompleteSelectedProfile` 作 end 的第二条信号

`end` 原来只认 backend 的 `client/match/local/end` 一个来源，漏读就卡 `start`。
实测 application 通道的 `CompleteSelectedProfile`（回到菜单时的档案加载）**只出现在战局外**：

```
外 13:51:19  CompleteSelectedProfile      ← 游戏刚启动
外 14:36:40  CompleteSelectedProfile      ← 第 1 局结束 15 秒后
外 15:35:48  CompleteSelectedProfile      ← 第 2 局结束 13 秒后
外 15:36:51  CompleteSelectedProfile
（战局内 0 次）
```

所以它现在也产生 `end` 事件，作为兜底。

### 12.4 修完的实测

```
修复前：raid = {phase: "end",   ts: 15:35:37.659, ...}   ← 第 2 局的结束
修复后：raid = {phase: "start", ts: 15:39:19.517, ...}   ← 第 3 局的出生（真实状态）
```

三道门的最终行为：

| 场景 | 自动截图 |
| --- | --- |
| 匹配中 / 加载中（`matching` / `loading`） | 停 |
| 玩家出生后（`PlayerSpawnEvent` → `start`） | 拍 |
| 切到别的窗口 | 停（前台检查） |
| 回到菜单 / 战局结束 | 停 |

新增测试 5 条（`tests/test_eftlog.py`）：阶段不能倒流、没时间戳照单全收、
跨通道按时间合并、换会话清状态、回菜单判 end。
