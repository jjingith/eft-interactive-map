# -*- coding: utf-8 -*-
"""R220：行情「数据年龄」必须随时间推进，不能停在快照被缓存的那一刻。

用户原话（2026-11-10）：
  「数据截止 11-09 15:01（20 小时前） · 非实时 · 已过期 8 小时 54 分钟  还是这样」

同一行出现两个互相矛盾的年龄：前半句由前端用 `snapshotAt` 现算（20 小时前），
后半句读服务端返回的 `ageSec`——而 `load_bundled` 把 `ageSec` / `stale` 连同快照一起缓存，
命中缓存直接返回旧值，进程活得越久落后越多（实测落后 27.9 分钟且 4 秒内不推进）。

本文件守住三件事：
  1. 服务端缓存命中时必须用「当前时间 − snapshotAt」重算 ageSec / stale；
  2. 前端一律现算（`liveAgeSec` / `liveStale`），服务端 ageSec 只作无时间戳时的兜底；
  3. `_error_text` 能读到 `CloudError.to_dict()` 的真实键名 `error`（旧代码读 message / detail）。
"""
from __future__ import annotations

import datetime
import json
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import prices_source  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MARKET_JS = ROOT / "js" / "market.js"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


# ---------------------------------------------------------------- 静态契约

def test_cutoff_never_trusts_baked_age():
    """前端不许再把服务端缓存的 ageSec 当作「已过期 N」的依据。"""
    js = _text(MARKET_JS)
    assert "function liveAgeSec(snap) {" in js, "缺少现算年龄的 liveAgeSec"
    assert "function liveStale(snap) {" in js, "缺少现算过期判定的 liveStale"
    assert "agePhrase(snap.ageSec)" not in js, "仍在直接展示服务端缓存的 ageSec"
    assert "stale = !!snap.stale;" not in js, "过期判定仍在直接信服务端缓存的 stale"
    # 展示处全部走现算（截止徽标 + 过期横幅）
    assert js.count("liveStale(snap)") >= 2
    assert js.count("liveAgeSec(snap)") >= 2


# ---------------------------------------------------------------- 前端现算（Node 抽函数）

LIVE_JS = r"""
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
function extractVar(source, name) {
  var i = source.indexOf("var " + name + " =");
  if (i < 0) { throw new Error("找不到 var " + name); }
  var j = source.indexOf(";", i);
  return source.slice(i, j + 1);
}
var chk = [];
function check(name, ok, extra) {
  chk.push((ok ? "PASS " : "FAIL ") + name + (ok ? "" : ("  <= " + (extra === undefined ? "" : extra))));
  if (!ok) { process.exitCode = 1; }
}
var FN = [
  extractVar(src, "STALE_HOURS"),
  extractFn(src, "parseTime"),
  extractFn(src, "agePhrase"),
  extractFn(src, "liveAgeSec"),
  extractFn(src, "liveStale"),
  "return { liveAgeSec: liveAgeSec, liveStale: liveStale, agePhrase: agePhrase };"
].join("\n");
var api = new Function(FN)();

function isoAgo(sec) { return new Date(Date.now() - sec * 1000).toISOString(); }
function near(a, b, tol) { return Math.abs(a - b) <= (tol || 10); }

/* ① 三小时前的快照 → 年龄约 10800 秒，且判为过期（阈值 2 小时） */
var threeH = api.liveAgeSec({ snapshotAt: isoAgo(3 * 3600), ageSec: 60, stale: false });
check("① 年龄按 snapshotAt 现算，不读缓存的 ageSec", near(threeH, 10800, 15), threeH);
check("①b 现算后判为过期（不读缓存的 stale=false）", api.liveStale({ snapshotAt: isoAgo(3 * 3600), ageSec: 60, stale: false }) === true);

/* ② 用户看到的那一行：20 小时前 vs 缓存的「8 小时 54 分钟」——现算必须给出 20 小时 */
var frozen = { snapshotAt: isoAgo(20 * 3600), ageSec: 8 * 3600 + 54 * 60, stale: true, staleAfterSec: 7200 };
var age20 = api.liveAgeSec(frozen);
check("② 20 小时前的快照算出 20 小时，不再是缓存的 8 小时 54 分", near(age20, 72000, 60), age20);
check("②b 文案为「20 小时」，与前半句「20 小时前」一致", api.agePhrase(age20) === "20 小时", api.agePhrase(age20));

/* ③ 刚生成的快照不能因为缓存 stale=true 就标红 */
var fresh = { snapshotAt: isoAgo(120), ageSec: 99999, stale: true, staleAfterSec: 7200 };
check("③ 2 分钟前的快照判为未过期", api.liveStale(fresh) === false);
check("③b 年龄约 120 秒", near(api.liveAgeSec(fresh), 120, 5), api.liveAgeSec(fresh));

/* ④ 时间戳不可解析 → 退回服务端 ageSec（兜底，不是主路径） */
check("④ 无时间戳时用 ageSec 兜底", api.liveAgeSec({ snapshotAt: "live", ageSec: 9999 }) === 9999);
check("④b 连 ageSec 都没有 → null，且不判过期", api.liveAgeSec({ snapshotAt: null }) === null &&
  api.liveStale({ snapshotAt: null }) === false);

/* ⑤ 阈值以服务端 staleAfterSec 为准 */
check("⑤ 服务端阈值更大时不误判过期", api.liveStale({ snapshotAt: isoAgo(3 * 3600), staleAfterSec: 40000 }) === false);

/* ⑥ 未来时间戳不出现负年龄 */
var future = api.liveAgeSec({ snapshotAt: new Date(Date.now() + 600000).toISOString() });
check("⑥ 未来时间戳收敛为 0", future === 0, future);

console.log(chk.join("\n"));
"""


