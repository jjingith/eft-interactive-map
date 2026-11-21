# -*- coding: utf-8 -*-
"""R19.13 布局规则修订 · 浏览器验收（1920×919 / 1384×805）。

覆盖任务书第 6 节的 12 项：前照门对齐、无枪管槽前照门、瞄具在上机匣正上方、照门在拉机柄左侧、
MPR45 在护木正上方、上方导轨配件在其左侧、前握把在下护木/导轨下方、枪口纵向链、护木其余附件进第六行、
6×9 稳定不漂移、以及 R19.12 功能不回退。
输出 docs/r19.13-layout-audit/{_accept.json,screenshots/*.png}
"""
import base64
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r181_accept import CDP, find_chrome, launch, wait_ready  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "r19.13-layout-audit")
SHOTS = os.path.join(OUT, "screenshots")
os.makedirs(SHOTS, exist_ok=True)

GRID_JS = """(function(){
  var t=document.getElementById('gw-tree');
  if(!t) return null;
  var cs=getComputedStyle(t);
  var body=t.querySelector('.gw-cell-body');
  var cards=[].slice.call(t.querySelectorAll('.gw-part[data-row]')).map(function(c){
    var r=c.getBoundingClientRect();
    return {slot:c.getAttribute('data-slot')||'', row:+c.getAttribute('data-row'),
      col:+c.getAttribute('data-col'), parent:c.getAttribute('data-parent')||'',
      item:c.getAttribute('data-item')||'',
      base:(c.getAttribute('data-slot')||'').split('/').pop().replace(/^mod_/,'').replace(/[_#][0-9]+$/,''),
      x:Math.round(r.x), y:Math.round(r.y), w:Math.round(r.width), h:Math.round(r.height)};});
  var br=body?body.getBoundingClientRect():null;
  return JSON.stringify({
    cols: cs.gridTemplateColumns.split(' ').length,
    rows: cs.gridTemplateRows === 'none' ? 0 : cs.gridTemplateRows.split(' ').length,
    width: Math.round(t.getBoundingClientRect().width),
    height: Math.round(t.getBoundingClientRect().height),
    body: br ? {row: body.getAttribute('data-row'), col: body.getAttribute('data-col'),
                span: body.getAttribute('data-span')} : null,
    cards: cards,
    scrollW: document.documentElement.scrollWidth, innerW: innerWidth
  });
})()"""


def shot(cdp, name):
    data = base64.b64decode(cdp.call("Page.captureScreenshot", format_="png",
                                     captureBeyondViewport=False)["data"])
    with open(os.path.join(SHOTS, name), "wb") as f:
        f.write(data)


def pick_gun(cdp, needle):
    for _ in range(5):
        cdp.eval("""(function(){var b=document.querySelector('.gw-mode[data-gwmode="caliber"]');
          if(b)b.click();})()""")
        time.sleep(0.7)
        pos = cdp.eval("""(function(){var cs=document.querySelectorAll('#gw-browse .gw-card');
          for(var i=0;i<cs.length;i++){var s=cs[i].querySelector('span');
            if(s && s.textContent.indexOf(%s)>=0){cs[i].scrollIntoView({block:'center'});
              var r=cs[i].getBoundingClientRect();
              return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2});}}})()"""
                      % json.dumps(needle, ensure_ascii=False))
        if not pos or pos == "null":
            continue
        p = json.loads(pos)
        time.sleep(0.4)
        cdp.click_at(p["x"], p["y"])
        time.sleep(2.0)
        cur = cdp.eval("(document.getElementById('gw-current')||{}).textContent") or ""
        if needle.split(" ")[0] in cur:
            # 恢复官方默认装配：排除上一轮验收/用户改动造成的持久化装配干扰
            cdp.eval("document.getElementById('gw-default') && document.getElementById('gw-default').click()")
            time.sleep(1.6)
            return True
    return False


