# -*- coding: utf-8 -*-
"""R19.22 浏览器验收：任务系统 + 中文化 + 既有功能回归。

只读真实运行页面：节点/边数量、缩放平移、搜索、筛选、详情区块、目标勾选联动、
刷新持久化、导入校验、PvE 隔离、地图联动钉点、i18n 未覆盖清单、四视图与校准器回归。
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
OUT = os.path.join(ROOT, "docs", "r19.22-tasks-i18n")
SHOTS = os.path.join(OUT, "screenshots")
BASE = "http://127.0.0.1:8787"
report = {"pass": False, "checks": [], "detail": {}}


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


def nav(cdp, url, needle, wait=4.0):
    cdp.call("Page.navigate", url=url)
    wait_ready(cdp, want_url=needle)
    time.sleep(wait)


def wait_nodes(cdp, minimum=100, tries=30):
    for _ in range(tries):
        n = int(cdp.eval("document.querySelectorAll('#tk-nodes .tk-node').length") or 0)
        if n >= minimum:
            return n
        time.sleep(0.5)
    return int(cdp.eval("document.querySelectorAll('#tk-nodes .tk-node').length") or 0)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9751)
    args = ap.parse_args(argv)
    os.makedirs(SHOTS, exist_ok=True)
    prof = os.path.join(os.environ.get("TEMP", "."), "r1922acc_%d" % args.port)
    proc, ws = launch(find_chrome(), args.port, 1680, 1050, prof)
    cdp = CDP(ws)
    try:
        for m in ("Page.enable", "Runtime.enable", "Log.enable", "Network.enable"):
            cdp.call(m)
        cdp.call("Network.setCacheDisabled", cacheDisabled=True)
        cdp.call("Emulation.setDeviceMetricsOverride", width=1680, height=1050,
                 deviceScaleFactor=1, mobile=False)

        # ---------------- 1 任务树
        nav(cdp, BASE + "/index.html#tasks", "index.html", 5.0)
        n = wait_nodes(cdp)
        edges = int(cdp.eval("document.querySelectorAll('#tk-edges .tk-edge').length") or 0)
        ok("T1 任务树渲染全部任务节点", n >= 490, {"nodes": n, "edges": edges})
        ok("T1b 关系边由真实前置生成", edges >= 200, {"edges": edges})
        ok("T1c 任务视图选中", cdp.eval(
            "(document.querySelector('[data-view=tasks]')||{}).getAttribute('aria-selected')") == "true")
        counts = cdp.eval("(document.getElementById('tk-counts')||{}).textContent") or ""
        ok("T1d 状态栏统计含总数", "503" in counts, counts)
        shot(cdp, "01-task-tree.png")

        cam0 = cdp.eval("(document.getElementById('tk-cam')||{}).getAttribute('transform')")
        pos = json.loads(cdp.eval(
            "(function(){var s=document.getElementById('tk-svg').getBoundingClientRect();"
            "return JSON.stringify({x:Math.round(s.x+s.width/2),y:Math.round(s.y+s.height/2)});})()"))
        # 窗口未聚焦时 CDP 输入会丢事件：先 bringToFront，必要时重试一次
        cdp.call("Page.bringToFront")
        for _try in range(2):
            cdp.call("Input.dispatchMouseEvent", type="mouseWheel", x=pos["x"], y=pos["y"],
                     deltaX=0, deltaY=-240, button="none")
            time.sleep(0.7)
            cam1 = cdp.eval("(document.getElementById('tk-cam')||{}).getAttribute('transform')")
            if cam0 != cam1:
                break
            cdp.call("Page.bringToFront")
            time.sleep(0.4)
        ok("T2 滚轮缩放生效", cam0 != cam1, {"before": cam0, "after": cam1})
        # 拖拽必须从**空白处**起手（落在节点上是选中而不是平移）
        # R19.25：新布局会让画布满是节点，固定取右下角可能正好压在卡片上（那里拖不动是正确行为）。
        # 改成扫描一个"确实空白"的点（elementFromPoint 不在 .tk-node 里），再从这里起拖。
        empty = json.loads(cdp.eval(
            "(function(){var s=document.getElementById('tk-svg').getBoundingClientRect();"
            "for(var gy=0;gy<10;gy++){for(var gx=0;gx<10;gx++){"
            "var x=Math.round(s.x+40+(s.width-80)*gx/9), y=Math.round(s.y+40+(s.height-80)*gy/9);"
            "var el=document.elementFromPoint(x,y);"
            "if(el && !(el.closest && el.closest('.tk-node')) && el.closest('#tk-svg')){"
            "return JSON.stringify({x:x,y:y});}}}"
            "return JSON.stringify({x:Math.round(s.x+s.width-80),y:Math.round(s.y+s.height-90)});})()"))
        cdp.call("Input.dispatchMouseEvent", type="mousePressed", x=empty["x"], y=empty["y"],
                 button="left", clickCount=1)
        cdp.call("Input.dispatchMouseEvent", type="mouseMoved", x=empty["x"] - 140, y=empty["y"] - 70, button="left")
        cdp.call("Input.dispatchMouseEvent", type="mouseReleased", x=empty["x"] - 140, y=empty["y"] - 70, button="left")
        time.sleep(0.6)
        cam2 = cdp.eval("(document.getElementById('tk-cam')||{}).getAttribute('transform')")
        ok("T2b 拖拽平移生效", cam2 != cam1, {"after": cam2})

        needle = cdp.eval("""(function(){
          var n=document.querySelector('#tk-nodes .tk-node-name');
          var t=n?n.textContent:'';
          return t.replace(/[^\u4e00-\u9fff]/g,'').slice(0,2);})()""") or ""
        cdp.eval("(function(){var i=document.getElementById('tk-search');i.value=%s;"
                 "i.dispatchEvent(new Event('input',{bubbles:true}));})()" % json.dumps(needle))
        time.sleep(0.9)
        matches = int(cdp.eval("(window.GWTasks.state.matches||[]).length") or 0)
        ok("T3 中文搜索命中", bool(needle) and matches >= 1, {"needle": needle, "matches": matches})

        trader = cdp.eval("(function(){var s=document.getElementById('tk-trader');"
                          "if(!s||s.options.length<2) return '';s.selectedIndex=1;"
                          "s.dispatchEvent(new Event('change',{bubbles:true}));return s.value;})()")
        time.sleep(0.9)
        dim = int(cdp.eval("document.querySelectorAll('#tk-nodes .tk-node.is-dim').length") or 0)
        ok("T4 商人筛选弱化非命中节点", bool(trader) and dim > 0, {"trader": trader, "dim": dim})
        cdp.eval("(function(){var s=document.getElementById('tk-trader');s.selectedIndex=0;"
                 "s.dispatchEvent(new Event('change',{bubbles:true}));"
                 "var i=document.getElementById('tk-search');i.value='';"
                 "i.dispatchEvent(new Event('input',{bubbles:true}));})()")
        time.sleep(0.6)

        sel = cdp.eval("(function(){var g=document.querySelector('#tk-nodes .tk-node');"
                       "if(!g) return '';g.dispatchEvent(new MouseEvent('click',{bubbles:true}));"
                       "return g.getAttribute('data-id');})()")
        time.sleep(0.9)
        side = cdp.eval("(document.querySelector('.tk-side-title')||{}).textContent") or ""
        ok("T5 点击节点出侧栏摘要", bool(sel) and bool(side), {"id": sel, "title": side})
        shot(cdp, "02-tree-selected.png")

        cdp.eval("(function(){var g=document.querySelector('#tk-nodes .tk-node');"
                 "if(g) g.dispatchEvent(new MouseEvent('dblclick',{bubbles:true}));})()")
        time.sleep(1.3)
        ok("T5b 双击进入详情", bool(cdp.eval("(document.querySelector('.tk-detail-title')||{}).textContent")))

        # ---------------- 2 详情
        detail = cdp.eval("""(function(){
          var d=document.querySelector('.tk-detail-body');
          if(!d) return null;
          return JSON.stringify({
            title:(d.querySelector('.tk-detail-title')||{}).textContent,
            sections:[].map.call(d.querySelectorAll('.tk-h3'),function(x){return x.textContent;}),
            facts:d.querySelectorAll('.tk-fact').length,
            objectives:d.querySelectorAll('.tk-obj').length,
            guideNote:(d.querySelector('.tk-alert')||{}).textContent
          });})()""")
        d = json.loads(detail) if detail else {}
        need = ("前置任务", "前置条件", "任务目标", "详细攻略", "任务奖励", "后续任务")
        ok("T6 详情六区块齐全", all(any(k in s for s in d.get("sections", [])) for k in need),
           d.get("sections"))
        ok("T6b 基本信息字段 ≥ 6", d.get("facts", 0) >= 6, {"facts": d.get("facts")})
        ok("T6c 攻略标明状态", bool(d.get("guideNote")), d.get("guideNote"))
        shot(cdp, "03-task-detail.png")

        tid = cdp.eval("(window.GWTasks.state.selected)||''")
        cdp.eval("""(function(){var cb=document.querySelector('.tk-obj-check input');
          if(!cb) return; cb.checked=true; cb.dispatchEvent(new Event('change',{bubbles:true}));})()""")
        time.sleep(1.0)
        st1 = cdp.eval("window.GWTasks.status('%s')" % tid)
        ok("T6d 勾选目标进入进行中", st1 in ("active", "completed"), {"status": st1})

        cdp.eval("""(function(){[].forEach.call(document.querySelectorAll('.tk-obj-check input'),
          function(cb){ if(!cb.checked){ cb.checked=true; cb.dispatchEvent(new Event('change',{bubbles:true})); } });})()""")
        time.sleep(1.4)
        st2 = cdp.eval("window.GWTasks.status('%s')" % tid)
        ok("T6e 必需目标全勾自动完成", st2 == "completed", {"status": st2})

        # ---------------- 3 商人页
        cdp.eval("(function(){var b=document.querySelector('[data-taskview=traders]');if(b)b.click();})()")
        time.sleep(1.5)
        cards = int(cdp.eval("document.querySelectorAll('.tk-trader-card').length") or 0)
        rows = int(cdp.eval("document.querySelectorAll('.tk-table .tk-tr').length") or 0)
        chains = int(cdp.eval("document.querySelectorAll('.tk-chain').length") or 0)
        ok("T7 商人卡片与任务列表", cards >= 8 and rows >= 50, {"cards": cards, "rows": rows})
        ok("T7b 任务链渲染", chains >= 1, {"chains": chains})
        shot(cdp, "04-traders.png")
        cdp.eval("(function(){var c=document.querySelectorAll('.tk-trader-card')[1];"
                 "if(c) c.click();})()")
        time.sleep(1.0)
        rows2 = int(cdp.eval("document.querySelectorAll('.tk-table .tk-tr').length") or 0)
        ok("T7c 点商人卡片按商人过滤", rows2 < rows and rows2 > 1, {"rows": rows2})

        # ---------------- 4 进度页
        cdp.eval("(function(){var b=document.querySelector('[data-taskview=progress]');if(b)b.click();})()")
        time.sleep(1.4)
        cards2 = int(cdp.eval("document.querySelectorAll('.tk-card').length") or 0)
        groups = int(cdp.eval("document.querySelectorAll('.tk-group').length") or 0)
        ok("T8 进度页卡片与分组", cards2 == 4 and groups >= 4, {"cards": cards2, "groups": groups})
        exp = cdp.eval("""(function(){var t=window.GWTasks.exportProgress();
          try{var d=JSON.parse(t);return d.kind+':'+Object.keys(d.modes).length;}catch(e){return 'bad';}})()""")
        # R19.23 起进度结构为三模式（PvP / PvE / PvPS），此处同步升级断言
        ok("T8b 导出进度 JSON 合法", exp == "eftmap-task-progress:3", exp)
        shot(cdp, "05-progress.png")

        badmsg = cdp.eval("window.GWTasks.importProgress('{\"schema\":9}')")
        st_after = cdp.eval("window.GWTasks.status('%s')" % tid)
        ok("T8c 非法导入不破坏原进度", "失败" in badmsg and st_after == "completed", {"msg": badmsg, "status": st_after})

        # ---------------- 5 刷新持久化
        nav(cdp, BASE + "/index.html#tasks", "index.html", 5.0)
        wait_nodes(cdp)
        st3 = cdp.eval("window.GWTasks.status('%s')" % tid)
        ok("T9 刷新后进度保留", st3 == "completed", {"status": st3})

        # ---------------- 6 PvE 隔离
        cdp.eval("(function(){var b=document.querySelector('[data-tkmode=pve]');if(b)b.click();})()")
        n_pve = wait_nodes(cdp, 480)
        st_pve = cdp.eval("window.GWTasks.status('%s')" % tid)
        ok("T10 PvE 模式独立数据", 470 <= n_pve <= 520, {"nodes": n_pve})
        ok("T10b PvE 进度与 PvP 隔离", st_pve == "none", {"status": st_pve})
        shot(cdp, "06-pve-tree.png")
        cdp.eval("(function(){var b=document.querySelector('[data-tkmode=regular]');if(b)b.click();})()")
        wait_nodes(cdp)

        # ---------------- 7 地图联动
        cdp.eval("(function(){var b=document.querySelector('[data-taskview=tree]');if(b)b.click();})()")
        time.sleep(0.8)
        # 挑一个目标区域落在本地已收录地图（海关）上的任务，避免「本图未收录」的正常回退干扰断言
        pick = cdp.eval("""(function(){
          var st=window.GWTasks.state, order=st.order, tasks=st.tasks;
          for (var i=0;i<order.length;i++){
            var r=tasks[order[i]];
            var zones=[];
            (r.objectives||[]).forEach(function(o){(o.zones||[]).forEach(function(z){zones.push(z);});});
            for (var j=0;j<zones.length;j++){
              if (zones[j].mapId==='56f40101d2720b2a4d8b45d6') return order[i];
            }
          }
          return '';})()""")
        if pick:
            cdp.eval("window.GWTasks.openTask(%s)" % json.dumps(pick))
            time.sleep(1.6)
            clicked = cdp.eval("""(function(){
              var b=document.querySelector('[data-locate-zone]'); if(!b) return 'no-btn';
              b.click(); return 'ok';})()""")
            time.sleep(3.0)
            view_map = cdp.eval("(document.querySelector('[data-view=map]')||{}).getAttribute('aria-selected')")
            pin = cdp.eval("!!document.querySelector('.task-pin')")
            ok("T11 详情可跳转地图", clicked == "ok" and view_map == "true", {"clicked": clicked, "map": view_map})
            ok("T11b 地图出现任务目标钉点", bool(pin), {"pin": pin})
        else:
            ok("T11 详情可跳转地图", False, "找不到落在本地地图上的任务目标区域")
        shot(cdp, "07-map-pin.png")

        # ---------------- 8 i18n 覆盖率
        cov = cdp.eval("JSON.stringify(window.GWI18n.coverage())")
        c = json.loads(cov) if cov else {}
        unmapped = [u["text"] for u in (c.get("unmapped") or [])]
        ok("T12 i18n 未覆盖英文为 0", len(unmapped) == 0, unmapped[:10])
        ok("T12b 已有中文字典与名称表", c.get("entries", 0) >= 90 and c.get("names", {}).get("tasks", 0) > 0, c.get("names"))

        # ---------------- 9 既有视图回归
        reg = {}
        for view, label in (("map", "地图"), ("loadout", "配装"), ("gun", "配枪"), ("ammo", "弹药")):
            cdp.eval("(function(){var b=document.querySelector('[data-view=%s]');if(b)b.click();})()" % view)
            time.sleep(2.4)
            sel_ok = cdp.eval("(document.querySelector('[data-view=%s]')||{}).getAttribute('aria-selected')" % view)
            errs = cdp.eval("(window.__errs||[]).length")
            reg[view] = {"selected": sel_ok, "errors": errs}
            shot(cdp, "reg-%s.png" % view)
        ok("T13 四个既有视图均可打开且无脚本错误",
           all(v["selected"] == "true" and v["errors"] == 0 for v in reg.values()), reg)

        nav(cdp, BASE + "/index.html?layoutCalibrator=1", "layoutCalibrator=1", 5.0)
        cal = cdp.eval("(function(){return JSON.stringify({grid:!!document.getElementById('cal-grid'),"
                       "cards:document.querySelectorAll('.cal-card').length});})()")
        ok("T13b 校准器仍可用", bool(cal) and '"grid":true' in (cal or ""), cal)
        shot(cdp, "reg-calibrator.png")

        report["pass"] = all(x["ok"] for x in report["checks"])
        report["detail"]["i18n"] = c
        report["detail"]["regression"] = reg
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
        except Exception:
            pass
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
