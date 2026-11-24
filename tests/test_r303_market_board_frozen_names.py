# -*- coding: utf-8 -*-
"""R303：安装版市场大盘物品名显示为 ID 的修复。

根因：market_overview._project_root() 用 __file__ 上两级找 data/。
PyInstaller 冻结后 __file__ 落在 <exe>/_internal/tools/，onefile 模式下并不可靠，
导致 data/items.json 读空 → _item_index() 空表 → 名称全部回退成物品 ID。
源码运行不受影响，只有安装版出现（用户反馈：另一台电脑装了之后大盘全是 ID）。

修复：_project_root() 增加 frozen 分支，按 _MEIPASS / exe 旁 _internal / exe 目录
依次探测含 data/ 的目录，和 serve.py 的云证书查找模式一致。

不变量：
1. 源码环境 _project_root() 仍返回项目根（含 data/）；
2. frozen 且 exe 指向 dist/EFTMap 时，_project_root() 返回 _internal（含 data/items.json）；
3. _item_index() 能解析出目标物品名，不回退成 ID。
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MO = ROOT / "tools" / "market_overview.py"


def _load_mo():
    spec = importlib.util.spec_from_file_location("mo_r303", str(MO))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_source_root_unchanged():
    mo = _load_mo()
    got = os.path.abspath(mo._project_root())
    assert os.path.isfile(os.path.join(got, "data", "items.json")), \
        "源码环境 _project_root 应指向含 data/ 的项目根，实际 %s" % got


def test_frozen_root_finds_internal_data(monkeypatch):
    exe = ROOT / "dist" / "EFTMap" / "EFTMap.exe"
    if not exe.exists():
        return  # 无打包产物时跳过（纯源码 CI）
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe), raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    mo = _load_mo()
    got = os.path.abspath(mo._project_root())
    assert os.path.isfile(os.path.join(got, "data", "items.json")), \
        "frozen 环境 _project_root 应指向含 data/ 的 _internal，实际 %s" % got


def test_item_index_has_name():
    mo = _load_mo()
    idx = mo._item_index()
    assert len(idx) > 1000, "items.json 应解析出完整索引"
    # 用户反馈的具体物品：C-3 舱室钥匙卡
    name = idx.get("69bb3f7df94327bc0f0230c9", {}).get("name")
    assert name and name != "69bb3f7df94327bc0f0230c9", \
        "该物品必须解析出中文名而非回退成 ID，实际 %r" % name
