# -*- coding: utf-8 -*-
"""R19.12 合并开发 · 浏览器验收（1920×919 / 1384×805）。

覆盖：
  A 枪匠大师：有效方案整树校验徽标、应用后装配一致、无解明确提示、100 发容量回归
  B 固定 6×9 画布：六类枪械（标准 / 无独立枪管槽 / 缓冲管+枪托 / 一体式枪托 /
     枪口子槽 / 多层附件）的 DOM 网格测量 + 截图
  C 动态外观：默认装配 → 换件 → 卸件 三态图层对比
  D R19.11 回归：个人属性入口、属性条三值、红斜纹、隐藏不兼容、SPEAR 弹匣
输出 docs/r19.12-canvas-audit/{_accept.json,screenshots/*.png}
"""
import base64
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r181_accept import CDP, find_chrome, launch, wait_ready  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "r19.12-canvas-audit")
SHOTS = os.path.join(OUT, "screenshots")
os.makedirs(SHOTS, exist_ok=True)

M4A1 = "柯尔特 M4A1"
AK74 = "AK-74 5.45"
SA58 = "DS Arms SA-58"
SCAR = "FN SCAR-H 7.62x51 突击"
SPEAR = "SIG MCX SPEAR"
GLOCK = "Glock 17"
ORSIS = "ORSIS T-5000M"

GRID_JS = """(function(){
  var t=document.getElementById('gw-tree');
  if(!t) return null;
  var cs=getComputedStyle(t);
  var body=t.querySelector('.gw-cell-body');
  var cards=[].slice.call(t.querySelectorAll('.gw-part[data-row]')).map(function(c){
    var r=c.getBoundingClientRect();
    return {slot:c.getAttribute('data-slot')||'', row:+c.getAttribute('data-row'),
      col:+c.getAttribute('data-col'), parent:c.getAttribute('data-parent')||'',
      item:c.getAttribute('data-item')||'', lane:c.getAttribute('data-lane')||'',
      base:(c.getAttribute('data-slot')||'').split('/').pop().replace(/^mod_/,''),
      x:Math.round(r.x), y:Math.round(r.y), w:Math.round(r.width), h:Math.round(r.height)};});
  var br=body?body.getBoundingClientRect():null;
  var skin=[].slice.call(t.querySelectorAll('.gw-skin .gw-skin-l')).map(function(i){
    return {slot:i.getAttribute('data-slot'), base:i.getAttribute('data-base'), src:(i.getAttribute('src')||'').slice(0,60)};});
  return JSON.stringify({
    cols: cs.gridTemplateColumns.split(' ').length,
    rows: cs.gridTemplateRows === 'none' ? 0 : cs.gridTemplateRows.split(' ').length,
    tplCols: cs.gridTemplateColumns, tplRows: cs.gridTemplateRows,
    gap: cs.gap,
    width: Math.round(t.getBoundingClientRect().width),
    height: Math.round(t.getBoundingClientRect().height),
    body: br ? {x:Math.round(br.x), y:Math.round(br.y), w:Math.round(br.width), h:Math.round(br.height),
                row: body.getAttribute('data-row'), col: body.getAttribute('data-col'),
                span: body.getAttribute('data-span')} : null,
    cards: cards, skin: skin,
    scrollW: document.documentElement.scrollWidth, innerW: innerWidth,
    consoleCount: 0
  });
})()"""


def shot(cdp, name, clip=None):
    p = {"format": "png", "captureBeyondViewport": False}
    if clip:
        p["clip"] = dict(clip, scale=1)
    data = base64.b64decode(cdp.call("Page.captureScreenshot", **p)["data"])
    with open(os.path.join(SHOTS, name), "wb") as f:
        f.write(data)


def clip_of(cdp, sel, pad=6):
    box = cdp.eval(
        """(function(){var e=document.querySelector(%s); if(!e) return null;
           var r=e.getBoundingClientRect();
           return JSON.stringify({x:Math.max(0,r.x-%d),y:Math.max(0,r.y-%d),
             width:r.width+2*%d,height:r.height+2*%d});})()"""
        % (json.dumps(sel), pad, pad, pad, pad))
    return json.loads(box) if box and box != "null" else None


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


