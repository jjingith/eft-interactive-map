# -*- coding: utf-8 -*-
"""构建期工具（R29.1）：生成配装工作台「空装备槽」的**原图素描**占位图。

需求
----
配装工作台左侧装备栏在空槽时显示占位图形。R28.0 用户要求：
「换成灰色的装备轮廓图，描边要精细」——即**只画轮廓线、内部不填充**的线稿
（此前 R18.1 是白底纯黑剪影，R21.0 是灰白填充 + 灰内描边，都是实心块）。
且每类槽位必须对应**指定装备**的真实轮廓：

    helmet       HighCom Striker ULACH IIIA   5b40e1525acfc4771e1c6611
    armor        6B45 防弹衣                   68948a95d8f2b85fb705e2a6
    rig          Azimut SS "Zhuk" 胸挂（黑）    603648ff5a45383c122086ac
    backpack     Pilgrim 旅行包                59e763f286f7742ee57895da
    headphones   Peltor ComTac VI 耳机（狼棕）  66b5f6985891c84aab75ca76
    glasses      NPP KIASS Condor 护目镜        603409c80ca681766b6a0fb2
    face         巴拉克拉瓦头套                 572b7f1624597762ae139822
    gun(主1/主2) AK-74 5.45x39 突击步枪        5bf3e03b0db834001d2c4a9c
    holster      Glock 17 9x19 手枪            5a7ae0c351dfba0017554310
    melee        ER「支点」刺刀                 54491bb74bdc2d09088b4567

素材与做法
----------
主路径：`assets/ui/placeholders/_src/{id}.webp`（构建期用 `--fetch` 从
`https://assets.tarkov.dev/{id}-base-image.webp` 抓下来的**透明底**大图，127–442 px）。
Alpha 通道就是真实模型轮廓，二值化后取形态学梯度（膨胀 − 腐蚀）得到骑在轮廓上的细环，
再按 OUT_SCALE 放大画布输出 —— 形状与比例完全来自真实装备模型渲染，无需猜测。

回退路径：若 `_src` 里没有对应文件，退回到 `assets/icons-items/{id}.webp`
（64×64 **不透明**灰底图标）。这种图必须先做前景分割，见 `split_foreground()` 注释。
回退产物的轮廓质量明显低于主路径，manifest 里会如实标注 `source: "icons-items-fallback"`。

输出：`assets/ui/placeholders/{key}.png`（RGBA、透明底、灰色 #808080 细轮廓、无任何文字；
画布为卡片尺寸的 `OUT_SCALE` 倍，HiDPI 屏不发虚）。
原始素材只读不改；运行期零网络请求；不使用任何外部图片 URL。

用法：
    python tools/build_slot_placeholders.py              # 只用本地素材
    python tools/build_slot_placeholders.py --fetch      # 缺 _src 时先走代理下载
    python tools/build_slot_placeholders.py --debug      # 额外输出联系表
"""
import json
import math
import os
import sys
from collections import deque

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

_sin = math.sin

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICON_DIR = os.path.join(ROOT, "assets", "icons-items")
OUT_DIR = os.path.join(ROOT, "assets", "ui", "placeholders")
SRC_DIR = os.path.join(OUT_DIR, "_src")
DEBUG_DIR = os.path.join(OUT_DIR, "_debug")

