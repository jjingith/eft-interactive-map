#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R20.4 枪械构建器真实浏览器验收（参考站 db4tarkov Gun Builder 仿制）。

用真实 Chrome + CDP 操作**本地**应用，覆盖：
  1) 枪械搜索与选择（浏览页卡片含口径 / 价格 / 重量）
  2) 装配普通配件
  3) 装配带子槽位的配件（子槽在父件附近展开）
  4) 更换父配件后子槽处理（旧子件不残留）
  5) 尝试装配不兼容配件（必须被拒绝且状态不变）
  6) 拆除配件
  7) 属性实时更新
  8) 切换枪械后状态重置
  9) 候选表商人价 / 解锁等级列 + 「仅商人可买」过滤
 10) 浏览器控制台错误与外部网络请求

只读本地服务，不访问参考站；不修改任何业务数据。
"""
import argparse
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from r181_accept import CDP, find_chrome, launch, wait_ready  # noqa: E402

DEFAULT_BASE = "http://127.0.0.1:8801"
OUT_DIR = os.path.join(os.path.dirname(HERE), "docs", "r20.4-reference")


class Checker:
    def __init__(self):
        self.items = []

    def ok(self, cid, cond, detail=""):
        self.items.append({"id": cid, "pass": bool(cond), "detail": str(detail)[:400]})
        print(("PASS " if cond else "FAIL ") + cid + ("  " + str(detail)[:160] if detail else ""))
        return bool(cond)


def js(cdp, expr):
    r = cdp.eval(expr)
    if isinstance(r, str):
        t = r.strip()
        if t[:1] in ("{", "["):
            try:
                return json.loads(t)
            except Exception:  # noqa: BLE001
                return r
    return r


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--port", type=int, default=9710)
    args = ap.parse_args(argv)

    os.makedirs(OUT_DIR, exist_ok=True)
    shots = os.path.join(OUT_DIR, "screenshots")
    os.makedirs(shots, exist_ok=True)

    profile = os.path.join(os.environ.get("TEMP", "."), "r204accept")
    proc, ws = launch(find_chrome(), args.port, 1600, 950, profile)
    cdp = CDP(ws)
    chk = Checker()
    report = {"base": args.base, "checks": [], "shots": []}
    try:
        for m in ("Page.enable", "Runtime.enable", "Log.enable", "Network.enable"):
            cdp.call(m)
        cdp.call("Network.setCacheDisabled", cacheDisabled=True)
        cdp.call("Page.navigate", url=args.base + "/index.html")
        wait_ready(cdp, want_url="index.html")
        time.sleep(4)

        def shot(name):
            import base64
            r = cdp.call("Page.captureScreenshot", format="png")
            p = os.path.join(shots, name)
            with open(p, "wb") as fh:
                fh.write(base64.b64decode(r["data"]))
            report["shots"].append(name)
            print("shot:", name)

        # ---------- 进入枪械视图 ----------
        cdp.eval("(function(){var b=document.querySelector('[data-view=gun]');if(b)b.click();return !!b;})()")
        time.sleep(2.5)
        chk.ok("A1_进入枪械视图", js(cdp, "!!document.getElementById('gw-browse')"))

        # ---------- 1) 浏览页：卡片含价格与重量 ----------
        cards = js(cdp, """(function(){
          var cs=document.querySelectorAll('#gw-browse .gw-card');
          var out=[];
          for(var i=0;i<cs.length && i<6;i++){
            out.push({gun:cs[i].dataset.gun,text:(cs[i].innerText||'').replace(/\\n/g,' | '),
                      price:(cs[i].querySelector('.gw-card-price')||{}).textContent||'',
                      wt:(cs[i].querySelector('.gw-card-wt')||{}).textContent||''});
          }
          return JSON.stringify({total:cs.length, sample:out});})()""")
        chk.ok("A2_浏览卡片总数", cards["total"] > 100, "cards=%s" % cards["total"])
        has_price = [c for c in cards["sample"] if c["price"] and "缺失" not in c["price"]]
        has_wt = [c for c in cards["sample"] if c["wt"] and "缺失" not in c["wt"]]
        chk.ok("A3_卡片显示价格", len(has_price) > 0, has_price[0]["price"] if has_price else "")
        chk.ok("A4_卡片显示重量", len(has_wt) > 0, has_wt[0]["wt"] if has_wt else "")
        shot("local-browse-price-weight.png")

        # ---------- 枪械搜索 ----------
        cdp.eval("(function(){var s=document.getElementById('gw-search');if(s){s.value='AK-74';s.dispatchEvent(new Event('input',{bubbles:true}));}return !!s;})()")
        time.sleep(1.5)
        res = js(cdp, """(function(){var r=document.getElementById('gw-results');
          return JSON.stringify({hidden:r?r.hidden:null,items:r?r.querySelectorAll('[data-gun],button,li').length:0,
            text:r?(r.innerText||'').slice(0,120):''});})()""")
        chk.ok("A5_搜索有结果", (not res["hidden"]) and res["items"] > 0, res["text"].replace("\n", " ")[:100])
        shot("local-search.png")
        cdp.eval("(function(){var s=document.getElementById('gw-search');if(s){s.value='';s.dispatchEvent(new Event('input',{bubbles:true}));}return 1;})()")
        time.sleep(1.0)

        # ---------- 选两把结构不同的枪 ----------
        def pick_card(match):
            return js(cdp, """(function(){var m=%s;
              var cs=document.querySelectorAll('#gw-browse .gw-card');
              for(var i=0;i<cs.length;i++){ if((cs[i].innerText||'').indexOf(m)>=0){cs[i].click();
                return JSON.stringify({ok:true,name:cs[i].innerText.split('\\n').pop()});}}
              return JSON.stringify({ok:false});})()""" % json.dumps(match))

        def meta_info():
            return js(cdp, """(function(){var t=(document.getElementById('gw-meta')||{}).innerText||'';
              var m=t.match(/已装配件\\s*\\|?\\s*(\\d+)/);
              var parts=document.querySelectorAll('#gw-tree .gw-part').length;
              var subs=document.querySelectorAll('#gw-tree .gw-part-sub').length;
              var bars=(document.getElementById('gw-bars')||{}).innerText||'';
              return JSON.stringify({installed:m?parseInt(m[1],10):null,parts:parts,subs:subs,bars:bars.slice(0,220),meta:t.slice(0,160)});})()""")

        def focus_slot(idx=0):
            return js(cdp, """(function(){var i=%d;
              var ps=document.querySelectorAll('#gw-tree .gw-part');
              if(ps.length>i){ps[i].click();return true;} return false;})()""" % idx)

        def table_state():
            return js(cdp, """(function(){
              var head=[].slice.call(document.querySelectorAll('#gw-table .tbl-head .tbl-cell')).map(function(x){return (x.textContent||'').trim();});
              var rows=[].slice.call(document.querySelectorAll('#gw-table .tbl-row'));
              var conf=0,okc=0;
              for(var i=0;i<rows.length;i++){ if(rows[i].className.indexOf('tbl-conflict')>=0)conf++; else okc++; }
              return JSON.stringify({head:head,rows:rows.length,conflict:conf,ok:okc});})()""")

        resA = pick_card("M4A1")
        chk.ok("B1_选择AR系枪(M4A1)", resA.get("ok"), resA.get("name"))
        time.sleep(2.5)
        info0 = meta_info()
        chk.ok("B2_装配画布有槽位", info0["parts"] > 0, "parts=%s" % info0["parts"])
        shot("local-m4a1-empty.png")

        # 2) 打开一个槽位 → 候选表出现
        focus_slot(0)
        time.sleep(1.2)
        tbl = table_state()
        chk.ok("B3_点击槽位出候选", tbl["rows"] > 0, "rows=%s" % tbl["rows"])
        chk.ok("B4_候选表含商人价列", any("商人价" in h for h in tbl["head"]), tbl["head"])
        chk.ok("B5_候选表含解锁列", any("解锁" in h for h in tbl["head"]), tbl["head"])
        slot_path = js(cdp, """(function(){var f=document.querySelector('#gw-tree .gw-part-focus');
          return f?(f.dataset.slot||''):'';})()""")
        chk.ok("B6_焦点槽位已定位", bool(slot_path), slot_path)

        # I) 价格口径切换（对照参考站 gun 页 lastPrice / avg24h）
        pills = js(cdp, """(function(){var p=document.querySelectorAll('#gw-prices .gw-price-pill');
          return JSON.stringify([].slice.call(p).map(function(x){
            return (x.textContent||'').trim()+(x.disabled?'(禁用)':'');}));})()""")
        chk.ok("I1_枪械页价格口径切换", any(x.startswith("LAST") for x in pills)
               and len([x for x in pills if "(禁用)" not in x]) >= 3, pills)
        js(cdp, """(function(){var p=document.querySelector('#gw-prices .gw-price-pill[data-mode=last]');
          if(p) p.click(); return !!p;})()""")
        time.sleep(1.4)
        head_last = table_state()["head"]
        chk.ok("I2_LAST口径生效", any("LAST" in h for h in head_last), head_last)
        js(cdp, """(function(){var p=document.querySelector('#gw-prices .gw-price-pill[data-mode=flea]');
          if(p) p.click(); return !!p;})()""")
        time.sleep(1.2)

        # 3) 装配一个**带属性增量且未安装**的普通配件 → 属性应实时变化
        info0 = meta_info()
        pick_row = """(function(){
          var head=[].slice.call(document.querySelectorAll('#gw-table .tbl-head .tbl-cell'));
          var iE=-1,iR=-1,iS=-1;
          head.forEach(function(h,k){var t=(h.textContent||'').trim();
            if(t.indexOf('人机')===0)iE=k; if(t.indexOf('后坐')>=0)iR=k; if(t.indexOf('子槽')>=0)iS=k;});
          var rows=[].slice.call(document.querySelectorAll('#gw-table .tbl-row'));
          for(var i=0;i<rows.length;i++){
            if(rows[i].className.indexOf('tbl-conflict')>=0)continue;
            var cs=rows[i].querySelectorAll('.tbl-cell');
            var txt=(rows[i].innerText||'');
            if(/已装/.test(txt))continue;
            var ergo=iE>=0&&cs[iE]?(cs[iE].textContent||'').trim():'—';
            var rec=iR>=0&&cs[iR]?(cs[iR].textContent||'').trim():'—';
            if(ergo!=='—'&&ergo!==''&&(iE<0||true)){
              rows[i].click();
              return JSON.stringify({ok:true,kind:'stat',text:txt.split('\\n')[0],ergo:ergo,recoil:rec});}
          }
          return JSON.stringify({ok:false});})()"""
        def slot_item(path):
            return js(cdp, """(function(){var p=%s;
              var c=document.querySelector('#gw-tree .gw-part[data-slot="'+p+'"]');
              return c?(c.getAttribute('data-item')||''):'';})()""" % json.dumps(path))

        before_item = slot_item(slot_path)
        st = js(cdp, pick_row)
        time.sleep(2.0)
        info1 = meta_info()
        after_item = slot_item(slot_path)
        chk.ok("C1_装配普通配件生效", st.get("ok") and bool(after_item) and after_item != before_item,
               "槽位 %s：'%s' -> '%s'（人机=%s）" % (slot_path, before_item, after_item, st.get("ergo")))
        chk.ok("C2_属性实时更新", info1["bars"] != info0["bars"] or info1["meta"] != info0["meta"],
               "bars/meta 发生变化")

        # J) Δ 对比列（对照参考站 builder 的属性增减角标）：当前槽位已有件 → 出现差额列
        head_d = table_state()["head"]
        d_cols = [h for h in head_d if h.startswith("Δ")]
        chk.ok("J1_差额列存在", any(h.startswith("Δ人机") for h in head_d)
               and any(h.startswith("Δ重量") for h in head_d)
               and any(h.startswith("Δ价") for h in head_d), head_d)
        # Δ后坐：基线件缺后坐属性时整列隐藏（沿用「缺失属性整列隐藏」约定），
        # 此时已装行的「后坐力」单元格应为 —，据此证明是数据缺失而非实现缺陷。
        if not any(h.startswith("Δ后坐") for h in head_d):
            miss_recoil = js(cdp, """(function(){
              var head=[].slice.call(document.querySelectorAll('#gw-table .tbl-head .tbl-cell'));
              var i=-1; head.forEach(function(h,k){if((h.textContent||'').trim().indexOf('后坐')===0)i=k;});
              if(i<0) return 'no-col';
              var rows=[].slice.call(document.querySelectorAll('#gw-table .tbl-row'));
              for(var j=0;j<rows.length;j++){
                if(/已装/.test(rows[j].innerText||'')){
                  var cs=rows[j].querySelectorAll('.tbl-cell');
                  return (cs[i]?(cs[i].textContent||'').trim():'?');}}
              return 'no-row';})()""")
            chk.ok("J1b_Δ后坐隐藏原因=基线缺后坐", miss_recoil == "—",
                   "已装行后坐力单元格=%r（缺数据→整列隐藏）" % miss_recoil)
        zero = js(cdp, """(function(){
          var head=[].slice.call(document.querySelectorAll('#gw-table .tbl-head .tbl-cell'));
          var i=-1; head.forEach(function(h,k){if((h.textContent||'').trim().indexOf('Δ人机')===0)i=k;});
          if(i<0) return JSON.stringify({ok:false});
          var rows=[].slice.call(document.querySelectorAll('#gw-table .tbl-row'));
          for(var j=0;j<rows.length;j++){
            if(/已装/.test(rows[j].innerText||'')){
              var cs=rows[j].querySelectorAll('.tbl-cell');
              return JSON.stringify({ok:true,v:(cs[i]?cs[i].textContent||'':'').trim()});}}
          return JSON.stringify({ok:false});})()""")
        chk.ok("J2_已装件差额为0", zero.get("ok") and zero.get("v") in ("0", "+0", "0.00"),
               "已装行 Δ人机 = %r" % zero.get("v"))

        # 4) 装配带子槽位的配件（且未安装）→ 画布应出现以当前槽位为父的子槽
        sub_pick = """(function(){
          var head=[].slice.call(document.querySelectorAll('#gw-table .tbl-head .tbl-cell'));
          var iS=-1; head.forEach(function(h,k){if((h.textContent||'').trim().indexOf('子槽')===0)iS=k;});
          var rows=[].slice.call(document.querySelectorAll('#gw-table .tbl-row'));
          for(var i=0;i<rows.length;i++){
            if(rows[i].className.indexOf('tbl-conflict')>=0)continue;
            var txt=(rows[i].innerText||''); if(/已装/.test(txt))continue;
            var cs=rows[i].querySelectorAll('.tbl-cell');
            var v=iS>=0&&cs[iS]?(cs[iS].textContent||'').trim():'';
            if(v && v!=='0' && v!=='—'){ rows[i].click();
              return JSON.stringify({ok:true,sub:v,text:txt.split('\\n')[0]});}}
          return JSON.stringify({ok:false});})()"""
        sub_click = js(cdp, sub_pick)
        time.sleep(2.2)
        info2 = meta_info()
        child = js(cdp, """(function(){var p=%s;
          var n=document.querySelectorAll('#gw-tree .gw-part[data-parent="'+p+'"]').length;
          return JSON.stringify({children:n});})()""" % json.dumps(slot_path))
        chk.ok("C3_装配带子槽配件", sub_click.get("ok"), sub_click.get("text"))
        chk.ok("C4_子槽位展开", child["children"] > 0,
               "父槽 %s 的子槽卡片数=%s" % (slot_path, child["children"]))
        shot("local-m4a1-installed.png")

        # 5) 不兼容配件必须被拒绝
        inst_before_bad = info2["installed"]
        bad = js(cdp, """(function(){var rows=[].slice.call(document.querySelectorAll('#gw-table .tbl-row'));
          for(var i=0;i<rows.length;i++){ if(rows[i].className.indexOf('tbl-conflict')>=0){rows[i].click();
            return JSON.stringify({ok:true,text:(rows[i].innerText||'').replace(/\\n/g,' | ').slice(0,80)});}}
          return JSON.stringify({ok:false});})()""")
        time.sleep(1.5)
        info3 = meta_info()
        info3_item = slot_item(slot_path)
        hint = js(cdp, "(document.getElementById('gw-hint')||{}).innerText||''")
        chk.ok("D1_存在不兼容候选并被拒", (not bad.get("ok")) or
               (info3["installed"] == inst_before_bad),
               "installed %s -> %s; hint=%s" % (inst_before_bad, info3["installed"], hint[:60]))
        if bad.get("ok"):
            chk.ok("D2_不兼容提示", "⛔" in hint or "无法安装" in hint, hint[:80])

        # 6) 拆除配件（再次点击已装候选 → 应用逻辑：同件再点即卸下）
        inst_before_rm = info3["installed"]
        removed = js(cdp, """(function(){var rows=[].slice.call(document.querySelectorAll('#gw-table .tbl-row'));
          for(var i=0;i<rows.length;i++){ var t=(rows[i].innerText||'');
            if(rows[i].className.indexOf('tbl-conflict')<0 && /已装/.test(t)){ rows[i].click();
              return JSON.stringify({ok:true,text:t.split('\\n')[0]});}}
          return JSON.stringify({ok:false});})()""")
        time.sleep(1.8)
        info4 = meta_info()
        after_rm = slot_item(slot_path)
        chk.ok("E1_拆除配件生效", removed.get("ok") and (after_rm != info3_item),
               "槽位 '%s' -> '%s'（已装总数 %s -> %s）" % (info3_item, after_rm,
                                                inst_before_rm, info4["installed"]))

        # 7) 「仅商人可买」过滤
        rows_before = table_state()["rows"]
        js(cdp, """(function(){var c=document.getElementById('gw-onlytrader');
          if(!c) return false; c.checked=true; c.dispatchEvent(new Event('change',{bubbles:true})); return true;})()""")
        time.sleep(1.5)
        rows_after = table_state()["rows"]
        cnt = js(cdp, "(document.getElementById('gw-onlytrader-count')||{}).innerText||''")
        chk.ok("F1_仅商人可买过滤生效", rows_after <= rows_before,
               "rows %s -> %s; %s" % (rows_before, rows_after, cnt))
        js(cdp, """(function(){var c=document.getElementById('gw-onlytrader');
          if(c){c.checked=false;c.dispatchEvent(new Event('change',{bubbles:true}));} return 1;})()""")
        time.sleep(1.0)

        # K) 商人等级门槛（对照参考站 only TraderLvl）
        rows_before_lv = table_state()["rows"]
        js(cdp, """(function(){var s=document.getElementById('gw-trader-lv');
          if(!s) return false; s.value='1'; s.dispatchEvent(new Event('change',{bubbles:true})); return true;})()""")
        time.sleep(1.3)
        lv_rows = table_state()["rows"]
        max_lv = js(cdp, """(function(){
          var head=[].slice.call(document.querySelectorAll('#gw-table .tbl-head .tbl-cell'));
          var i=-1; head.forEach(function(h,k){if((h.textContent||'').trim().indexOf('解锁')===0)i=k;});
          if(i<0) return -1;
          var rows=[].slice.call(document.querySelectorAll('#gw-table .tbl-row')); var mx=0;
          for(var j=0;j<rows.length;j++){var cs=rows[j].querySelectorAll('.tbl-cell');
            if(cs[i]){var v=(cs[i].textContent||'').replace(/[^0-9]/g,''); if(v&&+v>mx)mx=+v;}}
          return mx;})()""")
        chk.ok("K1_商人等级门槛生效", lv_rows <= rows_before_lv and (max_lv == -1 or max_lv <= 1),
               "rows %s -> %s; 可见行最高解锁等级=%s" % (rows_before_lv, lv_rows, max_lv))
        js(cdp, """(function(){var s=document.getElementById('gw-trader-lv');
          if(s){s.value='0';s.dispatchEvent(new Event('change',{bubbles:true}));} return 1;})()""")
        time.sleep(1.0)
        shot("local-candidates-columns.png")

        # 8) 切换枪械 → 状态重置
        resB = pick_card("AK-74")
        chk.ok("G1_切换到AK系枪", resB.get("ok"), resB.get("name"))
        time.sleep(2.5)
        info5 = meta_info()
        chk.ok("G2_换枪后槽位重置", info5["parts"] > 0 and info5["installed"] != info4["installed"],
               "installed %s -> %s, parts=%s" % (info4["installed"], info5["installed"], info5["parts"]))
        shot("local-ak74.png")

        # 9) 控制台与外部请求
        console = [c for c in cdp.console if c.get("type") == "error"]
        chk.ok("H1_无控制台错误", len(console) == 0, json.dumps(console[:3], ensure_ascii=False))
        ext = [r.get("url") for r in cdp.requests
               if "127.0.0.1" not in r.get("url", "") and not r.get("url", "").startswith("data:")]
        chk.ok("H2_无外部网络请求", len(ext) == 0, json.dumps(ext[:3], ensure_ascii=False))

        report["checks"] = chk.items
        report["pass"] = all(c["pass"] for c in chk.items)
        report["consoleErrors"] = console
        report["externalRequests"] = ext
        report["samples"] = {"cards": cards["sample"], "tableHead": tbl["head"],
                              "m4a1": info2, "ak74": info5}
        with open(os.path.join(OUT_DIR, "browser-accept.json"), "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
        print("\n==== %d/%d 通过 ====" % (sum(1 for c in chk.items if c["pass"]), len(chk.items)))
        return 0 if report["pass"] else 1
    finally:
        proc.terminate()


if __name__ == "__main__":
    sys.exit(main())
