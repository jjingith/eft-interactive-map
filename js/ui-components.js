/* ============================================================================
 * ui-components.js —— 项目通用组件（原生 JS，无依赖，离线可用，R19.24）
 * ----------------------------------------------------------------------------
 * 规范：docs/ui-system/design-spec.md §4
 * 用法：<script src="js/ui-components.js"></script> → window.GWUI
 *
 * 设计约束（写代码前先读）：
 *   1) 组件只管"展示 + 基础交互"，不碰任何业务数据（不知道任务/枪械/弹药）。
 *   2) 每个组件接受 className 追加钩子类，但钩子类不得改变视觉。
 *   3) 浮层（dialog / menu / tooltip / toast）一律挂 document.body，避免被父容器裁切。
 *   4) 同一个组件不会被重复插入：dialog 同时只开一个实例；menu 全局单例；tooltip 复用同一个节点。
 *   5) 所有可关闭的东西都返回 close()，并且会恢复调用前的焦点。
 * ==========================================================================*/
(function () {
  "use strict";

  var VERSION = "1.0";
  var uid = 0;
  function nextId(prefix) { uid += 1; return "ui-" + prefix + "-" + uid; }

  // ---------------------------------------------------------------- 基础
  function el(tag, opts) {
    opts = opts || {};
    var node = document.createElement(tag);
    if (opts.cls) { node.className = opts.cls; }
    if (opts.text != null) { node.textContent = String(opts.text); }
    if (opts.html != null) { node.innerHTML = opts.html; }   // 仅用于受控图标片段
    if (opts.attrs) {
      Object.keys(opts.attrs).forEach(function (k) {
        var v = opts.attrs[k];
        if (v === false || v == null) { return; }
        if (v === true) { node.setAttribute(k, ""); return; }
        node.setAttribute(k, String(v));
      });
    }
    if (opts.style) {
      Object.keys(opts.style).forEach(function (k) { node.style.setProperty(k, opts.style[k]); });
    }
    (opts.children || []).forEach(function (c) {
      if (c) { node.appendChild(typeof c === "string" ? document.createTextNode(c) : c); }
    });
    if (opts.on) {
      Object.keys(opts.on).forEach(function (evt) { node.addEventListener(evt, opts.on[evt]); });
    }
    return node;
  }

  function svgIcon(path, size) {
    var s = size || 16;
    var wrap = document.createElement("span");
    wrap.className = "ui-btn__icon";
    wrap.innerHTML = '<svg viewBox="0 0 16 16" width="' + s + '" height="' + s +
      '" aria-hidden="true" focusable="false"><path fill="currentColor" d="' + path + '"/></svg>';
    return wrap;
  }

  var ICONS = {
    close: "M3 3l10 10M13 3L3 13",
    check: "M2 8l4 4 8-8",
    warn: "M8 1l7 13H1z",
    info: "M8 1a7 7 0 100 14A7 7 0 008 1zm0 3a1 1 0 110 2 1 1 0 010-2zm1 4v4H7V8z",
    chevron: "M4 6l4 4 4-4"
  };

  // ---------------------------------------------------------------- 按钮
  function btn(opts) {
    opts = opts || {};
    var cls = ["ui-btn"];
    if (opts.variant && opts.variant !== "default") { cls.push("ui-btn--" + opts.variant); }
    if (opts.size) { cls.push("ui-btn--" + opts.size); }
    if (opts.className) { cls.push(opts.className); }
    var node = el("button", {
      cls: cls.join(" "),
      attrs: {
        type: opts.type || "button",
        title: opts.title || null,
        "aria-label": opts.ariaLabel || null,
        "aria-pressed": opts.pressed == null ? null : String(!!opts.pressed),
        "aria-busy": opts.busy ? "true" : null,
        disabled: !!opts.disabled,
        "aria-disabled": opts.disabled ? "true" : null
      }
    });
    if (opts.icon) { node.appendChild(typeof opts.icon === "string" ? svgIcon(opts.icon) : opts.icon); }
    if (opts.label != null) { node.appendChild(el("span", { cls: "ui-btn__label", text: opts.label })); }
    if (opts.onClick) { node.addEventListener("click", opts.onClick); }
    return node;
  }

  // ---------------------------------------------------------------- 表单
  function field(opts) {
    opts = opts || {};
    var wrap = el("label", { cls: "ui-field" + (opts.error ? " is-error" : ""), attrs: { for: opts.id || null } });
    if (opts.label) { wrap.appendChild(el("span", { cls: "ui-field__label", text: opts.label })); }
    var control = opts.control;
    if (control) {
      if (opts.id) { control.id = opts.id; }
      wrap.appendChild(control);
    }
    if (opts.error) { wrap.appendChild(el("span", { cls: "ui-field__error", text: opts.error })); }
    else if (opts.hint) { wrap.appendChild(el("span", { cls: "ui-field__hint", text: opts.hint })); }
    return wrap;
  }

  function input(opts) {
    opts = opts || {};
    var cls = ["ui-input"];
    if (opts.num) { cls.push("ui-input--num"); }
    if (opts.size === "sm") { cls.push("ui-input--sm"); }
    if (opts.className) { cls.push(opts.className); }
    var node = el("input", {
      cls: cls.join(" "),
      attrs: {
        type: opts.type || "text",
        placeholder: opts.placeholder || null,
        value: opts.value == null ? null : opts.value,
        name: opts.name || null,
        "aria-label": opts.ariaLabel || opts.label || null,
        "aria-invalid": opts.invalid ? "true" : null,
        disabled: !!opts.disabled,
        min: opts.min == null ? null : opts.min,
        max: opts.max == null ? null : opts.max,
        step: opts.step == null ? null : opts.step,
        autocomplete: opts.autocomplete || "off"
      }
    });
    if (opts.onInput) { node.addEventListener("input", function (ev) { opts.onInput(node.value, ev); }); }
    if (opts.onChange) { node.addEventListener("change", function (ev) { opts.onChange(node.value, ev); }); }
    return node;
  }

  function select(opts) {
    opts = opts || {};
    var node = el("select", {
      cls: "ui-select" + (opts.className ? " " + opts.className : ""),
      attrs: {
        "aria-label": opts.ariaLabel || opts.label || null,
        disabled: !!opts.disabled
      }
    });
    (opts.options || []).forEach(function (o) {
      var opt = el("option", { text: o.label });
      opt.value = o.value;
      if (String(o.value) === String(opts.value)) { opt.selected = true; }
      if (o.disabled) { opt.disabled = true; }
      node.appendChild(opt);
    });
    if (opts.onChange) { node.addEventListener("change", function () { opts.onChange(node.value); }); }
    return node;
  }

  function check(opts) {
    opts = opts || {};
    var id = opts.id || nextId("check");
    var wrap = el("label", {
      cls: "ui-check" + (opts.radio ? " ui-check--radio" : "") + (opts.className ? " " + opts.className : "")
    });
    var box = el("input", {
      attrs: { type: opts.radio ? "radio" : "checkbox", id: id, name: opts.name || null,
               disabled: !!opts.disabled, checked: !!opts.checked }
    });
    if (opts.value != null) { box.value = opts.value; }
    wrap.appendChild(box);
    wrap.appendChild(el("span", { cls: "ui-check__box", attrs: { "aria-hidden": "true" } }));
    wrap.appendChild(el("span", { cls: "ui-check__label", text: opts.label == null ? "" : opts.label }));
    if (opts.onChange) {
      box.addEventListener("change", function () { opts.onChange(box.checked, box); });
    }
    wrap.input = box;
    return wrap;
  }

  // ---------------------------------------------------------------- 标签页
  function tabs(opts) {
    opts = opts || {};
    var wrap = el("div", {
      cls: "ui-tabs" + (opts.segmented ? " ui-tabs--segmented" : "") + (opts.className ? " " + opts.className : ""),
      attrs: { role: "tablist", "aria-label": opts.ariaLabel || "标签页" }
    });
    var buttons = [];
    (opts.items || []).forEach(function (item, i) {
      var b = el("button", {
        cls: "ui-tab",
        attrs: {
          type: "button", role: "tab",
          "aria-selected": String(item.key === opts.value),
          "aria-controls": item.controls || null,
          tabindex: item.key === opts.value ? "0" : "-1",
          disabled: !!item.disabled
        },
        text: item.label
      });
      if (item.title) { b.title = item.title; }
      b.dataset.key = item.key;
      b.addEventListener("click", function () {
        if (item.disabled) { return; }
        setValue(item.key);
        if (opts.onChange) { opts.onChange(item.key); }
      });
      b.addEventListener("keydown", function (ev) {
        var delta = ev.key === "ArrowRight" ? 1 : (ev.key === "ArrowLeft" ? -1 : 0);
        if (!delta) { return; }
        ev.preventDefault();
        var next = i;
        for (var step = 0; step < buttons.length; step++) {
          next = (next + delta + buttons.length) % buttons.length;
          if (!buttons[next].disabled) { break; }
        }
        buttons[next].focus();
        buttons[next].click();
      });
      buttons.push(b);
      wrap.appendChild(b);
    });
    function setValue(key) {
      buttons.forEach(function (b) {
        var on = b.dataset.key === String(key);
        b.setAttribute("aria-selected", String(on));
        b.tabIndex = on ? 0 : -1;
      });
    }
    wrap.setValue = setValue;
    return wrap;
  }

  // ---------------------------------------------------------------- 面板
  function panel(opts) {
    opts = opts || {};
    var cls = ["ui-panel"];
    if (opts.group) { cls.push("ui-panel--group"); }
    if (opts.plain) { cls.push("ui-panel--plain"); }
    if (opts.inset) { cls.push("ui-panel--inset"); }
    if (opts.floating) { cls.push("ui-panel--floating"); }
    if (opts.collapsible) { cls.push("ui-panel--collapsible"); }
    if (opts.className) { cls.push(opts.className); }
    var wrap = el("section", {
      cls: cls.join(" "),
      attrs: opts.collapsible ? { "aria-expanded": opts.expanded === false ? "false" : "true" } : null
    });
    var head = el("div", { cls: "ui-panel__head", attrs: { tabindex: opts.collapsible ? "0" : null } });
    if (opts.icon) { head.appendChild(opts.icon); }
    head.appendChild(el("h3", { cls: "ui-panel__title", text: opts.title || "" }));
    if (opts.sub) { head.appendChild(el("span", { cls: "ui-panel__sub", text: opts.sub })); }
    if (opts.actions && opts.actions.length) {
      var acts = el("div", { cls: "ui-panel__actions" });
      opts.actions.forEach(function (a) { acts.appendChild(a); });
      head.appendChild(acts);
    }
    wrap.appendChild(head);
    var body = el("div", { cls: "ui-panel__body" });
    if (opts.body) { body.appendChild(opts.body); }
    wrap.appendChild(body);
    if (opts.foot) { wrap.appendChild(el("div", { cls: "ui-panel__foot", text: opts.foot })); }
    if (opts.collapsible) {
      var toggle = function () {
        var on = wrap.getAttribute("aria-expanded") !== "false";
        wrap.setAttribute("aria-expanded", String(!on));
      };
      head.addEventListener("click", function (ev) {
        if (ev.target.closest(".ui-panel__actions")) { return; }
        toggle();
      });
      head.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); toggle(); }
      });
    }
    wrap.body = body;
    return wrap;
  }

  // ---------------------------------------------------------------- 工具条
  function toolbar(opts) {
    opts = opts || {};
    var wrap = el("div", {
      cls: "ui-toolbar" + (opts.flat ? " ui-toolbar--flat" : "") + (opts.className ? " " + opts.className : ""),
      attrs: { role: "toolbar", "aria-label": opts.ariaLabel || "工具条" }
    });
    (opts.groups || []).forEach(function (group) {
      if (group === "sep") { wrap.appendChild(el("span", { cls: "ui-toolbar__sep", attrs: { "aria-hidden": "true" } })); return; }
      if (group === "grow") { wrap.appendChild(el("span", { cls: "ui-toolbar__grow" })); return; }
      var g = el("div", { cls: "ui-toolbar__group" });
      (Array.isArray(group) ? group : [group]).forEach(function (n) { if (n) { g.appendChild(n); } });
      wrap.appendChild(g);
    });
    return wrap;
  }

  // ---------------------------------------------------------------- 表格
  function table(opts) {
    opts = opts || {};
    var cols = opts.columns || [];
    var wrap = el("div", {
      cls: "ui-table" + (opts.className ? " " + opts.className : ""),
      attrs: { role: opts.role || "table" }
    });
    var tpl;
    if (opts.colTemplate) {
      tpl = opts.colTemplate;
    } else {
      tpl = cols.map(function (c) {
        if (typeof c === "string") { return "minmax(60px, 1fr)"; }
        if (c.width) { return c.width; }
        return "minmax(60px, 1fr)";
      }).join(" ");
    }
    wrap.style.setProperty("--ui-table-cols", tpl);

    var head = el("div", { cls: "ui-table__head" + (opts.headClass ? " " + opts.headClass : ""), attrs: { role: "row" } });
    cols.forEach(function (c) {
      var label = typeof c === "string" ? c : c.label;
      var cell = el("span", {
        cls: "ui-table__cell" + (c && c.align === "right" ? " ui-table__cell--num" : "") +
          (c && c.cellClass ? " " + c.cellClass : ""),
        text: label,
        attrs: { role: "columnheader" }
      });
      head.appendChild(cell);
    });
    wrap.appendChild(head);

    var rows = opts.rows || [];
    if (!rows.length) {
      wrap.appendChild(el("div", { cls: "ui-table__empty", text: opts.empty || "没有内容" }));
      return wrap;
    }
    rows.forEach(function (row, i) {
      var rowCls = "ui-table__row" + (opts.rowClass ? " " + opts.rowClass(row, i) : "");
      var r = el("div", { cls: rowCls, attrs: { role: "row" } });
      if (opts.rowAttrs) {
        var attrs = opts.rowAttrs(row, i) || {};
        Object.keys(attrs).forEach(function (k) {
          if (attrs[k] != null) { r.setAttribute(k, String(attrs[k])); }
        });
      }
      cols.forEach(function (c, ci) {
        var key = typeof c === "string" ? c : c.key;
        var cell = el("span", {
          cls: "ui-table__cell" + (c && c.align === "right" ? " ui-table__cell--num" : "") +
            (c && c.wrap ? " ui-table__cell--wrap" : "") +
            (c && c.cellClass ? " " + c.cellClass : ""),
          attrs: { role: "cell" }
        });
        if (opts.renderCell) {
          var out = opts.renderCell(row, c, ci);
          if (out == null) { /* 空 */ }
          else if (typeof out === "string" || typeof out === "number") { cell.textContent = String(out); }
          else if (out.nodeType) { cell.appendChild(out); }
        } else {
          cell.textContent = row[key] == null ? "" : String(row[key]);
        }
        r.appendChild(cell);
      });
      if (opts.onRowClick) {
        r.addEventListener("click", function (ev) { opts.onRowClick(row, i, ev); });
        r.style.cursor = "pointer";
      }
      wrap.appendChild(r);
    });
    return wrap;
  }

  function badge(text, kind, title) {
    return el("span", {
      cls: "ui-badge" + (kind ? " ui-badge--" + kind : ""),
      text: text,
      attrs: { title: title || null }
    });
  }

  // ---------------------------------------------------------------- 弹窗
  var openDialog = null;

  function dialog(opts) {
    opts = opts || {};
    if (openDialog) { openDialog.close(); }        // 同时只允许一个
    var prevFocus = document.activeElement;
    var scrim = el("div", { cls: "ui-dialog__scrim", attrs: { role: "presentation" } });
    var box = el("div", {
      cls: "ui-dialog__box",
      attrs: {
        role: "dialog", "aria-modal": "true",
        "aria-label": opts.title || "对话框",
        tabindex: "-1"
      }
    });
    if (opts.danger) { box.classList.add("ui-dialog--danger"); }
    if (opts.wide) { box.classList.add("ui-dialog--wide"); }

    var head = el("div", { cls: "ui-dialog__head" });
    head.appendChild(el("h2", { cls: "ui-dialog__title", text: (opts.danger ? "⚠ " : "") + (opts.title || "提示") }));
    var closeBtn = el("button", {
      cls: "ui-dialog__close", text: "✕",
      attrs: { type: "button", "aria-label": "关闭对话框" }
    });
    head.appendChild(closeBtn);
    box.appendChild(head);

    var body = el("div", { cls: "ui-dialog__body" });
    if (opts.body) {
      body.appendChild(typeof opts.body === "string" ? el("p", { text: opts.body }) : opts.body);
    }
    box.appendChild(body);

    var foot = el("div", { cls: "ui-dialog__foot" });
    var buttons = [];
    (opts.buttons || []).forEach(function (b, i) {
      var node = btn({
        label: b.label,
        variant: b.variant || (b.danger ? "danger" : "default"),
        size: b.size,
        disabled: b.disabled,
        onClick: function () {
          if (b.onClick) {
            var keep = b.onClick(api);
            if (keep === false) { return; }
          }
          if (b.close !== false) { api.close(); }
        }
      });
      buttons.push(node);
      foot.appendChild(node);
    });
    if (!buttons.length) {
      foot.appendChild(btn({ label: "关闭", onClick: function () { api.close(); } }));
    }
    box.appendChild(foot);
    scrim.appendChild(box);
    document.body.appendChild(scrim);
    document.body.classList.add("ui-scroll-lock");

    function focusables() {
      return Array.prototype.slice.call(
        box.querySelectorAll('button,[href],input,select,textarea,[tabindex]:not([tabindex="-1"])')
      ).filter(function (n) { return !n.disabled && n.getClientRects().length; });
    }

    function onKey(ev) {
      if (ev.key === "Escape" && opts.dismissible !== false) {
        ev.preventDefault();
        api.close();
        return;
      }
      if (ev.key !== "Tab") { return; }
      var list = focusables();
      if (!list.length) { ev.preventDefault(); box.focus(); return; }
      var first = list[0], last = list[list.length - 1];
      if (ev.shiftKey && document.activeElement === first) { ev.preventDefault(); last.focus(); }
      else if (!ev.shiftKey && document.activeElement === last) { ev.preventDefault(); first.focus(); }
    }

    var closed = false;
    var api = {
      el: box,
      body: body,
      close: function () {
        if (closed) { return; }
        closed = true;
        document.removeEventListener("keydown", onKey, true);
        if (scrim.parentNode) { scrim.parentNode.removeChild(scrim); }
        document.body.classList.remove("ui-scroll-lock");
        openDialog = null;
        try { if (prevFocus && prevFocus.focus) { prevFocus.focus(); } } catch (e) { /* 元素已移除 */ }
        if (opts.onClose) { opts.onClose(); }
      }
    };

    closeBtn.addEventListener("click", function () { api.close(); });
    if (opts.dismissible !== false) {
      scrim.addEventListener("mousedown", function (ev) {
        if (ev.target === scrim) { api.close(); }
      });
    }
    document.addEventListener("keydown", onKey, true);
    openDialog = api;

    // 默认焦点：危险操作优先落在"非危险"按钮（调用方把「取消」放第一位），否则第一个按钮
    var preferred = buttons[0];
    if (opts.danger) {
      var safe = null;
      for (var bi = 0; bi < buttons.length; bi++) {
        if (buttons[bi].className.indexOf("ui-btn--danger") < 0) { safe = buttons[bi]; break; }
      }
      preferred = safe || buttons[0];
    }
    (preferred || closeBtn).focus();
    return api;
  }

  // ---------------------------------------------------------------- 菜单
  var liveMenu = null;

  function closeMenu(restoreFocus) {
    if (!liveMenu) { return; }
    var m = liveMenu;
    liveMenu = null;
    document.removeEventListener("mousedown", m._down, true);
    document.removeEventListener("keydown", m._key, true);
    if (m.el.parentNode) { m.el.parentNode.removeChild(m.el); }
    if (restoreFocus !== false && m.restore && m.restore.focus) {
      try { m.restore.focus(); } catch (e) { /* 触发元素已被移除 */ }
    }
  }

  function menu(opts) {
    opts = opts || {};
    closeMenu(false);                       // 换菜单时不抢焦点
    var anchor = opts.anchor;
    var node = el("div", { cls: "ui-menu", attrs: { role: "menu", "aria-label": opts.ariaLabel || "菜单" } });
    var items = opts.items || [];
    items.forEach(function (item) {
      if (item === "sep") { node.appendChild(el("div", { cls: "ui-menu__sep", attrs: { role: "separator" } })); return; }
      if (item.groupLabel) { node.appendChild(el("div", { cls: "ui-menu__label", text: item.groupLabel })); return; }
      var b = el("button", {
        cls: "ui-menu__item",
        text: item.label,
        attrs: {
          type: "button", role: "menuitem",
          disabled: !!item.disabled,
          "aria-checked": item.checked == null ? null : String(!!item.checked)
        }
      });
      if (item.hint) { b.title = item.hint; }
      b.addEventListener("click", function () {
        if (item.disabled) { return; }
        closeMenu();
        if (item.onClick) { item.onClick(); }
      });
      node.appendChild(b);
    });
    document.body.appendChild(node);

    // 定位：锚点矩形 + 视口碰撞翻转（先量尺寸再定位，避免闪一下）
    var r = anchor ? anchor.getBoundingClientRect() : { left: 40, top: 40, bottom: 40, right: 40 };
    node.style.left = "0px";
    node.style.top = "0px";
    var mw = node.offsetWidth, mh = node.offsetHeight;
    var x = opts.align === "right" ? r.right - mw : r.left;
    var y = r.bottom + 2;
    if (y + mh > window.innerHeight - 8) { y = Math.max(8, r.top - mh - 2); }
    if (x + mw > window.innerWidth - 8) { x = Math.max(8, window.innerWidth - mw - 8); }
    node.style.left = Math.round(Math.max(8, x)) + "px";
    node.style.top = Math.round(y) + "px";

    var prevFocus = document.activeElement;
    var m = { el: node, restore: prevFocus, _down: null, _key: null };
    m._down = function (ev) {
      if (node.contains(ev.target) || (anchor && anchor.contains(ev.target))) { return; }
      closeMenu();
    };
    m._key = function (ev) {
      var list = Array.prototype.slice.call(node.querySelectorAll(".ui-menu__item:not([disabled])"));
      var idx = list.indexOf(document.activeElement);
      if (ev.key === "Escape") { ev.preventDefault(); closeMenu(); return; }
      if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
        if (!list.length) { return; }
        ev.preventDefault();
        var step = ev.key === "ArrowDown" ? 1 : -1;
        var next = idx < 0 ? 0 : (idx + step + list.length) % list.length;
        list[next].focus();
      }
      if (ev.key === "Tab") { closeMenu(false); }
    };
    // 延后一帧再挂全局监听：否则"打开菜单"的那次点击会立刻把菜单关掉
    setTimeout(function () {
      if (liveMenu !== m) { return; }
      document.addEventListener("mousedown", m._down, true);
      document.addEventListener("keydown", m._key, true);
    }, 0);

    liveMenu = m;
    var first = node.querySelector(".ui-menu__item:not([disabled])");
    if (first) { first.focus(); }
    return { el: node, close: function () { closeMenu(); } };
  }

  // ---------------------------------------------------------------- 提示
  var tipNode = null, tipTimer = null, tipTarget = null;

  function ensureTip() {
    if (tipNode) { return tipNode; }
    tipNode = el("div", { cls: "ui-tooltip", attrs: { role: "tooltip", hidden: true } });
    document.body.appendChild(tipNode);
    return tipNode;
  }

  function showTip(target, content, opts) {
    var tip = ensureTip();
    tip.innerHTML = "";
    if (typeof content === "string") { tip.textContent = content; }
    else if (content && content.nodeType) { tip.appendChild(content); }
    tip.hidden = false;
    // 定位：默认在上方，空间不足翻到下方；水平方向夹在视口内
    var r = target.getBoundingClientRect();
    var tw = tip.offsetWidth, th = tip.offsetHeight;
    var side = opts && opts.side === "bottom" ? "bottom" : "top";
    var y = side === "top" ? r.top - th - 8 : r.bottom + 8;
    if (y < 4) { side = "bottom"; y = r.bottom + 8; }
    if (y + th > window.innerHeight - 4) { side = "top"; y = Math.max(4, r.top - th - 8); }
    var x = Math.min(Math.max(8, r.left), Math.max(8, window.innerWidth - tw - 8));
    tip.style.left = Math.round(x) + "px";
    tip.style.top = Math.round(y) + "px";
    tip.setAttribute("data-side", side);
    tipTarget = target;
    if (opts && opts.id) { tip.id = opts.id; }
  }

  function hideTip() {
    if (tipTimer) { clearTimeout(tipTimer); tipTimer = null; }
    if (tipNode) { tipNode.hidden = true; tipNode.innerHTML = ""; }
    tipTarget = null;
  }

  /**
   * 给元素挂提示。返回 destroy()。
   * 注意：设计规范要求"用自定义提示的元素不要再设 title"，否则会出现双提示。
   */
  function attachTip(target, content, opts) {
    opts = opts || {};
    var delay = opts.delay == null ? 300 : opts.delay;
    var descId = opts.id || nextId("tip");
    target.setAttribute("aria-describedby", descId);
    var enter = function () {
      if (tipTimer) { clearTimeout(tipTimer); }
      tipTimer = setTimeout(function () { showTip(target, typeof content === "function" ? content() : content, { side: opts.side, id: descId }); }, delay);
    };
    var leave = function () {
      if (tipTimer) { clearTimeout(tipTimer); tipTimer = null; }
      hideTip();
    };
    target.addEventListener("mouseenter", enter);
    target.addEventListener("focus", function () { showTip(target, typeof content === "function" ? content() : content, { side: opts.side, id: descId }); });
    target.addEventListener("mouseleave", leave);
    target.addEventListener("blur", leave);
    return function destroy() {
      target.removeEventListener("mouseenter", enter);
      target.removeEventListener("mouseleave", leave);
      hideTip();
      target.removeAttribute("aria-describedby");
    };
  }

  // ---------------------------------------------------------------- 轻提示
  function toast(text, kind, ms) {
    var stack = document.getElementById("ui-toast-stack");
    if (!stack) {
      stack = el("div", { cls: "ui-toast-stack", attrs: { id: "ui-toast-stack", role: "status", "aria-live": "polite" } });
      document.body.appendChild(stack);
    }
    var t = el("div", { cls: "ui-toast" + (kind ? " ui-toast--" + kind : ""), text: text });
    stack.appendChild(t);
    setTimeout(function () {
      if (t.parentNode) { t.parentNode.removeChild(t); }
    }, ms == null ? 2600 : ms);
    return t;
  }

  // ---------------------------------------------------------------- 暴露
  window.GWUI = {
    version: VERSION,
    icons: ICONS,
    el: el,
    icon: svgIcon,
    btn: btn,
    input: input,
    select: select,
    check: check,
    field: field,
    tabs: tabs,
    panel: panel,
    toolbar: toolbar,
    table: table,
    badge: badge,
    dialog: dialog,
    menu: menu,
    tooltip: { attach: attachTip, hide: hideTip, show: showTip },
    toast: toast,
    closeMenu: closeMenu,
    _state: function () { return { dialog: !!openDialog, menu: !!liveMenu, tip: !!tipTarget }; }
  };
})();
