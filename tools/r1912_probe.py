# -*- coding: utf-8 -*-
"""R19.12 快速探针：固定 6×9 画布的实际渲染 + 截图。

用法: python tools/r1912_probe.py [--gun 名称子串]
输出: docs/r19.12-canvas-audit/_probe.json + screenshots/*.png
"""
import base64, json, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r181_accept import CDP, find_chrome, launch, wait_ready

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "r19.12-canvas-audit")
SHOTS = os.path.join(OUT, "screenshots")
os.makedirs(SHOTS, exist_ok=True)

GRID_JS = """(function(){
  var t=document.getElementById('gw-tree');
  if(!t) return null;
  var cs=getComputedStyle(t);
  var body=t.querySelector('.gw-cell-body');
  var cards=[].slice.call(t.querySelectorAll('.gw-part[data-row]')).map(function(c){
    var r=c.getBoundingClientRect();
    return {slot:c.getAttribute('data-slot'), row:+c.getAttribute('data-row'),
      col:+c.getAttribute('data-col'), parent:c.getAttribute('data-parent')||'',
      item:c.getAttribute('data-item')||'', lane:c.getAttribute('data-lane')||'',
      x:Math.round(r.x), y:Math.round(r.y), w:Math.round(r.width), h:Math.round(r.height)};});
  var br=body?body.getBoundingClientRect():null;
  return JSON.stringify({
    cols: cs.gridTemplateColumns.split(' ').length,
    rows: cs.gridTemplateRows === 'none' ? null : cs.gridTemplateRows.split(' ').length,
    tplCols: cs.gridTemplateColumns, tplRows: cs.gridTemplateRows,
    gap: cs.gap, width: Math.round(t.getBoundingClientRect().width),
    height: Math.round(t.getBoundingClientRect().height),
    body: br ? {x:Math.round(br.x), y:Math.round(br.y), w:Math.round(br.width), h:Math.round(br.height),
                row: body.getAttribute('data-row'), col: body.getAttribute('data-col'),
                span: body.getAttribute('data-span')} : null,
    cards: cards,
    scrollW: document.documentElement.scrollWidth, innerW: innerWidth
  });
})()"""


def shot(cdp, name):
    r = cdp.call("Page.captureScreenshot", format_="png")
    p = os.path.join(SHOTS, name)
    with open(p, "wb") as f:
        f.write(base64.b64decode(r["data"]))
    return p


def pick_gun(cdp, name):
    return cdp.eval("""(function(want){
      var cs=[].slice.call(document.querySelectorAll('#gw-browse .gw-card'));
      for(var i=0;i<cs.length;i++){
        var s=cs[i].querySelector('span');
        if(s && s.textContent.indexOf(want)>=0){ cs[i].click(); return s.textContent; }
      }
      return null;})(""" + json.dumps(name) + ")")


def main():
    want = "柯尔特 M4A1"
    if "--gun" in sys.argv:
        want = sys.argv[sys.argv.index("--gun") + 1]
    proc, ws = launch(find_chrome(), 9461, 1920, 919, os.path.join(os.environ.get("TEMP", "."), "r1912"))
    rep = {}
    try:
        cdp = CDP(ws)
        for m in ("Page.enable", "Runtime.enable", "Log.enable", "Network.enable"):
            cdp.call(m)
        cdp.call("Emulation.setDeviceMetricsOverride", width=1920, height=919,
                 deviceScaleFactor=1, mobile=False)
        cdp.call("Page.navigate", url="http://127.0.0.1:8787/index.html")
        wait_ready(cdp, want_url="index.html")
        time.sleep(2)
        cdp.eval("try{localStorage.removeItem('eftmap.gwmode')}catch(e){}")
        cdp.eval("document.querySelector('[data-view=\"gun\"]').click()")
        time.sleep(2)
        rep["picked"] = pick_gun(cdp, want)
        time.sleep(2.5)
        rep["gun"] = cdp.eval("(document.getElementById('gw-current')||{}).textContent")
        rep["grid1920"] = json.loads(cdp.eval(GRID_JS) or "null")
        shot(cdp, "P-%s-1920.png" % ("m4" if "M4A1" in want else "gun"))
        cdp.call("Emulation.setDeviceMetricsOverride", width=1384, height=805,
                 deviceScaleFactor=1, mobile=False)
        time.sleep(1.5)
        rep["grid1384"] = json.loads(cdp.eval(GRID_JS) or "null")
        shot(cdp, "P-%s-1384.png" % ("m4" if "M4A1" in want else "gun"))
        rep["console"] = (getattr(cdp, "console", None) or [])[:6]
        rep["external"] = [r["url"] for r in (getattr(cdp, "requests", None) or [])
                           if "127.0.0.1" not in r["url"]]
        print(json.dumps({k: v for k, v in rep.items() if not k.startswith("grid")},
                         ensure_ascii=False, indent=1))
        for tag in ("grid1920", "grid1384"):
            g = rep.get(tag) or {}
            print(tag, "cols=", g.get("cols"), "rows=", g.get("rows"),
                  "w=", g.get("width"), "h=", g.get("height"),
                  "body=", g.get("body"), "scrollW/innerW=", g.get("scrollW"), g.get("innerW"))
    finally:
        proc.terminate()
    with open(os.path.join(OUT, "_probe.json"), "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
