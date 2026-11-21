// R19.12 默认弹药审计：把 app.js 的 gwDefaultAmmoRule() 抠到 node 上，用真实弹药库跑全枪。
// 用法：node tools/r1912_ammo.js  → docs/r19.12-canvas-audit/default-ammo.json 内容到 stdout
const fs = require("fs");
const path = require("path");
const ROOT = path.resolve(__dirname, "..");

const items = JSON.parse(fs.readFileSync(path.join(ROOT, "data/items.json"), "utf8")).items;
const stats = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gun-stats.json"), "utf8"));
const ammo = JSON.parse(fs.readFileSync(path.join(ROOT, "data/ammo.json"), "utf8")).ammo;
const presets = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gun-presets.json"), "utf8")).presets || {};

const src = fs.readFileSync(path.join(ROOT, "app.js"), "utf8");
const block = src.slice(src.indexOf("function gwDefaultAmmoRule("), src.indexOf("function defaultAmmoForGun("));
const rule = new Function("list", block + "\nreturn gwDefaultAmmoRule(list);");

const byCal = {};
ammo.forEach(function (a) { (byCal[a.cal] = byCal[a.cal] || []).push(a); });

const gunIds = [];
Object.values(presets).forEach(function (p) { if (gunIds.indexOf(p.g) < 0) { gunIds.push(p.g); } });

const guns = {};
const summary = { guns: 0, withAmmo: 0, fmjMode: 0, medianMode: 0, noData: [], notMedian: [], higherThanMedian: [] };

gunIds.forEach(function (gid) {
  const st = stats.guns[gid] || {};
  const list = (byCal[st.cal] || []);
  const r = rule(list);
  const rec = {
    gunId: gid,
    name: (items[gid] || {}).n,
    caliber: st.cal || null,
    caliberZh: (list[0] && (list[0].caln || list[0].cal)) || null,
    compatibleAmmo: list.length,
    defaultAmmoId: r.id,
    defaultAmmoName: r.n,
    pen: r.pen,
    dmg: r.dmg,
    v0: r.v0,
    medianPen: r.median,
    mode: r.mode,
    reason: r.reason,
    // 该口径里穿深最高 / 最低的弹（用于证明"没有默认选最高穿深"）
    maxPen: list.filter(function (a) { return a.t === "bullet"; })
      .reduce(function (m, a) { return (a.pen > m ? a.pen : m); }, 0),
    minPen: list.filter(function (a) { return a.t === "bullet" && a.pen > 0; })
      .reduce(function (m, a) { return (m === 0 || a.pen < m ? a.pen : m); }, 0)
  };
  if (r.id) {
    summary.withAmmo++;
    if (r.mode === "fmj") { summary.fmjMode++; } else { summary.medianMode++; }
    if (r.pen !== r.median) { summary.notMedian.push(rec.name); }
    if (r.pen > r.median) { summary.higherThanMedian.push({ gun: rec.name, pen: r.pen, median: r.median }); }
    // 反向校验：默认弹必须真的属于该口径
    const rec0 = list.filter(function (a) { return a.id === r.id; })[0];
    if (!rec0) { rec.compatible = false; }
    else { rec.compatible = true; }
  } else {
    summary.noData.push({ gun: rec.name, caliber: rec.caliber });
  }
  guns[gid] = rec;
  summary.guns++;
});

console.log(JSON.stringify({
  schema: "eftmap.r19.12.default-ammo/1",
  rule: "只取真实弹头(t=bullet,pen>0)；优先 FMJ 类标准弹；否则取穿深最接近该口径中位数的普通弹；平手取更便宜、再按名称",
  summary: summary,
  highlights: ["5447a9cd4bdc2dbd208b4567", "5a7ae0c351dfba0017554310",
               "65290f395ae2ae97b80fdf2d", "5bf3e03b0db834001d2c4a9c",
               "5a7ae0c351dfba0017554310"].filter(function (v, i, a) { return a.indexOf(v) === i; })
    .map(function (id) { return guns[id] || null; }).filter(Boolean),
  guns: guns
}, null, 1));
