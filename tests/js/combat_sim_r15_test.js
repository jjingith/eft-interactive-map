// r15：逐发引擎专项场景（node 输出 JSON，再由 pytest 断言数值关系）
// 用法：node tests/js/combat_sim_r15_test.js <combat_sim.js 路径>
// 只导出原始计算结果；断言在 Python 侧做，避免把某个示例的期望输出写进引擎/测试脚本。
'use strict';
const path = require('path');
const CS = require(path.resolve(process.argv[2]));

const out = {};

// —— 基础目标（7 部位） ——
const HP = { head: 35, chest: 85, stomach: 70, leftArm: 60, rightArm: 60, leftLeg: 60, rightLeg: 60 };
const AMMO = { id: 'a', n: 'TEST', dmg: 50, pen: 40, ard: 30, v0: 900, pc: 1, pch: 1, ric: 0.1 };

function mag(ammo, n) {
  const a = [];
  for (let i = 0; i < n; i++) { a.push(JSON.parse(JSON.stringify(ammo))); }
  return a;
}
function base(extra) {
  const cfg = {
    magazine: mag(AMMO, 3), rpm: 600, dist: 0,
    penChanceFn: function () { return 1; },
    targetPartHp: HP, armorLayers: [], hitProfile: { mode: 'fixed', part: 'chest' }, seed: 11
  };
  Object.keys(extra || {}).forEach(function (k) { cfg[k] = extra[k]; });
  return cfg;
}
const PLATE = { name: '硬插板', kind: 'plate', zones: ['chest'], cls: 4, dur: 40, durMax: 40, material: 'ceramic', bluntThroughput: 0.2 };
const LINER = { name: '软内衬', kind: 'liner', zones: ['chest'], cls: 3, dur: 30, durMax: 30, material: 'aramid', bluntThroughput: 0.3 };
const clone = function (o) { return JSON.parse(JSON.stringify(o)); };

// —— A：射速决定时间间隔（引擎侧） ——
out.rpm600 = CS.simulate(base({ rpm: 600 })).shots.map(function (s) { return s.timeMs; });
out.rpm900 = CS.simulate(base({ rpm: 900 })).shots.map(function (s) { return s.timeMs; });
out.rpm150 = CS.simulate(base({ rpm: 150 })).shots.map(function (s) { return s.timeMs; });
out.throwRpm0 = (function () { try { CS.simulate(base({ rpm: 0 })); return null; } catch (e) { return e.message; } })();
out.throwRpmMissing = (function () {
  const cfg = base({}); delete cfg.rpm;
  try { CS.simulate(cfg); return null; } catch (e) { return e.message; }
})();

// —— E：多层护甲 ——
// A) 高穿弹穿透硬板 → 被软内衬挡住
out.ePlatePenLinerBlock = CS.simulate(base({
  magazine: mag(AMMO, 1),
  penChanceFn: function (pen, cls) { return cls === 4 ? 1 : 0; },
  armorLayers: [clone(PLATE), clone(LINER)]
}));

// A2) 同配置但没有软内衬（对照：穿透硬板后直接进人体）
out.ePlatePenNoLiner = CS.simulate(base({
  magazine: mag(AMMO, 1),
  penChanceFn: function () { return 1; },
  armorLayers: [clone(PLATE)]
}));

// B) 未穿透硬板：钝伤；分别在有/无软内衬托底时计算
out.eBluntWithLiner = CS.simulate(base({
  magazine: mag(AMMO, 1),
  penChanceFn: function () { return 0; },
  armorLayers: [clone(PLATE), clone(LINER)]
}));
out.eBluntNoLiner = CS.simulate(base({
  magazine: mag(AMMO, 1),
  penChanceFn: function () { return 0; },
  armorLayers: [clone(PLATE)]
}));

// C) 依次穿过硬板与软内衬
out.eThroughBoth = CS.simulate(base({
  magazine: mag(AMMO, 1),
  penChanceFn: function () { return 1; },
  armorLayers: [clone(PLATE), clone(LINER)]
}));

// D) 连续两发：第一发被挡、插板掉耐久；第二发用新耐久判定并穿透
// R19.8 新耐久公式的单发甲伤更低，这里把甲伤从 30 提到 45，使一发后耐久跌破 80% 阈值，
// 保持本场景原本要验证的「第二发读取新耐久」语义（不是放宽断言）。
out.eDurDrop = CS.simulate(base({
  magazine: mag(Object.assign({}, AMMO, { ard: 45 }), 2),
  penChanceFn: function (pen, cls, dur, durMax) { return dur >= durMax * 0.8 ? 0 : 1; },
  armorLayers: [clone(PLATE)]
}));

