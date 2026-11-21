# -*- coding: utf-8 -*-
"""R19.74：七天价格榜按「过去七天平均价格」降序。

用户口径：过去七天价格平均越高，排得越高。
旧的「连续上涨段」排序已被取消，只保留连涨信息在 tooltip 里，不参与排序。
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_static_seven_day_average_sort():
    js = read("js/market-board.js")
    assert "function sevenDayAvg(" in js
    assert "b.avg7 - a.avg7" in js
    assert "七天价格榜" in js
    # 连涨不再参与排序
    assert "b.trend.streakRatio - a.trend.streakRatio" not in js
    # 异常天价挂单剔除：以中位数为基准，超过 5 倍的不计入均价
    assert "vals[j] <= median * 5" in js
    assert "超过中位数 5 倍" in js


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
    const card = getEl('ROOT|[data-rank-card="trend"]');
    const tbody = card.querySelector('tbody');
    if (!tbody.children.length) { console.log('NO_ROWS'); process.exitCode = 1; return; }
    // stub 的 textContent="" 不清空 children，会残留首次渲染占位；过滤掉空值
    const order = tbody.children.map(function (tr) {
      return tr.children[1] && tr.children[1].children[1] &&
             tr.children[1].children[1].textContent;
    }).filter(function (name) { return !!name; });
    // 期望：均价 233 的「暴涨震荡」第一，均价 130 的「一路稳涨」第二；
    // 只有一笔 1000 万天价挂单的「离谱挂单」剔除异常后均价只有 50，必须排最后。
    const ok = order[0] === '暴涨震荡' && order[1] === '一路稳涨' && order[2] === '离谱挂单';
    console.log(JSON.stringify({ order, ok }));
    process.exitCode = ok ? 0 : 1;
  }, 600);
} catch (e) {
  console.error('THROWN: ' + (e && e.stack ? e.stack.split('\n').slice(0, 3).join(' | ') : e));
  process.exitCode = 1;
}
'''


def test_trend_ranks_highest_seven_day_average_first(tmp_path):
    steady = "100,110,120,130,140,150,160".split(",")
    spiky = "100,400,120,380,130,360,140".split(",")
    # 6 笔 50 ₽ + 1 笔 1000 万 ₽：不剔除异常时均价 ≈ 1,428,621，会霸占第一
    weird = "50,50,50,50,50,50,10000000".split(",")
    def pts(vals):
        return [["2026-11-%02dT12:00:00+00:00" % (11 + i), int(v)]
                for i, v in enumerate(vals)]
    fixture = {
        "overview": {
            "ok": True, "mode": "regular", "status": "ok",
            "generatedAt": "2026-11-17T12:00:00+00:00", "minOffers": 3,
            "gainers": [
                {"id": "spiky", "name": "暴涨震荡", "sector": "Other", "sectorLabel": "其他",
                 "change": 40, "offers": 50, "price": 140},
                {"id": "steady", "name": "一路稳涨", "sector": "Other", "sectorLabel": "其他",
                 "change": 60, "offers": 50, "price": 160},
                {"id": "weird", "name": "离谱挂单", "sector": "Other", "sectorLabel": "其他",
                 "change": 5, "offers": 50, "price": 50},
            ],
            "losers": [], "hot": [],
        },
        "series": {"ok": True, "points": {
            "steady": pts(steady), "spiky": pts(spiky), "weird": pts(weird),
        }},
        "offers": {"ok": True, "status": "ok", "items": {}},
    }
    fp = tmp_path / "fixture.json"
    fp.write_text(json.dumps(fixture, ensure_ascii=False), encoding="utf-8")
    script = tmp_path / "smoke.js"
    script.write_text(SMOKE, encoding="utf-8")
    proc = subprocess.run(
        ["node", str(script), str(fp), str(ROOT / "js" / "market-board.js")],
        cwd=str(ROOT), capture_output=True, text=True, timeout=30,
    )
    out = (proc.stdout or "").strip()
    assert proc.returncode == 0, \
        "七天价格榜未按均价排序：%s / %s" % (out, (proc.stderr or "")[:300])
    assert '"ok":true' in out.replace(" ", ""), out
