# -*- coding: utf-8 -*-
"""R19.5b：参考视口(1920×919)本地截图 + overlay/diff 合成 + 任务书命名截图。"""
import base64, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r181_accept import find_chrome, launch, CDP, wait_ready

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = os.path.join(ROOT, "docs", "r19.5-layout-audit", "screenshots")
os.makedirs(S, exist_ok=True)


def shot(cdp, path):
    r = cdp.call("Page.captureScreenshot", format_="png")
    with open(path, "wb") as f:
        f.write(base64.b64decode(r["data"]))


def pick(cdp, needle):
    for _ in range(4):
        cdp.eval("""
          (function(){var b=document.querySelector('.gw-mode[data-gwmode="caliber"]');
            if(b)b.click();})()""")
        time.sleep(1.0)
        cdp.eval("""
          (function(){var cs=document.querySelectorAll('#gw-browse .gw-card');
            for(var i=0;i<cs.length;i++){var s=cs[i].querySelector('span');
              if(s && s.textContent.indexOf('%s')>=0){
                cs[i].scrollIntoView({block:'center'});}}})()""" % needle)
        time.sleep(1.0)
        pos = cdp.eval("""
          (function(){var cs=document.querySelectorAll('#gw-browse .gw-card');
            for(var i=0;i<cs.length;i++){var s=cs[i].querySelector('span');
              if(s && s.textContent.indexOf('%s')>=0){
                var r=cs[i].getBoundingClientRect();
                return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2});}}})()""" % needle)
        if not pos or pos == "null":
            continue
        p = json.loads(pos)
        hit = cdp.eval(
            "(function(){var e=document.elementFromPoint(%f,%f);"
            "return !!(e&&e.closest&&e.closest('#gw-browse .gw-card'));})()" % (p["x"], p["y"]))
        if not hit:
            continue
        cdp.click_at(p["x"], p["y"])
        time.sleep(2.4)
        cur = cdp.eval("(document.getElementById('gw-current')||{}).textContent") or ""
        if needle.split(" ")[0] in cur:
            return True
    return False


def main():
    proc, ws = launch(find_chrome(), 9416, 1920, 919,
                      os.path.join(os.environ.get("TEMP", "."), "r195b-%d" % os.getpid()))
    try:
        cdp = CDP(ws)
        for m in ("Page.enable", "Runtime.enable"):
            cdp.call(m)
        # ---- 1) 参考对齐视口 1920×919：AK-74 工作台 ----
        cdp.call("Emulation.setDeviceMetricsOverride", width=1920, height=919,
                 deviceScaleFactor=1, mobile=False)
        cdp.call("Page.navigate", url="http://127.0.0.1:8787/index.html")
        wait_ready(cdp, want_url="index.html")
        time.sleep(2.0)
        cdp.eval("try{localStorage.removeItem('eftmap.gwmode')}catch(e){}")
        cdp.eval("document.querySelector('[data-view=\"gun\"]').click()")
        time.sleep(2.5)
        assert pick(cdp, "AK-74 5.45x39 突击步枪"), "AK-74 选枪失败"
        time.sleep(1.0)
        shot(cdp, os.path.join(S, "local-after.png"))
        print("local-after saved (1920x919)")
        # 几何实测
        geo = cdp.eval("""
          (function(){
            function r(sel){var e=document.querySelector(sel);
              if(!e)return null;var b=e.getBoundingClientRect();
              return [Math.round(b.x),Math.round(b.y),Math.round(b.width),Math.round(b.height)];}
            return JSON.stringify({
              forge:r('.gw-forge'), center:r('.gw-center'), cands:r('.gw-cands'),
              loadvar:r('.gw-loadvar'), nodecanvas:r('.gw-nodecanvas'),
              bars:r('#gw-bars'), tree:r('#gw-tree'),
              innerW:window.innerWidth, innerH:window.innerHeight,
              overflowX:document.documentElement.scrollWidth>window.innerWidth+1});
          })()""")
        print("geo:", geo)
        json.dump(json.loads(geo), open(os.path.join(S, "_local-geo.json"), "w"))

        # ---- 2) 任务书命名截图：1920×1080 三枪 + 1264×705 ----
        cdp.call("Emulation.setDeviceMetricsOverride", width=1920, height=1080,
                 deviceScaleFactor=1, mobile=False)
        time.sleep(0.6)
        shot(cdp, os.path.join(S, "builder-ak74.png"))
        for needle, name in (("柯尔特 M4A1", "builder-m4a1.png"), ("HK MP5", "builder-mp5.png")):
            assert pick(cdp, needle), needle + " 选枪失败"
            time.sleep(1.0)
            shot(cdp, os.path.join(S, name))
            print(name, "saved")
        cdp.call("Emulation.setDeviceMetricsOverride", width=1264, height=705,
                 deviceScaleFactor=1, mobile=False)
        time.sleep(1.0)
        shot(cdp, os.path.join(S, "builder-1264.png"))
        print("builder-1264 saved")
    finally:
        proc.terminate()

    # ---- 3) overlay 50% + diff（参考视口 vs local-after） ----
    from PIL import Image, ImageChops
    ref = Image.open(os.path.join(S, "reference-viewport.png")).convert("RGB")
    loc = Image.open(os.path.join(S, "local-after.png")).convert("RGB")
    if loc.size != ref.size:
        loc = loc.resize(ref.size)
    Image.blend(ref, loc, 0.5).save(os.path.join(S, "overlay-50.png"))
    diff = ImageChops.difference(ref, loc)
    # 增强对比度便于阅读
    diff = diff.point(lambda v: min(255, v * 3))
    diff.save(os.path.join(S, "diff.png"))
    print("overlay-50 + diff saved")
    # local-before：本轮修改前的首版 R19.5 截图（改前状态）
    import shutil
    src = os.path.join(S, "p-1920-builder-ak74.png")
    if os.path.exists(src):
        shutil.copy(src, os.path.join(S, "local-before.png"))
        print("local-before copied from first-round shot")


if __name__ == "__main__":
    main()
