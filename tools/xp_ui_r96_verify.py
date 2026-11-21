# -*- coding: utf-8 -*-
"""R96 实测：A 滑块三层背景端头恒定 / B 表头九宫格端头恒定 / C 箭头三角 / mini 零影响。

用 CDP 起一个不隐藏滚动条的 headless Chrome，在真实页面里插临时滚动容器
（用完即删，不改应用 DOM），把滚动条列截图落 docs/xp-ui-r96-shots/ 并做像素比对。

用法：python tools/xp_ui_r96_verify.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import r181_accept as R  # noqa: E402
from PIL import Image  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOTS = os.path.join(ROOT, "docs", "xp-ui-r96-shots")
PORT = 9346
PROFILE = os.path.join(ROOT, "docs", ".r96-profile")
URL = "http://127.0.0.1:8791/index.html"

# 竖向：容器 300 高、上下按钮各 27 → 轨道 246；内容 3690/1230/369 时滑块 ≈ 20/60/200
V_CASES = [(3690, 20), (1230, 60), (369, 200)]
# 横向：容器 300 宽、左右按钮各 21 → 轨道 258；内容 3870/1290/387 时滑块 ≈ 20/60/200
H_CASES = [(3870, 20), (1290, 60), (387, 200)]
ARROW_INK = (59, 65, 47)


def launch(chrome):
    """和 r181_accept.launch 一致，但去掉 --hide-scrollbars（否则截图里没有滚动条）。"""
    import subprocess
    import urllib.request
    import json
    args = [chrome, "--headless=new", "--remote-debugging-port=%d" % PORT,
            "--user-data-dir=%s" % PROFILE, "--no-first-run", "--no-default-browser-check",
            "--disable-gpu", "--disable-extensions", "--no-proxy-server",
            "--disable-background-networking", "--disable-sync", "--disable-component-update",
            "--force-device-scale-factor=1", "--window-size=1834,1030", "about:blank"]
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ws_url = None
    for _ in range(160):
        time.sleep(0.25)
        try:
            with urllib.request.urlopen("http://127.0.0.1:%d/json/list" % PORT, timeout=2) as r:
                tabs = json.loads(r.read())
            for t in tabs:
                if t.get("type") == "page":
                    ws_url = t["webSocketDebuggerUrl"]
                    break
            if ws_url:
                break
        except Exception:
            continue
    if not ws_url:
        proc.terminate()
        raise SystemExit("Chrome CDP 没有就绪")
    return proc, ws_url


def make_box(cdp, inner_h, inner_w=None):
    cdp.eval("""