# R18.1 原：纯黑剪影（INK=(0,0,0)）。R21.0 需求改为「灰白剪影 + 灰色描边」：
# 空槽卡片是深色(#171717)，纯黑剪影几乎不可见；改成灰白填充 + 灰描边后既保留
# 真实装备轮廓，又能在深色卡片上清晰呈现。
# R29.0：用户指出「只要外轮廓」不算结构素描 —— 要的是**用线讲清形体结构**。
# 因此画四层（外轮廓 / 内侧等距结构线 / 中轴+剖面辅助线 / 暗部排线），
# 线宽一律按「显示 px」定义，再按 OUT_SCALE×SS 换算到工作分辨率。
# R29.1：用户要求「直拿原图套个转素描的滤镜」——不再人工构造轮廓/辅助线，
# 改用局部对比度提取笔触（白纸黑线），结构全部来自原图本身。
# R29.2：规格改为「原生分辨率提笔触 + 铅笔灰线稿」。
#   关键教训（R29.1 的问题根源）：占位源图只有 127–253 px，若先放大到 4× 画布再提笔触，
#   细节已被插值糊掉，笔触必然发虚。现在改为**在源分辨率上提线**，只在最后做小幅放大。
SKETCH_RADIUS = 0.055           # 局部对比度半径（相对短边，越大笔触越「大块」）
SKETCH_GAIN = 2.6               # 笔触强度增益（越大越黑越密）
SKETCH_CAP = 150                # 笔触峰值上限：防止暗部糊成黑块（局部对比度在深色区会爆）
SKETCH_FLOOR = 40               # 笔触阈值下限：低于此值视为纸面留白
SKETCH_CONTRAST = 1.6           # 笔触对比提升（越大线越硬朗）
SKETCH_INK = 110                # 笔触颜色（铅笔灰 #6e6e6e；比纯黑柔和，比浅灰可辨）
OUTLINE_ALPHA = 0.60            # 形状轮廓不透明度（源自 Alpha 边缘，保证外形永远可辨）
OUT_SCALE_MAX = 2               # 输出画布最多放大到卡片尺寸的 2 倍——再放大只是插值，没有新细节
CLOSE_PX = 0.6                  # 闭运算半径（**显示像素**）：并掉 Alpha 阈值留下的亚像素细缝
OUT_SCALE = 2                   # 输出画布 = 卡片尺寸 × 2（HiDPI 2× 屏够用；再大只是插值）
SS = 2                          # 作画超采样倍数（work = 输出 × SS，缩回时得到抗锯齿）
MARGIN = 0.06                   # 剪影相对画布边的最小留白比例
ALPHA_CUT = 128             # Alpha 二值化阈值（透明底素材）
MIN_PART = 12               # 小于该像素数的孤立碎块丢弃（Alpha 边缘噪点）
LOC_TOL = 8                 # 回退路径：区域生长的局部色差容差
BASE_IMAGE_URL = "https://assets.tarkov.dev/{id}-base-image.webp"

# key -> (物品 id, 素材对应的装备名, 目标画布宽, 目标画布高[, 取图用的物品 id])
# 画布尺寸 = style.css 里对应卡片的实际内框（网格轨道 65/19/33/37/108 列 × 78/107/108 行，
# 扣掉 1px 边框）：这样 object-fit: contain 之后白底正好铺满卡片，不露出底色。
# 主武器 1 与 主武器 2 共用同一张 AK-74 剪影（同一文件，不重复出图）。
#
# R18.2 修正：枪械**本体**的 base-image 是裁切后的侧视图 —— EFT 的枪托 / 握把是可拆的独立
# 配件（mod_stock / mod_pistol_grip），所以本体图只有机匣 + 枪管 + 弹匣，没有枪托，看起来
# 像"机匣部件"而不是完整枪。改用**预设（Preset）**的 base-image：预设代表完整装配形态，
# 图里枪管、机匣、弹匣、握把、枪托齐全。第 5 列就是"取图用的物品 id"（预设），
# 第 1 列仍是槽位代表的真实装备（AK-74 本体 / Glock 17 本体），两者分开记录在 manifest 里。
SLOTS = [
    ("helmet",     "5b40e1525acfc4771e1c6611", "HighCom Striker ULACH IIIA 头盔（黑色）", 76, 76),
    ("armor",      "68948a95d8f2b85fb705e2a6", "6B45 防弹衣（数码丛林迷彩）",           106, 105),
    ("rig",        "603648ff5a45383c122086ac", 'Azimut SS "Zhuk" 胸挂（黑）',            106, 105),
    ("backpack",   "59e763f286f7742ee57895da", "Pilgrim 旅行包",                          106, 106),
    ("headphones", "66b5f6985891c84aab75ca76", "Peltor ComTac VI 耳机（狼棕色）",          63, 61),
    ("glasses",    "603409c80ca681766b6a0fb2", "NPP KIASS Condor 护目镜",                  63, 61),
    ("face",       "572b7f1624597762ae139822", "巴拉克拉瓦头套",                          63, 61),
    ("primary",    "5bf3e03b0db834001d2c4a9c", "AK-74 5.45x39 突击步枪",                260, 106,
                   "5c0c1ce886f77401c119d014"),
    ("holster",    "5a7ae0c351dfba0017554310", "Glock 17 9x19 手枪",                     152, 106,
                   "5a88acfb86f77457fd2c0d8f"),
    ("melee",      "54491bb74bdc2d09088b4567", "ER「支点」刺刀",                          106, 106),
]


