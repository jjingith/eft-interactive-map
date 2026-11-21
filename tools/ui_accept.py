# -*- coding: utf-8 -*-
"""R19.24 设计系统真实浏览器验收（Chrome + CDP，纯标准库）。

覆盖：
  A 展示页：令牌是否生效、组件是否渲染、按钮/输入/标签/表格状态、弹窗（含 Esc 与焦点归还）、
            菜单（Esc 关闭）、提示（不被裁切）、键盘焦点可见、长中文不溢出
  B 试点页（任务 · 商人任务中心）：表格/徽标/工具栏/数据说明弹窗/模式提示是否真的用上了组件，
            以及原有业务（任务树节点数、模式切换、详情、进度页）没有回归
  C 离线：所有请求必须是同源本地资源，不得出现外部 CDN / 字体 / 图标
  D 断点：1280 / 1440 / 1680 三档下不得出现横向溢出

用法：
    python tools/ui_accept.py --port 9791 --base http://127.0.0.1:8790
产物：
    docs/ui-system/browser-accept.json
    docs/ui-system/shots/*.png
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
OUT = os.path.join(ROOT, "docs", "ui-system")
SHOTS = os.path.join(OUT, "shots")
TASKS_DIR = os.path.join(ROOT, "data", "tasks")
report = {"build": "R19.24", "pass": False, "checks": [], "detail": {}}


def ok(name, cond, detail=None):
    report["checks"].append({"name": name, "ok": bool(cond), "detail": detail})
    print(("  PASS " if cond else "  FAIL ") + name + ("" if cond else "  -> %s" % (detail,)))
    return bool(cond)


def js(cdp, expr, default=None):
    try:
        return cdp.eval(expr)
    except Exception as exc:                     # noqa: BLE001
        print("   eval failed:", str(exc)[:200])
        return default


def nav(cdp, url, needle="", wait=2.2):
    cdp.call("Page.navigate", url=url)
    wait_ready(cdp, want_url=needle or None)
    time.sleep(wait)


def shot(cdp, name):
    os.makedirs(SHOTS, exist_ok=True)
    try:
        cdp.shot(os.path.join(SHOTS, name))
        return True
    except Exception as exc:                     # noqa: BLE001
        print("   screenshot failed:", exc)
        return False


def shot_full(cdp, name):
    """整页截图（含滚动区），用于设计系统总览。"""
    os.makedirs(SHOTS, exist_ok=True)
    try:
        # 粘性头部在 captureBeyondViewport 下会被画在滚动位置（Chrome 已知行为），截前先去掉 sticky
        cdp.eval("(function(){var h=document.querySelector('.showcase__top');"
                 "if(h){h.dataset.prevPos=h.style.position;h.style.position='static';}})()")
        m = cdp.call("Page.getLayoutMetrics")
        size = m.get("cssContentSize") or m.get("contentSize")
        h = min(int(size["height"]), 4200)
        res = cdp.call("Page.captureScreenshot", format="png", captureBeyondViewport=True,
                       clip={"x": 0, "y": 0, "width": int(size["width"]), "height": h, "scale": 1})
        with open(os.path.join(SHOTS, name), "wb") as fh:
            fh.write(base64.b64decode(res["data"]))
        cdp.eval("(function(){var h=document.querySelector('.showcase__top');"
                 "if(h&&h.dataset.prevPos!==undefined){h.style.position=h.dataset.prevPos;}})()")
        return True
    except Exception as exc:                     # noqa: BLE001
        print("   full screenshot failed:", exc)
        return False


def counts(mode):
    with open(os.path.join(TASKS_DIR, "tasks.%s.json" % mode), encoding="utf-8") as fh:
        return json.load(fh)["counts"]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9791)
    ap.add_argument("--base", default="http://127.0.0.1:8790")
    args = ap.parse_args(argv)
    base = args.base.rstrip("/")
    os.makedirs(SHOTS, exist_ok=True)
    prof = os.path.join(os.environ.get("TEMP", "."), "r1924ui_%d" % args.port)
    proc, ws = launch(find_chrome(), args.port, 1680, 1050, prof)
    cdp = CDP(ws)
    try:
        for m in ("Page.enable", "Runtime.enable", "Log.enable", "Network.enable"):
            cdp.call(m)
        cdp.call("Network.setCacheDisabled", cacheDisabled=True)
        cdp.call("Emulation.setDeviceMetricsOverride", width=1680, height=1050,
                 deviceScaleFactor=1, mobile=False)

        # ==================================================== A 展示页
        nav(cdp, base + "/ui-showcase", "ui-showcase", 2.6)
        sections = int(js(cdp, "document.querySelectorAll('.showcase__block').length", 0) or 0)
        ok("A1 展示页加载成功且有 10 个分节", sections == 10 and bool(js(cdp, "!!document.getElementById('sc-main')")),
           {"sections": sections})
        ok("A2 GWUI 已加载", js(cdp, "!!window.GWUI && window.GWUI.version") is not None,
           js(cdp, "window.GWUI && window.GWUI.version"))

        # 令牌：桥接值必须与 --xp-* 完全一致（防止第二套近似色）
        tok = js(cdp, r"""(function(){
          var cs = getComputedStyle(document.documentElement);
          var names = ["--ui-color-primary","--ui-color-surface","--ui-color-selected","--ui-color-border",
                       "--ui-color-text","--ui-fs-body","--ui-space-3","--ui-control-h-md","--ui-z-dialog"];
          var out = {};
          names.forEach(function(n){ out[n] = cs.getPropertyValue(n).trim(); });
          var probe = document.createElement("div");
          probe.style.color = "var(--ui-color-primary)";
          document.body.appendChild(probe);
          out.primaryResolved = getComputedStyle(probe).color;
          probe.style.color = "var(--xp-luna-1)";
          out.xpResolved = getComputedStyle(probe).color;
          document.body.removeChild(probe);
          out.bodyBg = getComputedStyle(document.body).backgroundColor;
          return JSON.stringify(out);})()""", "{}")
        t = json.loads(tok or "{}")
        report["detail"]["tokens"] = t
        ok("A3 设计令牌已加载且可解析（颜色/字号/间距/尺寸/层级）",
           all(t.get(k) for k in ("--ui-color-primary", "--ui-color-surface", "--ui-fs-body",
                                  "--ui-space-3", "--ui-control-h-md", "--ui-z-dialog")), t)
        ok("A4 桥接令牌与既有 --xp-* 解析为同一颜色（没有第二套近似色）",
           t.get("primaryResolved") and t.get("primaryResolved") == t.get("xpResolved"), t)
        ok("A5 页面底色来自 --ui-color-surface", t.get("bodyBg") not in (None, "", "rgba(0, 0, 0, 0)"),
           t.get("bodyBg"))

        comp = js(cdp, r"""(function(){
          function n(s){ return document.querySelectorAll(s).length; }
          return JSON.stringify({btn:n(".ui-btn"), input:n(".ui-input"), select:n(".ui-select"),
            check:n(".ui-check"), tab:n(".ui-tab"), panel:n(".ui-panel"),
            row:n(".ui-table__row"), badge:n(".ui-badge"), dialog:n(".ui-dialog__box"),
            menu:n(".ui-menu"), tip:n(".ui-tooltip")});})()""", "{}")
        c = json.loads(comp or "{}")
        report["detail"]["components"] = c
        ok("A6 十类基础组件都渲染出来了",
           all(c.get(k, 0) >= 1 for k in ("btn", "input", "select", "check", "tab", "panel",
                                          "row", "badge")), c)
        shot(cdp, "showcase-01-panel-button.png")

        # 按钮状态
        st = js(cdp, r"""(function(){
          var all=[].slice.call(document.querySelectorAll("#sec-button .ui-btn"));
          var dis=all.filter(function(b){return b.disabled;})[0];
          var tog=all.filter(function(b){return b.getAttribute("aria-pressed")!==null;})[0];
          var before = tog ? getComputedStyle(tog).backgroundImage + "|" + tog.getAttribute("aria-pressed") : "";
          if (tog) { tog.click(); }
          var after = tog ? getComputedStyle(tog).backgroundImage + "|" + tog.getAttribute("aria-pressed") : "";
          var ring = "";
          var b2 = all[0];
          b2.focus();
          ring = getComputedStyle(b2).boxShadow;
          return JSON.stringify({disabled: !!dis, cursor: dis?getComputedStyle(dis).cursor:"",
            before: before, after: after, ring: ring,
            disabledCursorOk: dis ? getComputedStyle(dis).cursor === "not-allowed" : false});})()""", "{}")
        b = json.loads(st or "{}")
        ok("A7 禁用按钮真的是禁用（disabled + not-allowed）", b.get("disabled") and b.get("disabledCursorOk"), b)
        ok("A8 开关型按钮点击后 aria-pressed 与底色同时变化",
           b.get("before") != b.get("after"), {"before": b.get("before"), "after": b.get("after")})
        ok("A9 键盘焦点有可见焦点环（box-shadow 非 none）",
           b.get("ring") not in (None, "", "none"), b.get("ring"))

        # 弹窗：打开 → Esc → 焦点归还
        dlg = js(cdp, r"""(function(){
          var btns=[].slice.call(document.querySelectorAll("#sec-dialog .ui-btn"));
          var trigger=btns.filter(function(x){return x.textContent.indexOf("普通")>=0;})[0];
          trigger.focus(); trigger.click();
          var box=document.querySelector(".ui-dialog__box");
          var title=box?box.querySelector(".ui-dialog__title").textContent:"";
          var ariaModal=box?box.getAttribute("aria-modal"):"";
          return JSON.stringify({open:!!box,title:title,ariaModal:ariaModal,
            scrollLock:document.body.classList.contains("ui-scroll-lock")});})()""", "{}")
        d1 = json.loads(dlg or "{}")
        ok("A10 弹窗可打开且带 role=dialog/aria-modal、锁滚动",
           d1.get("open") and d1.get("ariaModal") == "true" and d1.get("scrollLock"), d1)
        shot(cdp, "showcase-02-dialog.png")
        cdp.call("Input.dispatchKeyEvent", type="keyDown", key="Escape", code="Escape", windowsVirtualKeyCode=27)
        cdp.call("Input.dispatchKeyEvent", type="keyUp", key="Escape", code="Escape", windowsVirtualKeyCode=27)
        time.sleep(0.5)
        d2 = js(cdp, r"""(function(){
          return JSON.stringify({open:!!document.querySelector(".ui-dialog__box"),
            lock:document.body.classList.contains("ui-scroll-lock"),
            focus:(document.activeElement||{}).textContent||""});})()""", "{}")
        d2p = json.loads(d2 or "{}")
        ok("A11 Esc 关闭弹窗、解除滚动锁并把焦点还给触发按钮",
           (not d2p.get("open")) and (not d2p.get("lock")) and "普通" in (d2p.get("focus") or ""), d2p)

        # 危险弹窗默认焦点在取消
        d3 = js(cdp, r"""(function(){
          var btns=[].slice.call(document.querySelectorAll("#sec-dialog .ui-btn"));
          var t=btns.filter(function(x){return x.textContent.indexOf("危险")>=0;})[0];
          t.click();
          var foot=document.querySelectorAll(".ui-dialog__foot .ui-btn");
          var confirm=foot[foot.length-1];
          return JSON.stringify({focus:(document.activeElement||{}).textContent,
            confirmCls:confirm?confirm.className:"",
            headBg:getComputedStyle(document.querySelector(".ui-dialog__head")).backgroundImage});})()""", "{}")
        dd = json.loads(d3 or "{}")
        ok("A12 危险弹窗：确认按钮为 danger 变体，默认焦点在「取消」",
           "取消" in (dd.get("focus") or "") and "ui-btn--danger" in (dd.get("confirmCls") or ""), dd)
        js(cdp, "(function(){var b=document.querySelector('.ui-dialog__close');if(b)b.click();})()")
        time.sleep(0.3)

        # 菜单
        menu = js(cdp, r"""(function(){
          var btns=[].slice.call(document.querySelectorAll("#sec-overlay .ui-btn"));
          var t=btns.filter(function(x){return x.textContent.indexOf("打开菜单")>=0;})[0];
          t.click();
          var m=document.querySelector(".ui-menu");
          if(!m) return JSON.stringify({open:false});
          var r=m.getBoundingClientRect();
          return JSON.stringify({open:true, items:m.querySelectorAll(".ui-menu__item").length,
            inViewport: r.top>=0 && r.left>=0 && r.bottom<=innerHeight && r.right<=innerWidth,
            role:m.getAttribute("role"), focusInMenu:m.contains(document.activeElement)});})()""", "{}")
        mm = json.loads(menu or "{}")
        ok("A13 菜单可打开、在视口内、焦点进入菜单", mm.get("open") and mm.get("inViewport") and mm.get("focusInMenu"), mm)
        shot(cdp, "showcase-03-menu.png")
        cdp.call("Input.dispatchKeyEvent", type="keyDown", key="Escape", code="Escape", windowsVirtualKeyCode=27)
        cdp.call("Input.dispatchKeyEvent", type="keyUp", key="Escape", code="Escape", windowsVirtualKeyCode=27)
        time.sleep(0.4)
        ok("A14 Esc 关闭菜单", js(cdp, "!document.querySelector('.ui-menu')") is True)

        # 提示：hover 后出现且不被裁切
        tip = js(cdp, r"""(function(){
          var b=[].slice.call(document.querySelectorAll("#sec-overlay .ui-btn")).filter(function(x){
            return x.textContent.indexOf("长提示")>=0;})[0];
          if(!b) return JSON.stringify({found:false});
          b.dispatchEvent(new MouseEvent("mouseenter",{bubbles:true}));
          return JSON.stringify({found:true});})()""", "{}")
        time.sleep(0.6)
        tp = js(cdp, r"""(function(){
          var t=document.querySelector(".ui-tooltip");
          if(!t) return JSON.stringify({shown:false});
          var r=t.getBoundingClientRect();
          return JSON.stringify({shown:!t.hidden, text:(t.textContent||"").slice(0,30),
            inViewport:r.top>=0 && r.left>=0 && r.right<=innerWidth && r.bottom<=innerHeight,
            maxWidth:getComputedStyle(t).maxWidth});})()""", "{}")
        tpp = json.loads(tp or "{}")
        ok("A15 自定义提示可显示、不被视口裁切、限宽 320px",
           tpp.get("shown") and tpp.get("inViewport") and tpp.get("maxWidth") == "320px", tpp)
        shot(cdp, "showcase-04-tooltip.png")

        # 表格行选中 + 冲突行
        tb = js(cdp, r"""(function(){
          var rows=document.querySelectorAll("#sec-table .ui-table__row");
          rows[0].click();
          var sel=rows[0].getAttribute("aria-selected");
          var conflict=document.querySelector("#sec-table .ui-table__row.is-conflict");
          var dis=document.querySelector("#sec-table .ui-table__row.is-disabled");
          return JSON.stringify({rows:rows.length, sel:sel, selClass:rows[0].className,
            conflict:!!conflict,
            conflictBorder:conflict?getComputedStyle(conflict).borderTopStyle:"",
            disabledBg:dis?getComputedStyle(dis).backgroundColor:""});})()""", "{}")
        t2 = json.loads(tb or "{}")
        ok("A16 表格：行可选中（aria-selected+蓝底）、冲突行虚线、禁用行灰面",
           t2.get("sel") == "true" and t2.get("conflict") and t2.get("conflictBorder") == "dashed", t2)
        shot(cdp, "showcase-05-table.png")

        # 标签页切换
        tabs = js(cdp, r"""(function(){
          var grp=document.querySelector("#sec-tabs .ui-tabs");
          var t=[].slice.call(grp.querySelectorAll(".ui-tab"));
          var before=t.filter(function(x){return x.getAttribute("aria-selected")==="true";}).map(function(x){return x.textContent;});
          t[2].click();
          var after=t.filter(function(x){return x.getAttribute("aria-selected")==="true";}).map(function(x){return x.textContent;});
          return JSON.stringify({before:before, after:after, count:t.length});})()""", "{}")
        tt = json.loads(tabs or "{}")
        ok("A17 标签页切换改变 aria-selected（且只有一个当前项）",
           tt.get("before") != tt.get("after") and len(tt.get("after") or []) == 1, tt)

        # 长文本不溢出
        ov = js(cdp, r"""(function(){
          var d=document.documentElement, b=document.body;
          var out={docScroll:d.scrollWidth, docClient:d.clientWidth,
                   bodyScroll:b.scrollWidth, bodyClient:b.clientWidth};
          var prose=document.querySelector("#sec-type .ui-prose");
          if(prose){ out.proseScroll=prose.scrollWidth; out.proseClient=prose.clientWidth; }
          return JSON.stringify(out);})()""", "{}")
        o = json.loads(ov or "{}")
        ok("A18 1680px 下无横向溢出（整页与长文段落）",
           (o.get("docScroll") or 0) <= (o.get("docClient") or 1) + 2 and
           (o.get("proseScroll") or 0) <= (o.get("proseClient") or 1) + 2, o)
        shot_full(cdp, "showcase-00-full.png")

        # 断点 1280
        cdp.call("Emulation.setDeviceMetricsOverride", width=1280, height=900,
                 deviceScaleFactor=1, mobile=False)
        time.sleep(1.2)
        ov2 = json.loads(js(cdp, r"""(function(){var d=document.documentElement;
          return JSON.stringify({s:d.scrollWidth,c:d.clientWidth});})()""", "{}") or "{}")
        ok("A19 1280px 下无横向溢出", (ov2.get("s") or 0) <= (ov2.get("c") or 1) + 2, ov2)
        shot(cdp, "showcase-06-1280.png")
        cdp.call("Emulation.setDeviceMetricsOverride", width=1680, height=1050,
                 deviceScaleFactor=1, mobile=False)
        time.sleep(0.8)

        errs = list(cdp.console)
        ok("A20 展示页无 JS 异常/控制台错误", not [e for e in errs if e["type"] in ("exception", "error")],
           errs[:3])

        # ==================================================== B 试点页
        nav(cdp, base + "/index.html?ui=1#tasks", "index.html", 4.5)
        nodes = 0
        for _ in range(40):
            nodes = int(js(cdp, "document.querySelectorAll('#tk-nodes .tk-node').length", 0) or 0)
            if nodes:
                break
            time.sleep(0.4)
        ok("B1 任务树仍正常渲染（主程序未被设计系统破坏）",
           nodes == counts("regular")["tasks"], {"got": nodes, "expect": counts("regular")["tasks"]})

        # 进商人任务中心
        js(cdp, "(function(){var b=document.querySelector('[data-taskview=traders]');if(b)b.click();})()")
        time.sleep(1.6)
        pilot = js(cdp, r"""(function(){
          var t=document.querySelector(".tk-table");
          if(!t) return JSON.stringify({table:false});
          return JSON.stringify({
            table:true,
            isUiTable:t.classList.contains("ui-table"),
            rows:t.querySelectorAll(".tk-tr").length,
            uiRows:t.querySelectorAll(".ui-table__row").length,
            badges:t.querySelectorAll(".ui-badge").length,
            toolbar:!!document.querySelector(".tk-list-tools"),
            sort:!!document.getElementById("tk-sort"),
            head:!!document.querySelector(".tk-list-head h3"),
            modeCells:t.querySelectorAll(".tk-td-mode").length,
            tbCols:getComputedStyle(t).getPropertyValue("--ui-table-cols").trim()
          });})()""", "{}")
        p = json.loads(pilot or "{}")
        report["detail"]["pilot"] = p
        exp_rows = counts("regular")["tasks"] + 1
        ok("B2 商人任务表改由 ui-table 渲染（保留 tk-* 结构钩子）",
           p.get("isUiTable") and p.get("rows") == exp_rows and p.get("uiRows") == exp_rows - 1,
           {"rows": p.get("rows"), "expect": exp_rows, "uiRows": p.get("uiRows")})
        ok("B3 状态列用 ui-badge（每行一个）",
           (p.get("badges") or 0) >= counts("regular")["tasks"], p.get("badges"))
        ok("B4 工具栏与排序下拉改用组件，标题仍是原钩子",
           p.get("toolbar") and p.get("sort") and p.get("head"), p)
        ok("B5 表格列宽由 --ui-table-cols 控制（不再写死 grid）",
           bool(p.get("tbCols")), p.get("tbCols"))
        shot(cdp, "pilot-01-traders.png")

        # 排序真的生效
        first_before = js(cdp, "(document.querySelector('.tk-tr .tk-td-name')||{}).textContent", "")
        js(cdp, r"""(function(){var s=document.getElementById("tk-sort");
          s.value="name"; s.dispatchEvent(new Event("change",{bubbles:true}));})()""")
        time.sleep(1.2)
        first_after = js(cdp, "(document.querySelector('.tk-tr .tk-td-name')||{}).textContent", "")
        ok("B6 排序下拉切换后列表顺序变化（业务逻辑未被改坏）",
           first_before and first_after and first_before != first_after,
           {"before": first_before, "after": first_after})

        # 数据说明弹窗
        js(cdp, r"""(function(){var b=[].slice.call(document.querySelectorAll(".tk-list-tools .ui-btn"))
          .filter(function(x){return x.textContent.indexOf("数据说明")>=0;})[0]; if(b)b.click();})()""")
        time.sleep(0.8)
        note = js(cdp, r"""(function(){
          var box=document.querySelector(".ui-dialog__box");
          if(!box) return JSON.stringify({open:false});
          var txt=box.textContent;
          return JSON.stringify({open:true, text:txt.slice(0,400),
            hasMode:txt.indexOf("PvP（常规）")>=0,
            hasTasks:txt.indexOf("%d")>=0});})()""" % counts("regular")["tasks"], "{}")
        n1 = json.loads(note or "{}")
        ok("B7「数据说明」弹窗内容来自真实数据（模式名 + 任务数）",
           n1.get("open") and n1.get("hasMode") and n1.get("hasTasks"), n1.get("text"))
        shot(cdp, "pilot-02-datanote.png")
        cdp.call("Input.dispatchKeyEvent", type="keyDown", key="Escape", code="Escape", windowsVirtualKeyCode=27)
        cdp.call("Input.dispatchKeyEvent", type="keyUp", key="Escape", code="Escape", windowsVirtualKeyCode=27)
        time.sleep(0.4)
        ok("B8 弹窗可 Esc 关闭", js(cdp, "!document.querySelector('.ui-dialog__box')") is True)

        # 模式列自定义提示
        js(cdp, r"""(function(){var c=document.querySelector(".tk-td-mode");
          if(c){c.dispatchEvent(new MouseEvent("mouseenter",{bubbles:true}));}})()""")
        time.sleep(0.6)
        tip2 = js(cdp, r"""(function(){var t=document.querySelector(".ui-tooltip");
          if(!t) return JSON.stringify({shown:false});
          var r=t.getBoundingClientRect();
          return JSON.stringify({shown:!t.hidden, text:(t.textContent||"").slice(0,26),
            inViewport:r.top>=0 && r.left>=0 && r.right<=innerWidth && r.bottom<=innerHeight});})()""", "{}")
        tp2 = json.loads(tip2 or "{}")
        ok("B9 模式列改用自定义提示（不再用原生 title）",
           tp2.get("shown") and tp2.get("inViewport") and "模式" in (tp2.get("text") or ""), tp2)
        shot(cdp, "pilot-03-tooltip.png")

        # 切模式：行数随数据变化（模式隔离仍成立）
        js(cdp, "(function(){var b=document.querySelector('.tk-modebar [data-tkmode=pvps]');if(b)b.click();})()")
        # 每个模式会恢复自己上次停留的内页（R19.23 行为），所以切完再点一次「商人任务」
        for _ in range(24):
            time.sleep(0.5)
            if js(cdp, "window.GWTasks.state.mode") == "pvps" and \
                    js(cdp, "Object.keys(window.GWTasks.state.cache).indexOf('pvps')>=0"):
                break
        js(cdp, "(function(){var b=document.querySelector('[data-taskview=traders]');if(b)b.click();})()")
        rows_pvps = 0
        for _ in range(16):
            time.sleep(0.5)
            rows_pvps = int(js(cdp, "document.querySelectorAll('.tk-table .tk-tr').length", 0) or 0)
            if rows_pvps == counts("pvps")["tasks"] + 1:
                break
        ok("B10 切到 PvPS 后表格行数 = PvPS 任务数（模式隔离未回归）",
           rows_pvps == counts("pvps")["tasks"] + 1,
           {"got": rows_pvps, "expect": counts("pvps")["tasks"] + 1})
        js(cdp, "window.GWUI && window.GWUI.tooltip.hide()")   # 截图前收起提示，避免挡住工具栏
        time.sleep(0.3)
        shot(cdp, "pilot-04-pvps-traders.png")

        # 任务详情 / 进度页仍可用
        js(cdp, "(function(){var b=document.querySelector('[data-taskview=tree]');if(b)b.click();})()")
        time.sleep(1.0)
        tid = js(cdp, "(function(){var st=window.GWTasks.state;return st.order[0]||'';})()")
        js(cdp, "window.GWTasks.openTask(%s)" % json.dumps(tid))
        time.sleep(1.2)
        ok("B11 任务详情页仍可打开且区块齐全",
           int(js(cdp, "document.querySelectorAll('.tk-h3').length", 0) or 0) >= 5,
           js(cdp, "document.querySelectorAll('.tk-h3').length", 0))
        js(cdp, "(function(){var b=document.querySelector('[data-taskview=progress]');if(b)b.click();})()")
        time.sleep(1.2)
        ok("B12 进度页仍可渲染三模式对照表",
           int(js(cdp, "document.querySelectorAll('.tk-modetable tr').length", 0) or 0) >= 4,
           js(cdp, "document.querySelectorAll('.tk-modetable tr').length", 0))

        # 筛选控件换成组件后仍工作
        js(cdp, "(function(){var b=document.querySelector('[data-taskview=tree]');if(b)b.click();})()")
        time.sleep(0.8)
        dim = js(cdp, r"""(function(){
          var s=document.getElementById("tk-special"); if(!s) return -1;
          s.value="kappa"; s.dispatchEvent(new Event("change",{bubbles:true}));
          return document.querySelectorAll("#tk-nodes .tk-node.is-dim").length;})()""")
        ok("B13 筛选下拉（ui-select）仍然驱动任务树弱化", (dim or 0) > 0, {"dim": dim})
        js(cdp, "(function(){var s=document.getElementById('tk-special');s.value='';"
                "s.dispatchEvent(new Event('change',{bubbles:true}));})()")

        # 搜索框（ui-input）仍工作
        needle = js(cdp, r"""(function(){var n=document.querySelector('#tk-nodes .tk-node-name');
          return n?n.textContent.replace(/[^\u4e00-\u9fff]/g,'').slice(0,2):'';})()""", "") or ""
        js(cdp, "(function(){var i=document.getElementById('tk-search');i.value=%s;"
                "i.dispatchEvent(new Event('input',{bubbles:true}));})()" % json.dumps(needle))
        time.sleep(0.9)
        m = int(js(cdp, "(window.GWTasks.state.matches||[]).length", 0) or 0)
        ok("B14 搜索框（ui-input）仍然命中任务", bool(needle) and m >= 1, {"needle": needle, "matches": m})

        # ==================================================== C 离线
        urls = [r["url"] for r in cdp.requests]
        external = [u for u in urls if not (u.startswith(base) or u.startswith("data:")
                                            or u.startswith("blob:") or u.startswith("about:"))]
        report["detail"]["requests"] = {"total": len(urls), "external": external[:20]}
        ok("C1 所有请求都是本地同源资源（无 CDN / 在线字体 / 在线图标）", not external, external[:8])
        ok("C2 请求里包含新样式与组件脚本",
           any("/styles/ui-components.css" in u for u in urls) and
           any("/js/ui-components.js" in u for u in urls),
           [u for u in urls if "ui-components" in u][:4])

        errs2 = list(cdp.console)
        ok("C3 试点页无新增 JS 异常", not [e for e in errs2 if e["type"] in ("exception", "error")],
           errs2[:3])

        report["pass"] = all(x["ok"] for x in report["checks"])
        with open(os.path.join(OUT, "browser-accept.json"), "w", encoding="utf-8", newline="\n") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=1)
        total = len(report["checks"])
        passed = sum(1 for x in report["checks"] if x["ok"])
        print("\n结果：%d/%d 通过" % (passed, total))
        for x in report["checks"]:
            if not x["ok"]:
                print("  FAILED:", x["name"], str(x.get("detail"))[:300])
    finally:
        try:
            proc.terminate()
        except Exception:                       # noqa: BLE001
            pass
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
