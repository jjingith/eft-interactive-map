#!/usr/bin/env python3
"""EFT 互动地图 · 运行期配置（纯标准库）

配置落在**用户级持久化目录**下的 `eftmap.config.json`（见 `default_storage_dir`）：

- Windows = `%APPDATA%\\EFTMap`，其它平台 = `~/.eftmap`。

刻意**不**放在软件目录：PyInstaller onedir 产物每次打包都会被整个重建
（`build.ps1` 会 `Remove-Item dist\\EFTMap`），配置跟着 exe 一起消失，表现为
「每次启动都要重设」。放到用户目录就与安装位置解耦，重装 / 移动 / 重新打包都不丢；
旧的软件目录里若还留着配置与提示音，首次启动会自动迁移一次（见 `migrate_legacy`）。

用户选取的自定义提示音会**复制**到同目录的 `sounds/` 里，这样配置文件只记录文件名，
换机器、重装、清缓存都不会因为绝对路径失效而丢声音。

设计上刻意保持纯数据结构 + 纯函数：
- `normalize` 把任意来源（手改的 JSON、旧版本、半截文件）收敛成完整且类型正确的配置；
- 读写都不抛异常以外的副作用，读写路径全部可注入（便于单测）。
"""

from __future__ import annotations

import datetime
import json
import math
import os
import re
import shutil
import sys
import time

CONFIG_NAME = "eftmap.config.json"
SOUNDS_DIRNAME = "sounds"
TRIAL_NAME = "local-trial.json"   # 新注册邮箱的 3 天试用记录（见 grant_local_trial）
TRIAL_DAYS = 3
STORAGE_DIRNAME = "EFTMap"      # %APPDATA% 下的子目录名（见 default_storage_dir）

# 三个提示音开关的 key（同时也是 config.sound 下的子对象名）
SOUND_KEYS = ("raid_start", "location_loading", "matching")
SOUND_LABELS = {
    "raid_start": "战局开始",
    "location_loading": "开始加载战局",
    "matching": "开始匹配",
}

# 允许导入的音频扩展名（浏览器能直接播的格式）
AUDIO_EXTS = (".mp3", ".wav", ".ogg", ".m4a", ".aac", ".flac", ".opus")

# 自动截图：间隔以毫秒计，钳在合理区间（太短会让截图目录爆炸增长）
# 默认 5 秒：一张图约 600 KB，1 秒一张 = 每小时约 2 GB，40 分钟战局就能吃掉 1.6 GB。
# 5 秒对「按文件名里的坐标复现路线」已经够密，需要更细的可以自己调小。
# R108：这是**会员**的缺省值；非会员的缺省与锁定值都是 SHOT_INTERVAL_LOCKED_MS。
SHOT_INTERVAL_DEFAULT = 5000
SHOT_INTERVAL_MIN = 200
SHOT_INTERVAL_MAX = 60000
# R108：非会员的自动截图间隔**锁死**为 10 秒；位置更新节流也用同一个值
# （见 serve.PositionTracker，两处共用这一个常量，避免以后改成两个数）。
SHOT_INTERVAL_LOCKED_MS = 10000

# 游戏内小浮窗（tools/overlay.py）：设置面板与宿主共用这一份配置。
# 宿主每 0.5 秒读一次配置，改完立刻生效（位置 / 大小 / 透明度不用重启小窗）。
OVERLAY_SIZE_MIN, OVERLAY_SIZE_MAX = 120, 1200
OVERLAY_OPACITY_MIN, OVERLAY_OPACITY_MAX = 0.3, 1.0
OVERLAY_OFFSET_MIN, OVERLAY_OFFSET_MAX = -800, 800
OVERLAY_CORNERS = ("top-left", "top-right", "bottom-left", "bottom-right")
OVERLAY_SHAPES = ("square", "circle")
# R76：尺寸基准 = min(工作区宽, 工作区高) × 20% × scale；fixed 模式才用 overlay.size。
OVERLAY_SIZE_MODES = ("auto", "fixed")
OVERLAY_SCALE_MIN, OVERLAY_SCALE_MAX = 0.5, 3.0
# R78：小地图**内部**缩放（不改窗口大小）。范围对齐参考实现 kaedeori 的 0.5–3；
# 1 = R77b 原有 150 米视野，3 = 50 米，0.5 = 300 米。步进（0.1）由前端决定，配置只存结果。
# R106：改为五档米制半径后，map_scale 只用于读取旧配置并迁移，不再由页面写入。
OVERLAY_MAP_SCALE_MIN, OVERLAY_MAP_SCALE_MAX = 0.5, 3.0
# R106：小地图视野 = 以玩家为中心、半径 N 米（只允许这五档）。旧 map_scale 按
# 「半径 = 75 / map_scale」迁移（1.0 = 旧 150 米视野 = 半径 75 米），再取最近的档位。
OVERLAY_MINI_RADIUS_CHOICES = (25, 50, 100, 200, 300)
OVERLAY_MINI_RADIUS_DEFAULT = 100

# 监听地址白名单：127.0.0.1（仅本机）或 0.0.0.0（所有网卡，允许局域网内其它设备访问）。
# 只认这两个值，手改配置写进来的怪值一律回落本机回环，避免服务意外对公网开放。
HOST_CHOICES = ("127.0.0.1", "0.0.0.0")
HOST_DEFAULT = "127.0.0.1"