# ----------------------------------------------------------------- 素材获取
def fetch_sources(missing_ids):
    """构建期下载透明底 base-image（走用户指定代理，不进入运行期）。"""
    import urllib.request
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or "http://127.0.0.1:7896"
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    # 上游对没有浏览器 UA 的请求直接 403；带 UA + Referer 才能拿到图
    opener.addheaders = [
        ("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
        ("Referer", "https://tarkov.dev/"),
    ]
    os.makedirs(SRC_DIR, exist_ok=True)
    ok = 0
    for item_id in missing_ids:
        url = BASE_IMAGE_URL.format(id=item_id)
        dst = os.path.join(SRC_DIR, "%s.webp" % item_id)
        try:
            with opener.open(url, timeout=30) as resp:
                data = resp.read()
            if not data:
                raise ValueError("空响应")
            with open(dst, "wb") as f:
                f.write(data)
            print("      下载 %s (%d B)" % (os.path.basename(dst), len(data)))
            ok += 1
        except Exception as exc:      # noqa: BLE001 - 单件失败不阻断，回退到本地图标分割
            print("      下载失败 %s：%s" % (url, exc))
    return ok


# ----------------------------------------------------------------- 通用工具
def otsu_threshold(vals):
    """Otsu 最大类间方差阈值。"""
    hist = [0] * 256
    for v in vals:
        hist[min(255, max(0, v))] += 1
    total = len(vals)
    if total == 0:
        return 0
    sum_all = sum(i * hist[i] for i in range(256))
    w_b = 0
    sum_b = 0
    best = -1.0
    thr = 0
    for i in range(256):
        w_b += hist[i]
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += i * hist[i]
        m_b = sum_b / float(w_b)
        m_f = (sum_all - sum_b) / float(w_f)
        var = w_b * w_f * (m_b - m_f) * (m_b - m_f)
        if var > best:
            best = var
            thr = i
    return thr


def components(mask, w, h, want):
    """4 邻域连通域。"""
    seen = [[False] * w for _ in range(h)]
    out = []
    for sy in range(h):
        for sx in range(w):
            if mask[sy][sx] != want or seen[sy][sx]:
                continue
            comp = []
            q = deque([(sx, sy)])
            seen[sy][sx] = True
            while q:
                x, y = q.popleft()
                comp.append((x, y))
                for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                    if 0 <= nx < w and 0 <= ny < h and mask[ny][nx] == want and not seen[ny][nx]:
                        seen[ny][nx] = True
                        q.append((nx, ny))
            out.append(comp)
    return out


def drop_specks(mask, w, h, min_area=MIN_PART):
    """丢掉 alpha 边缘 / 压缩噪点造成的孤立小块；保留所有真正的分离部件。"""
    comps = components(mask, w, h, True)
    keep = set()
    for comp in comps:
        if len(comp) >= min_area:
            keep.update(comp)
    out = [[False] * w for _ in range(h)]
    for x, y in keep:
        out[y][x] = True
    return out, len(comps)


def tight_bbox(mask, w, h):
    x0, y0, x1, y1 = w, h, -1, -1
    for y in range(h):
        row = mask[y]
        for x in range(w):
            if row[x]:
                if x < x0: x0 = x
                if x > x1: x1 = x
                if y < y0: y0 = y
                if y > y1: y1 = y
    return None if x1 < 0 else (x0, y0, x1 + 1, y1 + 1)


# ------------------------------------------------------- 主路径：Alpha 剪影
def fill_holes(mask, w, h, max_ratio=0.015):
    """填掉「完全被主体包围」且面积很小的透明孔，其余镂空保留。

    只处理不与画布边界连通的空白连通域；面积上限取主体面积的 1.5%：
    这样 Alpha 边缘噪点、模型内腔的小孔会被填平，而耳机头梁内圈、头盔面罩开口、
    护目镜两片镜片之间、刺刀挂环、以及**枪械的扳机护圈**这些镂空会原样留下 ——
    它们是装备的可辨认特征。上限设 4% 时 Glock 的扳机护圈孔（约占主体 3.8%）
    会被当成噪点填平，剪影退化成一块实心黑，R18.2 已下调。
    """
    solid = sum(row.count(True) for row in mask)
    limit = max(8, int(solid * max_ratio))
    filled = 0
    for comp in components(mask, w, h, False):
        if len(comp) > limit:
            continue
        if any(x == 0 or y == 0 or x == w - 1 or y == h - 1 for x, y in comp):
            continue
        for x, y in comp:
            mask[y][x] = True
        filled += 1
    return mask, filled


def mask_from_alpha(path):
    """透明底素材 -> 布尔主体掩膜。Alpha 就是现成的轮廓，无需任何猜测。"""
    im = Image.open(path).convert("RGBA")
    w, h = im.size
    alpha = im.split()[3]
    mask = [[alpha.getpixel((x, y)) > ALPHA_CUT for x in range(w)] for y in range(h)]
    mask, parts = drop_specks(mask, w, h)
    mask, holes = fill_holes(mask, w, h)
    return mask, w, h, parts, holes


# --------------------------------------------- 回退路径：不透明图标前景分割
def split_foreground(img):
    """不透明灰底图标 -> 主体掩膜。

    这批 webp 背景是带 ±10 抖动的深色纹理，物品本身常常也是深色（黑枪、头套、护目镜），
    所以不能用「比背景亮就是物品」这种亮度阈值，否则暗色装备会被掏空成镂空剪影。
    这里用四层收口：

      1. 裁掉外 1px 装饰边框，剩余区域 3×3 中值滤波压掉背景噪点；
      2. 背景基准 = 滤波后外环像素的中位色（各图标背景亮度 12–50 不等，不能写死）；
      3. 从画布内侧边界做 BFS 区域生长，必须**同时**满足「与已判定背景像素局部色差
         <= LOC_TOL」和「与背景基准全局距离 <= d_t(Otsu)」才继续扩散 ——
         局部条件跟随渐变背景，全局条件在柔和过渡处收口；
      4. 由闭运算封 1–2px 断口、补内部洞、开运算去毛刺。

    注意：这条路径的轮廓质量低于 Alpha 主路径，仅在没有透明底素材时兜底。
    """
    core = img.crop((1, 1, img.size[0] - 1, img.size[1] - 1)).filter(ImageFilter.MedianFilter(3))
    px = core.load()
    w, h = core.size
    ring = []
    for x in range(w):
        ring.append(px[x, 0])
        ring.append(px[x, h - 1])
    for y in range(h):
        ring.append(px[0, y])
        ring.append(px[w - 1, y])
    base = tuple(sorted(c[k] for c in ring)[len(ring) // 2] for k in range(3))

    dist = [[0] * w for _ in range(h)]
    flat = []
    for y in range(h):
        for x in range(w):
            c = px[x, y]
            d = min(255, (abs(c[0] - base[0]) + abs(c[1] - base[1]) + abs(c[2] - base[2])) // 3)
            dist[y][x] = d
            flat.append(d)
    d_t = max(8, min(16, otsu_threshold(flat)))

    bg = [[False] * w for _ in range(h)]
    q = deque()

    def seed(x, y):
        if 1 <= x < w - 1 and 1 <= y < h - 1 and not bg[y][x] and dist[y][x] <= d_t:
            bg[y][x] = True
            q.append((x, y))

    for x in range(1, w - 1):
        seed(x, 1)
        seed(x, h - 2)
    for y in range(1, h - 1):
        seed(1, y)
        seed(w - 2, y)
    while q:
        x, y = q.popleft()
        c = px[x, y]
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if 1 <= nx < w - 1 and 1 <= ny < h - 1 and not bg[ny][nx]:
                n = px[nx, ny]
                local = (abs(n[0] - c[0]) + abs(n[1] - c[1]) + abs(n[2] - c[2])) // 3
                if local <= LOC_TOL and dist[ny][nx] <= d_t:
                    bg[ny][nx] = True
                    q.append((nx, ny))

    img_l = Image.new("L", (w, h), 0)
    lp = img_l.load()
    for y in range(h):
        for x in range(w):
            if not bg[y][x]:
                lp[x, y] = 255
    for _ in range(2):                 # 闭运算：接住轮廓上的低对比度断口
        img_l = img_l.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))
    img_l = img_l.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3))
    lp = img_l.load()
    m = [[lp[x, y] > 127 for x in range(w)] for y in range(h)]
    for comp in components(m, w, h, False):        # 补内部洞
        if not any(x == 0 or y == 0 or x == w - 1 or y == h - 1 for x, y in comp):
            for x, y in comp:
                m[y][x] = True
    m, parts = drop_specks(m, w, h, 24)
    full = [[False] * img.size[0] for _ in range(img.size[1])]
    for y in range(h):
        for x in range(w):
            if m[y][x]:
                full[y + 1][x + 1] = True
    return full, img.size[0], img.size[1], parts, (base, d_t)


