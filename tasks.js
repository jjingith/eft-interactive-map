/* ============================================================================
 * tasks.js —— EFT 任务系统（R19.23 三模式）
 *
 * 三个页面共用同一份任务数据与唯一任务 ID：
 *   页面 A 全局任务树（可拖拽 / 缩放 / 搜索 / 筛选 / 状态高亮）
 *   页面 B 商人任务中心（商人卡片 + 任务列表 + 任务链）
 *   页面 C 任务详情与攻略（前置 / 条件 / 目标 / 攻略 / 奖励 / 后续）
 *   另有「我的进度」页：进行中 / 可接取 / 阻塞原因 / 同图并行 / 待看后续
 *
 * 数据：data/tasks/tasks.<mode>.json + guides.<mode>.json + traders.json + index.json
 *      （由 tools/fetch_tasks.py 生成，离线可用）
 *      模式 regular=PvP / pve=PvE / pvps=PvPS（PvP 赛季服，上游 pvp-season 端点）
 *      三模式数据各自独立：任务集合、目标、前置、奖励、失败分支都按模式读，
 *      不做「PvP 复制成 PvPS」这种改名式复用。
 * 进度：localStorage eftmap.tasks.progress.v1，按模式隔离（三套互不影响），支持导入导出
 * 文字：中文优先，原始英文名走 title 浮窗（GWI18n.decorate 统一处理）
 * ==========================================================================*/