def test_live_age_recomputes_in_browser(tmp_path):
    """R220 核心：年龄与过期判定都按本机当前时间现算。"""
    script = tmp_path / "live_age_probe.js"
    script.write_text(LIVE_JS, encoding="utf-8")
    node = subprocess.run(["node", str(script), str(MARKET_JS)],
                          capture_output=True, text=True, timeout=60)
    out = (node.stdout or "") + (node.stderr or "")
    assert node.returncode == 0, "年龄现算 Node 断言失败：\n%s" % out
    assert "FAIL" not in node.stdout, out


# ---------------------------------------------------------------- 服务端：缓存命中也要重算

def _bundle(root: Path, generated_at: str, items: dict) -> None:
    path = root / "data" / "flea-prices.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "meta": {"generatedAt": generated_at},
        "gameMode": "regular",
        "items": items,
        "counts": {"itemsUpstream": len(items)},
    }, ensure_ascii=False), encoding="utf-8")


def test_bundled_cache_hit_recomputes_age_and_stale(tmp_path):
    """同一份内置快照，第二次读（命中缓存）也必须给出更大的 ageSec 与翻转后的 stale。"""
    prices_source.clear_cache()
    generated = "2026-11-09T10:00:00+08:00"
    _bundle(tmp_path, generated, {"x": {"lastLowPrice": 100, "avg24hPrice": 120}})
    tz = datetime.timezone(datetime.timedelta(hours=8))
    base = datetime.datetime(2026, 11, 9, 10, 0, 0, tzinfo=tz)

    first = prices_source.load_bundled(str(tmp_path), "regular", base + datetime.timedelta(hours=1))
    assert first["ok"] and first["available"]
    assert first["ageSec"] == 3600
    assert first["stale"] is False

    second = prices_source.load_bundled(str(tmp_path), "regular", base + datetime.timedelta(hours=3))
    assert second["ageSec"] == 3 * 3600, "缓存命中仍在返回旧的 ageSec（R220 回归）"
    assert second["stale"] is True, "超过 2 小时必须翻成过期"
    # 缓存命中不能把数据弄丢
    assert second["items"]["x"]["l"] == 100 and second["items"]["x"]["a"] == 120
    prices_source.clear_cache()


def test_bundled_age_follows_wall_clock_without_restart(tmp_path):
    """再读一次（仍命中缓存）年龄继续推进，证明不是「启动时算一次」。"""
    prices_source.clear_cache()
    generated = "2026-11-09T10:00:00+08:00"
    _bundle(tmp_path, generated, {"y": {"lastLowPrice": 5}})
    tz = datetime.timezone(datetime.timedelta(hours=8))
    base = datetime.datetime(2026, 11, 9, 10, 0, 0, tzinfo=tz)
    ages = [
        prices_source.load_bundled(str(tmp_path), "regular", base + datetime.timedelta(minutes=m))["ageSec"]
        for m in (10, 40, 130)
    ]
    assert ages == [600, 2400, 7800], ages
    prices_source.clear_cache()


# ---------------------------------------------------------------- 报错文案读对键名

def test_error_text_reads_error_key():
    """CloudError.to_dict() 的键是 error / code；旧代码读 message / detail 读不到真实说明。"""
    class Exc(Exception):
        def to_dict(self):
            return {"ok": False, "error": "会员已过期，请续费后重试", "code": "membership_required"}

    text = prices_source._error_text(Exc("fallback"))
    assert "会员已过期" in text, text
    assert "membership_required" in text, text

    class Bare(Exception):
        pass

    assert prices_source._error_text(Bare("网络不可达")) == "网络不可达"
