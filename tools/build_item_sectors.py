# -*- coding: utf-8 -*-
"""从 tarkov.dev 的 handbookCategories 生成物品的分类归属表。

游戏内 Handbook 的十个大类（交换物品 / 情报物品 / 容器 / 钥匙 / 装备 / 武器 /
配件 / 弹药 / 医疗 / 饮食）是 tarkov.dev 数据里的 handbookCategories 树：
每个物品带着自己的叶子分类 id，向上找到根分类即可归属。

输出 `data/item-sectors.json`：
    {"schema": 1, "source": "...", "items": {"<itemId>": ["Gear", "Container"]}}

多归属说明：容器是「装备 → 安全箱/收纳容器」的子类，参考站点的分类计数里
容器项同时计入装备（equipment 841 = gear 全量），所以这里允许一个物品带多个分类。

用法：
    python tools/build_item_sectors.py
"""
from __future__ import annotations

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "build-cache", "items-regular.json")
TARGET = os.path.join(ROOT, "data", "item-sectors.json")

# handbook 根分类 normalizedName → 大盘分类 key
ROOT_SECTORS = {
    "barter-items": "Barter",
    "info-items": "Info",
    "keys": "Key",
    "gear": "Gear",
    "weapons": "Weapon",
    "weapon-parts-mods": "Mod",
    "ammo": "Ammo",
    "medication": "Medical",
    "provisions": "Food",
}
# 容器是装备的子类：归到 Container（并保留 Gear 归属）。
# 参考站 eftarkov 的「容器」只统计收纳容器（storage-containers，38 项），
# 不含安全箱（secure-containers，13 项），这里与它保持一致。
CONTAINER_LEAVES = {"storage-containers"}


def _root_category(cat_id: str, handbook: dict) -> dict | None:
    current = handbook.get(cat_id)
    guard = 0
    while current and current.get("parent") and guard < 8:
        current = handbook.get(current["parent"])
        guard += 1
    return current


def build() -> dict:
    with open(CACHE, encoding="utf-8") as fh:
        doc = json.load(fh)
    data = doc.get("data") or {}
    handbook = data.get("handbookCategories") or {}
    items = data.get("items") or {}
    out: dict[str, list[str]] = {}
    for item_id, item in items.items():
        if not isinstance(item, dict):
            continue
        sectors: list[str] = []
        for cat_id in item.get("handbookCategories") or []:
            root = _root_category(str(cat_id), handbook)
            if not root:
                continue
            key = ROOT_SECTORS.get(str(root.get("normalizedName") or ""))
            if key and key not in sectors:
                sectors.append(key)
            leaf = handbook.get(str(cat_id)) or {}
            if str(leaf.get("normalizedName") or "") in CONTAINER_LEAVES:
                if "Gear" not in sectors:
                    sectors.append("Gear")
                if "Container" not in sectors:
                    sectors.append("Container")
        # 容器物品的主分类显示为「容器」（更具体），但仍保留装备归属
        if "Container" in sectors:
            sectors = ["Container"] + [key for key in sectors if key != "Container"]
        if sectors:
            out[str(item_id)] = sectors
    return {
        "schema": 1,
        "source": "tarkov.dev handbookCategories（build-cache/items-regular.json）",
        "items": out,
    }


def main() -> None:
    payload = build()
    os.makedirs(os.path.dirname(TARGET), exist_ok=True)
    with open(TARGET, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
    print("wrote %s (%d items)" % (TARGET, len(payload["items"])))


if __name__ == "__main__":
    main()
