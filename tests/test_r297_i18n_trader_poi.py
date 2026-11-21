# -*- coding: utf-8 -*-
"""R297：商人名不再被地图 POI 表误译 + 获取方式按图标对齐。

问题 1：配装界面多处把商人 Mechanic 显示成「机修区」。
根因：i18n.js 把 poi-zh.json 并进通用 entries，`tr("Mechanic")` 命中地名「机修区」；
`keptEnglish` 白名单只用于「未翻译统计」，**没有参与翻译判定**，所以挡不住。
同一英文既是商人名（应为 Mechanic）又是街区地名（应为机修区），必须按上下文分流。

问题 2：获取方式列原来是 inline-flex 流式排列，图标宽度在 11/16px 间跳，
多条来源各自漂移；用户要求并列且以图标为基准对齐。
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_JS = ROOT / "app.js"
I18N_JS = ROOT / "i18n.js"
STYLE = ROOT / "style.css"
I18N_DIR = ROOT / "data" / "i18n"


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_kept_whitelist_blocks_translation():
    js = read(I18N_JS)
    # 白名单必须先于词表判定，命中即返回 null
    assert "if (state.kept[s]) { return null; }" in js, \
        "白名单没有参与翻译判定，商人名仍会被 POI 表翻译"
    idx_kept = js.index("if (state.kept[s]) { return null; }")
    idx_entry = js.index("if (state.entries[s] != null) { return state.entries[s]; }")
    assert idx_kept < idx_entry, "白名单判定必须在词表查询之前"


def test_poi_zh_exposed_for_map_labels():
    js = read(I18N_JS)
    assert "function poiZh(text)" in js
    assert "state.poiEntries[s] || null" in js
    assert "poiZh: poiZh," in js
    assert "state.poiEntries[norm(k)] = DATA.poi.entries[k];" in js


def test_map_labels_use_explicit_poi_translation():
    js = read(APP_JS)
    assert "window.GWI18n.poiZh(label.text)" in js
    assert 'text.setAttribute("data-i18n-skip", "1")' in js, \
        "地图地名必须跳过后续自动翻译，否则会被白名单或其它词表二次改写"


def test_trader_names_colliding_with_poi_are_whitelisted():
    """只校验真正有冲突风险的：同时出现在商人表与地名表里的英文名。"""
    ui = json.loads(read(I18N_DIR / "ui-zh.json"))
    names = json.loads(read(I18N_DIR / "names.json"))
    poi = json.loads(read(I18N_DIR / "poi-zh.json"))
    kept = set((ui.get("keptEnglish") or {}).get("entries") or [])
    traders = set((names.get("traders") or {}).keys())
    poi_keys = set((poi.get("entries") or {}).keys())

    overlap = sorted(traders & poi_keys)
    assert "Mechanic" in overlap, "Mechanic 应同时是商人名与街区地名（本测试的前提）"
    missing = [t for t in overlap if t not in kept]
    assert not missing, "同名的商人名未进白名单，会被地名表翻译：%s" % missing
    # 地名表仍保留 Mechanic → 机修区（地图用 poiZh 显式取）
    assert poi["entries"].get("Mechanic") == "机修区"


SMOKE = r'''
const fs = require('fs');
const path = require('path');
const root = process.argv[2];
const i18nPath = process.argv[3];
function loadJSON(rel) {
  return JSON.parse(fs.readFileSync(path.join(root, rel), 'utf-8'));
}
global.window = { addEventListener() {} };
global.document = {
  readyState: 'loading',
  addEventListener() {},
  documentElement: { setAttribute() {} },
  body: {},
  createTreeWalker() { return { nextNode() { return null; } }; }
};
global.NodeFilter = { SHOW_TEXT: 4, FILTER_REJECT: 2, FILTER_ACCEPT: 1 };
global.fetch = function (url) {
  const rel = String(url).replace(/^.*?(data\/)/, '$1');
  return Promise.resolve({ ok: true, json() { return Promise.resolve(loadJSON(rel)); } });
};
eval(fs.readFileSync(i18nPath, 'utf-8'));
window.GWI18n.load().then(function () {
  console.log(JSON.stringify({
    mechanicTr: window.GWI18n.tr('Mechanic'),
    mechanicPoi: window.GWI18n.poiZh('Mechanic'),
    traderTrs: ['Fence', 'Prapor', 'Ref', 'BTR Driver', 'Therapist']
      .map(function (n) { return window.GWI18n.tr(n); }),
    normalTr: window.GWI18n.tr('Dorms')
  }));
}).catch(function (e) { console.error(String(e)); process.exitCode = 1; });
'''


def test_real_tables_keep_trader_english_but_translate_poi(tmp_path):
    script = tmp_path / "smoke.js"
    script.write_text(SMOKE, encoding="utf-8")
    proc = subprocess.run(
        ["node", str(script), str(ROOT), str(I18N_JS)],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")
    got = json.loads(proc.stdout.strip())
    assert got["mechanicTr"] is None, "商人 Mechanic 不应被翻译，实际：%r" % got["mechanicTr"]
    assert got["mechanicPoi"] == "机修区", "地图地名 Mechanic 仍应显示机修区"
    assert got["traderTrs"] == [None, None, None, None, None], \
        "商人名全部应保持英文，实际：%s" % got["traderTrs"]
    assert got["normalTr"] == "宿舍", "普通地名仍应正常翻译，实际：%r" % got["normalTr"]


def test_src_cell_is_icon_aligned_list():
    js = read(APP_JS)
    css = read(STYLE)
    assert 'list.className = "lw-src-list";' in js
    assert "list.appendChild(chip);" in js
    assert "if (list.childNodes.length) { cell.appendChild(list); }" in js
    assert ".loadout-workbench .lw-src-list {" in css
    assert "flex-direction: column;" in css
    # 图标宽度必须统一（有头像 img / 无头像 svg）
    assert ".loadout-workbench .lw-src .lw-price-glyph" in css
    assert "flex: 0 0 16px;" in css
