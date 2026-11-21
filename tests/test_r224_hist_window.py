# -*- coding: utf-8 -*-
"""R224：价格曲线的横轴必须按「所选区间」铺满，不能按数据首尾拉满。

用户原话（2026-11-10 15:09）：
  「现在24小时 七天和30天 怎么都是一样的曲线 注意 七天和30天 如果是因为没有数据
    那也要完整显示时间轴 没数据的部分就不显示线」

根因：`drawHistoryChart` 用 `rows[0]` / `rows[last]`（数据首尾）当时间轴两端。
7 天与 30 天返回的是同一批 86 个点（本地只有约 2 天数据），于是被分别拉伸到
整条画布，渲染结果像素级雷同；而 24h 也是拉满，只是点多一点。

本文件守住四条不变量：
1. 时间轴端点来自接口的 `windowStart`（或「全部」时的数据首尾），不来自 `rows`；
2. 轴刻度首尾 = 区间起点 / 终点，且中点刻度存在；
3. 采样断档按阈值切成多段，段与段之间不连线（孤立点单独画点）；
4. 图下不再渲染解释文案（R225 起）：区间 / 样本数 / 有数据时长 / 口径说明一律不出现。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MARKET_JS = ROOT / "js" / "market.js"


def _text() -> str:
    return MARKET_JS.read_text(encoding="utf-8-sig")


# ---------------------------------------------------------------- 静态契约

def test_axis_domain_comes_from_window_not_data():
    js = _text()
    # 旧的致命写法：拿数据首尾当轴
    assert "var t0 = parseTime(rows[0].t)" not in js
    assert "var t1 = parseTime(rows[rows.length - 1].t)" not in js
    # 新写法：窗口函数 + windowStart
    assert "function histWindow(windowStart, days, points)" in js
    assert "histWindow(data.windowStart, histState.days, series.points)" in js
    assert "function X(t) {" in js


def test_axis_ticks_cover_the_whole_window():
    js = _text()
    assert 'class="mk-hist-axis mk-hist-axis-x"' in js
    assert "mk-hist-axis-mid" in js
    # 三个刻度都用窗口端点/中点，不用 rows
    assert js.count("histStampMs(winT0, true)") >= 2
    assert js.count("histStampMs(winT1, true)") >= 2
    assert "histStampMs(midT, true)" in js


def test_gaps_break_the_line():
    js = _text()
    assert "function histGapMs(times)" in js
    assert "function histSegments(times, gapMs)" in js
    assert "linePaths.push(" in js and "areaPaths.push(" in js
    assert "lonely.push(pos[seg[0]])" in js
    # 每段单独起笔（M），不把所有点串成一条
    assert '(k ? "L" : "M")' in js


def test_footer_is_gone_entirely():
    """R225：图下的解释文案全部不显示（用户原话「这个注释直接去掉 不需要显示」）。"""
    js = _text()
    assert "覆盖 " not in js
    assert "data.coverageDays" not in js
    # 区间 / 样本 / 有数据时长 / 断档说明 / 口径说明，一条都不许回来
    assert "function histDurText(ms)" not in js
    assert "mk-hist-foot" not in js
    assert "mk-hist-gapnote" not in js
    assert "mk-hist-single" not in js
    assert '" · 有数据 "' not in js
    assert "不是逐笔成交" not in js
    # 唯一保留的说明：数据被截断（属数据缺失边界，不说会被读成「没有更早数据」）
    assert "只画最近 " in js


# ---------------------------------------------------------------- 纯函数（Node 抽函数）

NODE_JS = r"""
var fs = require("fs");
var src = fs.readFileSync(process.argv[2], "utf8");
function extractFn(source, name) {
  var i = source.indexOf("function " + name + "(");
  if (i < 0) { throw new Error("找不到 function " + name); }
  var depth = 0;
  for (var k = i; k < source.length; k++) {
    var c = source[k];
    if (c === '"' || c === "'" || c === "`") {
      var q = c; k++;
      while (k < source.length && source[k] !== q) { if (source[k] === "\\") { k++; } k++; }
      continue;
    }
    if (c === "/" && source[k + 1] === "/") { while (k < source.length && source[k] !== "\n") { k++; } continue; }
    if (c === "/" && source[k + 1] === "*") { k = source.indexOf("*/", k + 2); continue; }
    if (c === "{") { depth++; }
    else if (c === "}") { depth--; if (depth === 0) { return source.slice(i, k + 1); } }
  }
  throw new Error("花括号不平衡：" + name);
}
var FN = [
  extractFn(src, "parseTime"),
  extractFn(src, "histWindow"),
  extractFn(src, "histGapMs"),
  extractFn(src, "histSegments"),
  "return { histWindow: histWindow, histGapMs: histGapMs, histSegments: histSegments };"
].join("\n");
var api = new Function(FN)();
var chk = [];
function check(name, ok, extra) {
  chk.push((ok ? "PASS " : "FAIL ") + name + (ok ? "" : ("  <= " + (extra === undefined ? "" : extra))));
  if (!ok) { process.exitCode = 1; }
}

