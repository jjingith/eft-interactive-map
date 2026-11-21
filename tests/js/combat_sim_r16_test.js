// r16：方向性护甲 / 兼容性硬校验 / 出口碰撞估算 —— 只导出原始结果，断言在 Python 侧
// 用法：node tests/js/combat_sim_r16_test.js <combat_sim.js 路径>
'use strict';
const path = require('path');
const CS = require(path.resolve(process.argv[2]));

const HP = { head: 35, chest: 85, stomach: 70, leftArm: 60, rightArm: 60, leftLeg: 60, rightLeg: 60 };
const AMMO = { id: 'a', n: 'TEST', dmg: 50, pen: 40, ard: 30, v0: 900, pc: 1, pch: 1, ric: 0.1 };
const mag = (n, a) => { const out = []; for (let i = 0; i < n; i++) out.push(Object.assign({}, a || AMMO)); return out; };

const plate = (name, side, o) => Object.assign({
  name: name, kind: 'plate', side: side, zones: ['chest'], cls: 4,
  dur: 50, durMax: 50, material: 'ceramic', bluntThroughput: 0.2
}, o || {});
const liner = (name, side, o) => Object.assign({
  name: name, kind: 'liner', side: side, zones: ['chest'], cls: 3,
  dur: 40, durMax: 40, material: 'aramid', bluntThroughput: 0.3
}, o || {});

function cfg(extra) {
  const base = {
    magazine: mag(3), rpm: 600, dist: 0, dir: 'front',
    penChanceFn: function () { return 1; },
    targetPartHp: HP, armorLayers: [], barriers: [],
    hitProfile: { mode: 'fixed', part: 'chest' }, seed: 7
  };
  Object.keys(extra || {}).forEach(k => { base[k] = extra[k]; });
  return base;
}
const pellet = r => r.shots[0].pellets[0];
const clone = o => JSON.parse(JSON.stringify(o));

const out = {};

// —— A. 正面命中：只经过前插板 + 前内衬，后侧层被跳过 ——
const bothSides = [
  plate('前插板', 'front', { dur: 50 }),
  plate('后插板', 'back', { dur: 50, material: 'armorSteel' }),
  liner('前内衬', 'front', { dur: 40 }),
  liner('后内衬', 'back', { dur: 40 })
];
out.front = pellet(CS.simulate(cfg({ dir: 'front', armorLayers: clone(bothSides) })));
// —— B. 背面命中：只经过后插板 + 后内衬 ——
out.back = pellet(CS.simulate(cfg({ dir: 'back', armorLayers: clone(bothSides) })));
// —— C. 左侧命中：只经过左侧板 ——
out.left = pellet(CS.simulate(cfg({
  dir: 'left',
  armorLayers: [
    plate('前插板', 'front'), plate('后插板', 'back'),
    plate('左侧板', 'left', { cls: 3, dur: 30, durMax: 30 }), plate('右侧板', 'right', { cls: 3 })
  ]
})));
// —— D. 正面命中但只有后插板（前板未装）：正面不应吃到后板减伤 ——
out.frontNoFrontPlate = pellet(CS.simulate(cfg({
  dir: 'front', armorLayers: [plate('后插板', 'back')]
})));
// —— E. 正面击穿前板后被前内衬挡住；后插板耐久不得变化 ——
const eLayers = [
  plate('前插板', 'front', { dur: 20, durMax: 50, material: 'aramid' }),
  liner('前内衬', 'front', { cls: 3, dur: 40 }),
  plate('后插板', 'back', { dur: 50 })
];
out.penThenLiner = pellet(CS.simulate(cfg({
  dir: 'front', armorLayers: clone(eLayers),
  penChanceFn: (function () { let i = 0; return function () { i += 1; return i === 1 ? 1 : 0; }; })()
})));
// —— F. 出口碰撞：开启 estimate 时只多扣后板耐久，入体伤害不变 ——
out.exitOff = CS.simulate(cfg({ dir: 'front', exitModel: 'off', armorLayers: clone(eLayers) }));
out.exitOn = CS.simulate(cfg({ dir: 'front', exitModel: 'estimate', armorLayers: clone(eLayers) }));

// —— G. 兼容性硬校验 ——
function attempt(fn) { try { fn(); return null; } catch (e) { return e.message; } }
out.throwAmmoNotAllowed = attempt(() => CS.simulate(cfg({
  magazine: mag(2, { id: 'not-allowed', n: 'X', dmg: 50, pen: 40, ard: 30, v0: 900, pc: 1 }),
  constraints: { ammo: ['a'], magazines: ['m1'], hasMagSlot: true }, magazineId: 'm1'
})));
out.throwMagNotAllowed = attempt(() => CS.simulate(cfg({
  constraints: { ammo: ['a'], magazines: ['m1'], hasMagSlot: true }, magazineId: 'm2'
})));
out.throwNoMagSlot = attempt(() => CS.simulate(cfg({
  constraints: { ammo: ['a'], magazines: [], hasMagSlot: false }, magazineId: 'm1'
})));
out.okWhenAllowed = (function () {
  const r = CS.simulate(cfg({
    constraints: { ammo: ['a'], magazines: ['m1'], hasMagSlot: true }, magazineId: 'm1'
  }));
  return { shotCount: r.shotCount };
})();

// —— H. 方向 + 种子可复现 ——
out.reproA = JSON.stringify(CS.simulate(cfg({ dir: 'back', armorLayers: clone(bothSides), seed: 99 })));
out.reproB = JSON.stringify(CS.simulate(cfg({ dir: 'back', armorLayers: clone(bothSides), seed: 99 })));

// —— I. 旧行为兼容：层不带 side 时仍按顺序串联（R15 场景不回归） ——
out.legacyNoSide = pellet(CS.simulate(cfg({
  dir: 'front',
  armorLayers: [
    { name: '旧插板', kind: 'plate', zones: ['chest'], cls: 4, dur: 50, durMax: 50, material: 'ceramic', bluntThroughput: 0.2 },
    { name: '旧内衬', kind: 'liner', zones: ['chest'], cls: 3, dur: 40, durMax: 40, material: 'aramid', bluntThroughput: 0.3 }
  ]
})));

// —— J. 头盔与方向无关：正面/背面都应经过头盔（头部命中） ——
const helmCfg = d => ({
  dir: d, hitProfile: { mode: 'fixed', part: 'head' },
  armorLayers: [{ name: '头盔', kind: 'helmet', zones: ['head'], cls: 4, dur: 40, durMax: 40, material: 'titan', bluntThroughput: 0.2 }],
  penChanceFn: function () { return 0; }
});
out.helmetFront = pellet(CS.simulate(cfg(helmCfg('front'))));
out.helmetBack = pellet(CS.simulate(cfg(helmCfg('back'))));

process.stdout.write(JSON.stringify(out));
