# -*- coding: utf-8 -*-
"""R19.17 校准接入主程序 —— 真实浏览器验收（A–E + 校准器/主画布一致性）。

用法：python tools/r1925_accept.py --port 9642
产物：docs/r19.17-calibration-integration/browser-accept.json + screenshots/

测试矩阵：
  A 已校准枪械：AK-74N / Milkor M32A1 / FN SCAR-L / Sako TRG M10 —— 主画布逐条对照 JSON 保存坐标
  B 未校准枪械：马林 MXLR —— 自动布局照常渲染（无空白画布 / 无布局失败）
  C 配件变化：AK-74N 装上/卸下瞄具 —— 已校准槽位坐标不动、条件子槽走自动、身份不串位
  D 持久化：校准器拖动保存 → 刷新主程序生效 → 清除还原（用户数据恢复）
  E 数据安全：测试前后校准记录（枪集 + 每条坐标）逐条一致；缺记录回退由 B + 引擎审计覆盖
  F 一致性：校准器 manual 预览与主画布同一枪同坐标
"""
from __future__ import annotations

import argparse
import base64
import copy
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r181_accept import CDP, find_chrome, launch, wait_ready  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "r19.17-calibration-integration")
BASE = "http://127.0.0.1:8787"
CALIB = os.path.join(ROOT, "data", "gun-layout-calibration.json")

A_GUNS = [
    ("ak74n", "5644bd2b4bdc2d3b4c8b4572", "AK-74N"),
    ("milkor", "6275303a9f372d6ea97f9ec7", "M32A1"),
    ("scarl", "6184055050224f204c1da540", "SCAR-L"),
    ("m10", "673cab3e03c6a20581028bc1", "TRG M10"),
]
B_GUN = ("marlin", "67c6de3ce39861860909e8e5", "MXLR")   # 马林 MXLR，无校准记录


def shot(cdp, name):
    d = os.path.join(OUT, "screenshots")
    os.makedirs(d, exist_ok=True)
    data = base64.b64decode(cdp.call("Page.captureScreenshot", format_="png",
                                     captureBeyondViewport=False)["data"])
    with open(os.path.join(d, name), "wb") as f:
        f.write(data)
    return name


def load_calib():
    with open(CALIB, encoding="utf-8") as f:
        return json.load(f)


def records_of(doc, gid):
    return ((doc.get("guns") or {}).get(gid) or {}).get("slots") or {}


def snapshot_records(doc):
    """只留「枪 + 槽位坐标」核心内容，排除 updatedAt / history 等保存元数据。"""
    out = {}
    for gid, g in (doc.get("guns") or {}).items():
        slots = {}
        for k, r in (g.get("slots") or {}).items():
            slots[k] = {"logicalRow": r.get("logicalRow"), "col": r.get("col"),
                        "role": r.get("role"), "ownerItemId": r.get("ownerItemId"),
                        "slotPath": r.get("slotPath"), "slotId": r.get("slotId")}
        out[gid] = slots
    return out


def open_main(cdp):
    cdp.call("Page.navigate", url=BASE + "/index.html")
    wait_ready(cdp, want_url="index.html")
    time.sleep(2.5)
    cdp.eval("(document.querySelector('[data-view=\"gun\"]')||{click:function(){}}).click()")
    time.sleep(1.2)


def current_gun_id(cdp):
    raw = cdp.eval("(function(){try{return (JSON.parse(localStorage.getItem('eftmap.gun')||'{}')||{}).gunId||null;}catch(e){return null;}})()")
    return raw


