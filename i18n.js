/* ============================================================================
 * i18n.js —— 全项目中文显示层（R19.22）
 *
 * 设计原则（对应任务书第三部分）：
 *   1. 原始数据一字不改：物品 / 商人 / 地图 / 任务的英文名只用于「浮窗原文」。
 *   2. 中文优先：界面上能命中的英文一律替换为中文显示。
 *   3. 原文可查：被替换的元素自动带 title=原始英文（已有 title 的不覆盖，
 *      改为追加在末尾，避免把功能提示顶掉）。
 *   4. 统一机制：所有页面共用这一套（主程序 4 个视图 + 校准器 + 任务模块），
 *      不给任何单页写第二套逻辑。
 *   5. 动态内容：MutationObserver 监听新增/变更节点，异步合并成一次批处理
 *      （requestAnimationFrame），大表格重绘不会逐节点抖动。
 *   6. 可统计：scan() 记录「见过但没字典」的英文，供覆盖率报告与测试断言。
 *
 * 对外接口（window.GWI18n）：
 *   load()                  → Promise（加载 data/i18n/*.json）
 *   tr(text)                → 中文（没有映射返回 null）
 *   localize(root)          → 就地中文化 root 子树，返回替换条数
 *   start()                 → 开启 MutationObserver
 *   nameZh(kind, key)       → kind = trader | task | map | item | slot
 *   enOf(el)                → 元素对应的原始英文
 *   coverage()              → {translated, unmapped, entries, ...}
 *   reportUnmapped()        → 未覆盖英文清单（测试 / 报告用）
 * ==========================================================================*/
