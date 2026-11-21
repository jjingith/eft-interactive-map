// r14 阶段B：从 app.js 提取 amDesmosChance 纯函数，按固定向量求值并做性质断言。
// 用法：node tests/js/amdesmos_probe.js <app.js 路径>
// 输出 JSON：{ extracted, cases: [{p,c,d,y}], props: {...}, sweep: {...} }
'use strict';
const fs = require('fs');

const appPath = process.argv[2];
const src = fs.readFileSync(appPath, 'utf8');

// 花括号计数提取函数源码（app.js 是浏览器 IIFE，不能整体 require）
const marker = 'function amDesmosChance(p, c, d) {';
const start = src.indexOf(marker);
if (start < 0) { console.log(JSON.stringify({ extracted: false, error: 'marker not found' })); process.exit(0); }
let i = src.indexOf('{', start), depth = 0, end = -1;
for (; i < src.length; i++) {
  if (src[i] === '{') { depth++; }
  else if (src[i] === '}') { depth--; if (depth === 0) { end = i + 1; break; } }
}
if (end < 0) { console.log(JSON.stringify({ extracted: false, error: 'end brace not found' })); process.exit(0); }
const fnSrc = src.slice(start, end);
const amDesmosChance = new Function('return (' + fnSrc + ')')();

// 固定求值向量（期望值由 pytest 侧独立转录公式计算并断言）
const vectors = [
  [0, 6, 100], [40, 6, 100], [45.35510204081633, 6, 100], [45.36, 6, 100],
  [55, 6, 100], [60.35510204081633, 6, 100], [60.35510204081633 - 1e-9, 6, 100],
  [70, 6, 100], [1000, 6, 100], [30, 1, 50], [10, 3, 0], [0.5, 6, 0], [77, 6, 100]
];
const cases = vectors.map(function (v) {
  return { p: v[0], c: v[1], d: v[2], y: amDesmosChance(v[0], v[1], v[2]) };
});

// 性质断言（不依赖 Python 转录的独立锚点）
function a1(c, d) { return (121 - 5000 / (45 + 2 * d)) * c / 10; }
const a6 = a1(6, 100);
const props = {
  zeroBand_isZero: amDesmosChance(a6 - 15, 6, 100) === 0 && amDesmosChance(30, 6, 100) === 0,
  continuity_at_a: Math.abs(amDesmosChance(a6, 6, 100) - 0.9) < 1e-9 &&
                   Math.abs(amDesmosChance(a6 - 1e-9, 6, 100) - 0.9) < 1e-8,
  asymptote_below_1: (function () { var y = amDesmosChance(1000, 6, 100); return y < 1 && y > 0.98; })(),
  monotonic_high_pen: amDesmosChance(62, 6, 100) > amDesmosChance(61, 6, 100) &&
                      amDesmosChance(61, 6, 100) > 0.9,
  null_on_bad_input: amDesmosChance(null, 6, 100) === null &&
                     amDesmosChance(NaN, 6, 100) === null &&
                     amDesmosChance('x', 6, 100) === null &&
                     amDesmosChance(30, 'x', 100) === null &&
                     amDesmosChance(30, 6, 'x') === null &&
                     amDesmosChance(30, 0, 100) === null &&
                     amDesmosChance(30, 6, -1) === null &&
                     amDesmosChance(-5, 6, 100) === null,
  zero_dur_valid: (function () { var y = amDesmosChance(10, 3, 0); return typeof y === 'number' && y >= 0 && y <= 1; })()
};

// 全域扫描：p 0..80 步 0.5，c 1..6，d 0..100 步 5 → 全部为 [0,1] 内有限数且无 null
let sweepMin = 1, sweepMax = 0, sweepNull = 0, sweepCount = 0;
for (var c = 1; c <= 6; c++) {
  for (var d = 0; d <= 100; d += 5) {
    for (var p = 0; p <= 80.001; p += 0.5) {
      var y = amDesmosChance(p, c, d);
      sweepCount++;
      if (y === null || !isFinite(y)) { sweepNull++; continue; }
      if (y < sweepMin) { sweepMin = y; }
      if (y > sweepMax) { sweepMax = y; }
    }
  }
}
const sweep = { count: sweepCount, nullCount: sweepNull, min: sweepMin, max: sweepMax };

console.log(JSON.stringify({ extracted: true, cases: cases, props: props, sweep: sweep }));
