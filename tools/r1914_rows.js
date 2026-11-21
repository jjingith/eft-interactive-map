/* R19.14 画布六行真实高度测量（浏览器内执行，只认 computed layout） */
(function () {
  var t = document.getElementById("gw-tree");
  if (!t) return JSON.stringify({ ok: false, why: "no #gw-tree" });
  var cs = getComputedStyle(t);
  var tr = t.getBoundingClientRect();
  var rowsTpl = cs.gridTemplateRows;
  var colsTpl = cs.gridTemplateColumns;
  var rowSizes = rowsTpl === "none" ? [] : rowsTpl.split(" ").map(function (s) {
    return Math.round(parseFloat(s) * 10) / 10;
  });
  var colSizes = colsTpl === "none" ? [] : colsTpl.split(" ").map(function (s) {
    return Math.round(parseFloat(s) * 10) / 10;
  });

  // 六条网格行轨道的理论边界：从 padding-top 起按 track + row-gap 累加
  var padTop = parseFloat(cs.paddingTop) || 0;
  var padBottom = parseFloat(cs.paddingBottom) || 0;
  var rowGap = parseFloat(cs.rowGap) || 0;
  var colGap = parseFloat(cs.columnGap) || 0;
  var padLeft = parseFloat(cs.paddingLeft) || 0;
  var top0 = tr.top + padTop;
  var left0 = tr.left + padLeft;
  var trackRects = [];
  var y = top0;
  for (var i = 0; i < rowSizes.length; i++) {
    trackRects.push({
      track: i + 1,
      top: Math.round(y),
      bottom: Math.round(y + rowSizes[i]),
      height: rowSizes[i],
      visible: rowSizes[i] >= 8
    });
    y += rowSizes[i] + rowGap;
  }
  var colTrackRects = [];
  var x = left0;
  for (var ci = 0; ci < colSizes.length; ci++) {
    colTrackRects.push({
      track: ci + 1,
      left: Math.round(x),
      right: Math.round(x + colSizes[ci]),
      width: colSizes[ci]
    });
    x += colSizes[ci] + colGap;
  }

  // 每行上的真实元素（卡片/枪身/空位占位）——按列覆盖统计（枪身跨 3 列算 3 格）
  var byRow = {};
  var cover = {};
  for (var r = 1; r <= 6; r++) { byRow[r] = []; cover[r] = {}; }
  var cells = [].slice.call(t.querySelectorAll("[data-row][data-col]"));
  cells.forEach(function (el) {
    var r = +el.getAttribute("data-row");
    var c = +el.getAttribute("data-col");
    var span = +el.getAttribute("data-span") || 1;
    var rect = el.getBoundingClientRect();
    var st = getComputedStyle(el);
    (byRow[r] = byRow[r] || []).push({
      cls: el.className,
      row: r,
      col: c,
      span: span,
      slot: el.getAttribute("data-slot") || "",
      item: el.getAttribute("data-item") || "",
      ph: el.getAttribute("data-ghost") === "1",
      x: Math.round(rect.x), y: Math.round(rect.y),
      w: Math.round(rect.width), h: Math.round(rect.height),
      display: st.display, vis: st.visibility, op: st.opacity
    });
    for (var s = 0; s < span; s++) { (cover[r] = cover[r] || {})[c + s] = true; }
  });

  // 视口可见性：行轨道是否落在容器可视区内
  var parent = t.parentElement;
  var pr = parent ? parent.getBoundingClientRect() : null;
  var pst = parent ? getComputedStyle(parent) : null;
  var canvasVisible = tr.bottom <= (window.innerHeight + 1) && tr.top >= -1;

  // 父链 overflow 裁切检测
  var clipChain = [];
  var p = t.parentElement;
  while (p && p !== document.body) {
    var ps = getComputedStyle(p);
    if (/hidden|clip|auto|scroll/.test(ps.overflow + ps.overflowY + ps.overflowX)) {
      clipChain.push({
        cls: p.className,
        overflow: ps.overflow, overflowY: ps.overflowY, overflowX: ps.overflowX,
        h: Math.round(p.getBoundingClientRect().height),
        scrollH: p.scrollHeight,
        clientH: p.clientHeight
      });
    }
    p = p.parentElement;
  }

  var zeroRows = trackRects.filter(function (r) { return r.height < 8; }).map(function (r) { return r.track; });
  var rowsWithContent = Object.keys(byRow).filter(function (k) { return (byRow[k] || []).length; });
  var coverCount = {};
  for (var cr = 1; cr <= 6; cr++) {
    coverCount[cr] = Object.keys(cover[cr] || {}).length;
  }

  return JSON.stringify({
    ok: true,
    url: location.href,
    ua: navigator.userAgent,
    innerW: window.innerWidth, innerH: window.innerHeight,
    dpr: window.devicePixelRatio,
    assetV: (document.querySelector('script[src*="app.js"]') || {}).src || "",
    cssV: (document.querySelector('link[href*="style.css"]') || {}).src || "",
    grid: {
      className: t.className,
      rowsVar: t.style.getPropertyValue("--gw-rows"),
      colsVar: t.style.getPropertyValue("--gw-cols"),
      rowsTpl: rowsTpl, colsTpl: colsTpl,
      rowCount: rowSizes.length, colCount: colSizes.length,
      rowSizes: rowSizes, colSizes: colSizes,
      rowGap: rowGap, colGap: colGap,
      pad: { top: padTop, bottom: padBottom, left: padLeft },
      width: Math.round(tr.width), height: Math.round(tr.height),
      top: Math.round(tr.top), bottom: Math.round(tr.bottom),
      zeroRows: zeroRows,
      trackRects: trackRects,
      colTrackRects: colTrackRects
    },
    cellsTotal: cells.length,
    rowsWithContent: rowsWithContent,
    coverCount: coverCount,
    byRow: byRow,
    parent: pr ? {
      cls: parent.className,
      h: Math.round(pr.height), scrollH: parent.scrollHeight, clientH: parent.clientHeight,
      overflow: pst.overflow, overflowY: pst.overflowY
    } : null,
    clipChain: clipChain,
    canvasFullyInViewport: canvasVisible
  });
})()
