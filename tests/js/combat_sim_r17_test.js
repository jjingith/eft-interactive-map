// r17：护甲损毁公式 / Top-Loop-Bottom 预设压弹 / 肉体伤害与黑化分散 —— 只导出原始结果
// 用法：node tests/js/combat_sim_r17_test.js <combat_sim.js 路径>
'use strict';
const path = require('path');
const CS = require(path.resolve(process.argv[2]));

const out = {};

// ———————————————————— A：护甲耐久损毁 ————————————————————
const PMC = { head: 35, chest: 85, stomach: 70, leftArm: 60, rightArm: 60, leftLeg: 65, rightLeg: 65 };
const plate = (o) => Object.assign({
  name: '板', kind: 'plate', side: 'front', zones: ['chest'], cls: 5,
  dur: 50, durMax: 50, material: 'ceramic', bluntThroughput: 0.2
}, o);
const run1 = (extra) => CS.simulate(Object.assign({
  magazine: [{ id: 'a', n: 'A', dmg: 50, pen: 40, ard: 30, v0: 900, pc: 1 }],
  rpm: 600, dist: 0, penChanceFn: function () { return 0; },
  targetPartHp: { chest: 85 }, armorLayers: [],
  hitProfile: { mode: 'fixed', part: 'chest' }, seed: 1
}, extra));
const pel = (r, i) => r.shots[i || 0].pellets[0];

// A1 用户案例：5.56 HP（甲伤22 穿7）打 5 级陶瓷（50 耐久），未穿透
out.userCase = (() => {
  const ammo = { id: 'hp', n: 'HP', dmg: 79, pen: 7, ard: 22, v0: 900, pc: 1 };
  const r = run1({ magazine: Array.from({ length: 8 }, () => Object.assign({}, ammo)),
    targetPartHp: { chest: 1000 },
    armorLayers: [plate({})] });
  return {
    perShot: r.shots.map(s => s.pellets[0].layers[0].durDmg),
    durAfter: r.armorFinal[0].dur,
    durBase: pel(r).layers[0].durBase,
    durCoeff: pel(r).layers[0].durCoeff,
    durMode: pel(r).layers[0].durMode,
    conf: pel(r).layers[0].durConfidence
  };
})();

// A2 同一弹药对不同材质（未穿透）： ceramic / aramid / armorSteel / titan
out.materials = {};
for (const m of ['ceramic', 'aramid', 'armorSteel', 'titan']) {
  const r = run1({ armorLayers: [plate({ material: m })] });
  out.materials[m] = { durDmg: pel(r).layers[0].durDmg, durBase: pel(r).layers[0].durBase,
                       durCoeff: pel(r).layers[0].durCoeff };
}

// A3 穿透 vs 未穿透（同一块板，两次模拟各一发）
out.penVsUnpen = (() => {
  // R62：穿透 52/50=1.04 → 击穿侧被 0.9 截断、挡下侧 1.04，才能看到两套 clamp 的差异
  const ammo52 = { id: 'p52', n: 'P52', dmg: 50, pen: 52, ard: 30, v0: 900, pc: 1 };
  const pen1 = pel(run1({ magazine: [ammo52], penChanceFn: function () { return 1; }, armorLayers: [plate({})] })).layers[0];
  const pen0 = pel(run1({ magazine: [ammo52], penChanceFn: function () { return 0; }, armorLayers: [plate({})] })).layers[0];
  return { pen: { durDmg: pen1.durDmg, durBase: pen1.durBase, coeff: pen1.durCoeff },
           unpen: { durDmg: pen0.durDmg, durBase: pen0.durBase, coeff: pen0.durCoeff } };
})();

// A4 低穿 vs 高穿（同板同甲伤系数，仅穿深不同）
out.lowVsHigh = (() => {
  const low = pel(run1({ magazine: [{ id: 'l', n: 'L', dmg: 79, pen: 7, ard: 22, v0: 900, pc: 1 }], armorLayers: [plate({})] })).layers[0];
  const high = pel(run1({ magazine: [{ id: 'h', n: 'H', dmg: 42, pen: 50, ard: 40, v0: 900, pc: 1 }], armorLayers: [plate({})] })).layers[0];
  return { low: { durDmg: low.durDmg, durBase: low.durBase, coeff: low.durCoeff },
           high: { durDmg: high.durDmg, durBase: high.durBase, coeff: high.durCoeff } };
})();

