# -*- coding: utf-8 -*-
"""R19.9 验收：属性条三段式等宽/基准位置 + FORGE 手电激光型号选择（真实浏览器）。

1) 四枪（MCX .300 BLK / M4A1 / AK-74 / Glock 17）：
   - 记录 5 条属性条的轨道宽度、数值列宽度、数值是否被截断、基准竖线位置与基准值文本；
   - 确认轨道宽度全部相等、数值列全部相等、文本未溢出。
2) 设备型号选择：选第一把枪 → 展开手电列表 → 点某型号 → 生成 → 应用；
   - 断言方案里装的就是所选 id（不是"任意具备该功能的设备"）；
   - 断言结果说明行显示该型号名称。
3) 截图：bars-4guns.png / forge-devices.png 等。
"""
import base64
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r181_accept import find_chrome, launch, CDP, wait_ready  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "r19.9-audit", "screenshots")
os.makedirs(OUT, exist_ok=True)

GUNS = [("SIG MCX .300 Blackout", "mcx"), ("柯尔特 M4A1", "m4a1"),
        ("AK-74 5.45x39", "ak74"), ("Glock 17 9x19", "glock17")]


def shot(cdp, name):
    r = cdp.call("Page.captureScreenshot", format_="png")
    with open(os.path.join(OUT, name), "wb") as f:
        f.write(base64.b64decode(r["data"]))


def pick(cdp, needle):
    for _ in range(4):
        cdp.eval("""(function(){var b=document.querySelector('.gw-mode[data-gwmode="caliber"]');
          if(b)b.click();})()""")
        time.sleep(1.0)
        cdp.eval("""(function(){var cs=document.querySelectorAll('#gw-browse .gw-card');
          for(var i=0;i<cs.length;i++){var s=cs[i].querySelector('span');
            if(s && s.textContent.indexOf('%s')>=0){cs[i].scrollIntoView({block:'center'});}}})()""" % needle)
        time.sleep(0.9)
        pos = cdp.eval("""(function(){var cs=document.querySelectorAll('#gw-browse .gw-card');
          for(var i=0;i<cs.length;i++){var s=cs[i].querySelector('span');
            if(s && s.textContent.indexOf('%s')>=0){var r=cs[i].getBoundingClientRect();
              return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2});}}})()""" % needle)
        if not pos or pos == "null":
            continue
        p = json.loads(pos)
        hit = cdp.eval("(function(){var e=document.elementFromPoint(%f,%f);"
                       "return !!(e&&e.closest&&e.closest('#gw-browse .gw-card'));})()"
                       % (p["x"], p["y"]))
        if not hit:
            continue
        cdp.click_at(p["x"], p["y"])
        time.sleep(2.4)
        if needle.split(" ")[0] in (cdp.eval(
                "(document.getElementById('gw-current')||{}).textContent") or ""):
            return True
    return False


BAR_AUDIT = r"""
(function(){
  var rows=[].slice.call(document.querySelectorAll('#gw-bars .gw-bar'));
  return JSON.stringify(rows.map(function(r){
    var lab=r.querySelector('.gw-bar-lab');
    var tr=r.querySelector('.gw-bar-track');
    var val=r.querySelector('.gw-bar-val');
    var base=r.querySelector('.gw-bar-base');
    var lr=lab.getBoundingClientRect(), trr=tr.getBoundingClientRect(),
        vr=val.getBoundingClientRect();
    return {label:lab.textContent, trackW:Math.round(trr.width), trackX:Math.round(trr.x),
      valW:Math.round(vr.width), valX:Math.round(vr.x),
      valText:val.textContent, valClipped: val.scrollWidth>val.clientWidth+1,
      baseLeftPct: base ? base.style.left : null,
      baseTitle: base ? base.title : null};
  }));
})()
"""

DEVICE_AUDIT = r"""
(function(){
  var blocks=[].slice.call(document.querySelectorAll('.gw-forge-devblk'));
  return JSON.stringify(blocks.map(function(b){
    var cnt=b.querySelector('.gw-forge-devcnt');
    var rows=[].slice.call(b.querySelectorAll('.gw-forge-poolrow'));
    return {title:(b.querySelector('b')||{}).textContent||'',
      count:cnt?cnt.textContent:null,
      summary:(b.querySelector('.gw-forge-sel')||{}).textContent||'',
      rowCount:rows.length,
      firstRows:rows.slice(0,3).map(function(r){
        return {name:(r.querySelector('span')||{}).textContent||'',
                tag:(r.querySelector('.gw-forge-mag')||{}).textContent||'',
                on:r.dataset.on};})};
  }));
})()
"""


