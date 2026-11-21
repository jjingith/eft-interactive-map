# -*- coding: utf-8 -*-
"""R19.10 验收：FORGE 型号选择器（展开/收起/更换/清除/黄色选中）+ 前握把父子布局。

真实浏览器（Chrome CDP），两种视口（1920x919 / 1384x805）：
  · FORGE：未选不显示候选 → 点档位展开 → 选型号收起只剩一款 → 移开鼠标仍是黄色 →
    再点档位重新展开 → 换型号 → 清除 → 瞄具 + 手电 + 激光同时保留 → 生成/应用后核对真实装配 id；
  · 前握把：直接安装（护木槽）/ 转接皮轨（mount 槽）/ 子附件拥挤三种枪，检查
    data-parent、grid 行列、是否与弹匣同行、连接线是否指向真实父件。
输出 docs/r19.10-layout-audit/_accept.json + screenshots/*.png
"""
import base64
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r181_accept import CDP, find_chrome, launch, wait_ready  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "r19.10-layout-audit")
SHOTS = os.path.join(OUT, "screenshots")
os.makedirs(SHOTS, exist_ok=True)

GUNS = [
    # (卡片名, key, 期望前握把安装路径类型)
    ("HK 416A5 5.56x45", "hk416", "direct"),
    ("FN SCAR-H 7.62x51突击步枪", "scar", "rail"),
    ("SIG MCX .300 Blackout", "mcx", "direct"),
]

STATE = r"""
(function(){
  function g(el){return getComputedStyle(el);}
  var rows=[].slice.call(document.querySelectorAll('.gw-forge-opts .gw-forge-poolrow'));
  return JSON.stringify({
    nOptBox: document.querySelectorAll('.gw-forge-opts').length,
    rows: rows.map(function(r){
      var s=g(r);
      return {name:(r.querySelector('span')||{}).textContent||'',
        tag:(r.querySelector('.gw-forge-mag')||{}).textContent||'',
        on:r.dataset.on, bg:s.backgroundImage, bgc:s.backgroundColor,
        color:s.color, border:s.borderTopColor, weight:s.fontWeight,
        dev:(r.closest('.gw-forge-devblk')||{dataset:{}}).dataset.dev||'',
        visible:!r.hidden && r.offsetWidth>0};
    }),
    chips: [].slice.call(document.querySelectorAll('.gw-forge-sec .gw-chips')).map(function(box){
      return [].slice.call(box.children).map(function(c){
        return {t:c.textContent, on:c.dataset.on||'', open:c.dataset.open||'',
                pressed:c.getAttribute('aria-pressed')||''};});}),
    sel: [].slice.call(document.querySelectorAll('.gw-forge-sel')).map(function(s){
      return {text:s.textContent, on:s.dataset.on||''};}),
    notes: [].slice.call(document.querySelectorAll('.gw-forge-warn')).map(function(n){return n.textContent;})
  });
})()
"""

CANVAS = r"""
(function(){
  var cv=document.getElementById('gw-tree');
  if(!cv) return 'null';
  var body=cv.querySelector('.gw-cell-body');
  var br=body?body.getBoundingClientRect():null;
  var cr=cv.getBoundingClientRect();
  var cells=[].slice.call(cv.querySelectorAll('.gw-part[data-slot]')).map(function(c){
    var r=c.getBoundingClientRect();
    return {slot:c.getAttribute('data-slot'), parent:c.getAttribute('data-parent')||'',
      lane:c.getAttribute('data-lane'), row:+c.getAttribute('data-row'), col:+c.getAttribute('data-col'),
      item:c.getAttribute('data-item')||'', x:Math.round(r.x-cr.x), y:Math.round(r.y-cr.y),
      w:Math.round(r.width), h:Math.round(r.height),
      cx:Math.round(r.x-cr.x+r.width/2), bottom:Math.round(r.y-cr.y+r.height)};});
  var links=[].slice.call(cv.querySelectorAll('svg.gw-canvas-links path')).map(function(p){
    return {d:p.getAttribute('d')};});
  return JSON.stringify({cols:getComputedStyle(cv).getPropertyValue('--gw-cols').trim(),
    rows:getComputedStyle(cv).getPropertyValue('--gw-rows').trim(),
    body: body?{row:+body.getAttribute('data-row'), col:+body.getAttribute('data-col'),
                x:Math.round(br.x-cr.x), w:Math.round(br.width)}:null,
    cells:cells, links:links,
    ammoSlot:(cv.querySelector('.gw-part-ammo')?{row:+cv.querySelector('.gw-part-ammo').getAttribute('data-row'),
              col:+cv.querySelector('.gw-part-ammo').getAttribute('data-col')}:null)});
})()
"""