(function () {
  "use strict";

  var LS_PROGRESS = "eftmap.tasks.progress.v1";
  var LS_UI = "eftmap.tasks.ui.v1";
  // R86：剧情系统。剧情线与任务同属任务页，但进度、筛选、浏览状态各自独立（按模式隔离）。
  var LS_STORY_PROGRESS = "eftmap.stories.progress.v1";
  var LS_STORY_UI = "eftmap.stories.ui.v1";
  var STORY_FILTERS = [
    { key: "all", label: "全部" },
    { key: "none", label: "未开始" },
    { key: "active", label: "进行中" },
    { key: "done", label: "已完成" },
    { key: "endings", label: "含结局" }
  ];
  var STORY_STEP_LIMIT = 12;
  var SVG_NS = "http://www.w3.org/2000/svg";
  var NODE_W = 176, NODE_H = 48, GAP_X = 66, GAP_Y = 12;

  /** 三种游戏模式：key 与 data/tasks/tasks.<key>.json 一致，en 用于悬停提示（不覆盖中文）。 */
  var MODES = [
    { key: "regular", label: "PvP", full: "PvP（常规）", en: "PVP · 普通 PvP 角色（Regular）",
      note: "普通 PvP 模式角色与任务线。" },
    { key: "pve", label: "PvE", full: "PvE", en: "PVE · PvE 角色（Player vs Environment）",
      note: "PvE 模式角色：无玩家互相对抗，任务条件与 PvP 存在差异。" },
    { key: "pvps", label: "PvPS（赛季服）", full: "PvPS（赛季服）", en: "PVP SEASONAL · PvP 赛季服角色",
      note: "PvP 赛季服（Seasonal）：独立角色、独立进度，任务集来自上游 pvp-season 端点。" }
  ];
  var MODE_KEYS = MODES.map(function (m) { return m.key; });
  var MODE_BY_KEY = {};
  MODES.forEach(function (m) { MODE_BY_KEY[m.key] = m; });

  var STATUS = {
    none: { key: "none", zh: "未开始", glyph: "○", cls: "is-none" },
    active: { key: "active", zh: "进行中", glyph: "◐", cls: "is-active" },
    completed: { key: "completed", zh: "已完成", glyph: "✓", cls: "is-done" },
    failed: { key: "failed", zh: "已失败", glyph: "✕", cls: "is-fail" }
  };

  /** 当前游戏模式只有一份：读全局 GWGameMode（R19.27）。本地只存「每模式的浏览状态」。 */
  function globalMode() {
    var G = window.GWGameMode;
    var k = G && G.get ? G.get() : null;
    return MODE_KEYS.indexOf(k) >= 0 ? k : "regular";
  }

  var state = {
    mode: "regular",
    view: "list",
    index: null,          // data/tasks/index.json
    traders: {},          // id → 商人
    tasks: {},            // id → 任务（当前模式）
    guides: {},           // id → 攻略（当前模式）
    order: [],            // 稳定顺序（按商人 + 等级 + 名称）
    byRank: null,         // 树的层级索引
    selected: null,       // 当前选中任务 id
    search: "",
    matches: [],
    matchIdx: -1,
    filters: {
      trader: "", status: "", map: "", special: "",
      levelMin: 0, levelMax: 0, hideDone: false, hideLocked: false, onlyMatch: false,
      onlyDone: false, hasPre: false, hasPost: false
    },
    cam: { x: 0, y: 0, k: 1 },
    progress: { schema: 1, modes: { regular: {}, pve: {}, pvps: {} } },
    ui: { playerLevel: 0, sort: "level" },
    stats: null,
    // R77：地图页 #tasks:<taskId> 深链的落点。数据没到位先排队，到位后再打开 / 提示。
    pendingTaskOpen: null,
    missingTask: null,
    // 每个模式各自的数据缓存与浏览状态：切换模式不重新下载、不清空其他模式进度
    cache: {},            // mode → { tasks, guides, traders, meta }
    pending: {},          // mode → Promise（并发保护）
    perMode: {},          // mode → { view, search, filters, selected, cam, playerLevel, sort }
    season: null,         // data/tasks/season.json（赛季服元信息）
    taskImages: {},       // data/task-images.json：db4tarkov 任务封面（taskId → 本地路径）
    taskImagesReady: false,
    list: { search: "", sort: "default", status: "all", map: "", trader: "", allObj: false },
    // R86：剧情系统状态（与任务进度完全分开；data/stories.json 懒加载一次）
    storyDoc: null,
    storyReady: false,
    storyError: null,
    storySelected: null,
    storyStep: null,          // 深链 / 点击定位到的剧情步骤 id
    storySearch: "",
    storyFilter: "all",
    storyExpand: {},          // storyId → true：展开全部步骤（默认只显示前 N 步）
    storyProgress: { schema: 1, modes: { regular: {}, pve: {}, pvps: {} } },
    pendingStoryOpen: null,   // { storyId, stepId }：数据未就绪时排队
    missingStory: null,
    el: {},
    loading: false,
    error: null
  };

  function emptyFilters() {
    return {
      trader: "", status: "", map: "", special: "",
      levelMin: 0, levelMax: 0, hideDone: false, hideLocked: false, onlyMatch: false,
      onlyDone: false, hasPre: false, hasPost: false
    };
  }

  // ---------------------------------------------------------------- 工具
  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  function h(tag, cls, text) {
    var el = document.createElement(tag);
    if (cls) { el.className = cls; }
    if (text != null) { el.textContent = text; }
    return el;
  }

  // 任务树 / 详情 / 进度页共用设计系统按钮；tk-* 仅保留为业务与事件选择器。
  function taskButton(label, extraClass, options) {
    options = options || {};
    var cls = "tk-btn" + (extraClass ? " " + extraClass : "");
    var button = window.GWUI
      ? window.GWUI.btn({ label: label, size: options.size || "sm",
          variant: options.variant, className: cls })
      : h("button", "ui-btn ui-btn--sm " + cls, label);
    button.type = "button";
    return button;
  }

  function taskBadge(label, kind, legacyClass, title) {
    var badge = window.GWUI ? window.GWUI.badge(label, kind, title) : h("span", "ui-badge", label);
    if (legacyClass) { badge.classList.add(legacyClass); }
    return badge;
  }

  function taskNotice(title, text, kind) {
    var UI = window.GWUI;
    var body = h("p", "tk-alert-text", text);
    if (!UI) {
      var fallback = h("div", "tk-alert" + (kind === "warn" ? " is-warn" : ""));
      fallback.appendChild(h("strong", null, title));
      fallback.appendChild(body);
      return fallback;
    }
    var badge = UI.badge(kind === "warn" ? "需要留意" : "说明", kind || "info");
    var panel = UI.panel({ title: title, actions: [badge], body: body,
      plain: true, className: "tk-alert" });
    panel.setAttribute("role", kind === "warn" ? "status" : "note");
    return panel;
  }

  function taskSummaryCard(label, value, stateName) {
    if (window.GWUI) {
      var count = h("strong", "tk-card-num", String(value));
      return window.GWUI.panel({ title: label, body: count, plain: true,
        className: "tk-card is-" + stateName });
    }
    var card = h("div", "tk-card is-" + stateName);
    card.appendChild(h("span", "tk-card-num", String(value)));
    card.appendChild(h("span", "tk-card-label", label));
    return card;
  }

  function svgEl(tag, attrs) {
    var el = document.createElementNS(SVG_NS, tag);
    for (var k in attrs) {
      if (Object.prototype.hasOwnProperty.call(attrs, k)) { el.setAttribute(k, attrs[k]); }
    }
    return el;
  }

  function clampText(s, n) {
    s = String(s || "");
    return s.length > n ? s.slice(0, n - 1) + "…" : s;
  }

  /**
   * 节点标题截断（R19.25）：直接按字数截会把「TerraGroup 总部」截成「TerraGroup …」，
   * 屏幕上只剩英文、看不出是哪条任务。这里保证：原文含中文时，截断结果必须至少保留 1 个汉字。
   * 完整名称始终在节点 title 里。
   */
  function clampLabel(s, n) {
    s = String(s || "");
    if (s.length <= n) { return s; }
    var cut = s.slice(0, n - 1) + "…";
    var cjk = /[\u4e00-\u9fff]/;
    if (!cjk.test(cut) && cjk.test(s)) {
      var i = s.search(cjk);
      var keep = Math.min(s.length, Math.max(i + 2, n - 1));
      return s.slice(0, keep) + "…";
    }
    return cut;
  }

  /** 任务英文名浮窗文本：真实英文名（items.json）或 wiki slug 还原 + 任务 ID。 */
  function enTitle(rec) {
    if (!rec) { return ""; }
    var base = rec.englishName || rec.nameEn || "";
    return base ? (base + " · " + rec.id) : rec.id;
  }

  function decorateName(el, rec, maxLen) {
    var zh = maxLen ? clampText(rec.nameZh, maxLen) : rec.nameZh;
    el.textContent = zh;
    var en = enTitle(rec);
    if (en) { el.setAttribute("title", en); el.setAttribute("data-en-text", en); }
    return el;
  }

  // ---------------------------------------------------------------- 进度存取
  /** 读取进度：三个模式各读一次；老版本（只有 regular/pve）自动迁移，不丢数据。 */
  function loadProgress() {
    try {
      var raw = localStorage.getItem(LS_PROGRESS);
      if (!raw) { return; }
      var doc = JSON.parse(raw);
      if (!doc || doc.schema !== 1 || !doc.modes) { return; }
      var modes = {};
      MODE_KEYS.forEach(function (m) { modes[m] = doc.modes[m] || {}; });
      state.progress = { schema: 1, modes: modes };
    } catch (e) { /* 坏数据不覆盖、不崩溃：当作空进度 */ }
  }

  /** 落盘任务进度。返回是否成功（隐私模式/配额满时失败，调用方据此回滚或提示）。 */
  function saveProgress() {
    try {
      localStorage.setItem(LS_PROGRESS, JSON.stringify(state.progress));
      state.progressSavedAt = new Date().toISOString();
      // 云同步：只派发事件，由 js/cloud.js 去抖后按「变化的键」增量上传
      try { document.dispatchEvent(new CustomEvent("gw:progress-saved")); } catch (e) { /* ignore */ }
      return true;
    } catch (e) {
      if (window.console && console.warn) { console.warn("[GWTasks] saveProgress failed", e); }
      return false;
    }
  }

  /** 浏览器里各模式的记录条数（导出/导入提示、进度页统计用）。 */
  function progressCount() {
    var out = {};
    MODE_KEYS.forEach(function (m) { out[m] = Object.keys(state.progress.modes[m] || {}).length; });
    return out;
  }

  function loadUi() {
    try {
      var raw = localStorage.getItem(LS_UI);
      if (!raw) { return; }
      var doc = JSON.parse(raw);
      if (!doc || typeof doc !== "object") { return; }
      // R19.27：当前模式只认全局 GWGameMode（含刷新/重开恢复）；旧字段仅用于历史数据迁移
      state.mode = globalMode();
      if (doc.mode && MODE_KEYS.indexOf(doc.mode) >= 0 && !window.GWGameMode) {
        state.mode = doc.mode;        // 全局模块缺失的降级路径
      }
      if (doc.perMode && typeof doc.perMode === "object") {
        Object.keys(doc.perMode).forEach(function (m) {
          if (MODE_KEYS.indexOf(m) >= 0) { state.perMode[m] = doc.perMode[m]; }
        });
      } else {
        // R19.22 旧格式（全局单一状态）→ 归到当时所在模式，其它模式用默认值
        state.perMode[state.mode] = {
          view: doc.view, selected: doc.selected, ui: doc.ui, filters: doc.filters
        };
      }
      var cur = state.perMode[state.mode] || {};
      if (cur.view && ["tree", "list", "detail", "progress", "story"].indexOf(cur.view) >= 0) {
        state.view = cur.view;
      }
      state.selected = cur.selected || null;
      if (cur.ui) {
        state.ui.playerLevel = Number(cur.ui.playerLevel) || 0;
        state.ui.sort = cur.ui.sort || "level";
      }
      if (cur.filters) { Object.assign(state.filters, cur.filters); }
      if (typeof cur.search === "string") { state.search = cur.search; }
      if (cur.cam && isFinite(cur.cam.k)) { state.cam = { x: +cur.cam.x || 0, y: +cur.cam.y || 0, k: +cur.cam.k || 1 }; }
    } catch (e) { /* 忽略 */ }
  }

  /** 把「当前模式」的浏览状态存进 perMode（切换模式 / 关闭前调用）。 */
  function snapshotMode() {
    state.perMode[state.mode] = {
      view: state.view,
      search: state.search,
      filters: Object.assign({}, state.filters),
      selected: state.selected,
      cam: { x: state.cam.x, y: state.cam.y, k: state.cam.k },
      ui: { playerLevel: state.ui.playerLevel, sort: state.ui.sort }
    };
  }

  /** 进入目标模式：套用它上次的状态；无效状态单项回退，不牵扯其它模式。 */
  function restoreMode(mode) {
    var cur = state.perMode[mode] || {};
    state.search = typeof cur.search === "string" ? cur.search : "";
    state.filters = Object.assign(emptyFilters(), cur.filters || {});
    state.ui.playerLevel = cur.ui ? Number(cur.ui.playerLevel) || 0 : 0;
    state.ui.sort = (cur.ui && cur.ui.sort) || "level";
    // R68：已保存的 view="traders" 不再有效 → 回落到任务列表
    state.view = (cur.view && ["tree", "list", "detail", "progress", "story"].indexOf(cur.view) >= 0)
      ? cur.view : "list";
    state.selected = cur.selected || null;
    state.cam = cur.cam && isFinite(cur.cam.k)
      ? { x: +cur.cam.x || 0, y: +cur.cam.y || 0, k: +cur.cam.k || 1 }
      : { x: 0, y: 0, k: 1 };
    state.keepCam = !!(cur.cam && isFinite(cur.cam.k));   // 有历史视角就保留，不强行 focusStart
  }

  /**
   * 模式切换后做一次「本模式有效性」修剪：只清掉在该模式里不成立的那一项，
   * 例如商人/地图筛选在目标模式中没有对应任务 → 清空该筛选项（其它模式不受影响）。
   * 必须在数据就绪后调用。
   */
  function pruneModeState() {
    var f = state.filters;
    if (f.trader && !state.order.some(function (id) { return state.tasks[id].traderId === f.trader; })) {
      f.trader = "";
    }
    if (f.map) {
      var hasMap = state.order.some(function (id) {
        return (state.tasks[id].maps || []).indexOf(f.map) >= 0;
      });
      if (!hasMap) { f.map = ""; }
    }
    if (state.selected && !state.tasks[state.selected]) { state.selected = null; }
    if (state.view === "detail" && !state.selected) { state.view = "list"; }
    if (!state.selected) { state.matches = []; state.matchIdx = -1; }
  }

  function saveUi() {
    try {
      snapshotMode();
      // mode 不写这里：全局模式由 js/game-mode.js 的「eftmap.gameMode」唯一持久化，
      // 本文件只存每模式自己的页面/筛选/选中/缩放（R19.27 §7.6 分开存储）。
      localStorage.setItem(LS_UI, JSON.stringify({
        perMode: state.perMode
      }));
    } catch (e) { /* 忽略 */ }
  }

  function progOf(taskId) {
    var bag = state.progress.modes[state.mode] || (state.progress.modes[state.mode] = {});
    return bag[taskId] || null;
  }

  function statusOf(taskId) {
    var rec = progOf(taskId);
    if (rec && rec.status && STATUS[rec.status]) { return rec.status; }
    return "none";
  }

  /** 只改内存里的进度桶（不落盘）——批量联动用它拼一次原子更新。 */
  function setStatusRaw(taskId, status) {
    var bag = state.progress.modes[state.mode] || (state.progress.modes[state.mode] = {});
    var rec = bag[taskId] || (bag[taskId] = { objectives: {} });
    rec.status = status;
    rec.updatedAt = new Date().toISOString();
    if (status === "completed") {
      // 完成时把必需目标一并勾上，避免「已完成但目标全空」的自相矛盾
      var t = state.tasks[taskId];
      (t && t.objectives || []).forEach(function (o) {
        if (!o.optional) { rec.objectives[o.id] = true; }
      });
    }
  }

  function setStatus(taskId, status) {
    setStatusRaw(taskId, status);
    saveProgress();
    broadcast();
  }

  /** R72：任务 ID 一键复制（剪贴板不可用时退回 execCommand）。 */
  function copyTaskId(text, btn) {
    function done(ok) {
      if (!btn) { return; }
      btn.textContent = ok ? "已复制" : "复制失败";
      clearTimeout(btn._t);
      btn._t = setTimeout(function () { btn.textContent = "复制"; }, 1200);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () { done(true); },
        function () { done(false); });
      return;
    }
    try {
      var ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      done(document.execCommand("copy"));
      document.body.removeChild(ta);
    } catch (e) { done(false); }
  }

  /**
   * 一次性写入多条状态（含目标任务）：只 save 一次。
   * 保存失败时回滚到操作前快照并明确提示——绝不留下"只改了一半"的中间态。
   */
  function applyStatusBatch(pairs) {
    if (!pairs || !pairs.length) { return true; }
    var snapshot = JSON.stringify(state.progress);   // 回滚点
    try {
      pairs.forEach(function (pr) { setStatusRaw(pr.id, pr.status); });
    } catch (e) {
      state.progress = JSON.parse(snapshot);
      setStatusText("批量更新失败，已回滚：" + (e && e.message || e));
      renderAll();
      return false;
    }
    if (!saveProgress()) {
      state.progress = JSON.parse(snapshot);
      setStatusText("进度保存失败（浏览器存储不可写），已回滚本次 " + pairs.length + " 项变更。");
      renderAll();
      return false;
    }
    broadcast();
    renderAll();
    return true;
  }

  function toggleObjective(taskId, objId) {
    var bag = state.progress.modes[state.mode] || (state.progress.modes[state.mode] = {});
    var rec = bag[taskId] || (bag[taskId] = { objectives: {}, status: "active" });
    rec.objectives = rec.objectives || {};
    rec.objectives[objId] = !rec.objectives[objId];
    rec.updatedAt = new Date().toISOString();
    // 必需目标全勾 → 自动完成；否则若原本「未开始」则进入进行中
    var task = state.tasks[taskId];
    var required = (task && task.objectives || []).filter(function (o) { return !o.optional; });
    var allDone = required.length > 0 && required.every(function (o) { return rec.objectives[o.id]; });
    if (allDone) { rec.status = "completed"; }
    else if (!rec.status || rec.status === "none" || rec.status === "completed") { rec.status = "active"; }
    saveProgress();
    broadcast();
  }

  function broadcast() {
    try {
      document.dispatchEvent(new CustomEvent("gwtasks:progress", {
        detail: { mode: state.mode, total: countByStatus() }
      }));
    } catch (e) { /* 老浏览器忽略 */ }
    updateCounts();
  }

  function countByStatus() {
    var out = { none: 0, active: 0, completed: 0, failed: 0, total: state.order.length };
    state.order.forEach(function (id) {
      var s = statusOf(id);
      out[s] = (out[s] || 0) + 1;
    });
    return out;
  }

  // ---------------------------------------------------------------- 数据加载
  function fetchJSON(url) {
    return fetch(url, { cache: "no-cache" }).then(function (r) {
      if (!r.ok) { throw new Error("HTTP " + r.status + " " + url); }
      return r.json();
    });
  }

  /**
   * R217：赛季说明从任务详情底部搬到顶部菜单「关于」。
   * 周期取自 data/tasks/season.json（state.season），不在这里写死日期 —— 上游赛季换了，
   * 关于面板跟着数据变；元信息缺失时退回「暂缺」，与原来详情页的说法一致。
   */
  function syncAboutSeasonNote() {
    var node = document.getElementById("about-season-note");
    if (!node) { return; }
    var season = state.season || {};
    var range = (season.startISO && season.endISO)
      ? "对应当前赛季周期 " + season.startISO + " → " + season.endISO + "。"
      : "赛季元信息暂缺。";
    node.textContent = "赛季服说明：以上内容来自上游 pvp-season 端点，" + range +
      "赛季结束后请勿把旧赛季的完成状态当作新赛季进度。";
  }

  /** 把某模式的缓存装到当前全局状态（切换模式时只做指针替换，不重新解析）。 */
  function hydrate(mode) {
    var pack = state.cache[mode];
    if (!pack) { return false; }
    state.tasks = pack.tasks;
    state.guides = pack.guides;
    state.traders = pack.traders;
    state.dataMeta = pack.meta;
    indexTasks();
    return true;
  }

  /**
   * 载入某模式数据。命中内存缓存 → 立即返回（切换模式瞬时完成）；
   * 未命中 → 拉一次 tasks/guides/traders/index/season，成功后缓存，第二次切换不再下载。
   */
  function ensureData(mode) {
    if (state.cache[mode]) { hydrate(mode); return Promise.resolve(true); }
    if (state.pending[mode]) { return state.pending[mode]; }
    state.loading = true;
    var jobs = [
      fetchJSON("data/tasks/tasks." + mode + ".json"),
      fetchJSON("data/tasks/guides." + mode + ".json").catch(function () { return { guides: {} }; }),
      fetchJSON("data/tasks/traders.json").catch(function () { return { traders: {} }; }),
      state.index ? Promise.resolve(state.index)
        : fetchJSON("data/tasks/index.json").catch(function () { return null; }),
      state.season ? Promise.resolve(state.season)
        : fetchJSON("data/tasks/season.json").catch(function () { return null; })
    ];
    state.pending[mode] = Promise.all(jobs).then(function (res) {
      var doc = res[0] || {};
      state.index = res[3] || state.index;
      state.season = res[4] || state.season;
      syncAboutSeasonNote();
      var metaIndex = ((state.index || {}).modes || {})[mode] || {};
      var metaCross = ((state.index || {}).modeMeta || {})[mode] || {};
      state.cache[mode] = {
        tasks: doc.tasks || {},
        guides: (res[1] && res[1].guides) || {},
        traders: (res[2] && res[2].traders) || {},
        meta: {
          mode: mode,
          generatedAt: doc.generatedAt || "",
          counts: doc.counts || {},
          modeLabel: doc.modeLabel || (MODE_BY_KEY[mode] || {}).full || mode,
          upstreamGameMode: doc.upstreamGameMode || "",
          index: metaIndex,
          cross: metaCross
        }
      };
      delete state.pending[mode];
      state.loading = false;
      state.error = null;
      if (state.mode === mode) { hydrate(mode); }
      return true;
    }).catch(function (err) {
      delete state.pending[mode];
      state.loading = false;
      state.error = String(err && err.message || err);
      return false;
    });
    return state.pending[mode];
  }

  function indexTasks() {
    var ids = Object.keys(state.tasks);
    var traderRank = {};
    Object.keys(state.traders).forEach(function (tid, i) { traderRank[tid] = i; });
    state.order = ids.slice().sort(function (a, b) {
      var ra = state.tasks[a], rb = state.tasks[b];
      var ta = traderRank[ra.traderId] == null ? 99 : traderRank[ra.traderId];
      var tb = traderRank[rb.traderId] == null ? 99 : traderRank[rb.traderId];
      if (ta !== tb) { return ta - tb; }
      if (ra.minLevel !== rb.minLevel) { return ra.minLevel - rb.minLevel; }
      return String(ra.nameZh).localeCompare(String(rb.nameZh), "zh-Hans-CN");
    });
    state.byRank = null;
    state.stats = null;
  }

  function task(id) { return state.tasks[id] || null; }

  function traderOf(rec) {
    if (!rec) { return null; }
    return state.traders[rec.traderId] || { id: rec.traderId, nameZh: rec.traderZh || "",
                                            nameEn: rec.traderEn || "", localIcon: "" };
  }

  /**
   * 商人显示名（R19.25）：任务系统统一使用游戏内英文原名。
   * 数据来源：data/tasks/traders.json 的 nameEn（由上游 traders 端点解析并落盘）。
   * 不做中文机翻、不用内部 ID、不靠显示名反查；查不到时明确写"未收录商人"。
   */
  function traderEn(rec) {
    if (!rec) { return "未收录商人"; }
    var t = state.traders[rec.traderId];
    if (t && t.nameEn) { return t.nameEn; }
    if (rec.traderEn) { return rec.traderEn; }
    return "未收录商人";
  }

  /** 只有商人 ID 时（奖励、解锁、报价）走同一个映射，避免每个页面各写一张表。 */
  function traderNameById(id) {
    var t = state.traders[id];
    if (t && t.nameEn) { return t.nameEn; }
    return id ? "未收录商人" : "—";
  }

  /**
   * R73：地图显示名统一为中文。上游 tasks 数据里还留着两条「英文 + 中文后缀」的
   * 变体名，界面上只显示中文；英文原名进 title 浮窗，正文不再中英并排。
   * 只用于**显示**，筛选/定位仍用原始 maps 字符串。
   */
  var MAP_LABELS = {
    "Ground Zero 教程": { zh: "中心区（教程）", en: "Ground Zero (Tutorial)" },
    "实验室 (Dark)": { zh: "实验室（夜间）", en: "The Lab (Dark)" }
  };
  function mapLabel(m) {
    var row = MAP_LABELS[m];
    return row ? row.zh : m;
  }
  function mapEnTitle(m) {
    var row = MAP_LABELS[m];
    return row ? row.en : "";
  }
  function mapText(list, sep) {
    return (list || []).map(mapLabel).join(sep || "、");
  }

  function prereqNames(rec, limit) {
    var out = [];
    (rec.prerequisites || []).forEach(function (p) {
      var t = task(p.taskId);
      if (t) { out.push(t.nameZh); }
    });
    if (limit && out.length > limit) { out = out.slice(0, limit).concat(["…"]); }
    return out;
  }

  /** 可接取判定：只依据真实数据（前置完成状态 + 等级/忠诚/声望/阵营条件）。 */
  function availability(rec) {
    var reasons = [];
    var unknown = [];
    (rec.prerequisites || []).forEach(function (p) {
      var ok = false;
      var st = statusOf(p.taskId);
      var wants = p.statuses && p.statuses.length ? p.statuses : ["complete"];
      if (wants.indexOf("complete") >= 0 && st === "completed") { ok = true; }
      if (wants.indexOf("fail") >= 0 && st === "failed") { ok = true; }
      if (wants.indexOf("active") >= 0 && st === "active") { ok = true; }
      if (!ok) {
        var t = task(p.taskId);
        var wantZh = wants.map(function (w) {
          return w === "complete" ? "完成" : (w === "fail" ? "失败" : "接取");
        }).join(" / ");
        reasons.push("前置未满足：" + (t ? t.nameZh : p.taskId) + "（需" + wantZh + "）");
      }
    });
    var lv = state.ui.playerLevel || 0;
    if (rec.minLevel && lv && lv < rec.minLevel) {
      reasons.push("角色等级不足（需 " + rec.minLevel + "，当前 " + lv + "）");
    } else if (rec.minLevel && !lv) {
      unknown.push("角色等级 ≥ " + rec.minLevel + "（未填写当前等级）");
    }
    (rec.conditions || []).forEach(function (c) {
      if (c.kind === "playerLevel") {
        if (lv && lv < (c.value || 0)) { reasons.push("角色等级不足（需 " + c.value + "）"); }
        else if (!lv) { unknown.push(c.text); }
      } else if (c.kind === "traderLevel" || c.kind === "traderStanding" || c.kind === "faction" ||
                 c.kind === "skill" || c.kind === "dialogue" || c.kind === "globalVariable") {
        unknown.push(c.text);
      }
    });
    var st = statusOf(rec.id);
    return {
      state: st === "completed" ? "done"
        : (st === "failed" ? "failed"
          : (reasons.length ? "blocked" : "open")),
      reasons: reasons,
      unknown: unknown
    };
  }

  // ---------------------------------------------------------------- 状态联动（R19.26）
  /**
   * 修改任务状态前先算「联动计划」：
   *   情况 A：设为 进行中/已完成 时，前置条件尚未满足 → 列出要一并调整的前置任务；
   *   情况 B：设为 未开始 时，后续任务已进行中/已完成 → 列出要重置的后续任务（含间接下游）。
   * 确认前**不写任何状态**；确认后一次 applyStatusBatch 原子落盘。
   * 前置是 AND（条目全部满足）；条目内 statuses 是 OR（满足其一即可）。
   * 非任务型条件（商人等级 / 阵营 / 技能…）只列出、绝不伪造完成。
   */
  var STATUS_ZH = { none: "未开始", active: "进行中", completed: "已完成", failed: "已失败" };

  /**
   * 数据词面 → 进度状态（R19.27 修正）：
   *   上游 prerequisites.statuses 用 complete / active / failed，
   *   而进度状态是 completed / active / failed / none——过去只认 "fail" 导致
   *   「需前置失败」的条目永远判定不满足。这里统一归一，两个方向都走同一张表。
   */
  var WANT_TO_STATUS = { complete: "completed", completed: "completed",
                         active: "active", fail: "failed", failed: "failed" };
  function wantStatus(w) { return WANT_TO_STATUS[String(w).toLowerCase()] || null; }

  function wantedOf(p) {
    return (p.statuses && p.statuses.length) ? p.statuses : ["complete"];
  }
  function satisfies(st, wants) {
    return (wants || []).some(function (w) {
      var target = wantStatus(w);
      return target !== null && st === target;
    });
  }
  function wantZh(wants) {
    return (wants || []).map(function (w) {
      var st = wantStatus(w);
      return st ? (STATUS_ZH[st] || st) : String(w);
    }).join(" / ");
  }
  /** OR 条件只需满足其中一档：选与用户目标一致的档，否则选改动最小的一档。 */
  function pickStatus(wants, targetStatus) {
    var mapped = (wants || []).map(wantStatus).filter(Boolean);
    if (targetStatus === "active" && mapped.indexOf("active") >= 0) { return "active"; }
    if (targetStatus === "completed" && mapped.indexOf("completed") >= 0) { return "completed"; }
    if (mapped.indexOf("active") >= 0) { return "active"; }
    if (mapped.indexOf("completed") >= 0) { return "completed"; }
    if (mapped.indexOf("failed") >= 0) { return "failed"; }
    return null;
  }

  /**
   * 情况 A 的计划（R19.27 递归版）：把目标任务设成 targetStatus 需要调整哪些前置。
   *
   * 与 R19.26 的区别：不只看一层直接前置，而是**沿依赖链向上递归**——
   *   C 要完成 → 得先把 B 调到符合档 → B 自己的前置 A 也得调 → …直到链顶或无法自动处理。
   * 语义不变：
   *   · prerequisites 数组条目之间是 AND（全部满足）；
   *   · 单条目的 statuses 内是 OR（满足其一即可）→ pickStatus 只取一档，绝不全部标完成；
   *   · 已满足的条目不动；非任务型条件只进 notes，不伪造。
   * 防御：visited 防重复规划、path 防循环、guard 限制展开规模；异常链进 unfixable，不产生部分修改。
   */
  function planPrereqFix(taskId, targetStatus) {
    if (targetStatus !== "active" && targetStatus !== "completed") { return null; }
    var root = task(taskId);
    if (!root) { return null; }
    var changes = [], unfixable = [], notes = [];
    var planned = {};          // id → 已选定的目标状态（跨分支去重 / 冲突检测）
    var path = {};             // 当前递归路径（循环防御）
    var guard = 0;

    function walk(id, wantStatus, depth, via) {
      if (guard++ > 3000) {
        notes.push("依赖链展开超过安全上限，已停止继续规划（未做任何修改）");
        return;
      }
      if (path[id]) {
        unfixable.push({ id: id, name: (task(id) || {}).nameZh || id,
                         from: statusOf(id), need: "循环依赖，无法自动规划", depth: depth, via: via });
        return;                // 环：不静默删边、不继续展开
      }
      var rec = task(id);
      if (!rec) {
        unfixable.push({ id: id, name: id, from: "none", need: "任务不存在（异常依赖）",
                         depth: depth, via: via });
        return;
      }
      path[id] = 1;
      // 真实语义（data/tasks 实测）：prerequisites 条目间默认 AND；
      // 标了 logic=or 的条目构成「或组」——组内任一满足即可，只规划改动最少的一条（不全标完成）。
      var andList = [], orList = [];
      (rec.prerequisites || []).forEach(function (p) {
        if (!p.taskId) { return; }
        if (String(p.logic).toLowerCase() === "or") { orList.push(p); }
        else { andList.push(p); }
      });

      function planOne(p, d) {
        var pid = p.taskId;
        if (!task(pid)) {
          unfixable.push({ id: pid, name: pid, from: statusOf(pid),
                           need: "任务不存在（异常依赖）", depth: d, via: id });
          return false;
        }
        var wants = wantedOf(p);
        var cur = statusOf(pid);
        if (satisfies(cur, wants)) { return true; }     // 已满足：不动
        if (planned[pid]) {
          if (satisfies(planned[pid], wants)) { return true; }
          unfixable.push({ id: pid, name: (task(pid) || {}).nameZh || pid, from: cur,
                           need: "另一分支已要求「" + STATUS_ZH[planned[pid]] + "」，与本条 " +
                                 wantZh(wants) + " 冲突", depth: d, via: id });
          return false;
        }
        var t = task(pid);
        var to = pickStatus(wants, wantStatus);
        if (!to) {
          unfixable.push({ id: pid, name: t ? t.nameZh : pid, from: cur,
                           need: wantZh(wants), depth: d, via: id });
          return false;
        }
        planned[pid] = to;
        changes.push({ id: pid, name: t ? t.nameZh : pid, from: cur, to: to,
                       need: wantZh(wants), depth: d, via: id });
        walk(pid, to, d + 1, id);                       // 递归处理它自己的前置链
        return true;
      }

      andList.forEach(function (p) { planOne(p, depth); });

      // 或组：已有一条满足就整组不动；否则先试「无需改动」的，再按改动代价选一条
      if (orList.length) {
        var alreadyOk = orList.some(function (p) {
          var cur = statusOf(p.taskId);
          return satisfies(planned[p.taskId] || cur, wantedOf(p));
        });
        if (!alreadyOk) {
          // 改动代价：目标状态与当前状态相同的排前（0），其次 active（1），最后 completed/failed（2）
          function cost(p) {
            var cur = planned[p.taskId] || statusOf(p.taskId);
            var to = pickStatus(wantedOf(p), wantStatus);
            if (!to || cur === to) { return 0; }
            return to === "active" ? 1 : 2;
          }
          var ranked = orList.slice().sort(function (a, b) {
            return cost(a) - cost(b) || (a.taskId < b.taskId ? -1 : 1);
          });
          // 只规划第一条可行的；其余 OR 分支不碰（满足「只选一条有效路径」）
          for (var oi = 0; oi < ranked.length; oi++) {
            if (planOne(ranked[oi], depth)) {
              notes.push("或条件：已选「" + ((task(ranked[oi].taskId) || {}).nameZh || ranked[oi].taskId) +
                         "」这条分支（" + wantZh(wantedOf(ranked[oi])) + "），其余分支保持不变");
              break;
            }
          }
        }
      }
      (rec.conditions || []).forEach(function (c) {
        if (c.kind !== "playerLevel" && c.kind !== "playerLevelMin") {
          notes.push((rec.nameZh || id) + "：" + (c.text || String(c.kind)));
        }
      });
      delete path[id];
    }

    walk(taskId, targetStatus, 0, null);
    if (!changes.length && !unfixable.length) { return null; }
    // 展示按依赖深度分组（浅 → 深），同深度按名称稳定排序
    changes.sort(function (a, b) { return a.depth - b.depth || (a.name < b.name ? -1 : 1); });
    unfixable.sort(function (a, b) { return (a.depth || 0) - (b.depth || 0); });
    return { kind: "prereq", taskId: taskId, target: targetStatus,
             changes: changes, unfixable: unfixable, notes: notes,
             maxDepth: changes.reduce(function (m, c) { return Math.max(m, c.depth); }, 0) };
  }

  /** 情况 B 的计划：把 taskId 设为未开始后，哪些后续任务会失去解锁条件。
   *  只沿 followUps（真实解锁方向）传播；失败分支不是解锁边。
   *  OR 条件下若另一档仍满足，该后续不进重置计划。 */
  function planFollowUpReset(taskId) {
    var rec = task(taskId);
    if (!rec) { return null; }
    var shadow = {};
    function stOf(id) {
      if (id === taskId) { return "none"; }
      if (shadow[id] != null) { return shadow[id]; }
      return statusOf(id);
    }
    function okPrereqs(r) {
      return (r.prerequisites || []).every(function (p) {
        return satisfies(stOf(p.taskId), wantedOf(p));
      });
    }
    var plan = [];
    var inPlan = {};
    var depth = {};
    depth[taskId] = 0;
    var queue = [taskId];
    var guard = 0;
    while (queue.length && guard++ < 4000) {
      var id = queue.shift();
      var r = task(id);
      if (!r) { continue; }
      (r.followUps || []).forEach(function (fid) {
        var fr = task(fid);
        if (!fr) { return; }
        var st = statusOf(fid);
        if (st !== "active" && st !== "completed") { return; }   // 未开始/失败无需重置
        if (okPrereqs(fr)) { return; }                            // 其它 OR 分支仍满足
        if (inPlan[fid]) { return; }
        inPlan[fid] = 1;
        shadow[fid] = "none";
        depth[fid] = (depth[id] || 0) + 1;
        plan.push({ id: fid, name: fr.nameZh, from: st, depth: depth[fid], via: id });
        queue.push(fid);                                          // 继续向更下游传播
      });
    }
    if (!plan.length) { return null; }
    return { kind: "reset", taskId: taskId, plan: plan };
  }

  function planSignature(plan) {
    if (!plan) { return "null"; }
    var list = plan.kind === "prereq"
      ? plan.changes.map(function (c) { return c.id + ">" + c.to; })
      : plan.plan.map(function (c) { return c.id + ">" + c.from; });
    return plan.kind + "|" + list.sort().join(";");
  }

  function planBody(plan) {
    var wrap = h("div", "tk-plan");
    var rec = task(plan.taskId);
    var head = h("p", "tk-plan-head");
    head.textContent = plan.kind === "prereq"
      ? "你正在将「" + (rec ? rec.nameZh : plan.taskId) + "」设置为" + STATUS_ZH[plan.target] +
        "，但有 " + (plan.changes.length + plan.unfixable.length) + " 项前置条件未满足。"
      : "将「" + (rec ? rec.nameZh : plan.taskId) + "」设置为未开始，会影响 " +
        plan.plan.length + " 个依赖它的后续任务。";
    wrap.appendChild(head);

    var list = h("ul", "tk-plan-list");
    if (plan.kind === "prereq") {
      // 按依赖深度分组展示：第 1 层 = 直接前置，第 2 层 = 前置的前置…
      var byDepth = {};
      plan.changes.forEach(function (c) {
        (byDepth[c.depth] = byDepth[c.depth] || []).push(c);
      });
      Object.keys(byDepth).map(Number).sort(function (a, b) { return a - b; }).forEach(function (d) {
        list.appendChild(h("li", "tk-plan-group", (d === 0 ? "直接前置（第 1 层）" : "间接前置（第 " + (d + 1) + " 层）")));
        byDepth[d].forEach(function (c) {
          var li = h("li", "tk-plan-item");
          li.appendChild(h("span", "tk-plan-name", "「" + c.name + "」"));
          li.appendChild(h("span", null, "：" + STATUS_ZH[c.from] + " → " + STATUS_ZH[c.to] +
            "（需 " + c.need + (c.via ? "；因「" + ((task(c.via) || {}).nameZh || c.via) + "」需要" : "") + "）"));
          list.appendChild(li);
        });
      });
      plan.unfixable.forEach(function (c) {
        list.appendChild(h("li", "tk-plan-warn", "「" + c.name + "」无法自动处理：" +
          STATUS_ZH[c.from] + " → 需 " + c.need + (c.depth ? "（第 " + (c.depth + 1) + " 层）" : "") +
          "（请在游戏内自行推进）"));
      });
    } else {
      plan.plan.forEach(function (c) {
        list.appendChild(h("li", null, (c.depth > 1 ? "间接（第 " + c.depth + " 层）" : "直接后续") +
          "「" + c.name + "」：" + STATUS_ZH[c.from] + " → 未开始"));
      });
    }
    wrap.appendChild(list);
    if (plan.notes && plan.notes.length) {
      wrap.appendChild(h("p", "tk-plan-note", "另有非任务型条件（不会被自动伪造）：" + plan.notes.join("；")));
    }
    wrap.appendChild(h("p", "tk-plan-note", "确认前不会修改任何任务状态；取消则全部保持原样。"));
    return wrap;
  }

  function openLinkageDialog(plan) {
    var UI = window.GWUI;
    if (!UI || !UI.dialog) {
      // 没有通用弹窗时退回原生 confirm（项目审计记录此降级路径）
      var txt = planBody(plan).textContent;
      if (window.confirm(txt)) { executePlan(plan); }
      return;
    }
    var busy = false;
    UI.dialog({
      title: plan.kind === "prereq" ? "前置任务尚未完成" : "重置后续任务？",
      wide: true,
      body: planBody(plan),
      buttons: plan.kind === "prereq"
        ? [
            { label: "取消", variant: "" },
            { label: "确认并调整前置任务", variant: "primary", onClick: function () {
              if (busy) { return false; }
              busy = true;
              executePlan(plan);
            } }
          ]
        : [
            { label: "取消", variant: "" },
            { label: "仅重置当前任务", variant: "", onClick: function () {
              if (busy) { return false; }
              busy = true;
              applyStatusBatch([{ id: plan.taskId, status: "none" }]);
            } },
            { label: "确认并重置后续任务", variant: "primary", onClick: function () {
              if (busy) { return false; }
              busy = true;
              executePlan(plan);
            } }
          ]
    });
  }

  /** 执行计划：先复核（防覆盖用户刚做的其它修改），一致才一次性写入。 */
  function executePlan(plan) {
    var fresh = plan.kind === "prereq"
      ? planPrereqFix(plan.taskId, plan.target)
      : planFollowUpReset(plan.taskId);
    if (planSignature(fresh) !== planSignature(plan)) {
      setStatusText("任务状态刚发生变化，联动计划已失效，请重新操作（本次未修改任何状态）。");
      renderAll();
      return;
    }
    if (plan.kind === "prereq") {
      var pairs = (fresh ? fresh.changes : []).map(function (c) { return { id: c.id, status: c.to }; });
      pairs.push({ id: plan.taskId, status: plan.target });
      applyStatusBatch(pairs);
    } else {
      var pairs2 = (fresh ? fresh.plan : []).map(function (c) { return { id: c.id, status: "none" }; });
      pairs2.push({ id: plan.taskId, status: "none" });
      applyStatusBatch(pairs2);
    }
  }

  /** 用户入口：按目标状态决定走联动弹窗还是直接更新。 */
  function requestStatusChange(id, status) {
    if (!id || !STATUS[status]) { return; }
    if (statusOf(id) === status) { return; }
    if (status === "active" || status === "completed") {
      var planA = planPrereqFix(id, status);
      if (planA) { openLinkageDialog(planA); return; }
    } else if (status === "none") {
      var planB = planFollowUpReset(id);
      if (planB) { openLinkageDialog(planB); return; }
    }
    setStatus(id, status);
    renderAll();
    // R72：状态即时生效后给一行轻量反馈（底部状态栏），不弹窗、不冻结界面。
    var rec = task(id);
    setStatusText("已将「" + ((rec && rec.nameZh) || id) + "」标记为「" + STATUS[status].zh + "」");
  }

  // ---------------------------------------------------------------- 骨架
  function skeleton() {
    var root = h("div", "tk-shell");
    root.id = "task-root";

    var head = h("header", "tk-head");
    // 第一行：标题（左） + 三模式切换（右，永不被搜索/筛选挤走）
    // R19.27：模式切换升级为全应用控件（页头右上角 #game-mode-bar，js/game-mode.js），
    // 任务页不再重复放一份按钮；此处只保留「当前模式」文字说明（数据归属一目了然）。
    var bar = h("div", "tk-titlebar");
    var brand = h("div", "tk-brand");
    brand.appendChild(h("h2", "tk-title", "任务系统"));
    brand.appendChild(h("span", "tk-build", "三模式数据 · 独立进度"));
    bar.appendChild(brand);
    // R19.88：「当前模式」从子栏挪到标题行，紧跟在「任务系统 / 三模式数据 · 独立进度」右侧。
    var scope = h("span", "tk-scope");
    scope.id = "tk-scope";
    bar.appendChild(scope);
    var modeHint = h("span", "tk-mode-hint tk-visually-hidden");
    modeHint.id = "tk-mode-hint";
    modeHint.textContent = "模式：…";
    bar.appendChild(modeHint);

    // R74：模式切换收敛为**右上角全局唯一条**（#game-mode-bar）。
    // 任务页这里只保留账号版本下拉，不再重复一组 PvP / PvE / PvPS 分段按钮。
    var scopeBar = h("div", "tk-scope-bar");
    scopeBar.id = "tk-scope-bar";
    scopeBar.setAttribute("role", "group");
    scopeBar.setAttribute("aria-label", "账号版本（模式请用右上角全局切换）");

    var edWrap = h("label", "tk-edition-wrap");
    edWrap.appendChild(h("span", "tk-edition-label", "版本"));
    var edSel = h("select", "tk-edition");
    edSel.id = "tk-edition";
    edSel.setAttribute("aria-label", "账号版本");
    edSel.addEventListener("change", function () {
      var val = this.value || null;
      var DS = window.GWDataScope;
      // R72：走 applyEdition 同一入口，保证 localStorage 持久化与账号卡联动。
      if (DS && DS.setEdition) { DS.setEdition(val); }
      else if (DS && DS.apply) { DS.apply({ edition: val }); }
      var fb = document.getElementById("tk-scope-feedback");
      if (fb) {
        fb.textContent = val ? "版本已切换" : "版本已清除";
        fb.classList.add("is-on");
        clearTimeout(fb._t);
        fb._t = setTimeout(function () {
          fb.classList.remove("is-on");
          fb.textContent = "";
        }, 1400);
      }
    });
    edWrap.appendChild(edSel);
    scopeBar.appendChild(edWrap);

    var fb = h("span", "tk-scope-feedback");
    fb.id = "tk-scope-feedback";
    fb.setAttribute("aria-live", "polite");
    scopeBar.appendChild(fb);
    bar.appendChild(scopeBar);
    head.appendChild(bar);

    // R19.89：五个子页导航直接放进标题行（任务系统 / 三模式数据 / 当前模式 同一行），
    // 不再单独占一行，也不上提到二级工具条。
    var tabs = h("div", "tk-tabs");
    tabs.setAttribute("role", "tablist");
    tabs.setAttribute("aria-label", "任务视图");
    // R68：移除「商人任务」页签 —— 它与任务列表的「按商人分组」重复。
    // 入口从 DOM 中不渲染（而不是 display:none），避免焦点/Tab 顺序里留下不可达按钮。
    [["tree", "任务树"], ["list", "任务列表"], ["detail", "任务详情"], ["progress", "我的进度"], ["story", "剧情"]].forEach(function (v) {
      var b = h("button", "tk-tab", v[1]);
      b.type = "button";
      b.dataset.taskview = v[0];
      b.setAttribute("role", "tab");
      tabs.appendChild(b);
    });
    // 顺序：任务系统 / 三模式数据 → 当前模式 → 五个子页 → 版本（最右）
    bar.insertBefore(tabs, scopeBar);

    // 筛选条（R19.24 起改用设计系统组件；id 保持不变，事件与筛选逻辑一行未改）
    var filters = h("div", "tk-filters");
    var search = window.GWUI
      ? window.GWUI.input({ type: "search", placeholder: "搜索任务名 / 英文名 / 任务 ID", ariaLabel: "搜索任务" })
      : h("input", "tk-search");
    search.id = "tk-search";
    search.className += " tk-search";
    if (!window.GWUI) { search.type = "search"; search.placeholder = "搜索任务名 / 英文名 / 任务 ID"; }
    filters.appendChild(search);

    filters.appendChild(selectEl("tk-trader", "商人", [["", "全部商人"]]));
    filters.appendChild(selectEl("tk-status", "状态", [
      ["", "全部状态"], ["none", "未开始"], ["active", "进行中"], ["completed", "已完成"], ["failed", "已失败"]
    ]));
    filters.appendChild(selectEl("tk-map", "地图", [["", "全部地图"]]));
    // 说明：主线 / 剧情标记上游任务数据未提供（taskType 与 isStoryTask 都不存在），
    // 因此不做「主线」筛选项——宁可少一个筛选项，也不给一个永远筛不到东西的假开关。
    // 同理「DSPT 任务」：当前上游任务数据里没有任何 DSPT 字段（已用 grep 全量核对），
    // 所以不照抄参考站点的这个开关。
    filters.appendChild(selectEl("tk-special", "特殊", [
      ["", "全部任务"], ["kappa", "Kappa 必需"], ["lightkeeper", "灯塔相关"],
      ["faction", "阵营限定"], ["season", "赛季专属"]
    ]));

    var lvWrap = h("label", "tk-lv");
    lvWrap.appendChild(h("span", "tk-lv-label", "等级"));
    var lvMin = window.GWUI
      ? window.GWUI.input({ type: "number", num: true, size: "sm", min: 0, max: 80, placeholder: "最小", ariaLabel: "最低等级" })
      : h("input", "tk-lv-input");
    lvMin.id = "tk-level-min";
    lvMin.className += " tk-lv-input";
    var lvMax = window.GWUI
      ? window.GWUI.input({ type: "number", num: true, size: "sm", min: 0, max: 80, placeholder: "最大", ariaLabel: "最高等级" })
      : h("input", "tk-lv-input");
    lvMax.id = "tk-level-max";
    lvMax.className += " tk-lv-input";
    lvWrap.appendChild(lvMin);
    lvWrap.appendChild(h("span", "tk-lv-sep", "–"));
    lvWrap.appendChild(lvMax);
    filters.appendChild(lvWrap);

    [["tk-hide-done", "隐藏已完成"], ["tk-only-done", "只显示已完成"],
     ["tk-hide-locked", "隐藏暂不可接"], ["tk-only-match", "仅显示筛选结果"],
     ["tk-has-pre", "有前置任务"], ["tk-has-post", "有后续任务"]]
      .forEach(function (x) {
        if (window.GWUI) {
          filters.appendChild(window.GWUI.check({ id: x[0], label: x[1], className: "tk-check" }));
          return;
        }
        var lab = h("label", "tk-check");
        var cb = h("input");
        cb.type = "checkbox";
        cb.id = x[0];
        lab.appendChild(cb);
        lab.appendChild(h("span", null, x[1]));
        filters.appendChild(lab);
      });

    var btns = h("div", "tk-fbtn");
    [["tk-fit", "适配全图"], ["tk-zoom-in", "放大"], ["tk-zoom-out", "缩小"], ["tk-reset", "重置视图"],
     ["tk-expand-pre", "展开前置链"], ["tk-expand-post", "展开后续链"]].forEach(function (x) {
      var b = taskButton(x[1]);
      b.id = x[0];
      btns.appendChild(b);
    });
    filters.appendChild(btns);
    var modeNote = h("div", "tk-mode-note");
    modeNote.id = "tk-mode-note";
    head.appendChild(modeNote);
    head.appendChild(filters);
    root.appendChild(head);

    // 主体
    var body = h("div", "tk-body");
    var paneTree = h("div", "tk-pane tk-pane-tree");
    var stage = h("div", "tk-stage");
    var svg = svgEl("svg", { id: "tk-svg", class: "tk-svg", "aria-label": "任务关系树" });
    stage.appendChild(svg);
    var legend = h("div", "tk-legend");
    legend.appendChild(h("span", "tk-legend-title", "图例"));
    [["is-none", "○", "未开始"], ["is-active", "◐", "进行中"], ["is-done", "✓", "已完成"],
     ["is-fail", "✕", "已失败"]].forEach(function (s) {
      var item = h("span", "tk-legend-item");
      item.appendChild(h("i", "tk-legend-dot " + s[0], s[1]));
      item.appendChild(h("span", null, s[2]));
      legend.appendChild(item);
    });
    [["tk-legend-line", "必须完成（AND）"],
     ["tk-legend-line is-or", "满足其一（OR）"],
     ["tk-legend-line is-fail", "失败分支"],
     ["tk-legend-line is-cross", "跨商人依赖"]].forEach(function (x) {
      var edgeItem = h("span", "tk-legend-item");
      edgeItem.appendChild(h("i", x[0]));
      edgeItem.appendChild(h("span", null, x[1]));
      legend.appendChild(edgeItem);
    });
    legend.appendChild(h("span", "tk-legend-item tk-legend-note",
      "横向浅色带 = 一个商人的任务线；箭头为真实前置方向"));
    stage.appendChild(legend);
    paneTree.appendChild(stage);
    var side = h("aside", "tk-side");
    side.id = "tk-side";
    paneTree.appendChild(side);
    body.appendChild(paneTree);

    // R68：「商人任务」列表不再生成 DOM（见 skeleton 的页签说明）；任务列表自身的
    // 商人分组/筛选（db4 左列 + tk-trader 下拉）保持原样。
    var paneList = h("div", "tk-pane tk-pane-list");
    paneList.hidden = true;
    paneList.id = "tk-list";
    body.appendChild(paneList);

    var paneDetail = h("div", "tk-pane tk-pane-detail");
    paneDetail.hidden = true;
    paneDetail.id = "tk-detail";
    body.appendChild(paneDetail);

    var paneProgress = h("div", "tk-pane tk-pane-progress");
    paneProgress.hidden = true;
    paneProgress.id = "tk-progress";
    body.appendChild(paneProgress);

    // R19.90：剧情子页暂时下线重做，只显示「施工中」占位。
    // 旧剧情 UI（左侧索引 / 右侧剧情树）不再挂载，渲染代码保留待重做时接回。
    var paneStory = h("div", "tk-pane tk-pane-story");
    paneStory.hidden = true;
    paneStory.id = "tk-story";
    var storyWip = h("div", "tk-wip");
    storyWip.appendChild(h("b", "tk-wip-title", "施工中"));
    storyWip.appendChild(h("p", "tk-wip-desc", "剧情系统正在重做，完成后重新开放。"));
    paneStory.appendChild(storyWip);
    body.appendChild(paneStory);

    root.appendChild(body);

    var bar2 = h("footer", "tk-statusbar");
    bar2.appendChild(h("span", "tk-status-text", "正在加载任务数据…")).id = "tk-status-text";
    bar2.appendChild(h("span", "tk-counts", "")).id = "tk-counts";
    bar2.appendChild(h("span", "tk-datasrc", "")).id = "tk-datasrc";
    root.appendChild(bar2);

    return root;
  }

  function selectEl(id, label, options) {
    var wrap = h("label", "tk-sel");
    wrap.appendChild(h("span", "tk-sel-label", label));
    var sel;
    if (window.GWUI) {
      sel = window.GWUI.select({
        ariaLabel: label,
        options: options.map(function (o) { return { value: o[0], label: o[1] }; })
      });
      sel.className += " tk-sel-input";
    } else {
      sel = h("select");
      options.forEach(function (o) {
        var opt = h("option", null, o[1]);
        opt.value = o[0];
        sel.appendChild(opt);
      });
    }
    sel.id = id;
    wrap.appendChild(sel);
    return wrap;
  }

  var modeSubscribed = false;

  function mount() {
    var host = document.getElementById("task-view");
    if (!host) { return false; }
    // 订阅全局游戏模式（R19.27）：右上角控件或任何页面改模式 → 任务数据随之切换
    if (!modeSubscribed && window.GWGameMode && window.GWGameMode.onChange) {
      window.GWGameMode.onChange(onGlobalModeChange);
      modeSubscribed = true;
    }
    if (document.getElementById("task-root")) {
      state.el.root = document.getElementById("task-root");
      cacheEls();
      syncAboutSeasonNote();
      return true;
    }
    state.el.root = skeleton();
    host.appendChild(state.el.root);
    cacheEls();
    bind();
    loadProgress();
    loadUi();
    loadStoryProgress();
    loadStoryUi();
    // 初始模式 = 全局当前模式（可能是上次会话留下的 PvPS）
    state.mode = globalMode();
    open();
    syncAboutSeasonNote();
    return true;
  }

  function cacheEls() {
    state.el.svg = document.getElementById("tk-svg");
    state.el.stage = $(".tk-stage");
    state.el.side = document.getElementById("tk-side");
    state.el.list = document.getElementById("tk-list");
    state.el.detail = document.getElementById("tk-detail");
    state.el.progress = document.getElementById("tk-progress");
    state.el.story = document.getElementById("tk-story");
    state.el.storyList = document.getElementById("tk-story-list");
    state.el.storyMain = document.getElementById("tk-story-main");
    state.el.storySearch = document.getElementById("tk-story-search");
    state.el.storyStats = document.getElementById("tk-story-stats");
    state.el.search = document.getElementById("tk-search");
    state.el.statusText = document.getElementById("tk-status-text");
    state.el.counts = document.getElementById("tk-counts");
    state.el.datasrc = document.getElementById("tk-datasrc");
  }

  // ---------------------------------------------------------------- 事件
  function bind() {
    var root = state.el.root;
    // R73：点空白处收起「模式归属」行内说明（点在说明/触发按钮本身时不收）
    document.addEventListener("click", function (ev) {
      var t = ev.target;
      if (t && t.closest && t.closest(".tk-fact-scope")) { return; }
      closeScopeNotes();
    });
    // R72：账号面板里换版本时，顶栏下拉同步（仅控件同步）。
    window.addEventListener("gw:edition", function () { fillEditionOptions(); });
    root.addEventListener("click", function (ev) {
      var t = ev.target;
      if (!t || !t.closest) { return; }
      // R74：模式按钮已移除（唯一切换入口在右上角），这里只派发版本等点击。
      var tab = t.closest("[data-taskview]");
      if (tab) { setView(tab.dataset.taskview); return; }
      // R86：剧情页交互（全部走 data-* 委托，节点由 renderStory 重建也不会丢事件）
      var storyItem = t.closest("[data-story-id]");
      if (storyItem) { openStory(storyItem.dataset.storyId); return; }
      var storyFilter = t.closest("[data-story-filter]");
      if (storyFilter) {
        state.storyFilter = storyFilter.dataset.storyFilter || "all";
        saveStoryUi();
        renderStory();
        return;
      }
      var storyStep = t.closest("[data-story-step-toggle]");
      if (storyStep) { requestStoryStepToggle(storyStep.dataset.storyStepToggle); return; }
      // R101：整行（圆点 / 步骤名 / 卡片空白处）同样算勾选。按钮只有几十像素宽，
      // 用户点在行上不该毫无反应；有前置时同样先弹窗，不会静默改写。
      var storyNode = t.closest("[data-story-node]");
      if (storyNode) { requestStoryStepToggle(storyNode.dataset.storyNode); return; }
      var storyChoice = t.closest("[data-story-choice]");
      if (storyChoice) {
        chooseStoryOption(storyChoice.dataset.storyChoice, storyChoice.dataset.storyValue);
        return;
      }
      var storyExpand = t.closest("[data-story-expand]");
      if (storyExpand) {
        var sid = storyExpand.dataset.storyExpand;
        state.storyExpand[sid] = !state.storyExpand[sid];
        state.storyStep = null;
        saveStoryUi();
        renderStory();
        return;
      }
      var storyLink = t.closest("[data-story-open]");
      if (storyLink) { openStory(storyLink.dataset.storyOpen); return; }
      // 目标点「在地图定位」（防止 label 把点击当成勾选）
      var loc = t.closest("[data-db4-loc]");
      if (loc) {
        ev.preventDefault();
        var parts = loc.dataset.db4Loc.split("|");
        locateByObjective(parts[0], parts[1]);
        return;
      }
      // R41：db4 风格任务板的商人头像条 / 排序 / 状态筛选
      var db4Trader = t.closest("[data-db4-trader]");
      if (db4Trader) {
        var tid = db4Trader.dataset.db4Trader;
        state.list.trader = state.list.trader === tid ? "" : tid;
        renderListRows();
        return;
      }
      var db4Sort = t.closest("[data-db4-sort]");
      if (db4Sort) {
        state.list.sort = db4Sort.dataset.db4Sort;
        renderListRows();
        return;
      }
      var db4Status = t.closest("[data-db4-status]");
      if (db4Status) {
        state.list.status = db4Status.dataset.db4Status;
        renderListRows();
        return;
      }
      var db4Reset = t.closest("[data-db4-reset]");
      if (db4Reset) {
        state.list.search = "";
        state.list.status = "";
        state.list.trader = "";
        state.list.map = "";
        renderListRows();
        return;
      }
      var listOpen = t.closest("[data-list-open-task]");
      if (listOpen) { openTask(listOpen.dataset.listOpenTask); return; }
      var listStatus = t.closest("[data-list-status]");
      if (listStatus) {
        requestStatusChange(listStatus.dataset.listTask, listStatus.dataset.listStatus);
        if (state.view === "list") { renderList(); }
        return;
      }
      var jump = t.closest("[data-jump-section]");
      if (jump) {
        var sec = document.getElementById(jump.dataset.jumpSection);
        if (sec) { sec.scrollIntoView({ block: "start", behavior: "smooth" }); }
        return;
      }
      var id = t.getAttribute("data-open-task") || (t.closest("[data-open-task]") || {}).dataset &&
        (t.closest("[data-open-task]") || {}).dataset.openTask;
      if (id) { openTask(id); return; }
      var copyBtn = t.closest("[data-copy-task-id]");
      if (copyBtn) { copyTaskId(copyBtn.dataset.copyTaskId, copyBtn); return; }
      var st = t.getAttribute("data-set-status");
      if (st && state.selected) { requestStatusChange(state.selected, st); return; }
      var loc = t.getAttribute("data-locate");
      if (loc) { locateSelected(); return; }
      var zi = t.getAttribute("data-locate-zone");
      if (zi !== null && zi !== "") { locateZoneByIndex(Number(zi)); return; }
      if (t.id) {
        switch (t.id) {
          case "tk-fit": fitTree(); break;
          case "tk-zoom-in": zoomBy(1.2); break;
          case "tk-zoom-out": zoomBy(1 / 1.2); break;
          case "tk-reset": resetCam(); break;
          case "tk-expand-pre": expandChain("pre"); break;
          case "tk-expand-post": expandChain("post"); break;
        }
      }
    });

    // R82：搜索 / 商人 / 状态 / 地图 四个控件由 js/app-menubar.js 上提到上下文栏，
    // change 不再冒泡到 task-view，所以同一处理器再挂一份到上下文栏的「任务」槽
    // （两个目标互不包含，不会重复触发；槽不存在时保持原行为）。
    function onChange(ev) {
      var t = ev.target;
      if (!t) { return; }
      if (t.dataset && t.dataset.listObj) {
        var parts = t.dataset.listObj.split("|");
        toggleObjective(parts[0], parts[1]);
        if (state.view === "list") { renderListRows(); }
        return;
      }
      if (!t.id) { return; }
      switch (t.id) {
        case "tk-list-status": state.list.status = t.value; renderListRows(); return;
        case "tk-list-sort": state.list.sort = t.value; renderListRows(); return;
        case "tk-list-map": state.list.map = t.value; renderListRows(); return;
        case "tk-list-trader": state.list.trader = t.value; renderListRows(); return;
        case "tk-list-allobj": state.list.allObj = t.checked; renderListRows(); return;
        case "tk-trader": state.filters.trader = t.value; break;
        case "tk-status": state.filters.status = t.value; break;
        case "tk-map": state.filters.map = t.value; break;
        case "tk-special": state.filters.special = t.value; break;
        case "tk-level-min": state.filters.levelMin = Number(t.value) || 0; break;
        case "tk-level-max": state.filters.levelMax = Number(t.value) || 0; break;
        case "tk-hide-done": state.filters.hideDone = t.checked; break;
        case "tk-only-done": state.filters.onlyDone = t.checked; break;
        case "tk-has-pre": state.filters.hasPre = t.checked; break;
        case "tk-has-post": state.filters.hasPost = t.checked; break;
        case "tk-hide-locked": state.filters.hideLocked = t.checked; break;
        case "tk-only-match": state.filters.onlyMatch = t.checked; break;
        case "tk-player-level":
          state.ui.playerLevel = Number(t.value) || 0;
          saveUi();
          renderAll();
          return;
        case "tk-sort":
          state.ui.sort = t.value;
          saveUi();
          return;
        case "tk-import-file":
          importFromFile(t.files && t.files[0]);
          return;
        default: break;
      }
      saveUi();
      refreshVisual();
    }

    root.addEventListener("change", onChange);
    (function () {
      var ctx = document.getElementById("cb-tasks");
      if (ctx && !root.contains(ctx)) { ctx.addEventListener("change", onChange); }
    })();

    if (state.el.search) {
      state.el.search.addEventListener("input", function () {
        state.search = state.el.search.value.trim();
        saveUi();
        runSearch();
      });
      state.el.search.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter") { ev.preventDefault(); nextMatch(ev.shiftKey ? -1 : 1); }
        if (ev.key === "Escape") { state.el.search.value = ""; state.search = ""; runSearch(); }
      });
    }

    if (state.el.storySearch) {
      state.el.storySearch.addEventListener("input", function () {
        state.storySearch = state.el.storySearch.value.trim();
        saveStoryUi();
        renderStory();
      });
      state.el.storySearch.addEventListener("keydown", function (ev) {
        if (ev.key === "Escape") {
          state.el.storySearch.value = "";
          state.storySearch = "";
          saveStoryUi();
          renderStory();
        }
      });
    }

    bindTreeInput();
    document.addEventListener("gwtasks:progress", function () {
      updateCounts();
      if (state.view === "list") { renderListRows(); }
    });
  }

  function setView(view) {
    state.view = ["tree", "list", "detail", "progress", "story"].indexOf(view) >= 0 ? view : "list";
    saveUi();
    // R216：db4 皮肤只属于「任务列表」子页（R41 照 db4tarkov Quest 页做的任务板）。
    // 旧版 ensureListUI() 会把 db4 加到整个 .tk-shell 且从不移除，于是进过列表页后
    // 全局页签 / 头部 / 状态栏一直挂着 db4 皮肤，切到任务树 / 剧情等 XP 子页就串台。
    // 这里按当前子页开关，让每种子页拿到自己的一整套皮肤。
    if (state.el.root) { state.el.root.classList.toggle("db4", state.view === "list"); }
    $$("[data-taskview]", state.el.root).forEach(function (b) {
      b.setAttribute("aria-selected", String(b.dataset.taskview === state.view));
    });
    ["tree", "list", "detail", "progress", "story"].forEach(function (v) {
      var pane = $(".tk-pane-" + v, state.el.root);
      if (pane) { pane.hidden = v !== state.view; }
    });
    // 筛选条只对「任务树」有意义；列表页有自己的工具条
    var filters = $(".tk-filters", state.el.root);
    if (filters) { filters.hidden = (state.view === "detail" || state.view === "progress" || state.view === "list" || state.view === "story"); }
    // R86：剧情页自带左侧索引，任务侧栏在该视图隐藏（不影响任务树/列表）
    if (state.el.side) { state.el.side.hidden = (state.view === "story"); }
    if (state.view === "list") { ensureTaskImages(); renderList(); }
    if (state.view === "detail") { renderDetail(); }
    if (state.view === "progress") { renderProgress(); }
    // R19.90：剧情子页暂时下线重做，只显示「施工中」占位（不加载剧情数据）
    if (state.view === "tree") { requestAnimationFrame(function () { focusStart(); }); }
  }

  /**
   * 切换全局游戏模式。模式的所有者是 js/game-mode.js（右上角控件 + localStorage）；
   * 这里只把「任务模块随模式换数据」的副作用挂在其回调上，页面间不会各存一份模式。
   */
  function setMode(mode) {
    if (MODE_KEYS.indexOf(mode) < 0) { return; }
    var G = window.GWGameMode;
    if (G && G.set) {
      G.set(mode, true);           // 通知 → onGlobalModeChange → applyMode
      return;
    }
    applyMode(mode);               // 全局模块缺失时的降级：仍然只改任务模块自己
  }

  /** 真正执行模式切换（GWGameMode 通知回调 / 降级路径共用）。 */
  function applyMode(mode) {
    if (MODE_KEYS.indexOf(mode) < 0) { return; }
    if (mode === state.mode && state.cache[mode]) {
      renderModeNote();
      return;
    }
    // 先把当前模式的浏览状态存起来，再切指针
    snapshotMode();
    state.mode = mode;
    state.graph = null;
    restoreMode(mode);
    state.matches = [];
    state.matchIdx = -1;
    saveUi();
    open();
  }

  /** 全局模式变化回调（含「其它页面切的模式」）。 */
  function onGlobalModeChange(key) {
    applyMode(key);
  }

  function open() {
    if (!state.el.root) { return; }
    var want = state.mode;                     // 记住本次要打开的模式
    // R73：模式切换过渡 —— 旧列表保留并轻微降透明度，避免白屏抖动。
    state.el.root.classList.add("is-mode-loading");
    state.el.root.setAttribute("aria-busy", "true");
    renderModeNote();
    var cached = !!state.cache[state.mode];
    setStatusText(cached ? "已切换到 " + modeLabel() + "（内存缓存，即时生效）"
      : "正在加载 " + modeLabel() + " 任务数据…");
    ensureData(state.mode).then(function (ok) {
      if (state.mode !== want) { return; }     // 期间又切走了：不覆盖新模式
      if (!ok) {
        setStatusText("任务数据加载失败：" + (state.error || "未知错误") + "（可点击「重置视图」重试）");
        state.el.root.classList.remove("is-mode-loading");
        state.el.root.setAttribute("aria-busy", "false");
        renderAll();
        return;
      }
      pruneModeState();
      if (state.el.search) { state.el.search.value = state.search || ""; }
      buildFilterOptions();
      setView(state.view);
      renderAll();
      state.el.root.classList.remove("is-mode-loading");
      state.el.root.setAttribute("aria-busy", "false");
      // R73：模式切换后数据集整体变化，保留旧滚动位置没有意义 → 回到顶部。
      // 列表页真正的滚动容器是内层 .db4-scroll（外层 tk-pane 不滚），两处都要归零。
      if (state.el.paneList) { state.el.paneList.scrollTop = 0; }
      if (state.el.paneList) {
        var db4Scroll = state.el.paneList.querySelector(".db4-scroll");
        if (db4Scroll) { db4Scroll.scrollTop = 0; db4Scroll.scrollLeft = 0; }
      }
      if (state.el.paneTree) { state.el.paneTree.scrollTop = 0; }
      var meta = state.dataMeta || {};
      setStatusText("已载入 " + (meta.modeLabel || state.mode) + " 任务 " +
        (state.order.length) + " 个 · 目标 " +
        ((meta.counts && meta.counts.objectives) || 0) + " 条 · 数据 " +
        String(meta.generatedAt || "").slice(0, 10));
      // R77：深链排队的任务在数据就绪后打开；找不到就明确提示，不静默停在别处。
      if (state.pendingTaskOpen) {
        var pid = state.pendingTaskOpen;
        state.pendingTaskOpen = null;
        if (state.tasks[pid]) {
          state.selected = pid;
          state.view = "detail";
          saveUi();
          setView("detail");
          renderSide();
          scrollDetailTop();
        } else {
          showMissingTask(pid);
        }
      }
      // R86：剧情深链同理（stories.json 与任务数据互不依赖，各自排队）
      if (state.pendingStoryOpen) {
        var ps = state.pendingStoryOpen;
        state.pendingStoryOpen = null;
        openStory(ps.storyId, ps.stepId);
      }
      requestAnimationFrame(function () {
        if (state.keepCam) { state.keepCam = false; applyCam(); }
        else { focusStart(); }
      });
    });
  }

  function modeNow() { return state.mode; }

  function modeLabel(key) {
    var m = MODE_BY_KEY[key || state.mode];
    return m ? m.full : (key || state.mode);
  }

  /** 头部模式说明条：中文说明 + 该模式数据规模 / 来源 / 数据缺口（如实说明）。 */
  /** R72：版本短名 —— 优先用数据里的中文别名（白边/黑边/蓝边），没有就用中文全名。 */
  function editionShort(ed) {
    var alias = (ed.aliases || [])[0] || "";
    if (/[\u4e00-\u9fa5]/.test(alias)) { return alias; }
    return ed.nameZh || ed.nameEn || ed.id;
  }

  /** 用 GWDataScope.editions 填充版本下拉；数据尚未落地时只留「未选版本」。 */
  var editionsRequested = false;
  function fillEditionOptions() {
    var sel = document.getElementById("tk-edition");
    if (!sel) { return; }
    var DS = window.GWDataScope;
    var list = (DS && DS.editions) || [];
    // R72：任务页首次进入时主动拉取一次版本清单（与账号面板共用 loadEditions 缓存）。
    if (!list.length && DS && DS.ensureEditions && !editionsRequested) {
      editionsRequested = true;
      Promise.resolve(DS.ensureEditions()).then(function () { fillEditionOptions(); });
      return;
    }
    var cur = "";
    try { cur = (DS && DS.get && DS.get().edition) || ""; } catch (e) { cur = ""; }
    if (sel.options.length !== list.length + 1) {
      sel.innerHTML = "";
      var none = document.createElement("option");
      none.value = "";
      none.textContent = "未选版本";
      sel.appendChild(none);
      list.forEach(function (ed) {
        var opt = document.createElement("option");
        opt.value = ed.id;
        opt.textContent = editionShort(ed);
        opt.title = (ed.nameZh || "") + (ed.nameEn ? " / " + ed.nameEn : "");
        sel.appendChild(opt);
      });
    }
    sel.value = cur || "";
    sel.title = "账号版本只更新版本对照说明；按现设计不影响任务数与价格";
  }

  /** 同步分段按钮的选中态（与全局模式保持一致）。 */
  function syncScopeBar() {
    var host = document.getElementById("tk-scope-bar");
    if (host) {
      Array.prototype.forEach.call(host.querySelectorAll("[data-tsmode]"), function (btn) {
        var on = btn.getAttribute("data-tsmode") === state.mode;
        btn.classList.toggle("is-on", on);
        btn.setAttribute("aria-selected", on ? "true" : "false");
        btn.setAttribute("aria-checked", on ? "true" : "false");
        btn.tabIndex = on ? 0 : -1;
      });
    }
    fillEditionOptions();
  }

  function renderModeNote() {
    var host = document.getElementById("tk-mode-note");
    var scope = document.getElementById("tk-scope");
    var m = MODE_BY_KEY[state.mode] || MODES[0];
    if (scope) {
      scope.textContent = "当前模式：" + m.full;
      scope.setAttribute("title", m.en);
      scope.setAttribute("data-en-text", m.en);
    }
    var hint = document.getElementById("tk-mode-hint");
    if (hint) {
      hint.textContent = "模式：" + m.full;
      hint.title = m.en;
      hint.setAttribute("data-en-text", m.en);
    }
    syncScopeBar();
    if (!host) { return; }
    host.innerHTML = "";
    host.className = "tk-mode-note is-" + state.mode;
    var meta = (state.cache[state.mode] || {}).meta || null;
    var txt = m.note;
    if (meta) {
      var c = meta.counts || {};
      txt += " 共 " + (c.tasks || 0) + " 个任务 / " + (c.objectives || 0) + " 条目标 / " +
        (c.edges || 0) + " 条前置关系。";
      // 上游端点 / 生成时间这类元信息统一放菜单「关于」，模式说明条只说玩法差异
    }
    host.appendChild(h("span", "tk-mode-note-text", txt));
    // 赛季服：把「赛季专属任务为 0」这类事实写明，用户不会以为漏了数据
    if (state.mode === "pvps") {
      var season = state.season || {};
      var extra = [];
      if (season.nameZh) {
        extra.push("当前赛季：" + season.nameZh);
      } else if (season.nameEn) {
        // 上游中文表只给了英文赛季名 → 原样保留并说明，不自己造译名
        extra.push("当前赛季：" + season.nameEn + "（上游未提供中文译名）");
      }
      if (season.startISO || season.endISO) {
        extra.push("周期 " + (season.startISO || "?") + " → " + (season.endISO || "?"));
      }
      var cross = (state.cache.pvps || {}).meta && state.cache.pvps.meta.cross || {};
      var sub = (cross.subsetOf || []).indexOf("regular") >= 0;
      if (sub) {
        extra.push("上游 pvp-season 快照中没有只属于赛季的任务，本模式任务集是 PvP 的子集（不补造赛季任务）");
      }
      if (extra.length) {
        var warn = h("span", "tk-mode-note-warn", extra.join("；") + "。");
        warn.setAttribute("title", "数据缺口说明：本项目只展示上游真实下发的内容");
        host.appendChild(warn);
      }
    }
  }

  function setStatusText(text) {
    if (state.el.statusText) { state.el.statusText.textContent = text; }
  }

  // ---------------------------------------------------------------- 筛选与搜索
  function passes(rec) {
    var f = state.filters;
    if (f.trader && rec.traderId !== f.trader) { return false; }
    if (f.status && statusOf(rec.id) !== f.status) { return false; }
    if (f.map && (rec.maps || []).indexOf(f.map) < 0) { return false; }
    if (f.special === "kappa" && !rec.kappaRequired) { return false; }
    if (f.special === "lightkeeper" && !rec.lightkeeperRequired) { return false; }
    if (f.special === "story" && rec.taskType !== "story") { return false; }
    if (f.special === "faction" && rec.faction === "Any") { return false; }
    if (f.special === "season" && !rec.seasonOnly) { return false; }
    if (f.levelMin && rec.minLevel < f.levelMin) { return false; }
    if (f.levelMax && rec.minLevel > f.levelMax) { return false; }
    if (f.onlyDone && statusOf(rec.id) !== "completed") { return false; }
    if (f.hideDone && !f.onlyDone && statusOf(rec.id) === "completed") { return false; }
    if (f.hasPre && !(rec.prerequisites || []).length) { return false; }
    if (f.hasPost && !(rec.followUps || []).length) { return false; }
    if (f.hideLocked) {
      var av = availability(rec);
      if (av.state === "blocked") { return false; }
    }
    return true;
  }

  /** 当前模式下「赛季专属」任务数（用于决定是否显示该筛选项，避免假筛选）。 */
  function seasonOnlyCount() {
    return state.order.filter(function (id) { return state.tasks[id].seasonOnly; }).length;
  }

  function buildFilterOptions() {
    // 每个模式的任务/地图集合不同 → 选项按模式重建（用 builtMode 记住给哪个模式建的）
    var traderSel = document.getElementById("tk-trader");
    if (traderSel && traderSel.dataset.builtMode !== state.mode) {
      var counts = {};
      state.order.forEach(function (id) { counts[state.tasks[id].traderId] = (counts[state.tasks[id].traderId] || 0) + 1; });
      Array.prototype.slice.call(traderSel.options).forEach(function (o) { if (o.value) { o.remove(); } });
      Object.keys(state.traders).forEach(function (tid) {
        if (!counts[tid]) { return; }
        var o = h("option", null, (state.traders[tid].nameEn || "未收录商人") + "（" + counts[tid] + "）");
        o.setAttribute("data-i18n-skip", "1");   // 商人名是"英文原名"的显式例外
        o.value = tid;
        traderSel.appendChild(o);
      });
      traderSel.dataset.builtMode = state.mode;
      traderSel.value = state.filters.trader || "";
    }
    var mapSel = document.getElementById("tk-map");
    if (mapSel && mapSel.dataset.builtMode !== state.mode) {
      var maps = {};
      state.order.forEach(function (id) {
        (state.tasks[id].maps || []).forEach(function (m) { maps[m] = (maps[m] || 0) + 1; });
      });
      Array.prototype.slice.call(mapSel.options).forEach(function (o) { if (o.value) { o.remove(); } });
      Object.keys(maps).sort().forEach(function (m) {
        var o = h("option", null, m + "（" + maps[m] + "）");
        o.value = m;
        mapSel.appendChild(o);
      });
      mapSel.dataset.builtMode = state.mode;
      mapSel.value = state.filters.map || "";
    }
    // 「赛季专属」只在当前模式确实有赛季专属任务时出现（当前上游快照为 0 → 不显示假开关）
    var sp = document.getElementById("tk-special");
    if (sp) {
      var opt = sp.querySelector('option[value="season"]');
      var need = seasonOnlyCount() > 0;
      if (need && !opt) {
        opt = h("option", null, "赛季专属（" + seasonOnlyCount() + "）");
        opt.value = "season";
        sp.appendChild(opt);
      } else if (!need && opt) {
        if (state.filters.special === "season") { state.filters.special = ""; }
        opt.remove();
      }
      sp.value = state.filters.special || "";
    }
    var st = document.getElementById("tk-status");
    if (st) { st.value = state.filters.status || ""; }
    var lvMin = document.getElementById("tk-level-min");
    var lvMax = document.getElementById("tk-level-max");
    if (lvMin) { lvMin.value = state.filters.levelMin || ""; }
    if (lvMax) { lvMax.value = state.filters.levelMax || ""; }
    [["tk-hide-done", "hideDone"], ["tk-only-done", "onlyDone"],
     ["tk-hide-locked", "hideLocked"], ["tk-only-match", "onlyMatch"],
     ["tk-has-pre", "hasPre"], ["tk-has-post", "hasPost"]].forEach(function (pair) {
      var el = document.getElementById(pair[0]);
      if (el) { el.checked = !!state.filters[pair[1]]; }
    });
  }

  function runSearch() {
    state.matches = [];
    state.matchIdx = -1;
    if (!state.search) { refreshVisual(); updateCounts(); return; }
    var q = state.search.toLowerCase();
    state.order.forEach(function (id) {
      var rec = state.tasks[id];
      if (!rec) { return; }
      var hay = [rec.nameZh, rec.englishName, rec.nameEn, rec.id].join(" ").toLowerCase();
      if (hay.indexOf(q) >= 0) { state.matches.push(id); }
    });
    state.matchIdx = state.matches.length ? 0 : -1;
    refreshVisual();
    if (state.matchIdx === 0) { centerOnTask(state.matches[0]); }
    updateCounts();
  }

  function nextMatch(dir) {
    if (!state.matches.length) { return; }
    state.matchIdx = (state.matchIdx + (dir || 1) + state.matches.length) % state.matches.length;
    var id = state.matches[state.matchIdx];
    centerOnTask(id);
    refreshVisual();
    setStatusText("匹配 " + (state.matchIdx + 1) + "/" + state.matches.length + "：" + state.tasks[id].nameZh);
  }

  // ---------------------------------------------------------------- 树布局
  /**
   * R19.25：布局交给 js/task-graph-layout.js（纯计算模块，按模式缓存）。
   *
   * 旧实现的问题（审计见 docs/r19.25-task-tree/audit.md）：
   *   层级 = 从前置算出的最长路径，而真实数据里 503 个任务中有 300 个没有前置，
   *   于是全部堆在第 0 列（画布 18000px 高）；列内又按商人/等级排序，
   *   与父节点毫无关系 → 974 处直线交叉、32 条边穿过别的卡片。
   *
   * 新实现：分量（任务线）为块 + 商人分带 + 分量内分层/中位数排序 + 正交连线。
   */
  function layoutRev() {
    return state.mode + ":" + Object.keys(state.tasks).length + ":" +
      String((state.dataMeta || {}).generatedAt || "");
  }

  function buildGraph() {
    var G = window.GWTaskGraph;
    if (!G) { return null; }
    var cache = state.layoutCache || (state.layoutCache = {});
    var hit = cache[state.mode];
    if (hit && hit.rev === layoutRev()) { return hit; }
    var r = G.layout(state.tasks, {
      traderOrder: Object.keys(state.traders),
      nodeW: NODE_W, nodeH: NODE_H
    });
    var nodes = {};
    r.nodes.forEach(function (n) { nodes[n.id] = n; });
    var graph = {
      nodes: nodes,
      ids: r.nodes.map(function (n) { return n.id; }),
      index: r.index,
      edges: r.edges,
      bands: r.bands,
      width: r.width,
      height: r.height,
      metrics: r.metrics,
      rev: layoutRev()
    };
    cache[state.mode] = graph;
    return graph;
  }

  function renderTree() {
    var svg = state.el.svg;
    if (!svg) { return; }
    while (svg.firstChild) { svg.removeChild(svg.firstChild); }
    if (!state.order.length) { return; }
    var graph = buildGraph();
    if (!graph) {
      var warn = svgEl("text", { x: 16, y: 28, class: "tk-node-meta" });
      warn.textContent = "布局模块未加载（js/task-graph-layout.js）";
      svg.appendChild(warn);
      return;
    }
    state.graph = graph;

    var defs = svgEl("defs");
    [["tk-arrow", "tk-arrow-head"], ["tk-arrow-or", "tk-arrow-head is-or"],
     ["tk-arrow-fail", "tk-arrow-head is-fail"]].forEach(function (m) {
      var marker = svgEl("marker", {
        id: m[0], viewBox: "0 0 10 10", refX: "9", refY: "5",
        markerWidth: "7", markerHeight: "7", orient: "auto-start-reverse"
      });
      marker.appendChild(svgEl("path", { d: "M0,0 L10,5 L0,10 z", class: m[1] }));
      defs.appendChild(marker);
    });
    svg.appendChild(defs);

    var cam = svgEl("g", { class: "tk-cam", id: "tk-cam" });
    var gBands = svgEl("g", { class: "tk-bands", id: "tk-bands" });
    var gEdges = svgEl("g", { class: "tk-edges", id: "tk-edges" });
    var gNodes = svgEl("g", { class: "tk-nodes", id: "tk-nodes" });
    cam.appendChild(gBands);
    cam.appendChild(gEdges);
    cam.appendChild(gNodes);
    svg.appendChild(cam);

    // 商人分带：横向一条带 = 一个商人的全部任务线（带标题写英文原名）
    (graph.bands || []).forEach(function (band) {
      var t = state.traders[band.trader] || {};
      // 带宽按该带的真实内容收口（不再横贯全图留下大片空白背景）
      var bx = 8, by = band.y + 2;
      var bw = Math.max((band.w || (graph.width - 16)) - 8, 200);
      var bh = Math.max(band.h - 6, 26);
      gBands.appendChild(svgEl("rect", {
        class: "tk-band", x: bx, y: by, width: bw, height: bh, rx: 2,
        "data-trader": band.trader
      }));
      var label = svgEl("text", {
        class: "tk-band-label", x: bx + 8, y: band.labelY, "data-trader": band.trader
      });
      label.textContent = (t.nameEn || band.trader || "未收录商人") + " · " + band.nodes + " 个任务" +
        (band.foreign ? " · 跨商人线 " + band.foreign : "");
      gBands.appendChild(label);
      var line = svgEl("line", {
        class: "tk-band-rule", x1: bx + 8, y1: band.labelY + 4,
        x2: bx + bw - 8, y2: band.labelY + 4
      });
      gBands.appendChild(line);
    });

    // 连线：正交折线（点集来自布局模块），OR / 失败分支 / 跨商人分别标注
    (graph.edges || []).forEach(function (e) {
      var fromRec = state.tasks[e.from] || {};
      var toRec = state.tasks[e.to] || {};
      var d = "M" + e.points.map(function (p) { return p[0] + "," + p[1]; }).join(" L ");
      var cls = "tk-edge";
      var marker = "url(#tk-arrow)";
      var tip = "";
      if (e.kind === "fail") {
        cls += " is-fail";
        marker = "url(#tk-arrow-fail)";
        var f = (toRec.failedConditions || []).filter(function (x) { return x.taskId === e.from; })[0] || {};
        tip = "失败分支：" + (fromRec.nameZh || e.from) + "（" + (f.statuses || []).join("/") +
          "）会导致 " + (toRec.nameZh || e.to) + " 失败";
      } else if (e.kind === "or") {
        cls += " is-or";
        marker = "url(#tk-arrow-or)";
        tip = "满足其一即可（OR）：" + (fromRec.nameZh || e.from) + " → " + (toRec.nameZh || e.to);
      } else {
        tip = "必须完成（AND）：" + (fromRec.nameZh || e.from) + " → " + (toRec.nameZh || e.to);
      }
      if (e.crossTrader) { cls += " is-cross"; }
      if (e.span > 1) { cls += " is-long"; }
      if (e.cycle) {
        cls += " is-cycle";
        marker = "url(#tk-arrow-fail)";
        tip = "环状依赖（数据里 A/B 互为前置）：" + (fromRec.nameZh || e.from) + " → " + (toRec.nameZh || e.to);
      }
      var path = svgEl("path", {
        d: d, class: cls, "marker-end": marker,
        "data-from": e.from, "data-to": e.to, "data-kind": e.kind,
        "data-span": String(e.span || 0)
      });
      var t = svgEl("title");
      t.textContent = tip + (e.crossTrader ? "（跨商人依赖）" : "");
      path.appendChild(t);
      gEdges.appendChild(path);
    });

    // 节点
    graph.ids.forEach(function (id) {
      var n = graph.nodes[id];
      var rec = state.tasks[id];
      if (!n || !rec) { return; }
      var g = svgEl("g", {
        class: "tk-node " + STATUS[statusOf(id)].cls +
          (rec.seasonOnly ? " is-season" : "") +
          (rec.onlyInModes && rec.onlyInModes.length ? " is-modeonly" : "") +
          (n.crossTrader ? " is-crosstrader" : ""),
        transform: "translate(" + n.x + "," + n.y + ")",
        "data-id": id, "data-mode": state.mode, "data-comp": String(n.comp),
        tabindex: "0", role: "button"
      });
      g.appendChild(svgEl("rect", { class: "tk-node-bg", width: NODE_W, height: NODE_H, rx: 2 }));
      var glyph = svgEl("text", { class: "tk-node-glyph", x: 10, y: NODE_H / 2 + 5 });
      glyph.textContent = STATUS[statusOf(id)].glyph;
      g.appendChild(glyph);
      var name = svgEl("text", { class: "tk-node-name", x: 26, y: 19 });
      name.textContent = clampLabel(rec.nameZh, 14);
      g.appendChild(name);
      var meta = svgEl("text", { class: "tk-node-meta", x: 26, y: 34 });
      var bits = [traderEn(rec), "Lv" + (rec.minLevel || 0), "目标 " + (rec.objectives || []).length];
      if (rec.faction && rec.faction !== "Any") { bits.push(rec.faction); }
      meta.textContent = clampText(bits.join(" · "), 24);
      g.appendChild(meta);
      var tip = svgEl("title");
      var tipBits = [rec.nameZh, enTitle(rec),
                     "商人：" + traderEn(rec),
                     "状态：" + STATUS[statusOf(id)].zh,
                     "模式：" + modeLabel()];
      if (rec.seasonOnly) { tipBits.push("赛季专属任务"); }
      if (rec.onlyInModes && rec.onlyInModes.length) {
        tipBits.push("仅出现在：" + rec.onlyInModes.map(modeLabel).join(" / "));
      }
      if (n.crossTrader) {
        tipBits.push("本条任务线的主商人是 " + traderEn(state.tasks[bandOwnerOf(n)] || rec));
      }
      if ((rec.failedConditions || []).length) {
        tipBits.push("失败分支 " + rec.failedConditions.length + " 条");
      }
      tip.textContent = tipBits.join("\n");
      g.appendChild(tip);
      if (rec.kappaRequired) {
        g.appendChild(svgEl("rect", { class: "tk-node-flag", x: NODE_W - 30, y: 6, width: 24, height: 12, rx: 2 }));
        var flag = svgEl("text", { class: "tk-node-flag-text", x: NODE_W - 18, y: 15, "text-anchor": "middle" });
        flag.textContent = "KAPPA";
        g.appendChild(flag);
      }
      if (rec.seasonOnly) {
        g.appendChild(svgEl("rect", { class: "tk-node-flag is-season", x: NODE_W - 34, y: NODE_H - 16,
                                      width: 28, height: 12, rx: 2 }));
        var sf = svgEl("text", { class: "tk-node-flag-text", x: NODE_W - 20, y: NODE_H - 7,
                                 "text-anchor": "middle" });
        sf.textContent = "赛季";
        g.appendChild(sf);
      }
      g.addEventListener("click", function (ev) {
        ev.stopPropagation();
        selectTask(id);
      });
      g.addEventListener("dblclick", function (ev) {
        ev.stopPropagation();
        openTask(id);
      });
      g.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); selectTask(id); }
      });
      gNodes.appendChild(g);
    });

    applyCam();
    refreshVisual();
  }

  /** 找某个节点所属任务线的主商人（用于提示文案）。 */
  function bandOwnerOf(node) {
    var t = state.tasks[node.id] || {};
    return t.traderId || "";
  }

  function applyCam() {
    var cam = document.getElementById("tk-cam");
    if (!cam) { return; }
    cam.setAttribute("transform", "translate(" + state.cam.x + "," + state.cam.y + ") scale(" + state.cam.k + ")");
  }

  function resetCam() {
    var box = state.el.svg && state.el.svg.getBoundingClientRect();
    var g = state.graph;
    if (!box || !g) { return; }
    state.cam.k = Math.min((box.width - 24) / Math.max(g.width, 1), (box.height - 24) / Math.max(g.height, 1), 1);
    state.cam.x = 12;
    state.cam.y = 12;
    applyCam();
  }

  /** 首次进入：整图适配往往缩到 0.2 倍（字看不清），改为 0.55 倍落在最左列，
   *  用户点「适配全图」再看全局。 */
  /**
   * 初始视角（R19.25）：500 个节点的全图看不到字，所以默认落在**第一条商人带**（Prapor）
   * 的可读区域；想看全貌点「适配全图」，想回到起点点「重置视图」。
   */
  function focusStart() {
    if (!state.graph || !state.el.svg) { return; }
    var box = state.el.svg.getBoundingClientRect();
    if (!box.width || !box.height) { return; }
    var fitK = Math.min((box.width - 32) / Math.max(state.graph.width, 1),
                        (box.height - 32) / Math.max(state.graph.height, 1), 1.4);
    if (fitK >= 0.55) { fitTree(); return; }
    // 第一条带（若带太高，只取它的前 3 行高度）
    var band = (state.graph.bands || [])[0];
    var k = 0.72;
    var targetH = box.height / k;
    state.cam.k = k;
    state.cam.x = 12;
    state.cam.y = band ? -(band.y + 6) * k + 8 : 16;
    if (band && band.h * k < box.height * 0.6) { state.cam.y = -(band.y) * k + 10; }
    if (targetH < 200) { state.cam.k = 0.55; }
    applyCam();
  }

  function fitTree() {
    if (!state.graph || !state.el.svg) { return; }
    var box = state.el.svg.getBoundingClientRect();
    if (!box.width || !box.height) { return; }
    var g = state.graph;
    var k = Math.min((box.width - 32) / Math.max(g.width, NODE_W), (box.height - 32) / Math.max(g.height, NODE_H), 1.4);
    if (!isFinite(k) || k <= 0) { k = 1; }
    state.cam.k = k;
    state.cam.x = (box.width - g.width * k) / 2;
    state.cam.y = (box.height - g.height * k) / 2;
    applyCam();
  }

  function zoomBy(factor) {
    var svg = state.el.svg;
    if (!svg) { return; }
    var box = svg.getBoundingClientRect();
    var cx = box.width / 2, cy = box.height / 2;
    var k0 = state.cam.k;
    var k1 = Math.max(0.12, Math.min(2.6, k0 * factor));
    state.cam.x = cx - (cx - state.cam.x) * (k1 / k0);
    state.cam.y = cy - (cy - state.cam.y) * (k1 / k0);
    state.cam.k = k1;
    applyCam();
  }

  function centerOnTask(id) {
    var n = state.graph && state.graph.nodes[id];
    var svg = state.el.svg;
    if (!n || !svg) { return; }
    var box = svg.getBoundingClientRect();
    if (!box.width) { return; }
    state.cam.x = box.width / 2 - (n.x + NODE_W / 2) * state.cam.k;
    state.cam.y = box.height / 2 - (n.y + NODE_H / 2) * state.cam.k;
    applyCam();
  }

  function bindTreeInput() {
    var svg = state.el.svg;
    var stage = state.el.stage;
    if (!stage || stage.dataset.bound === "1") { return; }
    stage.dataset.bound = "1";
    var drag = null;
    stage.addEventListener("pointerdown", function (ev) {
      if (ev.target.closest && ev.target.closest(".tk-node")) { return; }
      drag = { x: ev.clientX, y: ev.clientY, cx: state.cam.x, cy: state.cam.y };
      stage.setPointerCapture && stage.setPointerCapture(ev.pointerId);
      stage.classList.add("is-panning");
    });
    stage.addEventListener("pointermove", function (ev) {
      if (!drag) { return; }
      state.cam.x = drag.cx + (ev.clientX - drag.x);
      state.cam.y = drag.cy + (ev.clientY - drag.y);
      applyCam();
    });
    var end = function () { drag = null; stage.classList.remove("is-panning"); saveUi(); };
    stage.addEventListener("pointerup", end);
    stage.addEventListener("pointercancel", end);
    stage.addEventListener("wheel", function (ev) {
      if (!svg || !svg.contains(ev.target)) { return; }
      ev.preventDefault();
      var box = svg.getBoundingClientRect();
      var px = ev.clientX - box.left, py = ev.clientY - box.top;
      var factor = ev.deltaY < 0 ? 1.12 : 1 / 1.12;
      var k0 = state.cam.k;
      var k1 = Math.max(0.12, Math.min(2.6, k0 * factor));
      state.cam.x = px - (px - state.cam.x) * (k1 / k0);
      state.cam.y = py - (py - state.cam.y) * (k1 / k0);
      state.cam.k = k1;
      applyCam();
      saveUi();                    // 记住该模式的缩放/位置，切回来不跳
    }, { passive: false });
  }

  // ---------------------------------------------------------------- 高亮
  function refreshVisual() {
    if (!state.graph) { return; }
    var sel = state.selected;
    var neighbours = {};
    if (sel) {
      (state.tasks[sel].prerequisites || []).forEach(function (p) { neighbours[p.taskId] = "pre"; });
      (state.tasks[sel].followUps || []).forEach(function (f) { neighbours[f] = "post"; });
    }
    var matchSet = {};
    state.matches.forEach(function (m) { matchSet[m] = 1; });
    var nodes = $$(".tk-node", state.el.svg);
    nodes.forEach(function (g) {
      var id = g.dataset.id;
      var rec = state.tasks[id];
      var pass = !rec ? false : passes(rec);
      var isMatch = !!matchSet[id];
      g.classList.toggle("is-dim", !pass || (state.search && !isMatch));
      g.classList.toggle("is-hidden", state.filters.onlyMatch && !pass);
      g.classList.toggle("is-match", !!isMatch);
      g.classList.toggle("is-selected", id === sel);
      g.classList.toggle("is-pre", neighbours[id] === "pre");
      g.classList.toggle("is-post", neighbours[id] === "post");
      g.classList.toggle("is-cur", state.matchIdx >= 0 && state.matches[state.matchIdx] === id);
    });
    $$(".tk-edge", state.el.svg).forEach(function (e) {
      var from = e.dataset.from, to = e.dataset.to;
      var hot = sel && (from === sel || to === sel);
      e.classList.toggle("is-hot", !!hot);
      e.classList.toggle("is-dim", !hot && !!sel);
    });
    updateCounts();
  }

  function updateCounts() {
    if (!state.el.counts) { return; }
    var c = countByStatus();
    var shown = state.order.filter(function (id) { return passes(state.tasks[id]); }).length;
    state.el.counts.textContent = "共 " + c.total + " 个任务 · 已完成 " + c.completed +
      " · 进行中 " + c.active + " · 筛选命中 " + shown +
      (state.matches.length ? " · 搜索 " + state.matches.length : "");
    if (state.el.datasrc && state.dataMeta) {
      var meta = state.dataMeta;
      state.el.datasrc.textContent = "数据：" + (meta.modeLabel || state.mode) +
        " · 生成于 " + String(meta.generatedAt || "").slice(0, 19).replace("T", " ") +
        " · 任务 " + (meta.counts && meta.counts.tasks || 0) + " · 目标 " +
        (meta.counts && meta.counts.objectives || 0) +
        (state.mode === "pvps" ? " · 赛季服" : "");
    }
  }

  // ---------------------------------------------------------------- 侧栏
  function selectTask(id) {
    state.missingTask = null;
    state.selected = id;
    saveUi();
    renderSide();
    refreshVisual();
    if (state.graph && state.graph.nodes[id]) { centerOnTask(id); }
  }

  /** 该任务在三种模式中的归属说明（只根据上游任务集合算，不猜）。 */
  function modeScopeText(rec) {
    if (rec.seasonOnly) { return "赛季专属任务（仅 PvPS 赛季服下发）"; }
    if (rec.onlyInModes && rec.onlyInModes.length) {
      return "仅出现在：" + rec.onlyInModes.map(modeLabel).join(" / ") +
        "（当前为 " + modeLabel() + "）";
    }
    return "三种模式都有此任务；目标/前置/进度仍按模式各自独立保存";
  }

  /**
   * R73：关闭所有已展开的「模式归属」行内说明。
   * 说明用绝对定位浮在字段区上方（不撑高整块），所以点击别处 / Esc / 换任务时必须收起，
   * 否则会挡住下面的「所属商人」「地图」两行。
   */
  function closeScopeNotes() {
    var open = $$(".tk-fact-note");
    for (var i = 0; i < open.length; i++) {
      if (!open[i].hidden) {
        open[i].hidden = true;
        var btn = open[i].parentNode && open[i].parentNode.querySelector(".tk-scope-toggle");
        if (btn) {
          btn.setAttribute("aria-expanded", "false");
          btn.textContent = String(btn.getAttribute("data-scope-label") || "") + " ▸";
        }
      }
    }
  }

  /** R72：详情「模式归属」只显示短标签，完整解释放 title/悬浮提示。 */
  function modeScopeShort(rec) {
    if (rec.seasonOnly) { return "仅赛季服"; }
    if (rec.onlyInModes && rec.onlyInModes.length) {
      return "仅 " + rec.onlyInModes.map(function (m) {
        return (MODE_BY_KEY[m] || {}).label || m;
      }).join("/");
    }
    return "全模式";
  }

  function renderSide() {
    var side = state.el.side;
    if (!side) { return; }
    side.innerHTML = "";
    var id = state.selected;
    if (!id || !task(id)) {
      side.appendChild(h("p", "tk-side-empty", "点击任务节点查看摘要；双击进入详细攻略。"));
      return;
    }
    var rec = task(id);
    var st = STATUS[statusOf(id)];
    var av = availability(rec);
    side.appendChild(decorateName(h("h3", "tk-side-title"), rec));
    var meta = h("p", "tk-side-meta");
    meta.textContent = "商人：" + traderEn(rec) + " · 等级 " + (rec.minLevel || 0) +
      " · 状态 " + st.zh;
    side.appendChild(meta);
    side.appendChild(h("p", "tk-side-scope", modeScopeText(rec)));

    var badges = h("div", "tk-badges");
    if (rec.kappaRequired) { badges.appendChild(taskBadge("Kappa 必需", "warn", "is-kappa")); }
    if (rec.lightkeeperRequired) { badges.appendChild(taskBadge("灯塔相关", "info", "is-lk")); }
    if (rec.faction && rec.faction !== "Any") { badges.appendChild(taskBadge(rec.faction + " 限定", "primary")); }
    if (rec.restartable) { badges.appendChild(taskBadge("可重接", "muted")); }
    side.appendChild(badges);

    var obj = h("div", "tk-side-block");
    obj.appendChild(h("h4", null, "任务目标摘要（" + (rec.objectives || []).length + "）"));
    var ul = h("ul", "tk-side-obj");
    (rec.objectives || []).slice(0, 6).forEach(function (o) {
      var li = h("li", o.optional ? "is-opt" : null);
      li.textContent = (o.optional ? "（可选）" : "") + o.descZh;
      ul.appendChild(li);
    });
    if ((rec.objectives || []).length > 6) {
      ul.appendChild(h("li", "is-more", "另有 " + (rec.objectives.length - 6) + " 项目标…"));
    }
    obj.appendChild(ul);
    side.appendChild(obj);

    var rel = h("div", "tk-side-block");
    rel.appendChild(h("h4", null, "前置 " + (rec.prerequisites || []).length +
      " · 后续 " + (rec.followUps || []).length));
    var p1 = h("p", "tk-side-line");
    p1.textContent = "前置：" + ((prereqNames(rec, 4).join("、")) || "无");
    rel.appendChild(p1);
    var fu = (rec.followUps || []).map(function (f) { return task(f) ? task(f).nameZh : f; });
    var p2 = h("p", "tk-side-line");
    p2.textContent = "后续：" + ((fu.slice(0, 4).join("、")) || "无");
    rel.appendChild(p2);
    if (av.reasons.length) {
      var p3 = h("p", "tk-side-line is-warn");
      p3.textContent = "阻塞：" + av.reasons.slice(0, 2).join("；");
      rel.appendChild(p3);
    }
    side.appendChild(rel);

    var acts = h("div", "tk-side-actions");
    var btnDetail = taskButton("查看详细攻略");
    btnDetail.dataset.openTask = id;
    acts.appendChild(btnDetail);
    var btnLoc = taskButton("在地图定位");
    btnLoc.setAttribute("data-locate", "1");
    acts.appendChild(btnLoc);
    side.appendChild(acts);

    var sts = h("div", "tk-side-actions");
    sts.setAttribute("role", "group");
    sts.setAttribute("aria-label", "任务状态");
    ["none", "active", "completed", "failed"].forEach(function (k) {
      var on = statusOf(id) === k;
      var b = taskButton(STATUS[k].glyph + " " + STATUS[k].zh,
        "tk-btn-status" + (on ? " is-on" : ""));
      b.setAttribute("data-set-status", k);
      b.setAttribute("aria-pressed", on ? "true" : "false");
      sts.appendChild(b);
    });
    side.appendChild(sts);
  }

  // ---------------------------------------------------------------- 商人页
  /**
   * R19.24 试点：数据说明弹窗。
   * 内容全部取自当前模式真实数据（dataMeta / guides / season），不写死、不编造。
   */
  function openDataNote() {
    var UI = window.GWUI;
    if (!UI) { return; }
    var meta = state.dataMeta || {};
    var c = meta.counts || {};
    var cross = meta.cross || {};
    var g = { generated: 0, curated: 0, missing: 0 };
    state.order.forEach(function (id) {
      var st = (state.guides[id] || {}).status;
      if (st === "curated") { g.curated++; } else if (st === "generated") { g.generated++; } else { g.missing++; }
    });
    var rows = [
      { k: "当前模式", v: modeLabel() },
      { k: "任务数", v: String(c.tasks || state.order.length) },
      { k: "任务目标数", v: String(c.objectives || 0) },
      { k: "前置关系（边）", v: String(c.edges || 0) },
      { k: "赛季专属任务", v: String(c.seasonOnly || 0) },
      { k: "Kappa 必需", v: String(c.kappa || 0) },
      { k: "阵营限定", v: String(c.faction || 0) }
    ];
    if (cross.subsetOf && cross.subsetOf.length) {
      rows.push({ k: "任务集关系", v: "本模式任务集是 " + cross.subsetOf.map(modeLabel).join("、") + " 的子集" });
    }
    var body = UI.el("div", { cls: "ui-prose" });
    body.appendChild(UI.el("p", {
      text: "下表是当前模式的数据事实（来自本地数据文件，不是估算）。切换右上角模式后数值会随之变化。"
    }));
    body.appendChild(UI.table({
      columns: [{ key: "k", label: "项目", width: "150px" }, { key: "v", label: "值", wrap: true }],
      colTemplate: "150px minmax(160px, 1fr)",
      rows: rows
    }));
    if (state.mode === "pvps") {
      var season = state.season || {};
      var note = "赛季服：";
      if (season.nameZh) { note += "当前赛季「" + season.nameZh + "」。"; }
      else if (season.nameEn) { note += "上游只提供英文赛季名「" + season.nameEn + "」，无中文译名，按原样显示。"; }
      if (season.startISO) { note += "周期 " + season.startISO + " → " + season.endISO + "。"; }
      body.appendChild(UI.el("p", { text: note }));
    }
    UI.dialog({
      title: "数据说明 · " + modeLabel(),
      wide: true,
      body: body,
      buttons: [{ label: "关闭", variant: "primary" }]
    });
  }

  // ---------------------------------------------------------------- 任务列表（R20.17，照 db4tarkov Quest 页）
  // 条目数据仍来自本地 tarkov.dev 任务包；封面图来自 db4tarkov 公开 CDN（构建期下载）。
  var LIST_STATUS_OPTS = [
    ["all", "全部状态"], ["unfinished", "未完成"], ["active", "进行中"], ["completed", "已完成"],
    ["failed", "已失败"], ["available", "可接取"], ["season", "赛季专属"],
    ["kappa", "Kappa 必需"], ["lightkeeper", "灯塔相关"]
  ];
  var LIST_SORT_OPTS = [
    ["default", "默认（商人 + 等级）"], ["exp", "经验（高 → 低）"], ["map", "按地图"],
    ["progress", "按进度"], ["obj", "按目标完成度"], ["name", "按名称"]
  ];

  // R41：db4 任务页的排序 / 状态区（英文标签与参考站一致）
  var DB4_SORT = [
    ["default", "Default"], ["exp", "By Exp"], ["map", "By Map"],
    ["progress", "By Progress"], ["obj", "By Objectives"], ["name", "By Name"]
  ];
  var DB4_STATUS = [
    ["all", "All"], ["unfinished", "Uncompleted"], ["active", "Active"],
    ["completed", "Completed"], ["failed", "Failed"], ["available", "Available"]
  ];

  function ensureTaskImages() {
    if (state.taskImagesReady) { return; }
    state.taskImagesReady = true;
    fetchJSON("data/task-images.json").then(function (doc) {
      state.taskImages = (doc && doc.images) || {};
      if (state.view === "list") { renderListRows(); }
    }).catch(function () { /* 封面缺失不影响列表 */ });
  }

  /** R41：db4 风格任务板 —— 顶部商人头像条 + 左列表（按商人分组）+ 右筛选栏。 */
  function ensureListUI() {
    if (!state.el.list) { return; }
    if (state.el.list.getAttribute("data-mode") === state.mode && state.el.listRows) { return; }
    var host = state.el.list;
    host.innerHTML = "";
    host.setAttribute("data-mode", state.mode);
    host.classList.add("db4");
    // R216：db4 只留在任务板容器上；整壳的 db4 由 setView() 按子页统一开关，
    // 不再在这里「加一次就再也不摘」。
    var board = h("div", "db4-board");

    // 顶部搜索栏（对齐 db4 的 "Type to search - ESC to clear"）
    var bar = h("div", "db4-bar");
    var search = h("input", "db4-search");
    search.id = "tk-list-search";
    search.type = "search";
    search.placeholder = "Type to search — ESC 清空";
    search.value = state.list.search || "";
    search.addEventListener("input", function () {
      state.list.search = search.value;
      renderListRows();
    });
    search.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape") {
        search.value = "";
        state.list.search = "";
        renderListRows();
      }
    });
    bar.appendChild(search);
    var count = h("span", "db4-count");
    count.id = "tk-list-count";
    bar.appendChild(count);
    board.appendChild(bar);

    var strip = h("div", "db4-strip");
    strip.id = "db4-strip";
    board.appendChild(strip);

    var main = h("div", "db4-main");
    var scroll = h("div", "db4-scroll");
    var rows = h("div", "db4-groups");
    rows.id = "tk-list-rows";
    scroll.appendChild(rows);
    main.appendChild(scroll);

    var rail = h("aside", "db4-rail");
    rail.id = "db4-rail";
    main.appendChild(rail);

    board.appendChild(main);
    host.appendChild(board);
    state.el.listRows = rows;
    state.el.listCount = count;
    state.el.listStrip = strip;
    state.el.listRail = rail;
  }

  function db4StatusCounts() {
    var c = { all: state.order.length, active: 0, completed: 0, failed: 0, available: 0 };
    state.order.forEach(function (id) {
      var st = statusOf(id);
      if (c[st] != null) { c[st] += 1; }
      if (st !== "completed" && st !== "failed") {
        var rec = state.tasks[id];
        if (prereqMet(rec) && levelMet(rec)) { c.available += 1; }
      }
    });
    c.unfinished = c.all - c.completed - c.failed;
    return c;
  }

  function db4Face(tid) {
    var tr = state.traders[tid] || {};
    var img = h("img", "db4-face-img");
    img.src = tr.portrait || tr.localIcon || "assets/icons-traders/unknown.svg";
    img.alt = tr.nameEn || "";
    img.onerror = function () {
      this.onerror = null;
      this.src = tr.localIcon || "assets/icons-traders/unknown.svg";
    };
    return img;
  }

  function renderDb4Strip() {
    var strip = state.el.listStrip;
    if (!strip) { return; }
    strip.innerHTML = "";
    var sel = state.list.trader || "";
    Object.keys(state.traders).forEach(function (tid) {
      var tr = state.traders[tid] || {};
      var b = h("button", "db4-face" + (sel === tid ? " is-on" : (sel ? " is-off" : "")));
      b.type = "button";
      b.dataset.db4Trader = tid;
      b.title = (tr.nameEn || "未收录商人") + " · 点击只看该商人任务";
      b.appendChild(db4Face(tid));
      strip.appendChild(b);
    });
  }

  function renderDb4Rail() {
    var rail = state.el.listRail;
    if (!rail) { return; }
    rail.innerHTML = "";

    function grp(title, cls) {
      var g = h("div", "db4-rail-grp " + (cls || ""));
      g.appendChild(h("div", "db4-rail-title", title));
      rail.appendChild(g);
      return g;
    }

    // R41 第 4 轮：参考站右栏是「整宽居中按钮 + 选中反白」，没有下拉框、也不带计数；
    // 计数改成 title 提示，保留信息量但不破坏参考站的行高与居中排版。
    var counts = db4StatusCounts();
    var stG = grp("Status", "db4-rail-status");
    DB4_STATUS.forEach(function (o) {
      var b = h("button", "db4-rail-btn" + (state.list.status === o[0] ? " is-on" : ""), o[1]);
      b.type = "button";
      b.dataset.db4Status = o[0];
      var n = counts[o[0] || "all"];
      if (n != null) { b.title = o[1] + " · " + n; }
      stG.appendChild(b);
    });

    var spG = grp("Special", "db4-rail-special");
    // 商人英文名只能来自数据（R19.25 的约束）：Lightkeeper 段从 traders 里取，取不到就退回中文。
    var lkName = (state.traders["638f541a29ffd1183d187f57"] || {}).nameEn || "灯塔";
    [["kappa", "Kappa 必需"], ["lightkeeper", "Only-" + lkName], ["season", "赛季专属"]].forEach(function (o) {
      var n = state.order.filter(function (id) {
        var r = state.tasks[id];
        return o[0] === "kappa" ? r.kappaRequired :
          (o[0] === "lightkeeper" ? r.lightkeeperRequired : r.seasonOnly);
      }).length;
      var b = h("button", "db4-rail-btn" + (state.list.status === o[0] ? " is-on" : ""), o[1]);
      b.type = "button";
      b.dataset.db4Status = o[0];
      b.title = o[1] + " · " + n;
      spG.appendChild(b);
    });

    var sortG = grp("Sort", "db4-rail-sort");
    DB4_SORT.forEach(function (o) {
      var b = h("button", "db4-rail-btn" + (state.list.sort === o[0] ? " is-on" : ""), o[1]);
      b.type = "button";
      b.dataset.db4Sort = o[0];
      sortG.appendChild(b);
    });

    var dispG = grp("Display", "db4-rail-display");
    var lab = h("label", "db4-switch");
    var cb = h("input");
    cb.type = "checkbox";
    cb.id = "tk-list-allobj";
    cb.checked = !!state.list.allObj;
    lab.appendChild(cb);
    lab.appendChild(h("span", null, "Show all objectives"));
    dispG.appendChild(lab);

    var reset = h("button", "db4-reset", "Reset filters");
    reset.type = "button";
    reset.dataset.db4Reset = "1";
    rail.appendChild(reset);
  }


  function listSelect(id, options, value) {
    var sel = h("select", "tl-select");
    sel.id = id;
    options.forEach(function (o) {
      var opt = h("option", null, o[1]);
      opt.value = o[0];
      sel.appendChild(opt);
    });
    sel.value = value;
    return sel;
  }

  function objDoneCount(id) {
    var rec = progOf(id);
    var objs = (state.tasks[id] && state.tasks[id].objectives) || [];
    var done = 0, total = 0;
    objs.forEach(function (o) {
      if (o.optional) { return; }
      total += 1;
      if (rec && rec.objectives && rec.objectives[o.id]) { done += 1; }
    });
    return { done: done, total: total };
  }

  /** 前置任务是否满足（statuses 里的 complete 对应本地 completed） */
  function prereqMet(rec) {
    return (rec.prerequisites || []).every(function (p) {
      var st = statusOf(p.taskId);
      var want = p.statuses || ["complete"];
      var mapped = st === "completed" ? "complete" : st;
      return want.indexOf(mapped) !== -1 || want.indexOf(st) !== -1;
    });
  }

  function levelMet(rec) {
    if (!state.ui.playerLevel) { return true; }
    return (rec.minLevel || 0) <= state.ui.playerLevel;
  }

  function listPass(id) {
    var rec = state.tasks[id] || {};
    var f = state.list;
    if (f.map) {
      var maps = rec.maps && rec.maps.length ? rec.maps : (rec.map ? [rec.map] : []);
      if (maps.indexOf(f.map) === -1) { return false; }
    }
    if (f.trader && rec.traderId !== f.trader && rec.traderZh !== f.trader) { return false; }
    var st = statusOf(id);
    switch (f.status) {
      case "unfinished": if (st === "completed" || st === "failed") { return false; } break;
      case "active": if (st !== "active") { return false; } break;
      case "completed": if (st !== "completed") { return false; } break;
      case "failed": if (st !== "failed") { return false; } break;
      case "available": if (st === "completed" || st === "failed" || !prereqMet(rec) || !levelMet(rec)) { return false; } break;
      case "season": if (!rec.seasonOnly) { return false; } break;
      case "kappa": if (!rec.kappaRequired) { return false; } break;
      case "lightkeeper": if (!rec.lightkeeperRequired) { return false; } break;
      default: break;
    }
    if (f.search) {
      var q = f.search.toLowerCase();
      var text = ((rec.nameZh || "") + " " + (rec.nameEn || "") + " " +
        taskEnglishName(rec, id) + " " + id + " " +
        (rec.traderZh || "") + " " + (state.traders[rec.traderId] || {}).nameEn +
        " " + (rec.objectives || []).map(function (o) {
          return (o.descZh || "") + " " + (o.descEn || "");
        }).join(" ")).toLowerCase();
      if (text.indexOf(q) === -1) { return false; }
    }
    return true;
  }

  function listSorted() {
    var ids = state.order.filter(listPass);
    var f = state.list;
    if (f.sort === "exp") {
      ids.sort(function (a, b) { return (state.tasks[b].experience || 0) - (state.tasks[a].experience || 0); });
    } else if (f.sort === "map") {
      ids.sort(function (a, b) {
        var ma = state.tasks[a].map || "", mb = state.tasks[b].map || "";
        return ma.localeCompare(mb, "zh-Hans-CN") || (state.tasks[a].minLevel || 0) - (state.tasks[b].minLevel || 0);
      });
    } else if (f.sort === "progress" || f.sort === "obj") {
      ids.sort(function (a, b) {
        var pa = objDoneCount(a), pb = objDoneCount(b);
        var ra = pa.total ? pa.done / pa.total : 0, rb = pb.total ? pb.done / pb.total : 0;
        if (rb !== ra) { return rb - ra; }
        return (state.tasks[a].minLevel || 0) - (state.tasks[b].minLevel || 0);
      });
    } else if (f.sort === "name") {
      ids.sort(function (a, b) { return (state.tasks[a].nameZh || "").localeCompare(state.tasks[b].nameZh || "", "zh-Hans-CN"); });
    }
    return ids;
  }

  function renderList() {
    ensureListUI();
    renderListRows();
  }

  function renderListRows() {
    ensureListUI();
    var host = state.el.listRows;
    if (!host) { return; }
    renderDb4Strip();
    renderDb4Rail();
    var ids = listSorted();
    host.innerHTML = "";
    if (state.el.listCount) {
      state.el.listCount.textContent = ids.length + " / " + state.order.length;
    }
    if (!ids.length) {
      host.appendChild(h("div", "db4-empty", "没有符合筛选条件的任务"));
      return;
    }
    // 按商人分组（db4 是「左侧商人图标 + 右侧任务行」的连续列）
    var groups = {}, order = [];
    ids.forEach(function (id) {
      var tid = (state.tasks[id] || {}).traderId || "";
      if (!groups[tid]) { groups[tid] = []; order.push(tid); }
      groups[tid].push(id);
    });
    order.forEach(function (tid) {
      var tr = state.traders[tid] || {};
      var sec = h("section", "db4-group");
      sec.setAttribute("data-trader", tid);
      var gut = h("div", "db4-gutter");
      if (tr.portrait || tr.localIcon) {
        gut.appendChild(db4Face(tid));
      }
      var gname = h("span", "db4-gname", tr.nameEn || "未收录商人");
      gname.title = tr.nameEn || "";
      gut.appendChild(gname);
      sec.appendChild(gut);
      var rows = h("div", "db4-rows");
      groups[tid].forEach(function (id) { rows.appendChild(listRow(id)); });
      sec.appendChild(rows);
      host.appendChild(sec);
    });
  }

  /** 上游缺英文名时会填成「<id> name」；列表里只显示真正的英文名 */
  function taskEnglishName(rec, id) {
    var bad = id + " name";
    if (rec.englishName && rec.englishName !== bad) { return rec.englishName; }
    var en = rec.nameEn || "";
    if (en && en !== bad && en !== rec.nameZh) { return en; }
    return "";
  }

  function listRow(id) {
    var rec = state.tasks[id] || {};
    var st = statusOf(id);
    var row = h("article", "db4-row is-" + st);
    row.id = "tl-row-" + id;

    // 左侧状态勾选（db4 的方框）：点一下切换完成 / 重置
    var tick = h("button", "db4-tick");
    tick.type = "button";
    tick.dataset.listTask = id;
    tick.dataset.listStatus = st === "completed" ? "none" : "completed";
    tick.title = st === "completed" ? "已完成 · 点击重置" : "标记为已完成";
    tick.appendChild(h("span", "db4-tick-mark",
      st === "completed" ? "✓" : (st === "failed" ? "✕" : (st === "active" ? "◐" : ""))));
    row.appendChild(tick);

    var body = h("div", "db4-body");
    var head = h("div", "db4-trow");
    var name = h("button", "db4-name", rec.nameZh || rec.nameEn || id);
    name.type = "button";
    name.dataset.listOpenTask = id;
    name.title = "打开任务详情并在地图上定位";
    head.appendChild(name);
    var en = taskEnglishName(rec, id);
    if (en && en !== rec.nameZh) { head.appendChild(h("span", "db4-en", en)); }
    if (rec.minLevel) { head.appendChild(h("span", "db4-lv", "Lv " + rec.minLevel)); }
    if (rec.map) { head.appendChild(h("span", "db4-map", rec.map)); }
    body.appendChild(head);
    // 右侧经验徽标 + Complete 按钮（db4 的 exp / Complete 列）
    var exp = h("div", "db4-exp");
    exp.appendChild(h("span", "db4-exp-chip", "exp"));
    exp.appendChild(h("span", "db4-exp-val", "+" + (rec.experience || 0)));
    row.appendChild(exp);

    var comp = h("button", "db4-complete" + (st === "completed" ? " is-done" : ""));
    comp.type = "button";
    comp.dataset.listTask = id;
    comp.dataset.listStatus = st === "completed" ? "none" : "completed";
    comp.textContent = st === "completed" ? "Completed" : "Complete";
    comp.title = st === "completed" ? "已完成 · 点击重置" : "标记为已完成";
    row.appendChild(comp);

    var objs = (rec.objectives || []).slice();
    if (!state.list.allObj && objs.length > 1) { objs = [objs[0]]; }
    var olist = h("div", "db4-objs");
    var recProg = progOf(id);
    objs.forEach(function (o) {
      var lab = h("label", "db4-obj");
      var cb = h("input", "db4-cb");
      cb.type = "checkbox";
      cb.dataset.listObj = id + "|" + o.id;
      cb.checked = !!(recProg && recProg.objectives && recProg.objectives[o.id]);
      lab.appendChild(cb);
      if (o.items && o.items.length && o.items[0].id) {
        var ico = h("img", "db4-obj-icon");
        ico.src = "assets/icons-items/" + o.items[0].id + ".webp";
        ico.loading = "lazy";
        ico.alt = "";
        ico.onerror = function () { this.style.display = "none"; };
        lab.appendChild(ico);
      } else {
        lab.appendChild(h("span", "db4-pin"));
      }
      var desc = h("span", "db4-obj-desc", o.descZh || o.descEn || o.id);
      if (o.optional) { desc.classList.add("is-optional"); }
      lab.appendChild(desc);
      if (o.count) { lab.appendChild(h("span", "db4-obj-count", "×" + o.count)); }
      var maps = mapText((o.maps || []).filter(Boolean).slice(0, 2), " / ");
      if (maps) { lab.appendChild(h("span", "db4-obj-map", maps)); }
      if (o.zones && o.zones.length) {
        var lb = h("button", "db4-loc", "◎");
        lb.type = "button";
        lb.dataset.db4Loc = id + "|" + o.id;
        lb.title = "在地图上定位该目标点";
        lab.appendChild(lb);
      }
      olist.appendChild(lab);
    });
    if (!state.list.allObj && (rec.objectives || []).length > 1) {
      var more = h("button", "db4-obj-more",
        "+" + ((rec.objectives || []).length - 1) + " more objectives");
      more.type = "button";
      more.addEventListener("click", function () {
        state.list.allObj = true;
        renderListRows();
      });
      olist.appendChild(more);
    }
    body.appendChild(olist);
    row.insertBefore(body, exp);

    // 右侧交付物品图标列（只取当前展示的目标，最多 4 枚，其余折叠成 +N）
    var items = h("div", "db4-items");
    var seen = {}, ids = [];
    objs.forEach(function (o) {
      (o.items || []).forEach(function (it) {
        if (!it || !it.id || seen[it.id]) { return; }
        seen[it.id] = 1;
        ids.push(it);
      });
    });
    ids.slice(0, 4).forEach(function (it) {
      var cell = h("span", "db4-item-cell");
      var im = h("img", "db4-item");
      im.src = "assets/icons-items/" + it.id + ".webp";
      im.loading = "lazy";
      im.alt = it.nameZh || "";
      im.title = (it.nameZh || it.id) + " ×" + (it.count || 1);
      im.onerror = function () { this.style.display = "none"; };
      cell.appendChild(im);
      if ((it.count || 1) > 1) {
        cell.appendChild(h("span", "db4-item-n", "×" + it.count));
      }
      items.appendChild(cell);
    });
    if (ids.length > 4) {
      items.appendChild(h("span", "db4-item-more", "+" + (ids.length - 4)));
    }
    row.insertBefore(items, exp);
    return row;
  }

  function renderTraders() {
    var host = state.el.traders;
    if (!host) { return; }
    host.innerHTML = "";
    var wrap = h("div", "tk-traders-wrap");
    var left = h("div", "tk-trader-list");
    var right = h("div", "tk-trader-tasks");

    var byTrader = {};
    state.order.forEach(function (id) {
      var rec = state.tasks[id];
      (byTrader[rec.traderId] = byTrader[rec.traderId] || []).push(id);
    });
    var selectedTrader = state.filters.trader || "";
    Object.keys(byTrader).forEach(function (tid) {
      var list = byTrader[tid];
      var tr = state.traders[tid] || { nameEn: list.length ? (state.tasks[list[0]].traderEn || "") : "" };
      var done = list.filter(function (id) { return statusOf(id) === "completed"; }).length;
      var active = list.filter(function (id) { return statusOf(id) === "active"; }).length;
      var open = list.filter(function (id) { return availability(state.tasks[id]).state === "open"; }).length;
      var card = h("button", "tk-trader-card" + (selectedTrader === tid ? " is-on" : ""));
      card.type = "button";
      card.dataset.trader = tid;
      var img = h("img", "tk-trader-icon");
      img.src = tr.localIcon || ("assets/icons-traders/" + (tr.normalizedName || "unknown") + ".svg");
      img.alt = "";
      card.appendChild(img);
      var info = h("div", "tk-trader-info");
      var nm = h("span", "tk-trader-name", tr.nameEn || "未收录商人");
      nm.setAttribute("data-i18n-skip", "1");          // 英文原名，不参与中文化替换
      // R19.25 §5：商人主显示名与 Tooltip 都不再用未经核实的中文机翻
      nm.removeAttribute("title");
      info.appendChild(nm);
      info.appendChild(h("span", "tk-trader-counts",
        list.length + " 个任务 · 完成 " + done + " · 进行中 " + active + " · 可接 " + open));
      var bar = h("span", "tk-bar");
      var fill = h("span", "tk-bar-fill");
      fill.style.width = Math.round((done / Math.max(list.length, 1)) * 100) + "%";
      bar.appendChild(fill);
      info.appendChild(bar);
      card.appendChild(info);
      card.addEventListener("click", function () {
        state.filters.trader = state.filters.trader === tid ? "" : tid;
        var sel = document.getElementById("tk-trader");
        if (sel) { sel.value = state.filters.trader; }
        saveUi();
        renderTraders();
        refreshVisual();
      });
      left.appendChild(card);
    });

    var list = state.order.filter(function (id) {
      if (selectedTrader && state.tasks[id].traderId !== selectedTrader) { return false; }
      return passes(state.tasks[id]);
    });
    list.sort(sortFn());
    var UI = window.GWUI;
    var head = h("div", "tk-list-head");
    head.appendChild(h("h3", null, modeLabel() + " · " +
      (selectedTrader ? ((state.traders[selectedTrader] || {}).nameEn || "未收录商人") : "全部商人") +
      " · " + list.length + " 个任务"));
    if (!UI) {
      head.appendChild(h("span", "tk-list-note", "UI 组件库未加载（js/ui-components.js），已回退为纯文字列表。"));
      right.appendChild(head);
      var plain = h("ul", "tk-bullets");
      list.slice(0, 200).forEach(function (id) {
        var li = h("li");
        li.textContent = state.tasks[id].nameZh;
        plain.appendChild(li);
      });
      right.appendChild(plain);
      return;
    }

    // R19.24 试点：本页的「工具栏 / 表格 / 状态徽标 / 弹窗 / 提示」全部改用设计系统组件
    var sortSelect = UI.select({
      ariaLabel: "排序方式",
      value: state.ui.sort,
      options: [["level", "按等级"], ["name", "按名称"], ["progress", "按进度"], ["prereq", "按前置数"]]
        .map(function (o) { return { value: o[0], label: o[1] }; }),
      onChange: function (v) {
        state.ui.sort = v;
        saveUi();
        renderTraders();
      }
    });
    sortSelect.id = "tk-sort";
    sortSelect.className += " tk-sort";
    var infoBtn = UI.btn({
      label: "数据说明",
      size: "sm",
      icon: UI.icons.info,
      onClick: function () { openDataNote(); }
    });
    head.appendChild(UI.toolbar({
      flat: true,
      className: "tk-list-tools",
      groups: [
        [UI.el("span", { cls: "tk-sel-label", text: "排序" }), sortSelect],
        "grow",
        [infoBtn]
      ]
    }));
    right.appendChild(head);

    var STATUS_KIND = { completed: "ok", active: "info", failed: "danger", none: "" };
    var rows = list.map(function (id) { return id; });
    var table = UI.table({
      className: "tk-table",
      role: "table",
      headClass: "tk-tr tk-th",
      colTemplate: "minmax(140px, 2fr) 84px 44px 96px 66px 44px 44px 44px 56px",
      columns: [
        { key: "name", label: "任务", cellClass: "tk-td tk-td-name" },
        { key: "status", label: "状态", width: "84px", cellClass: "tk-td tk-td-status" },
        { key: "level", label: "等级", width: "44px", align: "right", cellClass: "tk-td tk-td-num" },
        { key: "map", label: "地图", width: "96px", cellClass: "tk-td" },
        { key: "mode", label: "模式", width: "66px", cellClass: "tk-td tk-td-mode" },
        { key: "pre", label: "前置", width: "44px", align: "right", cellClass: "tk-td tk-td-num" },
        { key: "obj", label: "目标", width: "44px", align: "right", cellClass: "tk-td tk-td-num" },
        { key: "post", label: "后续", width: "44px", align: "right", cellClass: "tk-td tk-td-num" },
        { key: "act", label: "", width: "56px", cellClass: "tk-td tk-td-act" }
      ],
      rows: rows,
      rowClass: function () { return "tk-tr"; },
      rowAttrs: function (id) { return { "data-task-id": id }; },
      renderCell: function (id, col, ci) {
        var rec = state.tasks[id];
        var st = STATUS[statusOf(id)];
        if (ci === 0) { return rec.nameZh; }
        if (ci === 1) { return UI.badge(st.zh, STATUS_KIND[statusOf(id)], st.glyph + " " + st.zh); }
        if (ci === 2) { return String(rec.minLevel || 0); }
        if (ci === 3) { return mapText((rec.maps || []).slice(0, 2)) || "—"; }
        if (ci === 4) {
          if (rec.seasonOnly) { return "赛季"; }
          if (rec.onlyInModes && rec.onlyInModes.length) {
            return "仅" + rec.onlyInModes.map(function (m) {
              return (MODE_BY_KEY[m] || {}).label || m;
            }).join("/");
          }
          return "全模式";
        }
        if (ci === 5) { return (rec.prerequisites || []).length ? String(rec.prerequisites.length) : "—"; }
        if (ci === 6) { return String((rec.objectives || []).length); }
        if (ci === 7) { return String((rec.followUps || []).length); }
        var b = UI.btn({ label: "详情", size: "sm" });
        b.dataset.openTask = id;
        b.className += " tk-btn-mini";
        return b;
      }
    });

    // 名称列：中文名 + 英文原名浮窗（沿用 R19.22 的 data-en-text 约定），目标摘要进自定义提示
    var nameCells = table.querySelectorAll(".tk-td-name");
    var modeCells = table.querySelectorAll(".tk-td-mode");
    list.forEach(function (id, i) {
      var rec = state.tasks[id];
      var cell = nameCells[i];
      if (cell) {
        decorateName(cell, rec, 22);
        var firstObj = (rec.objectives || [])[0];
        if (firstObj) {
          cell.removeAttribute("title");
          UI.tooltip.attach(cell, (rec.nameZh + "\n（" + (enTitle(rec) || "") + "）\n目标：" +
            firstObj.descZh + ((rec.objectives || []).length > 1
              ? " 等 " + rec.objectives.length + " 项" : "")), { delay: 260 });
        }
      }
      var mcell = modeCells[i];
      if (mcell) {
        mcell.removeAttribute("title");
        UI.tooltip.attach(mcell, modeScopeText(rec), { delay: 200 });
        if (rec.seasonOnly) { mcell.classList.add("is-season"); }
      }
    });
    right.appendChild(table);

    // 任务链：同一商人内的线性链（真实依赖，不按名称编号猜）
    var chains = buildChains(list);
    var chainBox = h("div", "tk-chains");
    chainBox.appendChild(h("h4", null, "任务链（按真实前置关系，跨商人前置以 ↗ 标出）"));
    if (!chains.length) {
      chainBox.appendChild(h("p", "tk-empty", "这些任务之间没有直接前后关系。"));
    }
    chains.forEach(function (chain) {
      var line = h("div", "tk-chain");
      chain.forEach(function (id, i) {
        if (i) { line.appendChild(h("span", "tk-chain-arrow", "→")); }
        var rec = state.tasks[id];
        var chip = h("button", "tk-chain-node " + STATUS[statusOf(id)].cls);
        chip.type = "button";
        chip.textContent = rec.nameZh;
        chip.title = enTitle(rec);
        chip.dataset.openTask = id;
        var cross = (rec.prerequisites || []).filter(function (p) {
          var t = task(p.taskId);
          return t && selectedTrader && t.traderId !== selectedTrader;
        });
        if (cross.length) {
          var badge = h("span", "tk-chain-cross", "↗");
          badge.title = "前置来自其他商人：" + cross.map(function (p) {
            return (task(p.taskId) || {}).nameZh;
          }).join("、");
          chip.appendChild(badge);
        }
        line.appendChild(chip);
      });
      chainBox.appendChild(line);
    });
    right.appendChild(chainBox);

    wrap.appendChild(left);
    wrap.appendChild(right);
    host.appendChild(wrap);
    if (window.GWI18n) { window.GWI18n.localize(host, true); }
  }

  function sortFn() {
    var s = state.ui.sort;
    return function (a, b) {
      var ra = state.tasks[a], rb = state.tasks[b];
      if (s === "name") { return String(ra.nameZh).localeCompare(String(rb.nameZh), "zh-Hans-CN"); }
      if (s === "progress") {
        var order = { completed: 0, active: 1, none: 2, failed: 3 };
        return order[statusOf(a)] - order[statusOf(b)];
      }
      if (s === "prereq") { return (rb.prerequisites || []).length - (ra.prerequisites || []).length; }
      if (ra.minLevel !== rb.minLevel) { return ra.minLevel - rb.minLevel; }
      return String(ra.nameZh).localeCompare(String(rb.nameZh), "zh-Hans-CN");
    };
  }

  /** 线性链提取：只把「一对一」的前后关系连成链，遇到分叉就断开（不伪造关系）。 */
  function buildChains(list) {
    var set = {};
    list.forEach(function (id) { set[id] = 1; });
    var chains = [];
    var used = {};
    list.forEach(function (id) {
      var rec = state.tasks[id];
      var pres = (rec.prerequisites || []).filter(function (p) { return set[p.taskId]; });
      if (pres.length) { return; }        // 只从链头开始
      var chain = [id];
      var cur = id;
      used[id] = 1;
      for (var guard = 0; guard < 40; guard++) {
        var fu = (state.tasks[cur].followUps || []).filter(function (f) { return set[f]; });
        if (fu.length !== 1) { break; }
        var next = fu[0];
        if (used[next]) { break; }
        var back = (state.tasks[next].prerequisites || []).filter(function (p) { return set[p.taskId]; });
        if (back.length !== 1) { break; }   // 还有其它前置 → 不是单链
        chain.push(next);
        used[next] = 1;
        cur = next;
      }
      if (chain.length > 1) { chains.push(chain); }
    });
    chains.sort(function (a, b) { return b.length - a.length; });
    return chains.slice(0, 24);
  }

  // ---------------------------------------------------------------- 详情页
  /** 详情容器滚到顶部（R77：从地图深链跳进来总是从任务标题开始看）。 */
  function scrollDetailTop() {
    if (!state.el || !state.el.detail) { return; }
    state.el.detail.scrollTop = 0;
    requestAnimationFrame(function () {
      if (state.el && state.el.detail) { state.el.detail.scrollTop = 0; }
    });
  }

  /** 当前模式下找不到任务：在详情区给可读提示 + 状态栏说明原因。 */
  function showMissingTask(id) {
    state.missingTask = id;
    state.selected = null;
    state.view = "detail";
    saveUi();
    setView("detail");
    renderSide();
    setStatusText("未找到任务 " + id + "（" + modeLabel() + " 中不存在；可能属于其它模式，切换后再试）");
  }

  function openTask(id) {
    if (!id) { return; }
    state.missingTask = null;
    // R77：从地图页跳过来时任务数据可能还在加载 / 尚未加载 → 先记下，数据就绪后再落点。
    if (!state.cache[state.mode]) {
      state.pendingTaskOpen = id;
      if (!state.loading) { open(); }
      return;
    }
    if (!state.tasks[id]) {
      showMissingTask(id);
      return;
    }
    state.pendingTaskOpen = null;
    state.selected = id;
    state.view = "detail";
    saveUi();
    setView("detail");
    renderSide();
    scrollDetailTop();
  }

  function renderDetail() {
    var host = state.el.detail;
    if (!host) { return; }
    host.innerHTML = "";
    // R77：深链指向的任务在当前模式里不存在 → 说清楚原因与下一步，而不是静默回列表。
    // （用户之后主动选了别的任务时 selected 不为空，这条提示自动让位。）
    if (state.missingTask && !state.selected) {
      host.appendChild(h("p", "tk-empty",
        "未找到任务 " + state.missingTask + "（当前模式 " + modeLabel() + " 下不存在）。" +
        "可能属于另一个模式：请用右上角切换模式后重试，或检查链接里的任务 ID。"));
      return;
    }
    var id = state.selected;
    if (!id || !task(id)) {
      host.appendChild(h("p", "tk-empty", "请先在任务树或商人列表中选一个任务。"));
      return;
    }
    var rec = task(id);
    var guide = state.guides[id] || {};
    var tr = traderOf(rec);
    var av = availability(rec);

    var article = h("article", "tk-detail-body");

    // 1) 基本信息
    var head = h("header", "tk-detail-head");
    var titleWrap = h("div", "tk-detail-titlewrap");
    titleWrap.appendChild(decorateName(h("h2", "tk-detail-title"), rec));
    var sub = h("p", "tk-detail-sub");
    // R72：状态改由右侧分段按钮表达，副标题只留身份信息，避免同一状态说两遍。
    // R73：商人名已在字段区出现，副标题不再重复（正文里同一商人只说一次）。
    sub.textContent = (rec.taskType === "story" ? "主线任务" : "常规任务") +
      " · 等级 " + (rec.minLevel || 0);
    titleWrap.appendChild(sub);
    head.appendChild(titleWrap);
    var statusBtns = h("div", "tk-detail-status");
    statusBtns.setAttribute("role", "radiogroup");
    statusBtns.setAttribute("aria-label", "任务状态");
    ["none", "active", "completed", "failed"].forEach(function (k) {
      var on = statusOf(id) === k;
      var b = taskButton(STATUS[k].glyph + " " + STATUS[k].zh,
        "tk-btn-status" + (on ? " is-on" : ""));
      b.setAttribute("data-set-status", k);
      b.setAttribute("role", "radio");
      b.setAttribute("aria-checked", on ? "true" : "false");
      // R73：radiogroup 键盘可达性 —— 只有当前项进 Tab 序列，方向键在四项间移动并即时切换。
      b.tabIndex = on ? 0 : -1;
      b.addEventListener("keydown", function (ev) {
        var step = ev.key === "ArrowRight" || ev.key === "ArrowDown" ? 1
          : ev.key === "ArrowLeft" || ev.key === "ArrowUp" ? -1 : 0;
        if (!step) { return; }
        ev.preventDefault();
        var order = ["none", "active", "completed", "failed"];
        var next = order[(order.indexOf(k) + step + order.length) % order.length];
        requestStatusChange(id, next);
        requestAnimationFrame(function () {
          var nb = document.querySelector('#tk-detail [data-set-status="' + next + '"]');
          if (nb) { nb.focus(); }
        });
      });
      statusBtns.appendChild(b);
    });
    var statusWrap = h("div", "tk-detail-statuswrap");
    statusWrap.appendChild(h("span", "tk-detail-status-label", "任务状态"));
    statusWrap.appendChild(statusBtns);
    head.appendChild(statusWrap);
    article.appendChild(head);
    var facts = h("dl", "tk-facts");
    [["任务 ID", rec.id, "id"],
     ["原始英文名", rec.englishName || rec.nameEn || "—", "nameEn"],
     ["当前模式", modeLabel()],
     ["模式归属", modeScopeShort(rec), "scopeShort", modeScopeText(rec)],
     ["所属商人", traderEn(rec), "traderEn"],
     ["地图", mapText(rec.maps) || "—", "map"],
     ["阵营要求", rec.faction && rec.faction !== "Any" ? rec.faction : "无"],
     ["Kappa 必需", rec.kappaRequired ? "是" : "否"],
     ["灯塔相关", rec.lightkeeperRequired ? "是" : "否"],
     ["可重接", rec.restartable ? "是" : "否"],
     ["经验奖励", rec.experience ? rec.experience + " 点" : "—", "num"],
     ["失败分支", (rec.failedConditions || []).length
       ? (rec.failedConditions || []).map(function (f) {
           var t = task(f.taskId);
           return (t ? t.nameZh : f.taskId) + "（" + (f.statuses || []).join("/") + "）";
         }).join("；")
       : "无"]
    ].forEach(function (kv) {
      var row = h("div", "tk-fact");
      row.appendChild(h("dt", null, kv[0]));
      var dd;
      if (kv[2] === "scopeShort") {
        // R73：点击展开行内短说明（绝对定位，不撑高整块），触屏/无 hover 也可读。
        dd = h("dd", "tk-fact-scope");
        var scopeLabel = String(kv[1]);
        var stBtn = h("button", "tk-scope-toggle", scopeLabel + " ▸");
        stBtn.type = "button";
        stBtn.setAttribute("aria-expanded", "false");
        stBtn.setAttribute("data-scope-label", scopeLabel);
        stBtn.setAttribute("aria-label", "展开模式归属说明：" + scopeLabel);
        var note = h("span", "tk-fact-note", String(kv[3] || ""));
        note.hidden = true;
        stBtn.addEventListener("click", function () {
          var open = note.hidden;
          if (open) { closeScopeNotes(); }
          note.hidden = !open;
          stBtn.setAttribute("aria-expanded", open ? "true" : "false");
          stBtn.textContent = scopeLabel + (open ? " ▾" : " ▸");
        });
        stBtn.addEventListener("keydown", function (ev) {
          if (ev.key === "Escape" && !note.hidden) {
            ev.preventDefault();
            ev.stopPropagation();
            closeScopeNotes();
          }
        });
        dd.appendChild(stBtn);
        dd.appendChild(note);
      } else if (kv[2] === "id") {
        dd = h("dd", "tk-fact-id");
        var code = h("code", "tk-id", String(kv[1]));
        dd.appendChild(code);
        var copy = h("button", "tk-copy-btn", "复制");
        copy.type = "button";
        copy.dataset.copyTaskId = String(kv[1]);
        copy.setAttribute("aria-label", "复制任务 ID");
        dd.appendChild(copy);
      } else {
        dd = h("dd", null, String(kv[1]));
        if (kv[1] === "—" || kv[1] === "无") { dd.classList.add("is-empty"); }
        // R73：地图正文只显示中文名，上游英文原名（Ground Zero / Dark 等）放进 title。
        if (kv[2] === "map" && (rec.maps || []).length) {
          dd.title = (rec.maps || []).join("、");
        }
      }
      if (kv[2] === "num") { dd.classList.add("is-num"); }
      // 「原始英文名」与「商人英文原名」都是有意的英文展示（R19.22 §7.2 / R19.25 §7），
      // 不是漏翻，因此标记 data-i18n-skip 让覆盖率统计不把它们算成缺口。
      if (kv[2] === "nameEn" || kv[2] === "traderEn") { dd.setAttribute("data-i18n-skip", "1"); }
      row.appendChild(dd);
      facts.appendChild(row);
    });

    // R73：概览卡 —— 只在确有数据时出现（前置 / 奖励 / 后续），点击跳到对应小节。
    // 没有数据就整张卡不渲染，不做「0 项」的假卡片占位。
    var sumCards = [];
    var preList = rec.prerequisites || [];
    var fuList = rec.followUps || [];
    var rwSum = rec.rewards || {};
    var rwItems = (rwSum.items || []).length;
    var rwStand = (rwSum.traderStanding || []).length;
    var rwUnlock = (rwSum.offerUnlock || []).length;
    if (preList.length) {
      var preDone = preList.filter(function (p) { return statusOf(p.taskId) === "completed"; }).length;
      sumCards.push({ sec: "tk-sec-pre", k: "前置任务", v: preList.length,
        x: "已完成 " + preDone + " / " + preList.length });
    }
    if (rec.experience || rwItems || rwStand || rwUnlock) {
      var rwTotal = (rec.experience ? 1 : 0) + rwItems + rwStand + rwUnlock;
      var rwBits = [];
      if (rec.experience) { rwBits.push("经验 " + rec.experience); }
      if (rwItems) { rwBits.push("物品 ×" + rwItems); }
      if (rwStand) { rwBits.push("声望 " + rwStand + " 条"); }
      if (rwUnlock) { rwBits.push("解锁 " + rwUnlock + " 项"); }
      sumCards.push({ sec: "tk-sec-reward", k: "任务奖励", v: rwTotal, x: rwBits.join(" · ") });
    }
    if (fuList.length) {
      var fuOpen = fuList.filter(function (fid) {
        var ft = task(fid);
        return !!(ft && availability(ft).state === "open");
      }).length;
      sumCards.push({ sec: "tk-sec-post", k: "后续任务", v: fuList.length,
        x: "当前可接 " + fuOpen + " / " + fuList.length });
    }
    if (sumCards.length) {
      var sum = h("div", "tk-summary");
      sumCards.forEach(function (c) {
        var card = h("button", "tk-sumcard");
        card.type = "button";
        card.setAttribute("data-jump-section", c.sec);
        card.appendChild(h("span", "tk-sumcard-k", c.k));
        card.appendChild(h("span", "tk-sumcard-v", String(c.v)));
        card.appendChild(h("span", "tk-sumcard-x", c.x));
        sum.appendChild(card);
      });
      // R73：宽屏时字段区占左、概览卡竖排贴右，避免只出现一张卡时右侧留下 2/3 空带。
      var top = h("div", "tk-detail-top");
      top.appendChild(facts);
      top.appendChild(sum);
      article.appendChild(top);
    } else {
      article.appendChild(facts);      // 没有任何概览数据时只渲染字段区，不留空槽
    }
    // R72：详情页不再渲染任何站外链接（原「参考条目：fandom」已迁到「关于」面板）。

    // 2) 前置任务
    var preTitle = sectionTitle("前置任务（" + (rec.prerequisites || []).length + "）");
    preTitle.id = "tk-sec-pre";
    article.appendChild(preTitle);
    if (!(rec.prerequisites || []).length) {
      article.appendChild(h("p", "tk-muted", "无任务前置（可能只有等级/声望等条件）。"));
    } else {
      var logicAll = (rec.prerequisites || []).every(function (p) { return p.logic !== "or"; });
      article.appendChild(h("p", "tk-muted", logicAll ? "需全部满足：" : "含「满足其一」的多状态条件（标记 OR）："));
      var pre = h("ul", "tk-req-list");
      (rec.prerequisites || []).forEach(function (p) {
        var t = task(p.taskId);
        var li = h("li", "tk-req");
        var st = STATUS[statusOf(p.taskId)];
        li.appendChild(h("span", "tk-req-dot " + st.cls, st.glyph));
        var nameEl = h("button", "tk-link", t ? t.nameZh : p.taskId);
        nameEl.type = "button";
        nameEl.dataset.openTask = p.taskId;
        if (t) { nameEl.title = enTitle(t); }
        li.appendChild(nameEl);
        li.appendChild(h("span", "tk-req-meta",
          (t ? traderEn(t) + " · " : "") + "需" +
          (p.statuses || ["complete"]).map(function (s) {
            return s === "complete" ? "完成" : (s === "fail" ? "失败" : "接取中");
          }).join(" 或 ") + (p.logic === "or" ? "（OR）" : "")));
        pre.appendChild(li);
      });
      article.appendChild(pre);
    }

    // 3) 非任务型条件
    article.appendChild(sectionTitle("前置条件（非任务）"));
    if (!(rec.conditions || []).length) {
      article.appendChild(h("p", "tk-muted", "无额外的等级 / 忠诚 / 声望条件。"));
    } else {
      var conds = h("ul", "tk-cond-list");
      rec.conditions.forEach(function (c) {
        var li = h("li", "tk-cond");
        li.appendChild(h("span", "tk-cond-kind", condLabel(c.kind)));
        li.appendChild(h("span", null, c.text));
        conds.appendChild(li);
      });
      article.appendChild(conds);
    }
    if (av.reasons.length) {
      article.appendChild(taskNotice("当前阻塞", av.reasons.join("；"), "warn"));
    }
    if (av.unknown.length) {
      article.appendChild(taskNotice("无法自动判定（需自行确认）", av.unknown.join("；"), "info"));
    }

    // 4) 任务目标（可勾选）
    article.appendChild(sectionTitle("任务目标（" + (rec.objectives || []).length + "）"));
    var prog = progOf(id) || { objectives: {} };
    var objList = h("ul", "tk-obj-list");
    (rec.objectives || []).forEach(function (o) {
      var li = h("li", "tk-obj" + (o.optional ? " is-opt" : ""));
      var lab = h("label", "tk-obj-check");
      var cb = h("input");
      cb.type = "checkbox";
      cb.checked = !!(prog.objectives && prog.objectives[o.id]);
      cb.setAttribute("data-objective", o.id);
      cb.addEventListener("change", function () {
        toggleObjective(id, o.id);
        renderDetail();
        refreshVisual();
      });
      lab.appendChild(cb);
      lab.appendChild(h("span", "tk-obj-text", o.descZh));
      li.appendChild(lab);
      var metaBits = [];
      metaBits.push(o.kindZh);
      if (o.count > 1) { metaBits.push("×" + o.count); }
      if (o.optional) { metaBits.push("可选"); }
      if ((o.maps || []).length) { metaBits.push(mapText(o.maps)); }
      if (o.items && o.items.length) {
        metaBits.push("物品：" + o.items.slice(0, 3).map(function (it) { return it.name; }).join("、") +
          (o.items.length > 3 ? "…" : ""));
      }
      li.appendChild(h("span", "tk-obj-meta", metaBits.join(" · ")));
      if ((o.constraints || []).length) {
        li.appendChild(h("span", "tk-obj-cons", o.constraints.join("；")));
      }
      objList.appendChild(li);
    });
    article.appendChild(objList);
    article.appendChild(h("p", "tk-muted", "勾选目标会即时保存到本机；必需目标全部勾选后自动标记为已完成。"));

    // 5) 详细攻略
    // 来源与「是否人工复核」这类说明统一收进顶部菜单「关于」，任务详情里只在**真的缺攻略**时提示，
    // 否则每个任务头上都挂一条免责声明，正经看攻略时会被它打断。
    article.appendChild(sectionTitle("详细攻略"));
    var gstatus = guide.status || "missing";
    if (gstatus === "missing") {
      article.appendChild(taskNotice("攻略待补充", "当前任务尚无可用的详细攻略内容。", "warn"));
    }

    if (guide.overview) {
      article.appendChild(h("h4", "tk-h4", "任务概述"));
      article.appendChild(h("p", "tk-p", guide.overview));
    }
    if ((guide.prep || []).length) {
      article.appendChild(h("h4", "tk-h4", "准备工作"));
      article.appendChild(bulletList(guide.prep));
    }
    if ((guide.route || []).length) {
      article.appendChild(h("h4", "tk-h4", "地图与目标位置"));
      var rl = h("ul", "tk-bullets");
      guide.route.forEach(function (r) {
        var li = h("li");
        li.textContent = r.text;
        if ((r.zones || []).length) {
          li.appendChild(h("span", "tk-muted", "（目标点：" + r.zones.slice(0, 6).join("、") + "）"));
        }
        rl.appendChild(li);
      });
      article.appendChild(rl);
    }
    if ((guide.steps || []).length) {
      article.appendChild(h("h4", "tk-h4", "步骤攻略"));
      var ol = h("ol", "tk-steps");
      guide.steps.forEach(function (s) {
        var li = h("li");
        li.appendChild(h("span", "tk-step-kind", s.kindZh + (s.optional ? "（可选）" : "")));
        li.appendChild(h("span", "tk-step-text", s.text));
        if ((s.constraints || []).length) {
          li.appendChild(h("span", "tk-step-cons", s.constraints.join("；")));
        }
        ol.appendChild(li);
      });
      article.appendChild(ol);
    }
    if ((guide.notes || []).length) {
      article.appendChild(h("h4", "tk-h4", "注意事项"));
      article.appendChild(bulletList(guide.notes));
    }
    if ((guide.afterDone || []).length) {
      article.appendChild(h("h4", "tk-h4", "完成后的操作"));
      article.appendChild(bulletList(guide.afterDone));
    }
    if ((guide.parallel || []).length) {
      article.appendChild(h("h4", "tk-h4", "同图可并行推进"));
      var par = h("div", "tk-inline-links");
      guide.parallel.forEach(function (p) {
        var t = task(p.id);
        if (!t) { return; }
        var b = h("button", "tk-link", t.nameZh);
        b.type = "button";
        b.dataset.openTask = p.id;
        b.title = enTitle(t);
        par.appendChild(b);
      });
      article.appendChild(par);
    }

    // 6) 地图与目标位置（联动）
    var zones = [];
    (rec.objectives || []).forEach(function (o) {
      (o.zones || []).forEach(function (z) { zones.push({ zone: z, obj: o }); });
    });
    article.appendChild(sectionTitle("地图定位（" + zones.length + " 个目标区域）"));
    if (!zones.length) {
      article.appendChild(h("p", "tk-muted", "该任务没有上游标注的目标区域（位置待核实）。"));
    } else {
      var zl = h("ul", "tk-zone-list");
      zones.slice(0, 24).forEach(function (item) {
        var z = item.zone;
        var li = h("li", "tk-zone");
        li.appendChild(h("span", "tk-zone-map", z.mapName ? mapLabel(z.mapName) : "未知地图"));
        li.appendChild(h("span", "tk-zone-id", z.id || ""));
        if (z.position) {
          li.appendChild(h("span", "tk-zone-pos",
            "x " + Math.round(z.position.x) + " / z " + Math.round(z.position.z)));
        }
        var btn = taskButton("在地图定位", "tk-btn-mini");
        btn.setAttribute("data-locate-zone", String(zones.indexOf(item)));
        li.appendChild(btn);
        zl.appendChild(li);
      });
      article.appendChild(zl);
      article.appendChild(h("p", "tk-muted",
        "坐标来自 tarkov.dev 的世界坐标，经 data/maps.json 的 worldToSvg 仿射变换落到本地底图；" +
        "本地没有的地图会提示「本图未收录」。"));
    }

    // 7) 后续任务
    var postTitle = sectionTitle("后续任务（" + (rec.followUps || []).length + "）");
    postTitle.id = "tk-sec-post";
    article.appendChild(postTitle);
    if (!(rec.followUps || []).length) {
      article.appendChild(h("p", "tk-muted", "没有已收录的后续任务。"));
    } else {
      var fl = h("ul", "tk-req-list");
      rec.followUps.forEach(function (fid) {
        var t = task(fid);
        if (!t) { return; }
        var li = h("li", "tk-req");
        var st = STATUS[statusOf(fid)];
        li.appendChild(h("span", "tk-req-dot " + st.cls, st.glyph));
        var b = h("button", "tk-link", t.nameZh);
        b.type = "button";
        b.dataset.openTask = fid;
        b.title = enTitle(t);
        li.appendChild(b);
        var extra = [];
        if (t.minLevel) { extra.push("等级 " + t.minLevel); }
        (t.conditions || []).forEach(function (c) {
          if (c.kind === "traderLevel") { extra.push(c.text); }
        });
        li.appendChild(h("span", "tk-req-meta",
          traderEn(t) + (extra.length ? " · " + extra.join(" · ") : "")));
        fl.appendChild(li);
      });
      article.appendChild(fl);
    }

    // 8) 奖励
    var rewardTitle = sectionTitle("任务奖励");
    rewardTitle.id = "tk-sec-reward";
    article.appendChild(rewardTitle);
    var rw = rec.rewards || {};
    var rl2 = h("ul", "tk-bullets");
    if (rec.experience) { rl2.appendChild(h("li", null, "经验：" + rec.experience)); }
    (rw.traderStanding || []).forEach(function (s) {
      rl2.appendChild(h("li", null, "声望：" + traderNameById(s.traderId) + " " +
        (s.standing > 0 ? "+" : "") + s.standing));
    });
    (rw.items || []).forEach(function (it) {
      rl2.appendChild(h("li", null, "物品：" + it.name + " ×" + (it.count || 1)));
    });
    (rw.offerUnlock || []).forEach(function (o) {
      var nm = o.item ? ((state.tasks[o.item] || {}).name || o.item) : (o.trader || "商人报价");
      rl2.appendChild(h("li", null, "解锁商人报价：" + nm + (o.level ? "（LL" + o.level + "）" : "")));
    });
    (rw.traderUnlock || []).forEach(function (t) {
      rl2.appendChild(h("li", null, "解锁商人：" + traderNameById(t)));
    });
    (rw.achievement || []).forEach(function (a) {
      rl2.appendChild(h("li", null, "成就解锁：" + (a.name || a.id || "")));
    });
    if (!rl2.childNodes.length) { rl2.appendChild(h("li", "tk-muted", "上游未提供奖励数据。")); }
    article.appendChild(rl2);

    // R217：赛季说明已按用户要求搬到顶部菜单「关于」（见 syncAboutSeasonNote），
    // 详情页不再追加 footer —— 三处「每次打开都要念一遍」的说明现在只有「关于」一处。

    host.appendChild(article);
    if (window.GWI18n) { window.GWI18n.localize(host, true); }
    // R73：换任务后详情回到顶部（innerHTML 同步重建时浏览器会沿用旧 scrollTop）
    host.scrollTop = 0;
  }

  function condLabel(kind) {
    var map = {
      playerLevel: "角色等级", traderLevel: "商人忠诚", traderStanding: "商人声望",
      faction: "阵营", skill: "技能", dialogue: "对话", globalVariable: "剧情变量"
    };
    return map[kind] || "条件";
  }

  function sectionTitle(text) {
    return h("h3", "tk-h3", text);
  }

  function bulletList(items) {
    var ul = h("ul", "tk-bullets");
    items.forEach(function (x) { ul.appendChild(h("li", null, x)); });
    return ul;
  }

  // ---------------------------------------------------------------- 进度页
  function renderProgress() {
    var host = state.el.progress;
    if (!host) { return; }
    host.innerHTML = "";
    var wrap = h("div", "tk-progress-wrap");

    var toolbar = h("div", "tk-progress-tools");
    var lvLab = h("label", "tk-sel");
    lvLab.appendChild(h("span", "tk-sel-label", "我的等级"));
    var lv = h("input", "tk-lv-input");
    lv.type = "number"; lv.id = "tk-player-level"; lv.min = "1"; lv.max = "80";
    lv.value = state.ui.playerLevel || "";
    lv.placeholder = "未填写";
    lvLab.appendChild(lv);
    toolbar.appendChild(lvLab);
    var exportBtn = taskButton("导出进度");
    exportBtn.id = "tk-export";
    exportBtn.addEventListener("click", exportProgress);
    toolbar.appendChild(exportBtn);
    var importBtn = taskButton("导入进度");
    importBtn.id = "tk-import";
    importBtn.addEventListener("click", function () {
      var f = document.getElementById("tk-import-file");
      if (f) { f.click(); }
    });
    toolbar.appendChild(importBtn);
    var file = h("input");
    file.type = "file";
    file.accept = ".json,application/json";
    file.id = "tk-import-file";
    file.hidden = true;
    toolbar.appendChild(file);
    var clearBtn = taskButton("清空本模式进度", "", { variant: "danger" });
    clearBtn.id = "tk-clear";
    clearBtn.addEventListener("click", function () {
      if (!window.confirm("确定清空当前模式（" + modeLabel() +
        "）的全部任务进度？此操作只影响本机、只影响当前模式，且不可撤销。")) { return; }
      state.progress.modes[state.mode] = {};
      saveProgress();
      renderAll();
    });
    toolbar.appendChild(clearBtn);
    wrap.appendChild(toolbar);

    var c = countByStatus();
    var cards = h("div", "tk-cards");
    [["进行中", c.active, "active"], ["已完成", c.completed, "done"],
     ["未开始", c.none, "none"], ["已失败", c.failed, "fail"]].forEach(function (x) {
      cards.appendChild(taskSummaryCard(x[0], x[1], x[2]));
    });
    wrap.appendChild(cards);

    // 三模式进度总览：明确显示「另一模式的完成数」不会串到本模式
    var counts = progressCount();
    var modeBox = h("section", "tk-group tk-progress-modes");
    modeBox.appendChild(h("h3", "tk-group-title", "三模式进度对照（各自独立，互不联动）"));
    var mt = h("table", "tk-modetable");
    var mh = h("tr");
    ["模式", "数据任务数", "本模式记录", "已完成", "进行中", "操作"].forEach(function (t) {
      mh.appendChild(h("th", null, t));
    });
    mt.appendChild(mh);
    MODES.forEach(function (m) {
      var tr = h("tr", m.key === state.mode ? "is-cur" : null);
      tr.appendChild(h("td", null, m.full));
      var pack = state.cache[m.key];
      tr.appendChild(h("td", null, pack ? String(pack.meta.counts.tasks || 0) : "未载入"));
      tr.appendChild(h("td", null, String(counts[m.key] || 0)));
      if (pack) {
        var done = 0, act = 0;
        Object.keys(state.progress.modes[m.key] || {}).forEach(function (tid) {
          var s = (state.progress.modes[m.key][tid] || {}).status;
          if (s === "completed") { done++; } else if (s === "active") { act++; }
        });
        tr.appendChild(h("td", null, String(done)));
        tr.appendChild(h("td", null, String(act)));
      } else {
        tr.appendChild(h("td", null, "—"));
        tr.appendChild(h("td", null, "—"));
      }
      var td = h("td");
      // R74：切换入口只在右上角全局条；这里只标注当前模式，不再放「切换到 X」按钮。
      td.appendChild(h("span", "tk-muted", m.key === state.mode ? "当前模式" : "在右上角切换"));
      tr.appendChild(td);
      mt.appendChild(tr);
    });
    modeBox.appendChild(mt);
    wrap.appendChild(modeBox);

    var groups = [
      { title: "进行中的任务", list: state.order.filter(function (id) { return statusOf(id) === "active"; }) },
      { title: "当前可接取（前置已满足；等级/声望见详情）", list: state.order.filter(function (id) {
        return availability(state.tasks[id]).state === "open";
      }) },
      { title: "暂时无法接取（含阻塞原因）", list: state.order.filter(function (id) {
        return availability(state.tasks[id]).state === "blocked";
      }), showReason: true },
      { title: "已完成但还没看后续", list: state.order.filter(function (id) {
        return statusOf(id) === "completed" && (state.tasks[id].followUps || []).some(function (f) {
          return statusOf(f) === "none";
        });
      }) },
      { title: "已失败（分支不可继续）", list: state.order.filter(function (id) { return statusOf(id) === "failed"; }) }
    ];

    // 同图并行：当前进行中任务里，同一张地图上的其它未完成任务
    var activeMaps = {};
    state.order.forEach(function (id) {
      if (statusOf(id) !== "active") { return; }
      (state.tasks[id].maps || []).forEach(function (m) { activeMaps[m] = 1; });
    });
    var parallel = state.order.filter(function (id) {
      if (statusOf(id) === "completed") { return false; }
      return (state.tasks[id].maps || []).some(function (m) { return activeMaps[m]; });
    });
    groups.splice(3, 0, { title: "同图可并行推进（与进行中任务同地图）", list: parallel.slice(0, 40) });

    groups.forEach(function (g) {
      var box = h("section", "tk-group");
      box.appendChild(h("h3", "tk-group-title", g.title + "（" + g.list.length + "）"));
      if (!g.list.length) {
        box.appendChild(h("p", "tk-muted", "没有符合条件的任务。"));
        wrap.appendChild(box);
        return;
      }
      var ul = h("ul", "tk-progress-list");
      g.list.slice(0, 60).forEach(function (id) {
        var rec = state.tasks[id];
        var li = h("li", "tk-progress-item");
        li.appendChild(h("span", "tk-req-dot " + STATUS[statusOf(id)].cls, STATUS[statusOf(id)].glyph));
        var b = h("button", "tk-link", rec.nameZh);
        b.type = "button";
        b.dataset.openTask = id;
        b.title = enTitle(rec);
        li.appendChild(b);
        var meta = [traderEn(rec), "等级 " + (rec.minLevel || 0)];
        if ((rec.maps || []).length) { meta.push(mapText(rec.maps.slice(0, 2))); }
        li.appendChild(h("span", "tk-req-meta", meta.join(" · ")));
        if (g.showReason) {
          var av = availability(rec);
          if (av.reasons.length) {
            li.appendChild(h("span", "tk-progress-reason", av.reasons.slice(0, 2).join("；")));
          }
        }
        ul.appendChild(li);
      });
      box.appendChild(ul);
      wrap.appendChild(box);
    });

    // R217：存储说明（localStorage / 按模式隔离 / 导入导出不会覆盖原数据）已搬到
    // 顶部菜单「关于」，进度页不再每屏重复一遍。

    host.appendChild(wrap);
    if (window.GWI18n) { window.GWI18n.localize(host, true); }
  }

  // ---------------------------------------------------------------- 导入导出
  function exportProgress() {
    var doc = {
      schema: 1,
      kind: "eftmap-task-progress",
      exportedAt: new Date().toISOString(),
      activeMode: state.mode,
      modes: state.progress.modes
    };
    var text = JSON.stringify(doc, null, 1);
    try {
      var blob = new Blob([text], { type: "application/json" });
      var a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "eft-task-progress-" + new Date().toISOString().slice(0, 10) + ".json";
      document.body.appendChild(a);
      a.click();
      setTimeout(function () {
        URL.revokeObjectURL(a.href);
        a.remove();
      }, 0);
      var n = progressCount();
      setStatusText("已导出进度（PvP " + n.regular + " / PvE " + n.pve +
        " / PvPS（赛季服）" + n.pvps + " 条记录）");
    } catch (e) {
      setStatusText("导出失败：" + (e && e.message || e));
    }
    return text;
  }

  function importFromFile(file) {
    if (!file) { return; }
    var reader = new FileReader();
    reader.onload = function () {
      var msg = importProgress(String(reader.result || ""));
      setStatusText(msg);
      renderAll();
    };
    reader.onerror = function () { setStatusText("读取文件失败，原进度未改动。"); };
    reader.readAsText(file);
  }

  /** 导入：先全量校验，任何一步失败都不落盘（原数据保持不变）。 */
  function importProgress(text) {
    var doc;
    try { doc = JSON.parse(text); } catch (e) { return "导入失败：不是合法 JSON，原进度未改动。"; }
    if (!doc || doc.kind !== "eftmap-task-progress" || doc.schema !== 1 || !doc.modes) {
      return "导入失败：文件结构不符合任务进度格式，原进度未改动。";
    }
    // 只接收已知模式；未知模式（例如别的版本）不写入，但也不清空已有三模式数据
    var clean = {};
    MODE_KEYS.forEach(function (m) { clean[m] = {}; });
    var unknownMode = 0, bad = 0, total = 0;
    Object.keys(doc.modes).forEach(function (mode) {
      if (MODE_KEYS.indexOf(mode) < 0) { unknownMode++; return; }
      Object.keys(doc.modes[mode] || {}).forEach(function (tid) {
        var rec = doc.modes[mode][tid];
        if (!rec || typeof rec !== "object") { bad++; return; }
        var status = ["none", "active", "completed", "failed"].indexOf(rec.status) >= 0 ? rec.status : "none";
        var objectives = {};
        Object.keys(rec.objectives || {}).forEach(function (oid) {
          if (rec.objectives[oid]) { objectives[oid] = true; }
        });
        clean[mode][tid] = { status: status, objectives: objectives,
                             updatedAt: rec.updatedAt || new Date().toISOString() };
        total++;
      });
    });
    state.progress = { schema: 1, modes: clean };
    saveProgress();
    broadcast();
    renderAll();
    return "已导入：" + MODE_KEYS.map(function (m) {
      return modeLabel(m) + " " + Object.keys(clean[m]).length + " 条";
    }).join("、") +
      (unknownMode ? "；忽略 " + unknownMode + " 个未知模式段" : "") +
      (bad ? "；忽略 " + bad + " 条非法记录" : "") +
      (total ? "" : "；文件里没有可导入的记录");
  }

  // ---------------------------------------------------------------- 地图联动
  function locateSelected() {
    if (!state.selected) { return; }
    var rec = task(state.selected);
    var zone = null, obj = null;
    (rec.objectives || []).forEach(function (o) {
      if (!zone && o.zones && o.zones.length) { zone = o.zones[0]; obj = o; }
    });
    if (!zone) {
      setStatusText("该任务没有可定位的目标区域（位置待核实）。");
      return;
    }
    locateZone(zone, rec, obj);
  }

  /** 详情页目标区域列表的索引定位（与侧栏「在地图定位」同一条路径）。 */
  function locateZoneByIndex(index) {
    var rec = task(state.selected);
    if (!rec) { return; }
    var zones = [];
    (rec.objectives || []).forEach(function (o) {
      (o.zones || []).forEach(function (z) { zones.push({ zone: z, obj: o }); });
    });
    var item = zones[index];
    if (!item) { setStatusText("该目标区域缺少坐标数据（位置待核实）。"); return; }
    locateZone(item.zone, rec, item.obj);
  }

  /** 从列表行直接定位某个目标的首个区域点（db4 板的 ◎ 按钮）。 */
  function locateByObjective(taskId, objId) {
    var rec = task(taskId);
    if (!rec) { return; }
    var obj = (rec.objectives || []).filter(function (o) { return o.id === objId; })[0];
    if (!obj) { return; }
    var zone = (obj.zones || [])[0];
    if (!zone) {
      setStatusText("该目标区域缺少坐标数据（位置待核实）。");
      return;
    }
    locateZone(zone, rec, obj);
  }

  function locateZone(zone, rec, obj) {
    if (!window.GWMapFocus) {
      setStatusText("地图联动接口不可用（主程序未就绪）。");
      return;
    }
    var ok = window.GWMapFocus(zone.mapId, zone.position, {
      label: rec.nameZh + (obj ? " · " + obj.descZh : ""),
      mapName: zone.mapName
    });
    if (!ok) {
      setStatusText("本图未收录到本地地图数据：" + (zone.mapName || zone.mapId) + "（位置待核实）。");
    } else {
      setStatusText("已在地图「" + zone.mapName + "」定位：" + rec.nameZh);
    }
  }

  // ---------------------------------------------------------------- 渲染总控
  function renderAll() {
    if (!state.el.root) { return; }
    renderModeNote();
    renderTree();
    if (state.view === "detail") { renderDetail(); }
    if (state.view === "progress") { renderProgress(); }
    renderSide();
    updateCounts();
  }

  function setStatusAndRender(id, status) {
    requestStatusChange(id, status);
  }

  function expandChain(dir) {
    if (!state.selected || !state.graph) { return; }
    var set = {};
    var walk = function (id, depth) {
      if (depth > 12 || set[id]) { return; }
      set[id] = 1;
      var rec = task(id);
      if (!rec) { return; }
      var next = dir === "pre" ? (rec.prerequisites || []).map(function (p) { return p.taskId; })
        : (rec.followUps || []);
      next.forEach(function (n) { walk(n, depth + 1); });
    };
    walk(state.selected, 0);
    state.filters = emptyFilters();
    state.filters.onlyMatch = true;
    state.matches = Object.keys(set);
    state.matchIdx = 0;
    state.search = "";
    saveUi();
    if (state.el.search) { state.el.search.value = ""; }
    refreshVisual();
    setTimeout(fitTree, 30);
    setStatusText((dir === "pre" ? "前置链" : "后续链") + "共 " + state.matches.length + " 个任务");
  }

  // ---------------------------------------------------------------- R86 剧情系统
  // 数据：data/stories.json（tools/build_stories.py 由 eftarkov 剧情页快照 + task-points 构建）
  // 结构对齐 db4tarkov：剧情线 = 章节容器，节点 = objectives，分支 = choice key/value，
  // 结局 = story_the_ticket_ending 这类 storyVariable 的取值。进度与任务进度分开存。

  function storyById(id) {
    if (!state.storyDoc || !id) { return null; }
    var list = state.storyDoc.stories || [];
    for (var i = 0; i < list.length; i++) {
      if (list[i].id === id) { return list[i]; }
    }
    return null;
  }

  function storyModes() {
    var out = {};
    MODE_KEYS.forEach(function (m) { out[m] = {}; });
    return out;
  }

  function ensureStoryMode() {
    var modes = state.storyProgress.modes;
    if (!modes[state.mode]) { modes[state.mode] = {}; }
    var m = modes[state.mode];
    if (!m.steps) { m.steps = {}; }
    if (!m.choices) { m.choices = {}; }
    return m;
  }

  function loadStoryProgress() {
    try {
      var raw = localStorage.getItem(LS_STORY_PROGRESS);
      if (!raw) { return; }
      var doc = JSON.parse(raw);
      if (!doc || doc.schema !== 1 || !doc.modes) { return; }
      var modes = storyModes();
      MODE_KEYS.forEach(function (m) { modes[m] = doc.modes[m] || {}; });
      state.storyProgress = { schema: 1, modes: modes };
    } catch (e) { /* 坏数据不覆盖：当空进度处理 */ }
  }

  function saveStoryProgress() {
    try {
      localStorage.setItem(LS_STORY_PROGRESS, JSON.stringify(state.storyProgress));
      return true;
    } catch (e) {
      if (window.console && console.warn) { console.warn("[GWTasks] saveStoryProgress failed", e); }
      return false;
    }
  }

  function loadStoryUi() {
    try {
      var raw = localStorage.getItem(LS_STORY_UI);
      if (!raw) { return; }
      var doc = JSON.parse(raw);
      if (!doc || typeof doc !== "object") { return; }
      if (typeof doc.search === "string") { state.storySearch = doc.search; }
      if (typeof doc.filter === "string") {
        for (var i = 0; i < STORY_FILTERS.length; i++) {
          if (STORY_FILTERS[i].key === doc.filter) { state.storyFilter = doc.filter; }
        }
      }
      if (doc.selected && typeof doc.selected === "string") { state.storySelected = doc.selected; }
      if (doc.expand && typeof doc.expand === "object") { state.storyExpand = doc.expand; }
    } catch (e) { /* 忽略 */ }
  }

  function saveStoryUi() {
    try {
      localStorage.setItem(LS_STORY_UI, JSON.stringify({
        search: state.storySearch,
        filter: state.storyFilter,
        selected: state.storySelected,
        expand: state.storyExpand
      }));
    } catch (e) { /* 忽略 */ }
  }

  function ensureStories() {
    if (state.storyReady || state.storyLoading) { flushPendingStory(); return; }
    state.storyLoading = true;
    renderStory();
    fetch("data/stories.json", { cache: "no-store" }).then(function (r) {
      if (!r.ok) { throw new Error("HTTP " + r.status); }
      return r.json();
    }).then(function (doc) {
      state.storyDoc = doc || { stories: [] };
      state.storyReady = true;
      state.storyLoading = false;
      if (!state.storySelected && state.storyDoc.stories && state.storyDoc.stories.length) {
        state.storySelected = state.storyDoc.stories[0].id;
      }
      renderStory();
      flushPendingStory();
    }).catch(function (err) {
      state.storyLoading = false;
      state.storyError = String(err && err.message || err);
      renderStory();
    });
  }

  function flushPendingStory() {
    if (!state.pendingStoryOpen || !state.storyReady) { return; }
    var p = state.pendingStoryOpen;
    state.pendingStoryOpen = null;
    openStory(p.storyId, p.stepId);
  }

  function storyStepDone(sid, stepId) {
    var m = ensureStoryMode();
    return !!(m.steps[sid] && m.steps[sid][stepId]);
  }

  function storyChoiceValue(sid, key) {
    var m = ensureStoryMode();
    return (m.choices[sid] && m.choices[sid][key]) || "";
  }

  function storyDoneCount(story) {
    var n = 0;
    (story.steps || []).forEach(function (st) {
      if (storyStepDone(story.id, st.id)) { n++; }
    });
    return n;
  }

  function storyStatus(story) {
    var total = (story.steps || []).length;
    var done = storyDoneCount(story);
    if (total && done >= total) { return "done"; }
    if (done > 0) { return "active"; }
    return "none";
  }

  function storyLocked(story) {
    var pres = story.prerequisites || [];
    for (var i = 0; i < pres.length; i++) {
      var pre = storyById(pres[i].storyId);
      if (!pre) { continue; }
      var satisfied = storyStatus(pre) === "done" || !!storyChoiceValue(pre.id, pres[i].choiceKey);
      if (!satisfied) { return true; }
    }
    return false;
  }

  // ---------------------------------------------------------------- R100 剧情步骤联动
  /**
   * 剧情树的前置关系与三态判定同源：storyStepStatus 把「同一条剧情线里排在前面的
   * 任意一步未完成」判为 locked。所以这里的「前置」就是 steps[0..idx-1] 中所有未完成
   * 的步骤，不另建第二套依赖数据。
   *
   * 数据事实（data/stories.json）：steps 只有 id / order / name / maps / points，没有
   * 步骤级的显式 requires 字段；结局与分支选项是 story.choices（role=ending），不在
   * steps 里，结构上不会成为可自动完成的前置。这里仍做一次防御性跳过并记日志。
   *
   * 与普通任务一致：确认前不写任何状态；确认后一次写入；取消则全部保持原样。
   */
  function storyStepIndex(story, stepId) {
    var steps = (story && story.steps) || [];
    for (var i = 0; i < steps.length; i++) {
      if (steps[i] && steps[i].id === stepId) { return i; }
    }
    return -1;
  }

  /** 抉择 / 结局节点 id → role（正常数据里它们不在 steps 中，仅作防御）。
   *  stories.json 的 choices 用 key（不是 id），结局的各个选项在 options[].value / endingKey
   *  上；这里把两处都记进映射，万一步骤误用了结局选项键也能被识别并跳过。 */
  function storyChoiceRoleMap(story) {
    var out = {};
    ((story && story.choices) || []).forEach(function (c) {
      if (!c) { return; }
      var role = c.role || "";
      var key = c.key || c.id;
      if (key) { out[key] = role; }
      if (role === "ending") {
        (c.options || []).forEach(function (o) {
          if (!o) { return; }
          if (o.value) { out[o.value] = "ending"; }
          if (o.endingKey) { out[o.endingKey] = "ending"; }
        });
      }
    });
    return out;
  }

  function storyPlanLog(msg) {
    if (window.console && console.warn) { console.warn("[GWTasks] " + msg); }
  }

  /** 三态与联动共用的唯一前置判定：idx 之前所有未完成步骤的下标（由近到远）。 */
  function storyMissingPrereqs(story, idx) {
    var out = [];
    for (var i = idx - 1; i >= 0; i--) {
      if (!storyStepDone(story.id, story.steps[i].id)) { out.push(i); }
    }
    return out;
  }

  /** 计划 A：把 idx 设为完成，需要一并完成哪些前置步骤（由近到远）。 */
  function planStoryPrereqFix(story, idx) {
    var steps = (story && story.steps) || [];
    if (!story || idx < 0 || idx >= steps.length) { return null; }
    var target = steps[idx];
    if (!target || !target.id) { return null; }
    var roles = storyChoiceRoleMap(story);
    var missing = storyMissingPrereqs(story, idx);
    if (missing.length > 1000) {
      storyPlanLog("剧情「" + (story.nameZh || story.id) +
        "」前置链超过安全上限，已停止规划（未做任何修改）");
      return null;
    }
    var seen = {}, changes = [], skipped = [];
    missing.forEach(function (i) {
      var st = steps[i];
      if (!st || !st.id) { return; }
      if (seen[st.id]) {
        // 线性依赖不会成环；出现重复 id 说明数据异常，只处理一次并如实记日志
        storyPlanLog("剧情「" + (story.nameZh || story.id) + "」步骤 id 重复：" + st.id + "（已跳过重复项）");
        return;
      }
      seen[st.id] = 1;
      if (roles[st.id] === "ending") {
        skipped.push({ id: st.id, name: st.name || st.id, why: "结局分支不参与自动完成" });
        return;
      }
      changes.push({ id: st.id, name: st.name || st.id, idx: i, depth: idx - 1 - i });
    });
    if (!changes.length) { return null; }
    return { kind: "prereq", storyId: story.id, stepId: target.id,
             stepName: target.name || target.id, changes: changes, skipped: skipped };
  }

  /** 计划 B：撤销 idx 会影响哪些已完成的后续步骤（由近到远）。 */
  function planStoryFollowUpReset(story, idx) {
    var steps = (story && story.steps) || [];
    if (!story || idx < 0 || idx >= steps.length) { return null; }
    var target = steps[idx];
    if (!target || !target.id) { return null; }
    var changes = [], guard = 0;
    for (var i = idx + 1; i < steps.length; i++) {
      if (guard++ > 1000) {
        storyPlanLog("剧情「" + (story.nameZh || story.id) +
          "」后续链展开超过安全上限，已停止规划（未做任何修改）");
        break;
      }
      var st = steps[i];
      if (!st || !st.id) { continue; }
      if (!storyStepDone(story.id, st.id)) { continue; }
      changes.push({ id: st.id, name: st.name || st.id, idx: i, depth: i - idx - 1 });
    }
    if (!changes.length) { return null; }
    return { kind: "reset", storyId: story.id, stepId: target.id,
             stepName: target.name || target.id, changes: changes };
  }

  /** 计划正文：复用任务联动弹窗的 tk-plan* 结构（不改类名、不新增样式）。 */
  function storyPlanBody(plan) {
    var wrap = h("div", "tk-plan");
    var head = h("p", "tk-plan-head");
    var isPre = plan.kind === "prereq";
    head.textContent = isPre
      ? "你正在将「" + plan.stepName + "」标记为完成，但前面还有 " + plan.changes.length +
        " 个步骤未完成，确认后会一并完成。"
      : "将「" + plan.stepName + "」标记为未完成，会影响 " + plan.changes.length +
        " 个已完成的后续步骤。";
    wrap.appendChild(head);

    var list = h("ul", "tk-plan-list");
    var byDepth = {};
    plan.changes.forEach(function (c) { (byDepth[c.depth] = byDepth[c.depth] || []).push(c); });
    Object.keys(byDepth).map(Number).sort(function (a, b) { return a - b; }).forEach(function (d) {
      list.appendChild(h("li", "tk-plan-group",
        isPre
          ? (d === 0 ? "直接前置（第 1 层）" : "间接前置（第 " + (d + 1) + " 层）")
          : (d === 0 ? "直接后续" : "间接（第 " + (d + 1) + " 层）")));
      byDepth[d].forEach(function (c) {
        var li = h("li", "tk-plan-item");
        li.appendChild(h("span", "tk-plan-name", "「" + c.name + "」"));
        li.appendChild(h("span", null, isPre
          ? "：#" + (c.idx + 1) + " 未完成 → 已完成"
          : "：#" + (c.idx + 1) + " 已完成 → 未完成"));
        list.appendChild(li);
      });
    });
    (plan.skipped || []).forEach(function (s) {
      list.appendChild(h("li", "tk-plan-warn", "「" + s.name + "」已跳过：" + s.why));
    });
    wrap.appendChild(list);
    wrap.appendChild(h("p", "tk-plan-note", "确认前不会修改任何剧情进度；取消则全部保持原样。"));
    return wrap;
  }

  function storyPlanSignature(plan) {
    if (!plan) { return "null"; }
    return plan.kind + "|" + plan.changes.map(function (c) { return c.id; }).sort().join(";");
  }

  /** 一次写入（带快照回滚）：完成 / 撤销若干步骤后立即重绘三态、勾选、进度条与统计。 */
  function applyStoryStepBatch(storyId, ids, done) {
    if (!storyId || !ids || !ids.length) { return true; }
    var snapshot = JSON.stringify(state.storyProgress);
    var m = ensureStoryMode();
    if (!m.steps[storyId]) { m.steps[storyId] = {}; }
    try {
      ids.forEach(function (id) {
        if (done) { m.steps[storyId][id] = true; }
        else { delete m.steps[storyId][id]; }
      });
    } catch (e) {
      state.storyProgress = JSON.parse(snapshot);
      setStatusText("剧情进度更新失败，已回滚：" + (e && e.message || e));
      renderStory();
      return false;
    }
    if (!saveStoryProgress()) {
      state.storyProgress = JSON.parse(snapshot);
      setStatusText("剧情进度保存失败（浏览器存储不可写），已回滚本次 " + ids.length + " 项变更。");
      renderStory();
      return false;
    }
    renderStory();
    return true;
  }

  function executeStoryPlan(plan) {
    var story = storyById(plan.storyId);
    var idx = storyStepIndex(story, plan.stepId);
    var fresh = plan.kind === "prereq"
      ? planStoryPrereqFix(story, idx)
      : planStoryFollowUpReset(story, idx);
    if (storyPlanSignature(fresh) !== storyPlanSignature(plan)) {
      setStatusText("剧情进度刚发生变化，联动计划已失效，请重新操作（本次未修改任何状态）。");
      renderStory();
      return;
    }
    var ids = plan.changes.map(function (c) { return c.id; });
    ids.push(plan.stepId);
    if (plan.kind === "prereq") {
      if (applyStoryStepBatch(plan.storyId, ids, true)) {
        setStatusText("已一并完成 " + plan.changes.length + " 个前置步骤，并把「" +
          plan.stepName + "」标记为完成。");
      }
    } else {
      if (applyStoryStepBatch(plan.storyId, ids, false)) {
        setStatusText("已撤销「" + plan.stepName + "」及其 " + plan.changes.length + " 个后续步骤。");
      }
    }
  }

  function openStoryLinkageDialog(plan) {
    var UI = window.GWUI;
    if (!UI || !UI.dialog) {
      // 没有通用弹窗时退回原生 confirm（与任务联动一致）
      if (window.confirm(storyPlanBody(plan).textContent)) { executeStoryPlan(plan); }
      return;
    }
    var busy = false;
    UI.dialog({
      title: plan.kind === "prereq" ? "前置步骤尚未完成" : "重置后续步骤？",
      wide: true,
      body: storyPlanBody(plan),
      buttons: plan.kind === "prereq"
        ? [
            { label: "取消", variant: "" },
            { label: "确认并完成前置步骤", variant: "primary", onClick: function () {
              if (busy) { return false; }
              busy = true;
              executeStoryPlan(plan);
            } }
          ]
        : [
            { label: "取消", variant: "" },
            { label: "仅撤销当前步骤", variant: "", onClick: function () {
              if (busy) { return false; }
              busy = true;
              if (applyStoryStepBatch(plan.storyId, [plan.stepId], false)) {
                setStatusText("已撤销「" + plan.stepName + "」（后续步骤保持不变）");
              }
            } },
            { label: "确认并撤销后续步骤", variant: "primary", onClick: function () {
              if (busy) { return false; }
              busy = true;
              executeStoryPlan(plan);
            } }
          ]
    });
  }

  /** 用户入口：完成前先算前置计划；撤销时若有已完成后续则先算重置计划。 */
  function requestStoryStepToggle(stepId) {
    var sid = state.storySelected;
    if (!sid || !stepId) { return; }
    var story = storyById(sid);
    if (!story) { return; }
    var idx = storyStepIndex(story, stepId);
    if (idx < 0) { return; }
    var name = story.steps[idx].name || stepId;
    if (storyStepDone(sid, stepId)) {
      var planB = planStoryFollowUpReset(story, idx);
      if (planB) { openStoryLinkageDialog(planB); return; }
      if (applyStoryStepBatch(sid, [stepId], false)) {
        setStatusText("已撤销「" + name + "」");
      }
      return;
    }
    var planA = planStoryPrereqFix(story, idx);
    if (planA) { openStoryLinkageDialog(planA); return; }
    if (applyStoryStepBatch(sid, [stepId], true)) {
      setStatusText("已完成「" + name + "」");
    }
  }

  function chooseStoryOption(key, value) {
    var sid = state.storySelected;
    if (!sid || !key) { return; }
    var m = ensureStoryMode();
    if (!m.choices[sid]) { m.choices[sid] = {}; }
    if (m.choices[sid][key] === value) { delete m.choices[sid][key]; }
    else { m.choices[sid][key] = value; }
    saveStoryProgress();
    renderStory();
  }

  /** 把深链里的点位短键（objectiveId 前 8 位）尽量解析成剧情树里的步骤 id。 */
  function resolveStoryStep(story, key) {
    if (!key || !story) { return null; }
    var steps = story.steps || [];
    var i;
    for (i = 0; i < steps.length; i++) {
      if (steps[i].id === key) { return steps[i].id; }
    }
    var pref = String(key).slice(0, 8);
    for (i = 0; i < steps.length; i++) {
      if (steps[i].id.slice(0, 8) === pref) { return steps[i].id; }
    }
    return null;
  }

  function openStory(id, stepId) {
    if (!id) { return; }
    state.missingStory = null;
    if (!state.storyReady) {
      state.storySelected = id;
      state.storyStep = stepId || null;
      state.pendingStoryOpen = { storyId: id, stepId: stepId || null };
      setView("story");
      return;
    }
    var story = storyById(id);
    if (!story) {
      state.missingStory = id;
      state.storySelected = null;
      state.storyStep = null;
      setView("story");
      renderStory();
      return;
    }
    state.pendingStoryOpen = null;
    state.storySelected = id;
    var resolved = resolveStoryStep(story, stepId);
    state.storyStep = resolved;
    if (resolved) { state.storyExpand[id] = true; }
    setView("story");
    saveStoryUi();
    renderStory();
    if (resolved) {
      requestAnimationFrame(function () {
        var node = $('[data-story-node="' + resolved + '"]', state.el.storyMain || document);
        if (node && node.scrollIntoView) {
          try { node.scrollIntoView({ block: "center", behavior: "smooth" }); }
          catch (e) { node.scrollIntoView(); }
        }
      });
    }
  }

  function storyMatches(story) {
    var q = String(state.storySearch || "").toLowerCase();
    if (q) {
      var hay = [story.nameZh, story.nameEn, story.id, story.storyKey || ""]
        .concat((story.steps || []).map(function (s) { return s.name; }))
        .join(" ").toLowerCase();
      if (hay.indexOf(q) < 0) { return false; }
    }
    var st = storyStatus(story);
    var f = state.storyFilter;
    if (f === "none" && st !== "none") { return false; }
    if (f === "active" && st !== "active") { return false; }
    if (f === "done" && st !== "done") { return false; }
    if (f === "endings") {
      var has = (story.choices || []).some(function (c) { return c.role === "ending"; });
      if (!has) { return false; }
    }
    return true;
  }

  function storyStatusText(st) {
    if (st === "done") { return "已完成"; }
    if (st === "active") { return "进行中"; }
    return "未开始";
  }

  function storyGapsNode() {
    var gaps = (state.storyDoc && state.storyDoc.dataGaps) || [];
    if (!gaps.length) { return null; }
    var det = h("details", "tk-story-gaps");
    det.appendChild(h("summary", null, "数据缺口 / 说明（" + gaps.length + "）"));
    var ul = h("ul");
    gaps.forEach(function (g) { ul.appendChild(h("li", null, g.message || String(g))); });
    det.appendChild(ul);
    return det;
  }

  // R86：data/stories.json 里的 maps 是 data/maps.json 的 key（与 task-points.json 一致），
  // 任务侧 mapLabel 只处理两个特例名，所以剧情 chip 单独用这份 key → 中文名（取自 data/maps.json）。
  var STORY_MAP_LABELS = {
    "streets-of-tarkov": "塔科夫街区",
    "ground-zero": "中心区",
    "customs": "海关",
    "factory": "工厂",
    "icebreaker": "破冰船",
    "interchange": "立交桥",
    "the-lab": "实验室",
    "the-labyrinth": "迷宫",
    "lighthouse": "灯塔",
    "reserve": "储备站",
    "shoreline": "海岸线",
    "terminal": "码头",
    "woods": "森林",
    "infected-lab": "实验室疫区",
    "infected-factory": "工厂疫区"
  };

  function storyMapLabel(m) {
    return STORY_MAP_LABELS[m] || mapLabel(m);
  }

  function storyMapChips(host, maps) {
    (maps || []).forEach(function (m) {
      host.appendChild(h("span", "tk-story-chip", storyMapLabel(m)));
    });
  }

  function renderStoryStats() {
    var host = state.el.storyStats;
    if (!host) { return; }
    host.textContent = "";
    if (!state.storyReady) { return; }
    var list = state.storyDoc.stories || [];
    var visible = list.filter(storyMatches);
    var steps = 0, done = 0, endings = 0;
    list.forEach(function (s) {
      steps += (s.steps || []).length;
      done += storyDoneCount(s);
      if ((s.choices || []).some(function (c) { return c.role === "ending"; })) { endings++; }
    });
    host.appendChild(h("span", "tk-story-stat", "剧情线 " + visible.length + " / " + list.length));
    host.appendChild(h("span", "tk-story-stat", "步骤 " + done + " / " + steps));
    if (endings) { host.appendChild(h("span", "tk-story-stat", "含结局 " + endings)); }
  }

  function renderStoryList() {
    var host = state.el.storyList;
    if (!host) { return; }
    host.textContent = "";
    if (!state.storyReady) {
      host.appendChild(h("div", "tk-story-empty " + (state.storyError ? "is-error" : "is-loading"),
        state.storyError ? "剧情数据加载失败" : "正在加载剧情数据…"));
      return;
    }
    var list = (state.storyDoc.stories || []).filter(storyMatches);
    if (!list.length) {
      host.appendChild(h("div", "tk-story-empty", "没有匹配的剧情线，换个关键词或筛选试试"));
      return;
    }
    list.forEach(function (s) {
      var b = h("button", "tk-story-item");
      b.type = "button";
      b.dataset.storyId = s.id;
      if (s.id === state.storySelected) { b.classList.add("is-on"); }
      if (storyLocked(s)) { b.classList.add("is-locked"); }
      b.appendChild(h("span", "tk-story-item-name", s.nameZh || s.nameEn || s.id));
      var total = (s.steps || []).length;
      var done = storyDoneCount(s);
      b.appendChild(h("span", "tk-story-item-meta",
        (s.maps || []).length + " 张地图 · " + total + " 步"));
      var bar = h("span", "tk-story-item-bar");
      var fill = h("span", "tk-story-item-fill");
      fill.style.width = (total ? Math.round(done / total * 100) : 0) + "%";
      bar.appendChild(fill);
      b.appendChild(bar);
      b.appendChild(h("span", "tk-story-item-num", done + "/" + total));
      if (storyLocked(s)) {
        b.appendChild(h("span", "tk-story-item-lock", "前置未满足"));
      }
      host.appendChild(b);
    });
  }

  function storyNodes(story) {
    var out = [];
    (story.steps || []).forEach(function (st, i) {
      out.push({ kind: "step", order: st.order || (i + 1) * 10, step: st, idx: i });
    });
    (story.choices || []).forEach(function (c) {
      if (c.role === "prerequisite") { return; }
      out.push({ kind: "choice", order: c.order || 9000, choice: c });
    });
    (story.prerequisites || []).forEach(function (p) {
      out.push({ kind: "pre", order: 0, ref: p, pre: storyById(p.storyId) });
    });
    out.sort(function (a, b) {
      if (a.order !== b.order) { return a.order - b.order; }
      return a.kind === "pre" ? -1 : 1;
    });
    return out;
  }

  function storyStepStatus(story, idx) {
    if (storyStepDone(story.id, story.steps[idx].id)) { return "done"; }
    return storyMissingPrereqs(story, idx).length ? "locked" : "avail";
  }

  function renderStoryMain() {
    var host = state.el.storyMain;
    if (!host) { return; }
    host.textContent = "";

    if (!state.storyReady) {
      host.appendChild(h("div", "tk-story-placeholder", state.storyError
        ? "剧情数据加载失败：" + state.storyError
        : "正在加载剧情数据…"));
      return;
    }

    if (state.missingStory) {
      var warn = h("div", "tk-story-warn");
      warn.appendChild(h("strong", null, "未找到剧情线 " + state.missingStory));
      warn.appendChild(h("p", null, "该 ID 不在 data/stories.json 中，可能是尚未收录的剧情或链接已失效。"));
      host.appendChild(warn);
    }

    var story = storyById(state.storySelected);
    if (!story) {
      var empty = h("div", "tk-story-placeholder");
      empty.appendChild(h("strong", null, "从左侧选择一条剧情线"));
      empty.appendChild(h("p", null, "剧情树会展示步骤、必要前置与分支结局；进度按游戏模式分别保存。"));
      host.appendChild(empty);
      var gaps0 = storyGapsNode();
      if (gaps0) { host.appendChild(gaps0); }
      return;
    }

    // ---- 头部
    var head = h("header", "tk-story-head");
    var title = h("div", "tk-story-title");
    title.appendChild(h("h3", null, story.nameZh || story.nameEn || story.id));
    if (story.nameEn && story.nameEn !== story.nameZh) {
      title.appendChild(h("span", "tk-story-en", story.nameEn));
    }
    head.appendChild(title);

    var meta = h("div", "tk-story-head-meta");
    storyMapChips(meta, story.maps);
    if (story.storyKey) { meta.appendChild(h("code", "tk-story-key", story.storyKey)); }
    if (story.pointCount) { meta.appendChild(h("span", "tk-story-stat", "地图剧情点 " + story.pointCount + " 处")); }
    head.appendChild(meta);

    var total = (story.steps || []).length;
    var done = storyDoneCount(story);
    var prog = h("div", "tk-story-head-prog");
    var pbar = h("span", "tk-story-prog-bar");
    var pfill = h("span", "tk-story-prog-fill");
    pfill.style.width = (total ? Math.round(done / total * 100) : 0) + "%";
    pbar.appendChild(pfill);
    prog.appendChild(pbar);
    prog.appendChild(h("span", "tk-story-prog-text", storyStatusText(storyStatus(story)) + " · " + done + "/" + total + " 步"));
    head.appendChild(prog);
    host.appendChild(head);

    // ---- 前置剧情
    if ((story.prerequisites || []).length) {
      var preBox = h("div", "tk-story-pres");
      (story.prerequisites || []).forEach(function (p) {
        var pre = storyById(p.storyId);
        var row = h("div", "tk-story-pre");
        if (!pre) {
          row.appendChild(h("span", "tk-story-pre-text", "前置剧情数据缺失：" + p.storyId));
        } else {
          var ok = storyStatus(pre) === "done" || !!storyChoiceValue(pre.id, p.choiceKey);
          row.appendChild(h("span", "tk-story-pre-badge" + (ok ? " is-ok" : ""), ok ? "前置已满足" : "需要前置"));
          row.appendChild(h("span", "tk-story-pre-text", "《" + (pre.nameZh || pre.id) + "》中的抉择 " + p.choiceKey));
          var go = h("button", "tk-story-pre-go", "查看前置剧情");
          go.type = "button";
          go.dataset.storyOpen = pre.id;
          row.appendChild(go);
        }
        preBox.appendChild(row);
      });
      host.appendChild(preBox);
    }

    // ---- 剧情树
    var treeHost = h("div", "tk-story-tree");
    var nodes = storyNodes(story);
    var expanded = !!state.storyExpand[story.id];
    var shown = 0;
    nodes.forEach(function (n) {
      if (n.kind !== "step" && n.kind !== "choice" && n.kind !== "pre") { return; }
      if (n.kind === "step" && !expanded && n.idx >= STORY_STEP_LIMIT) { return; }
      var node = null;
      if (n.kind === "step") { node = renderStoryStep(story, n.step, n.idx); }
      else if (n.kind === "choice") { node = renderStoryChoice(story, n.choice); }
      else { node = renderStoryPre(n.ref, n.pre); }
      if (node) { treeHost.appendChild(node); shown++; }
    });
    if (!shown) {
      treeHost.appendChild(h("div", "tk-story-empty", "这条剧情线暂无可展示的步骤（数据缺口，见下方说明）"));
    }
    host.appendChild(treeHost);

    // ---- 展开 / 收起
    if (total > STORY_STEP_LIMIT) {
      var exp = h("button", "tk-story-expand",
        expanded ? "收起（只显示前 " + STORY_STEP_LIMIT + " 步）" : "展开全部 " + total + " 步");
      exp.type = "button";
      exp.dataset.storyExpand = story.id;
      host.appendChild(exp);
    }

    var gaps = storyGapsNode();
    if (gaps) { host.appendChild(gaps); }

    // R217：剧情来源链接（数据来源：eftarkov 剧情页）已搬到顶部菜单「关于」，
    // 每条剧情的原文地址仍保留在 data/stories.json 的 sourcePage 字段里。
  }

  function renderStoryStep(story, st, idx) {
    var status = storyStepStatus(story, idx);
    var li = h("div", "tk-story-node is-" + status);
    li.dataset.storyNode = st.id;
    if (state.storyStep === st.id) { li.classList.add("is-focus"); }

    // R102：状态标记复用普通任务列表的 db4-tick / db4-tick-mark（18×18 方框 + 字符），
    // 不再用自制圆点。三态语义映射：已完成→completed（✓，绿框绿底）、
    // 可前往→active（◐，白框）、未解锁→none（空框）；与任务列表完全一致。
    var tick = h("button", "db4-tick");
    tick.type = "button";
    tick.dataset.storyStepToggle = st.id;
    tick.title = status === "done" ? "已完成 · 点击撤销" : "标记为已完成";
    tick.appendChild(h("span", "db4-tick-mark",
      status === "done" ? "✓" : (status === "avail" ? "◐" : "")));
    li.appendChild(tick);

    var card = h("div", "tk-story-card");
    var top = h("div", "tk-story-card-top");
    top.appendChild(h("span", "tk-story-idx", "#" + (idx + 1)));
    top.appendChild(h("span", "tk-story-name", st.name || st.id));
    top.appendChild(h("span", "tk-story-badge is-" + status,
      status === "done" ? "已完成" : (status === "avail" ? "可进行" : "未解锁")));
    card.appendChild(top);

    var meta = h("div", "tk-story-card-meta");
    if ((st.maps || []).length) { storyMapChips(meta, st.maps); }
    if (st.points) { meta.appendChild(h("span", "tk-story-stat", "地图点 " + st.points + " 处")); }
    if (!(st.maps || []).length) { meta.appendChild(h("span", "tk-story-stat is-muted", "无地图点位")); }
    meta.appendChild(h("code", "tk-story-oid", st.id));
    card.appendChild(meta);

    var act = h("div", "tk-story-card-actions");
    var tgl = h("button", "tk-story-check" + (status === "done" ? " is-on" : ""),
      status === "done" ? "已完成（点击撤销）" : "标记完成");
    tgl.type = "button";
    tgl.dataset.storyStepToggle = st.id;
    act.appendChild(tgl);
    card.appendChild(act);

    li.appendChild(card);
    return li;
  }

  function renderStoryChoice(story, c) {
    var li = h("div", "tk-story-node is-choice" + (c.role === "ending" ? " is-ending" : ""));
    li.appendChild(h("span", "tk-story-dot is-choice", c.role === "ending" ? "★" : "⑂"));
    var card = h("div", "tk-story-card tk-story-choice-card");
    var top = h("div", "tk-story-card-top");
    top.appendChild(h("span", "tk-story-name", c.title || "抉择"));
    if (c.role === "ending") { top.appendChild(h("span", "tk-story-badge is-ending", "结局分支")); }
    card.appendChild(top);
    if (c.desc) { card.appendChild(h("div", "tk-story-choice-desc", c.desc)); }

    var opts = h("div", "tk-story-opts");
    var selected = storyChoiceValue(story.id, c.key);
    (c.options || []).forEach(function (o) {
      var ob = h("button", "tk-story-opt" + (selected === o.value ? " is-on" : ""));
      ob.type = "button";
      ob.dataset.storyChoice = c.key;
      ob.dataset.storyValue = o.value;
      var nm = h("span", "tk-story-opt-name", o.name);
      ob.appendChild(nm);
      if (c.role === "ending") { ob.appendChild(h("span", "tk-story-ending-tag", "结局")); }
      if (o.desc) {
        ob.appendChild(h("span", "tk-story-opt-desc", o.desc));
        ob.setAttribute("title", o.desc);
      }
      opts.appendChild(ob);
    });
    card.appendChild(opts);
    if (selected) {
      card.appendChild(h("div", "tk-story-choice-sel", "已选择：" + selected));
    }
    li.appendChild(card);
    return li;
  }

  function renderStoryPre(ref, pre) {
    var li = h("div", "tk-story-node is-pre");
    li.appendChild(h("span", "tk-story-dot is-pre", "↩"));
    var card = h("div", "tk-story-card tk-story-pre-card");
    if (!pre) {
      card.appendChild(h("div", "tk-story-name", "前置剧情缺失：" + ref.storyId));
      card.appendChild(h("div", "tk-story-card-meta",
        "需要先在其它剧情中做出抉择 " + ref.choiceKey + "，但该剧情未收录。"));
    } else {
      var ok = storyStatus(pre) === "done" || !!storyChoiceValue(pre.id, ref.choiceKey);
      card.appendChild(h("div", "tk-story-name", "前置：《" + (pre.nameZh || pre.id) + "》"));
      card.appendChild(h("div", "tk-story-card-meta",
        (ok ? "已满足" : "未满足") + " · 抉择 " + ref.choiceKey + "（可选 " + (ref.options || []).join(" / ") + "）"));
      var go = h("button", "tk-story-pre-go", "打开这条剧情");
      go.type = "button";
      go.dataset.storyOpen = pre.id;
      card.appendChild(go);
    }
    li.appendChild(card);
    return li;
  }

  function renderStory() {
    if (!state.el.storyMain) { return; }
    STORY_FILTERS.forEach(function (f) {
      var b = $('[data-story-filter="' + f.key + '"]', state.el.root);
      if (b) { b.classList.toggle("is-on", state.storyFilter === f.key); }
    });
    if (state.el.storySearch && state.el.storySearch.value !== state.storySearch) {
      state.el.storySearch.value = state.storySearch;
    }
    renderStoryStats();
    renderStoryList();
    renderStoryMain();
  }

  // ---------------------------------------------------------------- 对外接口
  var API = {
    mount: mount,
    open: open,
    setMode: setMode,
    setView: setView,
    openTask: openTask,
    // R86：剧情系统对外接口（地图深链 / 验收脚本共用）
    openStory: openStory,
    stories: function () { return state.storyDoc ? JSON.parse(JSON.stringify(state.storyDoc)) : null; },
    storyStatus: function (id) { var s = storyById(id); return s ? storyStatus(s) : null; },
    storyProgress: function () { return JSON.parse(JSON.stringify(state.storyProgress)); },
    status: function (id) { return statusOf(id); },
    setStatus: function (id, st) { setStatus(id, st); renderAll(); },   // 编程接口：直写不弹窗
    requestStatusChange: requestStatusChange,
    planPrereqFix: planPrereqFix,
    planFollowUpReset: planFollowUpReset,
    applyStatusBatch: applyStatusBatch,
    progress: function () { return JSON.parse(JSON.stringify(state.progress)); },
    progressCount: progressCount,
    exportProgress: exportProgress,
    importProgress: function (text) { var m = importProgress(text); renderAll(); return m; },
    modes: function () { return MODES.map(function (m) { return { key: m.key, label: m.label, full: m.full }; }); },
    mode: function () { return state.mode; },
    /** 模式覆盖情况：任务数/目标数/关系边/赛季专属/缓存是否就绪（供验收脚本与测试断言） */
    modeInfo: function (key) {
      var pack = state.cache[key || state.mode];
      if (!pack) { return null; }
      var c = pack.meta.counts || {};
      return {
        mode: key || state.mode,
        label: pack.meta.modeLabel,
        upstream: pack.meta.upstreamGameMode,
        tasks: c.tasks || 0,
        objectives: c.objectives || 0,
        edges: c.edges || 0,
        seasonOnly: c.seasonOnly || 0,
        cross: pack.meta.cross || {},
        loaded: true
      };
    },
    season: function () { return state.season; },
    coverage: function () {
      var withGuide = 0, curated = 0, missing = 0;
      state.order.forEach(function (id) {
        var g = state.guides[id] || {};
        if (g.status === "curated") { curated++; withGuide++; }
        else if (g.status === "generated") { withGuide++; }
        else { missing++; }
      });
      return { tasks: state.order.length, guides: withGuide, curated: curated, guideMissing: missing,
               traders: Object.keys(state.traders).length, mode: state.mode };
    },
    state: state
  };
  window.GWTasks = API;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      if (document.getElementById("task-view")) { mount(); }
    });
  } else if (document.getElementById("task-view")) {
    mount();
  }
})();
