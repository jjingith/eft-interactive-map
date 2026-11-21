# -*- coding: utf-8 -*-
"""R234：截图 OCR 价格识别（复刻 XiaoMeowToolbox 管线，规格见
docs/r32-xiaomeow-re/REPORT.md §3）。

管线：
    截图 → OcrPreprocess 小图放大（≤1.6×，目标 1100px）
    → det.onnx（960 边长 32 对齐、ImageNet mean/std、CHW）
    → DB 后处理（thresh 0.30 / boxThresh 0.60 / unclip 1.5 / minSize 3、minAreaRect）
    → SortBoxes（先 y 后 x，同行 |Δy|<10 冒泡）
    → CropRotate（透视校正；h≥1.5w 竖排转正）
    → rec.onnx（48×320 右零填充、(x/255-0.5)/0.5、batch 8）
    → CTC 贪心解码 + ppocr_keys_v1.txt
    → ItemMatcher（OcrTextNorm → 精确/去空格/模糊三级；BlockList；置信度 0.35；
       模糊阈值 len>4?0.60:0.72；次名差距 <0.06 丢弃；跨 token 0.05 窗口；
       数字守卫；小字串守卫；24px 栅格去重）
    → 价格（市场同源 prices_source）+ ResultAnnotator 标注 PNG。

依赖分层（关键设计）：
    · 纯 stdlib：OcrTextNorm / short_name_of / ItemMatcher / ctc_greedy_decode /
      SortBoxes / PriceFormat —— 无 numpy / cv2 / onnxruntime 也可导入、可单测。
    · 重依赖懒加载：OcrEngine 与 annotate_image 内部才 import
      numpy / cv2 / onnxruntime；缺失时引擎构造抛 OcrUnavailable，
      /api/ocr/recognize 返回 503，其余功能不受影响。

与参考实现的已知偏差（均为数据可得性所限，如实标注）：
    · AmmoBlockedKeys（弹药同名不同口径按价格比拉黑）未复刻：项目 items.json
      无 AmmoKind/Category 字段；命中多个同名条目时由调用方按价格择优。
    · RecognizeChunked 分块识别未复刻：单图路径（截图 ROI）足够，超长图由
      det 的 960 缩放兜底。
"""

from __future__ import annotations

import difflib
import math
import os
import re
import sys
import time

# --------------------------------------------------------------------------
# 常量（与 XiaoMeowToolbox.Core 逐一对应）

DET_MAX_SIDE = 960          # det 输入最长边，之后 32 对齐
DET_MEAN = (0.485, 0.456, 0.406)   # ImageNet mean（BGR 序取反后的 RGB 通道序）
DET_STD = (0.229, 0.224, 0.225)    # ImageNet std
DB_THRESH = 0.30            # 二值化阈值
DB_BOX_THRESH = 0.60        # 框均分阈值
DB_MAX_CANDS = 1000         # 候选轮廓上限
DB_UNCLIP_RATIO = 1.5       # 外扩比例
DB_MIN_SIZE = 3             # 最小边长
REC_H = 48                  # rec 输入高
REC_W = 320                 # rec 输入宽
REC_BATCH = 8               # rec 批大小
MATCH_MIN_SCORE = 0.35      # OCR 置信度下限
FUZZY_THR_SHORT = 0.72      # 模糊阈值（len<=4）
FUZZY_THR_LONG = 0.60       # 模糊阈值（len>4）
DEDUP_GRID = 24             # 命中去重栅格（像素）

# ---- R236 分块识别（复刻 REPORT §3.4 RecognizeChunked / §3.2 TilePlan） ----
# 整图超过 TILED_TRIGGER 时切成块逐块识别：det 的 960 边长会把 1080p 截图压到
# 一半，游戏 14px 小字变 ~7px，检测器基本失明（实测「只能识别出几个物体」的根因）。
# XiaoMeow 的做法正是分块（tile=256、overlap=0，ROI 用法下够用）。
# 块几何保证：文本宽 L 完整落入某块 ⇔ L ≤ TILE_SIZE − step（窗口每 step 平移一次，
# 需 W−L ≥ S）。整页库存里物品名最宽约 320px（16px 字号 × 20 字），所以取
# 块 640 / 步进 320（overlap 0.5）：保证 L ≤ 320，1080p 约 24 块 ≈ 7s，1440p 约 40 块。
TILE_SIZE = 640
TILE_OVERLAP = 0.5
TILED_TRIGGER = 1200        # 最长边超过此值走分块（单次 det 缩放比 < 0.8 开始伤小字）
TILE_MAX_COUNT = 400        # 块数保险丝（超过则退回 overlap=0 的 tile=640 网格）

BLOCKLIST = frozenset((
    "cpu", "bear", "items", "pve", "pvp", "stash", "search", "filter",
    "scav", "junk",
))

# R242：库存栏位标题（区块名）。它们印在物品格**上方**，框选整页时 OCR 一定会
# 扫到，模糊层会把它们错配成物品（实测 '头部装备'/'面部装备'/'眼部装备' → 木质
# 装备箱、'背包' → VKBO军用背包，且背包标题出现两处 → 标签画在标题上 = 用户看到
# 的「位置不对」）。小喵没这个问题是因为它只扫鼠标光标周围一小块（
# CursorCenteredRegion），标题根本进不了画面；我们扫整个框选区，必须整词拦截。
# 只拦**整行/独立 token**，不影响含这些词的真物品全名（'VKBO军用背包' ≠ '背包'）。
SECTION_HEADERS = frozenset((
    "耳机", "头部装备", "面部装备", "身体护甲", "眼部装备", "眼镜",
    "背带", "臂章", "臂带", "主武器", "副武器", "近战武器",
    "战术胸挂", "胸挂", "口袋", "特殊装备", "背包", "刀鞘",
    "服装", "弹药", "弹匣", "医疗", "杂物", "钥匙",
))