(function(a){
  var old=document.getElementById('r96-probe'); if(old){ old.remove(); }
  var box=document.createElement('div');
  box.id='r96-probe';
  var w = a[1] ? 300 : 180, h = a[1] ? 60 : 300;
  var css='position:fixed;left:10px;top:10px;width:'+w+'px;height:'+h+'px;z-index:99999;background:#ddd;';
  css += a[1] ? 'overflow-x:scroll;overflow-y:hidden;' : 'overflow-y:scroll;overflow-x:hidden;';
  box.style.cssText=css;
  var inner=document.createElement('div');
  inner.style.cssText = a[1] ? ('width:'+a[1]+'px;height:40px;background:#ccc')
                             : ('height:'+a[0]+'px;background:#ccc');
  box.appendChild(inner);
  document.body.appendChild(box);
  box.scrollTop=0; box.scrollLeft=0;
  return 1;
})([%d,%s])
""" % (inner_h, "null" if inner_w is None else inner_w))


def rect_of(cdp):
    return cdp.eval("document.getElementById('r96-probe').getBoundingClientRect().toJSON()")


def rows_where(im, x, pred, y0, y1):
    px = im.load()
    out = []
    for y in range(y0, y1):
        if pred(px[x, y]):
            out.append(y)
    return out


def main():
    os.makedirs(SHOTS, exist_ok=True)
    chrome = R.find_chrome()
    proc, ws = launch(chrome)
    try:
        cdp = R.CDP(ws)
        cdp.call("Page.enable")
        cdp.call("Runtime.enable")
        cdp.call("Emulation.setDeviceMetricsOverride", width=1834, height=1030,
                 deviceScaleFactor=1, mobile=False)
        cdp.call("Page.navigate", url=URL)
        R.wait_ready(cdp, want_url="8791")
        R.wait_for(cdp, "!!document.getElementById('view-btn-loadout')", 40, "视图按钮")

        # ---------------- A 竖向 ----------------
        print("== A 竖滑块（三层背景）==")
        caps = {}
        for content_h, want in V_CASES:
            make_box(cdp, content_h)
            time.sleep(0.45)
            r = rect_of(cdp)
            p = os.path.join(SHOTS, "thumb-v-%03d.png" % want)
            cdp.shot(p, {"x": round(r["right"] - 22), "y": round(r["top"]), "width": 22, "height": 300})
            im = Image.open(p).convert("RGB")
            # 滑块左内棱 x=1 比轨道暗边（~82）亮得多，用它定位滑块行
            rows = rows_where(im, 1, lambda p: p[0] > 105, 28, 272)
            if not rows:
                print("  %3dpx 目标：没找到滑块" % want)
                continue
            top, bot = rows[0], rows[-1]
            print("  %3dpx 目标：滑块 y=%d..%d，长 %dpx" % (want, top, bot, bot - top + 1))
            caps[want] = (im, top, bot)

        if len(caps) == 3:
            wtop = wbot = 0
            for want in (60, 200):
                ref, cur = caps[20], caps[want]
                for i in range(3):
                    for x in range(22):
                        pa = ref[0].getpixel((x, ref[1] + i)); pb = cur[0].getpixel((x, cur[1] + i))
                        wtop = max(wtop, max(abs(pa[k] - pb[k]) for k in range(3)))
                for i in range(4):
                    for x in range(22):
                        pa = ref[0].getpixel((x, ref[2] - 3 + i)); pb = cur[0].getpixel((x, cur[2] - 3 + i))
                        wbot = max(wbot, max(abs(pa[k] - pb[k]) for k in range(3)))
            ok = max(wtop, wbot) <= 3
            print("  端头恒定：%s（顶 3 行最大差 %d/通道，底 4 行最大差 %d/通道）"
                  % ("是" if ok else "否", wtop, wbot))

            # C：底按钮里的三角 bbox（按钮 22×27，在轨道下方）
            im, top, bot = caps[200]
            pts = [(x, y) for y in range(273, 300) for x in range(22)
                   if im.getpixel((x, y)) == ARROW_INK]
            if pts:
                xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
                print("  C 下箭头三角：bbox=(%d,%d)-(%d,%d) %dx%d 距按钮顶 %d" %
                      (min(xs), min(ys) - 273, max(xs), max(ys) - 273,
                       max(xs) - min(xs) + 1, max(ys) - min(ys) + 1, min(ys) - 273))

        # ---------------- A 横向 ----------------
        print("== A 横滑块（三层背景）==")
        caps = {}
        for content_w, want in H_CASES:
            make_box(cdp, 40, content_w)
            time.sleep(0.45)
            r = rect_of(cdp)
            p = os.path.join(SHOTS, "thumb-h-%03d.png" % want)
            cdp.shot(p, {"x": round(r["left"]), "y": round(r["bottom"] - 21), "width": 300, "height": 21})
            im = Image.open(p).convert("RGB")
            # 滑块面 (231,228,213) 比轨道面（~135）亮得多；用面色锁定滑块中段。
            # 注意左右帽的最内侧 1 列与面色几乎同色（231,229,213 / 229,227,211），
            # 所以 face[0] 落在「左帽第 3 列」，face[-1] 落在「右帽第 1 列」：
            # 实际滑块 = face[0]-2 .. face[-1]+2，左右各补 2px 帽宽。
            face = [x for x in range(0, 300)
                    if all(abs(im.getpixel((x, 10))[k] - (231, 228, 213)[k]) <= 4
                           for k in range(3))]
            if not face:
                print("  %3dpx 目标：没找到滑块" % want); continue
            left, right = face[0] - 2, face[-1] + 2
            print("  %3dpx 目标：滑块 x=%d..%d，长 %dpx" % (want, left, right, right - left + 1))
            caps[want] = (im, left, right)
        if len(caps) == 3:
            worst = 0
            for want in (60, 200):
                ref, cur = caps[20], caps[want]
                for i in range(3):     # 左帽 3 列
                    for y in range(21):
                        pa = ref[0].getpixel((ref[1] + i, y)); pb = cur[0].getpixel((cur[1] + i, y))
                        worst = max(worst, max(abs(pa[k] - pb[k]) for k in range(3)))
                for i in range(3):     # 右帽 3 列
                    for y in range(21):
                        pa = ref[0].getpixel((ref[2] - 2 + i, y)); pb = cur[0].getpixel((cur[2] - 2 + i, y))
                        worst = max(worst, max(abs(pa[k] - pb[k]) for k in range(3)))
            ok = worst <= 3
            print("  端头恒定：%s（左 3 列 + 右 3 列逐像素比对，最大差 %d/通道）"
                  % ("是" if ok else "否", worst))

        # ---------------- B 表头 ----------------
        print("== B 表头（tbl-head.png 九宫格）==")
        cdp.eval("document.getElementById('r96-probe').remove()")
        cdp.eval("document.getElementById('view-btn-loadout').click()")
        R.wait_for(cdp, "!!document.querySelector('#gear-table .tbl-head')", 30, "配装表头")
        time.sleep(0.6)
        heads = {}
        for h in (20, 32, 48):
            r = cdp.eval("""
