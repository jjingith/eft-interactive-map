# -*- coding: utf-8 -*-
"""R18.1 真实浏览器验收（Chrome DevTools Protocol，纯标准库，无第三方依赖）。

只做「打开本机 http 服务上的页面 -> 真实操作 -> 读浏览器算出来的结果 -> 截图」，
不做任何推测：所有结论都来自 computed style / DOM 实测值 / PNG 像素统计。

覆盖（对应任务书阶段 C）：
  配装  空槽剪影 11 个（src / naturalWidth / 像素白底黑剪影占比）、装备选中后换成真实物品图标、
        卸下后恢复剪影、已装备物品悬停提示的文字颜色与框内位置；
  弹药  BALLISTICS graph 散点图坐标轴文字 / 悬停提示 / 图例颜色，弹药详情弹窗标题栏完整文字；
  模拟  目标护甲与插板下拉的 optgroup 分组 / 顺序 / 兼容过滤 / Boss 装备池约束。

用法：
    python tools/r181_accept.py --port 8801 --out docs/ui-windows-xp/r18.1
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import socket
import struct
import subprocess
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
]


# ------------------------------------------------------------------ WebSocket
class WS:
    """够用的 WebSocket 客户端（文本帧 + 分片 + ping/pong）。"""

    def __init__(self, url, timeout=60):
        u = urllib.parse.urlparse(url)
        self.sock = socket.create_connection((u.hostname, u.port), timeout=timeout)
        self.sock.settimeout(timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        req = ("GET %s HTTP/1.1\r\nHost: %s:%d\r\nUpgrade: websocket\r\n"
               "Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\n"
               "Sec-WebSocket-Version: 13\r\n\r\n" % (u.path, u.hostname, u.port, key))
        self.sock.sendall(req.encode())
        self.f = self.sock.makefile("rb")
        while True:
            line = self.f.readline()
            if line in (b"\r\n", b"\n", b""):
                break

    def _read(self, n):
        out = b""
        while len(out) < n:
            chunk = self.f.read(n - len(out))
            if not chunk:
                raise IOError("websocket closed")
            out += chunk
        return out

    def send(self, obj):
        data = json.dumps(obj).encode()
        head = bytearray([0x81])
        ln = len(data)
        if ln < 126:
            head.append(0x80 | ln)
        elif ln < 65536:
            head.append(0x80 | 126)
            head += struct.pack(">H", ln)
        else:
            head.append(0x80 | 127)
            head += struct.pack(">Q", ln)
        mask = os.urandom(4)
        head += mask
        self.sock.sendall(bytes(head) + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def recv(self):
        payload = b""
        while True:
            b1, b2 = self._read(2)
            fin = b1 & 0x80
            opcode = b1 & 0x0F
            masked = b2 & 0x80
            ln = b2 & 0x7F
            if ln == 126:
                ln = struct.unpack(">H", self._read(2))[0]
            elif ln == 127:
                ln = struct.unpack(">Q", self._read(8))[0]
            mask = self._read(4) if masked else None
            chunk = self._read(ln) if ln else b""
            if mask:
                chunk = bytes(c ^ mask[i % 4] for i, c in enumerate(chunk))
            if opcode == 0x9:
                self.sock.sendall(bytes([0x8A, 0x80]) + os.urandom(4))
                continue
            if opcode == 0x8:
                raise IOError("websocket closed by peer")
            payload += chunk
            if fin:
                return payload.decode("utf-8", "replace")


class CDP:
    def __init__(self, ws_url):
        self.ws = WS(ws_url)
        self.nid = 0
        self.console = []
        self.requests = []

    def call(self, method, timeout=60, **params):
        self.nid += 1
        mid = self.nid
        self.ws.send({"id": mid, "method": method, "params": params})
        deadline = time.time() + timeout
        while time.time() < deadline:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError("%s -> %s" % (method, msg["error"]))
                return msg.get("result", {})
            self._track(msg)
        raise TimeoutError(method)

    def _track(self, msg):
        m = msg.get("method")
        p = msg.get("params") or {}
        if m == "Runtime.consoleAPICalled" and p.get("type") in ("error", "assert"):
            self.console.append({"type": p.get("type"),
                                 "text": " ".join(str(a.get("value", a.get("description", "")))
                                                  for a in (p.get("args") or []))[:400]})
        elif m == "Runtime.exceptionThrown":
            d = p.get("exceptionDetails") or {}
            self.console.append({"type": "exception",
                                 "text": (str(d.get("text", "")) + " " +
                                          str((d.get("exception") or {}).get("description", "")))[:500]})
        elif m == "Log.entryAdded":
            e = p.get("entry") or {}
            if e.get("level") == "error" and e.get("source") != "network":
                self.console.append({"type": "log", "text": str(e.get("text", ""))[:400]})
        elif m == "Network.requestWillBeSent":
            u = (p.get("request") or {}).get("url", "")
            if u and not u.startswith("data:") and not u.startswith("blob:"):
                self.requests.append({"url": u[:300]})

    def drain(self, seconds=0.4):
        """把还在路上的事件读干净（事件只在 recv 里被跟踪）。"""
        self.ws.sock.settimeout(seconds)
        try:
            while True:
                msg = json.loads(self.ws.recv())
                self._track(msg)
        except Exception:
            pass
        finally:
            self.ws.sock.settimeout(60)

    def eval(self, expr, timeout=60, await_promise=False):
        r = self.call("Runtime.evaluate", timeout=timeout, expression=expr,
                      returnByValue=True, awaitPromise=await_promise, userGesture=True)
        if r.get("exceptionDetails"):
            raise RuntimeError("JS 异常：%s" %
                               json.dumps(r["exceptionDetails"], ensure_ascii=False)[:700])
        return r.get("result", {}).get("value")

    def mouse(self, x, y):
        self.call("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y,
                  button="none", clickCount=0)
        time.sleep(0.15)

    def click_at(self, x, y):
        self.call("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y,
                  button="left", clickCount=1)
        self.call("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y,
                  button="left", clickCount=1)
        time.sleep(0.35)

    def shot(self, path, clip=None):
        p = {"format": "png", "captureBeyondViewport": False}
        if clip:
            p["clip"] = dict(clip, scale=1)
        data = base64.b64decode(self.call("Page.captureScreenshot", **p)["data"])
        with open(path, "wb") as f:
            f.write(data)
        return len(data)


# ------------------------------------------------------------------ 浏览器启动
def find_chrome(explicit=None):
    for p in ([explicit] if explicit else []) + CHROME_CANDIDATES:
        if p and os.path.exists(p):
            return p
    raise SystemExit("找不到 Chrome，请用 --chrome 指定路径")


def launch(chrome, port, w, h, profile):
    args = [chrome, "--headless=new", "--remote-debugging-port=%d" % port,
            "--user-data-dir=%s" % profile, "--no-first-run", "--no-default-browser-check",
            "--disable-gpu", "--hide-scrollbars", "--disable-extensions",
            # 本机服务直连：不绕系统代理，否则 headless 会把 127.0.0.1 也送进代理，
            # 页面变成 chrome-error://chromewebdata/。外部请求仍会被 Network 事件记录。
            "--no-proxy-server",
            "--disable-background-networking", "--disable-sync", "--disable-component-update",
            "--force-device-scale-factor=1", "--window-size=%d,%d" % (w, h), "about:blank"]
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ws_url = None
    for _ in range(160):
        time.sleep(0.25)
        try:
            with urllib.request.urlopen("http://127.0.0.1:%d/json/list" % port, timeout=2) as r:
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
        raise SystemExit("Chrome CDP 没有就绪（端口 %d）" % port)
    return proc, ws_url


def wait_ready(cdp, want_url=None, timeout=60):
    """等页面真正可用：URL 已切到目标页 + DOM ready（about:blank 也是 complete，不能只看它）。"""
    end = time.time() + timeout
    while time.time() < end:
        try:
            st = cdp.eval("(function(){return {r:document.readyState,b:(document.body?1:0),"
                          "u:location.href};})()")
            if st and st.get("b") and st.get("r") in ("interactive", "complete"):
                if want_url is None or want_url in (st.get("u") or ""):
                    return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def wait_for(cdp, expr, timeout=40, label=""):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if cdp.eval(expr):
                return True
        except Exception:
            pass
        time.sleep(0.25)
    raise TimeoutError("等待超时：%s（%s）" % (label or expr, expr[:120]))


# ------------------------------------------------------------------ 色彩工具
def parse_rgb(s):
    s = (s or "").strip()
    if s.startswith("rgb"):
        nums = s[s.index("(") + 1:s.rindex(")")].split(",")
        try:
            return tuple(float(x) for x in nums[:3])
        except ValueError:
            return None
    return None


def rel_lum(rgb):
    def ch(v):
        v = v / 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(fg, bg):
    a, b = parse_rgb(fg), parse_rgb(bg)
    if not a or not b:
        return None
    l1, l2 = rel_lum(a), rel_lum(b)
    hi, lo = max(l1, l2), min(l1, l2)
    return round((hi + 0.05) / (lo + 0.05), 2)


# ------------------------------------------------------------------ 页面探针
JS_CELLS = """
JSON.stringify(Array.prototype.map.call(
  document.querySelectorAll('#loadout-workbench .lw-cell'), function (b) {
    var s = b.querySelector('.lw-sil'), ic = b.querySelector('.lw-cell-icon');
    return {slot: b.getAttribute('data-slot'), state: b.getAttribute('data-state'),
            sil: s ? s.getAttribute('src') : null,
            silW: s ? s.naturalWidth : 0,
            silOk: s ? (s.complete && s.naturalWidth > 0) : false,
            icon: ic ? ic.getAttribute('src') : null,
            blend: s ? getComputedStyle(s).mixBlendMode : null};
  }))
