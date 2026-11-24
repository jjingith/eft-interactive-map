/* ============================================================================
 * changes.js —— R305「游戏更新」视图（官方补丁说明）
 *
 * 信息架构对照 db4tarkov.com/changes：左边是版本时间线，右边是该版本改了什么。
 * 数据不是本站编辑的，而是 BSG 发在 Steam 上的官方补丁公告：
 *   - GET  api/game-changes          读内置快照 + 本地缓存（不打网络，离线可用）
 *   - POST api/game-changes/refresh  抓一次官方公告并落缓存
 * 正文保留英文原文（翻译大段补丁说明容易失真），只把分区标题映射成中文。
 *
 * 对外接口（window.GWChanges）：
 *   mount()   建骨架（懒挂载，首次进入视图时调用）
 *   open()    进入视图（保证已挂载）
 *   refresh() 触发一次「检查更新」
 * ==========================================================================*/
(function () {
  "use strict";

  // 官方公告里的分区标题 → 中文。查不到就原样显示英文，不硬猜。
  var SECTION_ZH = {
    "changes": "改动",
    "change": "改动",
    "changes to": "改动",
    "fixes": "修复",
    "fix": "修复",
    "fixed": "修复",
    "bug fixes": "修复",
    "balance changes": "平衡调整",
    "balance": "平衡调整",
    "balancing": "平衡调整",
    "new content": "新增内容",
    "added": "新增",
    "additions": "新增",
    "new items": "新增物品",
    "known issues": "已知问题",
    "qol": "体验优化",
    "quality of life": "体验优化",
    "improvements": "改进",
    "location changes": "地图改动",
    "locations": "地图改动",
    "maps": "地图改动",
    "expansion hub": "扩展中心",
    "events": "活动",
    "other": "其他"
  };

  var root = null;
  var mounted = false;
  var els = {};
  var state = {
    entries: [],
    selected: "",
    query: "",
    meta: null,
    busy: false,
    message: "",
    messageError: false
  };

  // ---------------------------------------------------------------- 小工具
  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) { node.className = className; }
    if (text != null) { node.textContent = text; }
    return node;
  }

  function sectionLabel(title) {
    var key = String(title || "").trim().toLowerCase();
    return SECTION_ZH[key] || String(title || "").trim();
  }

  /** 版本号类型由服务端算好（同一条规则只写一处，Python 侧有测试锁着）；
      老缓存里没有 kind 字段时按版本号现算一遍兜底。 */
  function versionKind(entry) {
    if (entry && entry.kind) { return entry.kind; }
    var nums = String((entry && entry.version) || "").split(".").map(function (p) {
      return parseInt(p, 10) || 0;
    });
    if (nums.length >= 4 && nums[3] > 0) { return "热修"; }
    if (nums.length >= 3 && nums[2] > 0) { return "小版本"; }
    return "大版本";
  }

  function entryText(entry) {
    var buf = [entry.version, entry.date, entry.title];
    (entry.sections || []).forEach(function (section) {
      // 英文原标题 + 中文对照都进索引：搜「修复」「改动」也能命中（正文仍是英文）
      buf.push(section.title, sectionLabel(section.title));
      (section.blocks || []).forEach(function (block) { buf.push(block.text); });
    });
    return buf.join(" ").toLowerCase();
  }

  function matches(entry, query) {
    if (!query) { return true; }
    return entryText(entry).indexOf(query) >= 0;
  }

  function current() {
    for (var i = 0; i < state.entries.length; i++) {
      if (state.entries[i].id === state.selected) { return state.entries[i]; }
    }
    return null;
  }

  // ---------------------------------------------------------------- 骨架
  function mount() {
    if (mounted) { return; }
    root = document.getElementById("changes-view");
    if (!root) { return; }
    // 补丁正文是英文原文，交给名词字典逐词替换会把句子拆坏，这里整块跳过 i18n
    root.setAttribute("data-i18n-skip", "");
    root.textContent = "";

    var wrap = el("div", "ch-wrap");

    var bar = el("div", "ch-toolbar");
    var left = el("div", "ch-tb-left");
    left.appendChild(el("span", "ch-tb-title", "游戏更新"));
    left.appendChild(el("span", "ch-tb-sub", "官方补丁说明"));
    bar.appendChild(left);

    var right = el("div", "ch-tb-right");
    var search = document.createElement("input");
    search.type = "search";
    search.className = "ch-search";
    search.placeholder = "搜索版本号或内容…";
    search.setAttribute("aria-label", "搜索补丁内容");
    right.appendChild(search);

    var refresh = document.createElement("button");
    refresh.type = "button";
    refresh.className = "ch-refresh";
    refresh.textContent = "检查更新";
    refresh.title = "从 Steam 官方公告获取最新补丁说明";
    right.appendChild(refresh);
    bar.appendChild(right);
    wrap.appendChild(bar);

    var main = el("div", "ch-main");
    var side = el("div", "ch-side");
    side.appendChild(el("div", "ch-side-head", "版本"));
    var list = el("div", "ch-list");
    list.setAttribute("role", "listbox");
    list.setAttribute("aria-label", "版本列表");
    side.appendChild(list);
    var detail = el("div", "ch-detail");
    detail.setAttribute("role", "region");
    detail.setAttribute("aria-label", "该版本改动内容");
    main.appendChild(side);
    main.appendChild(detail);
    wrap.appendChild(main);

    var status = el("div", "ch-status");
    wrap.appendChild(status);

    root.appendChild(wrap);
    els = { search: search, refresh: refresh, list: list, detail: detail, status: status };

    search.addEventListener("input", function () {
      state.query = search.value.trim().toLowerCase();
      renderList();
    });
    refresh.addEventListener("click", function () { refreshNow(); });
    list.addEventListener("click", function (event) {
      var item = event.target && event.target.closest ? event.target.closest(".ch-item") : null;
      if (!item) { return; }
      select(item.getAttribute("data-id"));
    });
    list.addEventListener("keydown", function (event) {
      var step = event.key === "ArrowDown" ? 1 : (event.key === "ArrowUp" ? -1 : 0);
      if (!step) { return; }
      event.preventDefault();
      moveSelection(step);
    });

    mounted = true;
  }

  // ---------------------------------------------------------------- 数据
  function requestJSON(url, options) {
    return fetch(url, options || { cache: "no-store" }).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (data) {
        if (!response.ok) {
          throw new Error((data && data.error) || ("HTTP " + response.status));
        }
        return data;
      });
    });
  }

  function load() {
    setMessage("正在读取补丁数据…", false);
    requestJSON("api/game-changes").then(applyPayload).catch(function (error) {
      setMessage("读取失败：" + error.message, true);
      renderAll();
    });
  }

  function refreshNow() {
    if (state.busy) { return; }
    state.busy = true;
    els.refresh.disabled = true;
    els.refresh.textContent = "正在获取…";
    setMessage("正在从 Steam 官方公告获取…", false);
    requestJSON("api/game-changes/refresh", {
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: "{}"
    }).then(function (data) {
      if (!data.ok) {
        // 失败时也把已缓存的内容留在页面上，只报错、不清空
        if (data.entries && data.entries.length) { applyPayload(data); }
        setMessage(data.error || "获取失败", true);
        return;
      }
      var added = Number(data.added) || 0;
      applyPayload(data);
      setMessage(added > 0 ? "已更新：新增 " + added + " 个版本" : "已是最新，共 " + data.count + " 个版本", false);
    }).catch(function (error) {
      setMessage("无法获取官方公告：" + error.message, true);
    }).then(function () {
      state.busy = false;
      els.refresh.disabled = false;
      els.refresh.textContent = "检查更新";
      renderStatus();
    });
  }

  function applyPayload(data) {
    state.meta = data;
    state.entries = (data && data.entries) || [];
    state.message = "";          // 数据到手后清掉「正在读取…」，别让它挂在状态栏上
    var keep = state.selected && current();
    if (!keep) {
      state.selected = state.entries.length ? state.entries[0].id : "";
    }
    renderAll();
  }

  // ---------------------------------------------------------------- 渲染
  function renderAll() {
    renderList();
    renderDetail();
    renderStatus();
  }

  function renderList() {
    var list = els.list;
    if (!list) { return; }
    list.textContent = "";
    var shown = state.entries.filter(function (entry) { return matches(entry, state.query); });
    if (!shown.length) {
      list.appendChild(el("div", "ch-empty", state.entries.length ? "没有匹配的版本" : "还没有数据"));
      return;
    }
    shown.forEach(function (entry) {
      var item = el("button", "ch-item");
      item.type = "button";
      item.setAttribute("role", "option");
      item.setAttribute("data-id", entry.id);
      item.setAttribute("aria-selected", String(entry.id === state.selected));

      var top = el("div", "ch-item-top");
      top.appendChild(el("span", "ch-ver", entry.version));
      top.appendChild(el("span", "ch-kind", versionKind(entry)));
      item.appendChild(top);

      var meta = el("div", "ch-item-meta");
      meta.appendChild(el("span", "ch-date", entry.date || "日期未知"));
      meta.appendChild(el("span", "ch-count", (entry.bullets || 0) + " 条"));
      item.appendChild(meta);

      var first = firstBullet(entry);
      if (first) {
        item.appendChild(el("div", "ch-item-sum", first));
      }
      list.appendChild(item);
    });
  }

  function firstBullet(entry) {
    var sections = entry.sections || [];
    for (var i = 0; i < sections.length; i++) {
      var blocks = sections[i].blocks || [];
      for (var j = 0; j < blocks.length; j++) {
        if (blocks[j].type === "bullet" && blocks[j].text) { return blocks[j].text; }
      }
    }
    return "";
  }

  function renderDetail() {
    var box = els.detail;
    if (!box) { return; }
    box.textContent = "";
    var entry = current();
    if (!entry) {
      var empty = el("div", "ch-placeholder");
      empty.appendChild(el("p", "ch-placeholder-title", "还没有可显示的补丁说明"));
      empty.appendChild(el("p", null,
        "点右上角「检查更新」从 Steam 官方公告获取。没有网络时也可以看随安装包内置的最近几个版本。"));
      box.appendChild(empty);
      return;
    }

    var head = el("div", "ch-detail-head");
    var titleRow = el("div", "ch-title-row");
    titleRow.appendChild(el("h2", "ch-title", "Patch " + entry.version));
    titleRow.appendChild(el("span", "ch-kind ch-kind-lg", versionKind(entry)));
    head.appendChild(titleRow);

    var metaRow = el("div", "ch-detail-meta");
    metaRow.appendChild(el("span", null, entry.date || "日期未知"));
    var total = (entry.sections || []).reduce(function (sum, section) {
      return sum + (section.blocks ? section.blocks.length : 0);
    }, 0);
    metaRow.appendChild(el("span", "ch-dot", "·"));
    metaRow.appendChild(el("span", null, total + " 条改动"));
    if (entry.url) {
      metaRow.appendChild(el("span", "ch-dot", "·"));
      var link = el("a", "ch-link", "官方公告原文");
      link.href = entry.url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      metaRow.appendChild(link);
    }
    head.appendChild(metaRow);
    box.appendChild(head);

    (entry.sections || []).forEach(function (section) {
      var block = el("section", "ch-section");
      var heading = el("h3", "ch-sec-title");
      var zh = sectionLabel(section.title);
      heading.appendChild(el("span", "ch-sec-zh", zh || "其他"));
      if (section.title && zh !== section.title) {
        heading.appendChild(el("span", "ch-sec-en", section.title));
      }
      block.appendChild(heading);

      // 按原始顺序渲染：列表项连续时合并成一个 <ul>，遇到段落就断开——
      // 官方公告里常见「先一句说明、再跟几条列表」，顺序错了读起来是反的。
      var list = null;
      (section.blocks || []).forEach(function (item) {
        if (item.type === "bullet") {
          if (!list) {
            list = el("ul", "ch-bullets");
            block.appendChild(list);
          }
          list.appendChild(el("li", null, item.text));
        } else {
          list = null;
          block.appendChild(el("p", "ch-para", item.text));
        }
      });
      box.appendChild(block);
    });

    var foot = el("p", "ch-foot",
      "内容来自 BSG 发布的官方公告，保留英文原文；分区标题为中文对照。");
    box.appendChild(foot);
    box.scrollTop = 0;
  }

  function renderStatus() {
    var bar = els.status;
    if (!bar) { return; }
    bar.textContent = "";
    bar.className = "ch-status" + (state.messageError ? " is-error" : "");
    if (state.message) {
      bar.appendChild(el("span", "ch-status-msg", state.message));
      bar.appendChild(el("span", "ch-dot", "·"));
    }
    var meta = state.meta || {};
    var latest = state.entries.length ? state.entries[0] : null;
    var parts = ["共 " + state.entries.length + " 个版本"];
    if (latest && latest.date) { parts.push("最近 " + latest.date); }
    if (meta.fetchedAt) { parts.push("检查于 " + meta.fetchedAt); }
    else if (meta.bundledAt) { parts.push("内置快照 " + meta.bundledAt); }
    parts.push(meta.from === "cache" ? "来源：本地缓存" : "来源：随包快照");
    bar.appendChild(el("span", "ch-status-text", parts.join(" · ")));
    if (meta.stale && !meta.fetchedAt) {
      bar.appendChild(el("span", "ch-status-warn", "缓存已超过 6 小时，建议检查更新"));
    } else if (meta.stale) {
      bar.appendChild(el("span", "ch-status-warn", "超过 6 小时未检查"));
    }
  }

  function setMessage(text, isError) {
    state.message = text || "";
    state.messageError = !!isError;
    renderStatus();
  }

  // ---------------------------------------------------------------- 交互
  function select(id) {
    if (!id || id === state.selected) { return; }
    state.selected = id;
    renderList();
    renderDetail();
    var item = els.list.querySelector('.ch-item[data-id="' + (window.CSS && CSS.escape ? CSS.escape(id) : id) + '"]');
    if (item) { item.scrollIntoView({ block: "nearest" }); }
  }

  function moveSelection(step) {
    var shown = state.entries.filter(function (entry) { return matches(entry, state.query); });
    if (!shown.length) { return; }
    var index = 0;
    for (var i = 0; i < shown.length; i++) {
      if (shown[i].id === state.selected) { index = i; break; }
    }
    index = Math.min(shown.length - 1, Math.max(0, index + step));
    select(shown[index].id);
    var button = els.list.querySelector('.ch-item[data-id="' + shown[index].id + '"]');
    if (button) { button.focus(); }
  }

  // ---------------------------------------------------------------- 对外
  window.GWChanges = {
    mount: mount,
    open: function () {
      mount();
      if (!state.entries.length) { load(); }
      if (els.search) { els.search.focus(); }
    },
    refresh: refreshNow,
    // 供测试 / 调试读取当前状态
    state: function () { return state; }
  };
})();