def shot(cdp, name, clip=None):
    p = {"format": "png", "captureBeyondViewport": False}
    if clip:
        p["clip"] = dict(clip, scale=1)
    data = base64.b64decode(cdp.call("Page.captureScreenshot", **p)["data"])
    with open(os.path.join(SHOTS, name), "wb") as f:
        f.write(data)


def pick(cdp, needle):
    for _ in range(5):
        cdp.eval("""(function(){var b=document.querySelector('.gw-mode[data-gwmode="caliber"]');
          if(b)b.click();})()""")
        time.sleep(0.8)
        pos = cdp.eval("""(function(){var cs=document.querySelectorAll('#gw-browse .gw-card');
          for(var i=0;i<cs.length;i++){var s=cs[i].querySelector('span');
            if(s && s.textContent.indexOf('%s')>=0){cs[i].scrollIntoView({block:'center'});
              var r=cs[i].getBoundingClientRect();
              return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2});}}})()""" % needle)
        if not pos or pos == "null":
            continue
        p = json.loads(pos)
        time.sleep(0.55)
        hit = cdp.eval("(function(){var e=document.elementFromPoint(%f,%f);"
                       "return !!(e&&e.closest&&e.closest('#gw-browse .gw-card'));})()"
                       % (p["x"], p["y"]))
        if not hit:
            continue
        cdp.click_at(p["x"], p["y"])
        time.sleep(2.2)
        if needle.split(" ")[0] in (cdp.eval(
                "(document.getElementById('gw-current')||{}).textContent") or ""):
            return True
    return False


def click_chip(cdp, label):
    return cdp.eval("""(function(){
      var bs=document.querySelectorAll('.gw-forge-sec .gw-chips .gw-chip');
      for(var i=0;i<bs.length;i++){ if(bs[i].textContent===%s){ bs[i].click(); return true; } }
      return false;})()""" % json.dumps(label, ensure_ascii=False))


def state(cdp):
    return json.loads(cdp.eval(STATE) or "{}")


def canvas(cdp):
    return json.loads(cdp.eval(CANVAS) or "{}")


def yellow(style):
    """选中行必须是黄色渐变 + 黑字（#fff6d2 → #ffe9a8）。"""
    bgi = (style.get("bg") or "").replace(" ", "")
    return "rgb(255,246,210)" in bgi and "rgb(255,233,168)" in bgi and \
        style.get("color") == "rgb(0, 0, 0)"


def measure_foregrip(cv):
    """从画布测量结果里取前握把 / 弹匣 / 后握把 / 父件 / 连接线。"""
    cells = cv.get("cells") or []
    by_slot = {c["slot"]: c for c in cells}
    fore = [c for c in cells if c["slot"].split("/")[-1] == "mod_foregrip"]
    mag = [c for c in cells if c["slot"] == "mod_magazine"]
    grip = [c for c in cells if c["slot"] in ("mod_pistol_grip", "mod_pistolgrip")]
    out = {"cells": len(cells), "cols": cv.get("cols"), "rows": cv.get("rows"),
           "body": cv.get("body"), "ammo": cv.get("ammoSlot"),
           "magazine": mag[0] if mag else None,
           "pistolGrip": grip[0] if grip else None}
    if not fore:
        out["foregrip"] = None
        return out
    f = fore[0]
    p = by_slot.get(f["parent"]) if f["parent"] else None
    out["foregrip"] = f
    out["parent"] = p
    out["parentSlot"] = f["parent"]
    out["sameRowAsMag"] = bool(mag) and mag[0]["row"] == f["row"]
    out["rightOfGrip"] = bool(grip) and grip[0]["row"] == f["row"] and f["col"] > grip[0]["col"]
    out["alignedWithParent"] = bool(p) and p["col"] == f["col"]
    out["directlyBelowParent"] = bool(p) and f["row"] == p["row"] + 1
    # 连接线：父件底边中心 → 子件顶边中心（同列时是一条竖线）
    out["linkFromParent"] = False
    if p:
        import re as _re
        for lk in cv.get("links") or []:
            d = lk.get("d") or ""
            m = _re.match(r"M\s*(-?[\d.]+)[ ,]+(-?[\d.]+)", d)
            if not m:
                continue
            x0, y0 = float(m.group(1)), float(m.group(2))
            if abs(x0 - p["cx"]) <= 1.5 and abs(y0 - p["bottom"]) <= 1.5:
                out["linkFromParent"] = True
                out["linkD"] = d
                break
    return out