/* ① 7 天窗口：轴必须正好 7 天，与数据多少无关 */
var w7 = api.histWindow("2026-11-03T15:00:00+08:00", 7, [["2026-11-08T14:42:56+08:00", 1, 2]]);
var span7 = (w7.t1 - w7.t0) / 86400000;
check("① 7 天轴跨度 = 7 天", Math.abs(span7 - 7) < 1e-6, span7);
check("①b 轴起点 = windowStart", new Date(w7.t0).toISOString() === new Date("2026-11-03T15:00:00+08:00").toISOString());

/* ② 30 天窗口与 7 天窗口不等宽（旧写法两者都等于数据跨度，才会一模一样） */
var w30 = api.histWindow("2026-10-11T15:00:00+08:00", 30, [["2026-11-08T14:42:56+08:00", 1, 2]]);
check("② 30 天轴比 7 天宽 23 天",
  Math.abs((w30.t1 - w30.t0) - (w7.t1 - w7.t0) - 23 * 86400000) < 1e-6);

/* ③ 「全部」才用数据首尾 */
var wAll = api.histWindow(null, 0, [["2026-11-08T14:42:56+08:00", 1, 2], ["2026-11-10T15:01:02+08:00", 1, 2]]);
check("③ 全部模式用数据首尾",
  new Date(wAll.t0).toISOString() === new Date("2026-11-08T14:42:56+08:00").toISOString() &&
  new Date(wAll.t1).toISOString() === new Date("2026-11-10T15:01:02+08:00").toISOString());

/* ④ windowStart 缺失时兜底到「最后一点往前推 N 天」，仍不拉满数据 */
var wFallback = api.histWindow(null, 7, [["2026-11-08T14:42:56+08:00", 1, 2], ["2026-11-10T15:01:02+08:00", 1, 2]]);
check("④ 缺 windowStart 时按最后一点回推 7 天",
  Math.abs((wFallback.t1 - wFallback.t0) / 86400000 - 7) < 1e-6);

/* ⑤ 断档阈值：30 分钟采样 → 75 分钟；有 6 小时空档 → 切成 2 段 */
function times(list) { return list.map(function (s) { return new Date(s).getTime(); }); }
var normal = [];
for (var i = 0; i < 5; i++) { normal.push(new Date(Date.parse("2026-11-10T12:00:00+08:00") + i * 1800000).toISOString()); }
var tNormal = times(normal);
check("⑤ 30 分钟间隔的阈值 = 75 分钟", api.histGapMs(tNormal) === 75 * 60000, api.histGapMs(tNormal));
check("⑤b 连续采样只有 1 段", api.histSegments(tNormal, api.histGapMs(tNormal)).length === 1);

var withGap = times([
  "2026-11-08T14:42:56+08:00",
  "2026-11-08T20:45:43+08:00",
  "2026-11-08T21:15:43+08:00"
]);
var segs = api.histSegments(withGap, api.histGapMs(withGap));
check("⑤c 6 小时空档切成 2 段", segs.length === 2, JSON.stringify(segs));
check("⑤d 断档前的孤立点单独成段", segs[0].length === 1, JSON.stringify(segs));

console.log(chk.join("\n"));
"""


def test_hist_window_helpers(tmp_path):
    script = tmp_path / "hist_window_probe.js"
    script.write_text(NODE_JS, encoding="utf-8")
    node = subprocess.run(["node", str(script), str(MARKET_JS)],
                          capture_output=True, text=True, timeout=60)
    out = (node.stdout or "") + (node.stderr or "")
    assert node.returncode == 0, "时间轴 Node 断言失败：\n%s" % out
    assert "FAIL" not in node.stdout, out


# ---------------------------------------------------------------- 真实数据回归（服务端不参与，只算坐标）

def test_three_ranges_do_not_collapse_to_same_pixels():
    """同一批 86 个点，7 天与 30 天必须落在不同位置（纯算术，不依赖浏览器）。"""
    points = []
    start = 1762569776.0  # 2026-11-08 14:42:56 +08:00
    for i in range(86):
        points.append((start + i * 1800, 1000 + i))
    first, last = points[0][0], points[-1][0]

    def x_of(win_start, days):
        t0 = win_start
        t1 = win_start + days * 86400
        return (first - t0) / (t1 - t0)

    x7 = x_of(last - 7 * 86400, 7)
    x30 = x_of(last - 30 * 86400, 30)
    assert x30 > x7 + 0.15, "30 天的数据起点必须明显比 7 天更靠右：%s vs %s" % (x30, x7)
    assert 0.6 < x7 < 0.8, x7
    assert 0.9 < x30 < 0.97, x30
