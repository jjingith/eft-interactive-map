// R19.28 勘察探针 2（只读）：照门 raw/calib 对照 + 燕尾槽真父子 + 第六行导轨子槽
const fs = require("fs"), path = require("path");
const ROOT = path.dirname(__dirname);
const GB = require(path.join(ROOT, "gun_builder.js"));
const items = JSON.parse(fs.readFileSync(path.join(ROOT, "data/items.json"), "utf8")).items;
const stats = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gun-stats.json"), "utf8"));
const presets = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gun-presets.json"), "utf8")).presets || {};
const gunslots = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gunslots.json"), "utf8")).guns;
const calib = JSON.parse(fs.readFileSync(path.join(ROOT, "data/gun-layout-calibration.json"), "utf8"));
const src = fs.readFileSync(path.join(ROOT, "app.js"), "utf8");
const block = src.slice(src.indexOf("function gwSidBase("), src.indexOf("function renderGunSkin("));
const api = new Function("itemRec", "GW_ITEM_MAP", block +
  "\nreturn {gwBuildLayout:gwBuildLayout,gwApplyCalibToLayout:gwApplyCalibToLayout," +
  "gwSlotVisible:gwSlotVisible,gwSidBase:gwSidBase};")(
  function (id) { return items[id] || null; }, items);
const ctx = GB.context(items, stats);

const AK_RS_SIG = {
  "59d650cf86f7741b846413a4": "AKM 照门", "5a0eb980fcdbcb001a3b00a6": "AKMB系统照门",
  "5649b0544bdc2d1b2b8b458a": "AK-74 照门", "5ac72e475acfc400180ae6fe": "AK-74M 照门",
  "5ac733a45acfc400192630e2": "AK-105 照门", "5bf3f59f0db834001a6fa060": "RPK-16 照门",
  "649ec2cec93611967b03495e": "AK-12照门", "628a7b23b0f75035732dd565": "RD Enhanced V2 AK 照门"
};

function defInst(gid) {
  const st = (stats.guns || {})[gid] || {};
  if (st.preset && presets[st.preset]) { return presets[st.preset].i || {}; }
  for (const p in presets) { if (presets[p] && presets[p].g === gid) { return presets[p].i || {}; } }
  return {};
}
function build(gid, instOverride, useCalib) {
  const inst = GB.sanitize(ctx, gid, instOverride || defInst(gid)).installed;
  const tree = GB.buildTree(ctx, gid, inst);
  const L = api.gwBuildLayout({ gunId: gid, installed: inst, slots: tree, noCalib: true });
  const recs = (calib.guns[gid] || {}).slots || {};
  let info = null;
  if (useCalib) { info = api.gwApplyCalibToLayout(L, { gunId: gid, installed: inst, slots: tree }, recs); }
  return { inst, tree, L, recs, info, topPad: L.topPad };
}
function cs(L) {
  return L.cells.map(function (c) {
    return { path: c.path, row: c.row, col: c.col, role: c.role || "",
             sid: api.gwSidBase((c.path.split("/").pop() || "")) };
  });
}
function pos(list, p) {
  const c = list.filter(function (x) { return x.path === p; })[0];
  return c ? ("r" + c.row + "c" + c.col) : "MISSING";
}
function findSlotDeep(slots, sid, pfx) {
  pfx = pfx || "";
  for (const s of slots) {
    if (s.sid === sid) { return pfx + s.sid; }
    if (s.slots) { const r = findSlotDeep(s.slots, sid, pfx + s.sid + "/"); if (r) { return r; } }
  }
  return null;
}

const only = process.argv[2];
const out = { rear: [], dvt: [], row6: [] };

