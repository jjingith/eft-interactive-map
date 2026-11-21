# -*- coding: utf-8 -*-
"""R19.11 合并修复 · 浏览器验收（1920×919 / 1384×805）。

覆盖：
  A 弹匣容量硬约束（M4A1 有 100 发、AK-74 没有）
  B 属性条实心/斜纹 + 基线/改装/技能三值（数值升高与降低两个方向）
  C 个人属性弹窗（保存 / 校验 / 持久化 / 全局重算 / 零等级）
  D 右侧候选栏（当前槽位在顶部、红斜纹、隐藏不兼容、不可安装、M4 枪托链路）
  E 逐发模拟弹匣（SPEAR 6.8×51 / 其他枪回归 / 口径筛选隐式换枪）
输出 docs/r19.11-merged-audit/{_accept.json,screenshots/*.png}
"""
import base64
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r181_accept import CDP, find_chrome, launch, wait_ready  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "r19.11-merged-audit")
SHOTS = os.path.join(OUT, "screenshots")
os.makedirs(SHOTS, exist_ok=True)

M4A1 = "5447a9cd4bdc2dbd208b4567"
AK74 = "5bf3e03b0db834001d2c4a9c"
SPEAR = "65290f395ae2ae97b80fdf2d"


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
    """在口径浏览页选枪（按卡片名子串）。"""
    for _ in range(5):
        cdp.eval("""(function(){var b=document.querySelector('.gw-mode[data-gwmode="caliber"]');
          if(b)b.click();})()""")
        time.sleep(0.8)
        pos = cdp.eval("""(function(){var cs=document.querySelectorAll('#gw-browse .gw-card');
          for(var i=0;i<cs.length;i++){var s=cs[i].querySelector('span');
            if(s && s.textContent.indexOf(%s)>=0){cs[i].scrollIntoView({block:'center'});
              var r=cs[i].getBoundingClientRect();
              return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2});}}})()"""
                      % json.dumps(needle, ensure_ascii=False))
        if not pos or pos == "null":
            continue
        p = json.loads(pos)
        time.sleep(0.5)
        cdp.click_at(p["x"], p["y"])
        time.sleep(2.2)
        if needle.split(" ")[0] in (cdp.eval(
                "(document.getElementById('gw-current')||{}).textContent") or ""):
            return True
    return False


def click_slot(cdp, sid_suffix):
    pos = cdp.eval("""(function(){
      var cs=[].slice.call(document.querySelectorAll('#gw-tree .gw-part[data-slot]'));
      for(var i=0;i<cs.length;i++){
        if(cs[i].getAttribute('data-slot').split('/').pop()===%s){
          cs[i].scrollIntoView({block:'center'});
          var r=cs[i].getBoundingClientRect();
          return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2});}}
      return null;})()""" % json.dumps(sid_suffix))
    if not pos or pos == "null":
        return False
    p = json.loads(pos)
    time.sleep(0.4)
    cdp.click_at(p["x"], p["y"])
    time.sleep(1.2)
    return True


def click_candidate(cdp, needle=None, index=0):
    """点右栏候选行（可按名称子串过滤），返回 {name, conflict} 或 None。"""
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
    time.sleep(1.4)
    return h


def installed_ids(cdp):
    return json.loads(cdp.eval("""(function(){
      var ids=[];
      [].forEach.call(document.querySelectorAll('#gw-tree .gw-part .gw-part-ic'), function(i){
        var m=(i.getAttribute('src')||'').match(/([0-9a-f]{24})\\.(png|webp|jpg)/);
        if(m) ids.push(m[1]);});
      return JSON.stringify(ids);})()""") or "[]")


BARS = r"""
(function(){
  return JSON.stringify([].slice.call(document.querySelectorAll('#gw-bars .gw-bar')).map(function(r){
    function pct(px){return Math.round(parseFloat(px)*10)/10;}
    var segs=[].slice.call(r.querySelectorAll('.gw-bar-seg')).map(function(s){
      return {cls:s.className.replace('gw-bar-seg ',''), left:pct(s.style.left), width:pct(s.style.width)};});
    var base=r.querySelector('.gw-bar-base');
    var val=r.querySelector('.gw-bar-val');
    return {key:r.dataset.key, label:(r.querySelector('.gw-bar-lab')||{}).textContent,
      segs:segs, baseLeft: base?pct(base.style.left):null,
      text: val?val.textContent:'', trackW: Math.round(r.querySelector('.gw-bar-track').getBoundingClientRect().width),
      valW: Math.round(val?val.getBoundingClientRect().width:0),
      valClipped: val ? (val.scrollWidth > val.clientWidth + 1) : false,
      clippedKeys: val ? [].slice.call(val.children).filter(function(x){
        return x.scrollWidth > x.clientWidth + 1;}).map(function(x){return x.dataset.k||'sep';}) : []};
  }));
})()
"""


def bars(cdp):
    return json.loads(cdp.eval(BARS) or "[]")