def click_slot(cdp, sid_suffix):
    pos = cdp.eval("""(function(){
      var cs=[].slice.call(document.querySelectorAll('#gw-tree .gw-part[data-slot]'));
      for(var i=0;i<cs.length;i++){
        if(cs[i].getAttribute('data-slot').split('/').pop()===%s){
          cs[i].scrollIntoView({block:'center'});
          var r=cs[i].getBoundingClientRect();
          return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2, slot:cs[i].getAttribute('data-slot')});}}
      return null;})()""" % json.dumps(sid_suffix))
    if not pos or pos == "null":
        return None
    p = json.loads(pos)
    time.sleep(0.35)
    cdp.click_at(p["x"], p["y"])
    time.sleep(1.1)
    return p


def click_candidate(cdp, needle=None, index=0):
    info = cdp.eval("""(function(){
      var rows=[].slice.call(document.querySelectorAll('#gw-table .tbl-row'));
      var hits=[];
      for(var i=0;i<rows.length;i++){
        if(rows[i].className.indexOf('tbl-empty')>=0) continue;
        var nm=(rows[i].querySelector('.gw-row-name b')||{}).textContent||'';
        if(%s && nm.indexOf(%s)<0) continue;
        var st=rows[i].querySelector('.tbl-cell[data-key="state"]');
        hits.push({row:rows[i], name:nm, conflict:rows[i].className.indexOf('tbl-conflict')>=0,
                   state:st?st.textContent:'', why:st?st.title:''});
      }
      if(!hits.length) return null;
      var h=hits[Math.min(%d,hits.length-1)];
      h.row.scrollIntoView({block:'center'});
      var r=h.row.getBoundingClientRect();
      return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2,name:h.name,
        conflict:h.conflict,state:h.state,why:h.why});})()"""
                    % ("true" if needle else "false", json.dumps(needle or "", ensure_ascii=False), index))
    if not info or info == "null":
        return None
    h = json.loads(info)
    time.sleep(0.3)
    cdp.click_at(h["x"], h["y"])
    time.sleep(1.3)
    return h


def grid_dump(cdp):
    return json.loads(cdp.eval(GRID_JS) or "null")


def analyze(g, name):
    """把 DOM 网格翻译成任务书的 12 条验收结论。"""
    if not g:
        return {"gun": name, "error": "no grid"}
    cards = g["cards"] or []
    by = {}
    for c in cards:
        by[c["slot"]] = c
    def base_is(b):
        return [c for c in cards if c["base"] == b]
    muzzle = (base_is("muzzle") or [None])[0]
    front = (base_is("sight_front") or [None])[0]
    scope = [c for c in base_is("scope") if c["row"] == 2 and c["col"] == 5]
    mpr = [c for c in cards if c["row"] == 2 and c["col"] == 4]
    rear = [c for c in base_is("sight_rear") if c["row"] == 2 and c["col"] == 8]
    charge = [c for c in base_is("charge") if c["row"] == 2 and c["col"] == 9]
    fores = base_is("foregrip")
    handguard = (base_is("handguard") or [None])[0]
    row6 = [c for c in cards if c["row"] == 6]
    out = {
        "gun": name,
        "cols": g["cols"], "rows": g["rows"],
        "noOverflow": g["scrollW"] == g["innerW"],
        "body": g["body"],
        "muzzle": muzzle and {"row": muzzle["row"], "col": muzzle["col"], "slot": muzzle["slot"]},
        "frontSight": front and {"row": front["row"], "col": front["col"], "slot": front["slot"]},
        "frontAlignedWithMuzzle": (None if not (muzzle and front)
                                   else bool(front["col"] == muzzle["col"] and front["row"] == 2)),
        "scopeAtR2C5": (None if not base_is("scope") else bool(scope)),
        "scopeSlot": scope[0]["slot"] if scope else None,
        "rearSightAtR2C8": (None if not base_is("sight_rear") else bool(rear)),
        "chargeAtR2C9": (None if not base_is("charge") else bool(charge)),
        "mpr45AtR2C4": (None if not mpr else True),
        "mpr45NotForegrip": all(c["base"] != "foregrip" for c in mpr) if mpr else None,
        "mpr45Slot": mpr[0]["slot"] if mpr else None,
        "railExtrasLeftOfMpr45": [
            {"slot": c["slot"], "row": c["row"], "col": c["col"]}
            for c in cards if c["row"] == 2 and 1 <= c["col"] <= 3],
        "foregrips": [
            {"slot": c["slot"], "row": c["row"], "col": c["col"],
             "parent": c["parent"],
             "parentPos": (by.get(c["parent"]) or {}) and
               {"row": (by.get(c["parent"]) or {}).get("row"), "col": (by.get(c["parent"]) or {}).get("col")},
             "belowParent": bool(by.get(c["parent"]) and c["row"] >= by[c["parent"]]["row"]),
             "sameColAsParent": bool(by.get(c["parent"]) and c["col"] == by[c["parent"]]["col"]),
             "notInRow2": c["row"] != 2,
             "notInRow4Fixed": not (c["row"] == 4 and 6 <= c["col"] <= 9)}
            for c in fores],
        "handguard": handguard and {"row": handguard["row"], "col": handguard["col"]},
        "row6Extras": [{"slot": c["slot"], "base": c["base"], "col": c["col"]} for c in row6],
        "cards": cards,
    }
    return out


