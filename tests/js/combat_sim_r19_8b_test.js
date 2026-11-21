// R19.8e：tarkovgunsmith Ballistics.cs 公式导出（穿透、减伤、钝伤、甲伤系数 site/video）
// 用法：node tests/js/combat_sim_r19_8b_test.js <combat_sim.js>
'use strict';
const path = require('path');
const CS = require(path.resolve(process.argv[2]));

function desmos(p, c, d) {
  const a = (121 - 5000 / (45 + 2 * d)) * c / 10;
  if (p <= a - 15) { return 0; }
  if (p < a) { const t = a - p - 15; return Math.max(0, Math.min(1, 0.4 * t * t / 100)); }
  let den = 0.9 * a - p; if (den >= -1e-9) { den = -1e-9; }
  const y = (100 + p / den) / 100;
  return y >= 0 ? Math.min(1, y) : 0;
}

function run(opts) {
  const sim = CS.simulate({
    magazine: [opts.ammo], rpm: 600, dist: 0,
    penChanceFn: opts.penChanceFn,
    penJitter: opts.penJitter,
    armorDamageMode: opts.mode,
    targetPartHp: { chest: 1000, head: 35 },
    hitProfile: { mode: 'fixed', part: opts.part || 'chest' },
    armorLayers: opts.layers,
    barriers: [], seed: opts.seed || 1
  });
  const shot = sim.shots[0];
  const p = shot.pellets[0];
  return {
    penBase: shot.penBase, penRoll: shot.penRoll, penUsed: shot.penUsed,
    penJitterMode: shot.penJitterMode, penDev: shot.penDev, penDevSource: shot.penDevSource,
    layers: p.layers.map(function (L) {
      return {
        name: L.name, kind: L.kind, cls: L.cls, durBefore: L.durBefore, durAfter: L.durAfter,
        durOrig: L.durOrig, chance: L.chance, roll: L.roll, penetrated: L.penetrated,
        durDmg: L.durDmg, durBase: L.durBase, durCoeff: L.durCoeff, durMode: L.durMode,
        factorA: L.factorA, durPct: L.durPct,
        penIn: L.penIn, penOut: L.penOut, dmgIn: L.dmgIn, dmgOut: L.dmgOut,
        reduceFactor: L.reduceFactor,
        bluntScale: L.bluntScale, bluntBase: L.bluntBase, blunt: L.blunt,
        bluntIn: L.bluntIn, bluntOut: L.bluntOut, bluntFactor: L.bluntFactor,
        bluntLayers: L.bluntLayers, softBacking: L.softBacking,
        afterBlock: L.afterBlock, blocked: L.blocked,
        linerDurScale: L.linerDurScale
      };
    }),
    dmgToPart: p.dmgToPart, stoppedBy: p.stoppedBy, penetrated: p.penetrated
  };
}

const AMMO47 = { id: 't47', n: 'T47', pen: 47, dmg: 50, ard: 50, v0: 900, pc: 1 };
const AMMO40 = { id: 't40', n: 'T40', pen: 40, dmg: 50, ard: 50, v0: 900, pc: 1 };
const AMMO43 = { id: 't43', n: 'T43', pen: 43, dmg: 80, ard: 67, v0: 900, pc: 1 };
const AMMO5 = { id: 't5', n: 'T5', pen: 5, dmg: 100, ard: 50, v0: 900, pc: 1 };
const AMMO60 = { id: 't60', n: 'T60', pen: 60, dmg: 100, ard: 50, v0: 900, pc: 1 };

const PLATE5 = { name: 'P5', kind: 'plate', zones: ['chest'], cls: 5, material: 'ceramic',
                 bluntThroughput: 0.3 };
const PLATE4 = { name: 'P4', kind: 'plate', zones: ['chest'], cls: 4, material: 'armorSteel',
                 bluntThroughput: 0.18 };
const HELM5 = { name: 'H5', kind: 'helmet', zones: ['head'], cls: 5, material: 'combined',
                bluntThroughput: 0.08 };
const MASK2 = { name: 'M2', kind: 'helmet', zones: ['head'], cls: 2, material: 'steel',
                bluntThroughput: 0.18, order: 100 };
const MASK2B = { name: 'M3', kind: 'helmet', zones: ['head'], cls: 2, material: 'steel',
                 bluntThroughput: 0.18, order: 101 };
const HELM3 = { name: 'H3', kind: 'helmet', zones: ['head'], cls: 3, material: 'combined',
                bluntThroughput: 0.2 };
