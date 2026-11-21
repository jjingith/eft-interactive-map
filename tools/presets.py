"""用户预设的本地持久化（人物装备方案 / 枪械改装方案）。

存储位置与 ``eftmap.config.json`` 同级，都在用户级目录
（Windows = ``%APPDATA%\\EFTMap``，其它平台 = ``~/.eftmap``），
重新打包 / 换安装目录都不会丢；**绝不写回** ``data/gunslots.json`` 等随包数据。

只依赖标准库。写盘采用「临时文件 + fsync + os.replace」的原子替换，
读取时做严格结构校验：文件损坏会抛出 ``PresetError(corrupt=True)``，
由调用方把它显示给用户，**不会静默用空数据覆盖原文件**。
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from typing import Any

import config

LOADOUT_KIND = "loadout"
WEAPON_KIND = "weapon"
KINDS = (LOADOUT_KIND, WEAPON_KIND)

FILE_NAMES = {
    LOADOUT_KIND: "loadout-presets.json",
    WEAPON_KIND: "weapon-presets.json",
}
VERSION = 1
MAX_PRESETS = 500
MAX_SLOTS = 400
MAX_NAME = 80
MAX_BODY = 4 * 1024 * 1024

ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
PRICE_MODES = ("flea", "pvp", "scav", "base")


class PresetError(Exception):
    """预设读写 / 校验错误。``corrupt`` 为真表示磁盘上的旧文件本身已损坏。"""

    def __init__(self, message: str, code: str = "invalid", corrupt: bool = False):
        super().__init__(message)
        self.code = code
        self.corrupt = corrupt


def store_path(kind: str, directory: str | None = None) -> str:
    if kind not in FILE_NAMES:
        raise PresetError("未知的预设类型：%s" % kind, code="kind")
    return os.path.join(directory or config.default_storage_dir(), FILE_NAMES[kind])


def new_id(kind: str) -> str:
    """稳定且不可猜测的预设 ID（时间戳 + 随机段，重命名不会改变它）。"""
    prefix = "lp" if kind == LOADOUT_KIND else "wp"
    return "%s_%s%s" % (prefix, format(int(time.time() * 1000), "x"), uuid.uuid4().hex[:8])


def _iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _text(value: Any, field: str, limit: int = 200) -> str:
    if not isinstance(value, str):
        raise PresetError("%s 必须是字符串" % field)
    out = value.strip()
    if not out:
        raise PresetError("%s 不能为空" % field)
    if len(out) > limit:
        raise PresetError("%s 超过 %d 个字符" % (field, limit))
    return out


def _timestamp(value: Any, fallback: str) -> str:
    if isinstance(value, str) and 10 <= len(value) <= 40:
        return value
    return fallback


def _slots(value: Any) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise PresetError("slots 必须是对象（槽位 id → 物品 id）")
    if len(value) > MAX_SLOTS:
        raise PresetError("槽位数量超过上限 %d" % MAX_SLOTS)
    out: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key or len(key) > 160:
            raise PresetError("槽位键非法：%r" % (key,))
        if not isinstance(item, str) or not item:
            raise PresetError("槽位 %s 的物品 id 非法" % key)
        if len(item) > 96:
            raise PresetError("槽位 %s 的物品 id 过长" % key)
        out[key] = item
    return out


def normalize_preset(kind: str, raw: Any) -> dict:
    """把任意来源（前端 / 导入文件）的单个预设压成受控结构。"""
    if not isinstance(raw, dict):
        raise PresetError("预设必须是 JSON 对象")
    now = _iso_now()
    pid = raw.get("id")
    if pid is None or pid == "":
        pid = new_id(kind)
    elif not isinstance(pid, str) or not ID_RE.match(pid):
        raise PresetError("预设 id 非法（只允许字母 / 数字 / 下划线 / 连字符）：%r" % (pid,))
    name = _text(raw.get("name"), "预设名称", MAX_NAME)
    created = _timestamp(raw.get("createdAt"), now)
    updated = _timestamp(raw.get("updatedAt"), created)

    if kind == LOADOUT_KIND:
        slots = _slots(raw.get("slots"))
        mode = raw.get("priceMode")
        if mode is not None and mode not in PRICE_MODES:
            raise PresetError("未知价格档：%r" % (mode,))
        sens = raw.get("sens")
        if sens is not None:
            try:
                sens = float(sens)
            except (TypeError, ValueError):
                raise PresetError("灵敏度必须是数字")
            if not (0.0 <= sens <= 1.0):
                raise PresetError("灵敏度必须在 0–1 之间")
        out = {"id": pid, "name": name, "createdAt": created, "updatedAt": updated,
               "slots": slots}
        if mode:
            out["priceMode"] = mode
        if sens is not None:
            out["sens"] = sens
        return out

    gun = _text(raw.get("gunId"), "基础枪械 id", 96)
    items = _slots(raw.get("items"))
    return {"id": pid, "name": name, "createdAt": created, "updatedAt": updated,
            "gunId": gun, "items": items}


def empty_store(kind: str) -> dict:
    return {"version": VERSION, "kind": kind, "presets": []}


def normalize_store(kind: str, raw: Any) -> dict:
    if not isinstance(raw, dict):
        raise PresetError("预设文件根节点必须是 JSON 对象")
    presets = raw.get("presets")
    if presets is None:
        presets = []
    if not isinstance(presets, list):
        raise PresetError("presets 必须是数组")
    if len(presets) > MAX_PRESETS:
        raise PresetError("预设数量超过上限 %d" % MAX_PRESETS)
    out = []
    seen = set()
    for item in presets:
        rec = normalize_preset(kind, item)
        if rec["id"] in seen:
            raise PresetError("预设 id 重复：%s" % rec["id"])
        seen.add(rec["id"])
        out.append(rec)
    return {"version": VERSION, "kind": kind, "presets": out}


def load(kind: str, directory: str | None = None) -> dict:
    """读预设文件。不存在 → 空结构；存在但损坏 → 抛 corrupt 错误。"""
    path = store_path(kind, directory)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except FileNotFoundError:
        return empty_store(kind)
    except (OSError, ValueError) as exc:
        raise PresetError("预设文件无法读取（已损坏或没有权限）：%s" % exc,
                          code="corrupt", corrupt=True)
    try:
        return normalize_store(kind, raw)
    except PresetError as exc:
        exc.corrupt = True
        exc.code = "corrupt"
        raise


def save(kind: str, payload: Any, directory: str | None = None,
         repair: bool = False) -> dict:
    """整包校验后原子写入。

    若磁盘上已有文件且已损坏，默认拒绝覆盖（``repair=False``），
    避免用户一次误操作把还能人工修复的数据冲掉。
    """
    store = normalize_store(kind, payload)
    path = store_path(kind, directory)
    if os.path.exists(path):
        try:
            load(kind, directory)
        except PresetError as exc:
            if exc.corrupt and not repair:
                raise PresetError(
                    "磁盘上的预设文件已损坏，已拒绝覆盖。请先备份 / 删除该文件，"
                    "或在界面上确认「修复并覆盖」后再保存。",
                    code="corrupt", corrupt=True)
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(store, fh, ensure_ascii=False, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    return store


def upsert(kind: str, raw: Any, store: dict) -> tuple[dict, dict]:
    """新增或覆盖单条预设（按 id 匹配），返回 (新 store, 该条记录)。

    覆盖时保留原 ``createdAt`` 并把 ``updatedAt`` 刷成当前时间；
    新记录直接追加。id 由前端沿用或由 :func:`new_id` 生成，名称可重名。
    """
    rec = normalize_preset(kind, raw)
    store = normalize_store(kind, store)
    rec["updatedAt"] = _iso_now()
    for idx, cur in enumerate(store["presets"]):
        if cur["id"] == rec["id"]:
            rec["createdAt"] = cur["createdAt"]
            store["presets"][idx] = rec
            return store, rec
    if len(store["presets"]) >= MAX_PRESETS:
        raise PresetError("预设数量已达上限 %d" % MAX_PRESETS, code="limit")
    store["presets"].append(rec)
    return store, rec


def remove(kind: str, pid: Any, store: dict) -> tuple[dict, dict]:
    """按 id 删除一条预设，返回 (新 store, 被删记录)；不存在时报错而不是静默成功。"""
    if not isinstance(pid, str) or not ID_RE.match(pid):
        raise PresetError("预设 id 非法：%r" % (pid,), code="id")
    store = normalize_store(kind, store)
    keep = [p for p in store["presets"] if p["id"] != pid]
    if len(keep) == len(store["presets"]):
        raise PresetError("预设不存在：%s" % pid, code="missing")
    gone = [p for p in store["presets"] if p["id"] == pid][0]
    return dict(store, presets=keep), gone


def import_one(kind: str, raw: Any, existing: dict) -> tuple[dict, dict]:
    """导入单个预设（或整包），id 冲突时换新 id，绝不覆盖同名方案。"""
    items = raw.get("presets") if isinstance(raw, dict) and isinstance(raw.get("presets"), list) \
        else [raw]
    if not items:
        raise PresetError("导入文件里没有预设")
    store = normalize_store(kind, existing)
    have = {p["id"] for p in store["presets"]}
    added = []
    for item in items:
        rec = normalize_preset(kind, item)
        if rec["id"] in have:
            rec["id"] = new_id(kind)
        have.add(rec["id"])
        rec["updatedAt"] = _iso_now()
        store["presets"].append(rec)
        added.append(rec)
    if len(store["presets"]) > MAX_PRESETS:
        raise PresetError("导入后预设数量超过上限 %d" % MAX_PRESETS)
    return store, added[0] if len(added) == 1 else {"count": len(added)}


def summary(store: dict) -> dict:
    return {"version": store.get("version", VERSION),
            "kind": store.get("kind"),
            "count": len(store.get("presets") or []),
            "presets": store.get("presets") or []}