# ----------------------------------------------------------------- 渲染
def _sketch_gray(src_rgba, ow, oh):
    """原图 -> 素描灰度层（0=最黑的笔触，255=纸）。

    R29.1：用户要求「直拿原图套个转素描的滤镜」，不要之前那套人工构造的轮廓/辅助线。
    这里用**局部对比度**提取笔触（素描滤镜的常见做法）：

        base   = 高斯模糊(灰度, r)      —— 当作「这一带的平均明度」
        stroke = max(0, base - gray)    —— 只有比周围更暗的像素才算笔触
        sketch = 255 - clamp(stroke*K)  —— 反相成「白纸黑线」

    这么做的好处：
      · 黑装备不会被涂成一块黑（大片均匀区域 base≈gray，不产生笔触 → 保持白纸）；
      · 结构（织带、口袋、缝线、扣具）都来自原图本身，不是画上去的几何线；
      · 亮部自然留白，暗部自然加密，观感接近铅笔/炭笔写生。
    """
    w, h = src_rgba.size
    white = Image.new("RGBA", (w, h), (255, 255, 255, 255))
    g = Image.alpha_composite(white, src_rgba).convert("L").resize((ow, oh), Image.LANCZOS)
    r = max(2, int(round(min(ow, oh) * SKETCH_RADIUS)))
    base = g.filter(ImageFilter.GaussianBlur(r))
    stroke = ImageChops.subtract(base, g)
    # 限幅：深色装备局部对比度会爆到满值，不限幅就会涂成一块黑
    stroke = stroke.point(lambda v: min(SKETCH_CAP, int(v * SKETCH_GAIN)))
    # 归一化到 0..255：不同装备的对比强度差异很大，固定阈值会让深色件没线、浅色件全糊
    lo, hi = stroke.getextrema()
    if hi > lo:
        stroke = stroke.point(lambda v: int(255 * (v - lo) / float(hi - lo)))
    # 阈值 + 对比：低于 floor 视为纸面留白
    stroke = stroke.point(lambda v: max(0, min(255, int((v - SKETCH_FLOOR) * SKETCH_CONTRAST))))
    return stroke