const LINER2 = { name: 'L2', kind: 'liner', zones: ['chest'], cls: 2, material: 'aramid',
                 bluntThroughput: 0.18, order: 100 };

const out = {};
out.consts = {
  mode: CS.ARMOR_DMG_COEFF_MODE,
  matCeramic: CS.MATERIAL_DESTRUCTIBILITY.ceramic,
  matGlass: CS.MATERIAL_DESTRUCTIBILITY.glass,
  linerMul: CS.SOFT_LINER_PLATE_BLUNT_MUL,
  throughMin: CS.EST_THROUGH_MIN,
  videoCap: CS.DUR_PROTECTION_CAP,
  res0: CS.armorClassResistance(0),
  res5: CS.armorClassResistance(5)
};
// 甲伤系数：decomp = P/(10×AC)（默认）；site = (P/AC)*10；video = P/(AC*10) 且保留 1.2 上限
out.coeffCases = {
  decompBlock20_4: CS.armorDamageCoeff(20, 4, false, 'decomp'),
  decompPen20_4: CS.armorDamageCoeff(20, 4, true, 'decomp'),
  decompLowBlock2_6: CS.armorDamageCoeff(2, 6, false, 'decomp'),
  decompHighBlock100_4: CS.armorDamageCoeff(100, 4, false, 'decomp'),
  siteBlock: CS.armorDamageCoeff(20, 4, false, 'site'),
  sitePen: CS.armorDamageCoeff(20, 4, true, 'site'),
  siteLowBlock: CS.armorDamageCoeff(2, 6, false, 'site'),
  videoBlock: CS.armorDamageCoeff(20, 4, false, 'video'),
  videoPen: CS.armorDamageCoeff(20, 4, true, 'video'),
  videoHighBlock: CS.armorDamageCoeff(100, 4, false, 'video')
};
// 钝伤系数：median(0.2, 1 - 0.03*(FactorA - P), 1)
out.bluntScaleCases = [0, 5, 20, 40, 50, 60].map(function (pen) {
  return { pen: pen, scale: CS.armorBluntScale(pen, 5, 100) };
});

out.penEqual = {
  a: run({ ammo: AMMO47, layers: [Object.assign({}, PLATE5, { dur: 30, durMax: 60, durOrig: 60 })],
           penChanceFn: function (p, c, dur, max, orig) { return desmos(p, c, 100 * dur / orig); } }),
  b: run({ ammo: AMMO47, layers: [Object.assign({}, PLATE5, { dur: 30, durMax: 30, durOrig: 60 })],
           penChanceFn: function (p, c, dur, max, orig) { return desmos(p, c, 100 * dur / orig); } })
};

out.jitterA = run({ ammo: AMMO43, layers: [Object.assign({}, PLATE5, { dur: 45, durMax: 45, durOrig: 45 })],
                    penChanceFn: function () { return 0; }, penJitter: true, seed: 7 });
out.jitterA2 = run({ ammo: AMMO43, layers: [Object.assign({}, PLATE5, { dur: 45, durMax: 45, durOrig: 45 })],
                     penChanceFn: function () { return 0; }, penJitter: true, seed: 7 });
out.jitterB = run({ ammo: AMMO43, layers: [Object.assign({}, PLATE5, { dur: 45, durMax: 45, durOrig: 45 })],
                    penChanceFn: function () { return 0; }, penJitter: true, seed: 8 });
// R62：带官方 σ 的弹种（M855A1 的 PenetrationPowerDiviation = 1.375）
out.jitterDev = run({ ammo: Object.assign({}, AMMO43, { penDev: 1.375 }),
                      layers: [Object.assign({}, PLATE5, { dur: 45, durMax: 45, durOrig: 45 })],
                      penChanceFn: function () { return 0; }, penJitter: 'normal', seed: 7 });
// 旧 ±1 均匀浮动仍可显式选择（仅调试）
out.jitterUniform = run({ ammo: AMMO43, layers: [Object.assign({}, PLATE5, { dur: 45, durMax: 45, durOrig: 45 })],
                         penChanceFn: function () { return 0; }, penJitter: 'uniform', seed: 7 });

out.reduceFull = run({ ammo: AMMO40, layers: [Object.assign({}, PLATE4, { dur: 45, durMax: 45, durOrig: 45 })],
                       penChanceFn: function () { return 1; } });
out.reduceHalf = run({ ammo: AMMO40, layers: [Object.assign({}, PLATE4, { dur: 22.5, durMax: 45, durOrig: 45 })],
                       penChanceFn: function () { return 1; } });

