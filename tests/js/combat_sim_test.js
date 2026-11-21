// r14 阶段C：combat_sim.js 场景测试（node，输出 JSON 供 pytest 断言）
// 用法：node tests/js/combat_sim_test.js <combat_sim.js 路径> <app.js 路径>
'use strict';
const fs = require('fs');
const path = require('path');

const CS = require(path.resolve(process.argv[2]));
const appSrc = fs.readFileSync(path.resolve(process.argv[3]), 'utf8');

// 从 app.js 提取真实的 amDesmosChance（与散点图共用同一实现）
function extractFn(marker) {
  const start = appSrc.indexOf(marker);
  if (start < 0) { throw new Error('marker not found: ' + marker); }
  let i = appSrc.indexOf('{', start), depth = 0, end = -1;
  for (; i < appSrc.length; i++) {
    if (appSrc[i] === '{') { depth++; }
    else if (appSrc[i] === '}') { depth--; if (depth === 0) { end = i + 1; break; } }
  }
  if (end < 0) { throw new Error('end brace not found'); }
  return new Function('return (' + appSrc.slice(start, end) + ')')();
}
const amDesmosChance = extractFn('function amDesmosChance(p, c, d) {');

const PMC_HP = { head: 35, chest: 85, stomach: 70, leftArm: 60, rightArm: 60, leftLeg: 60, rightLeg: 60 };
const out = {};

// 弹匣辅助：同一弹药重复 n 发（模拟整弹匣同种弹）
function rep(ammo, n) {
  var arr = [];
  for (var i = 0; i < n; i++) { arr.push(ammo); }
  return arr;
}

// 1. 无护甲直射：dmg42 → 85 血胸部 3 发死亡（弹匣 5 发，死亡后停射剩 2 发）
out.direct = CS.simulate({
  magazine: rep({ id: 'x', n: 'M995', dmg: 42, pen: 53, ard: 30, v0: 880, pc: 1 }, 5),
  rpm: 600, dist: 0, penChanceFn: amDesmosChance,
  targetPartHp: PMC_HP, armorLayers: [], hitProfile: { mode: 'fixed', part: 'chest' }, seed: 7
});

// 2. 满穿透桩：4 级板 + 穿透 → 伤害系数 clamp(53/52.5)=1 → ×0.9/层
out.pen1 = CS.simulate({
  magazine: rep({ id: 'x', n: 'M995', dmg: 42, pen: 53, ard: 30, v0: 880, pc: 1 }, 5),
  rpm: 600, dist: 0,
  penChanceFn: function () { return 1; },
  targetPartHp: PMC_HP,
  armorLayers: [{ name: 'plate', kind: 'plate', zones: ['chest'], cls: 4, dur: 40, durMax: 40, material: 'combined', bluntThroughput: 0.22 }],
  hitProfile: { mode: 'fixed', part: 'chest' }, seed: 7
});

// 3. 零穿透桩：只有钝伤 + 护甲逐发掉耐久（penLevel 夹持 0.5 → 每发约 3 点，5 发打不穿）
out.pen0 = CS.simulate({
  magazine: rep({ id: 'x', n: 'FMJ', dmg: 42, pen: 20, ard: 15, v0: 700, pc: 1 }, 5),
  rpm: 600, dist: 0,
  penChanceFn: function () { return 0; },
  targetPartHp: PMC_HP,
  armorLayers: [{ name: 'plate', kind: 'plate', zones: ['chest'], cls: 4, dur: 40, durMax: 40, material: 'combined', bluntThroughput: 0.22 }],
  hitProfile: { mode: 'fixed', part: 'chest' }, seed: 7
});

// 4. 混压弹匣顺序：[A,B,A] 且耗尽即停
out.mixed = CS.simulate({
  magazine: [
    { id: 'a', n: 'A弹', dmg: 20, pen: 10, ard: 5, v0: 300, pc: 1 },
    { id: 'b', n: 'B弹', dmg: 50, pen: 60, ard: 40, v0: 900, pc: 1 },
    { id: 'a', n: 'A弹', dmg: 20, pen: 10, ard: 5, v0: 300, pc: 1 }
  ],
  rpm: 600, dist: 0, penChanceFn: amDesmosChance,
  targetPartHp: { chest: 100 }, armorLayers: [], hitProfile: { mode: 'fixed', part: 'chest' }, seed: 3
});

// 5. 种子可复现：同种子同结果 / 异种子大概率不同（真实概率模型 + 分散命中）
const mkSim = function (seed) {
  return CS.simulate({
    magazine: rep({ id: 'x', n: 'BS', dmg: 40, pen: 38, ard: 28, v0: 880, pc: 1 }, 40),
    rpm: 800, dist: 50,
    flightFn: function (ammo, d) { return { speed: ammo.v0 * 0.9, pen: ammo.pen - 2, dmg: ammo.dmg * 0.95 }; },
    penChanceFn: amDesmosChance,
    targetPartHp: PMC_HP,
    armorLayers: [{ name: 'plate', kind: 'plate', zones: ['chest'], cls: 5, dur: 50, durMax: 50, material: 'uhmwpe', bluntThroughput: 0.24 }],
    hitProfile: { mode: 'dist', weights: { chest: 0.5, stomach: 0.3, head: 0.2 } },
    maxShots: 40, seed: seed
  });
};
out.reproA = mkSim(123);
out.reproA2 = mkSim(123);
out.reproB = mkSim(456);

