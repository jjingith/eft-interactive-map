# -*- coding: utf-8 -*-
"""R19.3：用 EFTForge 黄金向量 + 373 条官方预设验证新公式。"""
import json, os, subprocess, sys, statistics

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HARNESS = os.path.join(ROOT, "tests", "js", "_verify_forge_tmp.js")

HARNESS_SRC = r"""
const fs = require('fs');
const GB = require(process.argv[2]);
const items = JSON.parse(fs.readFileSync(process.argv[3], 'utf8')).items;
const stats = JSON.parse(fs.readFileSync(process.argv[4], 'utf8'));
const gp = JSON.parse(fs.readFileSync(process.argv[5], 'utf8'));
const golden = JSON.parse(fs.readFileSync(process.argv[6], 'utf8'))["cases"];
const ctx = GB.context(items, stats);

// ---- 1) 黄金向量 ----
let gFail = 0, gPass = 0;
for (const c of golden) {
  // 独立重算（与 gun_builder 同公式）
  const eff = Math.max(0, c.total_ergo * (1 + c.equip_ergo_modifier));
  const effC = Math.min(Math.max(eff, 0), 100);
  const need = c.total_weight <= 3 ? 0 : 100 * (1 - 3 / c.total_weight);
  const ted = effC - need;
  const sway = Math.min(Math.max((c.total_weight * (1 - effC / 100) - 3) / 4, 0), 1);
  const ew = c.total_weight * (1 - Math.sqrt(Math.max(0, eff)) / 25);
  const drain = Math.sqrt(Math.max(ew, 0)) * 1.1 * (1 - c.strength_level * 0.004);
  const arm = drain > 0 ? 80 / drain : null;
  const ok = Math.abs(ted - c.expected_true_ergo_delta) < 0.01
    && ((ted < 0) === c.expected_overswing)
    && Math.round(sway * 1000) / 10 === c.expected_aim_sway
    && (arm === null ? c.expected_arm_stamina === null : Math.abs(Math.round(arm * 100) / 100 - c.expected_arm_stamina) < 0.011);
  if (ok) gPass++; else { gFail++; console.log('GOLDEN FAIL', JSON.stringify(c), 'got', {ted, sway, arm}); }
}

// ---- 2) 373 预设回归：ergo / rv / rh / moa ----
const rows = [];
for (const pid in gp.presets) {
  const pr = gp.presets[pid];
  if (!pr.g || !gp.presets.hasOwnProperty(pid)) continue;
  const st = GB.compute(ctx, pr.g, pr.i || {}, { assumeFullMag: false });
  rows.push({
    n: pr.n, ergo: [st.fields.ergonomics.v, pr.e],
    rv: [st.fields.recoilV.v, pr.rv], rh: [st.fields.recoilH.v, pr.rh],
    moa: [st.fields.accuracy.v, pr.moa]
  });
}
function dist(key) {
  const d = rows.filter(r => r[key][0] !== null && r[key][1] !== null).map(r => r[key][0] - r[key][1]);
  const abs = d.map(Math.abs).sort((a, b) => a - b);
  const mean = d.reduce((a, b) => a + b, 0) / (d.length || 1);
  return { n: d.length, mean: +mean.toFixed(3), med: +(abs[Math.floor(abs.length / 2)] || 0).toFixed(3),
           p95: +(abs[Math.floor(abs.length * 0.95)] || 0).toFixed(3), max: +(abs[abs.length - 1] || 0).toFixed(3) };
}
// MOA 独立重算（含枪管 COI 覆盖规则）—— 用引擎值与真值对比已在 dist 里
console.log(JSON.stringify({ golden: { pass: gPass, fail: gFail },
  ergo: dist('ergo'), rv: dist('rv'), rh: dist('rh'), moa: dist('moa') }));
"""
with open(HARNESS, "w", encoding="utf-8") as f:
    f.write(HARNESS_SRC)
try:
    proc = subprocess.run(
        ["node", HARNESS,
         os.path.join(ROOT, "gun_builder.js"),
         os.path.join(ROOT, "data", "items.json"),
         os.path.join(ROOT, "data", "gun-stats.json"),
         os.path.join(ROOT, "data", "gun-presets.json"),
         os.path.join(ROOT, "build-cache", "r193-eftforge", "stat_formula_golden.json")],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    print(proc.stdout[-1500:] or proc.stderr[-1500:])
finally:
    os.remove(HARNESS)