def install_foregrip(cdp):
    """点前握把槽位卡 → 右栏候选 → 装第一款不冲突的配件。"""
    pos = cdp.eval("""(function(){
      var cs=[].slice.call(document.querySelectorAll('#gw-tree .gw-part[data-slot]'));
      for(var i=0;i<cs.length;i++){
        if(cs[i].getAttribute('data-slot').split('/').pop()==='mod_foregrip'){
          cs[i].scrollIntoView({block:'center'});
          var r=cs[i].getBoundingClientRect();
          return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2,slot:cs[i].getAttribute('data-slot')});}}
      return null;})()""")
    if not pos or pos == "null":
        return {"error": "画布上没有前握把槽位卡"}
    p = json.loads(pos)
    time.sleep(0.5)
    hit = cdp.eval("(function(){var e=document.elementFromPoint(%f,%f);"
                   "return !!(e&&e.closest&&e.closest('.gw-part[data-slot]'));})()" % (p["x"], p["y"]))
    if not hit:
        return {"error": "前握把卡不可点击", "pos": p}
    cdp.click_at(p["x"], p["y"])
    time.sleep(1.6)
    name = cdp.eval("""(function(){
      var rows=[].slice.call(document.querySelectorAll('#gw-cands .tbl-row, .gw-cands .tbl-row'));
      if(!rows.length){ rows=[].slice.call(document.querySelectorAll('.tbl-row')); }
      for(var i=0;i<rows.length;i++){
        if(rows[i].className.indexOf('tbl-conflict')>=0) continue;
        var nm=rows[i].querySelector('.gw-row-name b');
        if(!nm) continue;
        var r=rows[i].getBoundingClientRect();
        if(r.width<=0) continue;
        rows[i].scrollIntoView({block:'center'});
        var r2=rows[i].getBoundingClientRect();
        return JSON.stringify({x:r2.x+r2.width/2,y:r2.y+r2.height/2,name:nm.textContent});
      }
      return null;})()""")
    if not name or name == "null":
        return {"error": "右栏没有可选前握把候选"}
    n = json.loads(name)
    time.sleep(0.4)
    cdp.click_at(n["x"], n["y"])
    time.sleep(1.8)
    return {"slot": p["slot"], "picked": n["name"]}


