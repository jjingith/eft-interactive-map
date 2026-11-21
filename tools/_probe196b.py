import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r181_accept import CDP
from r196_devtools import launch_proxy

proc, ws = launch_proxy(9427, 1920, 919, os.path.join(os.environ.get("TEMP","."), "p196b-%d"%os.getpid()))
try:
    cdp = CDP(ws)
    for m in ("Page.enable","Runtime.enable"):
        cdp.call(m)
    cdp.call("Emulation.setDeviceMetricsOverride", width=1920, height=919, deviceScaleFactor=1, mobile=False)
    cdp.call("Page.navigate", url="https://db4tarkov.com/gun")
    time.sleep(14)
    # 开启 Flutter 语义树
    print("placeholder:", cdp.eval("""(function(){
      var p=document.querySelector('flt-semantics-placeholder');
      if(!p) return 'none';
      var r=p.getBoundingClientRect();
      p.click();
      return JSON.stringify({x:Math.round(r.x),y:Math.round(r.y),w:Math.round(r.width),h:Math.round(r.height),label:p.getAttribute('aria-label')});
    })()"""))
    time.sleep(4)
    print("semantics nodes:", cdp.eval("document.querySelectorAll('flt-semantics').length"))
    print(cdp.eval("""(function(){
      var ns=[].slice.call(document.querySelectorAll('flt-semantics'));
      var out=ns.filter(function(e){var r=e.getBoundingClientRect();return r.width>10;})
        .slice(0,40).map(function(e){var r=e.getBoundingClientRect();
          return (e.getAttribute('aria-label')||e.textContent||'').trim().slice(0,28)+
            ' ['+Math.round(r.x)+','+Math.round(r.y)+','+Math.round(r.width)+','+Math.round(r.height)+']';});
      return JSON.stringify(out,null,1);
    })()"""))
finally:
    proc.terminate()
