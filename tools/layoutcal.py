# -*- coding: utf-8 -*-
"""R19.16 武器槽位布局校准数据（data/gun-layout-calibration.json）的读写与校验。

设计约束（对应任务书第七、八、十二节）：

* 只读写**一个**固定文件，路径由服务端拼出，客户端无法传入任意路径；
* 只保存**逻辑网格行列**（`logicalRow` / `col`），同时记录当时的 `topPad` 与显示行列，
  顶部扩展前后不会把人工坐标解释错；
* 槽位身份 = 枪械 ID + 完整槽位路径 + 槽位 ID + **拥有该子槽的物品 ID**，
  避免同名槽位在不同父件下串用坐标；
* 写入前整包校验，写入用「临时文件 + fsync + os.replace」原子替换；
* 每次成功保存前把上一版复制为 `.bak.json`，支持「恢复上一版」；
* 绝不触碰 items.json / gun-compat.json / 用户预设。

本模块只用标准库，可被 pytest 直接调用（无需起服务）。
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import time
from typing import Any

SCHEMA_VERSION = 1
TOOL_VERSION = "R19.16"
FILENAME = "gun-layout-calibration.json"
BACKUP_SUFFIX = ".bak.json"
MAX_GUNS = 400
MAX_SLOTS_PER_GUN = 400
ROW_MIN, ROW_MAX = -6, 6          # 顶部扩展后的逻辑行范围
COL_MIN, COL_MAX = 1, 9
MAX_NOTE = 200


class CalibrationError(Exception):
    """校学校验失败。``code`` 供界面判断是「请求不合法」还是「磁盘文件损坏」。"""

    def __init__(self, message: str, code: str = "invalid", corrupt: bool = False):
        super().__init__(message)
        self.code = code
        self.corrupt = corrupt


def path_for(directory: str | None = None) -> str:
    base = directory or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "data", FILENAME)


def backup_path_for(directory: str | None = None) -> str:
    return path_for(directory) + BACKUP_SUFFIX


def empty_doc() -> dict:
    return {"schemaVersion": SCHEMA_VERSION, "toolVersion": TOOL_VERSION,
            "updatedAt": None, "guns": {}}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _check_text(v: Any, field: str, limit: int = 200) -> str:
    if not isinstance(v, str) or not v.strip():
        raise CalibrationError("%s 必须是非空字符串" % field)
    if len(v) > limit:
        raise CalibrationError("%s 过长（上限 %d 字符）" % (field, limit))
    return v


def _is_stale_note(note: str) -> bool:
    """失效注记判定（项目约定自 R19.18）：note 含「不再生效」= 只存档不生效的记录。"""
    return "不再生效" in (note or "")


def validate_slot_entry(raw: Any) -> dict:
    """校验单个槽位校准记录，返回规范化副本。"""
    if not isinstance(raw, dict):
        raise CalibrationError("槽位记录必须是对象")
    slot_path = _check_text(raw.get("slotPath"), "slotPath", 260)
    if not slot_path.startswith("mod_") and "/" not in slot_path:
        raise CalibrationError("slotPath 必须是以 mod_ 开头的真实槽位路径：%s" % slot_path)
    for seg in slot_path.split("/"):
        if not seg or len(seg) > 80 or " " in seg:
            raise CalibrationError("slotPath 段不合法：%s" % slot_path)
    slot_id = _check_text(raw.get("slotId"), "slotId", 120)
    owner = raw.get("ownerItemId") or ""
    if not isinstance(owner, str) or len(owner) > 120:
        raise CalibrationError("ownerItemId 必须是不超过 120 字符的字符串")
    row = raw.get("logicalRow", raw.get("row"))
    col = raw.get("col")
    if not _is_int(row) or not _is_int(col):
        raise CalibrationError("行列必须是整数：%r / %r" % (row, col))
    if not (ROW_MIN <= row <= ROW_MAX):
        raise CalibrationError("行号 %d 超出允许范围 %d..%d" % (row, ROW_MIN, ROW_MAX))
    if not (COL_MIN <= col <= COL_MAX):
        raise CalibrationError("列号 %d 超出允许范围 %d..%d" % (col, COL_MIN, COL_MAX))
    note = raw.get("note") or ""
    if not isinstance(note, str):
        raise CalibrationError("note 必须是字符串")
    if len(note) > MAX_NOTE:
        raise CalibrationError("note 过长（上限 %d 字符）" % MAX_NOTE)
    role = raw.get("role") or ""
    if role and not isinstance(role, str):
        raise CalibrationError("role 必须是字符串")
    top_pad = raw.get("topPad", 0)
    if top_pad is not None and (not _is_int(top_pad) or not (0 <= top_pad <= 6)):
        raise CalibrationError("topPad 必须是 0..6 的整数")
    display_row = raw.get("displayRow")
    if display_row is not None and not _is_int(display_row):
        raise CalibrationError("displayRow 必须是整数")
    return {
        "slotId": slot_id,
        "slotPath": slot_path,
        "ownerItemId": owner,
        "logicalRow": row,
        "col": col,
        "topPad": top_pad or 0,
        "displayRow": display_row if display_row is not None else None,
        "role": role,
        "source": raw.get("source") or "manual",
        "note": note,
        "updatedAt": raw.get("updatedAt") or _now(),
        "autoRow": raw.get("autoRow"),
        "autoCol": raw.get("autoCol"),
    }


def slot_key(entry: dict) -> str:
    """槽位唯一身份：路径 + 槽位 ID + 拥有者物品 ID（同名槽位在不同父件下不会串用）。"""
    return "%s|%s|%s" % (entry["slotPath"], entry["slotId"], entry.get("ownerItemId") or "")


def validate_gun(raw: Any, gun_id: str, known_guns: set[str] | None = None) -> dict:
    if known_guns is not None and gun_id not in known_guns:
        raise CalibrationError("未知枪械 ID：%s" % gun_id)
    if not isinstance(raw, dict):
        raise CalibrationError("gun 必须是对象")
    slots_in = raw.get("slots")
    if not isinstance(slots_in, dict):
        raise CalibrationError("gun.slots 必须是 {身份: 校准记录} 对象")
    if len(slots_in) > MAX_SLOTS_PER_GUN:
        raise CalibrationError("单把枪的校准槽位过多（上限 %d）" % MAX_SLOTS_PER_GUN)
    slots: dict[str, dict] = {}
    used: dict[str, str] = {}
    for key, entry in slots_in.items():
        _check_text(key, "校准键", 320)
        norm = validate_slot_entry(entry)
        expect = slot_key(norm)
        if key != expect:
            raise CalibrationError("校准键与记录不一致：%s ≠ %s" % (key, expect))
        pos = "%d|%d" % (norm["logicalRow"], norm["col"])
        # R19.20：失效注记记录（note 含「不再生效」——R19.18 起的项目约定标记）只存档、
        # 不参与同格占位（对应真实条件子槽已被数据层移除，运行时也不会被套用）。
        # 活跃记录同格仍然拒绝，保留保存时的防重叠保护。
        if not _is_stale_note(norm.get("note") or ""):
            if pos in used:
                raise CalibrationError(
                    "同一把枪的两个槽位被校准到同一格 r%dc%d（%s 与 %s）；"
                    "请先调整其中之一再保存" % (norm["logicalRow"], norm["col"], used[pos], key))
            used[pos] = key
        slots[key] = norm
    name = raw.get("name")
    if name is not None and not isinstance(name, str):
        raise CalibrationError("gun.name 必须是字符串")
    history = raw.get("history")
    if history is not None and not isinstance(history, list):
        raise CalibrationError("gun.history 必须是数组")
    return {
        "name": (name or "")[:120],
        "updatedAt": raw.get("updatedAt") or _now(),
        "slots": slots,
        "history": (history or [])[-50:],
    }


def validate_doc(raw: Any, known_guns: set[str] | None = None) -> dict:
    """整包校验，返回规范化文档（不改动传入对象）。"""
    if not isinstance(raw, dict):
        raise CalibrationError("校准数据必须是 JSON 对象")
    ver = raw.get("schemaVersion", SCHEMA_VERSION)
    if not _is_int(ver) or ver != SCHEMA_VERSION:
        raise CalibrationError("schemaVersion 不支持：%r（当前只接受 %d）" % (ver, SCHEMA_VERSION))
    guns_in = raw.get("guns")
    if not isinstance(guns_in, dict):
        raise CalibrationError("guns 必须是对象")
    if len(guns_in) > MAX_GUNS:
        raise CalibrationError("枪械条目过多（上限 %d）" % MAX_GUNS)
    guns: dict[str, dict] = {}
    for gid, gun in guns_in.items():
        _check_text(gid, "gunId", 64)
        guns[gid] = validate_gun(gun, gid, known_guns)
    return {"schemaVersion": SCHEMA_VERSION,
            "toolVersion": raw.get("toolVersion") or TOOL_VERSION,
            "updatedAt": raw.get("updatedAt") or _now(),
            "guns": guns}


def load(directory: str | None = None, known_guns: set[str] | None = None) -> dict:
    """读取校准文件；文件不存在时返回空文档（不是错误）。文件损坏时报 corrupt。"""
    path = path_for(directory)
    if not os.path.exists(path):
        return empty_doc()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        raise CalibrationError("校准文件无法解析：%s" % exc, code="corrupt", corrupt=True)
    try:
        return validate_doc(raw, known_guns)
    except CalibrationError as exc:
        exc.corrupt = True
        exc.code = "corrupt"
        raise


def load_backup(directory: str | None = None) -> dict | None:
    path = backup_path_for(directory)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _atomic_write(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def save(doc: dict, directory: str | None = None, known_guns: set[str] | None = None,
         backup: bool = True) -> dict:
    """整包校验 → 备份上一版 → 原子写入。返回写入后的文档。"""
    norm = validate_doc(doc, known_guns)
    norm["updatedAt"] = _now()
    path = path_for(directory)
    if backup and os.path.exists(path):
        try:
            shutil.copy2(path, backup_path_for(directory))
        except OSError:
            pass
    _atomic_write(path, norm)
    return norm


def merge_gun(doc: dict, gun_id: str, gun: dict, known_guns: set[str] | None = None) -> dict:
    """把单把枪的校准并入整包（其余枪保持不变）。"""
    out = copy.deepcopy(doc)
    out.setdefault("guns", {})
    out["guns"][gun_id] = gun
    return validate_doc(out, known_guns)


def drop_gun(doc: dict, gun_id: str) -> dict:
    out = copy.deepcopy(doc)
    out.get("guns", {}).pop(gun_id, None)
    return out


def restore_backup(directory: str | None = None, known_guns: set[str] | None = None) -> dict:
    """用上一版备份覆盖当前校准（当前版本另存为 .prev 便于回退）。"""
    bak = backup_path_for(directory)
    if not os.path.exists(bak):
        raise CalibrationError("没有可恢复的上一版备份", code="no-backup")
    with open(bak, "r", encoding="utf-8") as fh:
        raw = json.load(fh)
    doc = validate_doc(raw, known_guns)
    path = path_for(directory)
    if os.path.exists(path):
        try:
            shutil.copy2(path, path + ".prev.json")
        except OSError:
            pass
    _atomic_write(path, doc)
    return doc


def summary(doc: dict) -> dict:
    guns = doc.get("guns") or {}
    slots = sum(len((g or {}).get("slots") or {}) for g in guns.values())
    return {"guns": len(guns), "slots": slots, "updatedAt": doc.get("updatedAt"),
            "schemaVersion": doc.get("schemaVersion"), "toolVersion": doc.get("toolVersion")}
