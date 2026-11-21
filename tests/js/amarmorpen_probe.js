// R19.8b：从 app.js 提取穿透模型（Desmos 主模型 + table 备选），输出测试向量。
// 用法：node tests/js/amarmorpen_probe.js <app.js 路径>
'use strict';
const fs = require('fs');

const src = fs.readFileSync(process.argv[2], 'utf8');

function extractFn(marker) {
  const start = src.indexOf(marker);
  if (start < 0) { return null; }
  let i = src.indexOf('{', start), depth = 0, end = -1;
  for (; i < src.length; i++) {
    if (src[i] === '{') { depth++; }
    else if (src[i] === '}') { depth--; if (depth === 0) { end = i + 1; break; } }
  }
  return end < 0 ? null : src.slice(start, end);
}

const fDesmos = extractFn('function amDesmosChance(p, c, d) {');
const anchor = 'function amArmorPenChance(p, c, dur, durMax, durOrig) {';
const blockStart = src.indexOf('var AM_ARMOR_PEN_MODEL');
if (!fDesmos || blockStart < 0 || src.indexOf(anchor) < 0) {
  console.log(JSON.stringify({ extracted: false }));
  process.exit(0);
}
const fModel = extractFn(anchor);
const block = src.slice(blockStart, src.indexOf(anchor) + fModel.length);
const factory = new Function(
  fDesmos + '\n' + block + '\n' +
  'return { f: amArmorPenChance, setModel: function(m){ AM_ARMOR_PEN_MODEL = m; }, getModel: function(){ return AM_ARMOR_PEN_MODEL; } };'
);
const M = factory();

function pair(p, c, dur, durMax, durOrig) {
  return { p: p, c: c, dur: dur, durMax: durMax, durOrig: durOrig, y: M.f(p, c, dur, durMax, durOrig) };
}

const cases = [];
for (const p of [37, 38, 39, 40, 41]) { cases.push(pair(p, 4, 40, 40, 40)); }
for (const p of [47, 48, 49, 50, 51]) { cases.push(pair(p, 5, 50, 50, 50)); }
cases.push(pair(47, 5, 30, 60, 60));   // 原始满 60，当前 30 → d=50
cases.push(pair(47, 5, 30, 30, 60));   // 维修后上限 30，原始满 60 → d=50
cases.push(pair(47, 5, 40, 50, 50));   // d=80
cases.push(pair(47, 5, 20, 50, 50));   // d=40
cases.push(pair(43, 6, 45, 45, 45));   // d=100
cases.push(pair(43, 6, 12, 45, 45));   // d=26.67
cases.push(pair(43, 6, 0, 45, 45));
cases.push(pair(null, 5, 30, 60, 60));
cases.push(pair(47, 5, -1, 50, 50));

M.setModel('table');
const tableCases = [];
for (const p of [37, 38, 39, 40, 41]) { tableCases.push(pair(p, 4, 40, 40, 40)); }
for (const p of [47, 48, 49, 50, 51]) { tableCases.push(pair(p, 5, 50, 50, 50)); }
tableCases.push(pair(47, 5, 30, 60, 60));
tableCases.push(pair(47, 5, 30, 30, 60));
M.setModel('desmos');

console.log(JSON.stringify({ extracted: true, model: M.getModel(), cases: cases, table: tableCases }));
