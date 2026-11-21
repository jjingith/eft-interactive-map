// R19.12 引擎侧审计探针（真实数据，不做模拟）
//   node tools/r1912_engine.js all
// 输出三份 JSON 到 docs/r19.12-canvas-audit/：
//   optimizer-conflicts.json      真实互斥案例（含修复前会通过的组合）+ 修复后结论
//   optimizer-final-validation.json  每个有效方案的整树校验档案
//   optimizer-no-solution.json    无解案例与可读原因
const fs = require("fs");
const path = require("path");
const ROOT = path.resolve(__dirname, "..");
const GB = require(path.join(ROOT, "gun_builder.js"));

const items = JSON.parse(fs.readFileSync(path.join(ROOT, "data/items.json"), "utf8")).items;
const stats = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gun-stats.json"), "utf8"));
const presets = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gun-presets.json"), "utf8")).presets || {};

const OUT = path.join(ROOT, "docs", "r19.12-canvas-audit");
fs.mkdirSync(OUT, { recursive: true });

const ctx = GB.context(items, stats);
const byGun = {};
Object.values(presets).forEach(function (p) { (byGun[p.g] = byGun[p.g] || []).push(p); });

const NAME = function (id) { return (items[id] || {}).n || id; };

function defaultInstalled(gunId) {
  // 预设 map 的**键**才是预设 id（值对象里没有 .id 字段）——必须按 key 取官方默认预设，
  // 否则会退回列表第一项（往往是改型预设，不是出厂默认）。
  const def = (stats.guns[gunId] || {}).preset;
  const p = (def && presets[def] && presets[def].g === gunId) ? presets[def]
    : (byGun[gunId] || [])[0];
  return (p && p.i) || {};
}

function pairsOf(installed) {
  return GB.conflictPairs(ctx, installed).map(function (p) {
    return {
      a: p.nameA, b: p.nameB, idA: p.a, idB: p.b,
      pathA: p.pathA, pathB: p.pathB,
      dirAtoB: p.dirAtoB, dirBtoA: p.dirBtoA
    };
  });
}

// ---------------------------------------------------------------- 1) 冲突案例
function conflictsReport() {
  const known = {
    // 实测在修复前会作为"有效方案"输出的真实互斥组合（数据里的 conflictingItems 是单向的）
    m4a1: "5447a9cd4bdc2dbd208b4567",
    heraGrip: "5a33e75ac4a2826c6e06d759",
    ubrStock: "5947e98b86f774778f1448bc",
    a2Rear: "55d5f46a4bdc2d1b198b4567"
  };
  const gid = known.m4a1;
  const base = GB.sanitize(ctx, gid, defaultInstalled(gid)).installed;

  // 修复前等价装配：默认装配 + 把枪托换成 UBR（握把仍是 Hera 一体化枪托）
  const legacy = {};
  Object.keys(base).forEach(function (k) { if (base[k] && !/^mod_stock(\/|$)/.test(k)) { legacy[k] = base[k]; } });
  legacy["mod_stock"] = known.ubrStock;
  // 修复前的口径：不查 conflictingItems（当时的 validate 只查槽位/allow），
  // 所以这一对会原样保留。这里直接对原始装配算互斥对，不经过现在的 sanitize。
  const legacyPairs = pairsOf(legacy);
  const legacySan = GB.sanitize(ctx, gid, legacy);
  const legacyVerify = GB.verifyBuild(ctx, gid, legacySan.installed, null,
    { ids: [known.ubrStock, known.heraGrip] });
  const legacyRawVerify = GB.verifyBuild(ctx, gid, legacy, null,
    { ids: [known.ubrStock, known.heraGrip] });

  // 修复后：同一意图跑优化器，看它还敢不敢输出这对组合
  const res = GB.optimize(ctx, gid, base, { budget: 900 });
  const after = res.builds.map(function (b) {
    const v = GB.verifyBuild(ctx, gid, b.installed, null, { ids: b.expectIds || [] });
    return {
      name: b.name,
      ok: b.constraintOk,
      verifyOk: v.ok,
      parts: v.parts,
      pairs: pairsOf(b.installed),
      problems: v.problems.map(function (x) { return { kind: x.kind, why: x.why }; }),
      grip: NAME(b.installed["mod_pistol_grip"]),
      stock: NAME(b.installed["mod_stock"]),
      dropped: (b.dropped || []).map(function (d) { return d.name + "(" + d.why + ")"; })
    };
  });

  // 全量扫描：默认权重 + 极端权重，统计还有多少互斥对
  const weights = [{ name: "extreme", recoil: 5, ergo: 5, weight: 0.1, cost: 0.05 }];
  let builds = 0, bad = 0;
  const samples = [];
  Object.keys(byGun).forEach(function (g2) {
    const b0 = GB.sanitize(ctx, g2, defaultInstalled(g2)).installed;
    [undefined, weights].forEach(function (w) {
      const r = GB.optimize(ctx, g2, b0, { budget: 500, weights: w });
      r.builds.forEach(function (b) {
        builds++;
        const pr = pairsOf(b.installed);
        if (pr.length) {
          bad++;
          if (samples.length < 10) {
            samples.push({ gun: NAME(g2), build: b.name, pairs: pr.slice(0, 2), ok: b.constraintOk });
          }
        }
      });
    });
  });

  return {
    schema: "eftmap.r19.12.optimizer-conflicts/1",
    knownCase: {
      gun: NAME(gid),
      intent: "保留 Hera 一体化枪托（握把槽）并换成 Magpul UBR GEN2 枪托",
      items: [
        { role: "握把（一体化枪托）", id: known.heraGrip, name: NAME(known.heraGrip) },
        { role: "枪托", id: known.ubrStock, name: NAME(known.ubrStock) }
      ],
      beforeFix: {
        note: "修复前 validate() 不检查 conflictingItems（只查槽位存在 / allow），"
            + "sanitize 不会清掉任何一方，优化器把这对组合当有效方案输出且 constraintOk=true",
        pairs: legacyPairs,
        // 旧口径（不查互斥）下这套装配只剩结构性问题
        problemsIgnoringConflicts: legacyRawVerify.problems
          .filter(function (p) { return p.kind !== "conflict"; })
          .map(function (x) { return { kind: x.kind, why: x.why }; }),
        // 现在的 sanitize 会把两件里路径靠后的一件清掉，从而拒绝"顺手拆除"式安装
        problemsAfterSanitize: legacyVerify.problems.map(function (x) { return { kind: x.kind, why: x.why }; }),
        sanitizedStillHasBoth: !!(legacySan.installed["mod_stock"] === known.ubrStock &&
                                  legacySan.installed["mod_pistol_grip"] === known.heraGrip)
      },
      afterFix: after
    },
    scan: { buildsChecked: builds, buildsWithPairs: bad, samples: samples },
    rule: "conflictPairs(ctx, installed) 双向比较所有已装件；validate()/checkConstraints()/verifyBuild() 同源"
  };
}