CANDS = r"""
(function(){
  var rows=[].slice.call(document.querySelectorAll('#gw-table .tbl-row'));
  var out=rows.filter(function(r){return r.className.indexOf('tbl-empty')<0;}).map(function(r){
    var st=r.querySelector('.tbl-cell[data-key="state"]');
    return {name:(r.querySelector('.gw-row-name b')||{}).textContent||'',
      conflict:r.className.indexOf('tbl-conflict')>=0,
      state:st?st.textContent:'', why:st?st.title:''};});
  return JSON.stringify({total:out.length, bad:out.filter(function(x){return x.conflict;}).length,
    rows:out.slice(0,40)});
})()
"""


def cands(cdp):
    return json.loads(cdp.eval(CANDS) or "{}")


def slot_info(cdp):
    return json.loads(cdp.eval("""(function(){
      var e=document.getElementById('gw-slotinfo');
      if(!e) return JSON.stringify({exists:false});
      var t=e.querySelector('.gw-slotinfo-title'), s=e.querySelector('.gw-slotinfo-sub');
      var cand=document.querySelector('.gw-cands');
      return JSON.stringify({exists:true, title:t?t.textContent:'', sub:s?s.textContent:'',
        kind:e.dataset.kind||'', slot:e.dataset.slot||'',
        topOffset: Math.round(e.getBoundingClientRect().top - cand.getBoundingClientRect().top),
        beforeSearch: e.getBoundingClientRect().top <=
          (document.getElementById('gw-cand-search')||{getBoundingClientRect:function(){return {top:1e9};}}).getBoundingClientRect().top,
        inCenter: !!document.querySelector('.gw-center .lw-focus, .gw-center #gw-focus')});})()""") or "{}")


def toast_text(cdp):
    # gunToast 把提示写进 g.pending → 顶栏 #gw-hint
    return cdp.eval("(document.getElementById('gw-hint')||{}).textContent || ''")


# ------------------------------------------------------------------ A 容量约束
def part_capacity(cdp, rep):
    r = {}
    assert pick_gun(cdp, "柯尔特 M4A1"), "选 M4A1 失败"
    time.sleep(1.2)
    # 点「100 发」容量芯片
    clicked = cdp.eval("""(function(){
      var bs=[].slice.call(document.querySelectorAll('.gw-forge .gw-chips .gw-chip'));
      for(var i=0;i<bs.length;i++){
        if(bs[i].className.indexOf('gw-chip-missing')>=0) continue;   // 只点"该枪真的有"的容量
        if(bs[i].textContent.indexOf('100 发')===0){ bs[i].click(); return true; } }
      return false;})()""")
    r["capChip"] = clicked
    time.sleep(0.6)
    cdp.eval("document.querySelector('.gw-forge-go').click()")
    for _ in range(50):
        time.sleep(0.4)
        if cdp.eval("document.querySelectorAll('.gw-forge-res').length") > 0 or \
           cdp.eval("!!document.querySelector('.gw-forge-nosolution')"):
            break
    r["m4"] = json.loads(cdp.eval("""(function(){
      var rows=[].slice.call(document.querySelectorAll('.gw-forge-res'));
      return JSON.stringify(rows.map(function(x){
        return {text:(x.textContent||'').replace(/\\s+/g,' ').slice(0,140),
                bad:!!x.querySelector('.gw-forge-viol')};}));})()""") or "[]")
    r["m4Note"] = cdp.eval("""(function(){var n=document.querySelector('.gw-forge-nosolution');
      return n?n.textContent:'';})()""")
    r["m4Info"] = cdp.eval("""(function(){var p=document.querySelector('.gw-forge-sec + .gw-forge-note');
      var all=[].slice.call(document.querySelectorAll('.gw-forge-note'));
      for(var i=0;i<all.length;i++){ if(all[i].textContent.indexOf('个有效方案')>=0) return all[i].textContent; }
      return '';})()""")
    shot(cdp, "A1-m4-100-cap.png", clip_of(cdp, ".gw-forge", 4))
    # 应用第一个方案，核对真实弹匣容量
    applied = cdp.eval("""(function(){
      var b=document.querySelector('.gw-forge-res button'); if(!b||b.disabled) return false;
      b.click(); return true;})()""")
    time.sleep(2.0)
    r["m4Applied"] = bool(applied)
    r["m4Mag"] = json.loads(cdp.eval("""(function(){
      var out=[];
      [].forEach.call(document.querySelectorAll('#gw-tree .gw-part[data-slot]'), function(c){
        var s=c.getAttribute('data-slot')||'';
        if(!/magazine/.test(s)) return;
        var nm=c.getAttribute('data-item')||'';
        var img=c.querySelector('.gw-part-ic'); var src=img?(img.getAttribute('src')||''):'';
        var m=src.match(/([0-9a-f]{24})\\./);
        out.push({slot:s, item:nm, id:m?m[1]:null});});
      return JSON.stringify(out);})()""") or "[]")
    r["m4Bars"] = bars(cdp)

    # AK-74：没有 100 发弹匣 → 换枪后 100 约束被继承 → 必须明确无解
    assert pick_gun(cdp, "AK-74 5.45x39"), "选 AK-74 失败"
    time.sleep(1.2)
    r["akMissingChip"] = cdp.eval("""(function(){
      var m=document.querySelector('.gw-forge .gw-chip-missing');
      return m?{text:m.textContent, title:m.title}:null;})()""")
    time.sleep(0.3)
    cdp.eval("document.querySelector('.gw-forge-go').click()")
    for _ in range(50):
        time.sleep(0.4)
        if cdp.eval("!!document.querySelector('.gw-forge-nosolution')"):
            break
    r["akNote"] = cdp.eval("""(function(){var n=document.querySelector('.gw-forge-nosolution');
      return n?n.textContent:'';})()""")
    r["akRows"] = cdp.eval("document.querySelectorAll('.gw-forge-res').length")
    r["akInfo"] = cdp.eval("""(function(){var all=[].slice.call(document.querySelectorAll('.gw-forge-note'));
      for(var i=0;i<all.length;i++){ if(all[i].textContent.indexOf('个有效方案')>=0) return all[i].textContent; }
      return '';})()""")
    shot(cdp, "A2-ak74-100-nosolution.png", clip_of(cdp, ".gw-forge", 4))
    rep["capacity"] = r
    return r


