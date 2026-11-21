# -*- coding: utf-8 -*-
"""R99：ADS 时间必须随**总人机工效**走（含技能修正后的真实人机）。

分工：
· 静态：公式只有一份实现（gun_builder.adsTimeFromErgo），app.js 的技能叠加
  必须在改完 ergonomics 之后用它重算 adsTime；
· 动态（node + 真实数据）：同枪换高 ergo 预设 → ADS 变快；两把不同枪总 ergo
  相同 → ADS 相同；人机边界值不出现负数 / 0 / 无穷。

依据：
· 数据：data/gun-stats.json 的 guns[gunId].e（枪本体人机）、mods[itemId].e（配件人机）；
· 公式：gun_builder.js 的社区拟合式 2.35 − 0.028 × 人机（EFTForge 无该指标）；
· 合成链：gun_builder.js compute() 里 ergonomics = 基础 e + Σ 配件 e，
  ADS 直接读 out.fields.ergonomics.v —— 与「总人机工效」是同一条链。
"""

from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app.js"
GB = ROOT / "gun_builder.js"
PROBE = ROOT / "tools" / "r99_ads.js"

AK74 = "5bf3e03b0db834001d2c4a9c"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _fn(js: str, name: str) -> str:
    i = js.find("function %s(" % name)
    assert i >= 0, "找不到函数 %s" % name
    depth, j = 0, js.index("{", i)
    while j < len(js):
        if js[j] == "{":
            depth += 1
        elif js[j] == "}":
            depth -= 1
            if depth == 0:
                return js[i:j + 1]
        j += 1
    return js[i:]


def _node() -> bool:
    return shutil.which("node") is not None


def _run(*args):
    proc = subprocess.run(["node", str(PROBE)] + list(args),
                          capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr[:800]
    return json.loads(proc.stdout)


# ---------------------------------------------------------------- 静态契约
def test_formula_has_single_source():
    gb = _read(GB)
    assert "function adsTimeFromErgo(ergo)" in gb
    assert gb.count("2.35 - 0.028") == 1, "拟合式只允许在 adsTimeFromErgo 里出现一次"
    ads_block = _fn(gb, "adsTimeFromErgo")
    assert "Math.max(0.2," in ads_block, "下限沿用 0.2s，避免 0 / 负数"
    assert "isFinite(ergo)" in ads_block, "NaN / Infinity 必须按缺失处理"
    assert "adsTimeFromErgo(ergoAds)" in gb, "compute 里的 ADS 必须调用同一个函数"
    assert "adsTimeFromErgo: adsTimeFromErgo" in gb, "必须导出，供 app.js 技能后重算"


def test_bare_gun_table_uses_shared_formula():
    app = _read(APP)
    assert "2.35 - 0.028" not in app, "app.js 里的裸枪对比表也必须调用 GB.adsTimeFromErgo，不得另抄公式"
    assert "window.GB.adsTimeFromErgo(st.e)" in app


def test_app_recomputes_ads_after_skill_ergo():
    fn = _fn(_read(APP), "gwApplySkillStats")
    i_ergo = fn.index('mul("ergonomics"')
    i_ads = fn.index("adsTimeFromErgo")
    assert i_ergo < i_ads, "必须先叠加技能人机，再按新值重算 ADS"
    assert "out.fields.ergonomics.v" in fn, "ADS 的输入必须是技能后的总人机工效"
    assert "out.fields.adsTime" in fn


# ---------------------------------------------------------------- 动态（真实数据）
@pytest.mark.skipif(not _node(), reason="需要 node")
def test_same_gun_higher_ergo_makes_ads_faster():
    out = _run("sameGun", AK74)
    low, high = out["low"], out["high"]
    assert low["e"] < high["e"], (low, high)
    assert high["ads"] < low["ads"], "高 ergo 装配的 ADS 必须更快"
    for item in (low, high, out["bare"]):
        expect = max(0.2, round(2.35 - 0.028 * item["e"], 2))
        assert item["ads"] == pytest.approx(expect, abs=1e-9), item


@pytest.mark.skipif(not _node(), reason="需要 node")
def test_two_guns_with_same_ergo_get_same_ads():
    out = _run("twoGuns")
    a, b = out["a"], out["b"]
    assert a["gun"] != b["gun"]
    assert a["e"] == b["e"], (a, b)
    assert a["ads"] == b["ads"], "人机相同则 ADS 必须一致，不能按武器 id 残留差异"
    assert a["ads"] > 0.2, "这一对必须落在公式区间内，不能靠 0.2s 地板碰巧相等"


@pytest.mark.skipif(not _node(), reason="需要 node")
def test_ads_bounds_are_finite_and_positive():
    out = _run("bounds")
    for key in ("-100", "0", "10", "50", "100", "200", "1000"):
        v = out[key]
        assert v is not None and math.isfinite(v), (key, v)
        assert v >= 0.2, "不能出现 0 或负数：%s -> %s" % (key, v)
    for key in ("NaN", "Infinity", "null"):
        assert out[key] is None, "非有限输入必须按缺失处理：%s -> %s" % (key, out[key])


# ---------------------------------------------------------------- 技能后重算（提取 app.js 函数跑 node）
@pytest.mark.skipif(not _node(), reason="需要 node")
def test_skill_level_recomputes_ads(tmp_path):
    src = _read(APP)
    constant = re.search(r"var GW_SKILL_EFFECT = \{[^}]*\};", src, re.S)
    assert constant, "找不到 GW_SKILL_EFFECT"
    harness = "\n".join([
        "var window = { GB: require(%s) };" % json.dumps(str(GB)),
        constant.group(0),
        _fn(src, "gwClampLevel"),
        _fn(src, "gwSkillFactor"),
        _fn(src, "gwApplySkillStats"),
        "function mk(){ return { fields: {",
        "  recoilV: { v: 100 }, recoilH: { v: 100 },",
        "  ergonomics: { v: 50 }, adsTime: { v: 0.95, why: 'base' } } }; }",
        "var off = gwApplySkillStats(mk(), 0);",
        "var on  = gwApplySkillStats(mk(), 51);",
        "console.log(JSON.stringify({ off: off.fields, on: on.fields }));",
    ])
    js = tmp_path / "skill_ads.js"
    js.write_text(harness, encoding="utf-8")
    proc = subprocess.run(["node", str(js)], capture_output=True, text=True, encoding="utf-8")
    assert proc.returncode == 0, proc.stderr[:800]
    got = json.loads(proc.stdout)
    assert got["off"]["ergonomics"]["v"] == 50
    assert got["off"]["adsTime"]["v"] == 0.95, "无技能时不得改动 ADS"
    assert got["on"]["ergonomics"]["v"] == 55, "51 级 = 人机 +10%（封顶）"
    assert got["on"]["adsTime"]["v"] == pytest.approx(0.81, abs=1e-9), "ADS 按技能后人机 55 重算"
    assert got["on"]["adsTime"].get("skill") is True
