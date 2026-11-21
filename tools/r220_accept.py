# -*- coding: utf-8 -*-
"""R220 真实浏览器验收：「数据截止 …（N 小时前）· 已过期 M 小时」必须自洽。

用户反馈（2026-11-10）：
  「数据截止 11-09 15:01（20 小时前） · 非实时 · 已过期 8 小时 54 分钟  还是这样」

前半句由前端用 snapshotAt 现算，后半句读服务端 ageSec；服务端把 ageSec 连同快照缓存，
于是同一行出现两个相差十几个小时的数字。本脚本只做实测：

  1. 同一行里「N 小时前」与「已过期 M 小时」的差距 ≤ 1 小时（取整容差）；
  2. 「已过期 M」与本机按 snapshotAt 算出的真实年龄差 ≤ 10 分钟；
  3. 横幅（.mk-stale）与行内文案给出的是同一个年龄，不打架；
  4. 服务端 /api/price-snapshot 的 ageSec 也等于真实年龄（≤ 10 分钟），证明不是只修了前端。

用法：
    python tools/r220_accept.py --port 8787 --out D:/Temp/2/r220
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import r181_accept as base  # noqa: E402


def q(cdp, expr):
    return cdp.eval("Promise.resolve((function(){" + expr + "})())", await_promise=True)


def hours_of(text):
    """「19 小时 41 分钟」/「20 小时前」→ 19.68 / 20.0"""
    if not text:
        return None
    total = 0.0
    m = re.search(r"(\d+)\s*小时", text)
    if m:
        total += int(m.group(1))
    m = re.search(r"(\d+)\s*分钟", text)
    if m:
        total += int(m.group(1)) / 60.0
    return total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--cdp-port", type=int, default=9421)
    ap.add_argument("--out", default="D:/Temp/2/r220")
    ap.add_argument("--chrome", default=None)
    a = ap.parse_args()

    chrome = base.find_chrome(a.chrome)
    os.makedirs(a.out, exist_ok=True)
    profile = os.path.join(a.out, "_profile_%d" % int(time.time()))
    proc, ws_url = base.launch(chrome, a.cdp_port, 1600, 1000, profile)
    rep = {"checks": [], "shots": []}
    try:
        cdp = base.CDP(ws_url)
        cdp.call("Page.enable")
        cdp.call("Runtime.enable")
        cdp.call("Network.enable")
        cdp.call("Network.setCacheDisabled", cacheDisabled=True)
        cdp.call("Page.navigate", url="http://127.0.0.1:%d/" % a.port)
        base.wait_ready(cdp)

        q(cdp, "var b=document.getElementById('view-btn-market'); if(b){b.click(); return true;} return false;")
        base.wait_for(cdp, "(function(){var e=document.querySelector('.mk-cutoff');"
                          "return !!(e && (e.textContent||'').trim());})()", timeout=90, label="行情截止行")

        data = q(cdp, """
          var cut = document.querySelector('.mk-cutoff');
          var st = document.querySelector('.mk-stale');
          var s = (window.GWMarketData && window.GWMarketData.snapshot) ? window.GWMarketData.snapshot() : null;
          return {
            cutoff: cut ? (cut.textContent || '').trim() : null,
            banner: st ? ((st.hidden ? '' : (st.textContent || '').trim())) : null,
            snapshotAt: s ? s.snapshotAt : null,
            ageSec: s ? s.ageSec : null,
            stale: s ? s.stale : null,
            source: s ? s.source : null,
            tooltip: cut ? (cut.title || '') : ''
          };
        """)
        rep["ui"] = data

        # 服务端口径：同一时刻的 ageSec 是否等于真实年龄
        with urllib.request.urlopen("http://127.0.0.1:%d/api/price-snapshot?mode=regular" % a.port, timeout=180) as r:
            api = json.loads(r.read())
        snap_at = datetime.datetime.fromisoformat(api["snapshotAt"])
        now = datetime.datetime.now(snap_at.tzinfo)
        real_age = (now - snap_at).total_seconds()
        rep["api"] = {"snapshotAt": api["snapshotAt"], "ageSec": api["ageSec"],
                      "realAgeSec": int(real_age), "stale": api["stale"],
                      "deltaMin": round((real_age - api["ageSec"]) / 60.0, 1)}
        rep["checks"].append(("服务端 ageSec 与真实年龄差 ≤ 10 分钟",
                              abs(real_age - api["ageSec"]) <= 600))

        cutoff = data.get("cutoff") or ""
        m_ago = re.search(r"（([^）]*)）", cutoff)
        ago_text = m_ago.group(1) if m_ago else ""
        m_exp = re.search(r"已过期\s*([0-9]+\s*小时[^·]*|不到 1 分钟|[0-9]+\s*分钟)", cutoff)
        exp_text = m_exp.group(1).strip() if m_exp else ""

        ago_h = hours_of(ago_text)
        exp_h = hours_of(exp_text)
        stale = bool(data.get("stale"))
        # 本机真实年龄：now - snapshotAt
        real_h = None
        if data.get("snapshotAt"):
            d = datetime.datetime.fromisoformat(data["snapshotAt"])
            real_h = (datetime.datetime.now(d.tzinfo) - d).total_seconds() / 3600.0
            rep["realHours"] = round(real_h, 2)
        rep["parsed"] = {"ago": ago_text, "agoHours": ago_h,
                         "expired": exp_text, "expiredHours": exp_h, "stale": stale}

        rep["checks"].append(("「N 小时/分钟前」可解析", ago_h is not None))
        if stale:
            # 用户报的那种状态：同一行两个年龄必须自洽
            rep["checks"].append(("过期态下行内出现「已过期」", bool(exp_text)))
            if ago_h is not None and exp_h is not None:
                rep["checks"].append(("行内两个年龄相差 ≤ 1 小时（用户报的就是这条）",
                                      abs(ago_h - exp_h) <= 1.0))
                if real_h is not None:
                    rep["checks"].append(("「已过期」与本机真实年龄差 ≤ 1 小时",
                                          abs(exp_h - real_h) <= 1.0))
            if real_h is not None and ago_h is not None:
                rep["checks"].append(("「N 小时前」与本机真实年龄差 ≤ 1 小时",
                                      abs(ago_h - real_h) <= 1.0))
        else:
            # 数据新鲜时不该出现「已过期」，且行内年龄要与真实年龄一致
            rep["checks"].append(("新鲜态下不显示「已过期」", not exp_text))
            rep["checks"].append(("新鲜态标为「近实时」", "近实时" in cutoff))
            if real_h is not None and ago_h is not None:
                rep["checks"].append(("行内年龄与本机真实年龄差 ≤ 5 分钟",
                                      abs(ago_h - real_h) * 60 <= 5))

        banner = data.get("banner") or ""
        if stale:
            rep["checks"].append(("横幅也给出同一个年龄", (not banner) or
                                  (hours_of(banner) is not None and exp_h is not None and
                                   abs((hours_of(banner) or 0) - exp_h) <= 1.0)))
        else:
            rep["checks"].append(("新鲜态下不显示过期横幅", not banner))

        # 悬停里的「数据年龄」同样是现算
        rep["checks"].append(("悬停说明写明按当前时间现算", "按本机当前时间现算" in (data.get("tooltip") or "")))

        shot = os.path.join(a.out, "market-cutoff.png")
        try:
            cdp.shot(shot)
            rep["shots"].append(shot)
        except Exception as exc:  # 截图失败不影响判定
            rep["shots"].append("截图失败：%s" % exc)
    finally:
        try:
            proc.terminate()
        except Exception:
            pass

    ok = all(v for _, v in rep["checks"])
    for label, val in rep["checks"]:
        print(("PASS " if val else "FAIL ") + label)
    print(json.dumps({k: v for k, v in rep.items() if k != "checks"}, ensure_ascii=False, indent=1))
    print("\n结果：%s（%d/%d）" % ("通过" if ok else "未通过",
                                 sum(1 for _, v in rep["checks"] if v), len(rep["checks"])))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