// A5 耐久归零后的下一发：3 耐久板吃一发大伤害 → 归零；下一发 degraded + 内衬照常结算
out.zeroDur = (() => {
  const ammo = { id: 'x', n: 'X', dmg: 60, pen: 60, ard: 60, v0: 900, pc: 1 };
  const r = run1({
    magazine: Array.from({ length: 2 }, () => Object.assign({}, ammo)),
    penChanceFn: function () { return 0; },
    armorLayers: [plate({ dur: 3, durMax: 50 }), { name: '内衬', kind: 'liner', side: 'front', zones: ['chest'], cls: 2, dur: 30, durMax: 30, material: 'aramid', bluntThroughput: 0.3 }]
  });
  return {
    shot1: { durDmg: pel(r, 0).layers[0].durDmg, durAfter: pel(r, 0).layers[0].durAfter, degraded: pel(r, 0).layers[0].degraded },
    shot2: { degraded: pel(r, 1).layers[0].degraded, zeroConf: pel(r, 1).layers[0].zeroDurConfidence,
             linerBlocked: pel(r, 1).layers[1] ? pel(r, 1).layers[1].blocked : null,
             blunt: pel(r, 1).dmgToPart, stoppedBy: pel(r, 1).stoppedBy }
  };
})();

// A6 多层：一发只在自己的层上扣耐久（板 + 内衬，均穿透）
out.multiLayer = (() => {
  const r = run1({ penChanceFn: function () { return 1; },
    armorLayers: [plate({}), { name: '内衬', kind: 'liner', side: 'front', zones: ['chest'], cls: 2, dur: 30, durMax: 30, material: 'aramid', bluntThroughput: 0.3 }] });
  const p = pel(r);
  return { plateDmg: p.layers[0].durDmg, linerDmg: p.layers[1].durDmg,
           dmgToArmor: p.dmgToArmor, sum: p.layers[0].durDmg + p.layers[1].durDmg };
})();

// A7 霰弹：4 弹丸零穿透 → 单发总甲伤 ≥ 4（每颗最低 1）
out.shotgun = (() => {
  const r = run1({ magazine: [{ id: 's', n: 'SG', dmg: 12, pen: 2, ard: 5, v0: 400, pc: 4 }],
    armorLayers: [plate({})] });
  return { dmgToArmor: r.shots[0].dmgToArmor, shotPellets: r.shots[0].pellets.length };
})();

// A8 常数导出（Python 侧做量纲/公式断言）
out.consts = { MODE: CS.ARMOR_DMG_COEFF_MODE,
               LINER_MUL: CS.SOFT_LINER_PLATE_BLUNT_MUL,
               MAT: CS.MATERIAL_DESTRUCTIBILITY };

// ———————————————————— C：预设压弹 ————————————————————
out.preset = {};
out.preset.mixed = CS.buildMagazineFromPreset(
  [{ zone: 'top', ammoId: 'A', count: 3 }, { zone: 'loop', ammoId: 'B', count: 1 },
   { zone: 'loop', ammoId: 'C', count: 1 }, { zone: 'loop', ammoId: '', count: 1 },
   { zone: 'bottom', ammoId: 'D', count: 2 }], 12);
out.preset.loopOnly = CS.buildMagazineFromPreset(
  [{ zone: 'top', ammoId: '', count: 3 }, { zone: 'loop', ammoId: 'B', count: 1 },
   { zone: 'loop', ammoId: 'C', count: 1 }, { zone: 'loop', ammoId: '', count: 1 },
   { zone: 'bottom', ammoId: '', count: 2 }], 6);
out.preset.single = CS.buildMagazineFromPreset(
  [{ zone: 'top', ammoId: 'A', count: 30 }, { zone: 'loop', ammoId: '', count: 1 },
   { zone: 'loop', ammoId: '', count: 1 }, { zone: 'loop', ammoId: '', count: 1 },
   { zone: 'bottom', ammoId: '', count: 2 }], 10);
out.preset.over = CS.buildMagazineFromPreset(
  [{ zone: 'top', ammoId: 'A', count: 8 }, { zone: 'loop', ammoId: 'B', count: 1 },
   { zone: 'loop', ammoId: 'C', count: 1 }, { zone: 'loop', ammoId: 'D', count: 1 },
   { zone: 'bottom', ammoId: 'E', count: 5 }], 10);
