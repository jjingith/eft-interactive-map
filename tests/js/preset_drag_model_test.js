// tests/js/preset_drag_model_test.js — R17S5：预设行拖放模型（空行可拖）确定性测试
// 直接从 app.js 抽取真实实现（amSimPresetDrop / amSimIdxByUid / 计数 helper），
// 不做任何复制实现，避免「测试通过但线上逻辑不同」。
'use strict';
const fs = require('fs');
const path = require('path');

const APP = path.join(__dirname, '..', '..', 'app.js');
const src = fs.readFileSync(APP, 'utf8');

const a = src.indexOf('function amSimPresetZoneLabel');
const b = src.indexOf('var AM_SIM_ZONES = [');
if (a < 0 || b < 0 || b <= a) { throw new Error('无法从 app.js 抽取拖放模型区间'); }

const body = src.slice(a, b);
const factory = new Function(
  'AM_SIM_ZONE_MAX', 'AM_SIM_ZONE_ROWS_MAX',
  body + '\n return { drop: amSimPresetDrop, idx: amSimIdxByUid, rows: amSimPresetZoneCount,' +
  ' ammo: amSimPresetZoneAmmoCount, ord: amSimZoneOrdinal, label: amSimPresetZoneLabel };'
);
const M = factory(5, 8);

// state: [zone, ammoId] → slot（uid 按生成顺序固定，模拟真实稳定性）
function mk(list) {
  let uid = 0;
  return { magPreset: list.map(function (x) { return { uid: ++uid, zone: x[0], ammoId: x[1] || null, count: x[1] ? 1 : 0 }; }) };
}
function view(s, zone) {
  return s.magPreset.filter(function (r) { return r.zone === zone; })
    .map(function (r) { return r.ammoId || '(空)'; });
}
function uidOf(s, zone, i) {
  const rows = s.magPreset.filter(function (r) { return r.zone === zone; });
  return rows[i] ? rows[i].uid : null;
}
const out = {};

// 1) 空首发 → 循环第一位：循环 [空,A,B,C]，首发不再包含该行
out.emptyTopToLoopFirst = (function () {
  const s = mk([['top', null], ['loop', 'A'], ['loop', 'B'], ['loop', 'C']]);
  const from = uidOf(s, 'top', 0);
  const target = uidOf(s, 'loop', 0);
  const r = M.drop(s, from, 'loop', target, 'before');
  return { moved: r.moved, msg: r.msg || null, top: view(s, 'top'), loop: view(s, 'loop'),
           uidCount: s.magPreset.length, uidUnique: new Set(s.magPreset.map(function (x) { return x.uid; })).size };
})();

// 2) 空末位 → 循环第二位：循环 [A,空,B,C]，末尾不再包含
out.emptyBottomToLoopSecond = (function () {
  const s = mk([['loop', 'A'], ['loop', 'B'], ['loop', 'C'], ['bottom', null]]);
  const from = uidOf(s, 'bottom', 0);
  const target = uidOf(s, 'loop', 1);
  const r = M.drop(s, from, 'loop', target, 'after');
  return { moved: r.moved, loop: view(s, 'loop'), bottom: view(s, 'bottom'), uidCount: s.magPreset.length };
})();

// 3) 空循环 → 首发（插入到已占用的首发区）
out.emptyLoopToTop = (function () {
  const s = mk([['top', 'D'], ['loop', 'A'], ['loop', null], ['loop', 'C']]);
  const from = uidOf(s, 'loop', 1);
  const target = uidOf(s, 'top', 0);
  const r = M.drop(s, from, 'top', target, 'after');
  return { moved: r.moved, top: view(s, 'top'), loop: view(s, 'loop') };
})();

// 4) 空行在循环区内部改顺序（C 前移到 A 之前）
out.emptyReorderInsideLoop = (function () {
  const s = mk([['loop', 'A'], ['loop', null], ['loop', 'C']]);
  const from = uidOf(s, 'loop', 1);
  const target = uidOf(s, 'loop', 0);
  const r = M.drop(s, from, 'loop', target, 'before');
  return { moved: r.moved, loop: view(s, 'loop'), ord: M.ord(s, s.magPreset[0].uid) };
})();

