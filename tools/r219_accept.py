# -*- coding: utf-8 -*-
"""R219 真实浏览器验收：配装右侧列表的价格回到「获取方式」格内，并随模式 / 价格档变化。

只做实测，不做推断：
  · 表头最后一列是「获取方式」，且不再有「跳蚤 24h 均价 / 跳蚤 7d 均价」两列；
  · 格内 `.lw-src-price` 真的渲染出金额（不是空壳），且浮窗写清模式 / 档位 / 来源；
  · 点 PvE / PvPS 后同一行的价格会变（模式开关生效）；
  · 点「24h 均价」后同一行的价格会变（价格档开关生效）。

用法：
    python tools/r219_accept.py --port 8787 --out D:/Temp/2/r219
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import r181_accept as base  # noqa: E402  （复用纯标准库的 WS / CDP / 启动逻辑）


def q(cdp, expr, label=""):
    """在页面里求值并返回 JS 值（awaitPromise 以便等异步）。"""
    return cdp.eval("Promise.resolve((function(){" + expr + "})())", await_promise=True)


PRICE_JS = """
  var rows = document.querySelectorAll('#gear-table .tbl-row');
  var out = [];
  for (var i = 0; i < rows.length; i++) {
    var cell = rows[i].querySelector('.tbl-cell[data-key="srcGroup"]');
    if (!cell) { continue; }
    var chips = cell.querySelectorAll('.lw-src-price');
    if (!chips.length) { continue; }
    out.push({ name: (rows[i].textContent || '').slice(0, 18), price: chips[0].textContent,
               title: chips[0].title, kind: chips[0].parentNode.dataset.kind });
  }
  return out.slice(0, 3);
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8787, help="本机源码服务端口")
    ap.add_argument("--cdp-port", type=int, default=9419)
    ap.add_argument("--out", default="D:/Temp/2/r219")
    ap.add_argument("--chrome", default=None)
    a = ap.parse_args()

    chrome = base.find_chrome(a.chrome)
    os.makedirs(a.out, exist_ok=True)
    # 每次用干净 profile：Chrome 磁盘缓存会让「改了 app.js 但页面还是旧代码」重演
    profile = os.path.join(a.out, "_profile_%d" % int(time.time()))
    proc, ws_url = base.launch(chrome, a.cdp_port, 1600, 1000, profile)
    rep = {"shots": [], "checks": []}
    try:
        cdp = base.CDP(ws_url)
        cdp.call("Page.enable")
        cdp.call("Runtime.enable")
        cdp.call("Network.enable")
        cdp.call("Network.setCacheDisabled", cacheDisabled=True)
        cdp.call("Page.navigate", url="http://127.0.0.1:%d/" % a.port)
        base.wait_ready(cdp)
        # 切到配装视图（右侧候选列表只在该视图渲染）
        q(cdp, "var b = document.getElementById('view-btn-loadout'); if (b) { b.click(); return true; } return false;", "切配装视图")
        base.wait_for(cdp, "!!document.querySelector('#gear-table .tbl-head .tbl-cell')", timeout=40, label="配装表表头")
        # 点一个已有候选的槽位（默认 focus 是头盔，等候选行渲染出来）
        base.wait_for(cdp, "document.querySelectorAll('#gear-table .tbl-row').length > 0", timeout=40, label="配装表首行")
        # 模式会持久化在 localStorage（上一次验收可能停在 PvE），先显式切回 PvP 再测
        q(cdp, """
          var bs = document.querySelectorAll('.gm-btn');
          for (var i = 0; i < bs.length; i++) {
            if ((bs[i].textContent || '').trim() === 'PvP') { bs[i].click(); return true; }
          }
          return false;
        """, "切回 PvP")
        # 等本模式行情真正落袋（云端不可达时服务端会重试约 40s 再退回内置快照）
        base.wait_for(cdp, "(function(){var s=window.GWMarketData&&window.GWMarketData.snapshot();"
                          "return !!(s&&s.mode==='regular'&&s.available);})()", timeout=90, label="PvP 行情快照")
        time.sleep(0.8)
        rep["snapshot"] = q(cdp, "var s=window.GWMarketData.snapshot();"
                                "return s?{mode:s.mode,source:s.source,items:Object.keys(s.items||{}).length}:null;", "行情快照")

        heads = q(cdp, """
          var hs = document.querySelectorAll('#gear-table .tbl-head .tbl-cell');
          var out = [];
          for (var i = 0; i < hs.length; i++) { out.push((hs[i].textContent || '').trim()); }
          return out;
        """, "表头")
        rep["headers"] = heads

        # 表尾一列必须是获取方式，且没有独立价格列
        rep["checks"].append(("表尾是获取方式", len(heads) > 0 and heads[-1].startswith("获取方式")))
        rep["checks"].append(("没有『跳蚤 24h 均价』列", all("24h 均价" not in h for h in heads)))
        rep["checks"].append(("没有『跳蚤 7d 均价』列", all("7d 均价" not in h for h in heads)))

        # 格内价格
        before = q(cdp, PRICE_JS, "格内价格")
        rep["before"] = before
        rep["checks"].append(("获取方式格内有金额（不是空壳）", bool(before)))
        rep["checks"].append(("跳蚤那一枚带口径浮窗",
                              bool(before) and "行情快照" in (before[0].get("title") or "")
                              or bool(before) and "退回构建期" in (before[0].get("title") or "")))

        # 价格档 pills 可见
        pills = q(cdp, """
          var box = document.getElementById('lw-prices');
          if (!box) { return null; }
          return { hidden: !!box.hidden, count: box.querySelectorAll('.lw-price').length,
                   labels: Array.prototype.map.call(box.querySelectorAll('.lw-price'), function (b) { return b.textContent; }) };
        """, "价格档 pills")
        rep["pills"] = pills
        rep["checks"].append(("价格档 pills 可见", bool(pills) and not pills["hidden"] and pills["count"] >= 2))

        # 切「24h 均价」
        clicked = q(cdp, """
          var b = document.querySelector('#lw-prices .lw-price[data-mode="avg24h"]');
          if (!b || b.disabled) { return 'disabled'; }
          b.click(); return 'ok';
        """, "点 24h 均价")
        time.sleep(0.6)
        after_basis = q(cdp, PRICE_JS, "切档后价格")
        rep["after_basis"] = after_basis
        rep["checks"].append(("切 24h 均价后价格档变了",
                              clicked == "ok" and bool(after_basis) and
                              (not before or after_basis[0]["price"] != before[0]["price"] or
                               "24h" in (after_basis[0].get("title") or ""))))

        # 切模式 PvE
        mode = q(cdp, """
          var bs = document.querySelectorAll('.gm-btn');
          for (var i = 0; i < bs.length; i++) {
            var t = (bs[i].textContent || '').trim();
            if (t === 'PvE') { bs[i].click(); return t; }
          }
          return null;
        """, "切 PvE")
        # 等 PvE 行情落袋（同样是云端重试 → 内置快照）
        waited = False
        try:
            base.wait_for(cdp, "(function(){var s=window.GWMarketData&&window.GWMarketData.snapshot();"
                               "return !!(s&&s.mode==='pve'&&s.available);})()", timeout=90, label="PvE 行情快照")
            waited = True
        except TimeoutError:
            waited = False
        time.sleep(1.0)
        rep["snapshot_pve"] = q(cdp, "var s=window.GWMarketData.snapshot();"
                                     "return s?{mode:s.mode,source:s.source,items:Object.keys(s.items||{}).length}:null;", "PvE 行情快照")
        after_mode = q(cdp, PRICE_JS, "切模式后价格")
        rep["after_mode"] = after_mode
        rep["checks"].append(("PvE 行情确实切到了本模式", waited))
        rep["checks"].append(("切到 PvE 后同一行价格变了",
                              bool(mode) and bool(after_mode) and bool(after_basis) and
                              after_mode[0]["price"] != after_basis[0]["price"]))
        rep["checks"].append(("切到 PvE 后浮窗写的是 PvE",
                              bool(after_mode) and "PvE" in (after_mode[0].get("title") or "")))

        shot = os.path.join(a.out, "loadout-price.png")
        cdp.shot(shot)
        rep["shots"].append(shot)
    finally:
        try:
            proc.terminate()
        except Exception:
            pass

    print(json.dumps(rep, ensure_ascii=False, indent=2))
    bad = [n for n, ok in rep["checks"] if not ok]
    print("\n结果：%d/%d 通过" % (len(rep["checks"]) - len(bad), len(rep["checks"])))
    if bad:
        print("未通过：", "、".join(bad))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
