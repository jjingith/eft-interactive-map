/* ============================================================================
 * ui-showcase.js —— 设计系统展示页（R19.24）
 * 只调用 window.GWUI；不碰业务模块、不联网、不发请求。
 * 页面上的数据全部是示例（示例任务 A/B/C…），不代表真实游戏数据。
 * ==========================================================================*/
(function () {
  "use strict";

  var UI = window.GWUI;
  var logEl = document.getElementById("sc-log");
  var stateEl = document.getElementById("sc-state");
  var logCount = 0;

  function log(msg) {
    logCount += 1;
    if (logEl) { logEl.textContent = "交互日志（" + logCount + "）：" + msg; }
    syncState();
  }

  function syncState() {
    if (!stateEl) { return; }
    var s = UI._state();
    var bits = [];
    if (s.dialog) { bits.push("弹窗已开"); }
    if (s.menu) { bits.push("菜单已开"); }
    if (s.tip) { bits.push("提示已显示"); }
    stateEl.textContent = bits.length ? "组件状态：" + bits.join(" / ") : "组件状态：空闲";
    stateEl.className = "ui-badge " + (bits.length ? "ui-badge--warn" : "ui-badge--info");
  }
  setInterval(syncState, 400);

  // 每个分节统一用 panel 包起来，标题条就是该节的名字
  function block(id, build) {
    var host = document.getElementById(id);
    if (!host) { return; }
    var title = host.getAttribute("data-title") || id;
    var body = UI.el("div", { cls: "sc-col" });
    var wrap = UI.panel({ title: title, className: "showcase__panel" });
    wrap.body.appendChild(body);
    host.appendChild(wrap);
    build(body);
    return body;
  }

  function row(children, tight) {
    return UI.el("div", { cls: "sc-row" + (tight ? " sc-row--tight" : ""), children: children });
  }
  function label(text) { return UI.el("span", { cls: "sc-label", text: text }); }
  function note(text) { return UI.el("p", { cls: "sc-note", text: text }); }

  // ---------------------------------------------------------------- 导航
  var nav = document.getElementById("sc-nav");
  Array.prototype.slice.call(document.querySelectorAll(".showcase__block")).forEach(function (sec) {
    if (!nav) { return; }
    var a = document.createElement("a");
    a.href = "#" + sec.id;
    a.textContent = sec.getAttribute("data-title") || sec.id;
    nav.appendChild(a);
  });

  // ---------------------------------------------------------------- 1 标题栏与面板
  block("sec-panel", function (host) {
    // XP 标题栏
    var bar = UI.el("div", { cls: "ui-titlebar" });
    bar.appendChild(UI.el("span", {
      cls: "ui-titlebar__icon",
      html: '<svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">' +
            '<rect x="1" y="3" width="14" height="10" fill="#ffffff" stroke="#0a3f9e"/>' +
            '<rect x="1" y="3" width="14" height="3" fill="#4a9bff"/></svg>'
    }));
    bar.appendChild(UI.el("h2", { cls: "ui-titlebar__title", text: "示例窗口标题栏（Luna 渐变 + 内亮边）" }));
    var acts = UI.el("div", { cls: "ui-titlebar__actions" });
    ["–", "□", "✕"].forEach(function (sym) {
      var b = UI.el("button", { cls: "ui-titlebar__btn", text: sym, attrs: { type: "button", "aria-label": "标题栏按钮 " + sym } });
      b.addEventListener("click", function () { log("标题栏按钮 " + sym); });
      acts.appendChild(b);
    });
    bar.appendChild(acts);
    host.appendChild(bar);
    host.appendChild(note("标题栏不是「给 div 涂蓝」：渐变两端 + 1px 内亮边 + 上两角 3px 圆角 + 标题省略号。"));

    // 三种面板
    var grid = UI.el("div", { cls: "sc-grid sc-grid--3" });
    grid.appendChild(UI.panel({
      title: "普通面板",
      sub: "面 + 1px 深边",
      body: UI.el("p", { text: "正文内容。面板本身不带阴影，层级靠边框与面色区分。" })
    }));
    grid.appendChild(UI.panel({
      title: "分组框（GroupBox）",
      group: true,
      body: UI.el("p", { text: "标题压在边框上，这是 XP 分组框的标准形态。" })
    }));
    var coll = UI.panel({
      title: "可折叠面板",
      collapsible: true,
      body: UI.el("p", { text: "点标题条（或聚焦后用回车/空格）折叠。aria-expanded 同步更新。" })
    });
    grid.appendChild(coll);
    host.appendChild(grid);

    var act = UI.btn({ label: "面板操作按钮", size: "sm", onClick: function () { log("面板标题栏按钮"); } });
    host.appendChild(UI.panel({
      title: "带操作区的面板",
      actions: [act],
      body: UI.el("p", { text: "标题栏右侧可以放操作按钮；点击操作区不会触发折叠。" })
    }));

    host.appendChild(UI.panel({
      title: "双层嵌套（规范允许的上限）",
      body: UI.panel({
        title: "内层面板",
        plain: true,
        body: UI.el("p", { text: "再嵌一层就应改成「小标题 + 分隔线」，避免边框套边框。" })
      })
    }));
  });

  // ---------------------------------------------------------------- 2 按钮
  block("sec-button", function (host) {
    host.appendChild(row([
      label("变体"),
      UI.btn({ label: "默认" }),
      UI.btn({ label: "主要操作", variant: "primary", onClick: function () { log("主要操作"); } }),
      UI.btn({ label: "危险操作", variant: "danger", onClick: function () { log("危险操作（示例并未真的删除）"); } }),
      UI.btn({ label: "幽灵按钮", variant: "ghost", onClick: function () { log("幽灵按钮"); } }),
      UI.btn({ label: "文字按钮", variant: "link", onClick: function () { log("文字按钮"); } })
    ]));

    host.appendChild(row([
      label("尺寸"),
      UI.btn({ label: "小 22px", size: "sm" }),
      UI.btn({ label: "中 26px" }),
      UI.btn({ label: "大 30px", size: "lg" })
    ]));

    var pressed = UI.btn({
      label: "开关型（aria-pressed）", pressed: false,
      onClick: function () {
        var on = pressed.getAttribute("aria-pressed") === "true";
        pressed.setAttribute("aria-pressed", String(!on));
        log("开关型按钮 → " + (!on ? "按下" : "弹起"));
      }
    });
    var busyBtn = UI.btn({
      label: "点我看加载态",
      onClick: function () {
        busyBtn.setAttribute("aria-busy", "true");
        busyBtn.querySelector(".ui-btn__label").textContent = "处理中…";
        log("按钮进入加载态（1.5 秒后恢复）");
        setTimeout(function () {
          busyBtn.removeAttribute("aria-busy");
          busyBtn.querySelector(".ui-btn__label").textContent = "点我看加载态";
          log("按钮加载态结束");
        }, 1500);
      }
    });
    host.appendChild(row([
      label("状态"),
      pressed,
      busyBtn,
      UI.btn({ label: "禁用（真的不可点）", disabled: true, onClick: function () { log("不应该被触发"); } }),
      UI.btn({ label: "图标 + 文字", icon: UI.icons.check })
    ]));

    host.appendChild(note("规则：悬停转琥珀、按下下沉 1px 并翻成凹陷、选区用蓝、禁用同时给 disabled 与 aria-disabled。"));

    // 键盘焦点演示
    var focusRow = UI.el("div", { cls: "sc-row" });
    focusRow.appendChild(label("Tab 走一遍"));
    for (var i = 1; i <= 3; i++) {
      focusRow.appendChild(UI.btn({ label: "焦点示例 " + i, onClick: function () { /* 示例 */ } }));
    }
    host.appendChild(focusRow);
  });

  // ---------------------------------------------------------------- 3 表单
  block("sec-form", function (host) {
    var grid = UI.el("div", { cls: "sc-grid sc-grid--2" });

    grid.appendChild(UI.field({
      label: "任务名称（文本）",
      id: "sc-in-1",
      hint: "支持中文长文本，输入框不会随内容撑宽。",
      control: UI.input({ placeholder: "例如：示例任务 A", onInput: function (v) { log("输入框 → " + (v || "（清空）")); } })
    }));

    grid.appendChild(UI.field({
      label: "最小等级（数字）",
      id: "sc-in-2",
      control: UI.input({ num: true, type: "number", min: 0, max: 80, placeholder: "0", onInput: function (v) { log("数字框 → " + v); } })
    }));

    grid.appendChild(UI.field({
      label: "商人（下拉）",
      id: "sc-sel-1",
      hint: "保留原生下拉：离线、可键盘、无浮层裁切问题。",
      control: UI.select({
        options: [{ value: "", label: "全部商人" }, { value: "a", label: "示例商人甲" }, { value: "b", label: "示例商人乙" }],
        onChange: function (v) { log("下拉选择 → " + (v || "全部")); }
      })
    }));

    grid.appendChild(UI.field({
      label: "错误态示例",
      id: "sc-in-3",
      error: "等级必须是 0–80 之间的整数。",
      control: UI.input({ value: "999", invalid: true })
    }));

    grid.appendChild(UI.field({
      label: "禁用输入框",
      id: "sc-in-4",
      hint: "禁用时背景转凹陷面、文字转灰、不可聚焦。",
      control: UI.input({ value: "只读/禁用值", disabled: true })
    }));

    grid.appendChild(UI.field({
      label: "只有说明没有值",
      id: "sc-in-5",
      hint: "提示文字在标签与说明之间保持同一行高。",
      control: UI.input({ placeholder: "占位文本" })
    }));

    host.appendChild(grid);

    var checks = UI.el("div", { cls: "sc-row" });
    checks.appendChild(label("复选"));
    ["只显示已完成", "有前置任务", "有后续任务"].forEach(function (t, i) {
      checks.appendChild(UI.check({
        label: t, checked: i === 0,
        onChange: function (v) { log("复选「" + t + "」→ " + (v ? "选中" : "取消")); }
      }));
    });
    checks.appendChild(UI.check({ label: "禁用复选", checked: true, disabled: true }));
    host.appendChild(checks);

    var radios = UI.el("div", { cls: "sc-row" });
    radios.appendChild(label("单选"));
    ["未开始", "进行中", "已完成"].forEach(function (t, i) {
      radios.appendChild(UI.check({
        radio: true, name: "sc-status", label: t, checked: i === 1,
        onChange: function (v) { if (v) { log("单选「" + t + "」"); } }
      }));
    });
    host.appendChild(radios);

    host.appendChild(row([
      label("长标签换行"),
      UI.check({
        label: "这是一个很长很长很长很长的复选标签，用来检查换行时勾选框是否仍然与第一行文字对齐",
        checked: false
      })
    ]));
  });

  // ---------------------------------------------------------------- 4 标签页与工具条
  block("sec-tabs", function (host) {
    host.appendChild(row([
      label("普通标签"),
      UI.tabs({
        items: [{ key: "a", label: "任务树" }, { key: "b", label: "商人任务" }, { key: "c", label: "我的进度", disabled: false }],
        value: "a",
        onChange: function (k) { log("标签切换 → " + k); }
      })
    ]));
    host.appendChild(row([
      label("分段控件"),
      UI.tabs({
        segmented: true,
        items: [{ key: "pvp", label: "PvP" }, { key: "pve", label: "PvE" }, { key: "pvps", label: "PvPS（赛季服）" }],
        value: "pvp",
        onChange: function (k) { log("分段切换 → " + k); }
      })
    ]));
    host.appendChild(note("普通标签的当前项是琥珀底 + 上亮边；分段控件的当前项多一层内凹（像被按下）。方向键可切换。"));

    var tb = UI.toolbar({
      ariaLabel: "示例工具条",
      groups: [
        [UI.btn({ label: "适配全图", size: "sm", onClick: function () { log("工具条：适配全图"); } }),
         UI.btn({ label: "放大", size: "sm" }),
         UI.btn({ label: "缩小", size: "sm" })],
        "sep",
        [UI.btn({ label: "重置视图", size: "sm" })],
        "grow",
        [UI.check({ label: "仅显示筛选结果" })]
      ]
    });
    host.appendChild(tb);

    var tb2 = UI.toolbar({
      flat: true,
      groups: [
        [UI.field({ label: "搜索", id: "sc-tb-search", control: UI.input({ placeholder: "搜索任务名…", size: "sm" }) })],
        [UI.field({ label: "状态", id: "sc-tb-status", control: UI.select({
          options: [{ value: "", label: "全部状态" }, { value: "done", label: "已完成" }]
        }) })]
      ]
    });
    host.appendChild(tb2);
  });

  // ---------------------------------------------------------------- 5 菜单与提示
  block("sec-overlay", function (host) {
    var anchor = UI.btn({
      label: "打开菜单（↓/↑ 选择，Esc 关闭）",
      onClick: function () {
        UI.menu({
          anchor: anchor,
          items: [
            { groupLabel: "示例分组" },
            { label: "标记为进行中", onClick: function () { log("菜单：标记为进行中"); } },
            { label: "标记为已完成", checked: true, onClick: function () { log("菜单：标记为已完成"); } },
            "sep",
            { label: "定位到地图", hint: "示例项", onClick: function () { log("菜单：定位到地图"); } },
            { label: "不可用项（逻辑上禁用）", disabled: true }
          ]
        });
      }
    });
    var edgeAnchor = UI.btn({
      label: "靠近右边缘打开（翻转）",
      onClick: function () {
        UI.menu({ anchor: edgeAnchor, align: "right", items: [
          { label: "靠近视口右侧时应向左对齐", onClick: function () { log("菜单：右对齐项"); } },
          { label: "第二项" }
        ] });
      }
    });
    var longAnchor = UI.btn({
      label: "靠近底部打开（向上翻转）",
      onClick: function () {
        var items = [];
        for (var i = 1; i <= 12; i++) {
          (function (n) {
            items.push({ label: "菜单项 " + n, onClick: function () { log("菜单：项 " + n); } });
          })(i);
        }
        UI.menu({ anchor: longAnchor, items: items });
      }
    });
    host.appendChild(row([label("菜单"), anchor, edgeAnchor, longAnchor]));
    host.appendChild(note("菜单挂在 body 上、视口内翻转、Esc/点外部关闭；打开时焦点进入第一项，关闭后回到触发按钮。"));

    // 提示：短、长（换行）、按钮上
    var t1 = UI.btn({ label: "短提示（300ms 后出现）" });
    UI.tooltip.attach(t1, "这是一条短提示。", { delay: 300 });
    var longText = "这是一条很长的提示，用来验证换行与最大宽度（320px）：目标区域为上游标注的矩形范围，" +
      "实际位置以游戏内地形为准；如果提示被裁切或溢出屏幕，说明边界处理有问题。";
    var t2 = UI.btn({ label: "长提示（自动换行）" });
    UI.tooltip.attach(t2, longText, { delay: 200 });
    var t3 = UI.badge("悬停我", "info");
    UI.tooltip.attach(t3, "徽标也能挂提示。注意：挂了自定义提示的元素不再设置 title，避免双提示。");
    host.appendChild(row([label("提示"), t1, t2, t3]));
  });

  // ---------------------------------------------------------------- 6 对话框
  block("sec-dialog", function (host) {
    function openInfo() {
      var body = UI.el("div", { cls: "ui-prose" });
      body.appendChild(UI.el("p", { text: "这是一个普通对话框：标题栏、正文、按钮区。Esc 可关闭，关闭后焦点回到触发按钮。" }));
      body.appendChild(UI.el("p", { text: "正文用 --ui-fs-body 与 1.5 倍行高；长文本会出现滚动条而不是把对话框撑出屏幕。" }));
      UI.dialog({
        title: "数据说明（示例）",
        body: body,
        buttons: [
          { label: "取消" },
          { label: "知道了", variant: "primary", onClick: function () { log("对话框：知道了"); } }
        ],
        onClose: function () { log("对话框已关闭，焦点已归还"); }
      });
    }

    function openDanger() {
      UI.dialog({
        title: "清空示例进度",
        danger: true,
        body: "清空后无法恢复。危险操作的确认按钮是红色，默认焦点落在「取消」上。",
        buttons: [
          { label: "取消" },
          { label: "确认清空", danger: true, onClick: function () { log("对话框：危险操作已确认（示例不会真的清空）"); } }
        ]
      });
    }

    function openWide() {
      var body = UI.el("div", { cls: "ui-prose" });
      body.appendChild(UI.el("p", { text: "宽对话框用于放表格或长说明（最大 760px / 94vw）。" }));
      body.appendChild(UI.table({
        columns: [{ key: "k", label: "项目", width: "160px" }, { key: "v", label: "说明" }],
        rows: [
          { k: "示例键一", v: "这是一段较长的说明文字，用来验证对话框内表格的换行与滚动。" },
          { k: "示例键二", v: "第二行。" }
        ]
      }));
      UI.dialog({
        title: "宽对话框", wide: true, body: body,
        buttons: [{ label: "关闭", variant: "primary" }]
      });
    }

    function openStatic() {
      UI.dialog({
        title: "不可通过遮罩关闭",
        dismissible: false,
        body: "dismissible:false 时点遮罩与 Esc 都不会关，只能用按钮关闭（用于「必须先处理」的场景）。",
        buttons: [{ label: "我知道了", variant: "primary" }]
      });
    }

    host.appendChild(row([
      label("对话框"),
      UI.btn({ label: "普通", onClick: openInfo }),
      UI.btn({ label: "危险确认", variant: "danger", onClick: openDanger }),
      UI.btn({ label: "宽（含表格）", onClick: openWide }),
      UI.btn({ label: "不可遮罩关闭", onClick: openStatic })
    ]));
    host.appendChild(note("同时只允许一个对话框；打开时锁滚动、限制焦点在框内、关闭后恢复焦点到触发元素。"));
  });

  // ---------------------------------------------------------------- 7 徽标
  block("sec-badge", function (host) {
    host.appendChild(row([
      label("种类"),
      UI.badge("默认"),
      UI.badge("已完成", "ok"),
      UI.badge("进行中", "info"),
      UI.badge("待补充", "warn"),
      UI.badge("已失败", "danger"),
      UI.badge("当前模式", "primary"),
      UI.badge("次要信息", "muted")
    ]));
    host.appendChild(row([
      label("在文字里"),
      UI.el("span", { text: "示例任务 A " }),
      UI.badge("Kappa", "warn"),
      UI.el("span", { text: " · 示例任务 B " }),
      UI.badge("赛季", "primary")
    ]));
    host.appendChild(note("徽标必须带文字；状态含义不能只靠颜色（色盲可辨）。"));
  });

  // ---------------------------------------------------------------- 8 表格
  block("sec-table", function (host) {
    var rows = [
      { name: "示例任务 A", trader: "示例商人甲", lvl: 5, state: "已完成", mode: "全模式" },
      { name: "示例任务 B（当前选中行）", trader: "示例商人乙", lvl: 12, state: "进行中", mode: "全模式" },
      { name: "示例任务 C", trader: "示例商人甲", lvl: 20, state: "未开始", mode: "仅 PvE" },
      { name: "示例任务 D（逻辑禁用）", trader: "示例商人丙", lvl: 30, state: "不可用", mode: "—" },
      { name: "示例任务 E（冲突行）", trader: "示例商人乙", lvl: 8, state: "槽位冲突", mode: "全模式" },
      { name: "示例任务 F：这一行故意放一个很长很长很长很长的任务名称，用来检查省略号与提示", trader: "示例商人丁", lvl: 40, state: "未开始", mode: "全模式" }
    ];
    var tbl = UI.table({
      columns: [
        { key: "name", label: "任务", cellClass: "sc-cell-name" },
        { key: "trader", label: "商人" },
        { key: "lvl", label: "等级", align: "right", width: "60px" },
        { key: "state", label: "状态", width: "96px" },
        { key: "mode", label: "模式", width: "96px" }
      ],
      colTemplate: "minmax(200px, 2fr) 140px 60px 96px 96px",
      rows: rows,
      rowAttrs: function (row, i) {
        if (i === 1) { return { "aria-selected": "true" }; }
        return {};
      },
      rowClass: function (row, i) {
        if (i === 1) { return "is-selected"; }
        if (i === 3) { return "is-disabled"; }
        if (i === 4) { return "is-conflict"; }
        return "";
      },
      renderCell: function (row, col, ci) {
        if (ci === 3) {
          var kind = row.state === "已完成" ? "ok" : (row.state === "进行中" ? "info" :
            (row.state === "槽位冲突" ? "danger" : (row.state === "不可用" ? "muted" : "")));
          return UI.badge(row.state, kind);
        }
        return row[col.key];
      },
      onRowClick: function (row, i, ev) {
        if (i === 3) { log("禁用行被点击（应当由业务层拦截）"); return; }
        Array.prototype.slice.call(tbl.querySelectorAll(".ui-table__row")).forEach(function (r, j) {
          r.classList.toggle("is-selected", j === i);
          if (j === i) { r.setAttribute("aria-selected", "true"); } else { r.removeAttribute("aria-selected"); }
        });
        log("表格行选中 → " + row.name);
      }
    });
    host.appendChild(tbl);

    // 长文本单元格 + 提示（不用 title，改用 GWUI.tooltip）
    var rowsAll = tbl.querySelectorAll(".ui-table__row");
    var lastRow = rowsAll[rowsAll.length - 1];
    if (lastRow) {
      var target = lastRow.querySelector(".sc-cell-name");
      if (target) { UI.tooltip.attach(target, target.textContent + "（完整名称，可换行显示）", { delay: 200 }); }
    }

    host.appendChild(note("行状态：悬停浅琥珀、选中蓝底白字、禁用灰化、冲突红虚线 + 左红条。长单元格省略号 + 自定义提示。"));

    host.appendChild(UI.table({
      columns: [{ key: "a", label: "空表也要有说明" }],
      rows: [],
      empty: "当前筛选条件下没有数据（这是空态，不是加载失败）。"
    }));
  });

  // ---------------------------------------------------------------- 9 文字与间距
  block("sec-type", function (host) {
    [["--ui-fs-title 18px", "页面标题：任务系统", "var(--ui-fs-title)"],
     ["--ui-fs-panel 15px", "面板标题：商人任务中心", "var(--ui-fs-panel)"],
     ["--ui-fs-strong 14px", "强调正文：PvPS（赛季服）", "var(--ui-fs-strong)"],
     ["--ui-fs-body 13px", "正文：勾选目标会即时保存到本机。", "var(--ui-fs-body)"],
     ["--ui-fs-compact 12px", "表格/紧凑控件：示例任务 A · 示例商人甲 · 等级 5", "var(--ui-fs-compact)"],
     ["--ui-fs-micro 11px", "辅助信息：数据生成于 2026-10-28 · 目标 4 条", "var(--ui-fs-micro)"]]
      .forEach(function (x) {
        var r = UI.el("div", { cls: "sc-row" });
        r.appendChild(UI.el("span", { cls: "sc-label", text: x[0] }));
        r.appendChild(UI.el("span", { text: x[1], style: { "font-size": x[2] } }));
        host.appendChild(r);
      });

    host.appendChild(row([
      label("字重"),
      UI.el("span", { text: "常规 400", style: { "font-weight": "400" } }),
      UI.el("span", { text: "加粗 700", style: { "font-weight": "700" } }),
      UI.el("span", { text: "等宽（ID/坐标）", style: { "font-family": "var(--ui-font-mono)" } })
    ]));

    var ruler = UI.el("div", { cls: "sc-ruler" });
    [1, 2, 3, 4, 5, 6, 7].forEach(function (n, i) {
      ruler.appendChild(UI.el("i", { style: { height: (14 + i * 10) + "px" } }));
    });
    host.appendChild(row([label("间距 1–7"), ruler,
      UI.el("span", { cls: "sc-note", text: "4 / 6 / 8 / 12 / 16 / 20 / 24px" })]));

    var radii = UI.el("div", { cls: "sc-row" });
    [["面板 0", "0"], ["控件 2px", "2px"], ["按钮 3px", "3px"], ["药丸 10px", "10px"]].forEach(function (r) {
      radii.appendChild(UI.el("span", {
        text: r[0],
        style: {
          display: "inline-block", padding: "3px 8px", "border-radius": r[1],
          border: "1px solid var(--ui-color-border-dark)",
          background: "var(--ui-color-surface-raised)", "font-size": "var(--ui-fs-micro)"
        }
      }));
    });
    host.appendChild(row([label("圆角档位"), radii]));

    host.appendChild(UI.el("p", {
      cls: "ui-prose",
      text: "长中文段落（1.7 倍行高，最大 760px）：任务攻略这类长文用正文 13px + 宽松行高，" +
        "单行不超过 42 个汉字，避免眼睛在长行上跳行。这里故意写长一点，检查 1240px 容器里" +
        "是否会自动换行、是否与右侧边距保持 12px、是否出现横向滚动条。若出现横向滚动条，" +
        "说明有元素撑破了容器（常见原因是 white-space:nowrap 用在了长文本上）。"
    }));
  });

  // ---------------------------------------------------------------- 10 底色对比与键盘
  block("sec-contrast", function (host) {
    host.appendChild(row([
      label("浅底"),
      UI.btn({ label: "按钮" }),
      UI.input({ placeholder: "输入框" }),
      UI.badge("徽标", "ok")
    ]));

    var dark = UI.el("div", { cls: "sc-dark" });
    dark.appendChild(row([
      label("深底"),
      UI.btn({ label: "按钮（组件仍然可读）" }),
      UI.badge("徽标", "warn")
    ]));
    dark.appendChild(UI.el("p", {
      text: "深底只用于地图画布这类特殊区域；面板会自带浅底，保证文字对比度不下降。",
      style: { "font-size": "var(--ui-fs-micro)", margin: "6px 0 0" }
    }));
    host.appendChild(dark);

    host.appendChild(row([
      label("键盘"),
      UI.btn({ label: "Tab 到我（应出现蓝环）", onClick: function () { log("键盘激活按钮"); } }),
      UI.input({ placeholder: "Tab 到输入框（蓝边 + 蓝环）" }),
      UI.check({ label: "Tab 到复选（框上出现蓝环）" })
    ]));

    var err = UI.el("div", { cls: "ui-field is-error" });
    err.appendChild(UI.el("span", { cls: "ui-field__label", text: "错误提示示例" }));
    err.appendChild(UI.input({ value: "非法值", invalid: true }));
    err.appendChild(UI.el("span", { cls: "ui-field__error", text: "这段红字说明为什么错、怎么改；aria-invalid=true 已设置。" }));
    host.appendChild(err);

    host.appendChild(note("自检方法：从页面顶部按 Tab，应依次经过「跳到主要内容」→ 顶部按钮 → 各分节控件，全程可见焦点环。"));
  });

  // ---------------------------------------------------------------- 顶部"焦点自检"
  var focusBtn = document.getElementById("sc-focus-test");
  if (focusBtn) {
    focusBtn.addEventListener("click", function () {
      var first = document.querySelector("#sec-button .ui-btn");
      if (first) {
        first.focus();
        log("焦点已移到「按钮」分节的第一个控件（继续按 Tab 可走完整个页面）");
      }
    });
  }

  // 初始日志
  if (logEl) { logEl.textContent = "交互日志：等待操作…（页面加载完成，GWUI " + UI.version + "）"; }
  syncState();
})();