# R242：用户点名不识别的物品（价格无意义/干扰视觉）：臂带、臂章、狗牌及其容器。
# 在物品解析层按名字片段排除（整词拦 '臂带'/'臂章' 已进 SECTION_HEADERS）。
ITEM_NAME_EXCLUDES = ("臂带", "臂章", "狗牌", "dogtag", "armband")


def item_name_excluded(name: str) -> bool:
    low = str(name or "").lower()
    return any(f in low for f in ITEM_NAME_EXCLUDES)

_NORM_RE = re.compile(r"[^a-zа-я0-9\u4e00-\u9fff.,\-]+")
_SHORT_HEAD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*(?:[ ][A-Za-z0-9][A-Za-z0-9._-]*)*")
_DIGIT_RE = re.compile(r"[0-9.,]")
_DIGIT_RUN_RE = re.compile(r"\d+")
_PURE_LATIN_RE = re.compile(r"^[a-z]+$")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
# 价格标签形态：'53,548' / '1.234.567' / '53548'（归一化后逗号已变点）。
# 纯数字串不参与匹配——XiaoMeow 用 AmmoBlockedKeys（价格比>3 拉黑同名弹药）挡这类，
# 本项目无该数据，改用形态守卫（千分位分组数字是价格标签的强特征）。
_PURE_NUMBER_RE = re.compile(r"^\d+(?:\.\d{3})*\.?\d*$")
# R242：弹药计数形态 '21/21' '7/50' '0/30'——库存里到处都是（物品格右下角），
# 整串模糊会把它们擦线配到瞄具/弹匣类物品（实测 '0/30' → M700 瞄具基座环）。
_COUNT_RE = re.compile(r"^\d+\s*/\s*\d+$")

# R260：OCR 常把 '/' 读成 '1'/'l'/'|'、'0' 读成 'O'、'5' 读成 'S'、'8' 读成 'B'。
# 弹匣/弹药包/药品下方的计数（30/30、3/3、45.5/60）被读花后仍一眼是计数，绝不
# 能当物品名（用户实反馈：这些 xx/xx 特别容易被误识别成物资）。
_COUNT_FIX = str.maketrans({
    "O": "0", "o": "0", "D": "0",
    "l": "1", "I": "1", "|": "1", "!": "1",
    "S": "5", "s": "5", "B": "8", "Z": "2",
    "/": "-", "\\": "-", "／": "-", "｜": "-", "丨": "-",
})
_NUM_ATOM = r"\d+(?:[.,]\d+)*"
_COUNT_SHAPE_RE = re.compile(r"^%s-%s$" % (_NUM_ATOM, _NUM_ATOM))
_NUMBER_SHAPE_RE = re.compile(r"^%s$" % _NUM_ATOM)


def looks_like_count_or_number(text: str) -> bool:
    """像「计数 / 价格」而不是物品名：3/3、30/30、45.5/60、53548、53.548。

    物品名一定含字母或汉字；这里要求原串**至少一个数字**，且把常见 OCR 误读
    （O→0、l→1、S→5、B→8，斜杠变体统一成 '-'）后整串只剩数字/分隔——满足即
    判为计数/价格（不参与物品名匹配）。纯字母名（无数字）一律放行。"""
    s = str(text or "").strip()
    if not s or not re.search(r"\d", s):
        return False
    fixed = s.translate(_COUNT_FIX).replace(" ", "")
    return bool(_COUNT_SHAPE_RE.match(fixed) or _NUMBER_SHAPE_RE.match(fixed))
# 整串模糊阈值（本项目补充层）：维持规格档位 0.60。实测把它提到 0.70 会连带杀掉
# 正确路径（'宿舍118房间钥起'→宿舍118钥匙 0.667、'上洛关9x18pm手柜'→马卡洛夫 0.696），
# 而 EXPIE 误配 0.67 与它们落在同一分数带——ratio 无法区分好乱串与坏乱串；
# 碎片守卫（无 CJK 的 <3 字符 token / 整串）才是主要防线，残余误报如实标注。
FUZZY_WHOLE_THR = 0.60

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

OCR_FILES = ("det.onnx", "rec.onnx", "ppocr_keys_v1.txt")


def resolve_assets_dir() -> str:
    """模型目录探测：源码运行与 PyInstaller 冻结态都要能找到 assets/ocr。

    R279：冻结态里本文件被放到 `_internal\\ocr.py`，`PROJECT_ROOT` 于是变成
    产物根目录，`assets/ocr` 实际在 `_internal\\assets\\ocr`——原来那条路径
    指不到模型，`/api/ocr/recognize` 一律 503「模型文件缺失」，用户看到的就是
    「截图能框选，松手后什么都没发生」。这里按「先冻结、后源码」的顺序探测，
    第一个三件套齐全的目录胜出；都不齐全时返回源码路径，让报错信息指向仓库。
    """
    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(os.path.join(meipass, "assets", "ocr"))
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    candidates.extend((
        os.path.join(exe_dir, "_internal", "assets", "ocr"),
        os.path.join(exe_dir, "assets", "ocr"),
    ))
    candidates.append(os.path.join(PROJECT_ROOT, "assets", "ocr"))
    for path in candidates:
        if all(os.path.isfile(os.path.join(path, name)) for name in OCR_FILES):
            return path
    return candidates[-1]


OCR_ASSETS_DIR = resolve_assets_dir()


class OcrUnavailable(RuntimeError):
    """onnxruntime / opencv / 模型文件缺失。message 面向用户，附 hint。"""


# --------------------------------------------------------------------------
# 文本归一化（REPORT §3.5 OcrTextNorm）


