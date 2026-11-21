/* R19 配枪引擎单测（Node，无第三方依赖）
 *
 * 最强的一条：拿 data/gun-presets.json 里 **373 个真实预设**当基准 ——
 * 每个预设都记录了完整装配清单和游戏内真值（e / rv / rh），
 * 用引擎按清单重算，逐条比残差。公式对不对不靠自述，靠这 373 条数据。
 *
 * 运行：node tests/js/gun_builder_test.js
 */
"use strict";

const path = require("path");
const fs = require("fs");
const GB = require(path.join(__dirname, "..", "..", "gun_builder.js"));

const ROOT = path.join(__dirname, "..", "..");
const items = JSON.parse(fs.readFileSync(path.join(ROOT, "data", "items.json"), "utf8")).items;
const statData = JSON.parse(fs.readFileSync(path.join(ROOT, "data", "gun-stats.json"), "utf8"));
const presets = JSON.parse(fs.readFileSync(path.join(ROOT, "data", "gun-presets.json"), "utf8")).presets;

const ctx = GB.context(items, statData);

let pass = 0, fail = 0;
const failures = [];
function ok(cond, name, detail) {
  if (cond) { pass++; return true; }
  fail++;
  failures.push(name + (detail ? "  -> " + detail : ""));
  return false;
}
function near(a, b, tol) { return a !== null && b !== null && Math.abs(a - b) <= tol; }

// ---------------------------------------------------------------- 1. 公式对 373 条真值
const residuals = { e: [], rv: [], rh: [] };
let checked = 0;
for (const pid in presets) {
  const pr = presets[pid];
  const installed = pr.i || {};
  const st = GB.compute(ctx, pr.g, installed);
  if (!st.fields.ergonomics || st.fields.ergonomics.v === null) { continue; }
  checked++;
  if (typeof pr.e === "number") { residuals.e.push(st.fields.ergonomics.v - pr.e); }
  if (typeof pr.rv === "number") { residuals.rv.push(st.fields.recoilV.v - pr.rv); }
  if (typeof pr.rh === "number") { residuals.rh.push(st.fields.recoilH.v - pr.rh); }
}
function dist(arr) {
  const abs = arr.map(Math.abs).sort((a, b) => a - b);
  const mean = arr.reduce((s, v) => s + v, 0) / arr.length;
  return { mean, med: abs[Math.floor(abs.length / 2)],
           p95: abs[Math.floor(abs.length * 0.95)], max: abs[abs.length - 1] };
}
const se = dist(residuals.e), sv = dist(residuals.rv), sh = dist(residuals.rh);
console.log("[1] 真实预设重算：%d 条", checked);
console.log("    人机工效  平均残差 %s  中位 %s  p95 %s  最大 %s",
  se.mean.toFixed(3), se.med.toFixed(3), se.p95.toFixed(3), se.max.toFixed(3));
console.log("    垂直后坐力 平均残差 %s  中位 %s  p95 %s  最大 %s",
  sv.mean.toFixed(3), sv.med.toFixed(3), sv.p95.toFixed(3), sv.max.toFixed(3));
console.log("    水平后坐力 平均残差 %s  中位 %s  p95 %s  最大 %s",
  sh.mean.toFixed(3), sh.med.toFixed(3), sh.p95.toFixed(3), sh.max.toFixed(3));
ok(checked >= 300, "预设样本数 >= 300", String(checked));
ok(se.p95 <= 0.11, "人机工效 p95 残差 <= 0.11", se.p95.toFixed(3));
ok(sv.p95 <= 0.5, "垂直后坐力 p95 残差 <= 0.5", sv.p95.toFixed(3));
ok(sh.p95 <= 0.5, "水平后坐力 p95 残差 <= 0.5", sh.p95.toFixed(3));

// ---------------------------------------------------------------- 2. 递归槽位
const AK74 = "5bf3e03b0db834001d2c4a9c";
const tree0 = GB.buildTree(ctx, AK74, {});
ok(tree0.order.length > 5, "AK-74 初始槽位 > 5", String(tree0.order.length));
// 装一个带子槽的护木后，树上应出现它的子槽
let handguardPath = null, handguardId = null;
for (const p of tree0.order) {
  const c = GB.candidates(ctx, AK74, {}, p);
  const hit = c.rows.filter(r => !r.blocked && r.slots >= 2)[0];
  if (hit) { handguardPath = p; handguardId = hit.id; break; }
}
ok(!!handguardPath, "能找到带子槽的配件用于递归测试", handguardPath || "none");
if (handguardPath) {
  const inst = {}; inst[handguardPath] = handguardId;
  const tree1 = GB.buildTree(ctx, AK74, inst);
  const childPaths = tree1.order.filter(p => p.indexOf(handguardPath + "/") === 0);
  ok(childPaths.length > 0, "装父件后展开子槽", childPaths.join(",") || "no child");
  // 父件移除 → 子槽必须消失
  const tree2 = GB.buildTree(ctx, AK74, {});
  const orphan = tree2.order.filter(p => p.indexOf(handguardPath + "/") === 0);
  ok(orphan.length === 0, "卸下父件后子槽消失", orphan.join(",") || "ok");
}

