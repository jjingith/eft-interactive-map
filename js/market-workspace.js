/* R286 市场工作区子页切换（市场列表 / 市场大盘）
 *
 * 只做一件事：在 #market-view 内切换两个 pane，并通知对应的模块挂载 / 刷新。
 * 不新建数据层、不改全局视图体系；「市场」仍是唯一的顶层工作区。
 */
(function () {
  "use strict";

  var LS_TAB = "eftmap.market.tab.v1";
  var TABS = ["list", "board"];
  var current = "list";
  var inited = false;

  function qsa(sel) { return document.querySelectorAll(sel); }

  function savedTab() {
    try {
      var value = localStorage.getItem(LS_TAB);
      return TABS.indexOf(value) >= 0 ? value : "list";
    } catch (e) {
      return "list";
    }
  }

  function mountList() {
    if (window.GWMarket && typeof window.GWMarket.mount === "function") {
      window.GWMarket.mount();
      window.GWMarket.open();
    }
  }

  function mountBoard() {
    if (window.GWMarketBoard && typeof window.GWMarketBoard.mount === "function") {
      window.GWMarketBoard.mount();
      window.GWMarketBoard.open();
    }
  }

  function show(name, persist, silent) {
    var target = TABS.indexOf(name) >= 0 ? name : "list";
    current = target;
    var tabs = qsa("[data-market-tab]");
    for (var i = 0; i < tabs.length; i++) {
      var isOn = tabs[i].getAttribute("data-market-tab") === target;
      tabs[i].classList.toggle("is-active", isOn);
      tabs[i].setAttribute("aria-selected", String(isOn));
    }
    var listPane = document.getElementById("market-list-pane");
    var boardPane = document.getElementById("market-board-pane");
    if (listPane) { listPane.hidden = target !== "list"; }
    if (boardPane) { boardPane.hidden = target !== "board"; }
    // silent：只摆 DOM 显隐，不触发模块挂载（页面初始化时市场视图可能还没打开）。
    if (!silent) {
      if (target === "board") { mountBoard(); } else { mountList(); }
    }
    if (persist !== false) {
      try { localStorage.setItem(LS_TAB, target); } catch (e) { /* 无痕模式忽略 */ }
    }
  }

  function open(name) {
    if (name === "list" || name === "board") { show(name); return; }
    show(savedTab(), false);
  }

  function init() {
    if (inited) { return; }
    inited = true;
    var tabs = qsa("[data-market-tab]");
    for (var i = 0; i < tabs.length; i++) {
      (function (tab) {
        tab.addEventListener("click", function () {
          show(tab.getAttribute("data-market-tab"));
        });
        tab.addEventListener("keydown", function (ev) {
          if (ev.key !== "ArrowLeft" && ev.key !== "ArrowRight") { return; }
          ev.preventDefault();
          var order = ["list", "board"];
          var index = order.indexOf(current);
          var next = order[(index + (ev.key === "ArrowRight" ? 1 : -1) + order.length) % order.length];
          show(next);
          var btn = document.querySelector('[data-market-tab="' + next + '"]');
          if (btn && btn.focus) { btn.focus(); }
        });
      })(tabs[i]);
    }
    // 不在 setView 里重复挂载；这里只恢复上次的子页（列表默认）。
    show(savedTab(), false, true);
  }

  window.GWMarketWorkspace = { open: open, show: show, current: function () { return current; } };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
