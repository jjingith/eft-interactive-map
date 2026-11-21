# -*- coding: utf-8 -*-
"""R19.18 快速目视探针：选枪 → 导出画布卡片 + 指定槽位候选列表（一次性排查用）。"""
from __future__ import annotations
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r181_accept import CDP, find_chrome, launch, wait_ready

BASE = "http://127.0.0.1:8787"
NEEDLE = sys.argv[1] if len(sys.argv) > 1 else "AKM 7.62x39"
SLOT = sys.argv[2] if len(sys.argv) > 2 else "mod_sight_rear"


def pick_gun(cdp, needle):
    for _ in range(6):
        cdp.eval("""(function(){var b=document.querySelector('.gw-mode[data-gwmode="caliber"]');
          if(b)b.click();})()""")
        time.sleep(0.6)
        pos = cdp.eval("""(function(){var cs=document.querySelectorAll('#gw-browse .gw-card');
          for(var i=0;i<cs.length;i++){var s=cs[i].querySelector('span');
            if(s && s.textContent.indexOf(%s)>=0){cs[i].scrollIntoView({block:'center'});
              var r=cs[i].getBoundingClientRect();
              return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2});}}})()"""
                      % json.dumps(needle, ensure_ascii=False))
        if not pos or pos == "null":
            continue
        p = json.loads(pos)
        cdp.click_at(p["x"], p["y"])
        time.sleep(2.2)
        gid = cdp.eval("(function(){try{return (JSON.parse(localStorage.getItem('eftmap.gun')||'{}')||{}).gunId||null;}catch(e){return null;}})()")
        if gid:
            cdp.eval("document.getElementById('gw-default') && document.getElementById('gw-default').click()")
            time.sleep(1.6)
            return gid
    return None


def main():
    port = 9655
    prof = os.path.join(os.environ.get("TEMP", "."), "r1926probe_%d" % port)
    proc, ws = launch(find_chrome(), port, 1920, 919, prof)
    try:
        cdp = CDP(ws)
        for m in ("Page.enable", "Runtime.enable", "Log.enable"):
            cdp.call(m)
        cdp.call("Emulation.setDeviceMetricsOverride", width=1920, height=919, deviceScaleFactor=1, mobile=False)
        cdp.call("Page.navigate", url=BASE + "/index.html")
        wait_ready(cdp, want_url="index.html")
        time.sleep(2.5)
        cdp.eval("(document.querySelector('[data-view=\"gun\"]')||{click:function(){}}).click()")
        time.sleep(1.2)
        gid = pick_gun(cdp, NEEDLE)
        print("gunId:", gid)
        cards = cdp.eval(r"""(function(){
          var t=document.getElementById('gw-tree');
          return JSON.stringify([].slice.call(t.querySelectorAll('.gw-part')).filter(function(c){return c.dataset.slot;})
            .map(function(c){return {slot:c.dataset.slot,row:+c.dataset.row,col:+c.dataset.col,
                                     text:(c.textContent||'').replace(/\s+/g,' ').trim().slice(0,40)};}));})()""")
        print("画布卡片:")
        for c in json.loads(cards or "[]"):
            print("   r%dc%-2d %-44s %s" % (c["row"], c["col"], c["slot"], c["text"]))
        cdp.eval("(document.querySelector('.gw-part[data-slot=\"%s\"]')||{click:function(){}}).click()" % SLOT)
        time.sleep(1.0)
        rows = cdp.eval(r"""(function(){
          var rs=document.querySelectorAll('#gw-table .tbl-row');
          var out=[];for(var i=0;i<rs.length;i++){out.push({id:rs[i].dataset.id||'',
            t:(rs[i].textContent||'').replace(/\s+/g,' ').trim().slice(0,60),conflict:rs[i].className.indexOf('tbl-conflict')>=0});}
          return JSON.stringify(out);})()""")
        print("槽位 %s 的候选:" % SLOT)
        for r in json.loads(rows or "[]"):
            print("   %s %s%s" % (r["id"], r["t"], "  [不兼容]" if r["conflict"] else ""))
    finally:
        try:
            cdp.call("Browser.close")
        except Exception:
            pass
        if proc:
            proc.terminate()


if __name__ == "__main__":
    main()
