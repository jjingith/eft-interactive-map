# -*- coding: utf-8 -*-
"""R100 验收：剧情步骤「完成时级联补齐前置」的真实浏览器行为。

覆盖：
  1. 冷启动深链 #stories:<id>~<pointKey> 直接落在该剧情点
  2. 从未开始状态勾最后一个步骤 → 弹窗列出全部前置（数与实际勾选数一致）
  3. 取消 → 勾选框 / 进度 / localStorage 全部不变（无新增写入）
  4. 确认 → 一次性写入，三态、勾选框、进度条与统计同步
  5. 再重复一次同样的操作（撤销最后一个 → 重新勾选）→ 前置已满足，不再弹窗
  6. 刷新后进度仍在（写在 eftmap.stories.progress.v1）
  7. ?mini=1 → 无数剧情节点、无弹窗、控制台无报错

用法：python tools/r100_accept.py [--port 8791]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import r181_accept as A  # noqa: E402

BATYA = "68da36cf7cff54fc6109874a"
BATYA_POINT = "6ab8b193f6a955f4260db207"   # interchange 上的剧情点 → pointKey
LS_KEY = "eftmap.stories.progress.v1"

STATE = r"""
(function(){
  var checks = document.querySelectorAll('.tk-story-check');
  var on = 0;
  Array.prototype.forEach.call(checks, function(b){ if (b.classList.contains('is-on')) { on++; } });
  var fill = document.querySelector('.tk-story-prog-fill');
  var visible = 0;
  Array.prototype.forEach.call(document.querySelectorAll('[data-story-node]'), function(n){
    if (n.getBoundingClientRect().width > 0) { visible++; }
  });
  return {
    stepNodes: document.querySelectorAll('[data-story-node]').length,
    visibleNodes: visible,
    toggles: checks.length,
    on: on,
    progText: (document.querySelector('.tk-story-prog-text') || {}).textContent || null,
    progWidth: fill ? fill.style.width : null,
    badges: {
      done: document.querySelectorAll('.tk-story-badge.is-done').length,
      avail: document.querySelectorAll('.tk-story-badge.is-avail').length,
      locked: document.querySelectorAll('.tk-story-badge.is-locked').length
    },
    focus: document.querySelectorAll('.tk-story-node.is-focus').length,
    dialog: (function(){
      var box = document.querySelector('.ui-dialog__box');
      if (!box) { return null; }
      return {
        title: (box.querySelector('.ui-dialog__title') || {}).textContent || null,
        head: (box.querySelector('.tk-plan-head') || {}).textContent || null,
        items: box.querySelectorAll('.tk-plan-item').length,
        groups: Array.prototype.map.call(box.querySelectorAll('.tk-plan-group'),
                 function(n){ return n.textContent; }),
        buttons: Array.prototype.map.call(box.querySelectorAll('.ui-dialog__foot button'),
                 function(n){ return n.textContent; }),
        note: (box.querySelector('.tk-plan-note') || {}).textContent || null
      };
    })(),
    storage: localStorage.getItem('eftmap.stories.progress.v1'),
    mini: !!(document.documentElement.classList.contains('tk-mini-root') ||
              document.body.classList.contains('tk-mini'))
  };
})()
"""

CLICK_TEXT = r"""
(function(text){
  var btns = document.querySelectorAll('.ui-dialog__foot button');
  for (var i = 0; i < btns.length; i++) {
    if (btns[i].textContent.trim() === text) { btns[i].click(); return true; }
  }
  return false;
})(%s)
"""

CLICK_LAST_STEP = r"""
(function(){
  var list = document.querySelectorAll('.tk-story-check');
  if (!list.length) { return null; }
  var b = list[list.length - 1];
  var id = b.dataset.storyStepToggle;
  var node = b.closest('[data-story-node]');
  var name = node ? (node.querySelector('.tk-story-name') || {}).textContent : null;
  b.click();
  return { id: id, name: name };
})()
"""


def state(cdp):
    return cdp.eval(STATE)


def stored_ids(cdp):
    doc = cdp.eval("(function(){try{return JSON.parse(localStorage.getItem(%s)||'null');}"
                   "catch(e){return null;}})()" % json.dumps(LS_KEY))
    if not doc:
        return []
    steps = (((doc.get("modes") or {}).get("regular") or {}).get("steps") or {}).get(BATYA) or {}
    return sorted(steps.keys())


def open_story(cdp, port, hash_):
    cdp.call("Page.navigate", url="http://127.0.0.1:%d/index.html%s" % (port, hash_))
    A.wait_for(cdp, "!!document.querySelector('.tk-story-check')", timeout=60, label="剧情节点")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8791)
    ap.add_argument("--cdp", type=int, default=9335)
    ap.add_argument("--out", default=os.path.join(tempfile.gettempdir(), "r100_shots"))
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    chrome = A.find_chrome(None)
    profile = tempfile.mkdtemp(prefix="r100_chrome_")
    proc, ws_url = A.launch(chrome, args.cdp, 1680, 1180, profile)
    cdp = A.CDP(ws_url)
    out = {"checks": []}

    def check(name, ok, detail=None):
        out["checks"].append({"case": name, "ok": bool(ok), "detail": detail})

    try:
        cdp.call("Network.enable")
        cdp.call("Network.setBlockedURLs",
                 urls=["*api/config*", "*api/prefs*", "*api/events*"])
        cdp.call("Page.enable")

        # ---- 1) 冷启动 + 深链 #stories:<id>~<pointKey>
        deep = "#stories:%s~%s" % (BATYA, BATYA_POINT)
        open_story(cdp, args.port, deep)
        time.sleep(0.5)
        s0 = state(cdp)
        check("深链进入后落在该剧情点（有 is-focus 节点）", s0["focus"] >= 1, s0["focus"])
        check("初始未开始（0 步已完成）", s0["on"] == 0, s0["progText"])
        # 展开全部步骤（深链带了 pointKey 时默认已展开，只在按钮文字是「展开」时点）
        cdp.eval("(function(){var b=document.querySelector('.tk-story-expand');"
                 "if(b && b.textContent.indexOf('展开') === 0){b.click();return 1;}return 0;})()")
        time.sleep(0.3)
        s1 = state(cdp)
        total = s1["toggles"]
        check("全部 %d 个步骤可见" % total, total > 20, total)
        cdp.shot(os.path.join(args.out, "r100_1_initial.png"))

        # ---- 2) 勾最后一个步骤 → 弹窗
        clicked = cdp.eval(CLICK_LAST_STEP)
        A.wait_for(cdp, "!!document.querySelector('.ui-dialog__box')", timeout=10, label="前置弹窗")
        d = state(cdp)["dialog"]
        n_plan = d["items"]
        check("勾最后一步弹出前置弹窗", d is not None and d["title"] == "前置步骤尚未完成",
              d and d["title"])
        check("弹窗数量 = 前置未完成步数（%d）" % (total - 1), n_plan == total - 1, n_plan)
        check("弹窗有步骤标题与层次分组", bool(d["head"]) and len(d["groups"]) >= 1,
              {"head": d["head"], "groups": d["groups"][:3]})
        check("取消按钮存在", "取消" in d["buttons"], d["buttons"])
        cdp.shot(os.path.join(args.out, "r100_2_dialog.png"))
        before_storage = state(cdp)["storage"]

        # ---- 3) 取消：不改状态、不写 storage
        cdp.eval(CLICK_TEXT % json.dumps("取消"))
        A.wait_for(cdp, "!document.querySelector('.ui-dialog__box')", timeout=10, label="弹窗关闭")
        s_cancel = state(cdp)
        check("取消后一步都没勾上", s_cancel["on"] == 0, s_cancel["progText"])
        check("取消后 localStorage 无新增写入", s_cancel["storage"] == before_storage,
              {"before": before_storage, "after": s_cancel["storage"]})

        # ---- 4) 再勾一次 → 确认级联
        cdp.eval(CLICK_LAST_STEP)
        A.wait_for(cdp, "!!document.querySelector('.ui-dialog__box')", timeout=10, label="前置弹窗")
        cdp.eval(CLICK_TEXT % json.dumps("确认并完成前置步骤"))
        A.wait_for(cdp, "!document.querySelector('.ui-dialog__box')", timeout=10, label="弹窗关闭")
        time.sleep(0.3)
        s2 = state(cdp)
        check("确认后实际勾选数 = 弹窗列出数 + 当前步骤",
              s2["on"] == n_plan + 1, {"on": s2["on"], "plan": n_plan})
        prog = (s2["progText"] or "").replace(" ", "")
        check("进度统计同步", ("%d/%d" % (n_plan + 1, total)) in prog, s2["progText"])
        check("进度条宽度同步（>0）", bool(s2["progWidth"]) and s2["progWidth"] != "0%", s2["progWidth"])
        check("三态同步：最后一步为已完成", s2["badges"]["done"] == n_plan + 1, s2["badges"])
        ids = stored_ids(cdp)
        check("localStorage 一次写入 %d 个步骤" % (n_plan + 1), len(ids) == n_plan + 1, len(ids))
        check("localStorage 只写剧情专属键，未动任务进度",
              cdp.eval("!localStorage.getItem('eftmap.tasks.progress.v1')"), True)
        cdp.shot(os.path.join(args.out, "r100_3_done.png"))

        # ---- 5) 重复同样操作：撤销最后一步 → 再勾 → 不再弹窗
        again = cdp.eval(CLICK_LAST_STEP)
        time.sleep(0.25)
        s3 = state(cdp)
        check("撤销最后一步不弹窗（后面没有已完成的步骤）", s3["dialog"] is None, s3["dialog"])
        check("撤销后回到 %d 步" % n_plan, s3["on"] == n_plan, s3["on"])
        clicked = cdp.eval(CLICK_LAST_STEP)
        time.sleep(0.25)
        s4 = state(cdp)
        check("前置已满足时再勾最后一步不弹窗", s4["dialog"] is None, s4["dialog"])
        check("直接完成且回到 %d 步" % (n_plan + 1), s4["on"] == n_plan + 1, s4["on"])

        # ---- 5b) 反向：撤销中间步骤 → 提示重置后续（与任务「取消后续」同构）
        idx_mid = 19   # 第 20 步，后面还有 18 步已完成
        cdp.eval("document.querySelectorAll('.tk-story-check')[%d].click()" % idx_mid)
        A.wait_for(cdp, "!!document.querySelector('.ui-dialog__box')", timeout=10, label="重置弹窗")
        d2 = state(cdp)["dialog"]
        n_reset = d2["items"] if d2 else -1
        check("撤销中间步骤弹出重置后续弹窗", d2 is not None and d2["title"] == "重置后续步骤？",
              d2 and d2["title"])
        check("重置数量 = 已完成后续步数（%d）" % (total - idx_mid - 1),
              n_reset == total - idx_mid - 1, n_reset)
        before_reset = state(cdp)["storage"]
        cdp.eval(CLICK_TEXT % json.dumps("取消"))
        A.wait_for(cdp, "!document.querySelector('.ui-dialog__box')", timeout=10, label="弹窗关闭")
        s_cancel2 = state(cdp)
        check("重置弹窗取消后仍是 %d 步且 storage 不变" % (n_plan + 1),
              s_cancel2["on"] == n_plan + 1 and s_cancel2["storage"] == before_reset,
              {"on": s_cancel2["on"]})
        # 仅撤销当前步骤
        cdp.eval("document.querySelectorAll('.tk-story-check')[%d].click()" % idx_mid)
        A.wait_for(cdp, "!!document.querySelector('.ui-dialog__box')", timeout=10, label="重置弹窗")
        cdp.eval(CLICK_TEXT % json.dumps("仅撤销当前步骤"))
        A.wait_for(cdp, "!document.querySelector('.ui-dialog__box')", timeout=10, label="弹窗关闭")
        s_only = state(cdp)
        check("仅撤销当前步骤后剩 %d 步" % (total - 1), s_only["on"] == total - 1, s_only["on"])
        # 再勾回来 → 前置都已完成，不再弹窗
        cdp.eval("document.querySelectorAll('.tk-story-check')[%d].click()" % idx_mid)
        time.sleep(0.25)
        s_back = state(cdp)
        check("勾回中间步骤不弹窗且回到 %d 步" % total,
              s_back["dialog"] is None and s_back["on"] == total, s_back["on"])

        # ---- 6) 刷新后仍在
        cdp.call("Page.reload")
        A.wait_for(cdp, "!!document.querySelector('.tk-story-check')", timeout=60, label="刷新后剧情节点")
        time.sleep(0.4)
        s5 = state(cdp)
        check("刷新后进度保持 %d 步" % (n_plan + 1), s5["on"] == n_plan + 1, s5["on"])

        # ---- 7) ?mini=1 零影响
        cdp.call("Page.navigate",
                 url="http://127.0.0.1:%d/index.html?mini=1#stories:%s" % (args.port, BATYA))
        A.wait_ready(cdp, want_url="mini=1")
        time.sleep(1.0)
        s6 = state(cdp)
        check("?mini=1 下没有可见剧情节点", s6["visibleNodes"] == 0,
              {"nodes": s6["stepNodes"], "visible": s6["visibleNodes"], "toggles": s6["toggles"]})
        check("?mini=1 下没有弹窗", s6["dialog"] is None)
        check("?mini=1 被识别为迷你模式", s6["mini"] is True, s6["mini"])

        out["n_plan"] = n_plan
        out["total"] = total
        out["console"] = [m.get("text") for m in cdp.console
                          if m.get("type") in ("error", "assert", "exception")]
        check("控制台无报错", not out["console"], out["console"])
        out["all_ok"] = all(c["ok"] for c in out["checks"])
        print(json.dumps(out, ensure_ascii=False, indent=2))
    finally:
        try:
            proc.terminate()
        except Exception:
            pass


if __name__ == "__main__":
    main()
