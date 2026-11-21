# -*- coding: utf-8 -*-
"""R277 浏览器验收：云账号面板的会员充值档位卡片与激活码兑换。

  · 5 档价格（1天¥1 / 1月¥12 / 3月¥30 / 6月¥60 / 12月¥108）由云端接口驱动；
  · 卡片 3 列网格、点选高亮并更新提示；
  · 兑换成功 / 重复兑换都有中文反馈，成功后会员徽标同步刷新。

用法：python tools/r277_accept.py --port 8787 --out .shots/r277
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


def _json(port, path, attempts=4):
    """BFF 的云端 keep-alive 偶尔被服务端提前关掉，幂等 GET 重试即可。"""
    last = None
    for _ in range(attempts):
        try:
            with _opener().open("http://127.0.0.1:%d%s" % (port, path), timeout=15) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - 验收脚本只需最终成功
            last = exc
            time.sleep(1.0)
    raise last


READ = r"""
(function () {
  function rect(el) {
    if (!el) { return null; }
    var r = el.getBoundingClientRect();
    return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)};
  }
  var panel = document.getElementById('am-cloud-panel');
  var area = document.querySelector('[data-role="redeem-area"]');
  var host = document.querySelector('[data-role="rd-tiers"]');
  var cards = Array.prototype.map.call(document.querySelectorAll('.rd-tier'), function (n) {
    var lab = n.querySelector('.rd-tier-label');
    var price = n.querySelector('.rd-tier-price');
    var r = rect(n);
    return {tier: n.getAttribute('data-tier'), active: n.classList.contains('is-active'),
            label: lab && lab.textContent, price: price && price.textContent,
            x: r.x, y: r.y, w: r.w, h: r.h};
  });
  var input = document.querySelector('[data-role="rd-code"]');
  var button = document.querySelector('[data-action="redeem"]');
  var buy = document.querySelector('[data-action="redeem-buy"]');
  var msg = document.querySelector('[data-role="rd-msg"]');
  var hint = document.querySelector('[data-role="rd-hint"]');
  var badge = document.getElementById('vt-member-expire');
  return JSON.stringify({
    panelOpen: !!panel && !panel.hidden,
    panelRect: rect(panel),
    area: !!area,
    cols: host ? getComputedStyle(host).gridTemplateColumns : '',
    cards: cards,
    input: rect(input),
    inputValue: input ? input.value : null,
    button: rect(button),
    buyHidden: buy ? buy.hidden : null,
    buyDisplay: buy ? getComputedStyle(buy).display : null,
    buyText: buy ? buy.textContent.trim() : '',
    hint: hint ? hint.textContent : '',
    msg: msg ? msg.textContent : '',
    msgError: msg ? msg.classList.contains('is-error') : null,
    badgeText: badge ? badge.textContent.trim() : '',
    badgeTone: badge ? badge.dataset.tone : ''
  });
})()
"""

# 用假的云响应验证 UI 分支，不真的消费卡密、也不改真实会员态
STUB = r"""
(function () {
  if (window.__r277Orig) { return 1; }
  window.__r277Orig = window.fetch;
  window.__r277Mode = 'success';
  window.fetch = function (url, init) {
    var u = String(url);
    var opts = init || {};
    function reply(status, payload) {
      return Promise.resolve({
        ok: status >= 200 && status < 300, status: status,
        json: function () { return Promise.resolve(payload); }
      });
    }
    if (u.indexOf('/api/cloud/redeem') === 0 && opts.method === 'POST') {
      if (window.__r277Mode === 'error') {
        return reply(409, {ok: false, code: 'code_used', error: '激活码已被使用'});
      }
      return reply(200, {email: 'buyer@example.com', tier: 'm3', label: '3 个月',
        added_days: 90, code_hint: 'AB12••••CD34', member: true,
        member_status: 'active', member_plan: 'quarterly',
        member_since: '2026-11-13T07:00:00+00:00',
        member_expires_at: '2027-02-11T07:00:00+00:00'});
    }
    if (u.indexOf('/api/cloud/me') === 0 || u.indexOf('/api/member') === 0) {
      return reply(200, {member: true, member_status: 'active',
        member_plan: 'quarterly', member_since: '2026-11-13T07:00:00+00:00',
        member_expires_at: '2027-02-11T07:00:00+00:00'});
    }
    return window.__r277Orig.apply(this, arguments);
  };
  return 1;
})()
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--cdp-port", type=int, default=9446)
    ap.add_argument("--out", default=".shots/r277")
    ap.add_argument("--chrome", default=None)
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    checks = []

    def check(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": str(detail)[:400]})

    tiers = _json(a.port, "/api/cloud/redeem/tiers")["tiers"]
    expected_prices = ["¥%s" % t["price"] for t in tiers]
    expected_labels = [t["label"] for t in tiers]

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
        cdp.eval("document.getElementById('am-cloud').click()")
        base.wait_for(
            cdp, "document.querySelector('[data-role=\"redeem-area\"]') && "
                 "document.querySelectorAll('.rd-tier').length === 5",
            timeout=25, label="兑换区与 5 张档位卡片")
        time.sleep(1.2)   # 等 /api/cloud/status 与 me 回填完成后再读

        st = json.loads(cdp.eval(READ))
        check("云账号面板已打开", st["panelOpen"], st["panelRect"])
        check("兑换区已挂载", st["area"])
        check("5 张档位卡片", len(st["cards"]) == 5, len(st["cards"]))
        check("档位名称与云端一致",
              [c["label"] for c in st["cards"]] == expected_labels,
              [c["label"] for c in st["cards"]])
        check("价格写在卡片里",
              [c["price"] for c in st["cards"]] == expected_prices,
              [c["price"] for c in st["cards"]])
        check("3 列网格、卡片有可见尺寸",
              ("repeat(3," in (st["cols"] or "").replace(" ", "") or
               len((st["cols"] or "").split()) == 3) and
              all(c["w"] > 30 and c["h"] > 25 for c in st["cards"]),
              "%s / %s" % (st["cols"], [(c["w"], c["h"]) for c in st["cards"]]))
        check("第一行 3 张同高对齐",
              st["cards"][0]["y"] == st["cards"][1]["y"] == st["cards"][2]["y"],
              [c["y"] for c in st["cards"][:3]])
        check("兑换输入框与主按钮可见",
              st["input"] and st["input"]["w"] > 80 and st["button"] and st["button"]["w"] > 40,
              "%s / %s" % (st["input"], st["button"]))
        check("提示说明无需选档位", "不用选档位" in st["hint"], st["hint"])
        check("档位卡片没有选中态",
              all(c["active"] is False for c in st["cards"]))
        check("购买入口可见并指向爱发电",
              st["buyHidden"] is False and st["buyDisplay"] != "none" and
              "爱发电" in st["buyText"],
              "%s / %s / %s" % (st.get("buyHidden"), st.get("buyDisplay"), st.get("buyText")))

        # 点购买 -> 用 window.open 打开商品页（这里拦截 open，确认 URL 不是空串）
        cdp.eval("window.__r277Opened = null;"
                 "window.open = function (url) { window.__r277Opened = String(url); return null; };")
        cdp.eval("document.querySelector('[data-action=\"redeem-buy\"]').click()")
        time.sleep(0.4)
        opened = cdp.eval("window.__r277Opened")
        check("点击购买打开爱发电商品页",
              isinstance(opened, str) and opened.startswith("https://afdian.com/item/"),
              opened)

        shots = []
        png = os.path.join(a.out, "01-redeem-panel.png")
        cdp.shot(png)
        shots.append(png)

        # 成功分支
        cdp.eval(STUB)
        cdp.eval("(function(){var i=document.querySelector('[data-role=\"rd-code\"]');"
                 "i.value='AB12-CDEF-GHJK-MNP3';"
                 "i.dispatchEvent(new Event('input',{bubbles:true}));"
                 "document.querySelector('[data-action=\"redeem\"]').click();return 1;})()")
        time.sleep(1.4)
        ok_state = json.loads(cdp.eval(READ))
        check("兑换成功有中文反馈",
              "兑换成功" in ok_state["msg"] and "90 天" in ok_state["msg"] and
              not ok_state["msgError"], ok_state["msg"])
        check("成功后输入框清空", ok_state["inputValue"] == "", ok_state["inputValue"])
        check("会员徽标同步为限时会员",
              ok_state["badgeTone"] == "member" and "会员到期：" in ok_state["badgeText"],
              "%s / %s" % (ok_state["badgeText"], ok_state["badgeTone"]))

        # 错误分支
        cdp.eval("window.__r277Mode = 'error'")
        cdp.eval("(function(){var i=document.querySelector('[data-role=\"rd-code\"]');"
                 "i.value='AB12-CDEF-GHJK-MNP3';"
                 "i.dispatchEvent(new Event('input',{bubbles:true}));"
                 "document.querySelector('[data-action=\"redeem\"]').click();return 1;})()")
        time.sleep(1.2)
        err_state = json.loads(cdp.eval(READ))
        check("重复兑换显示中文错误",
              err_state["msgError"] and "已被使用" in err_state["msg"], err_state["msg"])

        png2 = os.path.join(a.out, "02-redeem-result.png")
        cdp.shot(png2)
        shots.append(png2)

        errs = [c for c in cdp.console if c.get("type") in ("error", "exception", "assert")]
        errs = [c for c in errs if "favicon" not in (c.get("text") or "").lower()]
        check("无 JS 异常", not errs, json.dumps(errs[:3], ensure_ascii=False))

        with open(os.path.join(a.out, "report.json"), "w", encoding="utf-8") as fh:
            json.dump({"checks": checks, "tiers": tiers, "shots": shots},
                      fh, ensure_ascii=False, indent=2)
        for c in checks:
            print("  [%s] %s%s" % ("PASS" if c["ok"] else "FAIL", c["name"],
                                   ("  -> " + c["detail"]) if c["detail"] else ""))
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