out.preset.emptyLoopRow = CS.buildMagazineFromPreset(
  [{ zone: 'top', ammoId: '', count: 3 }, { zone: 'loop', ammoId: 'B', count: 1 },
   { zone: 'loop', ammoId: '', count: 1 }, { zone: 'loop', ammoId: 'C', count: 1 },
   { zone: 'bottom', ammoId: '', count: 2 }], 5);
out.preset.bottomOnly = CS.buildMagazineFromPreset(
  [{ zone: 'top', ammoId: '', count: 3 }, { zone: 'loop', ammoId: '', count: 1 },
   { zone: 'loop', ammoId: '', count: 1 }, { zone: 'loop', ammoId: '', count: 1 },
   { zone: 'bottom', ammoId: 'D', count: 2 }], 5);
out.preset.noCapacity = CS.buildMagazineFromPreset(
  [{ zone: 'top', ammoId: 'A', count: 3 }], 0);
out.preset.empty = CS.buildMagazineFromPreset(
  [{ zone: 'top', ammoId: '', count: 3 }, { zone: 'loop', ammoId: '', count: 1 },
   { zone: 'loop', ammoId: '', count: 1 }, { zone: 'loop', ammoId: '', count: 1 },
   { zone: 'bottom', ammoId: '', count: 2 }], 10);
out.preset.weights = CS.buildMagazineFromPreset(
  [{ zone: 'top', ammoId: 'A', count: 1 }, { zone: 'loop', ammoId: 'B', count: 2 },
   { zone: 'loop', ammoId: 'C', count: 1 }, { zone: 'loop', ammoId: '', count: 1 },
   { zone: 'bottom', ammoId: 'E', count: 1 }], 7);

// ———————————————————— 补充：肉体伤害 / 黑化分散 / 续命中 ————————————————————
out.body = {};
const BODY_HP = { head: 35, chest: 85, stomach: 70, leftArm: 60, rightArm: 60, leftLeg: 65, rightLeg: 65 };
const hit = (part, extra) => CS.simulate(Object.assign({
  magazine: [{ id: 'x', n: 'X', dmg: 40, pen: 99, ard: 10, v0: 900, pc: 1 }],
  rpm: 600, dist: 0, penChanceFn: function () { return 1; },
  targetPartHp: Object.assign({}, BODY_HP), armorLayers: [],
  hitProfile: { mode: 'fixed', part: part }, seed: 1
}, extra));
const bh = (r) => r.shots[0].pellets[0];

out.body.chest = (() => { const r = hit('chest'); return { chest: r.targetFinal.parts.chest.hp, dmgToPart: bh(r).dmgToPart, overflow: bh(r).overflow || null }; })();
out.body.leftArm = (() => { const r = hit('leftArm'); return { leftArm: r.targetFinal.parts.leftArm.hp, dmgToPart: bh(r).dmgToPart }; })();
out.body.leftLeg = (() => { const r = hit('leftLeg'); return { leftLeg: r.targetFinal.parts.leftLeg.hp, dmgToPart: bh(r).dmgToPart }; })();
out.body.stomach = (() => { const r = hit('stomach'); return { stomach: r.targetFinal.parts.stomach.hp, dmgToPart: bh(r).dmgToPart }; })();