// ---------------------------------------------------------------- 2) 最终校验档案
function finalValidationReport() {
  const rows = [];
  Object.keys(byGun).forEach(function (gid) {
    const base = GB.sanitize(ctx, gid, defaultInstalled(gid)).installed;
    const r = GB.optimize(ctx, gid, base, {
      budget: 700,
      constraints: { scope: true, caps: [] }
    });
    r.builds.forEach(function (b) {
      const v = GB.verifyBuild(ctx, gid, b.installed, { scope: true }, { ids: b.expectIds || [] });
      rows.push({
        gun: NAME(gid), gunId: gid, build: b.name,
        parts: v.parts,
        constraintOk: b.constraintOk,
        verifyOk: v.ok,
        conflicts: v.conflicts.length,
        problems: v.problems.map(function (x) { return { kind: x.kind, why: x.why }; }),
        missing: v.missing,
        droppedCount: (b.dropped || []).length
      });
    });
  });
  // 另跑一遍「纯装配合法性」（不带用户约束）：区分"结构/互斥不合法"和"用户约束未满足"
  let pureTotal = 0, pureOk = 0;
  const pureBad = [];
  Object.keys(byGun).forEach(function (gid) {
    const base = GB.sanitize(ctx, gid, defaultInstalled(gid)).installed;
    const r = GB.optimize(ctx, gid, base, { budget: 500 });
    r.builds.forEach(function (b) {
      pureTotal++;
      const v = GB.verifyBuild(ctx, gid, b.installed, null, { ids: b.expectIds || [] });
      if (v.ok) { pureOk++; } else if (pureBad.length < 8) {
        pureBad.push({ gun: NAME(gid), build: b.name,
                       problems: v.problems.map(function (x) { return x.kind + ":" + x.why; }) });
      }
    });
  });
  const byKind = {};
  rows.forEach(function (r) {
    r.problems.forEach(function (p) {
      byKind[p.kind] = (byKind[p.kind] || 0) + 1;
    });
  });
  return {
    schema: "eftmap.r19.12.optimizer-final-validation/1",
    rule: "每个方案出结果前跑 verifyBuild：槽位存在 + allow 收录 + 父件在位 + 双向互斥 + 用户约束 + 声称件是否还在",
    withConstraints: {
      note: "带 scope:true 的一轮；notOk 多数是「该枪装不上瞄具」这类用户约束未满足，不是结构不合法",
      total: rows.length,
      ok: rows.filter(function (r) { return r.verifyOk; }).length,
      notOk: rows.filter(function (r) { return !r.verifyOk; }).length,
      problemKinds: byKind
    },
    structuralOnly: {
      note: "不带用户约束，只看整棵装配树是否成立（结构 + 双向互斥 + 声称件是否还在）",
      total: pureTotal,
      ok: pureOk,
      badSamples: pureBad
    },
    builds: rows
  };
}