(function(h){
  var el=document.querySelector('#gear-table .tbl-head');
  el.style.minHeight=h+'px'; el.style.height=h+'px';
  var cs=getComputedStyle(el), b=el.getBoundingClientRect();
  return {x:b.left,y:b.top,w:b.width,h:b.height,
          src:cs.borderImageSource, biw:cs.borderImageWidth, rep:cs.borderImageRepeat,
          bg:cs.backgroundImage};
})(%d)
""" % h)
            time.sleep(0.25)
            p = os.path.join(SHOTS, "head-%02d.png" % h)
            cdp.shot(p, {"x": round(r["x"]), "y": round(r["y"]),
                         "width": round(r["w"]), "height": round(r["h"])})
            heads[h] = p
            print("  %dpx: 实测 %.1fx%.1f  border-image=%s  width=%s  repeat=%s  background=%s" %
                  (h, r["w"], r["h"], r["src"].rsplit("/", 1)[-1], r["biw"], r["rep"],
                   r["bg"][:46]))

        def corner_mask(im, side):
            """端头最外 2 列 × 前 10 行的「暗边」形状（luma<160 记 1）。
            只取 2 列：第 3 列起已进入内容区（表头文字随高度垂直居中移动，会误判）。"""
            w, h = im.size
            xs = range(0, 2) if side == "L" else range(w - 2, w)
            return [[1 if (0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2]) < 160 else 0
                     for p in [im.getpixel((x, y))]][0] for x in xs for y in range(min(10, h))]

        ok = True
        for h in (32, 48):
            a = Image.open(heads[20]).convert("RGB")
            b = Image.open(heads[h]).convert("RGB")
            for side in ("L", "R"):
                if corner_mask(a, side) != corner_mask(b, side):
                    ok = False
                    print("  %s 端形状不同（%dpx）" % (side, h))
        print("  端头恒定：%s（暗边形状 最外 2 列×10 行 完全一致）" % ("是" if ok else "否"))
        cdp.eval("(function(){var el=document.querySelector('#gear-table .tbl-head');"
                 "el.style.minHeight='';el.style.height='';})()")

        # ---------------- R97：六处 100% 100% 拉伸收尾 ----------------
        print("== R97 行/按钮/进度条去拉伸 ==")

        def set_view(view, wait_sel, label):
            cdp.eval("document.getElementById('view-btn-%s').click()" % view)
            try:
                R.wait_for(cdp, "!!document.querySelector('%s')" % wait_sel, 25, label)
            except TimeoutError:
                print("  [%s] 未渲染 %s" % (label, wait_sel))
                return False
            time.sleep(0.5)
            return True

        def probe2(sel, h, tag):
            """把元素钉成 h 高，截图并返回几何 + 左右边线颜色。"""
            r = cdp.eval("""
