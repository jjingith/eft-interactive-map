// R63 验收：重型护甲技能（globals 0.004/级）、可选碎片化（固定种子可复现）、无衰减飞行模型。
// 用法：node tests/js/combat_sim_r63_flight_frag_skills.js <combat_sim.js>
'use strict';
const path = require('path');
const CS = require(path.resolve(process.argv[2]));
const ROOT = path.resolve(__dirname, '..', '..');
const AMMO = require(path.join(ROOT, 'data', 'ammo.json')).ammo;

function ammoById(id) {
  for (let i = 0; i < AMMO.length; i++) { if (AMMO[i].id === id) { return AMMO[i]; } }
  throw new Error('ammo not found: ' + id);
}

const M855A1 = ammoById('54527ac44bdc2d36668b4567');   // P44 D49 frag 0.44
const RIP = ammoById('5c0d56a986f774449d5de529');       // 9x19 RIP：P2 frag 1（pen<20 闸门用例）

function plateLayer(armorType) {
  return {
    name: '测试钢插板', kind: 'plate', zones: ['chest'], cls: 4,
    dur: 40, durMax: 40, durOrig: 40, material: 'armorSteel',
    bluntThroughput: 0.18, armorType: armorType
  };
}

function runHv(level, armorType) {
  const sim = CS.simulate({
    magazine: [M855A1], rpm: 600, dist: 0, seed: 7,
    penChanceFn: function () { return 0; },   // 恒挡下 → 只看钝伤
    penJitter: false, armorDamageMode: 'decomp',
    fragmentation: false, heavyVestsLevel: level,
    targetPartHp: { chest: 5000 },
    hitProfile: { mode: 'fixed', part: 'chest' },
    armorLayers: [plateLayer(armorType)], barriers: []
  });
  const p = sim.shots[0].pellets[0];
  return {
    dmgToPart: p.dmgToPart,
    blunt: p.layers[0].blunt,
    bluntFactor: p.layers[0].bluntFactor,
    hvReduce: p.layers[0].hvReduce,
    hvLevel: p.layers[0].hvLevel,
    armorType: p.layers[0].armorType
  };
}

function fragRun(ammo, seed, on) {
  const magazine = [];
  for (let i = 0; i < 40; i++) { magazine.push(ammo); }   // 40 发，避免目标死亡影响计数
  const sim = CS.simulate({
    magazine: magazine, rpm: 600, dist: 0, seed: seed,
    penChanceFn: function () { return 0; }, penJitter: false,
    fragmentation: on, heavyVestsLevel: 0,
    targetPartHp: { chest: 5000 },
    hitProfile: { mode: 'fixed', part: 'chest' },
    armorLayers: [], barriers: []
  });
  return {
    fragCount: sim.fragCount,
    models: sim.models,
    rolls: sim.shots.map(function (s) {
      const p = s.pellets[0];
      return p.frag ? p.frag.roll : null;
    }),
    chances: sim.shots.map(function (s) {
      const p = s.pellets[0];
      return p.frag ? p.frag.chance : null;
    }),
    dmg: sim.shots.map(function (s) { return s.pellets[0].dmgToPart; }),
    triggered: sim.shots.map(function (s) {
      const p = s.pellets[0];
      return p.frag ? p.frag.triggered : false;
    })
  };
}

// 无衰减飞行模型：用 CS.defaultFlight，距离 100 m 仍应等于纸面值
const flat = CS.simulate({
  magazine: [M855A1], rpm: 600, dist: 100, seed: 9,
  flightFn: CS.defaultFlight,
  penChanceFn: function () { return 0; }, penJitter: false,
  fragmentation: false, heavyVestsLevel: 0,
  targetPartHp: { chest: 5000 }, hitProfile: { mode: 'fixed', part: 'chest' },
  armorLayers: [], barriers: []
});

const out = {
  meta: {
    M855A1: { pen: M855A1.pen, dmg: M855A1.dmg, frag: M855A1.frag },
    RIP: { pen: RIP.pen, dmg: RIP.dmg, frag: RIP.frag }
  },
  hv: {
    zeroHeavy: runHv(0, 'Heavy'),
    maxHeavy: runHv(50, 'Heavy'),
    maxLight: runHv(50, 'Light'),
    perLevel: CS.HV_REDUCE_PER_LEVEL,
    maxLevel: CS.HV_MAX_LEVEL
  },
  frag: {
    off: fragRun(M855A1, 42, false),
    onA: fragRun(M855A1, 42, true),
    onB: fragRun(M855A1, 42, true),
    onOtherSeed: fragRun(M855A1, 43, true),
    gate: fragRun(RIP, 42, true),
    minPen: CS.FRAG_MIN_PEN,
    extraMul: CS.FRAG_EXTRA_MUL
  },
  flight: {
    dist: 100,
    dmgToPart: flat.shots[0].pellets[0].dmgToPart,
    penIn: flat.shots[0].pellets[0].penIn,
    models: flat.models,
    defaultFlat: CS.defaultFlight(M855A1, 100)
  }
};

process.stdout.write(JSON.stringify(out));
