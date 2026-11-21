/* js/app-menubar.js —— R80 顶部菜单栏（Adobe 式层级第 1 层）
 *
 * 只负责新增的 #app-menubar：
 *   · 文件 / 视图 / 工具 / 帮助 的打开、收起、悬停高亮（样式在 xp-ui-app.css）、点项执行、
 *     点外收起、Esc 收起、上下方向键在菜单项里走、左右方向键在顶层菜单间走；
 *   · 把原有的模式条 / 账号版本 / 运行版本迁进右侧，把设置 / 关于 / 战局 / 保存配置 / 个人属性
 *     的原按钮与面板放进隐藏锚点：id 与 app.js 既有绑定全部保留，只换位置；
 *   · 账号版本入口的文案跟随 GWDataScope（白边 / 黑边 / 蓝边…）显示当前版本。
 *
 * 硬约束：?mini=1 时整段跳过（连 DOM 都不迁），小地图路径完全不受影响。
 * ==========================================================================*/
(function () {
  "use strict";

  var isMini = false;
  try {
    isMini = /(?:^|[?&])mini=(?:1|true)?(?:&|$|=)/.test(location.search);
  } catch (e) { isMini = false; }
  if (isMini) { return; }

  function ready(fn) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", fn);
    } else {
      fn();
    }
  }

  ready(function () {
    // 双保险：app.js 的 boot 可能已经挂上 tk-mini（监听顺序在它之后）
    if (document.body.classList.contains("tk-mini") ||
        document.documentElement.classList.contains("tk-mini-root")) { return; }

    var bar = document.getElementById("app-menubar");
    if (!bar) { return; }

    relocate();
    relocateContext();
    bindViewToolbar();
    bindMenus(bar);
    bindAppMenu();
    bindMapTools();
    bindLayerQuick();
    bindEditionLabel();
    bindStatusBar();
  });

  // ---------------------------------------------------------------- 主工具条键盘
  /* 点击仍走 app.js 绑定的 setView；这里只补组内方向键（Enter / Space 由原生按钮触发 click）。
     工具条在 ?mini=1 时随 #menubar 一起隐藏，mini 下本文件整体不执行。 */
  function bindViewToolbar() {
    var tools = document.getElementById("view-switch");
    if (!tools) { return; }
    tools.addEventListener("keydown", function (ev) {
      var btn = ev.target && ev.target.closest ? ev.target.closest(".view-btn") : null;
      if (!btn || !tools.contains(btn)) { return; }
      var group = btn.closest(".vt-group") || tools;
      var list = [].slice.call(group.querySelectorAll(".view-btn"));
      var i = list.indexOf(btn);
      var next = -1;
      if (ev.key === "ArrowRight" || ev.key === "ArrowDown") {
        next = (i + 1) % list.length;
      } else if (ev.key === "ArrowLeft" || ev.key === "ArrowUp") {
        next = (i - 1 + list.length) % list.length;
      } else if (ev.key === "Home") {
        next = 0;
      } else if (ev.key === "End") {
        next = list.length - 1;
      }
      if (next < 0 || next === i) { return; }
      ev.preventDefault();
      list[next].focus();
    });
  }

  // ---------------------------------------------------------------- 元素迁移
  /* 只换位置，不重建：所有 id / 监听 / aria 原样保留，app.js 的菜单绑定继续生效。 */
  function relocate() {
    var right = document.getElementById("app-menubar-right");
    if (!right) { return; }

    // 工作区是高频主导航：放在应用菜单之前，也让键盘焦点顺序与视觉顺序一致。
    var menus = document.getElementById("app-menus");
    var workspace = document.getElementById("view-switch");
    if (menus && workspace && menus.parentNode === right.parentNode) {
      menus.parentNode.insertBefore(workspace, menus);
    }

    // R87：账号版本入口在模式条左侧，与 PvP / PvE / PvPS 选择栏同排（DOM 顺序同步，
    //否则 CSS order 虽能改视觉，Tab 焦点顺序会倒着走）。
    var account = document.getElementById("menu-account");
    var accountWrap = account && account.closest ? account.closest(".menu-wrap") : null;
    if (accountWrap) {
      accountWrap.classList.add("app-account-wrap");
      account.classList.add("app-account-btn");
      right.appendChild(accountWrap);
    }

    // 模式 + 价格来源徽标（整组一起迁，窄屏换行逻辑不受影响）
    var modeBar = document.getElementById("game-mode-bar");
    var scope = modeBar && modeBar.closest ? modeBar.closest(".scope-cluster") : null;
    if (scope) { right.appendChild(scope); }

    // 运行版本徽标
    var rev = document.getElementById("build-rev");
    if (rev) { right.appendChild(rev); }

    // 隐藏锚点：原有面板挂在这里（样式里用 position:fixed 贴到菜单栏下方）
    var anchors = document.createElement("div");
    anchors.className = "app-panel-anchors";
    right.appendChild(anchors);

    ["menu-raid", "menu-about"].forEach(function (id) {
      var btn = document.getElementById(id);
      if (!btn) { return; }
      var wrap = btn.closest ? btn.closest(".menu-wrap") : null;
      if (wrap) { anchors.appendChild(wrap); }
      btn.hidden = true;
      btn.setAttribute("tabindex", "-1");
      btn.setAttribute("aria-hidden", "true");
    });

    var save = document.getElementById("save-config");
    if (save) {
      save.hidden = true;
      save.setAttribute("tabindex", "-1");
      anchors.appendChild(save);
    }

    var prof = document.getElementById("btn-profile");
    if (prof) {
      prof.hidden = true;
      prof.setAttribute("tabindex", "-1");
      anchors.appendChild(prof);
    }
  }

  // ---------------------------------------------------------------- 上下文栏（R82）
  /* 第三行随视图切换。做法同菜单栏：只把**现有控件节点**换父级，不复制、不重建，
     所以 id / 事件绑定 / 当前值（选档、下拉、搜索词）全部沿用；切视图时只切显示哪一个槽。
     迁不动的（弹药口径分组树、地图图层树、地图 HUD 浮层）留在原位，见交付说明。 */
  function relocateContext() {
    var bar = document.getElementById("context-bar");
    if (!bar) { return; }

    function pane(view) { return document.getElementById("cb-" + view); }
    function mk(tag, cls) {
      var el = document.createElement(tag);
      if (cls) { el.className = cls; }
      return el;
    }
    // 一个分组：可选小标题 + 一串被迁入的节点；空分组不落地
    function group(target, labelText, nodes) {
      if (!target || !nodes || !nodes.length) { return null; }
      var g = mk("span", "cb-group");
      if (labelText) {
        var lb = mk("span", "cb-label");
        lb.textContent = labelText;
        g.appendChild(lb);
      }
      nodes.forEach(function (n) { if (n) { g.appendChild(n); } });
      if (!g.children.length) { return null; }
      target.appendChild(g);
      return g;
    }
    function sep(target) {
      if (!target || !target.children.length) { return; }
      target.appendChild(mk("span", "cb-sep"));
    }

    // ---- 地图：第一阶段已把「地图」块直接放进 #cb-map，
    // 不再从左侧栏迁移；工具栏顺序在 HTML 里固定为「地图 → 楼层 → 定位 → 复位 → 显示」。

    // ---- 任务：搜索 + 商人 / 状态 / 地图三档筛选（子页导航已在页头标题行，不迁）
    var tkPane = pane("tasks");
    var tkSearch = document.getElementById("tk-search");
    if (tkPane && tkSearch) {
      tkSearch.classList.add("cb-input");
      group(tkPane, null, [tkSearch]);
      sep(tkPane);
      ["tk-trader", "tk-status", "tk-map"].forEach(function (id) {
        var sel = document.getElementById(id);
        var wrap = sel && sel.closest ? sel.closest(".tk-sel") : null;
        if (wrap) { tkPane.appendChild(wrap); }
      });
    }

    // ---- 弹药：搜索 + 价格口径（含 RESET）+ 单位
    var amPane = pane("ammo");
    var amSearch = document.getElementById("am-search");
    var amHead = document.querySelector(".am-side .am-side-head");
    var amPrice = document.getElementById("am-price-mode");
    var amUnits = document.getElementById("am-units");
    if (amPane && amSearch) {
      amSearch.classList.add("cb-input");
      group(amPane, null, [amSearch]);
      sep(amPane);
      if (amHead) { group(amPane, null, [amHead, amPrice]); }
      if (amUnits) {
        var unitH3 = amUnits.previousElementSibling;
        group(amPane, null, [unitH3 && unitH3.tagName === "H3" ? unitH3 : null, amUnits]);
      }
    }

    // ---- 配枪：基础枪械搜索（已在 #cb-gun 的 HTML 里）+ 类别 / 射击模式 / 预设链接
    var gwPane = pane("gun");
    var gwSearch = document.getElementById("gw-search");
    if (gwPane && gwSearch) {
      sep(gwPane);
      var kind = document.getElementById("gw-kindchips");
      if (kind) { gwPane.appendChild(kind); }
      sep(gwPane);
      var fire = document.getElementById("gw-firechips");
      if (fire) { gwPane.appendChild(fire); }
      var presetLinks = document.getElementById("gw-preset-links");
      if (presetLinks) { gwPane.appendChild(presetLinks); }
    }

    // ---- 配装：浏览分类（7 类）+ 名称筛选
    var lwPane = pane("loadout");
    var lwCats = document.getElementById("lw-cats");
    var lwSearch = document.getElementById("lw-search");
    if (lwPane && lwCats) {
      lwPane.appendChild(lwCats);
      sep(lwPane);
      if (lwSearch) { lwSearch.classList.add("cb-input"); lwPane.appendChild(lwSearch); }
    }

    // 空槽兜底：这一档没有任何可上提的控件时给一条占位（行高由 .context-bar 固定，不塌）
    [].forEach.call(bar.querySelectorAll(".cb-pane"), function (p) {
      if (!p.children.length) {
        var ph = mk("span", "cb-empty");
        ph.textContent = "此视图暂无可上提的操作项";
        p.appendChild(ph);
      }
    });

    syncContext();
  }

  /* 当前视图 → 只显示对应槽。复用 #view-switch 的 aria-selected（app.js setView 写的），
     不新造状态；菜单 / 工具条怎么切，这一行都跟着走。 */
  function syncContext() {
    var bar = document.getElementById("context-bar");
    var switcher = document.getElementById("view-switch");
    if (!bar || !switcher) { return; }
    var btn = switcher.querySelector('.view-btn[aria-selected="true"]');
    var cur = (btn && btn.getAttribute("data-view")) || "map";
    [].forEach.call(bar.querySelectorAll(".cb-pane"), function (p) {
      p.hidden = (p.getAttribute("data-view") !== cur);
    });
  }

  // ---------------------------------------------------------------- 底部状态栏（R83）
  /* 纯显示层：字段全部读现有状态（#view-switch / #map-list / GWGameMode / data/meta.json /
     #build-rev），不新造状态、不放操作。视图与模式变化各挂观察者，切换后立即同步。 */
  var VIEW_NAMES = { map: "地图", tasks: "任务", ammo: "弹药", gun: "配枪", loadout: "配装" };

  function bindStatusBar() {
    var bar = document.getElementById("app-statusbar");
    if (!bar) { return; }
    var switcher = document.getElementById("view-switch");
    var mapSel = document.getElementById("map-list");
    var revBadge = document.getElementById("build-rev");

    syncStatus();

    if (switcher) {
      new MutationObserver(syncStatus).observe(switcher, {
        subtree: true, attributeFilter: ["aria-selected"]
      });
    }
    if (mapSel) {
      mapSel.addEventListener("change", function () { setTimeout(syncStatus, 0); });
    }
    // 地图切换后 app.js 会改写地图区的状态行，跟着它同步最稳（也兜住非地图视图）
    var mapStatus = document.getElementById("status-map");
    if (mapStatus) {
      new MutationObserver(syncStatus).observe(mapStatus, {
        childList: true, characterData: true, subtree: true
      });
    }
    if (window.GWGameMode && typeof window.GWGameMode.onChange === "function") {
      window.GWGameMode.onChange(syncStatus);
    } else {
      var modeBar = document.getElementById("game-mode-bar");
      if (modeBar) {
        new MutationObserver(syncStatus).observe(modeBar, {
          subtree: true, attributeFilter: ["aria-selected", "class"]
        });
      }
    }
    if (revBadge) {
      // 构建号由页面内联脚本异步回填到 data-rev，这里只负责把它放进「关于」，不再上顶栏
      new MutationObserver(syncBuildRev).observe(revBadge, {
        attributes: true, attributeFilter: ["data-rev"]
      });
    }
    syncBuildRev();

    loadDataVersion();
    loadDataDate();
  }

  // ---------------------------------------------------------------- 数据版本（R301）
  /* 右上角 / 状态栏显示的都是「数据截止」，真值只认 data/meta.json 的 generatedAt
     —— 那是本项目主数据源 tarkov.dev 的快照生成时间，和界面里物品/任务/价格同源。
     旧版这里显示的是「游戏版本 X」，取自 data/game-truth/meta.json 的
     source.exe_version（**本机 EFT 客户端** exe 版本）—— 与 tarkov.dev 数据源无关，
     会让人误以为数据来自那个客户端版本。R301 起改为数据截止日期，不再冒充游戏版本。 */
  var dataDate = "";
  var dataDateTitle = "";
  var dataDateSeq = 0;   // 数据版本请求序号：只采纳最后一次请求的结果

  function setDataDate(v, title) {
    dataDate = v;
    dataDateTitle = title;
    var badge = document.getElementById("build-rev");
    if (badge) {
      badge.textContent = "数据截止 " + v;
      badge.setAttribute("title", title);
    }
    syncStatus();
  }

  function loadDataDate() {
    // 切换账号版本后重新取一次；只让最后一次请求落地，避免旧响应后到写回旧值。
    var seq = ++dataDateSeq;
    function fail() {
      if (seq !== dataDateSeq) { return; }
      var badge = document.getElementById("build-rev");
      if (badge) {
        badge.textContent = "数据截止 —";
        badge.setAttribute("title", "未读到 data/meta.json 的 generatedAt；构建版本见「关于」");
      }
      syncStatus();
    }
    function apply(j) {
      if (seq !== dataDateSeq) { return; }
      var raw = String((j && j.generatedAt) || "").trim();
      if (!raw) { throw new Error("no generatedAt"); }
      // generatedAt 形如 2026-11-15T13:01:30Z，界面只取日期部分
      var day = /^\d{4}-\d{2}-\d{2}/.test(raw) ? raw.slice(0, 10) : raw;
      setDataDate(day, "数据截止 " + day +
        " · 来源 data/meta.json 的 generatedAt（主数据源 tarkov.dev 快照生成时间）" +
        " · 完整时间戳 " + raw);
    }
    // 优先复用 app.js 已渲染到 #about-meta-line 的版本文案，避免重复请求
    var line = document.getElementById("about-meta-line");
    var m = line && /版本\s+(\S+)\s*·/.exec(line.textContent || "");
    if (m) { apply({ generatedAt: m[1] }); return; }
    fetch("data/meta.json", { cache: "no-store" }).then(function (r) {
      if (!r.ok) { throw new Error("HTTP " + r.status); }
      return r.json();
    }).then(apply).catch(fail);
  }

  /** 构建号只出现在「帮助 → 关于」，从内联脚本写的 data-rev 读取，不在顶栏显示。 */
  function syncBuildRev() {
    var badge = document.getElementById("build-rev");
    var rev = (badge && badge.getAttribute("data-rev")) ||
      document.documentElement.getAttribute("data-build-rev") || "";
    var line = document.getElementById("about-build-line");
    if (line && rev && rev !== "—") {
      line.textContent = "构建版本：" + rev + "（仅用于排查；右上角与状态栏显示数据截止日期）";
    }
  }

  /** 读 data/meta.json 拿数据版本（app.js 已渲染到 #about-meta-line 时直接复用，不再请求）。 */
  function loadDataVersion() {
    function setData(txt, ok) {
      var d = document.getElementById("sb-data");
      if (d) { d.textContent = txt; }
      var s = document.getElementById("sb-state");
      if (s) { s.textContent = ok ? "数据已加载" : "数据未就绪"; }
      syncStatus();
    }
    var line = document.getElementById("about-meta-line");
    var m = line && /版本\s+(\S+)\s*·/.exec(line.textContent || "");
    if (m) { setData("数据：" + m[1], true); return; }
    try {
      fetch("data/meta.json", { cache: "no-store" }).then(function (r) {
        if (!r.ok) { throw new Error("HTTP " + r.status); }
        return r.json();
      }).then(function (j) {
        var v = String(j.generatedAt || "—");
        var short = /^\d{4}-\d{2}-\d{2}/.test(v) ? v.slice(0, 10) : v;
        setData("数据：" + short + (j.schema != null ? " · schema " + j.schema : ""), true);
      }).catch(function () {
        setData("数据：—", false);
      });
    } catch (e) {
      setData("数据：—", false);
    }
  }

  /** 把当前状态写进状态栏，并把完整字段拼进整条 title（860 隐藏项的兜底）。 */
  function syncStatus() {
    var switcher = document.getElementById("view-switch");
    var btn = switcher && switcher.querySelector('.view-btn[aria-selected="true"]');
    var key = btn && btn.getAttribute("data-view");
    var viewText = VIEW_NAMES[key] || (btn && btn.textContent.trim()) || "地图";
    var viewEl = document.getElementById("sb-view");
    if (viewEl) { viewEl.textContent = "视图：" + viewText; }

    var mapText = "";
    var sel = document.getElementById("map-list");
    if (sel && sel.options && sel.selectedIndex >= 0) {
      mapText = (sel.options[sel.selectedIndex].textContent || "").split(" · ")[0].trim();
    }
    if (!mapText) {
      var sm = document.getElementById("status-map");
      mapText = sm ? (sm.textContent || "").split(" · ")[0].trim() : "";
    }
    if (mapText && mapText !== "加载中…") {
      var mapEl = document.getElementById("sb-map");
      if (mapEl) { mapEl.textContent = "地图：" + mapText; }
    }

    var mode = "";
    if (window.GWGameMode && typeof window.GWGameMode.get === "function") {
      var info = window.GWGameMode.info(window.GWGameMode.get());
      mode = (info && (info.label || info.full)) || "";
    }
    if (!mode) {
      var on = document.querySelector('.game-mode-bar .gm-btn[aria-selected="true"], .game-mode-bar .gm-btn.is-on');
      mode = on ? on.textContent.trim() : "";
    }
    var modeEl = document.getElementById("sb-mode");
    if (modeEl && mode) { modeEl.textContent = "模式：" + mode; }

    var revEl = document.getElementById("sb-rev");
    if (revEl) {
      if (dataDate) {
        revEl.textContent = "数据截止 " + dataDate;
        revEl.setAttribute("title", dataDateTitle);
      } else if (!/数据截止/.test(revEl.textContent || "")) {
        revEl.textContent = "数据截止 —";
      }
    }

    var bar = document.getElementById("app-statusbar");
    if (bar) {
      var stateEl = document.getElementById("sb-state");
      var dataEl = document.getElementById("sb-data");
      bar.setAttribute("title", [
        "视图：" + viewText,
        "地图：" + (mapText || "—"),
        dataEl ? dataEl.textContent.trim() : "",
        modeEl ? modeEl.textContent.trim() : "",
        stateEl ? stateEl.textContent.trim() : "",
        revEl ? revEl.textContent.trim() : ""
      ].filter(Boolean).join(" · "));
    }
  }

  // ---------------------------------------------------------------- 菜单交互
  function bindMenus(bar) {
    var menus = [].slice.call(bar.querySelectorAll(".app-menu")).filter(function (m) {
      // 第一阶段：「应用菜单」是包含滑块 / 复选框的设置弹层，走 bindAppMenu() 的专用事件；
      // 这里排除它，通用菜单的方向键 / Tab 逻辑不再接管。
      if (m.querySelector(".app-app-panel")) { return false; }
      return m.querySelector(".app-menu-btn") && m.querySelector(".app-menu-panel");
    });
    if (!menus.length) { return; }

    var openMenu = null;
    var statusEl = document.getElementById("app-menu-status");
    var statusTimer = 0;

    function btnOf(m) { return m.querySelector(".app-menu-btn"); }
    function panelOf(m) { return m.querySelector(".app-menu-panel"); }
    function itemsOf(m) {
      return [].slice.call(panelOf(m).querySelectorAll(".app-menu-item")).filter(function (it) {
        return !it.closest("[hidden]");
      });
    }

    /** 视图项打勾：跟 #view-switch 当前的 aria-selected 同步，不改状态本身。 */
    function renderChecks() {
      var sel = document.querySelector("#view-switch .view-btn[aria-selected='true']");
      var current = sel ? sel.getAttribute("data-view") : null;
      menus.forEach(function (m) {
        itemsOf(m).forEach(function (it) {
          var cmd = it.getAttribute("data-cmd") || "";
          var on = cmd.indexOf("view:") === 0 && cmd.slice(5) === current;
          it.classList.toggle("is-current", on);
          it.setAttribute("aria-checked", on ? "true" : "false");
        });
      });
    }

    function closeAll(focusBack) {
      var last = openMenu;
      menus.forEach(function (m) {
        btnOf(m).classList.remove("open");
        btnOf(m).setAttribute("aria-expanded", "false");
        panelOf(m).hidden = true;
      });
      openMenu = null;
      if (focusBack && last) { btnOf(last).focus(); }
    }

    function openTo(m, focusFirst) {
      if (!m) { return; }
      closeAll(false);
      openMenu = m;
      btnOf(m).classList.add("open");
      btnOf(m).setAttribute("aria-expanded", "true");
      panelOf(m).hidden = false;
      renderChecks();
      if (focusFirst) {
        var list = itemsOf(m);
        if (list.length) { list[0].focus(); }
      }
    }

    function toggle(m) {
      if (openMenu === m) { closeAll(true); } else { openTo(m, false); }
    }

    function flash(text) {
      if (!statusEl) { return; }
      statusEl.textContent = text;
      statusEl.hidden = false;
      if (statusTimer) { clearTimeout(statusTimer); }
      statusTimer = setTimeout(function () { statusEl.hidden = true; }, 1800);
    }

    /** 执行菜单项：全部落到既有按钮上，菜单本身只当入口，不复制业务逻辑。 */
    function run(item) {
      var cmd = item.getAttribute("data-cmd") || "";
      var pane = item.getAttribute("data-panel") || "";
      closeAll(false);

      if (cmd === "reload") { location.reload(); return; }

      if (cmd === "save-config") {
        var save = document.getElementById("save-config");
        if (save) { save.click(); flash("配置已保存 ✓"); }
        return;
      }

      if (cmd === "profile") {
        var prof = document.getElementById("btn-profile");
        if (prof) { prof.click(); }
        return;
      }

      if (cmd.indexOf("view:") === 0) {
        var view = document.getElementById("view-btn-" + cmd.slice(5));
        if (view) { view.click(); }
        return;
      }

      if (pane) {
        var trigger = document.getElementById("menu-" + pane);
        if (trigger) { trigger.click(); }
      }
    }

    menus.forEach(function (m) {
      var btn = btnOf(m);
      var panel = panelOf(m);

      btn.addEventListener("click", function (ev) {
        ev.stopPropagation();
        toggle(m);
      });

      btn.addEventListener("keydown", function (ev) {
        var k = ev.key;
        if (k === "ArrowDown" || k === "Enter" || k === " ") {
          ev.preventDefault();
          openTo(m, true);
          return;
        }
        if (k === "ArrowLeft" || k === "ArrowRight") {
          ev.preventDefault();
          var idx = menus.indexOf(m);
          var next = menus[(idx + (k === "ArrowRight" ? 1 : -1) + menus.length) % menus.length];
          if (openMenu) { openTo(next, false); }
          btnOf(next).focus();
          return;
        }
        if (k === "Escape" && openMenu === m) {
          ev.preventDefault();
          closeAll(true);
        }
      });

      panel.addEventListener("click", function (ev) {
        var item = ev.target.closest ? ev.target.closest(".app-menu-item") : null;
        if (!item || !panel.contains(item)) { return; }
        ev.stopPropagation();
        run(item);
      });

      panel.addEventListener("keydown", function (ev) {
        var list = itemsOf(m);
        if (!list.length) {
          // R109：对话框型面板（云账号 / 小地图设置）里是真实表单控件，
          // 方向键与 Tab 必须留给控件本身，不能被菜单当成「按 Tab 收起」。
          if (ev.key === "Escape") { ev.preventDefault(); closeAll(true); }
          return;
        }
        var i = list.indexOf(document.activeElement);
        var k = ev.key;
        if (k === "ArrowDown") {
          ev.preventDefault();
          list[(i + 1) % list.length].focus();
        } else if (k === "ArrowUp") {
          ev.preventDefault();
          list[(i - 1 + list.length) % list.length].focus();
        } else if (k === "Home") {
          ev.preventDefault();
          list[0].focus();
        } else if (k === "End") {
          ev.preventDefault();
          list[list.length - 1].focus();
        } else if (k === "Escape") {
          ev.preventDefault();
          closeAll(true);
        } else if (k === "Tab") {
          closeAll(false);
        }
      });
    });

    // 工具条 ↔ 菜单 ↔ 上下文栏：setView 只改 aria-selected，这里监听它的变化，
    // 让已展开的「视图」菜单立刻跟上，同时切换上下文栏的槽（每次 setView 都走同一条路径）。
    if (window.MutationObserver) {
      var switcher = document.getElementById("view-switch");
      if (switcher) {
        new MutationObserver(function () {
          syncContext();
          if (openMenu) { renderChecks(); }
        }).observe(switcher, { subtree: true, attributeFilter: ["aria-selected"] });
      }
    }

    // 点外收起：用捕获阶段，赶在 app.js 里「模式/账号按钮 stopPropagation」之前判断，
    // 避免点账号入口时新菜单还开着（那会让两块面板同时存在）。
    document.addEventListener("click", function (ev) {
      if (!openMenu) { return; }
      if (openMenu.contains(ev.target)) { return; }
      closeAll(false);
    }, true);

    document.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape" && openMenu) { closeAll(true); }
    });

    closeAll(false);
  }

  // ---------------------------------------------------------------- 应用菜单（第一阶段）
  /* 「应用菜单」是设置弹层，不是普通下拉菜单：
     · 分区导航用 tab 语义，方向键只在导航按钮上接管；
     · 面板里的滑块 / 复选框 / 输入框保留原生键盘行为；
     · Esc 关闭并把焦点还给触发按钮，点面板外关闭。 */
  function bindAppMenu() {
    var trigger = document.getElementById("am-app");
    var panel = document.getElementById("am-app-panel");
    if (!trigger || !panel) { return; }

    var nav = panel.querySelector(".app-app-nav");
    var navBtns = [].slice.call(panel.querySelectorAll(".app-app-navbtn"));
    var sections = [].slice.call(panel.querySelectorAll(".app-app-sec"));
    var closeBtn = document.getElementById("am-app-close");
    var open = false;

    function selectSection(id, focusNav) {
      var found = false;
      sections.forEach(function (sec) {
        var on = sec.getAttribute("data-sec") === id;
        if (on) { found = true; }
        sec.hidden = !on;
      });
      if (!found) { return; }
      navBtns.forEach(function (btn) {
        var on = btn.getAttribute("data-sec") === id;
        btn.classList.toggle("is-active", on);
        btn.setAttribute("aria-selected", on ? "true" : "false");
        if (on && focusNav) { btn.focus(); }
      });
    }

    function openPanel() {
      open = true;
      panel.hidden = false;
      trigger.classList.add("open");
      trigger.setAttribute("aria-expanded", "true");
      var active = navBtns.filter(function (b) {
        return b.getAttribute("aria-selected") === "true";
      })[0] || navBtns[0];
      if (active) { active.focus(); }
    }

    function closePanel(back) {
      open = false;
      panel.hidden = true;
      trigger.classList.remove("open");
      trigger.setAttribute("aria-expanded", "false");
      if (back) { trigger.focus(); }
    }

    function runCommand(cmd) {
      closePanel(false);
      if (cmd === "reload") { location.reload(); return; }
      if (cmd === "save-config") {
        var save = document.getElementById("save-config");
        if (save) { save.click(); }
        return;
      }
      if (cmd === "profile") {
        var prof = document.getElementById("btn-profile");
        if (prof) { prof.click(); }
      }
    }

    trigger.addEventListener("click", function (ev) {
      ev.stopPropagation();
      if (open) { closePanel(true); } else { openPanel(); }
    });

    trigger.addEventListener("keydown", function (ev) {
      if (ev.key === "ArrowDown" || ev.key === "Enter" || ev.key === " ") {
        ev.preventDefault();
        openPanel();
      }
    });

    nav.addEventListener("click", function (ev) {
      var btn = ev.target && ev.target.closest ? ev.target.closest(".app-app-navbtn") : null;
      if (!btn || !nav.contains(btn)) { return; }
      selectSection(btn.getAttribute("data-sec"), false);
    });

    nav.addEventListener("keydown", function (ev) {
      var btn = ev.target && ev.target.closest ? ev.target.closest(".app-app-navbtn") : null;
      if (!btn || !nav.contains(btn)) { return; }
      var i = navBtns.indexOf(btn);
      var next = -1;
      if (ev.key === "ArrowDown" || ev.key === "ArrowRight") {
        next = (i + 1) % navBtns.length;
      } else if (ev.key === "ArrowUp" || ev.key === "ArrowLeft") {
        next = (i - 1 + navBtns.length) % navBtns.length;
      } else if (ev.key === "Home") {
        next = 0;
      } else if (ev.key === "End") {
        next = navBtns.length - 1;
      }
      if (next < 0 || next === i) { return; }
      ev.preventDefault();
      selectSection(navBtns[next].getAttribute("data-sec"), true);
    });

    panel.addEventListener("click", function (ev) {
      var item = ev.target && ev.target.closest ? ev.target.closest("[data-cmd]") : null;
      if (!item || !panel.contains(item)) { return; }
      ev.stopPropagation();
      runCommand(item.getAttribute("data-cmd"));
    });

    if (closeBtn) {
      closeBtn.addEventListener("click", function (ev) {
        ev.stopPropagation();
        trigger.click();
      });
    }

    document.addEventListener("click", function (ev) {
      if (!open) { return; }
      if (panel.contains(ev.target) || trigger.contains(ev.target)) { return; }
      closePanel(false);
    }, true);

    document.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape" && open) {
        ev.preventDefault();
        closePanel(true);
      }
    });
  }

  // ---------------------------------------------------------------- 地图工具栏 / 图层搜索 / 快捷开关
  function bindMapTools() {
    var displayBtn = document.getElementById("cb-display");
    var displayPop = document.getElementById("display-pop");
    if (displayBtn && displayPop) {
      function showDisplay(on) {
        displayPop.hidden = !on;
        displayBtn.classList.toggle("is-open", on);
        displayBtn.setAttribute("aria-expanded", on ? "true" : "false");
      }
      displayBtn.addEventListener("click", function (ev) {
        ev.stopPropagation();
        showDisplay(displayPop.hidden);
      });
      document.addEventListener("click", function (ev) {
        if (displayPop.hidden) { return; }
        if (displayPop.contains(ev.target) || displayBtn.contains(ev.target)) { return; }
        showDisplay(false);
      }, true);
      document.addEventListener("keydown", function (ev) {
        if (ev.key === "Escape" && !displayPop.hidden) {
          ev.preventDefault();
          showDisplay(false);
        }
      });
    }

    [["cb-follow", "follow"], ["cb-reset", "reset"]].forEach(function (pair) {
      var btn = document.getElementById(pair[0]);
      var target = document.getElementById(pair[1]);
      if (!btn || !target) { return; }
      btn.addEventListener("click", function () { target.click(); });
    });

    var input = document.getElementById("layer-search");
    var toggles = document.getElementById("layer-toggles");
    if (!input || !toggles) { return; }
    var wikiCats = document.getElementById("wiki-cats");
    var raf = 0;

    function applyFilter() {
      var q = String(input.value || "").trim().toLowerCase();
      [].forEach.call(toggles.querySelectorAll(".legend-group"), function (group) {
        var rows = [].slice.call(group.querySelectorAll(".legend-item"));
        if (!rows.length) { return; }
        var titleEl = group.querySelector(".legend-group-title");
        var groupMatch = !!q && titleEl &&
          (titleEl.textContent || "").toLowerCase().indexOf(q) >= 0;
        var any = false;
        rows.forEach(function (row) {
          var hit = !q || groupMatch ||
            (row.textContent || "").toLowerCase().indexOf(q) >= 0;
          row.hidden = !hit;
          if (hit) { any = true; }
        });
        group.hidden = !!q && !any;
        var body = group.querySelector(".legend-group-body");
        var toggle = group.querySelector(".legend-group-toggle");
        if (body) {
          if (q) {
            body.hidden = !any;
          } else if (toggle) {
            body.hidden = toggle.getAttribute("aria-expanded") === "false";
          }
        }
      });
      if (wikiCats) {
        [].forEach.call(wikiCats.querySelectorAll(".wiki-cat"), function (row) {
          row.hidden = !!q && (row.textContent || "").toLowerCase().indexOf(q) < 0;
        });
      }
    }

    function scheduleFilter() {
      if (raf) { return; }
      raf = (window.requestAnimationFrame || function (fn) { return setTimeout(fn, 0); })(function () {
        raf = 0;
        applyFilter();
      });
    }

    input.addEventListener("input", scheduleFilter);
    input.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape" && input.value) {
        ev.preventDefault();
        input.value = "";
        scheduleFilter();
      }
    });
    new MutationObserver(scheduleFilter).observe(toggles, { childList: true, subtree: true });
    if (wikiCats) {
      new MutationObserver(scheduleFilter).observe(wikiCats, { childList: true, subtree: true });
    }
    applyFilter();
  }

  /* 常用图层快捷开关：只驱动 #layer-toggles 里已有的 checkbox（不新造状态）。
     「撤离点」控制 3 个复选框，部分开启时 aria-pressed="mixed"；
     点击规则：全开 → 全关；混合或全关 → 全开。 */
  function bindLayerQuick() {
    var quick = document.getElementById("layer-quick");
    var toggles = document.getElementById("layer-toggles");
    if (!quick || !toggles) { return; }

    var KEYS = {
      extracts: ["extract_shared", "extract_pmc", "extract_scav"],
      valuables: ["valuables"],
      hazards: ["hazards"],
      bosses: ["bosses"],
      labels: ["labels"]
    };

    function boxesFor(name) {
      var keys = KEYS[name] || [];
      var out = [];
      keys.forEach(function (key) {
        var box = toggles.querySelector('input[data-layer="' + key + '"]');
        if (box) { out.push(box); }
      });
      return out;
    }

    function syncChips() {
      [].forEach.call(quick.querySelectorAll(".layer-chip"), function (chip) {
        var boxes = boxesFor(chip.getAttribute("data-quick"));
        if (!boxes.length) {
          chip.hidden = true;
          chip.disabled = true;
          chip.setAttribute("aria-pressed", "false");
          return;
        }
        chip.hidden = false;
        chip.disabled = false;
        var on = boxes.filter(function (b) { return b.checked || b.indeterminate; }).length;
        var state = on === boxes.length ? "true" : (on === 0 ? "false" : "mixed");
        chip.setAttribute("aria-pressed", state);
      });
    }

    quick.addEventListener("click", function (ev) {
      var chip = ev.target && ev.target.closest ? ev.target.closest(".layer-chip") : null;
      if (!chip || !quick.contains(chip)) { return; }
      var boxes = boxesFor(chip.getAttribute("data-quick"));
      if (!boxes.length) { return; }
      var allOn = boxes.every(function (b) { return b.checked; });
      var next = !allOn;
      boxes.forEach(function (box) {
        if (box.checked === next) { return; }
        box.checked = next;
        box.dispatchEvent(new Event("change", { bubbles: true }));
      });
      syncChips();
    });

    toggles.addEventListener("change", syncChips);
    new MutationObserver(syncChips).observe(toggles, { childList: true, subtree: true });
    syncChips();
  }

  // ---------------------------------------------------------------- 账号版本文案
  function bindEditionLabel() {
    var btn = document.getElementById("menu-account");
    if (!btn) { return; }

    function editionName() {
      var scope = window.GWDataScope;
      if (!scope) { return "未选择"; }
      var cur = scope.get ? scope.get() : null;
      var id = cur && cur.edition;
      if (!id) { return "未选择"; }
      var list = scope.editions || [];
      for (var i = 0; i < list.length; i++) {
        if (list[i].id === id) { return list[i].nameZh || id; }
      }
      return id;
    }

    function sync() { btn.textContent = "版本：" + editionName(); }

    // R88：app.js 在 window 上派发 gw:edition，原先监听 document 收不到，
    // 导致选完版本要刷新才更新文案。这里改为监听 window，并在事件里立刻同步。
    function onEdition() {
      sync();             // 版本名直接读当前 GWDataScope，同一次点击内落地
      loadDataDate();     // 数据截止日期重取（同一份 data/meta.json，切换版本数据源不变）
    }

    sync();
    window.addEventListener("gw:edition", onEdition);

    // 版本清单可能还没落地：没有数据时主动拉一次，再刷新文案（失败就保持 id / 未选择）
    var scope = window.GWDataScope;
    if (scope && scope.ensureEditions && (!scope.editions || !scope.editions.length)) {
      try {
        var p = scope.ensureEditions();
        if (p && p.then) { p.then(sync, function () {}); }
      } catch (e) { /* 忽略：文案保持「未选择」 */ }
    }
  }
})();
