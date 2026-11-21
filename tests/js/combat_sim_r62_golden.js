// R62 实弹锚点：用 data/ammo.json + data/items.json 的真实数值跑三组 golden
// 用法：node tests/js/combat_sim_r62_golden.js <combat_sim.js>
'use strict';
const path = require('path');
const CS = require(path.resolve(process.argv[2]));
const ROOT = path.resolve(__dirname, '..', '..');
const AMMO = require(path.join(ROOT, 'data', 'ammo.json')).ammo;
const ITEMS = require(path.join(ROOT, 'data', 'items.json')).items;

function ammoById(id) {
  for (let i = 0; i < AMMO.length; i++) { if (AMMO[i].id === id) { return AMMO[i]; } }
  return null;
}
function itemById(id) { return ITEMS[id] || null; }

const MAT = {
  ArmoredSteel: 'armorSteel', ArmorSteel: 'armorSteel', Ceramic: 'ceramic', Combined: 'combined',
  Titan: 'titan', Aluminium: 'aluminium', UHMWPE: 'uhmwpe', Aramid: 'aramid', Glass: 'glass'
};

function plateLayer(id, zone) {
  const it = itemById(id);
  return {
    name: it.n, kind: 'plate', zones: [zone || 'chest'],
    cls: it.cl, dur: it.dur, durMax: it.dur, durOrig: it.dur,
    material: MAT[it.mat] || 'combined',
    bluntThroughput: it.bt
  };
}

function run(ammo, layers, opts) {
  opts = opts || {};
  const sim = CS.simulate({
    magazine: [ammo], rpm: 600, dist: 0, seed: opts.seed || 1,
    penChanceFn: opts.penChanceFn || function () { return 1; },
    penJitter: opts.penJitter || false,
    armorDamageMode: 'decomp',
    targetPartHp: { chest: 1000, head: 35 },
    hitProfile: { mode: 'fixed', part: opts.part || 'chest' },
    armorLayers: layers, barriers: []
  });
  const p = sim.shots[0].pellets[0];
  return {
    penIn: p.layers[0] ? p.layers[0].penIn : null,
    layers: p.layers.map(function (L) {
      return {
        name: L.name, kind: L.kind, cls: L.cls, durBefore: L.durBefore, durAfter: L.durAfter,
        durDmg: L.durDmg, durBase: L.durBase, durCoeff: L.durCoeff, durMode: L.durMode,
        factorA: L.factorA, reduceFactor: L.reduceFactor,
        bluntScale: L.bluntScale, blunt: L.blunt, bluntOut: L.bluntOut,
        penOut: L.penOut, dmgOut: L.dmgOut
      };
    }),
    dmgToPart: p.dmgToPart, stoppedBy: p.stoppedBy, penetrated: p.penetrated
  };
}

const M855A1 = ammoById('54527ac44bdc2d36668b4567');
const M995 = ammoById('59e690b686f7746c9f75e848');
const ME308 = ammoById('67c540cfb032bbdb530201b8');   // .308 ME LOKT P24/D96

const out = {
  meta: {
    M855A1: { n: M855A1.n, pen: M855A1.pen, dmg: M855A1.dmg, ard: M855A1.ard },
    M995: { n: M995.n, pen: M995.pen, dmg: M995.dmg, ard: M995.ard },
    ME308: { n: ME308.n, pen: ME308.pen, dmg: ME308.dmg, ard: ME308.ard }
  },
  // (a) 同一发 P44 打不同等级：原文比值随等级下降，旧 site 口径恒 1.1
  ratio: [2, 3, 4, 5, 6].map(function (cls) {
    return { cls: cls, decomp: CS.armorDamageCoeff(44, cls, false, 'decomp'),
             site: CS.armorDamageCoeff(44, cls, false, 'site') };
  }),
  // (d1) M855A1 打 4 级钢插板（6B23-2）满耐久
  m855a1_class4: run(M855A1, [plateLayer('657b22485f444d6dff0c6c2f')]),
  // (d2) M995 打 5 级 SAPI 满耐久
  m995_class5: run(M995, [plateLayer('655746010177119f4a097ff7')]),
  // (d3) 视频锚点：.308 ME LOKT + Altyn 5 级面罩 10% 耐久 + 2 级面罩
  video8to1: (function () {
    const altyn = {
      name: 'Altyn 面罩', kind: 'helmet', zones: ['head'], cls: 5,
      dur: 5, durMax: 50, durOrig: 50, material: 'combined', bluntThroughput: 0.0792
    };
    const mask = {
      name: '2 级面罩', kind: 'helmet', zones: ['head'], cls: 2,
      dur: 45, durMax: 45, durOrig: 45, material: 'steel', bluntThroughput: 0.099, order: 100
    };
    return run(ME308, [altyn, mask], { part: 'head', penChanceFn: function () { return 0; } });
  })()
};

process.stdout.write(JSON.stringify(out));