def app_dir() -> str:
    """软件目录（站点文件所在处；也是旧版配置的遗留位置）。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def default_storage_dir() -> str:
    """用户级持久化目录（配置与 sounds/ 的家）。

    与软件目录解耦，重新打包 / 移动 / 重装 exe 都不会丢设置。
    Windows 取 `%APPDATA%\\EFTMap`（没有 APPDATA 环境变量时回退 `~/.eftmap`）。
    """
    base = os.environ.get("APPDATA")
    if base:
        return os.path.join(base, STORAGE_DIRNAME)
    return os.path.join(os.path.expanduser("~"), ".eftmap")


def migrate_legacy(dest_dir: str, legacy_dir: str) -> list[str]:
    """把旧软件目录里的配置与自定义提示音搬到持久化目录。

    只在目标缺失时搬，且**不删**旧文件；任何一步失败都静默跳过（绝不因此影响启动）。
    返回实际搬动的项目名，供界面提示「已迁移 N 项」。
    """
    moved: list[str] = []
    if not legacy_dir or os.path.abspath(legacy_dir) == os.path.abspath(dest_dir):
        return moved

    legacy_cfg, dest_cfg = config_path(legacy_dir), config_path(dest_dir)
    try:
        if os.path.isfile(legacy_cfg) and not os.path.exists(dest_cfg):
            os.makedirs(dest_dir, exist_ok=True)
            shutil.copyfile(legacy_cfg, dest_cfg)
            moved.append(CONFIG_NAME)
    except OSError:
        pass

    src_sounds, dst_sounds = sounds_dir(legacy_dir), sounds_dir(dest_dir)
    if not os.path.isdir(src_sounds):
        return moved
    try:
        names = [n for n in os.listdir(src_sounds) if n.lower().endswith(AUDIO_EXTS)]
    except OSError:
        names = []
    for name in names:
        try:
            target = os.path.join(dst_sounds, name)
            if os.path.isfile(target):
                continue
            os.makedirs(dst_sounds, exist_ok=True)
            shutil.copyfile(os.path.join(src_sounds, name), target)
            moved.append(name)
        except OSError:
            continue
    return moved


def config_path(directory: str | None = None) -> str:
    return os.path.join(directory or default_storage_dir(), CONFIG_NAME)


def sounds_dir(directory: str | None = None) -> str:
    return os.path.join(directory or default_storage_dir(), SOUNDS_DIRNAME)


def ensure_sounds_dir(directory: str | None = None) -> str:
    path = sounds_dir(directory)
    os.makedirs(path, exist_ok=True)
    return path


def default_config() -> dict:
    """默认配置：目录留空（由自动定位或用户手填），自动居中默认开，声音/自动截图默认关。

    `ui` 空字典表示「用户还没在页面上保存过界面偏好」，前端据此回退到本地偏好，
    而不是被一份空偏好覆盖掉（见 `_normalize_ui`）。
    """
    return {
        "version": 1,
        "host": HOST_DEFAULT,
        "game_dir": None,
        "screenshots_dir": None,
        # R107：游戏日志目录。留空 = 自动探测（游戏目录\Logs → 常见安装位置 → 文档目录）
        "log_dir": None,
        # R108 / 会员模型：会员态由服务端下发，**不读**这个配置键。
        # 这里保留字段只是为了旧配置文件不报错；normalize 会用进程内快照覆盖它。
        "account": {"member": False},
        "auto_zoom": False,
        "auto_center": True,
        "auto_start": False,
        "auto_screenshot": {
            "enabled": False,
            # 默认是非会员，所以默认值就是锁定值；会员缺省时由 normalize 回落 5000
            "interval_ms": SHOT_INTERVAL_LOCKED_MS,
            "key": None,
            # R107：战局结束时清理「本工具自动截出来的图」。默认关，开启后才删；
            # 只删 AutoShotter 记录过的文件，不碰任何手动截图（清单见 serve.ShotManifest）
            "cleanup_on_raid_end": False,
        },
        "auto_delete": {
            "enabled": False,
            "since": None,     # 开启时刻的时间戳：只删「开启之后」产生的截图，历史截图一律保留
        },
        "sound": {
            "enabled": False,
            "raid_start": {"on": True, "file": None},
            "location_loading": {"on": True, "file": None},
            "matching": {"on": True, "file": None},
        },
        # 游戏内小浮窗：大小 / 位置 / 透明度等，宿主 tools/overlay.py 实时读取并应用
        "overlay": dict(OVERLAY_DEFAULTS),
        # R42 可选在线行情：默认关闭 = 全程离线；只有显式开启后才访问 json.tarkov.dev
        "livePrices": dict(LIVE_PRICES_DEFAULTS),
        # R241 截图识别：热键 + 价格标签档位样式（样式仅会员可自定义）
        "ocrScan": _normalize_ocr_scan(None),
        # R260：数据范围（PvP/PvE/PvPS）——页面右上角选择的模式，截图识别按它取价
        "dataScope": {"mode": "regular"},
        "ui": {},
    }


_VALID_MEMBER_STATUS = {"none", "active", "permanent", "expired", "trial"}

# 服务端下发的会员快照（进程内缓存）。默认非会员；由 tools/cloud.py 写入。
_member_state: dict = {
    "member": False,
    "member_status": "none",
    "member_plan": None,
    "member_since": None,
    "member_expires_at": None,
}


def is_member(directory: str | None = None) -> bool:
    """会员态**唯一判定入口**（R108 / 会员模型）。

    只认服务端下发的快照：`tools/cloud.py` 在收到云端 `me` / 登录 / 刷新
    响应后调用 `set_member_state()` 写入进程内缓存，这里直接读缓存。

    配置文件里的 `account.member` **一律忽略**——手改
    `eftmap.config.json` 不再能「解锁」；未登录 / 未收到响应 / 云端说不是
    会员，统一按非会员处理。权威判定在服务端 `/v1/auth/me`。

    R273：新注册邮箱赠送的 3 天试用属于**本机兜底**（见 local_trial）——
    只在「云端没说是会员」时补上，云端一旦确认会员就以云端为准。
    """
    return member_state()["member"] is True


# ---------------------------------------------------------------- 新注册试用（3 天）
# 注册接口在远端云服务上，本地改不了服务端策略；这里做的是**本机试用**：注册并验证
# 成功后，该邮箱在本机获得 TRIAL_DAYS 天会员态（member_status="trial"）。
# 局限（如实说明）：换机器 / 手改 local-trial.json 都会影响它；要真正跨设备生效，
# 需要云端 `/v1/auth/register` 侧给同样的赠送规则。
_trial_cache: dict | None = None
_trial_loaded = False


def trial_path(directory: str | None = None) -> str:
    return os.path.join(directory or default_storage_dir(), TRIAL_NAME)


def _read_trial() -> dict | None:
    global _trial_cache, _trial_loaded
    if _trial_loaded:
        return _trial_cache
    _trial_loaded = True
    try:
        with open(trial_path(), "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        data = None
    _trial_cache = data if isinstance(data, dict) else None
    return _trial_cache


def _parse_moment(value) -> datetime.datetime | None:
    """ISO 时间串 → 带时区的 datetime；解不出返回 None（不猜）。"""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        moment = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=datetime.timezone.utc)
    return moment


def _write_trial(payload: dict) -> None:
    global _trial_cache, _trial_loaded
    try:
        directory = default_storage_dir()
        os.makedirs(directory, exist_ok=True)
        tmp = trial_path(directory) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False)
        os.replace(tmp, trial_path(directory))
    except OSError:
        pass   # 写不进去也不能影响注册 / 登录本身
    _trial_cache = payload
    _trial_loaded = True


def local_trial() -> dict | None:
    """当前生效的本机试用（没有 / 已过期 → None）。"""
    data = _read_trial() or {}
    accounts = data.get("accounts") if isinstance(data.get("accounts"), dict) else {}
    email = data.get("email")
    entry = accounts.get(email) if isinstance(email, str) else None
    if not isinstance(entry, dict):
        return None
    expires = _parse_moment(entry.get("expires_at"))
    if expires is None or expires <= datetime.datetime.now(datetime.timezone.utc):
        return None
    return dict(entry)


def grant_local_trial(email: str, days: int = TRIAL_DAYS) -> dict:
    """给「刚注册并验证通过」的邮箱发本机试用；同一邮箱只发一次（不叠加）。

    返回该邮箱的试用记录（含 expires_at），已发过就原样返回旧记录。
    """
    email = (email or "").strip().lower()
    days = max(1, int(days))
    data = _read_trial() or {}
    accounts = dict(data.get("accounts")) if isinstance(data.get("accounts"), dict) else {}
    entry = accounts.get(email) if email and isinstance(accounts.get(email), dict) else None
    if entry is None:
        now = datetime.datetime.now(datetime.timezone.utc)
        entry = {
            "email": email,
            "granted_at": now.isoformat(),
            "expires_at": (now + datetime.timedelta(days=days)).isoformat(),
            "days": days,
        }
        if email:
            accounts[email] = entry
    # 已发过也要把 current 切回这个邮箱：否则登录过别的账号之后重试注册会不生效
    _write_trial({"email": email, "accounts": accounts})
    return dict(entry)


def set_current_trial_email(email: str | None) -> None:
    """把本机试用归属切到当前登录账号（登录 / 注册 / 登出时调用）。

    没有该邮箱的试用记录就把 current 置空，试用随即失效——否则 A 注册送的
    3 天会在登录 B 之后被 B 继续享用。`set_current_trial_email(\"\")` 用于登出。
    """
    data = _read_trial() or {}
    accounts = data.get("accounts") if isinstance(data.get("accounts"), dict) else {}
    key = (email or "").strip().lower()
    wanted = key if isinstance(accounts.get(key), dict) else ""
    if data.get("email") == wanted:
        return
    _write_trial({"email": wanted, "accounts": accounts})


def set_member_state(payload: dict | None) -> dict:
    """写入服务端下发的会员快照（仅内存，不落配置文件）。

    `None` / 缺字段 = 非会员；字段类型不对一律丢弃，避免脏缓存变成会员。

    过期即非会员（修复「会员已过期但功能仍可用」）：服务端若显式给
    `member_status="expired"`，或 `member=True` 但 `member_expires_at` 已过去，
    都强制按非会员处理。否则在新机器上本机 3 天试用会把已过期状态顶掉，
    造成过期账号仍能用会员功能的漏洞。
    """
    global _member_state
    raw = payload if isinstance(payload, dict) else {}
    member = raw.get("member") is True
    status = raw.get("member_status")
    if status not in _VALID_MEMBER_STATUS:
        status = "permanent" if member and not raw.get("member_expires_at") else (
            "active" if member else "none")
    expires_at = raw.get("member_expires_at")
    # 过期即非会员：服务端显式 expired，或 member 为真但到期时间已过。
    if status == "expired":
        member = False
    elif member and isinstance(expires_at, str):
        exp = _parse_moment(expires_at)
        if exp is not None and exp <= datetime.datetime.now(datetime.timezone.utc):
            member = False
            status = "expired"
    _member_state = {
        "member": member,
        "member_status": status,
        "member_plan": raw.get("member_plan") if isinstance(raw.get("member_plan"), str) else None,
        "member_since": raw.get("member_since") if isinstance(raw.get("member_since"), str) else None,
        "member_expires_at": (
            raw.get("member_expires_at") if isinstance(raw.get("member_expires_at"), str) else None
        ),
    }
    return dict(_member_state)


def member_state() -> dict:
    """当前会员快照（**展示用缓存**，授权判定同源，见 `is_member`）。

    2026-11-15 起**只认服务端**：注册赠送的时长由云端写进账号的
    `member_expires_at`（服务端 `EFT_REGISTER_FREE_DAYS`），客户端不再用
    `local-trial.json` 兜底。

    为什么去掉本机兜底：那是**另一本账**——账号本身还是「未开通」，换台机器就没了，
    却能在本机解锁功能，于是出现「账号显示已到期 / 本机却能用会员功能」的矛盾状态。
    用户明确要求「免费时长要和充值一样加在账号上」，因此本机试用不再参与判定。
    旧的 local-trial.json 不会被读取，也不会被删除（避免动用户数据）。
    """
    return dict(_member_state)


def clamp_interval(value, member=None) -> int:
    """把截图间隔钳到合法毫秒数（R108 起区分会员态）。

    - `member is False`：非会员，**固定返回 SHOT_INTERVAL_LOCKED_MS（10000）**，
      不透传用户值——这样即使旧配置 / 旧客户端写进来 200ms，服务端也不会照做；
    - `member is True`：会员，沿用 [SHOT_INTERVAL_MIN, SHOT_INTERVAL_MAX]（200–60000）；
    - `member is None`：调用方不知道会员态（启动器构建配置、旧单测），只做通用区间清洗。

    为什么分两处：**服务端并不知道真实会员态**，`is_member()` 读到的只是本地配置，
    本质是「客户端自报」。所以真正的锁定是「客户端钳制（页面把输入框锁成 10000 并禁用）
    + 服务端保底（这里再按同一个值钳一次）」，两边都做只是为了别让脏值把轮询拖到不可用；
    它拦不住有意绕过的人（见 `is_member` 的说明）。
    """
    if member is False:
        return SHOT_INTERVAL_LOCKED_MS
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return SHOT_INTERVAL_DEFAULT
    return max(SHOT_INTERVAL_MIN, min(SHOT_INTERVAL_MAX, number))


# 地图图标的整体缩放（页面右上角滑条）：区间与前端 app.js 的 ICON_SCALE_MIN/MAX 对齐。
# 4K 屏上图标偏小，用户可以整体放大；默认 1.0 = 原始大小。
ICON_SCALE_DEFAULT = 1.0
# 旧刻度（0.5～3，1 = 100%）：只给还没迁移的旧配置 / 旧客户端用，前端读到没有
# icon_scale_v2 / icon_scale_v3 标记的值时会按「旧值 ÷ 0.55」换算成新刻度。
ICON_SCALE_MIN = 0.5
ICON_SCALE_MAX = 3.0
# R89 刻度：旧 55% = 新 100%；0 = 0%（图标不可见），5.45 = 旧 3.0 ÷ 0.55。
ICON_SCALE_V2_MIN = 0.0
ICON_SCALE_V2_MAX = 5.45
# R98 新刻度：10%～190%，中点 100%；渲染仍是 pct/100 × 0.55，所以同一百分比尺寸不变。
ICON_SCALE_V3_MIN = 0.1
ICON_SCALE_V3_MAX = 1.9


def clamp_icon_scale(value, v2: bool = False, v3: bool = False) -> float:
    """把图标缩放钳到合法区间；脏值（含 NaN）回落 1.0。

    v3=True 按 R98 刻度 [0.1, 1.9]（10%～190%），0 会被抬到 10%；
    v2=True 按 R89 刻度 [0, 5.45]，允许 0%（老配置的落点）；
    v2/v3 都为 False 时按旧刻度 [0.5, 3]，保持旧配置与旧客户端的行为不变。
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ICON_SCALE_DEFAULT
    if not math.isfinite(number):
        return ICON_SCALE_DEFAULT
    if v3:
        return round(max(ICON_SCALE_V3_MIN, min(ICON_SCALE_V3_MAX, number)), 3)
    if v2:
        return round(max(ICON_SCALE_V2_MIN, min(ICON_SCALE_V2_MAX, number)), 3)
    if number <= 0:
        return ICON_SCALE_DEFAULT
    return round(max(ICON_SCALE_MIN, min(ICON_SCALE_MAX, number)), 3)