// D2) 两发：内衬耐久独立于插板（插板穿透，内衬挡住 → 内衬独立掉耐久）
out.eLinerIndependent = CS.simulate(base({
  magazine: mag(AMMO, 2),
  penChanceFn: function (pen, cls) { return cls === 4 ? 1 : 0; },
  armorLayers: [clone(PLATE), clone(LINER)]
}));

// 材质影响耐久损失：同一发子弹打陶瓷 vs 芳纶插板
out.eMatCeramic = CS.simulate(base({
  magazine: mag(AMMO, 1),
  penChanceFn: function () { return 0; },
  armorLayers: [Object.assign(clone(PLATE), { material: 'ceramic' })]
}));
out.eMatAramid = CS.simulate(base({
  magazine: mag(AMMO, 1),
  penChanceFn: function () { return 0; },
  armorLayers: [Object.assign(clone(PLATE), { material: 'aramid' })]
}));

// 等级影响穿透判定输入：同一发弹对 3 级 vs 5 级（概率函数按等级返回不同值）
out.eClass3 = CS.simulate(base({
  magazine: mag(AMMO, 1),
  penChanceFn: function (pen, cls) { return cls === 3 ? 0.9 : 0.1; },
  armorLayers: [Object.assign(clone(PLATE), { cls: 3 })]
}));
out.eClass5 = CS.simulate(base({
  magazine: mag(AMMO, 1),
  penChanceFn: function (pen, cls) { return cls === 3 ? 0.9 : 0.1; },
  armorLayers: [Object.assign(clone(PLATE), { cls: 5 })]
}));

// 种子可复现（含护甲层）
out.eReproA = JSON.stringify(CS.simulate(base({
  magazine: mag(AMMO, 5),
  penChanceFn: function (pen, cls, dur, durMax) { var d = 100 * dur / durMax; return Math.max(0, Math.min(1, (pen - cls * 8) / 40 + (100 - d) / 300)); },
  armorLayers: [clone(PLATE), clone(LINER)], seed: 4242
})));
out.eReproA2 = JSON.stringify(CS.simulate(base({
  magazine: mag(AMMO, 5),
  penChanceFn: function (pen, cls, dur, durMax) { var d = 100 * dur / durMax; return Math.max(0, Math.min(1, (pen - cls * 8) / 40 + (100 - d) / 300)); },
  armorLayers: [clone(PLATE), clone(LINER)], seed: 4242
})));

// —— F：障碍物 ——
const B_WOOD = { id: 'wood_plank', n: '木板', material: 'wood', penChanceMul: 1, dmgKeep: 0.85, penKeep: 0.9, ricochetMul: 0.5 };
const B_METAL = { id: 'metal_sheet', n: '铁皮', material: 'metal', penChanceMul: 0.6, dmgKeep: 0.75, penKeep: 0.8, ricochetMul: 1 };

out.fBase = CS.simulate(base({ magazine: mag(AMMO, 1), barriers: [] }));
out.fOne = CS.simulate(base({ magazine: mag(AMMO, 1), barriers: [clone(B_WOOD)] }));
out.fTwo = CS.simulate(base({ magazine: mag(AMMO, 1), barriers: [clone(B_WOOD), clone(B_METAL)] }));
out.fOrderAB = CS.simulate(base({ magazine: mag(AMMO, 1), barriers: [clone(B_METAL), clone(B_WOOD)], seed: 3 }));
out.fOrderBA = CS.simulate(base({ magazine: mag(AMMO, 1), barriers: [clone(B_WOOD), clone(B_METAL)], seed: 3 }));
out.fBlocked = CS.simulate(base({
  magazine: [Object.assign(mag(AMMO, 1)[0], { pch: 0 })],
  barriers: [clone(B_WOOD)]
}));
out.fThenArmor = CS.simulate(base({
  magazine: mag(AMMO, 1), barriers: [clone(B_WOOD)], armorLayers: [clone(PLATE), clone(LINER)]
}));
out.fReproA = JSON.stringify(CS.simulate(base({
  magazine: mag(AMMO, 4),
  barriers: [clone(B_WOOD), clone(B_METAL)],
  penChanceFn: function (pen, cls, dur, durMax) { var d = 100 * dur / durMax; return Math.max(0, Math.min(1, (pen - cls * 8) / 40 + (100 - d) / 300)); },
  seed: 77
})));
out.fReproA2 = JSON.stringify(CS.simulate(base({
  magazine: mag(AMMO, 4),
  barriers: [clone(B_WOOD), clone(B_METAL)],
  penChanceFn: function (pen, cls, dur, durMax) { var d = 100 * dur / durMax; return Math.max(0, Math.min(1, (pen - cls * 8) / 40 + (100 - d) / 300)); },
  seed: 77
})));

console.log(JSON.stringify(out));
