# -*- coding: utf-8 -*-
"""R18.2 真实浏览器验收（Chrome DevTools Protocol，纯标准库）。

覆盖：
  1. 配装右侧列表 10 个槽位分类的图标：src 是否指向白底版、图片是否加载成功、
     透明 PNG 是否真的透出容器白底、选中行/悬停行的图标背景；
  2. 左侧卡片板：主武器 1 / 主武器 2 / 手枪空槽剪影是否指向完整枪械图；
  3. 装备一把真实枪械 → 卡片切真实物品图标 → 卸下 → 恢复黑色剪影；
  4. 布局健康度：横向溢出、控制台错误、外部请求、构建标记。

用法：
    python tools/r182_accept.py --port 8787 --out docs/ui-windows-xp/r18.2
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r181_accept import CDP, find_chrome, launch, wait_for, wait_ready  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# (槽位 key, 切换方式, 中文名)
SLOTS = [
    ("helmet", ".lw-cat[data-slot=helmet]", "头盔"),
    ("armor", ".lw-cat[data-slot=armor]", "护甲"),
    ("rig", ".lw-cat[data-slot=rig]", "胸挂"),
    ("backpack", ".lw-cat[data-slot=backpack]", "背包"),
    ("headphones", ".lw-cat[data-slot=headphones]", "耳机"),
    ("glasses", ".lw-cat[data-slot=glasses]", "眼镜"),
    ("face", ".lw-cat[data-slot=face]", "面部"),
    ("primary1", ".lw-cell[data-slot=primary1]", "主武器 1"),
    ("holster", ".lw-cell[data-slot=holster]", "手枪"),
    ("melee", ".lw-cell[data-slot=melee]", "近战武器"),
]

JS_ICON_PROBE = """
(function(){
  var rows = document.querySelectorAll('#loadout-workbench .tbl-row');
  var out = [];
  for (var i = 0; i < rows.length && out.length < 6; i++) {
    var img = rows[i].querySelector('.tbl-icon');
    if (!img) { continue; }
    var cs = getComputedStyle(img);
    out.push({
      src: img.getAttribute('src'),
      natural: img.naturalWidth + 'x' + img.naturalHeight,
      ok: !!(img.complete && img.naturalWidth > 0),
      boxBg: cs.backgroundColor,
      size: cs.width + 'x' + cs.height
    });
  }
  return JSON.stringify(out);
})()
"""

JS_ICON_PIXELS = """
(function(){
  var img = document.querySelector('#loadout-workbench .tbl-row .tbl-icon');
  if (!img || !img.naturalWidth) { return null; }
  var c = document.createElement('canvas');
  c.width = img.naturalWidth; c.height = img.naturalHeight;
  var x = c.getContext('2d');
  x.drawImage(img, 0, 0);
  var d = x.getImageData(0, 0, c.width, c.height).data;
  var n = d.length / 4, trans = 0, opaque = 0;
  for (var i = 0; i < d.length; i += 4) {
    if (d[i + 3] < 10) { trans++; }
    else if (d[i + 3] > 200) { opaque++; }
  }
  // 四角透明度
  var corners = [];
  [[0,0],[c.width-1,0],[0,c.height-1],[c.width-1,c.height-1]].forEach(function(p){
    corners.push(x.getImageData(p[0], p[1], 1, 1).data[3]);
  });
  return JSON.stringify({w: c.width, h: c.height,
    transparentPct: Math.round(1000*trans/n)/10,
    opaquePct: Math.round(1000*opaque/n)/10,
    cornerAlpha: corners});
})()
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "ui-windows-xp", "r18.2"))
    ap.add_argument("--cdp-port", type=int, default=9344)
    a = ap.parse_args()
    out_dir = a.out
    os.makedirs(out_dir, exist_ok=True)

    rep = {"round": "R18.2", "base": "http://127.0.0.1:%d" % a.port,
           "slots": [], "gunSwitch": {}, "build": None,
           "console": [], "externalRequests": [], "layout": {}}
    shots = []

    def shot(cdp, name, clip=None):
        path = os.path.join(out_dir, name)
        n = cdp.shot(path, clip)
        shots.append({"file": name, "bytes": n})
        return path

    def box(cdp, sel):
        return cdp.eval("(function(){var e=document.querySelector(%s);"
                        "if(!e){return null;}var r=e.getBoundingClientRect();"
                        "return {x:r.x,y:r.y,w:r.width,h:r.height};})()" % json.dumps(sel))

    def clip(cdp, sel, pad=4, scroll=True):
        if scroll:
            cdp.eval("(function(){var e=document.querySelector(%s);"
                     "if(e){e.scrollIntoView({block:'center'});}})()" % json.dumps(sel))
            time.sleep(0.3)
        b = box(cdp, sel)
        if not b or b["w"] < 4:
            return None
        vw, vh = cdp.eval("[innerWidth, innerHeight]")
        x, y = max(0, b["x"] - pad), max(0, b["y"] - pad)
        return {"x": x, "y": y,
                "width": max(4, min(b["w"] + pad * 2, vw - x)),
                "height": max(4, min(b["h"] + pad * 2, vh - y))}

    proc = None
    try:
        proc, ws_url = launch(find_chrome(), a.cdp_port, 1600, 900,
                             os.path.join(os.environ.get("TEMP", "."), "r182-%d" % os.getpid()))
        cdp = CDP(ws_url)
        for m in ("Page.enable", "Runtime.enable", "Network.enable", "Log.enable"):
            cdp.call(m)
        cdp.call("Emulation.setDeviceMetricsOverride", width=1600, height=900,
                 deviceScaleFactor=1, mobile=False)
        cdp.call("Page.navigate", url="http://127.0.0.1:%d/index.html" % a.port)
        wait_ready(cdp, want_url="index.html")
        cdp.eval("try{localStorage.clear()}catch(e){}")
        cdp.call("Page.reload")
        wait_ready(cdp, want_url="index.html")
        time.sleep(1.4)

        # ---- 左侧卡片板（空槽） ----
        cdp.eval("document.querySelector('[data-view=\"loadout\"]').click()")
        wait_for(cdp, "!!document.querySelector('#loadout-workbench .lw-cell')", label="配装板")
        time.sleep(1.0)
        # 清空已有配装：本地配置可能带着上次的装备，会让「选中行/空槽」判定错位
        for _ in range(30):
            # 两类卸载按钮都要点：.lw-node-x 在节点行上、.lw-ci-x 在卡片图标角上
            left = cdp.eval("""
              (function(){
                var xs=document.querySelectorAll(
                  '#loadout-workbench .lw-ci-x, #loadout-workbench .lw-node-x');
                if(!xs.length){return 0;}
                xs[0].click();
                return xs.length;
              })()""")
            if not left:
                break
            time.sleep(0.45)
        rep["clearedNodes"] = cdp.eval(
            "document.querySelectorAll('#loadout-workbench .lw-ci-x, "
            "#loadout-workbench .lw-node-x').length")
        time.sleep(0.6)

        rep["leftSilhouettes"] = json.loads(cdp.eval("""
          (function(){
            var out=[];
            document.querySelectorAll('#loadout-workbench .lw-cell').forEach(function(b){
              var s=b.querySelector('.lw-sil');
              if(!s){return;}
              out.push({slot:b.getAttribute('data-slot'),
                        src:s.getAttribute('src').split('/').pop(),
                        natural:s.naturalWidth+'x'+s.naturalHeight,
                        ok:!!(s.complete&&s.naturalWidth>0)});
            });
            return JSON.stringify(out);
          })()"""))
        shot(cdp, "after-01-left-silhouettes.png", clip(cdp, "#loadout-workbench .lw-board"))

        # ---- 逐槽位检查右侧列表图标 ----
        for key, sel, zh in SLOTS:
            clicked = cdp.eval("(function(){var e=document.querySelector(%s);"
                               "if(!e){return false;}e.click();return true;})()" % json.dumps(sel))
            if not clicked:
                rep["slots"].append({"key": key, "name": zh, "error": "找不到切换按钮"})
                continue
            time.sleep(0.6)
            # 等图片进入 complete 状态：白底 PNG 缺失时会 onerror 回退到原 webp，
            # 这个替换是异步的，立刻读会拿到 naturalWidth=0 的中间态。
            for _ in range(20):
                pending = cdp.eval("""
                  (function(){
                    var n=0;
                    document.querySelectorAll('#loadout-workbench .tbl-icon').forEach(function(i){
                      if(!i.complete || !i.naturalWidth){n++;}
                    });
                    return n;
                  })()""")
                if not pending:
                    break
                time.sleep(0.2)
            icons = json.loads(cdp.eval(JS_ICON_PROBE) or "[]")
            entry = {"key": key, "name": zh, "icons": icons}
            if key in ("helmet", "armor", "primary1", "holster"):
                px = cdp.eval(JS_ICON_PIXELS)
                entry["pixels"] = json.loads(px) if px else None
            # 选中第一行（点行 = 装备），再截图看选中态
            cdp.eval("""
              (function(){
                var r=document.querySelector('#loadout-workbench .tbl-row');
                if(r){r.setAttribute('data-probe', '1');}
              })()""")
            shot(cdp, "after-02-list-%s.png" % key,
                 clip(cdp, "#loadout-workbench .lw-table, #loadout-workbench .tbl-head", pad=2))
            # 取消选中，避免影响下一个槽位
            cdp.eval("(function(){var r=document.querySelector('[data-probe]');"
                     "if(r){r.removeAttribute('data-probe');}})()")
            rep["slots"].append(entry)

        # ---- 选中态 / 悬停态背景色 ----
        cdp.eval("document.querySelector('.lw-cat[data-slot=helmet]').click()")
        time.sleep(0.9)
        row = cdp.eval("""
          (function(){
            var r=document.querySelector('#loadout-workbench .tbl-row');
            if(!r){return null;}
            var b=r.getBoundingClientRect();
            return {x:b.x+b.width/2, y:b.y+b.height/2};
          })()""")
        state = {}
        if row:
            cdp.mouse(row["x"], row["y"])
            time.sleep(0.4)
            state["hover"] = json.loads(cdp.eval("""
              (function(){
                var img=document.querySelector('#loadout-workbench .tbl-row .tbl-icon');
                var row=img?img.closest('.tbl-row'):null;
                return JSON.stringify({rowBg: row?getComputedStyle(row).backgroundColor:null,
                  iconBg: img?getComputedStyle(img).backgroundColor:null});
              })()"""))
            shot(cdp, "after-03-hover-row.png", clip(cdp, "#loadout-workbench .tbl-head", pad=2))
            cdp.click_at(row["x"], row["y"])
            time.sleep(0.9)
            state["selected"] = json.loads(cdp.eval("""
              (function(){
                var img=document.querySelector('#loadout-workbench .tbl-row .tbl-icon');
                var row=img?img.closest('.tbl-row'):null;
                return JSON.stringify({rowBg: row?getComputedStyle(row).backgroundColor:null,
                  iconBg: img?getComputedStyle(img).backgroundColor:null,
                  selected: row?row.getAttribute('aria-selected'):null});
              })()"""))
            shot(cdp, "after-04-selected-row.png",
                 clip(cdp, "#loadout-workbench .lw-table, #loadout-workbench .tbl-head", pad=2))
            # 卸下，恢复空槽
            cdp.eval("(function(){var xs=document.querySelectorAll('#loadout-workbench .lw-node-x');"
                     "if(xs.length){xs[0].click();}})()")
            time.sleep(0.7)
        rep["rowStates"] = state

        # ---- 枪械：装上一把真实枪 → 卸下 ----
        # 注意：枪械槽的候选是"已保存的枪械预设"，点行的语义是 **toggle**
        # （点已装的那一行 = 卸下），所以流程必须按当前状态分叉，不能假设起始为空。
        def gun_state():
            return json.loads(cdp.eval("""
              (function(){
                var c=document.querySelector('.lw-cell[data-slot=primary1]');
                var s=c.querySelector('.lw-sil'), ic=c.querySelector('.lw-cell-icon');
                return JSON.stringify({sil: s?s.getAttribute('src').split('/').pop():null,
                  icon: ic?ic.getAttribute('src').split('/').pop():null,
                  state: c.getAttribute('data-state')});
              })()"""))

        def click_row(want_selected):
            """点第一行；want_selected=False 时点未选中的行（= 装上另一把）。"""
            pos = cdp.eval("""
              (function(){
                var rows=document.querySelectorAll('#loadout-workbench .tbl-row');
                for(var i=0;i<rows.length;i++){
                  var sel=rows[i].getAttribute('aria-selected')==='true';
                  if(sel===(%s)){ var b=rows[i].getBoundingClientRect();
                    return {x:b.x+b.width/2,y:b.y+b.height/2,i:i}; }
                }
                return null;
              })()""" % ("true" if want_selected else "false"))
            if not pos:
                return None
            cdp.click_at(pos["x"], pos["y"])
            time.sleep(1.1)
            return pos

        cdp.eval("document.querySelector('.lw-cell[data-slot=primary1]').click()")
        time.sleep(1.2)
        initial = gun_state()
        if initial.get("icon"):
            click_row(True)                     # 已装着 -> 点它卸下
        before = gun_state()
        shot(cdp, "after-05-gun-slot-empty.png", clip(cdp, "#loadout-workbench .lw-board"))
        picked = click_row(False)               # 点一把未选中的 -> 装上
        equipped = gun_state()
        shot(cdp, "after-06-gun-equipped.png", clip(cdp, "#loadout-workbench .lw-board"))
        click_row(True)                         # 再点已选中的 -> 卸下
        removed = gun_state()
        shot(cdp, "after-07-gun-removed.png", clip(cdp, "#loadout-workbench .lw-board"))
        rep["gunSwitch"] = {"initial": initial, "before": before, "equipped": equipped,
                            "removed": removed, "pickedRow": picked}

        # ---- 构建标记 / 布局 ----
        cdp.eval("document.querySelector('[data-view=\"ammo\"]').click()")
        time.sleep(0.8)
        cdp.eval("document.querySelector('.am-tab[data-tab=\"sim\"]').click()")
        time.sleep(1.8)
        rep["build"] = cdp.eval("(function(){var e=document.querySelector('.am-sim-runhint');"
                                "return e?e.textContent.trim():null;})()")
        rep["layout"] = {
            "noHScroll": cdp.eval("document.documentElement.scrollWidth <= "
                                  "document.documentElement.clientWidth + 1"),
            "bodyW": cdp.eval("document.documentElement.clientWidth"),
        }
        cdp.call("Page.navigate", url="http://127.0.0.1:%d/index.html" % a.port)
        wait_ready(cdp, want_url="index.html")
        time.sleep(1.0)
        rep["console"] = cdp.console
        rep["externalRequests"] = [r for r in cdp.requests
                                   if not r["url"].startswith("http://127.0.0.1:%d" % a.port)
                                   and not r["url"].startswith("devtools://")]
    finally:
        if proc:
            try:
                proc.terminate()
            except Exception:
                pass

    rep["shots"] = shots
    out = os.path.join(out_dir, "_accept.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    print("报告：", os.path.relpath(out, ROOT))
    print("截图 %d 张 / 控制台错误 %d / 外部请求 %d"
          % (len(shots), len(rep["console"]), len(rep["externalRequests"])))


if __name__ == "__main__":
    main()
