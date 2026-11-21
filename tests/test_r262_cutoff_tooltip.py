# -*- coding: utf-8 -*-
"""R262：数据截止徽标的悬停注释精简。

用户反馈（2026-11-12）：「鼠标移到底部『数据截止 20:01（23 分钟前）· 近实时』上显示的
注释没必要写那么清楚，写明『会员版数据是云端服务器实时抓取、免费版是离线快照』就行。」

即：徽标文字（数据截止/近实时）保持不变，只把 title 悬停注释从一大段精简为两句话。
"""

import os
import sys

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TEST_DIR)

JS = open(os.path.join(ROOT, "js", "market.js"), encoding="utf-8").read()


def test_tooltip_has_concise_two_line_explanation():
    assert "会员：云端最新快照 · CD 30 秒，每日不限次数" in JS
    assert "免费：云端快照延迟 12 小时 · 每日 24 次 · CD 59:59" in JS


def _update_cutoff_body():
    i = JS.index("function updateCutoff")
    j = JS.index("function ", i + 10)
    return JS[i:j]


def test_tooltip_drops_verbose_details():
    body = _update_cutoff_body()
    for noisy in ("内置快照随安装包发布", "7 日均价快照日", "数据年龄：",
                  "内置快照文件：", "上游最新 updated：", "数据时间："):
        assert noisy not in body, "updateCutoff 悬停注释里不应再有细节：%s" % noisy
    assert "parts" not in body, "旧的大段拼装应已删除"


def test_badge_label_still_shows_cutoff():
    # 徽标正文（数据截止 … · 近实时 / 缓存 / 免费延迟）保持清楚
    assert "数据截止" in JS
    assert "· 近实时" in JS
    assert "非实时" in JS
    assert "免费延迟 12 小时" in JS
