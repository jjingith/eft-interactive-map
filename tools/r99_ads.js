// R99 ADS 引擎探针（node，真实数据）：ADS 只由总人机工效决定。
// 用法：
//   node tools/r99_ads.js sameGun <gunId>
//   node tools/r99_ads.js twoGuns
//   node tools/r99_ads.js bounds
const fs = require("fs");
const path = require("path");
const ROOT = path.resolve(__dirname, "..");
const GB = require(path.join(ROOT, "gun_builder.js"));

const items = JSON.parse(fs.readFileSync(path.join(ROOT, "data/items.json"), "utf8")).items;
const stats = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gun-stats.json"), "utf8"));
const presets = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gun-presets.json"), "utf8")).presets;
const ctx = GB.context(items, stats);

const mode = process.argv[2];

function field(st, key) {
  return st && st.fields && st.fields[key] ? st.fields[key].v : null;
}

if (mode === "sameGun") {
  const gunId = process.argv[3];
  const list = Object.keys(presets)
    .map(function (k) { const p = presets[k]; return { id: k, e: p.e, i: p.i || {}, g: p.g }; })
    .filter(function (p) { return p.g === gunId && typeof p.e === "number"; })
    .sort(function (a, b) { return a.e - b.e; });
  const lo = list[0], hi = list[list.length - 1];
  function pack(p) {
    const st = GB.compute(ctx, gunId, p ? p.i : {});
    return { e: field(st, "ergonomics"), ads: field(st, "adsTime"), preset: p ? p.id : null };
  }
  console.log(JSON.stringify({ gunId: gunId, bare: pack(null), low: pack(lo), high: pack(hi) }));
} else if (mode === "twoGuns") {
  // 优先挑「人机值不触发 0.2s 下限」的一对，确保比的是公式而不是地板
  const seen = {};
  const pairs = [];
  Object.keys(stats.guns).forEach(function (id) {
    const e = stats.guns[id].e;
    if (typeof e !== "number") { return; }
    if (seen[e]) { pairs.push([seen[e], id, e]); } else { seen[e] = id; }
  });
  pairs.sort(function (x, y) { return Math.abs(x[2] - 50) - Math.abs(y[2] - 50); });
  const pick = pairs[0] || null;
  if (!pick) { console.log(JSON.stringify({ pair: null })); process.exit(0); }
  function pack(id) {
    const st = GB.compute(ctx, id, {});
    return { gun: id, name: (items[id] || {}).n || id,
             e: field(st, "ergonomics"), ads: field(st, "adsTime") };
  }
  console.log(JSON.stringify({ a: pack(pick[0]), b: pack(pick[1]) }));
} else if (mode === "bounds") {
  const vals = [-100, 0, 10, 50, 100, 200, 1000];
  const out = {};
  vals.forEach(function (v) { out[String(v)] = GB.adsTimeFromErgo(v); });
  out.NaN = GB.adsTimeFromErgo(NaN);
  out.Infinity = GB.adsTimeFromErgo(Infinity);
  out.null = GB.adsTimeFromErgo(null);
  console.log(JSON.stringify(out));
} else {
  console.error("unknown mode");
  process.exit(2);
}
