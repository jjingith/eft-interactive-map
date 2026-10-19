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

import json
import os
import re
import shutil
import sys

CONFIG_NAME = "eftmap.config.json"
SOUNDS_DIRNAME = "sounds"
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
SHOT_INTERVAL_DEFAULT = 1000
SHOT_INTERVAL_MIN = 200
SHOT_INTERVAL_MAX = 60000


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
        "game_dir": None,
        "screenshots_dir": None,
        "auto_zoom": False,
        "auto_center": True,
        "auto_start": False,
        "auto_screenshot": {
            "enabled": False,
            "interval_ms": SHOT_INTERVAL_DEFAULT,
            "key": None,
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
        "ui": {},
    }


def clamp_interval(value) -> int:
    """把截图间隔钳到 [SHOT_INTERVAL_MIN, SHOT_INTERVAL_MAX] 的整数毫秒；脏值回落默认。"""
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return SHOT_INTERVAL_DEFAULT
    return max(SHOT_INTERVAL_MIN, min(SHOT_INTERVAL_MAX, number))


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
    """页面偏好（图层开关 / 楼层开关 / 钉选）：只保留真给过来的键，没给就留空。

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
    for key in ("floor_auto", "floor_filter"):
        if isinstance(raw.get(key), bool):
            out[key] = raw[key]
    if "pins" in raw:
        out["pins"] = _normalize_pins(raw.get("pins"))
    return out


def merge_ui(cfg, prefs) -> dict:
    """把页面提交的偏好并进配置：只覆盖 `prefs` 里出现的键，其余原样保留。

    `prefs` 形如 `{"auto_center": true, "ui": {"layers": {...}, "floor_auto": true}}`。
    `auto_center` 与启动器里的「点位自动居中」共用同一个键，所以页面点按钮也会同步过去。
    """
    merged = normalize(cfg)
    if isinstance(prefs, dict) and isinstance(prefs.get("auto_center"), bool):
        merged["auto_center"] = prefs["auto_center"]

    incoming = _normalize_ui(prefs.get("ui") if isinstance(prefs, dict) else None)
    ui = dict(merged.get("ui") or {})
    if "layers" in incoming:
        # 与已有开关合并，避免只发部分键就把别的键清掉
        layers = dict(ui.get("layers") or {})
        layers.update(incoming["layers"])
        ui["layers"] = layers
    for key in ("map", "floor_auto", "floor_filter", "pins"):
        if key in incoming:
            ui[key] = incoming[key]
    merged["ui"] = ui
    return merged


def normalize(raw) -> dict:
    """把任意来源的配置收敛成完整的、类型正确的配置（缺项补默认，脏项丢弃）。"""
    cfg = default_config()
    if not isinstance(raw, dict):
        return cfg

    cfg["game_dir"] = _as_text(raw.get("game_dir"))
    cfg["screenshots_dir"] = _as_text(raw.get("screenshots_dir"))
    cfg["auto_zoom"] = _as_bool(raw.get("auto_zoom"), False)
    cfg["auto_center"] = _as_bool(raw.get("auto_center"), True)
    cfg["auto_start"] = _as_bool(raw.get("auto_start"), False)

    shot = raw.get("auto_screenshot")
    if isinstance(shot, dict):
        cfg["auto_screenshot"]["enabled"] = _as_bool(shot.get("enabled"), False)
        cfg["auto_screenshot"]["interval_ms"] = clamp_interval(shot.get("interval_ms"))
        cfg["auto_screenshot"]["key"] = _as_text(shot.get("key"))

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
    os.replace(tmp, path)
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
