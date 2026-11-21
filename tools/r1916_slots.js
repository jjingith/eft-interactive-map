/* R19.14.1 画布验收探针：真实 DOM 坐标 / 父子关系 / 占位格 / 外观合成区 */
(function () {
  var t = document.getElementById("gw-tree");
  if (!t) return JSON.stringify({ ok: false, why: "no #gw-tree" });
  var cs = getComputedStyle(t);
  var tr = t.getBoundingClientRect();
  var rowSizes = cs.gridTemplateRows === "none" ? [] : cs.gridTemplateRows.split(" ").map(function (s) {
    return Math.round(parseFloat(s) * 10) / 10;
  });
  var colSizes = cs.gridTemplateColumns === "none" ? [] : cs.gridTemplateColumns.split(" ").map(function (s) {
    return Math.round(parseFloat(s) * 10) / 10;
  });

  var slots = [];
  var phantoms = [];
  var occupied = {};
  [].slice.call(t.children).forEach(function (el) {
    if (el.tagName.toLowerCase() === "svg") return;
    var r = el.getAttribute("data-row"), c = el.getAttribute("data-col");
    if (!r || !c) return;
    r = +r; c = +c;
    var span = +el.getAttribute("data-span") || 1;
    var rect = el.getBoundingClientRect();
    var st = getComputedStyle(el);
    var isGhost = /ghost|placeholder/i.test(el.className) || el.getAttribute("data-ghost");
    var rec = {
      slot: el.getAttribute("data-slot") || "",
      parent: el.getAttribute("data-parent") || "",
      item: el.getAttribute("data-item") || "",
      row: r, col: c, span: span,
      cls: String(el.className),
      empty: /gw-part-empty/.test(el.className),
      body: /gw-cell-body/.test(el.className),
      ammo: /gw-part-ammo/.test(el.className),
      w: Math.round(rect.width), h: Math.round(rect.height),
      border: st.borderTopWidth + " " + st.borderTopStyle,
      bg: st.backgroundColor,
      pointer: st.pointerEvents
    };
    if (isGhost) { phantoms.push(rec); return; }
    slots.push(rec);
    for (var s = 0; s < span; s++) occupied[r + "|" + (c + s)] = true;
  });

  // 空坐标命中测试：格中心最上层若是槽位卡/占位格，说明该坐标被错误占用
  var padL = parseFloat(cs.paddingLeft) || 0, padT = parseFloat(cs.paddingTop) || 0;
  var rowGap = parseFloat(cs.rowGap) || 0, colGap = parseFloat(cs.columnGap) || 0;
  var violations = [];
  for (var rr = 1; rr <= rowSizes.length; rr++) {
    for (var cc = 1; cc <= colSizes.length; cc++) {
      if (occupied[rr + "|" + cc]) continue;
      var y = tr.top + padT, x = tr.left + padL;
      for (var i = 0; i < rr - 1; i++) y += rowSizes[i] + rowGap;
      for (var j = 0; j < cc - 1; j++) x += colSizes[j] + colGap;
      var hit = document.elementFromPoint(x + colSizes[cc - 1] / 2, y + rowSizes[rr - 1] / 2);
      var guard = 0;
      while (hit && hit !== t && hit !== document.body && guard++ < 8) {
        var hc = String(hit.className || "");
        if (/ghost|placeholder/i.test(hc) || (hit.getAttribute && hit.getAttribute("data-ghost"))) {
          violations.push({ row: rr, col: cc, why: "ghost", cls: hc }); break;
        }
        if (hit.classList && (hit.classList.contains("gw-part") || hit.classList.contains("gw-cell-body"))) {
          violations.push({ row: rr, col: cc, why: "real-cell-on-empty-coord", cls: hc }); break;
        }
        hit = hit.parentElement;
      }
    }
  }

  return JSON.stringify({
    ok: true,
    url: location.href,
    innerW: window.innerWidth, innerH: window.innerHeight,
    appSrc: (document.querySelector('script[src*="app.js"]') || {}).src || "",
    rowsVar: t.style.getPropertyValue("--gw-rows"),
    colsVar: t.style.getPropertyValue("--gw-cols"),
    rowCount: rowSizes.length,
    colCount: colSizes.length,
    rowHeights: rowSizes,
    topPad: +(t.getAttribute("data-top-pad") || 0),
    treeSlots: +(t.getAttribute("data-tree-slots") || 0),
    gridH: Math.round(tr.height),
    slots: slots,
    phantomCount: phantoms.length + violations.length,
    phantoms: phantoms.concat(violations),
    emptySlots: slots.filter(function (s) { return s.slot && s.empty; }),
    bodyCell: slots.filter(function (s) { return s.body; })[0] || null,
    skinPresent: !!document.querySelector("#gw-tree .gw-skin"),
    skinTag: (function () {
      var e = document.querySelector("#gw-tree .gw-skin-tag");
      return e ? e.textContent : null;
    }()),
    ammoText: (function () {
      var e = document.querySelector("#gw-tree .gw-part-ammo");
      return e ? (e.getAttribute("aria-label") || "") : null;
    }())
  });
})()
