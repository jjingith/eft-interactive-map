"""R51 专项：任务目标物品数量（objective item count）链路。

覆盖三件事：
  1. 上游单物品目标的 count 会写进生成的 item.count；
  2. 多物品目标（任选/某类合计）不会把总数误写到每个物品上；
  3. 前端角标读取的键仍是 it.count，真实数据里至少有一个 count > 1 的图标。
"""
from __future__ import annotations

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

TASKS_DIR = os.path.join(ROOT, "data", "tasks")
TASKS_JS = os.path.join(ROOT, "tasks.js")
MODES = ("regular", "pve", "pvps")


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def test_single_item_objective_carries_count():
    import fetch_tasks as ft

    raw = [{"id": "o1", "type": "giveItem", "count": 3, "items": ["item-a"]}]
    objs = ft.norm_objectives(raw, {}, {"item-a": "Item A"}, {})
    assert objs[0]["count"] == 3
    assert objs[0]["items"][0]["count"] == 3


def test_multi_item_objective_keeps_count_at_objective_level():
    import fetch_tasks as ft

    raw = [{"id": "o2", "type": "sellItem", "count": 5, "items": ["a", "b", "c"]}]
    objs = ft.norm_objectives(raw, {}, {}, {})
    assert objs[0]["count"] == 5
    assert all(it["count"] is None for it in objs[0]["items"])


def test_non_item_objective_does_not_stamp_item_count():
    import fetch_tasks as ft

    raw = [{"id": "o3", "type": "shoot", "count": 20, "items": ["weapon-x"]}]
    objs = ft.norm_objectives(raw, {}, {}, {})
    assert objs[0]["items"][0]["count"] is None


def test_frontend_badge_uses_item_count_key():
    with open(TASKS_JS, encoding="utf-8") as fh:
        js = fh.read()
    assert re.search(r"it\.count\s*\|\|\s*1", js), "角标应读取 it.count 并以 1 兜底"
    assert "db4-item-n" in js


def test_generated_packs_expose_item_counts():
    badge_hits = {}
    for mode in MODES:
        doc = _load(os.path.join(TASKS_DIR, "tasks.%s.json" % mode))
        items = [it for t in doc["tasks"].values()
                 for o in t.get("objectives") or [] for it in o.get("items") or []]
        single = [it for it in items if isinstance(it.get("count"), (int, float))]
        badge_hits[mode] = sum(1 for it in single if it["count"] > 1)
    assert all(n > 0 for n in badge_hits.values()), badge_hits
