# -*- coding: utf-8 -*-
"""全项目用户可见文字盘点（R19.22，只读）。

不复用「搜 app.js 里的英文字符串」这种做法——那会漏掉数据驱动名称、SVG 文本、
动态拼接、服务端下发字段。这里用真实浏览器逐视图扫描：

  · 主程序四个视图（地图 / 配装 / 配枪 / 弹药）+ 导航面板 + 设置弹窗
  · 武器槽位校准器（?layoutCalibrator=1）
  · 任务模块（/?task，若已实现）

采集内容：可见文本节点（含 CJK 判定）、title / placeholder / aria-label 属性。
输出 docs/r19.22-tasks-i18n/i18n-inventory.json，并在终端给出统计。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from r181_accept import CDP, find_chrome, launch, wait_ready  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "r19.22-tasks-i18n")
BASE = "http://127.0.0.1:8787"
CJK = re.compile(r"[\u3400-\u9fff]")
LATIN = re.compile(r"[A-Za-z]{2,}")

# 采集脚本：文本节点 + 属性，跳过脚本/样式/隐藏元素
COLLECT = r"""
(function(){
  var out = [];
  var skip = {SCRIPT:1, STYLE:1, NOSCRIPT:1, TEMPLATE:1};
  function visible(el){
    var r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return false;
    var st = getComputedStyle(el);
    if (st.visibility === 'hidden' || st.display === 'none' || +st.opacity === 0) return false;
    return true;
  }
  var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
    acceptNode: function(n){
      var p = n.parentElement;
      if (!p || skip[p.tagName]) return NodeFilter.FILTER_REJECT;
      var t = (n.nodeValue || '').trim();
      if (!t) return NodeFilter.FILTER_REJECT;
      if (!visible(p)) return NodeFilter.FILTER_REJECT;
      return NodeFilter.FILTER_ACCEPT;
    }
  });
  var n;
  while ((n = walker.nextNode())) {
    var el = n.parentElement;
    out.push({
      kind: 'text',
      text: (n.nodeValue || '').replace(/\s+/g, ' ').trim(),
      tag: el.tagName.toLowerCase(),
      cls: (el.className && String(el.className).slice(0, 60)) || '',
      path: (function(){
        var p = el, parts = [];
        while (p && p !== document.body && parts.length < 4) {
          parts.unshift(p.tagName.toLowerCase() + (p.id ? '#' + p.id : ''));
          p = p.parentElement;
        }
        return parts.join('>');
      })(),
      title: el.getAttribute('title') || ''
    });
  }
  // 属性文本（浮窗/占位/无障碍）
  var attrs = [];
  ['title', 'placeholder', 'aria-label', 'alt'].forEach(function(a){
    Array.prototype.forEach.call(document.querySelectorAll('[' + a + ']'), function(el){
      if (!visible(el)) return;
      var v = (el.getAttribute(a) || '').trim();
      if (!v) return;
      attrs.push({ kind: 'attr', attr: a, text: v, tag: el.tagName.toLowerCase(),
                   id: el.id || '', cls: String(el.className || '').slice(0, 60) });
    });
  });
  return JSON.stringify({view: (document.body.dataset.view || ''), text: out, attrs: attrs});
})()
"""

# 视图 → (标签, 代表元素选择器)：等到真实内容出现再采集，避免扫到空壳
VIEWS = [("map", "地图", "#map-svg path, #map-svg circle"),
         ("loadout", "配装", "#gear-table .tbl-row, #lw-figure .lw-card"),
         ("gun", "配枪", "#gw-browse .gw-card, #gw-table .tbl-row"),
         ("ammo", "弹药", "#am-table .tbl-row")]


def collect(cdp, label: str) -> dict:
    raw = cdp.eval(COLLECT)
    data = json.loads(raw) if raw else {"text": [], "attrs": []}
    data["label"] = label
    return data


def scan_main(cdp, shots_dir=None) -> list:
    out = []
    cdp.call("Page.navigate", url=BASE + "/index.html")
    wait_ready(cdp, want_url="index.html")
    time.sleep(4)
    for view, label, selector in VIEWS:
        cdp.eval("(function(){var b=document.querySelector('[data-view=\"%s\"]');"
                 "if(b) b.click();})()" % view)
        for _ in range(24):
            if cdp.eval("!!document.querySelector(%s)" % json.dumps(selector)):
                break
            time.sleep(0.5)
        time.sleep(1.6)
        out.append(collect(cdp, "主程序 · " + label))
    # 导航面板 + 菜单
    cdp.eval("(function(){var b=document.getElementById('menu-nav'); if(b) b.click();})()")
    time.sleep(1.0)
    out.append(collect(cdp, "主程序 · 导航面板"))
    cdp.eval("(function(){var b=document.getElementById('menu-nav'); if(b) b.click();})()")
    time.sleep(0.4)
    # 配枪视图里的表格页 / 构建页
    cdp.eval("(function(){var b=document.querySelector('[data-view=\"gun\"]'); if(b) b.click();})()")
    time.sleep(1.0)
    for mode in ("table", "build", "class"):
        cdp.eval("(function(){var b=document.querySelector('.gw-mode[data-gwmode=\"%s\"]');"
                 "if(b) b.click();})()" % mode)
        time.sleep(1.6)
        out.append(collect(cdp, "配枪 · " + mode))
    return out


def scan_calibrator(cdp) -> list:
    cdp.call("Page.navigate", url=BASE + "/index.html?layoutCalibrator=1")
    wait_ready(cdp, want_url="layoutCalibrator=1")
    time.sleep(4)
    return [collect(cdp, "校准器")]


def scan_tasks(cdp) -> list:
    cdp.call("Page.navigate", url=BASE + "/index.html#tasks")
    wait_ready(cdp, want_url="index.html")
    time.sleep(4)
    has = cdp.eval("!!document.getElementById('task-root')")
    if not has:
        return []
    out = [collect(cdp, "任务 · 全局树")]
    for view in ("traders", "detail", "progress"):
        cdp.eval("(function(){var b=document.querySelector('[data-taskview=\"%s\"]');"
                 "if(b) b.click();})()" % view)
        time.sleep(1.8)
        out.append(collect(cdp, "任务 · " + view))
    return out


def summarize(collections: list) -> dict:
    texts = {}
    attrs = {}
    for col in collections:
        for rec in col.get("text") or []:
            t = rec["text"]
            if not LATIN.search(t) or CJK.search(t):
                continue
            key = t
            slot = texts.setdefault(key, {"text": t, "count": 0, "where": [], "tags": set()})
            slot["count"] += 1
            if col["label"] not in slot["where"]:
                slot["where"].append(col["label"])
            slot["tags"].add(rec.get("tag") or "")
        for rec in col.get("attrs") or []:
            t = rec["text"]
            if not LATIN.search(t) or CJK.search(t):
                continue
            slot = attrs.setdefault(t, {"text": t, "count": 0, "where": [], "attrs": set()})
            slot["count"] += 1
            if col["label"] not in slot["where"]:
                slot["where"].append(col["label"])
            slot["attrs"].add(rec.get("attr") or "")
    for v in list(texts.values()) + list(attrs.values()):
        if "tags" in v:
            v["tags"] = sorted(v["tags"])
        if "attrs" in v:
            v["attrs"] = sorted(v["attrs"])
    total_nodes = sum(len(c.get("text") or []) + len(c.get("attrs") or []) for c in collections)
    latin_nodes = sum(1 for c in collections
                      for r in (c.get("text") or []) + (c.get("attrs") or [])
                      if LATIN.search(r["text"]) and not CJK.search(r["text"]))
    return {
        "scannedViews": [c["label"] for c in collections],
        "totalNodes": total_nodes,
        "latinOnlyNodes": latin_nodes,
        "uniqueLatinTexts": len(texts),
        "uniqueLatinAttrs": len(attrs),
        "texts": sorted(texts.values(), key=lambda x: -x["count"]),
        "attrs": sorted(attrs.values(), key=lambda x: -x["count"]),
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9731)
    args = ap.parse_args(argv)
    os.makedirs(OUT, exist_ok=True)
    prof = os.path.join(os.environ.get("TEMP", "."), "r1922scan_%d" % args.port)
    proc, ws = launch(find_chrome(), args.port, 1600, 1000, prof)
    cdp = CDP(ws)
    try:
        for m in ("Page.enable", "Runtime.enable", "Network.enable", "Log.enable"):
            cdp.call(m)
        cdp.call("Network.setCacheDisabled", cacheDisabled=True)
        cdp.call("Emulation.setDeviceMetricsOverride", width=1600, height=1000,
                 deviceScaleFactor=1, mobile=False)
        cols = scan_main(cdp) + scan_calibrator(cdp) + scan_tasks(cdp)
        rep = summarize(cols)
        rep["schema"] = 1
        rep["scannedAt"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        with open(os.path.join(OUT, "i18n-inventory.json"), "w", encoding="utf-8", newline="\n") as fh:
            json.dump(rep, fh, ensure_ascii=False, indent=1)
        print("扫描视图:", ", ".join(rep["scannedViews"]))
        print("文本/属性节点 %d，其中纯英文 %d；去重英文文本 %d 条、属性 %d 条"
              % (rep["totalNodes"], rep["latinOnlyNodes"], rep["uniqueLatinTexts"],
                 rep["uniqueLatinAttrs"]))
        for t in rep["texts"][:25]:
            print("  %-46s x%-3d %s" % (t["text"][:46], t["count"], ",".join(t["where"])[:40]))
        for a in rep["attrs"][:10]:
            print("  [%s] %-40s x%d" % ("/".join(a["attrs"]), a["text"][:40], a["count"]))
    finally:
        try:
            proc.terminate()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