# ------------------------------------------------------------------ B 属性条
def part_bars(cdp, rep):
    r = {}
    assert pick_gun(cdp, "柯尔特 M4A1"), "选 M4A1 失败"
    time.sleep(1.4)
    r["default"] = bars(cdp)
    shot(cdp, "B0-bars-default.png", clip_of(cdp, "#gw-bars", 4))

    # 用「高人机工效」方案（人机 > 基线）→ 斜纹应在基线右侧
    cdp.eval("document.querySelector('.gw-forge-go').click()")
    for _ in range(40):
        time.sleep(0.4)
        if cdp.eval("document.querySelectorAll('.gw-forge-res').length") > 0:
            break
    ergo_rows = json.loads(cdp.eval("""(function(){
      var rows=[].slice.call(document.querySelectorAll('.gw-forge-res'));
      return JSON.stringify(rows.map(function(x,i){
        var t=(x.textContent||'');var m=t.match(/人机\\s*([\\d.]+)/);
        return {i:i, ergo:m?parseFloat(m[1]):null, name:(x.querySelector('b')||{}).textContent};}));})()""") or "[]")
    r["buildErgos"] = ergo_rows
    hi = max([x for x in ergo_rows if x["ergo"] is not None], key=lambda x: x["ergo"], default=None)
    lo = min([x for x in ergo_rows if x["ergo"] is not None], key=lambda x: x["ergo"], default=None)
    def apply_row(idx):
        return cdp.eval("""(function(){
          var rows=[].slice.call(document.querySelectorAll('.gw-forge-res'));
          var b=rows[%d].querySelector('button'); if(!b||b.disabled) return false; b.click(); return true;})()""" % idx)
    if hi:
        apply_row(hi["i"]); time.sleep(1.8)
        r["high"] = {"build": hi, "bars": bars(cdp)}
        shot(cdp, "B1-bars-ergo-up.png", clip_of(cdp, "#gw-bars", 4))
    if lo and hi and lo["i"] != hi["i"]:
        apply_row(lo["i"]); time.sleep(1.8)
        r["low"] = {"build": lo, "bars": bars(cdp)}
        shot(cdp, "B2-bars-ergo-down.png", clip_of(cdp, "#gw-bars", 4))
    # 恢复默认 → 无差异
    cdp.eval("document.getElementById('gw-default').click()")
    time.sleep(1.8)
    r["restored"] = bars(cdp)
    shot(cdp, "B3-bars-restored.png", clip_of(cdp, "#gw-bars", 4))
    rep["bars"] = r
    return r


