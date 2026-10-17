/* EFT 互动地图 · 前端（原生 JS，零依赖）
 *
 * 设计要点：
 * - 底图 SVG 整体注入 <svg id="map-svg">，与其共享同一套用户坐标系（viewBox）。
 *   上游每张图都把地面层放在一个顶层 <g id="…"> 里，其它楼层是它的兄弟分支，
 *   因此“只显示某一层”= 隐藏不在目标层自身及其祖先链上的 <g id>。
 * - 标注点的世界坐标 (x, z) 经 data/maps.json 里的 worldToSvg 系数直接落到用户坐标，
 *   与底图天然对齐，无需再做任何校准。
 * - 平移/缩放作用在 #viewport 的 CSS transform 上（屏幕像素空间，光标锚点）；
 *   标注点自带 1/k 反向缩放以保持屏幕上大小恒定。
 */

(function () {
  "use strict";

  var SVG_NS = "http://www.w3.org/2000/svg";
  var LS_MAP = "eftmap.map";
  var LS_LAYERS = "eftmap.layers";
  var LS_FOLLOW = "eftmap.follow";
  var ZOOM_MIN = 0.5;
  var ZOOM_MAX = 20;
  // 底图矩形最多向外扩这么多比例，用来容纳紧贴边缘的标注点
  var PAD_RATIO = 0.12;

  var state = {
    maps: [],            // data/maps.json 的地图数组
    meta: null,          // data/meta.json
    map: null,           // 当前地图条目
    layers: { extracts: true, transits: true, spawns: false, labels: true },
    // 相机：z 是相对「整图适配」的放大倍数，cx/cy 是屏幕中心所在的地图坐标。
    // 缩放走 viewBox 而不是 CSS transform —— 后者会把 SVG 栅格化再放大，越放越糊。
    z: 1, cx: 0, cy: 0,
    baseVb: [0, 0, 1, 1],// z=1 时的 viewBox（底图矩形 + 外边距）
    fit: 1,              // z=1 时每用户单位对应多少屏幕像素
    vb: [0, 0, 1, 1],    // 当前实际使用的 viewBox（随相机变化）
    svgCache: {},        // 每张图的 SVG 文本缓存
    markerScaleNodes: [],// 需要随缩放反向补偿的节点
    selected: null,
    player: null,        // 实时定位：最新解析到的玩家位置 {x, z, yaw, name, mtime}
    positionInfo: { available: false, reason: null },
    follow: true,        // 是否自动居中到玩家
    playerNode: null,    // 玩家标记节点（renderOverlay 清空时会一并丢掉）
    events: null         // EventSource
  };

  var el = {};

  // ---------------------------------------------------------------- 工具
  function $(id) { return document.getElementById(id); }
  function svgEl(tag, attrs) {
    var node = document.createElementNS(SVG_NS, tag);
    if (attrs) { for (var key in attrs) { node.setAttribute(key, attrs[key]); } }
    return node;
  }
  function loadJSON(url) {
    return fetch(url, { cache: "no-cache" }).then(function (res) {
      if (!res.ok) { throw new Error(url + " → HTTP " + res.status); }
      return res.json();
    });
  }
  function loadText(url) {
    return fetch(url).then(function (res) {
      if (!res.ok) { throw new Error(url + " → HTTP " + res.status); }
      return res.text();
    });
  }
  function showError(html) {
    el.error.innerHTML = html;
    el.error.hidden = false;
  }

  // ---------------------------------------------------------------- 启动
  function boot() {
    el.mapList = $("map-list");
    el.search = $("search");
    el.searchResults = $("search-results");
    el.detail = $("detail");
    el.detailBlock = $("detail-block");
    el.statusMap = $("status-map");
    el.statusCursor = $("status-cursor");
    el.statusPosition = $("status-position");
    el.followBtn = $("follow");
    el.error = $("error");
    el.svg = $("map-svg");
    el.viewport = $("viewport");
    // #stage 不被 transform 影响，尺寸/坐标换算一律以它为准（#viewport 会被平移缩放改变 rect）
    el.stage = $("stage");

    restoreLayers();
    restoreFollow();
    bindUI();
    initRealtime();

    Promise.all([
      loadJSON("data/maps.json"),
      loadJSON("data/meta.json").catch(function () { return null; })
    ]).then(function (results) {
      var data = results[0];
      state.meta = results[1];
      state.maps = data.maps || [];
      if (!state.maps.length) { throw new Error("data/maps.json 里没有任何地图"); }
      renderMetaLine();
      renderMapList();
      var wanted = localStorage.getItem(LS_MAP);
      var initial = state.maps.some(function (m) { return m.key === wanted; }) ? wanted : state.maps[0].key;
      return selectMap(initial);
    }).catch(function (err) {
      showError(
        "<strong>无法加载地图数据</strong><br>" + String(err.message || err) +
        "<br><br>如果你是从 <code>file://</code> 直接打开的页面，浏览器会拦截本地数据读取。" +
        "<br>请通过本地服务访问：<code>python tools/serve.py</code>，再打开 <code>http://127.0.0.1:8787/</code>。"
      );
    });
  }

  // ---------------------------------------------------------------- 侧栏
  function renderMetaLine() {
    var meta = state.meta;
    if (!meta) { return; }
    var counts = meta.counts || {};
    $("meta-line").textContent =
      "数据版本：" + (meta.generatedAt || "未知") + " · 模式 " + (meta.gameMode || "regular") +
      " · " + (counts.maps || 0) + " 张图 / " + (counts.extracts || 0) + " 个撤离点";
  }

  function renderMapList() {
    el.mapList.innerHTML = "";
    state.maps.forEach(function (map) {
      var btn = document.createElement("button");
      btn.className = "map-item";
      btn.setAttribute("role", "option");
      btn.dataset.key = map.key;
      var name = document.createElement("span");
      name.textContent = map.name;
      var count = document.createElement("span");
      count.className = "count";
      count.textContent = (map.layers.extracts || []).length + " 撤离";
      btn.appendChild(name);
      btn.appendChild(count);
      btn.title = map.name + "（" + map.key + "）";
      btn.addEventListener("click", function () { selectMap(map.key); });
      el.mapList.appendChild(btn);
    });
    markSelectedMap();
  }

  function markSelectedMap() {
    var items = el.mapList.querySelectorAll(".map-item");
    for (var i = 0; i < items.length; i++) {
      items[i].setAttribute("aria-selected", String(items[i].dataset.key === (state.map && state.map.key)));
    }
  }

  function restoreLayers() {
    try {
      var saved = JSON.parse(localStorage.getItem(LS_LAYERS) || "null");
      if (saved) { for (var key in state.layers) { if (key in saved) { state.layers[key] = !!saved[key]; } } }
    } catch (e) { /* 损坏的本地存储忽略即可 */ }
    var boxes = document.querySelectorAll("#layer-toggles input");
    for (var i = 0; i < boxes.length; i++) {
      boxes[i].checked = !!state.layers[boxes[i].dataset.layer];
    }
  }

  function bindUI() {
    var boxes = document.querySelectorAll("#layer-toggles input");
    for (var i = 0; i < boxes.length; i++) {
      boxes[i].addEventListener("change", function (ev) {
        state.layers[ev.target.dataset.layer] = ev.target.checked;
        localStorage.setItem(LS_LAYERS, JSON.stringify(state.layers));
        renderOverlay();
      });
    }

    $("zoom-in").addEventListener("click", function () { zoomAt(centerX(), centerY(), 1.25); });
    $("zoom-out").addEventListener("click", function () { zoomAt(centerX(), centerY(), 1 / 1.25); });
    $("reset").addEventListener("click", function () { resetView(); });
    if (el.followBtn) {
      el.followBtn.addEventListener("click", function () { setFollow(!state.follow); });
    }

    el.search.addEventListener("input", renderSearchResults);
    el.search.addEventListener("keydown", function (ev) {
      if (ev.key === "Enter") {
        var first = el.searchResults.querySelector(".search-item");
        if (first) { first.click(); }
      } else if (ev.key === "Escape") {
        el.search.value = "";
        renderSearchResults();
      }
    });

    // 平移
    var dragging = false, startX = 0, startY = 0;
    var dragMoved = false;
    el.viewport.addEventListener("mousedown", function (ev) {
      if (ev.button !== 0) { return; }
      dragging = true;
      dragMoved = false;
      startX = ev.clientX; startY = ev.clientY;
      el.viewport.style.cursor = "grabbing";
      ev.preventDefault();
    });
    window.addEventListener("mousemove", function (ev) {
      if (!dragging) { return; }
      var dx = ev.clientX - startX, dy = ev.clientY - startY;
      if (Math.abs(dx) + Math.abs(dy) > 3 && !dragMoved) {
        dragMoved = true;
        setFollow(false);                      // 用户接管视角
        startX = ev.clientX; startY = ev.clientY;   // 以当前点为平移起点，避免首次跳变
      }
      if (dragMoved) {
        panBy(ev.clientX - startX, ev.clientY - startY);
        startX = ev.clientX; startY = ev.clientY;
      }
    });
    window.addEventListener("mouseup", function () {
      if (!dragging) { return; }
      dragging = false;
      el.viewport.style.cursor = "";
    });
    // 拖拽后紧接着的一次 click 不应触发选中标记
    el.viewport.addEventListener("click", function (ev) {
      if (dragMoved) { dragMoved = false; ev.stopPropagation(); }
    }, true);

    // 光标锚点缩放；跟随模式下改为以屏幕中心（也就是玩家所在处）为锚点，避免把玩家甩出视野
    el.viewport.addEventListener("wheel", function (ev) {
      ev.preventDefault();
      var rect = el.stage.getBoundingClientRect();
      var factor = ev.deltaY < 0 ? 1.15 : 1 / 1.15;
      if (state.follow && state.player) {
        zoomAt(rect.width / 2, rect.height / 2, factor);
      } else {
        zoomAt(ev.clientX - rect.left, ev.clientY - rect.top, factor);
      }
    }, { passive: false });

    // 鼠标位置读数
    el.viewport.addEventListener("mousemove", function (ev) {
      var rect = el.stage.getBoundingClientRect();
      var world = screenToWorld(ev.clientX - rect.left, ev.clientY - rect.top);
      el.statusCursor.textContent = "世界坐标：x " + Math.round(world.x) + " / z " + Math.round(world.z);
    });

    window.addEventListener("resize", function () {
      updateMetrics();
      applyView();
      renderOverlay();
    });
    renderMapList();
  }

  // ---------------------------------------------------------------- 地图加载
  function selectMap(key) {
    var map = state.maps.filter(function (m) { return m.key === key; })[0];
    if (!map) { return Promise.resolve(); }
    state.map = map;
    state.selected = null;
    el.detailBlock.hidden = true;
    localStorage.setItem(LS_MAP, key);
    markSelectedMap();
    el.statusMap.textContent = "正在载入 " + map.name + " …";

    return svgText(map).then(function (text) {
      buildSvg(text, map);
      renderOverlay();
      resetView();
      el.search.value = "";
      renderSearchResults();
      el.statusMap.textContent = map.name + " · " + map.viewBox[2].toFixed(0) + "×" + map.viewBox[3].toFixed(0) + " 世界单位";
    }).catch(function (err) {
      showError("<strong>无法载入底图</strong>：" + map.svg + "<br>" + String(err.message || err));
    });
  }

  function svgText(map) {
    if (state.svgCache[map.key]) { return Promise.resolve(state.svgCache[map.key]); }
    return loadText(map.svg).then(function (text) {
      state.svgCache[map.key] = text;
      return text;
    });
  }

  /** 注入底图并只保留目标图层 */
  function buildSvg(text, map) {
    var parsed = new DOMParser().parseFromString(text, "image/svg+xml");
    if (parsed.querySelector("parsererror")) { throw new Error("底图 SVG 解析失败"); }
    var srcRoot = parsed.documentElement;

    while (el.svg.firstChild) { el.svg.removeChild(el.svg.firstChild); }
    // 相机按 #stage 的宽高比构造 viewBox，两轴比例天然一致，用 none 保证精确铺满无信箱边
    el.svg.setAttribute("preserveAspectRatio", "none");

    var base = svgEl("g", { id: "emk-base" });
    var children = Array.prototype.slice.call(srcRoot.childNodes);
    children.forEach(function (node) {
      base.appendChild(document.importNode(node, true));
    });
    el.svg.appendChild(base);

    var overlay = svgEl("g", { id: "emk-overlay" });
    el.svg.appendChild(overlay);
    el.overlay = overlay;

    isolateLayer(base, map.svgLayer);

    updateMetrics();
  }

  /** 只显示 target 层：隐藏所有既不等于 target、也不在 target 子树/祖先链上的 <g id> */
  function isolateLayer(root, layerId) {
    var target = null;
    if (layerId) { target = root.querySelector('[id="' + layerId.replace(/"/g, '\\"') + '"]'); }
    if (!target) {
      console.warn("底图里找不到图层 " + layerId + "，改为显示全部内容");
      return;
    }
    var ancestors = [];
    for (var node = target.parentNode; node && node !== root; node = node.parentNode) { ancestors.push(node); }

    var groups = root.querySelectorAll("g[id]");
    for (var i = 0; i < groups.length; i++) {
      var g = groups[i];
      var keep = (g === target) || target.contains(g) || ancestors.indexOf(g) !== -1;
      if (!keep) { g.style.display = "none"; }
    }
  }

  // ---------------------------------------------------------------- 视图
  function stageSize() {
    var rect = el.stage.getBoundingClientRect();
    return { w: rect.width, h: rect.height };
  }
  function centerX() { return stageSize().w / 2; }
  function centerY() { return stageSize().h / 2; }

  /** 计算实际 viewBox（底图矩形 + 最多 PAD_RATIO 的外边距，用于容纳贴边标注） */
  function computeViewBox(map) {
    var vb = map.viewBox;
    var x0 = vb[0], y0 = vb[1], x1 = vb[0] + vb[2], y1 = vb[1] + vb[3];
    var hw = vb[2] * PAD_RATIO, hh = vb[3] * PAD_RATIO;
    var bounds = allPointsBBox(map);
    var nx0 = Math.max(x0 - hw, Math.min(bounds.minX, x0));
    var ny0 = Math.max(y0 - hh, Math.min(bounds.minY, y0));
    var nx1 = Math.min(x1 + hw, Math.max(bounds.maxX, x1));
    var ny1 = Math.min(y1 + hh, Math.max(bounds.maxY, y1));
    return [nx0, ny0, nx1 - nx0, ny1 - ny0];
  }

  /** 含所有图层与地名的包围盒（用户坐标） */
  function allPointsBBox(map) {
    var box = { minX: Infinity, minY: Infinity, maxX: -Infinity, maxY: -Infinity };
    eachPoint(map, function (sx, sy) {
      if (sx < box.minX) { box.minX = sx; }
      if (sy < box.minY) { box.minY = sy; }
      if (sx > box.maxX) { box.maxX = sx; }
      if (sy > box.maxY) { box.maxY = sy; }
    });
    return box;
  }

  function eachPoint(map, fn) {
    ["extracts", "transits", "spawns"].forEach(function (kind) {
      (map.layers[kind] || []).forEach(function (item) { fn(svgX(map, item.x, item.z), svgY(map, item.x, item.z)); });
    });
    (map.labels || []).forEach(function (label) { fn(svgX(map, label.x, label.z), svgY(map, label.x, label.z)); });
  }

  /** 世界坐标 → 底图用户坐标（含旋转的交叉项，不能把 x、z 分开算） */
  function svgX(map, x, z) {
    var c = map.worldToSvg;
    return c.a * x + c.b * z + c.c;
  }
  function svgY(map, x, z) {
    var c = map.worldToSvg;
    return c.d * x + c.e * z + c.f;
  }

  function updateMetrics() {
    if (!state.map) { return; }
    var size = stageSize();
    state.baseVb = computeViewBox(state.map);
    // preserveAspectRatio=none 时两轴各自铺满；适配比例取较小值即为「整图可见」
    var sx = size.w / state.baseVb[2], sy = size.h / state.baseVb[3];
    state.fit = Math.min(sx, sy) || 1;
  }

  /** 相机 → viewBox（缩放走 viewBox，SVG 每次都是矢量重绘，不会越放越糊） */
  function applyView() {
    if (!state.map) { return; }
    var size = stageSize();
    var p = state.fit * state.z;             // 每用户单位对应多少屏幕像素
    var vw = size.w / p, vh = size.h / p;
    state.vb = [state.cx - vw / 2, state.cy - vh / 2, vw, vh];
    el.svg.setAttribute("viewBox", state.vb.join(" "));
    updateCounterScale();
  }

  /** 标注点在屏幕上大小恒定：内部再乘 1/z 反向补偿 */
  function updateCounterScale() {
    var inv = 1 / state.z;
    for (var i = 0; i < state.markerScaleNodes.length; i++) {
      var node = state.markerScaleNodes[i];
      var base = node.__emkBase;
      if (base && base.sx !== undefined) {
        node.setAttribute("transform", "translate(" + base.sx + " " + base.sy + ") scale(" + inv + ")");
      }
    }
  }

  function resetView() {
    var vb = state.baseVb;
    state.z = 1;
    state.cx = vb[0] + vb[2] / 2;
    state.cy = vb[1] + vb[3] / 2;
    applyView();
  }

  function zoomAt(px, py, factor) {
    var z2 = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, state.z * factor));
    if (Math.abs(z2 - state.z) < 1e-6) { return; }
    var anchor = screenToUser(px, py);       // 缩放前光标下的地图点
    state.z = z2;
    var size = stageSize();
    var p2 = state.fit * z2;
    // 让这个点缩放后仍落在 (px, py)
    state.cx = anchor.x + (size.w / 2 - px) / p2;
    state.cy = anchor.y + (size.h / 2 - py) / p2;
    applyView();
  }

  /** 屏幕坐标（相对 #stage 左上角）→ 地图用户坐标 */
  function screenToUser(px, py) {
    var p = state.fit * state.z;
    return { x: state.vb[0] + px / p, y: state.vb[1] + py / p };
  }

  /** 拖动平移：位移量按当前比例换算成地图坐标 */
  function panBy(dxPx, dyPx) {
    var p = state.fit * state.z;
    state.cx -= dxPx / p;
    state.cy -= dyPx / p;
    applyView();
  }

  /** 屏幕坐标（相对 #viewport 左上角）→ 世界坐标 */
  function screenToWorld(px, py) {
    var map = state.map;
    var u = screenToUser(px, py);
    var c = map.worldToSvg;
    // 反解线性方程组 [a b; d e] · [x; z] = [ux - c; uy - f]
    var det = c.a * c.e - c.b * c.d;
    if (Math.abs(det) < 1e-12) { return { x: NaN, z: NaN }; }
    var rx = u.x - c.c, ry = u.y - c.f;
    return { x: (c.e * rx - c.b * ry) / det, z: (-c.d * rx + c.a * ry) / det };
  }

  function centerOnPoint(sx, sy) {
    state.cx = sx;
    state.cy = sy;
    applyView();
  }

  // ---------------------------------------------------------------- 覆盖层
  function renderOverlay() {
    if (!el.overlay || !state.map) { return; }
    var map = state.map;
    var unit = 1 / state.fit;         // 目标屏幕像素 → 用户单位（1/z 的反向补偿在节点 transform 里）

    while (el.overlay.firstChild) { el.overlay.removeChild(el.overlay.firstChild); }
    state.markerScaleNodes = [];

    if (state.layers.spawns) {
      var spawns = svgEl("g", { class: "emk-spawn" });
      map.layers.spawns.forEach(function (item) {
        var node = svgEl("circle", {
          cx: svgX(map, item.x, item.z), cy: svgY(map, item.x, item.z), r: 2.2 * unit
        });
        spawns.appendChild(node);
      });
      el.overlay.appendChild(spawns);
    }

    if (state.layers.labels) {
      var labels = svgEl("g", { id: "emk-labels" });
      map.labels.forEach(function (label) {
        var sx = svgX(map, label.x, label.z);
        var sy = svgY(map, label.x, label.z);
        // 地名同样做 1/k 反向缩放：屏幕上字号恒定，放大后不会把图糊住
        var g = svgEl("g", { "pointer-events": "none" });
        g.__emkBase = { sx: sx, sy: sy, isLabel: true };
        g.setAttribute("transform", "translate(" + sx + " " + sy + ") scale(1)");
        var text = svgEl("text", {
          class: "emk-label",
          "font-size": 12 * unit,
          "text-anchor": "middle",
          "dominant-baseline": "central",
          x: 0,
          y: 0
        });
        text.textContent = label.text;
        g.appendChild(text);
        labels.appendChild(g);
        state.markerScaleNodes.push(g);
      });
      el.overlay.appendChild(labels);
    }

    [["extracts", 5.2], ["transits", 4.6]].forEach(function (pair) {
      var kind = pair[0], radius = pair[1];
      if (!state.layers[kind]) { return; }
      (map.layers[kind] || []).forEach(function (item) {
        el.overlay.appendChild(makeMarker(map, kind, item, radius * unit));
      });
    });

    updateCounterScale();
    renderPlayer();            // 覆盖层被重建，玩家标记要跟着回来
    updatePositionStatus();
  }

  function makeMarker(map, kind, item, radius) {
    var c = map.worldToSvg;
    var sx = c.a * item.x + c.b * item.z + c.c;
    var sy = c.d * item.x + c.e * item.z + c.f;
    var cls = "emk-marker emk-" + kind;
    if (kind === "extracts") { cls += " emk-extract-" + (item.faction || "shared"); }
    var g = svgEl("g", { class: cls });
    g.__emkBase = { sx: sx, sy: sy };
    g.setAttribute("transform", "translate(" + sx + " " + sy + ") scale(1)");
    g.appendChild(svgEl("circle", { r: radius }));
    g.addEventListener("click", function (ev) {
      ev.stopPropagation();
      showDetail(map, kind, item, g);
    });
    state.markerScaleNodes.push(g);
    return g;
  }

  // ---------------------------------------------------------------- 详情与搜索
  var KIND_LABEL = { extracts: "撤离点", transits: "过境点", labels: "地名" };
  var FACTION_LABEL = { pmc: "USEC / PMC", scav: "Scav", shared: "通用" };

  function showDetail(map, kind, item, node) {
    state.selected = { kind: kind, item: item };
    var rows = [["名称", item.name || "（未命名）"], ["类型", KIND_LABEL[kind] || kind]];
    if (kind === "extracts") { rows.push(["阵营", FACTION_LABEL[item.faction] || item.faction || "通用"]); }
    rows.push(["世界坐标", "x " + item.x + " ／ z " + item.z]);
    rows.push(["地图", map.name]);
    el.detail.innerHTML = "";
    rows.forEach(function (row) {
      var dt = document.createElement("dt");
      dt.textContent = row[0];
      var dd = document.createElement("dd");
      dd.textContent = row[1];
      el.detail.appendChild(dt);
      el.detail.appendChild(dd);
    });
    el.detailBlock.hidden = false;

    if (node) {
      node.querySelectorAll(".emk-ring").forEach(function (ring) { ring.remove(); });
      var ring = svgEl("circle", { class: "emk-ring", r: node.firstChild.getAttribute("r") });
      node.appendChild(ring);
      window.setTimeout(function () { if (ring.parentNode) { ring.remove(); } }, 3400);
    }
  }

  function searchableItems(map) {
    var items = [];
    (map.layers.extracts || []).forEach(function (it) { items.push({ kind: "extracts", name: it.name, item: it }); });
    (map.layers.transits || []).forEach(function (it) { items.push({ kind: "transits", name: it.name, item: it }); });
    (map.labels || []).forEach(function (it) { items.push({ kind: "labels", name: it.text, item: it }); });
    return items;
  }

  function renderSearchResults() {
    var map = state.map;
    if (!map) { return; }
    var query = el.search.value.trim().toLowerCase();
    el.searchResults.innerHTML = "";
    if (!query) { el.searchResults.hidden = true; return; }

    var hits = searchableItems(map).filter(function (entry) {
      return entry.name && entry.name.toLowerCase().indexOf(query) !== -1;
    }).slice(0, 30);

    if (!hits.length) {
      var empty = document.createElement("div");
      empty.className = "search-empty";
      empty.textContent = "没有匹配的标记";
      el.searchResults.appendChild(empty);
      el.searchResults.hidden = false;
      return;
    }

    hits.forEach(function (hit) {
      var btn = document.createElement("button");
      btn.className = "search-item";
      var name = document.createElement("span");
      name.textContent = hit.name;
      var kind = document.createElement("span");
      kind.className = "kind";
      kind.textContent = KIND_LABEL[hit.kind] || hit.kind;
      btn.appendChild(name);
      btn.appendChild(kind);
      btn.addEventListener("click", function () { focusItem(hit); });
      el.searchResults.appendChild(btn);
    });
    el.searchResults.hidden = false;
  }

  function focusItem(hit) {
    var map = state.map;
    // 目标图层若被关闭则自动打开，否则用户会“找不到”搜出来的东西
    var layerKey = hit.kind === "labels" ? "labels" : hit.kind;
    if (!state.layers[layerKey]) {
      state.layers[layerKey] = true;
      var box = document.querySelector('#layer-toggles input[data-layer="' + layerKey + '"]');
      if (box) { box.checked = true; }
      localStorage.setItem(LS_LAYERS, JSON.stringify(state.layers));
      renderOverlay();
    }
    var node = findMarkerNode(map, hit);
    if (node) { centerOnPoint(node.__emkBase.sx, node.__emkBase.sy); }
    else {
      var sx = map.worldToSvg.a * hit.item.x + map.worldToSvg.b * hit.item.z + map.worldToSvg.c;
      var sy = map.worldToSvg.d * hit.item.x + map.worldToSvg.e * hit.item.z + map.worldToSvg.f;
      centerOnPoint(sx, sy);
    }
    if (hit.kind === "labels") { showDetail(map, "labels", { name: hit.item.text, x: hit.item.x, z: hit.item.z }, null); }
    else { showDetail(map, hit.kind, hit.item, node); }
  }

  function findMarkerNode(map, hit) {
    var nodes = el.overlay.querySelectorAll(".emk-" + hit.kind);
    for (var i = 0; i < nodes.length; i++) {
      var b = nodes[i].__emkBase;
      if (!b) { continue; }
      var sx = map.worldToSvg.a * hit.item.x + map.worldToSvg.b * hit.item.z + map.worldToSvg.c;
      var sy = map.worldToSvg.d * hit.item.x + map.worldToSvg.e * hit.item.z + map.worldToSvg.f;
      if (Math.abs(b.sx - sx) < 0.01 && Math.abs(b.sy - sy) < 0.01) { return nodes[i]; }
    }
    return null;
  }

  // ---------------------------------------------------------------- 实时定位
  /** 朝向角 → SVG 里的箭头旋转角（度）：必须过仿射的线性部分 */
  function svgAngle(map, yaw) {
    var c = map.worldToSvg;
    var rad = yaw * Math.PI / 180;
    var dx = Math.sin(rad), dz = Math.cos(rad);
    return Math.atan2(c.d * dx + c.e * dz, c.a * dx + c.b * dz) * 180 / Math.PI;
  }

  function restoreFollow() {
    state.follow = localStorage.getItem(LS_FOLLOW) !== "0";
    syncFollowButton();
  }

  function setFollow(on) {
    if (state.follow === on) { return; }
    state.follow = on;
    localStorage.setItem(LS_FOLLOW, on ? "1" : "0");
    syncFollowButton();
    if (on) { centerOnPlayer(); }
  }

  function syncFollowButton() {
    if (!el.followBtn) { return; }
    el.followBtn.classList.toggle("on", state.follow);
    el.followBtn.textContent = state.follow ? "跟随中" : "已锁定";
    el.followBtn.title = state.follow
      ? "实时定位自动居中（拖动地图会切到「已锁定」按手动视角）"
      : "已手动锁定视角，点击恢复自动跟随玩家";
  }

  function centerOnPlayer() {
    if (!state.map || !state.player) { return; }
    centerOnPoint(svgX(state.map, state.player.x, state.player.z),
                  svgY(state.map, state.player.x, state.player.z));
  }

  /** 首屏先直接问一次，再订阅 SSE：不必等连接建立才看到定位状态 */
  function initRealtime() {
    fetch("api/position", { cache: "no-store" }).then(function (res) {
      return res.ok ? res.json() : null;
    }).then(function (payload) {
      if (payload && !state.player) { applyPosition(payload); }
    }).catch(function () { /* 无服务时静默：地图本体不受影响 */ });

    if (typeof EventSource === "undefined") {
      setPositionStatus(false, "此浏览器不支持实时定位（EventSource）");
      return;
    }
    var source = new EventSource("events");
    state.events = source;
    source.onmessage = function (ev) {
      var payload;
      try { payload = JSON.parse(ev.data); } catch (e) { return; }
      applyPosition(payload);
    };
    source.onerror = function () {
      // EventSource 会自动重连，这里只反映状态
      setPositionStatus(false, "定位：连接中断，正在重连…");
    };
  }

  function applyPosition(payload) {
    state.positionInfo = { available: !!payload.available, reason: payload.reason || null };
    var pos = payload.position || null;
    var moved = !!pos && (!state.player || state.player.name !== pos.name ||
                          state.player.x !== pos.x || state.player.z !== pos.z);
    state.player = pos;
    if (state.map) { renderPlayer(); }
    updatePositionStatus();
    if (pos && state.follow && moved) { centerOnPlayer(); }
  }

  function insideMap(map, pos) {
    var vb = map.viewBox;
    var sx = svgX(map, pos.x, pos.z), sy = svgY(map, pos.x, pos.z);
    return sx >= vb[0] && sx <= vb[0] + vb[2] && sy >= vb[1] && sy <= vb[1] + vb[3];
  }

  function positionStatusText() {
    var pos = state.player;
    if (!pos) { return "定位：" + (state.positionInfo.reason || "不可用"); }
    var text = "定位：x " + Math.round(pos.x) + " / z " + Math.round(pos.z);
    if (state.map && !insideMap(state.map, pos)) { text += " · 可能不在当前地图"; }
    return text;
  }

  function setPositionStatus(available, text) {
    if (!el.statusPosition) { return; }
    el.statusPosition.textContent = text;
    el.statusPosition.classList.toggle("pos-on", !!available);
    el.statusPosition.classList.toggle("pos-off", !available);
    el.statusPosition.title = available
      ? "来源：EFT 截图文件名里的坐标（只读文件名与时间戳，不读图片、不碰游戏进程）"
      : text;
  }

  function updatePositionStatus() {
    setPositionStatus(!!state.player, positionStatusText());
  }

  /** 玩家标记：光点 + 朝向箭头（两者都随缩放保持屏幕大小恒定） */
  function renderPlayer() {
    if (!el.overlay) { return; }
    if (state.playerNode && state.playerNode.parentNode) {
      state.playerNode.parentNode.removeChild(state.playerNode);
    }
    state.playerNode = null;
    var map = state.map, pos = state.player;
    if (!map || !pos) { return; }

    var unit = 1 / state.fit;
    var sx = svgX(map, pos.x, pos.z), sy = svgY(map, pos.x, pos.z);
    var g = svgEl("g", { id: "emk-player", class: "emk-player" });
    g.__emkBase = { sx: sx, sy: sy };
    g.setAttribute("transform", "translate(" + sx + " " + sy + ") scale(" + (1 / state.z) + ")");
    g.appendChild(svgEl("circle", { class: "emk-player-halo", r: 13 * unit }));
    g.appendChild(svgEl("circle", { class: "emk-player-dot", r: 4.4 * unit }));

    // 箭头本体指向 SVG 的 +x，再整体旋转到真实朝向对应的屏幕角
    var arrow = svgEl("g", { class: "emk-player-arrow", transform: "rotate(" + svgAngle(map, pos.yaw).toFixed(2) + ")" });
    arrow.appendChild(svgEl("polygon", {
      points: (function () {
        var pts = [[19, 0], [8.5, -6.6], [8.5, 6.6]];
        return pts.map(function (p) {
          return (p[0] * unit).toFixed(4) + "," + (p[1] * unit).toFixed(4);
        }).join(" ");
      })()
    }));
    g.appendChild(arrow);

    el.overlay.appendChild(g);
    state.playerNode = g;
    state.markerScaleNodes.push(g);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
