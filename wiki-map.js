/* ============================================================================
 * wiki-map.js —— R20.21 官方 Wiki 互动地图底图模式
 *
 * 与现有矢量地图共用同一个 #stage / 地图下拉：左侧下拉可在「矢量图」与
 * 「官方 Wiki」之间切换。官方模式加载 data/wiki-maps.json（由
 * tools/fetch_wiki_maps.py 从 Escape from Tarkov Wiki 互动地图抓取），
 * 平铺渲染官方底图与官方标点；多楼层是拼在一张图里的，所以不做楼层过滤。
 * R34：官方标点的分类面板复用 app.js 的 LAYER_SPEC 分组顺序 / 名称 / 图标，
 * 官方 categoryId 与矢量 item.key 的差异集中在 WIKI_TO_VECTOR / WIKI_EXTRA 两张表。
 *
 * 说明：官方互动地图的 markers 坐标原点在左下角（origin=bottom-left），
 * 这里统一换成 SVG 的左上角坐标（y = height - marker.y）。
 * ==========================================================================*/
(function () {
  "use strict";

  var LS_MODE = "eftmap.baseMode";
  var DATA_URL = "data/wiki-maps.json";
  var SVG_NS = "http://www.w3.org/2000/svg";
  var ICON_SIZE = 40;          // 官方 60px 图标，画到 40px；与官方地图的标记大小接近
  var ICON_SCALE_BASE = 0.55;  // R89：与 app.js 一致 —— 滑条新刻度（旧 55% = 新 100%），渲染乘回 0.55
  var ZOOM_MAX = 12;

  // R34：官方 Wiki 分类 → 矢量图 LAYER_SPEC 的 item.key。
  // 两边字段命名不同：矢量图是 kind + where，官方是 categoryId；这里只做「分组 UI」的桥接，
  // 不改变任何一端的渲染与数据结构。键 = data/wiki-maps.json 的 category.id，
  // 值 = app.js LAYER_SPEC 的 item.key（分组顺序/名称/图标直接复用 app.js 暴露的同一份定义）。
  // 映射保持一对一；若将来出现多对一，需要在这里合并计数与勾选，不能直接叠两行同名。
  var WIKI_TO_VECTOR = {
    // 撤离点 / 转移点
    exfil_pmc: "extract_pmc",
    exfil_scav: "extract_scav",
    exfil_transit: "transits",
    // 物资：官方容器名与矢量图的 14 类容器键不同，只在这一层换算
    container_safe: "container_safe",
    container_jacket: "container_jacket",
    container_pc: "container_pcblock",
    container_dead: "container_scavbody",
    container_drawer: "container_drawer",
    container_duffle: "container_duffle",
    container_stash: "container_cache",
    container_medical: "container_med",
    container_crate: "container_supply",
    container_suitcase: "container_suitcase",
    container_tool: "container_toolbox",
    container_cash: "container_register",
    container_grenade: "container_grenade",
    container_weapon: "container_weapon",
    loot_loose: "loose",
    // 出生点
    spawn_pmc: "spawn_pmc",
    spawn_scav: "spawn_scav",
    spawn_sniper: "spawn_sniper",
    spawn_boss: "bosses",
    // 钥匙与门
    locked: "locks_door",
    // 其他
    stationarygun: "stationary"
  };

  // 没有矢量图 item 对应的官方分类：仍放进最接近的矢量分组，行名/图标用官方原始数据。
  // 这些不是矢量图层，不硬塞进不相关的开关；完整清单同时写进 ledger 的「未对应分类」。
  var WIKI_EXTRA = [
    { cat: "container_ammo", group: "物资", label: "弹药箱" },
    { cat: "container_medcase", group: "物资", label: "医疗箱" },
    { cat: "container_greencrate", group: "物资", label: "木箱" },
    { cat: "loot_key", group: "钥匙与门", label: "钥匙刷新点" },
    { cat: "loot_keycard", group: "钥匙与门", label: "钥匙卡刷新点" },
    { cat: "lever", group: "钥匙与门", label: "拉杆 / 按钮" },
    { cat: "spawn_cultist", group: "出生点", label: "邪教徒" },
    { cat: "spawn_rogueraider", group: "出生点", label: "黑卫队" },
    { cat: "quest", group: "其他", label: "电力面板" }
  ];

  var state = {
    mode: "vector",
    data: null,
    key: "customs",
    map: null,
    renderedKey: null,
    cats: {},
    search: "",
    iconScale: 1,
    z: 1,
    cx: 0,
    cy: 0,
    fit: 1,
    vb: null,
    markers: [],
    drag: null,
    loadPromise: null,
    error: null,
  };
  var el = {};

  function $(sel) { return document.querySelector(sel); }

  function svgEl(tag, attrs) {
    var n = document.createElementNS(SVG_NS, tag);
    for (var k in attrs) {
      if (Object.prototype.hasOwnProperty.call(attrs, k)) { n.setAttribute(k, attrs[k]); }
    }
    return n;
  }

  function clamp(v, a, b) { return Math.max(a, Math.min(b, v)); }

  function currentMapKey() {
    var sel = $("#map-list");
    return sel && sel.value ? sel.value : state.key;
  }

  // ---------------------------------------------------------------- 数据
  function loadData() {
    if (state.data) { return Promise.resolve(state.data); }
    if (state.loadPromise) { return state.loadPromise; }
    state.loadPromise = fetch(DATA_URL, { cache: "no-store" })
      .then(function (r) {
        if (!r.ok) { throw new Error("HTTP " + r.status); }
        return r.json();
      })
      .then(function (doc) {
        state.data = doc;
        return doc;
      })
      .catch(function (err) {
        state.loadPromise = null;
        state.error = err;
        throw err;
      });
    return state.loadPromise;
  }

  // ---------------------------------------------------------------- 分类筛选
  function catIcon(catId) {
    var map = state.map;
    if (!map) { return ""; }
    var c = (map.categories || []).filter(function (x) { return x.id === catId; })[0];
    return c ? c.icon : "";
  }

  /** 矢量图分组定义由 app.js 暴露；这里只建 categoryId → item.key 的反向索引，不复制分组表。 */
  function vectorSpecs() {
    var api = window.GWMapLayerSpec;
    if (!api || !api.groups || !api.icon) { return null; }
    var catsByKey = {};
    Object.keys(WIKI_TO_VECTOR).forEach(function (catId) {
      var key = WIKI_TO_VECTOR[catId];
      if (!catsByKey[key]) { catsByKey[key] = []; }
      catsByKey[key].push(catId);
    });
    return { api: api, groups: api.groups, catsByKey: catsByKey };
  }

  /** 一行图例：复用矢量图的 .toggle.legend-item 结构（勾选框 + 图标 + 名称 + 计数）。 */
  function makeLegendRow(cat, spec, label, api) {
    var row = document.createElement("label");
    row.className = "toggle legend-item";
    row.title = label + " · " + cat.count + " 个";
    var box = document.createElement("input");
    box.type = "checkbox";
    box.checked = state.cats[cat.id] !== false;
    box.dataset.cat = cat.id;
    row.appendChild(box);
    var icon = null;
    if (spec && api && api.icon) { icon = api.icon(spec); }
    if (!icon) {
      icon = document.createElement("img");
      icon.className = "legend-ico wiki-legend-img";
      icon.alt = "";
      icon.loading = "lazy";
      if (cat.icon) { icon.src = cat.icon; }
    }
    row.appendChild(icon);
    var name = document.createElement("span");
    name.className = "legend-name";
    name.textContent = label;
    row.appendChild(name);
    var count = document.createElement("span");
    count.className = "legend-count";
    count.textContent = String(cat.count || 0);
    row.appendChild(count);
    row.dataset.on = box.checked ? "true" : "false";
    return row;
  }

  /** 官方 Wiki 分类复用矢量图的 group 顺序 / 标题 / 行样式；0 个的分类与矢量图一样不显示。 */
  function renderPanel() {
    if (!state.map || !el.cats) { return; }
    var cats = state.map.categories || [];
    var byId = {};
    cats.forEach(function (c) { byId[c.id] = c; });
    state.cats = {};
    cats.forEach(function (c) { state.cats[c.id] = true; });
    el.cats.innerHTML = "";

    var vs = vectorSpecs();
    var used = {};
    (vs ? vs.groups : []).forEach(function (group) {
      var rows = [];
      group.items.forEach(function (item) {
        (vs.catsByKey[item.key] || []).forEach(function (catId) {
          var c = byId[catId];
          if (!c) { return; }
          used[catId] = true;
          if (!c.count) { return; }   // 与矢量图一致：当前地图 0 个的图层不显示
          rows.push(makeLegendRow(c, item, item.label, vs.api));
        });
      });
      WIKI_EXTRA.forEach(function (extra) {
        if (extra.group !== group.group) { return; }
        var c = byId[extra.cat];
        if (!c) { return; }
        used[extra.cat] = true;
        if (!c.count) { return; }
        rows.push(makeLegendRow(c, null, extra.label || c.nameZh || c.name || extra.cat, vs.api));
      });
      if (!rows.length) { return; }
      var heading = document.createElement("div");
      heading.className = "toggle-group";
      heading.textContent = group.group;
      el.cats.appendChild(heading);
      rows.forEach(function (row) { el.cats.appendChild(row); });
    });

    // 兜底：上游新增、尚未登记映射的分类不静默丢弃，单列一组并标明「未映射」。
    var rest = cats.filter(function (c) { return !used[c.id] && c.count > 0; });
    if (rest.length) {
      var other = document.createElement("div");
      other.className = "toggle-group";
      other.textContent = vs ? "官方 Wiki 其他分类（未映射）" : "官方 Wiki 分类";
      el.cats.appendChild(other);
      rest.forEach(function (c) {
        el.cats.appendChild(makeLegendRow(c, null, c.nameZh || c.name || c.id, vs && vs.api));
      });
    }
    syncRowStates();
    updateCount();
  }

  /** 勾选状态压暗整行，与矢量图 legend-item[data-on] 的视觉一致。 */
  function syncRowStates() {
    if (!el.cats) { return; }
    var rows = el.cats.querySelectorAll(".legend-item");
    for (var i = 0; i < rows.length; i++) {
      var box = rows[i].querySelector("input");
      rows[i].dataset.on = (box && box.checked) ? "true" : "false";
    }
  }

  function updateCount() {
    if (!el.count || !state.map) { return; }
    var total = state.map.markers.length;
    var visible = state.markers.filter(function (o) { return !o.node.classList.contains("is-off"); }).length;
    el.count.textContent = visible + " / " + total;
  }

  function applyFilter() {
    hidePop();
    var q = (state.search || "").trim().toLowerCase();
    state.markers.forEach(function (o) {
      var on = state.cats[o.cat] !== false;
      if (on && q) {
        var hay = ((o.title || "") + " " + (o.catName || "") + " " + (o.desc || "")).toLowerCase();
        on = hay.indexOf(q) !== -1;
      }
      o.node.classList.toggle("is-off", !on);
    });
    syncRowStates();
    updateCount();
  }

  // ---------------------------------------------------------------- 渲染
  function buildSvg() {
    while (el.svg.firstChild) { el.svg.removeChild(el.svg.firstChild); }
    state.markers = [];
    if (!state.map) { return; }
    var w = state.map.width, h = state.map.height;
    var img = svgEl("image", {
      href: state.map.image, x: 0, y: 0, width: w, height: h,
      preserveAspectRatio: "none", "image-rendering": "auto",
    });
    el.svg.appendChild(img);
    var layer = svgEl("g", { id: "wiki-markers" });
    var iconSize = ICON_SIZE * state.iconScale;
    var catNames = {};
    (state.map.categories || []).forEach(function (c) {
      catNames[c.id] = (c.nameZh || c.name || c.id);
    });
    (state.map.markers || []).forEach(function (m) {
      var node = svgEl("g", { class: "wm-marker", "data-cat": m.categoryId });
      var icon = svgEl("image", {
        href: catIcon(m.categoryId), x: -iconSize / 2, y: -iconSize / 2,
        width: iconSize, height: iconSize, preserveAspectRatio: "xMidYMid meet",
      });
      node.appendChild(icon);
      node.addEventListener("click", function (ev) {
        ev.stopPropagation();
        showPop(node, m);
      });
      layer.appendChild(node);
      state.markers.push({
        node: node, icon: icon, cat: m.categoryId, catName: catNames[m.categoryId] || "",
        x: m.x, y: h - m.y,
        title: m.title || "", desc: m.desc || "",
      });
    });
    el.svg.appendChild(layer);
    applyFilter();
  }

  function updateMarkerTransforms() {
    var scale = 1 / (state.fit * state.z);
    var list = state.markers;
    for (var i = 0; i < list.length; i++) {
      list[i].node.setAttribute("transform",
        "translate(" + list[i].x + " " + list[i].y + ") scale(" + scale + ")");
    }
  }

  function viewportSize() {
    return { w: el.viewport.clientWidth, h: el.viewport.clientHeight };
  }

  function applyView() {
    if (!state.map || !el.svg) { return; }
    var size = viewportSize();
    if (!size.w || !size.h) { return; }
    state.fit = Math.min(size.w / state.map.width, size.h / state.map.height) || 1;
    var p = state.fit * state.z;
    var vw = size.w / p, vh = size.h / p;
    if (vw >= state.map.width) { state.cx = state.map.width / 2; }
    else { state.cx = clamp(state.cx, vw / 2, state.map.width - vw / 2); }
    if (vh >= state.map.height) { state.cy = state.map.height / 2; }
    else { state.cy = clamp(state.cy, vh / 2, state.map.height - vh / 2); }
    state.vb = [state.cx - vw / 2, state.cy - vh / 2, vw, vh];
    el.svg.setAttribute("viewBox", state.vb.join(" "));
    el.svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
    updateMarkerTransforms();
  }

  function resetView() {
    if (!state.map) { return; }
    state.z = 1;
    state.cx = state.map.width / 2;
    state.cy = state.map.height / 2;
    applyView();
  }

  function screenToMap(sx, sy) {
    var size = viewportSize();
    if (!state.vb) { return { x: state.cx, y: state.cy }; }
    return {
      x: state.vb[0] + sx * (state.vb[2] / size.w),
      y: state.vb[1] + sy * (state.vb[3] / size.h),
    };
  }

  function zoomAt(sx, sy, factor) {
    if (!state.map) { return; }
    var size = viewportSize();
    var anchor = screenToMap(sx, sy);
    var z2 = clamp(state.z * factor, 1, ZOOM_MAX);
    if (Math.abs(z2 - state.z) < 1e-6) { return; }
    state.z = z2;
    var p2 = state.fit * z2;
    state.cx = anchor.x + (size.w / 2 - sx) / p2;
    state.cy = anchor.y + (size.h / 2 - sy) / p2;
    applyView();
  }

  function zoomCenter(factor) {
    var size = viewportSize();
    zoomAt(size.w / 2, size.h / 2, factor);
  }

  // ---------------------------------------------------------------- 弹窗
  function showPop(node, m) {
    if (!el.pop) { return; }
    el.pop.innerHTML = "";
    var title = document.createElement("strong");
    title.textContent = m.title || "(无标题)";
    el.pop.appendChild(title);
    if (m.desc) {
      var desc = document.createElement("span");
      desc.textContent = m.desc;
      el.pop.appendChild(desc);
    }
    var vr = el.viewport.getBoundingClientRect();
    var r = node.getBoundingClientRect();
    var left = r.left - vr.left + r.width / 2;
    var top = r.top - vr.top - 6;
    var popW = el.pop.offsetWidth || 220;
    left = clamp(left, popW / 2 + 6, vr.width - popW / 2 - 6);
    el.pop.style.left = left + "px";
    el.pop.style.top = Math.max(8, top) + "px";
    el.pop.style.transform = "translate(-50%, -100%)";
    el.pop.hidden = false;
  }

  function hidePop() {
    if (el.pop) { el.pop.hidden = true; }
  }

  // ---------------------------------------------------------------- 模式
  function ensureMap() {
    var key = currentMapKey();
    state.key = key;
    loadData().then(function (doc) {
      var map = doc.maps[key] || doc.maps.customs;
      if (!map) { throw new Error("没有这张地图的官方底图"); }
      state.map = map;
      if (state.renderedKey !== key) {
        state.renderedKey = key;
        state.search = "";
        if (el.search) { el.search.value = ""; }
        renderPanel();
        buildSvg();
      }
      state.z = 1;
      state.cx = map.width / 2;
      state.cy = map.height / 2;
      resetView();
      hidePop();
    }).catch(function (err) {
      state.error = err;
      if (window.console && console.warn) { console.warn("[GWWikiMap]", err); }
      if (el.count) { el.count.textContent = "载入失败"; }
    });
  }

  /** 打开 / 收起底图下拉；触发器复用 .map-select，展开层是同页 listbox，方便截图与键盘关闭。 */
  function setMenuOpen(open) {
    if (!el.modeMenu || !el.modeTrigger) { return; }
    el.modeMenu.hidden = !open;
    el.modeTrigger.setAttribute("aria-expanded", open ? "true" : "false");
  }

  function setMode(mode, silent) {
    // R34：底图只有矢量图 / 官方 Wiki 两态；卫星入口已移除，旧偏好里的 satellite 一律回落矢量图。
    state.mode = mode === "wiki" ? "wiki" : "vector";
    var isWiki = state.mode === "wiki";
    document.body.classList.toggle("wiki-base", isWiki);
    // R34：右侧任务栏据此在「任务列表」与「官方图层空态说明」之间切换。
    try {
      window.dispatchEvent(new CustomEvent("gwmap:mode", { detail: { mode: state.mode } }));
    } catch (e) { /* 忽略 */ }
    if (el.viewport) { el.viewport.hidden = !isWiki; }
    if (el.panel) { el.panel.hidden = !isWiki; }
    if (el.modeValue) { el.modeValue.textContent = isWiki ? "官方 Wiki" : "矢量图"; }
    if (el.modeOptions) {
      [].slice.call(el.modeOptions).forEach(function (btn) {
        var on = btn.dataset.mode === state.mode;
        btn.classList.toggle("is-on", on);
        btn.setAttribute("aria-selected", on ? "true" : "false");
      });
    }
    setMenuOpen(false);
    if (!silent) {
      try { localStorage.setItem(LS_MODE, state.mode); } catch (e) { /* 忽略 */ }
    }
    hidePop();
    // 卫星渲染能力保留在 app.js（GWMapSatellite），这里只确保底图不是卫星态。
    if (window.GWMapSatellite) { window.GWMapSatellite.set(false); }
    if (isWiki) {
      // R211：底图说明统一由 #wiki-panel 的 .wiki-note 承载，不再往上下文栏写提示。
      ensureMap();
      // 侧栏刚显示出来时 #stage 尺寸可能还没变，下一帧再对齐一次
      setTimeout(applyView, 30);
    }
  }

  // ---------------------------------------------------------------- 绑定
  function bind() {
    if (el.modeTrigger && el.modeMenu) {
      el.modeTrigger.addEventListener("click", function (ev) {
        ev.stopPropagation();
        setMenuOpen(el.modeMenu.hidden);
      });
    }
    if (el.modeMenu) {
      el.modeMenu.addEventListener("click", function (ev) {
        var node = ev.target;
        while (node && node !== el.modeMenu && !(node.dataset && node.dataset.mode)) {
          node = node.parentNode;
        }
        if (!node || node === el.modeMenu || !node.dataset.mode) { return; }
        setMode(node.dataset.mode);
      });
      el.modeMenu.addEventListener("keydown", function (ev) {
        if (ev.key !== "ArrowDown" && ev.key !== "ArrowUp") { return; }
        ev.preventDefault();
        var opts = [].slice.call(el.modeOptions);
        var i = opts.indexOf(document.activeElement);
        var next = 0;
        if (i >= 0) {
          next = ev.key === "ArrowDown" ? (i + 1) % opts.length : (i - 1 + opts.length) % opts.length;
        }
        if (opts[next]) { opts[next].focus(); }
      });
    }
    if (el.modeTrigger) {
      el.modeTrigger.addEventListener("keydown", function (ev) {
        if (ev.key !== "ArrowDown" && ev.key !== "ArrowUp") { return; }
        ev.preventDefault();
        setMenuOpen(true);
        var opts = [].slice.call(el.modeOptions);
        var idx = state.mode === "wiki" ? 1 : 0;
        if (opts[idx]) { opts[idx].focus(); }
      });
    }
    document.addEventListener("click", function (ev) {
      if (!el.modeMenu || el.modeMenu.hidden) { return; }
      if (el.modeMenu.contains(ev.target) || el.modeTrigger.contains(ev.target)) { return; }
      setMenuOpen(false);
    });
    document.addEventListener("keydown", function (ev) {
      if (!el.modeMenu || el.modeMenu.hidden) { return; }
      if (ev.key === "Escape") {
        setMenuOpen(false);
        if (el.modeTrigger) { el.modeTrigger.focus(); }
      }
    });
    if (el.zoomIn) { el.zoomIn.addEventListener("click", function () { zoomCenter(1.25); }); }
    if (el.zoomOut) { el.zoomOut.addEventListener("click", function () { zoomCenter(0.8); }); }
    if (el.reset) { el.reset.addEventListener("click", function () { resetView(); hidePop(); }); }

    if (el.cats) {
      el.cats.addEventListener("change", function (ev) {
        var cb = ev.target;
        if (!cb || cb.type !== "checkbox" || !cb.dataset.cat) { return; }
        state.cats[cb.dataset.cat] = cb.checked;
        applyFilter();
      });
    }
    if (el.search) {
      el.search.addEventListener("input", function () {
        state.search = el.search.value;
        applyFilter();
      });
    }
    if (el.all) {
      el.all.addEventListener("click", function () {
        Object.keys(state.cats).forEach(function (k) { state.cats[k] = true; });
        if (el.cats) {
          [].slice.call(el.cats.querySelectorAll("input[data-cat]")).forEach(function (cb) { cb.checked = true; });
        }
        applyFilter();
      });
    }
    if (el.none) {
      el.none.addEventListener("click", function () {
        Object.keys(state.cats).forEach(function (k) { state.cats[k] = false; });
        if (el.cats) {
          [].slice.call(el.cats.querySelectorAll("input[data-cat]")).forEach(function (cb) { cb.checked = false; });
        }
        applyFilter();
      });
    }

    var scale = $("#icon-scale");
    if (scale) {
      // R89：滑条值是新刻度（旧 55% = 新 100%），这里换回旧系数再乘进 ICON_SIZE；
      // 0 表示 0%（合法），脏值 / 非数字沿用原来的 1× 兜底。
      var toLegacy = function (v) { return isFinite(v) && v >= 0 ? v * ICON_SCALE_BASE : 1; };
      var sync = function () {
        var v = parseFloat(scale.value);
        state.iconScale = toLegacy(v);
        if (state.map) { hidePop(); buildSvg(); resetView(); }
      };
      scale.addEventListener("input", sync);
      var v0 = parseFloat(scale.value);
      if (isFinite(v0) && v0 >= 0) { state.iconScale = toLegacy(v0); }
    }

    window.addEventListener("gwmap:select", function (ev) {
      state.key = ev.detail && ev.detail.key ? ev.detail.key : currentMapKey();
      if (state.mode === "wiki") { ensureMap(); }
    });
    window.addEventListener("resize", function () {
      if (state.mode === "wiki") { applyView(); }
    });

    // 拖拽平移
    if (el.viewport) {
      el.viewport.addEventListener("mousedown", function (ev) {
        if (ev.button !== 0 || state.mode !== "wiki") { return; }
        if (ev.target && ev.target.closest && ev.target.closest(".wm-marker")) { return; }
        state.drag = { x: ev.clientX, y: ev.clientY, cx: state.cx, cy: state.cy };
        el.svg.classList.add("is-panning");
        hidePop();
        ev.preventDefault();
      });
      window.addEventListener("mousemove", function (ev) {
        if (!state.drag || state.mode !== "wiki") { return; }
        var p = state.fit * state.z;
        state.cx = state.drag.cx - (ev.clientX - state.drag.x) / p;
        state.cy = state.drag.cy - (ev.clientY - state.drag.y) / p;
        applyView();
      });
      window.addEventListener("mouseup", function () {
        if (!state.drag) { return; }
        state.drag = null;
        if (el.svg) { el.svg.classList.remove("is-panning"); }
      });
      el.viewport.addEventListener("wheel", function (ev) {
        if (state.mode !== "wiki") { return; }
        ev.preventDefault();
        var r = el.viewport.getBoundingClientRect();
        zoomAt(ev.clientX - r.left, ev.clientY - r.top, ev.deltaY < 0 ? 1.22 : 0.82);
      }, { passive: false });
      el.viewport.addEventListener("click", function (ev) {
        if (ev.target === el.svg || (ev.target && ev.target.tagName === "image" && !ev.target.closest(".wm-marker"))) {
          hidePop();
        }
      });
    }
  }

  function boot() {
    el.viewport = $("#wiki-viewport");
    el.svg = $("#wiki-svg");
    el.pop = $("#wiki-pop");
    el.panel = $("#wiki-panel");
    el.count = $("#wiki-count");
    el.cats = $("#wiki-cats");
    el.search = $("#wiki-search");
    el.all = $("#wiki-all");
    el.none = $("#wiki-none");
    el.zoomIn = $("#wiki-zoom-in");
    el.zoomOut = $("#wiki-zoom-out");
    el.reset = $("#wiki-reset");
    el.modeTrigger = $("#base-mode-trigger");
    el.modeMenu = $("#base-mode-menu");
    el.modeValue = $("#base-mode-value");
    el.modeOptions = document.querySelectorAll(".base-mode-option");
    // R211：#base-mode-note 已移除，底图说明不再由本模块写入。
    if (!el.viewport || !el.svg) { return; }
    state.key = currentMapKey();
    bind();

    var saved = null;
    try { saved = localStorage.getItem(LS_MODE); } catch (e) { /* 忽略 */ }
    if (saved === "wiki") {
      setMode("wiki", true);
    } else {
      setMode("vector", true);
      // 清掉旧版遗留的 satellite 偏好，避免下次启动又走已移除的入口
      if (saved && saved !== "vector") {
        try { localStorage.setItem(LS_MODE, "vector"); } catch (e) { /* 忽略 */ }
      }
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      // 等 app.js 把地图下拉填好，官方模式才知道当前是哪张图
      var tries = 0;
      (function waitMap() {
        var sel = $("#map-list");
        if (sel && sel.options && sel.options.length) { boot(); return; }
        if (tries++ < 40) { setTimeout(waitMap, 100); }
      })();
    });
  } else {
    boot();
  }
})();
