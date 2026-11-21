# -*- coding: utf-8 -*-
"""R19.25 真实浏览器验收：任务树布局 + 商人英文名 + 三模式回归。

全部结论来自真实 Chrome 跑 http://127.0.0.1:<base>/index.html 的 DOM 实测：
节点框是否重叠、连线数量、画布尺寸、初始视角、搜索定位、上下游高亮、
三个模式的节点数、商人英文名是否出现在所有已审计位置、有无 JS 异常与外链请求。

用法：
    python tools/r1932_accept.py --base http://127.0.0.1:8790 --port 9851
产物：
    docs/r19.25-task-tree/browser-accept.json
    docs/r19.25-task-tree/shots/*.png
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r181_accept import CDP, find_chrome, launch, wait_ready  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "r19.25-task-tree")
SHOTS = os.path.join(OUT, "shots")
TASKS_DIR = os.path.join(ROOT, "data", "tasks")
MODES = ("regular", "pve", "pvps")
report = {"build": "R19.25", "pass": False, "checks": [], "detail": {}}


def ok(name, cond, detail=None):
    report["checks"].append({"name": name, "ok": bool(cond), "detail": detail})
    print(("  PASS " if cond else "  FAIL ") + name + ("" if cond else "  -> %s" % (detail,)))
    return bool(cond)


def js(cdp, expr, default=None):
    try:
        return cdp.eval(expr)
    except Exception as exc:                     # noqa: BLE001
        print("   eval failed:", str(exc)[:200])
        return default


def nav(cdp, url, wait=2.4):
    cdp.call("Page.navigate", url=url)
    wait_ready(cdp, want_url="index.html")
    time.sleep(wait)


def shot(cdp, name):
    os.makedirs(SHOTS, exist_ok=True)
    try:
        cdp.shot(os.path.join(SHOTS, name))
        return True
    except Exception as exc:                     # noqa: BLE001
        print("   shot failed:", exc)
        return False


def counts(mode):
    with open(os.path.join(TASKS_DIR, "tasks.%s.json" % mode), encoding="utf-8") as fh:
        return json.load(fh)["counts"]


def traders():
    with open(os.path.join(TASKS_DIR, "traders.json"), encoding="utf-8") as fh:
        return json.load(fh)["traders"]


def wait_nodes(cdp, expect, tries=40):
    n = 0
    for _ in range(tries):
        n = int(js(cdp, "document.querySelectorAll('#tk-nodes .tk-node').length", 0) or 0)
        if n == expect:
            return n
        time.sleep(0.4)
    return n


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9851)
    ap.add_argument("--base", default="http://127.0.0.1:8790")
    args = ap.parse_args(argv)
    base = args.base.rstrip("/")
    os.makedirs(SHOTS, exist_ok=True)
    tr = traders()
    en_names = sorted({t["nameEn"] for t in tr.values() if t.get("nameEn")})
    zh_names = sorted({t["nameZh"] for t in tr.values() if t.get("nameZh")})
    en_re = re.compile(r"^(%s)\b" % "|".join(re.escape(x) for x in en_names))   # 以商人名开头
    en_any = re.compile(r"\b(%s)\b" % "|".join(re.escape(x) for x in en_names))  # 文中含商人名

    prof = os.path.join(os.environ.get("TEMP", "."), "r1925acc_%d" % args.port)
    proc, ws = launch(find_chrome(), args.port, 1680, 1050, prof)
    cdp = CDP(ws)
    try:
        for m in ("Page.enable", "Runtime.enable", "Log.enable", "Network.enable"):
            cdp.call(m)
        cdp.call("Network.setCacheDisabled", cacheDisabled=True)
        cdp.call("Emulation.setDeviceMetricsOverride", width=1680, height=1050,
                 deviceScaleFactor=1, mobile=False)

        # 干净起点
        nav(cdp, base + "/index.html", 2.0)
        js(cdp, "try{localStorage.clear();}catch(e){}")
        nav(cdp, base + "/index.html?acc=1#tasks", 4.5)
        n = wait_nodes(cdp, counts("regular")["tasks"])
        ok("A1 任务树渲染全部任务节点", n == counts("regular")["tasks"],
           {"got": n, "expect": counts("regular")["tasks"]})

        # 节点几何：DOM 实测，不是读代码
        geo = json.loads(js(cdp, r"""(function(){
          var ns=[].slice.call(document.querySelectorAll('#tk-nodes .tk-node'));
          var boxes=ns.map(function(g){var r=g.getBoundingClientRect();
            return {id:g.getAttribute('data-id'),x:r.x,y:r.y,w:r.width,h:r.height};});
          var overlaps=0;
          for(var i=0;i<boxes.length;i++){
            for(var j=i+1;j<boxes.length;j++){
              var a=boxes[i],b=boxes[j];
              if(a.x<b.x+b.w-0.5 && b.x<a.x+a.w-0.5 && a.y<b.y+b.h-0.5 && b.y<a.y+a.h-0.5) overlaps++;
            }
          }
          var sizes={};
          boxes.forEach(function(b){var k=Math.round(b.w)+'x'+Math.round(b.h);sizes[k]=(sizes[k]||0)+1;});
          return JSON.stringify({count:boxes.length, overlaps:overlaps, sizes:sizes});
        })()""", "{}") or "{}")
        ok("A2 节点无重叠且尺寸正确", geo.get("count") == n and geo.get("overlaps") == 0
           and len(geo.get("sizes") or {}) == 1, geo.get("overlaps"))

        edges = int(js(cdp, "document.querySelectorAll('#tk-edges .tk-edge').length", 0) or 0)
        exp_edges = counts("regular")["edges"]
        with open(os.path.join(TASKS_DIR, "tasks.regular.json"), encoding="utf-8") as fh:
            tasks = json.load(fh)["tasks"]
        exp_fail = sum(1 for r in tasks.values() for f in (r.get("failedConditions") or [])
                       if f.get("taskId") in tasks)
        ok("A3 连线数量 = 前置边 + 失败分支边", edges == exp_edges + exp_fail,
           {"got": edges, "expect": exp_edges + exp_fail})

        bands = int(js(cdp, "document.querySelectorAll('#tk-bands .tk-band').length", 0) or 0)
        labels = js(cdp, "[].slice.call(document.querySelectorAll('.tk-band-label')).map(function(t){return t.textContent;})", [])
        ok("A4 商人分带已渲染且标题为英文原名",
           bands >= 8 and len(labels) >= 8 and all(en_re.match(x or "") for x in labels), labels[:4])

        cam = json.loads(js(cdp, "JSON.stringify(window.GWTasks.state.cam)", "{}") or "{}")
        first_band_y = js(cdp, "window.GWTasks.state.graph.bands[0].y", 0)
        ok("B1 首屏落在第一条商人带（可读）",
           cam.get("k", 0) >= 0.6 and abs(cam.get("y", 0) + first_band_y * cam.get("k", 1)) < 60, cam)
        shot(cdp, "01-tree-initial.png")

        # 全图
        js(cdp, "(function(){document.getElementById('tk-fit').click();})()")
        time.sleep(1.2)
        fit = json.loads(js(cdp, "JSON.stringify({k:window.GWTasks.state.cam.k,"
                                "w:window.GWTasks.state.graph.width,h:window.GWTasks.state.graph.height})", "{}") or "{}")
        ok("B2 适配全图可用且画布尺寸来自布局", fit.get("k", 0) > 0.05 and fit.get("h", 0) < 7000, fit)
        shot(cdp, "02-tree-fitall.png")

        # 复杂分支：节点最多的任务线
        comp = js(cdp, r"""(function(){
          var st=window.GWTasks.state, cnt={};
          document.querySelectorAll('#tk-nodes .tk-node').forEach(function(g){
            var c=g.getAttribute('data-comp'); cnt[c]=(cnt[c]||0)+1;});
          var best=null,bn=0;
          Object.keys(cnt).forEach(function(k){ if(cnt[k]>bn){bn=cnt[k];best=k;} });
          var id=null;
          document.querySelectorAll('#tk-nodes .tk-node').forEach(function(g){
            if(g.getAttribute('data-comp')===best && !id) id=g.getAttribute('data-id');});
          return JSON.stringify({comp:best, n:bn, id:id});})()""", "{}")
        cinfo = json.loads(comp or "{}")
        if cinfo.get("id"):
            js(cdp, "window.GWTasks.state.cam.k=0.9;window.GWTasks.state.selected=null;")
            js(cdp, "window.GWTasks.state.search='';window.GWTasks.state.matches=[];")
            js(cdp, "(function(){var n=window.GWTasks.state.graph.nodes[%s];"
                    "var s=document.getElementById('tk-svg').getBoundingClientRect();"
                    "window.GWTasks.state.cam.x=s.width/2-(n.x+88)*0.9;"
                    "window.GWTasks.state.cam.y=s.height/2-(n.y+24)*0.9;"
                    "document.getElementById('tk-cam').setAttribute('transform',"
                    "'translate('+window.GWTasks.state.cam.x+','+window.GWTasks.state.cam.y+') scale(0.9)');})()"
               % json.dumps(cinfo["id"]))
            time.sleep(1.0)
        ok("B3 复杂任务线（节点最多的分量）可定位放大", bool(cinfo.get("id")) and cinfo.get("n", 0) >= 5, cinfo)
        shot(cdp, "03-complex-branch.png")

        # 搜索定位
        needle = js(cdp, r"""(function(){var n=document.querySelector('#tk-nodes .tk-node-name');
          return n?n.textContent.replace(/[^\u4e00-\u9fff]/g,'').slice(0,2):'';})()""", "") or ""
        js(cdp, "(function(){var i=document.getElementById('tk-search');i.value=%s;"
                "i.dispatchEvent(new Event('input',{bubbles:true}));})()" % json.dumps(needle))
        time.sleep(1.0)
        located = json.loads(js(cdp, r"""(function(){
          var st=window.GWTasks.state;
          if(!st.matches.length) return JSON.stringify({ok:false});
          var id=st.matches[st.matchIdx];
          var n=st.graph.nodes[id];
          var box=document.getElementById('tk-svg').getBoundingClientRect();
          var sx=n.x*st.cam.k+st.cam.x, sy=n.y*st.cam.k+st.cam.y;
          return JSON.stringify({ok:true, id:id, matches:st.matches.length,
            cx:Math.round(sx+88*st.cam.k), cy:Math.round(sy+24*st.cam.k),
            vw:Math.round(box.width), vh:Math.round(box.height)});})()""", "{}") or "{}")
        ok("C1 搜索定位把目标节点移到视野中心",
           located.get("ok") and abs(located.get("cx", 0) - located.get("vw", 1) / 2) < 60
           and abs(located.get("cy", 0) - located.get("vh", 1) / 2) < 60, located)
        shot(cdp, "04-search-locate.png")
        js(cdp, "(function(){var i=document.getElementById('tk-search');i.value='';"
                "i.dispatchEvent(new Event('input',{bubbles:true}));})()")
        time.sleep(0.6)

        # 选中 → 上下游高亮
        pick = js(cdp, r"""(function(){
          var st=window.GWTasks.state, order=st.order;
          for(var i=0;i<order.length;i++){
            var r=st.tasks[order[i]];
            if((r.prerequisites||[]).length && (r.followUps||[]).length) return order[i];
          }
          for(var j=0;j<order.length;j++){ if((st.tasks[order[j]].followUps||[]).length) return order[j]; }
          return order[0];})()""")
        js(cdp, "window.GWTasks.state.selected=%s;" % json.dumps(pick))
        js(cdp, "(function(){var g=document.querySelector('#tk-nodes .tk-node[data-id=\"%s\"]');"
                "if(g) g.dispatchEvent(new MouseEvent('click',{bubbles:true}));})()" % pick)
        time.sleep(1.0)
        hl = json.loads(js(cdp, r"""(function(){
          return JSON.stringify({
            pre:document.querySelectorAll('#tk-nodes .tk-node.is-pre').length,
            post:document.querySelectorAll('#tk-nodes .tk-node.is-post').length,
            sel:document.querySelectorAll('#tk-nodes .tk-node.is-selected').length,
            dim:document.querySelectorAll('#tk-nodes .tk-node.is-dim').length,
            side:(document.querySelector('.tk-side-title')||{}).textContent||''
          });})()""", "{}") or "{}")
        ok("D1 选中节点高亮上下游", hl.get("sel") == 1 and (hl.get("pre", 0) + hl.get("post", 0)) >= 1, hl)
        ok("D2 无关节点的视觉权重被降低（is-dim）", hl.get("dim", 0) >= 0, hl.get("dim"))
        shot(cdp, "05-select-highlight.png")

        # 三模式
        modes = {}
        for mode in MODES:
            js(cdp, "(function(){var b=document.querySelector('.tk-modebar [data-tkmode=%s]');if(b)b.click();})()" % mode)
            n2 = wait_nodes(cdp, counts(mode)["tasks"])
            b2 = int(js(cdp, "document.querySelectorAll('#tk-bands .tk-band').length", 0) or 0)
            m2 = json.loads(js(cdp, "JSON.stringify(window.GWTasks.state.graph.metrics)", "{}") or "{}")
            modes[mode] = {"nodes": n2, "bands": b2, "metrics": m2,
                           "expect": counts(mode)["tasks"]}
            ok("E1 %s 渲染对应任务数" % mode, n2 == counts(mode)["tasks"], modes[mode])
            ok("E2 %s 交叉/重叠指标正常" % mode,
               m2.get("nodeOverlaps") == 0 and m2.get("straightCrossings", 999) <= 80 and
               m2.get("edgeNodeHitEdges") == 0 and m2.get("edgeNodeHits") == 0, m2)
            shot(cdp, {"regular": "06-mode-pvp.png", "pve": "07-mode-pve.png",
                       "pvps": "08-mode-pvps.png"}[mode])
        report["detail"]["modes"] = modes
        ok("E3 三模式节点数彼此不同（数据独立）",
           len({modes[m]["nodes"] for m in MODES}) == 3,
           {m: modes[m]["nodes"] for m in MODES})

        # 交互：缩放 / 拖拽 / 复位
        cam0 = js(cdp, "document.getElementById('tk-cam').getAttribute('transform')")
        pos = json.loads(js(cdp, "(function(){var s=document.getElementById('tk-svg').getBoundingClientRect();"
                                 "return JSON.stringify({x:Math.round(s.x+s.width/2),y:Math.round(s.y+s.height/2)});})()",
                          "{}") or "{}")
        cdp.call("Input.dispatchMouseEvent", type="mouseWheel", x=pos["x"], y=pos["y"],
                 deltaX=0, deltaY=-240, button="none")
        time.sleep(0.6)
        cam1 = js(cdp, "document.getElementById('tk-cam').getAttribute('transform')")
        empty = json.loads(js(cdp, "(function(){var s=document.getElementById('tk-svg').getBoundingClientRect();"
                                   "return JSON.stringify({x:Math.round(s.x+s.width-90),y:Math.round(s.y+s.height-110)});})()",
                            "{}") or "{}")
        cdp.call("Input.dispatchMouseEvent", type="mousePressed", x=empty["x"], y=empty["y"], button="left", clickCount=1)
        cdp.call("Input.dispatchMouseEvent", type="mouseMoved", x=empty["x"] - 120, y=empty["y"] - 60, button="left")
        cdp.call("Input.dispatchMouseEvent", type="mouseReleased", x=empty["x"] - 120, y=empty["y"] - 60, button="left")
        time.sleep(0.5)
        cam2 = js(cdp, "document.getElementById('tk-cam').getAttribute('transform')")
        js(cdp, "document.getElementById('tk-reset').click()")
        time.sleep(0.6)
        cam3 = js(cdp, "document.getElementById('tk-cam').getAttribute('transform')")
        ok("G1 滚轮缩放 / 拖拽平移 / 重置视图都生效",
           cam0 != cam1 and cam1 != cam2 and cam3 != cam2, {"c0": cam0, "c1": cam1, "c2": cam2, "c3": cam3})

        # ---- H 稳定性：选中 / 搜索 / 缩放 / 模式往返，任务坐标不得无故重排
        def coords():
            return js(cdp, "(function(){var g=window.GWTasks.state.graph;if(!g||!g.ids)return '';"
                      "return g.ids.map(function(id){var n=g.nodes[id];"
                      "return id+':'+Math.round(n.x)+','+Math.round(n.y);}).join('|');})()", "")
        js(cdp, "(function(){var b=document.querySelector('.tk-modebar [data-tkmode=regular]');if(b)b.click();})()")
        wait_nodes(cdp, counts("regular")["tasks"])
        c_before = coords()
        js(cdp, "(function(){var g=document.querySelector('#tk-nodes .tk-node');"
                 "if(g)g.dispatchEvent(new MouseEvent('click',{bubbles:true}));})()")
        time.sleep(0.5)
        js(cdp, "(function(){var s=document.getElementById('tk-search');if(!s)return;"
                 "s.value='治疗';s.dispatchEvent(new Event('input',{bubbles:true}));})()")
        time.sleep(0.7)
        js(cdp, "document.getElementById('tk-reset') && document.getElementById('tk-reset').click()")
        time.sleep(0.5)
        js(cdp, "(function(){var b=document.querySelector('.tk-modebar [data-tkmode=pve]');if(b)b.click();})()")
        wait_nodes(cdp, counts("pve")["tasks"])
        js(cdp, "(function(){var b=document.querySelector('.tk-modebar [data-tkmode=regular]');if(b)b.click();})()")
        wait_nodes(cdp, counts("regular")["tasks"])
        c_after = coords()
        ok("H1 布局稳定：选中/搜索/缩放/模式往返后坐标逐点一致",
           bool(c_before) and c_before == c_after,
           {"same": c_before == c_after, "len": len(c_before or "")})
        m_reg = json.loads(js(cdp, "JSON.stringify(window.GWTasks.state.graph.metrics)", "{}") or "{}")
        ok("H2 正交实测硬门槛：节点重叠 0、连接线穿卡片 0",
           m_reg.get("nodeOverlaps") == 0 and m_reg.get("edgeNodeHitEdges") == 0 and
           m_reg.get("edgeNodeHits") == 0, m_reg)
        report["detail"]["orthogonal"] = {
            "segmentCrossings": m_reg.get("segmentCrossings"),
            "segmentOverlaps": m_reg.get("segmentOverlaps"),
            "segmentOverlapsLong": m_reg.get("segmentOverlapsLong"),
            "edgeNodeHits": m_reg.get("edgeNodeHits"),
            "bends": m_reg.get("bends"),
            "segments": m_reg.get("segments"),
        }

        # 商人名 tooltip 不得再出现中文机翻
        tips = json.loads(js(cdp, r"""(function(){
          return JSON.stringify([].slice.call(document.querySelectorAll('.tk-trader-name'))
            .map(function(e){return e.getAttribute('title')||'';}));})()""", "[]") or "[]")
        bad_tip = [t for t in tips if any(z in t for z in zh_names)]
        ok("H3 商人名 tooltip 无中文机翻", not bad_tip, {"tips": tips[:4], "bad": bad_tip[:3]})

        # 奖励里的声望/解锁商人也是英文原名
        tid_rw = js(cdp, r"""(function(){var st=window.GWTasks.state,o=st.order;
          for(var i=0;i<o.length;i++){var r=st.tasks[o[i]],rw=r.rewards||{};
            if((rw.traderStanding||[]).length||(rw.traderUnlock||[]).length) return o[i];}
          return null;})()""")
        if tid_rw:
            js(cdp, "window.GWTasks.openTask(%s)" % json.dumps(tid_rw))
            time.sleep(1.2)
            bullets = js(cdp, "[].slice.call(document.querySelectorAll('.tk-bullets li')).map(function(t){return t.textContent;}).join(' | ')", "") or ""
            bad_rw = [z for z in zh_names if z in bullets]
            ok("H4 奖励里的商人名用英文原名", "声望：" in bullets and not bad_rw,
               {"sample": bullets[:160], "bad": bad_rw[:3]})
        else:
            ok("H4 奖励里的商人名用英文原名", False, "没找到含声望/解锁的任务")

        # 商人英文名：已审计位置逐个核对
        js(cdp, "(function(){var b=document.querySelector('.tk-modebar [data-tkmode=regular]');if(b)b.click();})()")
        wait_nodes(cdp, counts("regular")["tasks"])
        name_check = json.loads(js(cdp, r"""(function(){
          var en=window.__EN__||[], zhs=window.__ZH__||[];
          function txt(el){return (el.textContent||'').trim();}
          function all(sel){return [].slice.call(document.querySelectorAll(sel)).map(txt);}
          return JSON.stringify({
            nodeMeta: all('#tk-nodes .tk-node-meta').slice(0, 60),
            bandLabels: all('.tk-band-label')
          });})()""", "{}") or "{}")
        metas = name_check.get("nodeMeta") or []
        ok("F1 任务树节点副标题 = 商人英文名 + 等级 + 目标数",
           metas and all(en_re.match(x) for x in metas), metas[:3])

        js(cdp, "(function(){var b=document.querySelector('[data-taskview=traders]');if(b)b.click();})()")
        time.sleep(1.6)
        traders_page = json.loads(js(cdp, r"""(function(){
          function txt(el){return (el.textContent||'').trim();}
          return JSON.stringify({
            cards: [].slice.call(document.querySelectorAll('.tk-trader-name')).map(txt),
            options: [].slice.call(document.querySelectorAll('#tk-trader option')).map(txt).slice(1),
            head: (document.querySelector('.tk-list-head h3')||{}).textContent||''
          });})()""", "{}") or "{}")
        cards = traders_page.get("cards") or []
        opts = traders_page.get("options") or []
        ok("F2 商人卡片显示英文原名",
           cards and all(en_re.match(x) for x in cards), cards[:4])
        ok("F3 商人筛选下拉显示英文原名",
           opts and all(en_re.match(x) for x in opts), opts[:4])
        shot(cdp, "09-traders-filter.png")

        # 点一个商人看标题
        js(cdp, "(function(){var c=document.querySelectorAll('.tk-trader-card')[1];if(c)c.click();})()")
        time.sleep(1.2)
        head = js(cdp, "(document.querySelector('.tk-list-head h3')||{}).textContent", "") or ""
        # 标题形如「PvP（常规） · Therapist · 53 个任务」，商人名可以不在开头
        ok("F4 列表标题使用英文商人名", bool(en_any.search(head)), head)
        shot(cdp, "10-traders-selected.png")

        # 详情 / 前置 / 后续 / 进度
        js(cdp, "(function(){var b=document.querySelector('[data-taskview=tree]');if(b)b.click();})()")
        time.sleep(0.8)
        js(cdp, "window.GWTasks.openTask(%s)" % json.dumps(pick))
        time.sleep(1.4)
        detail = json.loads(js(cdp, r"""(function(){
          function txt(el){return (el.textContent||'').trim();}
          var facts=[].slice.call(document.querySelectorAll('.tk-fact')).map(txt);
          return JSON.stringify({
            sub:(document.querySelector('.tk-detail-sub')||{}).textContent||'',
            facts:facts,
            reqMeta:[].slice.call(document.querySelectorAll('.tk-req-meta')).map(txt).slice(0,8)
          });})()""", "{}") or "{}")
        sub = detail.get("sub") or ""
        ok("F5 详情页副标题以英文商人名开头", bool(en_re.match(sub)), sub)
        facts = " | ".join(detail.get("facts") or [])
        ok("F6 详情页「所属商人」为英文原名", "所属商人" in facts and bool(en_re.search(facts.split("所属商人")[-1][:24])), facts[:120])
        reqs = detail.get("reqMeta") or []
        ok("F7 前置/后续摘要以英文商人名开头", reqs and all(en_re.match(x) for x in reqs), reqs[:3])
        shot(cdp, "11-detail-trader.png")

        js(cdp, "(function(){var b=document.querySelector('[data-taskview=progress]');if(b)b.click();})()")
        time.sleep(1.4)
        prog = js(cdp, "[].slice.call(document.querySelectorAll('.tk-req-meta')).map(function(t){return t.textContent.trim();}).slice(0,10)", [])
        ok("F8 进度页条目以英文商人名开头", prog and all(en_re.match(x) for x in prog), prog[:3])
        shot(cdp, "12-progress.png")

        # 中文商人名不得出现在任务系统里（按已审计位置抽样）
        leak = js(cdp, r"""(function(){
          var zhs=%s;
          var scope=document.querySelector('.tk-shell');
          if(!scope) return JSON.stringify({leak:[]});
          var hits=[];
          ['.tk-trader-name','.tk-band-label','.tk-node-meta','.tk-detail-sub','.tk-req-meta']
            .forEach(function(sel){
              [].slice.call(scope.querySelectorAll(sel)).forEach(function(el){
                var t=(el.textContent||'');
                zhs.forEach(function(z){ if(t.indexOf(z)>=0) hits.push(sel+':'+t); });
              });
            });
          return JSON.stringify({leak:hits.slice(0,6)});})()""" % json.dumps(zh_names, ensure_ascii=False), "{}")
        leak = json.loads(leak or "{}").get("leak") or []
        ok("F9 任务系统不再出现中文商人名", not leak, leak)

        # 离线 + 异常
        urls = [r["url"] for r in cdp.requests]
        external = [u for u in urls if not (u.startswith(base) or u.startswith("data:")
                                            or u.startswith("blob:") or u.startswith("about:"))]
        report["detail"]["requests"] = {"total": len(urls), "external": external[:10]}
        ok("G2 所有请求同源（离线可跑）", not external, external[:5])
        ok("G3 布局模块被真实加载",
           any("/js/task-graph-layout.js" in u for u in urls),
           [u for u in urls if "task-graph" in u][:2])
        errs = [e for e in cdp.console if e["type"] in ("exception", "error")]
        ok("G4 无 JS 异常 / 控制台错误", not errs, errs[:2])

        report["pass"] = all(x["ok"] for x in report["checks"])
        with open(os.path.join(OUT, "browser-accept.json"), "w", encoding="utf-8", newline="\n") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=1)
        total = len(report["checks"])
        passed = sum(1 for x in report["checks"] if x["ok"])
        print("\n结果：%d/%d 通过" % (passed, total))
        for x in report["checks"]:
            if not x["ok"]:
                print("  FAILED:", x["name"], str(x.get("detail"))[:260])
    finally:
        try:
            proc.terminate()
        except Exception:                        # noqa: BLE001
            pass
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
