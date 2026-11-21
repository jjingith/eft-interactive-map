# -*- coding: utf-8 -*-
"""R40：无软内衬护甲不再显示有效耐久 + 配装页价格说明迁入「关于」。

三段断言各夹一头：
  1. 无固定软内衬（只有硬板插槽、没有 aps[].fx）的护甲行 → 有效耐久为空；
  2. 有内衬的护甲行仍按 linerBreakdown().eff（Σ 每块内衬 dur/d）显示；
  3. 插板选择窗与头盔继续走本体 effectiveDurability()，数值不变。

同时锁定价格说明的逐字文本只在「关于」出现一次，配装页左侧不再保留该段。
"""

from __future__ import annotations

import json
import os
import re
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app.js")
INDEX = os.path.join(ROOT, "index.html")

PRICE_NOTE = "构建期快照 · 配装表价格在「获取方式」格内，随右上角 PvP / PvE / PvPS 与价格档（最新 / 24h / 7 日均价）变化 · 运行期不联网"

NO_LINER_IDS = ["5fd4c474dd870108a754b241", "628b9784bcf6e2659e09b8a2",
                "628cd624459354321c4b7fa2", "63737f448b28897f2802b874",
                "64a5366719bab53bd203bf33", "66b6295a8ca68c6461709efa",
                "67ab2eecfe82855dcc0f2af6", "693fd0e9deee848f70054999",
                "693fd1200ec97e98040bd3f9", "693fd13aa490096a05028cc8"]


def _text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _extract_fn(src, header):
    """按花括号配平截取一个函数定义（app.js 里这些函数嵌套 if，不能用正则偷懒）。"""
    start = src.index(header)
    i = src.index("{", start)
    depth = 0
    while i < len(src):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[start:i + 1]
        i += 1
    raise AssertionError("函数未闭合：%s" % header)


# ---------------------------------------------------------------- 1. 显示判定

def test_no_liner_armor_rows_are_scoped_not_by_hardcoded_ids():
    src = _text(APP)
    assert "linerScope: linerScope" in src, "行上必须带行级作用域，不能只靠 r.liners===null"
    assert 'node.kind === "plate"' in src, "插板选择窗要单独标成 plate，不能被护甲口径误伤"
    for item_id in NO_LINER_IDS:
        assert item_id not in src, "不得用硬编码 id 列表实现：%s" % item_id


def test_effdur_runtime_matrix():
    """真实跑 efDurValue：无内衬护甲空、有内衬按 Σ、插板/头盔保留本体值。"""
    src = _text(APP)
    fn = _extract_fn(src, "function effDurValue(r) {")
    js = "\n".join([
        "var rows = [",
        '{linerScope:"armor", liners:{eff:null,total:null}, effDur:480},',       # 无内衬插板背心
        '{linerScope:"armor", liners:{eff:1867,total:350}, effDur:1866},',      # 6B43 有内衬
        '{linerScope:"armor", liners:{eff:832,total:156}, effDur:832},',        # 6B23 有内衬
        '{linerScope:"plate", liners:{eff:null,total:null}, effDur:120},',      # 插板
        '{linerScope:null, liners:null, effDur:154},',                          # 头盔
        "];",
        fn,
        "console.log(JSON.stringify(rows.map(effDurValue)));",
    ])
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True)
    assert json.loads(out.stdout) == [None, 1867, 832, 120, 154]


def test_no_liner_tooltip_states_the_reason():
    src = _text(APP)
    assert "无固定软内衬（仅硬质插板插槽）：纸面耐久 ÷ 损毁系数不适用" in src


# ---------------------------------------------------------------- 2. 价格说明迁移

def test_price_note_lives_in_about_panel_exactly_once():
    html = _text(INDEX)
    start = html.index('id="about-block"')
    panel = html[start:html.index("<!-- R19.11", start)]
    assert PRICE_NOTE in panel, "价格说明必须出现在关于面板"
    assert "行情" in panel
    assert html.count(PRICE_NOTE) == 1, "逐字文本只应出现一次（不能在地图/配装页重复）"


def test_loadout_workspace_no_longer_has_the_price_footnote():
    html = _text(INDEX)
    workbench = html[html.index('id="loadout-workbench"'):]
    assert PRICE_NOTE not in workbench
    assert "lw-foot" not in html, "撤掉段落后不能留下空占位/多余分隔线"