// 6. 头部：头盔 2 级，满穿透 → 35 血头一枪死；零穿透 → 钝伤掉血不死
const headLayers = [{ name: 'helm', kind: 'helmet', zones: ['head'], cls: 2, dur: 20, durMax: 20, material: 'titan', bluntThroughput: 0.14 }];
out.headKill = CS.simulate({
  magazine: [{ id: 'x', n: 'SNB', dmg: 60, pen: 40, ard: 35, v0: 700, pc: 1 }],
  rpm: 600, dist: 0, penChanceFn: function () { return 1; },
  targetPartHp: PMC_HP, armorLayers: headLayers.map(function (l) { return JSON.parse(JSON.stringify(l)); }),
  hitProfile: { mode: 'fixed', part: 'head' }, seed: 1
});
out.headBlunt = CS.simulate({
  magazine: [{ id: 'x', n: 'FMJ', dmg: 30, pen: 10, ard: 8, v0: 400, pc: 1 }],
  rpm: 600, dist: 0, penChanceFn: function () { return 0; },
  targetPartHp: PMC_HP, armorLayers: headLayers.map(function (l) { return JSON.parse(JSON.stringify(l)); }),
  hitProfile: { mode: 'fixed', part: 'head' }, maxShots: 5, seed: 1
});

// 7. 手臂摧毁溢出：一发 100 打手臂 → 60 扣完，剩余 40 全额均摊到其余 6 个存活部位
// （0.49× 比例仅作用于对已摧毁部位的后续命中，见 combat_sim.js applyDamage/overflow）
out.overflow = CS.simulate({
  magazine: [{ id: 'x', n: '大口径', dmg: 100, pen: 70, ard: 50, v0: 800, pc: 1 }],
  rpm: 600, dist: 0, penChanceFn: amDesmosChance,
  targetPartHp: PMC_HP, armorLayers: [],
  hitProfile: { mode: 'fixed', part: 'leftArm' }, seed: 1
});

// 8. 霰弹多弹丸：pc=8，零穿透 → 护甲耐久单发至少掉 8（每颗最低 1）
out.pellets = CS.simulate({
  magazine: [{ id: 'x', n: '12g 霰弹', dmg: 12, pen: 6, ard: 4, v0: 400, pc: 8 }],
  rpm: 60, dist: 10, penChanceFn: function () { return 0; },
  targetPartHp: PMC_HP,
  armorLayers: [{ name: 'plate', kind: 'plate', zones: ['chest'], cls: 4, dur: 40, durMax: 40, material: 'armorSteel', bluntThroughput: 0.18 }],
  hitProfile: { mode: 'fixed', part: 'chest' }, maxShots: 1, seed: 1
});

// 9. 节奏：600rpm → 每发 100ms；耗尽即停（3 发弹匣只打 3 发）
out.timing = CS.simulate({
  magazine: [{ id: 'x', n: 'a', dmg: 1, pen: 1, ard: 1, v0: 100, pc: 1 },
             { id: 'x', n: 'a', dmg: 1, pen: 1, ard: 1, v0: 100, pc: 1 },
             { id: 'x', n: 'a', dmg: 1, pen: 1, ard: 1, v0: 100, pc: 1 }],
  rpm: 600, dist: 0, penChanceFn: function () { return 0; },
  targetPartHp: PMC_HP, armorLayers: [],
  hitProfile: { mode: 'fixed', part: 'chest' }, seed: 1
});

// 10. 耐久退化影响穿透概率：真实模型下，逐步降低耐久 → 同弹药同部位概率单调不降
let prev = -1, monotonic = true;
for (let d = 100; d >= 0; d -= 10) {
  const c = amDesmosChance(38, 5, d);
  if (c === null) { continue; }
  if (c < prev - 1e-12) { monotonic = false; }
  prev = c;
}
out.durMonotonic = monotonic;

// 11. 加权命中分布（原始百分比权重，总和≠1）：引擎须按权重总和归一化后抽取
const mkDist = function (weights, seed) {
  return CS.simulate({
    magazine: rep({ id: 'x', n: 'A', dmg: 1, pen: 1, ard: 1, v0: 100, pc: 1 }, 200),
    rpm: 600, dist: 0, penChanceFn: function () { return 0; },
    targetPartHp: { head: 100000, chest: 100000, stomach: 100000, leftArm: 100000, rightArm: 100000, leftLeg: 100000, rightLeg: 100000 },
    armorLayers: [], hitProfile: { mode: 'dist', weights: weights }, maxShots: 200, seed: seed
  });
};
const countParts = function (r) {
  const c = {};
  r.shots.forEach(s => { c[s.part] = (c[s.part] || 0) + 1; });
  return c;
};
out.rawDistHead5 = countParts(mkDist({ head: 5, chest: 95 }, 42));    // 头 ≈5%
out.rawDistHead95 = countParts(mkDist({ head: 95, chest: 5 }, 42));   // 头 ≈95%
out.rawDistNormalized = countParts(mkDist({ head: 0.5, chest: 0.5 }, 42)); // 已归一化权重同样有效

console.log(JSON.stringify(out));
