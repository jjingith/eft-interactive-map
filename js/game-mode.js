/* ============================================================================
 * game-mode.js —— 全局游戏模式（R19.27）
 *
 * 唯一职责：PvP / PvE / PvPS（赛季服）的「当前模式」状态 + 右上角常驻切换控件。
 *   · 状态只有一个：window.GWGameMode.get()，全应用（地图/配装/配枪/弹药/任务）读同一份
 *   · 持久化：localStorage「eftmap.gameMode」，只接受合法 key，非法/缺失回退默认
 *   · 切换：set(key) → 落盘 → 通知所有订阅者（任务模块据此换数据，其它模块按需响应）
 *   · UI：挂在全局页头 #game-mode-bar（不随页面切换消失，不被工具栏挤走）
 *
 * 页面自己的搜索/筛选/缩放/选中仍由各模块保存；本模块**不**保存任何页面局部状态。
 * ==========================================================================*/
(function () {
  "use strict";

  var LS_KEY = "eftmap.gameMode";

  var MODES = [
    { key: "regular", label: "PvP", full: "PvP（常规）", en: "PVP · Regular PvP character",
      note: "普通 PvP 模式角色与任务线。" },
    { key: "pve", label: "PvE", full: "PvE", en: "PVE · Player vs Environment character",
      note: "PvE 模式角色：无玩家互相对抗，任务条件与 PvP 存在差异。" },
    { key: "pvps", label: "PvPS", full: "PvPS（赛季服）",
      en: "PVP SEASONAL · PvP Seasonal character",
      note: "PvP 赛季服（Seasonal）：独立角色、独立进度，任务集来自上游 pvp-season 端点。" }
  ];
  var KEYS = MODES.map(function (m) { return m.key; });
  var BY = {};
  MODES.forEach(function (m) { BY[m.key] = m; });

  var current = "regular";
  var listeners = [];
  var mounted = false;

  function valid(key) {
    return KEYS.indexOf(key) >= 0 ? key : null;
  }

  /** 读取持久化的模式：非法值一律回退默认 regular（不抛错、不静默改写存储）。 */
  function readStored() {
    try {
      var raw = localStorage.getItem(LS_KEY);
      return valid(raw);
    } catch (e) { return null; }
  }

  function persist(key) {
    try {
      localStorage.setItem(LS_KEY, key);
      return true;
    } catch (e) {
      // 隐私模式等写入失败：内存里仍然是新模式，只是下次打开会回退默认
      return false;
    }
  }

  /** R260：把当前模式同步到本地服务配置，截图识别（scan.py）按它取价——
   *  页面右上角选 PvE，截图识别也用 PvE。服务未起 / 静态打开时静默失败。 */
  function pushMode(key) {
    try {
      if (typeof fetch !== "function") { return; }
      fetch("api/prefs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ dataScope: { mode: key } })
      }).catch(function () {});
    } catch (e) { /* 忽略 */ }
  }

  function notify(fromUser) {
    listeners.slice().forEach(function (fn) {
      try { fn(current, { fromUser: !!fromUser }); } catch (e) {
        if (window.console && console.warn) { console.warn("[GWGameMode] listener error", e); }
      }
    });
  }

  function syncButtons() {
    if (!mounted) { return; }
    var bar = document.getElementById("game-mode-bar");
    if (!bar) { return; }
    var btns = bar.querySelectorAll("[data-tkmode]");
    for (var i = 0; i < btns.length; i++) {
      var on = btns[i].dataset.tkmode === current;
      btns[i].setAttribute("aria-selected", String(on));
      btns[i].classList.toggle("is-on", on);
    }
    bar.setAttribute("data-mode", current);
    var lbl = document.getElementById("game-mode-label");
    if (lbl) {
      lbl.textContent = "模式：" + (BY[current] || {}).full;
      lbl.title = (BY[current] || {}).en || "";
    }
  }

  /** 切换模式。key 非法返回 false；重复设置同一模式是幂等的（不重复通知）。 */
  function set(key, fromUser) {
    var k = valid(key);
    if (!k) { return false; }
    if (k === current && fromUser !== "force") {
      syncButtons();
      return true;
    }
    current = k;
    persist(k);
    pushMode(k);          // R260：同步到服务端配置，截图识别跟随
    syncButtons();
    notify(fromUser === true || fromUser === "force");
    return true;
  }

  /** 把控件渲染进全局页头（幂等）。 */
  function mount() {
    var host = document.getElementById("game-mode-bar");
    if (!host) {
      // 页头还没有挂点：延迟到 DOM 就绪再试一次（脚本可能先于 HTML 被解析）
      if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", mount, { once: true });
      }
      return;
    }
    if (mounted && host.getAttribute("data-gm-built") === "1") {
      syncButtons();
      return;
    }
    host.innerHTML = "";
    host.className = "game-mode-bar tk-modebar";   // tk-modebar：沿用既有验收选择器
    host.id = "game-mode-bar";
    host.setAttribute("role", "tablist");
    host.setAttribute("aria-label", "游戏模式");
    host.setAttribute("data-gm-built", "1");

    MODES.forEach(function (m) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "gm-btn tk-mode";
      b.dataset.tkmode = m.key;
      b.setAttribute("role", "tab");
      b.setAttribute("aria-label", m.full);
      b.setAttribute("title", m.en);
      b.setAttribute("data-en-text", m.en);
      b.textContent = m.label;
      b.addEventListener("click", function () { set(m.key, true); });
      host.appendChild(b);
    });

    var lbl = document.createElement("span");
    lbl.id = "game-mode-label";
    lbl.className = "gm-label";
    host.appendChild(lbl);

    mounted = true;
    // 初始值：存储 → 合法则用存储值；否则默认 regular
    var saved = readStored();
    if (saved && saved !== current) { current = saved; }
    syncButtons();
  }

  /** R308：localStorage 没有值时（壳清缓存 / 换 profile / 首次启动），回读服务端
      配置里的 dataScope.mode——否则每次启动都会用默认 PvP 把已保存的模式覆盖掉。 */
  function restoreFromServer() {
    var done = false;
    var fallback = function () {
      if (done) { return; }
      done = true;
      pushMode(current);
    };
    try {
      if (typeof fetch !== "function") { fallback(); return; }
      fetch("api/config", { cache: "no-store" }).then(function (r) {
        return r.ok ? r.json() : null;
      }).then(function (p) {
        if (done) { return; }
        var key = p && p.config && p.config.dataScope && p.config.dataScope.mode;
        if (valid(key)) {
          done = true;
          set(key, "server");   // 落 localStorage + 通知订阅者；set 内部会 pushMode
        } else {
          fallback();
        }
      }).catch(fallback);
    } catch (e) {
      fallback();
    }
  }

  // 启动即读存储（不等 mount，任务模块可能先问模式）
  // R308：没有本地存储时先问服务端，避免默认 PvP 覆盖上次保存的模式。
  (function () {
    var saved = readStored();
    if (saved) {
      current = saved;
      pushMode(current);    // 页面一打开就把当前模式同步给截图识别
    } else {
      restoreFromServer();
    }
  })();

  window.GWGameMode = {
    version: "1.0",
    MODES: MODES,
    keys: function () { return KEYS.slice(); },
    get: function () { return current; },
    key: function () { return current; },
    info: function (key) { return BY[key || current] || null; },
    is: function (key) { return current === key; },
    set: set,
    mount: mount,
    /** 订阅模式变化（返回退订函数）。fn(key, {fromUser}) */
    onChange: function (fn) {
      if (typeof fn !== "function") { return function () {}; }
      listeners.push(fn);
      return function () {
        var i = listeners.indexOf(fn);
        if (i >= 0) { listeners.splice(i, 1); }
      };
    },
    /** 仅供测试/验收：重置为默认（不通知） */
    reset: function () { current = "regular"; persist("regular"); syncButtons(); }
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mount);
  } else {
    mount();
  }
})();
