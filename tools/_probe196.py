import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r181_accept import find_chrome, CDP
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r196_devtools import launch_proxy

proc, ws = launch_proxy(9426, 1920, 919, os.path.join(os.environ.get("TEMP","."), "p196-%d"%os.getpid()))
try:
    cdp = CDP(ws)
    for m in ("Page.enable","Runtime.enable"):
        cdp.call(m)
    cdp.call("Emulation.setDeviceMetricsOverride", width=1920, height=919, deviceScaleFactor=1, mobile=False)
    cdp.call("Page.navigate", url="https://db4tarkov.com/gun")
    time.sleep(14)
    print("tags:", cdp.eval("JSON.stringify([].map.call(document.body.querySelectorAll('*'),function(e){return e.tagName.toLowerCase()+'.'+String(e.className||'').slice(0,30);}))"))
    print("canvas:", cdp.eval("""(function(){
      var cs=[].slice.call(document.querySelectorAll('canvas'));
      return JSON.stringify(cs.map(function(c){var r=c.getBoundingClientRect();
        return {w:Math.round(r.width),h:Math.round(r.height),x:Math.round(r.x),y:Math.round(r.y),
          id:c.id,cls:String(c.className||'')};}));
    })()"""))
    print("frames:", cdp.eval("JSON.stringify([].map.call(document.querySelectorAll('iframe'),function(f){return {src:(f.src||'').slice(0,90), w:f.getBoundingClientRect().width, h:f.getBoundingClientRect().height};}))"))
    print("body nodes:", cdp.eval("document.body.querySelectorAll('*').length"))
    # 从 window.frames 里探
    print("frame count:", cdp.eval("window.frames.length"))
    print(cdp.eval("""
      (function(){
        try{
          var d=window.frames.length? window.frames[0].document : null;
          if(!d) return 'no frame doc';
          return 'frame body nodes='+d.querySelectorAll('*').length+
                 ' hasGENERATE='+/GENERATE BUILDS/.test(d.body.textContent||'');
        }catch(e){ return 'ERR '+e.message; }
      })()"""))
finally:
    proc.terminate()