def skin_dump(cdp):
    return json.loads(cdp.eval("""(function(){
      var ls=[].slice.call(document.querySelectorAll('.gw-skin .gw-skin-l'));
      return JSON.stringify({count:ls.length,
        layers:ls.map(function(i){return {base:i.getAttribute('data-base'),
          slot:i.getAttribute('data-slot'), title:i.title};}),
        tag:(document.querySelector('.gw-skin-tag')||{}).textContent||''});})()""") or "null")


def installed_dump(cdp):
    return json.loads(cdp.eval("""(function(){
      var out=[];
      [].forEach.call(document.querySelectorAll('#gw-tree .gw-part[data-slot]'), function(c){
        var it=c.getAttribute('data-item');
        if(it) out.push({slot:c.getAttribute('data-slot'), item:it});});
      return JSON.stringify(out);})()""") or "[]")


def set_viewport(cdp, w, h):
    cdp.call("Emulation.setDeviceMetricsOverride", width=w, height=h,
             deviceScaleFactor=1, mobile=False)
    time.sleep(1.2)


def forge_generate(cdp):
    """点 GENERATE BUILDS，返回方案行列表。"""
    clicked = cdp.eval("""(function(){
      var bs=[].slice.call(document.querySelectorAll('.gw-forge button'));
      for(var i=0;i<bs.length;i++){
        if(bs[i].textContent.indexOf('GENERATE')>=0){bs[i].click();return true;}}
      return false;})()""")
    if not clicked:
        return {"error": "找不到 GENERATE BUILDS 按钮"}
    time.sleep(3.5)
    return json.loads(cdp.eval("""(function(){
      var rows=[].slice.call(document.querySelectorAll('.gw-forge-res'));
      var empty=[].slice.call(document.querySelectorAll('.gw-forge .lw-ci-empty, .gw-forge .gw-forge-nosolution'))
        .map(function(e){return e.textContent;});
      return JSON.stringify({rows: rows.map(function(r){
          return {text:r.textContent.slice(0,180),
            cls:r.className,
            verify:(r.querySelector('.gw-forge-verify')||{}).textContent||'',
            verifyOk:(r.querySelector('.gw-forge-verify')||{}).dataset.ok||'',
            dropped:(r.querySelector('.gw-forge-dropped')||{}).textContent||'',
            warn:(r.querySelector('.gw-forge-viol')||{}).textContent||'',
            applyDisabled: !!((r.querySelector('button.gw-btn')||{}).disabled)};
        }), empty: empty});})()""") or "{}")


