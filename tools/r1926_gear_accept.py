# -*- coding: utf-8 -*-
"""R19.26 真实浏览器验收：配装插板持久化 / 装备栏紧凑化 / 任务状态联动。

（注意：tools/r1926_accept.py 是 R19.18 遗留的同名旧文件，本轮不覆盖它。）

用法：
    python tools/r1926_gear_accept.py --base http://127.0.0.1:8791 --port 9871
产物：
    docs/r19.26/browser-accept.json + shots/*.png
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
OUT = os.path.join(ROOT, "docs", "r19.26")
SHOTS = os.path.join(OUT, "shots")
ITEMS = json.load(open(os.path.join(ROOT, "data", "items.json"), encoding="utf-8"))["items"]


def pick_armors():
    """挑两件护甲 A/B：都有 Front_plate 板位，且 A 的某块合法插板不在 B 的合法列表里。"""
    armors = []
    for iid, r in ITEMS.items():
        if r.get("pt") != "Armor":
            continue
        front = [a for a in (r.get("aps") or [])
                 if str(a.get("zone", "")).lower() == "front_plate" and (a.get("plates") or [])]
        if front:
            armors.append((iid, r.get("n") or "", set(front[0]["plates"])))
    for i in range(len(armors)):
        for j in range(len(armors)):
            if i == j:
                continue
            only = armors[i][2] - armors[j][2]
            if only:
                pid = sorted(only)[0]
                return {
                    "a": armors[i][0], "aName": armors[i][1],
                    "b": armors[j][0], "bName": armors[j][1],
                    "plate": pid, "plateName": (ITEMS.get(pid) or {}).get("n") or pid,
                    "zone": "Front_plate",
                }
    raise SystemExit("items.json 里找不到一对可区分插板兼容性的护甲")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9871)
    ap.add_argument("--base", default="http://127.0.0.1:8791")
    args = ap.parse_args(argv)
    base = args.base.rstrip("/")
    os.makedirs(SHOTS, exist_ok=True)
    pick = pick_armors()
    report = {"schema": 1, "tool": "tools/r1926_gear_accept.py", "base": base,
              "armors": pick, "checks": [], "detail": {}}

    def ok(name, cond, detail=None):
        report["checks"].append({"name": name, "ok": bool(cond), "detail": detail})
        print(("  PASS " if cond else "  FAIL ") + name +
              ("" if cond else "  " + json.dumps(detail, ensure_ascii=False)[:220]))

    def js(cdp, expr, default=None):
        try:
            v = cdp.eval(expr)
            return default if v is None else v
        except Exception:                               # noqa: BLE001
            return default

    def shot(cdp, name):
        try:
            cdp.shot(os.path.join(SHOTS, name))
        except Exception as exc:                        # noqa: BLE001
            print("   shot failed:", exc)

    prof = os.path.join(os.environ.get("TEMP", "."), "r1926gear_%d" % args.port)
    proc, ws = launch(find_chrome(), args.port, 1680, 1050, prof)
    cdp = CDP(ws)
    try:
        for m in ("Page.enable", "Runtime.enable", "Log.enable", "Network.enable"):
            cdp.call(m)
        cdp.call("Network.setCacheDisabled", cacheDisabled=True)
        cdp.call("Emulation.setDeviceMetricsOverride", width=1680, height=1050,
                 deviceScaleFactor=1, mobile=False)
        cdp.call("Page.bringToFront")

        # 干净起点
        cdp.call("Page.navigate", url=base + "/index.html")
        wait_ready(cdp, want_url="index.html")
        time.sleep(1.5)
        js(cdp, "try{localStorage.clear();}catch(e){}")
        cdp.call("Page.navigate", url=base + "/index.html?r1926=1")
        wait_ready(cdp, want_url="index.html")
        time.sleep(2.0)
        js(cdp, "(function(){var b=document.querySelector('[data-view=loadout]');if(b)b.click();})()")
        time.sleep(2.5)
        ok("L0 配装接口存在", js(cdp, "!!(window.GWLoadout && window.GWLoadout.plateGet)") is True)

        # ================= 一、插板持久化 =================
        A, B, P, Z = pick["a"], pick["b"], pick["plate"], pick["zone"]
        js(cdp, "window.GWLoadout.equip(%s, 'armor')" % json.dumps(A))
        time.sleep(0.8)
        js(cdp, "window.GWLoadout.plateSet('armor/' + %s, %s, %s)" % (json.dumps(Z), json.dumps(A), json.dumps(P)))
        time.sleep(0.8)
        got1 = js(cdp, "window.GWLoadout.plateGet('armor/' + %s, %s)" % (json.dumps(Z), json.dumps(A)))
        states1 = json.loads(js(cdp, "JSON.stringify(window.GWLoadout.plateStates(%s, 'armor'))" % json.dumps(A), "[]") or "[]")
        front1 = [s for s in states1 if (s.get("slotId") or "").endswith("/" + Z)]
        ok("P1 护甲 A 的前插板已写入稳定身份键", got1 == P,
           {"got": got1, "want": P,
            "key": js(cdp, "window.GWLoadout.slotKey('armor/'+%s, %s)" % (json.dumps(Z), json.dumps(A)))})
        ok("P1b 板位状态显示为已安装", bool(front1) and front1[0].get("state") == "on", front1[:1])

        js(cdp, "window.GWLoadout.equip(%s, 'armor')" % json.dumps(B))
        time.sleep(1.0)
        gotB = js(cdp, "window.GWLoadout.plateGet('armor/' + %s, %s)" % (json.dumps(Z), json.dumps(B)))
        statesB = json.loads(js(cdp, "JSON.stringify(window.GWLoadout.plateStates(%s, 'armor'))" % json.dumps(B), "[]") or "[]")
        frontB = [s for s in statesB if (s.get("slotId") or "").endswith("/" + Z)]
        ok("P2 切到护甲 B 后不套用 A 的插板（兼容性不被绕过）",
           gotB is None and (not frontB or frontB[0].get("state") != "on"),
           {"gotB": gotB, "frontB": frontB[:1]})

        js(cdp, "window.GWLoadout.equip(%s, 'armor')" % json.dumps(A))
        time.sleep(1.0)
        got3 = js(cdp, "window.GWLoadout.plateGet('armor/' + %s, %s)" % (json.dumps(Z), json.dumps(A)))
        ok("P3 切回护甲 A 后插板配置恢复", got3 == P, {"got": got3})

        js(cdp, "(function(){var b=document.querySelector('[data-view=tasks]');if(b)b.click();})()")
        time.sleep(1.5)
        js(cdp, "(function(){var b=document.querySelector('[data-view=loadout]');if(b)b.click();})()")
        time.sleep(1.5)
        got4 = js(cdp, "window.GWLoadout.plateGet('armor/' + %s, %s)" % (json.dumps(Z), json.dumps(A)))
        ok("P4 切换页面后插板配置仍在", got4 == P, {"got": got4})

        cdp.call("Page.navigate", url=base + "/index.html?r1926=2")
        wait_ready(cdp, want_url="index.html")
        time.sleep(2.5)
        js(cdp, "(function(){var b=document.querySelector('[data-view=loadout]');if(b)b.click();})()")
        time.sleep(2.0)
        got5 = js(cdp, "window.GWLoadout.plateGet('armor/' + %s, %s)" % (json.dumps(Z), json.dumps(A)))
        ok("P5 刷新页面后插板配置恢复（沿用 eftmap.loadout）", got5 == P, {"got": got5})

        w_with = js(cdp, "window.GWLoadout.totals().weight")
        js(cdp, "window.GWLoadout.equip(%s, 'armor')" % json.dumps(B))
        time.sleep(0.8)
        w_other = js(cdp, "window.GWLoadout.totals().weight")
        plate_w = (ITEMS.get(P) or {}).get("w") or 0
        armor_w = (ITEMS.get(A) or {}).get("w") or 0
        other_w = (ITEMS.get(B) or {}).get("w") or 0
        ok("P6 统计不把别的护甲的插板算进来",
           abs((w_with or 0) - (armor_w + plate_w)) < 0.02 and abs((w_other or 0) - other_w) < 0.02,
           {"withA": w_with, "expectA": armor_w + plate_w,
            "withB": w_other, "expectB": other_w, "plateW": plate_w})

        js(cdp, "window.GWLoadout.equip(%s, 'armor')" % json.dumps(A))
        time.sleep(0.8)
        js(cdp, "window.GWLoadout.clear('armor/' + %s, %s)" % (json.dumps(Z), json.dumps(A)))
        time.sleep(0.8)
        got7 = js(cdp, "window.GWLoadout.plateGet('armor/' + %s, %s)" % (json.dumps(Z), json.dumps(A)))
        ok("P7 主动卸下插板立即生效并保存", got7 is None, {"got": got7})
        shot(cdp, "01-loadout-plates.png")

        # ================= 二、装备栏紧凑化 =================
        side = json.loads(js(cdp, """(function(){
          var s=document.querySelector('.loadout-workbench .lw-side');
          if(!s) return '{}';
          var cells=[].slice.call(document.querySelectorAll('.loadout-workbench .lw-cellbox'));
          var rows=cells.map(function(c){var r=c.getBoundingClientRect();
            return {cell:c.getAttribute('data-cell'), y:Math.round(r.y), h:Math.round(r.height)};})
            .sort(function(a,b){return a.y-b.y;});
          var lines=[];
          rows.forEach(function(r){
            if(!lines.length || r.y-lines[lines.length-1].y>4){lines.push({y:r.y,bottom:r.y+r.h,cells:[r.cell]});}
            else {lines[lines.length-1].bottom=Math.max(lines[lines.length-1].bottom,r.y+r.h);
                  lines[lines.length-1].cells.push(r.cell);}
          });
          var gaps=[];
          for(var i=1;i<lines.length;i++){gaps.push(lines[i].y-lines[i-1].bottom);}
          var clipped=[];
          [].slice.call(document.querySelectorAll('.lw-cell-label,.lw-node-label,.lw-focus-name'))
            .forEach(function(el){ if(el.scrollWidth>el.clientWidth+1) clipped.push(el.textContent); });
          return JSON.stringify({scrollH:s.scrollHeight, clientH:s.clientHeight,
            boardH:Math.round((document.querySelector('.lw-board')||{getBoundingClientRect:function(){return {height:0};}}).getBoundingClientRect().height),
            lineGaps:gaps, clipped:clipped});})()""", "{}") or "{}")
        before = json.load(open(os.path.join(OUT, "layout-before.json"), encoding="utf-8"))
        report["detail"]["side"] = side
        report["detail"]["sideBefore"] = {
            "scrollH": before.get("sideScrollH"), "lineGaps": before.get("lineGaps"),
            "boardH": (before.get("board") or {}).get("h"),
        }
        ok("L1 内容高下降且不再溢出滚动",
           side.get("scrollH", 9999) <= side.get("clientH", 0) and
           side.get("scrollH", 9999) < (before.get("sideScrollH") or 0),
           {"before": before.get("sideScrollH"), "after": side.get("scrollH"), "client": side.get("clientH")})
        ok("L2 相邻装备行间距全面收紧",
           sum(side.get("lineGaps") or []) < sum(before.get("lineGaps") or []),
           {"before": before.get("lineGaps"), "after": side.get("lineGaps")})
        ok("L3 无文本裁切", not side.get("clipped"), side.get("clipped"))
        shot(cdp, "02-side-compact.png")

        # ================= 三、任务状态联动 =================
        js(cdp, "(function(){var b=document.querySelector('[data-view=tasks]');if(b)b.click();})()")
        time.sleep(2.5)
        pair = json.loads(js(cdp, r"""(function(){
          var st=window.GWTasks.state, o=st.order;
          function status(id){return window.GWTasks.status(id);}
          var a=null,b=null;
          for(var i=0;i<o.length && (!a||!b);i++){
            var rec=st.tasks[o[i]];
            var pre=(rec.prerequisites||[]);
            if(!a && pre.length && pre.every(function(p){return status(p.taskId)!=='completed';})) a=o[i];
            var fu=(rec.followUps||[]);
            if(!b && fu.length) b=o[i];
          }
          return JSON.stringify({a:a, b:b});})()""", "{}") or "{}")
        tidA, tidB = pair.get("a"), pair.get("b")
        ok("T0 找到联动测试用任务", bool(tidA and tidB), pair)

        js(cdp, "window.GWTasks.openTask(%s)" % json.dumps(tidA))
        time.sleep(1.2)
        st_before = {tidA: js(cdp, "window.GWTasks.status(%s)" % json.dumps(tidA))}
        pre_ids = json.loads(js(cdp,
            "JSON.stringify((window.GWTasks.state.tasks[%s].prerequisites||[]).map(function(p){return p.taskId;}))"
            % json.dumps(tidA), "[]") or "[]")
        pre_names = json.loads(js(cdp,
            "JSON.stringify((window.GWTasks.state.tasks[%s].prerequisites||[]).map(function(p){"
            "return (window.GWTasks.state.tasks[p.taskId]||{}).nameZh||'';}))" % json.dumps(tidA), "[]") or "[]")
        for pid in pre_ids:
            st_before[pid] = js(cdp, "window.GWTasks.status(%s)" % json.dumps(pid))
        js(cdp, "(function(){var b=document.querySelector('[data-set-status=completed]');if(b)b.click();})()")
        time.sleep(1.0)
        dlg = json.loads(js(cdp, r"""(function(){
          var d=document.querySelector('.ui-dialog__box');
          if(!d) return '{}';
          return JSON.stringify({open:true, title:(d.querySelector('.ui-dialog__title')||{}).textContent||'',
            body:(d.querySelector('.ui-dialog__body')||{}).textContent||'',
            buttons:[].slice.call(d.querySelectorAll('.ui-btn')).map(function(b){return b.textContent.trim();})});})()""", "{}") or "{}")
        ok("T1 未满足前置时弹出确认框（含确认按钮）",
           dlg.get("open") is True and "前置" in (dlg.get("title") or "") and
           any("确认" in b for b in (dlg.get("buttons") or [])), dlg.get("title"))
        body = dlg.get("body") or ""
        ok("T2 弹窗列出了前置任务名称", any(nm and nm in body for nm in pre_names),
           {"names": pre_names[:3], "body": body[:160]})
        st_open = {tidA: js(cdp, "window.GWTasks.status(%s)" % json.dumps(tidA))}
        ok("T3 弹窗打开期间未提前改状态", st_open == {tidA: st_before[tidA]}, st_open)
        shot(cdp, "03-link-dialog-prereq.png")
        js(cdp, "(function(){var d=document.querySelector('.ui-dialog__box');if(!d)return;"
                 "var bs=[].slice.call(d.querySelectorAll('.ui-btn'));"
                 "var c=bs.filter(function(b){return b.textContent.indexOf('取消')>=0;})[0]; if(c)c.click();})()")
        time.sleep(0.8)
        st_cancel = {tidA: js(cdp, "window.GWTasks.status(%s)" % json.dumps(tidA))}
        for pid in pre_ids:
            st_cancel[pid] = js(cdp, "window.GWTasks.status(%s)" % json.dumps(pid))
        ok("T4 取消后当前任务与前置全部不变", st_cancel == st_before,
           {"before": st_before, "after": st_cancel})

        js(cdp, "(function(){var b=document.querySelector('[data-set-status=completed]');if(b)b.click();})()")
        time.sleep(1.0)
        js(cdp, "(function(){var d=document.querySelector('.ui-dialog__box');if(!d)return;"
                 "var bs=[].slice.call(d.querySelectorAll('.ui-btn'));"
                 "var c=bs.filter(function(b){return b.textContent.indexOf('确认并调整')>=0;})[0]; if(c)c.click();})()")
        time.sleep(1.2)
        st_after = {tidA: js(cdp, "window.GWTasks.status(%s)" % json.dumps(tidA))}
        for pid in pre_ids:
            st_after[pid] = js(cdp, "window.GWTasks.status(%s)" % json.dumps(pid))
        fixed = [pid for pid in pre_ids if st_after.get(pid) in ("completed", "active", "failed")]
        ok("T5 确认后前置被调整、当前任务变为已完成",
           st_after.get(tidA) == "completed" and len(fixed) == len(pre_ids),
           {"after": st_after, "pre": pre_ids})
        shot(cdp, "04-link-applied.png")

        st_pvp = js(cdp, "window.GWTasks.status(%s)" % json.dumps(tidA))
        js(cdp, "(function(){var b=document.querySelector('.tk-modebar [data-tkmode=pve]');if(b)b.click();})()")
        time.sleep(2.5)
        st_pve = js(cdp, "window.GWTasks.status(%s)" % json.dumps(tidA))
        js(cdp, "(function(){var b=document.querySelector('.tk-modebar [data-tkmode=pvps]');if(b)b.click();})()")
        time.sleep(2.5)
        st_pvps = js(cdp, "window.GWTasks.status(%s)" % json.dumps(tidA))
        ok("T10 三模式进度隔离（同 ID 不互相污染）",
           st_pvp == "completed" and st_pve == "none" and st_pvps == "none",
           {"pvp": st_pvp, "pve": st_pve, "pvps": st_pvps})
        cdp.call("Page.navigate", url=base + "/index.html?r1926=3#tasks")
        wait_ready(cdp, want_url="index.html")
        time.sleep(4.0)
        ok("T11 刷新后非当前模式不被污染",
           js(cdp, "window.GWTasks.status(%s)" % json.dumps(tidA)) == "none",
           {"pvps": js(cdp, "window.GWTasks.status(%s)" % json.dumps(tidA))})
        js(cdp, "(function(){var b=document.querySelector('.tk-modebar [data-tkmode=regular]');if(b)b.click();})()")
        time.sleep(2.5)
        ok("T12 刷新后 PvP 模式仍保留确认后的状态",
           js(cdp, "window.GWTasks.status(%s)" % json.dumps(tidA)) == "completed",
           {"pvp": js(cdp, "window.GWTasks.status(%s)" % json.dumps(tidA))})


        if tidB:
            fu_ids = json.loads(js(cdp, "JSON.stringify(window.GWTasks.state.tasks[%s].followUps||[])"
                                   % json.dumps(tidB), "[]") or "[]")
            if fu_ids:
                js(cdp, "window.GWTasks.setStatus(%s, 'completed')" % json.dumps(fu_ids[0]))
                time.sleep(0.5)
                js(cdp, "window.GWTasks.openTask(%s)" % json.dumps(tidB))
                time.sleep(1.0)
                js(cdp, "(function(){var b=document.querySelector('[data-set-status=none]');if(b)b.click();})()")
                time.sleep(1.0)
                dlgB = json.loads(js(cdp, r"""(function(){
                  var d=document.querySelector('.ui-dialog__box');
                  if(!d) return '{}';
                  return JSON.stringify({title:(d.querySelector('.ui-dialog__title')||{}).textContent||'',
                    body:(d.querySelector('.ui-dialog__body')||{}).textContent||'',
                    buttons:[].slice.call(d.querySelectorAll('.ui-btn')).map(function(b){return b.textContent.trim();})});})()""", "{}") or "{}")
                ok("T6 重置后续确认框出现并含「仅重置当前任务」",
                   "重置" in (dlgB.get("title") or "") and
                   any("仅重置当前任务" in b for b in (dlgB.get("buttons") or [])), dlgB.get("title"))
                ok("T7 弹窗列出直接/间接后续任务",
                   any(x in (dlgB.get("body") or "") for x in ("直接后续", "间接")),
                   (dlgB.get("body") or "")[:160])
                shot(cdp, "05-link-dialog-reset.png")
                js(cdp, "(function(){var d=document.querySelector('.ui-dialog__box');if(!d)return;"
                         "var bs=[].slice.call(d.querySelectorAll('.ui-btn'));"
                         "var c=bs.filter(function(b){return b.textContent.indexOf('仅重置当前任务')>=0;})[0]; if(c)c.click();})()")
                time.sleep(1.0)
                ok("T8 「仅重置当前任务」不动后续任务",
                   js(cdp, "window.GWTasks.status(%s)" % json.dumps(tidB)) == "none" and
                   js(cdp, "window.GWTasks.status(%s)" % json.dumps(fu_ids[0])) == "completed",
                   {"cur": js(cdp, "window.GWTasks.status(%s)" % json.dumps(tidB)),
                    "fu": js(cdp, "window.GWTasks.status(%s)" % json.dumps(fu_ids[0]))})
                js(cdp, "window.GWTasks.setStatus(%s, 'completed')" % json.dumps(tidB))
                js(cdp, "window.GWTasks.setStatus(%s, 'completed')" % json.dumps(fu_ids[0]))
                time.sleep(0.5)
                js(cdp, "(function(){var b=document.querySelector('[data-set-status=none]');if(b)b.click();})()")
                time.sleep(1.0)
                js(cdp, "(function(){var d=document.querySelector('.ui-dialog__box');if(!d)return;"
                         "var bs=[].slice.call(d.querySelectorAll('.ui-btn'));"
                         "var c=bs.filter(function(b){return b.textContent.indexOf('确认并重置')>=0;})[0]; if(c)c.click();})()")
                time.sleep(1.2)
                ok("T9 确认后后续任务被重置（真实解锁方向）",
                   js(cdp, "window.GWTasks.status(%s)" % json.dumps(fu_ids[0])) == "none" and
                   js(cdp, "window.GWTasks.status(%s)" % json.dumps(tidB)) == "none",
                   {"fu": js(cdp, "window.GWTasks.status(%s)" % json.dumps(fu_ids[0])),
                    "cur": js(cdp, "window.GWTasks.status(%s)" % json.dumps(tidB))})

        urls = [r["url"] for r in cdp.requests]
        external = [u for u in urls if not (u.startswith(base) or u.startswith("data:")
                                            or u.startswith("blob:") or u.startswith("about:"))]
        report["detail"]["requests"] = {"total": len(urls), "external": external[:10]}
        ok("G1 所有请求同源（离线可跑）", not external, external[:5])
        errs = [e for e in cdp.console if e["type"] in ("exception", "error")]
        ok("G2 无 JS 异常 / 控制台错误", not errs, errs[:2])

        report["pass"] = all(x["ok"] for x in report["checks"])
        with open(os.path.join(OUT, "browser-accept.json"), "w", encoding="utf-8", newline="\n") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=1)
        total = len(report["checks"])
        passed = sum(1 for x in report["checks"] if x["ok"])
        print("结果：%d/%d 通过" % (passed, total))
        return 0 if report["pass"] else 1
    finally:
        try:
            proc.terminate()
        except Exception:                               # noqa: BLE001
            pass


if __name__ == "__main__":
    sys.exit(main())