# ------------------------------------------------------------------ C 个人属性
def part_profile(cdp, rep):
    r = {}
    assert pick_gun(cdp, "柯尔特 M4A1"), "选 M4A1 失败"
    time.sleep(1.2)
    r["before"] = {"bars": bars(cdp),
                   "stats": cdp.eval("(document.getElementById('gw-stats')||{}).textContent.slice(0,120)")}
    cdp.eval("document.getElementById('btn-profile').click()")
    time.sleep(0.7)
    r["modalOpen"] = cdp.eval("!document.getElementById('gw-profile').hidden")
    shot(cdp, "C1-profile-modal.png")
    # 非法值 → 报错且不保存
    cdp.eval("""(function(){
      document.getElementById('gw-prof-strength').value = '99';
      document.getElementById('gw-prof-save').click();})()""")
    time.sleep(0.6)
    r["invalid"] = cdp.eval("""(function(){var e=document.getElementById('gw-prof-err');
      return {shown:!e.hidden, text:e.textContent, stored:localStorage.getItem('eftmap.profile.v1')};})()""")
    shot(cdp, "C2-profile-invalid.png")
    # 合法值 → 保存
    cdp.eval("""(function(){
      document.getElementById('gw-prof-strength').value = '40';
      document.getElementById('gw-prof-endurance').value = '25';
      document.getElementById('gw-prof-skill-default').value = '30';
      var inp=document.querySelector('#gw-prof-skillrows input[data-skill="pistol"]');
      if(inp){ inp.value='45'; }
      document.getElementById('gw-prof-save').click();})()""")
    time.sleep(1.6)
    r["afterSave"] = {
        "hidden": cdp.eval("document.getElementById('gw-profile').hidden"),
        "stored": json.loads(cdp.eval("localStorage.getItem('eftmap.profile.v1')") or "null"),
        "bars": bars(cdp),
        "toast": toast_text(cdp),
        "stats": cdp.eval("(document.getElementById('gw-stats')||{}).textContent.slice(0,120)"),
    }
    shot(cdp, "C3-profile-applied-bars.png", clip_of(cdp, "#gw-bars", 4))
    # 手枪覆盖：换到手枪，技能等级应取 45（覆盖默认 30）
    assert pick_gun(cdp, "Glock 17 9x19"), "选 Glock 17 失败"
    time.sleep(1.4)
    r["pistol"] = {
        "bars": bars(cdp),
        "skillNote": cdp.eval("""(function(){var n=document.querySelector('.gw-bar-skillnote');
          return n?n.textContent:'';})()"""),
    }
    shot(cdp, "C4-profile-pistol-override.png", clip_of(cdp, "#gw-bars", 4))
    # 切页再回来 + 刷新
    cdp.eval("document.querySelector('[data-view=\"map\"]').click()"); time.sleep(1.0)
    cdp.eval("document.querySelector('[data-view=\"gun\"]').click()"); time.sleep(1.6)
    r["afterPageSwitch"] = {"skillNote": cdp.eval("""(function(){var n=document.querySelector('.gw-bar-skillnote');
      return n?n.textContent:'';})()""")}
    cdp.call("Page.navigate", url="http://127.0.0.1:8787/index.html")
    wait_ready(cdp, want_url="index.html")
    time.sleep(2.5)
    cdp.eval("document.querySelector('[data-view=\"gun\"]').click()")
    time.sleep(1.5)
    r["afterReload"] = {
        "stored": json.loads(cdp.eval("localStorage.getItem('eftmap.profile.v1')") or "null"),
        "modalValues": json.loads(cdp.eval("""(function(){
          document.getElementById('btn-profile').click();
          var v={strength:document.getElementById('gw-prof-strength').value,
                 endurance:document.getElementById('gw-prof-endurance').value,
                 skill:document.getElementById('gw-prof-skill-default').value};
          document.getElementById('gw-prof-cancel').click();
          return JSON.stringify(v);})()""") or "{}"),
    }
    # 零等级 → 技能 == 改装
    cdp.eval("""(function(){
      document.getElementById('btn-profile').click();
      document.getElementById('gw-prof-skill-default').value='0';
      var inp=document.querySelector('#gw-prof-skillrows input[data-skill="pistol"]');
      if(inp){ inp.value=''; }
      document.getElementById('gw-prof-save').click();})()""")
    time.sleep(1.4)
    r["zeroSkill"] = {"bars": bars(cdp)}
    shot(cdp, "C5-profile-zero-skill.png", clip_of(cdp, "#gw-bars", 4))
    rep["profile"] = r
    return r