"""

JS_SIL_PIXELS = """
(function () {
  var out = [];
  Array.prototype.forEach.call(
    document.querySelectorAll('#loadout-workbench .lw-cell .lw-sil'), function (img) {
    if (!img.complete || !img.naturalWidth) { return; }
    var c = document.createElement('canvas');
    c.width = img.naturalWidth; c.height = img.naturalHeight;
    var x = c.getContext('2d');
    x.drawImage(img, 0, 0);
    var d = x.getImageData(0, 0, c.width, c.height).data;
    var white = 0, black = 0, mid = 0, n = d.length / 4;
    for (var i = 0; i < d.length; i += 4) {
      var v = (d[i] + d[i + 1] + d[i + 2]) / 3;
      if (v >= 250) { white++; }
      else if (v <= 8) { black++; }
      else { mid++; }
    }
    var cell = img.closest('.lw-cell');
    out.push({slot: cell ? cell.getAttribute('data-slot') : '?',
              w: c.width, h: c.height,
              whitePct: Math.round(1000 * white / n) / 10,
              blackPct: Math.round(1000 * black / n) / 10,
              midPct: Math.round(1000 * mid / n) / 10});
  });
  return JSON.stringify(out);
})()
"""

JS_TIP = """
(function () {
  var t = document.querySelector('.loadout-workbench .lw-tip');
  if (!t || t.style.display === 'none' || !t.textContent.trim()) {
    return JSON.stringify({shown: false});
  }
  var head = t.querySelector('.lw-tip-head'), line = t.querySelector('.lw-tip-line');
  var r = t.getBoundingClientRect();
  return JSON.stringify({
    shown: true,
    headText: head ? head.textContent.slice(0, 80) : null,
    lineText: line ? line.textContent.slice(0, 120) : null,
    headColor: head ? getComputedStyle(head).color : null,
    lineColor: line ? getComputedStyle(line).color : null,
    bg: getComputedStyle(t).backgroundColor,
    rect: {x: Math.round(r.x), y: Math.round(r.y),
           w: Math.round(r.width), h: Math.round(r.height)},
    inViewport: r.x >= -1 && r.y >= -1 && r.right <= innerWidth + 1 && r.bottom <= innerHeight + 1
  });
})()
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8801)
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "ui-windows-xp", "r18.1"))
    ap.add_argument("--chrome", default=None)
    ap.add_argument("--cdp-port", type=int, default=9333)
    ap.add_argument("--json", default=None)
    a = ap.parse_args()
    out_dir = a.out
    os.makedirs(out_dir, exist_ok=True)

    chrome = find_chrome(a.chrome)
    profile = os.path.join(os.environ.get("TEMP", "."), "r181-prof-%d" % os.getpid())
    rep = {"round": "R18.1", "base": "http://127.0.0.1:%d" % a.port,
           "viewports": [], "shots": [], "console": [], "externalRequests": []}

    def shot(cdp, name, clip=None):
        path = os.path.join(out_dir, name)
        n = cdp.shot(path, clip)
        rep["shots"].append({"file": name, "bytes": n})
        return path

    def box_of(cdp, selector):
        return cdp.eval("(function(){var e=document.querySelector(%s);"
                        "if(!e){return null;}var r=e.getBoundingClientRect();"
                        "return {x:r.x,y:r.y,w:r.width,h:r.height};})()"
                        % json.dumps(selector))

    def clip_of(cdp, selector, pad=6, scroll=True):
        """取元素的截图区域。默认先滚到视口中央，否则小视口下常截到一片空白。"""
        if scroll:
            cdp.eval("(function(){var e=document.querySelector(%s);"
                     "if(e){e.scrollIntoView({block:'center'});}})()" % json.dumps(selector))
            time.sleep(0.35)
        b = box_of(cdp, selector)
        if not b or b["w"] < 2 or b["h"] < 2:
            return None
        vw, vh = cdp.eval("[innerWidth, innerHeight]")
        x = max(0, b["x"] - pad)
        y = max(0, b["y"] - pad)
        return {"x": x, "y": y,
                "width": max(2, min(b["w"] + pad * 2, vw - x)),
                "height": max(2, min(b["h"] + pad * 2, vh - y))}

    proc = None
    try:
        proc, ws_url = launch(chrome, a.cdp_port, 1920, 1080, profile)
        cdp = CDP(ws_url)
        for m in ("Page.enable", "Runtime.enable", "Network.enable", "Log.enable"):
            cdp.call(m)

        for (vw, vh, tagv) in ((1920, 1080, "1920"), (1264, 705, "1264")):
            cdp.call("Emulation.setDeviceMetricsOverride", width=vw, height=vh,
                     deviceScaleFactor=1, mobile=False)
            cdp.call("Page.navigate", url="http://127.0.0.1:%d/index.html" % a.port)
            wait_ready(cdp, want_url="index.html")
            cdp.eval("try{localStorage.clear()}catch(e){}")
            cdp.call("Page.reload")
            wait_ready(cdp, want_url="index.html")
            time.sleep(1.3)
            vp = {"w": vw, "h": vh, "tag": tagv}

            vp["noHScroll"] = cdp.eval("document.documentElement.scrollWidth <= "
                                       "document.documentElement.clientWidth + 1")

            # ---------------- 配装：空槽剪影 ----------------
            cdp.eval("document.querySelector('[data-view=\"loadout\"]').click()")
            wait_for(cdp, "!!document.querySelector('#loadout-workbench .lw-cell')",
                     label="配装卡片板")
            time.sleep(0.9)
            vp["cellsEmpty"] = json.loads(cdp.eval(JS_CELLS))
            vp["silPixels"] = json.loads(cdp.eval(JS_SIL_PIXELS))
            shot(cdp, "%s-01-loadout-empty.png" % tagv,
                 clip_of(cdp, "#loadout-workbench .lw-board"))

            # ---------------- 配装：装备 / 提示 / 卸下 ----------------
            row = cdp.eval("""
              (function(){
                var r=document.querySelector('#loadout-workbench .tbl-row');
                if(!r){return null;}
                var b=r.getBoundingClientRect();
                var nm=r.querySelector('.tbl-cell[data-key=n]');
                return {id:r.dataset.id, x:b.x+b.width/2, y:b.y+b.height/2,
                        name:nm?nm.textContent:null};
              })()""")
            if row:
                cdp.click_at(row["x"], row["y"])
                time.sleep(0.9)
                vp["equippedName"] = row.get("name")
                vp["afterEquip"] = json.loads(cdp.eval(JS_CELLS))
                shot(cdp, "%s-02-loadout-equipped.png" % tagv,
                     clip_of(cdp, "#loadout-workbench .lw-board"))

                # 提示框在配装工作台不同位置都要能正常显示、不被裁切：
                # 逐类锚点真实鼠标移入，收集所有成功弹出的提示，而不是只测第一个。
                tips = []
                for sel in ("#loadout-workbench .lw-node", "#loadout-workbench .lw-src",
                            "#loadout-workbench .lw-plate-cell",
                            "#loadout-workbench .lw-node-group",
                            "#loadout-workbench .lw-ci"):
                    b = box_of(cdp, sel)
                    if not b or b["w"] < 3 or b["h"] < 3:
                        continue
                # 先把锚点滚进视口，否则小视口下 hover 落在屏幕外，提示根本不会触发
                    cdp.eval("(function(){var e=document.querySelector(%s);"
                             "if(e){e.scrollIntoView({block:'center'});}})()"
                             % json.dumps(sel))
                    time.sleep(0.25)
                    b = box_of(cdp, sel) or b
                # 真实鼠标移入
                    cdp.mouse(b["x"] + min(b["w"] / 2, 24), b["y"] + b["h"] / 2)
                    time.sleep(0.45)
                    got = json.loads(cdp.eval(JS_TIP))
                    if not got.get("shown"):
                        continue
                    got["anchor"] = sel
                    got["contrastHead"] = contrast(got.get("headColor"), got.get("bg"))
                    got["contrastLine"] = contrast(got.get("lineColor"), got.get("bg"))
                    tips.append(got)
                    if len(tips) == 1:
                        shot(cdp, "%s-03-loadout-tooltip.png" % tagv,
                             clip_of(cdp, "#loadout-workbench .lw-tip", pad=10, scroll=False))
                vp["tooltips"] = tips
                vp["tooltip"] = tips[0] if tips else {"shown": False}

                # 再装一件护甲：插板位的提示是另一类锚点（第一行含装备名），
                # 换个位置复验同一套 lw-tip 配色，顺带看它有没有被侧栏裁切。
                cdp.eval("(function(){var c=document.querySelector("
                         "'#loadout-workbench .lw-cell[data-slot=armor]');"
                         "if(c){c.click();}})()")
                time.sleep(0.6)
                r2 = cdp.eval("""
                  (function(){
                    var r=document.querySelector('#loadout-workbench .tbl-row');
                    if(!r){return null;}var b=r.getBoundingClientRect();
                    return {x:b.x+b.width/2,y:b.y+b.height/2};})()""")
                if r2:
                    cdp.click_at(r2["x"], r2["y"])
                    time.sleep(0.9)
                    vp["armorEquipped"] = json.loads(cdp.eval(JS_CELLS))
                    shot(cdp, "%s-03b-loadout-armor.png" % tagv,
                         clip_of(cdp, "#loadout-workbench .lw-board"))
                    pb = box_of(cdp, "#loadout-workbench .lw-plate-cell")
                    if pb and pb["w"] > 3:
                        cdp.eval("(function(){var e=document.querySelector("
                                 "'#loadout-workbench .lw-plate-cell');"
                                 "if(e){e.scrollIntoView({block:'center'});}})()")
                        time.sleep(0.3)
                        pb = box_of(cdp, "#loadout-workbench .lw-plate-cell") or pb
                        cdp.mouse(pb["x"] + pb["w"] / 2, pb["y"] + pb["h"] / 2)
                        time.sleep(0.5)
                        t2 = json.loads(cdp.eval(JS_TIP))
                        if t2.get("shown"):
                            t2["anchor"] = "#loadout-workbench .lw-plate-cell"
                            t2["contrastHead"] = contrast(t2.get("headColor"), t2.get("bg"))
                            t2["contrastLine"] = contrast(t2.get("lineColor"), t2.get("bg"))
                            vp["tooltips"].append(t2)
                            vp["tooltipPlate"] = t2
                            shot(cdp, "%s-03c-loadout-tip-plate.png" % tagv,
                                 clip_of(cdp, "#loadout-workbench .lw-tip", pad=10, scroll=False))
                    cdp.eval("(function(){var xs=document.querySelectorAll("
                             "'#loadout-workbench .lw-node-x');"
                             "if(xs.length){xs[xs.length-1].click();}})()")
                    time.sleep(0.5)
                cdp.eval("(function(){var t=document.querySelector('.loadout-workbench .lw-tip');"
                         "if(t){t.style.display='none';}})()")

                vp["removeClicked"] = cdp.eval(
                    "(function(){var xs=document.querySelectorAll("
                    "'#loadout-workbench .lw-node-x, #loadout-workbench .lw-ci-x');"
                    "if(!xs.length){return false;}xs[0].click();return true;})()")
                time.sleep(0.8)
                vp["afterRemove"] = json.loads(cdp.eval(JS_CELLS))
                shot(cdp, "%s-04-loadout-removed.png" % tagv,
                     clip_of(cdp, "#loadout-workbench .lw-board"))

            # ---------------- 弹药：BALLISTICS graph ----------------
            cdp.eval("document.querySelector('[data-view=\"ammo\"]').click()")
            time.sleep(0.9)
            cdp.eval("document.querySelector('.am-tab[data-tab=\"graph\"]').click()")
            wait_for(cdp, "!!document.querySelector('.am-graph-svg .am-gdot')", label="散点图")
            time.sleep(1.1)
            vp["graphText"] = json.loads(cdp.eval("""
              (function(){
                var svg=document.querySelector('.am-graph-svg');
                if(!svg){return 'null';}
                var texts=svg.querySelectorAll('text'), out=[], hist={};
                Array.prototype.forEach.call(texts, function(t){
                  var f=getComputedStyle(t).fill;
                  hist[f]=(hist[f]||0)+1;
                  if(out.length<5){out.push({txt:t.textContent.slice(0,20), fill:f});}
                });
                var lg=document.querySelector('.am-graph-lg');
                var note=document.querySelector('.am-graph-note');
                var plot=svg.querySelector('rect');
                var gg=document.querySelector('.am-graph');
                return JSON.stringify({sample:out, fillHistogram:hist, count:texts.length,
                  plotFill: plot?getComputedStyle(plot).fill:null,
                  legendColor: lg?getComputedStyle(lg).color:null,
                  noteColor: note?getComputedStyle(note).color:null,
                  plotAreaBg: gg?getComputedStyle(gg).backgroundColor:null});
              })()"""))
            shot(cdp, "%s-05-ammo-graph.png" % tagv, clip_of(cdp, ".am-graph-stage"))

            gt = {"shown": False}
            dot = cdp.eval("""
              (function(){var g=document.querySelector('.am-graph-svg .am-gdot');
               if(!g){return null;}var r=g.getBoundingClientRect();
               return {x:r.x+r.width/2,y:r.y+r.height/2};})()""")
            if dot:
                cdp.mouse(dot["x"], dot["y"])
                time.sleep(0.7)
                gt = json.loads(cdp.eval("""
                  (function(){
                    var t=document.querySelector('.am-graph-tip');
                    if(!t||t.hidden){return JSON.stringify({shown:false});}
                    var row=t.querySelector('.am-graph-tip-row');
                    var nm=t.querySelector('.am-graph-tip-name');
                    var mt=t.querySelector('.am-graph-tip-meta');
                    return JSON.stringify({shown:true,
                      rowText:(row?row.textContent:'').slice(0,60),
                      nameColor: nm?getComputedStyle(nm).color:null,
                      rowColor: row?getComputedStyle(row).color:null,
                      metaColor: mt?getComputedStyle(mt).color:null,
                      bg: getComputedStyle(t).backgroundColor});
                  })()"""))
                if gt.get("shown"):
                    gt["contrastName"] = contrast(gt.get("nameColor"), gt.get("bg"))
                    gt["contrastMeta"] = contrast(gt.get("metaColor"), gt.get("bg"))
                shot(cdp, "%s-06-ammo-graph-tip.png" % tagv, clip_of(cdp, ".am-graph-stage", scroll=False))
            vp["graphTip"] = gt

            # ---------------- 弹药详情弹窗（多种口径 / 长名称） ----------------
            cdp.eval("document.querySelector('.am-tab[data-tab=\"ballistics\"]').click()")
            time.sleep(0.9)
            modals = []
            for want in ("5.45", "7.62", ".357", "12/70"):
                ok = cdp.eval("""
                  (function(){
                    var rows=document.querySelectorAll('.am-main .tbl-row');
                    for(var i=0;i<rows.length;i++){
                      if((rows[i].textContent||'').indexOf(%s)>=0){ rows[i].click(); return true; }
                    }
                    return false;
                  })()""" % json.dumps(want))
                if not ok:
                    continue
                time.sleep(0.85)
                info = json.loads(cdp.eval("""
                  (function(){
                    var head=document.querySelector('#am-detail .am-modal-head');
                    if(!head){return JSON.stringify({open:false});}
                    var nm=head.querySelector('.am-detail-name');
                    var mt=head.querySelector('.am-detail-meta');
                    var tt=head.querySelector('.am-modal-title');
                    var cs=getComputedStyle(head);
                    return JSON.stringify({open:true,
                      name: nm?nm.textContent:null,
                      nameColor: nm?getComputedStyle(nm).color:null,
                      meta: mt?mt.textContent:null,
                      metaColor: mt?getComputedStyle(mt).color:null,
                      titleColor: tt?getComputedStyle(tt).color:null,
                      headGradient: cs.backgroundImage.slice(0,90)});
                  })()"""))
                if info.get("open"):
                    info["probe"] = want
                    # 标题栏实际是 Luna 蓝渐变，取渐变中段色 (#1e63c8 附近) 做对比度基准
                    info["contrastMeta"] = contrast(info.get("metaColor"), "rgb(30,99,200)")
                    modals.append(info)
                    shot(cdp, "%s-07-ammo-detail-%d.png" % (tagv, len(modals)),
                         clip_of(cdp, "#am-detail .am-modal-head", pad=4))
                cdp.eval("(function(){var x=document.querySelector('#am-detail .am-modal-x');"
                         "if(x){x.click();}})()")
                time.sleep(0.5)
            vp["ammoDetail"] = modals

            # ---------------- 逐发模拟：护甲 / 插板分组 ----------------
            cdp.eval("document.querySelector('.am-tab[data-tab=\"sim\"]').click()")
            wait_for(cdp, "!!document.querySelector('[data-sim=\"armor-pick\"]')", label="模拟器护甲下拉")
            time.sleep(1.2)
            vp["build"] = cdp.eval(
                "(function(){var e=document.querySelector('.am-sim-runhint');"
                "return e?e.textContent.trim().slice(0,110):null;})()")
            vp["armorGroups"] = json.loads(cdp.eval("""
              (function(){
                var s=document.querySelector('[data-sim=armor-pick]');
                if(!s){return 'null';}
                var out=[];
                Array.prototype.forEach.call(s.querySelectorAll('optgroup'), function(g){
                  out.push({label:g.label, n:g.querySelectorAll('option').length});
                });
                var loose=0;
                Array.prototype.forEach.call(s.children, function(c){
                  if(c.tagName==='OPTION'){loose++;}});
                return JSON.stringify({groups:out, total:s.querySelectorAll('option').length,
                  looseOptions:loose});
              })()"""))
            shot(cdp, "%s-08-sim-armor-groups.png" % tagv,
                 clip_of(cdp, "[data-sim=\"armor-pick\"]"))

            # 逐件尝试，直到选到一件「有可换插板位」的护甲（有些护甲只有固定内衬）
            vp["armorPicked"] = cdp.eval("""
              (function(){
                var s=document.querySelector('[data-sim=armor-pick]');
                var opts=[].slice.call(s.querySelectorAll('optgroup option'));
                for(var i=0;i<opts.length;i++){
                  if(!opts[i].value){continue;}
                  s.value=opts[i].value;
                  s.dispatchEvent(new Event('change',{bubbles:true}));
                  var p=document.querySelector('[data-sim=plate-pick]');
                  if(p && p.querySelectorAll('option').length>1){
                    return {id:opts[i].value, text:opts[i].textContent,
                            grp:opts[i].parentNode.label, at:i};
                  }
                }
                return null;
              })()""")
            time.sleep(1.1)
            vp["plateGroups"] = json.loads(cdp.eval("""
              (function(){
                var s=document.querySelector('[data-sim=plate-pick]');
                if(!s){return JSON.stringify({none:true});}
                var out=[];
                Array.prototype.forEach.call(s.querySelectorAll('optgroup'), function(g){
                  out.push({label:g.label, n:g.querySelectorAll('option').length});
                });
                return JSON.stringify({groups:out, total:s.querySelectorAll('option').length,
                  zone:s.dataset.zone,
                  looseOptions:(function(){var c=0;
                    Array.prototype.forEach.call(s.children,function(n){
                      if(n.tagName==='OPTION'){c++;}});return c;})()});
              })()"""))
            shot(cdp, "%s-09-sim-plate-groups.png" % tagv,
                 clip_of(cdp, "[data-sim=\"armor-slots\"]"))

            # 原生 <select> 的展开列表无法直接截图；这里临时把 size 撑开把分组结构拍下来，
            # 拍完立刻还原（只是验收取证手段，不改任何业务状态）。报告里会明确标注这一点。
            for (sel_key, fname) in (("armor-pick", "%s-09b-armor-open.png" % tagv),
                                     ("plate-pick", "%s-09c-plate-open.png" % tagv)):
                opened = cdp.eval("""
                  (function(){
                    var s=document.querySelector('[data-sim=%s]');
                    if(!s){return false;}
                    s.dataset.prevSize = s.getAttribute('size') || '';
                    s.setAttribute('size', '14');
                    return true;
                  })()""" % json.dumps(sel_key))
                if opened:
                    time.sleep(0.3)
                    shot(cdp, fname, clip_of(cdp, "[data-sim=\"%s\"]" % sel_key, pad=8))
                    cdp.eval("""
                      (function(){
                        var s=document.querySelector('[data-sim=%s]');
                        if(!s){return;}
                        if(s.dataset.prevSize){s.setAttribute('size', s.dataset.prevSize);}
                        else{s.removeAttribute('size');}
                        delete s.dataset.prevSize;
                      })()""" % json.dumps(sel_key))
                    time.sleep(0.2)

            boss = cdp.eval("""
              (function(){
                // 目标类型默认是 PMC，必须先把类型切到 Boss，具体目标下拉里才会出现 Boss 列表
                var k=document.querySelector('[data-sim=target-kind]');
                if(!k){return {why:'no kind'};}
                k.value='boss';
                k.dispatchEvent(new Event('change',{bubbles:true}));
                var sel=document.querySelector('[data-sim=target-pick]');
                if(!sel){return {why:'no target-pick'};}
                var opts=Array.prototype.slice.call(sel.options);
                var hit=opts.filter(function(o){return /tagilla/i.test(o.textContent);})[0];
                if(!hit){return {why:'no tagilla', n:opts.length,
                                 names:opts.slice(0,6).map(function(o){return o.textContent;})};}
                sel.value=hit.value; sel.dispatchEvent(new Event('change',{bubbles:true}));
                return {id:hit.value, text:hit.textContent, total:opts.length};
              })()""")
            time.sleep(1.6)
            vp["bossPicked"] = boss
            vp["bossState"] = json.loads(cdp.eval("""
              (function(){
                var a=document.querySelector('[data-sim=armor-pick]');
                var s=document.querySelector('[data-sim=plate-pick]');
                var ag=[], pg=[];
                if(a){Array.prototype.forEach.call(a.querySelectorAll('optgroup'),function(g){
                  ag.push({label:g.label,n:g.querySelectorAll('option').length});});}
                if(s){Array.prototype.forEach.call(s.querySelectorAll('optgroup'),function(g){
                  pg.push({label:g.label,n:g.querySelectorAll('option').length});});}
                var note=document.querySelector('[data-sim=pool-note]');
                return JSON.stringify({armorGroups:ag, plateGroups:pg,
                  armorTotal:a?a.querySelectorAll('option').length:0,
                  plateTotal:s?s.querySelectorAll('option').length:0,
                  note:note?note.textContent.slice(0,160):null});
              })()"""))
            shot(cdp, "%s-10-sim-boss.png" % tagv, clip_of(cdp, "#am-workbench"))

            vp["noHScroll2"] = cdp.eval("document.documentElement.scrollWidth <= "
                                        "document.documentElement.clientWidth + 1")
            rep["viewports"].append(vp)

        cdp.drain(0.6)
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

    out = a.json or os.path.join(out_dir, "_accept.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)
    print("报告：", os.path.relpath(out, ROOT))
    print("截图 %d 张 / 控制台错误 %d 条 / 外部请求 %d 条"
          % (len(rep["shots"]), len(rep["console"]), len(rep["externalRequests"])))


if __name__ == "__main__":
    main()
