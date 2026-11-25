#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""EFT 互动地图 · 截图识别宿主（R240，QQ 式速度：保温窗口 + BMP 冻结帧）

    热键（默认 Ctrl+Alt+P，配置 `ocrScan.hotkey` 或 `--hotkey` 可改）
      → PIL ImageGrab 抓整屏 → **BMP** 冻结帧（免压缩编码）→ POST /api/ocr/frame
      → **唤醒保温的选择窗**（R240：浏览器窗口识别完只隐藏不销毁，页面轮询新帧
        ≤150ms 换上——不再每次拉起浏览器，QQ 式 <0.5s 可框选）
      → 用户框选 → 前端裁剪送 /api/ocr/recognize → POST /api/ocr/overlay/state 交接
      → 宿主**隐藏**选择窗，改开**原生透明浮窗**（R239）：
          · 标签窗：UpdateLayeredWindow 逐像素透明 + WS_EX_TRANSPARENT 全窗点击
            穿透——价格文字直接叠在对应装备上，不打断游戏操作；
          · 控制条窗：R249 起是**两个分开的 XP Luna 按钮**（口径循环 + ✕ 关闭），
            整组压在框选区顶边上方 1px，不挡价格。

## R240 防闪动

- 冷启动：窗口在 **-32000 屏幕外**创建，剥标题栏、定位、客户区补偿全部在屏幕外
  完成，就绪后才移入屏幕——用户永远看不到「带标题栏 → 剥掉 → 挪位置」的过程；
- 热键路径：帧先上传再唤醒窗口，页面 `visibilitychange` 立即拉新帧，无白屏/旧帧闪动；
- 隐藏选择窗时把焦点还给游戏（进入框选前记下前台窗口）。

## 生命周期

常驻后台：只注册热键不显示任何窗口。热键 → 选择窗；交接 → 透明浮窗 + 选择窗
保温隐藏；浮窗 ✕ / 再按热键 → 关浮窗。适合 `pythonw tools/scan.py` 挂登录自启。

## 边界

