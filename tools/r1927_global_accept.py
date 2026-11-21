# -*- coding: utf-8 -*-
"""R19.27 真实浏览器验收：全局游戏模式 / 递归前置联动 / 任务进度持久化。

说明：tools/r1927_accept.py 是 R19.19 的遗留文件（名字撞车），本文件不覆盖它。

运行：
  python tools/r1927_global_accept.py --base http://127.0.0.1:8791 --port 9901
产物：
  docs/r19.27/browser-accept.json + docs/r19.27/shots/*.png
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r181_accept import CDP, find_chrome, launch, wait_ready  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "r19.27")
SHOTS = os.path.join(OUT, "shots")
BASE = "http://127.0.0.1:8791"

VIEWS = ["map", "loadout", "gun", "ammo", "tasks"]


def js(cdp, expr, default=None):
    try:
        v = cdp.eval(expr)
        return default if v is None else v
    except Exception:                                  # noqa: BLE001
        return default


def shot(cdp, name):
    try:
        cdp.shot(os.path.join(SHOTS, name))
        return True
    except Exception as exc:                           # noqa: BLE001
        print("   shot failed", name, exc)
        return False


def wait_tasks(cdp, min_n=50, tries=30):
    for _ in range(tries):
        time.sleep(0.5)
        try:
            if int(js(cdp, "Object.keys(window.GWTasks.state.tasks).length", 0) or 0) >= min_n:
                return True
        except Exception:                              # noqa: BLE001
            pass
    return False


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9901)
    ap.add_argument("--base", default=BASE)
    args = ap.parse_args(argv)
    os.makedirs(SHOTS, exist_ok=True)
    report = {"schema": 1, "round": "R19.27", "pass": 0, "fail": 0, "checks": [], "detail": {}}
    prof = os.path.join(os.environ.get("TEMP", "."), "r1927acc_%d" % args.port)
    proc, ws = launch(find_chrome(), args.port, 1680, 1050, prof)
    cdp = CDP(ws)
    base = args.base.rstrip("/")

    def ok(name, cond, detail=None):
        report["checks"].append({"name": name, "ok": bool(cond), "detail": detail})
        if cond:
            report["pass"] += 1
            print("  PASS", name)
        else:
            report["fail"] += 1
            print("  FAIL", name, json.dumps(detail, ensure_ascii=False)[:300] if detail else "")

    try:
        for m in ("Page.enable", "Runtime.enable", "Log.enable", "Network.enable"):
            cdp.call(m)
        cdp.call("Network.setCacheDisabled", cacheDisabled=True)
        cdp.call("Emulation.setDeviceMetricsOverride", width=1680, height=1050,
                 deviceScaleFactor=1, mobile=False)

        # ========== 1 全局模式控件 ==========
        cdp.call("Page.navigate", url=base + "/index.html")
        wait_ready(cdp, want_url="index.html")
        time.sleep(1.5)
        js(cdp, "try{localStorage.clear();}catch(e){}")
        cdp.call("Page.navigate", url=base + "/index.html?acc=1")
        wait_ready(cdp, want_url="index.html")
        time.sleep(2.5)

        bar = json.loads(js(cdp, r"""JSON.stringify((function(){
          var bar=document.getElementById('game-mode-bar');
          if(!bar) return null;
          var head=document.querySelector('.menubar');
          var btns=[].map.call(bar.querySelectorAll('[data-tkmode]'), function(el){
            return {key:el.dataset.tkmode, text:el.textContent.trim(),
                    selected:el.getAttribute('aria-selected')};
          });
          return {inMenubar: !!(head&&head.contains(bar)),
                  buttons:btns, mode: window.GWGameMode && window.GWGameMode.get(),
                  api: !!window.GWGameMode};
        })())""", "null") or {})
        report["detail"]["modeBar"] = bar
        ok("G1 右上角全局模式控件存在（PvP/PvE/PvPS）",
           bar.get("inMenubar") is True and bar.get("api") is True and
           [b["key"] for b in bar.get("buttons", [])] == ["regular", "pve", "pvps"], bar)
        ok("G2 初始默认 PvP 且唯一选中",
           bar.get("mode") == "regular" and
           [b["key"] for b in bar.get("buttons", []) if b.get("selected") == "true"] == ["regular"], bar)

        per_view = {}
        for view in VIEWS:
            js(cdp, "(function(){var b=document.querySelector('[data-view=%s]');if(b)b.click();})()" % view)
            time.sleep(1.4)
            per_view[view] = json.loads(js(cdp, r"""JSON.stringify((function(){
              var bar=document.getElementById('game-mode-bar');
              if(!bar) return null;
              var r=bar.getBoundingClientRect();
              return {visible: r.width>0 && r.height>0 && r.top>=0,
                      mode: window.GWGameMode && window.GWGameMode.get(),
                      inMenubar: !!document.querySelector('.menubar').contains(bar)};
            })())""", "null") or {})
        report["detail"]["perView"] = per_view
        ok("G3 地图/配装/配枪/弹药/任务 五页右上角都可见同一控件",
           all(v and v.get("visible") and v.get("inMenubar") for v in per_view.values()), per_view)
        shot(cdp, "01-map-mode.png")

        js(cdp, "(function(){var b=document.querySelector('[data-view=loadout]');if(b)b.click();})()")
        time.sleep(1.0)
        js(cdp, "(function(){var b=document.querySelector('[data-tkmode=pvps]');if(b)b.click();})()")
        time.sleep(1.2)
        js(cdp, "(function(){var b=document.querySelector('[data-view=tasks]');if(b)b.click();})()")
        time.sleep(3.5)
        mode_after = js(cdp, "window.GWGameMode.get()")
        task_mode = js(cdp, "window.GWTasks.state.mode")
        ok("G4 跨页面模式一致：配装页切 PvPS → 任务页仍 PvPS",
           mode_after == "pvps" and task_mode == "pvps",
           {"global": mode_after, "tasks": task_mode})
        shot(cdp, "02-loadout-mode.png")

        cdp.call("Page.navigate", url=base + "/index.html?acc=2")
        wait_ready(cdp, want_url="index.html")
        time.sleep(2.5)
        mode_reload = js(cdp, "window.GWGameMode.get()")
        ok("G5 刷新后恢复上次模式（PvPS）", mode_reload == "pvps", mode_reload)

        js(cdp, "localStorage.setItem('eftmap.gameMode','bogus')")
        cdp.call("Page.navigate", url=base + "/index.html?acc=3")
        wait_ready(cdp, want_url="index.html")
        time.sleep(2.0)
        mode_bad = js(cdp, "window.GWGameMode.get()")
        ok("G6 非法存储值回退默认 PvP", mode_bad == "regular", mode_bad)

        # ========== 2 递归前置联动 ==========
        js(cdp, "try{localStorage.clear();}catch(e){}")
        cdp.call("Page.navigate", url=base + "/index.html?acc=4#tasks")
        wait_ready(cdp, want_url="index.html")
        wait_tasks(cdp, 50, 30)
        time.sleep(1.5)

        chain = json.loads(js(cdp, r"""JSON.stringify((function(){
          var st=window.GWTasks.state;
          function depthOf(id, seen){
            seen=seen||{}; if(seen[id]) return 0; seen[id]=1;
            var r=st.tasks[id]; if(!r) return 0;
            var ps=(r.prerequisites||[]).filter(function(p){return p.taskId && st.tasks[p.taskId];});
            if(!ps.length) return 0;
            var best=0;
            ps.forEach(function(p){ best=Math.max(best, 1+depthOf(p.taskId, Object.assign({},seen))); });
            return best;
          }
          var best=null,bestD=0;
          st.order.forEach(function(id){
            var d=depthOf(id);
            if(d>bestD){bestD=d;best=id;}
          });
          if(!best) return null;
          var chain=[best], cur=best, seen={};
          while(chain.length<6){
            seen[cur]=1;
            var r=st.tasks[cur];
            var p=(r.prerequisites||[]).filter(function(x){return x.taskId && st.tasks[x.taskId] && !seen[x.taskId];})[0];
            if(!p) break;
            chain.push(p.taskId); cur=p.taskId;
          }
          return {target:best, depth:bestD, chain:chain};
        })())""", "null") or {})
        report["detail"]["chain"] = chain
        ok("R1 找到三层以上依赖链（真实数据）",
           bool(chain) and chain.get("depth", 0) >= 2 and len(chain.get("chain", [])) >= 3, chain)

        if chain and len(chain.get("chain", [])) >= 3:
            tid = chain["target"]
            for cid in chain["chain"]:
                js(cdp, "window.GWTasks.setStatus(%s,'none')" % json.dumps(cid))
            time.sleep(0.5)
            js(cdp, "window.GWTasks.openTask(%s)" % json.dumps(tid))
            time.sleep(1.2)
            shot(cdp, "03-detail-before.png")

            js(cdp, "window.GWTasks.requestStatusChange(%s,'completed')" % json.dumps(tid))
            time.sleep(1.2)
            dlg = json.loads(js(cdp, r"""JSON.stringify((function(){
              var d=document.querySelector('.ui-dialog__box');
              if(!d) return null;
              return {title:(d.querySelector('.ui-dialog__title')||{}).textContent||'',
                      items:[].map.call(d.querySelectorAll('.tk-plan-item,.tk-plan-group,.tk-plan-warn'),
                        function(li){return li.textContent.trim();}),
                      btns:[].map.call(d.querySelectorAll('.ui-btn'),
                        function(b){return b.textContent.trim();})};
            })())""", "null") or {})
            report["detail"]["prereqDialog"] = dlg
            ok("R2 递归确认弹窗展示全部层级（含间接前置）",
               bool(dlg) and dlg.get("title", "").find("前置") >= 0 and
               any(("间接" in x or "第" in x) for x in dlg.get("items", [])) and
               len(dlg.get("items", [])) >= 3, dlg)
            shot(cdp, "04-recursive-dialog.png")

            clicked = js(cdp, """(function(){
              var d=document.querySelector('.ui-dialog__box'); if(!d) return false;
              var bs=[].slice.call(d.querySelectorAll('.ui-btn'));
              var b=bs.filter(function(x){return x.textContent.indexOf('确认')>=0;})[0];
              if(b){b.click(); return true;} return false;})()""")
            time.sleep(1.5)
            chain_states = json.loads(js(cdp,
                "JSON.stringify(%s.map(function(id){return [id, window.GWTasks.status(id)];}))"
                % json.dumps(chain["chain"]), "[]") or "[]")
            report["detail"]["chainAfter"] = chain_states
            # 递归生效 = 整条链都被推进到「符合下游要求的档位」：
            # 多数是 completed；若某前置被下游要求「进行中/失败」，它就该是 active/failed（不是未开始）。
            statuses = [st for _i, st in chain_states]
            ok("R3 确认后整条依赖链递归推进（目标已完成、无一停在未开始）",
               bool(clicked) and len(chain_states) >= 3 and
               statuses[0] == "completed" and
               all(st != "none" for st in statuses) and
               sum(1 for st in statuses if st == "completed") >= len(statuses) - 1,
               chain_states)

            for cid in chain["chain"]:
                js(cdp, "window.GWTasks.setStatus(%s,'none')" % json.dumps(cid))
            time.sleep(0.4)
            js(cdp, "window.GWTasks.requestStatusChange(%s,'completed')" % json.dumps(tid))
            time.sleep(1.0)
            js(cdp, """(function(){
              var d=document.querySelector('.ui-dialog__box'); if(!d) return;
              var bs=[].slice.call(d.querySelectorAll('.ui-btn'));
              var b=bs.filter(function(x){return x.textContent.trim()==='取消';})[0];
              if(b)b.click();})()""")
            time.sleep(1.0)
            cancel_states = json.loads(js(cdp,
                "JSON.stringify(%s.map(function(id){return [id, window.GWTasks.status(id)];}))"
                % json.dumps(chain["chain"]), "[]") or "[]")
            report["detail"]["chainCancel"] = cancel_states
            ok("R4 取消后当前任务与全部前置保持原状",
               all(st == "none" for _id, st in cancel_states), cancel_states)

        # ========== 3 后续重置（不退化） ==========
        fu = json.loads(js(cdp, r"""JSON.stringify((function(){
          var st=window.GWTasks.state;
          for(var i=0;i<st.order.length;i++){
            var r=st.tasks[st.order[i]];
            if((r.followUps||[]).length>=2){
              var okk=r.followUps.every(function(f){return st.tasks[f];});
              if(okk) return {id:st.order[i], followUps:r.followUps};
            }
          }
          return null;})())""", "null") or {})
        if fu:
            for fid in [fu["id"]] + fu["followUps"]:
                js(cdp, "window.GWTasks.setStatus(%s,'completed')" % json.dumps(fid))
            time.sleep(0.5)
            js(cdp, "window.GWTasks.requestStatusChange(%s,'none')" % json.dumps(fu["id"]))
            time.sleep(1.0)
            dlg2 = json.loads(js(cdp, r"""JSON.stringify((function(){
              var d=document.querySelector('.ui-dialog__box');
              if(!d) return null;
              return {title:(d.querySelector('.ui-dialog__title')||{}).textContent||'',
                      btns:[].map.call(d.querySelectorAll('.ui-btn'),function(b){return b.textContent.trim();})};
            })())""", "null") or {})
            report["detail"]["resetDialog"] = dlg2
            ok("R5 未开始仍弹「重置后续任务」确认（含仅重置当前）",
               bool(dlg2) and "重置" in dlg2.get("title", "") and
               any("仅重置" in b for b in dlg2.get("btns", [])), dlg2)
            shot(cdp, "05-reset-dialog.png")
            js(cdp, """(function(){
              var d=document.querySelector('.ui-dialog__box'); if(!d) return;
              var bs=[].slice.call(d.querySelectorAll('.ui-btn'));
              var b=bs.filter(function(x){return x.textContent.indexOf('仅重置')>=0;})[0];
              if(b)b.click();})()""")
            time.sleep(1.0)
            after_only = json.loads(js(cdp,
                "JSON.stringify([window.GWTasks.status(%s)].concat(%s.map(function(f){return window.GWTasks.status(f);})))"
                % (json.dumps(fu["id"]), json.dumps(fu["followUps"])), "[]") or "[]")
            ok("R6 「仅重置当前任务」不动后续",
               bool(after_only) and after_only[0] == "none" and
               all(x == "completed" for x in after_only[1:]), after_only)

        # ========== 4 进度持久化 + 三模式隔离 ==========
        js(cdp, "try{localStorage.clear();}catch(e){}")
        cdp.call("Page.navigate", url=base + "/index.html?acc=5#tasks")
        wait_ready(cdp, want_url="index.html")
        wait_tasks(cdp)
        pick = js(cdp, "window.GWTasks.state.order[0]")
        js(cdp, "window.GWTasks.setStatus(%s,'completed')" % json.dumps(pick))
        time.sleep(0.6)
        ls_prog = json.loads(js(cdp, "localStorage.getItem('eftmap.tasks.progress.v1')", "null") or "null")
        ok("P1 状态写入立即落盘（localStorage）",
           bool(ls_prog) and ((ls_prog.get("modes", {}).get("regular", {}) or {})
                              .get(pick, {}) or {}).get("status") == "completed",
           {"key": pick, "saved": bool(ls_prog)})

        cdp.call("Page.navigate", url=base + "/index.html?acc=6#tasks")
        wait_ready(cdp, want_url="index.html")
        wait_tasks(cdp)
        st_after = js(cdp, "window.GWTasks.status(%s)" % json.dumps(pick))
        ok("P2 刷新后任务状态恢复", st_after == "completed", st_after)

        js(cdp, "(function(){var b=document.querySelector('[data-tkmode=pve]');if(b)b.click();})()")
        for _ in range(25):
            time.sleep(0.5)
            if js(cdp, "window.GWTasks.state.mode") == "pve":
                wait_tasks(cdp, 50, 12)
                break
        st_pve = js(cdp, "window.GWTasks.status(%s)" % json.dumps(pick))
        js(cdp, "(function(){var b=document.querySelector('[data-tkmode=pvps]');if(b)b.click();})()")
        for _ in range(25):
            time.sleep(0.5)
            if js(cdp, "window.GWTasks.state.mode") == "pvps":
                wait_tasks(cdp, 50, 12)
                break
        st_pvps = js(cdp, "window.GWTasks.status(%s)" % json.dumps(pick))
        ok("P3 三模式进度隔离：PvP 已完成 ≠ PvE/PvPS",
           st_after == "completed" and st_pve == "none" and st_pvps == "none",
           {"regular": st_after, "pve": st_pve, "pvps": st_pvps})
        shot(cdp, "06-mode-isolation.png")

        # ========== 5 离线 / 无异常 ==========
        urls = [r.get("url", "") for r in cdp.requests]
        ext = [u for u in urls if u.startswith("http") and not u.startswith(base)
               and not u.startswith("http://127.0.0.1")]
        ok("P4 所有请求同源（离线可跑）", not ext, {"total": len(urls), "external": ext[:5]})
        errs = [c for c in cdp.console if str(c.get("level", "")) == "error"
                or "error" in str(c.get("text", "")).lower()]
        ok("P5 无 JS 异常", not errs, errs[:3])
        shot(cdp, "07-final.png")

    finally:
        try:
            proc.terminate()
        except Exception:                              # noqa: BLE001
            pass

    with open(os.path.join(OUT, "browser-accept.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=1)
    print("== R19.27 browser accept: %d pass / %d fail ==" % (report["pass"], report["fail"]))
    return 0 if report["fail"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
