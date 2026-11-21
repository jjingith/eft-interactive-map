# -*- coding: utf-8 -*-
"""R19.15.1 全枪械真实 DOM 扫描：逐枪选枪 + 恢复官方默认装配，抓画布每个槽位卡的
行列坐标、真实槽位树规模、行/列数、连接线与外观层状态。

用法：
  python tools/r1921_scan_all.py --out docs/r19.15.1-layout-audit/dom-all-after.json --port 9581

注意：选枪走真实 UI（搜索框 + 卡片点击），不调用页面内部函数，保证与应用实际行为一致。
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
URL = "http://127.0.0.1:8787/index.html"

DOM_JS = r"""
(function(){
  var tree=document.getElementById('gw-tree');
  if(!tree) return JSON.stringify({ok:false,why:'no #gw-tree'});
  var cards=[].slice.call(tree.querySelectorAll('.gw-part[data-slot]'));
  var slots=cards.map(function(c){
    var r=c.getBoundingClientRect();
    return {slot:c.getAttribute('data-slot'),
            row:+(c.getAttribute('data-row')||0),
            col:+(c.getAttribute('data-col')||0),
            item:c.getAttribute('data-item')||'',
            empty:c.className.indexOf('gw-part-empty')>=0,
            w:Math.round(r.width),h:Math.round(r.height)};
  });
  var rs=getComputedStyle(tree).gridTemplateRows.split(' ').map(parseFloat);
  var gs=tree.querySelector('.gw-gun, [data-row][data-col]');
  return JSON.stringify({
    ok:true,
    gunName:(document.getElementById('gw-current')||{}).textContent||'',
    rows:rs.length, rowHeights:rs,
    cols:getComputedStyle(tree).gridTemplateColumns.split(' ').length,
    rowsVar:tree.style.getPropertyValue('--gw-rows'),
    topPad:+(tree.getAttribute('data-top-pad')||0),
    treeSlots:+(tree.getAttribute('data-tree-slots')||0),
    placedCells:+(tree.getAttribute('data-placed-cells')||0),
    svgCount:tree.querySelectorAll('svg').length,
    connectorPaths:tree.querySelectorAll('.gw-canvas-links path').length,
    skinCount:document.querySelectorAll('.gw-skin').length,
    skinTagCount:document.querySelectorAll('.gw-skin-tag').length,
    viewport:{w:window.innerWidth,h:window.innerHeight},
    installed:(function(){ try{
      var s=JSON.parse(localStorage.getItem('eftmap.gun')||'null');
      return (s&&s.installed)?s.installed:null;
    }catch(e){ return null; } })(),
    slots:slots
  });
})()
"""

SELECT_JS = r"""
(function(id){
  var inp=document.getElementById('gw-search');
  var card=document.querySelector('#gw-browse .gw-card[data-gun="'+id+'"]');
  if(!card && inp){
    inp.value=''; inp.dispatchEvent(new Event('input',{bubbles:true}));
  }
  return card? 'direct':'needsearch';
})(%s)
"""

SEARCH_JS = r"""
(function(id, name){
  var inp=document.getElementById('gw-search');
  if(!inp) return 'noinput';
  inp.value=name;
  inp.dispatchEvent(new Event('input',{bubbles:true}));
  return 'ok';
})(%s, %s)
"""

CLICK_JS = r"""
(function(id){
  var card=document.querySelector('#gw-browse .gw-card[data-gun="'+id+'"]');
  if(!card) return 'missing';
  card.scrollIntoView({block:'center'});
  var r=card.getBoundingClientRect();
  if(!r.width || !r.height) return 'zero-rect';
  var hit=document.elementFromPoint(r.x+r.width/2, r.y+r.height/2);
  if(!hit || !card.contains(hit)) return 'not-hittable';
  return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2});
})(%s)
"""

OPEN_BROWSE_JS = """
(function(){var b=document.querySelector('.gw-mode[data-gwmode="caliber"]'); if(b) b.click(); return !!b;})()
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--port", type=int, default=9581)
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=919)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--url", default="index.html", help="要扫描的页面（相对项目根）")
    args = ap.parse_args()

    guns = json.load(open(os.path.join(ROOT, "data", "gunslots.json"), encoding="utf-8"))["guns"]
    items = json.load(open(os.path.join(ROOT, "data", "items.json"), encoding="utf-8"))["items"]

    prof = os.path.join(os.environ.get("TEMP", "."), "r1921scan_%d" % args.port)
    proc, ws = launch(find_chrome(), args.port, args.width, args.height, prof)
    out = {"generatedAt": time.strftime("%Y-%m-%dT%H:%M:%S"), "guns": {}, "fail": []}
    try:
        cdp = CDP(ws)
        for m in ("Page.enable", "Runtime.enable", "Log.enable", "Network.enable"):
            cdp.call(m)
        cdp.call("Network.setCacheDisabled", cacheDisabled=True)
        cdp.call("Emulation.setDeviceMetricsOverride", width=args.width, height=args.height,
                 deviceScaleFactor=1, mobile=False)
        cdp.call("Page.navigate", url="http://127.0.0.1:8787/" + args.url)
        wait_ready(cdp, want_url=args.url.split("/")[-1].split("?")[0])
        time.sleep(2.6)
        cdp.eval("document.querySelector('[data-view=\"gun\"]').click()")
        time.sleep(2.0)
        # 默认按口径分组，卡片才是全量
        cdp.eval("""(function(){var b=document.querySelector('.gw-mode[data-gwmode="caliber"]');
          if(b)b.click();})()""")
        time.sleep(1.0)

        ids = list(guns.keys())
        if args.limit:
            ids = ids[: args.limit]
        for n, gid in enumerate(ids, 1):
            name = (items.get(gid) or {}).get("n") or ""
            # 每次选枪前都切回「口径」浏览面板（选枪后工作台会切到建造模式，列表被隐藏）
            cdp.eval(OPEN_BROWSE_JS)
            time.sleep(0.45)
            st = cdp.eval(SELECT_JS % json.dumps(gid))
            if st == "needsearch":
                cdp.eval(SEARCH_JS % (json.dumps(gid), json.dumps(name, ensure_ascii=False)))
                time.sleep(0.45)
            pos = cdp.eval(CLICK_JS % json.dumps(gid))
            if not pos or pos == "missing":
                # 搜索失败：用名称前 8 字再试一次
                cdp.eval(SEARCH_JS % (json.dumps(gid), json.dumps(name[:8], ensure_ascii=False)))
                time.sleep(0.5)
                pos = cdp.eval(CLICK_JS % json.dumps(gid))
            if not pos or pos == "missing":
                out["fail"].append({"gun": name, "id": gid, "why": "card not found"})
                continue
            p = json.loads(pos)
            cdp.click_at(p["x"], p["y"])
            time.sleep(1.15)
            cdp.eval("document.getElementById('gw-default') && document.getElementById('gw-default').click()")
            time.sleep(0.85)
            m = json.loads(cdp.eval(DOM_JS) or "{}")
            m["id"] = gid
            m["name"] = name
            if gid not in (m.get("gunName") or ""):
                got = m.get("gunName") or ""
                if not (name[:6] and name[:6] in got):
                    out["fail"].append({"gun": name, "id": gid, "why": "select mismatch: " + got})
                    continue
            out["guns"][gid] = m
            if n % 20 == 0:
                print("  scanned", n, "/", len(ids), flush=True)
    finally:
        try:
            proc.terminate()
        except Exception:
            pass

    with open(os.path.join(ROOT, args.out), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    ok = len(out["guns"])
    print("scanned ok", ok, "fail", len(out["fail"]), "->", args.out)


if __name__ == "__main__":
    main()
