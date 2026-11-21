import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r181_accept import find_chrome, launch, CDP, wait_ready

JS = r"""(function(){
  function parse(c){
    var m=c.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)/);
    if(!m) return null;
    return [ +m[1], +m[2], +m[3], m[4]===undefined?1:+m[4] ];
  }
  function lum(rgb){
    var a=rgb.slice(0,3).map(function(v){v/=255;return v<=0.03928?v/12.92:Math.pow((v+0.055)/1.055,2.4);});
    return 0.2126*a[0]+0.7152*a[1]+0.0722*a[2];
  }
  function bgOf(el){
    var e=el;
    while(e && e!==document.documentElement){
      var c=parse(getComputedStyle(e).backgroundColor);
      if(c && c[3]>0.5) return c;
      e=e.parentElement;
    }
    return parse(getComputedStyle(document.body).backgroundColor) || [255,255,255,1];
  }
  function blend(fg,bg){
    var a=fg[3];
    return [fg[0]*a+bg[0]*(1-a), fg[1]*a+bg[1]*(1-a), fg[2]*a+bg[2]*(1-a), 1];
  }
  function ratio(a,b){
    var l1=lum(a), l2=lum(b);
    var hi=Math.max(l1,l2), lo=Math.min(l1,l2);
    return (hi+0.05)/(lo+0.05);
  }
  var out=[];
  var host=document.querySelector('#gun-view');
  if(!host) return '[]';
  var walker=document.createTreeWalker(host, NodeFilter.SHOW_TEXT, null);
  var seen={};
  var n;
  while((n=walker.nextNode())){
    var t=(n.textContent||'').trim();
    if(t.length<2) continue;
    var el=n.parentElement;
    if(!el) continue;
    var st=getComputedStyle(el);
    if(st.display==='none'||st.visibility==='hidden'||+st.opacity<0.2) continue;
    var r=el.getBoundingClientRect();
    if(r.width<4||r.height<4) continue;
    var fg=parse(st.color); if(!fg) continue;
    var bg=bgOf(el);
    var fgB=blend(fg,bg);
    var cr=ratio(fgB,bg);
    if(cr<2.6){
      var key=el.className+'|'+st.color+'|'+bg.slice(0,3).join(',');
      if(seen[key]) continue;
      seen[key]=1;
      out.push({cls:String(el.className).slice(0,50), tag:el.tagName,
        text:t.slice(0,26), color:st.color, bg:'rgb('+bg.slice(0,3).join(',')+')',
        ratio:Math.round(cr*100)/100});
    }
  }
  return JSON.stringify(out);
})()"""

proc, ws = launch(find_chrome(), 9399, 1920, 1080,
                  os.path.join(os.environ.get("TEMP", "."), "ca-%d" % os.getpid()))
try:
    cdp = CDP(ws)
    for m in ("Page.enable", "Runtime.enable"):
        cdp.call(m)
    cdp.call("Emulation.setDeviceMetricsOverride", width=1920, height=1080, deviceScaleFactor=1, mobile=False)
    cdp.call("Page.navigate", url="http://127.0.0.1:8787/index.html")
    wait_ready(cdp, want_url="index.html"); time.sleep(2.0)
    cdp.eval("document.querySelector('[data-view=\"gun\"]').click()"); time.sleep(2.5)
    print("=== Caliber 浏览页 ===")
    print(cdp.eval(JS))
    cdp.eval("""(function(){var cs=document.querySelectorAll('#gw-browse .gw-card');
      for(var i=0;i<cs.length;i++){var s=cs[i].querySelector('span');
        if(s&&s.textContent.indexOf('AK-74 5')>=0){cs[i].click();return;}}})()""")
    time.sleep(3.0)
    print("=== 工作台 ===")
    rows=json.loads(cdp.eval(JS) or "[]")
    for r in rows[:40]:
        print("  %-28s %-22s %-14s on %-18s %.2f" % (r["cls"], r["text"][:20], r["color"], r["bg"], r["ratio"]))
    print("共", len(rows), "处低对比")
finally:
    proc.terminate()