# ------------------------------------------------------------------ D 右栏
def part_panel(cdp, rep):
    r = {}
    assert pick_gun(cdp, "柯尔特 M4A1"), "选 M4A1 失败"
    time.sleep(1.4)
    cdp.eval("document.getElementById('gw-default').click()")
    time.sleep(1.4)
    r["initial"] = slot_info(cdp)
    # 枪托槽（默认装配：缓冲管 + M4SS 枪托）
    assert click_slot(cdp, "mod_stock"), "找不到枪托槽"
    time.sleep(0.8)
    r["stock"] = {"slot": slot_info(cdp), "cands": cands(cdp)}
    shot(cdp, "D1-stock-candidates.png", clip_of(cdp, ".gw-cands", 4))

    # 先试：装着缓冲管时装「Hera 一体化枪托」（握把槽）→ 必须被拒绝（反向互斥）
    assert click_slot(cdp, "mod_pistol_grip"), "找不到握把槽"
    time.sleep(0.8)
    hera = click_candidate(cdp, "Hera Arms CQR AR-15 一体化枪托")
    time.sleep(1.5)
    r["heraBlockedByTube"] = {"picked": hera, "toast": toast_text(cdp), "slot": slot_info(cdp)}
    shot(cdp, "D2a-integrated-blocked-by-tube.png", clip_of(cdp, ".gw-cands", 4))
    # 卸下枪托（右键）→ 再装一体式枪托 → 缓冲管类候选变互斥
    cdp.eval("""(function(){var cs=[].slice.call(document.querySelectorAll('#gw-tree .gw-part[data-slot]'));
      for(var i=0;i<cs.length;i++){ if(cs[i].getAttribute('data-slot')==='mod_stock'){
        cs[i].dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,cancelable:true})); return;}}})()""")
    time.sleep(1.5)
    assert click_slot(cdp, "mod_pistol_grip"), "找不到握把槽"
    time.sleep(0.6)
    hera = click_candidate(cdp, "Hera Arms CQR AR-15 一体化枪托")
    time.sleep(1.6)
    r["heraGrip"] = {"picked": hera, "slot": slot_info(cdp), "toast": toast_text(cdp)}
    assert click_slot(cdp, "mod_stock"), "装了一体式枪托后找不到枪托槽"
    time.sleep(0.9)
    conflict_state = {"slot": slot_info(cdp), "cands": cands(cdp)}
    r["stockWithIntegratedGrip"] = conflict_state
    shot(cdp, "D2-stock-conflict-stripes.png", clip_of(cdp, ".gw-cands", 4))

    # 斜纹样式（覆盖整条 + 不拦截鼠标）
    stripe = cdp.eval("""(function(){
      var bad=document.querySelector('#gw-table .tbl-row.tbl-conflict');
      if(!bad) return null;
      var cs=getComputedStyle(bad,'::after');
      var rect=bad.getBoundingClientRect();
      var cell=bad.querySelector('.tbl-cell');
      return JSON.stringify({bgImage:cs.backgroundImage, pointer:cs.pointerEvents, zIndex:cs.zIndex,
        coverW:Math.round(rect.width), coverH:Math.round(rect.height),
        rowW:Math.round(bad.getBoundingClientRect().width),
        textColor:cell?getComputedStyle(cell).color:null,
        why:(bad.querySelector('.gw-row-why')||{}).textContent||'',
        name:(bad.querySelector('.gw-row-name b')||{}).textContent||''});})()""")
    r["stripeStyle"] = json.loads(stripe) if stripe and stripe != "null" else None

    # 悬停：斜纹仍在；点击：不得装上
    if r["stripeStyle"]:
        hover = json.loads(cdp.eval("""(function(){
          var bad=document.querySelector('#gw-table .tbl-row.tbl-conflict');
          var r=bad.getBoundingClientRect();
          return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2,
            name:(bad.querySelector('.gw-row-name b')||{}).textContent||''});})()"""))
        cdp.mouse(hover["x"], hover["y"])
        time.sleep(0.35)
        r["stripeOnHover"] = json.loads(cdp.eval("""(function(){
          var bad=document.querySelector('#gw-table .tbl-row.tbl-conflict');
          if(!bad) return null; var cs=getComputedStyle(bad,'::after');
          return JSON.stringify({bgImage:cs.backgroundImage,
            hoverBg:getComputedStyle(bad).backgroundColor});})()""") or "null")
        shot(cdp, "D3-conflict-hover.png", clip_of(cdp, ".gw-cands", 4))
        before_ids = installed_ids(cdp)
        before_slot = cdp.eval("(document.querySelector('#gw-slotinfo')||{}).textContent")
        clicked = click_candidate(cdp, hover["name"])
        after_ids = installed_ids(cdp)
        r["blockedInstall"] = {
            "candidate": clicked, "unchanged": before_ids == after_ids,
            "toast": toast_text(cdp),
            "installedHas": json.loads(cdp.eval("""(function(){
              var n=%s, out=0;
              [].forEach.call(document.querySelectorAll('#gw-tree .gw-part[data-slot]'), function(c){
                if((c.getAttribute('data-item')||'')===n) out++;});
              return JSON.stringify(out);})()""" % json.dumps(hover["name"])))}
        shot(cdp, "D4-conflict-click-blocked.png", clip_of(cdp, ".gw-cands", 4))

        # 隐藏不兼容（勾选 → 消失；搜索仍生效；取消 → 恢复）
        before = cands(cdp)
        cdp.eval("""(function(){var c=document.getElementById('gw-hidebad');
          c.checked=true; c.dispatchEvent(new Event('change',{bubbles:true}));})()""")
        time.sleep(0.9)
        after = cands(cdp)
        r["hide"] = {"before": {"total": before["total"], "bad": before["bad"]},
                     "after": {"total": after["total"], "bad": after["bad"]},
                     "count": cdp.eval("(document.getElementById('gw-hidebad-count')||{}).textContent")}
        shot(cdp, "D5-hide-incompat-on.png", clip_of(cdp, ".gw-cands", 4))
        cdp.eval("""(function(){var s=document.getElementById('gw-cand-search');
          s.value='缓冲管'; s.dispatchEvent(new Event('input',{bubbles:true}));})()""")
        time.sleep(0.7)
        r["hide"]["withSearch"] = {"cands": cands(cdp),
                                   "query": cdp.eval("(document.getElementById('gw-cand-search')||{}).value")}
        # 全部被过滤 → 空结果提示（不是"加载失败"）
        cdp.eval("""(function(){var s=document.getElementById('gw-cand-search');
          s.value='UBR GEN2'; s.dispatchEvent(new Event('input',{bubbles:true}));})()""")
        time.sleep(0.7)
        r["hide"]["emptyState"] = {
            "rows": (cands(cdp) or {}).get("total"),
            "text": cdp.eval("""(function(){var e=document.querySelector('#gw-table .tbl-row.tbl-empty');
              return e?e.textContent.trim():'';})()""")}
        shot(cdp, "D7a-hide-empty-state.png", clip_of(cdp, ".gw-cands", 4))
        shot(cdp, "D6-hide-with-search.png", clip_of(cdp, ".gw-cands", 4))
        cdp.eval("""(function(){var s=document.getElementById('gw-cand-search');
          s.value=''; s.dispatchEvent(new Event('input',{bubbles:true}));
          var c=document.getElementById('gw-hidebad'); c.checked=false;
          c.dispatchEvent(new Event('change',{bubbles:true}));})()""")
        time.sleep(0.9)
        un = cands(cdp)
        r["unhide"] = {"total": un["total"], "bad": un["bad"]}
        shot(cdp, "D7-hide-incompat-off.png", clip_of(cdp, ".gw-cands", 4))

    # 其它槽位的"当前槽位"信息
    for sid, key in (("mod_handguard", "handguard"), ("mod_scope", "scope"),
                     ("mod_magazine", "magazine")):
        if click_slot(cdp, sid):
            time.sleep(0.7)
            r[key] = {"slot": slot_info(cdp),
                      "cands": {k: cands(cdp).get(k) for k in ("total", "bad")}}
    # 子弹槽 → 弹药上下文
    if cdp.eval("""(function(){var a=document.querySelector('.gw-part-ammo');
      if(!a) return false; a.click(); return true;})()"""):
        time.sleep(1.0)
        r["ammo"] = {"slot": slot_info(cdp),
                     "cands": {k: (json.loads(cdp.eval(CANDS) or "{}")).get(k)
                               for k in ("total", "bad")}}
        shot(cdp, "D8-ammo-slotinfo.png", clip_of(cdp, ".gw-cands", 4))
    # 前握把（换一把有前握把槽位的枪）
    assert pick_gun(cdp, "HK 416A5"), "选 416A5 失败"
    time.sleep(1.4)
    if click_slot(cdp, "mod_foregrip"):
        time.sleep(0.7)
        r["foregrip"] = {"slot": slot_info(cdp),
                         "cands": {k: cands(cdp).get(k) for k in ("total", "bad")}}
    rep["panel"] = r
    return r


