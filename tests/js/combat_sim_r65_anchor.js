// R65 锚点：插板挡下 → 内衬只乘自身 BT；甲伤浮点直减。
// 用法：node tests/js/combat_sim_r65_anchor.js <combat_sim.js> <on|off>
'use strict';
const path = require('path');
const CS = require(path.resolve(process.argv[2]));
CS.SOFT_LINER_PLATE_BLUNT_ENABLED = (process.argv[3] === 'on');

// 用户锚点：伤害 162.3 / 穿透 36.7；5 级 UHMWPE 插板（原始 BT 0.155，用户给的 0.093 是 ×0.6 后）；
// 3 级芳纶内衬 40/40，BT 兜底 0.18。
const AMMO = {
  id: 'r65-anchor', n: 'R65 锚点弹', dmg: 162.3, pen: 36.7, ard: 52,
  v0: 900, bc: 0.3, m: 10, dia: 7.62, frag: 0, ric: 0, pc: 0
};

function plate(bt) {
  return { name: 'UHMWPE 5 级插板', kind: 'plate', zones: ['chest'], cls: 5,
           dur: 40, durMax: 40, durOrig: 40, material: 'uhmwpe',
           bluntThroughput: bt, armorType: 'Heavy' };
}
function liner() {
  return { name: '芳纶 3 级内衬', kind: 'liner', zones: ['chest'], cls: 3,
           dur: 40, durMax: 40, durOrig: 40, material: 'aramid',
           bluntThroughput: 0.18, armorType: 'Light' };
}

function run(bt, shots) {
  const mag = [];
  for (let i = 0; i < shots; i++) { mag.push(AMMO); }
  const sim = CS.simulate({
    magazine: mag, rpm: 600, dist: 0, seed: 11,
    penChanceFn: function () { return 0; }, penJitter: false,
    armorDamageMode: 'decomp', fragmentation: false, heavyVestsLevel: 0,
    targetPartHp: { chest: 5000 }, hitProfile: { mode: 'fixed', part: 'chest' },
    armorLayers: [plate(bt), liner()], barriers: []
  });
  const p = sim.shots[0].pellets[0];
  return {
    bt: bt,
    plateBlunt: p.layers[0].bluntOut,
    plateFactor: p.layers[0].bluntFactor,
    plateScale: p.layers[0].bluntScale,
    penIn: p.penIn,
    plateDur: p.layers[0].durDmg,
    plateDurAfter: p.layers[0].durAfter,
    linerIn: p.layers[1].bluntIn,
    linerFactor: p.layers[1].bluntFactor,
    linerOut: p.layers[1].bluntOut,
    linerAfterBlock: p.layers[1].afterBlock === true,
    linerChance: p.layers[1].chance,
    linerRoll: p.layers[1].roll,
    linerDur: p.layers[1].durDmg,
    linerDurAfter: p.layers[1].durAfter,
    dmgToPart: p.dmgToPart,
    stoppedBy: p.stoppedBy,
    threeShotsDur: sim.shots.slice(0, 3).map(function (s) {
      return [s.pellets[0].layers[0].durDmg, s.pellets[0].layers[0].durAfter];
    })
  };
}

process.stdout.write(JSON.stringify({
  enabled06: CS.SOFT_LINER_PLATE_BLUNT_ENABLED,
  rawBT0155: run(0.155, 3),     // 用户口径的原始 BT（0.093 = 0.155 × 0.6）
  bt0093: run(0.093, 3),        // 把 0.093 当原始 BT
  noLiner: (function () {
    const sim = CS.simulate({
      magazine: [AMMO], rpm: 600, dist: 0, seed: 11,
      penChanceFn: function () { return 0; }, penJitter: false,
      armorDamageMode: 'decomp', fragmentation: false, heavyVestsLevel: 0,
      targetPartHp: { chest: 5000 }, hitProfile: { mode: 'fixed', part: 'chest' },
      armorLayers: [plate(0.155)], barriers: []
    });
    const p = sim.shots[0].pellets[0];
    return { plateBlunt: p.layers[0].bluntOut, dmgToPart: p.dmgToPart, stoppedBy: p.stoppedBy };
  })()
}));