// 5) 空行拖入「已有 5 种弹药」的循环区：允许（空行不占弹药名额）
out.emptyIntoFullLoop = (function () {
  const s = mk([['top', null], ['loop', 'A'], ['loop', 'B'], ['loop', 'C'], ['loop', 'D'], ['loop', 'E']]);
  const from = uidOf(s, 'top', 0);
  const target = uidOf(s, 'loop', 4);
  const r = M.drop(s, from, 'loop', target, 'after');
  return { moved: r.moved, msg: r.msg || null, loop: view(s, 'loop'),
           ammoCount: M.ammo(s, 'loop'), rowCount: M.rows(s, 'loop'), top: view(s, 'top') };
})();

// 6) 带弹药条目拖入「已有 5 种弹药」的循环区：拒绝且配置零变化
out.ammoIntoFullLoop = (function () {
  const s = mk([['top', 'D'], ['loop', 'A'], ['loop', 'B'], ['loop', 'C'], ['loop', 'E1'], ['loop', 'E2']]);
  const before = JSON.stringify(s.magPreset);
  const from = uidOf(s, 'top', 0);
  const target = uidOf(s, 'loop', 0);
  const r = M.drop(s, from, 'loop', target, 'after');
  return { moved: r.moved, msg: r.msg || null, unchanged: JSON.stringify(s.magPreset) === before,
           top: view(s, 'top'), loop: view(s, 'loop') };
})();

// 7) 空行拖入不覆盖目标行已有弹药
out.emptyDoesNotOverwrite = (function () {
  const s = mk([['loop', 'A'], ['loop', 'B'], ['bottom', null]]);
  const from = uidOf(s, 'bottom', 0);
  const target = uidOf(s, 'loop', 0);
  const r = M.drop(s, from, 'loop', target, 'before');
  return { moved: r.moved, loop: view(s, 'loop'), bottom: view(s, 'bottom') };
})();

// 8) 连续多次拖动：uid 不重复、行数守恒、空行数量守恒
out.repeatedDrags = (function () {
  const s = mk([['top', null], ['loop', 'A'], ['loop', null], ['bottom', null]]);
  const uidSet = function () { return s.magPreset.map(function (x) { return x.uid; }).sort().join(','); };
  const u0 = uidSet();
  const emptyCount = function () { return s.magPreset.filter(function (x) { return !x.ammoId; }).length; };
  const e0 = emptyCount();
  // top空 → loop第1位前; 该空行进 loop 后再拖到 bottom; loop 剩余空行内部重排
  M.drop(s, uidOf(s, 'top', 0), 'loop', uidOf(s, 'loop', 0), 'before');   // 空行: top → loop 首位
  M.drop(s, uidOf(s, 'loop', 0), 'bottom', null, 'before');               // 同一个空行: loop → bottom
  M.drop(s, uidOf(s, 'top', 0), 'bottom', uidOf(s, 'bottom', 0), 'before'); // 另一个空行: top → bottom 首位
  M.drop(s, uidOf(s, 'loop', 2), 'loop', uidOf(s, 'loop', 0), 'before');  // loop 内部把末尾行前移
  return { uidStable: uidSet() === u0, rows: s.magPreset.length, emptySame: emptyCount() === e0,
           top: view(s, 'top'), loop: view(s, 'loop'), bottom: view(s, 'bottom') };
})();

// 9) 行数上限：空行拖入已达 8 行的区被拒（不破坏配置）
out.rowCapGuard = (function () {
  const s = mk([['top', null], ['loop', 'A'], ['loop', 'B'], ['loop', 'C'], ['loop', 'D'],
                ['loop', 'E'], ['loop', null], ['loop', null], ['loop', null]]);
  const before = JSON.stringify(s.magPreset);
  const r = M.drop(s, uidOf(s, 'top', 0), 'loop', uidOf(s, 'loop', 0), 'after');
  return { moved: r.moved, msg: r.msg || null, unchanged: JSON.stringify(s.magPreset) === before,
           rowCount: M.rows(s, 'loop') };
})();

process.stdout.write(JSON.stringify(out));