# ------------------------------------------------------------------ D2 M4 枪托链路
def part_m4_stock(cdp, rep):
    r = {}
    assert pick_gun(cdp, "柯尔特 M4A1"), "选 M4A1 失败"
    time.sleep(1.4)
    cdp.eval("document.getElementById('gw-default').click()")   # 默认装配（含缓冲管）
    time.sleep(1.6)
    assert click_slot(cdp, "mod_stock"), "找不到枪托槽"
    time.sleep(0.8)
    r["tubeSlot"] = {"slot": slot_info(cdp), "cands": cands(cdp)}
    # 子槽（缓冲管上的枪托）
    child = cdp.eval("""(function(){
      var cs=[].slice.call(document.querySelectorAll('#gw-tree .gw-part[data-slot]'));
      return JSON.stringify(cs.map(function(c){return c.getAttribute('data-slot');})
        .filter(function(s){return /mod_stock\\//.test(s);}));})()""")
    r["childSlots"] = json.loads(child or "[]")
    if r["childSlots"]:
        cdp.eval("""(function(){
          var cs=[].slice.call(document.querySelectorAll('#gw-tree .gw-part[data-slot]'));
          for(var i=0;i<cs.length;i++){ if(/mod_stock\\//.test(cs[i].getAttribute('data-slot'))){
            var r=cs[i].getBoundingClientRect(); window.__childXY={x:r.x+r.width/2,y:r.y+r.height/2}; return; }}})()""")
        xy = cdp.eval("window.__childXY ? JSON.stringify(window.__childXY) : null")
        if xy and xy != "null":
            p = json.loads(xy)
            cdp.click_at(p["x"], p["y"])
            time.sleep(1.0)
            r["childCands"] = {"slot": slot_info(cdp), "cands": {k: cands(cdp).get(k) for k in ("total", "bad")}}
            shot(cdp, "D7-m4-child-stock.png", clip_of(cdp, ".gw-cands", 4))
    # 装一体式枪托（UBR GEN2）
    assert click_slot(cdp, "mod_stock"), "找不到枪托槽"
    time.sleep(0.8)
    picked = click_candidate(cdp, "UBR GEN2")
    time.sleep(1.4)
    r["integrated"] = {
        "picked": picked,
        "installed": installed_ids(cdp),
        "childSlotsAfter": json.loads(cdp.eval("""(function(){
          var cs=[].slice.call(document.querySelectorAll('#gw-tree .gw-part[data-slot]'));
          return JSON.stringify(cs.map(function(c){return c.getAttribute('data-slot');})
            .filter(function(s){return /mod_stock\\//.test(s);}));})()""") or "[]"),
        "stockItems": json.loads(cdp.eval("""(function(){
          var out=[];
          [].forEach.call(document.querySelectorAll('#gw-tree .gw-part[data-slot]'), function(c){
            var s=c.getAttribute('data-slot')||'';
            if(!/stock/.test(s)) return;
            out.push({slot:s, item:c.getAttribute('data-item')||''});});
          return JSON.stringify(out);})()""") or "[]"),
        "toast": toast_text(cdp),
    }
    shot(cdp, "D8-m4-integrated-stock.png", clip_of(cdp, "#gw-tree", 6))
    # 再点枪托槽：候选中不应再出现"需要缓冲管才能装"的子槽（只剩根槽候选）
    assert click_slot(cdp, "mod_stock"), "找不到枪托槽"
    time.sleep(0.9)
    r["afterIntegrated"] = {"slot": slot_info(cdp), "cands": cands(cdp)}
    shot(cdp, "D9-m4-integrated-candidates.png", clip_of(cdp, ".gw-cands", 4))
    rep["m4stock"] = r
    return r