def pick_gun(cdp, needle, want_gid=None):
    """选枪；want_gid 给出时用 localStorage 里的真实枪 ID 校验（防同名变体点错）。"""
    tried = set()
    for _ in range(8):
        cdp.eval("""(function(){var b=document.querySelector('.gw-mode[data-gwmode="caliber"]');
          if(b)b.click();})()""")
        time.sleep(0.6)
        raw = cdp.eval("""(function(){var cs=document.querySelectorAll('#gw-browse .gw-card');
          var out=[];for(var i=0;i<cs.length;i++){var s=cs[i].querySelector('span');
            if(s && s.textContent.indexOf(%s)>=0){out.push(i);}}return JSON.stringify(out);})()"""
                      % json.dumps(needle, ensure_ascii=False))
        idxs = json.loads(raw or "[]")
        nxt = next((i for i in idxs if i not in tried), None)
        if nxt is None:
            return False
        tried.add(nxt)
        pos = cdp.eval("""(function(){var cs=document.querySelectorAll('#gw-browse .gw-card');
          var c=cs[%d]; if(!c) return null; c.scrollIntoView({block:'center'});
          var r=c.getBoundingClientRect();
          return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2});})()""" % nxt)
        if not pos or pos == "null":
            continue
        p = json.loads(pos)
        cdp.click_at(p["x"], p["y"])
        time.sleep(2.0)
        gid = current_gun_id(cdp)
        if want_gid and gid != want_gid:
            continue
        cdp.eval("document.getElementById('gw-default') && document.getElementById('gw-default').click()")
        time.sleep(1.6)
        return gid or True
    return False


