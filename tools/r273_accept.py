# -*- coding: utf-8 -*-
"""R273 浏览器验收：云账号版本按钮 / 会员到期徽标 / 配枪属性块排版。

  · 一级栏「云账号：XX版」与 /api/member 真值一致；
  · 二级栏常显会员到期（永久会员显示「永久」，限时会员显示 MM-DD HH:mm）；
  · 整枪属性 / 隐藏属性同为一行三个、同底色同字号；消音对比与技能后数值不再渲染。

用法：python tools/r273_accept.py --port 8787 --out docs/r273
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import r181_accept as base  # noqa: E402


def _opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _json(port, path):
    with _opener().open("http://127.0.0.1:%d%s" % (port, path), timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


# 只用于在没有载入枪械时验证 CSS：往两个容器里塞同结构的假属性行，不写任何文件。
INJECT = r"""
(function () {
  // 未选枪时 #gw-buildpage 是 hidden（display:none），几何量全为 0；
  // 验收只关心 CSS 排版，这里在浏览器内存里展开它，等价于选中枪械后的状态。
  var bp = document.getElementById('gw-buildpage');
  if (bp) { bp.hidden = false; }
  function fake(label) {
    var row = document.createElement('div');
    row.className = 'gw-stat-ex';
    var lab = document.createElement('span');
    lab.className = 'gw-stat-lab';
    lab.textContent = label;
    var val = document.createElement('b');
    val.className = 'gw-stat-val';
    val.textContent = '12.3';
    row.appendChild(lab); row.appendChild(val);
    return row;
  }
  ['gw-stats', 'gw-hidden'].forEach(function (id) {
    var host = document.getElementById(id);
    if (!host || host.querySelector('.gw-stat-ex')) { return; }
    // 未选枪时容器里只有一条空态提示，它会占掉一个格子；清掉并补上真实场景里的标题行
    Array.prototype.slice.call(host.querySelectorAll('.lw-ci-empty')).forEach(
      function (n) { n.parentNode.removeChild(n); });
    if (!host.querySelector('.gw-stat-head')) {
      var head = document.createElement('div');
      head.className = 'gw-stat-head';
      head.textContent = id === 'gw-stats' ? '整枪属性' : '隐藏属性';
      host.insertBefore(head, host.firstChild);
    }
    for (var i = 0; i < 3; i++) { host.appendChild(fake('属性' + i)); }
  });
  return 1;
})()
"""

READ = r"""
(function () {
  function cs(id) {
    var el = document.getElementById(id);
    if (!el) { return null; }
    var s = getComputedStyle(el);
    var row = el.querySelector('.gw-stat-ex');
    var lab = el.querySelector('.gw-stat-lab');
    var val = el.querySelector('.gw-stat-val');
    function box(n) { return n ? getComputedStyle(n) : null; }
    return {
      cols: s.gridTemplateColumns,
      display: s.display,
      bg: s.backgroundColor,
      border: s.borderTopWidth,
      rowH: box(row) && box(row).height,
      rowBg: box(row) && box(row).backgroundColor,
      labFs: box(lab) && box(lab).fontSize,
      valFs: box(val) && box(val).fontSize,
      rows: el.querySelectorAll('.gw-stat-ex').length,
      rowRects: Array.prototype.map.call(el.querySelectorAll('.gw-stat-ex'), function (n) {
        var r = n.getBoundingClientRect();
        return {x: Math.round(r.x), y: Math.round(r.y)};
      })
    };
  }
  var cloud = document.getElementById('am-cloud');
  var badge = document.getElementById('vt-member-expire');
  function rect(el) { var r = el.getBoundingClientRect(); return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)}; }
  return JSON.stringify({
    cloudText: cloud ? cloud.textContent.trim() : null,
    cloudRect: cloud ? rect(cloud) : null,
    badgeText: badge ? badge.textContent.trim() : null,
    badgeTone: badge ? badge.dataset.tone : null,
    badgeRect: badge ? rect(badge) : null,
    stats: cs('gw-stats'),
    hidden: cs('gw-hidden'),
    silcompare: document.querySelectorAll('.gw-silcompare').length,
    skillnote: document.querySelectorAll('.gw-bar-skillnote').length,
    skillText: document.body.innerText.indexOf('技能后数值：') >= 0
  });
})()
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--cdp-port", type=int, default=9441)
    ap.add_argument("--out", default="docs/r273")
    ap.add_argument("--chrome", default=None)
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    checks = []

    def check(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": str(detail)[:400]})

    member = _json(a.port, "/api/member")
    expected_btn = "云账号：" + ("会员版" if member.get("member") else "免费版")
    if member.get("member") and member.get("member_status") == "expired":
        expected_btn = "云账号：免费版"

    chrome = base.find_chrome(a.chrome)
    profile = os.path.join(a.out, "_profile_%d" % int(time.time()))
    os.makedirs(profile, exist_ok=True)
    proc, ws_url = base.launch(chrome, a.cdp_port, 1600, 1000, profile)
    try:
        cdp = base.CDP(ws_url)
        cdp.call("Page.enable")
        cdp.call("Runtime.enable")
        cdp.call("Log.enable")
        cdp.call("Network.setCacheDisabled", cacheDisabled=True)
        cdp.call("Page.navigate", url="http://127.0.0.1:%d/" % a.port)
        base.wait_ready(cdp)
        base.wait_for(cdp, "document.getElementById('am-cloud') !== null",
                      timeout=30, label="菜单栏加载")
        # cloud.js 启动时异步拉 /api/member，等徽标被真实写入
        base.wait_for(cdp, "document.getElementById('vt-member-expire') && "
                           "document.getElementById('vt-member-expire').dataset.tone",
                      timeout=20, label="会员徽标刷新")

        first = json.loads(cdp.eval(READ))
        check("云账号按钮显示版本", first["cloudText"] == expected_btn,
              "%s / 期望 %s" % (first["cloudText"], expected_btn))
        check("二级栏会员徽标可见", bool(first["badgeText"]) and
              first["badgeRect"]["w"] > 0, json.dumps(first["badgeText"]))
        if member.get("member") and member.get("member_status") in ("permanent", "active") \
                and not member.get("member_expires_at"):
            check("永久会员显示「会员到期：永久」",
                  first["badgeText"] == "会员到期：永久", first["badgeText"])
        check("会员徽标在云账号按钮下方",
              first["badgeRect"]["y"] > first["cloudRect"]["y"],
              "cloud y=%s badge y=%s" % (first["cloudRect"]["y"], first["badgeRect"]["y"]))

        cdp.eval("document.getElementById('view-btn-gun').click()")
        time.sleep(1.5)
        cdp.eval(INJECT)
        time.sleep(0.2)
        st = json.loads(cdp.eval(READ))
        shots = []
        png = os.path.join(a.out, "01-gun-stats.png")
        cdp.shot(png)
        shots.append(png)

        def cols(s):
            raw = (s or {}).get("cols", "") or ""
            if "repeat(3," in raw.replace(" ", ""):
                return 3          # Chromium 有时返回指定值而非 used value 的像素段
            return len(raw.split())

        def same_line(s):
            rs = (s or {}).get("rowRects") or []
            if len(rs) < 3:
                return False
            return rs[0]["y"] == rs[1]["y"] == rs[2]["y"] and \
                rs[0]["x"] < rs[1]["x"] < rs[2]["x"]

        check("整枪属性 3 列", cols(st["stats"]) == 3 and same_line(st["stats"]),
              json.dumps(st["stats"] and st["stats"]["rowRects"]))
        check("隐藏属性 3 列", cols(st["hidden"]) == 3 and same_line(st["hidden"]),
              json.dumps(st["hidden"] and st["hidden"]["rowRects"]))
        check("两块底色一致", st["stats"] and st["hidden"] and
              st["stats"]["bg"] == st["hidden"]["bg"],
              "%s / %s" % (st["stats"] and st["stats"]["bg"], st["hidden"] and st["hidden"]["bg"]))
        check("属性行高 / 字号按隐藏属性（12px / 9px）",
              st["stats"] and st["hidden"] and
              st["stats"]["rowH"] == st["hidden"]["rowH"] and
              st["stats"]["labFs"] == st["hidden"]["labFs"] and
              st["stats"]["labFs"] == "9px",
              json.dumps({"stats": st["stats"], "hidden": st["hidden"]})[:380])
        check("消音对比已删除", st["silcompare"] == 0, st["silcompare"])
        check("技能后数值已删除", st["skillnote"] == 0 and not st["skillText"],
              json.dumps({"note": st["skillnote"], "text": st["skillText"]}))

        errs = [c for c in cdp.console if c.get("type") in ("error", "exception", "assert")]
        errs = [c for c in errs if "favicon" not in (c.get("text") or "").lower()]
        check("无 JS 异常", not errs, json.dumps(errs[:3], ensure_ascii=False))

        with open(os.path.join(a.out, "report.json"), "w", encoding="utf-8") as fh:
            json.dump({"checks": checks, "member": member, "first": first,
                       "stats": st, "shots": shots}, fh, ensure_ascii=False, indent=2)
        for c in checks:
            print("  [%s] %s%s" % ("PASS" if c["ok"] else "FAIL", c["name"],
                                   ("  → " + c["detail"]) if c["detail"] else ""))
        ok = sum(1 for c in checks if c["ok"])
        print("\n%d/%d PASS" % (ok, len(checks)))
        return 0 if ok == len(checks) else 1
    finally:
        try:
            proc.terminate()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
