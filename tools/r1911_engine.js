// R19.11 引擎探针（node，真实数据）：弹匣容量硬约束 / 弹匣清单同源 / M4 枪托链路。
// 用法：
//   node tools/r1911_engine.js caps <gunId> <cap,cap>
//   node tools/r1911_engine.js mags <gunId>[,gunId...]
//   node tools/r1911_engine.js stock <gunId>
const fs = require("fs");
const path = require("path");
const ROOT = path.resolve(__dirname, "..");
const GB = require(path.join(ROOT, "gun_builder.js"));

const items = JSON.parse(fs.readFileSync(path.join(ROOT, "data/items.json"), "utf8")).items;
const stats = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gun-stats.json"), "utf8"));
const presets = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gun-presets.json"), "utf8")).presets;
const compat = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gun-compat.json"), "utf8")).guns;
const ctx = GB.context(items, stats);

function defaultInstalled(gunId) {
  const list = Object.keys(presets).map(function (k) { return presets[k]; })
    .filter(function (p) { return p.g === gunId; });
  const def = (stats.guns[gunId] || {}).preset;
  const p = list.filter(function (x) { return x.id === def; })[0] || list[0];
  return p ? (p.i || {}) : {};
}

function magTreeIds(gunId) {
  const tree = GB.buildTree(ctx, gunId, defaultInstalled(gunId));
  const out = [];
  tree.order.forEach(function (p) {
    if (!/magazine/i.test(String(tree.nodes[p].sid || ""))) { return; }
    (tree.nodes[p].allow || []).forEach(function (id) { if (out.indexOf(id) < 0) { out.push(id); } });
  });
  return out;
}

const mode = process.argv[2];

if (mode === "caps") {
  const gunId = process.argv[3];
  const caps = (process.argv[4] || "").split(",").filter(Boolean).map(Number);
  const base = GB.sanitize(ctx, gunId, defaultInstalled(gunId)).installed;
  const res = GB.optimize(ctx, gunId, base, { budget: 4000, constraints: { caps: caps } });
  const builds = (res.builds || []).map(function (b) {
    const mags = Object.keys(b.installed || {})
      .filter(function (p) { return /magazine/i.test(p); })
      .map(function (p) {
        const it = items[b.installed[p]] || {};
        return { path: p, id: b.installed[p], n: it.n || "", cap: typeof it.cap === "number" ? it.cap : null };
      });
    return {
      name: b.name, ok: b.constraintOk !== false, capsOk: b.capsOk !== false,
      mags: mags,
      violations: (b.violations || []).map(function (v) { return { kind: v.kind, why: v.why }; })
    };
  });
  console.log(JSON.stringify({
    gun: gunId, gunName: (items[gunId] || {}).n, caps: caps,
    available: GB.magCapacities(ctx, gunId, base).map(function (c) { return c.cap; }),
    builds: builds
  }, null, 1));
} else if (mode === "mags") {
  const guns = (process.argv[3] || "").split(",").filter(Boolean);
  const out = {};
  guns.forEach(function (gid) {
    const tree = magTreeIds(gid);
    const cmp = (compat[gid] || {}).mags || [];
    out[gid] = {
      name: (items[gid] || {}).n,
      tree: tree, compat: cmp,
      sameSet: tree.slice().sort().join(",") === cmp.slice().sort().join(","),
      count: tree.length
    };
  });
  console.log(JSON.stringify(out, null, 1));
} else if (mode === "stock") {
  const gunId = process.argv[3];
  const base = GB.sanitize(ctx, gunId, defaultInstalled(gunId)).installed;
  const t0 = GB.buildTree(ctx, gunId, base);
  const stockPaths = t0.order.filter(function (p) { return /^mod_stock(\/|$)/.test(p); });
  const root = t0.nodes["mod_stock"];
  // 一体式枪托（无 stock 子槽）vs 缓冲管（带 stock 子槽）
  const integrated = [], carriers = [];
  (root ? root.allow : []).forEach(function (id) {
    const rec = items[id] || {};
    const hasStockSlot = (rec.slots || []).some(function (s) { return /stock/i.test(s.sid || ""); });
    (hasStockSlot ? carriers : integrated).push({ id: id, n: rec.n });
  });
  // 子槽候选（缓冲管托管的枪托）是否也出现在根槽里（= 需要缓冲管却可直接挂枪身）
  const childIds = [];
  stockPaths.forEach(function (p) {
    if (p === "mod_stock") { return; }
    (t0.nodes[p].allow || []).forEach(function (id) { if (childIds.indexOf(id) < 0) { childIds.push(id); } });
  });
  const rootAllow = root ? root.allow : [];
  const leak = childIds.filter(function (id) { return rootAllow.indexOf(id) >= 0; });
  // 装上一体式枪托后：子槽应消失、只剩一件
  const ubr = integrated.filter(function (x) { return /UBR GEN2/.test(x.n || ""); })[0] ||
              integrated[0];
  let after = null;
  if (ubr) {
    function trialOf(dropGripToo) {
      const t = {};
      Object.keys(base).forEach(function (k) { if (base[k] && !/^mod_stock(\/|$)/.test(k)) { t[k] = base[k]; } });
      if (dropGripToo) { 
        Object.keys(t).forEach(function (k) { if (/^mod_pistol_grip$/.test(k)) { delete t[k]; } });
      }
      t["mod_stock"] = ubr.id;
      const out = GB.sanitize(ctx, gunId, t);
      const t1 = GB.buildTree(ctx, gunId, out.installed);
      return {
        integratedId: ubr.id, integratedName: ubr.n,
        keptStock: out.installed["mod_stock"] === ubr.id,
        dropped: (out.dropped || []).map(function (d) {
          return { path: d.path, name: ((items[d.id] || {}).n || ""), why: d.why };
        }),
        stockPathsAfter: t1.order.filter(function (p) { return /^mod_stock(\/|$)/.test(p); }),
        stockItems: Object.keys(out.installed).filter(function (p) { return /stock/i.test(p); })
          .map(function (p) { return p + "=" + ((items[out.installed[p]] || {}).n || ""); })
      };
    }
    // R19.12：默认 M4 装配里握把是「Hera 一体化枪托」，它与 UBR 等独立枪托上游互斥。
    //   ① 保留握把直接换 UBR → 必须被拒（冲突）
    //   ② 先腾空握把再换 UBR → 合法
    after = trialOf(false);
    after.freeSlot = trialOf(true);
  }
  console.log(JSON.stringify({
    gun: gunId, gunName: (items[gunId] || {}).n,
    stockPaths: stockPaths, rootAllow: rootAllow.length,
    carriers: carriers, integrated: integrated,
    childCount: childIds.length, leakToRoot: leak.length,
    afterIntegrated: after
  }, null, 1));
} else {
  console.error("usage: caps <gun> <caps> | mags <gun,guns> | stock <gun>");
  process.exit(2);
}