// ---------------------------------------------------------------- 3) 无解案例
function noSolutionReport() {
  const cases = [];
  // 3.1 弹匣容量：AK-74 无 100 发
  const ak = "5bf3e03b0db834001d2c4a9c";
  const akBase = GB.sanitize(ctx, ak, defaultInstalled(ak)).installed;
  const akRes = GB.optimize(ctx, ak, akBase, { budget: 500, constraints: { caps: [100] } });
  cases.push({
    case: "容量约束无解",
    gun: NAME(ak),
    constraints: { caps: [100] },
    availableCaps: GB.magCapacities(ctx, ak, akBase).map(function (c) { return c.cap; }),
    builds: akRes.builds.map(function (b) {
      return { name: b.name, ok: b.constraintOk, capsOk: b.capsOk, why: (b.violations[0] || {}).why };
    }),
    allInvalid: akRes.builds.every(function (b) { return b.constraintOk === false; }),
    firstReason: (akRes.builds[0] && akRes.builds[0].violations[0] && akRes.builds[0].violations[0].why) || ""
  });
  // 3.2 必装型号与枪械不兼容（Glock 的手电装到 AK-74）
  const gtl = "59d790f486f77403cb06aec6";   // Glock GTL 21
  const ak2 = GB.optimize(ctx, ak, akBase, { budget: 400, constraints: { deviceIds: [gtl] } });
  cases.push({
    case: "必装型号不兼容",
    gun: NAME(ak),
    constraints: { deviceIds: [gtl], wanted: NAME(gtl) },
    builds: ak2.builds.map(function (b) {
      return { name: b.name, ok: b.constraintOk, why: (b.violations[0] || {}).why };
    }),
    allInvalid: ak2.builds.every(function (b) { return b.constraintOk === false; }),
    firstReason: (ak2.builds[0] && ak2.builds[0].violations[0] && ak2.builds[0].violations[0].why) || ""
  });
  // 3.3 手枪 100 发弹匣（Glock 17）
  const glock = "5a7ae0c351dfba0017554310";
  const gBase = GB.sanitize(ctx, glock, defaultInstalled(glock)).installed;
  const gRes = GB.optimize(ctx, glock, gBase, { budget: 400, constraints: { caps: [100] } });
  cases.push({
    case: "手枪无 100 发弹匣",
    gun: NAME(glock),
    constraints: { caps: [100] },
    availableCaps: GB.magCapacities(ctx, glock, gBase).map(function (c) { return c.cap; }),
    builds: gRes.builds.map(function (b) {
      return { name: b.name, ok: b.constraintOk, why: (b.violations[0] || {}).why };
    }),
    allInvalid: gRes.builds.every(function (b) { return b.constraintOk === false; }),
    firstReason: (gRes.builds[0] && gRes.builds[0].violations[0] && gRes.builds[0].violations[0].why) || ""
  });
  return {
    schema: "eftmap.r19.12.optimizer-no-solution/1",
    rule: "无解时所有方案 constraintOk=false，且 violations[0].why 给可读原因；绝不退回 30 发/不换型号",
    cases: cases
  };
}

const mode = process.argv[2] || "all";
if (mode === "all" || mode === "conflicts") {
  fs.writeFileSync(path.join(OUT, "optimizer-conflicts.json"),
    JSON.stringify(conflictsReport(), null, 1), "utf8");
}
if (mode === "all" || mode === "final") {
  fs.writeFileSync(path.join(OUT, "optimizer-final-validation.json"),
    JSON.stringify(finalValidationReport(), null, 1), "utf8");
}
if (mode === "all" || mode === "nosolution") {
  fs.writeFileSync(path.join(OUT, "optimizer-no-solution.json"),
    JSON.stringify(noSolutionReport(), null, 1), "utf8");
}
console.log(JSON.stringify({ written: mode, out: OUT }, null, 1));