// ---------------------------------------------------------------- 3. 兼容性校验
{
  const inst = {};
  inst[handguardPath || tree0.order[0]] = "5bf3e03b0db834001d2c4a9c";   // 枪械本身不是配件
  const v = GB.validate(ctx, AK74, inst);
  ok(!v.ok, "把枪械本体当配件装进槽位应判非法");
  // 合法装配
  const good = {};
  const anyPath = tree0.order[0];
  const cand = GB.candidates(ctx, AK74, {}, anyPath);
  const row = cand.rows.filter(r => !r.blocked)[0];
  if (row) {
    good[anyPath] = row.id;
    ok(GB.validate(ctx, AK74, good).ok, "合法装配通过校验", anyPath);
    // 同一型号配件装在多个槽位：**合法**，但要记录在 duplicates 里（成本按件数算）。
    // 用真实官方预设验证（M4A1 LVOA 里两个相同的 mod_mount_002/003）。
    let dupCase = null;
    for (const pid in presets) {
      const pr = presets[pid];
      const v = GB.validate(ctx, pr.g, pr.i || {});
      if (v.ok && v.duplicates.length) { dupCase = { pr: pr, v: v }; break; }
    }
    ok(!!dupCase, "存在官方预设使用同一型号配件两次");
    if (dupCase) {
      const ids = {};
      Object.values(dupCase.pr.i).forEach(id => { ids[id] = (ids[id] || 0) + 1; });
      const dupId = Object.keys(ids).filter(k => ids[k] > 1)[0];
      const c = GB.cost(ctx, dupCase.pr.g, dupCase.pr.i, { includeStock: true });
      const same = c.rows.filter(r => r.id === dupId);
      ok(same.length >= 2, "成本明细里同一配件按件数出现多次",
         dupId + " x" + same.length);
    }
    // sanitize 会把它清掉
    const bad = {}; bad["不存在的槽位"] = row.id;
    const s = GB.sanitize(ctx, AK74, bad);
    ok(Object.keys(s.installed).length === 0 && s.dropped.length === 1,
       "sanitize 清掉非法槽位", JSON.stringify(s.dropped));
  }
}

// ---------------------------------------------------------------- 4. 预设序列化往返
{
  const inst = {};
  tree0.order.slice(0, 3).forEach(p => {
    const c = GB.candidates(ctx, AK74, inst, p);
    const r = c.rows.filter(x => !x.blocked)[0];
    if (r) { inst[p] = r.id; }
  });
  const json = JSON.stringify(GB.serialize(AK74, inst, { name: "测试" }));
  const back = GB.parse(json);
  ok(back.gunId === AK74, "序列化往返 gunId");
  ok(JSON.stringify(back.slots) === JSON.stringify(inst), "序列化往返 slots");
  let threw = false;
  try { GB.parse(JSON.stringify({ kind: "other", gunId: AK74, slots: {} })); }
  catch (e) { threw = true; }
  ok(threw, "解析非本格式的 JSON 应报错");
}

// ---------------------------------------------------------------- 5. 成本
{
  const inst = {};
  const p0 = tree0.order[0];
  const r0 = GB.candidates(ctx, AK74, {}, p0).rows.filter(r => !r.blocked)[0];
  if (r0) { inst[p0] = r0.id; }
  const c = GB.cost(ctx, AK74, inst, { includeStock: true });
  ok(c.total !== null && c.total > 0, "整枪成本 > 0", String(c.total));
  const c2 = GB.cost(ctx, AK74, inst, { includeStock: false, stockIds: {} });
  ok(c2.total !== null, "改装件成本可算", String(c2.total));
  ok(c.rows.some(r => r.role === "枪械本体"), "成本明细含枪械本体");
}

// ---------------------------------------------------------------- 6. 比较
{
  const a = GB.compute(ctx, AK74, {});
  const b = GB.compute(ctx, "5447a9cd4bdc2dbd208b4567", {});
  const rows = GB.compare(a, b);
  ok(rows.length >= 6, "比较字段 >= 6", String(rows.length));
  const erg = rows.filter(r => r.key === "ergonomics")[0];
  ok(erg && erg.a !== null && erg.b !== null && erg.delta !== null, "比较给出 A/B/delta");
}

// ---------------------------------------------------------------- 7. 优化器
{
  const t0 = Date.now();
  const res = GB.optimize(ctx, AK74, {}, { budget: 2500 });
  const ms = Date.now() - t0;
  ok(res.builds.length >= 2, "优化器产出 >= 2 个方案", String(res.builds.length));
  ok(res.evaluations <= 2500, "优化器评估次数在预算内", String(res.evaluations));
  ok(ms < 8000, "优化器耗时 < 8s", ms + "ms");
  let allValid = true, worse = 0;
  const base = GB.compute(ctx, AK74, {});
  res.builds.forEach(b => {
    const v = GB.validate(ctx, AK74, b.installed);
    if (!v.ok) { allValid = false; }
    if (b.stats.fields.recoilV.v > base.fields.recoilV.v) { worse++; }
  });
  ok(allValid, "优化器所有方案都通过兼容性校验");
  ok(worse === 0, "优化方案的后坐力都不劣于空装配", String(worse));
}

// ---------------------------------------------------------------- 8. 缺失值不填 0
{
  const st = GB.compute(ctx, AK74, {});
  ok(st.fields.velocity.v === null && st.fields.velocity.conf === "missing",
     "未选弹药时初速为 null 且标 missing",
     String(st.fields.velocity.v) + "/" + st.fields.velocity.conf);
  const fakeGun = "____not_a_gun____";
  const st2 = GB.compute(ctx, fakeGun, {});
  ok(st2.fields.ergonomics.v === null, "未知枪械属性为 null 而非 0");
}

// ---------------------------------------------------------------- 输出
console.log("\n%d passed, %d failed", pass, fail);
if (failures.length) {
  console.log("\n失败项：");
  failures.forEach(f => console.log("  - " + f));
  process.exit(1);
}
