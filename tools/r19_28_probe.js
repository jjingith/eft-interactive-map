// R19.28 勘察探针（只读，不写正式数据）
//   用途：查出当前 (1) AK 系照门列 (2) 燕尾槽父子坐标 (3) 第六行战术装置布局
//   输出：docs/r19.28/probe-baseline.json + 控制台摘要
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

// 结构签名：AK 系标准照门物品 id（父照门 = AKM/AKMB/AK-74/AK-74M/AK-105/RPK-16/AK-12/RD V2）
const AK_RS_SIG = {
  "59d650cf86f7741b846413a4": "AKM 照门",
  "5a0eb980fcdbcb001a3b00a6": "AKMB系统照门",
  "5649b0544bdc2d1b2b8b458a": "AK-74 照门",
  "5ac72e475acfc400180ae6fe": "AK-74M 照门",
  "5ac733a45acfc400192630e2": "AK-105 照门",
  "5bf3f59f0db834001a6fa060": "RPK-16 照门",
  "649ec2cec93611967b03495e": "AK-12照门",
  "628a7b23b0f75035732dd565": "RD Enhanced V2 AK 照门"
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
function cellsOf(L) {
  return L.cells.map(function (c) {
    return { path: c.path, row: c.row - L.topPad, col: c.col, role: c.role || "",
             lane: c.lane || "", pin: !!c.pinned, anchor: c.anchorSlot || "",
             sid: (c.path.split("/").pop() || "").replace(/_\d+$/, "") };
  });
}
function findSlot(slots, sid) {
  for (const s of slots) {
    if (s.sid === sid) { return s; }
    if (s.slots) { const r = findSlot(s.slots, sid); if (r) { return r; } }
  }
  return null;
}

const out = { rearSight: [], dovetail: [], row6: [], akFamily: [] };

// ---------- 1) 全部有照门槽的枪：当前列 ----------
const rsGuns = [];
for (const gid of Object.keys(gunslots)) {
  const g = gunslots[gid];
  const rs = findSlot(g.slots || [], "mod_sight_rear");
  if (!rs) { continue; }
  const allow = rs.allow || [];
  const sig = allow.filter(function (a) { return AK_RS_SIG[a]; }).map(function (a) { return AK_RS_SIG[a]; });
  rsGuns.push({ gid: gid, name: g.n, sig: sig, allowNames: allow.map(function (a) { return (items[a] || {}).n || a; }) });
}
for (const r of rsGuns) {
  const b = build(r.gid, null, true);
  const cs = cellsOf(b.L);
  const rsCells = cs.filter(function (c) { return c.sid === "mod_sight_rear"; });
  const rs2 = rsCells.filter(function (c) { return c.role === "rearSight2" || c.path.indexOf("/") >= 0; });
  const rsMain = rsCells.filter(function (c) { return c.path.indexOf("/") < 0; });
  out.rearSight.push({
    gid: r.gid, name: r.name,
    akFamily: r.sig.length > 0,
    sig: r.sig,
    calibCount: Object.keys(b.recs).length,
    topPad: b.topPad,
    main: rsMain.map(function (c) { return "r" + c.row + "c" + c.col + "[" + c.role + "]"; }),
    subs: rs2.map(function (c) { return "r" + c.row + "c" + c.col + "[" + c.role + "]"; }),
    all: cs.map(function (c) { return c.sid + "@r" + c.row + "c" + c.col; })
  });
}
out.akFamily = rsGuns.filter(function (r) { return r.sig.length > 0; })
  .map(function (r) { return { gid: r.gid, name: r.name }; });

// ---------- 2) 燕尾槽父子：mount -> children ----------
for (const gid of Object.keys(gunslots)) {
  const g = gunslots[gid];
  // 找出根级/机匣级 mount 且 allow 直接含 Scope
  const cands = [];
  (function walk(sl, pfx, parBase) {
    for (const s of sl) {
      const base = api.gwSidBase(s.sid);
      if (base === "mount") {
        const allow = s.allow || [];
        const hasScope = allow.some(function (a) { return (items[a] || {}).pt === "Scope"; });
        if (hasScope && (!parBase || /^(reciever|receiver|slide|frame|upper|lower)$/.test(parBase))) {
          cands.push({ path: pfx + s.sid, s: s });
        }
      }
      if (s.slots) { walk(s.slots, pfx + s.sid + "/", base); }
    }
  })(g.slots || [], "", "");
  if (!cands.length) { continue; }
  const b = build(gid, null, true);
  const cs = cellsOf(b.L);
  for (const cd of cands) {
    const my = cs.filter(function (c) { return c.path === cd.path; })[0];
    const kids = (cd.s.slots || []).map(function (k) { return cd.path + "/" + k.sid; });
    const kidCells = kids.map(function (k) {
      const kc = cs.filter(function (c) { return c.path === k; })[0];
      return { path: k, pos: kc ? ("r" + kc.row + "c" + kc.col) : "MISSING", role: kc ? kc.role : "" };
    });
    const nv = [];
    for (const k of kids) { if (!cs.some(function (c) { return c.path === k; })) { nv.push(k); } }
    out.dovetail.push({
      gid: gid, name: g.n, parent: cd.path,
      parentPos: my ? ("r" + my.row + "c" + my.col) : "MISSING",
      parentRole: my ? my.role : "",
      kids: kidCells
    });
  }
}

// ---------- 3) 第六行战术装置（有手动校准的）----------
for (const gid of Object.keys(calib.guns)) {
  const recs = calib.guns[gid].slots || {};
  const r6 = [];
  for (const k of Object.keys(recs)) {
    const s = recs[k];
    if (s.logicalRow === 6 && s.col >= 1 && s.col <= 4) {
      r6.push({ key: k, col: s.col, sid: s.slotId, role: s.role, source: s.source });
    }
  }
  r6.sort(function (a, b) { return a.col - b.col; });
  if (r6.length >= 2) {
    const b1 = build(gid, null, true);
    const cs = cellsOf(b1.L);
    const seen = {};
    const dup = [];
    for (const c of cs) { const k = c.row + "|" + c.col; if (seen[k]) { dup.push(k); } seen[k] = 1; }
    out.row6.push({
      gid: gid, name: calib.guns[gid].name,
      calib: r6,
      actual: r6.map(function (e) {
        // 按 slotPath 找（key 首段是 path）
        const p = (e.key.split("|")[0] || "");
        const c = cs.filter(function (x) { return x.path === p; })[0];
        return { key: e.key, want: "r6c" + e.col, got: c ? ("r" + c.row + "c" + c.col) : "MISSING" };
      }),
      dupCells: dup,
      topPad: b1.topPad
    });
  }
}

fs.mkdirSync(path.join(ROOT, "docs/r19.28"), { recursive: true });
fs.writeFileSync(path.join(ROOT, "docs/r19.28/probe-baseline.json"),
  JSON.stringify(out, null, 2), "utf8");

// ---------- 控制台摘要 ----------
console.log("=== 1) AK 系照门（结构签名命中 " + out.akFamily.length + " 把）===");
for (const r of out.rearSight) {
  if (!r.akFamily) { continue; }
  console.log(" " + r.name.padEnd(34) + " main=" + JSON.stringify(r.main) + " subs=" + JSON.stringify(r.subs) + " topPad=" + r.topPad);
}
console.log("\n=== 1b) 非 AK 系但含 TT01 的照门（应不受影响）===");
for (const r of out.rearSight) {
  if (r.akFamily) { continue; }
  if (r.name.indexOf("VPO") === 0) { console.log(" " + r.name.padEnd(34) + " main=" + JSON.stringify(r.main)); }
}
let nonAk6 = out.rearSight.filter(function (r) { return !r.akFamily && r.main.some(function (m) { return m.indexOf("r2c6") >= 0; }); });
console.log(" 非 AK 系落在 r2c6 的枪数：" + nonAk6.length);

console.log("\n=== 2) 燕尾槽父子（共 " + out.dovetail.length + " 组）===");
let bad = 0;
for (const d of out.dovetail) {
  const pr = d.parentPos;
  const kids = d.kids;
  const flag = kids.filter(function (k) {
    if (k.pos === "MISSING") { return true; }
    const kc = +k.pos.split("c")[1];
    const pc = +pr.split("c")[1];
    const kr = +k.pos.slice(1).split("c")[0];
    const prr = +pr.slice(1).split("c")[0];
    return !(kc === pc && kr < prr);
  });
  if (d.parentPos === "MISSING" || flag.length) { bad++; }
  console.log(" " + d.name.slice(0, 26).padEnd(28) + " P=" + pr.padEnd(7) +
    " K=" + kids.map(function (k) { return k.pos; }).join(",").padEnd(26) +
    (flag.length ? "  <== 非正上方: " + flag.map(function (f) { return f.path + "@" + f.pos; }).join(" ") : ""));
}
console.log(" 未满足「子槽在父正上方」的组数：" + bad);

console.log("\n=== 3) 第六行战术装置（>=2，手动校准）共 " + out.row6.length + " 把 ===");
for (const r of out.row6) {
  console.log(" " + r.name.slice(0, 28).padEnd(30) + " " +
    r.actual.map(function (a) { return a.key.split("|")[0].split("/").pop() + " " + a.want + "->" + a.got; }).join(" | "));
}
console.log("\n输出：docs/r19.28/probe-baseline.json");