def run_forge(cdp, rep, tag):
    """6.1 全流程。"""
    r = {}
    cdp.eval("document.querySelector('.gw-forge').scrollTop = 0")
    time.sleep(0.3)
    rep["forge"]["initial_" + tag] = state(cdp)

    # 1) 展开「中」
    click_chip(cdp, "中")
    time.sleep(0.8)
    opened = state(cdp)
    rep["forge"]["mid_open_" + tag] = opened
    r["openRows"] = len(opened["rows"])

    # 2) 选第一款
    first = cdp.eval("""(function(){var r=document.querySelector('.gw-forge-opts .gw-forge-poolrow');
      if(!r) return null; var n=(r.querySelector('span')||{}).textContent; r.click(); return n;})()""")
    time.sleep(0.8)
    cdp.mouse(8, 60)          # 鼠标移开（仍在页面内，但不悬停在该行）
    time.sleep(0.4)
    closed = state(cdp)
    rep["forge"]["picked_" + tag] = {"name": first, "state": closed}
    r["pickedRows"] = len(closed["rows"])
    r["pickedYellow"] = bool(closed["rows"]) and yellow(closed["rows"][0])
    r["pickedName"] = first

    # 3) 再点档位 → 重新展开
    click_chip(cdp, "中")
    time.sleep(0.8)
    reopen = state(cdp)
    rep["forge"]["reopen_" + tag] = reopen
    r["reopenRows"] = len(reopen["rows"])
    r["reopenKeepsSelected"] = any(x["on"] == "1" for x in reopen["rows"])

    # 4) 换一个型号
    second = cdp.eval("""(function(){
      var rows=[].slice.call(document.querySelectorAll('.gw-forge-opts .gw-forge-poolrow'));
      for(var i=0;i<rows.length;i++){ if(rows[i].dataset.on!=='1'){
        var n=(rows[i].querySelector('span')||{}).textContent; rows[i].click(); return n; } }
      return null;})()""")
    time.sleep(0.8)
    cdp.mouse(8, 60)
    time.sleep(0.4)
    swapped = state(cdp)
    rep["forge"]["swapped_" + tag] = {"name": second, "state": swapped}
    r["swappedRows"] = len(swapped["rows"])
    r["swappedName"] = swapped["rows"][0]["name"] if swapped["rows"] else None
    r["swappedYellow"] = bool(swapped["rows"]) and yellow(swapped["rows"][0])
    r["oldHidden"] = r["swappedName"] is not None and r["swappedName"] != first

    # 5) 清除
    click_chip(cdp, "清除")
    time.sleep(0.7)
    cleared = state(cdp)
    rep["forge"]["cleared_" + tag] = cleared
    r["clearedRows"] = len(cleared["rows"])
    r["clearedNoSel"] = not any(s["on"] == "1" for s in cleared["sel"])

    # 6) 瞄具 + 手电 + 激光 同时保留
    click_chip(cdp, "中")
    time.sleep(0.6)
    cdp.eval("""(function(){var r=document.querySelector('.gw-forge-opts .gw-forge-poolrow');
      if(r) r.click();})()""")
    time.sleep(0.6)
    click_chip(cdp, "手电")
    time.sleep(0.7)
    cdp.eval("""(function(){var b=document.querySelector('.gw-forge-devblk[data-dev="light"] .gw-forge-opts .gw-forge-poolrow');
      if(b) b.click();})()""")
    time.sleep(0.7)
    click_chip(cdp, "激光")
    time.sleep(0.7)
    cdp.eval("""(function(){var b=document.querySelector('.gw-forge-devblk[data-dev="laser"] .gw-forge-opts .gw-forge-poolrow');
      if(b) b.click();})()""")
    time.sleep(0.8)
    cdp.mouse(8, 60)
    time.sleep(0.3)
    both = state(cdp)
    rep["forge"]["both_" + tag] = both
    r["bothRows"] = len(both["rows"])
    r["bothAllYellow"] = bool(both["rows"]) and all(yellow(x) for x in both["rows"])
    r["bothDevTags"] = [x["dev"] for x in both["rows"] if x["dev"]]
    r["bothText"] = [x["name"] for x in both["rows"]]
    r["chips"] = [c for grp in both["chips"] for c in grp]
    return r


def run_tiers(cdp):
    """近 / 中 / 远 三档逐一验证：展开 → 选型号收起 → 黄色 → 重新展开 → 清除。"""
    out = {}
    for tier, label in (("near", "近"), ("mid", "中"), ("far", "远")):
        click_chip(cdp, label)
        time.sleep(0.8)
        opened = state(cdp)
        n_open = len(opened["rows"])
        picked = cdp.eval("""(function(){var r=document.querySelector('.gw-forge-opts .gw-forge-poolrow');
          if(!r) return null; var n=(r.querySelector('span')||{}).textContent; r.click(); return n;})()""")
        time.sleep(0.8)
        cdp.mouse(8, 60)
        time.sleep(0.3)
        closed = state(cdp)
        shot(cdp, "tier-%s-picked.png" % tier)
        click_chip(cdp, label)
        time.sleep(0.7)
        reopened = state(cdp)
        click_chip(cdp, "清除")
        time.sleep(0.6)
        cleared = state(cdp)
        out[tier] = {
            "openRows": n_open,
            "tierChipPressed": any(c["pressed"] == "true" for grp in opened["chips"] for c in grp),
            "picked": picked,
            "pickedRows": len(closed["rows"]),
            "pickedYellow": bool(closed["rows"]) and yellow(closed["rows"][0]),
            "reopenRows": len(reopened["rows"]),
            "reopenKeeps": any(r["on"] == "1" for r in reopened["rows"]),
            "clearedRows": len(cleared["rows"]),
            "clearedTierOff": not any(c["on"] == "1" for grp in cleared["chips"] for c in grp
                                      if c["t"] in ("近", "中", "远")),
        }
    return out