# ------------------------------------------------------------------ E 模拟器弹匣
SIM_PROBE = r"""
(function(){
  var g=document.querySelector("[data-sim='gun-pick']");
  var m=document.querySelector("[data-sim='mag-pick']");
  var cap=document.querySelector("[data-sim='mag-cap']");
  var meta=document.querySelector('.am-sim-gunmeta');
  return JSON.stringify({
    gun: g?g.value:null,
    gunText: (g&&g.selectedIndex>=0)?g.options[g.selectedIndex].textContent:null,
    mags: m?[].slice.call(m.options).map(function(o){return {v:o.value,t:o.textContent};}):null,
    magDisabled: m?m.disabled:null,
    cap: cap?cap.textContent:null,
    meta: meta?meta.textContent:null});
})()
"""


def part_sim(cdp, rep):
    r = {}
    cdp.eval("document.querySelector('[data-view=\"ammo\"]').click()")
    time.sleep(1.4)
    cdp.eval("""(function(){var t=[].slice.call(document.querySelectorAll('.am-tab'));
      for(var i=0;i<t.length;i++){if(t[i].dataset.tab==='sim'){t[i].click();return;}}})()""")
    time.sleep(2.5)
    r["initial"] = json.loads(cdp.eval(SIM_PROBE) or "{}")
    # 直接选 SPEAR
    sel = cdp.eval("""(function(){
      var s=document.querySelector("[data-sim='gun-pick']");
      var o=[].slice.call(s.options).filter(function(x){return /MCX SPEAR/.test(x.textContent);})[0];
      if(!o) return null; s.value=o.value; s.dispatchEvent(new Event('change',{bubbles:true}));
      return o.value;})()""")
    time.sleep(2.0)
    r["spearSelected"] = sel
    r["spear"] = json.loads(cdp.eval(SIM_PROBE) or "{}")
    shot(cdp, "E1-sim-spear-mags.png")
    # 换一个弹匣 → 容量刷新
    changed = cdp.eval("""(function(){
      var m=document.querySelector("[data-sim='mag-pick']");
      if(!m||m.options.length<2) return null;
      var o=m.options[1]; m.value=o.value; m.dispatchEvent(new Event('change',{bubbles:true}));
      return o.textContent;})()""")
    time.sleep(1.2)
    r["magChanged"] = {"picked": changed, "probe": json.loads(cdp.eval(SIM_PROBE) or "{}")}
    shot(cdp, "E2-sim-spear-mag-capacity.png")
    # 回归：M4 / MCX .300 / 7.62 枪
    for needle, key in (("柯尔特 M4A1", "m4"), ("MCX .300", "mcx300"), ("Model 700", "m700")):
        got = cdp.eval("""(function(){
          var s=document.querySelector("[data-sim='gun-pick']");
          var o=[].slice.call(s.options).filter(function(x){return x.textContent.indexOf(%s)>=0;})[0];
          if(!o) return 'no-option';
          s.value=o.value; s.dispatchEvent(new Event('change',{bubbles:true}));
          return o.textContent;})()""" % json.dumps(needle, ensure_ascii=False))
        time.sleep(1.6)
        r[key] = {"picked": got, "probe": json.loads(cdp.eval(SIM_PROBE) or "{}")}
    # 口径筛选隐式换枪（旧 bug：弹匣列表停在上一把枪）
    cal = cdp.eval("""(function(){
      var c=document.querySelector("[data-sim='cal-filter']");
      if(!c) return 'no-cal';
      var o=[].slice.call(c.options).filter(function(x){return /6\\.8/.test(x.textContent);})[0];
      if(!o) return 'no-68';
      c.value=o.value; c.dispatchEvent(new Event('change',{bubbles:true})); return o.textContent;})()""")
    time.sleep(1.8)
    r["calFilter"] = {"picked": cal, "probe": json.loads(cdp.eval(SIM_PROBE) or "{}")}
    shot(cdp, "E3-sim-cal-filter.png")
    rep["sim"] = r
    return r


