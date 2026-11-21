/* ==========================================================================
   R19.16 武器槽位布局校准器（calibrator.js）
   仅在 ?layoutCalibrator=1 时激活；普通页面不受影响。
   数据与引擎来源：window.GWCalib（app.js 暴露的同一套真实槽位树 + 同一个 gwBuildLayout）。
   拖动只改视觉坐标，绝不改物品 ID / 槽位 ID / 父子关系 / allow / 配装。
   ========================================================================== */
(function () {
  "use strict";

  if (!/[?&]layoutCalibrator=1/.test(location.search)) { return; }   // 普通模式零副作用

  var API = "/api/layout-calibration";
  var COLS = 9, CELL = 64, GAP = 4;

  var S = {
    guns: [], filtered: [], gunId: null, gunName: "",
    build: null,                 // GWCalib.build() 结果（自动布局）
    slots: {},                   // key -> {key,slotId,slotPath,owner,role,autoRow,autoCol,row,col,empty,item,itemName,allow}
    saved: {},                   // key -> 已保存记录（文件里的）
    overrides: {},               // key -> {logicalRow, col}
    selected: null,
    undo: [], redo: [],
    dirty: false,
    view: "manual",              // manual | auto
    topPad: 0, rows: 6,          // 自动布局基线（topPad / 行数）
    previewByKey: {},            // R19.17：校准预览最终坐标（与主程序同规则）
    previewTopPad: 0,
    previewRows: 6,
    calibDoc: null,
    presetId: null
  };

  // ---------------------------------------------------------------- 工具
  function $(id) { return document.getElementById(id); }
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) { n.className = cls; }
    if (text !== undefined) { n.textContent = text; }
    return n;
  }
  /** 非阻塞三态确认框：返回 Promise（保存并切换 / 丢弃并切换 / 取消） */
  function askChoice(text, buttons) {
    return new Promise(function (resolve) {
      var old = document.getElementById("cal-modal");
      if (old) { old.remove(); }
      var m = el("div", "cal-modal");
      m.id = "cal-modal";
      m.appendChild(el("div", "cal-modal-text", text));
      var row = el("div", "cal-modal-btns");
      buttons.forEach(function (b) {
        var btn = el("button", null, b.label);
        btn.setAttribute("data-choice", b.value);
        btn.addEventListener("click", function () {
          m.remove();
          resolve(b.value);
        });
        row.appendChild(btn);
      });
      m.appendChild(row);
      document.getElementById("cal-overlay").appendChild(m);
    });
  }

  function msg(text, kind) {
    var m = $("cal-msg");
    if (!m) { return; }
    m.textContent = text || "";
    m.className = "cal-msg" + (kind ? " " + kind : "");
  }
  function keyOf(slotPath, slotId, owner) {
    return slotPath + "|" + slotId + "|" + (owner || "");
  }

  /** R19.17：校准预览与主程序**同一条**应用规则（GWCalib.applyCalibration）。
   *  把当前 overrides 里真正移动过的槽位转成记录，套到自动布局副本上，
   *  得到最终显示坐标 / topPad / 行数——避免同一份数据两处显示不同。 */
  function previewView() {
    var records = {};
    Object.keys(S.overrides).forEach(function (k) {
      var s = S.slots[k], o = S.overrides[k];
      if (!s) { return; }
      if (o.logicalRow === s.logicalRow && o.col === s.col) { return; }
      records[k] = { logicalRow: o.logicalRow, col: o.col, role: s.role };
    });
    var L0 = S.build && S.build.layout;
    if (!L0) { return { info: { byKey: {}, topPad: S.topPad }, rows: S.rows }; }
    var L = {
      cells: L0.cells.map(function (c) {
        var nc = {};
        for (var kk in c) {
          if (Object.prototype.hasOwnProperty.call(c, kk)) { nc[kk] = c[kk]; }
        }
        return nc;
      }),
      rows: L0.rows, cols: L0.cols, topPad: L0.topPad | 0,
      grid: { rows: L0.grid.rows, cols: L0.grid.cols, cells: L0.grid.cells },
      body: { row: L0.body.row, col: L0.body.col, span: L0.body.span },
      emptyAnchors: (L0.emptyAnchors || []).map(function (a) {
        return { row: a.row, col: a.col };
      }),
      roles: L0.roles, ammoRow: L0.ammoRow, magCol: L0.magCol
    };
    var info = window.GWCalib.applyCalibration(L, S.build.installed, S.build.tree, records);
    return { L: L, info: info, rows: L.rows };
  }

  function curRows() {
    return S.view === "auto" ? S.rows : S.previewRows;
  }
  function curTopPad() {
    return S.view === "auto" ? S.topPad : S.previewTopPad;
  }
  function clonePos(o) { return { logicalRow: o.logicalRow, col: o.col }; }

  // ---------------------------------------------------------------- 初始化
  function boot() {
    if (!window.GWCalib) {
      document.addEventListener("DOMContentLoaded", boot);
      return;
    }
    buildShell();
    window.GWCalib.ensure().then(function () {
      S.guns = window.GWCalib.guns();
      S.filtered = S.guns.slice();
      renderGunList();
      return fetch(API).then(function (r) { return r.json(); });
    }).then(function (doc) {
      if (doc && doc.ok) {
        S.calibDoc = doc.data;
        renderGunList();
        msg("已读取校准文件 " + (doc.path || "") + "（" + (doc.summary.guns || 0) +
            " 把枪 / " + (doc.summary.slots || 0)  + " 条记录）", "ok");
      } else if (doc) {
        msg("读取校准文件失败：" + (doc.error || "未知错误"), "err");
      }
      // 默认选第一把有校准记录的枪，没有则选 ASH-12 / M4A1 / 第一把
      var prefer = ["5cadfbf7ae92152ac412eeef", "5447a9cd4bdc2dbd208b4567"];
      var first = null;
      for (var i = 0; i < prefer.length; i++) {
        if (S.guns.some(function (g) { return g.id === prefer[i]; })) { first = prefer[i]; break; }
      }
      selectGun(first || (S.guns[0] && S.guns[0].id));
    }).catch(function (err) {
      msg("初始化失败：" + err, "err");
    });
  }

  // ---------------------------------------------------------------- 界面骨架
  function buildShell() {
    var root = el("div", "cal-overlay");
    root.id = "cal-overlay";

    var head = el("div", "cal-head");
    head.innerHTML =
      '<span class="cal-title">武器槽位布局校准器</span>' +
      '<span class="cal-ver" id="cal-ver"></span>' +
      '<span class="spacer"></span>' +
      '<button id="cal-view-auto" aria-pressed="false" title="查看原始自动布局">自动布局</button>' +
      '<button id="cal-view-manual" aria-pressed="true" title="查看人工校准预览">校准预览</button>' +
      '<button id="cal-undo">撤销</button><button id="cal-redo">重做</button>' +
      '<button id="cal-reset-slot">还原本槽自动位</button>' +
      '<button id="cal-restore">恢复已保存</button>' +
      '<button id="cal-save">保存当前枪</button>' +
      '<button id="cal-save-all">保存全部</button>' +
      '<button id="cal-clear">清除人工校准</button>' +
      '<button id="cal-export">导出 JSON</button>' +
      '<button id="cal-import">导入 JSON</button>' +
      '<button id="cal-exit">退出</button>';
    root.appendChild(head);

    var body = el("div", "cal-body");
    body.innerHTML =
      '<div class="cal-left">' +
      '  <div class="cal-h">枪械</div>' +
      '  <input class="cal-search" id="cal-search" placeholder="搜索名称 / ID / 口径…" />' +
      '  <div class="cal-scroll"><ul class="cal-gunlist" id="cal-gunlist"></ul></div>' +
      '  <div class="cal-preset" id="cal-preset"></div>' +
      '  <dl class="cal-info" id="cal-info"></dl>' +
      '</div>' +
      '<div class="cal-center">' +
      '  <div class="cal-h">装配画布（六行九列基础网格 + 顶部扩展）——拖动卡片仅改视觉坐标</div>' +
      '  <div class="cal-diff" id="cal-diff"></div>' +
      '  <div class="cal-canvas-wrap" id="cal-canvas-wrap"><div class="cal-grid" id="cal-grid"></div></div>' +
      '  <div class="cal-msg" id="cal-msg"></div>' +
      '</div>' +
      '<div class="cal-right">' +
      '  <div class="cal-h">槽位信息与校准</div>' +
      '  <div class="cal-slots" id="cal-slots"><div class="cal-msg">点击画布上的真实槽位卡片查看详情。</div></div>' +
      '</div>';
    root.appendChild(body);
    document.body.appendChild(root);

    var ver = $("cal-ver");
    ver.textContent = "构建 " + window.GWCalib.version() +
      " · 校准数据 data/gun-layout-calibration.json";

    $("cal-search").addEventListener("input", function () {
      var q = this.value.trim().toLowerCase();
      S.filtered = !q ? S.guns.slice() : S.guns.filter(function (g) {
        return g.name.toLowerCase().indexOf(q) >= 0 || g.id.toLowerCase().indexOf(q) >= 0;
      });
      renderGunList();
    });
    $("cal-view-auto").addEventListener("click", function () { setView("auto"); });
    $("cal-view-manual").addEventListener("click", function () { setView("manual"); });
    $("cal-undo").addEventListener("click", doUndo);
    $("cal-redo").addEventListener("click", doRedo);
    $("cal-reset-slot").addEventListener("click", resetSelectedSlot);
    $("cal-restore").addEventListener("click", restoreSaved);
    $("cal-save").addEventListener("click", function () { saveGun(false); });
    $("cal-save-all").addEventListener("click", function () { saveGun(true); });
    $("cal-clear").addEventListener("click", clearGun);
    $("cal-export").addEventListener("click", exportJson);
    $("cal-import").addEventListener("click", importJson);
    $("cal-exit").addEventListener("click", function () {
      var go = function () {
        location.search = location.search.replace(/[?&]layoutCalibrator=1/, "") || "?";
      };
      if (!S.dirty) { go(); return; }
      askChoice("当前还有未保存的修改，确定退出？",
        [{ label: "保存并退出", value: "save" },
         { label: "直接退出", value: "go" },
         { label: "取消", value: "cancel" }]).then(function (choice) {
        if (choice === "cancel") { return; }
        if (choice === "save") { saveGun(false); setTimeout(go, 350); } else { go(); }
      });
    });
  }

  function setView(v) {
    S.view = v;
    $("cal-view-auto").setAttribute("aria-pressed", v === "auto" ? "true" : "false");
    $("cal-view-manual").setAttribute("aria-pressed", v === "manual" ? "true" : "false");
    renderCanvas();
  }

  // ---------------------------------------------------------------- 枪械列表
  function renderGunList() {
    var ul = $("cal-gunlist");
    ul.innerHTML = "";
    var docGuns = (S.calibDoc && S.calibDoc.guns) || {};
    S.filtered.forEach(function (g) {
      var li = el("li", null, null);
      li.setAttribute("data-gun", g.id);
      if (g.id === S.gunId) { li.setAttribute("data-on", "1"); }
      li.appendChild(el("span", null, g.name));
      if (docGuns[g.id]) { li.appendChild(el("span", "mark", " ✔已校准")); }
      li.addEventListener("click", function () { selectGun(g.id); });
      ul.appendChild(li);
    });
  }

  function renderGunInfo() {
    var dl = $("cal-info");
    dl.innerHTML = "";
    if (!S.gunId) { return; }
    var presets = window.GWCalib.presets(S.gunId);
    var slotCount = Object.keys(S.slots).length;
    var savedCount = Object.keys(S.saved).length;
    var movedCount = movedKeys().length;
    var rows = [
      ["名称", S.gunName],
      ["物品 ID", S.gunId],
      ["内置预设", (presets.list.length ? presets.defaultName : "（无）") +
        (presets.list.length > 1 ? "（共 " + presets.list.length + " 个）" : "")],
      ["真实槽位", String(slotCount)],
      ["画布行数", S.rows + " 行（含顶部扩展 " + S.topPad + "）"],
      ["已保存校准", savedCount ? savedCount + " 条" : "无"],
      ["未保存修改", S.dirty ? ("有 " + movedCount + " 处") : "无"]
    ];
    rows.forEach(function (r) {
      dl.appendChild(el("dt", null, r[0]));
      var dd = el("dd", null, r[1]);
      if (r[0] === "未保存修改" && S.dirty) { dd.className = "dirty"; }
      if (r[0] === "未保存修改" && !S.dirty) { dd.className = "ok"; }
      dl.appendChild(dd);
    });
  }

  // ---------------------------------------------------------------- 选枪 / 计算布局
  function selectGun(gunId) {
    if (!gunId) { return; }
    if (S.dirty && gunId !== S.gunId) {
      askChoice("当前枪械有未保存的修改。切换前请选择处理方式：",
        [{ label: "保存并切换", value: "save" },
         { label: "丢弃并切换", value: "drop" },
         { label: "取消", value: "cancel" }]).then(function (choice) {
        if (choice === "cancel") { return; }
        if (choice === "save") {
          saveGun(false);
          setTimeout(function () { doSelectGun(gunId); }, 350);
        } else {
          S.dirty = false;
          S.overrides = {};
          doSelectGun(gunId);
        }
      });
      return;
    }
    doSelectGun(gunId);
  }

  function doSelectGun(gunId) {
    S.gunId = gunId;
    S.selected = null;
    S.undo = []; S.redo = [];
    var preset = window.GWCalib.presets(gunId);
    S.presetId = preset.defaultId;
    S.presetInfo = preset;
    S.build = window.GWCalib.build(gunId, presetInstalled(gunId, S.presetId));
    if (!S.build) { msg("无法计算该枪槽位树", "err"); return; }
    S.gunName = S.build.name;
    S.topPad = (S.build.layout && S.build.layout.topPad) || 0;
    S.rows = (S.build.layout && S.build.layout.rows) || 6;
    S.slots = collectSlots();
    S.saved = (((S.calibDoc || {}).guns || {})[gunId] || {}).slots || {};
    S.overrides = {};
    // 从已保存记录恢复人工坐标（逻辑行 + 列）
    Object.keys(S.saved).forEach(function (k) {
      if (S.slots[k]) {
        S.overrides[k] = { logicalRow: S.saved[k].logicalRow, col: S.saved[k].col };
      }
    });
    S.dirty = false;
    renderGunList();
    renderPresetPicker();
    renderGunInfo();
    renderCanvas();
    renderSlotInfo();
    msg("已选择 " + S.gunName + "：真实槽位 " + Object.keys(S.slots).length +
        " 个，已保存校准 " + Object.keys(S.saved).length + " 条", "ok");
  }

  function collectSlots() {
    var out = {};
    var tree = S.build.tree || { nodes: {} };
    var inst = S.build.installed || {};
    var cells = (S.build.layout && S.build.layout.cells) || [];
    var byPath = {};
    cells.forEach(function (c) { byPath[c.path] = c; });
    Object.keys(tree.nodes).forEach(function (p) {
      var n = tree.nodes[p];
      var cell = byPath[p];
      if (!cell) { return; }                       // 只登记真实落位的槽位
      var parent = n.parent || "";
      var owner = parent ? (inst[parent] || "") : "";
      var k = keyOf(p, n.sid, owner);
      out[k] = {
        key: k,
        slotPath: p,
        slotId: n.sid,
        owner: owner,
        parent: parent,
        role: cell.role || cell.lane || "",
        autoRow: cell.row, autoCol: cell.col,
        logicalRow: cell.row - S.topPad, col: cell.col,
        item: inst[p] || "",
        itemName: inst[p] ? ((window.GWCalib.item(inst[p]) || {}).n || "") : "",
        empty: !inst[p],
        allow: (n.allow || []).slice(0, 40),
        anchorSlot: cell.anchorSlot || "",
        extra: cell.extraDovetail === true
      };
    });
    return out;
  }

  /** 预设 → 装配清单（切换装配状态可校准条件子槽位，例如装上瞄具底座后出现的瞄具槽） */
  function presetInstalled(gunId, presetId) {
    if (!presetId) { return null; }
    var presets = (window.__GUN_PRESETS__ || {}).presets || {};
    var p = presets[presetId];
    return (p && p.i) || null;
  }

  function renderPresetPicker() {
    var box = $("cal-preset");
    if (!box) { return; }
    box.innerHTML = "";
    var info = S.presetInfo || { list: [] };
    if (!info.list.length) {
      box.appendChild(el("div", "cal-msg", "该枪没有内置预设，使用默认装配。"));
      return;
    }
    box.appendChild(el("div", null, "装配状态（切换可校准条件子槽位）："));
    var sel = el("select");
    sel.id = "cal-preset-sel";
    info.list.forEach(function (p) {
      var opt = el("option", null, p.name + "（" + p.count + " 件）");
      opt.value = p.id;
      if (p.id === S.presetId) { opt.selected = true; }
      sel.appendChild(opt);
    });
    sel.addEventListener("change", function () {
      S.presetId = this.value;
      S.build = window.GWCalib.build(S.gunId, presetInstalled(S.gunId, S.presetId));
      if (!S.build) { msg("无法计算该装配状态的槽位树", "err"); return; }
      S.topPad = (S.build.layout && S.build.layout.topPad) || 0;
      S.rows = (S.build.layout && S.build.layout.rows) || 6;
      S.slots = collectSlots();
      S.overrides = {};
      S.dirty = false;
      S.undo = []; S.redo = [];
      renderCanvas(); renderGunInfo(); renderSlotInfo();
      msg("已切换装配状态：" + sel.options[sel.selectedIndex].text +
          "；真实槽位 " + Object.keys(S.slots).length + " 个", "ok");
    });
    box.appendChild(sel);
  }

  function movedKeys() {
    return Object.keys(S.overrides).filter(function (k) {
      var s = S.slots[k];
      return s && (s.logicalRow !== S.overrides[k].logicalRow || s.col !== S.overrides[k].col);
    });
  }

  // ---------------------------------------------------------------- 画布
  function renderCanvas() {
    var grid = $("cal-grid");
    grid.innerHTML = "";
    // R19.17：manual 视图 = 主程序同一条校准规则（applyCalibration）；auto 视图 = 纯自动布局
    if (S.view !== "auto") {
      var pv = previewView();
      S.previewByKey = (pv.info && pv.info.byKey) || {};
      S.previewTopPad = (pv.info && pv.info.topPad) | 0;
      S.previewRows = pv.rows || (6 + S.previewTopPad);
    }
    var rowsNow = curRows();
    grid.style.gridTemplateRows = "repeat(" + rowsNow + ", " + (CELL - 4) + "px)";

    // 1) 网格辅助线（仅校准器可见；不是可安装槽位，不响应事件）
    for (var r = 1; r <= rowsNow; r++) {
      for (var c = 1; c <= COLS; c++) {
        var g = el("div", "cal-gcell");
        g.setAttribute("data-row", String(r));
        g.setAttribute("data-col", String(c));
        if (r === 3 && c >= 6 && c <= 8) { g.setAttribute("data-body", "1"); }
        g.style.gridRow = String(r);
        g.style.gridColumn = String(c);
        grid.appendChild(g);
        if (c === 1) {
          var rl = el("div", "cal-rowlab", "r" + r);
          rl.style.top = ((r - 1) * (CELL + GAP) + 22) + "px";
          grid.appendChild(rl);
        }
        if (r === 1) {
          var cl = el("div", "cal-collab", "c" + c);
          cl.style.left = ((c - 1) * (CELL + GAP) + CELL / 2 - 6) + "px";
          grid.appendChild(cl);
        }
      }
    }

    // 2) 真实槽位卡片
    Object.keys(S.slots).forEach(function (k) {
      var s = S.slots[k];
      var pos, row;
      if (S.view === "auto") {
        pos = { logicalRow: s.autoRow - S.topPad, col: s.autoCol };
        row = pos.logicalRow + S.topPad;
      } else if (S.previewByKey[k]) {
        row = S.previewByKey[k].row;
        pos = { logicalRow: row - S.previewTopPad, col: S.previewByKey[k].col };
      } else {
        pos = S.overrides[k] || { logicalRow: s.logicalRow, col: s.col };
        row = pos.logicalRow + S.previewTopPad;
      }
      var card = el("div", "cal-card");
      card.setAttribute("data-key", k);
      card.setAttribute("data-slot", s.slotPath);
      card.setAttribute("data-row", String(row));
      card.setAttribute("data-col", String(pos.col));
      if (S.selected === k) { card.classList.add("sel"); }
      if (s.slotPath === "mod_reciever" || s.parent === "" && /reciever|receiver/.test(s.slotId)) {
        card.setAttribute("data-body", "1");
      }
      var title = el("div", "sid", s.slotId);
      card.appendChild(title);
      var itm = el("div", "itm", s.empty ? "（空槽 · 真实槽位）" : s.itemName);
      card.appendChild(itm);
      var tag = el("div", null, null);
      tag.innerHTML = '<span class="coord">r' + row + "c" + pos.col + "</span>";
      var saved = S.saved[k];
      var isMoved = saved && (saved.logicalRow !== s.autoRow - S.topPad || saved.col !== s.autoCol);
      if (isMoved) {
        var t2 = el("span", "tag moved", "已校准");
        tag.appendChild(t2);
      }
      card.appendChild(tag);
      if (S.view === "auto") { card.style.cursor = "default"; }
      card.addEventListener("pointerdown", onCardDown);
      card.addEventListener("click", function (ev) {
        ev.stopPropagation();
        S.selected = k;
        renderCanvas();
        renderSlotInfo();
      });
      card.style.gridRow = String(Math.max(1, Math.min(rowsNow, row)));
      card.style.gridColumn = String(Math.max(1, Math.min(COLS, pos.col)));
      grid.appendChild(card);
    });

    renderDiff();
  }

  function renderDiff() {
    var box = $("cal-diff");
    var moved = movedKeys();
    if (!moved.length) {
      box.innerHTML = S.view === "auto"
        ? "当前显示：<b>原始自动布局</b>（未应用任何人工校准）"
        : "当前显示：<b>校准预览</b>；与自动布局一致，无差异。";
      return;
    }
    var parts = moved.slice(0, 8).map(function (k) {
      var s = S.slots[k], o = S.overrides[k];
      return '<span class="m">' + s.slotId + " " +
        "r" + (s.autoRow - S.topPad) + "c" + s.autoCol + " → r" + o.logicalRow + "c" + o.col + "</span>";
    });
    box.innerHTML = "已移动 <b>" + moved.length + "</b> 处（逻辑坐标，不含顶部扩展偏移）：" +
      parts.join("；") + (moved.length > 8 ? " …" : "") +
      (S.dirty ? ' · <b style="color:#a11b1b">未保存</b>' : " · 已与文件同步");
  }

  // ---------------------------------------------------------------- 拖动
  var drag = null;
  function onCardDown(ev) {
    if (S.view !== "manual") { return; }
    var card = ev.currentTarget;
    var k = card.getAttribute("data-key");
    var s = S.slots[k];
    if (!s) { return; }
    S.selected = k;
    drag = {
      key: k, card: card,
      start: { logicalRow: (S.overrides[k] || s).logicalRow, col: (S.overrides[k] || s).col },
      moved: false
    };
    card.classList.add("dragging");
    card.setPointerCapture && card.setPointerCapture(ev.pointerId);
    card.addEventListener("pointermove", onCardMove);
    card.addEventListener("pointerup", onCardUp);
    card.addEventListener("pointercancel", onCardUp);
    ev.preventDefault();
  }

  function cellFromPoint(x, y) {
    var g = $("cal-grid");
    var rect = g.getBoundingClientRect();
    var relX = x - rect.left, relY = y - rect.top;
    var col = Math.floor(relX / (CELL + GAP)) + 1;
    var row = Math.floor(relY / (CELL + GAP)) + 1;
    return { row: row, col: col, inGrid: row >= 1 && row <= curRows() && col >= 1 && col <= COLS };
  }

  function onCardMove(ev) {
    if (!drag) { return; }
    drag.moved = true;
    var t = cellFromPoint(ev.clientX, ev.clientY);
    clearDropHint();
    if (!t.inGrid) { return; }
    var key = drag.key;
    var res = planMove(key, t.row - S.topPad, t.col);
    var cell = document.querySelector('.cal-gcell[data-row="' + t.row + '"][data-col="' + t.col + '"]');
    if (cell) { cell.setAttribute("data-drop", res.ok ? "1" : "bad"); }
  }

  function onCardUp(ev) {
    if (!drag) { return; }
    var card = drag.card;
    card.classList.remove("dragging");
    card.removeEventListener("pointermove", onCardMove);
    card.removeEventListener("pointerup", onCardUp);
    card.removeEventListener("pointercancel", onCardUp);
    clearDropHint();
    if (drag.moved) {
      var t = cellFromPoint(ev.clientX, ev.clientY);
      if (t.inGrid) {
        applyMove(drag.key, t.row - S.topPad, t.col);
      }
    } else {
      renderCanvas();
      renderSlotInfo();
    }
    drag = null;
  }

  function clearDropHint() {
    [].forEach.call(document.querySelectorAll('.cal-gcell[data-drop]'), function (c) {
      c.removeAttribute("data-drop");
    });
  }

  function currentPos(k) {
    var s = S.slots[k];
    return S.overrides[k] || { logicalRow: s.logicalRow, col: s.col };
  }

  /** 计算一次放置的结果：ok / reason / swapWith / body */
  function planMove(k, logicalRow, col) {
    if (logicalRow < -6 || logicalRow > 6 || col < 1 || col > COLS) {
      return { ok: false, reason: "目标超出网格范围 r" + logicalRow + "c" + col };
    }
    // R19.17：本体区按逻辑行判定（显示行 − topPad），与主程序 gwCalibForbidden 同口径
    if (logicalRow === 3 && col >= 6 && col <= 8) {
      return { ok: false, reason: "目标是枪械本体占用区（逻辑 r3c6–c8），不允许放置" };
    }
    var hit = null;
    Object.keys(S.slots).forEach(function (kk) {
      if (kk === k) { return; }
      var p = currentPos(kk);
      if (p.logicalRow === logicalRow && p.col === col) { hit = kk; }
    });
    if (hit) {
      return { ok: true, swapWith: hit };
    }
    return { ok: true };
  }

  function applyMove(k, logicalRow, col) {
    var plan = planMove(k, logicalRow, col);
    if (!plan.ok) {
      msg("无法放置：" + plan.reason, "err");
      renderCanvas();
      return;
    }
    var before = clonePos(currentPos(k));
    var after = { logicalRow: logicalRow, col: col };
    var step = { moves: [{ key: k, before: before, after: after }] };
    S.overrides[k] = after;
    if (plan.swapWith) {
      var wk = plan.swapWith;
      var wb = clonePos(currentPos(wk));
      S.overrides[wk] = clonePos(before);
      step.moves.push({ key: wk, before: wb, after: clonePos(before) });
      msg("已与 " + S.slots[wk].slotId + " 交换位置（未丢失任何槽位）", "ok");
    } else {
      msg("已移动 " + S.slots[k].slotId + " → r" + logicalRow + "c" + col + "（未保存）", "ok");
    }
    S.undo.push(step);
    S.redo = [];
    S.dirty = true;
    S.selected = k;
    renderCanvas();
    renderGunInfo();
    renderSlotInfo();
  }

  function doUndo() {
    var step = S.undo.pop();
    if (!step) { msg("没有可撤销的操作"); return; }
    step.moves.forEach(function (m) {
      if (m.before) { S.overrides[m.key] = clonePos(m.before); }
      else { delete S.overrides[m.key]; }
    });
    S.redo.push(step);
    S.dirty = true;
    renderCanvas(); renderGunInfo();
    msg("已撤销一步", "ok");
  }
  function doRedo() {
    var step = S.redo.pop();
    if (!step) { msg("没有可重做的操作"); return; }
    step.moves.forEach(function (m) {
      S.overrides[m.key] = clonePos(m.after);
    });
    S.undo.push(step);
    S.dirty = true;
    renderCanvas(); renderGunInfo();
    msg("已重做一步", "ok");
  }

  function resetSelectedSlot() {
    var k = S.selected;
    if (!k || !S.slots[k]) { msg("请先点选一个槽位卡片", "err"); return; }
    var before = S.overrides[k] ? clonePos(S.overrides[k]) : null;
    delete S.overrides[k];
    S.undo.push({ moves: [{ key: k, before: before, after: { logicalRow: S.slots[k].logicalRow, col: S.slots[k].col } }] });
    S.redo = [];
    S.dirty = true;
    renderCanvas(); renderGunInfo(); renderSlotInfo();
    msg("已把 " + S.slots[k].slotId + " 还原到自动布局位置", "ok");
  }

  // ---------------------------------------------------------------- 右侧信息
  function renderSlotInfo() {
    var box = $("cal-slots");
    box.innerHTML = "";
    var k = S.selected;
    if (!k || !S.slots[k]) {
      box.appendChild(el("div", "cal-msg", "点击画布上的真实槽位卡片查看详情。"));
      return;
    }
    var s = S.slots[k];
    var pos = currentPos(k);
    var kv = el("dl", "kv");
    var ownerName = s.owner ? ((window.GWCalib.item(s.owner) || {}).n || s.owner) : "（枪身根级）";
    var rows = [
      ["枪械", S.gunName],
      ["枪械 ID", S.gunId],
      ["槽位 ID", s.slotId],
      ["完整路径", s.slotPath],
      ["父槽位", s.parent || "（根级）"],
      ["拥有者物品", ownerName + (s.owner ? "（" + s.owner + "）" : "")],
      ["当前安装", s.empty ? "（空槽）" : (s.itemName + "（" + s.item + "）")],
      ["自动坐标", "r" + (s.autoRow - S.topPad) + "c" + s.autoCol + "（显示 r" + s.autoRow + "c" + s.autoCol + "）"],
      ["校准坐标", "r" + pos.logicalRow + "c" + pos.col + "（显示 r" + (pos.logicalRow + curTopPad()) + "c" + pos.col + "）"],
      ["topPad", String(curTopPad()) + (S.view === "auto" ? "（自动布局）" : "（校准预览，顶部扩展按最终坐标重算）")],
      ["布局角色", s.role || "—"],
      ["固定锚点", s.anchorSlot ? ("锚于 " + s.anchorSlot) : (s.role && /hammer|trigger|dovetail|stock|mag|grip|bad|charge|receiver/i.test(s.role) ? "是（角色锚点）" : "否")],
      ["条件子槽", s.parent && s.owner ? "是（父件 " + s.owner + " 提供）" : "否"],
      ["身份键", s.key]
    ];
    rows.forEach(function (r) {
      kv.appendChild(el("dt", null, r[0]));
      kv.appendChild(el("dd", null, r[1]));
    });
    box.appendChild(kv);

    var allowBox = el("div", "cal-allow");
    allowBox.appendChild(el("div", null, "允许安装（allow，前 " + s.allow.length + " 项）："));
    s.allow.forEach(function (id) {
      var it = window.GWCalib.item(id) || {};
      allowBox.appendChild(el("div", null, (it.n || id) + "（" + id + "）"));
    });
    box.appendChild(allowBox);

    var row = el("div", "coordrow");
    row.appendChild(el("span", null, "行 r"));
    var inR = el("input"); inR.id = "cal-in-row"; inR.value = String(pos.logicalRow);
    row.appendChild(inR);
    row.appendChild(el("span", null, "列 c"));
    var inC = el("input"); inC.id = "cal-in-col"; inC.value = String(pos.col);
    row.appendChild(inC);
    var btn = el("button", null, "应用坐标");
    btn.addEventListener("click", function () {
      var r = parseInt($("cal-in-row").value, 10);
      var c = parseInt($("cal-in-col").value, 10);
      if (isNaN(r) || isNaN(c)) { msg("行列必须是整数", "err"); return; }
      applyMove(k, r, c);
    });
    row.appendChild(btn);
    box.appendChild(row);

    var noteRow = el("div", "coordrow");
    noteRow.appendChild(el("span", null, "备注"));
    var inN = el("input"); inN.id = "cal-in-note"; inN.style.width = "170px";
    inN.value = (S.saved[k] && S.saved[k].note) || "";
    noteRow.appendChild(inN);
    box.appendChild(noteRow);

    var warn = el("div", "cal-msg");
    warn.textContent = "拖动 / 填写坐标只改变视觉布局，不会改动物品 ID、槽位 ID、父子关系、allow 清单或实际配装。";
    box.appendChild(warn);
  }

  // ---------------------------------------------------------------- 保存 / 恢复 / 清除
  function buildGunPayload() {
    var slots = {};
    // R19.21 修复：本次会话**碰过**的槽位一律以当前 override 落盘（即使拖回自动位），
    // 并保留旧注记；绝不再回落到 S.saved 的旧坐标——否则「拖回自动位 + 保存」会把
    // 上一次保存的坐标原样写回（保存结果与界面显示不一致的陈旧值 bug）。
    Object.keys(S.overrides).forEach(function (k) {
      var s = S.slots[k];
      if (!s) { return; }
      var o = S.overrides[k];
      var prev = S.saved[k] || {};
      slots[k] = {
        slotId: s.slotId,
        slotPath: s.slotPath,
        ownerItemId: s.owner,
        logicalRow: o.logicalRow,
        col: o.col,
        topPad: S.topPad,
        displayRow: o.logicalRow + S.topPad,
        role: s.role,
        source: "manual",
        note: (($("cal-in-note") && S.selected === k && $("cal-in-note").value) || prev.note || "").slice(0, 200),
        autoRow: s.autoRow,
        autoCol: s.autoCol
      };
    });
    // 保留未在本次会话改动、但文件里已有的记录
    Object.keys(S.saved).forEach(function (k) {
      if (!slots[k] && !S.overrides[k] && S.saved[k]) { slots[k] = S.saved[k]; }
    });
    var history = (((S.calibDoc || {}).guns || {})[S.gunId] || {}).history || [];
    history = history.slice(-49).concat([{
      at: new Date().toISOString().slice(0, 19),
      changed: Object.keys(slots).length
    }]);
    return { name: S.gunName, slots: slots, history: history };
  }

  function saveGun(all) {
    var body = all
      ? { action: "save-all", guns: (function () {
          var o = {}; o[S.gunId] = buildGunPayload(); return o;
        })() }
      : { action: "save", gunId: S.gunId, gun: buildGunPayload() };
    fetch(API, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    }).then(function (r) { return r.json(); }).then(function (res) {
      if (!res.ok) { msg("保存失败：" + (res.error || "未知错误"), "err"); return; }
      S.calibDoc = res.data;
      S.saved = ((res.data.guns || {})[S.gunId] || {}).slots || {};
      S.dirty = false;
      renderGunList(); renderGunInfo(); renderCanvas();
      msg("已保存到 " + res.path + "（" + res.summary.guns + " 把枪 / " +
          res.summary.slots + " 条；上一版已备份为 .bak.json）", "ok");
    }).catch(function (err) { msg("保存失败：" + err, "err"); });
  }

  function restoreSaved() {
    fetch(API).then(function (r) { return r.json(); }).then(function (res) {
      if (!res.ok) { msg("读取失败：" + (res.error || ""), "err"); return; }
      S.calibDoc = res.data;
      S.saved = ((res.data.guns || {})[S.gunId] || {}).slots || {};
      S.overrides = {};
      Object.keys(S.saved).forEach(function (k) {
        if (S.slots[k]) { S.overrides[k] = { logicalRow: S.saved[k].logicalRow, col: S.saved[k].col }; }
      });
      S.dirty = false;
      S.undo = []; S.redo = [];
      renderCanvas(); renderGunInfo(); renderSlotInfo();
      msg("已恢复该枪上次保存的布局（丢弃未保存修改）", "ok");
    }).catch(function (err) { msg("恢复失败：" + err, "err"); });
  }

  function clearGun() {
    askChoice("将清除 " + S.gunName + " 的全部人工校准记录（不影响真实槽位数据 / 预设）。确定？",
      [{ label: "确认清除", value: "ok" }, { label: "取消", value: "cancel" }]).then(function (choice) {
    if (choice !== "ok") { return; }
    fetch(API, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "clear", gunId: S.gunId })
    }).then(function (r) { return r.json(); }).then(function (res) {
      if (!res.ok) { msg("清除失败：" + (res.error || ""), "err"); return; }
      S.calibDoc = res.data;
      S.saved = {};
      S.overrides = {};
      S.dirty = false;
      renderGunList(); renderCanvas(); renderGunInfo(); renderSlotInfo();
      msg("已清除该枪的人工校准（文件中已备份上一版）", "ok");
    }).catch(function (err) { msg("清除失败：" + err, "err"); });
    });
  }

  // ---------------------------------------------------------------- 导入 / 导出
  function exportJson() {
    fetch(API).then(function (r) { return r.json(); }).then(function (res) {
      if (!res.ok) { msg("导出失败：" + (res.error || ""), "err"); return; }
      var blob = new Blob([JSON.stringify(res.data, null, 1)], { type: "application/json" });
      var a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = "gun-layout-calibration.json";
      a.click();
      URL.revokeObjectURL(a.href);
      msg("已导出 JSON（内容与 data/gun-layout-calibration.json 一致）", "ok");
    });
  }

  function importJson() {
    var input = document.createElement("input");
    input.type = "file";
    input.accept = "application/json,.json";
    input.addEventListener("change", function () {
      var f = input.files && input.files[0];
      if (!f) { return; }
      var reader = new FileReader();
      reader.onload = function () {
        var data;
        try { data = JSON.parse(reader.result); }
        catch (e) { msg("导入失败：不是合法 JSON", "err"); return; }
        fetch(API, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "import", data: data })
        }).then(function (r) { return r.json(); }).then(function (res) {
          if (!res.ok) {
            msg("导入被拒绝：" + (res.error || "结构不合法") + "（已有数据未被覆盖）", "err");
            return;
          }
          S.calibDoc = res.data;
          S.saved = ((res.data.guns || {})[S.gunId] || {}).slots || {};
          renderGunList(); renderGunInfo(); renderCanvas();
          msg("导入成功：" + res.summary.guns + " 把枪 / " + res.summary.slots + " 条", "ok");
        }).catch(function (err) { msg("导入失败：" + err, "err"); });
      };
      reader.readAsText(f, "utf-8");
    });
    input.click();
  }

  boot();
})();
