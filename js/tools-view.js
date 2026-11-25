/* ============================================================================
 * tools-view.js —— R307「小工具」视图
 *
 * 结构与「地图 / 配装」同级的一级视图：左栏工具列表，右栏该工具的设置。
 * 现在有两项（小地图浮窗 / 价格识别），以后加工具只要在 index.html 里补一个
 * `.tl-item[data-tool=xxx]` 和一个 `.tl-pane[data-tool-pane=xxx]`，本模块自动接管。
 *
 * 对外接口（window.GWTools）：
 *   mount()        建绑定（懒挂载，首次进入视图时调用）
 *   open()         进入视图
 *   select(key)    切到某个工具（供深链 / 外部调用）
 * ==========================================================================*/
(function () {
  "use strict";

  var root = null;
  var mounted = false;
  var current = "mini";

  function items() {
    return root ? [].slice.call(root.querySelectorAll(".tl-item")) : [];
  }

  function panes() {
    return root ? [].slice.call(root.querySelectorAll(".tl-pane")) : [];
  }

  function select(key) {
    if (!root || !key) { return; }
    var found = false;
    panes().forEach(function (pane) {
      var on = pane.getAttribute("data-tool-pane") === key;
      if (on) { found = true; }
      pane.hidden = !on;
    });
    if (!found) { return; }
    current = key;
    try { localStorage.setItem("eftmap.tools", key); } catch (e) { /* 隐私模式忽略 */ }
    items().forEach(function (item) {
      var on = item.getAttribute("data-tool") === key;
      item.classList.toggle("is-active", on);
      item.setAttribute("aria-selected", on ? "true" : "false");
    });
  }

  function mount() {
    if (mounted) { return; }
    root = document.getElementById("tools-view");
    if (!root) { return; }

    items().forEach(function (item) {
      item.addEventListener("click", function () {
        select(item.getAttribute("data-tool"));
      });
      // 上下键在列表内移动（与顶栏视图标签的键盘行为一致）
      item.addEventListener("keydown", function (ev) {
        var step = ev.key === "ArrowDown" ? 1 : (ev.key === "ArrowUp" ? -1 : 0);
        if (!step) { return; }
        ev.preventDefault();
        var list = items();
        var index = list.indexOf(item);
        var next = list[(index + step + list.length) % list.length];
        if (!next) { return; }
        select(next.getAttribute("data-tool"));
        next.focus();
      });
    });

    mounted = true;
    // 默认回到上次选中的工具（记在 localStorage，跨重启保持）
    var saved = null;
    try { saved = localStorage.getItem("eftmap.tools"); } catch (e) { /* 隐私模式忽略 */ }
    select(saved || current);
  }

  window.GWTools = {
    mount: mount,
    open: function () {
      mount();
      select(current);
    },
    select: function (key) { mount(); select(key); }
  };
})();
