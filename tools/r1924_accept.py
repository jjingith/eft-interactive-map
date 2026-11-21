# -*- coding: utf-8 -*-
"""R19.16 武器槽位布局校准器 —— 真实浏览器验收（拖动 / 撤销 / 保存 / 重载 / 条件槽位）。

用法：python tools/r1924_accept.py --port 9640
输出：docs/r19.16-calibrator-audit/browser-check.json + screenshots/
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r181_accept import CDP, find_chrome, launch, wait_ready  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "r19.16-calibrator-audit")
BASE = "http://127.0.0.1:8787"

GUNS = [
    ("ash12", "ASh-12"),
    ("axmc", "AXMC"),
    ("m10", "TRG M10"),
    ("marlin", "MXLR"),
    ("ak74n", "AK-74N"),
    ("m4a1", "柯尔特 M4A1"),
    ("sa58", "DS Arms SA-58"),
    ("sv98", "SV-98"),
]


def shot(cdp, name, folder="screenshots"):
    d = os.path.join(OUT, folder)
    os.makedirs(d, exist_ok=True)
    data = base64.b64decode(cdp.call("Page.captureScreenshot", format_="png",
                                     captureBeyondViewport=False)["data"])
    with open(os.path.join(d, name), "wb") as f:
        f.write(data)
    return name


def snap(cdp):
    """读取校准器当前状态（枪 / 槽位 / 坐标 / 选中 / 未保存）。"""
    raw = cdp.eval(r"""(function(){
      var g = document.getElementById('cal-grid');
      if (!g) return JSON.stringify({ok:false});
      var cards = [].slice.call(g.querySelectorAll('.cal-card'));
      var info = (document.getElementById('cal-info')||{textContent:''}).textContent;
      return JSON.stringify({
        ok: true,
        gun: (document.getElementById('cal-msg')||{textContent:''}).textContent,
        rows: getComputedStyle(g).gridTemplateRows.split(' ').length,
        cards: cards.map(function(c){
          return { key: c.getAttribute('data-key'), slot: c.getAttribute('data-slot'),
                   row: +c.getAttribute('data-row'), col: +c.getAttribute('data-col'),
                   moved: !!c.querySelector('.tag.moved'),
                   body: c.getAttribute('data-body')==='1',
                   text: (c.textContent||'').replace(/\s+/g,' ').trim().slice(0,40),
                   x: Math.round(c.getBoundingClientRect().x), y: Math.round(c.getBoundingClientRect().y),
                   w: Math.round(c.getBoundingClientRect().width), h: Math.round(c.getBoundingClientRect().height) };
        }),
        msg: (document.getElementById('cal-msg')||{textContent:''}).textContent,
        dirty: /未保存修改 有/.test(info),
        info: info.replace(/\s+/g,' ').slice(0,300)
      });})()""")
    return json.loads(raw) if raw else {"ok": False}


def find_card(cdp, suffix=None, row=None, col=None):
    for c in (snap(cdp).get("cards") or []):
        if suffix and not (c["slot"] or "").endswith(suffix):
            continue
        if row is not None and c["row"] != row:
            continue
        if col is not None and c["col"] != col:
            continue
        return c
    return None


def cell_center(cdp, row, col):
    raw = cdp.eval("""(function(){
      var c=document.querySelector('.cal-gcell[data-row="%d"][data-col="%d"]');
      if(!c) return null;
      var r=c.getBoundingClientRect();
      return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2});})()""" % (row, col))
    return json.loads(raw) if raw and raw != "null" else None


def drag(cdp, card, row, col):
    """把卡片拖到 r{row}c{col}（显示坐标）。"""
    t = cell_center(cdp, row, col)
    if not t:
        return False
    sx, sy = card["x"] + card["w"] / 2, card["y"] + card["h"] / 2
    cdp.call("Input.dispatchMouseEvent", type="mousePressed", x=sx, y=sy, button="left", clickCount=1)
    for i in range(1, 6):
        cdp.call("Input.dispatchMouseEvent", type="mouseMoved",
                 x=sx + (t["x"] - sx) * i / 5.0, y=sy + (t["y"] - sy) * i / 5.0, button="left")
    cdp.call("Input.dispatchMouseEvent", type="mouseMoved", x=t["x"], y=t["y"], button="left")
    time.sleep(0.25)
    cdp.call("Input.dispatchMouseEvent", type="mouseReleased", x=t["x"], y=t["y"], button="left", clickCount=1)
    time.sleep(0.5)
    return True


def pick_gun(cdp, needle):
    cdp.eval("""(function(){var s=document.getElementById('cal-search');
      if(!s) return false; s.value=%s;
      s.dispatchEvent(new Event('input',{bubbles:true})); return true;})()"""
             % json.dumps(needle, ensure_ascii=False))
    time.sleep(0.5)
    raw = cdp.eval("""(function(){
      var li=document.querySelector('#cal-gunlist li[data-gun]');
      if(!li) return null;
      li.click();
      return li.getAttribute('data-gun');})()""")
    time.sleep(0.6)
    # 未保存修改会弹非阻塞选择框：自动化统一走「丢弃并切换」
    cdp.eval("""(function(){
      var b=document.querySelector('#cal-modal button[data-choice="drop"]') ||
            document.querySelector('#cal-modal button[data-choice="ok"]') ||
            document.querySelector('#cal-modal button[data-choice="go"]');
      if(b){ b.click(); return true; } return false;})()""")
    time.sleep(1.0)
    return raw


def preset_count(cdp):
    raw = cdp.eval(r"""(function(){
      var sel=document.getElementById('cal-preset-sel');
      return sel ? sel.options.length : 0;})()""")
    return raw or 0


def switch_preset(cdp, index):
    raw = cdp.eval("""(function(idx){
      var sel=document.getElementById('cal-preset-sel');
      if(!sel || idx >= sel.options.length) return null;
      sel.selectedIndex = idx;
      sel.dispatchEvent(new Event('change',{bubbles:true}));
      return sel.options[idx].text;})(%d)""" % int(index))
    time.sleep(1.2)
    return raw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9640)
    args = ap.parse_args()

    prof = os.path.join(os.environ.get("TEMP", "."), "r1924prof_%d" % args.port)
    proc, ws = launch(find_chrome(), args.port, 1920, 919, prof)
    rep = {"generatedFor": "R19.16", "guns": {}, "flow": {}, "console": []}
    try:
        cdp = CDP(ws)
        for m in ("Page.enable", "Runtime.enable", "Log.enable", "Network.enable"):
            cdp.call(m)
        cdp.call("Network.setCacheDisabled", cacheDisabled=True)
        cdp.call("Emulation.setDeviceMetricsOverride", width=1920, height=919,
                 deviceScaleFactor=1, mobile=False)
        cdp.call("Page.navigate", url=BASE + "/index.html?layoutCalibrator=1")
        wait_ready(cdp, want_url="index.html")
        time.sleep(3.0)
        rep["build"] = cdp.eval("(document.getElementById('cal-ver')||{textContent:''}).textContent")
        rep["overlayVisible"] = cdp.eval("!!document.getElementById('cal-overlay')")
        shot(cdp, "A-calibrator-main-1920.png")

        # ---------- 各枪真实槽位快照 ----------
        for key, needle in GUNS:
            gid = pick_gun(cdp, needle)
            s = snap(cdp)
            rep["guns"][key] = {
                "gunId": gid,
                "slotCount": len(s.get("cards") or []),
                "rows": s.get("rows"),
                "cards": [
                    {"slot": c["slot"], "row": c["row"], "col": c["col"], "body": c["body"]}
                    for c in (s.get("cards") or [])
                ],
                "presets": preset_count(cdp),
            }
            shot(cdp, "B-%s-calibrator-1920.png" % key)

        # ---------- 拖动 / 撤销 / 重做（AK-74N 燕尾槽基座） ----------
        pick_gun(cdp, "AK-74N")
        before = snap(cdp)
        card = find_card(cdp, suffix="mod_mount_000")
        rep["flow"]["dragSource"] = card
        drag(cdp, card, 5, 1)
        after = snap(cdp)
        moved = find_card(cdp, suffix="mod_mount_000")
        rep["flow"]["afterDrag"] = {"row": moved and moved["row"], "col": moved and moved["col"],
                                    "dirty": after.get("dirty"), "msg": after.get("msg")}
        shot(cdp, "C-after-drag-1920.png")

        cdp.eval("document.getElementById('cal-undo').click()")
        time.sleep(0.6)
        un = find_card(cdp, suffix="mod_mount_000")
        rep["flow"]["afterUndo"] = {"row": un and un["row"], "col": un and un["col"]}

        cdp.eval("document.getElementById('cal-redo').click()")
        time.sleep(0.6)
        re = find_card(cdp, suffix="mod_mount_000")
        rep["flow"]["afterRedo"] = {"row": re and re["row"], "col": re and re["col"]}

        # 拖回原位（保持数据干净）
        drag(cdp, find_card(cdp, suffix="mod_mount_000"), 2, 8)

        # ---------- 本体保护区：拖到 r3c6 必须被拒绝 ----------
        card = find_card(cdp, suffix="mod_charge")
        drag(cdp, card, 3, 6)
        s2 = snap(cdp)
        rep["flow"]["bodyReject"] = {
            "msg": s2.get("msg"),
            "rejected": "本体" in (s2.get("msg") or "") or "不允许" in (s2.get("msg") or ""),
            "chargePos": (find_card(cdp, suffix="mod_charge") or {}).get("row"),
        }

        # ---------- 交换：r2c8 基座 ↔ r2c9 拉机柄 ----------
        a = find_card(cdp, suffix="mod_mount_000")
        drag(cdp, a, 2, 9)
        s3 = snap(cdp)
        m8 = find_card(cdp, suffix="mod_mount_000")
        c9 = find_card(cdp, suffix="mod_charge")
        rep["flow"]["swap"] = {
            "mount": {"row": m8 and m8["row"], "col": m8 and m8["col"]},
            "charge": {"row": c9 and c9["row"], "col": c9 and c9["col"]},
            "msg": s3.get("msg"),
            "allSlotsKept": len(s3.get("cards") or []) == len(before.get("cards") or []),
        }
        # 交换回来
        drag(cdp, find_card(cdp, suffix="mod_mount_000"), 2, 9)

        # ---------- 条件子槽位：切换预设 ----------
        pick_gun(cdp, "DS Arms SA-58")
        base_slots = len(snap(cdp).get("cards") or [])
        preset_names = cdp.eval("""(function(){var s=document.getElementById('cal-preset-sel');
          return s?[].slice.call(s.options).map(function(o){return o.text;}):[];})()""") or []
        switched = None
        if len(preset_names) > 1:
            switched = switch_preset(cdp, 1)
        after_slots = len(snap(cdp).get("cards") or [])
        rep["flow"]["conditional"] = {
            "gun": "SA-58", "presetNames": preset_names, "switchedTo": switched,
            "slotsBefore": base_slots, "slotsAfter": after_slots,
            "changed": base_slots != after_slots
        }
        shot(cdp, "D-conditional-preset-1920.png")

        # ---------- 坐标输入 + 保存 ----------
        pick_gun(cdp, "AK-74N")
        card = find_card(cdp, suffix="mod_mount_000")
        cdp.eval("""(function(){
          var c=document.querySelector('.cal-card[data-key=%s]'); if(c) c.click();})()"""
                 % json.dumps(card["key"]))
        time.sleep(0.5)
        cdp.eval("""(function(){
          var r=document.getElementById('cal-in-row'), c=document.getElementById('cal-in-col');
          if(!r||!c) return false;
          r.value='5'; c.value='2';
          var btns=[].slice.call(document.querySelectorAll('#cal-slots button'));
          for(var i=0;i<btns.length;i++){ if(btns[i].textContent.indexOf('应用')>=0){ btns[i].click(); return true; }}
          return false;})()""")
        time.sleep(0.7)
        rep["flow"]["coordInput"] = {
            "movedTo": (find_card(cdp, suffix="mod_mount_000") or {}),
            "msg": snap(cdp).get("msg")
        }
        shot(cdp, "E-coord-input-1920.png")

        cdp.eval("document.getElementById('cal-save').click()")
        time.sleep(1.2)
        rep["flow"]["afterSave"] = {"msg": snap(cdp).get("msg"), "dirty": snap(cdp).get("dirty")}

        # 文件侧验证（同一进程 API）
        rep["flow"]["fileAfterSave"] = json.loads(cdp.eval(
            "fetch('/api/layout-calibration').then(function(r){return r.json();})") or "{}") \
            if False else None
        raw = cdp.eval("""(async function(){
          var r = await fetch('/api/layout-calibration');
          return JSON.stringify(await r.json());})()""")
        time.sleep(0.8)
        # async eval 通过 CDP 返回 Promise 结果需要 awaitPromise；这里改用同步方式拿文件摘要
        file_state = cdp.eval("""(function(){
          var x=new XMLHttpRequest(); x.open('GET','/api/layout-calibration',false); x.send();
          try{ var d=JSON.parse(x.responseText); return JSON.stringify({ok:d.ok, summary:d.summary,
            ak:(d.data.guns['5644bd2b4bdc2d3b4c8b4572']||{}).slots||{},
            backup:d.backup}); }catch(e){ return JSON.stringify({err:String(e)}); }})()""")
        rep["flow"]["fileAfterSave"] = json.loads(file_state or "{}")

        # ---------- 刷新后重载 ----------
        cdp.call("Page.navigate", url=BASE + "/index.html?layoutCalibrator=1")
        wait_ready(cdp, want_url="index.html")
        time.sleep(3.0)
        pick_gun(cdp, "AK-74N")
        after_reload = find_card(cdp, suffix="mod_mount_000")
        rep["flow"]["afterReload"] = {
            "row": after_reload and after_reload["row"],
            "col": after_reload and after_reload["col"],
            "movedTag": after_reload and after_reload["moved"],
            "msg": snap(cdp).get("msg")
        }
        shot(cdp, "F-after-reload-1920.png")

        # ---------- 导入无效 JSON：拒绝且不覆盖 ----------
        rep["flow"]["importReject"] = json.loads(cdp.eval("""(function(){
          var x=new XMLHttpRequest(); x.open('POST','/api/layout-calibration',false);
          x.setRequestHeader('Content-Type','application/json');
          x.send(JSON.stringify({action:'import', data:{schemaVersion:99, guns:{}}}));
          try{ var d=JSON.parse(x.responseText); return JSON.stringify({ok:d.ok, err:d.error}); }
          catch(e){ return JSON.stringify({err:String(e)}); }})()""") or "{}")

        # ---------- 1384 视口 ----------
        cdp.call("Emulation.setDeviceMetricsOverride", width=1384, height=805,
                 deviceScaleFactor=1, mobile=False)
        time.sleep(1.0)
        rep["viewports"] = {"1384x805": snap(cdp)}
        shot(cdp, "G-calibrator-1384x805.png")
        cdp.call("Emulation.setDeviceMetricsOverride", width=1920, height=919,
                 deviceScaleFactor=1, mobile=False)

        # ---------- 普通页面不得出现校准器调试元素 ----------
        cdp.call("Page.navigate", url=BASE + "/index.html")
        wait_ready(cdp, want_url="index.html")
        time.sleep(3.0)
        rep["normalPage"] = json.loads(cdp.eval("""(function(){
          return JSON.stringify({
            overlay: !!document.getElementById('cal-overlay'),
            calGrid: document.querySelectorAll('.cal-grid, .cal-gcell, .cal-card').length,
            gridlines: document.querySelectorAll('.cal-rowlab, .cal-collab').length,
            gunCanvas: !!document.getElementById('gw-tree'),
            ghost: document.querySelectorAll('[data-ghost], .gw-cell-ghost').length,
            connectors: document.querySelectorAll('.gw-canvas-links').length
          });})()"""))
        shot(cdp, "H-normal-page-1920.png")

        rep["console"] = [e for e in (getattr(cdp, "logs", []) or [])][:20]
    finally:
        proc.terminate()

    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "browser-check.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    print("overlay:", rep.get("overlayVisible"), "|", rep.get("build"))
    for k, v in rep["guns"].items():
        print(" gun", k, v.get("slotCount"), "slots, rows", v.get("rows"), "presets", v.get("presets"))
    for k, v in rep["flow"].items():
        if isinstance(v, dict):
            print(" flow", k, json.dumps({kk: vv for kk, vv in v.items() if kk != "cards"},
                                         ensure_ascii=False)[:220])
    print(" normalPage", rep.get("normalPage"))
    print("wrote", path)


if __name__ == "__main__":
    main()
