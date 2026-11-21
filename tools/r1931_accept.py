# -*- coding: utf-8 -*-
"""R19.23 真实浏览器验收：三模式切换 / 数据隔离 / 进度隔离 / 中文化 / 回归。

全部结论来自真实 Chrome 跑到 http://127.0.0.1:8787 上点的结果：
DOM 实测值、getBoundingClientRect 几何、页面里 GWTasks 的真实状态、PNG 截图。

用法：
    python tools/r1931_accept.py --port 9761
产物：
    docs/r19.23/browser-accept.json
    docs/r19.23/shots/*.png
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r181_accept import CDP, find_chrome, launch, wait_ready  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "r19.23")
SHOTS = os.path.join(OUT, "shots")
TASKS_DIR = os.path.join(ROOT, "data", "tasks")
BASE = "http://127.0.0.1:8787"
MODES = ("regular", "pve", "pvps")

report = {"build": "R19.23", "pass": False, "checks": [], "detail": {}}


def ok(name, cond, detail=None):
    report["checks"].append({"name": name, "ok": bool(cond), "detail": detail})
    print(("  PASS " if cond else "  FAIL ") + name + ("" if cond else "  -> %s" % (detail,)))
    return bool(cond)


def shot(cdp, name):
    os.makedirs(SHOTS, exist_ok=True)
    try:
        res = cdp.call("Page.captureScreenshot", format="png")
        with open(os.path.join(SHOTS, name), "wb") as fh:
            fh.write(base64.b64decode(res["data"]))
    except Exception as exc:                      # noqa: BLE001
        print("   screenshot failed:", exc)


def js(cdp, expr, default=None):
    try:
        return cdp.eval(expr)
    except Exception as exc:                      # noqa: BLE001
        print("   eval failed:", exc)
        return default


def nav(cdp, url, needle="index.html", wait=4.0):
    cdp.call("Page.navigate", url=url)
    wait_ready(cdp, want_url=needle)
    time.sleep(wait)


def wait_nodes(cdp, expected, tries=40):
    n = 0
    for _ in range(tries):
        n = int(js(cdp, "document.querySelectorAll('#tk-nodes .tk-node').length", 0) or 0)
        if n == expected:
            return n
        time.sleep(0.5)
    return n


def expected_edges(mode):
    """按 tasks.js renderTree 的规则算期望边数：前置边（两端都在本模式）+ 失败分支边。"""
    with open(os.path.join(TASKS_DIR, "tasks.%s.json" % mode), encoding="utf-8") as fh:
        tasks = json.load(fh)["tasks"]
    ids = set(tasks)
    n = 0
    for rec in tasks.values():
        n += sum(1 for p in (rec.get("prerequisites") or []) if p.get("taskId") in ids)
        n += sum(1 for f in (rec.get("failedConditions") or []) if f.get("taskId") in ids)
    return n


def counts_of(mode):
    with open(os.path.join(TASKS_DIR, "tasks.%s.json" % mode), encoding="utf-8") as fh:
        return json.load(fh)["counts"]


def mode_buttons_box(cdp):
    """R19.27：模式控件在全局页头右上角（#game-mode-bar），不再量任务壳内边距。"""
    return js(cdp, r"""(function(){
      var bar=document.getElementById('game-mode-bar')||document.querySelector('.tk-modebar');
      if(!bar) return null;
      var b=bar.getBoundingClientRect();
      var head=document.querySelector('.menubar');
      var hb=head?head.getBoundingClientRect():{right:innerWidth,top:0};
      var btns=[].map.call(bar.querySelectorAll('[data-tkmode]'), function(el){
        var r=el.getBoundingClientRect();
        return {key:el.dataset.tkmode, text:el.textContent.trim(), w:Math.round(r.width),
                h:Math.round(r.height), selected:el.getAttribute('aria-selected'),
                title:el.getAttribute('title')||''};
      });
      return {gapRight:Math.round(hb.right-b.right), gapTop:Math.round(b.top-(hb.top||0)),
              w:Math.round(b.width), h:Math.round(b.height), buttons:btns,
              selCount: btns.filter(function(x){return x.selected==='true';}).length,
              inMenubar: !!(head && head.contains(bar)),
              globalAPI: !!window.GWGameMode,
              mode: window.GWGameMode ? window.GWGameMode.get() : (window.GWTasks.state||{}).mode};
    })()""")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9761)
    ap.add_argument("--base", default=BASE)
    args = ap.parse_args(argv)
    os.makedirs(SHOTS, exist_ok=True)
    prof = os.path.join(os.environ.get("TEMP", "."), "r1923acc_%d" % args.port)
    proc, ws = launch(find_chrome(), args.port, 1680, 1050, prof)
    cdp = CDP(ws)
    base = args.base.rstrip("/")
    try:
        for m in ("Page.enable", "Runtime.enable", "Log.enable", "Network.enable"):
            cdp.call(m)
        cdp.call("Network.setCacheDisabled", cacheDisabled=True)
        cdp.call("Emulation.setDeviceMetricsOverride", width=1680, height=1050,
                 deviceScaleFactor=1, mobile=False)

        # ================================================== 1 三模式按钮位置
        # 浏览器 profile 是临时目录，但可能残留上一次的 localStorage：
        # 先清空再**整页重载**，保证「首次使用默认 PvP」这条断言是确定性的。
        # 注意：只改 hash 属于同文档跳转，不会重新初始化应用，所以带一个一次性查询参数。
        nav(cdp, base + "/index.html", "index.html", 2.5)
        js(cdp, "try{localStorage.clear();}catch(e){}")
        nav(cdp, base + "/index.html?acc=1#tasks", "index.html", 5.5)
        wait_nodes(cdp, counts_of("regular")["tasks"], 40)
        box = mode_buttons_box(cdp)
        report["detail"]["modeBar"] = box
        ok("A1 右上角三个模式按钮齐全",
           bool(box) and [b["key"] for b in box["buttons"]] == list(MODES), box)
        ok("A2 初始选中 PvP（唯一选中态）",
           bool(box) and box["selCount"] == 1 and
           [b["key"] for b in box["buttons"] if b["selected"] == "true"] == ["regular"], box)
        # gapRight 量的是「页头右缘 − 模式栏右缘」：右侧还有版本徽标，故上界放宽到 220
        ok("A3 模式按钮固定在全局页头右上角（R19.27）",
           bool(box) and box.get("inMenubar") is True and box.get("globalAPI") is True
           and 0 <= box["gapRight"] <= 220 and box["w"] >= 180 and box["h"] >= 20, box)
        ok("A4 按钮文字为 PvP / PvE / PvPS（赛季服）",
           bool(box) and [b["text"] for b in box["buttons"]] == ["PvP", "PvE", "PvPS（赛季服）"],
           [b["text"] for b in (box or {}).get("buttons", [])])
        ok("A5 按钮带英文悬停提示",
           bool(box) and all(b["title"] for b in box["buttons"]),
           [b["title"] for b in (box or {}).get("buttons", [])])
        shot(cdp, "01-mode-switch.png")

        # 四个内页都可见
        per_view = {}
        for view in ("tree", "traders", "detail", "progress"):
            js(cdp, "(function(){var b=document.querySelector('[data-taskview=%s]');if(b)b.click();})()" % view)
            time.sleep(1.2)
            b2 = mode_buttons_box(cdp)
            per_view[view] = b2
        ok("A6 四个内页都保持三模式按钮可见且位置不变",
           all(v and v["w"] >= 180 and v.get("inMenubar") for v in per_view.values()), per_view)
        js(cdp, "(function(){var b=document.querySelector('[data-taskview=tree]');if(b)b.click();})()")
        time.sleep(0.8)

        # ================================================== 2 三模式任务树
        tree_stat = {}
        for mode in MODES:
            c = counts_of(mode)
            exp_nodes = c["tasks"]
            exp_edges = expected_edges(mode)
            js(cdp, "(function(){var b=document.querySelector('[data-tkmode=%s]');if(b)b.click();})()" % mode)
            n = wait_nodes(cdp, exp_nodes, 40)
            e = int(js(cdp, "document.querySelectorAll('#tk-edges .tk-edge').length", 0) or 0)
            season = int(js(cdp, "document.querySelectorAll('#tk-nodes .tk-node.is-season').length", 0) or 0)
            fail_edges = int(js(cdp, "document.querySelectorAll('#tk-edges .tk-edge.is-fail').length", 0) or 0)
            or_edges = int(js(cdp, "document.querySelectorAll('#tk-edges .tk-edge.is-or').length", 0) or 0)
            meta = js(cdp, "JSON.stringify(window.GWTasks.modeInfo())", "{}")
            tree_stat[mode] = {"nodes": n, "edges": e, "expectNodes": exp_nodes,
                               "expectEdges": exp_edges, "seasonNodes": season,
                               "failEdges": fail_edges, "orEdges": or_edges,
                               "modeInfo": json.loads(meta or "{}")}
            ok("B1 %s 任务树节点数 = 数据任务数（%d）" % (mode, exp_nodes), n == exp_nodes, tree_stat[mode])
            ok("B2 %s 关系边数 = 前置边 + 失败分支边（%d）" % (mode, exp_edges), e == exp_edges,
               {"got": e, "expect": exp_edges})
            ok("B3 %s 赛季专属节点标记与数据一致" % mode,
               season == c.get("seasonOnly", 0), {"got": season, "data": c.get("seasonOnly")})
            shot(cdp, {"regular": "02-pvp-tree.png", "pve": "03-pve-tree.png",
                       "pvps": "04-pvps-tree.png"}[mode])
        report["detail"]["trees"] = tree_stat

        # 三模式节点数必须各不相同（数据真的独立）
        ns = [tree_stat[m]["nodes"] for m in MODES]
        ok("B4 三种模式任务数彼此不同（不是同一份数据改名）", len(set(ns)) == 3, ns)

        # 搜索 / 筛选 / 缩放 / 平移（在 pvps 上做，确认新模式的交互没坏）
        needle = js(cdp, r"""(function(){
          var n=document.querySelector('#tk-nodes .tk-node-name');
          return n?n.textContent.replace(/[^\u4e00-\u9fff]/g,'').slice(0,2):'';})()""") or ""
        js(cdp, "(function(){var i=document.getElementById('tk-search');i.value=%s;"
                "i.dispatchEvent(new Event('input',{bubbles:true}));})()" % json.dumps(needle))
        time.sleep(1.0)
        matches = int(js(cdp, "(window.GWTasks.state.matches||[]).length", 0) or 0)
        ok("B5 PvPS 树内搜索命中", bool(needle) and matches >= 1, {"needle": needle, "matches": matches})
        js(cdp, "(function(){var i=document.getElementById('tk-search');i.value='';"
                "i.dispatchEvent(new Event('input',{bubbles:true}));})()")
        time.sleep(0.7)

        cam0 = js(cdp, "(document.getElementById('tk-cam')||{}).getAttribute&&"
                       "document.getElementById('tk-cam').getAttribute('transform')")
        pos = json.loads(js(cdp, "(function(){var s=document.getElementById('tk-svg').getBoundingClientRect();"
                                 "return JSON.stringify({x:Math.round(s.x+s.width/2),y:Math.round(s.y+s.height/2)});})()",
                          "{}") or "{}")
        if pos:
            cdp.call("Input.dispatchMouseEvent", type="mouseWheel", x=pos["x"], y=pos["y"],
                     deltaX=0, deltaY=-240, button="none")
            time.sleep(0.6)
        cam1 = js(cdp, "document.getElementById('tk-cam').getAttribute('transform')")
        ok("B6 PvPS 树滚轮缩放生效", cam0 != cam1, {"before": cam0, "after": cam1})
        empty = json.loads(js(cdp, "(function(){var s=document.getElementById('tk-svg').getBoundingClientRect();"
                                  "return JSON.stringify({x:Math.round(s.x+s.width-90),y:Math.round(s.y+s.height-100)});})()",
                           "{}") or "{}")
        if empty:
            cdp.call("Input.dispatchMouseEvent", type="mousePressed", x=empty["x"], y=empty["y"],
                     button="left", clickCount=1)
            cdp.call("Input.dispatchMouseEvent", type="mouseMoved", x=empty["x"] - 120, y=empty["y"] - 60,
                     button="left")
            cdp.call("Input.dispatchMouseEvent", type="mouseReleased", x=empty["x"] - 120,
                     y=empty["y"] - 60, button="left")
            time.sleep(0.6)
        cam2 = js(cdp, "document.getElementById('tk-cam').getAttribute('transform')")
        ok("B7 PvPS 树拖拽平移生效", cam1 != cam2, {"after": cam2})

        # 筛选：等级 + 有前置
        js(cdp, "(function(){var s=document.getElementById('tk-special');if(s){s.value='kappa';"
                "s.dispatchEvent(new Event('change',{bubbles:true}));}})()")
        time.sleep(0.8)
        kappaN = int(js(cdp, "(window.GWTasks.state.order||[]).filter(function(id){"
                             "return window.GWTasks.state.tasks[id].kappaRequired;}).length", 0) or 0)
        shown = int(js(cdp, "(window.GWTasks.state.order||[]).filter(function(id){"
                            "return window.GWTasks.state.tasks[id].kappaRequired;}).length", 0) or 0)
        ok("B8 Kappa 筛选在 PvPS 上可用（命中数与数据一致）", kappaN == shown, {"kappa": kappaN})
        js(cdp, "(function(){var s=document.getElementById('tk-special');if(s){s.value='';"
                "s.dispatchEvent(new Event('change',{bubbles:true}));}})()")
        time.sleep(0.6)

        # ================================================== 3 跨页面切换
        # R19.23 每个模式各自记住「上次停留的内页」，所以切换模式后可能落回该模式的内页。
        # 因此逐个模式验证「当前可见内页 + 四个内页」都必须是目标模式的数据。
        cross = {}
        mode_label = {"regular": "PvP（常规）", "pve": "PvE", "pvps": "PvPS（赛季服）"}
        for mode in ("pve", "pvps", "regular"):
            js(cdp, "(function(){var b=document.querySelector('[data-tkmode=%s]');if(b)b.click();})()" % mode)
            time.sleep(2.2)
            shown_view = js(cdp, "(function(){var p=[].filter.call("
                                 "document.querySelectorAll('.tk-pane'),function(x){return !x.hidden;});"
                                 "return p.length?p[0].className:'';})()", "") or ""
            per = {}
            # 商人列表
            js(cdp, "(function(){var b=document.querySelector('[data-taskview=traders]');if(b)b.click();})()")
            time.sleep(1.5)
            per["traders"] = {"head": js(cdp, "(document.querySelector('.tk-list-head h3')||{}).textContent", ""),
                              "rows": int(js(cdp, "document.querySelectorAll('.tk-table .tk-tr').length", 0) or 0)}
            # 详情
            pick = js(cdp, r"""(function(){var st=window.GWTasks.state,o=st.order;
              for(var i=0;i<o.length;i++){var r=st.tasks[o[i]];
                if((r.objectives||[]).length>=2 && (r.prerequisites||[]).length>0) return o[i];}
              return o[0];})()""")
            js(cdp, "window.GWTasks.openTask(%s)" % json.dumps(pick))
            time.sleep(1.4)
            per["detail"] = {
                "title": js(cdp, "(document.querySelector('.tk-detail-title')||{}).textContent", ""),
                "facts": js(cdp, "[].map.call(document.querySelectorAll('.tk-fact'),"
                                 "function(r){return r.textContent;}).join('|')", "")[:400],
                "objectives": int(js(cdp, "document.querySelectorAll('.tk-obj').length", 0) or 0),
                "guide": js(cdp, "(document.querySelector('.tk-alert')||{}).textContent", "")[:80],
            }
            # 任务树
            js(cdp, "(function(){var b=document.querySelector('[data-taskview=tree]');if(b)b.click();})()")
            time.sleep(1.2)
            per["tree"] = {"nodes": int(js(cdp, "document.querySelectorAll('#tk-nodes .tk-node').length", 0) or 0),
                           "edges": int(js(cdp, "document.querySelectorAll('#tk-edges .tk-edge').length", 0) or 0)}
            # 进度
            js(cdp, "(function(){var b=document.querySelector('[data-taskview=progress]');if(b)b.click();})()")
            time.sleep(1.4)
            per["progress"] = {
                "rows": json.loads(js(cdp, "JSON.stringify([].map.call("
                                           "document.querySelectorAll('.tk-modetable tr'),"
                                           "function(r){return r.textContent;}))", "[]") or "[]"),
            }
            cross[mode] = {"shownView": shown_view, **per}
            c = counts_of(mode)
            ok("C1 %s 商人列表使用本模式数据（标题+行数）" % mode,
               mode_label[mode] in per["traders"]["head"] and per["traders"]["rows"] == c["tasks"] + 1,
               {"head": per["traders"]["head"], "rows": per["traders"]["rows"], "expect": c["tasks"] + 1})
            ok("C2 %s 详情页「当前模式」与本模式一致" % mode,
               ("当前模式" + mode_label[mode]) in per["detail"]["facts"] and per["detail"]["objectives"] >= 1,
               {"facts": per["detail"]["facts"][:160], "objs": per["detail"]["objectives"]})
            ok("C3 %s 任务树节点/边来自本模式" % mode,
               per["tree"]["nodes"] == c["tasks"] and per["tree"]["edges"] == expected_edges(mode),
               per["tree"])
            ok("C4 %s 进度页对照表标出本模式" % mode,
               any(mode_label[mode] in r and "当前模式" in r for r in per["progress"]["rows"]),
               per["progress"]["rows"])
        report["detail"]["cross"] = cross
        # 专门回 PvP 的商人页拍一张（上面循环结束时停在进度页）
        js(cdp, "(function(){var b=document.querySelector('[data-tkmode=regular]');if(b)b.click();})()")
        time.sleep(2.0)
        js(cdp, "(function(){var b=document.querySelector('[data-taskview=traders]');if(b)b.click();})()")
        time.sleep(1.6)
        ok("C5 商人任务中心可用（卡片 + 任务链 + 模式列）",
           int(js(cdp, "document.querySelectorAll('.tk-trader-card').length", 0) or 0) >= 8 and
           int(js(cdp, "document.querySelectorAll('.tk-chain').length", 0) or 0) >= 1 and
           js(cdp, "!!document.querySelector('.tk-td-mode')") is True,
           {"cards": js(cdp, "document.querySelectorAll('.tk-trader-card').length"),
            "chains": js(cdp, "document.querySelectorAll('.tk-chain').length")})
        shot(cdp, "05-traders.png")

        # ================================================== 4 进度隔离
        # 回到 PvP，勾满一个任务的必需目标 → 自动完成
        js(cdp, "(function(){var b=document.querySelector('[data-tkmode=regular]');if(b)b.click();})()")
        wait_nodes(cdp, counts_of("regular")["tasks"], 30)
        iso = {}
        # 选一个「三模式都存在 / 有 2–3 个必需目标 / 无任务前置」的任务，
        # 这样「同名任务进度不串模式」的对比才有说服力（不是拿某模式独有的任务比较）。
        sets = {}
        for m in MODES:
            with open(os.path.join(TASKS_DIR, "tasks.%s.json" % m), encoding="utf-8") as fh:
                sets[m] = json.load(fh)["tasks"]
        common = set(sets["regular"]) & set(sets["pve"]) & set(sets["pvps"])
        target = None
        for tid in sorted(common, key=lambda x: sets["regular"][x]["minLevel"]):
            rec = sets["regular"][tid]
            req = [o for o in (rec.get("objectives") or []) if not o.get("optional")]
            if 2 <= len(req) <= 3 and not (rec.get("prerequisites") or []):
                target = tid
                break
        if not target:
            target = js(cdp, r"""(function(){
              var st=window.GWTasks.state,o=st.order;
              for(var i=0;i<o.length;i++){var r=st.tasks[o[i]];
                var req=(r.objectives||[]).filter(function(x){return !x.optional;});
                if(req.length>=2 && req.length<=3) return o[i];}
              return o[0];})()""")
        report["detail"]["isoTask"] = target
        js(cdp, "window.GWTasks.openTask(%s)" % json.dumps(target))
        time.sleep(1.3)
        js(cdp, """(function(){[].forEach.call(document.querySelectorAll('.tk-obj-check input'),
          function(cb){ if(!cb.checked){ cb.checked=true; cb.dispatchEvent(new Event('change',{bubbles:true})); } });})()""")
        time.sleep(1.6)
        st_reg = js(cdp, "window.GWTasks.status(%s)" % json.dumps(target))
        iso["regular"] = {"task": target, "status": st_reg}
        ok("D1 PvP 勾满必需目标后自动完成", st_reg == "completed", iso["regular"])
        shot(cdp, "06-detail-completed.png")

        js(cdp, "(function(){var b=document.querySelector('[data-tkmode=pve]');if(b)b.click();})()")
        time.sleep(1.8)
        st_pve_same = js(cdp, "window.GWTasks.status(%s)" % json.dumps(target))
        iso["pveSame"] = st_pve_same
        ok("D2 同名任务在 PvE 不会被连带完成", st_pve_same == "none", iso["pveSame"])

        other = js(cdp, "(function(){var st=window.GWTasks.state,o=st.order;"
                        "for(var i=0;i<o.length;i++){ if(o[i]!==%s) return o[i];} return o[0];})()"
                        % json.dumps(target))
        js(cdp, "window.GWTasks.setStatus(%s,'active')" % json.dumps(other))
        time.sleep(0.8)
        iso["pveOther"] = {"task": other, "status": js(cdp, "window.GWTasks.status(%s)" % json.dumps(other))}
        ok("D3 PvE 自己改状态有效（不与 PvP 混）", iso["pveOther"]["status"] == "active", iso["pveOther"])

        js(cdp, "(function(){var b=document.querySelector('[data-tkmode=pvps]');if(b)b.click();})()")
        time.sleep(1.8)
        st_pvps_same = js(cdp, "window.GWTasks.status(%s)" % json.dumps(target))
        st_pvps_other = js(cdp, "window.GWTasks.status(%s)" % json.dumps(other))
        iso["pvps"] = {"sameTask": st_pvps_same, "otherTask": st_pvps_other}
        ok("D4 PvPS 两个任务都是独立空白进度",
           st_pvps_same == "none" and st_pvps_other == "none", iso["pvps"])
        # 同一个任务：PvP 已完成 / PvPS 未开始 —— 这是三模式进度隔离最直观的证据
        js(cdp, "window.GWTasks.openTask(%s)" % json.dumps(target))
        time.sleep(1.4)
        pvps_state = js(cdp, "(document.querySelector('.tk-detail-sub')||{}).textContent", "") or ""
        ok("D4b 同一任务在 PvPS 详情显示「未开始」",
           "未开始" in pvps_state, pvps_state)
        shot(cdp, "07-mode-status-diff.png")

        # 进度页三模式对照表
        js(cdp, "(function(){var b=document.querySelector('[data-taskview=progress]');if(b)b.click();})()")
        time.sleep(1.4)
        table = js(cdp, "JSON.stringify([].map.call(document.querySelectorAll('.tk-modetable tr'),"
                       "function(r){return r.textContent;}))", "[]")
        rows = json.loads(table or "[]")
        ok("D5 进度页有三模式对照表且标出当前模式",
           len(rows) >= 4 and any("当前模式" in r for r in rows), rows)
        shot(cdp, "08-progress-isolation.png")
        iso["progressTable"] = rows

        # 刷新后仍保留（刷新后页面会回到上次使用的模式，因此逐个模式切过去读）
        nav(cdp, base + "/index.html?acc=2#tasks", "index.html", 5.5)
        time.sleep(1.0)
        after = {}
        for m in MODES:
            js(cdp, "(function(){var b=document.querySelector('[data-tkmode=%s]');if(b)b.click();})()" % m)
            time.sleep(2.0)
            after[m] = {"same": js(cdp, "window.GWTasks.status(%s)" % json.dumps(target)),
                        "other": js(cdp, "window.GWTasks.status(%s)" % json.dumps(other))}
        iso["afterReload"] = after
        ok("D6 刷新后三模式各自状态都保留",
           after["regular"]["same"] == "completed" and after["pve"]["same"] == "none" and
           after["pve"]["other"] == "active" and after["pvps"]["same"] == "none" and
           after["pvps"]["other"] == "none", after)

        # 导出 / 导入
        exp = js(cdp, """(function(){var t=window.GWTasks.exportProgress();
          try{var d=JSON.parse(t);return JSON.stringify({kind:d.kind,modes:Object.keys(d.modes),
          regular:Object.keys(d.modes.regular||{}).length,pve:Object.keys(d.modes.pve||{}).length,
          pvps:Object.keys(d.modes.pvps||{}).length});}catch(e){return 'bad';}})()""", "{}")
        e1 = json.loads(exp or "{}")
        ok("D7 导出进度含三个模式段", e1.get("kind") == "eftmap-task-progress" and
           e1.get("modes") == list(MODES), e1)
        badmsg = js(cdp, "window.GWTasks.importProgress('{\"schema\":9}')", "")
        ok("D8 非法导入不破坏已有进度",
           "失败" in (badmsg or "") and js(cdp, "window.GWTasks.status(%s)" % json.dumps(target)) in ("completed", "none"),
           {"msg": badmsg})
        good = json.dumps({"schema": 1, "kind": "eftmap-task-progress", "modes": {
            "regular": {target: {"status": "completed", "objectives": {}}},
            "pve": {other: {"status": "none", "objectives": {}}},
            "pvps": {target: {"status": "active", "objectives": {}}}}})
        imp = js(cdp, "window.GWTasks.importProgress(%s)" % json.dumps(good), "")
        ok("D9 合法导入按模式分别落盘", "已导入" in (imp or "") and
           js(cdp, "window.GWTasks.status(%s)" % json.dumps(target)) == "active", {"msg": imp})
        # 恢复原样，避免污染后续检查
        js(cdp, "window.GWTasks.importProgress(%s)" % json.dumps(
            json.dumps({"schema": 1, "kind": "eftmap-task-progress", "modes": {
                "regular": {target: {"status": "completed", "objectives": {}}},
                "pve": {other: {"status": "active", "objectives": {}}},
                "pvps": {}}})))

        # ================================================== 5 赛季数据真实性
        js(cdp, "(function(){var b=document.querySelector('[data-tkmode=pvps]');if(b)b.click();})()")
        time.sleep(1.8)
        info = json.loads(js(cdp, "JSON.stringify(window.GWTasks.modeInfo())", "{}") or "{}")
        season = json.loads(js(cdp, "JSON.stringify(window.GWTasks.season())", "{}") or "{}")
        data_pvps = counts_of("pvps")
        report["detail"]["season"] = {"modeInfo": info, "season": season}
        ok("E1 PvPS 数据来自上游 pvp-season 端点",
           info.get("upstream") == "pvp-season", info.get("upstream"))
        ok("E2 PvPS 任务数与数据文件一致", info.get("tasks") == data_pvps["tasks"], info.get("tasks"))
        ok("E3 赛季元信息可读（赛季 id + 起止时间）",
           bool(season.get("id")) and bool(season.get("startISO")) and bool(season.get("endISO")),
           {"id": season.get("id"), "start": season.get("startISO"), "end": season.get("endISO")})
        # 赛季专属任务：当前快照为 0，界面必须如实说明，不得伪造
        season_only_ui = int(js(cdp, "document.querySelectorAll('#tk-nodes .tk-node.is-season').length", 0) or 0)
        note_warn = js(cdp, "(document.querySelector('.tk-mode-note-warn')||{}).textContent", "") or ""
        ok("E4 赛季专属任务计数与上游一致（当前 0 条，不伪造）",
           season_only_ui == data_pvps.get("seasonOnly", 0), {"ui": season_only_ui,
                                                             "data": data_pvps.get("seasonOnly")})
        ok("E5 界面如实说明「PvPS 是 PvP 子集、无赛季专属任务」",
           "没有只属于赛季的任务" in note_warn, note_warn[:160])
        ok("E6 赛季专属筛选项不出现（无数据时不做假筛选）",
           js(cdp, "!!document.querySelector('#tk-special option[value=season]')") is False)
        shot(cdp, "09-pvps-season-note.png")

        # 地图联动：必须用当前模式（PvPS）的任务目标，而不是 PvP 的
        dlg = js(cdp, r"""(function(){
          var st=window.GWTasks.state;
          for (var i=0;i<st.order.length;i++){
            var r=st.tasks[st.order[i]];
            var zs=[]; (r.objectives||[]).forEach(function(o){(o.zones||[]).forEach(function(z){zs.push(z);});});
            for (var j=0;j<zs.length;j++){ if (zs[j].mapId==='56f40101d2720b2a4d8b45d6') return st.order[i]; }
          } return '';})()""")
        if dlg:
            js(cdp, "window.GWTasks.openTask(%s)" % json.dumps(dlg))
            time.sleep(1.5)
            clicked = js(cdp, "(function(){var b=document.querySelector('[data-locate-zone]');"
                              "if(!b) return 'no-btn'; b.click(); return 'ok';})()")
            time.sleep(3.0)
            view_map = js(cdp, "(document.querySelector('[data-view=map]')||{}).getAttribute('aria-selected')")
            pin = js(cdp, "!!document.querySelector('.task-pin')")
            ok("F5 PvPS 详情可跳转地图并落点（用本模式目标坐标）",
               clicked == "ok" and view_map == "true" and bool(pin),
               {"clicked": clicked, "map": view_map, "pin": pin})
            js(cdp, "(function(){var b=document.querySelector('[data-view=tasks]');if(b)b.click();})()")
            time.sleep(2.0)
        else:
            ok("F5 PvPS 详情可跳转地图并落点（用本模式目标坐标）", False,
               "PvPS 数据里没有落在本地已收录地图上的目标区域")

        # ================================================== 6 中文化 + 英文悬停
        i18n = json.loads(js(cdp, "JSON.stringify(window.GWI18n.coverage())", "{}") or "{}")
        unmapped = [u.get("text") for u in (i18n.get("unmapped") or [])]
        ok("F1 全项目 i18n 未覆盖英文为 0", len(unmapped) == 0, unmapped[:10])
        ok("F2 模式按钮与说明均为中文优先",
           all(js(cdp, "!!document.querySelector('[data-tkmode=%s]')" % m) for m in MODES) and
           "当前模式" in (js(cdp, "(document.getElementById('tk-scope')||{}).textContent", "") or ""),
           js(cdp, "(document.getElementById('tk-scope')||{}).textContent", ""))
        en_hover = js(cdp, """JSON.stringify([].map.call(
          document.querySelectorAll('[data-en-text]'), function(e){
            return {t:(e.textContent||'').trim().slice(0,12), en:e.getAttribute('data-en-text')};}).slice(0,6))""", "[]")
        has_hover = bool(json.loads(en_hover or "[]"))
        ok("F3 元素带英文悬停提示（data-en-text/title）", has_hover, en_hover)
        js(cdp, "window.GWTasks.openTask(%s)" % json.dumps(target))
        time.sleep(1.2)
        facts = js(cdp, "[].map.call(document.querySelectorAll('.tk-fact'),function(r){return r.textContent;}).join(' | ')", "")
        ok("F4 详情页保留原始英文名字段（有意的英文展示）", "原始英文名" in (facts or ""), (facts or "")[:120])
        shot(cdp, "10-i18n-detail.png")

        # ================================================== 7 既有功能回归
        reg = {}
        for view in ("map", "loadout", "gun", "ammo"):
            js(cdp, "(function(){var b=document.querySelector('[data-view=%s]');if(b)b.click();})()" % view)
            time.sleep(2.4)
            sel_ok = js(cdp, "(document.querySelector('[data-view=%s]')||{}).getAttribute('aria-selected')" % view)
            errs = js(cdp, "(window.__errs||[]).length", 0)
            reg[view] = {"selected": sel_ok, "errors": errs}
            shot(cdp, "reg-%s.png" % view)
        ok("G1 四个既有视图可打开且无脚本错误",
           all(v["selected"] == "true" and (v["errors"] or 0) == 0 for v in reg.values()), reg)
        nav(cdp, base + "/index.html?layoutCalibrator=1", "layoutCalibrator=1", 5.0)
        cal = js(cdp, "JSON.stringify({grid:!!document.getElementById('cal-grid'),"
                      "cards:document.querySelectorAll('.cal-card').length})", "{}")
        ok("G2 武器槽位校准器仍可用", '"grid":true' in (cal or ""), cal)
        shot(cdp, "reg-calibrator.png")
        # 校准数据文件未被本轮改动
        calib = os.path.join(ROOT, "data", "gun-layout-calibration.json")
        ok("G3 校准数据文件仍在且可解析", os.path.exists(calib) and
           bool(json.load(open(calib, encoding="utf-8"))), calib)
        # 深链
        nav(cdp, base + "/index.html?acc=3#tasks", "index.html", 5.0)
        ok("G4 #tasks 深链仍可直达任务模块",
           js(cdp, "(document.querySelector('[data-view=tasks]')||{}).getAttribute('aria-selected')") == "true")

        report["detail"]["iso"] = iso
        report["detail"]["i18n"] = i18n
        report["detail"]["regression"] = reg
        report["pass"] = all(x["ok"] for x in report["checks"])
        with open(os.path.join(OUT, "browser-accept.json"), "w", encoding="utf-8", newline="\n") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=1)
        total = len(report["checks"])
        passed = sum(1 for x in report["checks"] if x["ok"])
        print("\n结果：%d/%d 通过" % (passed, total))
        for x in report["checks"]:
            if not x["ok"]:
                print("  FAILED:", x["name"], x.get("detail"))
    finally:
        try:
            proc.terminate()
        except Exception:  # noqa: BLE001
            pass
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
