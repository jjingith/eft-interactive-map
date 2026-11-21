/* EFT 互动地图 · 配枪计算引擎（R19，独立纯函数模块，零 DOM 依赖）
 *
 * 为什么单独一个文件
 * ------------------
 * `app.js` 已经 1.2 万行且是单个 IIFE，把「属性公式 / 兼容图 / 预设序列化 / 优化器」
 * 塞进去既难单测也容易碰坏既有功能。这里只放**纯计算**，UI 仍在 app.js 里调用。
 * 与 `combat_sim.js` 同样的约定：浏览器挂 `window.GB`，Node 里 `module.exports`。
 *
 * 数据来源与可信度
 * ----------------
 * · `data/items.json`   —— 本地快照：名称、价格、重量、槽位 allow、互斥 conflict、
 *                          人机工效修正 mod.e、后坐力百分比 mod.r、弹匣容量 cap
 * · `data/gun-stats.json` —— 构建期从 tarkov.dev 公开数据集提取（见 tools/build_gun_stats.py）：
 *                          枪械基础 rv/rh/coi/rpm/sr/v0，配件 rm/am/v0
 * 每个属性都带 `conf`：
 *   verified  —— 字段直接对应游戏内数值，公式为加法或百分比乘算，社区一致
 *   estimated —— 公式形式已知但某一环节（换算/单位）未核实
 *   missing   —— 数据缺失，返回 null，**绝不填 0**
 */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) { module.exports = api; }
  if (root) { root.GB = api; }
}(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var CONF = { V: "verified", E: "estimated", M: "missing" };

  function num(v) { return (typeof v === "number" && isFinite(v)) ? v : null; }
  function r2(v) { return v === null ? null : Math.round(v * 100) / 100; }
  function r1(v) { return v === null ? null : Math.round(v * 10) / 10; }
  function r3(v) { return v === null ? null : Math.round(v * 1000) / 1000; }
  function ergoV0(out) { return out.fields.ergonomics && out.fields.ergonomics.v !== null; }

  // ---------------------------------------------------------------- 上下文
  /** 一次计算需要的全部数据。调用方只构造一次，之后复用（避免每帧重建索引）。 */
  function context(items, stats) {
    var byId = items || {};
    var gs = stats || { guns: {}, mods: {} };
    var guns = gs.guns || {};
    var mods = gs.mods || {};
    return {
      item: function (id) { return id ? byId[id] || null : null; },
      gunStat: function (id) { return id ? guns[id] || null : null; },
      modStat: function (id) { return id ? mods[id] || null : null; },
      mods: mods,
      statsMeta: gs
    };
  }

  /** 已安装清单：path -> itemId（保持路径，用于父子关系与定位） */
  function installedList(installed) {
    var out = [];
    for (var path in (installed || {})) {
      if (installed[path]) { out.push({ path: path, id: installed[path] }); }
    }
    return out;
  }

  // ---------------------------------------------------------------- 槽位树
  /**
   * 递归展开槽位树。与 app.js 的 addGunSlots 同构，但**不写进 state**：
   * 传进来的 installed 决定要展开哪些子槽（装了护木才有护木上的导轨槽）。
   * 返回 { nodes: {path: node}, order: [path...], depthOf: {path: n} }
   */
  function buildTree(ctx, gunId, installed) {
    var tree = { nodes: {}, order: [], depthOf: {} };
    var gun = ctx.item(gunId);
    if (!gun) { return tree; }
    var seen = {};       // 防循环引用（上游数据异常时不至于栈溢出）
    function walk(rec, prefix, parentPath, depth) {
      if (!rec || seen[prefix + "|" + (rec.n || "")] > 3) { return; }
      seen[prefix + "|" + (rec.n || "")] = (seen[prefix + "|" + (rec.n || "")] || 0) + 1;
      var slots = rec.slots || [];
      var used = {};
      for (var i = 0; i < slots.length; i++) {
        var slot = slots[i] || {};
        var sid = slot.sid || slot.id || ("s" + i);
        var n = used[sid] === undefined ? 0 : used[sid] + 1;
        used[sid] = n;
        if (n > 0) { sid = sid + "#" + n; }
        var path = prefix ? (prefix + "/" + sid) : sid;
        var node = {
          path: path, sid: sid, label: slot.label || slot.sid || sid,
          raw: slot, allow: (slot.allow || []).slice(),
          parent: parentPath, children: [], depth: depth,
          required: !!slot.required
        };
        tree.nodes[path] = node;
        tree.order.push(path);
        tree.depthOf[path] = depth;
        if (parentPath && tree.nodes[parentPath]) { tree.nodes[parentPath].children.push(path); }
        var childId = installed && installed[path];
        if (childId) { walk(ctx.item(childId), path, path, depth + 1); }
      }
    }
    walk(gun, "", null, 0);
    // 枪械本体也算一层（槽位从 depth 0 起算，父件子槽从 depth 1 起）
    return tree;
  }

  // ---------------------------------------------------------------- 互斥（R19.12）
  /**
   * 上游 conflictingItems 的规范化读取。
   * items.json 的 `conflict` 只保证「这一方声明了」，**不保证双向**——
   * 实测 Hera 一体化枪托声明了 57 件互斥品，但那些枪托的 conflict 里没有它。
   * 所以任何判定都必须两个方向都查，不能只看当前物品的列表。
   */
  function conflictSet(ctx, id) {
    var rec = ctx.item(id);
    var out = {};
    ((rec && rec.conflict) || []).forEach(function (x) { if (x) { out[x] = 1; } });
    return out;
  }

  /** 两件配件是否互斥（任一方向声明即算） */
  function conflictsWith(ctx, idA, idB) {
    if (!idA || !idB || idA === idB) { return false; }
    if (conflictSet(ctx, idA)[idB]) { return true; }
    return !!conflictSet(ctx, idB)[idA];
  }

  /**
   * 整套装配的互斥对。逐对比较**所有已装件**（不只看正在选的那个槽位），
   * 因此能抓到「分别都能装、装到一起不行」的组合（例如一体化枪托 + 独立枪托、
   * 照门 + 瞄准镜、短枪管 + 不匹配护木）。按路径排序保证结果稳定。
   */
  function conflictPairs(ctx, installed) {
    var ents = installedList(installed).sort(function (a, b) { return a.path < b.path ? -1 : (a.path > b.path ? 1 : 0); });
    var sets = {};
    ents.forEach(function (e) { sets[e.id] = conflictSet(ctx, e.id); });
    var out = [];
    for (var i = 0; i < ents.length; i++) {
      for (var j = i + 1; j < ents.length; j++) {
        var a = ents[i], b = ents[j];
        var ab = !!sets[a.id][b.id], ba = !!sets[b.id][a.id];
        if (!ab && !ba) { continue; }
        out.push({
          a: a.id, b: b.id, pathA: a.path, pathB: b.path,
          dirAtoB: ab, dirBtoA: ba,
          nameA: nameOfItem(ctx, a.id), nameB: nameOfItem(ctx, b.id)
        });
      }
    }
    return out;
  }

  /** 某个槽位的候选配件：allow 里排除「已被别的槽位占用」与「互斥」的项 */
  function candidates(ctx, gunId, installed, path) {
    var tree = buildTree(ctx, gunId, installed);
    var node = tree.nodes[path];
    if (!node) { return { node: null, rows: [], reason: "槽位不存在" }; }
    var used = {};
    installedList(installed).forEach(function (e) { if (e.path !== path) { used[e.id] = e.path; } });
    var rows = [];
    for (var i = 0; i < node.allow.length; i++) {
      var id = node.allow[i];
      var rec = ctx.item(id);
      if (!rec) { continue; }
      var why = "";
      if (used[id]) { why = "同一配件已装在「" + used[id] + "」"; }
      else {
        // R19.12：与**任何**已装件互斥（双向）都不能算候选，和右栏候选表同一套结论
        var ents = installedList(installed);
        for (var ei = 0; ei < ents.length; ei++) {
          if (ents[ei].path === path) { continue; }
          if (conflictsWith(ctx, id, ents[ei].id)) {
            why = "与已装的「" + nameOfItem(ctx, ents[ei].id) + "」互斥（上游 conflictingItems）";
            break;
          }
        }
      }
      // 纯外观件（没有属性也没有子槽）同样允许装，只是没有增益——不需要额外分支。
      rows.push({
        id: id, n: rec.n || id, pt: rec.pt || "",
        w: num(rec.w), price: priceOf(ctx, rec),
        ergo: pickE(ctx, id), recoilPct: pickRm(ctx, id), accMod: pickAm(ctx, id),
        velPct: pickV0(ctx, id),
        slots: (rec.slots || []).length,
        installed: (installed && installed[path]) === id,
        blocked: !!why, blockedWhy: why
      });
    }
    return { node: node, rows: rows, reason: "" };
  }

  // ---------------------------------------------------------------- 单件属性
  function pickE(ctx, id) {
    var ms = ctx.modStat(id);
    if (ms && num(ms.e) !== null) { return ms.e; }
    var rec = ctx.item(id);
    return rec && rec.mod && num(rec.mod.e) !== null ? rec.mod.e : null;
  }
  function pickRm(ctx, id) {
    var ms = ctx.modStat(id);
    if (ms && num(ms.rm) !== null) { return ms.rm; }
    var rec = ctx.item(id);
    return rec && rec.mod && num(rec.mod.r) !== null ? rec.mod.r : null;
  }
  function pickAm(ctx, id) {
    var ms = ctx.modStat(id);
    return ms && num(ms.am) !== null ? ms.am : null;
  }
  function pickV0(ctx, id) {
    var ms = ctx.modStat(id);
    if (ms && num(ms.v0) !== null) { return ms.v0; }
    return null;
  }

  /** ADS 时间拟合式（社区拟合；EFTForge 未实现、官方公式不可得）：
   *  2.35 − 0.028 × 总人机工效，下限 0.2s。人机越高开镜越快。
   *  这是唯一实现处——compute 与 app.js 的「技能后重算」都调它，避免两套公式漂移。
   *  非数字 / NaN / Infinity 返回 null（按缺失处理，不伪造 0 或无穷）。 */
  function adsTimeFromErgo(ergo) {
    if (typeof ergo !== "number" || !isFinite(ergo)) { return null; }
    return Math.max(0.2, r2(2.35 - 0.028 * ergo));
  }
  function priceOf(ctx, rec) {
    if (!rec) { return null; }
    if (rec.p) {
      if (num(rec.p.a) !== null) { return rec.p.a; }        // 跳蚤 24h 均价
      if (num(rec.p.b) !== null) { return rec.p.b; }        // 基础参考价
    }
    if (num(rec.price) !== null) { return rec.price; }
    return null;
  }

  // ---------------------------------------------------------------- 整枪属性
  /**
   * 计算整枪属性。返回每个字段一个对象 {v, conf, why}，缺失时 v=null。
   *
   * 公式（详见 docs/r19-gun-builder/stats-calculation.md）：
   *   ergonomics = 枪械基础 e + Σ配件 e            —— verified（加法，EFT 机制）
   *   recoilV/H  = 基础 * (1 + Σ配件 rm)           —— verified（百分比累加后乘一次）
   *   weight     = 枪械 w + Σ配件 w                —— verified
   *   accuracy   = 枪械 coi + Σ配件 am             —— estimated（coi 单位/换算未核实，展示原始角值）
   *   fireRate   = 枪械 rpm                        —— verified（配件不改射速）
   *   sighting   = 枪械 sr + 瞄具 sr（取最大）      —— verified
   *   magCap     = 已装弹匣的 cap                   —— verified
   *   velocity   = 弹药初速 * (1 + (枪械 v0 + Σ配件 v0)/100) —— estimated（需选中弹药）
   */
  function compute(ctx, gunId, installed, opts) {
    opts = opts || {};
    var gun = ctx.item(gunId);
    var gs = ctx.gunStat(gunId) || {};
    var parts = installedList(installed);
    var out = { gunId: gunId, parts: parts.length, fields: {}, missing: [] };

    var ergoSum = null, rmSum = 0, amSum = 0, wSum = 0, v0Pct = null;
    var srMax = null, magCap = null, hasRm = false, hasAm = false, weightKnown = true;

    parts.forEach(function (e) {
      var rec = ctx.item(e.id);
      if (!rec) { return; }
      var w = num(rec.w);
      if (w === null) { weightKnown = false; } else { wSum += w; }
      var ev = pickE(ctx, e.id);
      if (ev !== null) { ergoSum = (ergoSum === null ? 0 : ergoSum) + ev; }
      var rm = pickRm(ctx, e.id);
      if (rm !== null) { rmSum += rm; hasRm = true; }
      var am = pickAm(ctx, e.id);
      if (am !== null) { amSum += am; hasAm = true; }
      var vp = pickV0(ctx, e.id);
      if (vp !== null) { v0Pct = (v0Pct === null ? 0 : v0Pct) + vp; }
      if (num(rec.cap) !== null) { magCap = Math.max(magCap || 0, rec.cap); }
      var rsr = num(rec.sr);
      if (rsr !== null) { srMax = Math.max(srMax || 0, rsr); }
    });

    var baseE = num(gs.e);
    var baseW = gun ? num(gun.w) : null;
    if (baseW !== null) { wSum += baseW; }

    // 人机工效
    var ergo = (baseE === null) ? null : baseE + (ergoSum || 0);
    out.fields.ergonomics = {
      label: "人机工效", v: r1(ergo),
      conf: baseE === null ? CONF.M : CONF.V,
      why: baseE === null ? "缺少枪械基础人机工效" : "基础 " + baseE + " + 配件 " + r1(ergoSum || 0)
    };

    // 后坐力（百分比累加后乘一次；缺少基础值或没有任何修正时按基础算）
    var baseRv = num(gs.rv), baseRh = num(gs.rh);
    var mul = 1 + rmSum;
    out.fields.recoilV = {
      label: "垂直后坐力", v: baseRv === null ? null : r1(baseRv * mul),
      conf: baseRv === null ? CONF.M : CONF.V,
      why: baseRv === null ? "缺少枪械基础后坐力"
        : "基础 " + baseRv + " × (1 " + (rmSum >= 0 ? "+" : "-") + Math.abs(r1(rmSum * 100)) + "%)"
    };
    out.fields.recoilH = {
      label: "水平后坐力", v: baseRh === null ? null : r1(baseRh * mul),
      conf: baseRh === null ? CONF.M : CONF.V,
      why: baseRh === null ? "缺少枪械基础后坐力" : "基础 " + baseRh + " × 同一修正系数"
    };

    // 重量
    out.fields.weight = {
      label: "重量", v: weightKnown ? r2(wSum) : null,
      conf: weightKnown ? CONF.V : CONF.M,
      why: weightKnown ? "枪械 + 已装配件逐项累加" : "有配件缺重量字段"
    };

    // 精度：只给出上游 centerOfImpact 的原值。
    // 用 373 个真实预设反证过：`coi + Σ accuracyModifier` 与游戏内 MOA 的中位误差 2.5、
    // 最大 42，且 moa/(coi*60) 的比值在 0.571~39.55 之间浮动 —— 说明还依赖
    // deviationCurve / devMax 等未公开的项，无法可靠换算。按任务要求不伪造，
    // 所以这里只展示「散布角」原值（越小越准），配件的精度修正单独列出不做合成。
    var coi = num(gs.coi);
    out.fields.accuracy = {
      label: "散布角", v: coi === null ? null : r3(coi), unit: "度",
      conf: coi === null ? CONF.M : CONF.V,
      why: coi === null ? "缺少枪械 centerOfImpact"
        : ("上游 centerOfImpact 原值；配件 accuracyModifier 合计 " + r3(hasAm ? amSum : 0) +
           "，其与游戏内 MOA 的换算未确认，不做合成")
    };

    // 射速
    out.fields.fireRate = {
      label: "射速", v: num(gs.rpm), conf: num(gs.rpm) === null ? CONF.M : CONF.V,
      why: num(gs.rpm) === null ? "缺少 fireRate" : "枪械固有，配件不改变射速"
    };

    // 瞄准距离
    var baseSr = num(gs.sr);
    var sr = baseSr === null ? srMax : Math.max(baseSr, srMax || 0);
    out.fields.sightingRange = {
      label: "瞄准距离", v: sr, conf: sr === null ? CONF.M : CONF.V,
      why: sr === null ? "缺少 sightingRange" : "枪械基础与瞄具取较大值"
    };

    // 弹匣容量
    out.fields.magCapacity = {
      label: "弹匣容量", v: magCap, conf: magCap === null ? CONF.M : CONF.V,
      why: magCap === null ? "当前没有安装弹匣（或弹匣缺 cap 字段）" : "取已装弹匣的 capacity"
    };

    // 初速（依赖弹药）
    var ammo = opts.ammo || null;
    if (ammo && num(ammo.v0) !== null) {
      var gunPct = num(gs.v0) === null ? 0 : gs.v0;
      var total = gunPct + (v0Pct || 0);
      out.fields.velocity = {
        label: "初速", v: Math.round(ammo.v0 * (1 + total / 100)),
        conf: CONF.E, ammoId: ammo.id || null,
        why: "弹药 " + ammo.v0 + " m/s × (1 + 枪械/配件 " + r1(total) + "%)；枪械 velocity 字段单位按百分比解释"
      };
    } else {
      out.fields.velocity = {
        label: "初速", v: null, conf: CONF.M,
        why: "需要先选中弹药（配枪页与弹药库联动）"
      };
    }

    // ============================================================ R19.3 瞄准类隐藏属性
    // 公式来源：EFTForge（github.com/SouthHorizons76/EFTForge，AGPL-3.0-or-later）
    //   backend/stats.py::_compute_stats / _calc_aiming_stats 与
    //   frontend/modules/calculations.js（两边由 stat_formula_golden.json 黄金向量锁定一致）。
    // 该项目自述"Every formula here reproduces the game exactly"（复现游戏内计算），
    // 并给出 11 组黄金测试向量；本实现为**独立重写**（公式本身不受版权保护，
    // 未复制其代码），并用同一组黄金向量 + 373 条官方预设做了回归验证。
    // 输入：
    //   opts.strengthLevel       —— 玩家力量技能等级（0~51，EFTForge 默认 10）
    //   opts.equipErgoModifier   —— 装备人机修正 b（头盔/护甲等，十进制小数，默认 0）
    //   opts.assumeFullMag       —— 满弹匣重量计入（默认 true，需已选弹药）
    // 公式（符号与 stats.py 一致）：
    //   effErgo      = max(0, ergo × (1 + b))
    //   ergoNeeded   = W ≤ 3 ? 0 : 100 × (1 − 3/W)
    //   TrueErgoDelta= min(max(eff,0),100) − ergoNeeded            （负 = 已过摆）
    //   overswing    = TED < 0
    //   aimSway      = clamp((W×(1−clamp(eff,0,100)/100) − 3) / (7−3), 0, 1) × 100%
    //   armStamina   = 80 / ( √(max(W×(1−√eff/25),0)) × 1.1 × (1 − str×0.004) ) 秒
    //   MOA          = (100/2.9089) × coi × (1 − ΣaccuracyModifier/100) × 弹药系数
    //     其中 coi = 已装枪管的 centerOfImpact（覆盖枪械基础值，EFTForge 同规则）；
    //     弹药系数：acc ≤ 0 → (100+|acc|)/100，acc > 0 → 100/(100+acc)
    var STR = (opts.strengthLevel === undefined || opts.strengthLevel === null)
      ? 10 : Math.max(0, num(opts.strengthLevel) || 0);
    var B = (opts.equipErgoModifier === undefined || opts.equipErgoModifier === null)
      ? 0 : (num(opts.equipErgoModifier) || 0);
    var fullMag = opts.assumeFullMag !== false;

    var ergoNow = out.fields.ergonomics.v;
    var wNow = wSum;
    var magCapNow = magCap;
    var ammoW = 0;
    if (fullMag && ammo && num(ammo.w) !== null && magCapNow) {
      ammoW = ammo.w * magCapNow;
      wNow = wNow + ammoW;
    }
    var effErgo = ergoNow === null ? null : Math.max(0, ergoNow * (1 + B));
    var effClamped = effErgo === null ? 0 : Math.min(Math.max(effErgo, 0), 100);
    var ergoNeeded = (wNow <= 3) ? 0 : 100 * (1 - 3 / wNow);
    var ted = effErgo === null ? null : effClamped - ergoNeeded;
    var sway = Math.min(Math.max((wNow * (1 - effClamped / 100) - 3) / 4, 0), 1);
    var ergoWeight = (effErgo === null) ? null
      : wNow * (1 - Math.sqrt(Math.max(0, effErgo)) / 25);
    var drain = (ergoWeight === null) ? null
      : Math.sqrt(Math.max(ergoWeight, 0)) * 1.1 * (1 - STR * 0.004);
    var armSec = (drain !== null && drain > 0) ? 80 / drain : null;

    out.fields.trueErgoDelta = {
      label: "TrueErgoDelta", v: ted === null ? null : r2(ted),
      conf: ted === null ? CONF.M : CONF.V,
      why: "EFTForge 游戏内公式：有效人机(" + (effErgo === null ? "—" : r1(effErgo)) +
           ") − 该重量不超摆所需人机(" + r1(ergoNeeded) + ")；负值 = 已会过摆。"
           + "黄金向量 + 373 预设回归验证"
    };
    out.fields.overSwing = {
      label: "OverSwing", v: ted === null ? null : (ted < 0 ? "是" : "否"),
      conf: ted === null ? CONF.M : CONF.V,
      why: "过摆判定 = TrueErgoDelta < 0；摆动强度 " + Math.round(sway * 100) +
           "%（有效重量 W×(1−eff/100) 超过 3kg 开始，7kg 达到满幅）"
    };
    out.fields.aimSway = {
      label: "Aim Sway 摆动强度", v: Math.round(sway * 1000) / 10, unit: "%",
      conf: CONF.V,
      why: "EFTForge：clamp((W×(1−eff/100) − 3kg) / 4kg, 0, 1)"
    };
    out.fields.armStamina = {
      label: "ArmStamina", v: armSec === null ? null : r1(armSec), unit: "s",
      conf: armSec === null ? CONF.M : CONF.V,
      why: "80 点池 ÷ (√(W×(1−√eff/25)) × 1.1 × (1 − 力量" + STR + "级×0.004))；" +
           "假设：站立、满水分、力量等级 " + STR + "（EFTForge 默认，可在 FORGE 面板调整）"
    };

    // MOA：枪管 COI 覆盖基础值（EFTForge 同规则），精度百分比修正、弹药精度系数
    var barrelCoi = null;
    parts.forEach(function (e) {
      var m = ctx.mods ? ctx.mods[e.id] : null;
      if (m && typeof m.coi === "number") { barrelCoi = m.coi; }
    });
    var coiBase = (barrelCoi !== null) ? barrelCoi : coi;
    var accFactor = 1;
    if (ammo && typeof ammo.acc === "number" && ammo.acc !== 0) {
      accFactor = ammo.acc <= 0 ? (100 + Math.abs(ammo.acc)) / 100 : 100 / (100 + ammo.acc);
    }
    if (coiBase !== null) {
      var moaV = (100 / 2.9089) * coiBase * (1 - (hasAm ? amSum : 0) / 100) * accFactor;
      out.fields.accuracy = {
        label: "精度 MOA", v: Math.round(moaV * 100) / 100, unit: "MOA",
        conf: CONF.V,
        why: "EFTForge：100/2.9089 × COI(" + coiBase + (barrelCoi !== null ? "，枪管覆盖" : "，枪械基础") +
             ") × (1 − 精度修正" + r3(hasAm ? amSum : 0) + "%) × 弹药系数(" + r3(accFactor) + ")" +
             (ammo ? "" : "；未选弹药，弹药精度系数按 1")
      };
    }

    // ADS 时间：EFTForge 没有实现该指标（检索其 stats.py / calculations.js / stats-panel.js
    // 均无 aiming time），db4tarkov 标注 (beta) 的公式也未公开。保留社区拟合式作为估算，
    // 与 R19.2 相同，但说明检索结论。
    if (ergoV0(out)) {
      var ergoAds = out.fields.ergonomics.v;
      out.fields.adsTime = {
        label: "ADS 时间", v: adsTimeFromErgo(ergoAds), unit: "s",
        conf: CONF.E,
        why: "社区拟合式 2.35 − 0.028 × 人机（db4 AK-74 预设单点校验 0.460 vs 0.465s）。" +
             "EFTForge 未实现 ADS、官方客户端公式不可得——仅作参考估算"
      };
    } else {
      out.fields.adsTime = { label: "ADS 时间", v: null, conf: CONF.M, why: "人机工效缺失" };
    }

    // 爆头有效距离：几何推导（同 R19.2），假设头宽 16cm、满散布锥
    var coiEff = (coiBase !== null) ? coiBase + (hasAm ? amSum : 0) : null;
    if (coiEff !== null && coiEff > 0.0005) {
      out.fields.headshotRange = {
        label: "爆头有效距离", v: Math.round(0.08 / Math.tan(coiEff * Math.PI / 180)), unit: "m",
        conf: CONF.E,
        why: "0.08m(头部半径) / tan(散布角 " + r3(coiEff) + "°)；几何推导估算，非游戏命中概率模型"
      };
    } else {
      out.fields.headshotRange = { label: "爆头有效距离", v: null, conf: CONF.M,
                                   why: "缺 centerOfImpact（或散布角过小）" };
    }

    // 上游原始隐藏值：直接展示（verified）
    if (num(gs.cam) !== null) {
      out.fields.cameraSnap = { label: "相机后坐", v: r2(gs.cam), conf: CONF.V,
                                why: "上游 cameraSnap 原值（开镜镜头偏移强度）" };
    }
    if (num(gs.devMax) !== null) {
      out.fields.devMax = { label: "散布偏差上限", v: num(gs.devMax), conf: CONF.V,
                            why: "上游 deviationMax 原值" };
    }
    if (num(gs.disp) !== null) {
      out.fields.dispersion = { label: "后坐散布", v: num(gs.disp), conf: CONF.V,
                                why: "上游 recoilDispersion 原值" };
    }
    if (num(gs.ra) !== null) {
      out.fields.recoilAngle = { label: "后坐角", v: num(gs.ra), conf: CONF.V,
                                 why: "上游 recoilAngle 原值" };
    }

    Object.keys(out.fields).forEach(function (k) {
      if (out.fields[k].v === null) { out.missing.push(k); }
    });
    return out;
  }

  // ---------------------------------------------------------------- 成本
  /**
   * 成本明细。规则（可在 UI 里切换）：
   *   includeStock = true  —— 计入全部已安装件（含原厂默认件），得到"整枪落地价"
   *   includeStock = false —— 只计"改装件"（默认装配之外换上去的），得到"改装花费"
   * 两种规则都逐项列出，界面上明确写出当前用的是哪一种。
   * 缺价格的配件计入 missingPrice 列表，**不按 0 元**混进总价。
   */
  function cost(ctx, gunId, installed, opts) {
    opts = opts || {};
    var includeStock = opts.includeStock !== false;
    // 2026-11：价格口径统一到市场页（最新 / 24h / 7d），由调用方传入取价函数；
    // 未传时保持旧行为（逐项 24h 均价）。
    var priceFn = (typeof opts.priceOf === "function") ? opts.priceOf : function (rec) { return priceOf(ctx, rec); };
    var gun = ctx.item(gunId);
    var rows = [];
    var total = 0, missing = 0;
    if (gun) {
      var gp = priceFn(gun);
      if (gp === null) { missing++; }
      else if (includeStock) { total += gp; }
      rows.push({ id: gunId, n: gun.n, role: "枪械本体", price: gp, stock: true });
    }
    installedList(installed).forEach(function (e) {
      var rec = ctx.item(e.id);
      if (!rec) { return; }
      var p = priceFn(rec);
      var isStock = !!opts.stockIds && !!opts.stockIds[e.id];
      if (p === null) { missing++; }
      else if (includeStock || !isStock) { total += p; }
      rows.push({ id: e.id, path: e.path, n: rec.n, role: "配件",
                  price: p, stock: isStock });
    });
    return { total: missing && total === 0 ? null : Math.round(total),
             rows: rows, missingPrice: missing, includeStock: includeStock };
  }

  // ---------------------------------------------------------------- 校验
  /**
   * 校验一套装配是否全部合法（导入预设时必须过这一关）：
   *   · 枪械 id 存在
   *   · 每个配件都在对应槽位的 allow 里
   *   · 父子路径存在（父件没装时子槽不该有配件）
   *   · 同一配件不重复占用
   * 返回 { ok, errors: [{path, id, why}] }
   */
  function validate(ctx, gunId, installed) {
    var tree = buildTree(ctx, gunId, installed);
    var errors = [];
    if (!ctx.item(gunId)) { errors.push({ path: "", id: gunId, why: "物品库里没有这把枪" }); }
    var used = {};
    var duplicates = [];
    installedList(installed).forEach(function (e) {
      var node = tree.nodes[e.path];
      if (!node) {
        errors.push({ path: e.path, id: e.id, why: "槽位不存在（父件可能已更换）" });
        return;
      }
      if (node.allow.indexOf(e.id) < 0) {
        errors.push({ path: e.path, id: e.id, why: "不在该槽位的合法配件列表里" });
      }
      // 同一型号配件装在多个槽位是**合法**的（等于买两件）：
      // data/gun-presets.json 里 32 条官方预设就是两个相同的导轨座 / 战术设备。
      // 这里只做记录，不判非法；成本按件数计。
      if (used[e.id]) { duplicates.push({ path: e.path, id: e.id, other: used[e.id] }); }
      else { used[e.id] = e.path; }
    });
    // R19.12：整套装配的互斥检查（上游 conflictingItems，双向）。同一对只报一次，
    // 归咎于路径排序靠后的那一件——sanitize 因此只掉一件，不会把两边都清掉。
    var pairs = conflictPairs(ctx, installed);
    var seenPair = {};
    pairs.forEach(function (p) {
      var key = p.a + "|" + p.b;
      if (seenPair[key]) { return; }
      seenPair[key] = 1;
      var blamePath = p.pathA < p.pathB ? p.pathB : p.pathA;
      errors.push({
        path: blamePath, id: (blamePath === p.pathA ? p.a : p.b), kind: "conflict",
        why: "与「" + (blamePath === p.pathA ? p.nameB : p.nameA) + "」互斥（上游 conflictingItems，" +
             (p.dirAtoB && p.dirBtoA ? "双向声明" : (p.dirAtoB ? "A 声明 B" : "B 声明 A")) + "）"
      });
    });
    return { ok: errors.length === 0, errors: errors, duplicates: duplicates,
             conflicts: pairs, tree: tree };
  }

  /** 清掉非法项（导入时用）：返回 { installed, dropped } */
  function sanitize(ctx, gunId, installed) {
    var cur = {};
    for (var k in (installed || {})) { if (installed[k]) { cur[k] = installed[k]; } }
    var dropped = [];
    for (var round = 0; round < 12; round++) {
      var v = validate(ctx, gunId, cur);
      if (v.ok) { break; }
      var changed = false;
      v.errors.forEach(function (e) {
        if (e.path && cur[e.path]) {
          dropped.push({ path: e.path, id: cur[e.path], why: e.why });
          delete cur[e.path];
          changed = true;
        }
      });
      if (!changed) { break; }
    }
    return { installed: cur, dropped: dropped };
  }

  // ---------------------------------------------------------------- 预设
  var PRESET_VERSION = 1;

  function serialize(gunId, installed, meta) {
    var slots = {};
    installedList(installed).sort(function (a, b) { return a.path < b.path ? -1 : 1; })
      .forEach(function (e) { slots[e.path] = e.id; });
    return {
      kind: "eftmap.gunbuild", version: PRESET_VERSION,
      gunId: gunId || "", slots: slots,
      name: (meta && meta.name) || "", savedAt: (meta && meta.savedAt) || "",
      note: (meta && meta.note) || ""
    };
  }

  /** 解析并规范化一份预设；结构不对直接抛错，交给调用方提示 */
  function parse(text) {
    var obj = (typeof text === "string") ? JSON.parse(text) : text;
    if (!obj || obj.kind !== "eftmap.gunbuild") { throw new Error("不是本项目的配枪预设（kind 不符）"); }
    if (!obj.gunId) { throw new Error("预设缺少 gunId"); }
    if (!obj.slots || typeof obj.slots !== "object") { throw new Error("预设缺少 slots"); }
    var slots = {};
    for (var k in obj.slots) {
      if (typeof obj.slots[k] === "string" && obj.slots[k]) { slots[k] = obj.slots[k]; }
    }
    return { gunId: obj.gunId, slots: slots, name: obj.name || "",
             version: obj.version || 0, savedAt: obj.savedAt || "" };
  }

  // ---------------------------------------------------------------- 组合
  /**
   * 从兼容图生成"安装链组合"，不写死任何一把枪的清单。
   * 做法：在树的每个末端槽位里找候选，再沿着 parent 链回溯，拼出
   *   枪械 -> 父件 -> ... -> 末端件
   * 的完整路径。用于「枪口组合」「瞄具+座+导轨」这类多级安装。
   */
  function chains(ctx, gunId, installed, opts) {
    opts = opts || {};
    var tree = buildTree(ctx, gunId, installed);
    var wantSid = opts.sidMatch ? new RegExp(opts.sidMatch) : null;
    var out = [];
    tree.order.forEach(function (path) {
      var node = tree.nodes[path];
      if (wantSid && !wantSid.test(node.sid)) { return; }
      var cand = candidates(ctx, gunId, installed, path);
      cand.rows.forEach(function (row) {
        if (row.blocked) { return; }
        var rec = ctx.item(row.id);
        var chain = [{ path: path, id: row.id, n: row.n }];
        // 若该配件自己还有子槽（例如瞄具座），把它的第一个可用子槽也算进链里
        if (rec && rec.slots && rec.slots.length) {
          var sub = installed || {};
          var subInstalled = {};
          for (var k in sub) { subInstalled[k] = sub[k]; }
          subInstalled[path] = row.id;
          var subTree = buildTree(ctx, gunId, subInstalled);
          var childPath = path + "/" + (rec.slots[0].sid || rec.slots[0].id);
          var childNode = subTree.nodes[childPath];
          if (childNode && childNode.allow.length) {
            var pc = candidates(ctx, gunId, subInstalled, childPath);
            var best = pc.rows.filter(function (r) { return !r.blocked; })[0];
            if (best) { chain.push({ path: childPath, id: best.id, n: best.n }); }
          }
        }
        out.push({ root: path, sid: node.sid, label: node.label,
                   chain: chain, ergo: row.ergo, recoilPct: row.recoilPct });
      });
    });
    return out;
  }

  // ---------------------------------------------------------------- 比较
  /** 两套装配的差异：逐字段列出 A / B / delta，缺失值保持 null（不填 0） */
  function compare(a, b) {
    var keys = ["ergonomics", "recoilV", "recoilH", "weight", "accuracy",
                "fireRate", "sightingRange", "magCapacity", "velocity"];
    var rows = [];
    keys.forEach(function (k) {
      var fa = a && a.fields && a.fields[k], fb = b && b.fields && b.fields[k];
      var va = fa ? fa.v : null, vb = fb ? fb.v : null;
      var delta = (va !== null && vb !== null) ? Math.round((vb - va) * 100) / 100 : null;
      rows.push({
        key: k, label: (fa && fa.label) || (fb && fb.label) || k,
        a: va, b: vb, delta: delta,
        better: betterOf(k, va, vb),
        confA: fa ? fa.conf : CONF.M, confB: fb ? fb.conf : CONF.M
      });
    });
    return rows;
  }
  /** 该字段"越小越好"还是"越大越好"；返回 "a" / "b" / ""（无法判断或相等） */
  function betterOf(key, a, b) {
    if (a === null || b === null || a === b) { return ""; }
    var lowerBetter = { recoilV: 1, recoilH: 1, weight: 1, accuracy: 1 };
    if (lowerBetter[key]) { return a < b ? "a" : "b"; }
    return a > b ? "a" : "b";
  }

  // ---------------------------------------------------------------- 优化器
  /**
   * 多目标装配搜索（贪心 + 局部改进 + 预算控制）。
   *
   * 目标（可加权）：低后坐力、高人机工效、低重量、低成本。
   * 约束：只在该槽位的 allow 里选（真实兼容），预算上限（可选），必装/禁装清单。
   *
   * 为什么不是穷举：一把枪的合法组合可达 10^8 量级，浏览器里必须限预算。
   * 算法：
   *   1. 从"当前装配"出发，逐槽位尝试替换成候选里得分最好的一个，接受有改善的改动；
   *   2. 反复 2~3 轮直到没有改善或达到评估预算；
   *   3. 用不同的权重组合跑多次，得到多个方案（Pareto 味道的候选集）。
   * 每次接受前都重新校验父子关系（装上新护木会让旧导轨失效，此时清掉子槽）。
   */
  // ---------------------------------------------------------------- 约束（R19.4）
  /**
   * FORGE 约束的**引擎端**实现（UI 与引擎共用同一套判断，不在两边各写一份）。
   *
   * constraints = {
   *   caps:     [10,30,...]   允许的弹匣容量集合（缺省/空 = 不约束）
   *   scope:    true          结果必须装有瞄具（判定：安装路径任一段 sid 含 scope）
   *   scopeId:  "itemId"      R19.8：必须安装的具体瞄具（按真实槽位兼容判定，允许自动补一级转接座）
   *   deviceIds: ["itemId",…] R19.9：必须安装的具体战术设备型号（手电 / 激光），逐件终检
   *   required: [itemId,...]  必须安装的配件
   *   excluded: [itemId,...]  禁止出现的配件（含其子槽）
   *   features: [{key,label,ids}]  R19.8：功能约束（手电 / 激光），ids 为该功能的真实设备集合，
   *                                 方案里至少要装其中一件；一件双功能设备可同时满足两组
   * }
   *
   * checkConstraints 做最终校验（方案应用前必须再跑一次）：
   *   - required 逐件找"允许它的树节点"，装不上 → 报冲突原因；
   *   - excluded 检查全部已装件（含递归子槽）；
   *   - caps 检查全部已装弹匣（有 cap 字段的件）；
   *   - scope 检查安装路径。
   * 返回 { ok, violations:[{kind, id, why}] }，ok=false 时调用方必须停止输出方案。
   */
  function checkConstraints(ctx, gunId, installed, cons) {
    cons = cons || {};
    var violations = [];
    var tree = buildTree(ctx, gunId, installed);
    var entries = installedList(installed);

    // R19.12：结构完整性与整套互斥属于**装配合法性**，和用户约束同级检查。
    // 以前这里只查 required/excluded/caps，于是「互斥的两件同时装着」的装配能拿到 ok=true。
    var v0 = validate(ctx, gunId, installed);
    v0.errors.forEach(function (e) {
      violations.push({ kind: e.kind || "structure", id: e.id || null, path: e.path || null,
                        why: (e.kind === "conflict" ? "装配冲突：" : "结构不合法：") + e.why });
    });

    // required：能在当前树的某个节点合法安装（或已经装着）
    (cons.required || []).forEach(function (id) {
      if (entries.some(function (e) { return e.id === id; })) { return; }
      var ok = tree.order.some(function (path) {
        return tree.nodes[path].allow.indexOf(id) >= 0;
      });
      if (!ok) {
        violations.push({ kind: "required", id: id,
          why: "「" + nameOfItem(ctx, id) + "」在当前枪械（含已装父件展开的槽位）里没有合法安装位置" });
      }
    });
    // excluded：全部已装件（含递归子槽）
    (cons.excluded || []).forEach(function (id) {
      var at = entries.filter(function (e) { return e.id === id; })
                      .map(function (e) { return e.path; });
      if (at.length) {
        violations.push({ kind: "excluded", id: id,
          why: "排除的「" + nameOfItem(ctx, id) + "」出现在方案里（" + at.join("、") + "）" });
      }
    });
    // caps：全部有 cap 的已装件
    if (cons.caps && cons.caps.length) {
      entries.forEach(function (e) {
        var rec = ctx.item(e.id);
        var cap = rec ? num(rec.cap) : null;
        if (cap !== null && cons.caps.indexOf(cap) < 0) {
          violations.push({ kind: "caps", id: e.id,
            why: "弹匣「" + nameOfItem(ctx, e.id) + "」容量 " + cap +
                 " 发不在允许集合 [" + cons.caps.join(",") + "]" });
        }
      });
    }
    // scope：安装路径任一段 sid 含 scope
    if (cons.scope) {
      var hasScope = entries.some(function (e) {
        return e.path.split("/").some(function (seg) { return /scope/i.test(seg); });
      });
      if (!hasScope) {
        violations.push({ kind: "scope", id: null,
          why: "方案里没有任何瞄具（当前枪械与已装父件下找不到可装的 mod_scope 槽位，或候选被排除）" });
      }
    }
    // scopeId（R19.8）：具体瞄具必须真的装在方案里，且与真实槽位兼容
    if (cons.scopeId) {
      var scopeAt = entries.filter(function (e) { return e.id === cons.scopeId; })
                           .map(function (e) { return e.path; });
      if (!scopeAt.length) {
        var scopeInstallable = tree.order.some(function (path) {
          return tree.nodes[path].allow.indexOf(cons.scopeId) >= 0;
        });
        violations.push({ kind: "scopeId", id: cons.scopeId,
          why: scopeInstallable
            ? "所选瞄具「" + nameOfItem(ctx, cons.scopeId) + "」没有装进方案"
            : "所选瞄具「" + nameOfItem(ctx, cons.scopeId) +
              "」与当前枪械的槽位不兼容（装配树里没有能直接安装它的槽位，也没有可用的转接座）" });
      }
    }
    // deviceIds（R19.9）：选定的具体战术设备型号必须真的装在方案里
    (cons.deviceIds || []).forEach(function (id) {
      if (!id) { return; }
      var at = entries.filter(function (e) { return e.id === id; })
                      .map(function (e) { return e.path; });
      if (at.length) { return; }
      var installable = tree.order.some(function (path) {
        return tree.nodes[path].allow.indexOf(id) >= 0;
      });
      violations.push({ kind: "deviceId", id: id,
        why: installable
          ? "所选战术设备「" + nameOfItem(ctx, id) + "」没有装进方案"
          : "所选战术设备「" + nameOfItem(ctx, id) + "」未装入方案：装配树里没有可安装它的槽位（可能被其它配件选择占用或被转接座替换）" });
    });

    // features（R19.8）：手电 / 激光等功能各自至少命中一件真实设备
    (cons.features || []).forEach(function (spec) {
      var ids = (spec && spec.ids) || [];
      if (!ids.length) { return; }
      var hit = entries.filter(function (e) { return ids.indexOf(e.id) >= 0; });
      if (hit.length) { return; }
      var label = (spec && spec.label) || (spec && spec.key) || "该功能";
      var anyInstallable = tree.order.some(function (path) {
        return tree.nodes[path].allow.some(function (id) { return ids.indexOf(id) >= 0; });
      });
      violations.push({ kind: "feature", id: (spec && spec.key) || null,
        why: anyInstallable
          ? "方案缺少具备" + label + "功能的战术设备（当前枪械有可安装设备，但方案里没有装上）"
          : "当前枪械没有兼容的" + label + "设备（真实槽位里找不到符合该功能的设备）" });
    });
    return { ok: violations.length === 0, violations: violations };
  }

  /**
   * R19.12：**最终整树校验** —— 优化器出方案、UI 应用方案、预设导入都用这一个口。
   *
   * 与 checkConstraints 的分工：
   *   · checkConstraints 回答「用户约束满足了吗」；
   *   · verifyBuild 回答「这套装配本身是真的吗」——槽位存在、allow 收录、
   *     父件在位、任意两件不互斥，且**方案声称装了的件真的还在**。
   *
   * expect: { ids: [itemId...], note } —— 调用方（优化器 / UI）声称会装的件。
   * 返回 { ok, problems, parts, conflicts, dropped? }；problems 里的 kind 取值：
   *   structure / conflict / required / excluded / caps / scope / scopeId /
   *   deviceId / feature / missing（声称装了但最终没有）
   */
  function verifyBuild(ctx, gunId, installed, cons, expect) {
    var problems = [];
    var chk = checkConstraints(ctx, gunId, installed, cons || {});
    (chk.violations || []).forEach(function (v) {
      problems.push({ kind: v.kind, id: v.id || null, path: v.path || null, why: v.why });
    });
    var have = {};
    installedList(installed).forEach(function (e) { have[e.id] = (have[e.id] || 0) + 1; });
    var missing = [];
    ((expect && expect.ids) || []).forEach(function (id) {
      if (!id) { return; }
      if (!have[id]) {
        missing.push(id);
        problems.push({ kind: "missing", id: id,
          why: "方案声称已装「" + nameOfItem(ctx, id) + "」，最终装配里没有它（可能被互斥/兼容清理掉了）" });
      }
    });
    var pairs = conflictPairs(ctx, installed);
    return {
      ok: problems.length === 0,
      problems: problems,
      parts: installedList(installed).length,
      conflicts: pairs,
      missing: missing,
      checkedAt: Date.now()
    };
  }

  /**
   * R19.8：把 targetId 装进 cur 的安装计划。
   * 先找能直接安装它的树节点；找不到时尝试"自动补一级转接座"——
   * 某个可装配件的子槽 allow 里含目标件时，先装该配件，再装到它新展开的子槽上。
   * 只补一级（真实的瞄具/战术设备链条上游最多就是"座 + 设备"两层），不递归造链。
   * 返回 { ok, steps:[{path,id}] }；ok=false 表示真实不兼容（由终检给出可读原因）。
   */
  function resolveInstall(ctx, gunId, cur, targetId, cons) {
    var tree = buildTree(ctx, gunId, cur);
    // R19.10：先找**空槽**（或已经装着同一件），再退到被占用的槽位。
    // 否则手电 + 激光同时必装时，第二件会把第一件（含其转接座）从槽里顶掉。
    var fits = tree.order.filter(function (p) {
      return tree.nodes[p].allow.indexOf(targetId) >= 0;
    });
    var direct = fits.filter(function (p) { return !cur[p] || cur[p] === targetId; })[0] || fits[0];
    if (direct) { return { ok: true, steps: [{ path: direct, id: targetId }] }; }
    for (var i = 0; i < tree.order.length; i++) {
      var p = tree.order[i];
      var rows = candidates(ctx, gunId, cur, p).rows;
      for (var j = 0; j < rows.length; j++) {
        var row = rows[j];
        if (row.blocked) { continue; }
        if (cons && cons.excluded && cons.excluded.indexOf(row.id) >= 0) { continue; }
        var rec = ctx.item(row.id);
        var slots = (rec && rec.slots) || [];
        var carries = false;
        for (var s = 0; s < slots.length; s++) {
          var allow = (slots[s] && slots[s].allow) || [];
          if (allow.indexOf(targetId) >= 0) { carries = true; break; }
        }
        if (!carries) { continue; }
        var trial = {};
        for (var k in cur) { trial[k] = cur[k]; }
        trial[p] = row.id;
        var inst = sanitize(ctx, gunId, trial).installed;
        var t2 = buildTree(ctx, gunId, inst);
        var p2 = t2.order.filter(function (pp) {
          return t2.nodes[pp].allow.indexOf(targetId) >= 0;
        })[0];
        if (p2) { return { ok: true, steps: [{ path: p, id: row.id }, { path: p2, id: targetId }] }; }
      }
    }
    return { ok: false, steps: [] };
  }

  function nameOfItem(ctx, id) {
    var r = ctx.item(id);
    return (r && r.n) || id;
  }

  /** 枚举当前枪械真实兼容的弹匣容量（按默认装配展开整棵树，收集 allow 里带 cap 的件）。
   *  baseInstalled 由调用方传入（app.js 的 gunDefaultBuild），嵌套弹匣井要靠它展开。 */
  function magCapacities(ctx, gunId, baseInstalled) {
    var tree = buildTree(ctx, gunId, baseInstalled || {});
    var caps = {};
    tree.order.forEach(function (path) {
      tree.nodes[path].allow.forEach(function (id) {
        var rec = ctx.item(id);
        var cap = rec ? num(rec.cap) : null;
        if (cap !== null) { caps[cap] = (caps[cap] || 0) + 1; }
      });
    });
    return Object.keys(caps).map(Number).sort(function (a, b) { return a - b; })
      .map(function (c) { return { cap: c, count: caps[c] }; });
  }

  /**
   * R19.11：弹匣容量硬约束。
   * 把「允许容量集合」当成硬条件：先给每个弹匣槽装上**容量合规**的弹匣，并把这些槽位锁死，
   * 让后面的贪心不可能再换成 30 发之类的弹匣。找不到合规弹匣时 ok=false 并给出可读原因，
   * 由上层把这种方案从"有效方案"里剔除（不是标红后继续当有效结果）。
   * 容量来自物品自身的 cap 字段（真实数据）；cap 缺失按"未知"处理，绝不当作合规。
   */
  function enforceMagCapacity(ctx, gunId, cur, cons) {
    var caps = (cons && cons.caps) || [];
    if (!caps.length) { return { ok: true, installed: cur, locked: [], why: null, detail: null }; }
    var locked = [];
    var magPaths = [];
    var t0 = buildTree(ctx, gunId, cur);
    t0.order.forEach(function (path) {
      if (/magazine/i.test(String(t0.nodes[path].sid || ""))) { magPaths.push(path); }
    });
    if (!magPaths.length) {
      return { ok: false, installed: cur, locked: [], why: "当前枪械没有弹匣槽（内置供弹），无法满足容量约束",
               detail: { magPaths: 0, available: [] } };
    }
    var available = magCapacities(ctx, gunId, cur).map(function (c) { return c.cap; });
    var why = null;
    for (var i = 0; i < magPaths.length; i++) {
      var path = magPaths[i];
      var tree = buildTree(ctx, gunId, cur);
      var node = tree.nodes[path];
      if (!node) { continue; }
      var curId = cur[path] || null;
      var curRec = curId ? ctx.item(curId) : null;
      var curCap = curRec ? num(curRec.cap) : null;
      if (curCap !== null && caps.indexOf(curCap) >= 0) { locked.push(path); continue; }
      var rows = candidates(ctx, gunId, cur, path).rows;
      var pick = null;
      for (var j = 0; j < rows.length; j++) {
        var row = rows[j];
        if (row.blocked) { continue; }
        if (cons.excluded && cons.excluded.indexOf(row.id) >= 0) { continue; }
        var rec = ctx.item(row.id);
        var cap = rec ? num(rec.cap) : null;
        if (cap === null || caps.indexOf(cap) < 0) { continue; }
        var trial = {};
        for (var k in cur) { trial[k] = cur[k]; }
        trial[path] = row.id;
        var inst = sanitize(ctx, gunId, trial).installed;
        if (inst[path] !== row.id) { continue; }   // 会被兼容校验清掉的不算
        pick = row.id;
        break;
      }
      if (!pick) {
        why = "当前枪械没有满足 " + caps.join(" / ") + " 发容量约束的弹匣或弹鼓" +
              (available.length ? ("（该枪可选容量：" + available.join(" / ") + " 发）")
                                : "（该枪没有带容量数据的弹匣）");
        continue;
      }
      var t2 = {};
      for (var k2 in cur) { t2[k2] = cur[k2]; }
      t2[path] = pick;
      cur = sanitize(ctx, gunId, t2).installed;
      locked.push(path);
    }
    return { ok: !why, installed: cur, locked: locked, why: why,
             detail: { magPaths: magPaths.length, available: available } };
  }

  /**
   * R19.12：试装结果是否"顺手拆掉"了不该动的件。
   * 只允许动目标槽位自己及其子树（换护木连带换掉导轨属于正常更换），
   * 其余任何受保护（必装 / 锁定 / 容量槽）的件消失或被换掉都算非法改动。
   */
  function evictsProtected(ctx, before, after, targetPath, protectedIds, lockedPaths) {
    for (var p in before) {
      if (!before[p]) { continue; }
      if (targetPath && (p === targetPath || p.indexOf(targetPath + "/") === 0)) { continue; }
      var now = after[p];
      if (now === before[p]) { continue; }
      if (protectedIds[before[p]] || (lockedPaths && lockedPaths[p])) { return true; }
    }
    return false;
  }

  function optimize(ctx, gunId, installed, opts) {
    opts = opts || {};
    var cons = opts.constraints || null;
    var budget = opts.budget || 4000;
    var weightsList = opts.weights || [
      { name: "低后坐力", recoil: 1.0, ergo: 0.15, weight: 0.1, cost: 0 },
      { name: "高人机工效", recoil: 0.15, ergo: 1.0, weight: 0.1, cost: 0 },
      { name: "轻量化", recoil: 0.2, ergo: 0.2, weight: 1.0, cost: 0 },
      { name: "性价比", recoil: 0.4, ergo: 0.4, weight: 0.2, cost: 1.0 }
    ];
    var evaluations = 0;
    var results = [];

    function scoreOf(st, w) {
      // 归一化：后坐力按 100、ergo 按 50、重量按 5、成本按 200000 做尺度
      var rv = st.fields.recoilV.v, rh = st.fields.recoilH.v;
      var er = st.fields.ergonomics.v, wt = st.fields.weight.v;
      var s = 0;
      if (rv !== null && rh !== null) { s += w.recoil * ((rv + rh) / 100); }
      if (er !== null) { s -= w.ergo * (er / 50); }
      if (wt !== null) { s += w.weight * (wt / 5); }
      return s;
    }

    weightsList.forEach(function (w) {
      var cur = {};
      for (var k in (installed || {})) { if (installed[k]) { cur[k] = installed[k]; } }
      cur = sanitize(ctx, gunId, cur).installed;
      var startSnapshot = {};
      for (var sk in cur) { startSnapshot[sk] = cur[sk]; }
      var st = compute(ctx, gunId, cur, opts);
      var best = scoreOf(st, w);
      var costNow = cost(ctx, gunId, cur, { includeStock: true }).total;
      evaluations++;

      // R19.4 / R19.8：必装件预装（在贪心之前，失败即报约束冲突）
      //  R19.8：cons.scopeId 视为必装瞄具，且允许自动补一级转接座（真实兼容链）
      var consErr = [];
      var capsOk = true, capsWhy = null;
      var lockedIds = {};
      var protectedIds = {};      // R19.12：必装 / 锁定 / 弹匣容量槽上的件，任何一步都不许被顺手清掉
      var claimedIds = [];        // 方案会"声称已装"的件（终检时逐件核对是否真的还在）
      var dropLog = [];           // 方案过程中被兼容链清掉的件（用于报告，不隐藏）
      var lockedPaths = {};   // R19.9：必装件的安装路径（含自动补的转接座）在贪心阶段锁定
      if (cons) {
        var reqAll = (cons.required || []).slice();
        if (cons.scopeId && reqAll.indexOf(cons.scopeId) < 0) { reqAll.push(cons.scopeId); }
        (cons.deviceIds || []).forEach(function (id) {
          if (id && reqAll.indexOf(id) < 0) { reqAll.push(id); }   // R19.9：选定型号计入必装
        });
        var mustKeepIds = {};
        (cons.deviceIds || []).forEach(function (id) { if (id) { mustKeepIds[id] = 1; } });
        function preinstallRequired() {
          reqAll.forEach(function (id) {
            if (installedList(cur).some(function (e) { return e.id === id; })) { lockedIds[id] = 1; return; }
            var plan = resolveInstall(ctx, gunId, cur, id, cons);
            if (!plan.ok) { return; }        // 最终校验会给出可读冲突
            plan.steps.forEach(function (step) {
              lockedPaths[step.path] = 1;   // 直接槽位 + 转接座槽位一并锁定
              // R19.10：选定型号还要锁住**承载它的父件槽位**（护木 / 机匣 / 转接座）。
              // 否则贪心会把护木换成战术槽更少的型号，两件必装设备就只剩一件能装。
              if (mustKeepIds[id]) {
                var cutAt = step.path.lastIndexOf("/");
                if (cutAt > 0) { lockedPaths[step.path.slice(0, cutAt)] = 1; }
              }
              var trial = {};
              for (var kk in cur) { trial[kk] = cur[kk]; }
              trial[step.path] = step.id;
              var pRes = sanitize(ctx, gunId, trial);
              cur = pRes.installed;
              lockedIds[step.id] = 1;
              protectedIds[step.id] = 1;
              if (claimedIds.indexOf(step.id) < 0) { claimedIds.push(step.id); }
            });
          });
        }
        // R19.11：弹匣容量是硬约束 —— 预装合规弹匣并锁死该槽位
        if (cons.caps && cons.caps.length) {
          var magFix = enforceMagCapacity(ctx, gunId, cur, cons);
          cur = magFix.installed;
          for (var mfi = 0; mfi < magFix.locked.length; mfi++) {
            lockedPaths[magFix.locked[mfi]] = 1;
          }
          if (!magFix.ok) {
            capsOk = false;
            capsWhy = magFix.why;
            if (consErr.indexOf(magFix.why) < 0) { consErr.push(magFix.why); }
          } else {
            magFix.locked.forEach(function (mp) {
              if (cur[mp]) { protectedIds[cur[mp]] = 1; claimedIds.push(cur[mp]); }
            });
          }
        }
        // 两件必装设备可能抢同一个战术槽：安装顺序里后一件顶掉前一件时，
        // 下一轮把缺的那件补到剩下的空槽（resolveInstall 已优先选空槽），最多三轮。
        for (var prePass = 0; prePass < 3; prePass++) {
          var missingReq = reqAll.filter(function (id) {
            return !installedList(cur).some(function (e) { return e.id === id; });
          });
          if (!missingReq.length) { break; }
          preinstallRequired();
        }
        if (cons.required && cons.excluded &&
            cons.required.some(function (id) { return cons.excluded.indexOf(id) >= 0; })) {
          consErr.push("同一个配件同时出现在「必须包含」和「排除」里");
        }
        if (cons.excluded && cons.scopeId && cons.excluded.indexOf(cons.scopeId) >= 0) {
          consErr.push("所选瞄具同时被列入「排除」，条件自相矛盾");
        }
      }

      for (var round = 0; round < 3 && evaluations < budget; round++) {
        var improved = false;
        var tree = buildTree(ctx, gunId, cur);
        for (var i = 0; i < tree.order.length && evaluations < budget; i++) {
          var path = tree.order[i];
          var cand = candidates(ctx, gunId, cur, path);
          var pickBest = null, pickScore = best, pickCost = costNow;
          for (var j = 0; j < cand.rows.length && evaluations < budget; j++) {
            var row = cand.rows[j];
            if (row.blocked) { continue; }
            if (opts.blockIds && opts.blockIds[row.id]) { continue; }
            // R19.9：必装件安装路径（含转接座）锁定，不允许贪心替换
            if (lockedPaths[path]) { continue; }
            // R19.4：约束过滤（排除 / 弹匣容量）；必装件所在槽位锁定不被换掉
            if (cons) {
              if (cons.excluded && cons.excluded.indexOf(row.id) >= 0) { continue; }
              var curId = cur[path];
              if (curId && lockedIds[curId] && row.id !== curId) { continue; }
              if (cons.caps && cons.caps.length) {
                var recC = ctx.item(row.id);
                var capC = recC ? num(recC.cap) : null;
                if (capC !== null && cons.caps.indexOf(capC) < 0) { continue; }
              }
            }
            var trial = {};
            for (var kk in cur) { trial[kk] = cur[kk]; }
            trial[path] = row.id;
            // R19.12：试装用真实兼容链清理，但**不接受两种结果**：
            //   ① 候选自己被清掉（说明它其实装不上）；
            //   ② 连带清掉了受保护件（必装 / 用户锁定 / 弹匣容量槽）。
            // 以前这里直接拿清理后的结果继续算分，于是"局部替换引入冲突"被静默吞掉。
            var tRes = sanitize(ctx, gunId, trial);
            trial = tRes.installed;
            if (trial[path] !== row.id) { continue; }
            if (evictsProtected(ctx, cur, trial, path, protectedIds, lockedPaths)) { continue; }
            var sc = cost(ctx, gunId, trial, { includeStock: true }).total;
            if (opts.maxCost && sc !== null && sc > opts.maxCost) { continue; }
            var ts = compute(ctx, gunId, trial, opts);
            var sc2 = scoreOf(ts, w);
            evaluations++;
            if (sc2 < pickScore - 1e-6) {
              pickScore = sc2; pickBest = row.id; pickCost = sc;
            }
          }
          if (pickBest) {
            cur[path] = pickBest;
            cur = sanitize(ctx, gunId, cur).installed;
            best = pickScore; costNow = pickCost;
            improved = true;
          }
        }
        if (!improved) { break; }
      }
      // R19.8：贪心可能换掉必装件所依赖的父件，sanitize 会把必装子件一起清掉 → 再补装一次
      // R19.10：选定的战术设备型号（deviceIds）与瞄具同属"必装件"，必须一起补装，
      //         否则贪心换掉护木/转接座后，方案里就只剩"任意具备该功能的设备"或干脆没有。
      if (cons) {
        var reqFix = (cons.required || []).slice();
        if (cons.scopeId && reqFix.indexOf(cons.scopeId) < 0) { reqFix.push(cons.scopeId); }
        (cons.deviceIds || []).forEach(function (id) {
          if (id && reqFix.indexOf(id) < 0) { reqFix.push(id); }
        });
        reqFix.forEach(function (id) {
          if (installedList(cur).some(function (e) { return e.id === id; })) { return; }
          var plan2 = resolveInstall(ctx, gunId, cur, id, cons);
          if (!plan2.ok) { return; }
          plan2.steps.forEach(function (step) {
            var trial2 = {};
            for (var kk2 in cur) { trial2[kk2] = cur[kk2]; }
            trial2[step.path] = step.id;
            cur = sanitize(ctx, gunId, trial2).installed;
          });
        });
      }
      // R19.4：要求瞄具但贪心没装上 → 从 scope 槽位候选里挑得分最好的一件补装
      if (cons && cons.scope) {
        var hasScope = installedList(cur).some(function (e) {
          return e.path.split("/").some(function (seg) { return /scope/i.test(seg); });
        });
        if (!hasScope) {
          var t2 = buildTree(ctx, gunId, cur);
          var bestScope = null, bestSc = null;
          t2.order.forEach(function (path) {
            if (!/scope/i.test(path)) { return; }
            candidates(ctx, gunId, cur, path).rows.forEach(function (row) {
              if (row.blocked) { return; }
              if (cons.excluded && cons.excluded.indexOf(row.id) >= 0) { return; }
              var trial = {};
              for (var kk in cur) { trial[kk] = cur[kk]; }
              trial[path] = row.id;
              trial = sanitize(ctx, gunId, trial).installed;
              var ts = compute(ctx, gunId, trial, opts);
              var sc = scoreOf(ts, w);
              if (bestSc === null || sc < bestSc) { bestSc = sc; bestScope = { path: path, id: row.id }; }
            });
          });
          if (bestScope) {
            cur[bestScope.path] = bestScope.id;
            cur = sanitize(ctx, gunId, cur).installed;
          }
        }
      }
      // R19.8：功能约束（手电 / 激光）——贪心结束后补装满足功能的战术设备
      //  一件双功能设备可同时满足两组；否则按真实槽位装两件独立设备。
      if (cons && cons.features && cons.features.length) {
        cons.features.forEach(function (spec) {
          var ids = (spec && spec.ids) || [];
          if (!ids.length) { return; }
          if (installedList(cur).some(function (e) { return ids.indexOf(e.id) >= 0; })) { return; }
          var t4 = buildTree(ctx, gunId, cur);
          var pick = null, pickKey = null;
          function consider(instTrial, devId) {
            var st2 = compute(ctx, gunId, instTrial, opts);
            var sc = scoreOf(st2, w);
            // 覆盖数优先（尽量一件设备满足多个已选功能），同覆盖再按当前权重得分
            var cover = 0;
            cons.features.forEach(function (s2) {
              if (s2 && s2.ids && s2.ids.indexOf(devId) >= 0) { cover++; }
            });
            var key = cover * 1e6 - sc;
            if (pickKey === null || key > pickKey) { pickKey = key; pick = { installed: instTrial }; }
          }
          t4.order.forEach(function (path) {
            candidates(ctx, gunId, cur, path).rows.forEach(function (row) {
              if (row.blocked) { return; }
              if (cons.excluded && cons.excluded.indexOf(row.id) >= 0) { return; }
              if (opts.blockIds && opts.blockIds[row.id]) { return; }
              var trial = {};
              for (var kk in cur) { trial[kk] = cur[kk]; }
              if (ids.indexOf(row.id) >= 0) {
                trial[path] = row.id;
                consider(sanitize(ctx, gunId, trial).installed, row.id);
                return;
              }
              // 一级转接：该配件的子槽 allow 里含目标设备（例如换上有导轨的护木）
              var recD = ctx.item(row.id);
              var sls = (recD && recD.slots) || [];
              var carry = null;
              for (var s = 0; s < sls.length && !carry; s++) {
                var allowD = (sls[s] && sls[s].allow) || [];
                for (var a = 0; a < allowD.length; a++) {
                  if (ids.indexOf(allowD[a]) >= 0) { carry = allowD[a]; break; }
                }
              }
              if (!carry) { return; }
              trial[path] = row.id;
              var instP = sanitize(ctx, gunId, trial).installed;
              var t5 = buildTree(ctx, gunId, instP);
              var p5 = t5.order.filter(function (pp) {
                return t5.nodes[pp].allow.indexOf(carry) >= 0;
              })[0];
              if (!p5) { return; }
              instP[p5] = carry;
              consider(sanitize(ctx, gunId, instP).installed, carry);
            });
          });
          if (pick) { cur = pick.installed; }
        });
      }
      var finalSt = compute(ctx, gunId, cur, opts);
      var chk = cons ? checkConstraints(ctx, gunId, cur, cons) : { ok: true, violations: [] };
      if (consErr.length) {
        chk = { ok: false,
                violations: consErr.map(function (m) { return { kind: "conflict", id: null, why: m }; })
                  .concat(chk.violations) };
      }
      // R19.11：容量合规是"有效方案"的必要条件 —— 不合规的方案不进有效列表
      var magOkNow = capsOk;
      var magWhyNow = capsWhy;
      if (capsOk && cons && cons.caps && cons.caps.length) {
        var recount = enforceMagCapacity(ctx, gunId, cur, cons);
        // 贪心结束后再核对一次（例如贪心把承载弹匣的父件换掉了）
        if (!recount.ok) { magOkNow = false; magWhyNow = recount.why; }
        else { cur = recount.installed; }
      }
      if (!magOkNow && magWhyNow) {
        chk = { ok: false,
                violations: [{ kind: "caps", id: null, why: magWhyNow }].concat(chk.violations) };
      }
      // ---- R19.12：出方案前的**独立整树校验**（不复用上面任何中间判断）----
      var expectIds = claimedIds.slice();
      (cons ? (cons.required || []) : []).forEach(function (id) { if (id) { expectIds.push(id); } });
      if (cons && cons.scopeId) { expectIds.push(cons.scopeId); }
      (cons ? (cons.deviceIds || []) : []).forEach(function (id) { if (id) { expectIds.push(id); } });
      // 容量槽上实际装着的合规弹匣也算"声称已装"——它被清掉就是方案失效
      if (cons && cons.caps && cons.caps.length) {
        installedList(cur).forEach(function (e) {
          var r = ctx.item(e.id);
          var c = r ? num(r.cap) : null;
          if (c !== null && cons.caps.indexOf(c) >= 0) { expectIds.push(e.id); }
        });
        var magPathsNow = [];
        buildTree(ctx, gunId, cur).order.forEach(function (pp) {
          if (/magazine/i.test(pp)) { magPathsNow.push(pp); }
        });
        magPathsNow.forEach(function (pp) { if (cur[pp]) { expectIds.push(cur[pp]); } });
      }
      var seenExpect = {}, expectUniq = [];
      expectIds.forEach(function (id) {
        if (id && !seenExpect[id]) { seenExpect[id] = 1; expectUniq.push(id); }
      });
      // 方案相对"起始装配"改动了哪些件：被换掉的、被移除的都记下来（不隐藏）
      Object.keys(startSnapshot).sort().forEach(function (sp) {
        if (!startSnapshot[sp]) { return; }
        if (cur[sp] === startSnapshot[sp]) { return; }
        dropLog.push({
          path: sp, id: startSnapshot[sp], name: nameOfItem(ctx, startSnapshot[sp]),
          replacedBy: cur[sp] || null, why: cur[sp] ? "被替换" : "被移除（与最终装配不共存）"
        });
      });
      var verify = verifyBuild(ctx, gunId, cur, cons, { ids: expectUniq });
      var finalPairs = conflictPairs(ctx, cur);
      if (finalPairs.length) {
        // 兜底：正常情况下 sanitize 已经清干净，走到这里说明清理没生效 → 明确判无效
        finalPairs.forEach(function (p) {
          verify.problems.push({ kind: "conflict", id: p.a,
            why: "最终装配里仍有互斥组合：「" + p.nameA + "」(" + p.pathA + ") 与「" +
                 p.nameB + "」(" + p.pathB + ")" });
        });
        verify.ok = false;
      }
      if (!verify.ok) {
        // 顺序很重要：先给"用户约束"的可读原因（例如"没有满足 100 发容量约束"），
        // 再给整树校验细节；同一条原因只留一次。
        var merged = chk.violations.slice();
        var seenWhy = {};
        merged.forEach(function (v) { seenWhy[v.kind + "|" + v.why] = 1; });
        verify.problems.forEach(function (x) {
          var key = (x.kind || "") + "|" + x.why;
          if (seenWhy[key]) { return; }
          seenWhy[key] = 1;
          merged.push({ kind: x.kind, id: x.id || null, why: x.why });
        });
        chk = { ok: false, violations: merged };
      }
      results.push({
        name: w.name, installed: cur, stats: finalSt,
        cost: cost(ctx, gunId, cur, { includeStock: true }),
        score: Math.round(scoreOf(finalSt, w) * 1000) / 1000,
        constraintOk: chk.ok, violations: chk.violations,
        capsOk: magOkNow, capsWhy: magWhyNow,
        // R19.12：方案自带的整树校验档案（UI / 审计 / 应用前复核都用它）
        verify: { ok: verify.ok, parts: verify.parts, problems: verify.problems,
                  conflicts: verify.conflicts.length },
        expectIds: expectUniq, dropped: dropLog
      });
    });

    // 去重（不同权重可能收敛到同一套装配）
    var seen = {}, uniq = [];
    results.forEach(function (r) {
      var key = Object.keys(r.installed).sort().map(function (p) {
        return p + "=" + r.installed[p];
      }).join("|") + "#" + r.name;
      if (seen[key]) { return; }
      seen[key] = 1;
      uniq.push(r);
    });
    return { builds: uniq, evaluations: evaluations, budget: budget };
  }

  return {
    CONF: CONF, context: context, buildTree: buildTree, candidates: candidates,
    compute: compute, cost: cost, validate: validate, sanitize: sanitize,
    serialize: serialize, parse: parse, chains: chains, compare: compare,
    adsTimeFromErgo: adsTimeFromErgo,
    optimize: optimize, PRESET_VERSION: PRESET_VERSION,
    checkConstraints: checkConstraints, magCapacities: magCapacities,
    resolveInstall: resolveInstall,
    conflictSet: conflictSet, conflictsWith: conflictsWith,
    conflictPairs: conflictPairs, verifyBuild: verifyBuild,
    _internal: { pickE: pickE, pickRm: pickRm, priceOf: priceOf, betterOf: betterOf }
  };
}));
