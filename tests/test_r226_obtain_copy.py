# -*- coding: utf-8 -*-
"""R226：Obtain 获取途径不再外露上游字段名。

用户原话（2026-11-10 15:58）：
  「其中「上游 types 未含 noFlea」「（minLevelForFlea）」「；上表 src 只说明上游标记的
    获取方式」 这几个去掉 不需要显示」

守住四条：
1. `renderObtain()` 体内不得再出现 `noFlea` / `minLevelForFlea` / `上游 types` / `上表 src`；
2. 判定结论本身保留（「可上跳蚤」「上架等级 Lv N」「禁止上跳蚤」）；
3. 来源芯片与「当前模式行情没有…」那句保留（去掉尾巴，不动事实）；
4. Banned 禁售判定 tab 是另一处、主题就是禁售字段，不在本次范围内（不得被连带改坏）。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARKET_JS = os.path.join(ROOT, "js", "market.js")


def _read(path):
    with open(path, encoding="utf-8-sig") as fh:
        return fh.read()


def _obtain_body() -> str:
    js = _read(MARKET_JS)
    m = re.search(r"function renderObtain\(\) \{(.*?)\n  \}\n", js, re.S)
    assert m, "找不到 renderObtain() 函数体"
    return m.group(1)


def _banned_body() -> str:
    js = _read(MARKET_JS)
    m = re.search(r"function renderBanned\(\) \{(.*?)\n  \}\n", js, re.S)
    assert m, "找不到 renderBanned() 函数体"
    return m.group(1)


def _obtain_strings() -> str:
    """只取字符串字面量：`row.noFlea` 是代码变量，不算「显示出来的字段名」。"""
    body = _obtain_body()
    parts = re.findall(r'"([^"\\]*)"', body) + re.findall(r"'([^'\\]*)'", body)
    return "".join(parts)


def test_obtain_hides_upstream_field_names():
    text = _obtain_strings()
    for banned in ("noFlea", "minLevelForFlea", "上游 types", "上表 src"):
        assert banned not in text, "Obtain 的文案里不该再出现上游字段名：%s" % banned


def test_obtain_keeps_the_actual_verdict():
    body = _obtain_body()
    assert "可上跳蚤" in body
    assert "上架等级 Lv " in body
    assert "禁止上跳蚤" in body
    assert "不能在跳蚤挂单或购买。" in body
    # 上架等级后面直接结束，不带括号字段名
    assert body.count("（minLevelForFlea）") == 0


def test_obtain_keeps_sources_and_empty_trade_note():
    body = _obtain_body()
    assert "mk-src-chips" in body and "srcLabel" in body
    assert "当前模式行情没有该物品的商人买价或兑换配方。" in body
    # 旧尾巴必须消失
    assert "src 只说明" not in body


def test_banned_tab_still_explains_the_field():
    """Banned tab 的主题就是禁售判定，字段名在这里出现是有意的，不得被连带删掉。"""
    body = _banned_body()
    assert "noFlea" in body
    assert "Banned" in body


# ---------------------------------------------------------------- 真实渲染（Node 抽函数）

NODE_JS = r"""
var fs = require("fs");
var src = fs.readFileSync(process.argv[2], "utf8");
function body(name) {
  var i = src.indexOf("function " + name + "() {");
  if (i < 0) { throw new Error("找不到 " + name); }
  var depth = 0;
  for (var k = src.indexOf("{", i); k < src.length; k++) {
    var c = src[k];
    if (c === '"' || c === "'" || c === "`") {
      var q = c; k++;
      while (k < src.length && src[k] !== q) { if (src[k] === "\\") { k++; } k++; }
      continue;
    }
    if (c === "/" && src[k + 1] === "/") { while (k < src.length && src[k] !== "\n") { k++; } continue; }
    if (c === "{") { depth++; }
    else if (c === "}") { depth--; if (depth === 0) { return src.slice(i, k + 1); } }
  }
  throw new Error("花括号不平衡：" + name);
}

// 极简 DOM 桩：只够 renderObtain 跑起来，记录 append 的文本
function makeEl(tag, cls, text) {
  var node = {
    tag: tag, className: cls || "", children: [], _text: text === undefined ? null : String(text),
    appendChild: function (c) { this.children.push(c); return c; },
    get textContent() {
      var out = this._text === null ? "" : this._text;
      for (var i = 0; i < this.children.length; i++) { out += this.children[i].textContent; }
      return out;
    }
  };
  return node;
}
globalThis.el = makeEl;

var pane = makeEl("div");
globalThis.ui = { tabPane: pane };
globalThis.traderIcon = function () { return makeEl("img"); };
globalThis.traderNameOf = function (t) { return "T:" + t; };
globalThis.num = function (v) { return (v === null || v === undefined || isNaN(Number(v))) ? null : Number(v); };
globalThis.fmt = function (v) { return String(v); };
globalThis.api = { item: function () { return null; } };
globalThis.srcLabel = function (s) { return "SRC:" + s; };

var fnSrc = body("renderObtain");
var renderObtain = new Function("return " + fnSrc)();

var chk = [];
function check(name, ok, extra) {
  chk.push((ok ? "PASS " : "FAIL ") + name + (ok ? "" : ("  <= " + (extra === undefined ? "" : extra))));
  if (!ok) { process.exitCode = 1; }
}

function render(row) {
  pane.children = [];
  globalThis.modalRow = row;
  renderObtain();
  return pane.textContent;
}

var t1 = render({ id: "a", noFlea: false, lv: 30, rec: { src: ["flea"], trade: [] } });
check("① 可上跳蚤 + 上架等级", /可上跳蚤/.test(t1) && /上架等级 Lv 30/.test(t1), t1);
check("①b 无 noFlea / minLevelForFlea", t1.indexOf("noFlea") < 0 && t1.indexOf("minLevelForFlea") < 0, t1);
check("①c 无「上游 types」", t1.indexOf("上游 types") < 0, t1);
check("①d 无「上表 src」", t1.indexOf("上表 src") < 0 && t1.indexOf("src 只说明") < 0, t1);
check("①e 保留无商人买价说明", t1.indexOf("当前模式行情没有该物品的商人买价或兑换配方。") >= 0, t1);

var t2 = render({ id: "b", noFlea: true, lv: null, rec: { src: ["none"], trade: [] } });
check("② 禁售物品说「禁止上跳蚤」+「不能在跳蚤挂单或购买」",
  /禁止上跳蚤/.test(t2) && /不能在跳蚤挂单或购买/.test(t2), t2);
check("②b 禁售物品也不带字段名", t2.indexOf("noFlea") < 0, t2);

var t3 = render({ id: "c", noFlea: false, lv: null, rec: { src: ["flea"], trade: [{ k: "buy", t: "x", l: 4, c: "RUB", p: 100 }] } });
check("③ lv 为 null 时显示 —", /上架等级 Lv —/.test(t3), t3);
check("③b 有商人买价时不出现「没有…」", t3.indexOf("当前模式行情没有该物品") < 0, t3);

console.log(chk.join("\n"));
"""


def test_render_obtain_text(tmp_path):
    script = tmp_path / "obtain_probe.js"
    script.write_text(NODE_JS, encoding="utf-8")
    node = subprocess.run(["node", str(script), str(MARKET_JS)],
                          capture_output=True, text=True, timeout=60)
    out = (node.stdout or "") + (node.stderr or "")
    assert node.returncode == 0, "Obtain 渲染断言失败：\n%s" % out
    assert "FAIL" not in node.stdout, out