// 黑化后再命中：手臂 0.49 / 腿 0.7 / 胃 1.05（一发 40 打黑化部位）
const blacked = (part, hp0) => {
  const ammo = { id: 'x', n: 'X', dmg: 40, pen: 99, ard: 10, v0: 900, pc: 1 };
  const r = CS.simulate({
    magazine: [Object.assign({}, ammo), Object.assign({}, ammo)],
    rpm: 600, dist: 0, penChanceFn: function () { return 1; },
    targetPartHp: Object.assign({}, BODY_HP, part === 'leftArm' || part === 'leftLeg' || part === 'stomach' ? {} : {}),
    armorLayers: [], hitProfile: { mode: 'fixed', part: part }, seed: 1
  });
  return r;
};
// 用「先打残 1 发（低伤）→ 再打 40」的两发序列构造黑化后命中：直接以 maxShots 控制不适用，
// 改为自定义部件血量让第一发恰好打黑、第二发打黑化部位
out.body.blackedArm = (() => {
  const ammo = { id: 'x', n: 'X', dmg: 40, pen: 99, ard: 10, v0: 900, pc: 1 };
  const r = CS.simulate({
    magazine: [Object.assign({}, ammo), Object.assign({}, ammo)],
    rpm: 600, dist: 0, penChanceFn: function () { return 1; },
    targetPartHp: { head: 35, chest: 85, stomach: 70, leftArm: 40, rightArm: 60, leftLeg: 65, rightLeg: 65 },
    armorLayers: [], hitProfile: { mode: 'fixed', part: 'leftArm' }, seed: 1
  });
  const p2 = r.shots[1].pellets[0];
  return { overflow: p2.overflow, aliveParts: p2.overflow ? p2.overflow.to.length : 0 };
})();
out.body.blackedLeg = (() => {
  const ammo = { id: 'x', n: 'X', dmg: 40, pen: 99, ard: 10, v0: 900, pc: 1 };
  const r = CS.simulate({
    magazine: [Object.assign({}, ammo), Object.assign({}, ammo)],
    rpm: 600, dist: 0, penChanceFn: function () { return 1; },
    targetPartHp: { head: 35, chest: 85, stomach: 70, leftArm: 60, rightArm: 60, leftLeg: 40, rightLeg: 65 },
    armorLayers: [], hitProfile: { mode: 'fixed', part: 'leftLeg' }, seed: 1
  });
  const p2 = r.shots[1].pellets[0];
  return { overflow: p2.overflow, aliveParts: p2.overflow ? p2.overflow.to.length : 0 };
})();
out.body.blackedStomach = (() => {
  const ammo = { id: 'x', n: 'X', dmg: 40, pen: 99, ard: 10, v0: 900, pc: 1 };
  const r = CS.simulate({
    magazine: [Object.assign({}, ammo), Object.assign({}, ammo)],
    rpm: 600, dist: 0, penChanceFn: function () { return 1; },
    targetPartHp: { head: 35, chest: 85, stomach: 40, leftArm: 60, rightArm: 60, leftLeg: 65, rightLeg: 65 },
    armorLayers: [], hitProfile: { mode: 'fixed', part: 'stomach' }, seed: 1
  });
  const p2 = r.shots[1].pellets[0];
  return { overflow: p2.overflow, aliveParts: p2.overflow ? p2.overflow.to.length : 0 };
})();

// 穿过手臂后继续命中胸腔（估算模型，默认关闭）
out.body.throughOff = (() => { const r = hit('leftArm'); const p = bh(r); return { has: !!p.throughBody, chest: r.targetFinal.parts.chest.hp }; })();
out.body.throughOn = (() => { const r = hit('leftArm', { throughBody: 'estimate' }); const p = bh(r);
  return { tb: p.throughBody, chest: r.targetFinal.parts.chest.hp, arm: r.targetFinal.parts.leftArm.hp }; })();

// Boss 与 PMC 血池不同
out.body.bossVsPmc = (() => {
  const BOSS = { head: 70, chest: 210, stomach: 170, leftArm: 100, rightArm: 100, leftLeg: 120, rightLeg: 120 };
  const a = hit('chest');
  const b = CS.simulate({
    magazine: [{ id: 'x', n: 'X', dmg: 40, pen: 99, ard: 10, v0: 900, pc: 1 }],
    rpm: 600, dist: 0, penChanceFn: function () { return 1; },
    targetPartHp: BOSS, armorLayers: [], hitProfile: { mode: 'fixed', part: 'chest' }, seed: 1
  });
  return { pmcChest: a.targetFinal.parts.chest.hp, bossChest: b.targetFinal.parts.chest.hp };
})();

// 复现
out.body.reproA = JSON.stringify(hit('chest', { throughBody: 'estimate', seed: 42 }).targetFinal.parts);
out.body.reproB = JSON.stringify(hit('chest', { throughBody: 'estimate', seed: 42 }).targetFinal.parts);

// —— R17S2：严格 30 发序列 + 多弹药固定区 + 区域迁移语义 ——
out.preset.exact30 = CS.buildMagazineFromPreset(
  [{ zone: 'top', ammoId: 'A', count: 3 }, { zone: 'loop', ammoId: 'B', count: 1 },
   { zone: 'loop', ammoId: 'C', count: 1 }, { zone: 'loop', ammoId: '', count: 1 },
   { zone: 'bottom', ammoId: 'D', count: 2 }], 30);
