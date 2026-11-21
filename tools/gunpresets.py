"""内置枪械参考预设的**构建期还原**（纯函数，产物是 `data/gun-presets.json`）。

上游 497 套内置预设只在 Preset 物品的 `containsItems` 里给配件清单，且**没有槽位路径**；
本模块把这些配件按基础枪械真实的 `slots[].allow` 关系回溯分配到槽位上，得到可直接装载的
`{槽位路径: 配件 id}`。槽位路径由上游 `slotId` 的 `sid`（如 `mod_reciever/mod_barrel`）拼成。

三个原则：

- **只信上游字段**：能不能装只看 `slots[].allow`；解不出来就标 `unsolved`，不接近似推断；
- **不写回源数据**：产物是独立文件，`data/gunslots.json` 保持原样；
- **确定性**：候选按（可放槽位数, 物品 id）排序回溯，同一输入永远同一结果。
"""
from __future__ import annotations

from collections import Counter

SCHEMA = 1
MAX_NODES = 40000     # 单套预设的回溯节点上限：防止病态数据把构建卡死


def slot_paths(record: dict, prefix: str = "") -> list[tuple[str, list, dict]]:
    """父物品的子槽列表 → `[(路径, allow, 原始槽定义), …]`；重复 `sid` 追加 `#序号`。"""
    out = []
    used: dict = {}
    for i, slot in enumerate((record or {}).get("slots") or []):
        sid = slot.get("sid") or ("s%d" % i)
        used[sid] = used.get(sid, -1) + 1
        if used[sid] > 0:
            sid = "%s#%d" % (sid, used[sid])
        path = (prefix + "/" + sid) if prefix else sid
        out.append((path, slot.get("allow") or [], slot))
    return out


def _parts(preset_record: dict) -> list[str]:
    """Preset 物品的 `ci`（[[配件 id, 数量], …]）展开成多重集。"""
    out = []
    for entry in (preset_record or {}).get("ci") or []:
        if not isinstance(entry, (list, tuple)) or not entry:
            continue
        item_id = entry[0]
        try:
            count = int(entry[1]) if len(entry) > 1 else 1
        except (TypeError, ValueError):
            count = 1
        out.extend([item_id] * max(1, count))
    return out


def solve(base_id: str, part_ids: list[str], items: dict) -> dict | None:
    """把配件多重集分配到可装槽位；无解返回 None（**不猜测**）。"""
    remaining = Counter(part_ids)
    remaining[base_id] -= 1
    if remaining.get(base_id, 0) <= 0:
        remaining.pop(base_id, None)
    nodes = 0

    def dfs(installed: dict, open_slots: list, left: Counter):
        nonlocal nodes
        nodes += 1
        if nodes > MAX_NODES:
            return None
        if not left:
            return dict(installed)
        options = []
        for pid in sorted(left):
            slots = [s for s in open_slots if pid in s[1]]
            if slots:
                options.append((len(slots), pid, slots))
        if not options:
            return None
        options.sort(key=lambda t: (t[0], t[1]))
        for (_, pid, slots) in options[:4]:      # 最多试 4 个最紧的配件，避免爆炸
            for (path, _allow, _slot) in slots:
                rest = Counter(left)
                rest[pid] -= 1
                if rest[pid] <= 0:
                    del rest[pid]
                nxt = dict(installed)
                nxt[path] = pid
                opened = [s for s in open_slots if s[0] != path]
                opened.extend(slot_paths(items.get(pid) or {}, path))
                got = dfs(nxt, opened, rest)
                if got is not None:
                    return got
        return None

    return dfs({}, slot_paths(items.get(base_id) or {}, ""), remaining)


def build(gunslots: dict, items: dict) -> dict:
    """产出 `data/gun-presets.json` 的完整结构（内置预设保持原始元数据，仅补 items）。"""
    guns = (gunslots or {}).get("guns") or {}
    presets: dict = {}
    unsolved = []
    for gun_id, gun in guns.items():
        for meta in (gun or {}).get("presets") or []:
            pid = meta.get("id")
            if not pid:
                continue
            parts = _parts(items.get(pid) or {})
            solved = solve(gun_id, parts, items) if parts else None
            base = {"g": gun_id, "n": meta.get("n"), "e": meta.get("e"),
                    "rv": meta.get("rv"), "rh": meta.get("rh"), "moa": meta.get("moa")}
            if solved is None:
                reason = "缺少配件清单（Preset 无 containsItems）" if not parts \
                    else "配件与当前槽位允许关系不匹配（%d 件）" % len(parts)
                unsolved.append(dict(base, id=pid, reason=reason, parts=len(parts)))
            else:
                presets[pid] = dict(base, i=solved, parts=len(parts))
    return {
        "schema": SCHEMA,
        "source": "tarkov.dev 内置预设（Preset.containsItems）+ 本地上游槽位关系构建期还原",
        "count": len(presets),
        "unsolvedCount": len(unsolved),
        "presets": presets,
        "unsolved": unsolved,
    }


def stats(payload: dict) -> dict:
    """覆盖率摘要，供 meta.json / 验收报告引用。"""
    return {"count": payload.get("count", 0),
            "unsolved": payload.get("unsolvedCount", 0),
            "withItems": sum(1 for p in (payload.get("presets") or {}).values() if p.get("i"))}
