// combat_sim.js — r14 阶段C / r15 修复 / r16 方向性护甲：EFT 逐发击杀模拟引擎（纯计算，无 DOM / 无网络 / ES5）
// 依赖注入：穿透概率模型由调用方传入（app.js 传 amDesmosChance）；飞行弹道与终端伤害分离，
// 引擎只消费「终端状态」{speed, pen, dmg}（由 flightFn(ammo, dist) 计算，缺省不衰减）。
// r15：障碍物与护甲分层独立结算；护甲按「硬插板 → 头盔 → 软内衬」顺序逐层传递剩余状态。
// r16：
//   · 每层可带 side（front/back/left/right/all，缺省 all 保持旧行为），单发按射击方向 dir 只经过
//     该方向真正存在的防护层——正面射击不会把后插板当成入体前的第二层。
//   · 子弹入体后，可选的「躯干出口 / 对侧插板二次碰撞」是**独立后续事件**（exitModel=estimate），
//     只影响该插板耐久并单独记账，绝不回算入体前的减伤；缺省关闭。
//   · constraints 可对弹药/弹匣做硬校验：不在白名单内直接抛错，不允许非法输入静默进引擎。
// 所有经验模型均在 docs/r15-fixes/armor-layer-research.md 与 barrier-research.md 登记
// 证据等级（verified / estimated / missing）；方向性部分见 docs/r16-completeness/armor-direction-research.md。
(function (global) {
  'use strict';

  var CS = {};

  // —— R62：按 0.13.x 客户端反编译原文重写甲伤 / 跳弹 / 穿透浮动 ——
  // 权威依据：D:\personal\trae\02-塔科夫\逆向参考\r61-eft-decompiled-ballistics.md
  //   Armor.ApplyDamage：DamageToArmor = P × ArmorDamage × clamp(P / Resistance, …) × Destructibility
  //   Resistance = 10 × ArmorClass（0 级为 1），不是 FactorA；原文没有 ×0.7 / 1.2 封顶 / 66–75% 随机区间。
  //   跳弹后 Damage / ArmorDamage / Penetration 全部 ÷2，再走「被挡下」分支，仍按同一甲伤公式扣耐久。
  // 旧口径保留为可选（'site' / 'video'），默认关闭；UI「关于」注明来源差异。
  CS.ARMOR_DMG_COEFF_MODE = 'decomp';  // 'decomp'=原文 P/(10×AC) | 'site'=旧 (P/AC)*10 | 'video'=旧 P/(AC*10)
  CS.ARMOR_CLASS_PROTECTION = 10;      // 原文 Resistance = 等级 × 10
  CS.DUR_PROTECTION_CAP = 1.2;         // 仅旧 video 模式保留（已非默认）
  CS.EST_THROUGH_MIN = 0.6;            // 减伤系数下限（Ballistics.cs CalculateReductionFactor clamp 0.6）
  // 插板 + 内衬同时存在时，插板钝伤 ×0.6（0.12 槽位口径）。
  // 0.13.x 原文（r65）里 BluntDamageReduceFromSoftArmorMod 0 引用，角色已由「后继层各自 ×BT」承担
  // → 默认停用；启用会与后继层 BT 形成双重扣减（仅作历史对照开关）。
  CS.SOFT_LINER_PLATE_BLUNT_MUL = 0.6;
  CS.SOFT_LINER_PLATE_BLUNT_ENABLED = false;

  // —— R63：重型护甲技能（data/game-truth/globals_ballistic.json → SkillsSettings.HeavyVests） ——
  // 原文 ArmorComponent.ApplyDamage：num2 = Template.BluntThroughput;
  //   if (flag && Template.ArmorType == Heavy) num2 *= 1 - heavyVestsDamageReduction;
  // globals 字段名即「每级减少量」：BluntThroughputDamageHVestsReducePerLevel = 0.004。
  // 0–50 级线性推断（字段名直述 per level；游戏是否另有递减曲线未知 → 台账标注）。
  CS.HV_REDUCE_PER_LEVEL = 0.004;
  CS.HV_MAX_LEVEL = 50;
  // —— R63：碎片化（社区经验模型，默认关闭） ——
  // 原文 CreateShot 只把 FragmentationChance / MinFragmentsCount / MaxFragmentsCount 传进 Shot，
  // 未摘到「碎片数 → 附加伤害」的映射。社区服务端 Ballistics.cs 近似：
  //   pen < 20 → frag_chance = 0；average_damage = D×(1−fc) + (D×1.5)×fc。
  // 因此本项目只做最保守实现：触发时额外 +0.5×入体伤害（按 1 片计），并标注 estimated。
  CS.FRAG_EXTRA_MUL = 0.5;
  CS.FRAG_MIN_PEN = 20;

  /** Ballistics.cs CalculateFactor_A：durPct = 耐久百分比 0–100。 */
  CS.armorFactorA = function (cls, durPct) {
    return (121 - 5000 / (45 + durPct * 2)) * cls * 0.1;
  };
  /** Ballistics.cs CalculateReductionFactor：clamp(P/(FactorA+12), 0.6, 1)。 */
  CS.armorReductionFactor = function (pen, cls, durPct) {
    return clamp(pen / (CS.armorFactorA(cls, durPct) + 12), CS.EST_THROUGH_MIN, 1);
  };
  /** 原文 Resistance = armor.class[cls].resistance：0 级为 1，其余 10×等级。 */
  CS.armorClassResistance = function (cls) {
    var c = Number(cls);
    if (!isFinite(c) || c <= 0) { return 1; }
    return c * CS.ARMOR_CLASS_PROTECTION;
  };
  /** 护甲耐久伤害系数：格挡 clamp(0.6,1.1)；击穿 clamp(0.5,0.9)。
   *  decomp（默认）：原文 P / Resistance，Resistance = 10×AC，不会恒顶上限；
   *  site（旧，可选）：C# 左结合 (P/AC)*10 —— 常见输入恒顶到 1.1/0.9；
   *  video（旧，可选）：P/(AC*10)，保留 1.2 上限（与反编译原文不符）。 */
  CS.armorDamageCoeff = function (pen, cls, penetrated, mode) {
    var ac = Math.max(1, cls);
    var v;
    if (mode === 'site') {
      v = (pen / ac) * CS.ARMOR_CLASS_PROTECTION;
    } else if (mode === 'video') {
      v = pen / (ac * CS.ARMOR_CLASS_PROTECTION);
    } else {
      v = pen / CS.armorClassResistance(cls);
    }
    if (penetrated) {
      return clamp(v, 0.5, mode === 'video' ? CS.DUR_PROTECTION_CAP : 0.9);
    }
    return clamp(v, 0.6, mode === 'video' ? CS.DUR_PROTECTION_CAP : 1.1);
  };
  /** Ballistics.cs BluntDamage 的系数：median(0.2, 1 - 0.03*(FactorA - P), 1)。 */
  CS.armorBluntScale = function (pen, cls, durPct) {
    return clamp(1 - 0.03 * (CS.armorFactorA(cls, durPct) - pen), 0.2, 1);
  };
  // R19.8b：材质钝伤系数（用户给定：钛14/钢18/复合18（6级22）/聚乙烯26/陶瓷28–29）。
  // 仅当装备数据缺 bt 时作为兜底；逐件 BT 优先（内衬钝伤不按材质区分）。
  CS.MATERIAL_BLUNT = { titan: 0.14, armorSteel: 0.18, combined: 0.18,
                        uhmwpe: 0.26, ceramic: 0.28, glass: 0.29,
                        aramid: 0.18, aluminium: 0.18 };
  CS.defaultBlunt = function (material, cls) {
    if (material === 'combined' && cls >= 6) { return 0.22; }
    return CS.MATERIAL_BLUNT[material] !== undefined ? CS.MATERIAL_BLUNT[material] : 0.18;
  };
  // R19.8b：截图公式未画钳制；用户口径「高穿弹打低级甲就是 1.2，否则伤害溢出太离谱」，
  // 因此保留 1.2 上限（用户确认，不是截图推导）。
  CS.DUR_PROTECTION_CAP = 1.2;
  // 障碍物缺字段时的保守默认（仅当弹药没有 pch 时使用；当前 200 件弹药均有 pch）
  CS.EST_BARRIER_CHANCE = 0.5;
  CS.EST_BARRIER_DMG_KEEP = 0.8;      // 穿过障碍后保留伤害（Reddit jn9cxx 现象 ≈ 低 10%；取 0.8 保守）
  CS.EST_BARRIER_PEN_KEEP = 0.85;     // 穿过障碍后保留穿透力（community estimated）
  // 躯干出口 / 对侧插板的二次碰撞：只有在显式开启 exitModel 时启用，且**不参与**入体前的减伤。
  // 证据：社区报告「前方子弹经未覆盖区域后击中后插板并使后插板掉耐久」，但这可能是命中框/顺序问题，
  // 无法在当前资料下证实为普遍机制 → 作为可选估算模型（默认关闭），日志里单独标记。
  CS.EST_EXIT_DMG_KEEP = 0.35;        // 已在体内消耗后，撞到对侧插板时保留的弹体伤害（估算）
  CS.EST_EXIT_PEN_KEEP = 0.6;         // 撞到对侧插板时保留的穿透力（估算）
  CS.LIMB_OVERFLOW = 0.49;            // 手臂摧毁后分散比例（fandom Health_system，2026-10-23 实读 verified）
  CS.LEG_OVERFLOW = 0.7;              // 腿摧毁后分散比例（同上 verified；r17 修正——旧实现误用手臂的 0.49）
  CS.STOMACH_OVERFLOW = 1.05;         // 胃摧毁后分散比例（同上 verified）
  // —— r17 补充：穿过人体碰撞箱的估算续命中（默认关闭，cfg.throughBody='estimate' 开启） ——
  // 无官方数值：弹体穿出已命中的部位、继续命中躯干时按比例衰减（estimated）。
  // 续命中按「正常命中」语义结算到新部位（绝不套用黑化分散倍率）；默认不重算新部位的护甲。
  CS.EST_THROUGH_BODY_DMG_KEEP = 0.6;
  CS.EST_THROUGH_BODY_PEN_KEEP = 0.6;

  // 默认材质毁损系数 = 客户端 globals.json 的 ArmorMaterials[*].Destructibility
  // （data/game-truth/globals_ballistic.json 实抽；Ceramic 为 0.6，不是站点旧表的 0.55）
  CS.MATERIAL_DESTRUCTIBILITY = {
    aramid: 0.1875, uhmwpe: 0.3375, combined: 0.375, titan: 0.4125,
    aluminium: 0.45, armorSteel: 0.525, ceramic: 0.6, glass: 0.6
  };

  // —— 种子随机（mulberry32，可复现） ——
  CS.rng32 = function (seed) {
    var s = seed >>> 0;
    return function () {
      s = (s + 0x6D2B79F5) >>> 0;
      var t = s;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  };

  /** Box–Muller 正态采样（同一 seed 可复现）；u1 取 (0,1] 避免 log(0)。 */
  CS.normalRandom = function (rng, mean, sd) {
    var u1 = 1 - rng();
    var u2 = rng();
    return mean + sd * Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2);
  };

  // —— 终端状态（飞行模拟与终端伤害分离）：flightFn 缺省不衰减 ——
  CS.defaultFlight = function (ammo) {
    return { speed: ammo.v0, pen: ammo.pen, dmg: ammo.dmg };
  };

  // —— 状态构造 ——
  // 弹匣：rounds 为弹药对象数组（混压弹匣按数组顺序逐发，耗尽即停）
  CS.createMagazine = function (rounds) {
    return { rounds: rounds.slice(), pos: 0 };
  };

  // 目标：parts {part: {hp, max}}；死亡 = 头/胸摧毁 或 总血量 ≤ 0
  CS.createTarget = function (partHp) {
    var parts = {};
    var total = 0;
    for (var k in partHp) {
      if (Object.prototype.hasOwnProperty.call(partHp, k)) {
        parts[k] = { hp: partHp[k], max: partHp[k] };
        total += partHp[k];
      }
    }
    return { parts: parts, total: total, dead: false, deathCause: null };
  };

  // 护甲/头盔/软内衬层：layer = { name, kind: 'helmet'|'plate'|'liner',
  //   zones: [part...]|'all', cls, durMax, dur, material, bluntThroughput, order?,
  //   side?: 'front'|'back'|'left'|'right'|'all'  —— r16：该层实际处在哪一面；缺省 all（旧行为） }
  CS.createArmorLayers = function (cfg) {
    var out = [];
    (cfg || []).forEach(function (l, idx) {
      out.push({
        name: l.name || l.kind || 'layer',
        kind: l.kind || 'plate',
        zones: l.zones === 'all' ? 'all' : (l.zones || []).slice(),
        side: l.side || 'all',
        cls: l.cls,
        durMax: l.durMax || l.dur || 0,
        dur: l.dur || l.durMax || 0,
        durOrig: l.durOrig || l.durMax || l.dur || 0,
        material: l.material || 'combined',
        bluntThroughput: typeof l.bluntThroughput === 'number' ? l.bluntThroughput
          : CS.defaultBlunt(l.material || 'combined', l.cls),
        // R63：上游 ArmorType（Heavy/Light）——重型护甲技能只对 Heavy 生效（原文 ApplyDamage）
        armorType: (String(l.armorType || '').toLowerCase() === 'heavy') ? 'Heavy' : 'Light',
        ricochet: l.ricochet || null,
        order: typeof l.order === 'number' ? l.order : idx
      });
    });
    return out;
  };

  // 障碍物：b = { id, n, material, penChanceMul, dmgKeep, penKeep, ricochetMul }
  CS.createBarriers = function (cfg) {
    var out = [];
    (cfg || []).forEach(function (b, idx) {
      out.push({
        id: b.id || ('barrier' + idx),
        n: b.n || b.id || ('障碍 ' + (idx + 1)),
        material: b.material || 'unknown',
        penChanceMul: typeof b.penChanceMul === 'number' ? b.penChanceMul : 1,
        dmgKeep: typeof b.dmgKeep === 'number' ? b.dmgKeep : CS.EST_BARRIER_DMG_KEEP,
        penKeep: typeof b.penKeep === 'number' ? b.penKeep : CS.EST_BARRIER_PEN_KEEP,
        ricochetMul: typeof b.ricochetMul === 'number' ? b.ricochetMul : 1
      });
    });
    return out;
  };

  function covers(layer, part) {
    return layer.zones === 'all' || layer.zones.indexOf(part) >= 0;
  }

  // —— r17：预设压弹（Top / Loop / Bottom）——
  // slots = [ { zone:'top'|'loop'|'bottom', ammoId, count } ... ] 行序即 1–5 行；
  //   top = 最先射出的固定弹药，bottom = 最后射出的固定弹药，loop 按「行序 → 每行 count 发」循环。
  // 生成顺序恒为：Top 固定区 → Loop 循环区（填满剩余容量，末轮不足整轮按顺序截断）→ Bottom 固定区。
  // 纯函数、无随机：同输入必得同弹序（供逐发日志与测试复现）。
  CS.buildMagazineFromPreset = function (slots, capacity) {
    var res = { ok: false, error: null, warnings: [], sequence: [] };
    if (!(capacity > 0)) {
      res.error = '弹匣容量未知（missing），无法按预设装填';
      return res;
    }
    // R17S2：首发/末尾允许多个条目（按配置顺序依次输出，不参与循环）；循环区按序循环。
    var i, top = [], bottom = [], loop = [];
    for (i = 0; i < (slots || []).length; i++) {
      var s = slots[i];
      if (!s || !s.ammoId) { continue; }
      var n = (typeof s.count === 'number' && s.count > 0) ? Math.floor(s.count) : 0;
      if (n <= 0) { continue; }
      if (s.zone === 'top') { top.push({ ammoId: s.ammoId, count: n }); }
      else if (s.zone === 'bottom') { bottom.push({ ammoId: s.ammoId, count: n }); }
      else { loop.push({ ammoId: s.ammoId, count: n }); }
    }
    if (!top.length && !bottom.length && !loop.length) {
      res.error = '预设为空：请先在任意行选择弹药与数量';
      return res;
    }
    // r17s4：循环区最多 5 种弹药条目（UI 也会阻止，这里是最后一道防线）
    if (loop.length > 5) {
      res.error = '循环区最多 5 种弹药：当前 ' + loop.length + ' 种，已阻止装填';
      return res;
    }
    var t = 0, b = 0;
    for (i = 0; i < top.length; i++) { t += top[i].count; }
    for (i = 0; i < bottom.length; i++) { b += bottom[i].count; }
    t = Math.min(t, capacity);
    b = Math.min(b, capacity);
    if (t + b > capacity) {
      res.error = '首发 ' + t + ' 发 + 末发 ' + b + ' 发超过弹匣容量 ' + capacity + ' 发，请减少固定区数量';
      return res;
    }
    var loopNeed = capacity - t - b;
    if (!loop.length && loopNeed > 0) {
      res.warnings.push('循环区没有可用弹药：剩余 ' + loopNeed + ' 发未装填');
    }
    var seq = [];
    for (i = 0; i < top.length; i++) {
      var tn = Math.min(top[i].count, capacity - seq.length);
      for (var ti = 0; ti < tn; ti++) { seq.push(top[i].ammoId); }
    }
    if (loop.length && loopNeed > 0) {
      var pattern = [];
      for (i = 0; i < loop.length; i++) {
        for (var k = 0; k < loop[i].count; k++) { pattern.push(loop[i].ammoId); }
      }
      var filled = 0, pi = 0;
      while (filled < loopNeed) {
        seq.push(pattern[pi % pattern.length]);
        pi++;
        filled++;
      }
      if (loopNeed % pattern.length !== 0) {
        res.warnings.push('循环区最后一轮不满：已按循环顺序截断（剩余容量 ' + loopNeed + ' 发）');
      }
    }
    for (i = 0; i < bottom.length; i++) {
      var bn = Math.min(bottom[i].count, capacity - seq.length);
      for (var bi = 0; bi < bn; bi++) { seq.push(bottom[i].ammoId); }
    }
    res.ok = true;
    res.sequence = seq;
    return res;
  };

  // —— r16 方向性：该层是否处在本次射击会真正经过的一面 ——
  // dir 表示「子弹来的方向」：front = 射手在目标正面。层的 side 与 dir 不同 → 这一发不会碰到它。
  var AM_DIRS = { front: 'back', back: 'front', left: 'right', right: 'left' };
  function sideMatches(layerSide, dir) {
    if (!layerSide || layerSide === 'all') { return true; }
    if (!dir) { return true; }
    return layerSide === dir;
  }
  function oppositeDir(dir) {
    return AM_DIRS[dir] || null;
  }

  // 护甲层顺序：面罩/护目 → 硬插板 → 头盔本体 → 软内衬 → 其它（同组内保持调用方顺序）
  // R68：新增 face（头盔可挂载的装甲附加件）。它覆盖 Eyes/Jaw/HeadCommon，物理上先于头盔本体被命中；
  // plate/helmet 的原有相对次序（插板在头盔前）保持不变，老链路的排序结果不受影响。
  var KIND_RANK = { face: 0, plate: 1, helmet: 2, liner: 3 };
  function sortArmorLayers(layers) {
    return layers.slice().sort(function (a, b) {
      var ra = KIND_RANK[a.kind], rb = KIND_RANK[b.kind];
      if (ra === undefined) { ra = 3; }
      if (rb === undefined) { rb = 3; }
      if (ra !== rb) { return ra - rb; }
      return a.order - b.order;
    });
  }

  // R19.8f：插板下方只要还有任意非插板层（软内衬 / 面罩 / 头盔），就按站点口径把插板钝伤 ×0.6。
  // （原名 hasSoftBacking 只认 liner；用户要求「存在非插板层」即生效。）
  function hasNonPlateBacking(layers, part, fromIdx, dir) {
    for (var j = fromIdx + 1; j < layers.length; j++) {
      var L = layers[j];
      if (L.kind !== 'plate' && covers(L, part) && sideMatches(L.side, dir) &&
          L.cls > 0 && L.dur > 0) { return true; }
    }
    return false;
  }

  function clamp(v, lo, hi) {
    return Math.min(hi, Math.max(lo, v));
  }

  /** R63：重型护甲技能对钝伤系数（BT）的削减。原文 ApplyDamage 只在 ArmorType == Heavy 时
   *  num2 *= 1 - heavyVestsDamageReduction；globals 给的是每级 0.004（0–50 级线性推断）。 */
  function heavyVestsReduce(layer, level) {
    if (!(layer && layer.armorType === 'Heavy')) { return 0; }
    var lv = (typeof level === 'number' && isFinite(level)) ? clamp(level, 0, CS.HV_MAX_LEVEL) : 0;
    return clamp(lv * CS.HV_REDUCE_PER_LEVEL, 0, 1);
  }

  /** R19.8：头盔跳弹概率（来源：tarkovgunsmith 的 ricochetParams x/y/z + 官方 Wiki 定性）。
   *  x = 90°（掠射）时的最大概率，y = 最小角 z 时的最小概率；在 z→90° 之间线性插值。
   *  angle 为弹道与表面法线的夹角：0 = 正面命中，90 = 掠射；angle < z 不跳弹。
   *  这是社区/数据挖掘口径（estimated），不是官方公布公式。 */
  CS.ricochetChance = function (params, angle) {
    if (!params) { return 0; }
    var x = Number(params.x), y = Number(params.y), z = Number(params.z);
    if (!isFinite(x) || !isFinite(y) || !isFinite(z)) { return 0; }
    x = clamp(x, 0, 1); y = clamp(y, 0, 1); z = clamp(z, 0, 90);
    var a = (typeof angle === 'number' && isFinite(angle)) ? angle : 0;
    if (a <= 0 || x <= 0) { return 0; }
    if (a < z) { return 0; }
    if (a >= 90) { return x; }
    if (90 <= z) { return y; }
    return clamp(y + (x - y) * (a - z) / (90 - z), 0, 1);
  };

  // —— 单发核心 ——
  // ctx = { ammo, terminal, part, dir, layers, barriers, rng, penChanceFn, exitModel }
  // 返回逐层可审计日志：每层记录输入/输出穿透力与伤害、层前/层后耐久、概率与掷点、
  // 是否被挡住、钝伤以及最终进入人体的伤害；不属于本方向的层单独记在 layersSkipped。
  function resolveShot(ctx) {
    var rng = ctx.rng;
    var dir = ctx.dir || 'front';
    var st = { pen: ctx.terminal.pen, dmg: ctx.terminal.dmg, speed: ctx.terminal.speed };
    var log = {
      part: ctx.part,
      dir: dir,
      penIn: st.pen, dmgIn: st.dmg,
      pen: st.pen, dmg: st.dmg,
      barriers: [], layers: [], layersSkipped: [],
      penetrated: null, stoppedBy: null, bodyEntry: false,
      exit: null, ricochet: false,
      dmgToPart: 0, dmgToArmor: 0, blunt: false
    };

    // —— 1. 障碍物：与护甲完全分开的机制（不做「等级 × 穿透力」判定） ——
    var barriers = ctx.barriers || [];
    for (var bi = 0; bi < barriers.length; bi++) {
      var B = barriers[bi];
      var penInB = st.pen, dmgInB = st.dmg;
      var base = (typeof ctx.ammo.pch === 'number' && isFinite(ctx.ammo.pch)) ? ctx.ammo.pch : null;
      var chanceB = (base === null) ? CS.EST_BARRIER_CHANCE : clamp(base * B.penChanceMul, 0, 0.95);
      var rollB = rng();
      var passedB = rollB < chanceB;
      var entryB = {
        id: B.id, name: B.n, material: B.material,
        baseChance: base, chance: chanceB, roll: rollB, passed: passedB,
        penIn: penInB, dmgIn: dmgInB, penOut: penInB, dmgOut: dmgInB,
        ricochet: false, confidence: base === null ? 'missing' : 'estimated'
      };
      if (!passedB) {
        // 未穿透：社区资料未见转钝伤，子弹在障碍处终止（跳弹与否都无人体伤害）
        var ricChance = (typeof ctx.ammo.ric === 'number' && isFinite(ctx.ammo.ric))
          ? clamp(ctx.ammo.ric * B.ricochetMul, 0, 0.95) : 0;
        entryB.ricochet = rng() < ricChance;
        entryB.ricochetChance = ricChance;
        log.barriers.push(entryB);
        log.stoppedBy = 'barrier';
        log.penetrated = false;
        log.penAfter = penInB;
        log.dmgAfter = dmgInB;
        return log;
      }
      st.dmg = st.dmg * B.dmgKeep;
      st.pen = st.pen * B.penKeep;
      entryB.penOut = st.pen;
      entryB.dmgOut = st.dmg;
      log.barriers.push(entryB);
    }

    // —— 1b. 未命中目标：子弹从目标旁飞过 —— 掩体照常结算，但不触碰护甲/人体 ——
    if (ctx.missTarget) {
      log.miss = true;
      log.part = null;
      log.penetrated = null;
      log.penAfter = st.pen;
      log.dmgAfter = st.dmg;
      log.dmgToPart = 0;
      log.dmgToArmor = 0;
      return log;
    }

    // —— 2. 护甲：只经过「该方向真实存在」的层；硬插板 → 头盔 → 软内衬，逐层传递剩余状态 ——
    var layers = ctx.layers || [];
    var lastHardChance = null;   // R19.8e：上一硬层的击穿概率（内衬耐久伤害按它缩放）
    var bluntCarry = null;       // R19.8f：已挡下层的钝伤链；后续层继续按自身参数衰减
    for (var i = 0; i < layers.length; i++) {
      var L = layers[i];
      if (!covers(L, ctx.part)) { continue; }
      // 方向不符（例如正面射击时的后插板、左射时的右侧板）：本发不经过，单独记账，不参与任何结算
      if (!sideMatches(L.side, dir)) {
        log.layersSkipped.push({ name: L.name, kind: L.kind, side: L.side, dur: L.dur,
                                 reason: 'not-on-shot-direction' });
        continue;
      }
      if (!(L.cls > 0) || !(L.durMax > 0)) { continue; }   // 无防护层不判定
      var durRatio = L.durOrig > 0 ? (L.dur / L.durOrig) : 0;
      var penIn = st.pen, dmgIn = st.dmg;
      var entry = {
        name: L.name, kind: L.kind, side: L.side || 'all', cls: L.cls, material: L.material,
        durBefore: L.dur, durMax: L.durMax, durAfter: L.dur, durOrig: L.durOrig,
        penIn: penIn, dmgIn: dmgIn, penOut: penIn, dmgOut: dmgIn,
        chance: null, roll: null, penetrated: false,
        durDmg: 0, blocked: false, blunt: 0, softBacking: false,
        bluntIn: null, bluntOut: null, bluntFactor: null,
        ricochet: false, ricochetChance: null, ricochetRoll: null,
        degraded: false
      };
      // —— R65（原文 Player.ProceedDamageThroughArmor L27873–27929）： ——
      // 前一层已 Blocked/Deflected 后，所有仍覆盖该部位的后续层只做
      //   Damage *= 该层 BluntThroughput（Heavy 再 ×(1−重型护甲技能)）；
      // 不调用 ApplyDamage：不判穿透、不算甲伤、不扣耐久、不套 +12 减伤系数。
      if (bluntCarry !== null) {
        var hvReduceAfter = heavyVestsReduce(L, ctx.heavyVestsLevel);
        var afterFactor = L.bluntThroughput * (1 - hvReduceAfter);
        var afterOut = bluntCarry * afterFactor;
        entry.afterBlock = true;
        entry.blocked = true;
        entry.penetrated = false;
        entry.chance = null;
        entry.roll = null;
        entry.durDmg = 0;
        entry.durAfter = L.dur;
        entry.bluntIn = bluntCarry;
        entry.bluntOut = afterOut;
        entry.bluntFactor = Math.round(afterFactor * 10000) / 10000;
        entry.blunt = afterOut;
        entry.armorType = L.armorType;
        entry.hvLevel = ctx.heavyVestsLevel || 0;
        entry.hvReduce = Math.round(hvReduceAfter * 10000) / 10000;
        entry.confidence = 'decompiled';
        entry.note = 'R65 原文：前层已挡下/跳弹，本层只做 Damage×BT，不判穿透、不算甲伤、不扣耐久';
        bluntCarry = afterOut;
        log.layers.push(entry);
        continue;
      }
      // 0 耐久：社区口径为「全穿透、无减伤」，无官方依据 → estimated（r17 保留行为、显式标注）
      if (L.dur <= 0) {
        entry.degraded = true;
        entry.zeroDurConfidence = 'estimated';
        entry.zeroDurNote = '耐久 0 的护甲按「无防护」处理是社区口径（estimated），非官方确认；下一层的结算照常进行';
        entry.chance = 1;
        entry.roll = rng();
        entry.penetrated = true;
        entry.penOut = st.pen;
        entry.dmgOut = st.dmg;
        log.layers.push(entry);
        continue;
      }
      // —— R62 跳弹（原文 ArmorComponent.Deflects + ApplyDamage）： ——
      // 头盔与插板都用自己的 RicochetVals（x/y/z）参与判定；跳弹成立后
      // Damage / ArmorDamage / Penetration 全部 ÷2，再走「被挡下」分支：
      // 仍按 P×AD×clamp(P/Resistance)×Destructibility 扣护甲耐久，
      // 并把半值伤害按 BT×钝伤缩放交给人体（不再「扣 1 点、钝伤归零」）。
      if ((L.kind === 'face' || L.kind === 'helmet' || L.kind === 'plate') && L.ricochet && ctx.angle > 0) {
        var rc = CS.ricochetChance(L.ricochet, ctx.angle);
        if (rc > 0) {
          entry.ricochetChance = rc;
          entry.ricochetAngle = ctx.angle;
          entry.ricochetParams = L.ricochet;
          var rroll = rng();
          entry.ricochetRoll = rroll;
          if (rroll < rc) {
            var halfPen = st.pen * 0.5;
            var halfDmg = st.dmg * 0.5;
            var halfArdPct = (ctx.ammo.ard || 0) / 200;
            var durPct = durRatio * 100;
            var factorA = CS.armorFactorA(L.cls, durPct);
            var mat = CS.MATERIAL_DESTRUCTIBILITY[L.material] || 0.375;
            var mode = ctx.armorDamageMode || CS.ARMOR_DMG_COEFF_MODE;
            var coeff = CS.armorDamageCoeff(halfPen, L.cls, false, mode);
            var durBase = halfPen * halfArdPct * coeff * mat;
            // R65（原文 ApplyDurabilityDamage）：float 直减，无 Round；下限 Mathf.Max(1f, num)。
            var rdmg = Math.max(1, durBase);
            if (rdmg > L.dur) { rdmg = L.dur; }
            L.dur = Math.max(0, L.dur - rdmg);
            var bluntScale = CS.armorBluntScale(halfPen, L.cls, durPct);
            var nonPlateBacking = (L.kind === 'plate' && hasNonPlateBacking(layers, ctx.part, i, dir));
            var hvReduce = heavyVestsReduce(L, ctx.heavyVestsLevel);
            var bluntFactor = L.bluntThroughput * (1 - hvReduce) * bluntScale;
            if (nonPlateBacking && CS.SOFT_LINER_PLATE_BLUNT_ENABLED) {
              bluntFactor = bluntFactor * CS.SOFT_LINER_PLATE_BLUNT_MUL;
            }
            var bluntOut = halfDmg * bluntFactor;
            log.dmgToArmor += rdmg;
            entry.ricochet = true;
            entry.durDmg = rdmg;
            entry.durAfter = L.dur;
            entry.durBase = Math.round(durBase * 100) / 100;
            entry.durCoeff = Math.round(coeff * 10000) / 10000;
            entry.durMode = mode;
            entry.factorA = Math.round(factorA * 1000) / 1000;
            entry.durPct = Math.round(durPct * 100) / 100;
            entry.blocked = true;
            entry.penetrated = false;
            entry.blunt = bluntOut;
            entry.bluntScale = Math.round(bluntScale * 10000) / 10000;
            entry.bluntBase = halfDmg * L.bluntThroughput * bluntScale;
            entry.bluntFactor = Math.round(bluntFactor * 10000) / 10000;
            entry.softBacking = nonPlateBacking;
            entry.armorType = L.armorType;
            entry.hvLevel = ctx.heavyVestsLevel || 0;
            entry.hvReduce = Math.round(hvReduce * 10000) / 10000;
            entry.penOut = halfPen;
            entry.dmgOut = halfDmg;
            entry.durConfidence = 'estimated';
            entry.ricochetNote = '原文：Damage/ArmorDamage/Penetration ÷2 后按挡下分支结算';
            log.layers.push(entry);
            log.penetrated = false;
            log.stoppedBy = 'ricochet';
            log.ricochet = true;
            log.blunt = true;
            log.dmgToPart += bluntOut;
            log.penAfter = halfPen;
            log.dmgAfter = halfDmg;
            return log;
          }
        }
      }
      // R19.8e：穿透概率按 Ballistics.cs PenetrationChance（Desmos m8cmsfokkl），
      // 耐久% = 当前耐久 / 出厂原始满耐久（站点是 当前/当前上限，本项目按用户口径保留 durOrig）
      var chance = ctx.penChanceFn(st.pen, L.cls, L.dur, L.durMax, L.durOrig);
      if (typeof chance !== 'number' || !isFinite(chance)) { chance = 0; }
      chance = clamp(chance, 0, 1);
      var roll = rng();
      var penetrated = roll < chance;
      var durPct = durRatio * 100;
      var factorA = CS.armorFactorA(L.cls, durPct);
      var mat = CS.MATERIAL_DESTRUCTIBILITY[L.material] || 0.375;
      var ardPct = (ctx.ammo.ard || 0) / 100;
      var mode = ctx.armorDamageMode || CS.ARMOR_DMG_COEFF_MODE;
      // —— R62 耐久伤害（原文 Armor.ApplyDamage）：
      //   P × 甲伤% × clamp(P / Resistance, 击穿 0.5–0.9 / 挡下 0.6–1.1) × Destructibility，
      //   Resistance = 10×AC（0 级为 1），最低 1 点。
      //   旧 site / video 模式仅作为可选对照保留，默认不启用。
      var coeff = CS.armorDamageCoeff(st.pen, L.cls, penetrated, mode);
      // R65（原文 ApplyDurabilityDamage）：float 直减，无 Round；下限 Mathf.Max(1f, num)。
      var durBase = st.pen * ardPct * coeff * mat;
      var durDmg = Math.max(1, durBase);
      // R19.8e：内衬耐久伤害 = 自身伤害 × 上一层硬质护甲的击穿概率
      // （Ballistics.cs V2：expectedSoftDurabilityDamage *= platePenetrationChance）；
      // 在取整前缩放，低于 0.01 视为 0 —— 插板没穿时内衬几乎不掉耐久。
      if (L.kind === 'liner' && lastHardChance !== null) {
        var linerScaled = Math.max(1, durBase) * lastHardChance;
        durDmg = linerScaled < 0.01 ? 0 : linerScaled;   // R65：保持浮点，展示层再取整
      }
      if (durDmg > L.dur) { durDmg = L.dur; }   // 实际扣减不超过剩余耐久（实现上限，estimated）
      L.dur = Math.max(0, L.dur - durDmg);
      log.dmgToArmor += durDmg;
      entry.chance = chance;
      entry.roll = roll;
      entry.penetrated = penetrated;
      entry.durDmg = durDmg;
      entry.durAfter = L.dur;
      entry.durBase = Math.round(durBase * 100) / 100;
      entry.durCoeff = Math.round(coeff * 10000) / 10000;
      entry.durMode = mode;
      entry.factorA = Math.round(factorA * 1000) / 1000;
      entry.durPct = Math.round(durPct * 100) / 100;
      entry.linerDurScale = (L.kind === 'liner' && lastHardChance !== null)
        ? Math.round(lastHardChance * 10000) / 10000 : 1;
      entry.durConfidence = 'estimated';                  // 社区反查公式，非官方公布
      if (L.kind !== 'liner') { lastHardChance = chance; }
      if (penetrated) {
        // R19.8e：Ballistics.cs CalculateReductionFactor = clamp(P/(FactorA+12), 0.6, 1)。
        // 多层穿透时 P、D 都乘以同一系数（不再是固定 -1 点）。
        var rf = CS.armorReductionFactor(st.pen, L.cls, durPct);
        st.dmg = st.dmg * rf;
        st.pen = st.pen * rf;
        entry.penOut = st.pen;
        entry.dmgOut = st.dmg;
        entry.reduceFactor = Math.round(rf * 10000) / 10000;
        // R65：本层被穿透时不存在「已挡下钝伤链」（后继层已在循环顶部短路），
        // 因此这里不再携带 bluntCarry。
      } else {
        // R65：第一层挡下（bluntCarry 必为 null，后继层已在循环顶部短路）。
        // 该层钝伤 = 当前伤害 × BT × 钝伤缩放项；Heavy 层再乘 (1−重型护甲技能)。
        // 0.12 的「插板 ×0.6」默认停用（0.13 由后继层各自 BT 承担），仅保留对照开关。
        var bluntScale = CS.armorBluntScale(st.pen, L.cls, durPct);
        var nonPlateBacking = (L.kind === 'plate' && hasNonPlateBacking(layers, ctx.part, i, dir));
        var hvReduce = heavyVestsReduce(L, ctx.heavyVestsLevel);
        var bluntFactor = L.bluntThroughput * (1 - hvReduce) * bluntScale;
        entry.bluntLayers = [];
        if (nonPlateBacking && CS.SOFT_LINER_PLATE_BLUNT_ENABLED) {
          bluntFactor = bluntFactor * CS.SOFT_LINER_PLATE_BLUNT_MUL;
          entry.softBacking = true;
          entry.bluntLayers.push({ name: 'non-plate', kind: 'backing',
                                   mul: CS.SOFT_LINER_PLATE_BLUNT_MUL });
        }
        var bluntIn = null;
        var bluntOut = st.dmg * bluntFactor;   // R65：只有第一层挡下会产出钝伤
        entry.blocked = true;
        entry.bluntScale = Math.round(bluntScale * 10000) / 10000;
        entry.bluntBase = st.dmg * L.bluntThroughput * bluntScale;
        entry.bluntIn = bluntIn;
        entry.bluntOut = bluntOut;
        entry.bluntFactor = Math.round(bluntFactor * 10000) / 10000;
        entry.armorType = L.armorType;
        entry.hvLevel = ctx.heavyVestsLevel || 0;
        entry.hvReduce = Math.round(hvReduce * 10000) / 10000;
        entry.blunt = bluntOut;
        bluntCarry = bluntOut;
        log.blunt = true;
        log.stoppedBy = 'armor';
        log.layers.push(entry);
        continue;   // 关键：不终止，继续把钝伤送入下一层（后继层只乘 BT）
      }
      log.layers.push(entry);
    }

    // —— R19.8f：护甲挡住后的最终钝伤：只把钝伤链的最后一层输出交给人体 ——
    if (bluntCarry !== null) {
      log.dmgToPart += bluntCarry;
      log.penetrated = false;
      log.stoppedBy = 'armor';
      log.penAfter = st.pen;
      log.dmgAfter = st.dmg;
      log.bluntChain = bluntCarry;
      return log;
    }

    // —— 3. 未被挡住：剩余伤害进入人体 ——
    log.dmgToPart += st.dmg;
    log.bodyEntry = true;
    log.penetrated = log.layers.length ? true : null;
    log.penAfter = st.pen;
    log.dmgAfter = st.dmg;

    // —— 4.（可选，默认关闭）入体之后的躯干出口 / 对侧插板二次碰撞 ——
    // 独立后续事件：发生在人体伤害结算之后，只改对侧插板耐久并单独记账；
    // 绝不把它当成本发入体前的防护层，也不参与任何减伤计算。
    if (ctx.exitModel === 'estimate') {
      var opp = oppositeDir(dir);
      var hit = null;
      for (var q = 0; q < layers.length; q++) {
        var X = layers[q];
        if (X.kind === 'plate' && covers(X, ctx.part) && X.side === opp && X.cls > 0 && X.dur > 0) {
          hit = X;
          break;
        }
      }
      if (hit) {
        var ePen = st.pen * CS.EST_EXIT_PEN_KEEP;
        var eDmg = st.dmg * CS.EST_EXIT_DMG_KEEP;
        var eChance = ctx.penChanceFn(ePen, hit.cls, hit.dur, hit.durMax, hit.durOrig);
        if (typeof eChance !== 'number' || !isFinite(eChance)) { eChance = 0; }
        eChance = clamp(eChance, 0, 1);
        var eRoll = rng();
        var ePenetrated = eRoll < eChance;
        var eMat = CS.MATERIAL_DESTRUCTIBILITY[hit.material] || 0.375;
        // 与主护甲口径一致（原始满耐久分母 / site|video 甲伤系数）
        var eDurPct = 100 * (hit.durOrig > 0 ? hit.dur / hit.durOrig : 1);
        var eMode = ctx.armorDamageMode || CS.ARMOR_DMG_COEFF_MODE;
        var eCoeff = CS.armorDamageCoeff(ePen, hit.cls, ePenetrated, eMode);
        var eDur = Math.max(1, Math.round(
          ePen * ((ctx.ammo.ard || 0) / 100) * eMat * eCoeff));
        if (eDur > hit.dur) { eDur = hit.dur; }
        var eBefore = hit.dur;
        hit.dur = Math.max(0, hit.dur - eDur);
        log.dmgToArmor += eDur;
        log.exit = {
          phase: 'after-body', plate: hit.name, side: hit.side,
          chance: eChance, roll: eRoll, penetrated: ePenetrated,
          penIn: ePen, dmgIn: eDmg, durBefore: eBefore, durAfter: hit.dur, durDmg: eDur,
          durCoeff: Math.round(eCoeff * 10000) / 10000, durMode: eMode,
          factorA: Math.round(CS.armorFactorA(hit.cls, eDurPct) * 1000) / 1000,
          confidence: 'estimated',
          note: '入体后的二次碰撞估算：只影响对侧插板耐久，不改变本发人体伤害'
        };
      }
    }
    return log;
  }

  // —— 伤害入体：分部位 HP / 摧毁规则 / 溢出分摊 ——
  function applyDamage(target, part, dmg, log) {
    if (dmg <= 0 || target.dead) { return; }
    var p = target.parts[part];
    if (!p) { return; }
    if (p.hp > 0) {
      var applied = Math.min(p.hp, dmg);
      p.hp -= applied;
      var spill = dmg - applied;
      if (spill > 0) { overflow(target, part, spill, log); }
    } else {
      // 已摧毁部位（黑化）：按 wiki Health_system 的分散比例，把这一发的伤害分摊给其余存活部位
      // （手臂 0.49× / 腿 0.7× / 胃 1.05×，verified；头/胸黑化后不再结算——已即死）
      var mul = (part === 'stomach') ? CS.STOMACH_OVERFLOW
        : (part === 'leftLeg' || part === 'rightLeg') ? CS.LEG_OVERFLOW
        : CS.LIMB_OVERFLOW;
      if (part === 'head' || part === 'chest') { return; }   // 头/胸摧毁已即死
      overflow(target, part, dmg * mul, log);
    }
    if ((part === 'head' || part === 'chest') && p.hp <= 0) {
      target.dead = true;
      target.deathCause = part + ' destroyed';
    }
    if (!target.dead) {
      var total = 0;
      for (var k in target.parts) { if (Object.prototype.hasOwnProperty.call(target.parts, k)) { total += target.parts[k].hp; } }
      target.total = total;
      if (total <= 0) { target.dead = true; target.deathCause = 'total hp 0'; }
    }
    log.killed = target.dead;
  }

  function overflow(target, fromPart, dmg, log) {
    // 分摊到未摧毁部位（均摊，简化实现；fandom 仅给出 0.49×/1.05× 比例）
    var alive = [];
    for (var k in target.parts) {
      if (Object.prototype.hasOwnProperty.call(target.parts, k) && target.parts[k].hp > 0 && k !== fromPart) { alive.push(k); }
    }
    if (!alive.length) { return; }
    var each = dmg / alive.length;
    log.overflow = { from: fromPart, dmg: dmg, to: alive.slice(), each: each };
    for (var i = 0; i < alive.length; i++) {
      var p = target.parts[alive[i]];
      p.hp = Math.max(0, p.hp - each);
      if ((alive[i] === 'head' || alive[i] === 'chest') && p.hp <= 0) {
        target.dead = true;
        target.deathCause = alive[i] + ' destroyed by overflow';
      }
    }
  }

  // 穿过人体碰撞箱后可能继续命中的部位（估算映射，estimated；head/chest 无后续）
  CS.THROUGH_BODY_NEXT = { leftArm: 'chest', rightArm: 'chest', leftLeg: 'stomach', rightLeg: 'stomach', stomach: 'chest' };

  // —— 主入口 ——
  // cfg = {
  //   magazine: [ammoObj...]            混压弹匣（顺序即射击顺序，耗尽即停）
  //   rpm: 射速（必填 > 0；r15 起不再使用 600 兜底）, dist: 距离 m,
  //   dir: 'front'|'back'|'left'|'right'  射击方向（缺省 front）——决定经过哪些护甲层
  //   exitModel: 'off'|'estimate'       入体后对侧插板二次碰撞（缺省 off，估算模型）
  //   constraints: { ammo:[id...], magazines:[id...], hasMagSlot:bool }
  //                                     非空白名单即硬校验：非法弹药/弹匣直接抛错
  //   magazineId: 当前弹匣物品 ID（配合 constraints 校验）
  //   flightFn: (ammo, dist) -> {speed, pen, dmg}   缺省不衰减
  //   penChanceFn: (pen, cls, dur, durMax, durOrig) -> 0..1  必填（app.js 传 amArmorPenChance）
  //   armorDamageMode: 'decomp' | 'site' | 'video'  甲伤系数写法（缺省 'decomp' = 反编译原文）
  //   penJitter: true | 'normal' | 'uniform' | false 穿透浮动：缺省关闭；
  //             true/'normal' = N(pen, ammo.penDev)，'uniform' = 旧 ±1（仅调试）
  //   penDeviation: number                 弹药未带 penDev 时的兜底 σ（缺省 1，降级）
  //   fragmentation: true | false          碎片化（缺省 false；社区经验模型，见 CS.FRAG_*）
  //   heavyVestsLevel: 0–50                重型护甲技能等级（缺省 0 = 不影响；仅 ArmorType=Heavy）
  //                                      reduction = level × 0.004（globals 每级值），钝伤 BT ×(1−reduction)
  //   angle: 0–90                          弹道与表面法线夹角（跳弹判定；头盔/插板有效）
  //   targetPartHp: {head:35, chest:85, ...}        目标分部位 HP
  //   armorLayers: [ {name,kind,zones,side,cls,dur,durMax,material,bluntThroughput,ricochet} ... ]
  //   barriers:    [ {id,n,material,penChanceMul,dmgKeep,penKeep,ricochetMul} ... ]
  //   hitProfile: {mode:'fixed', part:'chest'} | {mode:'dist', weights:{chest:0.5,...}}
  //   maxShots: 上限（缺省 = 弹匣容量）
  //   seed: 随机种子（可复现）
  // }
  CS.simulate = function (cfg) {
    if (!cfg || !cfg.penChanceFn) { throw new Error('penChanceFn required'); }
    if (!(cfg.rpm > 0)) { throw new Error('rpm required (>0)'); }
    var cons = cfg.constraints || null;
    if (cons) {
      var allowAmmo = cons.ammo;
      if (allowAmmo && allowAmmo.length !== undefined) {
        for (var ai = 0; ai < (cfg.magazine || []).length; ai++) {
          var rid = (cfg.magazine[ai] || {}).id;
          if (allowAmmo.indexOf(rid) < 0) {
            throw new Error('ammo not allowed by gun: ' + rid);
          }
        }
      }
      if (cfg.magazineId && cons.hasMagSlot === false) {
        throw new Error('gun has no detachable magazine: ' + cfg.magazineId);
      }
      if (cfg.magazineId && cons.magazines && cons.magazines.length !== undefined) {
        if (cons.magazines.indexOf(cfg.magazineId) < 0) {
          throw new Error('magazine not allowed by gun: ' + cfg.magazineId);
        }
      }
    }
    var dir = cfg.dir || 'front';
    if (!AM_DIRS[dir] && dir !== 'front') { dir = 'front'; }
    var angle = (typeof cfg.angle === 'number' && isFinite(cfg.angle))
      ? clamp(cfg.angle, 0, 90) : 0;
    var rng = CS.rng32(cfg.seed || 1);
    var flight = cfg.flightFn || CS.defaultFlight;
    var layers = sortArmorLayers(CS.createArmorLayers(cfg.armorLayers));
    var barriers = CS.createBarriers(cfg.barriers);
    var target = CS.createTarget(cfg.targetPartHp);
    var mag = CS.createMagazine(cfg.magazine || []);
    var dt = 60000 / cfg.rpm;
    var shots = [];
    var t = 0;
    // r17s4：命中率（可选）。chance>=1 恒命中、<=0 恒不命中，两种边界都不额外消耗 rng，
    // 因此 100% 模式的逐发日志与「关闭命中率」完全一致。
    var hitChance = null;
    if (typeof cfg.hitChance === 'number' && isFinite(cfg.hitChance)) {
      hitChance = Math.max(0, Math.min(1, cfg.hitChance));
    }
    var hitCount = 0, missCount = 0, fragCount = 0;

    function pickPart() {
      var hp = cfg.hitProfile;
      if (!hp || hp.mode === 'fixed') { return hp && hp.part ? hp.part : 'chest'; }
      // 权重按总和归一化（UI 传入的是原始百分比，总和未必为 1）
      var keys = [], sum = 0;
      for (var k in hp.weights) {
        if (Object.prototype.hasOwnProperty.call(hp.weights, k)) {
          var v = Number(hp.weights[k]);
          if (isFinite(v) && v > 0) { keys.push([k, v]); sum += v; }
        }
      }
      if (!keys.length || sum <= 0) { return 'chest'; }
      var r = rng() * sum;
      var acc = 0;
      for (var i = 0; i < keys.length; i++) {
        acc += keys[i][1];
        if (r <= acc) { return keys[i][0]; }
      }
      return keys[keys.length - 1][0];
    }

    var n = 0;
    while (mag.pos < mag.rounds.length) {
      if (cfg.maxShots && n >= cfg.maxShots) { break; }
      if (target.dead) { break; }
      var ammo = mag.rounds[mag.pos];
      mag.pos++;
      n++;
      t += dt;
      var terminal = flight(ammo, cfg.dist || 0);
      // R62：原文 CreateShot = Normal(PenetrationPower, PenetrationPowerDiviation)。
      // 'uniform' 仅保留为旧口径调试选项（±1），默认不再使用。
      var penBase = terminal.pen;
      var penRoll = 0;
      var penJitterMode = null;
      var penDev = 0;
      var penDevSource = null;
      if (cfg.penJitter === 'uniform') {
        penJitterMode = 'uniform';
      } else if (cfg.penJitter) {
        penJitterMode = 'normal';
      }
      if (penJitterMode === 'uniform') {
        penRoll = rng() * 2 - 1;
        penDevSource = 'legacy-uniform';
        terminal = Object.assign({}, terminal, { pen: Math.max(0, penBase + penRoll) });
      } else if (penJitterMode) {
        if (typeof ammo.penDev === 'number' && isFinite(ammo.penDev)) {
          penDev = ammo.penDev;
          penDevSource = 'game-truth';
        } else if (typeof cfg.penDeviation === 'number' && isFinite(cfg.penDeviation)) {
          penDev = cfg.penDeviation;
          penDevSource = 'cfg';
        } else {
          penDev = 1;   // 降级：官方模板缺失时退回 ±1 量级（台账标注）
          penDevSource = 'fallback-sigma1';
        }
        penRoll = CS.normalRandom(rng, 0, penDev);
        terminal = Object.assign({}, terminal, { pen: Math.max(0, penBase + penRoll) });
      }
      // 每发独立命中判定：未命中 → 不进入护甲/人体结算（掩体逻辑仍在 resolveShot 内照常执行）
      var hit = true;
      if (hitChance !== null) {
        hit = (hitChance >= 1) ? true : (hitChance <= 0 ? false : (rng() < hitChance));
      }
      if (hit) { hitCount++; } else { missCount++; }
      // 多弹丸（霰弹 pc>1）：每颗独立判定，逐颗至少 1 点耐久损伤
      var pellets = Math.max(1, ammo.pc || 1);
      var shotLog = { n: n, timeMs: Math.round(t), ammoId: ammo.id, ammoName: ammo.n,
                      hit: hit, miss: !hit, part: hit ? pickPart() : null, dir: dir,
                      angle: angle, penBase: penBase, penRoll: Math.round(penRoll * 1000) / 1000,
                      penUsed: terminal.pen, penJitterMode: penJitterMode,
                      penDev: penDev, penDevSource: penDevSource,
                      pellets: [], dmgToPart: 0, dmgToArmor: 0 };
      for (var pi = 0; pi < pellets && !target.dead; pi++) {
        var sub = resolveShot({ ammo: ammo, terminal: terminal, part: shotLog.part,
                                dir: dir, layers: layers, barriers: barriers, rng: rng,
                                angle: angle,
                                exitModel: cfg.exitModel === 'estimate' ? 'estimate' : 'off',
                                missTarget: !hit,
                                armorDamageMode: cfg.armorDamageMode,
                                heavyVestsLevel: cfg.heavyVestsLevel,
                                penChanceFn: cfg.penChanceFn });
        sub.pellet = pellets > 1 ? pi + 1 : null;
        // —— R63：可选碎片化（默认关闭；社区经验模型，官方原文未给出碎片数→伤害映射） ——
        // 仅当本发击穿全部护甲、真正进入人体时判定；概率取弹药 FragmentationChance（frag）。
        // 社区服务端 Ballistics.cs：pen < 20 → 概率强制 0。触发时按「1 片、+0.5×入体伤害」保守结算。
        if (cfg.fragmentation && hit && sub.bodyEntry && sub.dmgToPart > 0) {
          var fc = (typeof ammo.frag === 'number' && isFinite(ammo.frag)) ? clamp(ammo.frag, 0, 1) : 0;
          var penForFrag = (typeof ammo.pen === 'number' && isFinite(ammo.pen)) ? ammo.pen : 0;
          if (penForFrag < CS.FRAG_MIN_PEN) { fc = 0; }
          var fragRoll = rng();
          var fragHit = fragRoll < fc;
          var fragExtra = fragHit ? sub.dmgToPart * CS.FRAG_EXTRA_MUL : 0;
          sub.frag = {
            chance: Math.round(fc * 10000) / 10000,
            roll: Math.round(fragRoll * 10000) / 10000,
            triggered: fragHit,
            extra: Math.round(fragExtra * 100) / 100,
            mul: CS.FRAG_EXTRA_MUL,
            fragments: fragHit ? 1 : 0,
            pen: penForFrag, penGate: CS.FRAG_MIN_PEN,
            confidence: 'estimated',
            note: '社区经验模型：pen<20 概率归零；触发按 1 片、+0.5×入体伤害；官方原文未给出碎片数→伤害映射'
          };
          if (fragExtra > 0) { sub.dmgToPart += fragExtra; }
          if (fragHit) { fragCount++; }
        }
        shotLog.pellets.push(sub);
        shotLog.dmgToPart += sub.dmgToPart;
        shotLog.dmgToArmor += sub.dmgToArmor;
        if (hit && !target.dead) { applyDamage(target, shotLog.part, sub.dmgToPart, sub); }
        // —— r17 补充：穿过人体碰撞箱的估算续命中（默认关闭） ——
        // 只在「护甲全穿、弹体入体、目标未死」时发生一次；新部位按正常命中语义结算，
        // 绝不套用黑化分散倍率；不重算新部位护甲（出侧护甲由 exitModel 单独负责）。
        if (cfg.throughBody === 'estimate' && sub.bodyEntry && !sub.stoppedBy && !target.dead) {
          var nextPart = CS.THROUGH_BODY_NEXT[shotLog.part] || null;
          var contDmg = sub.dmgToPart * CS.EST_THROUGH_BODY_DMG_KEEP;
          if (nextPart && contDmg > 0 && target.parts[nextPart]) {
            sub.throughBody = {
              from: shotLog.part, to: nextPart,
              dmgIn: Math.round(sub.dmgToPart * 100) / 100, dmg: Math.round(contDmg * 100) / 100,
              dmgKeep: CS.EST_THROUGH_BODY_DMG_KEEP, penKeep: CS.EST_THROUGH_BODY_PEN_KEEP,
              confidence: 'estimated',
              note: '穿过人体碰撞箱的估算续命中：弹体衰减后按正常命中结算，不套用黑化倍率'
            };
            applyDamage(target, nextPart, contDmg, sub);
          }
        }
        if (sub.killed || target.dead) {
          shotLog.death = true;
          shotLog.deathCause = target.deathCause;
          shotLog.killedAt = n;
          break;
        }
      }
      shots.push(shotLog);
    }
    return {
      shots: shots, shotCount: shots.length,
      hits: hitCount, misses: missCount, hitChance: hitChance,
      fragCount: fragCount,
      models: {
        flight: (flight === CS.defaultFlight) ? 'none' : 'approx',
        fragmentation: !!cfg.fragmentation,
        fragMinPen: CS.FRAG_MIN_PEN, fragExtraMul: CS.FRAG_EXTRA_MUL,
        heavyVestsLevel: (typeof cfg.heavyVestsLevel === 'number' ? cfg.heavyVestsLevel : 0),
        hvReducePerLevel: CS.HV_REDUCE_PER_LEVEL, hvMaxLevel: CS.HV_MAX_LEVEL,
        flightSource: 'G1-like drag + 50 m zero (approx, not decompiled)',
        fragSource: 'community Ballistics.cs (estimated; official mapping unknown)',
        hvSource: 'globals SkillsSettings.HeavyVests (BluntThroughputDamageHVestsReducePerLevel=0.004)'
      },
      dead: target.dead, deathCause: target.deathCause,
      killedAt: target.dead ? shots.length : null,
      timeMs: Math.round(t),
      targetFinal: target,
      armorFinal: layers.map(function (L) {
        return { name: L.name, kind: L.kind, dur: L.dur, durMax: L.durMax };
      }),
      barriers: barriers.map(function (B) { return { id: B.id, name: B.n, material: B.material }; }),
      roundsLeft: mag.rounds.length - mag.pos
    };
  };

  global.CS = CS;
  if (typeof module !== 'undefined' && module.exports) { module.exports = CS; }
})(typeof window !== 'undefined' ? window : globalThis);