def main():
    rep = {"viewport": {}, "console": []}
    proc, ws = launch(find_chrome(), 9453, 1920, 919,
                      os.path.join(os.environ.get("TEMP", "."), "r1911a-%d" % os.getpid()))
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
        cdp.eval("try{localStorage.removeItem('eftmap.profile.v1')}catch(e){}")
        rep["build"] = cdp.eval("(document.getElementById('build-rev')||{}).textContent")
        cdp.eval("document.querySelector('[data-view=\"gun\"]').click()")
        time.sleep(2.0)

        part_capacity(cdp, rep)
        part_bars(cdp, rep)
        part_profile(cdp, rep)
        part_panel(cdp, rep)
        part_m4_stock(cdp, rep)
        part_sim(cdp, rep)

        # 1384 视口复验（关键项）
        cdp.call("Emulation.setDeviceMetricsOverride", width=1384, height=805,
                 deviceScaleFactor=1, mobile=False)
        time.sleep(1.0)
        cdp.eval("document.querySelector('[data-view=\"gun\"]').click()")
        time.sleep(1.6)
        assert pick_gun(cdp, "柯尔特 M4A1"), "1384 选 M4A1 失败"
        time.sleep(1.2)
        assert click_slot(cdp, "mod_stock"), "1384 枪托槽"
        time.sleep(0.8)
        rep["viewport"]["1384"] = {
            "slot": slot_info(cdp),
            "cands": {k: cands(cdp).get(k) for k in ("total", "bad")},
            "bars": bars(cdp),
            "sw": cdp.eval("document.documentElement.scrollWidth"),
            "w": cdp.eval("innerWidth"),
        }
        shot(cdp, "Z-1384-panel.png")
        cdp.eval("document.getElementById('btn-profile').click()"); time.sleep(0.6)
        shot(cdp, "Z-1384-profile.png")
        cdp.eval("document.getElementById('gw-prof-cancel').click()")
        cdp.call("Emulation.setDeviceMetricsOverride", width=1920, height=919,
                 deviceScaleFactor=1, mobile=False)
        time.sleep(0.8)
        rep["viewport"]["1920"] = {"sw": cdp.eval("document.documentElement.scrollWidth"),
                                   "w": cdp.eval("innerWidth")}
        rep["console"] = (getattr(cdp, "console", None) or [])[:10]
        rep["external"] = [r for r in (getattr(cdp, "requests", None) or [])
                           if "127.0.0.1" not in r["url"]][:5]
    finally:
        proc.terminate()

    with open(os.path.join(OUT, "_accept.json"), "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    print(json.dumps({
        "build": rep.get("build"),
        "cap": {"m4rows": len(rep.get("capacity", {}).get("m4", [])),
                "m4bad": [r for r in rep.get("capacity", {}).get("m4", []) if r["bad"]][:1],
                "m4mag": rep.get("capacity", {}).get("m4Mag"),
                "akNote": rep.get("capacity", {}).get("akNote"),
                "akRows": rep.get("capacity", {}).get("akRows")},
        "barsHigh": rep.get("bars", {}).get("high", {}).get("bars"),
        "barsLow": rep.get("bars", {}).get("low", {}).get("bars"),
        "profile": {"modal": rep.get("profile", {}).get("modalOpen"),
                    "invalid": rep.get("profile", {}).get("invalid"),
                    "stored": rep.get("profile", {}).get("afterSave", {}).get("stored"),
                    "reload": rep.get("profile", {}).get("afterReload")},
        "panel": {"stock": rep.get("panel", {}).get("stock", {}).get("slot"),
                  "hide": rep.get("panel", {}).get("hide"),
                  "stripe": rep.get("panel", {}).get("stripeStyle"),
                  "blocked": rep.get("panel", {}).get("blockedInstall")},
        "m4": {k: rep.get("m4stock", {}).get(k) for k in ("childSlots", "integrated")},
        "sim": {"spear": rep.get("sim", {}).get("spear"),
                "m4": rep.get("sim", {}).get("m4", {}).get("probe"),
                "cal": rep.get("sim", {}).get("calFilter")},
        "console": rep["console"], "ext": len(rep.get("external") or []),
    }, ensure_ascii=False, indent=1)[:6000])


if __name__ == "__main__":
    main()
