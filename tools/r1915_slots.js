/* R19.14 布局修订：空坐标隐藏 / 真实空槽保留 —— 浏览器内测量 */
(function () {
  function measure(label) {
    var t = document.getElementById("gw-tree");
    if (!t) return { ok: false, label: label, why: "no #gw-tree" };
    var cs = getComputedStyle(t);
    var rowSizes = cs.gridTemplateRows === "none" ? [] : cs.gridTemplateRows.split(" ").map(function (s) {
      return Math.round(parseFloat(s) * 10) / 10;
    });
    var colSizes = cs.gridTemplateColumns === "none" ? [] : cs.gridTemplateColumns.split(" ").map(function (s) {
      return Math.round(parseFloat(s) * 10) / 10;
    });

    // 全部网格子元素（含枪身 / 槽位卡 / 子弹格）
    var nodes = [].slice.call(t.children).filter(function (el) {
      return el.tagName.toLowerCase() !== "svg";
    });
    var slots = [];
    var phantoms = [];
    var occupied = {};
    nodes.forEach(function (el) {
      var r = el.getAttribute("data-row");
      var c = el.getAttribute("data-col");
      var span = +el.getAttribute("data-span") || 1;
      if (!r || !c) return;
      r = +r; c = +c;
      var rect = el.getBoundingClientRect();
      var st = getComputedStyle(el);
      var isGhost = /ghost|placeholder/i.test(el.className) || el.getAttribute("data-ghost");
      var rec = {
        cls: String(el.className), row: r, col: c, span: span,
        slot: el.getAttribute("data-slot") || "",
        item: el.getAttribute("data-item") || "",
        isGhost: !!isGhost,
        empty: /gw-part-empty/.test(el.className),
        x: Math.round(rect.x), y: Math.round(rect.y),
        w: Math.round(rect.width), h: Math.round(rect.height),
        border: st.borderTopWidth + " " + st.borderTopStyle + " " + st.borderTopColor,
        bg: st.backgroundColor,
        pointer: st.pointerEvents
      };
      if (isGhost) {
        phantoms.push(rec);
        return;
      }
      slots.push(rec);
      for (var s = 0; s < span; s++) occupied[r + "|" + (c + s)] = true;
    });

    // 真实空槽（来自槽位树、未安装配件）统计
    var emptySlots = slots.filter(function (s) { return s.slot && s.empty; });

    // 空坐标处是否有可见 DOM（用元素中心点命中测试：在空坐标中心找最上层元素）
    var phantomByHit = [];
    var gridRect = t.getBoundingClientRect();
    var padL = parseFloat(cs.paddingLeft) || 0;
    var padT = parseFloat(cs.paddingTop) || 0;
    var rowGap = parseFloat(cs.rowGap) || 0;
    var colGap = parseFloat(cs.columnGap) || 0;
    for (var r = 1; r <= rowSizes.length; r++) {
      for (var c = 1; c <= colSizes.length; c++) {
        if (occupied[r + "|" + c]) continue;
        // 计算该格中心
        var y = gridRect.top + padT, x = gridRect.left + padL;
        for (var i = 0; i < r - 1; i++) y += rowSizes[i] + rowGap;
        for (var j = 0; j < c - 1; j++) x += colSizes[j] + colGap;
        var cx = x + colSizes[c - 1] / 2, cy = y + rowSizes[r - 1] / 2;
        var hit = document.elementFromPoint(cx, cy);
        while (hit && hit !== t && hit !== document.body) {
          var hcls = String(hit.className || "");
          if (/gw-cell-ghost|ghost|placeholder/i.test(hcls) || hit.getAttribute && hit.getAttribute("data-ghost")) {
            phantomByHit.push({ row: r, col: c, cls: hcls });
            break;
          }
          // 槽位卡 / 枪身 / 子弹格不该出现在空坐标中心
          if (hit.classList && (hit.classList.contains("gw-part") || hit.classList.contains("gw-cell-body"))) {
            phantomByHit.push({ row: r, col: c, cls: hcls, note: "real-card-center-on-empty-coord" });
            break;
          }
          hit = hit.parentElement;
        }
      }
    }

    return {
      ok: true,
      label: label,
      url: location.href,
      innerW: window.innerWidth, innerH: window.innerHeight,
      appSrc: (document.querySelector('script[src*="app.js"]') || {}).src || "",
      rowCount: rowSizes.length,
      colCount: colSizes.length,
      rowHeights: rowSizes,
      colWidths: colSizes,
      gridH: Math.round(gridRect.height),
      slotCount: slots.length,
      emptySlotCount: emptySlots.length,
      emptySlots: emptySlots.map(function (s) {
        return { slot: s.slot, row: s.row, col: s.col, w: s.w, h: s.h, border: s.border, pointer: s.pointer };
      }),
      phantomCount: phantoms.length + phantomByHit.length,
      phantoms: phantoms.concat(phantomByHit),
      slots: slots.map(function (s) {
        return { slot: s.slot, row: s.row, col: s.col, span: s.span, item: s.item,
                 empty: s.empty, w: s.w, h: s.h, x: s.x, y: s.y };
      }),
      occupied: Object.keys(occupied)
    };
  }

  // 槽位树规模：优先读画布上的真实槽位树钩子（renderGunTree 写入），
  // 不依赖闭包内的 ensureGunState（探针无法直接调用）。
  var treeEl = document.getElementById("gw-tree");
  var treeSlotCount = treeEl ? +(treeEl.getAttribute("data-tree-slots") || 0) : 0;
  var placedCells = treeEl ? +(treeEl.getAttribute("data-placed-cells") || 0) : 0;

  var out = measure("current");
  out.treeSlotCount = treeSlotCount;
  out.placedCells = placedCells;
  out.gunId = (document.getElementById("gw-current") || {}).textContent || null;
  return JSON.stringify(out);
})()
