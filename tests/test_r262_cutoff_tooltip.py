# -*- coding: utf-8 -*-
"""R262 / R308：数据截止徽标的悬停注释保持精简。

R262（2026-11-12）要求把大段拼装精简成两句话；
R308（2026-11-25）用户进一步要求不在各页面重复「免费 / 会员」差异：
这里只说明行情来自云端、额度与 CD 在账号上，不再罗列两档的次数与延迟。
"""

import os
import sys

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TEST_DIR)

JS = open(os.path.join(ROOT, "js", "market.js"), encoding="utf-8").read()


def test_tooltip_has_concise_explanation_without_tier_comparison():
    body = _update_cutoff_body()
    assert "行情来自云端；额度与 CD 记录在云端账号上。" in body
    assert "会员：" not in body and "免费：" not in body, \
        "行情页不再罗列会员 / 免费两档的次数与 CD"


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
    # 徽标正文（数据截止 … · 近实时 / 缓存）保持清楚
    assert "数据截止" in JS
    assert "· 近实时" in JS
    assert "非实时" in JS
    assert "免费延迟 12 小时" not in JS, "R308：不再到处写免费 / 会员差异"