// ================= 1) 照门：raw vs calib =================
console.log("=== 1) 照门落位（raw = 无校准，calib = 应用校准）===");
console.log(" 枪".padEnd(30) + " | raw     | calib   | topPad | 签名");
const nonAkC6 = [];
for (const gid of Object.keys(gunslots)) {
  const g = gunslots[gid];
  const rsp = findSlotDeep(g.slots || [], "mod_sight_rear");
  if (!rsp) { continue; }
  const rs = (function get(sl, p) {
    for (const s of sl) {
      if (s.sid === "mod_sight_rear") { return s; }
      if (s.slots) { const r = get(s.slots, p); if (r) { return r; } }
    }
    return null;
  })(g.slots || [], "");
  const allow = (rs && rs.allow) || [];
  const sig = allow.filter(function (a) { return AK_RS_SIG[a]; }).length;
  const b1 = build(gid, null, false);
  const b2 = build(gid, null, true);
  const c1 = cs(b1.L), c2 = cs(b2.L);
  const p1 = pos(c1, "mod_sight_rear"), p2 = pos(c2, "mod_sight_rear");
  if (!sig && p2 === "r2c6") { nonAkC6.push(g.n); }
  out.rear.push({ gid: gid, name: g.n, ak: sig > 0, raw: p1, calib: p2, topPad: b2.topPad,
                  calibN: Object.keys(b2.recs).length });
  if (sig || (!sig && (p1 === "r2c6" || p2 === "r2c6"))) {
    console.log(" " + g.n.slice(0, 28).padEnd(30) + " | " + p1.padEnd(8) + " | " + p2.padEnd(8) +
      " | " + String(b2.topPad).padEnd(6) + " | " + (sig ? "AK" : "-"));
  }
}
console.log(" 非 AK 系落在 r2c6 的：" + JSON.stringify(nonAkC6));

// AK 系但 calib != r2c6 的
const badAk = out.rear.filter(function (r) { return r.ak && r.calib !== "r2c6"; });
console.log(" AK 系但 calib 不等于 r2c6 的：" + badAk.length);
for (const b of badAk) { console.log("   !! " + b.name + " raw=" + b.raw + " calib=" + b.calib + " topPad=" + b.topPad); }

// ================= 2) 燕尾槽真父子 =================
console.log("\n=== 2) 燕尾槽基座 → 子槽（装上带子槽的候选件后）===");
const dvtRows = [];
for (const gid of Object.keys(gunslots)) {
  const g = gunslots[gid];
  const cands = [];
  (function walk(sl, pfx, parBase) {
    for (const s of sl) {
      const base = api.gwSidBase(s.sid);
      const p = pfx + s.sid;
      if (base === "mount") {
        const allow = s.allow || [];
        const hasScope = allow.some(function (a) { return (items[a] || {}).pt === "Scope"; });
        if (hasScope && (!parBase || /^(reciever|receiver|slide|frame|upper|lower)$/.test(parBase))) {
          // 找一个自带子槽的候选件
          const withKids = allow.filter(function (a) { return ((items[a] || {}).slots || []).length > 0; });
          if (withKids.length) { cands.push({ path: p, allow: allow, withKids: withKids }); }
        }
      }
      if (s.slots) { walk(s.slots, p + "/", base); }
    }
  })(g.slots || [], "", "");
  for (const cd of cands) {
    // 取子槽最多的候选件
    let best = cd.withKids[0];
    for (const w of cd.withKids) {
      if (((items[w] || {}).slots || []).length > ((items[best] || {}).slots || []).length) { best = w; }
    }
    const inst = Object.assign({}, defInst(gid));
    inst[cd.path] = best;
    const b = build(gid, inst, true);
    const cl = cs(b.L);
    const pp = pos(cl, cd.path);
    const kids = (b.tree.nodes[cd.path] || {}).children || [];
    const kp = kids.map(function (k) { return { p: k, pos: pos(cl, k), sid: api.gwSidBase((b.tree.nodes[k] || {}).sid || "") } });
    const off = kp.filter(function (k) {
      if (k.pos === "MISSING") { return false; }
      return !(k.pos.split("c")[1] === pp.split("c")[1] &&
               (+k.pos.slice(1).split("c")[0]) < (+pp.slice(1).split("c")[0]));
    });
    dvtRows.push({ gid: gid, name: g.n, item: (items[best] || {}).n, parent: cd.path, pp: pp, kids: kp,
                   off: off.map(function (o) { return o.p + "@" + o.pos; }) });
    out.dvt.push({ gid: gid, name: g.n, item: (items[best] || {}).n, parent: cd.path, pp: pp, kids: kp,
                   off: off.map(function (o) { return o.p + "@" + o.pos; }) });
  }
}
let nOff = 0;
for (const d of dvtRows) {
  const bad = d.off.length > 0 || d.kids.some(function (k) { return k.pos === "MISSING"; });
  if (bad) { nOff++; }
  console.log(" " + (d.name.slice(0, 20) + "/" + (d.item || "").slice(0, 16)).padEnd(38) +
    " P=" + d.pp.padEnd(6) + " K=[" + d.kids.map(function (k) { return k.sid + "@" + k.pos; }).join(" ") + "]" +
    (bad ? "   <<< 非正上方/缺位" : ""));
}
console.log(" 父-子未满足正上方（或子槽缺位）的组数：" + nOff + " / " + dvtRows.length);