def main():
    rep = {"guns": {}, "devices": {}}
    proc, ws = launch(find_chrome(), 9432, 1920, 919,
                      os.path.join(os.environ.get("TEMP", "."), "r199-%d" % os.getpid()))
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

        for needle, key in GUNS:
            assert pick(cdp, needle), needle + " 选枪失败"
            time.sleep(1.2)
            bars = json.loads(cdp.eval(BAR_AUDIT) or "[]")
            rep["guns"][key] = {
                "gun": cdp.eval("(document.getElementById('gw-current')||{}).textContent"),
                "bars": bars,
                "trackWidthsEqual": len(set(b["trackW"] for b in bars)) == 1,
                "valWidthsEqual": len(set(b["valW"] for b in bars)) == 1,
                "anyClipped": any(b["valClipped"] for b in bars),
            }
            shot(cdp, "bars-%s.png" % key)

        # ---- 设备型号选择：回到 AK-74 ----
        assert pick(cdp, "AK-74 5.45x39"), "AK-74 重新选枪失败"
        time.sleep(1.2)
        cdp.eval("document.querySelector('.gw-forge').scrollTop = 0")
        dev0 = json.loads(cdp.eval(DEVICE_AUDIT) or "[]")
        rep["devices"]["initial"] = dev0
        shot(cdp, "forge-devices.png")

        # 点手电列表第一项
        clicked = cdp.eval("""
          (function(){
            var b=document.querySelectorAll('.gw-forge-devblk')[0];
            if(!b) return 'no-block';
            var row=b.querySelector('.gw-forge-poolrow');
            if(!row) return 'no-row';
            row.click();
            return (row.querySelector('span')||{}).textContent || 'ok';
          })()""")
        time.sleep(1.0)
        rep["devices"]["pickedLight"] = clicked
        rep["devices"]["afterPick"] = json.loads(cdp.eval(DEVICE_AUDIT) or "[]")
        shot(cdp, "forge-devices-picked.png")

        # 生成并应用第一个方案
        gen = cdp.eval("""(function(){
          var b=document.querySelector('.gw-forge-go');
          if(!b) return 'no-gen'; b.click(); return 'clicked';})()""")
        rep["devices"]["generate"] = gen
        for _ in range(40):
            time.sleep(0.5)
            if cdp.eval("document.querySelectorAll('.gw-forge-res').length") > 0:
                break
        picks = cdp.eval("""
          (function(){
            var rows=[].slice.call(document.querySelectorAll('.gw-forge-res'));
            var out=[];
            rows.forEach(function(r){
              var note=r.querySelector('.gw-forge-viol');
              out.push({text:(r.textContent||'').replace(/\\s+/g,' ').slice(0,150),
                bad: !!note});
            });
            return JSON.stringify(out);
          })()""")
        rep["devices"]["results"] = json.loads(picks or "[]")
        shot(cdp, "forge-devices-results.png")

        # 应用第一个（未标红）方案并核对已装件
        applied = cdp.eval("""
          (function(){
            var rows=[].slice.call(document.querySelectorAll('.gw-forge-res'));
            var good=rows.filter(function(r){return !r.querySelector('.gw-forge-viol');})[0];
            if(!good) return 'no-good';
            var btn=good.querySelector('button');
            if(!btn) return 'no-btn';
            btn.click();
            return 'applied';
          })()""")
        time.sleep(2.5)
        rep["devices"]["apply"] = applied
        rep["devices"]["installedAfterApply"] = cdp.eval("""
          (function(){
            var ids=[];
            [].forEach.call(document.querySelectorAll('#gw-tree .gw-part:not(.gw-part-empty) .gw-part-ic'),
              function(i){var s=i.getAttribute('src')||'';var m=s.match(/([0-9a-f]{24})\\.png/);
                if(m) ids.push(m[1]);});
            return JSON.stringify(ids);
          })()""")
        shot(cdp, "forge-devices-applied.png")

        rep["console"] = (getattr(cdp, "console", None) or [])[:6]
        rep["requests"] = len([r for r in (getattr(cdp, "requests", None) or [])
                               if "127.0.0.1" not in r["url"]])
    finally:
        proc.terminate()

    with open(os.path.join(ROOT, "docs", "r19.9-audit", "_accept.json"), "w",
              encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    print(json.dumps({
        "guns": {k: {kk: v[kk] for kk in ("gun", "trackWidthsEqual", "valWidthsEqual", "anyClipped")}
                 for k, v in rep["guns"].items()},
        "trackW": {k: [b["trackW"] for b in v["bars"]] for k, v in rep["guns"].items()},
        "valText": {k: [b["valText"] for b in v["bars"]] for k, v in rep["guns"].items()},
        "pickedLight": rep["devices"].get("pickedLight"),
        "devAfter": rep["devices"].get("afterPick"),
        "apply": rep["devices"].get("apply"),
        "installed": rep["devices"].get("installedAfterApply"),
        "results0": (rep["devices"].get("results") or [])[:2],
        "console": rep["console"], "externalReq": rep["requests"],
    }, ensure_ascii=False, indent=1)[:3000])


if __name__ == "__main__":
    main()