# 地名的整体缩放与透明度（页面右上角滑条）：区间与前端 app.js 的 LABEL_SCALE_MIN/MAX 对齐。
# 地名不受「图标缩放」影响（跟地图绑定），所以单独给它一条缩放滑条，外加一条透明度滑条。
LABEL_SCALE_DEFAULT = 1.0
LABEL_SCALE_MIN = 0.1
LABEL_SCALE_MAX = 1.9
LABEL_ALPHA_DEFAULT = 1.0
LABEL_ALPHA_MIN = 0.0
LABEL_ALPHA_MAX = 1.0


def clamp_label_scale(value) -> float:
    """把地名缩放钳到 [LABEL_SCALE_MIN, LABEL_SCALE_MAX]；脏值（含 NaN）回落 1.0。

    R98 起区间是 10%～190%，0 / 负值不再回落 100%，而是钳到 10%（与前端迁移规则一致）。
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return LABEL_SCALE_DEFAULT
    if not math.isfinite(number):
        return LABEL_SCALE_DEFAULT
    return round(max(LABEL_SCALE_MIN, min(LABEL_SCALE_MAX, number)), 3)


def clamp_label_alpha(value) -> float:
    """把地名透明度钳到 [LABEL_ALPHA_MIN, LABEL_ALPHA_MAX]（0 = 全透明）；脏值回落 1.0。"""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return LABEL_ALPHA_DEFAULT
    if not math.isfinite(number):
        return LABEL_ALPHA_DEFAULT
    return round(max(LABEL_ALPHA_MIN, min(LABEL_ALPHA_MAX, number)), 3)


# ---------------------------------------------------------------- 类型收敛
def _as_bool(value, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or value == "":
        return default
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def _as_text(value) -> str | None:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return None


def _as_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def clamp_host(value) -> str:
    """监听地址收敛到白名单（`HOST_CHOICES`）；缺失或非法值一律回落本机回环。"""
    text = _as_text(value)
    return text if text in HOST_CHOICES else HOST_DEFAULT


# ---------------------------------------------------------------- 可选在线行情（R42）
# 默认 **关闭**：不开启时服务启动、页面加载都不联网，只用构建期快照 data/flea-prices.json。
# 开启后只访问 json.tarkov.dev（PvP=`regular` 端点，PvE=`pve` 端点），不做任何其它外连。
LIVE_PRICES_DEFAULTS = {
    "enabled": False,
    "mode": "regular",      # regular=PvP（常规），pve=PvE
    "ttlSec": 600,          # 与上游约 10 分钟一版对齐
    "source": None,         # 调试用：覆盖上游地址；None = 用内置地址
}
LIVE_PRICES_MODES = ("regular", "pve")
LIVE_PRICES_TTL_MIN = 60
LIVE_PRICES_TTL_MAX = 3600


def clamp_live_ttl(value) -> int:
    """行情缓存 TTL 钳到 [60, 3600] 秒；脏值回落 600。"""
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return LIVE_PRICES_DEFAULTS["ttlSec"]
    return max(LIVE_PRICES_TTL_MIN, min(LIVE_PRICES_TTL_MAX, number))


def _normalize_live_prices(raw) -> dict:
    out = dict(LIVE_PRICES_DEFAULTS)
    if not isinstance(raw, dict):
        return out
    out["enabled"] = _as_bool(raw.get("enabled"), False)
    mode = _as_text(raw.get("mode"))
    out["mode"] = mode if mode in LIVE_PRICES_MODES else LIVE_PRICES_DEFAULTS["mode"]
    out["ttlSec"] = clamp_live_ttl(raw.get("ttlSec"))
    source = _as_text(raw.get("source"))
    out["source"] = source if source and source.startswith(("http://", "https://")) else None
    return out


def live_prices(directory: str | None = None) -> dict:
    """读取 `livePrices` 段（已收敛）；缺失即默认关闭。"""
    return _normalize_live_prices((load(directory) or {}).get("livePrices"))


# ---------------------------------------------------------------- 游戏内小浮窗（R32.9）
# 设置面板（index.html 的「设置」菜单）与宿主 tools/overlay.py 共用这一份。
# 宿主每 0.5 秒读一次配置，位置 / 大小 / 透明度改完立刻生效，不用重启小窗。
OVERLAY_DEFAULTS = {
    "enabled": False,
    "size": 260,
    "size_mode": "auto",
    "scale": 1.0,
    "opacity": 0.9,
    "corner": "bottom-right",
    "offset_x": 0,
    "offset_y": 0,
    "shape": "square",
    "labels": False,
    "follow": True,
    "click_through": True,
    "exclude_from_capture": False,
    # R78：小地图内部缩放（1 = 默认 150 米视野）；R106 起只读，用于旧配置迁移
    "map_scale": 1.0,
    # R106：小地图视野半径（米），只允许 25 / 50 / 100 / 200 / 300 五档
    "mini_radius_m": OVERLAY_MINI_RADIUS_DEFAULT,
    # R104：小地图窗口自己的三条显示系数（地名缩放 / 地名透明度 / 图标缩放）。
    # 与主地图的 ui.label_scale / ui.label_alpha / ui.icon_scale 完全隔离，
    # 由主界面左侧栏那组「小地图」控件写入，小地图窗口经 config SSE 实时套用。
    "mini_label_scale": 1.0,
    "mini_label_alpha": 1.0,
    "mini_icon_scale": 1.0,
    # R105：自动缩放（进图 / 切图时把小地图缩放套回 100% 档位）。
    # 自动跟随复用上面的 follow（与设置面板「跟随玩家」是同一项）。
    "mini_auto_zoom": False,
}


def _clamp_num(value, low, high, fallback):
    """数字钳到 [low, high]；脏值回落 fallback。"""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    if number != number:          # NaN
        return fallback
    return max(low, min(high, number))


def nearest_mini_radius_m(value) -> int:
    """把任意半径吸附到五档之一；正好落在两档中间时取更大的一档（视野更宽，不会突然贴脸）。"""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return OVERLAY_MINI_RADIUS_DEFAULT
    if not math.isfinite(number):
        return OVERLAY_MINI_RADIUS_DEFAULT
    best = OVERLAY_MINI_RADIUS_DEFAULT
    best_diff = None
    for choice in OVERLAY_MINI_RADIUS_CHOICES:
        diff = abs(choice - number)
        if (best_diff is None or diff < best_diff - 1e-9
                or (abs(diff - best_diff) <= 1e-9 and choice > best)):
            best, best_diff = choice, diff
    return best


def mini_radius_from_map_scale(value) -> int:
    """旧配置迁移：map_scale = 1 表示 150 米视野高（半径 75 米），所以半径 = 75 / map_scale。"""
    scale = _clamp_num(value, OVERLAY_MAP_SCALE_MIN, OVERLAY_MAP_SCALE_MAX,
                       OVERLAY_DEFAULTS["map_scale"])
    return nearest_mini_radius_m(75.0 / scale)


def _normalize_overlay(raw) -> dict:
    """小浮窗设置：缺项补默认，脏值一律回落默认（宁可用默认，也不要产出越界坐标 / NaN）。"""
    out = dict(OVERLAY_DEFAULTS)
    if not isinstance(raw, dict):
        return out
    out["enabled"] = _as_bool(raw.get("enabled"), OVERLAY_DEFAULTS["enabled"])
    out["size"] = int(_clamp_num(raw.get("size"), OVERLAY_SIZE_MIN, OVERLAY_SIZE_MAX,
                                 OVERLAY_DEFAULTS["size"]))
    size_mode = _as_text(raw.get("size_mode"))
    out["size_mode"] = size_mode if size_mode in OVERLAY_SIZE_MODES else OVERLAY_DEFAULTS["size_mode"]
    out["scale"] = _clamp_num(raw.get("scale"), OVERLAY_SCALE_MIN, OVERLAY_SCALE_MAX,
                              OVERLAY_DEFAULTS["scale"])
    out["map_scale"] = round(_clamp_num(raw.get("map_scale"), OVERLAY_MAP_SCALE_MIN,
                                        OVERLAY_MAP_SCALE_MAX, OVERLAY_DEFAULTS["map_scale"]), 1)
    # R106：五档米制半径。新配置直接吸附；旧配置只有 map_scale 时先按「半径 = 75 / map_scale」迁移，
    # 避免升级后旧值被当成缺项、直接跳到默认 100 米（或更糟的 300 米）。
    if "mini_radius_m" in raw:
        out["mini_radius_m"] = nearest_mini_radius_m(raw.get("mini_radius_m"))
    elif "map_scale" in raw:
        out["mini_radius_m"] = mini_radius_from_map_scale(raw.get("map_scale"))
    else:
        out["mini_radius_m"] = OVERLAY_MINI_RADIUS_DEFAULT
    # R104：小地图专用三条显示系数；区间与前端滑条一致（地名 10%～190%、透明度 0%～100%）
    out["mini_label_scale"] = clamp_label_scale(raw.get("mini_label_scale"))
    out["mini_label_alpha"] = clamp_label_alpha(raw.get("mini_label_alpha"))
    out["mini_icon_scale"] = clamp_label_scale(raw.get("mini_icon_scale"))
    out["mini_auto_zoom"] = _as_bool(raw.get("mini_auto_zoom"), OVERLAY_DEFAULTS["mini_auto_zoom"])
    out["opacity"] = _clamp_num(raw.get("opacity"), OVERLAY_OPACITY_MIN, OVERLAY_OPACITY_MAX,
                                OVERLAY_DEFAULTS["opacity"])
    corner = _as_text(raw.get("corner"))
    out["corner"] = corner if corner in OVERLAY_CORNERS else OVERLAY_DEFAULTS["corner"]
    out["offset_x"] = int(_clamp_num(raw.get("offset_x"), OVERLAY_OFFSET_MIN, OVERLAY_OFFSET_MAX,
                                     OVERLAY_DEFAULTS["offset_x"]))
    out["offset_y"] = int(_clamp_num(raw.get("offset_y"), OVERLAY_OFFSET_MIN, OVERLAY_OFFSET_MAX,
                                     OVERLAY_DEFAULTS["offset_y"]))
    shape = _as_text(raw.get("shape"))
    out["shape"] = shape if shape in OVERLAY_SHAPES else OVERLAY_DEFAULTS["shape"]
    out["labels"] = _as_bool(raw.get("labels"), OVERLAY_DEFAULTS["labels"])
    out["follow"] = _as_bool(raw.get("follow"), OVERLAY_DEFAULTS["follow"])
    out["click_through"] = _as_bool(raw.get("click_through"), OVERLAY_DEFAULTS["click_through"])
    out["exclude_from_capture"] = _as_bool(raw.get("exclude_from_capture"),
                                           OVERLAY_DEFAULTS["exclude_from_capture"])
    return out


# ---------------------------------------------------------------- 配装视图（第十六轮）
# 顶栏视图的白名单：切换结果写进 ui.view，刷新后停在同一视图。
# 必须与 app.js 的 VIEWS 保持一致，否则白名单外的视图会被 `_normalize_ui` 丢弃，
# 而合并时旧值（如 market）会保留并随配置广播把界面切回去——R308 的
# 「价格识别里点单格价格就跳回市场」就是这个原因（changes / tools 漏了白名单）。
VIEWS = ("map", "loadout", "gun", "ammo", "tasks", "market", "changes", "tools")
# R19.22 任务；R97 市场；R305 游戏更新；R307 小工具（与 app.js 的 VIEWS 同步）
VIEW_DEFAULT = "map"

# 配装的根槽位（顺序与前端 app.js 的 ROOT_SLOTS 一致）：key 一一对应。
# 归属按构建期算好的一级类别 `cat` 判定（helmet / headphones / glasses / face / armor / rig /
# backpack）；其中 glasses = 上游 `glasses` type + `vis-observ-device` 分类，
# face = 上游 `face-cover` 分类——**不再用「护甲附件 + 未被引用」这类近似规则**（见 app.js 注释）。
# 后四个是第三轮新增的武器槽：枪械槽（primary1 / primary2 / holster）本轮只做 UI 与数据接口
# （待接入，不拿普通物品冒充枪械预设），melee 走上游真实 Melee 候选，可直接安装。
GEAR_SLOTS = ("helmet", "headphones", "glasses", "face", "armband", "dogtag",
              "armor", "rig", "backpack",
              "primary1", "primary2", "holster", "melee")

# 表格列宽像素区间（与前端 app.js 的 MIN_COL_W / MAX_COL_W 对齐）：钳在这个范围里，
# 避免列被拖到看不见或无限撑宽。
COL_W_MIN = 56
COL_W_MAX = 520

# 游戏内灵敏度区间：0 是合法值（部分玩家故意调 0），所以不能沿用「脏值回落默认」那套。
SENS_DEFAULT = 0.5
SENS_MIN = 0.0
SENS_MAX = 1.0


def clamp_sens(value) -> float | None:
    """把游戏内灵敏度钳到 [SENS_MIN, SENS_MAX]；非数 / NaN / 布尔返回 None（= 用户没填）。

    与 `clamp_label_alpha` 的关键区别：**0 是合法值**，不能当成「没填」丢掉；
    布尔要单独挡掉（`True` 会被 `float()` 当成 1.0）。
    """
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return round(max(SENS_MIN, min(SENS_MAX, number)), 3)


def clamp_col_w(value) -> int | None:
    """表格列宽像素：钳到 [COL_W_MIN, COL_W_MAX]；非数 / NaN / 布尔返回 None（丢弃该项）。"""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return int(round(max(COL_W_MIN, min(COL_W_MAX, number))))


def normalize_colw(raw) -> dict:
    """表格列宽：结构固定为 `{byCat: {类别: {列名: px}}, shared: {列名: px}}`。

    两个桶结构不同：`byCat` 两层（类别 → 列 → px），`shared` 一层（列 → px，
    放「同名同义列」供跨类别复用）。只收数值对，像素钳到 [COL_W_MIN, COL_W_MAX]，
    非法项丢弃（前端另有 clamp，后端只做守卫）。
    """
    out: dict = {"byCat": {}, "shared": {}}
    if not isinstance(raw, dict):
        return out
    by_cat = raw.get("byCat")
    if isinstance(by_cat, dict):
        for cat, cols in by_cat.items():
            if not isinstance(cols, dict):
                continue
            clean = {}
            for key, value in cols.items():
                width = clamp_col_w(value)
                if width is not None:
                    clean[str(key)] = width
            out["byCat"][str(cat)] = clean
    shared = raw.get("shared")
    if isinstance(shared, dict):
        for key, value in shared.items():
            width = clamp_col_w(value)
            if width is not None:
                out["shared"][str(key)] = width
    return out


def _normalize_gear(raw) -> dict:
    """配装槽位：只保留真给过来的槽，值收敛成「物品 id 或 None」。

    与 `_normalize_ui` 里图层开关一个思路——空 loadout 表示「用户还没配过装」，
    前端据此回退到本地偏好，而不是被一份空槽位表整体覆盖掉。
    空串 / 非字符串一律写 None（JSON null），表示「该槽是空的」，不写空串。
    """
    if not isinstance(raw, dict):
        return {}
    out: dict = {}
    for slot in GEAR_SLOTS:
        if slot in raw:
            out[slot] = _as_text(raw.get(slot))
    return out


# 钉选（搜索结果里钉住的「类型」）最多留这么多条，防止配置文件被写爆
PIN_MAX = 300


def _normalize_pins(raw) -> list[dict]:
    """钉选条目收敛成 `[{"kind": str, "name": str}, …]`（重复项去重，超量截断）。

    钉选是「按类型」钉的：kind + name 唯一确定一条（如 containers + 物资埋藏桶）。
    脏条目（缺 kind / name、类型不对）直接丢弃，非法的不写进配置。
    """
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        kind = _as_text(entry.get("kind"))
        name = _as_text(entry.get("name"))
        if not kind or not name:
            continue
        key = (kind, name)
        if key in seen:
            continue
        seen.add(key)
        out.append({"kind": kind, "name": name})
    return out[-PIN_MAX:]


def _normalize_ui(raw) -> dict:
    """页面偏好（图层开关 / 楼层开关 / 钉选 / 图标缩放 / 地名缩放与透明度）：只保留真给过来的键，没给就留空。

    不做默认值是有意的——空 `ui` 表示「还没保存过」，
    前端据此回退到本地偏好或内置默认，而不是被一份空偏好覆盖掉。
    """
    if not isinstance(raw, dict):
        return {}
    out: dict = {}
    layers = raw.get("layers")
    if isinstance(layers, dict):
        out["layers"] = {str(key): _as_bool(value, True) for key, value in layers.items()}
    if isinstance(raw.get("map"), str) and raw["map"].strip():
        out["map"] = raw["map"].strip()
    _scale = raw.get("icon_scale")
    if isinstance(_scale, (int, float)) and not isinstance(_scale, bool):
        # R98：icon_scale_v3=True 表示这份值已是 10%～190% 新刻度；
        # icon_scale_v2=True 是 R89 刻度（百分比，上限 545%），只用于读老配置；
        # 两者都没有的是更旧的 0.5～3，按旧区间收敛，前端读取时再 ÷0.55 迁移。
        _v3 = raw.get("icon_scale_v3") is True
        _v2 = raw.get("icon_scale_v2") is True
        out["icon_scale"] = clamp_icon_scale(_scale, v2=_v2, v3=_v3)
        if _v3:
            out["icon_scale_v3"] = True
        elif _v2:
            out["icon_scale_v2"] = True
    for key, clamp in (("label_scale", clamp_label_scale), ("label_alpha", clamp_label_alpha)):
        _value = raw.get(key)
        if isinstance(_value, (int, float)) and not isinstance(_value, bool):
            out[key] = clamp(_value)
    for key in ("floor_auto", "floor_filter"):
        if isinstance(raw.get(key), bool):
            out[key] = raw[key]
    if "pins" in raw:
        out["pins"] = _normalize_pins(raw.get("pins"))
    # 当前视图（配装视图用）：白名单外一律视为没给，前端自行回落 map
    view = _as_text(raw.get("view"))
    if view in VIEWS:
        out["view"] = view
    # 配装槽位：只要键在就整块收敛（六个槽一起给，缺的补 None）
    if "loadout" in raw:
        out["loadout"] = _normalize_gear(raw.get("loadout"))
    # 游戏内灵敏度：None 表示「没填」，前端据此显示空输入框
    if "sens" in raw:
        out["sens"] = clamp_sens(raw.get("sens"))
    # 表格列宽（配装工作台）：按类别 + 同名同义共享，结构固定，非法项丢弃
    if "colw" in raw:
        out["colw"] = normalize_colw(raw.get("colw"))
    return out


# ---------------------------------------------------------------- R241 截图识别设置
# 价格标签档位样式：按「当前口径的每件价格」分档上色。字号存的是**倍率**
# （相对 OCR 实测的游戏文字像素高）——各玩家分辨率 / UI 缩放不同，绝对像素必然错位，
# 实测高度才是唯一对得齐的基准（这也是不做游戏资源解包的原因）。
OCR_FONT_KEYS = ("msyh", "msyhbd", "simhei", "simsun")
OCR_FONT_NAMES = {"msyh": "微软雅黑", "msyhbd": "微软雅黑·粗", "simhei": "黑体", "simsun": "宋体"}
OCR_SCAN_TIERS_DEFAULT = [
    {"max": 50000, "color": "#b9c0c9", "sizeScale": 1.0, "font": "msyhbd",
     "outer": True, "outerColor": "#000000", "inner": False, "innerColor": "#000000"},
    {"max": 300000, "color": "#f2f2ee", "sizeScale": 1.0, "font": "msyhbd",
     "outer": True, "outerColor": "#000000", "inner": False, "innerColor": "#000000"},
    {"max": 1000000, "color": "#7fd48a", "sizeScale": 1.0, "font": "msyhbd",
     "outer": True, "outerColor": "#000000", "inner": False, "innerColor": "#000000"},
    {"max": None, "color": "#f2c14e", "sizeScale": 1.0, "font": "msyhbd",
     "outer": True, "outerColor": "#000000", "inner": False, "innerColor": "#000000"},
]
OCR_SCAN_DEFAULTS = {
    "hotkey": "ctrl+alt+p",
    "labelStyle": {"tiers": [dict(t) for t in OCR_SCAN_TIERS_DEFAULT]},
}


def _normalize_hex_color(v, fallback: str) -> str:
    s = str(v or "").strip()
    if re.fullmatch(r"#[0-9a-fA-F]{6}", s):
        return s.lower()
    return fallback


def _normalize_ocr_tier(raw, fallback: dict) -> dict:
    t = dict(fallback)
    if isinstance(raw, dict):
        mx = raw.get("max")
        if isinstance(mx, str) and mx.strip():
            try:
                mx = float(mx)          # 页面上限输入框传来的就是字符串
            except ValueError:
                mx = None
        t["max"] = int(mx) if isinstance(mx, (int, float)) and mx > 0 else None
        t["color"] = _normalize_hex_color(raw.get("color"), t["color"])
        try:
            t["sizeScale"] = round(min(3.0, max(0.5, float(raw.get("sizeScale", t["sizeScale"])))), 2)
        except (TypeError, ValueError):
            pass
        f = str(raw.get("font") or t["font"]).strip().lower()
        t["font"] = f if f in OCR_FONT_KEYS else "msyhbd"
        t["outer"] = _as_bool(raw.get("outer"), t["outer"])
        t["outerColor"] = _normalize_hex_color(raw.get("outerColor"), t["outerColor"])
        t["inner"] = _as_bool(raw.get("inner"), t["inner"])
        t["innerColor"] = _normalize_hex_color(raw.get("innerColor"), t["innerColor"])
    return t


def _normalize_ocr_scan(raw) -> dict:
    out = {"hotkey": OCR_SCAN_DEFAULTS["hotkey"],
           "fullScreen": False,
           "labelStyle": {"tiers": [dict(t) for t in OCR_SCAN_TIERS_DEFAULT],
                          "tierBasis": "overall"}}
    if isinstance(raw, dict):
        hk = str(raw.get("hotkey") or "").strip().lower()
        if hk and len(hk) <= 40:
            out["hotkey"] = hk
        if isinstance(raw.get("fullScreen"), bool):
            out["fullScreen"] = raw["fullScreen"]   # R255：全屏识别开关（所有人可用）
        ls = raw.get("labelStyle")
        if isinstance(ls, dict) and isinstance(ls.get("tiers"), list):
            tiers = [_normalize_ocr_tier(tr, OCR_SCAN_TIERS_DEFAULT[min(i, len(OCR_SCAN_TIERS_DEFAULT) - 1)])
                     for i, tr in enumerate(ls["tiers"][:6])]
            if tiers:
                # 有上限的按值升序在前，无上限（末档）殿后
                tiers.sort(key=lambda t: (t["max"] is None, t["max"] or 0))
                out["labelStyle"]["tiers"] = tiers
        # R259：配色依据（overall 整体 / perslot 单格），之前 save→normalize 会丢掉它
        if isinstance(ls, dict) and ls.get("tierBasis") in ("overall", "perslot"):
            out["labelStyle"]["tierBasis"] = ls["tierBasis"]
    return out


_DATA_SCOPE_MODES = ("regular", "pve", "pvps")


def _normalize_data_scope(raw) -> dict:
    """数据范围（R260）：只保留合法的 PvP/PvE/PvPS mode。

    截图识别（scan.current_mode）按这个 mode 取价，页面右上角选什么、识别就用什么。"""
    mode = "regular"
    if isinstance(raw, dict):
        m = str(raw.get("mode") or "").strip().lower()
        if m in _DATA_SCOPE_MODES:
            mode = m
    return {"mode": mode}


def merge_ui(cfg, prefs) -> dict:
    """把页面提交的偏好并进配置：只覆盖 `prefs` 里出现的键，其余原样保留。

    `prefs` 形如 `{"auto_center": true, "ui": {"layers": {...}, "floor_auto": true}}`。
    `auto_center` 与启动器里的「点位自动居中」共用同一个键，所以页面点按钮也会同步过去。
    """
    merged = normalize(cfg)
    if isinstance(prefs, dict) and isinstance(prefs.get("auto_center"), bool):
        merged["auto_center"] = prefs["auto_center"]

    # R106：页面「自动截图」勾选只覆盖 enabled（间隔 / 键仍归启动器管，别被页面写回旧值）
    # R107：页面新增间隔输入与「战局结束清理」勾选，只覆盖这两个字段，其余仍归启动器管
    if isinstance(prefs, dict) and isinstance(prefs.get("auto_screenshot"), dict):
        shot = prefs["auto_screenshot"]
        if isinstance(shot.get("enabled"), bool):
            merged["auto_screenshot"]["enabled"] = shot["enabled"]
        if "interval_ms" in shot:
            # R108：落盘值也按会员态钳一次（非会员 = 10000），避免配置文件里留一个
            # 「看起来可调、实际不生效」的值；页面 prefs 不能改 account.member。
            merged["auto_screenshot"]["interval_ms"] = clamp_interval(
                shot.get("interval_ms"), merged["account"]["member"])
        if isinstance(shot.get("cleanup_on_raid_end"), bool):
            merged["auto_screenshot"]["cleanup_on_raid_end"] = shot["cleanup_on_raid_end"]
        # R308：启动器移除后，截图键改为页面手动设置；空值/None = 清掉手动值，
        # 回到「自动读取游戏 Control.ini / 日志绑定」。
        if "key" in shot and (shot["key"] is None or isinstance(shot["key"], str)):
            merged["auto_screenshot"]["key"] = _as_text(shot["key"])

    # R107：页面可直接改日志目录 / 截图目录；空串 = 清掉手动值，退回自动探测
    if isinstance(prefs, dict):
        for key in ("log_dir", "screenshots_dir"):
            if key in prefs and (prefs[key] is None or isinstance(prefs[key], str)):
                merged[key] = _as_text(prefs[key])

    # 小浮窗设置（大小 / 位置 / 透明度）：页面「设置」菜单直接发整段，逐键覆盖
    if isinstance(prefs, dict) and isinstance(prefs.get("overlay"), dict):
        base = dict(merged.get("overlay") or {})
        incoming_overlay = dict(prefs["overlay"])
        # R106：旧客户端仍可能只发 map_scale；先迁移成 mini_radius_m，否则已归一化的
        # base.mini_radius_m 会永远压过旧值，表现为「改了缩放但小地图不动」。
        if "mini_radius_m" not in incoming_overlay and "map_scale" in incoming_overlay:
            incoming_overlay["mini_radius_m"] = mini_radius_from_map_scale(incoming_overlay["map_scale"])
        base.update(incoming_overlay)
        merged["overlay"] = _normalize_overlay(base)

    # R260：页面右上角选的模式（PvP/PvE/PvPS）也写进配置，供截图识别按同一模式取价。
    if isinstance(prefs, dict) and isinstance(prefs.get("dataScope"), dict):
        m = str(prefs["dataScope"].get("mode") or "").strip().lower()
        if m in _DATA_SCOPE_MODES:
            merged["dataScope"] = {"mode": m}

    # R241：截图识别设置。热键所有人可改；档位样式仅会员——非会员丢弃传入的
    # labelStyle（UI 有锁，这里兜住手搓请求直接写配置绕锁的情况）。
    if isinstance(prefs, dict) and isinstance(prefs.get("ocrScan"), dict):
        ocr = prefs["ocrScan"]
        base = dict(merged.get("ocrScan") or _normalize_ocr_scan(None))
        hk = ocr.get("hotkey")
        if isinstance(hk, str) and 0 < len(hk.strip()) <= 40:
            base["hotkey"] = hk.strip().lower()
        # R259：全屏识别开关——之前漏拷此键，勾选后保存仍为 false，页面回声把它弹回未勾选
        if isinstance(ocr.get("fullScreen"), bool):
            base["fullScreen"] = ocr["fullScreen"]
        if merged["account"]["member"] and isinstance(ocr.get("labelStyle"), dict):
            # R259：逐键合并——只改档位颜色时 prefs 不带 tierBasis，整体替换会把
            # 用户选的「单格/整体」配色依据冲掉。save() → normalize() 再收敛一遍。
            ls = dict(base.get("labelStyle") or {})
            ls.update(ocr["labelStyle"])
            base["labelStyle"] = ls
        merged["ocrScan"] = base

    incoming = _normalize_ui(prefs.get("ui") if isinstance(prefs, dict) else None)
    ui = dict(merged.get("ui") or {})
    if "layers" in incoming:
        # 与已有开关合并，避免只发部分键就把别的键清掉
        layers = dict(ui.get("layers") or {})
        layers.update(incoming["layers"])
        ui["layers"] = layers
    if "loadout" in incoming:
        # 同上：逐槽合并，避免只发其中一个槽就把别的槽清空
        gear = dict(ui.get("loadout") or {})
        gear.update(incoming["loadout"])
        ui["loadout"] = gear
    for key in ("map", "floor_auto", "floor_filter", "pins", "icon_scale", "icon_scale_v2",
                "icon_scale_v3", "label_scale", "label_alpha", "view", "sens", "colw"):
        if key in incoming:
            ui[key] = incoming[key]
    merged["ui"] = ui
    return merged


def normalize(raw) -> dict:
    """把任意来源的配置收敛成完整的、类型正确的配置（缺项补默认，脏项丢弃）。"""
    cfg = default_config()
    if not isinstance(raw, dict):
        return cfg

    cfg["host"] = clamp_host(raw.get("host"))
    cfg["game_dir"] = _as_text(raw.get("game_dir"))
    cfg["screenshots_dir"] = _as_text(raw.get("screenshots_dir"))
    cfg["log_dir"] = _as_text(raw.get("log_dir"))
    cfg["auto_zoom"] = _as_bool(raw.get("auto_zoom"), False)
    cfg["auto_center"] = _as_bool(raw.get("auto_center"), True)
    cfg["auto_start"] = _as_bool(raw.get("auto_start"), False)

    # R108 / 会员模型：会员态只认服务端下发（进程内快照，见 set_member_state）。
    # 配置文件里的 account.member 一律忽略，手改不再能解锁；页面 prefs 也不参与。
    cfg["account"] = {"member": is_member()}
    member = cfg["account"]["member"]

    shot = raw.get("auto_screenshot")
    if isinstance(shot, dict):
        cfg["auto_screenshot"]["enabled"] = _as_bool(shot.get("enabled"), False)
        cfg["auto_screenshot"]["interval_ms"] = clamp_interval(shot.get("interval_ms"), member)
        cfg["auto_screenshot"]["key"] = _as_text(shot.get("key"))
        cfg["auto_screenshot"]["cleanup_on_raid_end"] = _as_bool(shot.get("cleanup_on_raid_end"), False)
    else:
        # 没写 interval：非会员落锁定值，会员落 5 秒默认（default_config 的默认值面向非会员）
        cfg["auto_screenshot"]["interval_ms"] = clamp_interval(SHOT_INTERVAL_DEFAULT, member)

    delete = raw.get("auto_delete")
    if isinstance(delete, dict):
        cfg["auto_delete"]["enabled"] = _as_bool(delete.get("enabled"), False)
        cfg["auto_delete"]["since"] = _as_float(delete.get("since"))

    sound = raw.get("sound")
    if isinstance(sound, dict):
        cfg["sound"]["enabled"] = _as_bool(sound.get("enabled"), False)
        for key in SOUND_KEYS:
            sub = sound.get(key)
            if isinstance(sub, dict):
                cfg["sound"][key]["on"] = _as_bool(sub.get("on"), True)
                cfg["sound"][key]["file"] = _as_text(sub.get("file"))

    cfg["overlay"] = _normalize_overlay(raw.get("overlay"))
    cfg["livePrices"] = _normalize_live_prices(raw.get("livePrices"))
    cfg["ocrScan"] = _normalize_ocr_scan(raw.get("ocrScan"))
    cfg["dataScope"] = _normalize_data_scope(raw.get("dataScope"))
    cfg["ui"] = _normalize_ui(raw.get("ui"))
    return cfg


# ---------------------------------------------------------------- 读写
def load(directory: str | None = None) -> dict:
    """读配置；文件不存在 / 损坏 / 权限不足一律回退到默认配置（不抛异常）。"""
    try:
        with open(config_path(directory), "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, ValueError):
        return default_config()
    return normalize(raw)


def save(cfg, directory: str | None = None) -> dict:
    """写配置（先写临时文件再原子替换，避免半截文件把配置写坏）。返回落盘后的配置。"""
    directory = directory or default_storage_dir()
    payload = normalize(cfg)
    path = config_path(directory)
    os.makedirs(directory, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    # Windows：扫描宿主 / ConfigWatcher 正在读配置时，os.replace 可能瞬时
    # PermissionError（WinError 5/32，目标被占用）——短暂退避重试，避免偶发
    # 保存 500（页面回声把刚勾的开关弹回去，表现为「勾不上」）。
    for attempt in range(6):
        try:
            os.replace(tmp, path)
            return payload
        except PermissionError:
            if attempt == 5:
                raise
            time.sleep(0.03 * (attempt + 1))
    return payload


# ---------------------------------------------------------------- 音频文件
def _safe_name(stem: str) -> str:
    """把文件名洗成安全的 ASCII 主干（保留中文/字母数字，去掉路径与非法字符）。"""
    cleaned = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", stem).strip(" ._")
    return cleaned or "sound"


def import_sound(src: str, directory: str | None = None) -> str:
    """把用户选的音频复制进 `sounds/`，返回落盘后的文件名（配置里只存这个名字）。

    重名不覆盖已有文件，自动加 `_1`、`_2` 后缀；源文件已经在 `sounds/` 里时直接复用。
    """
    if not src or not os.path.isfile(src):
        raise FileNotFoundError("找不到音频文件：%s" % src)
    ext = os.path.splitext(src)[1].lower()
    if ext not in AUDIO_EXTS:
        raise ValueError("不支持的音频格式：%s（支持 %s）" % (ext or "未知", "/".join(AUDIO_EXTS)))

    target_dir = ensure_sounds_dir(directory)
    stem = _safe_name(os.path.splitext(os.path.basename(src))[0])
    name = stem + ext
    dest = os.path.join(target_dir, name)
    if os.path.abspath(src) != os.path.abspath(dest):
        index = 1
        while os.path.exists(dest):
            name = "%s_%d%s" % (stem, index, ext)
            dest = os.path.join(target_dir, name)
            index += 1
        shutil.copyfile(src, dest)
    return name


def resolve_sound(name: str | None, directory: str | None = None) -> str | None:
    """配置里的音频文件名 → 实际存在的绝对路径；不存在返回 None。"""
    if not name:
        return None
    path = os.path.join(sounds_dir(directory), name)
    return path if os.path.isfile(path) else None