def apply_and_check(cdp, rep, tag):
    """生成 + 应用 + 核对真实装配里的 id。"""
    r = {}
    sel_ids = cdp.eval("""(function(){
      var out=[];
      var rows=[].slice.call(document.querySelectorAll('.gw-forge-opts .gw-forge-poolrow'));
      rows.forEach(function(x){ if(x.dataset.on==='1'){
        var img=x.querySelector('img'), src=img?img.getAttribute('src')||'':'';
        var m=src.match(/([0-9a-f]{24})/);
        out.push({name:(x.querySelector('span')||{}).textContent||'', id:m?m[1]:null,
                  dev:(x.closest('.gw-forge-devblk')||{dataset:{}}).dataset.dev||'optic'});}});
      return JSON.stringify(out);})()""")
    r["selected"] = json.loads(sel_ids or "[]")
    cdp.eval("document.querySelector('.gw-forge-go').click()")
    for _ in range(46):
        time.sleep(0.5)
        if cdp.eval("document.querySelectorAll('.gw-forge-res').length") > 0:
            break
    res = cdp.eval("""(function(){
      var rows=[].slice.call(document.querySelectorAll('.gw-forge-res'));
      return JSON.stringify(rows.map(function(x){
        return {text:(x.textContent||'').replace(/\\s+/g,' ').slice(0,180),
                bad:!!x.querySelector('.gw-forge-viol')};}));})()""")
    r["results"] = json.loads(res or "[]")
    applied = cdp.eval("""(function(){
      var rows=[].slice.call(document.querySelectorAll('.gw-forge-res'));
      var good=rows.filter(function(x){return !x.querySelector('.gw-forge-viol');})[0];
      if(!good) return false;
      var b=good.querySelector('button'); if(!b||b.disabled) return false;
      b.click(); return true;})()""")
    time.sleep(2.4)
    r["applied"] = bool(applied)
    r["installedIds"] = json.loads(cdp.eval("""(function(){
      var ids=[];
      [].forEach.call(document.querySelectorAll('#gw-tree .gw-part .gw-part-ic'), function(i){
        var m=(i.getAttribute('src')||'').match(/([0-9a-f]{24})\\.(png|webp|jpg)/);
        if(m) ids.push(m[1]);});
      return JSON.stringify(ids);})()""") or "[]")
    want = [s["id"] for s in r["selected"] if s["id"]]
    r["constraintHits"] = {i: (i in r["installedIds"]) for i in want}
    rep["forge"]["apply_" + tag] = r
    return r