- 只支持 Windows；MVP 只抓主屏（多屏扩展待需要时做）。
- 冻结帧在 BFF 内存里只留最近一帧，10 分钟没人用即过期。
- 浮窗按框选瞬间的屏幕位置绘制——游戏内 UI 滚动/移动后价格会留在原处，再框一次即可。
"""

from __future__ import annotations

import argparse
import io
import json
import math
import os
import sys
import time

TOOLS = os.path.dirname(os.path.abspath(__file__))
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

try:
    from config import OCR_SCAN_TIERS_DEFAULT  # noqa: E402 - R241 档位样式默认值
except Exception:  # pragma: no cover - config 缺失时的兜底单档
    OCR_SCAN_TIERS_DEFAULT = [{"max": None, "color": "#f2f2ee", "sizeScale": 1.0,
                               "font": "msyhbd", "outer": True, "outerColor": "#000000",
                               "inner": False, "innerColor": "#000000"}]

IS_WINDOWS = sys.platform == "win32"
DEFAULT_SERVER = "http://127.0.0.1:8787"
DEFAULT_HOTKEY = "ctrl+alt+p"
SCAN_TITLE = "EFT 截图识别"
SCAN_TITLE_CLOSED = "EFT截图·关闭"
SCAN_TITLE_DONE = "EFT截图·完成"    # R239：交接成功，宿主切换透明浮窗


ROOT = os.path.dirname(TOOLS)
BUILD_DIR = os.path.join(ROOT, "build")
if getattr(sys, "frozen", False):
    # 打包后 ROOT 是 PyInstaller 的临时解包目录，进程退出就没了；
    # 宿主日志/浏览器 pid 落到 %LOCALAPPDATA%\EFTMap\logs 才留得住、可诊断。
    BUILD_DIR = os.path.join(
        os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "EFTMap", "logs"
    )
LOG_PATH = os.path.join(BUILD_DIR, "scan-host.log")

# 价格口径（控制条循环切换）；字段对应 /api/ocr/recognize 的 price 对象。
# R256：仅三档——最新价格 / 24小时均价 / 7日均价（7日均价来自快照 avg7d.values）。
PRICE_MODES = [("last", "最新价格"), ("a24", "24小时均价"), ("w7", "7日均价")]
MODE_FIELDS = {"last": "lastLow", "a24": "avg24h", "w7": "avg7d"}

# 游戏模式（控制条左键「切换模式」循环）；字段对应 /api/ocr/recognize 的 mode。
GAME_MODES = [("regular", "PvP"), ("pve", "PvE"), ("pvps", "PvPS")]


def game_mode_index(code: str) -> int:
    """把游戏模式代码映射到 GAME_MODES 下标（未知→0 即 PvP）。"""
    code = str(code or "regular")
    for i, (c, _l) in enumerate(GAME_MODES):
        if c == code:
            return i
    return 0


def game_mode_label(code: str) -> str:
    return GAME_MODES[game_mode_index(code)][1]


def log(msg: str) -> None:
    """日志同时打 stdout 与 build/scan-host.log——pythonw 下 stdout 无人收，
    文件是唯一可诊断出口（R240 起宿主排障全靠它）。"""
    line = "[%s] %s" % (time.strftime("%m-%d %H:%M:%S"), msg)
    print("[scan] %s" % line, flush=True)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def log_exc(prefix: str, exc: Exception) -> None:
    import traceback

    log("%s：%s\n%s" % (prefix, exc, traceback.format_exc()[-900:]))


def notify_failure(reason: str) -> None:
    """热键链路失败时弹一个置顶提示。

    R279：以前只在日志里写一行，用户按完热键「什么都没发生」——没有 Edge/Chrome、
    服务没起来、抓屏被拒这类环境问题全靠猜。现在给一个可见出口，并把日志路径带上，
    远程排障一句话就能定位。窗口置顶（MB_TOPMOST），游戏全屏独占下可能被吞，
    所以它只是「尽力而为」，真正的证据仍在日志。
    """
    text = "截图识别没有启动起来。\n\n%s\n\n日志：%s" % (reason, LOG_PATH)
    try:
        import ctypes

        MB_ICONERROR = 0x10
        MB_TOPMOST = 0x40000
        ctypes.windll.user32.MessageBoxW(None, text, "EFT 截图识别", MB_ICONERROR | MB_TOPMOST)
    except Exception:  # noqa: BLE001 - 弹窗失败不能再抛
        pass


SINGLE_INSTANCE_NAME = "Local\\EFTMap-ScanHost"
_SINGLE_INSTANCE_HANDLE = None


def acquire_single_instance() -> bool:
    """命名互斥量：同一台机器只允许一个截图宿主。

    打包版由主程序自动拉起宿主；如果用户机器上还留着旧的登录自启任务
    （或上次异常退出没来得及收），两个宿主会抢同一个全局热键——第二个
    RegisterHotKey 必然失败、表现为「按了没反应」。这里直接让后来的那个退出。
    """
    global _SINGLE_INSTANCE_HANDLE
    if not IS_WINDOWS:
        return True
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel32.CreateMutexW(None, False, SINGLE_INSTANCE_NAME)
    if not handle:
        return True                      # 拿不到互斥量时宁可放行，也不要静默不工作
    if ctypes.get_last_error() == 183:   # ERROR_ALREADY_EXISTS
        return False
    _SINGLE_INSTANCE_HANDLE = handle
    return True


def server_alive(server: str = DEFAULT_SERVER, timeout: float = 1.5) -> bool:
    import urllib.request

    try:
        with urllib.request.urlopen(server.rstrip("/") + "/api/health", timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def screen_size() -> tuple[int, int]:
    import ctypes

    user32 = ctypes.windll.user32
    return int(user32.GetSystemMetrics(0)), int(user32.GetSystemMetrics(1))  # SM_CX/YSCREEN


def grab_frame() -> bytes:
    """整屏冻结帧（主屏，物理像素）。

    R240 起编码为 **BMP**：免压缩，整屏抓取+编码 ~100-200ms（PNG 要数百毫秒），
    这是「按热键没有 QQ 截图快」的最大单一瓶颈。
    """
    from PIL import ImageGrab

    img = ImageGrab.grab()                     # MVP：主屏；all_screens 待多屏需求
    buf = io.BytesIO()
    img.save(buf, "BMP")
    return buf.getvalue()


def post_frame(server: str, data: bytes, timeout: float = 30.0) -> str:
    import urllib.request

    req = urllib.request.Request(
        server.rstrip("/") + "/api/ocr/frame", data=data,
        headers={"Content-Type": "application/octet-stream"}, method="POST")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # 本机直连
    with opener.open(req, timeout=timeout) as r:
        doc = json.loads(r.read().decode("utf-8"))
    if not doc.get("ok"):
        raise RuntimeError(doc.get("error") or "冻结帧提交失败")
    return doc["id"]


def post_overlay_state(server: str, region: dict, matches: list, timeout: float = 30.0) -> None:
    """R239 演示模式用：直接把交接态写进 BFF（scan.html 走的是页面内 fetch）。"""
    import urllib.request

    payload = json.dumps({"region": region, "matches": matches}).encode("utf-8")
    req = urllib.request.Request(
        server.rstrip("/") + "/api/ocr/overlay/state", data=payload,
        headers={"Content-Type": "application/json"}, method="POST")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=timeout) as r:
        doc = json.loads(r.read().decode("utf-8"))
    if not doc.get("ok"):
        raise RuntimeError(doc.get("error") or "交接态写入失败")


def fetch_state(server: str, timeout: float = 3.0) -> dict | None:
    """宿主在「EFT截图·完成」标题后取走交接态。失败返回 None（当取消处理）。"""
    import urllib.request

    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(server.rstrip("/") + "/api/ocr/overlay/state", timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def current_mode(config_dir: str | None) -> str:
    """当前游戏模式（设置面板的数据范围），识别价格按它取。"""
    try:
        import config

        scope = (config.load(config_dir) or {}).get("dataScope") or {}
        mode = str(scope.get("mode") or "regular")
        return mode if mode in ("regular", "pve", "pvps") else "regular"
    except Exception:
        return "regular"


def hotkey_requires_mod(parsed) -> bool:
    """R254：全局热键**必须带修饰键**（Ctrl/Alt/Shift/Win）。

    单键热键会 100% 吞掉那个游戏按键——真实事故：用户误把 `\\` 存成热键，
    全局 RegisterHotKey 之后游戏里那个键彻底失灵。UI 层已拒绝单键，这里对
    配置文件被手改的情况兜底。"""
    return bool(parsed) and bool(parsed[0])


def resolve_hotkey(args, config_dir: str | None):
    """--hotkey 显式 > 配置 ocrScan.hotkey > 默认 ctrl+alt+p。"""
    text = args.hotkey
    if not text:
        try:
            import config

            text = (config.load(config_dir).get("ocrScan") or {}).get("hotkey")
        except Exception:
            text = None
    text = text or DEFAULT_HOTKEY
    if str(text).lower() in ("off", "none", "no"):
        return None
    import overlay

    hk = overlay.parse_hotkey(text)
    if not hk:
        raise SystemExit("看不懂这个热键：%s（用 Ctrl/Alt/Shift/Win + 字母/数字/F1-F12）" % text)
    if not hotkey_requires_mod(hk):
        log("热键 %s 没有修饰键（全局注册会吞掉游戏按键），忽略并回退默认 %s"
            % (text, DEFAULT_HOTKEY))
        return overlay.parse_hotkey(DEFAULT_HOTKEY)
    return hk


# ---------------------------------------------------------------------------
# 纯函数：价格格式化与每件/每格/每公斤（可单测，不依赖 Win32）

def _trim(s: str) -> str:
    return s.rstrip("0").rstrip(".") if "." in s else s


def fmt_short(n) -> str:
    """精确卢布金额：'431,400 ₽'。用户要求：不用万/亿简写、精确到个位数；
    空值/非正数 → '—'（该口径无数据）。函数名保留（多处引用）。"""
    if not isinstance(n, (int, float)) or isinstance(n, bool) or not math.isfinite(n) or n <= 0:
        return "—"
    return format(int(round(n)), ",") + " ₽"


def price_base(m: dict, mode_key: str):
    """当前口径下的有效价格（R249/R258）。

    价格口径优先级（R258，用户提供）：
      1) 跳蚤有售卖（priceSource='flea'）→ 当前口径跳蚤价（lastLow/avg24h/avg7d）；
      2) 跳蚤不卖但商人会卖（priceSource='traderSell'）→ 商人售卖价（玩家从商人处买）；
      3) 都不卖（priceSource='trader'）→ 商人收购价（玩家卖给商人，红购物车警示）。
    `manual` 仍最高优先（用户手动选的口径价，R253）。"""
    p = m.get("price") or {}
    manual = p.get("manual")
    if isinstance(manual, (int, float)) and not isinstance(manual, bool) and manual > 0:
        return manual
    ps = p.get("priceSource")
    if ps == "traderSell":
        return p.get("traderSell")
    if ps == "trader":
        return p.get("trader")
    return p.get(MODE_FIELDS.get(mode_key, "lastLow"))


def tier_price(m: dict, mode_key: str, basis: str = "overall", base=None):
    """档位选色用的比价基准（R257）。

    - overall：整体价格（当前口径下每件物品的总价），与旧行为一致。
    - perslot：单格价格 = 整体价 / 占用格数(gw*gh)；取不到网格尺寸时回落整体价。
    仅影响浮窗上物品落在哪一档**颜色**，不改变显示的价格数字（显示恒用整体价）。"""
    if base is None:
        base = price_base(m, mode_key)
    if basis == "perslot":
        if isinstance(base, (int, float)) and base > 0:
            gw = m.get("gw"); gh = m.get("gh")
            if isinstance(gw, int) and isinstance(gh, int) and gw > 0 and gh > 0:
                slots = gw * gh
                if slots > 0:
                    return base / slots
        return base
    return base


def is_trader_price(m: dict) -> bool:
    """这一件是否按商人价显示（浮窗要画购物车图标）。

    R258：商人收购价（'trader'，红购物车警示）与商人售卖价（'traderSell'，
    蓝购物车）都画购物车，只是颜色不同——都不是跳蚤市场价。"""
    return (m.get("price") or {}).get("priceSource") in ("trader", "traderSell")


def trader_price_kind(m: dict) -> str:
    """图标档：'buy'=商人收购价（R280 起显示该商人头像，原为红购物车）
    / 'sell'=商人售卖价（蓝购物车，不变）/ ''=跳蚤价。"""
    ps = (m.get("price") or {}).get("priceSource")
    if ps == "traderSell":
        return "sell"
    if ps == "trader":
        return "buy"
    return ""


# 显示名撞名时，候选之间的价格差到这个倍数以上才认为「报价会误导」，于是只画徽章不报价。
# 差价很小的组（同款不同色、同价变体）仍然报价，只加一个 ? 提醒名字不唯一。
AMBIG_PRICE_MIN_SPREAD = 1.5


def is_ambig_name(m: dict) -> bool:
    """显示名本身有歧义（多个不同物品 / 多个口径）→ 画 ? 徽章。"""
    return bool((m.get("price") or {}).get("ambiguous") or m.get("ambiguous"))


def is_ambig_price(m: dict) -> bool:
    """歧义到「不能报价」的程度 → 浮窗只画 ? 徽章、不画价格。

    两种来源：
      · `price.ambiguous`：同短名多口径（.338/.300 AP、FMJ…，R251）——一律不报价；
      · `m.ambiguous`：同显示名不同物品（实验室白卡 / 蓝色记号钥匙卡 / 钥匙卡收纳盒
        都叫「钥匙卡」，R-fix）——**候选价差 ≥ AMBIG_PRICE_MIN_SPREAD 才不报价**，
        差价小的继续报价（只挂徽章），免得满屏问号。
    """
    p = m.get("price") or {}
    if p.get("manual") is not None:
        return False          # 玩家已在菜单里选定具体物品/口径 → 按所选价正常显示
    if p.get("ambiguous"):
        return True
    if not m.get("ambiguous"):
        return False
    spread = m.get("priceSpread")
    if not isinstance(spread, (int, float)):
        return True           # 拿不到价差 → 保守：宁可不报价
    return spread >= AMBIG_PRICE_MIN_SPREAD


def ambig_candidates(m: dict) -> list:
    """? 徽章点开后的候选表：口径歧义在 `price.candidates`，物品撞名在 `candidates`。"""
    p = (m or {}).get("price") or {}
    return p.get("candidates") or (m or {}).get("candidates") or []



def price_views(m: dict, mode_key: str) -> tuple[str, str, str]:
    """(主价, 每格, 每公斤) 文本。base 取当前口径字段，派生值随口径一起换。"""
    p = m.get("price") or {}
    base = price_base(m, mode_key)
    main = fmt_short(base)
    # R261：散装弹药堆叠数量没识别到（qty=1 兜底）时，base 其实是「单发商人收购价」，
    # 直接显示 405 会被误当成整堆价。加 "/发" 明确标注单发，避免「405 是什么意思」。
    if base and base > 0 and p.get("ammoStack") and p.get("qtyFound") is False:
        main = main + "/发"
    if base and base > 0:
        slots = None
        gw, gh = m.get("gw"), m.get("gh")
        if isinstance(gw, int) and isinstance(gh, int) and gw > 0 and gh > 0:
            slots = gw * gh
        kg = m.get("weight")
        slot_txt = fmt_short(base / slots) if slots else "—"
        kg_txt = fmt_short(base / kg) if isinstance(kg, (int, float)) and kg and kg > 0 else "—"
    else:
        slot_txt = kg_txt = "—"
    return main, slot_txt, kg_txt


def _tier_for(tiers, price):
    """按每件价格选档：命中第一个 max 为空或 price<=max 的档；价格未知落第一档
    （首档默认是最素的灰白——未知价格不该披金档）。"""
    for t in tiers or []:
        if not isinstance(price, (int, float)):
            break
        mx = t.get("max")
        if mx is None or price <= mx:
            return t
    return (tiers or [{}])[0]


def label_base_font(matches: list) -> int:
    """标签的**基准行高**（R243：用户要求「字体固定大小，不能每件不一样」）。

    取所有识别行框高的**中位数**——仍是该玩家屏幕上游戏文字的实际大小（分辨率/
    UI 缩放自适应），但统一成一个值，不随单件物品的检测框高低抖动。
    R249 起真正画出来的固定字号是 `0.80 × 此值` 再按单格宽度全局收缩一次
    （见 `_fixed_label_font()`），用户实测原值偏大、高价单格物资会溢出格子。"""
    heights = []
    for m in matches or []:
        try:
            heights.append(max(8, int(m.get("h") or 0)))
        except (TypeError, ValueError):
            pass
    if not heights:
        return 16
    heights.sort()
    return max(9, min(300, heights[len(heights) // 2]))


def control_position(rx: int, ry: int, rw: int, rh: int,
                     cw: int, ch: int, sw: int, sh: int) -> tuple[int, int]:
    """R249：控制按钮的屏幕位置（纯几何，可单测）。

    用户要求「按钮的最下面的边，在截图选框最上边的上面，有一个像素间隔」——
    即 `cy + ch == ry - 1`。原来放在 `ry + 2`（选区内部）会挡住价格。
    选区顶到屏幕上沿放不下时，退到选区下沿外 1px；再不行才贴屏幕上沿。
    """
    cx = max(0, min(rx + rw - cw - 2, sw - cw))
    cy = ry - ch - 1
    if cy < 0:
        below = ry + rh + 1
        cy = below if below + ch <= sh else 0
    return cx, max(0, min(cy, sh - ch))


def label_cell_unit(matches: list, base_fs: int) -> float:
    """估算游戏里 1×1 格子的像素宽度——价格不得超出单格物资（R249）。

    **实测标定**（`ui图标/ocr测试专用游戏内截图.png`，3840×2160 真实游戏仓库）：
    OCR 行框高 19~27px（中位 22），相邻单格物品名 x 间距 126px → 格宽 ≈ 5.7×行框高；
    1080p 同比例（约 11px 字 / 63px 格），所以这个比值与分辨率无关，不用解包游戏 UI 配置。

    有多件物品时再用相邻物品名的最小正间距校正（横/纵都算，格子是正方形），
    但钳在 3.2~7 倍行高内：2 格宽物品不会把格宽放大、OCR 碎片也不会把它压没。
    """
    unit = 5.7 * max(1, base_fs)
    pts = []
    for m in matches or []:
        try:
            pts.append((int(m.get("x") or 0), int(m.get("y") or 0)))
        except (TypeError, ValueError):
            pass
    if not pts:
        return max(24.0, unit)
    tol = 1.5 * base_fs
    lo, hi = 3.2 * base_fs, 7.0 * base_fs
    # 先按 y 聚类成「行」：OCR 碎片 / 计数数字散落在各列，直接对全体 x 求差
    # 会混出 30px、66px 这种假间距，把格宽压到 90px（真实是 126px）。
    groups: list[list[int]] = []
    for y in sorted(set(v for _x, v in pts)):
        if groups and y - groups[-1][-1] <= tol:
            groups[-1].append(y)
        else:
            groups.append([y])
    row_ys = [sum(g) / len(g) for g in groups]
    cand = [b - a for a, b in zip(row_ys, row_ys[1:]) if lo <= b - a <= hi]
    for g in groups:
        xs = sorted(set(x for x, y in pts if any(abs(y - yy) <= tol for yy in g)))
        cand += [b - a for a, b in zip(xs, xs[1:]) if lo <= b - a <= hi]
    if cand:
        cand.sort()
        # 中位数比最小值稳：2 格宽物品不会放大，个别碎片也不会把格宽压没。
        unit = min(unit, cand[len(cand) // 2])
    return max(24.0, unit)


_OCR_MEMBER_GREY_TIERS = [
    {"max": 50000, "color": "#b9c0c9", "sizeScale": 1.0, "font": "msyhbd",
     "outer": True, "outerColor": "#000000", "inner": False, "innerColor": "#000000"},
]


def load_label_tiers(config_dir: str | None = None, member: bool | None = None) -> list:
    """读 config.ocrScan.labelStyle.tiers（读不到回默认档）。每次重绘时现读，
    设置面板改完档位后下次识别 / 口径切换即生效。

    R255：非会员一律灰白单档（配置里的档位颜色只对会员生效，免费版用户
    拿不到服务器行情数据，按档位上色没有意义）。

    R259：`member` 由调用方传入（OverlaySession 从 BFF `/api/member` 拉到的
    跨进程会员态）。截图宿主是独立进程，本地 `config.is_member()` 永远 False，
    之前因此恒返灰白单档 → 价格颜色一直不生效。"""
    tiers = None
    try:
        import config

        tiers = ((config.load(config_dir).get("ocrScan") or {})
                 .get("labelStyle") or {}).get("tiers")
    except Exception:
        tiers = None
    if member is None:
        try:
            import config as _cfg

            member = _cfg.is_member(config_dir)
        except Exception:
            member = False
    if not member:
        return _OCR_MEMBER_GREY_TIERS
    if isinstance(tiers, list) and tiers:
        return tiers
    return OCR_SCAN_TIERS_DEFAULT


def load_tier_basis(config_dir: str | None = None) -> str:
    """读 config.ocrScan.labelStyle.tierBasis：'overall'(整体价格) 或 'perslot'(单格价格)。
    默认 overall，保持旧行为。非会员无所谓（配色强制灰白）。"""
    try:
        import config

        v = ((config.load(config_dir).get("ocrScan") or {})
             .get("labelStyle") or {}).get("tierBasis")
        if v in ("overall", "perslot"):
            return v
    except Exception:
        pass
    return "overall"


# ---------------------------------------------------------------------------
# 原生透明浮窗（R239）：UpdateLayeredWindow 逐像素 alpha，不走浏览器

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    WS_POPUP = 0x80000000
    WS_EX_LAYERED = 0x00080000
    WS_EX_TRANSPARENT = 0x00000020
    WS_EX_NOACTIVATE = 0x08000000
    WS_EX_TOOLWINDOW = 0x00000080
    WS_EX_TOPMOST = 0x00000008
    GWLP_USERDATA = -21
    GWL_EXSTYLE = -20
    WM_NCHITTEST = 0x0084
    WM_LBUTTONDOWN = 0x0201
    WM_MOUSEMOVE = 0x0200
    WM_LBUTTONUP = 0x0202
    WM_RBUTTONDOWN = 0x0204
    WM_MOUSELEAVE = 0x02A3
    WM_TIMER = 0x0113
    WM_KEYDOWN = 0x0100
    WM_SETCURSOR = 0x0020
    WM_DESTROY = 0x0002
    TME_LEAVE = 0x00000002
    VK_ESCAPE = 0x1B
    IDC_CROSS = 32515
    LWA_ALPHA = 0x00000002
    HTTRANSPARENT = -1
    HTCLIENT = 1
    SW_SHOWNOACTIVATE = 4
    SW_HIDE = 0
    SWP_NOMOVE = 0x0002
    SWP_NOSIZE = 0x0001
    SWP_NOZORDER = 0x0004
    SWP_NOACTIVATE = 0x0010
    HWND_TOPMOST = -1
    ULW_ALPHA = 2
    DIB_RGB_COLORS = 0

    LRESULT = ctypes.c_ssize_t
    WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT,
                                 wintypes.WPARAM, wintypes.LPARAM)

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                    ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD)]

    class BLENDFUNCTION(ctypes.Structure):
        _fields_ = [("BlendOp", wintypes.BYTE), ("BlendFlags", wintypes.BYTE),
                    ("SourceConstantAlpha", wintypes.BYTE), ("AlphaFormat", wintypes.BYTE)]

    class SIZE(ctypes.Structure):
        _fields_ = [("cx", wintypes.LONG), ("cy", wintypes.LONG)]

    class TRACKMOUSEEVENT(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                    ("hwndTrack", wintypes.HWND), ("dwHoverTime", wintypes.DWORD)]

    class WNDCLASSW(ctypes.Structure):
        _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC),
                    ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                    ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                    ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                    ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]

    _user32 = ctypes.windll.user32
    _gdi32 = ctypes.windll.gdi32
    _kernel32 = ctypes.windll.kernel32
    _kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    _kernel32.GetModuleHandleW.restype = wintypes.HMODULE
    _user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
    _user32.RegisterClassW.restype = wintypes.ATOM
    _user32.CreateWindowExW.argtypes = [
        wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
    _user32.CreateWindowExW.restype = wintypes.HWND
    _user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT,
                                       wintypes.WPARAM, wintypes.LPARAM]
    _user32.DefWindowProcW.restype = LRESULT
    _user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.DestroyWindow.argtypes = [wintypes.HWND]
    _user32.ScreenToClient.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    _user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    _user32.LoadCursorW.argtypes = [wintypes.HINSTANCE, ctypes.c_wchar_p]
    _user32.LoadCursorW.restype = wintypes.HANDLE
    _user32.SetCursor.argtypes = [wintypes.HANDLE]
    _user32.TrackMouseEvent.argtypes = [ctypes.POINTER(TRACKMOUSEEVENT)]
    _user32.TrackMouseEvent.restype = wintypes.BOOL
    _user32.SetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPCWSTR]
    _user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                     ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
    _user32.UpdateLayeredWindow.argtypes = [
        wintypes.HWND, wintypes.HDC, ctypes.POINTER(wintypes.POINT),
        ctypes.POINTER(SIZE), wintypes.HDC, ctypes.POINTER(wintypes.POINT),
        wintypes.COLORREF, ctypes.POINTER(BLENDFUNCTION), wintypes.DWORD]
    _DEF_WNDPROC = None  # 由 _ensure_wndclass 填

    _CLASS_NAME = "EFTScanOverlay"
    _CLASS_REGISTERED = False

    # 会话单例：WndProc 通过它把点击转给当前浮窗（同时只存在一个浮窗会话）
    _ACTIVE: "OverlaySession | None" = None
    # R247：ShareX 式原生选区窗（热键只 ShowWindow，不抓屏/不上传/不开浏览器）
    _SELECT_ACTIVE: "NativeSelection | None" = None
    _SELECT_RESULTS: list = []     # ("done", rect) / ("cancel", None)

    def _msg_point(hwnd, lparam):
        """WM_MOUSE* 的 lparam → 屏幕坐标（多屏负坐标也正确）。"""
        pt = wintypes.POINT(ctypes.c_short(lparam & 0xFFFF).value,
                            ctypes.c_short((lparam >> 16) & 0xFFFF).value)
        _user32.ClientToScreen(hwnd, ctypes.byref(pt))
        return pt.x, pt.y

    def _ov_wndproc(hwnd, msg, wparam, lparam):
        role = overlay_role(hwnd)
        if role == 3 and _SELECT_ACTIVE is not None:
            # 选区命中层：整窗可点、光标十字、键鼠事件在进程内处理（无浏览器）
            sel = _SELECT_ACTIVE
            if msg == WM_NCHITTEST:
                return HTCLIENT
            if msg == WM_SETCURSOR:
                _user32.SetCursor(_user32.LoadCursorW(None, ctypes.c_wchar_p(IDC_CROSS)))
                return 1
            if msg == WM_LBUTTONDOWN:
                x, y = _msg_point(hwnd, lparam)
                sel.on_down(x, y)
                return 0
            if msg == WM_MOUSEMOVE:
                x, y = _msg_point(hwnd, lparam)
                sel.on_move(x, y)
                return 0
            if msg == WM_LBUTTONUP:
                x, y = _msg_point(hwnd, lparam)
                sel.on_up(x, y)
                return 0
            if msg == WM_RBUTTONDOWN:
                sel.cancel()
                return 0
            if msg == WM_KEYDOWN and wparam == VK_ESCAPE:
                sel.cancel()
                return 0
            if msg == WM_DESTROY:
                return 0
            return _user32.DefWindowProcW(hwnd, msg, wparam, lparam)
        if msg == WM_NCHITTEST:
            if role in (2, 4, 5):      # 演示底图 / 选区边框 / 提示条：全穿透
                return HTTRANSPARENT
            if role == 0 and _ACTIVE is not None:   # 标签窗：仅 ? 徽章可点
                pt = wintypes.POINT(ctypes.c_short(lparam & 0xFFFF).value,
                                    ctypes.c_short((lparam >> 16) & 0xFFFF).value)
                _user32.ScreenToClient(hwnd, ctypes.byref(pt))
                return HTCLIENT if _ACTIVE.hit_badge(pt.x, pt.y) is not None \
                    else HTTRANSPARENT
            if role == 6:              # 口径选单：整窗可点（SetCapture 点外关闭）
                return HTCLIENT
            if role == 1 and _ACTIVE is not None:   # 控制条：仅两个 XP 按钮可点
                pt = wintypes.POINT(ctypes.c_short(lparam & 0xFFFF).value,
                                    ctypes.c_short((lparam >> 16) & 0xFFFF).value)
                _user32.ScreenToClient(hwnd, ctypes.byref(pt))
                return HTCLIENT if _ACTIVE.hit_button(pt.x, pt.y) else HTTRANSPARENT
            return HTCLIENT
        if role == 0 and _ACTIVE is not None:
            if msg == WM_MOUSEMOVE:
                # lparam 是客户坐标（WM_NCHITTEST 的才是屏幕坐标）
                x = ctypes.c_short(lparam & 0xFFFF).value
                y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
                try:
                    idx = _ACTIVE.hit_badge(x, y)
                    if idx is not None:
                        # R256：悬停 ? 徽章 → 弹窗列出所有候选口径+价（不画价格只画徽章）
                        if _ACTIVE.menu_for != idx:
                            _ACTIVE.open_menu(idx, capture=False)
                        _user32.KillTimer(hwnd, 7)
                        if not _ACTIVE._badge_tracking:
                            tme = TRACKMOUSEEVENT(ctypes.sizeof(TRACKMOUSEEVENT),
                                                  TME_LEAVE, hwnd, 0)
                            _ACTIVE._badge_tracking = bool(
                                _user32.TrackMouseEvent(ctypes.byref(tme)))
                    elif _ACTIVE.menu_for is not None and not _ACTIVE.menu_pinned:
                        _user32.SetTimer(hwnd, 7, 200, None)   # 离开徽章 → 延迟收起
                except Exception as exc:            # 悬停链路异常不能炸消息循环
                    log_exc("[scan] badge hover", exc)
                return 0
            if msg == WM_MOUSELEAVE:
                _ACTIVE._badge_tracking = False
                if _ACTIVE.menu_for is not None and not _ACTIVE.menu_pinned:
                    _user32.SetTimer(hwnd, 7, 200, None)   # 离开徽章 → 延迟收起
                return 0
            if msg == WM_TIMER and wparam == 7:
                _user32.KillTimer(hwnd, 7)
                if not _ACTIVE.menu_pinned:
                    try:
                        _ACTIVE.close_menu()
                    except Exception:
                        pass
                return 0
            if msg == WM_LBUTTONDOWN:
                # R306：WM_LBUTTONDOWN 的 lparam 已经是**客户坐标**（只有 WM_NCHITTEST
                # 才是屏幕坐标）。旧代码把它当屏幕坐标又做了一次 ScreenToClient，
                # 标签窗不在 (0,0) 时命中区被整体平移 → 点「?」徽章永远打不中，
                # 表现为「徽记看得到、点了没反应」。这里直接用客户坐标。
                x = ctypes.c_short(lparam & 0xFFFF).value
                y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
                try:
                    idx = _ACTIVE.hit_badge(x, y)
                    if idx is not None:
                        _ACTIVE.toggle_menu(idx)
                except Exception as exc:            # 选单链路异常不能炸消息循环
                    log_exc("[scan] badge click", exc)
                return 0
        if role == 6 and _ACTIVE is not None:
            if msg == WM_MOUSEMOVE:
                # 光标在菜单上 → 取消收起定时器（让悬停弹窗保持）
                try:
                    _user32.KillTimer(_ACTIVE.labels_hwnd, 7)
                except Exception:
                    pass
                return 0
            if msg == WM_MOUSELEAVE:
                if _ACTIVE.menu_for is not None and not _ACTIVE.menu_pinned:
                    _user32.SetTimer(_ACTIVE.labels_hwnd, 7, 200, None)   # 离开菜单 → 收起
                return 0
            if msg == WM_LBUTTONDOWN:
                x = ctypes.c_short(lparam & 0xFFFF).value
                y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
                try:
                    _ACTIVE.menu_click(x, y)
                except Exception as exc:
                    log_exc("[scan] menu click", exc)
                return 0
            if msg == WM_KEYDOWN and wparam == VK_ESCAPE:
                try:
                    _ACTIVE.close_menu()
                except Exception as exc:
                    log_exc("[scan] menu esc", exc)
                return 0
        if role == 1 and _ACTIVE is not None:
            if msg == WM_MOUSEMOVE:
                # lparam 是客户坐标（WM_NCHITTEST 的才是屏幕坐标）
                x = ctypes.c_short(lparam & 0xFFFF).value
                y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
                _ACTIVE.set_hover(_ACTIVE.hit_button(x, y))
                if not _ACTIVE._tracking:
                    tme = TRACKMOUSEEVENT(ctypes.sizeof(TRACKMOUSEEVENT), TME_LEAVE,
                                          hwnd, 0)
                    _ACTIVE._tracking = bool(_user32.TrackMouseEvent(ctypes.byref(tme)))
                return 0
            if msg == WM_MOUSELEAVE:
                _ACTIVE._tracking = False
                _ACTIVE.set_hover(None)
                _ACTIVE.set_pressed(None)
                return 0
            if msg == WM_LBUTTONDOWN:
                x = ctypes.c_short(lparam & 0xFFFF).value
                y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
                key = _ACTIVE.hit_button(x, y)
                _ACTIVE.set_pressed(key)
                if key == "gamemode":
                    if _ACTIVE.member:
                        _ACTIVE.cycle_game_mode()
                    # R255：非会员模式切换禁用（免费版无服务器行情，切了没意义）
                elif key == "basis":
                    if _ACTIVE.member:
                        _ACTIVE.cycle()
                    # R255：非会员口径按钮禁用（免费版无服务器行情，切了没意义）
                elif key == "close":
                    _ACTIVE.close()
                return 0
            if msg == WM_LBUTTONUP:
                _ACTIVE.set_pressed(None)
                return 0
        if msg == WM_DESTROY:
            return 0
        return _user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def overlay_role(hwnd: int) -> int:
        import overlay as _ov

        try:
            return int(_ov._get_style(hwnd, GWLP_USERDATA) or 0)
        except Exception:
            return 0

    def _ensure_wndclass() -> None:
        global _CLASS_REGISTERED, _DEF_WNDPROC
        if _CLASS_REGISTERED:
            return
        import overlay as _ov

        _ov.dpi_aware()
        proc = WNDPROC(_ov_wndproc)
        _DEF_WNDPROC = proc  # 防 GC
        wc = WNDCLASSW()
        wc.lpfnWndProc = proc
        wc.hInstance = _kernel32.GetModuleHandleW(None)
        wc.lpszClassName = _CLASS_NAME
        if not _user32.RegisterClassW(ctypes.byref(wc)):
            # ERROR_CLASS_ALREADY_EXISTS 等不致命——CreateWindowExW 会兜底报错
            log("RegisterClassW 返回 0（可能已注册），继续")
        _CLASS_REGISTERED = True

    def create_overlay_window(role: int, title: str = _CLASS_NAME) -> int:
        """role: 0=标签窗（? 徽章可点、其余穿透） 1=控制条（按钮可点） 2=演示底图窗
        3=R247 选区命中层（整窗可点，alpha=1 常量） 4=选区边框层 5=提示条层
        6=R253 口径选单弹窗（整窗可点）。
        """
        _ensure_wndclass()
        ex = WS_EX_LAYERED | WS_EX_TOPMOST | WS_EX_TOOLWINDOW
        if role != 3:                    # 选区命中层要拿键盘/鼠标，不能 NOACTIVATE
            ex |= WS_EX_NOACTIVATE
        if role in (4, 5):               # 纯视觉层全穿透（标签窗 R253 起徽章可点，
            ex |= WS_EX_TRANSPARENT      # 改用 WM_NCHITTEST 精确放行，不再整窗穿透）
        hwnd = _user32.CreateWindowExW(ex, _CLASS_NAME, title, WS_POPUP,
                                       0, 0, 1, 1, None, None, _kernel32.GetModuleHandleW(None),
                                       None)
        if not hwnd:
            raise OSError("CreateWindowExW 失败：%d" % _kernel32.GetLastError())
        import overlay as _ov

        _ov._set_style(hwnd, GWLP_USERDATA, role)
        if role == 3:
            # 常量 alpha=1：几乎不可见，但整窗仍接收鼠标（colorkey 会穿透，不能用）
            _user32.SetLayeredWindowAttributes(ctypes.c_void_p(hwnd), 0, 1, LWA_ALPHA)
        return hwnd

    def set_layered_bitmap(hwnd: int, img, x: int, y: int) -> None:
        """把 RGBA PIL 图写成窗口内容（逐像素 alpha），同时定位窗口。"""
        import numpy as np

        w, h = img.size
        arr = np.asarray(img.convert("RGBA"), dtype=np.uint16)
        alpha = arr[:, :, 3:4]
        prem = (arr[:, :, :3] * alpha // 255).astype(np.uint8)  # 预乘（ULW 要求）
        bgra = np.dstack([prem[:, :, 2], prem[:, :, 1], prem[:, :, 0],
                          arr[:, :, 3].astype(np.uint8)]).copy()
        hdc_screen = _user32.GetDC(None)
        hdc_mem = _gdi32.CreateCompatibleDC(hdc_screen)
        bi = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -h, 1, 32,
                              0, 0, 0, 0, 0, 0)
        bits = ctypes.c_void_p()
        hbmp = _gdi32.CreateDIBSection(hdc_mem, ctypes.byref(bi), DIB_RGB_COLORS,
                                       ctypes.byref(bits), None, 0)
        if not hbmp or not bits:
            raise OSError("CreateDIBSection 失败")
        old = _gdi32.SelectObject(hdc_mem, hbmp)
        ctypes.memmove(bits, bgra.ctypes.data, w * h * 4)
        blend = BLENDFUNCTION(0, 0, 255, 1)     # AC_SRC_OVER / 255 / AC_SRC_ALPHA
        ok = _user32.UpdateLayeredWindow(
            hwnd, hdc_screen, ctypes.byref(wintypes.POINT(x, y)),
            ctypes.byref(SIZE(w, h)), hdc_mem, ctypes.byref(wintypes.POINT(0, 0)),
            0, ctypes.byref(blend), ULW_ALPHA)
        _gdi32.SelectObject(hdc_mem, old)
        _gdi32.DeleteObject(hbmp)
        _gdi32.DeleteDC(hdc_mem)
        _user32.ReleaseDC(None, hdc_screen)
        if not ok:
            raise OSError("UpdateLayeredWindow 失败：%d" % ctypes.get_last_error())

    def _topmost(hwnd: int) -> None:
        _user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                             SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

    # ---- 字体与绘制 ----

    _FONT_CACHE: dict = {}
    _FONT_FILES = {"msyh": "msyh.ttc", "msyhbd": "msyhbd.ttc",
                   "simhei": "simhei.ttf", "simsun": "simsun.ttc",
                   "segoeuib": "segoeuib.ttf"}   # 仅内部用：₽ 字形（中文系字体没有 U+20BD）

    def _font(key: str, size: int):
        """按字体键取 PIL 字体（键来自 config.ocrScan 档位样式，见 config.OCR_FONT_KEYS）。"""
        key = str(key or "msyhbd").lower()
        cache_key = (key, size)
        if cache_key in _FONT_CACHE:
            return _FONT_CACHE[cache_key]
        from PIL import ImageFont

        windir = os.environ.get("WINDIR", r"C:\Windows")
        path = os.path.join(windir, "Fonts", _FONT_FILES.get(key) or "msyhbd.ttc")
        try:
            f = ImageFont.truetype(path, size)
        except Exception:
            try:
                f = ImageFont.truetype(os.path.join(windir, "Fonts", "msyhbd.ttc"), size)
            except Exception:
                f = ImageFont.load_default()
        _FONT_CACHE[cache_key] = f
        return f

    def _rgba(hex_color: str, alpha: int = 240):
        s = str(hex_color or "#ffffff").strip()
        try:
            return (int(s[1:3], 16), int(s[3:5], 16), int(s[5:7], 16), alpha)
        except (ValueError, IndexError):
            return (255, 255, 255, alpha)

    def _draw_styled(dr, pos, text, font, tier, fs):
        """按档位样式画一行：外描边（最外圈）→ 内描边（贴字环）→ 字体本色，三层叠加。"""
        w_o = max(1, fs // 9) if tier.get("outer") else 0
        w_i = max(1, fs // 16) if tier.get("inner") else 0
        w_total = w_o + w_i
        c_main = _rgba(tier.get("color"), 242)
        c_outer = _rgba(tier.get("outerColor"), 235)
        c_inner = _rgba(tier.get("innerColor"), 235)
        if w_total:
            first = c_outer if w_o else c_inner
            dr.text(pos, text, font=font, fill=first, stroke_width=w_total, stroke_fill=first)
        if w_o and w_i:
            dr.text(pos, text, font=font, fill=c_inner, stroke_width=w_total - w_i,
                    stroke_fill=c_inner)
        dr.text(pos, text, font=font, fill=c_main)

    def _split_ruble(text: str):
        """R243/R261：拆出 ₽ 及**其后可能跟的尾巴**（-微软雅黑/黑体/宋体都没有
        U+20BD 字形，会渲染成方框「口」，₽ 必须单独用 Segoe UI Bold 画）。

        返回 (前缀, 是否带 ₽, ₽ 之后的尾巴)：'405 ₽' → ('405', True, '')；
        '405 ₽/发' → ('405', True, '/发')；无 ₽ → (text, False, '')。
        尾巴（如 '/发'）用回主字体，避免中文/斜杠也塞进 Segoe UI 变方框。"""
        i = text.find("₽")
        if i < 0:
            return text, False, ""
        return text[:i].rstrip(), True, text[i + 1:]

    # ---- R249：红色购物车小图标（禁售跳蚤 → 只能卖给商人） ----

    def _cart_metrics(fs: int):
        """购物车占位（宽, 高）。画在主价左侧，整组仍右对齐到物品名右沿。"""
        h = max(9, int(round(fs * 0.92)))
        return int(round(h * 1.18)), h

    def _cart_gap(fs: int) -> int:
        return max(2, int(round(fs * 0.22)))

    # ---- R252：黄色 ? 徽章（同短名多口径歧义，市场页 mk-ocr-ambig 同款配色） ----

    def _ambig_metrics(fs: int):
        """徽章占位（直径, 与后续内容的间距）。画在主价行最左侧。"""
        d = max(9, int(round(fs * 0.92)))
        return d, max(2, int(round(fs * 0.22)))

    def _draw_ambig_badge(dr, x: float, y: float, fs: int):
        """自绘黄色圆形 ?：不用 Unicode emoji，? 字形本身各字体都有，
        用 segoeuib 单独绘制保证与 ₽ 同样的渲染质量。"""
        d, _ = _ambig_metrics(fs)
        x, y = int(round(x)), int(round(y))
        dr.ellipse([x, y, x + d, y + d],
                   fill=(243, 212, 118, 245), outline=(185, 150, 46, 245),
                   width=max(1, int(round(fs / 15))))
        dr.text((x + d / 2, y + d / 2), "?",
                font=_font("segoeuib", max(8, int(round(fs * 0.60)))),
                fill=(107, 82, 0, 255), anchor="mm")

    def _draw_cart(dr, x: float, y: float, fs: int, kind: str = "buy"):
        """自绘小购物车：把手 + 梯形车斗 + 两个轮子。
        红色=商人收购价(buy，警示) / 蓝色=商人售卖价(sell，玩家从商人处买)。
        不用 Unicode 字形（游戏内中文系字体没有 🛒，会变豆腐块）。"""
        w, h = _cart_metrics(fs)
        x, y = int(round(x)), int(round(y))
        if kind == "sell":
            red, dark = (56, 132, 224, 245), (12, 40, 92, 245)
        else:
            red, dark = (226, 54, 48, 245), (74, 14, 14, 245)
        lw = max(1, int(round(fs / 15)))
        dr.line([(x + w * 0.02, y + h * 0.20), (x + w * 0.20, y + h * 0.20),
                 (x + w * 0.30, y + h * 0.46)], fill=dark, width=lw, joint="curve")
        basket = [(x + w * 0.24, y + h * 0.44), (x + w * 0.98, y + h * 0.44),
                  (x + w * 0.86, y + h * 0.76), (x + w * 0.36, y + h * 0.76)]
        dr.polygon(basket, fill=red)
        dr.line(basket + [basket[0]], fill=dark, width=lw, joint="curve")
        r = max(1, int(round(h * 0.09)))
        for cx in (x + w * 0.41, x + w * 0.80):
            dr.ellipse([cx - r, y + h * 0.84 - r, cx + r, y + h * 0.84 + r],
                       fill=red, outline=dark, width=lw)

    # ---- R280：红色购物车 → 最高收购价商人的头像 --------------------------
    # 用户口径：「假如这个物资是跳蚤不能卖的，则显示最高收购价的商人的图片，
    # 后面再带价格」，并且「只改这个红色购物车图标」。所以：
    #   · 仅 priceSource='trader'（红购物车）换成商人头像；
    #   · 'traderSell'（蓝购物车）、跳蚤价、? 徽章、价格数字/颜色/字号/位置全不动；
    #   · 头像沿用任务界面 db4Face 的 portraits/<id>.webp，占位仍是 _cart_metrics，
    #     这样 _fixed_label_font 的算宽逻辑一点都不用改。
    _TRADER_PORTRAIT_CACHE: dict = {}

    def _asset_root() -> str:
        """资源根：冻结态是 _MEIPASS（即 _internal），源码态是仓库根。"""
        return getattr(sys, "_MEIPASS", None) or ROOT

    def trader_portrait_id(m: dict) -> str:
        """红购物车对应的商人 = 最高收购价商人（serve.py 的 price.traderId）。"""
        p = m.get("price") or {}
        if p.get("priceSource") == "trader":
            return str(p.get("traderId") or "")
        return ""

    def _trader_portrait(trader_id, size: int):
        """加载任务界面同款商人头像，按 (id, 尺寸) 缓存；缺文件返回 None。"""
        from PIL import Image, ImageOps

        tid = str(trader_id or "")
        if not tid or "/" in tid or "\\" in tid or ".." in tid:
            return None
        size = max(8, int(size))
        key = (tid, size)
        if key in _TRADER_PORTRAIT_CACHE:
            return _TRADER_PORTRAIT_CACHE[key]
        path = os.path.join(_asset_root(), "assets", "icons-traders",
                            "portraits", tid + ".webp")
        img = None
        if os.path.isfile(path):
            try:
                with Image.open(path) as src:
                    img = ImageOps.fit(src.convert("RGBA"), (size, size), Image.LANCZOS)
            except Exception:  # noqa: BLE001 - 坏图不能拖垮整个浮窗
                img = None
        _TRADER_PORTRAIT_CACHE[key] = img
        return img

    def _draw_trader_badge(img, dr, x: float, y: float, fs: int, trader_id) -> bool:
        """在购物车原占位里贴圆形商人头像；缺头像时给中性灰圆（绝不退回红购物车）。"""
        from PIL import Image, ImageDraw

        cw, ch = _cart_metrics(fs)
        side = max(8, ch)
        ox = int(round(x + (cw - side) / 2.0))
        oy = int(round(y))
        portrait = _trader_portrait(trader_id, side)
        if portrait is None:
            dr.ellipse([ox, oy, ox + side, oy + side], fill=(64, 64, 64, 220),
                       outline=(190, 190, 190, 230), width=1)
            return False
        mask = Image.new("L", (side, side), 0)
        ImageDraw.Draw(mask).ellipse([0, 0, side - 1, side - 1], fill=255)
        img.paste(portrait, (ox, oy), mask)
        dr.ellipse([ox, oy, ox + side, oy + side],
                   outline=(225, 225, 225, 220), width=1)
        return True

    def _price_line_width(dr, text: str, font_key: str, fs: int,
                          cart: bool = False, ambig: bool = False,
                          cart_kind: str = "") -> float:
        core, ruble, tail = _split_ruble(text)
        w = dr.textlength(core, font=_font(font_key, fs)) if core else 0
        if ruble:
            if core:
                w += fs * 0.12
            w += dr.textlength("₽", font=_font("segoeuib", fs))
            if tail:
                w += dr.textlength(tail, font=_font(font_key, fs))
        if cart:
            w += _cart_metrics(fs)[0] + _cart_gap(fs)
        if ambig:
            d, g = _ambig_metrics(fs)
            w += d + g
        return w

    def _draw_price_line(dr, pos, text: str, font_key: str, tier, fs,
                         cart: bool = False, ambig: bool = False,
                         cart_kind: str = "", img=None, trader_id=None):
        core, ruble, tail = _split_ruble(text)
        x, y = pos
        if ambig:                      # ? 徽章在最左，然后购物车，然后价格
            d, g = _ambig_metrics(fs)
            _draw_ambig_badge(dr, x, y + max(0, (fs - d) // 2), fs)
            x += d + g
        if cart:
            cw, ch = _cart_metrics(fs)
            icon_y = y + max(0, (fs - ch) // 2)
            if cart_kind == "buy" and img is not None:
                # R280：只换红色购物车；蓝色购物车（traderSell）保持自绘图标。
                _draw_trader_badge(img, dr, x, icon_y, fs, trader_id)
            else:
                _draw_cart(dr, x, icon_y, fs, cart_kind)
            x += cw + _cart_gap(fs)
        if core:
            _draw_styled(dr, (x, y), core, _font(font_key, fs), tier, fs)
            x += dr.textlength(core, font=_font(font_key, fs))
        if ruble:                      # ₽ 用 Segoe UI Bold；尾巴（/发）用回主字体
            if core:
                x += fs * 0.12
            _draw_styled(dr, (x, y), "₽", _font("segoeuib", fs), tier, fs)
            x += dr.textlength("₽", font=_font("segoeuib", fs))
            if tail:
                _draw_styled(dr, (x, y), tail, _font(font_key, fs), tier, fs)

    def _fixed_label_font(dr, ordered: list, tiers: list, base_fs: int,
                          unit: float) -> int:
        """R249：**全场统一固定字号**，不再为某一件单独缩字。

        起点按实测标定取 OCR 行框高的 0.80 倍（上一版直接等于行框高，高价单格
        物品的 `431,400 ₽` 会溢出格子）。再按最窄 1×1 格宽做一次**全局**收缩：
        四种口径、所有物品、所有档位字体里最长的那行必须塞得进单格，否则整屏
        字号一起降 1px——切换口径 / 不同物品看到的字号永远一致。
        """
        fs = max(9, min(300, int(round(base_fs * 0.80))))
        max_scale = 1.0
        fonts = []
        for t in tiers or []:
            try:
                max_scale = max(max_scale, float(t.get("sizeScale") or 1.0))
            except (TypeError, ValueError):
                pass
            fonts.append(t.get("font"))
        fonts = fonts or [None]
        limit = max(24.0, unit - max(4, int(base_fs * 0.20)))
        while fs > 9:
            widest = 0.0
            fs2 = max(9, int(round(fs * 0.74)))
            for m in ordered:
                lines = []
                for key in MODE_FIELDS:      # 四种口径取最坏情况，切换时字号不跳
                    main, slot_txt, _third = price_views(m, key)
                    lines.append((main, is_trader_price(m),
                                  is_ambig_price(m) or is_ambig_name(m), fs,
                                  trader_price_kind(m)))
                    lines.append(("单格 " + slot_txt, False, False, fs2, ""))
                for text, cart, amb, size, ckind in lines:
                    for fk in fonts:
                        widest = max(widest,
                                     _price_line_width(dr, text, fk, size, cart, amb,
                                                       ckind))
            widest = widest * max_scale + max(4, int(fs * 0.16))
            if widest <= limit:
                break
            fs -= 1
        return fs

    def render_labels(region_w: int, region_h: int, matches: list, mode_key: str,
                      tiers: list | None = None, extra_bottom: int = 0,
                      badges_out: list | None = None, tier_basis: str = "overall"):
        """价格标签位图（R249）：第 1 行留空（装备名那一行），第 2 行整体价、
        第 3 行单格价；**两行右端都对齐装备名最右侧的字**。

        R249 三处修正（用户实测反馈）：
          · 不再左对齐到名字左沿——游戏里名字印在格子右上角，左对齐会让价格
            向右冲进相邻格子；右对齐后价格向左展开，正好落在本格内。
          · 字号全屏固定（不再为单件临时缩字），基准 = 0.80×OCR 行框高；再按
            实测的 1×1 格宽做一次全局收缩，高价单格物资也不会溢出格子。
          · 禁售跳蚤的物品按商人收购价显示，主价左侧画红色购物车小图标。
          · R252：多口径歧义（.338/.300 AP 同名）的物品在主价最左侧画黄色
            ? 徽章——这价是按推断口径算的，提醒玩家去市场页核对候选。

        `extra_bottom`：画布向下多留的高度（像素）。框选区靠近屏幕下沿时，最后几行的
        价格仍能画在名字下方，而不是被夹回名字上（窗口仍是点击穿透的透明层）。

        `badges_out`：传入 list 时收集每件歧义物品的 ? 徽章矩形（画布坐标，
        R253 徽章可点击弹口径选单用）：[(match 序号, (x0, y0, x1, y1)), …]。
        """
        from PIL import Image, ImageDraw

        tiers = tiers or OCR_SCAN_TIERS_DEFAULT
        base_fs = label_base_font(matches)
        unit = label_cell_unit(matches, base_fs)
        canvas_h = max(1, int(region_h) + max(0, int(extra_bottom or 0)))
        img = Image.new("RGBA", (max(1, region_w), canvas_h), (0, 0, 0, 0))
        dr = ImageDraw.Draw(img)
        ordered = sorted(matches or [],
                         key=lambda x: (int(x.get("x") or 0), int(x.get("y") or 0)))
        # R309：徽章矩形记的是**原始 matches 下标**。render 按 (x,y) 重排过，
        # 若直接记排序后的位置，open_menu 拿到的就是另一件物品（多数没有候选，
        # 表现为「点 ? 没反应」）。
        orig_of = {id(m): i for i, m in enumerate(matches or [])}
        fixed_fs = _fixed_label_font(dr, ordered, tiers, base_fs, unit)
        for pos, m in enumerate(ordered):
            ax = int(m.get("x") or 0)
            ay = int(m.get("y") or 0)
            try:
                bh = max(8, int(m.get("h") or base_fs))
                bw = max(0, int(m.get("w") or 0))
            except (TypeError, ValueError):
                bh, bw = base_fs, 0
            right = ax + bw                 # 装备名最右侧的字 → 价格右沿
            base = price_base(m, mode_key)
            tier = _tier_for(tiers, tier_price(m, mode_key, tier_basis, base))
            fk = tier.get("font")
            try:
                fs = int(round(fixed_fs * float(tier.get("sizeScale") or 1.0)))
            except (TypeError, ValueError):
                fs = fixed_fs
            fs = max(9, min(300, fs))
            fs2 = max(9, int(round(fs * 0.74)))
            gap = max(2, int(round(fs * 0.10)))
            # 行距按真实墨迹算：中文字形比 em 框向下多出约 0.3×字号（含描边）。
            step = max(fs + 2, int(round(fs * 1.32)))
            main, slot_txt, _third = price_views(m, mode_key)
            line1 = main
            line2 = "单格 " + slot_txt
            cart_kind = trader_price_kind(m)
            cart = bool(cart_kind)
            amb = is_ambig_price(m)      # R252：黄色 ? 徽章（多口径歧义）→ 不报价
            soft = (not amb) and is_ambig_name(m)   # 名字有歧义但价差小 → 报价 + 徽章
            # 同一行右侧最近的装备名（或框选区右边界）是价格不得越过的硬边界。
            rights = [int(n.get("x") or 0) for n in ordered
                      if abs(int(n.get("y") or 0) - ay) <= max(bh, base_fs)
                      and int(n.get("x") or 0) >= right + gap]
            avail = (min(rights) - gap) if rights else (region_w - 2)

            def right_x(text, size, with_cart, with_ambig=False):
                # 描边向外扩 ~0.16×字号（textlength 不含描边），量宽时一起算进去
                lw = _price_line_width(dr, text, fk, size, with_cart, with_ambig) \
                    + max(4, int(size * 0.16))
                x = right - lw
                if x + lw > avail:
                    x = avail - lw
                return max(0, x), lw

            x1, w1 = right_x(line1, fs, cart, amb or soft)
            x2, w2 = right_x(line2, fs2, False)
            block_left = min(x1, x2)
            block_right = max(x1 + w1, x2 + w2)
            total_h = step + int(round(fs2 * 1.30))
            # 同一列下方最近的装备名：价格块不得越到它的行上（否则压住下一件名字）
            next_top = None
            for n in ordered[pos + 1:]:
                ny = int(n.get("y") or 0)
                if ny < ay + max(bh, base_fs):     # 同一行邻格不算「下方阻挡」
                    continue
                nx = int(n.get("x") or 0)
                nw = max(0, int(n.get("w") or 0))
                if block_left < nx + nw and nx < block_right:
                    next_top = ny
                    break
            limit = (next_top - gap) if next_top is not None else canvas_h - 2
            # 第 1 行留空 = 装备名自身那一行；价格从它下沿再起一行
            start_y = ay + max(bh, fs) + gap
            bd, _bg = _ambig_metrics(fs)

            def _badge_rect(lx, ly, size=None):
                """主价行最左元素是 ? 徽章（R253 可点击命中区，画布坐标）。

                R309：`soft`（撞名但价差小、仍报价）也会在价格左侧画 ?，
                命中区必须一并登记，否则那枚徽章是鼠标穿透的。
                """
                if not ((amb or soft) and badges_out is not None):
                    return
                d = _ambig_metrics(size or fs)[0]
                by = ly + max(0, ((size or fs) - d) // 2)
                badges_out.append((orig_of.get(id(m), pos),
                                   (int(lx), int(by), int(lx + d), int(by + d))))

            if start_y + total_h <= limit:
                if amb:
                    # R256：歧义物品只画 ? 徽章（不画价格）；悬停徽章弹窗列出候选口径+价
                    _badge_rect(x1, start_y)
                    _draw_ambig_badge(dr, x1, start_y + max(0, (fs - _ambig_metrics(fs)[0]) // 2), fs)
                else:
                    _badge_rect(x1, start_y)
                    _draw_price_line(dr, (x1, start_y), line1, fk, tier, fs, cart, soft,
                                     cart_kind, img, trader_portrait_id(m))
                    _draw_price_line(dr, (x2, start_y + step), line2, fk, tier, fs2)
            elif next_top is None and ay - total_h - gap >= 0:
                # 屏幕下沿兜底：下方没空间就画在名字上方（不会碰到下一行）
                top = ay - total_h - gap
                if amb:
                    _badge_rect(x1, top)
                    _draw_ambig_badge(dr, x1, top + max(0, (fs - _ambig_metrics(fs)[0]) // 2), fs)
                else:
                    _badge_rect(x1, top)
                    _draw_price_line(dr, (x1, top), line1, fk, tier, fs, cart, soft,
                                     cart_kind, img, trader_portrait_id(m))
                    _draw_price_line(dr, (x2, top + step), line2, fk, tier, fs2)
            else:
                # 行距太密（相邻两件贴得很近）：退化为名字右侧单行，绝不压字
                inline = main + (" · 单格 " + slot_txt if slot_txt != "—" else "")
                iw = _price_line_width(dr, inline, fk, fs2, cart, soft, cart_kind) \
                    + max(4, int(fs2 * 0.16))
                ix = ax + bw + gap
                if ix + iw > avail:
                    ix = max(0, min(ax, avail - iw))
                if amb:
                    _badge_rect(ix, ay, fs2)
                    _draw_ambig_badge(dr, ix, ay + max(0, (fs2 - _ambig_metrics(fs2)[0]) // 2), fs2)
                else:
                    _badge_rect(ix, ay, fs2)
                    _draw_price_line(dr, (ix, ay), inline, fk, tier, fs2, cart, soft,
                                     cart_kind, img, trader_portrait_id(m))
        return img

    # ---- R249：项目现成的 XP Luna 按钮皮肤（assets/xp-ui/btn-*.png） ----

    _XP_BTN_CACHE: dict = {}

    def _xp_btn_src(state: str):
        files = {"normal": "btn-normal.png", "hover": "btn-hover.png",
                 "pressed": "btn-pressed.png"}
        name = files.get(state, "btn-normal.png")
        if name in _XP_BTN_CACHE:
            return _XP_BTN_CACHE[name]
        from PIL import Image

        try:
            im = Image.open(os.path.join(ROOT, "assets", "xp-ui", name)).convert("RGBA")
        except Exception:
            im = None                       # 打包漏资源时走自绘兜底
        _XP_BTN_CACHE[name] = im
        return im

    def _nine_slice(src, w: int, h: int):
        """XP 按钮位图 95×42、四角 5px 不拉伸（manifest.json `slice_1x=5`）。"""
        from PIL import Image

        sw, sh = src.size
        c = 5
        # 皮肤是 42px 高的按钮、5px 立体边框；压到 24px 高时边框也要等比收成 3px，
        # 否则上下各 5px 全是被拉伸的深色边，按钮中间只剩一条浅色（不像 XP 按钮）。
        cc = max(2, min(c, w // 2, h // 2, max(2, int(round(c * h / sh)))))
        mw, mh = w - 2 * cc, h - 2 * cc
        crop = lambda a, b, d, e: src.crop((a, b, d, e))
        tiles = (
            (crop(0, 0, c, c).resize((cc, cc), Image.LANCZOS), (0, 0)),
            (crop(c, 0, sw - c, c).resize((mw, cc), Image.LANCZOS), (cc, 0)),
            (crop(sw - c, 0, sw, c).resize((cc, cc), Image.LANCZOS), (w - cc, 0)),
            (crop(0, c, c, sh - c).resize((cc, mh), Image.LANCZOS), (0, cc)),
            (crop(c, c, sw - c, sh - c).resize((mw, mh), Image.LANCZOS), (cc, cc)),
            (crop(sw - c, c, sw, sh - c).resize((cc, mh), Image.LANCZOS), (w - cc, cc)),
            (crop(0, sh - c, c, sh).resize((cc, cc), Image.LANCZOS), (0, h - cc)),
            (crop(c, sh - c, sw - c, sh).resize((mw, cc), Image.LANCZOS), (cc, h - cc)),
            (crop(sw - c, sh - c, sw, sh).resize((cc, cc), Image.LANCZOS), (w - cc, h - cc)),
        )
        out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        for tile, pos in tiles:
            out.alpha_composite(tile, dest=pos)
        return out

    def _paint_xp_button(img, box, state: str):
        from PIL import ImageDraw

        x0, y0, x1, y1 = box
        w, h = x1 - x0, y1 - y0
        src = _xp_btn_src(state)
        if src is not None and w > 4 and h > 4:
            img.alpha_composite(_nine_slice(src, w, h), dest=(x0, y0))
            return
        dr = ImageDraw.Draw(img)            # 兜底：XP Luna 立体边框
        dr.rounded_rectangle([x0, y0, x1 - 1, y1 - 1], radius=3,
                             fill=(236, 233, 216, 242), outline=(104, 104, 96, 255), width=1)
        dr.line([(x0 + 1, y0 + 1), (x1 - 2, y0 + 1)], fill=(255, 255, 255, 235))
        dr.line([(x0 + 1, y0 + 1), (x0 + 1, y1 - 2)], fill=(255, 255, 255, 235))

    def _paint_status_field(img, box):
        """只读金额栏：XP 凹面（暗线在上/左、亮线在下/右），不做按钮高光，
        避免玩家误以为可以点。"""
        from PIL import ImageDraw

        x0, y0, x1, y1 = box
        dr = ImageDraw.Draw(img)
        dr.rectangle([x0, y0, x1 - 1, y1 - 1], fill=(250, 249, 242, 246),
                     outline=(128, 126, 116, 255))
        dr.line([(x0 + 1, y0 + 1), (x1 - 2, y0 + 1)], fill=(170, 166, 152, 230))
        dr.line([(x0 + 1, y0 + 1), (x0 + 1, y1 - 2)], fill=(170, 166, 152, 230))
        dr.line([(x0 + 2, y1 - 2), (x1 - 2, y1 - 2)], fill=(255, 255, 255, 235))
        dr.line([(x1 - 2, y0 + 2), (x1 - 2, y1 - 2)], fill=(255, 255, 255, 235))

    def render_control(gamemode_label: str, basis_label: str, scale: float = 1.0,
                       hover: str | None = None, pressed: str | None = None,
                       member: bool = True, total_label: str = ""):
        """R256：**三个分开的 XP Luna 按钮** [切换模式][价格切换][✕关闭]，中间全透明间隔。
        R309：`total_label` 非空时，在最左侧「切换模式」按钮边上加一块只读总价值栏；
        它不参与 hit_button（鼠标照样穿透），只用来一眼看总价。

        顺序（左→右）严格按需求：价格切换按钮的左侧是「切换模式」按钮。
        返回 (位图, gamemode矩形, basis矩形, close矩形)（客户坐标）。
        非会员 `member=False` → 两个功能键都灰字（免费版无服务器行情，切了没意义），
        点击由 WndProc 忽略；关闭键永远可用。"""
        from PIL import Image, ImageDraw

        s = max(1.0, min(2.0, scale))
        fs = max(11, int(round(12 * s)))
        f = _font("msyh", fs)
        pad = max(5, int(6 * s))
        h = max(22, int(round(24 * s)))
        gap = max(3, int(round(4 * s)))     # 两键之间的透明间隔：真的是三个按钮

        def _chip_text_w(text: str) -> float:
            """金额栏文本宽：末尾 ₽ 雅黑没有字形，按 Segoe UI Bold 单独量。"""
            body, rub = (text[:-1], "₽") if text.endswith("₽") else (text, "")
            w = dr_len(body, f) if body else 0.0
            if rub:
                w += dr_len(rub, _font("segoeuib", fs)) + fs * 0.10
            return w

        total_w = 0
        if total_label:
            total_w = int(round(_chip_text_w(total_label))) + pad * 2
        gm_w = int(round(dr_len(gamemode_label, f))) + pad * 2 + 6
        basis_w = int(round(dr_len(basis_label, f))) + pad * 2 + 6
        close_w = h
        x = (total_w + gap) if total_w else 0
        w = x + gm_w + gap + basis_w + gap + close_w
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        rect_total = (0, 0, total_w, h) if total_w else None
        rect_gm = (x, 0, x + gm_w, h)
        rect_basis = (x + gm_w + gap, 0, x + gm_w + gap + basis_w, h)
        rect_close = (x + gm_w + gap + basis_w + gap, 0, w, h)
        if rect_total:
            _paint_status_field(img, rect_total)
        for key, rect in (("gamemode", rect_gm), ("basis", rect_basis),
                          ("close", rect_close)):
            state = ("normal" if not member and key in ("gamemode", "basis")
                     else "pressed" if pressed == key
                     else "hover" if hover == key else "normal")
            _paint_xp_button(img, rect, state)
        dr = ImageDraw.Draw(img)
        ink_off = (150, 154, 160, 235)
        ink_on = (24, 24, 24, 245)
        if rect_total:
            # ₽ 用 Segoe UI Bold：雅黑缺少该字形，直接画会变豆腐块
            body, rub = ((total_label[:-1], "₽") if total_label.endswith("₽")
                         else (total_label, ""))
            tx, ty = rect_total[0] + pad, (h - fs) / 2 - 1
            if body:
                dr.text((tx, ty), body, font=f, fill=(28, 34, 44, 245))
                tx += dr.textlength(body, font=f)
            if rub:
                dr.text((tx + fs * 0.10, ty), rub, font=_font("segoeuib", fs),
                        fill=(28, 34, 44, 245))
        tw_gm = dr.textlength(gamemode_label, font=f)
        dr.text((rect_gm[0] + (gm_w - tw_gm) / 2, (h - fs) / 2 - 1), gamemode_label,
                font=f, fill=ink_off if not member else ink_on)
        tw_b = dr.textlength(basis_label, font=f)
        dr.text((rect_basis[0] + (basis_w - tw_b) / 2, (h - fs) / 2 - 1), basis_label,
                font=f, fill=ink_off if not member else ink_on)
        cx = (rect_close[0] + rect_close[2]) / 2
        cy = h / 2
        r = max(3, int(round(h * 0.20)))
        lw = max(1, int(round(1.4 * s)))
        ink = (150, 32, 28, 245) if (hover == "close" or pressed == "close") \
            else (40, 40, 40, 240)
        dr.line([(cx - r, cy - r), (cx + r, cy + r)], fill=ink, width=lw)
        dr.line([(cx - r, cy + r), (cx + r, cy - r)], fill=ink, width=lw)
        return img, rect_gm, rect_basis, rect_close

    def dr_len(text: str, font) -> float:
        from PIL import Image, ImageDraw

        tmp = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
        return tmp.textlength(text, font=font)

    def render_menu(candidates: list, fs: int, current_name: str = "",
                    title: str = "选择口径"):
        """R253：口径选单位图（点浮窗 ? 徽章弹出）。

        XP Luna 弹出菜单风格：白底、Luna 蓝边框、深蓝标题条「选择口径」；
        每行 = 圆点(当前推断口径实心蓝) + 物品名 + 右对齐精确卢布价。
        返回 (位图, 行矩形列表)（菜单客户坐标），供点击命中。
        """
        from PIL import Image, ImageDraw

        fs = max(9, min(48, int(fs)))
        row_h = int(round(fs * 1.7))
        pad = max(6, int(round(fs * 0.55)))
        dot_r = max(2, int(round(fs * 0.16)))
        f = _font("msyh", fs)
        rows = []
        price_ws = []
        for c in candidates or []:
            name = str(c.get("name") or "?")
            price = c.get("price")
            price_txt = fmt_short(price) + ("/发" if c.get("kind") == "loose" else "")
            rows.append((name, price_txt, bool(price)))
            price_ws.append(dr_len(price_txt, f))
        if not rows:
            return None, []
        # 先定菜单宽：名字与价格之间永远留 ≥1.2×字号 的空隙，名字超长则截断
        max_price_w = max(price_ws)
        name_avail = max(60, int(dr_len(".338 Lapua Magnum FMJ", f) * 1.4))
        w = int(max_price_w + name_avail + pad * 2 + dot_r * 2 + 10)
        w = max(w, int(dr_len(title, f)) + pad * 2)
        name_limit = w - 3 - pad * 2 - dot_r * 2 - 8 - max_price_w
        title_h = int(round(fs * 1.5))
        h = title_h + row_h * len(rows) + pad
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        dr = ImageDraw.Draw(img)
        # 阴影 + 白底 + Luna 蓝边
        dr.rounded_rectangle([2, 2, w - 1, h - 1], radius=3,
                             fill=(0, 0, 0, 70))
        dr.rounded_rectangle([0, 0, w - 3, h - 3], radius=3,
                             fill=(255, 255, 255, 252),
                             outline=(122, 150, 214, 255), width=1)
        # 标题条（XP 蓝渐变简化为纯色）
        dr.rounded_rectangle([1, 1, w - 4, title_h], radius=2,
                             fill=(91, 125, 191, 255))
        dr.text((pad, (title_h - fs) // 2 - 1), title,
                font=f, fill=(255, 255, 255, 245))
        rects = []
        y = title_h + pad // 2
        for (name, price_txt, has_price), pw in zip(rows, price_ws):
            rects.append((0, y, w - 3, y + row_h))
            cy = y + row_h // 2
            # 当前推断（price.name）实心蓝点，否则浅灰空心圈
            cur = bool(current_name) and name == current_name
            dot = (58, 110, 200, 255) if cur else (0, 0, 0, 0)
            if cur:
                dr.ellipse([pad, cy - dot_r, pad + dot_r * 2, cy + dot_r], fill=dot)
            else:
                dr.ellipse([pad, cy - dot_r, pad + dot_r * 2, cy + dot_r],
                           outline=(190, 196, 205, 255), width=1)
            tx = pad + dot_r * 2 + 8
            shown = name
            while shown and dr_len(shown, f) > name_limit:
                shown = shown[:-1]
            if shown != name:
                shown = shown[:-1] + "…"
            dr.text((tx, cy - fs * 0.62), shown, font=f, fill=(30, 32, 36, 245))
            px = w - 3 - pad - pw
            if has_price:
                dr.text((px, cy - fs * 0.62), price_txt,
                        font=f, fill=(70, 74, 80, 245))
            else:
                nw = dr_len("无价", f)
                dr.text((w - 3 - pad - nw, cy - fs * 0.62), "无价",
                        font=f, fill=(160, 60, 55, 245))
            y += row_h
        return img, rects


class NativeSelection:
    """R247 · ShareX 式原生选区窗（热键零抓屏、零 HTTP、零浏览器）。

    对照 ShareX `RegionCaptureTransparentWindow`：
      · 常驻预热的**透明命中层**（常量 alpha=1，几乎不可见但整窗可点），
        热键只需 ShowWindow —— 不抓整屏、不上传冻结帧、不等页面轮询；
      · 另一层**只画选区**的小窗口（WS_EX_TRANSPARENT），拖动时每次只重绘
        选区大小的位图（几十 KB），不是整屏 8 MB；
      · 松手后先关窗再抓该区域（ShareX: "caller captures the screen after
        the window closes"），避免把选区边框截进识别图；
      · 预热：`RegionCaptureIntegration.WarmUp()` 同理，宿主启动时就把窗口建好。

    命中层用 LWA_ALPHA=1 而不是 colorkey：colorkey 的透明像素会把鼠标穿透到
    下层窗口，框选就收不到事件了（ShareX 源码注释也点明了这一点）。
    """

    MIN_SIZE = 8

    def __init__(self):
        import overlay

        self._ov = overlay
        self.sw, self.sh = screen_size()
        self.hit = create_overlay_window(3, "EFTScanSelectHit")
        self.frame = create_overlay_window(4, "EFTScanSelectFrame")
        self.hint = create_overlay_window(5, "EFTScanSelectHint")
        _user32.SetWindowPos(ctypes.c_void_p(self.hit), 0, 0, 0, self.sw, self.sh,
                             SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE)
        self._draw_hint()
        # ShareX WarmUp 同理：第一次 UpdateLayeredWindow 要付 GDI/DIB 初始化
        # （实测 130ms），放到宿主启动时预热，热键路径只做 ShowWindow。
        _user32.ShowWindow(ctypes.c_void_p(self.hint), SW_SHOWNOACTIVATE)
        set_layered_bitmap(self.hint, self._hint_img, *self._hint_pos)
        _user32.ShowWindow(ctypes.c_void_p(self.hint), 0)      # SW_HIDE
        self.active = False
        self.fg = None
        self.start = None
        self.rect = None
        self._last_draw = 0.0

    def _make_hint_image(self, text: str):
        from PIL import Image, ImageDraw

        f = _font("msyh", 14)
        w, h = 460, 40
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        dr = ImageDraw.Draw(img)
        dr.rounded_rectangle([0, 0, w - 1, h - 1], radius=6,
                             fill=(16, 18, 22, 225), outline=(105, 182, 225, 210), width=1)
        tw = dr.textlength(text, font=f)
        dr.text(((w - tw) / 2, (h - 18) / 2), text, font=f, fill=(232, 236, 242, 240))
        return img

    def _draw_hint(self):
        self._hint_img = self._make_hint_image(
            "按住左键框选要识别的区域   ·   Esc / 右键取消")
        self._hint_pos = ((self.sw - 460) // 2, 18)

    def show_status(self, text: str) -> None:
        """R248：松手后立刻给「识别中…」反馈（旧链路有页面状态文字，原生版不能没有）。"""
        import ctypes

        img = self._make_hint_image(text)
        _user32.ShowWindow(ctypes.c_void_p(self.hint), SW_SHOWNOACTIVATE)
        set_layered_bitmap(self.hint, img, *self._hint_pos)
        _user32.SetWindowPos(ctypes.c_void_p(self.hint), HWND_TOPMOST, 0, 0, 0, 0,
                             SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

    def hide_status(self) -> None:
        import ctypes

        _user32.ShowWindow(ctypes.c_void_p(self.hint), 0)

    def show(self):
        global _SELECT_ACTIVE

        import ctypes

        self.fg = self._ov.foreground_hwnd()
        self.active = True
        self.start = None
        self.rect = None
        _SELECT_ACTIVE = self
        _user32.ShowWindow(ctypes.c_void_p(self.hit), 5)     # SW_SHOW
        _user32.ShowWindow(ctypes.c_void_p(self.hint), SW_SHOWNOACTIVATE)
        _user32.SetWindowPos(ctypes.c_void_p(self.hit), HWND_TOPMOST, 0, 0, 0, 0,
                             SWP_NOMOVE | SWP_NOSIZE)
        _user32.BringWindowToTop(ctypes.c_void_p(self.hit))
        _user32.SetForegroundWindow(ctypes.c_void_p(self.hit))

    def hide(self):
        global _SELECT_ACTIVE

        import ctypes

        self.active = False
        _SELECT_ACTIVE = None
        for hwnd in (self.frame, self.hint, self.hit):
            _user32.ShowWindow(ctypes.c_void_p(hwnd), 0)     # SW_HIDE
        self._ov.restore_focus(self.fg)

    def cancel(self):
        self.hide()
        _SELECT_RESULTS.append(("cancel", None))

    def on_down(self, x, y):
        self.start = (x, y)
        self.rect = None
        self._redraw(None)

    def on_move(self, x, y):
        if self.start is None:
            return
        x0, y0 = self.start
        rect = (min(x0, x), min(y0, y), abs(x - x0), abs(y - y0))
        if rect == self.rect:
            return
        self.rect = rect
        now = time.monotonic()
        if now - self._last_draw < 0.008:       # ~120fps 上限，防大选区全屏重绘卡顿
            return
        self._last_draw = now
        self._redraw(rect)

    def on_up(self, x, y):
        if self.start is None:
            return
        x0, y0 = self.start
        rect = (min(x0, x), min(y0, y), abs(x - x0), abs(y - y0))
        self.start = None
        self.hide()
        if rect[2] >= self.MIN_SIZE and rect[3] >= self.MIN_SIZE:
            _SELECT_RESULTS.append(("done", rect))
        else:
            _SELECT_RESULTS.append(("cancel", None))

    def _redraw(self, rect):
        import ctypes

        if rect is None or rect[2] < 2 or rect[3] < 2:
            _user32.ShowWindow(ctypes.c_void_p(self.frame), 0)
            return
        from PIL import Image, ImageDraw

        x, y, w, h = rect
        pad = 2
        W, H = w + pad * 2, h + pad * 2
        W = min(W, self.sw)
        H = min(H, self.sh)
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        dr = ImageDraw.Draw(img)
        box = [pad, pad, W - pad - 1, H - pad - 1]
        dr.rectangle(box, fill=(105, 182, 225, 20))
        dr.rectangle(box, outline=(255, 255, 255, 240), width=2)
        # 黑色虚线（ShareX：白实线 + 黑虚线，物理像素宽，任何背景都看得清）
        for i in range(box[0], box[2], 11):
            dr.line([(i, box[1]), (min(i + 6, box[2]), box[1])], fill=(0, 0, 0, 210))
            dr.line([(i, box[3]), (min(i + 6, box[2]), box[3])], fill=(0, 0, 0, 210))
        for j in range(box[1], box[3], 11):
            dr.line([(box[0], j), (box[0], min(j + 6, box[3]))], fill=(0, 0, 0, 210))
            dr.line([(box[2], j), (box[2], min(j + 6, box[3]))], fill=(0, 0, 0, 210))
        label = "%d × %d" % (w, h)
        f = _font("msyhbd", 12)
        tw = dr.textlength(label, font=f)
        ly = box[1] + 4 if h < 44 else box[1] + 4
        dr.rounded_rectangle([box[0] + 4, ly - 2, box[0] + 12 + tw, ly + 17],
                             radius=3, fill=(16, 18, 22, 210))
        dr.text((box[0] + 8, ly), label, font=f, fill=(240, 240, 236, 240))
        _user32.ShowWindow(ctypes.c_void_p(self.frame), SW_SHOWNOACTIVATE)
        set_layered_bitmap(self.frame, img, max(0, x - pad), max(0, y - pad))
        _user32.SetWindowPos(ctypes.c_void_p(self.frame), HWND_TOPMOST, 0, 0, 0, 0,
                             SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)


class OverlaySession:
    """一组透明浮窗（标签窗 + 控制条窗）。

    标签窗全窗点击穿透（WS_EX_TRANSPARENT + WM_NCHITTEST 双保险），价格文字直接
    叠在装备上；控制条是**两个分开的 XP Luna 按钮**（口径切换 / 关闭），整组压在
    框选区顶边上方 1px，只有按钮区可点且不抢焦点。口径循环纯本地重绘，不经过 BFF。
    """

    def __init__(self, region: dict, matches: list, config_dir: str | None = None,
                 server: str | None = None, game_idx: int = 0,
                 on_gamemode=None):
        if not IS_WINDOWS:
            raise RuntimeError("仅支持 Windows")
        self.region = dict(region)
        self.matches = list(matches or [])
        self.mode_idx = 0
        self._config_dir = config_dir
        self._server = server
        self.game_idx = int(game_idx) if isinstance(game_idx, int) else 0
        self.on_gamemode = on_gamemode       # R256：点击「切换模式」时回调（触发重新识别）
        self.labels_hwnd = create_overlay_window(0)
        self.ctrl_hwnd = create_overlay_window(1)
        self.menu_hwnd = create_overlay_window(6)   # R253 口径选单
        self.btn_gamemode = None
        self.btn_basis = None
        self.btn_close = None
        self._rect = None
        self._ctrl_pos = (0, 0)
        self._hover = None                   # R249：XP 按钮 hover / pressed 态
        self._pressed = None
        self._tracking = False
        self._badge_tracking = False        # 悬停定时器用的 TrackMouseEvent 武装状态
        self.badges: list = []               # R253：[(match_idx, 徽章矩形画布坐标)]
        self.menu_for: int | None = None     # 打开选单的 match 序号
        self.menu_rows: list = []            # 选单行矩形（菜单窗客户坐标）
        self.menu_pinned = False             # True=点击打开（常驻）；False=悬停打开（自动收起）
        # R256：会员态**只认 BFF 的权威快照**（宿主进程读不到本机内存里的会员态）。
        # 启动时拉一次；拉不到按本机 config 兜底；仍失败=非会员（按钮灰）。
        self.member = fetch_member_state(server, config_dir)
        sw, sh = screen_size()
        self.ui_scale = max(1.0, min(2.0, sh / 1080.0))
        global _ACTIVE
        _ACTIVE = self

    def show(self) -> None:
        self._redraw()

    def cycle(self) -> None:
        self.mode_idx = (self.mode_idx + 1) % len(PRICE_MODES)
        self.close_menu()                     # 口径切换时收起选单，避免位置漂移
        self._redraw()

    @property
    def game_mode_code(self) -> str:
        return GAME_MODES[self.game_idx % len(GAME_MODES)][0]

    @property
    def game_mode_label(self) -> str:
        return GAME_MODES[self.game_idx % len(GAME_MODES)][1]

    def cycle_game_mode(self) -> None:
        """R256：点「切换模式」→ 循环 PvP/PvE/PvPS，立即更新按钮文案，
        再回调让宿主用新模式重识别同一区域（价格按新模式取）。"""
        self.game_idx = (self.game_idx + 1) % len(GAME_MODES)
        self._redraw()
        cb = self.on_gamemode
        if callable(cb):
            try:
                cb(self.game_mode_code)
            except Exception as exc:  # noqa: BLE001
                log_exc("切换模式回调失败", exc)

    @property
    def mode_label(self) -> str:
        return PRICE_MODES[self.mode_idx][1]

    def total_value_text(self) -> str:
        """控制条上的「总价值」：本次识别所有装备当前显示价之和。

        口径与浮窗价格严格同源（price_base，散装弹已是整堆价）。
        只画 ? 的歧义物品没有可靠价，不计入并被标成 ≈（总额只是已知下限）。
        """
        key = PRICE_MODES[self.mode_idx][0]
        total = 0.0
        has = False
        partial = False
        for m in self.matches:
            if is_ambig_price(m):
                partial = True
                continue
            base = price_base(m, key)
            if (isinstance(base, (int, float)) and not isinstance(base, bool)
                    and math.isfinite(base) and base > 0):
                total += float(base)
                has = True
            else:
                partial = True
        amount = fmt_short(total if has else 0)
        return "总价值 " + ("≈ " if (has and partial) else "") + amount

    def hit_button(self, x: int, y: int) -> str | None:
        """客户坐标落在哪个 XP 按钮上（键之间的透明间隔不响应点击）。"""
        for key, rect in (("gamemode", self.btn_gamemode), ("basis", self.btn_basis),
                          ("close", self.btn_close)):
            if rect and rect[0] <= x < rect[2] and rect[1] <= y < rect[3]:
                return key
        return None

    # ---- R253：? 徽章点击 → 口径选单 ----

    def hit_badge(self, x: int, y: int) -> int | None:
        """标签窗客户坐标命中哪个 ? 徽章 → match 序号；没命中 → None。"""
        for idx, rect in self.badges:
            x0, y0, x1, y1 = rect
            if x0 <= x < x1 and y0 <= y < y1:
                return idx
        return None

    def toggle_menu(self, idx: int) -> None:
        """点击徽章：悬停已打开的先钉住（而不是关掉），钉住后再点才关闭。"""
        if self.menu_for == idx and self.menu_pinned:
            self.close_menu()
        else:
            self.open_menu(idx)

    def open_menu(self, idx: int, capture: bool = True) -> None:
        m = self.matches[idx] if 0 <= idx < len(self.matches) else None
        p = (m or {}).get("price") or {}
        cands = ambig_candidates(m)
        if not cands:
            return
        # 菜单字号与识别标签字号解耦：标签行高跟随游戏截图分辨率（1080p/2K 下可达 40+），
        # 沿用它会让 10 个候选撑出接近整屏的弹窗。菜单按屏幕与候选数自适应，
        # 上限 16px；仍放不下就继续缩字号，但不裁剪候选（行号要与 cands 一一对应）。
        sw, sh = screen_size()
        fs = max(10, min(16, int(round(13 * self.ui_scale))))
        item_hit = bool((m or {}).get("ambiguous")) and not p.get("ambiguous")
        title = "选择物品" if item_hit else "选择口径"
        current = p.get("name") or (m or {}).get("name") or ""
        img, rows = render_menu(cands, fs, current, title)
        for _ in range(8):
            if img is None:
                return
            if img.size[0] <= sw * 0.55 and img.size[1] <= sh * 0.65:
                break
            nxt = max(9, int(fs * 0.85))
            if nxt == fs:
                break
            fs = nxt
            img, rows = render_menu(cands, fs, current, title)
        if img is None:
            return
        self.menu_rows = rows
        self.menu_for = idx
        self.menu_pinned = bool(capture)
        if self.menu_pinned:
            # 点击打开的菜单常驻，先撤掉悬停链路上可能挂着的收起定时器
            try:
                _user32.KillTimer(self.labels_hwnd, 7)
            except Exception:
                pass
        rx, ry = self._rect[0], self._rect[1] if self._rect else (0, 0)
        px, py = rx, ry
        for i, rect in self.badges:            # 菜单弹在徽章右下角
            if i == idx:
                px, py = rx + rect[2] + 4, ry + rect[3] + 4
                break
        px = max(0, min(px, sw - img.size[0] - 2))
        py = max(0, min(py, sh - img.size[1] - 2))
        set_layered_bitmap(self.menu_hwnd, img, px, py)
        _user32.ShowWindow(self.menu_hwnd, SW_SHOWNOACTIVATE)
        _topmost(self.menu_hwnd)
        if capture:
            _user32.SetCapture(ctypes.c_void_p(self.menu_hwnd))   # 点菜单外 → 收到全屏按下
        else:
            # R256：悬停弹窗——不捕获鼠标，靠标签窗/菜单窗的 WM_MOUSELEAVE 定时收起
            try:
                tme = TRACKMOUSEEVENT(ctypes.sizeof(TRACKMOUSEEVENT), TME_LEAVE,
                                      self.menu_hwnd, 0)
                _user32.TrackMouseEvent(ctypes.byref(tme))
            except Exception:
                pass

    def menu_click(self, x: int, y: int) -> None:
        """选单窗客户坐标的按下：行内 → 选口径；行外 → 关闭。"""
        row = next((i for i, r in enumerate(self.menu_rows)
                    if r[0] <= x < r[2] and r[1] <= y < r[3]), None)
        if row is None or self.menu_for is None:
            self.close_menu()
            return
        self.pick_candidate(self.menu_for, row)

    def pick_candidate(self, idx: int, row: int) -> None:
        m = self.matches[idx] if 0 <= idx < len(self.matches) else None
        cands = ambig_candidates(m)
        if not (m and 0 <= row < len(cands)):
            self.close_menu()
            return
        c = cands[row]
        p = m["price"]
        # 手动选择后固定显示所选价（price_base 优先 manual），徽章保留可重选
        p["manual"] = c.get("price")
        p["manualName"] = c.get("name")
        self.close_menu()
        self._redraw()

    def close_menu(self) -> None:
        if self.menu_for is None:
            return
        self.menu_for = None
        self.menu_rows = []
        self.menu_pinned = False
        _user32.ReleaseCapture()
        _user32.ShowWindow(self.menu_hwnd, SW_HIDE)

    def set_hover(self, key: str | None) -> None:
        if key == self._hover:
            return
        self._hover = key
        self._refresh_control()

    def set_pressed(self, key: str | None) -> None:
        if key == self._pressed:
            return
        self._pressed = key
        self._refresh_control()

    def _refresh_control(self) -> None:
        """只重绘控制条（hover/pressed 反馈），不碰价格标签位图。"""
        if not self._rect:
            return
        sw, sh = screen_size()
        self._place_control(*self._rect, sw, sh)

    def _place_control(self, rx: int, ry: int, rw: int, rh: int,
                       sw: int, sh: int) -> None:
        ctrl, rect_gm, rect_basis, rect_close = render_control(
            self.game_mode_label, self.mode_label, self.ui_scale,
            self._hover, self._pressed, member=self.member,
            total_label=self.total_value_text())
        self.btn_gamemode = rect_gm
        self.btn_basis = rect_basis
        self.btn_close = rect_close
        cw, ch = ctrl.size
        # R249：底边贴着框选区顶边上方 1px（cy + ch == ry - 1），不再压住价格。
        cx, cy = control_position(rx, ry, rw, rh, cw, ch, sw, sh)
        self._ctrl_pos = (cx, cy)
        set_layered_bitmap(self.ctrl_hwnd, ctrl, cx, cy)

    def close(self) -> None:
        self.close_menu()
        for hwnd in (self.labels_hwnd, self.ctrl_hwnd, self.menu_hwnd):
            try:
                _user32.DestroyWindow(hwnd)
            except Exception:
                pass
        global _ACTIVE
        if _ACTIVE is self:
            _ACTIVE = None

    def dead(self) -> bool:
        import overlay as _ov

        return not (_ov.is_alive(self.labels_hwnd) and _ov.is_alive(self.ctrl_hwnd)
                    and _ov.is_alive(self.menu_hwnd))

    def _redraw(self) -> None:
        sw, sh = screen_size()
        rx = max(0, min(int(self.region["x"]), sw - 16))
        ry = max(0, min(int(self.region["y"]), sh - 16))
        rw = max(16, min(int(self.region["w"]), sw - rx))
        rh = max(16, min(int(self.region["h"]), sh - ry))
        self._rect = (rx, ry, rw, rh)
        # 框选区贴近屏幕下沿时，价格仍要画在名字下方——画布向下多留 2.5 行（不超出屏幕）
        extra = int(label_base_font(self.matches) * 2.6) + 10
        extra = max(0, min(extra, sh - (ry + rh), 600))
        badges: list = []
        labels = render_labels(rw, rh, self.matches, PRICE_MODES[self.mode_idx][0],
                               load_label_tiers(self._config_dir, member=self.member),
                               extra_bottom=extra,
                               badges_out=badges,
                               tier_basis=load_tier_basis(self._config_dir))
        self.badges = badges                  # R253：? 徽章命中区随位图更新
        set_layered_bitmap(self.labels_hwnd, labels, rx, ry)
        self._place_control(rx, ry, rw, rh, sw, sh)
        for hwnd in (self.labels_hwnd, self.ctrl_hwnd):
            _user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
            _topmost(hwnd)
        # R285：重绘会把标签窗/控制条重新提到 TOPMOST 顶部，压住同为 TOPMOST 的
        # 选单窗；此时点击落在标签窗非徽章区（HTTRANSPARENT）会直接穿透到游戏，
        # 表现为「候选框看得到却点不了」。菜单显示期间每次重绘后都重新置顶。
        if self.menu_for is not None:
            _user32.ShowWindow(self.menu_hwnd, SW_SHOWNOACTIVATE)
            _topmost(self.menu_hwnd)


def scan_profile_dir(profile_dir: str | None = None) -> str:
    """扫描宿主专用的浏览器配置目录（独立 profile，避免污染用户日常浏览器）。"""
    return profile_dir or os.path.join(
        os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "EFTMap", "scan-profile")


BROWSER_PID_PATH = os.path.join(BUILD_DIR, "scan-browser.pid")


def _terminate_pid(pid: int) -> bool:
    """结束指定进程（纯 kernel32 调用，不启动任何子进程）。"""
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.windll.kernel32
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    k32.TerminateProcess.restype = wintypes.BOOL
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    PROCESS_TERMINATE = 0x0001
    h = k32.OpenProcess(PROCESS_TERMINATE, False, int(pid))
    if not h:
        return False
    try:
        return bool(k32.TerminateProcess(h, 1))
    finally:
        k32.CloseHandle(h)


def _image_name(pid: int) -> str:
    """进程可执行文件名（小写）。取不到返回空串——用于防止 PID 复用误杀。"""
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.windll.kernel32
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                               wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        if not k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return ""
        return os.path.basename(buf.value).lower()
    finally:
        k32.CloseHandle(h)


def kill_stale_scan_browsers() -> int:
    """结束旧的扫描浏览器进程（窗口标题命中 + 上次启动记录的 PID）。

    R245 用 PowerShell 按命令行过滤，但 pythonw 没有控制台——**每次热键都会先弹一个
    PowerShell 黑窗**再出截图（用户实测），且 PowerShell 自身要 ~1s 启动。
    R246 改为纯 ctypes：`overlay._enum_windows()` 拿窗口 PID + 读 `scan-browser.pid`，
    再用 `TerminateProcess` 结束；毫秒级、无窗口、无子进程。

    只杀 msedge.exe / chrome.exe（按可执行名二次校验，防 PID 复用时误杀），
    绝不按映像名扫射（R240.1 曾用 `taskkill /IM pythonw.exe` 误杀 BFF）。
    """
    import overlay

    titles = {SCAN_TITLE, SCAN_TITLE_DONE, SCAN_TITLE_CLOSED}
    pids = {pid for _h, pid, t in overlay._enum_windows() if t in titles and pid}
    try:
        with open(BROWSER_PID_PATH, "r", encoding="utf-8") as f:
            saved = int((f.read() or "0").strip() or 0)
        if saved > 0:
            pids.add(saved)
    except (OSError, ValueError):
        pass
    me = os.getpid()
    killed = 0
    for pid in pids:
        if pid == me:
            continue
        name = _image_name(pid)
        if not (name.endswith("msedge.exe") or name.endswith("chrome.exe")):
            continue                      # PID 被复用／不是浏览器 → 绝不误杀
        if _terminate_pid(pid):
            killed += 1
    if killed:
        time.sleep(0.25)                  # 等窗口销毁 / profile 锁释放
        try:
            os.remove(BROWSER_PID_PATH)
        except OSError:
            pass
    return killed


def launch_scan_window(server: str, frame_id: str, mode: str, profile_dir: str | None = None):
    """冷启动：全屏无边框浏览器窗口加载 scan.html。返回 (proc, hwnd)。

    R240 防闪动：窗口在 **-32000 屏幕外**创建，剥标题栏、等页面、定位、客户区
    补偿全部在屏幕外完成，就绪后才一次性移入屏幕——用户永远看不到
    「带标题栏 → 剥掉 → 挪位置」的过程（R238 的「窗口动一下」就是它）。
    （若浏览器把 -32000 钳回可见区，只是退回旧行为，不更糟。）
    """
    import ctypes
    import overlay

    url = ("%s/scan.html?frame=%s&mode=%s"
           % (server.rstrip("/"), frame_id, mode))
    found = overlay.find_browser()
    if not found:
        raise RuntimeError("没找到 Edge 或 Chrome（可用环境变量 EDGE_PATH 指定 msedge.exe）")
    _name, exe = found
    sw, sh = screen_size()
    profile = scan_profile_dir(profile_dir)
    os.makedirs(profile, exist_ok=True)
    cmd = [
        exe,
        "--app=%s" % url,
        "--window-size=%d,%d" % (sw, sh),
        "--window-position=-32000,-32000",
        "--user-data-dir=%s" % profile,
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-extensions",
        "--autoplay-policy=no-user-gesture-required",
        # R245：保温窗口不能「暂停合成」——否则隐藏后唤醒是白屏，要点击才重绘。
        # 关掉 Windows 遮挡检测 / 后台渲染降级 / 后台定时器节流（页面靠定时器轮询换帧）。
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        "--disable-background-timer-throttling",
        "--disable-features=Translate,MediaRouter,CalculateNativeWinOcclusion,"
        "CalculateNativeWinOcclusionOnShow",
    ]
    before = {h for h, _p, _t in overlay._enum_windows()}
    proc = __import__("subprocess").Popen(cmd)  # noqa: S603 - 参数全部来自本脚本
    # 记录本次启动的浏览器 PID：下次冷启动/宿主重启时按 PID 精准收掉（不扫射进程名）
    try:
        with open(BROWSER_PID_PATH, "w", encoding="utf-8") as f:
            f.write(str(proc.pid))
    except OSError:
        pass
    hwnd = overlay.wait_new_window(before, timeout=15.0)
    if hwnd is None:
        proc.terminate()
        raise RuntimeError("截图窗口没在超时时间内出现")
    overlay.style_overlay(hwnd, click_through=False)   # 窗口还在屏幕外，剥样式无感
    # R245：style_overlay 会加 WS_EX_NOACTIVATE（小地图等被动 HUD 需要），但**框选窗
    # 必须能拿键盘**（Esc 取消）与激活——否则 Chromium 视窗口为未激活，隐藏后唤醒
    # 不产出首帧（白屏，点一下才重绘），Esc 也永远收不到。
    _user32.GetWindowLongW.restype = ctypes.c_long
    ex = _user32.GetWindowLongW(ctypes.c_void_p(hwnd), -20) & 0xFFFFFFFF
    _user32.SetWindowLongW(ctypes.c_void_p(hwnd), -20, ex & ~WS_EX_NOACTIVATE)
    _user32.SetWindowPos(ctypes.c_void_p(hwnd), 0, 0, 0, 0, 0,
                         0x0027)   # NOMOVE|NOSIZE|NOZORDER|FRAMECHANGED
    if overlay.wait_window(0, timeout=15.0, title=SCAN_TITLE) is None:
        raise RuntimeError("scan.html 没加载出来（标题没变成「%s」）" % SCAN_TITLE)
    time.sleep(0.5)
    # 屏幕外完成尺寸与客户区补偿（top-left 锚在 -32000，窗口不出现在用户面前）
    overlay.move_window(hwnd, (-32000, -32000, sw, sh))
    time.sleep(0.3)
    overlay.fit_client(hwnd, (-32000, -32000, sw, sh), corner="top-left")
    time.sleep(0.2)
    # 入场：样式/位置/尺寸全部就绪，一次性出现（并激活——框选要吃键盘 Esc）
    overlay.move_window(hwnd, (0, 0, sw, sh))
    ctypes.windll.user32.SetWindowPos(ctypes.c_void_p(hwnd), -1, 0, 0, 0, 0, 0x0043)
    ctypes.windll.user32.BringWindowToTop(ctypes.c_void_p(hwnd))
    ctypes.windll.user32.SetForegroundWindow(ctypes.c_void_p(hwnd))
    return proc, hwnd


def show_selection(hwnd):
    """唤醒保温的选择窗：显示 + 置顶 + 激活（框选要吃键盘 Esc 与鼠标）。

    R245：隐藏期间 Chromium 会判定窗口「被遮挡」而暂停合成，唤醒后首帧可能是
    **白屏**，要有鼠标事件才重绘。这里显示后立刻强制一次重绘并等 DWM 提交，
    配合浏览器启动参数里的关遮挡/关后台节流（见 launch_scan_window）根治。
    """
    import ctypes

    user32 = ctypes.windll.user32
    user32.ShowWindow(ctypes.c_void_p(hwnd), 5)              # SW_SHOW
    user32.SetWindowPos(ctypes.c_void_p(hwnd), -1, 0, 0, 0, 0, 0x0043)  # TOPMOST|激活
    # R245：必须真正成为前台窗口——否则 Chromium 视其为未激活，隐藏后唤醒不出首帧
    # （白屏，点一下才重绘），页面也收不到 Esc。热键刚刚由本进程接收，通常有权置前。
    user32.BringWindowToTop(ctypes.c_void_p(hwnd))
    user32.SetForegroundWindow(ctypes.c_void_p(hwnd))
    # RDW_INVALIDATE|RDW_ERASE|RDW_FRAME|RDW_ALLCHILDREN|RDW_UPDATENOW
    user32.RedrawWindow(ctypes.c_void_p(hwnd), None, None, 0x0001 | 0x0004 | 0x0400 | 0x0080 | 0x0100)
    try:
        ctypes.windll.dwmapi.DwmFlush()
    except Exception:
        pass


def hide_selection(hwnd, fg=None):
    """隐藏选择窗（R240 保温：不销毁浏览器进程，下次热键直接唤醒）并还焦点给游戏。

    R245：隐藏前把窗口标题复位成中性标题——页面自己要到 visibilitychange 才复位，
    宿主 150ms 轮询可能先读到上一轮的「完成/关闭」而误判（用户看到的「闪一下白」）。
    """
    import ctypes
    import overlay

    try:
        ctypes.windll.user32.SetWindowTextW(ctypes.c_void_p(hwnd), SCAN_TITLE)
    except Exception:  # noqa: BLE001 - 标题复位失败不该阻断收窗
        pass
    ctypes.windll.user32.ShowWindow(ctypes.c_void_p(hwnd), 0)   # SW_HIDE
    overlay.restore_focus(fg)


def watch(server: str, hotkey, config_dir: str | None):
    """常驻循环（R240 保温版）。

    热键 → 冻结帧(BMP)上传 → 唤醒/冷启动选择窗（页面轮询新帧 ≤150ms 换上）；
    「完成」→ 隐藏选择窗（保温，不销毁）→ 开透明浮窗；「关闭」（取消）→ 隐藏保温。
    下一热键直接复用窗口——不再拉起浏览器，QQ 式速度。

    R239 注意：循环必须 DispatchMessage——原生浮窗的 WndProc（点击命中/按钮）
    依赖消息派发；WM_HOTKEY 的处理保持原语义。
    """
    import ctypes
    from ctypes import wintypes

    import overlay

    user32 = ctypes.windll.user32
    registered = False
    if hotkey:
        mod, vk = hotkey
        registered = bool(user32.RegisterHotKey(None, 1, mod, vk))
        if not registered:
            log("热键注册失败（err=%d，可能被其他程序占用）——按键不会有任何反应" % _kernel32.GetLastError())
        else:
            log("热键注册成功（id=1）")
    else:
        log("热键未配置（off），仅保留常驻")
    warm: dict | None = None      # {"hwnd", "fg", "shown_at", "phase"}
    sess: OverlaySession | None = None
    current_hk = hotkey           # 当前已注册的热键 (mod, vk) / None=off
    hk_text = None                # 当前生效热键的配置文本（防同键重复注册）
    hk_next_check = time.time() + 1.0
    msg = wintypes.MSG()
    user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                                    wintypes.UINT, wintypes.UINT, wintypes.UINT]
    user32.PeekMessageW.restype = wintypes.BOOL
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
    log("就绪：按热键框选识别；结果以透明浮窗叠在装备上（✕ 或再按热键关闭）")
    while True:
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            if msg.message == 0x0312:   # WM_HOTKEY
                if sess is not None:
                    sess.close()
                    sess = None
                    log("浮窗已关闭")
                try:
                    frame = grab_frame()
                    fid = post_frame(server, frame)
                    mode = current_mode(config_dir)
                    if warm is not None and overlay.is_alive(warm["hwnd"]):
                        # 保温路径：帧先上传再唤醒——页面可见后 ≤150ms 换帧，无冷启动
                        warm["shown_at"] = time.time()
                        warm["phase"] = "selecting"
                        warm["done_stale"] = False     # 重新武装完成信号
                        warm["closed_stale"] = False   # 重新武装关闭信号（防残留标题）
                        show_selection(warm["hwnd"])
                        log("选择窗已唤醒（frame=%s，mode=%s）" % (fid, mode))
                    else:
                        # 冷启动前清掉残留的旧浏览器进程——否则 Edge 单实例会把窗口
                        # 塞进旧进程，新启动参数（关遮挡/关节流）不生效 → 白屏
                        killed = kill_stale_scan_browsers()
                        if killed:
                            log("冷启动前清理旧的扫描浏览器进程 %d 个" % killed)
                        fg = overlay.foreground_hwnd()   # 记下游戏，收场时还焦点
                        _proc, hwnd = launch_scan_window(server, fid, mode)
                        warm = {"hwnd": hwnd, "fg": fg,
                                "shown_at": time.time(), "phase": "selecting",
                                "done_stale": False, "closed_stale": False}
                        log("选择窗已打开（frame=%s，mode=%s）" % (fid, mode))
                except Exception as exc:  # noqa: BLE001 - 单次失败不退出常驻
                    log_exc("启动选择失败", exc)
                    # R279：给用户一个可见出口，别让「按了热键没反应」变成哑谜。
                    notify_failure("%s: %s" % (type(exc).__name__, exc))
                    if warm is not None and not overlay.is_alive(warm["hwnd"]):
                        warm = None
            user32.DispatchMessageW(ctypes.byref(msg))
        if warm is not None:
            hwnd = warm["hwnd"]
            if not overlay.is_alive(hwnd):
                warm = None
            elif warm.get("phase") == "selecting":
                # 页面把标题改成「关闭」= 用户取消；「完成」= 交接成功切浮窗
                buf = ctypes.create_unicode_buffer(64)
                user32.GetWindowTextW(hwnd, buf, 64)
                title = buf.value
                if title == SCAN_TITLE_CLOSED:
                    # 唤醒瞬间页面标题可能还残留上一轮的「关闭」——页面要等
                    # visibilitychange 才复位标题，比宿主 150ms 轮询晚。若立刻执行，
                    # 窗口刚显示就被隐藏（用户看到的就是「闪一下白」）。因此要求
                    # 连续两次轮询都读到「关闭」才真的收窗。
                    if warm.get("closed_stale"):
                        hide_selection(hwnd, warm.get("fg"))
                        warm["phase"] = "idle"
                        warm["closed_stale"] = False
                        log("选择已取消，窗口保温待下次热键")
                    else:
                        warm["closed_stale"] = True
                elif title == SCAN_TITLE_DONE:
                    if warm.get("done_stale"):
                        pass  # 残留完成信号已忽略过一次，等页面把标题复位（防重复取态刷屏）
                    else:
                        state = fetch_state(server)
                        # ts 守卫：重开窗口瞬间可能读到上一轮残留的「完成」标题
                        fresh = bool(state) and (state.get("ts") or 0) >= warm.get("shown_at", 0) - 0.5
                        if not fresh:
                            warm["done_stale"] = True
                            log("完成信号为上一轮残留，忽略（页面即将复位标题）")
                        else:
                            hide_selection(hwnd, warm.get("fg"))
                            warm["phase"] = "idle"
                            matches = state.get("matches") or []
                            region = state.get("region")
                            log("交接成功：%d 件，区域 %s" % (len(matches), region))
                            if region and matches:
                                try:
                                    sess = OverlaySession(region, matches, config_dir, server=server)
                                    sess.show()
                                    log("透明浮窗已显示 %d 件（✕ 或热键关闭；口径键循环切换）"
                                        % len(matches))
                                except Exception as exc:  # noqa: BLE001
                                    log_exc("浮窗创建失败", exc)
                            else:
                                log("没有识别到物品")
                else:
                    warm["done_stale"] = False   # 标题已复位，重新武装完成信号
                    warm["closed_stale"] = False  # 同理重新武装「关闭」信号
        elif sess is not None and sess.dead():
            sess = None
            log("浮窗已关闭，回到等待")
        # R241 热键热更新：设置面板改截图键后 ≤1s 生效，不用重启宿主
        if time.time() >= hk_next_check:
            hk_next_check = time.time() + 1.0
            try:
                import config as _cfg

                text = str((_cfg.load(config_dir).get("ocrScan") or {})
                           .get("hotkey") or "").strip().lower()
            except Exception:
                text = None
            if text and text != hk_text:
                parsed = None
                if text not in ("off", "none", "no"):
                    parsed = overlay.parse_hotkey(text)
                    if parsed and not hotkey_requires_mod(parsed):
                        # R254：单键全局热键会吞游戏按键（真实事故），拒绝注册
                        log("热键 %s 没有修饰键，已拒绝（请用 Ctrl/Alt/Shift + 键）" % text)
                        parsed = "invalid"
                if text in ("off", "none", "no") or parsed not in (None, "invalid"):
                    hk_text = text
                    new_hk = None if parsed == "invalid" else parsed
                    if new_hk != current_hk:
                        if current_hk is not None:
                            user32.UnregisterHotKey(None, 1)
                        ok = True
                        if new_hk is not None:
                            mod, vk = new_hk
                            ok = bool(user32.RegisterHotKey(None, 1, mod, vk))
                        if ok:
                            current_hk = new_hk
                            log("热键已切换为 %s（即时生效）" % text)
                        else:
                            if current_hk is not None:
                                mod, vk = current_hk
                                user32.RegisterHotKey(None, 1, mod, vk)
                            log("热键 %s 注册失败（可能被占用），保留原热键" % text)
        time.sleep(0.15)


def fetch_member_state(server: str, config_dir: str | None) -> bool:
    """R256：截图宿主是独立进程，读不到 BFF 进程的会员快照（那个快照只由
    tools/cloud.py 在 BFF 进程内写入）。这里改为直接问 BFF 的 `/api/member`，
    拿到权威会员态。拿不到/异常一律按非会员降级（按钮灰），绝不让永久会员被误判。

    本地 `config.is_member` 作兜底：万一 BFF 没起来但本机确实配置过会员，也不至于全灰。
    """
    try:
        import config as _cfg
        local = bool(_cfg.is_member(config_dir))
    except Exception:
        local = False
    if not server:
        return local
    try:
        import json
        import urllib.request

        url = server.rstrip("/") + "/api/member"
        req = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
        op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with op.open(req, timeout=5) as r:
            d = json.loads(r.read().decode("utf-8"))
        if isinstance(d, dict) and d.get("member") is True:
            return True
    except Exception as exc:  # noqa: BLE001
        log("拉取会员态失败，降级用本机配置：%s" % exc)
    return local


def recognize_region(server: str, rect: tuple, mode: str, config_dir: str | None):
    """ShareX 式：选区窗关闭后**才**抓这一小块，直接送 OCR，不经冻结帧/浏览器。

    返回 (matches, region)。整屏 6 MB 的帧上传与二次下载全部省掉——只传选区 PNG。
    """
    import base64
    import io
    import json
    import urllib.request

    from PIL import ImageGrab

    x, y, w, h = rect
    try:
        ctypes.windll.dwmapi.DwmFlush()      # 等选区边框从 DWM 合成里消失
    except Exception:
        pass
    time.sleep(0.03)
    img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    body = json.dumps({"image": "data:image/png;base64," +
                                base64.b64encode(buf.getvalue()).decode(),
                       "annotate": False, "mode": mode}).encode()
    req = urllib.request.Request(server.rstrip("/") + "/api/ocr/recognize", data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with op.open(req, timeout=180) as r:
        d = json.loads(r.read().decode("utf-8"))
    if not d.get("ok", True):
        raise RuntimeError(str(d.get("error") or d.get("hint") or "识别失败"))
    matches = d.get("matches") or []
    # R261 调试：出现「散装弹没对上数量」时，把该次原始 lines + matches 落盘，
    # 供离线精确校准 _ocr_ammo_count 的对齐几何（build/ocr-debug.json 每次覆盖）。
    try:
        need = any((m.get("price") or {}).get("ammoStack")
                   and (m.get("price") or {}).get("qtyFound") is False for m in matches)
        if need and d.get("lines"):
            os.makedirs(os.path.join(ROOT, "build"), exist_ok=True)
            with open(os.path.join(ROOT, "build", "ocr-debug.json"),
                      "w", encoding="utf-8") as fh:
                json.dump({"rect": [x, y, w, h], "lines": d.get("lines"),
                           "matches": matches}, fh, ensure_ascii=False, indent=1)
    except Exception:
        pass
    return matches, {"x": x, "y": y, "w": w, "h": h}


def full_screen(config_dir: str | None) -> bool:
    """R255：设置面板「全屏识别」勾选态（每次热键按下现读，改动即时生效）。"""
    try:
        import config as _cfg

        return bool((_cfg.load(config_dir).get("ocrScan") or {}).get("fullScreen"))
    except Exception:
        return False


def _full_screen_worker(server: str, mode: str, config_dir: str | None,
                        results: list, recognizing: dict) -> None:
    """R255 全屏识别：不弹选区，抓整个屏幕进同一条 recognize_region 管线。"""
    try:
        sw, sh = screen_size()
        matches, region = recognize_region(server, (0, 0, sw, sh), mode, config_dir)
        results.append((matches, region, None))
    except Exception as exc:  # noqa: BLE001
        results.append(([], (0, 0, 0, 0), "%s: %s" % (type(exc).__name__, exc)))


def watch_native(server: str, hotkey, config_dir: str | None):
    """R247 常驻循环：热键 → 预热选区窗（<10ms）→ 松手抓选区 → OCR → 透明价格浮窗。

    完全不碰浏览器、不抓整屏、不传冻结帧、不轮询标题——ShareX 的速度。
    R248：识别放后台线程 + 立即显示「识别中」提示，避免长任务期间界面无响应、
    用户反复按热键把刚出现的浮窗关掉。
    """
    import ctypes
    import threading
    from ctypes import wintypes

    import overlay

    user32 = ctypes.windll.user32
    if hotkey:
        mod, vk = hotkey
        if not user32.RegisterHotKey(None, 1, mod, vk):
            log("热键注册失败（err=%d，可能被其他程序占用）" % _kernel32.GetLastError())
        else:
            log("热键注册成功（id=1）")
    else:
        log("热键未配置（off），仅保留常驻")

    sel = NativeSelection()                  # ShareX WarmUp：窗口先建好，热键零冷启动
    log("选区窗已预热：热键只需 ShowWindow（无抓屏 / 无 HTTP / 无浏览器）")
    sess: OverlaySession | None = None
    results: list = []                       # 后台识别线程 → 主线程（matches, region, error）
    recognizing = {"flag": False, "t0": 0.0}
    # R256：运行时游戏模式，可被浮窗「切换模式」按钮在 PvP/PvE/PvPS 间循环。
    # 初值取设置面板的数据范围；之后以浮窗按钮为准（不写回配置文件）。
    game_idx = game_mode_index(current_mode(config_dir))
    # 切换意图登记：WndProc 里只写这个 dict，真正的关窗+重识别放到主循环（避免在
    # 处理本窗口消息时销毁它自己导致消息泵崩溃）。
    gamemode_pending: dict = {"code": None, "region": None}

    def on_gamemode(new_code: str) -> None:
        r = _ACTIVE.region if _ACTIVE is not None else None
        gamemode_pending["code"] = new_code
        gamemode_pending["region"] = dict(r) if r else None

    def worker(rect, mode):
        try:
            matches, region = recognize_region(server, rect, mode, config_dir)
            results.append((matches, region, None))
        except Exception as exc:  # noqa: BLE001
            results.append(([], None, "%s: %s" % (type(exc).__name__, exc)))

    current_hk = hotkey
    hk_text = None
    hk_next_check = time.time() + 1.0
    msg = wintypes.MSG()
    user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                                   wintypes.UINT, wintypes.UINT, wintypes.UINT]
    user32.PeekMessageW.restype = wintypes.BOOL
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
    log("就绪：按热键 → 框选 → 价格浮窗（Esc / 右键取消，✕ 或热键关闭浮窗）")
    while True:
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            if msg.message == 0x0312:       # WM_HOTKEY
                if recognizing["flag"]:
                    log("上一轮识别仍在进行，按键忽略（界面有「识别中」提示）")
                else:
                    t0 = time.monotonic()
                    # R260：每次截图都重新读取页面右上角选的模式（默认跟随互动地图应用）
                    game_idx = game_mode_index(current_mode(config_dir))
                    if sess is not None:
                        sess.close()
                        sess = None
                    _SELECT_RESULTS.clear()
                    if sel.active:
                        sel.hide()               # 选区中再按热键 = 重新框选
                    # R255：勾了「全屏识别」→ 不弹选区，直接抓整屏进识别管线
                    if full_screen(config_dir):
                        try:
                            mode = GAME_MODES[game_idx][0]
                            recognizing["flag"] = True
                            recognizing["t0"] = time.time()
                            sel.show_status("全屏识别中…")
                            threading.Thread(
                                target=_full_screen_worker,
                                args=(server, mode, config_dir, results, recognizing),
                                daemon=True).start()
                            log("全屏识别开始（mode=%s）" % mode)
                        except Exception as exc:  # noqa: BLE001
                            recognizing["flag"] = False
                            log_exc("全屏识别失败", exc)
                        continue
                    try:
                        sel.show()
                        log("选区窗已显示 %.0f ms" % ((time.monotonic() - t0) * 1000))
                    except Exception as exc:  # noqa: BLE001
                        log_exc("显示选区窗失败", exc)
            user32.DispatchMessageW(ctypes.byref(msg))

        while _SELECT_RESULTS:
            kind, rect = _SELECT_RESULTS.pop(0)
            if kind == "cancel":
                log("选择已取消")
                continue
            if recognizing["flag"]:
                log("上一轮识别仍在进行，忽略本次框选")
                continue
            recognizing["flag"] = True
            recognizing["t0"] = time.monotonic()
            try:
                sel.show_status("识别中…  %d × %d" % (rect[2], rect[3]))
            except Exception as exc:  # noqa: BLE001
                log_exc("显示识别提示失败", exc)
            threading.Thread(target=worker,
                             args=(rect, GAME_MODES[game_idx][0]), daemon=True).start()

        while results:
            matches, region, err = results.pop(0)
            recognizing["flag"] = False
            try:
                sel.hide_status()
            except Exception:
                pass
            if err:
                log("识别失败：%s（%.0f ms）" % (err, (time.monotonic() - recognizing["t0"]) * 1000))
                continue
            log("识别完成：%d 件 / %.0f ms / 区域 %s" %
                (len(matches), (time.monotonic() - recognizing["t0"]) * 1000, region))
            if matches:
                try:
                    sess = OverlaySession(region, matches, config_dir, server=server,
                                          game_idx=game_idx, on_gamemode=on_gamemode)
                    sess.show()
                    log("透明浮窗已显示 %d 件" % len(matches))
                except Exception as exc:  # noqa: BLE001
                    log_exc("浮窗创建失败", exc)
            else:
                log("没有识别到物品")

        if sess is not None and sess.dead():
            sess = None
            log("浮窗已关闭，回到等待")

        # R256：处理「切换模式」意图（放在消息循环外，避免在途窗口销毁问题）。
        # 点击浮窗「切换模式」→ 同一区域用新模式重新识别 → 重建浮窗。
        if gamemode_pending["code"] and not recognizing["flag"]:
            code = gamemode_pending["code"]
            region = gamemode_pending["region"]
            gamemode_pending["code"] = None
            gamemode_pending["region"] = None
            game_idx = game_mode_index(code)
            if region:
                if sess is not None:
                    sess.close()
                    sess = None
                recognizing["flag"] = True
                recognizing["t0"] = time.monotonic()
                try:
                    sel.show_status("识别中…  %s" % code)
                except Exception:
                    pass
                rect = (region["x"], region["y"], region["w"], region["h"])
                threading.Thread(target=worker, args=(rect, code), daemon=True).start()
                log("模式切换：重新识别（mode=%s）" % code)

        # R241：设置面板改截图键后 ≤1s 生效，不用重启宿主
        if time.time() >= hk_next_check:
            hk_next_check = time.time() + 1.0
            try:
                import config as _cfg

                text = str((_cfg.load(config_dir).get("ocrScan") or {})
                           .get("hotkey") or "").strip().lower()
            except Exception:
                text = None
            if text and text != hk_text:
                parsed = None
                if text not in ("off", "none", "no"):
                    parsed = overlay.parse_hotkey(text)
                    if parsed and not hotkey_requires_mod(parsed):
                        # R254：单键全局热键会吞游戏按键（真实事故），拒绝注册
                        log("热键 %s 没有修饰键，已拒绝（请用 Ctrl/Alt/Shift + 键）" % text)
                        parsed = "invalid"
                if text in ("off", "none", "no") or parsed not in (None, "invalid"):
                    hk_text = text
                    new_hk = None if parsed == "invalid" else parsed
                    if new_hk != current_hk:
                        if current_hk is not None:
                            user32.UnregisterHotKey(None, 1)
                        ok = True
                        if new_hk is not None:
                            mod, vk = new_hk
                            ok = bool(user32.RegisterHotKey(None, 1, mod, vk))
                        if ok:
                            current_hk = new_hk
                            log("热键已切换为 %s（即时生效）" % text)
                        else:
                            if current_hk is not None:
                                mod, vk = current_hk
                                user32.RegisterHotKey(None, 1, mod, vk)
                            log("热键 %s 注册失败（可能被占用），保留原热键" % text)
        time.sleep(0.01)


# ---------------------------------------------------------------------------
# 演示模式（验收用）：合成帧 → OCR → 假游戏底图 + 透明浮窗 → 截图取证

def _demo_make_frame(path: str) -> tuple[int, int]:
    """生成与屏幕等大的合成「游戏画面」（3 个真实物品名 + 1 个价格标签）。"""
    items = json.load(open(os.path.join(ROOT, "data", "items.json"), encoding="utf-8"))["items"]
    prices = json.load(open(os.path.join(ROOT, "data", "flea-prices.json"),
                            encoding="utf-8"))["items"]
    want = ["工厂紧急出口钥匙", "宿舍118房间钥匙", "马卡洛夫9x18PM 手枪"]
    picks = [(iid, rec["n"]) for iid, rec in items.items()
             if rec.get("n") in want and prices.get(iid, {}).get("lastLowPrice")]
    if len(picks) < 3:
        picks = [(iid, rec["n"]) for iid, rec in list(items.items())[:3]]
    from PIL import Image, ImageDraw, ImageFont

    sw, sh = screen_size()
    font = ImageFont.truetype(os.path.join(os.environ.get("WINDIR", r"C:\Windows"),
                                           "Fonts", "msyhbd.ttc"), 28)
    img = Image.new("RGB", (sw, sh), (30, 32, 36))
    d = ImageDraw.Draw(img)
    # R244：行距按真实游戏比例（实测同列 dy/字高 ≈ 5.3），三行价格才有位置放
    row_gap = 150
    for i, (_iid, n) in enumerate(picks):
        d.text((40, 40 + i * row_gap), n, fill=(236, 236, 230), font=font)
    # 价格标签用 Segoe UI（雅黑没有 ₽ 字形，会渲染成方框）
    price_font = ImageFont.truetype(os.path.join(os.environ.get("WINDIR", r"C:\Windows"),
                                                 "Fonts", "segoeuib.ttf"), 28)
    d.text((int(sw * 0.55), 40 + 3 * row_gap), "53,548 ₽", fill=(220, 220, 214), font=price_font)
    img.save(path)
    return sw, sh


def run_demo(server: str, seconds: float = 6.0) -> int:
    """R239 验收：合成帧 → OCR → 假游戏底图 + 透明浮窗 → 截屏取证。

    输出 `RESULT labels_ex=… control_ex=… matches=N shot=路径`；截图存在
    build/_r239_overlay_demo.png（标签应叠在装备名上、背景透明露出底图）。
    """
    from PIL import Image, ImageGrab

    import overlay

    overlay.dpi_aware()
    frame_path = os.path.join(BUILD_DIR, "_r239_demo_frame.png")
    _demo_make_frame(frame_path)
    png = open(frame_path, "rb").read()
    fid = post_frame(server, png)

    # 区域：盖住 3 个物品名 + 价格标签（价格标签应被守卫挡掉不产生匹配）
    sw, sh = screen_size()
    region = {"x": 20, "y": 20, "w": min(int(sw * 0.62), sw - 40), "h": min(470, sh - 40)}
    img = Image.open(frame_path)
    crop = img.crop((region["x"], region["y"], region["x"] + region["w"], region["y"] + region["h"]))
    buf = io.BytesIO()
    crop.save(buf, "PNG")
    import base64
    import urllib.request

    req = urllib.request.Request(
        server.rstrip("/") + "/api/ocr/recognize",
        data=json.dumps({"image": base64.b64encode(buf.getvalue()).decode(),
                         "annotate": False}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=180) as r:
        d = json.loads(r.read().decode("utf-8"))
    matches = d.get("matches") or []
    log("识别出 %d 件" % len(matches))
    post_overlay_state(server, region, matches)

    # 假游戏底图（不透明分层窗，role=2 → 全穿透不挡鼠标，仅当背景用）
    game_hwnd = create_overlay_window(2)
    set_layered_bitmap(game_hwnd, img.convert("RGBA"), 0, 0)
    _user32.ShowWindow(game_hwnd, SW_SHOWNOACTIVATE)
    _topmost(game_hwnd)

    sess = OverlaySession(region, matches, server=server)
    sess.show()
    log("浮窗显示中（%d 件，口径 %s）——截屏取证后自动关闭" % (len(matches), sess.mode_label))

    time.sleep(max(2.0, seconds))
    rx, ry, rw, rh = sess._rect
    shot = ImageGrab.grab(bbox=(rx, ry, rx + rw, ry + rh))
    shot_path = os.path.join(BUILD_DIR, "_r239_overlay_demo.png")
    shot.save(shot_path)
    ex_l = overlay._get_style(sess.labels_hwnd, GWL_EXSTYLE)
    ex_c = overlay._get_style(sess.ctrl_hwnd, GWL_EXSTYLE)
    print("RESULT labels_ex=0x%X control_ex=0x%X matches=%d shot=%s"
          % (ex_l, ex_c, len(matches), shot_path), flush=True)
    sess.close()
    try:
        _user32.DestroyWindow(game_hwnd)
    except Exception:
        pass
    return 0 if matches else 3


def main(argv=None) -> int:
    global DEFAULT_SERVER
    ap = argparse.ArgumentParser(description="EFTMap 截图识别宿主（热键 → 框选 → 透明浮窗）")
    ap.add_argument("--server", default=DEFAULT_SERVER)
    ap.add_argument("--hotkey", default=None, help="全局热键（默认 ctrl+alt+p，off 关闭）")
    ap.add_argument("--config-dir", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--demo-overlay", action="store_true",
                    help="R239 验收：合成帧 → OCR → 透明浮窗演示（自动退出）")
    ap.add_argument("--demo-seconds", type=float, default=6.0)
    ap.add_argument("--legacy-select", action="store_true",
                    help="R247 回退：使用旧的 Edge 冻结帧选择窗（默认走原生 ShareX 式选区）")
    a = ap.parse_args(argv)
    DEFAULT_SERVER = a.server

    if not IS_WINDOWS:
        print("仅支持 Windows")
        return 2
    if a.dry_run:
        print("[dry-run] server=%s hotkey=%s" % (a.server, a.hotkey or "(配置)"))
        return 0
    if not server_alive(a.server):
        log("本机服务没开（%s/api/health 不通）——先启动地图服务再运行本工具" % a.server)
        return 1
    if not acquire_single_instance():
        log("已有截图宿主在运行，本次退出（同一热键只能注册一次）")
        return 0
    import overlay

    overlay.dpi_aware()
    log("宿主启动：pid=%d server=%s" % (os.getpid(), a.server))
    if a.demo_overlay:
        return run_demo(a.server, a.demo_seconds)
    killed = kill_stale_scan_browsers()
    if killed:
        log("启动清理：结束旧的扫描浏览器进程 %d 个（纯 ctypes，无子进程）" % killed)
    hotkey = resolve_hotkey(a, a.config_dir)
    if a.legacy_select:
        log("使用旧版 Edge 选择窗（--legacy-select）")
        watch(a.server, hotkey, a.config_dir)
    else:
        watch_native(a.server, hotkey, a.config_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