def canvas_snap(cdp):
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
        cards:cards.map(function(c){
          return {slot:c.dataset.slot,row:+c.dataset.row,col:+c.dataset.col,
                  parent:c.getAttribute('data-parent')||'',item:c.getAttribute('data-item')||''};
        }),
        ammo:ammo?{row:+ammo.getAttribute('data-row'),col:+ammo.getAttribute('data-col')}:null,
        gun:(document.getElementById('gw-current')||{textContent:''}).textContent.trim()
      });})()""")
    return json.loads(raw) if raw else {"ok": False}


def calib_card(cdp, suffix):
    raw = cdp.eval("""(function(){
      var cs=document.querySelectorAll('#cal-grid .cal-card');
      for(var i=0;i<cs.length;i++){
        var s=cs[i].getAttribute('data-slot')||'';
        if(s===%s||s.substr(s.length-%d)===%s){
          return JSON.stringify({slot:s,row:+cs[i].getAttribute('data-row'),col:+cs[i].getAttribute('data-col')});
        }
      }
      return null;})(%s)""" % (json.dumps(suffix), len(suffix), json.dumps(suffix), json.dumps(suffix)))
    return json.loads(raw) if raw and raw != "null" else None


def drag_card(cdp, card, row, col):
    def cell_center(row, col):
        raw = cdp.eval("""(function(){
          var c=document.querySelector('.cal-gcell[data-row="%d"][data-col="%d"]');
          if(!c) return null; var r=c.getBoundingClientRect();
          return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2});})()""" % (row, col))
        return json.loads(raw) if raw and raw != "null" else None
    t = cell_center(row, col)
    if not t:
        return False
    # 卡片的像素位置：calib_card 只有行列，补一次矩形
    rect = cdp.eval("""(function(){
      var cs=document.querySelectorAll('#cal-grid .cal-card');
      for(var i=0;i<cs.length;i++){
        if(+cs[i].getAttribute('data-row')===%d && +cs[i].getAttribute('data-col')===%d){
          var r=cs[i].getBoundingClientRect();
          return JSON.stringify({x:r.x,y:r.y,w:r.width,h:r.height});}}
      return null;})(%d,%d)""" % (card["row"], card["col"], card["row"], card["col"]))
    if not rect or rect == "null":
        return False
    rr = json.loads(rect)
    sx, sy = rr["x"] + rr["w"] / 2, rr["y"] + rr["h"] / 2
    cdp.call("Input.dispatchMouseEvent", type="mousePressed", x=sx, y=sy, button="left", clickCount=1)
    for i in range(1, 6):
        cdp.call("Input.dispatchMouseEvent", type="mouseMoved",
                 x=sx + (t["x"] - sx) * i / 5.0, y=sy + (t["y"] - sy) * i / 5.0, button="left")
    cdp.call("Input.dispatchMouseEvent", type="mouseMoved", x=t["x"], y=t["y"], button="left")
    time.sleep(0.25)
    cdp.call("Input.dispatchMouseEvent", type="mouseReleased", x=t["x"], y=t["y"], button="left", clickCount=1)
    time.sleep(0.6)
    return True


def cal_pick_gun(cdp, needle):
    cdp.eval("""(function(){var s=document.getElementById('cal-search');
      if(!s) return false; s.value=%s;
      s.dispatchEvent(new Event('input',{bubbles:true})); return true;})()"""
             % json.dumps(needle, ensure_ascii=False))
    time.sleep(0.6)
    raw = cdp.eval("""(function(){
      var li=document.querySelector('#cal-gunlist li[data-gun]');
      if(!li) return null; li.click();
      return li.getAttribute('data-gun');})()""")
    time.sleep(0.6)
    cdp.eval("""(function(){
      var b=document.querySelector('#cal-modal button[data-choice="drop"]') ||
            document.querySelector('#cal-modal button[data-choice="ok"]') ||
            document.querySelector('#cal-modal button[data-choice="go"]');
      if(b){ b.click(); return true; } return false;})()""")
    time.sleep(1.0)
    return raw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9642)
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)

    doc0 = load_calib()
    snap0 = snapshot_records(doc0)

    prof = os.path.join(os.environ.get("TEMP", "."), "r1925prof_%d" % args.port)
    proc, ws = launch(find_chrome(), args.port, 1920, 919, prof)
    rep = {"generatedFor": "R19.17", "A": {}, "B": {}, "C": {}, "D": {}, "E": {}, "F": {},
           "console": [], "failures": []}

    def fail(msg):
        rep["failures"].append(msg)

    try:
        cdp = CDP(ws)
        for m in ("Page.enable", "Runtime.enable", "Log.enable", "Network.enable"):
            cdp.call(m)
        cdp.call("Network.setCacheDisabled", cacheDisabled=True)
        cdp.call("Emulation.setDeviceMetricsOverride", width=1920, height=919,
                 deviceScaleFactor=1, mobile=False)

        # ============================================================ A
        open_main(cdp)
        for key, gid, needle in A_GUNS:
            if not pick_gun(cdp, needle, gid):
                fail("A：%s 选枪失败" % needle)
                continue
            time.sleep(0.8)
            s = canvas_snap(cdp)
            recs = records_of(doc0, gid)
            by_slot = {c["slot"]: c for c in s.get("cards") or []}
            per = {"gun": s.get("gun"), "topPad": s.get("topPad"),
                   "calib": s.get("calib"), "applied": s.get("applied"),
                   "fallback": s.get("fallback"), "rows": s.get("rows"),
                   "records": len(recs), "match": 0, "mismatch": []}
            for k, r in recs.items():
                path = r.get("slotPath") or k.split("|")[0]
                want_row = r["logicalRow"] + per["topPad"]
                c = by_slot.get(path)
                if c and c["row"] == want_row and c["col"] == r["col"]:
                    per["match"] += 1
                else:
                    per["mismatch"].append({"key": k, "want": {"r": want_row, "c": r["col"]},
                                            "got": c})
            if per["calib"] != "1" or per["match"] != len(recs) or per["mismatch"]:
                fail("A：%s 校准未全部生效 %s" % (needle, json.dumps(per["mismatch"], ensure_ascii=False)[:300]))
            rep["A"][key] = per
            shot(cdp, "A-%s-main.png" % key)

        # ============================================================ B
        if pick_gun(cdp, B_GUN[2], B_GUN[1]):
            time.sleep(0.8)
            s = canvas_snap(cdp)
            recs = records_of(doc0, B_GUN[1])
            ok = bool(s.get("cards")) and s.get("calib") == "0" and len(recs) == 0
            rep["B"] = {"gun": s.get("gun"), "calib": s.get("calib"), "applied": s.get("applied"),
                        "cards": len(s.get("cards") or []), "rows": s.get("rows"),
                        "recordsInFile": len(recs), "ok": ok}
            if not ok:
                fail("B：未校准枪械未正常回退自动布局")
            shot(cdp, "B-marlin-auto.png")
        else:
            fail("B：马林 MXLR 选枪失败")

        # ============================================================ C
        if pick_gun(cdp, "AK-74N", "5644bd2b4bdc2d3b4c8b4572"):
            time.sleep(0.8)
            s0 = canvas_snap(cdp)
            mount0 = [c for c in s0["cards"] if c["slot"] == "mod_mount_000"]
            rep["C"]["before"] = {"mount": mount0 and mount0[0], "cards": len(s0["cards"])}

            def click_candidate(nth):
                """点第 nth 条兼容候选（0-based，跳过不兼容行），返回 {id,text}。"""
                return cdp.eval(r"""(function(nth){
                  var rows=document.querySelectorAll('#gw-table .tbl-row');
                  var k=0;
                  for(var i=0;i<rows.length;i++){
                    if(rows[i].className.indexOf('tbl-conflict')>=0) continue;
                    if(k===nth){
                      var id=rows[i].dataset.id||'';
                      rows[i].click();
                      return JSON.stringify({id:id,text:(rows[i].textContent||'').replace(/\s+/g,' ').trim().slice(0,50)});}
                    k++;
                  }
                  return null;})(%d)""" % nth)

            # 装上：点燕尾槽卡片 → 点第一条兼容候选
            cdp.eval("(document.querySelector('.gw-part[data-slot=\"mod_mount_000\"]')||{click:function(){}}).click()")
            time.sleep(0.8)
            clicked = click_candidate(0)
            clicked = json.loads(clicked) if clicked and clicked != "null" else None
            time.sleep(1.8)
            s1 = canvas_snap(cdp)
            mount1 = [c for c in s1["cards"] if c["slot"] == "mod_mount_000"]
            kids1 = [c for c in s1["cards"] if c["slot"].startswith("mod_mount_000/")]
            rep["C"]["afterInstall"] = {
                "clicked": clicked,
                "mount": mount1 and mount1[0],
                "mountKept": bool(mount0 and mount1 and mount0[0]["row"] == mount1[0]["row"]
                                 and mount0[0]["col"] == mount1[0]["col"]),
                "installed": bool(mount1 and mount1[0].get("item")),
                "childSlots": kids1, "cards": len(s1["cards"]),
                "applied": s1.get("applied")
            }
            if not rep["C"]["afterInstall"]["installed"]:
                fail("C：候选行点击未能安装配件（clicked=%s）" % clicked)
            if not rep["C"]["afterInstall"]["mountKept"]:
                fail("C：装件后已校准燕尾槽坐标漂移")
            shot(cdp, "C-after-install.png")

            # 替换：点另一条未选中候选
            cdp.eval("(document.querySelector('.gw-part[data-slot=\"mod_mount_000\"]')||{click:function(){}}).click()")
            time.sleep(0.8)
            clicked2 = click_candidate(1)
            clicked2 = json.loads(clicked2) if clicked2 and clicked2 != "null" else None
            time.sleep(1.8)
            s1b = canvas_snap(cdp)
            mount1b = [c for c in s1b["cards"] if c["slot"] == "mod_mount_000"]
            rep["C"]["afterReplace"] = {
                "clicked": clicked2,
                "item": mount1b and mount1b[0].get("item"),
                "changed": bool(mount1 and mount1b and mount1[0].get("item") != mount1b[0].get("item")),
                "mountKept": bool(mount0 and mount1b and mount0[0]["row"] == mount1b[0]["row"]
                                  and mount0[0]["col"] == mount1b[0]["col"]),
            }
            if clicked2 and not rep["C"]["afterReplace"]["changed"]:
                fail("C：替换候选未改变已装件")
            if not rep["C"]["afterReplace"]["mountKept"]:
                fail("C：替换后已校准燕尾槽坐标漂移")
            shot(cdp, "C-after-replace.png")

            # 卸下：点当前选中候选（toggle off）
            cdp.eval("(document.querySelector('.gw-part[data-slot=\"mod_mount_000\"]')||{click:function(){}}).click()")
            time.sleep(0.8)
            cdp.eval("(document.querySelector('#gw-table .tbl-row[aria-selected=\"true\"]')||{click:function(){}}).click()")
            time.sleep(1.8)
            s2 = canvas_snap(cdp)
            mount2 = [c for c in s2["cards"] if c["slot"] == "mod_mount_000"]
            kids2 = [c for c in s2["cards"] if c["slot"].startswith("mod_mount_000/")]
            rep["C"]["afterRemove"] = {
                "mount": mount2 and mount2[0],
                "mountKept": bool(mount0 and mount2 and mount0[0]["row"] == mount2[0]["row"]
                                 and mount0[0]["col"] == mount2[0]["col"]),
                "emptied": bool(mount2 and not mount2[0].get("item")),
                "childSlots": kids2, "cards": len(s2["cards"])
            }
            if not rep["C"]["afterRemove"]["emptied"]:
                fail("C：卸下未清空已装件")
            if not rep["C"]["afterRemove"]["mountKept"]:
                fail("C：卸件后校准坐标漂移")
            if len(s2["cards"]) != len(s0["cards"]):
                fail("C：卸件后槽位卡数量未复原（%d→%d）" % (len(s0["cards"]), len(s2["cards"])))
            shot(cdp, "C-after-remove.png")
        else:
            fail("C：AK-74N 选枪失败")

        # ============================================================ D + E（保存→刷新生效→清除还原）
        doc_mid = load_calib()
        if records_of(doc_mid, B_GUN[1]):
            fail("D：马林 MXLR 事先已有校准记录，放弃写入测试")
        else:
            cdp.call("Page.navigate", url=BASE + "/index.html?layoutCalibrator=1")
            wait_ready(cdp, want_url="index.html")
            time.sleep(3.0)
            cal_pick_gun(cdp, B_GUN[2])
            card = calib_card(cdp, "mod_stock")
            if not card:
                card = calib_card(cdp, "mod_magazine")
            if not card:
                fail("D：校准器里没找到可拖动卡片")
            else:
                # 拖到一个明确空位（r6c2）
                ok_drag = drag_card(cdp, card, 6, 2)
                saved = cdp.eval(r"""(function(){
                  var b=document.getElementById('cal-save'); if(b) b.click(); return true;})()""")
                time.sleep(2.0)
                cdp.eval("""(function(){
                  var b=document.querySelector('#cal-modal button[data-choice="ok"]')||
                        document.querySelector('#cal-modal button[data-choice="go"]');
                  if(b) b.click();})()""")
                time.sleep(1.0)
                doc_d = load_calib()
                recs_d = records_of(doc_d, B_GUN[1])
                rep["D"]["savedRecords"] = [{"key": k, "logicalRow": r["logicalRow"], "col": r["col"]}
                                            for k, r in recs_d.items()]
                # 刷新主程序 → 必须应用
                open_main(cdp)
                pick_gun(cdp, B_GUN[2], B_GUN[1])
                time.sleep(0.8)
                s = canvas_snap(cdp)
                hit = []
                for k, r in recs_d.items():
                    path = r.get("slotPath") or k.split("|")[0]
                    want_row = r["logicalRow"] + (s.get("topPad") or 0)
                    got = [c for c in s["cards"] if c["slot"] == path]
                    hit.append({"key": k, "want": [want_row, r["col"]],
                                "got": got and [got[0]["row"], got[0]["col"]],
                                "ok": bool(got) and got[0]["row"] == want_row and got[0]["col"] == r["col"]})
                rep["D"]["afterReload"] = {"calib": s.get("calib"), "applied": s.get("applied"),
                                           "topPad": s.get("topPad"), "slots": hit}
                if not recs_d or not all(h["ok"] for h in hit):
                    fail("D：刷新后主程序未应用保存的校准坐标")
                shot(cdp, "D-marlin-calibrated.png")
                # 清除还原（恢复用户数据）
                cdp.call("Page.navigate", url=BASE + "/index.html?layoutCalibrator=1")
                wait_ready(cdp, want_url="index.html")
                time.sleep(3.0)
                cal_pick_gun(cdp, B_GUN[2])
                cdp.eval(r"""(function(){
                  var b=document.getElementById('cal-clear'); if(b) b.click(); return true;})()""")
                time.sleep(1.0)
                cdp.eval("""(function(){
                  var b=document.querySelector('#cal-modal button[data-choice="ok"]')||
                        document.querySelector('#cal-modal button[data-choice="clear"]')||
                        document.querySelector('#cal-modal button[data-choice="go"]');
                  if(b) b.click();})()""")
                time.sleep(2.0)

        # ============================================================ E 数据安全
        doc_end = load_calib()
        snap_end = snapshot_records(doc_end)
        same = snap_end == snap0
        rep["E"] = {
            "recordsBefore": sum(len(v) for v in snap0.values()),
            "recordsAfter": sum(len(v) for v in snap_end.values()),
            "gunsBefore": len(snap0), "gunsAfter": len(snap_end),
            "contentUnchanged": same,
        }
        if not same:
            diff_guns = [g for g in set(list(snap0) + list(snap_end))
                         if snap0.get(g) != snap_end.get(g)]
            rep["E"]["diffGuns"] = diff_guns[:10]
            fail("E：校准记录内容发生变化：%s" % diff_guns[:5])

        # ============================================================ F 一致性（校准器预览 vs 主画布）
        open_main(cdp)
        pick_gun(cdp, "AK-74N", "5644bd2b4bdc2d3b4c8b4572")
        time.sleep(0.8)
        s_main = canvas_snap(cdp)
        cdp.call("Page.navigate", url=BASE + "/index.html?layoutCalibrator=1")
        wait_ready(cdp, want_url="index.html")
        time.sleep(3.0)
        cal_pick_gun(cdp, "AK-74N")
        time.sleep(1.0)
        cmp_rows = []
        for c in s_main.get("cards") or []:
            cc = calib_card(cdp, c["slot"])
            same = bool(cc) and cc["row"] == c["row"] and cc["col"] == c["col"]
            cmp_rows.append({"slot": c["slot"], "main": [c["row"], c["col"]],
                             "calibrator": cc and [cc["row"], cc["col"]], "same": same})
        ok_f = all(r["same"] for r in cmp_rows) and len(cmp_rows) > 0
        rep["F"] = {"gun": "AK-74N", "compared": len(cmp_rows), "allSame": ok_f,
                    "diffs": [r for r in cmp_rows if not r["same"]][:10]}
        if not ok_f:
            fail("F：校准器预览与主画布坐标不一致")
        shot(cdp, "F-calibrator-consistency.png")

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
                      "A": {k: {kk: vv for kk, vv in v.items() if kk != "mismatch"}
                            for k, v in rep["A"].items()},
                      "B": rep["B"], "C": {k: v for k, v in rep["C"].items() if k != "afterInstall"},
                      "D": rep.get("D"), "E": rep["E"],
                      "F": {k: v for k, v in rep["F"].items() if k != "diffs"}}, ensure_ascii=False, indent=2))
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
