// R19.10 引擎探针：具体型号约束是否真的进入优化结果。
// 用法：node tools/r1910_engine.js <gunId> <scopeId|-> <devId1,devId2|->
// 输出 JSON：{ builds: [{name, ok, installedHas: {...}, violations: []}], check: {...} }
const fs = require("fs");
const path = require("path");
const ROOT = path.resolve(__dirname, "..");
const GB = require(path.join(ROOT, "gun_builder.js"));

const items = JSON.parse(fs.readFileSync(path.join(ROOT, "data/items.json"), "utf8")).items;
const stats = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gun-stats.json"), "utf8"));
const presets = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gun-presets.json"), "utf8")).presets;

const gunId = process.argv[2];
const scopeId = process.argv[3] && process.argv[3] !== "-" ? process.argv[3] : "";
const devIds = (process.argv[4] && process.argv[4] !== "-") ? process.argv[4].split(",") : [];

const ctx = GB.context(items, stats);
const list = Object.keys(presets).map(function (k) { return presets[k]; })
  .filter(function (p) { return p.g === gunId; });
const def = (stats.guns[gunId] || {}).preset;
const preset = list.filter(function (p) { return p.id === def; })[0] || list[0] || { i: {} };
const base = GB.sanitize(ctx, gunId, preset.i || {}).installed;

const cons = {};
if (scopeId) { cons.scopeId = scopeId; }
if (devIds.length) { cons.deviceIds = devIds; }

const want = (scopeId ? [scopeId] : []).concat(devIds);
const res = GB.optimize(ctx, gunId, base, { budget: 4000, constraints: cons });
const out = {
  gun: gunId, gunName: (items[gunId] || {}).n,
  want: want.map(function (id) { return { id: id, n: (items[id] || {}).n || id }; }),
  builds: (res.builds || []).map(function (b) {
    const ids = Object.keys(b.installed || {}).map(function (p) { return b.installed[p]; });
    return {
      name: b.name, ok: b.constraintOk !== false,
      missing: want.filter(function (id) { return ids.indexOf(id) < 0; }),
      violations: (b.violations || []).map(function (v) { return v.why; })
    };
  }),
  check: (function () {
    const first = (res.builds || [])[0];
    if (!first) { return { ok: false, violations: ["没有方案"] }; }
    const c = GB.checkConstraints(ctx, gunId, first.installed, cons);
    return { ok: c.ok, violations: (c.violations || []).map(function (v) { return v.why; }) };
  })()
};
console.log(JSON.stringify(out, null, 1));
