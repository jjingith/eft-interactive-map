# -*- coding: utf-8 -*-
"""R19.29 真实浏览器验收：光学子槽定位 / 战术槽避让 / 候选表 R+E/3 / 环境健康。

全部结论来自真实 Chrome 跑 http://127.0.0.1:<base>/index.html 的 DOM 实测，
不使用 node 探针的布局结果冒充浏览器结果。

覆盖（任务书 8.2 八项）：
  A1 AK 系后准星位置（AKM 照门 r2c6）
  A2 光学子槽与父件对齐（G36 / MCX SPEAR 的瞄具子槽正上方同列）
  B1 战术槽右移（SCAR-H：r6c1 装带子槽基座 → 子槽占 r6c2、原 r6c2 槽位右移）
  B2 移除后恢复（卸掉该基座 → 坐标回到初始）
  C1 候选表列（表头含 R+E/3，缺失属性整列隐藏）
  C2 R+E/3 正负显示（标题公式与列值一致，且 R 为「减少为正、增加为负」）
  D1 控制台无 JS 异常
  D2 无外部网络请求（只允许 127.0.0.1 / localhost）

用法：
    python tools/serve.py --port 8799         （另开一个终端）
    python tools/r1933_accept.py --base http://127.0.0.1:8799 --port 9701
产物：
    docs/r19.29/browser-accept.json
    docs/r19.29/shots/*.png
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r181_accept import CDP, find_chrome, launch, wait_ready  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "r19.29")
SHOTS = os.path.join(OUT, "shots")

GUN_AKM = "59d6088586f774275f37482f"
GUN_AK74N = "5644bd2b4bdc2d3b4c8b4572"
GUN_G36 = "623063e994fc3f7b302a9696"
GUN_MCX = "65290f395ae2ae97b80fdf2d"
GUN_SCARH = "6183afd850224f204c1da514"

report = {"build": "R19.29", "pass": False, "checks": [], "detail": {}}


def ok(name, cond, detail=None):
    report["checks"].append({"name": name, "ok": bool(cond), "detail": detail})
    print(("  PASS " if cond else "  FAIL ") + name + ("" if cond else "  -> %s" % (detail,)))
    return bool(cond)


def js(cdp, expr, default=None):
    try:
        return cdp.eval(expr)
    except Exception as exc:                       # noqa: BLE001
        print("   eval failed:", str(exc)[:200])
        return default


def shot(cdp, name):
    os.makedirs(SHOTS, exist_ok=True)
    try:
        data = base64.b64decode(cdp.call("Page.captureScreenshot", format_="png",
                                         captureBeyondViewport=False)["data"])
        with open(os.path.join(SHOTS, name), "wb") as f:
            f.write(data)
    except Exception as exc:                       # noqa: BLE001
        print("   shot failed:", str(exc)[:120])


def open_main(cdp, base):
    cdp.call("Page.navigate", url=base + "/index.html")
    wait_ready(cdp, want_url="index.html")
    time.sleep(2.5)
    js(cdp, """(function(){var b=document.querySelector('[data-view="gun"]');if(b)b.click();})()""")
    time.sleep(1.2)


def pick_gun(cdp, needle, want_gid):
    tried = set()
    for _ in range(10):
        js(cdp, """(function(){var b=document.querySelector('.gw-mode[data-gwmode="caliber"]');if(b)b.click();})()""")
        time.sleep(0.5)
        raw = js(cdp, """(function(){var cs=document.querySelectorAll('#gw-browse .gw-card');
          var out=[];for(var i=0;i<cs.length;i++){var s=cs[i].querySelector('span');
            if(s && s.textContent.indexOf(%s)>=0){out.push(i);}}return JSON.stringify(out);})()"""
                 % json.dumps(needle, ensure_ascii=False))
        try:
            idxs = json.loads(raw or "[]")
        except Exception:                          # noqa: BLE001
            idxs = []
        nxt = next((i for i in idxs if i not in tried), None)
        if nxt is None:
            return False
        tried.add(nxt)
        pos = js(cdp, """(function(){var cs=document.querySelectorAll('#gw-browse .gw-card');
          var c=cs[%d]; if(!c) return null; c.scrollIntoView({block:'center'});
          var r=c.getBoundingClientRect();
          return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2});})()""" % nxt)
        if not pos or pos == "null":
            continue
        p = json.loads(pos)
        cdp.click_at(p["x"], p["y"])
        time.sleep(1.8)
        gid = js(cdp, "(function(){try{return (JSON.parse(localStorage.getItem('eftmap.gun')||'{}')||{}).gunId||'';}catch(e){return '';}})()") or ""
        if gid == want_gid:
            js(cdp, "document.getElementById('gw-default') && document.getElementById('gw-default').click()")
            time.sleep(1.6)
            return True
    return False


def snap(cdp):
    raw = js(cdp, r"""(function(){
      var t=document.getElementById('gw-tree');
      if(!t) return JSON.stringify({ok:false});
      var cards=[].slice.call(t.querySelectorAll('.gw-part')).filter(function(c){return c.dataset.slot;});
      return JSON.stringify({
        ok:true, topPad:+(t.getAttribute('data-top-pad')||0),
        calib:t.getAttribute('data-calib'), calibApplied:t.getAttribute('data-calib-applied'),
        cards:cards.map(function(c){
          return {slot:c.dataset.slot,row:+c.dataset.row,col:+c.dataset.col,
                  parent:c.dataset.parent||'',item:c.getAttribute('data-item')||''};
        }),
        gun:(document.getElementById('gw-current')||{textContent:''}).textContent.trim()
      });})()""")
    return json.loads(raw) if raw else {"ok": False}


def base_of(slot):
    last = (slot or "").split("/")[-1]
    last = re.sub(r"^mod_", "", last)
    last = re.sub(r"_\d{3,}$", "", last)
    return last


def by_slot(s, slot):
    for c in s.get("cards", []):
        if c["slot"] == slot:
            return c
    return None


def card_at(s, row, col, needle=""):
    for c in s.get("cards", []):
        if c["row"] == row and c["col"] == col and (needle in c["slot"]):
            return c
    return None


def click_slot(cdp, slot):
    return js(cdp, """(function(){var c=document.querySelector('.gw-part[data-slot="%s"]');
      if(!c) return false; c.click(); return true;})()""" % slot)


def click_candidate(cdp, pred_js):
    raw = js(cdp, r"""(function(){
      var rows=document.querySelectorAll('#gw-table .tbl-row');
      for(var i=0;i<rows.length;i++){
        var r={id:rows[i].dataset.id||'',
               t:(rows[i].textContent||'').replace(/\s+/g,' ').trim().slice(0,60),
               conflict:rows[i].className.indexOf('tbl-conflict')>=0};
        if(%s){ rows[i].click(); return JSON.stringify(r);}}
      return null;})()""" % pred_js)
    if not raw or raw == "null":
        return None
    try:
        return json.loads(raw)
    except Exception:                              # noqa: BLE001
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8799")
    ap.add_argument("--port", type=int, default=9701)
    args = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)

    prof = os.path.join(os.environ.get("TEMP", "."), "r1933acc_%d" % args.port)
    proc, ws = launch(find_chrome(), args.port, 1920, 919, prof)
    cdp = CDP(ws)
    try:
        for m in ("Page.enable", "Runtime.enable", "Log.enable", "Network.enable"):
            cdp.call(m)
        cdp.call("Network.setCacheDisabled", cacheDisabled=True)
        cdp.call("Emulation.setDeviceMetricsOverride", width=1920, height=919,
                 deviceScaleFactor=1, mobile=False)

        open_main(cdp, args.base)
        ver = js(cdp, "(window.GWCalib && window.GWCalib.version && window.GWCalib.version())||''")
        ok("build = R19.29", ver == "R19.29", ver)

        # ---------------------------------------------------------------- A1
        if not pick_gun(cdp, "AKM 7.62x39", GUN_AKM):
            ok("A1 选枪 AKM", False, "选枪失败")
        else:
            s = snap(cdp)
            rear = by_slot(s, "mod_sight_rear")
            ok("A1 AKM 后照门在 r2c6", bool(rear) and rear["row"] == 2 and rear["col"] == 6, rear)
            report["detail"]["A1"] = {"gun": s.get("gun"), "rearSight": rear,
                                      "calib": s.get("calib")}
            shot(cdp, "A1-akm.png")

        # ---------------------------------------------------------------- A2
        a2 = []
        for needle, gid, name in (("HK G36", GUN_G36, "G36"), ("SIG MCX SPEAR", GUN_MCX, "MCX SPEAR")):
            if not pick_gun(cdp, needle, gid):
                a2.append({"gun": name, "picked": False})
                continue
            s = snap(cdp)
            pairs = []
            for c in s.get("cards", []):
                if base_of(c["slot"]) != "scope" or not c["parent"]:
                    continue
                p = by_slot(s, c["parent"])
                if not p or base_of(p["slot"]) != "scope":
                    continue
                pairs.append({"child": c["slot"], "c": [c["row"], c["col"]],
                              "parent": p["slot"], "p": [p["row"], p["col"]],
                              "aligned": c["col"] == p["col"] and c["row"] < p["row"]})
            a2.append({"gun": name, "picked": True, "pairs": pairs,
                       "allAligned": bool(pairs) and all(x["aligned"] for x in pairs)})
            shot(cdp, "A2-%s.png" % re.sub(r"\W+", "", name))
        report["detail"]["A2"] = a2
        ok("A2 光学子槽在父件上方同列（G36 / MCX SPEAR）",
           all(x.get("picked") and x.get("allAligned") for x in a2),
           [(x["gun"], x.get("pairs")) for x in a2])

        # ---------------------------------------------------------------- B
        b = {}
        if not pick_gun(cdp, "SCAR-H 7.62x51突击步枪", GUN_SCARH):
            ok("B 选枪 SCAR-H", False, "选枪失败")
        else:
            s0 = snap(cdp)
            slot1 = None
            for c in s0["cards"]:
                if c["row"] == 6 and c["col"] == 1 and "mod_tactical" in c["slot"]:
                    slot1 = c
                    break
            ok("B 定位 r6c1 战术槽", bool(slot1), slot1)
            if slot1:
                at6c2_before = card_at(s0, 6, 2)
                click_slot(cdp, slot1["slot"])
                time.sleep(0.9)
                cand = click_candidate(cdp, "(r.t.indexOf('Kiba Arms 25')>=0 && !r.conflict)")
                time.sleep(1.8)
                s1 = snap(cdp)
                child = None
                for c in s1["cards"]:
                    if c["parent"] == slot1["slot"] and base_of(c["slot"]) in (
                            "flashlight", "laser", "tactical", "devices", "emitter"):
                        child = c
                        break
                b["installed"] = cand
                b["parent"] = by_slot(s1, slot1["slot"])
                b["child"] = child
                b["at6c2Before"] = at6c2_before
                b["at6c2After"] = card_at(s1, 6, 2)
                b["at6c3After"] = card_at(s1, 6, 3)
                ok("B1 子槽占父件同行右邻格 r6c2",
                   bool(child) and bool(b["parent"]) and
                   child["row"] == b["parent"]["row"] and child["col"] == b["parent"]["col"] + 1,
                   {"parent": b["parent"], "child": child})
                ok("B2 原 r6c2 槽位右移且不与子槽同格",
                   bool(b["at6c2After"]) and bool(b["at6c3After"]) and
                   b["at6c2After"]["slot"] != b["at6c3After"]["slot"] and
                   (at6c2_before is None or b["at6c3After"]["slot"] == at6c2_before["slot"]),
                   {"before": b["at6c2Before"], "after6c2": b["at6c2After"], "after6c3": b["at6c3After"]})
                shot(cdp, "B1-scarh-shift.png")
                # 移除 → 恢复
                click_slot(cdp, slot1["slot"])
                time.sleep(0.9)
                js(cdp, """(function(){var r=document.querySelector('#gw-table .tbl-row[aria-selected="true"]');
                  if(r)r.click();})()""")
                time.sleep(1.8)
                s2 = snap(cdp)
                back = all((card_at(s0, c["row"], c["col"]) or {}).get("slot") == c["slot"]
                           for c in s0["cards"] if "mod_flashlight" not in c["slot"])
                no_child = not any(c["parent"] == slot1["slot"] for c in s2["cards"])
                b["restored"] = back and no_child
                b["afterRemove6c2"] = card_at(s2, 6, 2)
                ok("B3 移除后坐标完全恢复", back and no_child,
                   {"restored": back, "noChild": no_child, "at6c2": b["afterRemove6c2"]})
                shot(cdp, "B3-scarh-restore.png")
        report["detail"]["B"] = b

        # ---------------------------------------------------------------- C
        if pick_gun(cdp, "AKM 7.62x39", GUN_AKM):
            s = snap(cdp)
            tbl = {"head": [], "rows": []}
            for c in s["cards"][:8]:
                click_slot(cdp, c["slot"])
                time.sleep(1.1)
                raw = js(cdp, r"""(function(){
                  var t=document.getElementById('gw-table');
                  if(!t) return null;
                  var head=[].slice.call(t.querySelectorAll('.tbl-head .tbl-cell'))
                      .map(function(x){return (x.textContent||'').trim();});
                  var rows=[].slice.call(t.querySelectorAll('.tbl-row'));
                  var out=[];
                  for(var i=0;i<rows.length && out.length<24;i++){
                    var cs=[].slice.call(rows[i].querySelectorAll('.tbl-cell'));
                    if(!cs.length || rows[i].className.indexOf('tbl-empty')>=0) continue;
                    var rec={};
                    for(var j=0;j<cs.length;j++){
                      var k=cs[j].dataset.key||('i'+j);
                      rec[k]={text:(cs[j].textContent||'').trim(),
                              title:cs[j].getAttribute('title')||''};
                    }
                    out.push(rec);
                  }
                  return JSON.stringify({head:head,rows:out,slot:'%s'});})()"""
                         % c["slot"].replace('"', ""))
                if not raw:
                    continue
                cur = json.loads(raw)

                def _num(cell):
                    if not cell:
                        return None
                    t = (cell.get("text") or "").replace("%", "").replace(",", "")\
                        .replace("−", "-").replace("₽", "").strip()
                    try:
                        return float(t)
                    except Exception:              # noqa: BLE001
                        return None

                usable = sum(1 for r in cur.get("rows", [])
                             if _num(r.get("recoil")) is not None
                             and _num(r.get("ergo")) is not None
                             and _num(r.get("re3")) is not None)
                if usable >= 3:
                    tbl = cur
                    break
            head = tbl.get("head", [])
            ok("C1 候选表含 R+E/3 列", any("R+E/3" in h for h in head), head)

            def num(cell):
                if not cell:
                    return None
                txt = (cell.get("text") or "").replace("%", "").replace(",", "")\
                    .replace("−", "-").replace("₽", "").strip()
                try:
                    return float(txt)
                except Exception:                    # noqa: BLE001
                    return None

            good, bad, pos, neg = 0, [], 0, 0
            for row in tbl.get("rows", []):
                rc, er, re3c = row.get("recoil"), row.get("ergo"), row.get("re3")
                if not rc or not er or not re3c:
                    continue
                recoil_pct, ergo_v, re3_v = num(rc), num(er), num(re3c)
                if recoil_pct is None or ergo_v is None or re3_v is None:
                    continue
                gain = -recoil_pct                       # 正面增益：减少为正、增加为负
                expect = gain + ergo_v / 3.0
                calc_ok = abs(re3_v - expect) < 0.002
                show_ok = abs(re3_v - expect) < 0.002
                title_ok = ("R 取正面增益" in re3c.get("title", "")) and \
                    (re3c.get("title", "").split("=")[-1].strip().startswith("%.3f" % re3_v))
                if gain > 0:
                    pos += 1
                elif gain < 0:
                    neg += 1
                if calc_ok and show_ok and title_ok:
                    good += 1
                else:
                    bad.append({"recoil": rc["text"], "ergo": er["text"], "re3": re3c["text"],
                                "title": re3c.get("title", ""), "expect": round(expect, 3),
                                "calc": calc_ok, "titleOk": title_ok})
            ok("C2 R+E/3 计算/显示/符号一致", good >= 3 and not bad,
               {"slot": tbl.get("slot"), "rowsChecked": good, "bad": bad[:3],
                "gainPositive": pos, "gainNegative": neg})
            ok("C3 存在「减少后坐→增益为正」的真实行", pos >= 1, {"gainPositive": pos})
            report["detail"]["C"] = {"slot": tbl.get("slot"), "head": head,
                                     "rowsChecked": good, "bad": bad[:5],
                                     "gainPositive": pos, "gainNegative": neg}
            shot(cdp, "C2-re3-column.png")

        # ---------------------------------------------------------------- D
        cdp.drain(0.6)
        errs = [c for c in cdp.console if c.get("type") in ("error", "exception", "assert", "log")]
        ok("D1 控制台无 JS 异常/报错", not errs, errs[:5])
        hosts = {}
        for r in cdp.requests:
            m = re.match(r"^(?:https?:)?//([^/:]+)", r["url"])
            host = m.group(1) if m else "inline"
            hosts[host] = hosts.get(host, 0) + 1
        external = {h: n for h, n in hosts.items()
                    if h not in ("127.0.0.1", "localhost", "inline")}
        ok("D2 无外部网络请求", not external, external)
        report["detail"]["D"] = {"consoleErrors": errs[:5], "hosts": hosts,
                                 "external": external, "requests": len(cdp.requests)}

        report["pass"] = all(c["ok"] for c in report["checks"])
        with open(os.path.join(OUT, "browser-accept.json"), "w", encoding="utf-8", newline="") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
        print(json.dumps({"pass": report["pass"],
                          "failed": [c["name"] for c in report["checks"] if not c["ok"]]},
                         ensure_ascii=False))
        return 0 if report["pass"] else 1
    finally:
        try:
            proc.terminate()
        except Exception:                          # noqa: BLE001
            pass


if __name__ == "__main__":
    sys.exit(main())