def render(mask, w, h, cw, ch, src_img=None):
    """主体掩膜 + 原图 -> **透明底「原图素描」占位图**（灰色笔触，居中、等比、抗锯齿）。

    输出两通道各司其职：
      · **颜色** = 素描灰度（越暗的地方笔触越深）；
      · **Alpha** = (255 − 灰度) × 主体掩膜 —— 纸面透明，只有笔触可见。

    这样无论卡片是白底、选中蓝底还是深色底，都不会露出一块白色方块；
    笔触又保留了原图的真实结构（织带、口袋、缝线、扣具），不是几何辅助线。

    工程约束（踩过坑，别改回去）：
      · 掩膜要先**闭运算**：Alpha 阈值化留下的亚像素细缝会让笔触在缝上断掉；
      · Alpha 必须与掩膜相乘：素描滤镜会把「透明区当白纸」，不做裁剪就会画出轮廓外。
    """
    box = tight_bbox(mask, w, h)
    if box is None:
        return None
    bw, bh = box[2] - box[0], box[3] - box[1]
    binmask = Image.new("L", (bw, bh), 0)
    mp = binmask.load()
    for y in range(bh):
        row = mask[box[1] + y]
        for x in range(bw):
            if row[box[0] + x]:
                mp[x, y] = 255

    if src_img is None:
        return None

    # R29.2：**在源分辨率上提笔触**。源图只有 127–253 px，先放大再提线会把细节插值糊掉。
    gray = _sketch_gray(src_img, bw, bh)

    # 主体掩膜（源分辨率）：闭运算并掉 Alpha 阈值留下的亚像素细缝（否则笔触在缝上断掉）
    m = binmask.point(lambda v: 255 if v >= 128 else 0)
    k = 2 * max(1, int(round(CLOSE_PX * 4))) + 1
    m = m.filter(ImageFilter.MaxFilter(k)).filter(ImageFilter.MinFilter(k))

    # 笔触层：裁进主体掩膜内
    a_stroke = ImageChops.multiply(gray, m)

    # 形状轮廓层：取 Alpha 边缘（膨胀−腐蚀），骑在真实轮廓线上。
    # 薄物件（眼镜/匕首/耳机）几乎没有内部明暗，只靠笔触会「几乎空白」，这一层保证外形可辨。
    o_dil = m.filter(ImageFilter.MaxFilter(3))
    o_ero = m.filter(ImageFilter.MinFilter(3))
    cont = ImageChops.subtract(o_dil, o_ero)
    cont = cont.filter(ImageFilter.GaussianBlur(0.6)).point(
        lambda v: 255 if v >= 40 else int(v * 255 / 40))
    a_cont = ImageChops.multiply(cont, m).point(lambda v: int(v * OUTLINE_ALPHA))

    alpha = ImageChops.lighter(a_stroke, a_cont)
    if alpha.getbbox() is None:
        return None

    # 最后一步：等比放到目标画布（最多 2× 卡片 —— 再放大只是插值，没有新细节）
    W, H = cw * OUT_SCALE, ch * OUT_SCALE
    scale = min(W * (1 - 2 * MARGIN) / bw, H * (1 - 2 * MARGIN) / bh)
    ow, oh = max(1, int(round(bw * scale))), max(1, int(round(bh * scale)))
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    off = ((W - ow) // 2, (H - oh) // 2)
    ink = Image.new("L", (W, H), SKETCH_INK)
    a = Image.new("L", (W, H), 0)
    a.paste(alpha.resize((ow, oh), Image.LANCZOS), off)
    canvas.paste(Image.merge("RGBA", (ink, ink, ink, a)), (0, 0))
    return canvas


def ink_ratio(img):
    """主体占比：透明底版本按「非透明像素」统计（兼容旧 RGB 输入按暗像素）。"""
    if img.mode == "RGBA":
        a = img.split()[3]
        hist = a.histogram()
        return sum(hist[128:]) / float(img.size[0] * img.size[1])
    px = img.load()
    w, h = img.size
    n = 0
    for y in range(h):
        for x in range(w):
            if px[x, y][0] < 128:
                n += 1
    return n / float(w * h)


# ----------------------------------------------------------------- 主流程
def main():
    debug = "--debug" in sys.argv
    want_fetch = "--fetch" in sys.argv
    os.makedirs(OUT_DIR, exist_ok=True)
    if debug:
        os.makedirs(DEBUG_DIR, exist_ok=True)

    def slot_asset_id(entry):
        """元组第 5 列（若给出）= 取图用的物品 id（枪械用预设，见 SLOTS 注释）。"""
        return entry[5] if len(entry) > 5 else entry[1]

    if want_fetch:
        missing = [slot_asset_id(s) for s in SLOTS
                   if not os.path.exists(os.path.join(SRC_DIR, "%s.webp" % slot_asset_id(s)))]
        if missing:
            print("  需下载 %d 张透明底素材（走代理）" % len(missing))
            fetch_sources(missing)

    manifest = {
        "schema": 1,
        "round": "R28.0",
        "note": ("空槽占位图标：**原图转素描**（局部对比度提取笔触，透明底：纸面透明、只留笔触）。"
                 "结构全部来自上游透明底 base-image 本身；无透明底时回退到本地 64px 图标做前景分割。"
                 "输出画布为卡片尺寸的 %d 倍，HiDPI 屏不发虚。运行期零网络请求，原始素材只读不改。"
                 % OUT_SCALE),
        "generator": "tools/build_slot_placeholders.py",
        "render": {"mode": "RGBA", "paper": "transparent", "style": "pencil-sketch",
                   "radiusPct": SKETCH_RADIUS, "gain": SKETCH_GAIN, "cap": SKETCH_CAP,
                   "floor": SKETCH_FLOOR, "contrast": SKETCH_CONTRAST,
                   "ink": "#%02x%02x%02x" % (SKETCH_INK, SKETCH_INK, SKETCH_INK),
                   "outlineAlpha": OUTLINE_ALPHA,
                   "outScale": OUT_SCALE, "margin": MARGIN,
                   "nativeRes": "笔触在源分辨率提取，仅最后等比放大"},
        "items": [], "missing": []
    }
    thumbs = []
    for entry in SLOTS:
        key, item_id, name, cw, ch = entry[:5]
        asset_id = slot_asset_id(entry)
        alpha_src = os.path.join(SRC_DIR, "%s.webp" % asset_id)
        icon_src = os.path.join(ICON_DIR, "%s.webp" % asset_id)
        record = {"key": key, "file": "assets/ui/placeholders/%s.png" % key,
                  "itemId": item_id, "itemName": name, "canvas": [cw, ch],
                  "assetItemId": asset_id}
        if asset_id != item_id:
            # 枪械槽：剪影取自"完整装配形态"的预设图，而非本体裁切图
            record["assetItemName"] = {
                "5c0c1ce886f77401c119d014": "AK-74 5.45x39 突击步枪 默认（Preset）",
                "5a88acfb86f77457fd2c0d8f": "Glock 17 9x19 手枪 默认（Preset）",
            }.get(asset_id, asset_id)
            record["assetReason"] = ("枪械本体图不含枪托/握把（它们是独立 mod 配件），"
                                     "改用预设图以获得完整枪械轮廓")

        _src_rgba = None
        if os.path.exists(alpha_src):
            mask, w, h, parts, holes = mask_from_alpha(alpha_src)
            # 明暗信息用于「暗部排线」：源图（透明底渲染）本身带真实光影
            _src_rgba = Image.open(alpha_src).convert("RGBA")
            _src_rgba.load()
            record.update({
                "source": "alpha",
                "sourceFile": "assets/ui/placeholders/_src/%s.webp" % asset_id,
                "sourceOrigin": BASE_IMAGE_URL.format(id=asset_id),
                "sourceSize": [w, h], "parts": parts, "holesFilled": holes})
        elif os.path.exists(icon_src):
            img = Image.open(icon_src).convert("RGB")
            _src_rgba = img.convert("RGBA")          # 回退路径同样给排线提供明暗
            mask, w, h, parts, extra = split_foreground(img)
            record.update({
                "source": "icons-items-fallback",
                "sourceFile": "assets/icons-items/%s.webp" % item_id,
                "sourceOrigin": "https://assets.tarkov.dev/{id}-icon.webp",
                "sourceSize": [w, h], "parts": parts,
                "fallbackThresholds": {"bgBaseline": list(extra[0]), "color": extra[1]}})
        else:
            manifest["missing"].append({"key": key, "itemId": item_id, "name": name,
                                        "reason": "本地没有 base-image 也没有 icons-items 图标"})
            print("[MISS ] %-10s %s -> 无可用素材" % (key, name))
            continue

        out = render(mask, w, h, cw, ch, src_img=_src_rgba)
        if out is None:
            manifest["missing"].append({"key": key, "itemId": item_id, "name": name,
                                        "reason": "主体掩膜为空"})
            print("[MISS ] %-10s %s -> 掩膜为空" % (key, name))
            continue
        out.save(os.path.join(OUT_DIR, "%s.png" % key))
        record["inkRatio"] = round(ink_ratio(out), 4)
        record["fileSize"] = [out.size[0], out.size[1]]
        manifest["items"].append(record)
        print("[OK   ] %-10s %-4s 卡片%3dx%-3d 文件%4dx%-4d 源自 %-26s 部件%-3d 墨迹%.1f%%"
              % (key, record["source"][:4], cw, ch, out.size[0], out.size[1],
                 record["sourceFile"].split("/")[-1], record["parts"], 100 * record["inkRatio"]))
        if debug:
            thumbs.append((key, out))

    with open(os.path.join(OUT_DIR, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    if debug and thumbs:
        cell = 230
        cols = 3
        rows = (len(thumbs) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * cell, rows * (cell + 24)), (0x2b, 0x2b, 0x2b))
        dr = ImageDraw.Draw(sheet)
        for i, (k, im) in enumerate(thumbs):
            big = im.copy()
            big.thumbnail((cell - 20, cell - 20), Image.LANCZOS)
            cx, cy = (i % cols) * cell, (i // cols) * (cell + 24)
            sheet.paste(big, (cx + 10, cy + 24))
            dr.text((cx + 10, cy + 7), "%s  %dx%d" % (k, im.size[0], im.size[1]), fill=(235, 235, 235))
        sheet.save(os.path.join(DEBUG_DIR, "_contact_sheet.png"))
        print("联系表：%s" % os.path.join(DEBUG_DIR, "_contact_sheet.png"))

    print("生成 %d 张，缺失 %d 项 -> %s" % (len(manifest["items"]), len(manifest["missing"]), OUT_DIR))
    return 0 if not manifest["missing"] else 2


if __name__ == "__main__":
    sys.exit(main())
