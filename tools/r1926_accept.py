# -*- coding: utf-8 -*-
"""R19.18 真实浏览器验收：10 项问题逐条在运行中的本地程序上核对。

用法：python tools/r1926_accept.py --port 9658
产物：docs/r19.18-slot-fix-audit/browser-accept.json + screenshots/

覆盖枪械：SVDS / AK-74N·AK-74M(5.45) / AK-101·AK-102(5.56) / AKM·AKMS / G28 /
Saiga-12K（红线）/ T-5000 / SKS·OP-SKS / VSK-94 / AS VAL MOD.4 / TKPD。
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
OUT = os.path.join(ROOT, "docs", "r19.18-slot-fix-audit")
BASE = "http://127.0.0.1:8787"
CALIB = os.path.join(ROOT, "data", "gun-layout-calibration.json")

GUNS = {
    "svds": ("5c46fbd72e2216398b5a8c9c", "SVDS"),
    "ak74n": ("5644bd2b4bdc2d3b4c8b4572", "AK-74N"),
    "ak74m": ("5ac4cd105acfc40016339859", "AK-74M"),
    "ak101": ("5ac66cb05acfc40198510a10", "AK-101"),
    "ak102": ("5ac66d015acfc400180ae6e4", "AK-102"),
    "akm": ("59d6088586f774275f37482f", "AKM"),
    "akms": ("59ff346386f77477562ff5e2", "AKMS"),
    "g28": ("6176aca650224f204c1da3fb", "G28"),
    "s12k": ("6981d72ed009ad83920da43a", "Saiga-12K 12 铅径自动霰弹枪（红线）"),
    "t5000": ("5df24cf80dee1b22f862e9bc", "T-5000"),
    "sks": ("574d967124597745970e7c94", "SKS"),
    "opsks": ("587e02ff24597743df3deaeb", "OP-SKS"),
    "vsk94": ("645e0c6b3b381ede770e1cc9", "VSK-94"),
    "asvalmod4": ("6871284e9a353bb50606f3ed", "MOD.4"),
    "tkpd": ("68aee763130c00663d08aea8", "TKPD"),
    "marlin": ("67c6de3ce39861860909e8e5", "MXLR"),
}


def shot(cdp, name):
    d = os.path.join(OUT, "screenshots")
    os.makedirs(d, exist_ok=True)
    data = base64.b64decode(cdp.call("Page.captureScreenshot", format_="png",
                                     captureBeyondViewport=False)["data"])
    with open(os.path.join(d, name), "wb") as f:
        f.write(data)


def pick_gun(cdp, needle, want_gid):
    tried = set()
    for _ in range(8):
        cdp.eval("""(function(){var b=document.querySelector('.gw-mode[data-gwmode="caliber"]');
          if(b)b.click();})()""")
        time.sleep(0.5)
        raw = cdp.eval("""(function(){var cs=document.querySelectorAll('#gw-browse .gw-card');
          var out=[];for(var i=0;i<cs.length;i++){var s=cs[i].querySelector('span');
            if(s && s.textContent.indexOf(%s)>=0){out.push(i);}}return JSON.stringify(out);})()"""
                      % json.dumps(needle, ensure_ascii=False))
        idxs = json.loads(raw or "[]")
        nxt = next((i for i in idxs if i not in tried), None)
        if nxt is None:
            return None
        tried.add(nxt)
        pos = cdp.eval("""(function(){var cs=document.querySelectorAll('#gw-browse .gw-card');
          var c=cs[%d]; if(!c) return null; c.scrollIntoView({block:'center'});
          var r=c.getBoundingClientRect();
          return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2});})()""" % nxt)
        if not pos or pos == "null":
            continue
        p = json.loads(pos)
        cdp.click_at(p["x"], p["y"])
        time.sleep(1.8)
        gid = cdp.eval("(function(){try{return (JSON.parse(localStorage.getItem('eftmap.gun')||'{}')||{}).gunId||null;}catch(e){return null;}})()")
        if gid != want_gid:
            continue
        cdp.eval("document.getElementById('gw-default') && document.getElementById('gw-default').click()")
        time.sleep(1.6)
        return gid
    return None


def snap(cdp):
    raw = cdp.eval(r"""(function(){
      var t=document.getElementById('gw-tree');
      if(!t) return JSON.stringify({ok:false});
      var cards=[].slice.call(t.querySelectorAll('.gw-part')).filter(function(c){return c.dataset.slot;});
      var ammo=t.querySelector('.gw-part-ammo');
      return JSON.stringify({
        ok:true,
        calib:t.getAttribute('data-calib'),
        applied:t.getAttribute('data-calib-applied'),
        fallback:t.getAttribute('data-calib-fallback'),
        topPad:+(t.getAttribute('data-top-pad')||0),
        rows:getComputedStyle(t).gridTemplateRows.split(' ').length,
        cards:cards.map(function(c){return {slot:c.dataset.slot,row:+c.dataset.row,col:+c.dataset.col,
          parent:c.getAttribute('data-parent')||'',item:c.getAttribute('data-item')||''};}),
        ammo: ammo?{row:+ammo.getAttribute('data-row'),col:+ammo.getAttribute('data-col')}:null,
        gun:(document.getElementById('gw-current')||{textContent:''}).textContent.trim()
      });})()""")
    return json.loads(raw) if raw else {"ok": False}


def candidates(cdp, slot):
    """选中槽位 → 读候选列表（名称 + 是否不兼容）。"""
    cdp.eval("(function(){var c=document.querySelector('.gw-part[data-slot=\"%s\"]'); if(c)c.click();})()"
             % json.dumps(slot)[1:-1])
    time.sleep(0.9)
    raw = cdp.eval(r"""(function(){
      var rows=document.querySelectorAll('#gw-table .tbl-row');
      var out=[];for(var i=0;i<rows.length;i++){
        out.push({id:rows[i].dataset.id||'',t:(rows[i].textContent||'').replace(/\s+/g,' ').trim().slice(0,50),
                  conflict:rows[i].className.indexOf('tbl-conflict')>=0,
                  selected:rows[i].getAttribute('aria-selected')==='true'});}
      return JSON.stringify(out);})()""")
    return json.loads(raw or "[]")


def click_candidate(cdp, pred_js):
    """按 JS 谓词点第一条候选，返回点中的 id/text。"""
    raw = cdp.eval(r"""(function(){
      var rows=document.querySelectorAll('#gw-table .tbl-row');
      for(var i=0;i<rows.length;i++){
        var r={id:rows[i].dataset.id||'',
               t:(rows[i].textContent||'').replace(/\s+/g,' ').trim().slice(0,50),
               conflict:rows[i].className.indexOf('tbl-conflict')>=0,
               selected:rows[i].getAttribute('aria-selected')==='true'};
        if(%s){ rows[i].click();
          return JSON.stringify({id:r.id,t:r.t});}}
      return null;})()""" % pred_js)
    if not raw or raw == "null":
        return None
    time.sleep(1.4)
    return json.loads(raw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9658)
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    with open(CALIB, encoding="utf-8") as f:
        calib = json.load(f)

    prof = os.path.join(os.environ.get("TEMP", "."), "r1926acc_%d" % args.port)
    proc, ws = launch(find_chrome(), args.port, 1920, 919, prof)
    rep = {"generatedFor": "R19.18", "guns": {}, "checks": {}, "failures": [], "console": []}

    def check(name, cond, extra=None):
        rep["checks"][name] = bool(cond)
        if extra is not None:
            rep["checks"][name + "_detail"] = extra
        if not cond:
            rep["failures"].append(name)

    try:
        cdp = CDP(ws)
        for m in ("Page.enable", "Runtime.enable", "Log.enable", "Network.enable"):
            cdp.call(m)
        cdp.call("Network.setCacheDisabled", cacheDisabled=True)
        cdp.call("Emulation.setDeviceMetricsOverride", width=1920, height=919,
                 deviceScaleFactor=1, mobile=False)
        cdp.call("Page.navigate", url=BASE + "/index.html")
        wait_ready(cdp, want_url="index.html")
        time.sleep(2.5)
        cdp.eval("(document.querySelector('[data-view=\"gun\"]')||{click:function(){}}).click()")
        time.sleep(1.0)

        # ---------------- 问题 1：SVDS 燕尾槽 r2c7 ----------------
        gid, needle = GUNS["svds"]
        pick_gun(cdp, needle, gid)
        s = snap(cdp)
        dv = [c for c in s["cards"] if c["slot"] == "mod_mount_000"]
        check("svds_dovetail_r2c7", bool(dv) and dv[0]["row"] == 2 and dv[0]["col"] == 7,
              dv and {"r": dv[0]["row"], "c": dv[0]["col"]})
        check("svds_dovetail_not_duplicated", len(dv) == 1)
        cands = candidates(cdp, "mod_mount_000")
        check("svds_dovetail_has_real_items", any("燕尾槽" in c["t"] for c in cands),
              [c["t"][:24] for c in cands[:3]])
        rep["guns"]["svds"] = {"cards": len(s["cards"]), "dovetail": dv}
        shot(cdp, "01-svds.png")

        # ---------------- 问题 2/7：AK 照门 ----------------
        ak_report = {}
        for key in ("ak74n", "ak74m", "ak101", "ak102", "akm", "akms"):
            gid, needle = GUNS[key]
            pick_gun(cdp, needle, gid)
            s = snap(cdp)
            akmp = [c for c in s["cards"] if "mod_sight_rear/mod_sight_rear" in c["slot"]]
            recs = ((calib.get("guns") or {}).get(gid) or {}).get("slots") or {}
            ak_report[key] = {"gun": s.get("gun"), "akmpChildSlot": bool(akmp),
                              "cards": len(s["cards"]), "calib": s.get("calib"),
                              "applied": s.get("applied"), "fallback": s.get("fallback")}
            if key in ("ak74n", "ak74m", "ak101", "ak102"):
                check("ak_45_56_no_akmp_%s" % key, not akmp, akmp)
            else:
                check("akm_has_akmp_%s" % key, bool(akmp), akmp)
            shot(cdp, "02-%s.png" % key)
        rep["guns"]["ak_sights"] = ak_report

        # ---------------- 问题 3：G28 / S12K 七行 ----------------
        for key in ("g28", "s12k"):
            gid, needle = GUNS[key]
            pick_gun(cdp, needle, gid)
            s = snap(cdp)
            row7 = [c for c in s["cards"] if c["row"] >= 7]
            check("%s_rows_7" % key, s["rows"] >= 7, s["rows"])
            check("%s_row7_slots" % key, len(row7) > 0, row7)
            rep["guns"][key] = {"gun": s.get("gun"), "rows": s["rows"], "row7": row7,
                                "cards": len(s["cards"])}
            shot(cdp, "03-%s.png" % key)

        # ---------------- 问题 4：T-5000 战术槽位 ----------------
        gid, needle = GUNS["t5000"]
        pick_gun(cdp, needle, gid)
        s = snap(cdp)
        tac = [c for c in s["cards"] if "mod_tactical" in c["slot"]]
        rails = [c for c in s["cards"] if c["slot"].endswith(("mod_mount_000", "mod_mount_001",
                                                               "mod_mount_002", "mod_mount_003"))
                 and "handguard" in c["slot"]]
        check("t5000_tactical_2", len(tac) == 2, [c["slot"] for c in tac])
        check("t5000_rails_2", len(rails) == 2, [c["slot"] for c in rails])
        rep["guns"]["t5000"] = {"tactical": [c["slot"] for c in tac], "rails": [c["slot"] for c in rails]}
        shot(cdp, "04-t5000.png")

        # ---------------- 问题 5：SKS SOCOM ----------------
        for key in ("sks", "opsks"):
            gid, needle = GUNS[key]
            pick_gun(cdp, needle, gid)
            s = snap(cdp)
            soc = [c for c in s["cards"] if c["slot"] == "mod_barrel/mod_mount_001"]
            check("%s_socom_r4c3" % key, bool(soc) and soc[0]["row"] == 4 and soc[0]["col"] == 3,
                  soc and {"r": soc[0]["row"], "c": soc[0]["col"]})
            cands = candidates(cdp, "mod_barrel/mod_mount_001")
            check("%s_socom_installable" % key, any("SOCOM" in c["t"] for c in cands),
                  [c["t"][:24] for c in cands[:3]])
            # 装上 SOCOM → 条件子槽 r2c3 / r5c3；卸下 → 消失
            hit = click_candidate(cdp, "!r.conflict && /SOCOM/.test(r.t)")
            s2 = snap(cdp)
            scope = [c for c in s2["cards"] if c["slot"].endswith("mod_scope") and "mod_mount_001" in c["slot"]]
            tact = [c for c in s2["cards"] if "mod_mount_001/mod_tactical" in c["slot"]]
            check("%s_socom_scope_r2c3" % key, bool(scope) and scope[0]["row"] == 2 and scope[0]["col"] == 3,
                  scope and {"r": scope[0]["row"], "c": scope[0]["col"]})
            check("%s_socom_tactical_r5c3" % key, bool(tact) and tact[0]["row"] == 5 and tact[0]["col"] == 3,
                  tact and {"r": tact[0]["row"], "c": tact[0]["col"]})
            shot(cdp, "05-%s-socom.png" % key)
            # 卸下
            click_candidate(cdp, "r.selected")
            s3 = snap(cdp)
            left = [c for c in s3["cards"] if "mod_mount_001/mod_" in c["slot"]]
            check("%s_socom_children_removed" % key, not left, left)
            rep["guns"][key] = {"socom": soc, "installed": hit, "scope": scope, "tactical": tact}

        # ---------------- 问题 6：GP-25 ----------------
        gp = {}
        for key in ("ak74n", "akm", "ak101"):
            gid, needle = GUNS[key]
            pick_gun(cdp, needle, gid)
            s = snap(cdp)
            lc = [c for c in s["cards"] if c["slot"] == "mod_launcher"]
            gas = [c for c in s["cards"] if c["slot"].endswith("mod_gas_block")][0]
            check("gp25_slot_%s" % key, bool(lc), lc)
            if lc:
                check("gp25_below_gas_%s" % key, lc[0]["row"] == gas["row"] + 1 and lc[0]["col"] == gas["col"],
                      {"launcher": [lc[0]["row"], lc[0]["col"]], "gas": [gas["row"], gas["col"]]})
            cands = candidates(cdp, "mod_launcher")
            check("gp25_real_item_%s" % key, any("GP-25" in c["t"] for c in cands),
                  [c["t"][:26] for c in cands[:2]])
            gp[key] = {"launcher": lc and [lc[0]["row"], lc[0]["col"]], "gas": [gas["row"], gas["col"]]}
            shot(cdp, "06-%s-gp25.png" % key)
        # 不兼容的枪（AK-545）不应有 GP-25 槽
        pick_gun(cdp, "AK-545", "628b5638ad252a16da6dd245")
        s = snap(cdp)
        check("gp25_not_on_ak545", not [c for c in s["cards"] if c["slot"] == "mod_launcher"])
        rep["guns"]["gp25"] = gp

        # ---------------- 问题 7（VSK-94）----------------
        gid, needle = GUNS["vsk94"]
        pick_gun(cdp, needle, gid)
        s = snap(cdp)
        check("vsk94_no_b3_slot", not [c for c in s["cards"] if "mod_mount" in c["slot"]],
              [c["slot"] for c in s["cards"]])
        rep["guns"]["vsk94"] = {"cards": [c["slot"] for c in s["cards"]]}
        shot(cdp, "07-vsk94.png")

        # ---------------- 问题 8（AS VAL MOD.4 top cover）----------------
        gid, needle = GUNS["asvalmod4"]
        pick_gun(cdp, needle, gid)
        s = snap(cdp)
        rails = [c for c in s["cards"] if c["slot"] in ("mod_handguard/mod_mount_000", "mod_handguard/mod_mount_001")]
        check("asvalmod4_single_35in_rail", len(rails) == 1, [c["slot"] for c in rails])
        cover = [c for c in s["cards"] if c["slot"] == "mod_handguard/mod_mount_002"]
        check("asvalmod4_cover_installed_by_default", bool(cover) and bool(cover[0]["item"]),
              cover and cover[0]["item"])
        check("asvalmod4_dovetail_hidden_with_cover",
              not [c for c in s["cards"] if c["slot"] == "mod_mount_004"])
        # 卸下 top cover → 燕尾槽恢复
        cands = candidates(cdp, "mod_handguard/mod_mount_002")
        hit = click_candidate(cdp, "r.selected")
        s2 = snap(cdp)
        check("asvalmod4_dovetail_restored", bool([c for c in s2["cards"] if c["slot"] == "mod_mount_004"]),
              [c["slot"] for c in s2["cards"] if c["slot"] == "mod_mount_004"])
        check("asvalmod4_cover_children_gone",
              not [c for c in s2["cards"] if c["slot"].startswith("mod_handguard/mod_mount_002/mod_")])
        shot(cdp, "08-asvalmod4-no-cover.png")
        rep["guns"]["asvalmod4"] = {"rails": [c["slot"] for c in rails], "cover": cover,
                                    "removed": hit, "restored": bool([c for c in s2["cards"] if c["slot"] == "mod_mount_004"])}

        # ---------------- 问题 9（TKPD）----------------
        gid, needle = GUNS["tkpd"]
        pick_gun(cdp, needle, gid)
        s = snap(cdp)
        tac = [c for c in s["cards"] if "mod_tactical" in c["slot"]]
        dv = [c for c in s["cards"] if c["slot"] in ("mod_mount_000", "mod_mount_002")]
        check("tkpd_tactical_1", len(tac) == 1, [c["slot"] for c in tac])
        check("tkpd_two_dovetail", len(dv) == 2, [c["slot"] + "@r%dc%d" % (c["row"], c["col"]) for c in dv])
        cands0 = candidates(cdp, "mod_mount_000")
        check("tkpd_dovetail_installable", any("燕尾槽" in c["t"] or "Kobra" in c["t"] or "OKP" in c["t"] for c in cands0),
              [c["t"][:24] for c in cands0[:3]])
        rep["guns"]["tkpd"] = {"tactical": [c["slot"] for c in tac],
                                "dovetail": [c["slot"] + "@r%dc%d" % (c["row"], c["col"]) for c in dv]}
        shot(cdp, "09-tkpd.png")

        # ---------------- 刷新后依然正确 ----------------
        cdp.call("Page.navigate", url=BASE + "/index.html")
        wait_ready(cdp, want_url="index.html")
        time.sleep(2.5)
        cdp.eval("(document.querySelector('[data-view=\"gun\"]')||{click:function(){}}).click()")
        time.sleep(1.0)
        pick_gun(cdp, GUNS["svds"][1], GUNS["svds"][0])
        s = snap(cdp)
        dv = [c for c in s["cards"] if c["slot"] == "mod_mount_000"]
        check("svds_after_reload_r2c7", bool(dv) and dv[0]["row"] == 2 and dv[0]["col"] == 7)
        rep["guns"]["svds_after_reload"] = dv

        # ---------------- 校准器与主画布一致（G28 第 7 行）----------------
        cdp.call("Page.navigate", url=BASE + "/index.html?layoutCalibrator=1")
        wait_ready(cdp, want_url="index.html")
        time.sleep(3.0)
        cdp.eval("""(function(){var s=document.getElementById('cal-search');
          if(!s) return; s.value='G28'; s.dispatchEvent(new Event('input',{bubbles:true}));})()""")
        time.sleep(0.7)
        cdp.eval("""(function(){var li=document.querySelector('#cal-gunlist li[data-gun]');
          if(li) li.click();})()""")
        time.sleep(1.4)
        cal = json.loads(cdp.eval(r"""(function(){
          var g=document.getElementById('cal-grid');
          var cs=g.querySelectorAll('.cal-card');
          var rows=getComputedStyle(g).gridTemplateRows.split(' ').length;
          var out=[];for(var i=0;i<cs.length;i++){
            out.push({slot:cs[i].getAttribute('data-slot'),row:+cs[i].getAttribute('data-row'),
                      col:+cs[i].getAttribute('data-col')});}
          return JSON.stringify({rows:rows,cards:out});})()""") or "{}")
        row7 = [c for c in cal.get("cards", []) if c["row"] >= 7]
        check("calibrator_g28_rows_7", cal.get("rows", 0) >= 7, cal.get("rows"))
        check("calibrator_g28_row7_cards", len(row7) > 0, row7)
        # 拖动第 7 行卡片 → 应生效
        drag = cdp.eval(r"""(function(){
          var g=document.getElementById('cal-grid');
          function cardOf(row,col){var cs=g.querySelectorAll('.cal-card');
            for(var i=0;i<cs.length;i++){if(+cs[i].getAttribute('data-row')===row&&+cs[i].getAttribute('data-col')===col)return cs[i];}return null;}
          function cc(row,col){var c=g.querySelector('.cal-gcell[data-row="'+row+'"][data-col="'+col+'"]');
            if(!c)return null;var b=c.getBoundingClientRect();return {x:b.x+b.width/2,y:b.y+b.height/2};}
          var src=cardOf(7,1), dst=cc(6,1);
          if(!src||!dst) return JSON.stringify({ok:false});
          var b=src.getBoundingClientRect();
          function ev(t,x,y,btn){src.dispatchEvent(new PointerEvent(t,{bubbles:true,clientX:x,clientY:y,button:btn||0,buttons:btn?1:0,pointerId:1}));}
          ev('pointerdown',b.x+b.width/2,b.y+b.height/2,1);
          for(var i=1;i<=6;i++){ev('pointermove',b.x+b.width/2+(dst.x-b.x-b.width/2)*i/6,b.y+b.height/2+(dst.y-b.y-b.height/2)*i/6,1);}
          ev('pointerup',dst.x,dst.y,1);
          return JSON.stringify({ok:true,slot:src.getAttribute('data-slot')});})()""")
        time.sleep(1.0)
        after = json.loads(cdp.eval(r"""(function(){
          var cs=document.querySelectorAll('#cal-grid .cal-card');
          for(var i=0;i<cs.length;i++){if((cs[i].getAttribute('data-slot')||'').indexOf('mod_tactical_000')>=0)
            return JSON.stringify({row:+cs[i].getAttribute('data-row'),col:+cs[i].getAttribute('data-col')});}
          return JSON.stringify({});})()""") or "{}")
        check("calibrator_row7_drag_works", after.get("row") == 6 and after.get("col") == 1, {"drag": drag, "after": after})
        # 撤销 → 回原位；重做 → 再移动
        cdp.eval("document.getElementById('cal-undo').click()")
        time.sleep(0.8)
        undone = json.loads(cdp.eval(r"""(function(){
          var cs=document.querySelectorAll('#cal-grid .cal-card');
          for(var i=0;i<cs.length;i++){if((cs[i].getAttribute('data-slot')||'').indexOf('mod_tactical_000')>=0)
            return JSON.stringify({row:+cs[i].getAttribute('data-row'),col:+cs[i].getAttribute('data-col')});}
          return JSON.stringify({});})()""") or "{}")
        check("calibrator_row7_undo", undone.get("row") == 7, undone)
        cdp.eval("document.getElementById('cal-redo').click()")
        time.sleep(0.8)
        redone = json.loads(cdp.eval(r"""(function(){
          var cs=document.querySelectorAll('#cal-grid .cal-card');
          for(var i=0;i<cs.length;i++){if((cs[i].getAttribute('data-slot')||'').indexOf('mod_tactical_000')>=0)
            return JSON.stringify({row:+cs[i].getAttribute('data-row'),col:+cs[i].getAttribute('data-col')});}
          return JSON.stringify({});})()""") or "{}")
        check("calibrator_row7_redo", redone.get("row") == 6, redone)
        shot(cdp, "10-calibrator-g28.png")
        rep["guns"]["calibrator_g28"] = {"rows": cal.get("rows"), "row7": row7, "after": after,
                                         "undo": undone, "redo": redone}

        rep["console"] = cdp.console[-20:]
    finally:
        try:
            cdp.call("Browser.close")
        except Exception:
            pass
        if proc:
            proc.terminate()

    rep["ok"] = not rep["failures"]
    with open(os.path.join(OUT, "browser-accept.json"), "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)
    print(json.dumps({"ok": rep["ok"], "failures": rep["failures"],
                      "checks": {k: v for k, v in rep["checks"].items() if not k.endswith("_detail")}},
                     ensure_ascii=False, indent=1))
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
