# -*- coding: utf-8 -*-
"""R292：大盘整页挂载烟测（Node + 最小 DOM stub）。

R291 改造时曾把 renderRanks() 整个删掉，load() 抛 ReferenceError 后**整页空白**；
静态契约查不出来。这里真的执行 market-board.js 的 mount/open，
喂一份真实形状的响应，断言六个榜单都有行、且没有任何运行时异常。
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 最小但形状真实的接口响应（只用到字段，不依赖线上服务）
ITEM = "5447a9cd4bdc2dbd208b4567"
FIXTURE = {
    "overview": {
        "ok": True, "mode": "regular", "status": "ok", "generatedAt": "2026-11-17T12:00:00+00:00",
        "minOffers": 30,
        "gainers": [{"id": ITEM, "name": "测试物资", "change": 12.5, "changeAmount": 3500,
                     "offers": 40, "price": 31500}],
        "losers": [{"id": "b", "name": "跌幅物资", "change": -8.2, "changeAmount": -2000,
                    "offers": 35, "price": 22000}],
        "hot": [{"id": ITEM, "name": "测试物资", "offers": 40, "price": 31500}],
    },
    "series": {"ok": True, "points": {
        ITEM: [["2026-11-14T12:00:00+00:00", 28000],
               ["2026-11-16T12:00:00+00:00", 29000],
               ["2026-11-17T12:00:00+00:00", 31500]],
        "b": [["2026-11-14T12:00:00+00:00", 26000],
              ["2026-11-17T12:00:00+00:00", 22000]],
    }},
    "offers": {"ok": True, "status": "ok", "items": {
        ITEM: {"current": 40, "peak": 55, "samples": 12},
        "b": {"current": 35, "peak": 40, "samples": 12},
    }},
}

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
    const keys = ['gainers48','losers48','gainers24','losers24','hot','trend'];
    const empty = [];
    keys.forEach(function (k) {
      const card = getEl('ROOT|[data-rank-card="' + k + '"]');
      const tbody = card.querySelector('tbody');
      if (!tbody.children.length) { empty.push(k); }
    });
    console.log(empty.length ? ('EMPTY:' + empty.join(',')) : 'ALL_BOARDS_HAVE_ROWS');
    process.exitCode = empty.length ? 1 : 0;
  }, 600);
} catch (e) {
  console.error('THROWN: ' + (e && e.stack ? e.stack.split('\n').slice(0, 3).join(' | ') : e));
  process.exitCode = 1;
}
'''


def test_board_mount_renders_all_six_ranks(tmp_path):
    fixture = tmp_path / "fixture.json"
    fixture.write_text(json.dumps(FIXTURE, ensure_ascii=False), encoding="utf-8")
    script = tmp_path / "smoke.js"
    script.write_text(SMOKE, encoding="utf-8")
    proc = subprocess.run(
        ["node", str(script), str(fixture), str(ROOT / "js" / "market-board.js")],
        cwd=str(ROOT), capture_output=True, text=True, timeout=30,
    )
    out = (proc.stdout or "").strip()
    assert proc.returncode == 0 and out == "ALL_BOARDS_HAVE_ROWS", \
        "大盘挂载失败：%s / %s" % (out, (proc.stderr or "")[:300])


def test_render_ranks_is_defined():
    """补一道静态闸门：R291 曾误删该函数，导致整页空白但语法检查通过。"""
    js = (ROOT / "js" / "market-board.js").read_text(encoding="utf-8")
    assert "function renderRanks()" in js