def main():
    rep = {"forge": {}, "foregrip": {}, "viewports": {}}
    proc, ws = launch(find_chrome(), 9436, 1920, 919,
                      os.path.join(os.environ.get("TEMP", "."), "r1910a-%d" % os.getpid()))
    try:
        cdp = CDP(ws)
        for m in ("Page.enable", "Runtime.enable", "Log.enable", "Network.enable"):
            cdp.call(m)
        cdp.call("Emulation.setDeviceMetricsOverride", width=1920, height=919,
                 deviceScaleFactor=1, mobile=False)
        cdp.call("Page.navigate", url="http://127.0.0.1:8787/index.html")
        wait_ready(cdp, want_url="index.html")
        time.sleep(2.0)
        cdp.eval("try{localStorage.removeItem('eftmap.gwmode')}catch(e){}")
        cdp.eval("document.querySelector('[data-view=\"gun\"]').click()")
        time.sleep(2.5)

        # ---------------- 前握把：三种安装路径 ----------------
        for needle, key, kind in GUNS:
            assert pick(cdp, needle), needle + " 选枪失败"
            time.sleep(1.2)
            inst = install_foregrip(cdp)
            time.sleep(1.2)
            cv = canvas(cdp)
            m = measure_foregrip(cv)
            m["kind"] = kind
            m["install"] = inst
            rep["foregrip"][key] = m
            # 画布截图（整块中栏）
            box = cdp.eval("""(function(){var r=document.getElementById('gw-tree').getBoundingClientRect();
              return JSON.stringify({x:r.x-6,y:r.y-6,width:r.width+12,height:r.height+12});})()""")
            shot(cdp, "fg-%s-%s.png" % (key, kind), json.loads(box))
            if key == "hk416":
                for f in (".gw-forge",):
                    el = cdp.eval("""(function(){var r=document.querySelector('%s').getBoundingClientRect();
                      return JSON.stringify({x:r.x,y:r.y,width:r.width,height:Math.min(r.height,760)});})()""" % f)
                    shot(cdp, "forge-panel-1920.png", json.loads(el))

        # ---------------- FORGE 全流程（回到 AK-74 之外的有皮轨枪：416A5）----------------
        assert pick(cdp, "HK 416A5 5.56x45"), "重新选 416A5 失败"
        time.sleep(1.4)
        # 先记录未选状态
        rep["forge"]["initial"] = state(cdp)
        rep["forge"]["tierSummary"] = run_tiers(cdp)
        f1 = run_forge(cdp, rep, "1920")
        rep["forge"]["summary_1920"] = f1
        shot(cdp, "forge-both-picked-1920.png")
        ap = apply_and_check(cdp, rep, "1920")
        rep["forge"]["applySummary_1920"] = {k: ap[k] for k in
                                             ("selected", "applied", "constraintHits")}

        # 换到没有这些设备的枪（手枪）→ 旧选择不得继续显示为有效
        assert pick(cdp, "Glock 17 9x19"), "选 Glock 17 失败"
        time.sleep(1.6)
        after = state(cdp)
        rep["forge"]["afterSwitch"] = after
        rep["forge"]["switchCleared"] = {
            "rows": len(after["rows"]),
            "notes": after["notes"],
            "anyOn": any(r["on"] == "1" for r in after["rows"]),
        }
        shot(cdp, "forge-after-gun-switch.png")

        # 手枪三档：记录每档兼容数量 / 无兼容时的提示文案
        pistol = {}
        for tier, label in (("near", "近"), ("mid", "中"), ("far", "远")):
            cdp.eval("document.querySelector('.gw-forge').scrollTop = 0")
            click_chip(cdp, label)
            time.sleep(0.8)
            st = state(cdp)
            msg = cdp.eval("""(function(){
              var o=document.querySelector('.gw-forge-opts');
              if(!o) return null;
              var n=o.querySelector('.gw-forge-note');
              return n?n.textContent:null;})()""")
            pistol[tier] = {"rows": len(st["rows"]), "note": msg}
            shot(cdp, "pistol-tier-%s.png" % tier)
            click_chip(cdp, "清除")
            time.sleep(0.5)
        rep["forge"]["pistol_tiers"] = pistol

        # ---------------- 1384x805 视口复验 ----------------
        cdp.call("Emulation.setDeviceMetricsOverride", width=1384, height=805,
                 deviceScaleFactor=1, mobile=False)
        time.sleep(1.2)
        assert pick(cdp, "HK 416A5 5.56x45"), "1384 选 416A5 失败"
        time.sleep(1.4)
        f2 = run_forge(cdp, rep, "1384")
        rep["forge"]["summary_1384"] = f2
        shot(cdp, "forge-both-picked-1384.png")
        # 前握把画布（1384）
        inst2 = install_foregrip(cdp)
        time.sleep(1.2)
        m2 = measure_foregrip(canvas(cdp))
        m2["install"] = inst2
        rep["foregrip"]["hk416_1384"] = m2
        box = cdp.eval("""(function(){var r=document.getElementById('gw-tree').getBoundingClientRect();
          return JSON.stringify({x:r.x-6,y:r.y-6,width:r.width+12,height:r.height+12});})()""")
        shot(cdp, "fg-hk416-1384.png", json.loads(box))
        shot(cdp, "page-1384.png")

        # 溢出检查（两种视口）
        rep["viewports"]["1920"] = json.loads(cdp.eval(
            "(function(){return JSON.stringify({w:innerWidth,sw:document.documentElement.scrollWidth});})()")
            or "{}")
        cdp.call("Emulation.setDeviceMetricsOverride", width=1920, height=919,
                 deviceScaleFactor=1, mobile=False)
        time.sleep(1.0)
        rep["viewports"]["1384_restored"] = json.loads(cdp.eval(
            "(function(){return JSON.stringify({w:innerWidth,sw:document.documentElement.scrollWidth});})()")
            or "{}")

        rep["console"] = (getattr(cdp, "console", None) or [])[:8]
        rep["external"] = [r for r in (getattr(cdp, "requests", None) or [])
                           if "127.0.0.1" not in r["url"]][:6]
    finally:
        proc.terminate()

    with open(os.path.join(OUT, "_accept.json"), "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)

    print(json.dumps({
        "foregrip": {k: {kk: v.get(kk) for kk in
                         ("kind", "cols", "rows", "parentSlot", "alignedWithParent",
                          "directlyBelowParent", "sameRowAsMag", "rightOfGrip", "linkFromParent",
                          "install")} for k, v in rep["foregrip"].items()},
        "tiers": rep["forge"].get("tierSummary"),
        "forge1920": f1,
        "apply": rep["forge"].get("applySummary_1920"),
        "switch": rep["forge"].get("switchCleared"),
        "forge1384": f2,
        "viewports": rep["viewports"],
        "console": rep["console"], "external": len(rep["external"]),
    }, ensure_ascii=False, indent=1)[:6000])


if __name__ == "__main__":
    main()