out.preset.multiFixed = CS.buildMagazineFromPreset(
  [{ zone: 'top', ammoId: 'A', count: 2 }, { zone: 'top', ammoId: 'B', count: 1 },
   { zone: 'loop', ammoId: 'C', count: 1 }, { zone: 'bottom', ammoId: 'D', count: 1 },
   { zone: 'bottom', ammoId: 'E', count: 1 }], 30);
out.preset.threeLoop = CS.buildMagazineFromPreset(
  [{ zone: 'loop', ammoId: 'A', count: 1 }, { zone: 'loop', ammoId: 'B', count: 1 },
   { zone: 'loop', ammoId: 'C', count: 1 }], 10);
out.preset.topMultiOnly = CS.buildMagazineFromPreset(
  [{ zone: 'top', ammoId: 'A', count: 2 }, { zone: 'top', ammoId: 'B', count: 3 }], 10);
out.preset.capTruncTop = CS.buildMagazineFromPreset(
  [{ zone: 'top', ammoId: 'A', count: 8 }], 5);

// —— R17S3：区域内部顺序直接决定弹序（拖拽后 UI 顺序 = 引擎顺序） ——
out.preset.loopCAB = CS.buildMagazineFromPreset(
  [{ zone: 'loop', ammoId: 'C', count: 1 }, { zone: 'loop', ammoId: 'A', count: 1 },
   { zone: 'loop', ammoId: 'B', count: 1 }], 9);
out.preset.topOrder = CS.buildMagazineFromPreset(
  [{ zone: 'top', ammoId: 'A', count: 1 }, { zone: 'top', ammoId: 'B', count: 2 },
   { zone: 'bottom', ammoId: 'F', count: 1 }, { zone: 'bottom', ammoId: 'G', count: 1 }], 8);

const AMMO_FOR_HIT = { id: 'h', n: 'H', dmg: 40, pen: 30, ard: 20, v0: 900, pc: 1 };

// —— R17S4：命中率（0/50/100）+ 循环区上限 ——
const hitBase = {
  magazine: [Object.assign({}, AMMO_FOR_HIT), Object.assign({}, AMMO_FOR_HIT),
             Object.assign({}, AMMO_FOR_HIT), Object.assign({}, AMMO_FOR_HIT)],
  rpm: 600, penChanceFn: function () { return 1; }, seed: 9,
  targetPartHp: { head: 35, chest: 400, stomach: 70, leftArm: 60, rightArm: 60, leftLeg: 65, rightLeg: 65 },
  armorLayers: [{ name: 'p', kind: 'plate', side: 'front', zones: ['chest'], cls: 4,
                  dur: 40, durMax: 40, material: 'ceramic', bluntThroughput: 0.2 }],
  hitProfile: { mode: 'fixed', part: 'chest' }
};
out.hitRate = {};
out.hitRate.off = CS.simulate(hitBase);
out.hitRate.h100 = CS.simulate(Object.assign({}, hitBase, { hitChance: 1 }));
out.hitRate.h0 = CS.simulate(Object.assign({}, hitBase, { hitChance: 0 }));
out.hitRate.h50a = CS.simulate(Object.assign({}, hitBase, { hitChance: 0.5 }));
out.hitRate.h50b = CS.simulate(Object.assign({}, hitBase, { hitChance: 0.5 }));
out.hitRate.missBarrier = CS.simulate(Object.assign({}, hitBase, {
  hitChance: 0,
  barriers: [{ id: 'wood', n: '木板', material: 'wood', penChanceMul: 1, dmgKeep: 0.9, penKeep: 0.9, ricochetMul: 1 }]
}));

// 循环区 >5 种被引擎拒绝
out.preset.loop6 = CS.buildMagazineFromPreset([
  { zone: 'loop', ammoId: 'A', count: 1 }, { zone: 'loop', ammoId: 'B', count: 1 },
  { zone: 'loop', ammoId: 'C', count: 1 }, { zone: 'loop', ammoId: 'D', count: 1 },
  { zone: 'loop', ammoId: 'E', count: 1 }, { zone: 'loop', ammoId: 'F', count: 1 }
], 30);

process.stdout.write(JSON.stringify(out));
