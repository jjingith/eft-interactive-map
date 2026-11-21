# -*- coding: utf-8 -*-
"""R223：删掉「Collected 计数（仅本机，不跨设备）」——只写不读的空功能。

背景：
  这块来自 R97 对齐参考站时照搬的结构（参考站详情面板左列有
  `Collected: FIR [− 0 +] non-FIR [− 0 +]`）。我们没有游戏内数据来源，
  因此它只能做成手点计数器，写 `localStorage['eftmap.market.collected.v1']`。
  R19.47 曾拍板「保留但标注范围」，于是标题加「仅本机，不跨设备」、0 值挂
  「未记录」徽标。但实测（`tools/r223_counter_probe.py`，7/7）证明：点 + 两次
  确实变 2、确实落盘、刷新确实还在，而**页面没有任何地方消费这个数字**——
  行内没有徽标、工具栏没有「只看已收集」筛选、也没有导出。它是纯噪声。

本文件守住四条不变量：
1. 这块的 DOM / 样式 / 逻辑 / 事件委托全部消失，且不得复活；
2. `.mk-count`（工具栏「显示 N / M 条」）是**另一个东西**，必须还在；
3. 详情弹窗左列仍保留价格摘要与 Sell to，别删多了；
4. 删 UI 不等于删用户数据：代码里不得出现 `removeItem` 去清空那个键。
"""
from __future__ import annotations

import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return fh.read()


def test_collected_counter_is_gone_and_must_not_come_back():
    js = _read(os.path.join("js", "market.js"))
    for token in (
        "eftmap.market.collected.v1",  # 本地存储键
        "renderCollected",             # 渲染函数
        "readCollected",               # 读盘
        "saveCollected",               # 写盘
        "mk-collected",                # 容器
        "mk-count-btn",                # +/− 按钮
        "mk-count-hint",               # 「未记录」徽标
        "Collected 计数",              # 标题文案
        "仅保存在本机、不跨设备",       # 免责说明
        "data-count",                  # 事件委托属性
    ):
        assert token not in js, "R223 已删除该功能，代码里不应再出现：%s" % token


def test_collected_counter_has_no_leftover_css():
    css = _read("market.css")
    for token in (
        ".mk-collected",
        ".mk-count-row",
        ".mk-count-label",
        ".mk-count-btn",
        ".mk-count-value",
        ".mk-count-hint",
    ):
        assert token not in css, "R223 已删除该功能，样式里不应再出现：%s" % token


def test_toolbar_count_is_a_different_thing_and_survives():
    """`.mk-count` 是工具栏的「显示 120 / 3540 条」，删这块时不能误伤。"""
    js = _read(os.path.join("js", "market.js"))
    css = _read("market.css")
    assert 'class="mk-count"' in js
    assert 'querySelector(".mk-count")' in js
    assert "ui.count" in js
    assert ".mk-count {" in css


def test_modal_left_column_keeps_price_and_sellto_only():
    js = _read(os.path.join("js", "market.js"))
    left = re.search(r'<div class="mk-modal-left">(.*?)<div class="mk-modal-right">',
                     js, re.S)
    assert left, "弹窗左列模板没找到"
    block = left.group(1)
    assert "mk-priceblock" in block
    assert "mk-sellto" in block
    assert "mk-collected" not in block
    # 左右两栏都还在（不是把整块 modal-body 删掉）
    assert 'class="mk-modal-right"' in js


def test_removal_does_not_wipe_user_local_data():
    """删界面 ≠ 删数据：不许顺手 removeItem 清空用户已有的本机记录。"""
    js = _read(os.path.join("js", "market.js"))
    assert "removeItem" not in js
    assert "clear()" not in js


def test_modal_still_opens_with_tabs_and_sellto():
    """删干净后，详情弹窗的核心交互不能受牵连。"""
    js = _read(os.path.join("js", "market.js"))
    assert 'data-tab="obtain"' in js
    assert 'data-tab="uses"' in js
    assert 'data-tab="banned"' in js
    assert 'closest("[data-tab]")' in js
    assert "renderSellTo()" in js
    assert "renderPriceBlock()" in js
