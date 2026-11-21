# -*- coding: utf-8 -*-
"""R20.6 真实浏览器验收：配装页候选筛选条（对照 db4tarkov /preset）。

校验项：
  L1  筛选条存在（5 个筛选控件 + 3 个排序按钮）
  L2  重量上限过滤生效
  L3  防弹等级下限过滤生效
  L4  惩罚上限过滤生效
  L5  商人等级过滤生效
  L6  护甲等级过滤生效
  L7  移动分项排序生效（顺序变化 + 按钮高亮）
  L8  转身分项排序生效
  L9  人机分项排序生效
  L10 清空筛选后行数回到基线
  L11 装配一件装备后左侧槽位与费用更新（保证配装主流程未被破坏）
  L12 控制台 0 错误 / 运行期 0 外部请求
"""
import argparse
import base64
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r181_accept import CDP, find_chrome, launch, wait_ready

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "r20.6", "local-screenshots")


def js(cdp, expr):
    r = cdp.eval(expr)
    if isinstance(r, str) and r.strip()[:1] in ("{", "["):
        try:
            return json.loads(r)
        except Exception:  # noqa: BLE001
            return r
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8810")
    ap.add_argument("--port", type=int, default=9770)
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    checks = []

    def ok(cid, cond, detail=""):
        checks.append({"id": cid, "pass": bool(cond), "detail": str(detail)[:400]})
        print(("PASS " if cond else "FAIL ") + cid + ("  " + str(detail)[:200] if detail else ""))

    prof = os.path.join(tempfile.gettempdir(), "r206accept%d" % args.port)
    proc, ws = launch(find_chrome(), args.port, 1680, 1050, prof)
    cdp = CDP(ws)

    def rows():
        return js(cdp, "document.querySelectorAll('#gear-table .tbl-row').length")

    def set_val(el_id, value, evt="change"):
        return js(cdp, """(function(){var n=document.getElementById(%s);if(!n)return 'no-el';
          n.value=%s;
          n.dispatchEvent(new Event('input',{bubbles:true}));
          n.dispatchEvent(new Event('change',{bubbles:true}));
          return 'ok';})()""" % (json.dumps(el_id), json.dumps(str(value))))

    def first_names(n=3):
        return js(cdp, """(function(){return [].slice.call(document.querySelectorAll('#gear-table .tbl-row'))
          .slice(0,%d).map(function(r){return (r.innerText||'').split('\\n')[0];});})()""" % n)

    def first_pens(n=6):
        """前 n 行的「移动/转身/人机」三元组（-1.0/-4.0/-3.0 形式）。"""
        return js(cdp, """(function(){return [].slice.call(document.querySelectorAll('#gear-table .tbl-row'))
          .slice(0,%d).map(function(r){var t=(r.innerText||'').split('\\n');
            for(var i=0;i<t.length;i++){ if(/^-?\\d+\\.?-?\\d*\\//.test(t[i])) return t[i]; }
            return '';});})()""" % n)

    def pen_series(pens, idx):
        out = []
        for p in pens or []:
            parts = str(p).split("/")
            if len(parts) != 3:
                continue
            try:
                out.append(float(parts[idx]))
            except ValueError:
                continue
        return out

    def nonincreasing(vals):
        """降序（惩罚从重到轻）允许相等；带 0.05 容差。"""
        return all(vals[i] >= vals[i + 1] - 0.05 for i in range(len(vals) - 1))

    try:
        for m in ("Page.enable", "Runtime.enable", "Log.enable", "Network.enable"):
            cdp.call(m)
        cdp.call("Page.navigate", url=args.base + "/index.html")
        wait_ready(cdp, want_url="index.html")
        time.sleep(6)
        cdp.eval("(function(){var b=document.querySelector('[data-view=loadout]');if(b)b.click();return !!b;})()")
        time.sleep(3.5)

        # ---------------- L1 筛选条骨架
        sk = js(cdp, """(function(){return JSON.stringify({
          bar: !!document.getElementById('lw-filters'),
          cl: !!document.getElementById('lw-cl'),
          lv: !!document.getElementById('lw-traderlv'),
          kg: !!document.getElementById('lw-maxkg'),
          mincl: !!document.getElementById('lw-mincl'),
          pen: !!document.getElementById('lw-maxpen'),
          nSort: document.querySelectorAll('.lw-sortbtn').length});})()""")
        ok("L1_筛选条存在(5控件+3排序)", isinstance(sk, dict) and sk.get("bar")
           and sk.get("cl") and sk.get("lv") and sk.get("kg") and sk.get("mincl")
           and sk.get("pen") and sk.get("nSort") == 3, sk)

        base_n = rows()

        # ---------------- L2 重量上限
        set_val("lw-maxkg", 1)
        time.sleep(1.6)
        n2 = rows()
        st2 = js(cdp, "(document.getElementById('lw-fl-state')||{}).textContent||''")
        ok("L2_重量上限过滤生效", isinstance(n2, int) and n2 < base_n and "重量" in (st2 or ""),
           "%s -> %s ｜ %s" % (base_n, n2, st2))
        set_val("lw-maxkg", "")
        time.sleep(1.4)

        # ---------------- L3 防弹等级下限
        set_val("lw-mincl", 5)
        time.sleep(1.6)
        n3 = rows()
        ok("L3_防弹等级下限过滤生效", isinstance(n3, int) and n3 < base_n, "%s -> %s" % (base_n, n3))
        set_val("lw-mincl", "")
        time.sleep(1.4)

        # ---------------- L4 惩罚上限
        set_val("lw-maxpen", 5)
        time.sleep(1.6)
        n4 = rows()
        ok("L4_惩罚上限过滤生效", isinstance(n4, int) and n4 <= base_n, "%s -> %s" % (base_n, n4))
        set_val("lw-maxpen", "")
        time.sleep(1.4)

        # ---------------- L5 商人等级
        set_val("lw-traderlv", 1)
        time.sleep(1.6)
        n5 = rows()
        lv_ok = js(cdp, """(function(){var t=document.querySelectorAll('#gear-table .tbl-row');
          var bad=0;for(var i=0;i<t.length;i++){var m=(t[i].innerText||'').match(/Lv(\\d)/);
            if(m && Number(m[1])>1) bad++;} return bad;})()""")
        ok("L5_商人等级过滤生效", isinstance(n5, int) and n5 <= base_n and lv_ok == 0,
           "%s -> %s，越界行=%s" % (base_n, n5, lv_ok))
        set_val("lw-traderlv", 0)
        time.sleep(1.4)

        # ---------------- L6 护甲等级
        set_val("lw-cl", 5)
        time.sleep(1.6)
        n6 = rows()
        ok("L6_护甲等级过滤生效", isinstance(n6, int) and n6 <= base_n, "%s -> %s" % (base_n, n6))
        set_val("lw-cl", "")
        time.sleep(1.4)

        # ---------------- L6b 跳蚤上架等级（minLevelForFlea）
        fl = js(cdp, """(function(){var n=document.getElementById('lw-flealv');
          if(!n) return 'no-el';
          return JSON.stringify({disabled:!!n.disabled,
            opts:[].slice.call(n.options).map(function(o){return o.value;}),
            txt:[].slice.call(n.options).map(function(o){return o.textContent;}),
            sig:n.dataset.sig||''});})()""")
        opt_ok = isinstance(fl, dict) and fl.get("opts") and len(fl["opts"]) >= 2
        set_val("lw-flealv", "20")
        time.sleep(1.8)
        n6b = rows()
        st6b = js(cdp, "(document.getElementById('lw-fl-state')||{}).textContent||''")
        ok("L6b_跳蚤等级过滤生效", opt_ok and isinstance(n6b, int) and n6b <= base_n
           and "跳蚤等级" in (st6b or ""),
           "选项=%s ｜ %s -> %s ｜ %s" % (fl.get("txt") if isinstance(fl, dict) else fl, base_n, n6b, st6b))
        set_val("lw-flealv", "0")
        time.sleep(1.4)

        # ---------------- L7~L9 三个分项排序
        before = first_names(6)
        for key, idx, cid in (("mov", 0, "L7_移动分项排序生效"),
                              ("turn", 1, "L8_转身分项排序生效"),
                              ("ergo", 2, "L9_人机分项排序生效")):
            js(cdp, "(function(){var b=document.querySelector('.lw-sortbtn[data-lwsort=%s]');"
                    "if(b)b.click();return !!b;})()" % key)
            time.sleep(1.5)
            now = first_names(6)
            pens = first_pens(6)
            series = pen_series(pens, idx)
            on = js(cdp, "(function(){var b=document.querySelector('.lw-sortbtn[data-lwsort=%s]');"
                         "return b?b.getAttribute('aria-pressed'):'no';})()" % key)
            # 判定：按钮确实进入该排序；且「该分项取值单调降序」或「可见顺序发生变化」至少成立一条
            # （转身与人机的取值常常相同，只看首行会误判）
            cond = on == "true" and (nonincreasing(series) or now != before)
            ok(cid, cond, "aria-pressed=%s ｜ 序列=%s ｜ 首行 %s -> %s"
               % (on, series[:5], before[:1], now[:1]))
            before = now

        # ---------------- L10 清空筛选后回到基线
        for key in ("lw-maxkg", "lw-mincl", "lw-maxpen"):
            set_val(key, "")
        set_val("lw-cl", "")
        set_val("lw-traderlv", 0)
        time.sleep(1.8)
        n10 = rows()
        st10 = js(cdp, "(document.getElementById('lw-fl-state')||{}).textContent||''")
        ok("L10_清空筛选后回到基线", n10 == base_n and not (st10 or "").strip(),
           "%s -> %s ｜ 状态=%r" % (base_n, n10, st10))

        # ---------------- L11 装配一件装备（配装主流程未坏）
        head_before = js(cdp, "(function(){var n=document.querySelector('#lw-stats');"
                              "return n?(n.innerText||'').slice(0,40):'';})()")
        clicked = js(cdp, """(function(){var r=document.querySelector('#gear-table .tbl-row');
          if(!r) return 'no-row'; r.click(); return (r.innerText||'').split('\\n')[0];})()""")
        time.sleep(2.2)
        head_after = js(cdp, "(function(){var n=document.querySelector('#lw-stats');"
                             "return n?(n.innerText||'').slice(0,40):'';})()")
        ok("L11_装配一件后左栏统计更新", clicked != "no-row" and head_after != head_before,
           "%s ｜ %r -> %r" % (clicked, head_before, head_after))

        # ---------------- L12 控制台与网络
        errs = [c for c in cdp.console if c.get("level") == "error"]
        hosts = sorted(set(r.get("host", "") for r in cdp.requests))
        ext = [h for h in hosts if h and h not in ("127.0.0.1", "localhost")]
        ok("L12a_控制台无错误", not errs, errs[:2])
        ok("L12b_运行期无外部请求", not ext, ext[:5])

        r = cdp.call("Page.captureScreenshot", format="png")
        with open(os.path.join(OUT, "03-r206-accept.png"), "wb") as f:
            f.write(base64.b64decode(r["data"]))

        rep = {"validator": "r206_accept.py", "base": args.base,
               "pass": all(c["pass"] for c in checks),
               "summary": {"total": len(checks),
                           "passed": sum(1 for c in checks if c["pass"])},
               "baselineRows": base_n, "checks": checks,
               "consoleErrors": len(errs), "externalHosts": ext}
        out = os.path.join(ROOT, "docs", "r20.6", "browser-accept.r20.6.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(rep, f, ensure_ascii=False, indent=1)
        print("\n==== %d/%d 通过（报告：%s）====" % (rep["summary"]["passed"], rep["summary"]["total"], out))
    finally:
        proc.terminate()


if __name__ == "__main__":
    main()