// ================= 3) 第六行：装导轨后子槽落位 =================
console.log("\n=== 3) 第六行 r6c1 装「带子槽」候选件前后的布局 ===");
const row6Guns = [];
for (const gid of Object.keys(calib.guns)) {
  const recs = calib.guns[gid].slots || {};
  const r6 = [];
  for (const k of Object.keys(recs)) {
    const s = recs[k];
    if (s.logicalRow === 6 && s.col >= 1 && s.col <= 4) { r6.push({ key: k, col: s.col, path: k.split("|")[0] }); }
  }
  r6.sort(function (a, b) { return a.col - b.col; });
  if (r6.length >= 2) { row6Guns.push({ gid: gid, name: calib.guns[gid].name, r6: r6 }); }
}
for (const R of row6Guns) {
  const first = R.r6[0];
  const node = (function () {
    const b = build(R.gid, null, true);
    return b.tree.nodes[first.path] || null;
  })();
  if (!node) { continue; }
  const allow = node.allow || [];
  const withKids = allow.filter(function (a) { return ((items[a] || {}).slots || []).length > 0; });
  if (!withKids.length) { continue; }
  let best = withKids[0];
  for (const w of withKids) { if (((items[w] || {}).slots || []).length > ((items[best] || {}).slots || []).length) { best = w; } }
  const inst = Object.assign({}, defInst(R.gid));
  inst[first.path] = best;
  const b = build(R.gid, inst, true);
  const cl = cs(b.L);
  const kids = (b.tree.nodes[first.path] || {}).children || [];
  const before = cs(build(R.gid, null, true).L);
  const row = {
    gun: R.name, slot1: first.path, item: (items[best] || {}).n,
    before: R.r6.map(function (e) { return e.path.split("/").pop() + "@" + pos(before, e.path); }),
    after: R.r6.map(function (e) { return e.path.split("/").pop() + "@" + pos(cl, e.path); }),
    kids: kids.map(function (k) { return k + "@" + pos(cl, k); })
  };
  out.row6.push(row);
  const dup = {}; const d2 = [];
  for (const c of cl) { const k = c.row + "|" + c.col; if (dup[k]) { d2.push(k + ":" + c.path); } dup[k] = 1; }
  console.log(" " + R.name.slice(0, 24).padEnd(26) + " 装[" + (items[best] || {}).n + "] 于 " + first.path);
  console.log("    前: " + row.before.join("  "));
  console.log("    后: " + row.after.join("  ") + "   子槽: " + row.kids.join(" ") + (d2.length ? "  重叠!" + d2.join(",") : ""));
}

fs.mkdirSync(path.join(ROOT, "docs/r19.28"), { recursive: true });
fs.writeFileSync(path.join(ROOT, "docs/r19.28/probe-baseline.json"), JSON.stringify(out, null, 2), "utf8");
console.log("\n输出 docs/r19.28/probe-baseline.json");