(function(a){
  var el=document.querySelector(a[0]); if(!el) return null;
  if(!el.dataset.r97saved){
    el.dataset.r97saved='1';
    el.dataset.r97h=el.style.height||''; el.dataset.r97mh=el.style.minHeight||'';
  }
  el.scrollIntoView({block:'center'});
  el.style.boxSizing='border-box'; el.style.minHeight=a[1]+'px'; el.style.height=a[1]+'px';
  var b=el.getBoundingClientRect(), cs=getComputedStyle(el);
  return {x:b.left,y:b.top,w:b.width,h:b.height,
          bg:cs.backgroundImage, bc:cs.backgroundColor,
          bt:cs.borderTopColor, bb:cs.borderBottomColor};
})([%s,%d])
""" % (repr(sel), h))
            if not r:
                print("  %s：元素不存在" % tag)
                return None
            if r["w"] < 2 or r["h"] < 2:
                print("  %-14s %2dpx：容器当前不可见（%.0fx%.0f）bg-image=%s bg-color=%s"
                      % (tag, h, r["w"], r["h"],
                         r["bg"].rsplit("/", 1)[-1][:28], r["bc"]))
                return None
            time.sleep(0.2)
            p = os.path.join(SHOTS, "r97-%s-%02d.png" % (tag, h))
            cdp.shot(p, {"x": round(r["x"]), "y": round(r["y"]),
                         "width": round(r["w"]), "height": round(r["h"])})
            print("  %-14s %2dpx：实测 %.0fx%.0f  bg-image=%s  bg-color=%s"
                  % (tag, h, r["w"], r["h"], r["bg"].rsplit("/", 1)[-1][:28], r["bc"]))
            return p, r

        def edge_diff(pa, pb):
            """两档高度：比较顶 2 行 / 底 2 行，只取最左 3 列（避开文字）。"""
            a = Image.open(pa).convert("RGB"); b = Image.open(pb).convert("RGB")
            wa, ha = a.size; wb, hb = b.size
            worst = 0
            for i in range(2):
                for x in range(min(3, wa, wb)):
                    p = a.getpixel((x, i)); q = b.getpixel((x, i))
                    worst = max(worst, max(abs(p[k] - q[k]) for k in range(3)))
            for i in range(2):
                for x in range(min(3, wa, wb)):
                    p = a.getpixel((x, ha - 2 + i)); q = b.getpixel((x, hb - 2 + i))
                    worst = max(worst, max(abs(p[k] - q[k]) for k in range(3)))
            return worst

        def two_size(sel, h1, h2, tag):
            p1 = probe2(sel, h1, tag)
            p2 = probe2(sel, h2, tag)
            if not p1 or not p2:
                return
            flat = p1[1]["bg"] == "none" and p2[1]["bg"] == "none"
            d = edge_diff(p1[0], p2[0])
            print("     %d/%d 两档：背景无位图=%s  顶/底边线最大差 %d/通道  -> %s"
                  % (h1, h2, "是" if flat else "否", d,
                     "边线恒定" if flat and d <= 3 else "需复核"))
            cdp.eval("(function(){var el=document.querySelector(%s); if(!el) return;"
                     "el.style.height=el.dataset.r97h||''; el.style.minHeight=el.dataset.r97mh||'';"
                     "el.style.boxSizing='';})()" % repr(sel))

        # 1) 配装表格行（奇/偶）
        if set_view("loadout", "#gear-table .tbl-row", "配装"):
            two_size("#gear-table .tbl-row", 24, 48, "tbl-row")
            two_size("#gear-table .tbl-row:nth-child(even)", 24, 48, "tbl-row-alt")
            # 5) 费用行
            if cdp.eval("!!document.querySelector('.lw-cost-item')"):
                two_size(".lw-cost-item", 24, 42, "lw-cost-item")
            # 40 行长列表：超视口整表截图，逐行测底色纯度与接缝
            tb = cdp.eval("""(function(){
  var t=document.querySelector('#gear-table .tbl-scroll');
  if(!t) return null; var b=t.getBoundingClientRect();
  return {x:b.left,y:b.top,w:b.width,h:t.scrollHeight,rows:t.querySelectorAll('.tbl-row').length};
})()""")
            if tb:
                import base64
                data = base64.b64decode(cdp.call(
                    "Page.captureScreenshot", format="png", captureBeyondViewport=True,
                    clip={"x": tb["x"], "y": tb["y"] + 30, "width": tb["w"],
                          "height": min(tb["h"], 3200), "scale": 1})["data"])
                p = os.path.join(SHOTS, "r97-tbl-40rows.png")
                open(p, "wb").write(data)
                im = Image.open(p).convert("RGB")
                w, h = im.size
                xs = w - 12                      # 最右一格空白处
                runs = []
                prev = None
                for y in range(h):
                    q = im.getpixel((xs, y))
                    if prev is None or max(abs(q[k] - prev[k]) for k in range(3)) > 1:
                        runs.append([y, q]); prev = q
                print("  40 行整表截图 %dx%d，行数=%d，竖向色带变化点=%d"
                      % (w, h, tb["rows"], len(runs)))
                print("     变化点前 8 个 y/色：%s" % [(r[0], r[1]) for r in runs[:8]])

        def clone_probe(tag_html, sel, h1, h2, tag):
            """视图里容器折叠时，用同族类名的离屏探针验同一条 CSS 规则。
            tag_html 是「容器开标签 + 目标元素 + 容器闭标签」，容器带 data-r97 便于定位。"""
            cdp.eval("""(function(){
  var old=document.getElementById('r97-clone'); if(old) old.remove();
  var c=document.createElement('div');
  c.id='r97-clone'; c.setAttribute('data-r97','1');
  c.style.cssText='position:fixed;left:0;top:0;z-index:99999;background:#fff;';
  c.innerHTML=%s;
  document.body.appendChild(c);
  return 1;
})()""" % repr(tag_html))
            two_size("[data-r97] " + sel, h1, h2, tag)
            cdp.eval("(function(){var c=document.getElementById('r97-clone'); if(c) c.remove();})()")

        # 2) 任务行（视图内任务面板默认折叠 → 离屏同族探针）
        set_view("tasks", ".task-list", "任务")
        clone_probe('<div class="task-list" style="width:320px">'
                    '<div class="task-row" style="display:block;padding:4px">任务行探针</div></div>',
                    ".task-row", 24, 56, "task-row")

        # 4) 图层图例行（图层块在非地图视图隐藏 → 离屏同族探针）
        set_view("map", "#layers-block", "地图")
        clone_probe('<div id="layers-block" style="width:320px">'
                    '<div class="legend-item" style="display:block;padding:4px">图例行探针</div></div>',
                    ".legend-item", 24, 42, "legend-item")
        clone_probe('<div id="layers-block" style="width:320px">'
                    '<div class="legend-item legend-sub" style="display:block;padding:4px">子图例探针</div></div>',
                    ".legend-sub", 24, 42, "legend-sub")

        # 6) 枪械属性条段（.gw-bar-seg.neutral，live；表格 tab 默认不展开 → 离屏同族探针）
        cdp.eval("""(function(){
  var old=document.getElementById('r97-bar-probe'); if(old) old.remove();
  var c=document.createElement('div');
  c.id='r97-bar-probe'; c.className='gun-workbench';
  c.style.cssText='position:fixed;left:0;top:0;z-index:99999;width:260px;background:#fff;';
  c.innerHTML='<span class="gw-bar-track" style="display:block;width:240px">'
            + '<i class="gw-bar-seg neutral" style="left:0;width:60%"></i></span>';
  document.body.appendChild(c); return 1;})()""")
        seg = cdp.eval("""(function(){
  var d=document.querySelector('#r97-bar-probe .gw-bar-seg.neutral');
  if(!d) return null;
  var b=d.getBoundingClientRect(), cs=getComputedStyle(d);
  var t=document.querySelector('#r97-bar-probe .gw-bar-track').getBoundingClientRect();
  return {x:b.left,y:b.top,w:b.width,h:b.height,tx:t.left,ty:t.top,tw:t.width,th:t.height,
          bi:cs.borderImageSource, bw:cs.borderImageWidth, bs:cs.boxSizing,
          bg:cs.backgroundImage};
})()""")
        if seg:
            print("  gw-bar-seg.neutral：段 %.1fx%.1f（轨道 %.1fx%.1f）border-image=%s width=%s box-sizing=%s"
                  % (seg["w"], seg["h"], seg["tw"], seg["th"],
                     seg["bi"].rsplit("/", 1)[-1], seg["bw"], seg["bs"]))
            p = os.path.join(SHOTS, "r97-bar-seg.png")
            cdp.shot(p, {"x": round(seg["x"]), "y": round(seg["y"]),
                         "width": round(seg["w"]), "height": round(seg["h"])})
            im = Image.open(p).convert("RGB")
            # 源图带 alpha（indeterminate 的上下边缘是半透明），逐像素比对会被白底
            # 合成干扰；这里验「带结构」：第 1 行亮带 / 第 3 行暗带是否仍是纯蓝、
            # 且亮带整体明显亮于暗带（整图压扁会糊成一片中间灰蓝）。
            def rowmean(im, y):
                vals = [im.getpixel((x, y)) for x in range(3, im.size[0] - 3)]
                return tuple(sum(v[k] for v in vals) / len(vals) for k in range(3))
            m = [rowmean(im, y) for y in range(im.size[1])]
            print("     逐行均值：%s" % ["(%.0f,%.0f,%.0f)" % t for t in m])
            mid = m[1:4] if im.size[1] > 4 else m[1:-1]
            hi = max(mid, key=sum); lo = min(mid, key=sum)
            blue = all((t[2] - t[0]) > 55 for t in mid)
            contrast = sum(hi) - sum(lo)
            print("     双带：第 1/2/3 行均为纯蓝=%s，亮带−暗带=%.1f -> %s"
                  % ("是" if blue else "否", contrast,
                     "双带保住" if blue and abs(contrast) > 30 else "需复核"))
        cdp.eval("(function(){var d=document.getElementById('r97-bar-probe'); if(d) d.remove();})()")

        # 3) 已无 DOM 的规则：确认是否死代码
        dead = cdp.eval("""(function(){
  return {browse:document.querySelectorAll('.gw-browse-gun').length,
          fill:document.querySelectorAll('.gw-bar-fill').length};
})()""")
        print("  选择器命中数：.gw-browse-gun=%d  .gw-bar-fill=%d（均为死规则）；"
              ".gw-bar-seg.neutral 由 app.js 动态生成，live"
              % (dead["browse"], dead["fill"]))

        # ---------------- mini ----------------
        print("== ?mini=1 ==")
        cdp.call("Page.navigate", url=URL + "?mini=1")
        R.wait_ready(cdp, want_url="mini=1")
        time.sleep(1.2)
        st = cdp.eval("""(function(){
  function vis(id){var e=document.getElementById(id); return e?getComputedStyle(e).display:'missing';}
  return {root:document.documentElement.className, menubar:vis('app-menubar'),
          statusbar:vis('app-statusbar'), contexts:document.querySelectorAll('.task-context-item').length};
})()""")
        print("  html.class=%s\n  #app-menubar=%s  #app-statusbar=%s  右键菜单项=%d" %
              (st["root"], st["menubar"], st["statusbar"], st["contexts"]))
    finally:
        proc.terminate()


if __name__ == "__main__":
    main()