// R19.8f：多层钝伤链——层 1 挡下后钝伤继续送入层 2，按层 2 的 BT/等级/耐久再衰减
// 高穿弹（缩放项=1）：面罩 8 → 加二级面罩 8×0.18 = 1.44
out.bluntMulti = run({ ammo: AMMO60, part: 'head',
                      layers: [Object.assign({}, HELM5, { dur: 50, durMax: 50, durOrig: 50 }),
                               Object.assign({}, MASK2, { dur: 40, durMax: 40, durOrig: 40 })],
                      penChanceFn: function () { return 0; } });
// 同场景低穿弹：单层缩放项触到 median 下限 0.2 → 8×0.2=1.6，再过层 2 ×0.18 → 0.288
out.bluntMultiLow = run({ ammo: AMMO5, part: 'head',
                          layers: [Object.assign({}, HELM5, { dur: 50, durMax: 50, durOrig: 50 }),
                                   Object.assign({}, MASK2, { dur: 40, durMax: 40, durOrig: 40 })],
                          penChanceFn: function () { return 0; } });
// 三层：8 → 1.44 → 0.2592（每层都用自己的 BT × 缩放项）
out.bluntThree = run({ ammo: AMMO60, part: 'head',
                      layers: [Object.assign({}, HELM5, { dur: 50, durMax: 50, durOrig: 50 }),
                               Object.assign({}, MASK2, { dur: 40, durMax: 40, durOrig: 40 }),
                               Object.assign({}, MASK2B, { dur: 40, durMax: 40, durOrig: 40 })],
                      penChanceFn: function () { return 0; } });
// 层 2 被穿透：层 2 只按减伤/穿透逻辑处理，不衰减钝伤，也不终止链
out.bluntSecondPen = run({
  ammo: { id: 'p30', n: 'P30', pen: 30, dmg: 100, ard: 50, v0: 900, pc: 1 }, part: 'head',
  layers: [Object.assign({}, HELM3, { dur: 50, durMax: 50, durOrig: 50 }),
           Object.assign({}, MASK2, { dur: 40, durMax: 40, durOrig: 40 })],
  penChanceFn: function (p, c) { return c === 3 ? 0 : 1; }
});
// 插板 + 内衬：插板先按站点口径 ×0.6，内衬再按自身 BT×缩放衰减一次
out.bluntSoft = run({ ammo: AMMO60,
                      layers: [Object.assign({}, PLATE5, { dur: 50, durMax: 50, durOrig: 50 }),
                               Object.assign({}, LINER2, { dur: 40, durMax: 40, durOrig: 40 })],
                      penChanceFn: function () { return 0; } });
out.bluntPlateOnly = run({ ammo: AMMO60,
                           layers: [Object.assign({}, PLATE5, { dur: 50, durMax: 50, durOrig: 50 })],
                           penChanceFn: function () { return 0; } });
// 钝伤系数边界：P 0/5/20/50/60（无内衬，避免 0.6 因子干扰）
out.bluntF = [0, 5, 20, 50, 60].map(function (pen) {
  return run({ ammo: { id: 'f' + pen, n: 'F' + pen, pen: pen, dmg: 100, ard: 50, v0: 900, pc: 1 },
               layers: [Object.assign({}, PLATE5, { dur: 50, durMax: 50, durOrig: 50 })],
               penChanceFn: function () { return 0; } });
});
// 多层：板穿透 → P、D 各乘减伤系数；内衬被挡 → 钝伤；内衬耐久 × 板的击穿概率 0.8
out.multiPen = run({
  ammo: { id: 'm20', n: 'M20', pen: 20, dmg: 100, ard: 50, v0: 900, pc: 1 },
  layers: [Object.assign({}, PLATE4, { dur: 45, durMax: 45, durOrig: 45 }),
           Object.assign({}, LINER2, { dur: 40, durMax: 40, durOrig: 40 })],
  penChanceFn: function (p, c) { return c === 4 ? 0.8 : 0; }, seed: 1
});
// 同一场景的 video 甲伤写法（对照）
out.multiPenVideo = run({
  ammo: { id: 'm20', n: 'M20', pen: 20, dmg: 100, ard: 50, v0: 900, pc: 1 },
  layers: [Object.assign({}, PLATE4, { dur: 45, durMax: 45, durOrig: 45 }),
           Object.assign({}, LINER2, { dur: 40, durMax: 40, durOrig: 40 })],
  penChanceFn: function (p, c) { return c === 4 ? 0.8 : 0; }, seed: 1, mode: 'video'
});

process.stdout.write(JSON.stringify(out));
