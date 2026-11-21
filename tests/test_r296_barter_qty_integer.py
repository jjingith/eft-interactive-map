# -*- coding: utf-8 -*-
"""R296：竞技场商人 GP 币兑换的数量必须显示为整数。

现象：配装界面「获取方式」里的兑换配方显示成 `18.25×GP币`。
根因：tarkov.dev 的 barters 里，竞技场（Ref）的 GP 币价格是按汇率折算的浮点
（18.25 / 7.52 / 228.28 …），游戏内只收整枚 GP 币。前端直接拼了原始 count。

处理：`reqQty()` 统一四舍五入；原始折算值只留在 tooltip 里说明，数据不丢。

不变量：
1. items.json 里所有非整数的兑换数量**只能**来自 GP 币，不能影响普通物品；
2. 渲染不得再直接拼接原始 count；取整函数行为固定。
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_JS = ROOT / "app.js"
ITEMS = ROOT / "data" / "items.json"

GP_COIN = "5d235b4d86f7742e017bc88a"   # GP币


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_non_integer_barter_qty_only_from_gp_coin():
    items = json.loads(read(ITEMS))["items"]
    offenders = {}
    samples = []
    for iid, rec in items.items():
        for t in (rec.get("trade") or []):
            if t.get("k") != "barter":
                continue
            for pair in (t.get("r") or []):
                if not isinstance(pair, list) or len(pair) < 2:
                    continue
                qty = pair[1]
                if isinstance(qty, float) and qty % 1 != 0:
                    offenders[pair[0]] = offenders.get(pair[0], 0) + 1
                    if len(samples) < 5:
                        samples.append((rec.get("n"), qty))
    assert offenders, "数据里应仍有 GP 币折算值（否则本测试失去意义，需复核上游口径）"
    assert set(offenders) == {GP_COIN}, \
        "非整数兑换数量出现了 GP 币以外的物品，不能一律取整：%s" % offenders
    assert samples, "缺少样本"


def test_render_uses_rounded_quantity():
    js = read(APP_JS)
    assert "function reqQty(n)" in js
    assert "var q = Math.round(v);" in js
    assert "return q < 1 ? 1 : q;" in js
    # 格内摘要与 tooltip 都必须用取整后的 qty
    assert 'var qty = reqQty(rawQty);' in js
    assert 'reqBits.push(qty + "×" + nm);' in js
    assert 'v.tip += "\\n配方：" + qty + " × " + nm' in js
    # 旧写法（直接拼原始 count）必须消失
    assert 'reqBits.push((req[i][1] || 1) + "×" + nm);' not in js


def test_req_qty_rounds_half_up():
    js = read(APP_JS)
    i = js.index("function reqQty(n)")
    j = js.index("\n  }", i) + len("\n  }")
    fn = js[i:j]
    script = "const fs=require('fs');" \
             "const src=fs.readFileSync(process.argv[1],'utf-8');" \
             "const fn=src.slice(+process.argv[2], +process.argv[3]);" \
             "eval(fn);" \
             "console.log(JSON.stringify([reqQty(18.25),reqQty(228.28),reqQty(7.52),reqQty(3)," \
             "reqQty(0.42),reqQty(-2),reqQty('x')]));"
    proc = subprocess.run(
        ["node", "-e", script, str(APP_JS), str(i), str(j)],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, proc.stderr[:300]
    got = json.loads(proc.stdout.strip())
    assert got[:4] == [18, 228, 8, 3], "取整结果不符：%s" % got
    # 0.42 枚必须保底显示 1（数据里真实存在 41 条），不能出现 0×
    assert got[4] == 1, "低于 0.5 枚应保底 1：%s" % got
    # 非法值（负数 / 非数）回退为 1，不产生 NaN
    assert got[5:] == [1, 1], "非法数量应回退 1：%s" % got