def main():
    proc, ws = launch(find_chrome(), 9481, 1920, 919, os.path.join(os.environ.get("TEMP", "."), "r1913"))
    rep = {"build": None, "cases": {}, "console": [], "external": []}
    try:
        cdp = CDP(ws)
        for m in ("Page.enable", "Runtime.enable", "Log.enable", "Network.enable"):
            cdp.call(m)
        cdp.call("Emulation.setDeviceMetricsOverride", width=1920, height=919,
                 deviceScaleFactor=1, mobile=False)
        cdp.call("Page.navigate", url="http://127.0.0.1:8787/index.html")
        wait_ready(cdp, want_url="index.html")
        time.sleep(2)
        rep["build"] = cdp.eval("(document.getElementById('build-rev')||{}).textContent")
        cdp.eval("try{localStorage.removeItem('eftmap.gwmode')}catch(e){}")
        cdp.eval("document.querySelector('[data-view=\"gun\"]').click()")
        time.sleep(2)

        cases = [
            ("m4a1-standard", "柯尔特 M4A1", "标准结构 + MPR45 + 经导轨前握把"),
            ("akm-integral-front", "AKM 7.62x39", "无独立枪管槽：枪口 c2、前照门 r2c2"),
            ("hk416-muzzle-chain", "HK 416A5 5.56x45 突击步枪", "枪口→转接（纵向链）+ 直接前握把"),
            ("spear-multilayer", "SIG MCX SPEAR", "多层附件 + 护木其余附件进第六行"),
            ("sa58-stockchain", "DS Arms SA-58", "多层枪托链"),
            ("glock-pistol", "Glock 17", "手枪结构"),
        ]
        for key, needle, desc in cases:
            if not pick_gun(cdp, needle):
                rep["cases"][key] = {"gun": needle, "error": "选枪失败"}
                continue
            time.sleep(1.7)
            g = grid_dump(cdp)
            rep["cases"][key] = {"desc": desc, "raw": g, "check": analyze(g, needle)}
            shot(cdp, "L-%s-1920.png" % key)

        # 1384 视口复核两把代表枪
        cdp.call("Emulation.setDeviceMetricsOverride", width=1384, height=805,
                 deviceScaleFactor=1, mobile=False)
        time.sleep(1.2)
        for key, needle, desc in cases[:2]:
            if not pick_gun(cdp, needle):
                continue
            time.sleep(1.6)
            g = grid_dump(cdp)
            rep["cases"].setdefault(key, {})["raw1384"] = g
            rep["cases"].setdefault(key, {})["check1384"] = analyze(g, needle)
            shot(cdp, "L-%s-1384.png" % key)

        # ---- 情况 B 现场演示：M4A1 + DD RIS II 上护木 + 下护木 + 前握把 ----
        #（真实安装链：换低轮廓导气箍 → 换上护木 → 装下护木 → 装前握把）
        if pick_gun(cdp, "柯尔特 M4A1"):
            time.sleep(1.6)
            def click_slot_path(cdp, suffix):
                """按槽位路径后缀精确点（避免 mod_handguard 父子同名歧义）。"""
                pos = cdp.eval("""(function(){
                  var cs=[].slice.call(document.querySelectorAll('#gw-tree .gw-part[data-slot]'));
                  for(var i=0;i<cs.length;i++){
                    var s=cs[i].getAttribute('data-slot')||'';
                    if(s===%s || s.slice(-(%s.length+1))==='/'+%s){
                      cs[i].scrollIntoView({block:'center'});
                      var r=cs[i].getBoundingClientRect();
                      return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2, slot:s});}}
                  return null;})()""" % (json.dumps(suffix), json.dumps(suffix), json.dumps(suffix)))
                if not pos or pos == "null":
                    return None
                q = json.loads(pos)
                time.sleep(0.4)
                cdp.click_at(q["x"], q["y"])
                time.sleep(1.1)
                return q

            def slot_and_pick(slot_path, name, label):
                click_slot_path(cdp, slot_path)
                h = click_candidate(cdp, name)
                return {"label": label, "slot": slot_path,
                        "picked": (h or {}).get("name"), "conflict": (h or {}).get("conflict")}
            steps = [
                slot_and_pick("mod_barrel/mod_gas_block", "Daniel Defense MK12",
                              "换低轮廓导气箍（避开与护木互斥的准星导气箍）"),
                slot_and_pick("mod_reciever/mod_handguard", "规格护木（狼棕色）", "换上护木"),
                slot_and_pick("mod_handguard/mod_handguard", "下护木（狼棕色）", "装下护木"),
                slot_and_pick("mod_handguard/mod_foregrip", "BCM GUNFIGHTER", "装前握把"),
            ]
            time.sleep(1.2)
            g = grid_dump(cdp)
            rep["caseB"] = {"steps": steps, "check": analyze(g, "M4A1 caseB"), "raw": g}
            shot(cdp, "L-caseB-upper-lower-foregrip-1920.png")

        rep["console"] = (getattr(cdp, "console", None) or [])[:8]
        rep["external"] = [r["url"] for r in (getattr(cdp, "requests", None) or [])
                           if "127.0.0.1" not in r["url"] and "localhost" not in r["url"]]
    finally:
        proc.terminate()

    with open(os.path.join(OUT, "_accept.json"), "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    print("build:", rep["build"], "console:", len(rep["console"]), "external:", len(rep["external"]))
    cb = rep.get("caseB") or {}
    if cb:
        c = cb.get("check") or {}
        print("caseB steps:", [(x["label"], x["picked"], x["conflict"]) for x in cb.get("steps", [])])
        print("caseB foregrip:", [(f["row"], f["col"], f["parent"]) for f in (c.get("foregrips") or [])])
    for k, v in rep["cases"].items():
        c = v.get("check") or {}
        print("%-22s cols%s rows%s | 前照门对齐=%s 瞄具r2c5=%s 照门r2c8=%s 拉机柄r2c9=%s MPR45=%s | 前握把=%s | 第六行附件=%d" % (
            k, c.get("cols"), c.get("rows"), c.get("frontAlignedWithMuzzle"), c.get("scopeAtR2C5"),
            c.get("rearSightAtR2C8"), c.get("chargeAtR2C9"), c.get("mpr45AtR2C4"),
            [(f["row"], f["col"], f["belowParent"], f["sameColAsParent"], f["notInRow4Fixed"])
             for f in (c.get("foregrips") or [])],
            len(c.get("row6Extras") or [])))


if __name__ == "__main__":
    main()