def ocr_text_norm(s: str) -> str:
    """OCR 文本归一化：小写；只保留拉丁/西里尔/数字/汉字/点逗横线，其余折叠为空格。"""
    s = str(s or "").lower()
    s = _NORM_RE.sub(" ", s)
    s = s.strip()
    s = s.replace(",", ".")
    return s


def short_name_of(name: str) -> str:
    """市场视图 js/market.js shortNameOf 的 Python 版（括号前取拉丁/数字短名）。"""
    head = str(name or "").split("（")[0]
    m = _SHORT_HEAD_RE.search(head)
    return m.group(0) if m else ""


def price_fmt(v, wan: bool = True) -> str:
    """REPORT §3.6 PriceFormat.Fmt。v<=0 → '—'；wan=False 千分位；否则万缩写。"""
    try:
        v = int(v)
    except (TypeError, ValueError):
        return "—"
    if v <= 0:
        return "—"
    if not wan:
        return f"{v:,}"
    if v < 500:
        return "<0.1万"
    return f"{v / 10000.0:.1f}万"


# --------------------------------------------------------------------------
# ItemMatcher（REPORT §3.5，difflib 与 C# 的 SequenceMatcherRatio 逐位复刻）


class ItemMatcher:
    """OCR 文本 → 物品名。索引来自 items.json 的 n（真名）与 shortNameOf(n)。

    用法：
        m = ItemMatcher(names)            # names: 可迭代字符串
        hit = m.match_line("菲尼亚斯", 0.9)  # → (key, path) 或 None
    """

    def __init__(self, names):
        self._dlist: dict[str, list[str]] = {}        # 精确层：规范化（含空格）的键
        self._dlist_ns: dict[str, list[str]] = {}     # 去空格层：同名的无空格变体键
        self._by_fl: dict[str, dict[int, set[str]]] = {}
        self._by_len: dict[int, set[str]] = {}
        seen = set()
        for name in names:
            name = str(name or "").strip()
            if not name:
                continue
            for cand in (short_name_of(name), name):
                key = ocr_text_norm(cand)
                if not key or key in seen:
                    continue
                seen.add(key)
                self._dlist.setdefault(key, []).append(name)
                self._by_fl.setdefault(key[0], {}).setdefault(len(key), set()).add(key)
                self._by_len.setdefault(len(key), set()).add(key)
                no_space = key.replace(" ", "")
                if no_space and no_space != key:
                    self._dlist_ns.setdefault(no_space, []).append(name)

    def has_exact(self, norm: str) -> bool:
        return norm in self._dlist

    def _candidates(self, tok: str) -> set:
        """首字符 + 长度±2 的倒排候选，另补「以 token 开头且长度 ≤ len+1」的短名。

        OCR 常吞空格：候选窗口对 len(tok) 与 len(tok 去空格) **各开一档**，
        让无空格变体键也能进候选（否则全名键带空格、长度超出窗口整组丢失，
        反而让 'MP-153' 这类近似键错配——R236 实测教训）。
        """
        cands: set = set()
        fl = self._by_fl.get(tok[0])
        if not fl:
            return cands
        tok_ns = tok.replace(" ", "")
        for delta in (-2, -1, 0, 1, 2):
            for length in {len(tok) + delta, len(tok_ns) + delta}:
                lst = fl.get(length)
                if lst:
                    cands.update(lst)
        if len(tok_ns) >= 4:
            for length, lst in fl.items():
                if length <= len(tok) + 1:
                    for key in lst:
                        if key.startswith(tok) or key.replace(" ", "").startswith(tok_ns):
                            cands.add(key)
        return cands

    @staticmethod
    def _ratio_best(tok: str, key: str) -> float:
        """token 与键的两个形态（原样 / 去空格）取较高 ratio。"""
        sm = difflib.SequenceMatcher(None, tok, key)
        r1 = sm.ratio()
        key_ns = key.replace(" ", "")
        if key_ns != key:
            sm2 = difflib.SequenceMatcher(None, tok, key_ns)
            if sm2.real_quick_ratio() > r1:
                r2 = sm2.ratio()
                if r2 > r1:
                    r1 = r2
        return r1

    def _fuzzy(self, norm: str):
        """逐 token 模糊匹配，返回 (key, ratio) 或 None。判定顺序逐条复刻。

        阈值按 token 长度取档：去空格后 ≤6 字符用 0.72（短 token 在 0.60 下
        太松，实测 HUD 文字 'Esape' 会擦线配上 'eagle'），>6 用 0.60。
        """
        best = None  # (key, ratio)
        for tok in norm.split(" "):
            if (not tok or tok in BLOCKLIST or tok in SECTION_HEADERS
                    or _PURE_NUMBER_RE.match(tok) or _COUNT_RE.match(tok)
                    or looks_like_count_or_number(tok)):
                continue
            # 无 CJK 的 <3 字符 token 信息量太低（HUD 碎片 'un'/'EC'/'s1' 会配上海报、
            # 钥匙、兴奋剂），跳过；中文碎片不过滤——'洛芬' 整串命中布洛芬是正确路径。
            if len(tok) < 3 and not _CJK_RE.search(tok):
                continue
            cands = self._candidates(tok)
            if not cands:
                continue
            thr = FUZZY_THR_SHORT if len(tok.replace(" ", "")) <= 6 else FUZZY_THR_LONG
            tok_runs = _DIGIT_RUN_RE.findall(tok)
            ranked = []
            for c in cands:
                r = self._ratio_best(tok, c)
                # 数字段守卫：token 含数字段时，候选键（或其去空格形态）至少含一段
                # —— 'mk17' 不得配 'mk 47双侧拉机柄'（R237 实测错配）；O/0 误读时
                # 只要数字段有任一交集即放行（'GL0CK17' 仍可配 Glock 17）。
                if tok_runs:
                    c_ns = c.replace(" ", "")
                    if not any(run in c or run in c_ns for run in tok_runs):
                        continue
                ranked.append((r, c))
            ranked.sort(key=lambda x: (-x[0], x[1]))
            if not ranked or ranked[0][0] < thr:
                continue
            if len(ranked) >= 2 and ranked[1][0] > ranked[0][0] - 0.06:
                continue  # 歧义就丢
            if best is not None:
                if ranked[0][0] > best[1] + 0.05:
                    pass  # 更好，替换
                elif abs(ranked[0][0] - best[1]) > 0.05:
                    continue  # 更差就丢
                elif len(ranked[0][1]) <= len(best[0]):
                    continue  # 打平取更长的
            best = (ranked[0][1], ranked[0][0])
        return best

    def _fuzzy_whole(self, norm: str):
        """整串模糊兜底（本项目补充层，非 XiaoMeow 规格）。

        背景：XiaoMeow 索引的是紧凑短名（'AKM'），本项目 items.json 的 sn 是
        占位符，只能索引全名；而 OCR 会吞空格/小数点，还可能写错首字（实测
        '工厂紧急出口钥匙' → '十广紧急出口钥起'），按首字符取候选会整组丢失。
        做法：探针与候选键**两侧都去空格**后做 difflib（OCR 吞空格是常态，
        同名带/不带空格的两个形态不得互相判成歧义）——候选取「长度 ±4 的全部
        键」，预过滤两道闸：
          ① 数字守卫：探针含数字段时，候选键必须包含全部数字段（数字极少写错）；
          ② real_quick_ratio < 阈值的直接跳过（difflib 便宜剪枝）。
        阈值与歧义判定沿用规格（0.60/0.72、次名差 0.06 丢弃）。
        """
        probe = norm.replace(" ", "")
        if not probe or probe in BLOCKLIST:
            return None
        # 纯数字探针（'0 30' 归一化去空格成 '030' 这种计数残骸）不配物品——
        # 物品键都含字母/汉字（'9x19'、'AKM'），纯数字串只会擦线误配（R242 实测）。
        if probe.isdigit() or looks_like_count_or_number(norm):
            return None
        # 无 CJK 的 <3 字符碎片信息量太低（HUD 碎片 'un'/'EC'/'S1' 会配上海报、
        # 钥匙、兴奋剂），整串层与 token 层同规则；中文碎片不过滤——'洛芬'
        # 整串命中布洛芬是正确路径（R237 实测）。
        if len(probe) < 3 and not _CJK_RE.search(probe):
            return None
        digit_runs = _DIGIT_RUN_RE.findall(probe)
        lengths = [n for n in self._by_len if abs(n - len(probe)) <= 4]
        cand_keys: set = set()
        for n in lengths:
            cand_keys.update(self._by_len[n])
        thr = FUZZY_WHOLE_THR
        ranked = []
        seen_cc: set = set()
        for c in cand_keys:
            cc = c.replace(" ", "")
            if cc in seen_cc:
                continue  # 带空格/不带空格同形 → 同一物品，只比一次
            seen_cc.add(cc)
            if digit_runs and not all(run in cc for run in digit_runs):
                continue
            sm = difflib.SequenceMatcher(None, probe, cc)
            if sm.real_quick_ratio() < thr:
                continue
            ranked.append((sm.ratio(), c))
        if not ranked:
            return None
        ranked.sort(key=lambda x: (-x[0], x[1]))
        if ranked[0][0] < thr:
            return None
        if len(ranked) >= 2 and ranked[1][0] > ranked[0][0] - 0.06:
            return None  # 歧义就丢
        return (ranked[0][1], ranked[0][0])  # (key, ratio)，与 _fuzzy 一致

    def resolve_key(self, text: str):
        """文本 → (key, path)。path ∈ 精确 / 去空格 / 模糊(ratio) / 整串模糊(ratio)。"""
        raw = str(text or "").strip()
        norm = ocr_text_norm(text)
        if not norm:
            return None, norm
        # 计数形态要在**归一化前**查：'0/30' 的斜杠不在 NORM_RE 白名单里，
        # 归一化后变 '0 30' → 去空格 '030' 会绕过形态守卫（R242 实测漏网）。
        if _COUNT_RE.match(raw) or looks_like_count_or_number(raw):
            return None, norm
        if (_PURE_NUMBER_RE.match(norm) or _COUNT_RE.match(norm)
                or looks_like_count_or_number(norm)):
            return None, norm  # ⑨ 纯数字串（价格标签）/ 弹药计数（21/21）不参与匹配
        if norm in SECTION_HEADERS or norm.replace(" ", "") in SECTION_HEADERS:
            return None, norm  # R242：栏位标题（耳机/头部装备/背包…）不参与匹配
        if self.has_exact(norm):
            return norm, "精确"
        no_space = norm.replace(" ", "")
        if no_space and (no_space in self._dlist_ns or self.has_exact(no_space)):
            return no_space, "去空格"
        best = self._fuzzy(norm)
        if best is not None:
            return best[0], "模糊(%.2f)" % best[1]
        best = self._fuzzy_whole(norm)
        if best is not None:
            return best[0], "整串模糊(%.2f)" % best[1]
        return None, norm

    def names_for(self, key: str):
        return self._dlist.get(key) or self._dlist_ns.get(key) or []

    def match_line(self, text: str, score: float, box=None):
        """单行 OCR → match dict 或 None。box 为 [[x,y]×4]（原图坐标）。"""
        if score < MATCH_MIN_SCORE:
            return None
        key, path = self.resolve_key(text)
        if key is None:
            return None
        norm = ocr_text_norm(text)
        # ⑥ 防把纯数字（价格/数量）当物品名
        if _DIGIT_RE.search(key) and not _DIGIT_RE.search(norm):
            return None
        if box is not None:
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            x, y = int(min(xs)), int(min(ys))
            w = max(1, int(max(xs)) - x)
            h = max(1, int(max(ys)) - y)
            # ⑦ 小字串扰：低置信 + 小面积 + 纯拉丁
            if (score < 0.85 and w * h < 800 and len(norm) > 5
                    and not _DIGIT_RE.search(norm) and _PURE_LATIN_RE.match(norm)):
                return None
        else:
            x = y = w = h = 0
        return {
            "text": text, "norm": norm, "key": key, "path": path,
            "score": round(float(score), 4),
            "x": x, "y": y, "w": w, "h": h, "box": box,
        }

    def match_lines(self, lines):
        """lines: [{text, score, box}] → matches（24px 栅格去重）。"""
        out, seen = [], set()
        for ln in lines:
            m = self.match_line(ln.get("text", ""), ln.get("score", 0.0), ln.get("box"))
            if m is None:
                continue
            dedup = (m["key"], m["x"] // DEDUP_GRID, m["y"] // DEDUP_GRID)
            if dedup in seen:
                continue
            seen.add(dedup)
            out.append(m)
        return out


# --------------------------------------------------------------------------
# CTC 贪心解码（REPORT §3.4 CtcDecode.Decode，纯 stdlib，seq 只要求可下标）


def load_dict(dict_path: str, class_count: int | None = None):
    """CtcDecode.LoadDict：['blank'] + 字典行；模型类数多 1 时补空格。"""
    with open(dict_path, "r", encoding="utf-8") as f:
        lines = [ln.rstrip("\r") for ln in f.read().split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    chars = ["blank"] + lines
    if class_count is not None and class_count > len(chars):
        chars.append(" ")  # addSpace
    return chars


def ctc_collapse(indices, probs, chars):
    """对每步 argmax 结果做 prev 折叠 + 字符映射 + 均分。

    indices/probs 为长度 T 的序列（引擎侧来自 numpy argmax，测试侧可手写）。
    返回 (text, score)。
    """
    text_parts = []
    score_sum = 0.0
    count = 0
    prev = 0  # 上一步的 best_idx；0 = blank，首步遇 blank 不产生字符
    for idx, prob in zip(indices, probs):
        idx = int(idx)
        if idx != prev and idx != 0:
            if idx < len(chars):
                text_parts.append(chars[idx])
            score_sum += float(prob)
            count += 1
        prev = idx
    return "".join(text_parts), (score_sum / count if count > 0 else 0.0)


def ctc_greedy_decode(seq, T: int, C: int, chars):
    """纯 stdlib 版贪心解码（seq 为长度 T*C 的平铺序列）。小 T 场景 / 单测用。"""
    indices = []
    probs = []
    base = 0
    for _t in range(T):
        best = seq[base]
        best_idx = 0
        for c in range(1, C):
            v = seq[base + c]
            if v > best:
                best = v
                best_idx = c
        indices.append(best_idx)
        probs.append(best)
        base += C
    return ctc_collapse(indices, probs, chars)


# --------------------------------------------------------------------------
# 检测框排序（REPORT §3.4 SortBoxes：先 y 后 x，同行 |Δy|<10 冒泡一趟）


def sort_boxes(boxes):
    boxes = sorted(boxes, key=lambda b: (b["points"][0][1], b["points"][0][0]))
    for i in range(len(boxes) - 1):
        a, b = boxes[i], boxes[i + 1]
        if abs(a["points"][0][1] - b["points"][0][1]) < 10 and \
                b["points"][0][0] < a["points"][0][0]:
            boxes[i], boxes[i + 1] = b, a
    return boxes


# --------------------------------------------------------------------------
# 引擎（重依赖懒加载）


class OcrEngine:
    """det + rec ONNX 推理。构造即装载模型（约 1 s），实例可复用。"""

    def __init__(self, assets_dir: str = OCR_ASSETS_DIR):
        det_path = os.path.join(assets_dir, "det.onnx")
        rec_path = os.path.join(assets_dir, "rec.onnx")
        dict_path = os.path.join(assets_dir, "ppocr_keys_v1.txt")
        missing = [p for p in (det_path, rec_path, dict_path) if not os.path.isfile(p)]
        if missing:
            raise OcrUnavailable("模型文件缺失：%s" % ", ".join(os.path.basename(p) for p in missing))
        try:
            import numpy as np
            import cv2
            import onnxruntime as ort
        except ImportError as exc:
            raise OcrUnavailable("缺少 OCR 依赖（%s）—— pip install onnxruntime opencv-python-headless" % exc.name) from exc
        self._np, self._cv2, self._ort = np, cv2, ort

        cores = os.cpu_count() or 4
        threads = max(1, min(4, cores // 2))
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = threads
        opts.inter_op_num_threads = 1
        opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        opts.enable_cpu_mem_arena = False
        self._det = ort.InferenceSession(det_path, opts)
        self._rec = ort.InferenceSession(rec_path, opts)
        self._threads = threads

        # rec 的类数决定是否补空格（符号维度拿不到时留给首次推理后修正）
        rec_classes = self._rec.get_outputs()[0].shape[-1]
        self._dict_path = dict_path
        self._chars = load_dict(dict_path, rec_classes if isinstance(rec_classes, int) else None)

    # ---- 预处理（REPORT §3.2 逐条复刻） ----

    def det_preprocess(self, img, max_side: int = DET_MAX_SIDE):
        """img: BGR ndarray → (float32 CHW [3,h,w], h, w)。"""
        np, cv2 = self._np, self._cv2
        rows, cols = img.shape[0], img.shape[1]
        max_len = max(rows, cols)
        scale = max_side / max_len if max_len > max_side else 1.0
        w = max(32, int(round(int(cols * scale) / 32.0)) * 32)
        h = max(32, int(round(int(rows * scale) / 32.0)) * 32)
        resized = cv2.resize(img, (w, h), interpolation=cv2.INTER_LINEAR)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        mean = np.array(DET_MEAN, dtype=np.float32)
        std = np.array(DET_STD, dtype=np.float32)
        rgb = (rgb - mean) / std
        chw = rgb.transpose(2, 0, 1).copy()  # CHW
        return np.ascontiguousarray(chw), h, w

    def ocr_preprocess(self, img):
        """小图放大（≤1.6×，目标 1100px），返回 (img, scale)。"""
        cv2 = self._cv2
        max_len = max(img.shape[0], img.shape[1])
        scale = 1.0
        if max_len < 1100:
            scale = min(1.6, 1100.0 / max_len)
            if scale > 1.05:
                img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
                return img, scale
        return img, scale

    @staticmethod
    def _order_box_tl(pts):
        """minAreaRect 四点 → (左上, 右上, 右下, 左下)（REPORT §3.3 GetMiniBoxes）。"""
        pts = sorted(pts, key=lambda p: p[0])
        if pts[1][1] > pts[0][1]:
            i1, i4 = 0, 1
        else:
            i1, i4 = 1, 0
        if pts[3][1] > pts[2][1]:
            i2, i3 = 2, 3
        else:
            i2, i3 = 3, 2
        return [pts[i1], pts[i2], pts[i3], pts[i4]]

    def _get_mini_boxes(self, contour):
        cv2 = self._cv2
        rect = cv2.minAreaRect(contour)
        pts = cv2.boxPoints(rect)
        box = self._order_box_tl(pts)
        return box, min(rect[1][0], rect[1][1])

    def _box_score(self, binary, box):
        """BoxScoreFast：min-area 外接矩形内二值均值。"""
        np, cv2 = self._np, self._cv2
        box = np.array(box, dtype=np.float32)
        h, w = binary.shape[:2]
        xs = np.clip(np.round(box[:, 0]).astype(int), 0, w - 1)
        ys = np.clip(np.round(box[:, 1]).astype(int), 0, h - 1)
        x_min, x_max = max(0, int(xs.min())), min(w - 1, int(xs.max()))
        y_min, y_max = max(0, int(ys.min())), min(h - 1, int(ys.max()))
        mask = np.zeros((y_max - y_min + 1, x_max - x_min + 1), dtype=np.uint8)
        pts = (box - [x_min, y_min]).astype(np.int32).reshape(-1, 1, 2)
        cv2.fillPoly(mask, [pts], 1)
        region = binary[y_min:y_max + 1, x_min:x_max + 1]
        if region.size == 0:
            return 0.0
        return float((region * mask).sum() / max(1, mask.sum()))

    def _unclip(self, box, ratio: float):
        """pyclipper 式外扩：distance = area * ratio / perimeter，边法线偏移（凸四边形精确）。

        法线方向由有向面积决定（shoelace > 0 时 (dy,-dx) 指向凸包外侧）；
        新顶点 = 相邻两条偏移边所在直线的交点（标准点向式参数求解）。
        """
        n = len(box)
        signed2 = 0.0
        per = 0.0
        for i in range(n):
            x1, y1 = box[i]
            x2, y2 = box[(i + 1) % n]
            signed2 += x1 * y2 - x2 * y1
            per += math.hypot(x2 - x1, y2 - y1)
        area = abs(signed2) / 2.0
        if per <= 0:
            return None
        d = area * ratio / per
        sign = 1.0 if signed2 > 0 else -1.0

        def edge_offset(a, b):
            """边 a→b 外移 d：返回线上一点与方向向量。"""
            dx, dy = b[0] - a[0], b[1] - a[1]
            length = math.hypot(dx, dy) or 1.0
            nx, ny = sign * dy / length, -sign * dx / length
            return (a[0] + nx * d, a[1] + ny * d), (dx, dy)

        lines = [edge_offset(box[i], box[(i + 1) % n]) for i in range(n)]
        out = []
        for i in range(n):
            (p1, u1) = lines[(i - 1) % n]
            (p2, u2) = lines[i]
            denom = u1[0] * u2[1] - u1[1] * u2[0]
            if abs(denom) < 1e-9:
                out.append([p1[0], p1[1]])
                continue
            t = ((p2[0] - p1[0]) * u2[1] - (p2[1] - p1[1]) * u2[0]) / denom
            out.append([p1[0] + t * u1[0], p1[1] + t * u1[1]])
        return out

    def db_postprocess(self, pred, pred_h: int, pred_w: int, dest_h: int, dest_w: int):
        """REPORT §3.3 Process。pred: [1,1,predH,predW] 概率图。"""
        np, cv2 = self._np, self._cv2
        prob = np.asarray(pred).reshape(pred_h, pred_w)
        binary = (prob >= DB_THRESH).astype(np.uint8)
        contours, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        if len(contours) > DB_MAX_CANDS:
            contours = sorted(contours, key=cv2.contourArea, reverse=True)[:DB_MAX_CANDS]
        results = []
        for contour in contours:
            box, sside = self._get_mini_boxes(contour)
            if sside < DB_MIN_SIZE:
                continue
            score = self._box_score(binary, box)
            if score < DB_BOX_THRESH:
                continue
            pts = self._unclip(box, DB_UNCLIP_RATIO)
            if pts is None or len(pts) != 4:
                continue
            box2, sside2 = self._get_mini_boxes(np.array(pts, dtype=np.float32))
            if sside2 < DB_MIN_SIZE + 2:
                continue
            points = []
            for p in box2:
                x = int(min(max(round(p[0] / pred_w * dest_w), 0), dest_w))
                y = int(min(max(round(p[1] / pred_h * dest_h), 0), dest_h))
                points.append([x, y])
            results.append({"points": points, "score": score})
        return results

    def crop_rotate(self, img, box):
        """REPORT §3.2 CropRotate：透视校正 + 竖排转正。"""
        cv2, np = self._cv2, self._np

        def dist(a, b):
            return math.hypot(a[0] - b[0], a[1] - b[1])

        p0, p1, p2, p3 = box
        w = max(1, int(max(dist(p0, p1), dist(p2, p3))))
        h = max(1, int(max(dist(p0, p3), dist(p1, p2))))
        dst = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32)
        src = np.array(box, dtype=np.float32)
        m = cv2.getPerspectiveTransform(src, dst)
        out = cv2.warpPerspective(img, m, (w, h), flags=cv2.INTER_CUBIC,
                                  borderMode=cv2.BORDER_REPLICATE)
        if h / float(w) >= 1.5:
            out = cv2.rotate(out, cv2.ROTATE_90_CLOCKWISE)
        return out

    def rec_preprocess(self, crop):
        """REPORT §3.2 RecPreprocess：48×320 右零填充，(px/255-0.5)/0.5，CHW。

        注意：rec **不做** BGR→RGB 转换（PaddleOCR 惯例：det 用 RGB、rec 保持
        cv2 原始 BGR；通道错位会造成系统性字形误读，实测'马卡洛夫'→'瓦上没关'）。
        """
        np, cv2 = self._np, self._cv2
        rows, cols = crop.shape[0], crop.shape[1]
        aspect = cols / float(rows)
        w = int(math.ceil(REC_H * aspect))
        if w > REC_W:
            w = REC_W
        resized = cv2.resize(crop, (w, REC_H), interpolation=cv2.INTER_LINEAR)
        px = resized.astype(np.float32) / 255.0
        px = (px - 0.5) / 0.5
        out = np.zeros((3, REC_H, REC_W), dtype=np.float32)
        out[:, :, :w] = px.transpose(2, 0, 1)
        return out

    # ---- 主流程 ----

    def _recognize_lines(self, img_scaled, scale: float, off_x: int, off_y: int,
                         min_score: float):
        """对一张（已 OcrPreprocess 的）图跑 det→DB→SortBoxes→rec，
        坐标换算回全图（pt/scale + 块偏移，REPORT §3.4 RecognizeChunked 映射公式）。"""
        np = self._np
        data, dh, dw = self.det_preprocess(img_scaled)
        pred = self._det.run(None, {"x": data[None, ...]})[0]
        boxes = self.db_postprocess(pred, dh, dw, img_scaled.shape[0], img_scaled.shape[1])
        boxes = sort_boxes(boxes)

        lines = []
        for start in range(0, len(boxes), REC_BATCH):
            chunk = boxes[start:start + REC_BATCH]
            buf = np.zeros((len(chunk), 3, REC_H, REC_W), dtype=np.float32)
            for i, b in enumerate(chunk):
                crop = self.crop_rotate(img_scaled, b["points"])
                buf[i] = self.rec_preprocess(crop)
            outs = self._rec.run(None, {"x": buf})[0]
            bt, T, C = outs.shape[0], outs.shape[1], outs.shape[2]
            if C != len(self._chars):  # 类数与字典不齐 → 按实际类数重建（含空格补位）
                self._chars = load_dict(self._dict_path, C)
            best_idx = outs.argmax(axis=2)
            best_prob = outs.max(axis=2)
            for i in range(bt):
                text, score = ctc_collapse(best_idx[i].tolist(), best_prob[i].tolist(), self._chars)
                if score >= min_score:
                    pts = [[int(p[0] / scale) + off_x, int(p[1] / scale) + off_y]
                           for p in chunk[i]["points"]]
                    lines.append({"text": text, "score": round(float(score), 4), "points": pts})
        return lines

    def _recognize_single(self, img, min_score: float):
        """小图直识（≤TILED_TRIGGER）：整图 OcrPreprocess ≤1.6× 后单次 det。"""
        img_scaled, scale = self.ocr_preprocess(img)
        return self._recognize_lines(img_scaled, scale, 0, 0, min_score)

    def _recognize_tiled(self, img, min_score: float):
        """大图分块（REPORT §3.4 RecognizeChunked）：TILE_SIZE 块 + TILE_OVERLAP 比例重叠，
        每块独立 OcrPreprocess（≤1.6×）→ det → rec，坐标映射回全图。
        参考实现 overlap=0；这里 0.25 重叠防整页截图的文字被块缝切断。"""
        h, w = img.shape[0], img.shape[1]
        step = max(1, int(TILE_SIZE * (1 - TILE_OVERLAP)))
        xs = list(range(0, w, step)) if w > TILE_SIZE else [0]
        if xs and xs[-1] + TILE_SIZE < w:
            xs.append(w - TILE_SIZE)          # 右贴边补一块（TilePlan 规则）
        ys = list(range(0, h, step)) if h > TILE_SIZE else [0]
        if ys and ys[-1] + TILE_SIZE < h:
            ys.append(h - TILE_SIZE)
        if len(xs) * len(ys) > TILE_MAX_COUNT:  # 保险丝：超大图加大步进（去重叠）
            step = TILE_SIZE
            xs = list(range(0, w, step)) or [0]
            if xs and xs[-1] + TILE_SIZE < w:
                xs.append(w - TILE_SIZE)
            ys = list(range(0, h, step)) or [0]
            if ys and ys[-1] + TILE_SIZE < h:
                ys.append(h - TILE_SIZE)
        lines = []
        for ty in ys:
            for tx in xs:
                tw = min(w, tx + TILE_SIZE) - tx
                th = min(h, ty + TILE_SIZE) - ty
                tile = img[ty:ty + th, tx:tx + tw]
                tile_scaled, scale = self.ocr_preprocess(tile)
                lines.extend(self._recognize_lines(tile_scaled, scale, tx, ty, min_score))
        return lines

    @staticmethod
    def _same_text(a: str, b: str) -> bool:
        """宽松同文判定：完全相同 / 去空格后互为子串 / 长度相近且 ratio>0.75。
        重叠块对同一段文字常给出「部分串 vs 完整串」（块缝切割所致）。"""
        if a == b:
            return True
        an, bn = a.replace(" ", ""), b.replace(" ", "")
        if not an or not bn:
            return False
        if an in bn or bn in an:
            return True
        if abs(len(an) - len(bn)) <= 6:
            return difflib.SequenceMatcher(None, an, bn).ratio() > 0.75
        return False

    @staticmethod
    def _dedup_lines(lines):
        """跨块去重：同文（宽松）且（中心距 < DEDUP_GRID 或框 IoU > 0.3）只留最高分。

        中心距对付平移重复；IoU 对付「部分框 vs 完整框」——重叠块里同一段文字
        被切出宽窄不同的两个框，中心能差几十像素但 IoU 很高（实测 Flyye MBSS
        同名两行）。不同物理位置的同名物品 IoU=0，不受影响。
        """
        def bbox(ln):
            xs = [p[0] for p in ln["points"]]
            ys = [p[1] for p in ln["points"]]
            return min(xs), min(ys), max(xs), max(ys)

        def iou(a, b):
            ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
            iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
            inter = ix * iy
            if not inter:
                return 0.0
            area_a = max(1, (a[2] - a[0]) * (a[3] - a[1]))
            area_b = max(1, (b[2] - b[0]) * (b[3] - b[1]))
            return inter / min(area_a, area_b)

        kept = []
        for ln in sorted(lines, key=lambda x: -x["score"]):
            bb = bbox(ln)
            cx, cy = (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2
            dup = False
            for k in kept:
                if not OcrEngine._same_text(ln["text"], k["text"]):
                    continue
                kb = bbox(k)
                kcx, kcy = (kb[0] + kb[2]) / 2, (kb[1] + kb[3]) / 2
                if (abs(cx - kcx) < DEDUP_GRID and abs(cy - kcy) < DEDUP_GRID) \
                        or iou(bb, kb) > 0.3:
                    dup = True
                    break
            if not dup:
                kept.append(ln)
        kept.sort(key=lambda x: (x["points"][0][1], x["points"][0][0]))
        return kept

    def recognize(self, img, min_score: float = 0.0, annotate: bool = False):
        """img: BGR ndarray → (lines, annotated_bgr|None, took_ms)。

        lines: [{text, score, points:[[x,y]×4]}]（全图坐标，已排序 + 跨块去重）。
        最长边 > TILED_TRIGGER 走分块识别（修整图小字识别率），否则单次直识。
        """
        t0 = time.time()
        if max(img.shape[0], img.shape[1]) > TILED_TRIGGER:
            lines = self._recognize_tiled(img, min_score)
        else:
            lines = self._recognize_single(img, min_score)
        lines = self._dedup_lines(lines)
        annotated = self.annotate(img, lines) if annotate else None
        return lines, annotated, (time.time() - t0) * 1000.0

    # ---- 标注（REPORT §3.6 ResultAnnotator：数字徽章 + 框） ----

    def annotate(self, img, lines):
        cv2, np = self._cv2, self._np
        dst = img.copy()
        box_color = (225, 182, 105)   # RGB(105,182,225) → BGR
        badge_text = (36, 35, 24)     # RGB(24,35,36) → BGR
        for i, ln in enumerate(lines, 1):
            pts = np.array(ln["points"], dtype=np.int32)
            cv2.polylines(dst, [pts.reshape(-1, 1, 2)], True, box_color, 2, cv2.LINE_AA)
            x, y, w, h = cv2.boundingRect(pts)
            label = str(i)
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)
            r = max(8, max(tw, th) // 2 + 4)   # 半径按标签文字尺寸（规格 §3.6），不是框尺寸
            cx = int(min(max(x - r - 2, r + 1), dst.shape[1] - r - 1))
            cy = int(min(max(y + h // 2, r + 1), dst.shape[0] - r - 1))
            cv2.circle(dst, (cx, cy), r, box_color, -1, cv2.LINE_AA)
            cv2.putText(dst, label, (cx - tw // 2, cy + th // 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, badge_text, 1, cv2.LINE_AA)
        ok, buf = cv2.imencode(".png", dst)
        return buf.tobytes() if ok else None


def decode_image_bgr(img_bytes):
    """PNG/JPEG 字节 → BGR ndarray。缺依赖抛 OcrUnavailable；解不出返回 None。"""
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise OcrUnavailable("缺少 OCR 依赖（%s）—— pip install onnxruntime opencv-python-headless" % exc.name) from exc
    return cv2.imdecode(np.frombuffer(img_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)


def check_available():
    """轻量可用性探测（不装载模型）：模型文件 + 依赖包。返回 (ok, hint)。"""
    assets_dir = resolve_assets_dir()
    for name in OCR_FILES:
        if not os.path.isfile(os.path.join(assets_dir, name)):
            return False, "缺少模型文件 assets/ocr/%s（当前查找目录：%s）" % (name, assets_dir)
    for mod in ("numpy", "cv2", "onnxruntime"):
        try:
            __import__(mod)
        except ImportError:
            return False, "缺少 Python 依赖 %s（pip install onnxruntime opencv-python-headless）" % mod
    return True, None


# --------------------------------------------------------------------------
# 模块级单例（进程内复用；首次调用约 1 s 装载）

_ENGINE = None


def get_engine() -> OcrEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = OcrEngine()
    return _ENGINE