(function () {
  "use strict";

  var DATA = {
    ui: null,        // {entries, patterns, keptEnglish}
    names: null,     // {traders:{en:zh}, tasks:{en:zh}, maps:{id:zh}, items:{en:zh}}
    items: null      // data/i18n/items-zh.json：英文物品名 → 中文
  };

  var state = {
    loaded: false,
    loading: null,
    entries: {},     // 直接查表：en → zh
    patterns: [],    // [{re, zh}]
    nameTables: { trader: {}, task: {}, map: {}, item: {}, slot: {} },
    kept: {},        // 白名单：en → 原因分类（命中则**一律不翻译**）
    poiEntries: {},  // 地图 POI 地名（独立一份，供地图标签显式取中文）
    translated: 0,   // 累计替换次数
    unmapped: {},    // en → {count, where}
    observer: null,
    pending: null,
    seen: typeof WeakMap === "function" ? new WeakMap() : null,
    stats: { nodes: 0, attrs: 0 }
  };

  var CJK = /[\u3400-\u9fff]/;
  var LATIN = /[A-Za-z]{2,}/;

  function norm(s) {
    return String(s == null ? "" : s).replace(/\s+/g, " ").trim();
  }

  function isLatinOnly(s) {
    return !!s && LATIN.test(s) && !CJK.test(s);
  }

  // ---------------------------------------------------------------- 加载
  function fetchJSON(url) {
    return fetch(url, { cache: "no-cache" }).then(function (r) {
      if (!r.ok) { throw new Error("HTTP " + r.status + " " + url); }
      return r.json();
    });
  }

  function load() {
    if (state.loaded) { return Promise.resolve(state); }
    if (state.loading) { return state.loading; }
    state.loading = Promise.all([
      fetchJSON("data/i18n/ui-zh.json").catch(function () { return { entries: {} }; }),
      fetchJSON("data/i18n/names.json").catch(function () { return {}; }),
      fetchJSON("data/i18n/items-zh.json").catch(function () { return { items: {} }; }),
      fetchJSON("data/i18n/poi-zh.json").catch(function () { return { entries: {} }; })
    ]).then(function (res) {
      DATA.ui = res[0] || {};
      DATA.names = res[1] || {};
      DATA.items = res[2] || {};
      DATA.poi = res[3] || {};
      buildTables();
      state.loaded = true;
      state.loading = null;
      return state;
    }).catch(function (err) {
      // 字典缺失绝不能让页面挂掉：退化为「原样显示 + 空映射」
      state.loaded = true;
      state.loading = null;
      state.loadError = String(err && err.message || err);
      return state;
    });
    return state.loading;
  }

  function buildTables() {
    var ui = DATA.ui || {};
    state.entries = {};
    // 地图 POI 地名与界面词条同一个查表（都走 tr()），避免两套机制。
    // R297：另外单独留一份 poiEntries —— 地图标签改为显式查它并打 data-i18n-skip，
    // 这样「Mechanic」作为地名仍显示「机修区」，作为商人名则被白名单挡住保持英文。
    state.poiEntries = {};
    Object.keys((DATA.poi && DATA.poi.entries) || {}).forEach(function (k) {
      state.poiEntries[norm(k)] = DATA.poi.entries[k];
      state.entries[norm(k)] = DATA.poi.entries[k];
    });
    Object.keys(ui.entries || {}).forEach(function (k) { state.entries[norm(k)] = ui.entries[k]; });
    var names = DATA.names || {};
    state.nameTables.trader = names.traders || {};
    state.nameTables.task = names.tasks || {};
    state.nameTables.map = names.maps || {};
    state.nameTables.item = Object.assign({}, names.items || {},
      (DATA.items && DATA.items.items) || {});
    state.nameTables.slot = names.slots || {};
    state.patterns = [];
    (ui.patterns || []).forEach(function (p) {
      try {
        state.patterns.push({ re: new RegExp(p.pattern), zh: p.zh });
      } catch (e) { /* 坏正则跳过，不影响其它条目 */ }
    });
    state.kept = {};
    var why = (ui.keptEnglish && ui.keptEnglish.why) || {};
    Object.keys(why).forEach(function (k) { state.kept[k] = why[k]; });
    // 白名单里的具体字样（型号 / 标识）也登记，避免统计成遗漏
    (ui.keptEnglish && ui.keptEnglish.entries || []).forEach(function (e) { state.kept[e] = "whitelist"; });
  }

  // ---------------------------------------------------------------- 翻译
  function tr(text) {
    var s = norm(text);
    if (!s) { return null; }
    // R297：白名单（商人名 / Boss 代号 / 型号 / 口径 …）优先且**硬性不翻译**。
    // 之前白名单只用于「未翻译统计」，实际仍会命中词表 —— 商人 Mechanic 因此被
    // 地图 POI 表翻成「机修区」，用户明确要求商人名显示英文原名。
    if (state.kept[s]) { return null; }
    if (state.entries[s] != null) { return state.entries[s]; }
    for (var i = 0; i < state.patterns.length; i++) {
      var p = state.patterns[i];
      if (p.re.test(s)) { return s.replace(p.re, p.zh); }
    }
    return null;
  }

  /** 数据驱动名称：按 kind 查表；en 本身就是中文时原样返回。 */
  function nameZh(kind, key) {
    var table = state.nameTables[kind] || {};
    if (!key) { return ""; }
    if (table[key]) { return table[key]; }
    return key;
  }

  /** 地图地名专用：只查 POI 表，不受白名单约束。
   *  地图标签显式调用并打 data-i18n-skip，这样同名商人（Mechanic）不会互相污染，
   *  地名仍能显示「机修区」。 */
  function poiZh(text) {
    var s = norm(text);
    if (!s) { return null; }
    return state.poiEntries[s] || null;
  }

  function enOf(el) {
    if (!el || !el.getAttribute) { return ""; }
    return el.getAttribute("data-en-text") || el.getAttribute("title") || "";
  }

  function markOriginal(el, en) {
    if (!el || !en) { return; }
    if (!el.getAttribute("data-en-text")) { el.setAttribute("data-en-text", en); }
    var title = el.getAttribute("title");
    if (!title) {
      el.setAttribute("title", en);
    } else if (title.indexOf(en) < 0) {
      // 已有功能提示（例如「关闭（Esc）」）时不覆盖，原文附在末尾
      el.setAttribute("title", title + " · " + en);
    }
  }

  function shouldSkip(el) {
    if (!el) { return true; }
    if (el.hasAttribute && el.hasAttribute("data-i18n-skip")) { return true; }
    // SVG 里的 <style> 是小写 tagName，必须统一转大写再比（否则会把内联样式当成界面文字）
    var tag = String(el.tagName || "").toUpperCase();
    if (tag === "SCRIPT" || tag === "STYLE" || tag === "NOSCRIPT" || tag === "TEMPLATE") { return true; }
    if (el.namespaceURI === "http://www.w3.org/2000/svg" && tag === "STYLE") { return true; }
    return false;
  }

  /** 「合理保留英文」判定（与 tools/build_i18n.py 的 kept_reason 保持同一套规则）。
   *  型号 / 口径 / 罗马数字 / 版本号 / 内部 id / 来源标识不算翻译遗漏。 */
  function isKept(s) {
    if (/^rev R\d/.test(s)) { return true; }
    if (/^[IVX]+$/.test(s)) { return true; }
    if (/^[IVX]+ · [\d\s  ₽]+$/.test(s)) { return true; }
    if (/^[\d\.][\w\.\s]*·\s*\d+$/.test(s)) { return true; }
    if (/^[\w/]+ r-?\d+c\d+ → r-?\d+c\d+$/.test(s)) { return true; }
    if (/^[A-Za-z0-9_]+$/.test(s) && s.indexOf("_") >= 0) { return true; }
    if (/^[0-9a-f]{24}$/.test(s)) { return true; }
    if (["LEDX", "PvP", "PvE", "Scav", "PDW", "BTR"].indexOf(s) >= 0) { return true; }
    if (s.indexOf("tarkov-dev") >= 0 || s.indexOf("the-hideout") >= 0) { return true; }
    if (/\d/.test(s) && /[A-Z][a-z]+/.test(s)) { return true; }
    if (/^[A-Z][A-Za-z]+( [A-Za-z]+)*\.$/.test(s)) { return true; }
    if (/^\.[\w\s\.]+$/.test(s)) { return true; }      // .45 ACP 这类口径
    if (/^\d+[A-Za-z0-9]+$/.test(s)) { return true; }  // 20x1mm
    return false;
  }

  function translateTextNode(node) {
    var el = node.parentElement;
    if (!el || shouldSkip(el)) { return 0; }
    var raw = node.nodeValue;
    if (!raw || !isLatinOnly(raw)) { return 0; }
    var zh = tr(raw);
    if (zh == null || zh === raw) { return 0; }
    // 保留原有前后空白，避免影响布局（inline 元素之间的空格）
    var lead = raw.match(/^\s*/)[0];
    var tail = raw.match(/\s*$/)[0];
    node.nodeValue = lead + zh + tail;
    markOriginal(el, norm(raw));
    state.translated++;
    state.stats.nodes++;
    return 1;
  }

  var ATTRS = ["title", "placeholder", "aria-label", "alt", "data-tip"];

  function translateAttrs(el) {
    var n = 0;
    for (var i = 0; i < ATTRS.length; i++) {
      var a = ATTRS[i];
      if (!el.hasAttribute || !el.hasAttribute(a)) { continue; }
      var v = el.getAttribute(a) || "";
      if (!isLatinOnly(v)) { continue; }
      var zh = tr(v);
      if (zh == null || zh === v) { continue; }
      if (a === "title") {
        // title 既是浮窗又是原文载体：原文留在 data-en-text，title 显示中文
        if (!el.getAttribute("data-en-text")) { el.setAttribute("data-en-text", norm(v)); }
        el.setAttribute("title", zh);
      } else {
        el.setAttribute(a, zh);
        if (!el.getAttribute("data-en-text")) { el.setAttribute("data-en-text", norm(v)); }
        if (a === "placeholder" && !el.getAttribute("title")) { el.setAttribute("title", norm(v)); }
      }
      state.translated++;
      state.stats.attrs++;
      n++;
    }
    return n;
  }

  var WALKER_FILTER = {
    acceptNode: function (node) {
      var el = node.parentElement;
      if (!el || shouldSkip(el)) { return NodeFilter.FILTER_REJECT; }
      var t = node.nodeValue;
      if (!t || !t.trim()) { return NodeFilter.FILTER_REJECT; }
      return NodeFilter.FILTER_ACCEPT;
    }
  };

  /** 中文化一个子树；collect=true 时记录「见到但没映射」的英文。 */
  function localize(root, collect) {
    var scope = root || document.body;
    if (!scope || !document.createTreeWalker) { return 0; }
    var n = 0;
    var walker = document.createTreeWalker(scope, NodeFilter.SHOW_TEXT, WALKER_FILTER);
    var node = walker.nextNode();
    while (node) {
      var before = state.translated;
      translateTextNode(node);
      if (state.translated > before) { n++; }
      else if (collect) { recordUnmapped(node); }
      node = walker.nextNode();
    }
    // 属性：逐个元素扫一遍（数量远小于文本节点）
    var els = scope.querySelectorAll ? scope.querySelectorAll("[title],[placeholder],[aria-label],[alt]") : [];
    for (var i = 0; i < els.length; i++) {
      var b2 = state.translated;
      translateAttrs(els[i]);
      if (state.translated > b2) { n++; }
    }
    return n;
  }

  function recordUnmapped(node) {
    var raw = norm(node.nodeValue);
    if (!isLatinOnly(raw)) { return; }
    if (state.kept[raw] || isKept(raw)) { return; }   // 型号/标识/版本号不算漏翻
    if (state.entries[raw] != null) { return; }       // 已有映射（即使中文与英文同形，如 Kappa）
    if (/[{};:]/.test(raw)) { return; }               // 内联样式/脚本片段
    var el = node.parentElement;
    var key = raw;
    var slot = state.unmapped[key] || (state.unmapped[key] = { text: raw, count: 0, where: [] });
    slot.count++;
    var where = el ? (el.tagName.toLowerCase() + (el.id ? "#" + el.id : "")) : "";
    if (where && slot.where.indexOf(where) < 0 && slot.where.length < 4) { slot.where.push(where); }
  }

  // ---------------------------------------------------------------- 动态内容
  function schedule(root) {
    if (state.pending) { state.pendingRoots.push(root); return; }
    state.pending = true;
    state.pendingRoots = [root];
    var run = function () {
      var roots = state.pendingRoots || [];
      state.pending = false;
      state.pendingRoots = [];
      for (var i = 0; i < roots.length; i++) {
        try { localize(roots[i], true); } catch (e) { /* 单点失败不影响其它 */ }
      }
    };
    if (window.requestAnimationFrame) { window.requestAnimationFrame(run); }
    else { setTimeout(run, 16); }
  }

  function start() {
    if (state.observer || !window.MutationObserver) { return; }
    state.observer = new MutationObserver(function (records) {
      var roots = [];
      for (var i = 0; i < records.length; i++) {
        var r = records[i];
        if (r.type === "characterData" && r.target && r.target.parentElement) {
          roots.push(r.target.parentElement);
        } else if (r.type === "childList") {
          for (var j = 0; j < r.addedNodes.length; j++) {
            var nd = r.addedNodes[j];
            roots.push(nd.nodeType === 1 ? nd : nd.parentElement);
          }
        }
      }
      for (var k = 0; k < roots.length; k++) { if (roots[k]) { schedule(roots[k]); } }
    });
    state.observer.observe(document.body, {
      childList: true, subtree: true, characterData: true
    });
  }

  function coverage() {
    var unmapped = Object.keys(state.unmapped).map(function (k) { return state.unmapped[k]; })
      .sort(function (a, b) { return b.count - a.count; });
    return {
      entries: Object.keys(state.entries).length,
      poi: Object.keys((DATA.poi && DATA.poi.entries) || {}).length,
      patterns: state.patterns.length,
      names: {
        traders: Object.keys(state.nameTables.trader).length,
        tasks: Object.keys(state.nameTables.task).length,
        maps: Object.keys(state.nameTables.map).length,
        items: Object.keys(state.nameTables.item).length
      },
      translated: state.translated,
      nodes: state.stats.nodes,
      attrs: state.stats.attrs,
      unmappedCount: unmapped.length,
      unmapped: unmapped.slice(0, 200),
      loadError: state.loadError || null
    };
  }

  // ---------------------------------------------------------------- 启动
  function boot() {
    load().then(function () {
      localize(document.body, true);
      start();
      document.documentElement.setAttribute("data-i18n", "ready");
    });
  }

  window.GWI18n = {
    load: load,
    tr: tr,
    localize: localize,
    start: start,
    nameZh: nameZh,
    poiZh: poiZh,
    enOf: enOf,
    coverage: coverage,
    reportUnmapped: function () { return coverage().unmapped; },
    markOriginal: markOriginal,
    /** 给某个元素挂「中文显示 + 英文浮窗」（任务模块统一调用） */
    decorate: function (el, zh, en) {
      if (!el) { return el; }
      el.textContent = zh;
      if (en && norm(en) !== norm(zh)) { markOriginal(el, norm(en)); }
      return el;
    },
    _state: state
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
