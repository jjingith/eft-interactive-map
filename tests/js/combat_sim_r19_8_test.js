// R19.8：用真实弹种 × 护甲数据导出耐久公式结果（只导出原始值，断言在 Python 侧）
// 用法：node tests/js/combat_sim_r19_8_test.js <combat_sim.js> <项目根目录>
'use strict';
const fs = require('fs');
const path = require('path');
const CS = require(path.resolve(process.argv[2]));
const ROOT = path.resolve(process.argv[3]);
const ammo = JSON.parse(fs.readFileSync(path.join(ROOT, 'data', 'ammo.json'), 'utf8')).ammo;
const items = JSON.parse(fs.readFileSync(path.join(ROOT, 'data', 'items.json'), 'utf8')).items;

const MATKEY = {
  Ceramic: 'ceramic', UHMWPE: 'uhmwpe', Aramid: 'aramid', ArmoredSteel: 'armorSteel',
  Titan: 'titan', Aluminium: 'aluminium', Combined: 'combined', Glass: 'glass'
};
function ammoByName(n) { return ammo.find((a) => a.n === n); }

function run(ammoRec, plateRec, opts) {
  opts = opts || {};
  const sim = CS.simulate({
    magazine: opts.rounds || [ammoRec],
    rpm: 600, dist: 0,
    penChanceFn: function () { return opts.chance === undefined ? 0 : opts.chance; },
    targetPartHp: { chest: 1000 },
    hitProfile: { mode: 'fixed', part: 'chest' },
    armorLayers: [{
      name: plateRec.n, kind: 'plate', zones: ['chest'], cls: plateRec.cl,
      dur: opts.dur === undefined ? plateRec.dur : opts.dur,
      durMax: plateRec.dur, material: MATKEY[plateRec.mat],
      bluntThroughput: plateRec.bt
    }],
    barriers: [], seed: 1
  });
  const out = [];
  sim.shots.forEach(function (s) {
    const p = s.pellets[0], L = p.layers[0];
    out.push({
      durBefore: L.durBefore, durAfter: L.durAfter, durDmg: L.durDmg,
      durBase: L.durBase, durCoeff: L.durCoeff, durMode: L.durMode,
      factorA: L.factorA, durPct: L.durPct,
      penetrated: L.penetrated, chance: L.chance,
      blunt: L.blunt, bluntScale: L.bluntScale, bluntBase: L.bluntBase,
      penIn: L.penIn, penOut: L.penOut, dmgIn: L.dmgIn, dmgOut: L.dmgOut,
      dmgToPart: p.dmgToPart, durConfidence: L.durConfidence
    });
  });
  return out;
}

const out = {};
const M80 = ammoByName('7.62x51毫米 M80');
const M995 = ammoByName('5.56x45毫米 M995');
const BT = ammoByName('5.45x39毫米 BT');
const KITECO = items['656fafe3498d1b7e3e071da4'];
const SAPI = items['655746010177119f4a097ff7'];

out.meta = {
  M80: { n: M80.n, pen: M80.pen, dmg: M80.dmg, ard: M80.ard },
  M995: { n: M995.n, pen: M995.pen, dmg: M995.dmg, ard: M995.ard },
  BT: { n: BT.n, pen: BT.pen, dmg: BT.dmg, ard: BT.ard },
  KITECO: { n: KITECO.n, cls: KITECO.cl, dur: KITECO.dur, mat: KITECO.mat, bt: KITECO.bt, matKey: MATKEY[KITECO.mat] },
  SAPI: { n: SAPI.n, cls: SAPI.cl, dur: SAPI.dur, mat: SAPI.mat, bt: SAPI.bt, matKey: MATKEY[SAPI.mat] }
};
out.M80_KITECO_unpen = run(M80, KITECO, { chance: 0 });
out.M80_KITECO_pen = run(M80, KITECO, { chance: 1 });
out.M995_SAPI_pen = run(M995, SAPI, { chance: 1 });
out.BT_SAPI_unpen = run(BT, SAPI, { chance: 0 });
out.M80_KITECO_half = run(M80, KITECO, { chance: 0, dur: KITECO.dur / 2 });
out.M80_KITECO_low = run(M80, KITECO, { chance: 0, dur: 3 });
out.M80_KITECO_3shots = run(M80, KITECO, { chance: 0, rounds: Array(3).fill(M80) });

// R19.8 头盔跳弹：纯概率 + 引擎单发（合成头盔参数，来源 gunsmith 的 x/y/z 口径）
out.ricModel = {
  z40_below: CS.ricochetChance({ x: 0.9, y: 0.5, z: 40 }, 39),
  z40_at: CS.ricochetChance({ x: 0.9, y: 0.5, z: 40 }, 40),
  z40_65: CS.ricochetChance({ x: 0.9, y: 0.5, z: 40 }, 65),
  z40_90: CS.ricochetChance({ x: 0.9, y: 0.5, z: 40 }, 90),
  z50_below: CS.ricochetChance({ x: 0.9, y: 0.4, z: 50 }, 40),
  z50_at: CS.ricochetChance({ x: 0.9, y: 0.4, z: 50 }, 50),
  z50_70: CS.ricochetChance({ x: 0.9, y: 0.4, z: 50 }, 70),
  z50_90: CS.ricochetChance({ x: 0.9, y: 0.4, z: 50 }, 90),
  zero_x: CS.ricochetChance({ x: 0, y: 0, z: 80 }, 90),
  bad: CS.ricochetChance(null, 90)
};

function runRic(params, kind, angle, seed) {
  const sim = CS.simulate({
    magazine: [M80], rpm: 600, dist: 0, angle: angle,
    penChanceFn: function () { return 0; },
    targetPartHp: { head: 35, chest: 1000 },
    hitProfile: { mode: 'fixed', part: 'head' },
    armorLayers: [{ name: 'H', kind: kind, zones: ['head'], cls: 3, dur: 40, durMax: 40,
      material: 'combined', bluntThroughput: 0.15, ricochet: params }],
    barriers: [], seed: seed
  });
  const p = sim.shots[0].pellets[0], L = p.layers[0];
  return {
    ricochet: !!L.ricochet, chance: L.ricochetChance, roll: L.ricochetRoll,
    angle: L.ricochetAngle, durDmg: L.durDmg, durBefore: L.durBefore, durAfter: L.durAfter,
    dmgToPart: p.dmgToPart, stoppedBy: p.stoppedBy, penetrated: L.penetrated, blocked: L.blocked,
    durConfidence: L.durConfidence
  };
}
out.ricShots = {};
for (const seed of [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]) {
  out.ricShots['s' + seed] = runRic({ x: 0.9, y: 0.5, z: 40 }, 'helmet', 65, seed);
}
out.ricBelow = runRic({ x: 0.9, y: 0.5, z: 40 }, 'helmet', 39, 1);
out.ricZero = runRic({ x: 0.9, y: 0.5, z: 40 }, 'helmet', 0, 1);
out.ricPlate = runRic({ x: 0.9, y: 0.5, z: 40 }, 'plate', 65, 1);
out.ric90 = runRic({ x: 0.9, y: 0.5, z: 40 }, 'helmet', 90, 1);

process.stdout.write(JSON.stringify(out));
