import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r181_accept import find_chrome, launch, CDP, wait_ready

proc, ws = launch(find_chrome(), 9418, 1920, 919,
                  os.path.join(os.environ.get("TEMP", "."), "d195c-%d" % os.getpid()))
try:
    cdp = CDP(ws)
    for m in ("Page.enable", "Runtime.enable"):
        cdp.call(m)
    cdp.call("Emulation.setDeviceMetricsOverride", width=1920, height=919,
             deviceScaleFactor=1, mobile=False)
    cdp.call("Page.navigate", url="http://127.0.0.1:8787/index.html")
    wait_ready(cdp, want_url="index.html"); time.sleep(2.0)
    cdp.eval("try{localStorage.removeItem('eftmap.gwmode')}catch(e){}")
    cdp.eval("document.querySelector('[data-view=\"gun\"]').click()"); time.sleep(2.5)
    cdp.eval("""(function(){var cs=document.querySelectorAll('#gw-browse .gw-card');
      for(var i=0;i<cs.length;i++){var s=cs[i].querySelector('span');
        if(s&&s.textContent.indexOf('AK-74 5')>=0){cs[i].scrollIntoView({block:'center'});}}})()""")
    time.sleep(1.0)
    pos=json.loads(cdp.eval("""(function(){var cs=document.querySelectorAll('#gw-browse .gw-card');
      for(var i=0;i<cs.length;i++){var s=cs[i].querySelector('span');
        if(s&&s.textContent.indexOf('AK-74 5')>=0){var r=cs[i].getBoundingClientRect();
          return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2});}}})()"""))
    cdp.click_at(pos["x"],pos["y"]); time.sleep(2.5)
    print(cdp.eval("""
      (function(){
        var sels=['.gw-top','.gw-modes','.gw-loadvar','.gw-loadvar .gw-visual-slimbox',
          '.gw-nodecanvas','.gw-nodechain','#gw-bars','#gw-hidden','#gw-hidden .gw-stat','#gw-stats',
          '#gw-focus','#gw-tree','#gw-ammo','#gw-bottom','.gw-center'];
        return sels.map(function(s){
          var e=document.querySelector(s);
          if(!e) return s+': MISSING';
          var r=e.getBoundingClientRect();
          return s+': y='+Math.round(r.y)+' h='+Math.round(r.height)+' w='+Math.round(r.width);
        }).join('\\n');
      })()"""))
    print(cdp.eval("""(function(){
      var e=document.querySelector('#gw-hidden'); var cs=getComputedStyle(e);
      return 'disp='+cs.display+' cols='+cs.gridTemplateColumns+' pad='+cs.padding+
             ' children='+e.children.length;
    })()"""))
    # gw-stats 子行数与单行高
    print(cdp.eval("""
      (function(){
        var rows=document.querySelectorAll('#gw-stats .gw-stat, #gw-stats .gw-stat-ex');
        if(!rows.length) return 'stats rows 0';
        var r0=rows[0].getBoundingClientRect();
        var cs=getComputedStyle(document.querySelector('#gw-stats'));
        return 'stats rows='+rows.length+' firstH='+Math.round(r0.height)+
          ' cols='+cs.gridTemplateColumns.split(' ').length+
          ' heads='+document.querySelectorAll('#gw-stats .gw-stat-head').length;
      })()"""))
finally:
    proc.terminate()