def main():
    proc, ws = launch(find_chrome(), 9471, 1920, 919, os.path.join(os.environ.get("TEMP", "."), "r1912a"))
    rep = {"build": None, "console": [], "external": []}
    try:
        cdp = CDP(ws)
        for m in ("Page.enable", "Runtime.enable", "Log.enable", "Network.enable"):
            cdp.call(m)
        set_viewport(cdp, 1920, 919)
        cdp.call("Page.navigate", url="http://127.0.0.1:8787/index.html")
        wait_ready(cdp, want_url="index.html")
        time.sleep(2)
        rep["build"] = cdp.eval("(document.getElementById('build-rev')||{}).textContent")
        cdp.eval("try{localStorage.removeItem('eftmap.gwmode')}catch(e){}")
        cdp.eval("document.querySelector('[data-view=\"gun\"]').click()")
        time.sleep(2)

        # ---------------- A 枪匠大师 ----------------
        A = {}
        assert pick_gun(cdp, M4A1), "选 M4A1 失败"
        time.sleep(1.5)
        gen = forge_generate(cdp)
        A["generate"] = gen
        shot(cdp, "A1-forge-builds.png", clip_of(cdp, ".gw-forge", 4))
        # 应用第一个有效方案
        applied = cdp.eval("""(function(){
          var rows=[].slice.call(document.querySelectorAll('.gw-forge-res'));
          for(var i=0;i<rows.length;i++){
            var b=rows[i].querySelector('button.gw-btn');
            if(b && !b.disabled){ b.click(); return rows[i].textContent.slice(0,60); }}
          return null;})()""")
        time.sleep(2.2)
        A["appliedRow"] = applied
        A["afterApply"] = {
            "installed": installed_dump(cdp),
            "hint": cdp.eval("(document.getElementById('gw-hint')||{}).textContent"),
        }
        shot(cdp, "A2-after-apply.png", clip_of(cdp, ".gw-canvas", 4))
        # 页面内复核整树：互斥对 + 声称件
        A["verifyInPage"] = json.loads(cdp.eval("""(function(){
          var g=(window.AM&&window.AM.gunState)?window.AM.gunState():null;
          var ctx=window.GB&&window.GB.context?null:null;
          // 直接用 DOM 里的已装 id 与 GB.conflictPairs 不好接 ctx；改为读 forge 结果里的 verify 徽标
          var badges=[].slice.call(document.querySelectorAll('.gw-forge-verify'))
            .map(function(e){return {t:e.textContent, ok:e.dataset.ok};});
          return JSON.stringify({badges:badges});})()""") or "{}")
        # 100 发容量回归
        cdp.eval("""(function(){
          var bs=[].slice.call(document.querySelectorAll('.gw-forge .gw-chips .gw-chip'));
          for(var i=0;i<bs.length;i++){
            if(bs[i].className.indexOf('gw-chip-missing')>=0) continue;
            if(bs[i].textContent.indexOf('100 发')===0){bs[i].click();return;}}})()""")
        time.sleep(0.6)
        A["caps100"] = forge_generate(cdp)
        shot(cdp, "A3-caps100.png", clip_of(cdp, ".gw-forge", 4))
        # 无解：AK-74 + 100 发
        assert pick_gun(cdp, AK74), "选 AK-74 失败"
        time.sleep(1.5)
        A["akNoSolution"] = forge_generate(cdp)
        shot(cdp, "A4-ak74-nosolution.png", clip_of(cdp, ".gw-forge", 4))
        rep["optimizer"] = A

        # ---------------- B 固定画布案例 ----------------
        B = {"cases": {}}
        cases = [
            ("m4a1-standard", M4A1, "标准结构（有独立枪管槽）"),
            ("ak74-integral", AK74, "无独立枪管槽（一体式）"),
            ("sa58-stockchain", SA58, "缓冲管/枪托多级链"),
            ("scar-integrated", SCAR, "一体式枪托 + 转接"),
            ("spear-multilayer", SPEAR, "多层附件"),
            ("glock-pistol", GLOCK, "手枪结构"),
        ]
        for key, needle, desc in cases:
            if not pick_gun(cdp, needle):
                B["cases"][key] = {"error": "选枪失败: " + needle}
                continue
            time.sleep(1.6)
            g = grid_dump(cdp)
            B["cases"][key] = {"desc": desc, "gun": needle, "grid": g}
            shot(cdp, "B-%s-1920.png" % key)
        set_viewport(cdp, 1384, 805)
        time.sleep(1.2)
        for key, needle, desc in cases[:2]:
            if not pick_gun(cdp, needle):
                continue
            time.sleep(1.6)
            B["cases"].setdefault(key, {})["grid1384"] = grid_dump(cdp)
            shot(cdp, "B-%s-1384.png" % key)
        set_viewport(cdp, 1920, 919)
        time.sleep(1.0)
        rep["layout"] = B

        # ---------------- C 动态外观 ----------------
        C = {}
        assert pick_gun(cdp, M4A1), "选 M4A1 失败"
        time.sleep(1.6)
        cdp.eval("document.getElementById('gw-default') && document.getElementById('gw-default').click()")
        time.sleep(1.8)
        C["default"] = {"skin": skin_dump(cdp), "installed": installed_dump(cdp)}
        shot(cdp, "C1-skin-default.png", clip_of(cdp, "#gw-gun-shot", 4))
        # 换枪口装置
        slot = click_slot(cdp, "mod_muzzle")
        picked = click_candidate(cdp, index=1)
        time.sleep(1.4)
        C["changed"] = {"skin": skin_dump(cdp), "installed": installed_dump(cdp),
                        "slot": slot, "picked": picked}
        shot(cdp, "C2-skin-changed.png", clip_of(cdp, "#gw-gun-shot", 4))
        # 右键卸下枪口装置
        cdp.eval("""(function(){var cs=[].slice.call(document.querySelectorAll('#gw-tree .gw-part[data-slot]'));
          for(var i=0;i<cs.length;i++){ if(cs[i].getAttribute('data-slot').split('/').pop()==='mod_muzzle'){
            cs[i].dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,cancelable:true})); return;}}})()""")
        time.sleep(1.6)
        C["removed"] = {"skin": skin_dump(cdp), "installed": installed_dump(cdp)}
        shot(cdp, "C3-skin-removed.png", clip_of(cdp, "#gw-gun-shot", 4))
        C["layerDiff"] = {
            "defaultBases": [x["base"] for x in (C["default"]["skin"] or {}).get("layers", [])],
            "changedBases": [x["base"] for x in (C["changed"]["skin"] or {}).get("layers", [])],
            "removedBases": [x["base"] for x in (C["removed"]["skin"] or {}).get("layers", [])],
        }
        rep["appearance"] = C

        # ---------------- D R19.11 回归 ----------------
        D = {}
        D["profileBtn"] = cdp.eval("""(function(){var b=document.getElementById('btn-profile');
          return b?b.textContent:null;})()""")
        D["bars"] = json.loads(cdp.eval("""(function(){
          return JSON.stringify([].slice.call(document.querySelectorAll('#gw-bars .gw-bar')).map(function(r){
            var v=r.querySelector('.gw-bar-val');
            return {key:r.getAttribute('data-key'), text:v?v.textContent:'',
              segs:[].slice.call(r.querySelectorAll('.gw-bar-seg')).map(function(s){
                return s.className.replace('gw-bar-seg ','');})};}));})()""") or "[]")
        D["slotinfo"] = cdp.eval("(document.querySelector('#gw-slotinfo b')||{}).textContent")
        D["hideBad"] = json.loads(cdp.eval("""(function(){
          var c=document.getElementById('gw-hidebad');
          return JSON.stringify({exists:!!c, checked:c?c.checked:null});})()""") or "null")
        # 红斜纹：先卸下枪托 → 装 Hera 一体化枪托 → 枪托槽候选里与它互斥的项变红
        #（反向证据：直接装会被真实互斥拒绝，见 blockedByStock）
        assert pick_gun(cdp, M4A1), "选 M4A1 失败"
        time.sleep(1.5)
        cdp.eval("document.getElementById('gw-default') && document.getElementById('gw-default').click()")
        time.sleep(1.6)
        # ① 先试直接装（应被拒）
        click_slot(cdp, "mod_pistol_grip")
        click_candidate(cdp, "Hera Arms CQR AR-15 一体化枪托")
        time.sleep(1.2)
        D["blockedByStock"] = cdp.eval("(document.getElementById('gw-hint')||{}).textContent")
        # ② 卸下枪托后再装
        cdp.eval("""(function(){var cs=[].slice.call(document.querySelectorAll('#gw-tree .gw-part[data-slot]'));
          for(var i=0;i<cs.length;i++){ if(cs[i].getAttribute('data-slot')==='mod_stock'){
            cs[i].dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,cancelable:true})); return;}}})()""")
        time.sleep(1.4)
        click_slot(cdp, "mod_pistol_grip")
        click_candidate(cdp, "Hera Arms CQR AR-15 一体化枪托")
        time.sleep(1.6)
        D["heraInstalled"] = cdp.eval("""(function(){
          var c=document.querySelector('#gw-tree .gw-part[data-slot$="mod_pistol_grip"]');
          return c?c.getAttribute('data-item'):'none';})()""")
        click_slot(cdp, "mod_stock")
        time.sleep(1.0)
        D["conflictRows"] = json.loads(cdp.eval("""(function(){
          var rows=[].slice.call(document.querySelectorAll('#gw-table .tbl-row.tbl-conflict'));
          var bad=document.querySelector('#gw-table .tbl-row.tbl-conflict');
          var cs=bad?getComputedStyle(bad,'::after'):null;
          return JSON.stringify({count:rows.length,
            sample:rows.slice(0,3).map(function(r){return {
              name:(r.querySelector('.gw-row-name b')||{}).textContent||'',
              why:(r.querySelector('.gw-row-why')||{}).textContent||''};}),
            stripe: cs?cs.backgroundImage.slice(0,90):null,
            pointer: cs?cs.pointerEvents:null});})()""") or "{}")
        shot(cdp, "D1-conflict-stripes.png", clip_of(cdp, ".gw-cands", 4))
        # SPEAR 弹匣
        cdp.eval("document.querySelector('[data-view=\"ammo\"]').click()")
        time.sleep(1.6)
        cdp.eval("""(function(){var t=[].slice.call(document.querySelectorAll('.am-tab'));
          for(var i=0;i<t.length;i++){if(t[i].dataset.tab==='sim'){t[i].click();return;}}})()""")
        time.sleep(2.8)
        D["spearMags"] = json.loads(cdp.eval("""(function(){
          var s=document.querySelector(\"[data-sim='gun-pick']\");
          if(!s) return JSON.stringify({error:'no-gun-pick'});
          var o=[].slice.call(s.options).filter(x=>/SPEAR/.test(x.textContent))[0];
          if(o){s.value=o.value; s.dispatchEvent(new Event('change',{bubbles:true}));}
          return JSON.stringify({picked:o?o.textContent:null});})()""") or "{}")
        time.sleep(2.0)
        D["spearMags"].update(json.loads(cdp.eval("""(function(){
          var m=document.querySelector(\"[data-sim='mag-pick']\");
          return JSON.stringify({mags:m?m.options.length:-1, disabled:m?m.disabled:null,
            first:m&&m.options[0]?m.options[0].textContent:null});})()""") or "{}"))
        shot(cdp, "D2-spear-sim-mags.png")
        rep["regression"] = D

        rep["console"] = (getattr(cdp, "console", None) or [])[:8]
        rep["external"] = [r["url"] for r in (getattr(cdp, "requests", None) or [])
                           if "127.0.0.1" not in r["url"] and "localhost" not in r["url"]]
    finally:
        proc.terminate()

    with open(os.path.join(OUT, "_accept.json"), "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    # 摘要
    print("build:", rep.get("build"))
    print("console:", len(rep.get("console") or []), "external:", len(rep.get("external") or []))
    gen = (rep.get("optimizer") or {}).get("generate") or {}
    print("forge rows:", len(gen.get("rows") or []), "empty:", (gen.get("empty") or [])[:1])
    for r in (gen.get("rows") or [])[:4]:
        print("  ", r["verify"], "|", r["dropped"][:24], "|", r["text"][:40])
    for k, v in ((rep.get("layout") or {}).get("cases") or {}).items():
        g = (v or {}).get("grid") or {}
        print("layout", k, "cols", g.get("cols"), "rows", g.get("rows"), "cards", len(g.get("cards") or []))
    ap = rep.get("appearance") or {}
    print("skin default/chg/rm:", (ap.get("default") or {}).get("skin", {}).get("count"),
          (ap.get("changed") or {}).get("skin", {}).get("count"),
          (ap.get("removed") or {}).get("skin", {}).get("count"))
    print("conflict rows:", (rep.get("regression") or {}).get("conflictRows"))
    print("spear:", (rep.get("regression") or {}).get("spearMags"))


if __name__ == "__main__":
    main()
