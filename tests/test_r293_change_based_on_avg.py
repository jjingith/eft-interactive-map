# -*- coding: utf-8 -*-
"""R293：榜单「涨跌额 / 涨跌幅」必须以「过去 48h 均价」为基准。

用户报告：当前价 666,666、过去48h均价 290,754，却显示涨跌额 596,666 /
+852.38%。根因是 enrichItem.stat() 拿窗口**第一个采样点**（本例 70,000）
当基准，而均价列显示的是**窗口平均值** —— 三列口径互相矛盾。

正确口径（用户明确给出）：
  涨跌额 = 当前价 - 均价
  涨跌幅 = (当前价 / 均价 - 1) × 100%
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ITEM = "5c0530ee86f774697952daf7"  # 突袭海报（仅作 fixture 的 id）
CUR = 666666
PTS = [
    ["2026-11-16T12:00:00+00:00", 70000],   # 异常低点：旧代码拿它当基准
    ["2026-11-16T18:00:00+00:00", 200000],
    ["2026-11-17T06:00:00+00:00", 300000],
    ["2026-11-17T12:00:00+00:00", 600000],
]

FIXTURE = {
    "overview": {
        "ok": True, "mode": "regular", "status": "ok",
        "generatedAt": "2026-11-17T12:00:00+00:00", "minOffers": 3,
        "gainers": [{"id": ITEM, "name": "突袭海报", "sector": "InfoContent",
                     "sectorLabel": "情报", "change": 852.38,
                     "changeAmount": 596666, "offers": 13, "price": CUR}],
        "losers": [], "hot": [],
    },
    "series": {"ok": True, "points": {ITEM: PTS}},
    "offers": {"ok": True, "status": "ok", "items": {}},
}


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_static_base_is_average_not_first_point():
    js = read("js/market-board.js")
    assert "var amount = (cur !== null) ? cur - avg : null;" in js
    assert "amount / avg * 100" in js
    # 防回退：旧基准必须消失
    assert "cur - first" not in js
    assert "amount / first" not in js


SMOKE = r'''
const fs = require('fs');
const fix = JSON.parse(fs.readFileSync(process.argv[2], 'utf-8'));
const keyed = new Map();
function ctx() {
  return { setTransform(){}, clearRect(){}, fillRect(){}, beginPath(){}, moveTo(){},
    lineTo(){}, stroke(){}, fill(){}, fillText(){}, save(){}, restore(){},
    measureText(){ return { width: 40 }; },
    set fillStyle(v){}, set strokeStyle(v){}, set lineWidth(v){}, set font(v){} };
}
function makeEl(tag, key) {
  return {
    tagName: tag, className: '', textContent: '', innerHTML: '', hidden: false,
    style: { width:'', height:'', setProperty(){} },
    children: [], dataset: {}, title:'', alt:'', src:'', value:'', type:'', loading:'',
    clientWidth: 1400, clientHeight: 400,
    classList: { add(){}, remove(){}, toggle(){}, contains(){return false;} },
    appendChild(x){ this.children.push(x); return x; },
    removeChild(x){ return x; },
    setAttribute(){}, getAttribute(){ return null; }, addEventListener(){},
    querySelector(sel){ return getEl((key||'') + '|' + sel); },
    querySelectorAll(){ return []; },
    getContext(){ return ctx(); }, closest(){ return null; }, focus(){}
  };
}
function getEl(sel) {
  if (!keyed.has(sel)) keyed.set(sel, makeEl('div', sel));
  return keyed.get(sel);
}
const root = getEl('ROOT');
root.closest = () => null;
global.document = {
  readyState: 'complete', body: makeEl('body'),
  getElementById(id){ return id === 'market-board-pane' ? root : null; },
  createElement(tag){ return makeEl(tag); },
  querySelector(sel){ return getEl(sel); }, querySelectorAll(){ return []; },
  addEventListener(){}, removeEventListener(){}
};
global.window = {
  devicePixelRatio: 1,
  localStorage: { getItem(){ return null; }, setItem(){} },
  addEventListener(){}, removeEventListener(){},
  requestAnimationFrame(fn){ fn(); },
  ResizeObserver: function(){ this.observe = function(){}; },
  GWMarketData: null, GWGameMode: null
};
global.ResizeObserver = window.ResizeObserver;
global.fetch = function(url) {
  let data = {};
  if (url.indexOf('market-overview') >= 0) data = fix.overview;
  else if (url.indexOf('prices/series') >= 0) data = fix.series;
  else if (url.indexOf('market-offers') >= 0) data = fix.offers;
  return Promise.resolve({ ok: true, status: 200, json(){ return Promise.resolve(data); } });
};

try {
  eval(fs.readFileSync(process.argv[3], 'utf-8'));
  window.GWMarketBoard.mount();
  window.GWMarketBoard.open();
  setTimeout(function () {
    // 期望值独立算一遍，避免手算错误；口径与用户给的一致
    const pts = fix.series.points[Object.keys(fix.series.points)[0]];
    const avg = pts.reduce((s, p) => s + p[1], 0) / pts.length;
    const cur = fix.overview.gainers[0].price;
    const wantAvg = Math.round(avg).toLocaleString('zh-CN') + ' \u20bd';
    const wantAmount = Math.round(cur - avg).toLocaleString('zh-CN');
    const wantPct = '+' + ((cur / avg - 1) * 100).toFixed(2) + '%';

    const card = getEl('ROOT|[data-rank-card="gainers48"]');
    const tbody = card.querySelector('tbody');
    if (!tbody.children.length) { console.log('NO_ROWS'); process.exitCode = 1; return; }
    if (!tbody.children.length) { console.log('NO_ROWS'); process.exitCode = 1; return; }
    const tr = tbody.children[tbody.children.length - 1];
    const tds = tr.children;
    if (tds.length < 6) { console.log('BAD_TD_COUNT'); process.exitCode = 1; return; }
    const got = { avg: tds[3].textContent, amount: tds[4].textContent, pct: tds[5].textContent };
    const ok = got.avg === wantAvg && got.amount === wantAmount && got.pct === wantPct;
    console.log(JSON.stringify({ want: {avg:wantAvg, amount:wantAmount, pct:wantPct}, got: got, ok: ok }));
    process.exitCode = ok ? 0 : 1;
  }, 600);
} catch (e) {
  console.error('THROWN: ' + (e && e.stack ? e.stack.split('\n').slice(0, 3).join(' | ') : e));
  process.exitCode = 1;
}
'''


def test_rendered_change_matches_average_formula(tmp_path):
    fixture = tmp_path / "fixture.json"
    fixture.write_text(json.dumps(FIXTURE, ensure_ascii=False), encoding="utf-8")
    script = tmp_path / "smoke.js"
    script.write_text(SMOKE, encoding="utf-8")
    proc = subprocess.run(
        ["node", str(script), str(fixture), str(ROOT / "js" / "market-board.js")],
        cwd=str(ROOT), capture_output=True, text=True, timeout=30,
    )
    out = (proc.stdout or "").strip()
    assert proc.returncode == 0, \
        "涨跌口径不符合 (当前价-均价)/均价：%s / %s" % (out, (proc.stderr or "")[:300])
    assert '"ok":true' in out.replace(" ", ""), out
