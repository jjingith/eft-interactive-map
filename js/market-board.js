/* R286 市场大盘（市场工作区的子页，不再占用顶层视图）
 *
 * 定位：专业行情终端，而不是后台统计面板。
 *   · 顶部：有效物资 / 上涨 / 下跌 / 平均 48h 涨跌 / 在售挂单 / 数据截止；
 *   · 主区：选中物资的真实价格曲线（云端行情在本机累积的快照）+ 自选行情；
 *   · 下部：涨幅榜 / 跌幅榜（真实 48h 字段 + 在售挂单数）+ 板块行情。
 *
 * 数据口径（绝不伪造）：
 *   · 榜单涨跌改用云端真实采样点重算 24h / 48h（上游 48h 字段偶发极端脏值）；
 *   · 均价 / 涨跌额 / 涨跌幅统一以窗口内采样点的算术平均为基准，三列自洽：
 *     涨跌额 = 当前价 - 均价，涨跌幅 = (当前价 / 均价 - 1) × 100%；
 *   · 在售挂单数来自 `lastOfferCount`，**不是成交笔数**；上游没有成交笔数字段；
 *   · 没有历史快照时只画已有采样点，不插值、不补 0、不拿别的模式顶替；
 *   · 云端还没有足够的采样时，曲线区域明确显示「历史积累中」。
 */
(function () {
  "use strict";

  var LS_WATCH = "eftmap.market-board.watch.v1";
  var LS_RANGE = "eftmap.market-board.range.v1";
  var MAX_WATCH = 12;
  var RANGES = [
    { key: "1h", label: "1小时", hours: 1, days: 1 },
    { key: "6h", label: "6小时", hours: 6, days: 1 },
    { key: "24h", label: "24小时", hours: 24, days: 1 },
    { key: "7d", label: "7天", hours: 0, days: 7 },
    { key: "30d", label: "30天", hours: 0, days: 30 },
    { key: "all", label: "全部", hours: 0, days: 90 }
  ];

  var BOARD_HEADS = {
    gainers48: '<th>#</th><th>物资</th><th class="mb-num">当前价格</th><th class="mb-num">过去48h均价</th><th class="mb-num">涨跌额</th><th class="mb-num">涨跌幅</th><th>价格曲线</th><th class="mb-num">在售数量</th>',
    losers48:  '<th>#</th><th>物资</th><th class="mb-num">当前价格</th><th class="mb-num">过去48h均价</th><th class="mb-num">涨跌额</th><th class="mb-num">涨跌幅</th><th>价格曲线</th><th class="mb-num">在售数量</th>',
    gainers24: '<th>#</th><th>物资</th><th class="mb-num">当前价格</th><th class="mb-num">过去24h均价</th><th class="mb-num">涨跌额</th><th class="mb-num">涨跌幅</th><th>价格曲线</th><th class="mb-num">在售数量</th>',
    losers24:  '<th>#</th><th>物资</th><th class="mb-num">当前价格</th><th class="mb-num">过去24h均价</th><th class="mb-num">涨跌额</th><th class="mb-num">涨跌幅</th><th>价格曲线</th><th class="mb-num">在售数量</th>',
    hot:       '<th>#</th><th>物资</th><th class="mb-num">售卖数量</th><th class="mb-num">过去24h峰值数量</th><th>24h 数量曲线</th>',
    trend:     '<th>#</th><th>物资</th><th>过去七天价格</th><th class="mb-num">七天均价</th><th class="mb-num">当前售卖价格</th>'
  };
  var BOARD_TITLES = {
    gainers48: "涨幅榜 · 48小时", losers48: "跌幅榜 · 48小时",
    gainers24: "涨幅榜 · 24小时", losers24: "跌幅榜 · 24小时",
    hot: "热卖榜 · 在售挂单数", trend: "七天价格榜"
  };
  var BOARD_KEYS = ["gainers48", "losers48", "gainers24", "losers24", "hot", "trend"];

  var state = {
    root: null,
    mode: "regular",
    data: null,
    items: {},
    selectedId: "",
    range: "24h",
    series: null,
    seriesKey: "",
    seriesError: "",
    loading: false,
    watch: [],
    watchSeries: {},
    watchLoading: false,
    sector: "",
    seriesMap: {},        // id -> 7 天真序列（用于重算均价 / 涨跌 / 趋势）
    offersMap: {},        // id -> {current, peak, samples}（热卖榜）
    boards: null,         // 富化后的六张榜
    enrichKey: "",
    enrichLoading: false,
    narrow: false,
    chart: null,
    hover: -1,
    status: "",
    emptySectors: {}      // R306：没有任何 48h 行情的板块（点进去只会是 0 项）
  };
  var ui = {};
  var modeUnsub = null;
  var resizeObserver = null;
  var chartRaf = 0;

  // ---------------------------------------------------------------- 基础工具
  function fmt(n, digits) {
    if (typeof n !== "number" || !isFinite(n)) { return "—"; }
    var d = digits === undefined ? 0 : digits;
    return n.toLocaleString("zh-CN", { minimumFractionDigits: d, maximumFractionDigits: d });
  }
  function money(n) {
    if (typeof n !== "number" || !isFinite(n)) { return "—"; }
    return fmt(n, 0) + " ₽";
  }
  function pct(n) {
    if (typeof n !== "number" || !isFinite(n)) { return "—"; }
    return (n > 0 ? "+" : "") + fmt(n, 2) + "%";
  }
  function sign(n) {
    if (typeof n !== "number" || !isFinite(n)) { return ""; }
    return n > 0 ? "up" : (n < 0 ? "down" : "flat");
  }
  function esc(value) {
    return String(value === undefined || value === null ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) { node.className = cls; }
    if (text !== undefined && text !== null) { node.textContent = String(text); }
    return node;
  }
  function modeLabel(mode) {
    if (mode === "pve") { return "PvE"; }
    if (mode === "pvps") { return "PvPS"; }
    return "PvP";
  }
  // 板块中文名：与后端 market_overview.py 的 SECTOR_LABELS / SECTOR_ORDER 保持一致。
  // 只保留游戏内 Handbook 的十个分类，缺名字时回退显示 key，绝不返回 undefined。
  var SECTOR_ORDER = ["Barter", "Info", "Container", "Key", "Gear",
                      "Weapon", "Mod", "Ammo", "Medical", "Food"];
  var SECTOR_NAMES = {
    Barter: "交换物品", Info: "情报物品", Container: "容器", Key: "钥匙",
    Gear: "装备", Weapon: "武器", Mod: "配件", Ammo: "弹药",
    Medical: "医疗", Food: "饮食"
  };
  function sectorName(key) {
    if (!key) { return "其他"; }
    return SECTOR_NAMES[key] || String(key);
  }
  function sourceLabel(data) {
    if (!data) { return "云端行情"; }
    if (data.cached) { return "云端缓存（非实时）"; }
    return "云端行情";
  }
  function timeText(iso) {
    if (!iso) { return "—"; }
    var d = new Date(iso);
    if (isNaN(d.getTime())) { return String(iso); }
    var pad = function (n) { return n < 10 ? "0" + n : String(n); };
    return pad(d.getMonth() + 1) + "-" + pad(d.getDate()) + " " +
      pad(d.getHours()) + ":" + pad(d.getMinutes());
  }
  function clockText(iso) {
    if (!iso) { return "—"; }
    var d = new Date(iso);
    if (isNaN(d.getTime())) { return String(iso); }
    var pad = function (n) { return n < 10 ? "0" + n : String(n); };
    return pad(d.getHours()) + ":" + pad(d.getMinutes());
  }
  function iconUrl(id) { return "assets/icons-transparent/" + id + ".png"; }
  function fallbackIcon(id) { return "assets/icons-items/" + id + ".webp"; }
  function itemOf(id) { return state.items[id] || null; }
  function nameOf(id) {
    var rec = itemOf(id);
    if (rec && rec.n) { return rec.n; }
    var detail = detailOf(id);
    return (detail && detail.name) || id;
  }
  function detailOf(id) {
    if (state.data && state.data.items && state.data.items[id]) {
      return state.data.items[id];
    }
    var lists = state.data ? [state.data.gainers, state.data.losers, state.data.hot] : [];
    for (var i = 0; i < lists.length; i++) {
      var rows = lists[i] || [];
      for (var j = 0; j < rows.length; j++) {
        if (rows[j].id === id) { return rows[j]; }
      }
    }
    return null;
  }
  function quoteOf(id) {
    if (window.GWMarketData && typeof window.GWMarketData.quote === "function") {
      try { return window.GWMarketData.quote(id); } catch (e) { return null; }
    }
    return null;
  }
  function rangeDef(key) {
    for (var i = 0; i < RANGES.length; i++) {
      if (RANGES[i].key === key) { return RANGES[i]; }
    }
    return RANGES[2];
  }
  function readWatch() {
    var list = [];
    try {
      var raw = localStorage.getItem(LS_WATCH);
      var parsed = raw ? JSON.parse(raw) : [];
      if (Array.isArray(parsed)) {
        list = parsed.filter(function (id, index) {
          return typeof id === "string" && id && parsed.indexOf(id) === index;
        }).slice(0, MAX_WATCH);
      }
    } catch (e) { /* 损坏 / 无痕模式：空自选 */ }
    state.watch = list;
  }
  function saveWatch() {
    try { localStorage.setItem(LS_WATCH, JSON.stringify(state.watch)); } catch (e) { /* 忽略 */ }
  }
  function readRange() {
    try {
      var value = localStorage.getItem(LS_RANGE);
      if (rangeDef(value).key === value) { state.range = value; }
    } catch (e) { /* 默认 24h */ }
  }
  function saveRange() {
    try { localStorage.setItem(LS_RANGE, state.range); } catch (e) { /* 忽略 */ }
  }
  function setStatus(text) {
    state.status = text || "";
    if (ui.status) { ui.status.textContent = state.status; }
  }

  // ---------------------------------------------------------------- 数据加载
  function currentMode() {
    // 全局模式以 GWGameMode 为准（顶栏 PvP / PvE / PvPS 的唯一状态源）；
    // GWMarketData.scope 是数据层的镜像，初始化早期可能还是默认值。
    if (window.GWGameMode && typeof window.GWGameMode.get === "function") {
      try {
        var mode = window.GWGameMode.get();
        if (mode) { return mode; }
      } catch (e) { /* 模式未就绪 */ }
    }
    if (window.GWMarketData && typeof window.GWMarketData.scope === "function") {
      try {
        var scope = window.GWMarketData.scope();
        if (scope && scope.mode) { return scope.mode; }
      } catch (e) { /* 模式未就绪 */ }
    }
    return state.mode || "regular";
  }

  function ensureItems() {
    if (!window.GWMarketData) { return Promise.resolve({}); }
    if (typeof window.GWMarketData.ensure === "function") {
      return window.GWMarketData.ensure().then(function () {
        return window.GWMarketData.items ? window.GWMarketData.items() : {};
      });
    }
    return Promise.resolve(window.GWMarketData.items ? window.GWMarketData.items() : {});
  }

  function load() {
    if (!state.root || state.loading) { return; }
    state.loading = true;
    setStatus("正在读取行情…");
    var ids = [];
    if (state.selectedId) { ids.push(state.selectedId); }
    state.watch.forEach(function (id) { if (ids.indexOf(id) < 0) { ids.push(id); } });
    var url = "api/market-overview?mode=" + encodeURIComponent(state.mode) +
      "&hours=24&itemIds=" + encodeURIComponent(ids.join(",")) +
      "&sector=" + encodeURIComponent(state.sector || "");
    fetch(url, { cache: "no-store" })
      .then(function (res) {
        if (!res.ok) { throw new Error("HTTP " + res.status); }
        return res.json();
      })
      .then(function (data) {
        state.loading = false;
        if (!data || !data.ok) {
          if (data && data.loginRequired) {
            setStatus("市场行情来自云端，需登录账号获取");
          } else {
            setStatus(data && (data.message || data.hint || data.error)
              ? String(data.message || data.hint || data.error) : "云端行情不可用");
          }
          return;
        }
        state.data = data;
        state.mode = data.mode || state.mode;
        if (!state.selectedId) {
          var first = (data.gainers && data.gainers[0] && data.gainers[0].id) ||
            (state.watch[0] || "") || (data.losers && data.losers[0] && data.losers[0].id) || "";
          if (first) { state.selectedId = first; }
        }
        setStatus("");
        renderAll();                 // 先出骨架与已有数据，避免空白等待
        if (state.selectedId) { loadSeries(); }
        loadWatchSeries();
        // 用云端真实序列重算榜单（24h/48h 均价与涨跌），完成后再刷一次榜单
        enrichRanks().then(function () { renderRanks(); });
      })
      .catch(function (err) {
        state.loading = false;
        setStatus("读取失败：" + (err && err.message ? err.message : String(err)));
      });
  }

  /** 历史接口：优先新的大盘路由；老后端没有该路由（404）时退回价格历史接口。 */
  function fetchHistory(url, fallbackUrl) {
    return fetch(url, { cache: "no-store" }).then(function (res) {
      if (res.status === 404 && fallbackUrl) {
        return fetch(fallbackUrl, { cache: "no-store" });
      }
      return res;
    }).then(function (res) {
      if (!res.ok) { throw new Error("HTTP " + res.status); }
      return res.json();
    });
  }

  function loadSeries() {
    var id = state.selectedId;
    if (!id) { state.series = null; state.seriesError = ""; drawChart(); return; }
    var def = rangeDef(state.range);
    var key = id + ":" + state.range + ":" + state.mode;
    if (state.seriesKey === key && state.series) { drawChart(); return; }
    state.seriesKey = key;
    state.series = null;
    state.seriesError = "";
    setStatus("正在读取历史采样…");
    var query = "mode=" + encodeURIComponent(state.mode) +
      "&itemIds=" + encodeURIComponent(id) + "&days=" + def.days;
    fetchHistory("api/market-history?" + query,
                 "api/price-history?" + query.replace("itemIds=", "itemId="))
      .then(function (payload) {
        if (state.seriesKey !== key) { return; }
        if (!payload || payload.ok === false) {
          state.seriesError = (payload && (payload.hint || payload.error)) || "历史接口不可用";
          state.series = null;
        } else {
          var series = (payload.series && payload.series[id]) || null;
          state.series = series && series.points ? series : null;
        }
        setStatus("");
        drawChart();
      })
      .catch(function (err) {
        if (state.seriesKey !== key) { return; }
        state.seriesError = String(err && err.message ? err.message : err);
        state.series = null;
        setStatus("历史读取失败：" + state.seriesError);
        drawChart();
      });
  }

  function loadWatchSeries() {
    if (!state.watch.length) { state.watchSeries = {}; return; }
    var ids = state.watch.slice(0, MAX_WATCH);
    state.watchLoading = true;
    var query = "mode=" + encodeURIComponent(state.mode) +
      "&itemIds=" + encodeURIComponent(ids.join(",")) + "&days=1";
    fetchHistory("api/market-history?" + query, "api/price-history?" + query)
      .then(function (payload) {
        state.watchLoading = false;
        state.watchSeries = (payload && payload.series) || {};
        renderWatch();
      })
      .catch(function () {
        state.watchLoading = false;
        state.watchSeries = {};
        renderWatch();
      });
  }

  // ---------------------------------------------------------------- 渲染
  function renderAll() {
    renderHead();
    renderKpis();
    renderRanks();
    renderSectors();
    renderSelected();
    renderWatch();
  }

  function renderHead() {
    var data = state.data || {};
    var quota = data.quota || {};
    if (ui.source) {
      ui.source.textContent = sourceLabel(data) + " · " + modeLabel(state.mode);
      ui.source.classList.toggle("is-live", !data.cached && !data.dataDelayed);
    }
    if (ui.cutoff) {
      var limit = typeof quota.remaining_today === "number"
        ? " · 今日剩余 " + quota.remaining_today + " 次" : "";
      ui.cutoff.textContent = "截止 " + timeText(data.dataAt || data.generatedAt) + limit;
    }
    if (ui.note) {
      ui.note.textContent = data.cached
        ? "云端暂时取不到新数据，当前为本机上次成功获取的缓存；不伪造新行情。"
        : (data.note || "在售挂单数，非成交量；缺测显示「—」，不插值、不补点。");
    }
    if (ui.modeChip) { ui.modeChip.textContent = modeLabel(state.mode); }
  }

  function kpiValue(key, value, cls) {
    var node = ui["kpi_" + key];
    if (!node) { return; }
    node.textContent = value;
    node.className = "mb-kpi-value" + (cls ? " " + cls : "");
  }

  function renderKpis() {
    var data = state.data || {};
    var summary = data.summary || {};
    var coverage = data.coverage || {};
    kpiValue("items", fmt(summary.items || coverage.items || 0, 0), "");
    kpiValue("up", fmt(summary.up, 0), "up");
    kpiValue("down", fmt(summary.down, 0), "down");
    kpiValue("avg", pct(summary.avgChange), sign(summary.avgChange));
    kpiValue("offers", summary.offers === null || summary.offers === undefined
      ? "—" : fmt(summary.offers, 0), "");
    kpiValue("cutoff", timeText(data.dataAt || data.generatedAt), "small");
  }

  function rankRows(key) {
    var boards = state.boards || state.data || {};
    return boards[key] || [];
  }

  // ------------------------------------------------------- 榜单富化（R291）
  // 上游 changeLast48hPercent 偶发极端异常（某配件显示 +4496%、涨跌额 144 万），
  // 直接拿它排序会被脏数据霸榜。改用云端 /v1/prices/series 的真实采样点重算
  // 24h / 48h 均价与涨跌；|涨跌幅| > 1000% 判为异常，剔除榜单。
  // 基准必须是**均价**而不是窗口第一个点：否则窗口里有个异常低采样时，
  // 会出现「均价 290,754 / 涨跌额 596,666 / +852%」这种三列互相矛盾的行。
  var MAX_PLAUSIBLE_PCT = 1000;

  function seriesWindow(points, hours) {
    if (!points || !points.length) { return []; }
    var lastMs = Date.parse(points[points.length - 1][0]);
    if (!isFinite(lastMs)) { return points.slice(); }
    var cutoff = lastMs - hours * 3600 * 1000;
    var out = [];
    for (var i = 0; i < points.length; i++) {
      var ms = Date.parse(points[i][0]);
      if (!isFinite(ms) || ms >= cutoff) { out.push(points[i]); }
    }
    return out.length ? out : points.slice(-1);
  }

  /** 过去七天价格均值：窗口内真实采样价格的算术平均；没有有效采样返回 null（不上榜）。
   *
   *  异常剔除：跳蚤市场会有人挂出 1,000 万 ₽ 的孤品（例如 PvE 的消音器转接器），
   *  单笔就能把七天均价从 5,000 拉到 486,012。这里以中位数为基准，先剔除
   *  「超过中位数 5 倍」的天价采样，再对剩余采样求平均（仍是平均值口径）。
   */
  function sevenDayAvg(points) {
    var win = seriesWindow(points || [], 7 * 24);
    var vals = [];
    for (var i = 0; i < win.length; i++) {
      var v = win[i][1];
      if (typeof v === "number" && isFinite(v) && v > 0) { vals.push(v); }
    }
    if (!vals.length) { return null; }
    var sorted = vals.slice().sort(function (a, b) { return a - b; });
    var median = sorted[Math.floor(sorted.length / 2)];
    var kept = [];
    for (var j = 0; j < vals.length; j++) {
      if (vals[j] <= median * 5) { kept.push(vals[j]); }
    }
    var use = kept.length ? kept : vals;
    return use.reduce(function (x, y) { return x + y; }, 0) / use.length;
  }

  function enrichItem(id, raw) {
    var pts = state.seriesMap[id] || [];
    var cur = raw && typeof raw.price === "number" ? raw.price : null;
    if (cur === null && pts.length && typeof pts[pts.length - 1][1] === "number") {
      cur = pts[pts.length - 1][1];
    }
    function stat(hours) {
      var win = seriesWindow(pts, hours);
      var vals = [];
      for (var i = 0; i < win.length; i++) {
        var v = win[i][1];
        if (typeof v !== "number" || !isFinite(v) || v <= 0) { continue; }
        vals.push(v);
      }
      if (!vals.length) { return { avg: null, amount: null, change: null }; }
      // 均价、涨跌额、涨跌幅用同一个基准：窗口内真实采样点的算术平均。
      // 涨跌额 = 当前价 - 均价；涨跌幅 = (当前价 / 均价 - 1) × 100%。
      // 绝不拿窗口第一个点当基准 —— 单点异常会把另外两列带偏。
      var avg = vals.reduce(function (x, y) { return x + y; }, 0) / vals.length;
      var amount = (cur !== null) ? cur - avg : null;
      var change = (amount !== null && avg > 0) ? amount / avg * 100 : null;
      return { avg: avg, amount: amount, change: change };
    }
    var s24 = stat(24), s48 = stat(48);
    return {
      id: id, name: (raw && raw.name) || (state.items[id] && state.items[id].n) || id,
      price: cur, offers: raw && typeof raw.offers === "number" ? raw.offers : null,
      avg24: s24.avg, amount24: s24.amount, change24: s24.change,
      avg48: s48.avg, amount48: s48.amount, change48: s48.change,
      points: pts
    };
  }

  function plausible(row, field) {
    var v = row && row[field];
    return typeof v === "number" && isFinite(v) && Math.abs(v) <= MAX_PLAUSIBLE_PCT;
  }

  // 七天趋势强度：衡量「连着涨」。返回最长连续上涨段、其占全部相邻段的比例、
  // 上涨段占比、七天首尾涨幅。排序以「最长连涨段 / 相邻段总数」为主键 ——
  // 不同物资采样密度不同，用比例才能公平比较；一路连涨的比例=1，排最前。
  // 无效采样（非数 / <=0）整点剔掉，不补 0、不插值；时间升序后再逐段比较。
  function trendStrength(points) {
    var rows = [];
    for (var i = 0; i < (points || []).length; i++) {
      var p = points[i];
      if (!p) { continue; }
      var v = p[1];
      if (typeof v !== "number" || !isFinite(v) || v <= 0) { continue; }
      rows.push({ at: Date.parse(p[0]), v: v });
    }
    rows.sort(function (a, b) { return a.at - b.at; });
    if (rows.length < 2) {
      return { streak: 0, streakRatio: 0, upRatio: 0, change7d: null };
    }
    var longest = 0, run = 0, ups = 0, pairs = 0;
    for (var j = 1; j < rows.length; j++) {
      pairs++;
      if (rows[j].v > rows[j - 1].v) {
        ups++;
        run++;
        if (run > longest) { longest = run; }
      } else {
        run = 0;   // 持平或下跌都中断连涨
      }
    }
    var first = rows[0].v, last = rows[rows.length - 1].v;
    return {
      streak: longest,
      streakRatio: pairs ? longest / pairs : 0,
      upRatio: pairs ? ups / pairs : 0,
      change7d: first > 0 ? (last / first - 1) * 100 : null
    };
  }

  function enrichRanks() {
    if (!state.data || state.enrichLoading) { return Promise.resolve(); }
    var key = state.mode + "|" + state.sector + "|" +
      String(state.data.generatedAt || state.data.cutoff || "");
    if (state.enrichKey === key && state.boards) { return Promise.resolve(); }
    state.enrichLoading = true;

    var server = state.data;
    var serverRanks = !!server.gainers24;   // 新后端：六个榜单都由服务端从全市场算出
    var rawById = {};
    (server.gainers || []).concat(server.losers || [], server.hot || []).forEach(function (r) {
      if (r && r.id) { rawById[r.id] = r; }
    });
    // 六个榜单用到的 id 都要取序列（画价格曲线 / 数量曲线）
    ["gainers24", "losers24", "gainers48", "losers48", "trend"].forEach(function (name) {
      (server[name] || []).forEach(function (r) {
        if (r && r.id && !rawById[r.id]) { rawById[r.id] = r; }
      });
    });
    var ids = Object.keys(rawById);
    var jobs = [];
    for (var start = 0; start < ids.length; start += 12) {
      (function (batch) {
        jobs.push(fetch("api/cloud/prices/series?mode=" + encodeURIComponent(state.mode) +
          "&days=7&itemIds=" + encodeURIComponent(batch.join(",")), { cache: "no-store" })
          .then(function (r) { return r.ok ? r.json() : {}; })
          .then(function (d) {
            var pts = (d && d.points) || {};
            batch.forEach(function (id) { state.seriesMap[id] = pts[id] || []; });
          })
          .catch(function () { /* 单批失败：对应榜单显示「—」 */ }));
      })(ids.slice(start, start + 12));
    }
    if (ids.length) {
      // 热卖榜 12 件可能不在涨跌候选的前 24 个里；这里取全部候选（去重后 ≤ 36），
      // 否则热卖榜的 24h 曲线会因拿不到数量序列而全部显示「—」。
      jobs.push(fetch("api/market-offers?mode=" + encodeURIComponent(state.mode) +
        "&hours=24&itemIds=" + encodeURIComponent(ids.join(",")), { cache: "no-store" })
        .then(function (r) { return r.ok ? r.json() : {}; })
        .then(function (d) { state.offersMap = (d && d.items) || {}; })
        .catch(function () { state.offersMap = {}; }));
    }

    return Promise.all(jobs).then(function () {
      function pointsOf(id) { return state.seriesMap[id] || []; }
      function clone(row) {
        var copy = {};
        for (var k in row) {
          if (Object.prototype.hasOwnProperty.call(row, k)) { copy[k] = row[k]; }
        }
        return copy;
      }
      if (serverRanks) {
        // 服务端已从全市场（或当前板块的全量物品）算出六个榜单，这里只补曲线。
        function attach(list) {
          return (list || []).slice(0, 10).map(function (row) {
            var copy = clone(row);
            copy.points = pointsOf(row.id);
            return copy;
          });
        }
        var hotServer = (server.hot || []).slice(0, 10).map(function (row) {
          var o = state.offersMap[row.id] || {};
          var copy = clone(row);
          copy.peak = typeof o.peak === "number" ? o.peak : null;
          copy.samples = o.samples || 0;
          copy.points = o.points || [];
          return copy;
        });
        var trendServer = attach(server.trend);
        trendServer.forEach(function (row) { row.trend = trendStrength(row.points); });
        state.boards = {
          gainers48: attach(server.gainers48), losers48: attach(server.losers48),
          gainers24: attach(server.gainers24), losers24: attach(server.losers24),
          hot: hotServer, trend: trendServer,
          generatedAt: server.generatedAt, minOffers: server.minOffers,
          note: server.note
        };
      } else {
        // 旧后端（没有 gainers24 等字段）回退：从候选池按序列重算
        var rows = ids.map(function (id) { return enrichItem(id, rawById[id]); });
        function pick(field, reverse) {
          return rows.filter(function (r) { return plausible(r, field); })
            .sort(function (a, b) { return reverse ? b[field] - a[field] : a[field] - b[field]; })
            .slice(0, 10);
        }
        var hot = rows.map(function (r) {
          var o = state.offersMap[r.id] || {};
          return {
            id: r.id, name: r.name,
            offers: typeof r.offers === "number"
              ? r.offers
              : (typeof o.current === "number" ? o.current : null),
            peak: typeof o.peak === "number" ? o.peak : null,
            samples: o.samples || 0, price: r.price,
            points: o.points || []
          };
        }).filter(function (r) { return typeof r.offers === "number"; })
          .sort(function (a, b) {
            if (b.offers !== a.offers) { return b.offers - a.offers; }
            return (b.peak === null ? -1 : 1) - (a.peak === null ? -1 : 1);
          }).slice(0, 10);
        var trend = [];
        rows.forEach(function (r) {
          var avg7 = sevenDayAvg(r.points);
          if (avg7 === null) { return; }
          r.avg7 = avg7;
          r.trend = trendStrength(r.points);
          trend.push(r);
        });
        trend.sort(function (a, b) { return b.avg7 - a.avg7; });
        state.boards = {
          gainers48: pick("change48", true), losers48: pick("change48", false),
          gainers24: pick("change24", true), losers24: pick("change24", false),
          hot: hot, trend: trend.slice(0, 10),
          generatedAt: state.data.generatedAt, minOffers: state.data.minOffers,
          note: state.data.note
        };
      }
      state.enrichKey = key;
      state.enrichLoading = false;
    }).catch(function () { state.enrichLoading = false; });
  }

  function sparkSvg(points, width, height) {
    if (!points || points.length < 2) { return ""; }
    var vals = [];
    for (var i = 0; i < points.length; i++) {
      var v = points[i][1];
      if (typeof v === "number" && isFinite(v) && v > 0) { vals.push(v); }
    }
    if (vals.length < 2) { return ""; }
    var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
    if (hi === lo) { hi = lo * 1.01 + 1; lo = Math.max(0, lo * 0.99 - 1); }
    var parts = [], drawn = 0;
    for (var j = 0; j < points.length; j++) {
      var pv = points[j][1];
      if (typeof pv !== "number" || !isFinite(pv) || pv <= 0) { continue; }
      var x = 2 + drawn * (width - 4) / (vals.length - 1);
      var y = height - 2 - (pv - lo) / (hi - lo) * (height - 4);
      parts.push((drawn ? "L" : "M") + x.toFixed(1) + " " + y.toFixed(1));
      drawn++;
    }
    var color = vals[vals.length - 1] >= vals[0] ? "#e5484d" : "#2ea043";
    return '<svg class="mb-table-spark" viewBox="0 0 ' + width + ' ' + height +
      '" width="' + width + '" height="' + height + '" aria-hidden="true">' +
      '<path d="' + parts.join(" ") + '" fill="none" stroke="' + color +
      '" stroke-width="1.4"/></svg>';
  }

  function renderRanks() {
    BOARD_KEYS.forEach(renderRankTable);
    var boards = state.boards || state.data || {};
    var minOffers = typeof boards.minOffers === "number" ? boards.minOffers : null;
    if (ui.rankNotes && minOffers) {
      for (var n = 0; n < ui.rankNotes.length; n++) {
        ui.rankNotes[n].textContent = "仅统计在售 ≥ " + minOffers + " 的物资";
      }
    }
    if (ui.sectorChip) {
      ui.sectorChip.hidden = !state.sector;
      ui.sectorChip.textContent = state.sector
        ? ("板块：" + sectorName(state.sector) + " ×") : "";
    }
  }

  function renderRankTable(key) {
    var card = ui.rankCards && ui.rankCards[key];
    if (!card) { return; }
    var tbody = card.querySelector("tbody");
    if (!tbody) { return; }
    tbody.textContent = "";
    var rows = rankRows(key);
    if (!rows.length) {
      var emptyMsg = state.enrichLoading ? "正在重算榜单…"
        : (state.sector && state.emptySectors && state.emptySectors[state.sector]
          ? sectorName(state.sector) + "板块暂无可统计的行情：板块内多为不上架跳蚤市场的任务情报类物资"
          : "暂无满足条件的数据");
      var tr = el("tr");
      var td = el("td", "mb-table-empty", emptyMsg);
      td.colSpan = key === "trend" ? 5 : (key === "hot" ? 5 : 8);
      tr.appendChild(td);
      tbody.appendChild(tr);
      return;
    }
    rows.forEach(function (row, index) {
      var tr = el("tr", "mb-rank-row");
      tr.appendChild(el("td", "mb-rank-no", String(index + 1)));
      var nameCell = el("td", "mb-rank-name-cell");
      var img = el("img", "mb-item-icon");
      img.loading = "lazy"; img.alt = "";
      img.onerror = function () {
        this.onerror = function () { this.style.visibility = "hidden"; };
        this.src = fallbackIcon(row.id);
      };
      img.src = iconUrl(row.id);
      nameCell.appendChild(img);
      nameCell.appendChild(el("span", "mb-rank-name", row.name || row.id));
      nameCell.title = row.name || row.id;
      tr.appendChild(nameCell);

      if (key === "hot") {
        tr.appendChild(el("td", "mb-num", fmt(row.offers, 0)));
        tr.appendChild(el("td", "mb-num muted", row.peak === null || row.peak === undefined
          ? "—" : fmt(row.peak, 0)));
        var hotSpark = el("td", "mb-spark-cell");
        hotSpark.innerHTML = sparkSvg(row.points || [], 132, 24) || '<span class="mb-muted">—</span>';
        hotSpark.title = "过去24小时在售数量（每小时真实采样）；缺测不补点";
        tr.appendChild(hotSpark);
      } else if (key === "trend") {
        var sparkTd = el("td", "mb-spark-cell");
        sparkTd.innerHTML = sparkSvg(row.points, 132, 24) || '<span class="mb-muted">—</span>';
        var trendInfo = row.trend || {};
        sparkTd.title = "过去七天真实采样价格；缺测不补点" +
          (typeof row.avg7 === "number" ? "；七天均价 " + money(row.avg7) + "（按均价从高到低排序）" : "") +
          (trendInfo.change7d !== null && trendInfo.change7d !== undefined ? "；七天 " + pct(trendInfo.change7d) : "");
        tr.appendChild(sparkTd);
        tr.appendChild(el("td", "mb-num", money(row.avg7)));
        tr.appendChild(el("td", "mb-num strong", money(row.price)));
      } else {
        var is24 = key === "gainers24" || key === "losers24";
        var avg = is24 ? row.avg24 : row.avg48;
        var amount = is24 ? row.amount24 : row.amount48;
        var change = is24 ? row.change24 : row.change48;
        tr.appendChild(el("td", "mb-num strong", money(row.price)));
        tr.appendChild(el("td", "mb-num muted", avg === null ? "—" : money(avg)));
        tr.appendChild(el("td", "mb-num " + sign(amount), amount === null ? "—" : fmt(amount, 0)));
        tr.appendChild(el("td", "mb-num strong " + sign(change), pct(change)));
        // 涨跌榜价格曲线：与趋势榜同宽（132px），位置固定在涨跌幅与在售数量之间。
        // 24h 榜取 24h 采样窗口，48h 榜取 48h；缺测不补点，没有采样显示「—」。
        var winHours = is24 ? 24 : 48;
        var priceSpark = el("td", "mb-spark-cell");
        priceSpark.innerHTML = sparkSvg(seriesWindow(row.points || [], winHours), 132, 24) ||
          '<span class="mb-muted">—</span>';
        priceSpark.title = "过去" + winHours + "小时真实采样价格；缺测不补点";
        tr.appendChild(priceSpark);
        tr.appendChild(el("td", "mb-num muted", row.offers === null || row.offers === undefined
          ? "—" : fmt(row.offers, 0)));
      }
      tr.addEventListener("click", function () { selectItem(row.id, true); });
      tbody.appendChild(tr);
    });
  }

  function renderSectors() {
    var box = ui.sectors;
    if (!box) { return; }
    box.textContent = "";
    var sectors = (state.data && state.data.sectors) || [];
    if (!sectors.length) {
      box.appendChild(el("div", "mb-empty", "暂无板块数据（需要物资带有 48h 涨跌字段）"));
      return;
    }
    // 固定按游戏内十个分类展示（后端只返回有数据的分类，缺的分类补 0 项占位）
    var byKey = {};
    sectors.forEach(function (sector) {
      if (sector && sector.key) { byKey[sector.key] = sector; }
    });
    var list = SECTOR_ORDER.map(function (key) {
      return byKey[key] || {
        key: key, label: sectorName(key), items: 0, up: 0, down: 0,
        offers: 0, avgChange: null
      };
    });
    // R306：板块里没有任何一条 48h 涨跌（情报物品就是这种——板块内 92 个全是
    // 不上架跳蚤市场的任务情报，up/down/flat 全 0）时标记为空板块：
    // chip 置灰不可点，避免「点进去 0 项」的死胡同。
    state.emptySectors = {};
    list.forEach(function (sector) {
      if (!sector.up && !sector.down && !sector.flat &&
          (sector.avgChange === null || sector.avgChange === undefined)) {
        state.emptySectors[sector.key] = true;
      }
    });
    if (!sectors.length) { state.emptySectors = {}; }
    var maxAbs = 1;
    list.forEach(function (sector) {
      var value = Math.abs(Number(sector.avgChange) || 0);
      if (value > maxAbs) { maxAbs = value; }
    });
    list.forEach(function (sector) {
      var value = Number(sector.avgChange) || 0;
      var empty = !!state.emptySectors[sector.key];
      var intensity = Math.min(0.85, 0.16 + Math.abs(value) / maxAbs * 0.55);
      var cell = el("button", "mb-sector " + sign(value) + (empty ? " is-empty" : ""));
      cell.type = "button";
      cell.style.setProperty("--mb-heat", intensity.toFixed(2));
      cell.classList.toggle("is-active", state.sector === sector.key);
      if (empty) { cell.setAttribute("aria-disabled", "true"); }
      cell.appendChild(el("span", "mb-sector-name", sector.label || sector.key));
      cell.appendChild(el("span", "mb-sector-change", pct(sector.avgChange)));
      cell.appendChild(el("span", "mb-sector-meta", empty ? "无行情数据" :
        sector.items + " 项 · 涨 " + sector.up + " / 跌 " + sector.down));
      if (empty) {
        cell.title = (sector.label || sector.key) +
          "：当前数据源没有该板块的行情（板块内多为不上架跳蚤市场的任务情报类物资），不可筛选";
      } else {
        cell.title = (sector.label || sector.key) + "：在售挂单 " + fmt(sector.offers, 0) +
          "；点击查看该板块的涨跌榜";
        cell.addEventListener("click", function () {
          state.sector = state.sector === sector.key ? "" : sector.key;
          load();
        });
      }
      box.appendChild(cell);
    });
  }

  function renderSelected() {
    var box = ui.selectedInfo;
    if (!box) { return; }
    box.textContent = "";
    var id = state.selectedId;
    if (!id) {
      box.appendChild(el("div", "mb-selected-empty", "从涨幅榜、跌幅榜或自选行情里选择一个物资"));
      return;
    }
    var detail = detailOf(id) || {};
    var quote = quoteOf(id) || {};
    var rec = itemOf(id) || {};
    var name = detail.name || rec.n || id;
    var price = (typeof detail.price === "number" ? detail.price
      : (typeof quote.lastLow === "number" ? quote.lastLow : null));
    var change = detail.change;
    var offers = detail.offers;

    var head = el("div", "mb-selected-head");
    var img = el("img", "mb-selected-icon");
    img.alt = "";
    img.onerror = function () {
      this.onerror = function () { this.style.visibility = "hidden"; };
      this.src = fallbackIcon(id);
    };
    img.src = iconUrl(id);
    head.appendChild(img);
    var title = el("div", "mb-selected-title");
    title.appendChild(el("strong", "", name));
    title.appendChild(el("span", "mb-selected-sector", detail.sectorLabel || sectorName(detail.sector) || ""));
    head.appendChild(title);
    var priceBox = el("div", "mb-selected-price");
    priceBox.appendChild(el("span", "mb-selected-last " + sign(change), money(price)));
    priceBox.appendChild(el("span", "mb-selected-change " + sign(change), pct(change)));
    head.appendChild(priceBox);
    box.appendChild(head);

    var meta = el("div", "mb-selected-meta");
    meta.appendChild(el("span", "", "在售 " + (offers === null || offers === undefined ? "—" : fmt(offers, 0))));
    if (typeof detail.changeAmount === "number") {
      meta.appendChild(el("span", sign(detail.changeAmount), "48h " + fmt(detail.changeAmount, 0) + " ₽"));
    }
    if (typeof quote.low === "number" || typeof quote.high === "number") {
      meta.appendChild(el("span", "", "24h 低 " + fmt(quote.low) + " / 高 " + fmt(quote.high)));
    }
    meta.appendChild(el("span", "mb-muted", "涨跌口径：上游 48h"));
    box.appendChild(meta);
  }

  function sparkline(points) {
    var values = [];
    (points || []).forEach(function (point) {
      var value = point && point[1];
      if (typeof value === "number" && isFinite(value) && value > 0) { values.push(value); }
    });
    if (values.length < 2) { return '<span class="mb-spark-empty">—</span>'; }
    var lo = Math.min.apply(null, values);
    var hi = Math.max.apply(null, values);
    if (hi === lo) { hi = lo + 1; }
    var step = 68 / (values.length - 1);
    var d = "";
    values.forEach(function (value, index) {
      var x = index * step;
      var y = 20 - (value - lo) / (hi - lo) * 18;
      d += (index ? " L" : "M") + x.toFixed(1) + " " + y.toFixed(1);
    });
    var cls = values[values.length - 1] >= values[0] ? "up" : "down";
    return '<svg class="mb-spark ' + cls + '" viewBox="0 0 72 24" preserveAspectRatio="none" aria-hidden="true">' +
      '<path d="' + d + '"/></svg>';
  }

  function renderWatch() {
    var box = ui.watchList;
    if (!box) { return; }
    box.textContent = "";
    if (!state.watch.length) {
      var empty = el("div", "mb-watch-empty");
      empty.appendChild(el("p", "", "还没有自选物资。"));
      empty.appendChild(el("p", "mb-muted", "点击右上角「+ 添加」，搜索物资加入自选；这里不会放示例数据。"));
      box.appendChild(empty);
      return;
    }
    state.watch.forEach(function (id) {
      var detail = detailOf(id) || {};
      var quote = quoteOf(id) || {};
      var rec = itemOf(id) || {};
      var price = (typeof detail.price === "number" ? detail.price
        : (typeof quote.lastLow === "number" ? quote.lastLow : null));
      var change = detail.change;
      var row = el("div", "mb-watch-row" + (id === state.selectedId ? " is-active" : ""));
      var img = el("img", "mb-item-icon");
      img.alt = "";
      img.onerror = function () {
        this.onerror = function () { this.style.visibility = "hidden"; };
        this.src = fallbackIcon(id);
      };
      img.src = iconUrl(id);
      row.appendChild(img);
      var info = el("div", "mb-watch-info");
      info.appendChild(el("span", "mb-watch-name", detail.name || rec.n || id));
      info.appendChild(el("span", "mb-watch-sub", money(price) + " · " +
        (change === null || change === undefined ? "—" : pct(change))));
      row.appendChild(info);
      var spark = el("span", "mb-watch-spark");
      spark.innerHTML = sparkline((state.watchSeries[id] && state.watchSeries[id].points) || []);
      row.appendChild(spark);
      var changeNode = el("span", "mb-watch-change " + sign(change), pct(change));
      row.appendChild(changeNode);
      var remove = el("button", "mb-watch-remove", "×");
      remove.type = "button";
      remove.title = "从自选移除";
      remove.addEventListener("click", function (ev) {
        ev.stopPropagation();
        removeWatch(id);
      });
      row.appendChild(remove);
      row.addEventListener("click", function () { selectItem(id, true); });
      box.appendChild(row);
    });
  }

  // ---------------------------------------------------------------- 图表
  function drawChart() {
    var canvas = ui.canvas;
    if (!canvas) { return; }
    var wrap = ui.chartWrap;
    var width = wrap ? Math.max(280, wrap.clientWidth) : 640;
    var height = wrap ? Math.max(200, wrap.clientHeight || 260) : 260;
    var ratio = window.devicePixelRatio || 1;
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    canvas.style.width = width + "px";
    canvas.style.height = height + "px";
    var g = canvas.getContext("2d");
    g.setTransform(ratio, 0, 0, ratio, 0, 0);
    g.clearRect(0, 0, width, height);

    var pad = { left: 54, right: 16, top: 18, bottom: 26 };
    var def = rangeDef(state.range);
    var rawPoints = [];
    if (state.series && state.series.points) {
      state.series.points.forEach(function (point) {
        if (!Array.isArray(point) || point.length < 2) { return; }
        var value = point[1];
        if (typeof value !== "number" || !isFinite(value) || value <= 0) { return; }
        var at = Date.parse(point[0]);
        if (!isFinite(at)) { at = 0; }
        rawPoints.push({ at: at, iso: point[0], price: value, avg: point[2] });
      });
    }
    rawPoints.sort(function (a, b) { return a.at - b.at; });
    // 小时窗口以**最后一个采样点**为基准，而不是机器当前时间：
    // 云端 history 可能滞后，用 now 会把整段真实历史误过滤成空图。
    var points = rawPoints;
    if (def.hours && rawPoints.length) {
      var cutoff = rawPoints[rawPoints.length - 1].at - def.hours * 3600 * 1000;
      points = rawPoints.filter(function (point) { return !point.at || point.at >= cutoff; });
    }
    state.chart = null;
    if (!points.length) {
      drawChartEmpty(g, width, height, state.seriesError);
      return;
    }
    points.sort(function (a, b) { return a.at - b.at; });
    var values = points.map(function (p) { return p.price; });
    var min = Math.min.apply(null, values);
    var max = Math.max.apply(null, values);
    if (max === min) { max = min + Math.max(1, min * 0.01); min = Math.max(0, min - Math.max(1, min * 0.01)); }
    var span = max - min;
    min -= span * 0.08;
    max += span * 0.08;
    var plotW = width - pad.left - pad.right;
    var plotH = height - pad.top - pad.bottom;
    var xFor = function (index) {
      return pad.left + (points.length === 1 ? plotW / 2 : index * plotW / (points.length - 1));
    };
    var yFor = function (value) {
      return pad.top + (max - value) / (max - min) * plotH;
    };

    // 背景网格 + 纵轴价格
    g.strokeStyle = "rgba(255,255,255,0.07)";
    g.lineWidth = 1;
    g.fillStyle = "#7d8896";
    g.font = "10px ui-monospace, Consolas, monospace";
    for (var i = 0; i <= 4; i++) {
      var y = pad.top + plotH * i / 4;
      g.beginPath(); g.moveTo(pad.left, y); g.lineTo(width - pad.right, y); g.stroke();
      var label = max - (max - min) * i / 4;
      g.fillText(shortMoney(label), 4, y + 3);
    }
    // x 轴时间
    var xLabels = [0, Math.floor((points.length - 1) / 2), points.length - 1];
    g.fillStyle = "#7d8896";
    xLabels.forEach(function (index, n) {
      if (index < 0) { return; }
      var text = clockText(points[index].iso);
      var w = g.measureText(text).width;
      var x = xFor(index);
      if (n === 0) { x = pad.left; }
      if (n === 2) { x = width - pad.right - w; }
      else { x -= w / 2; }
      g.fillText(text, x, height - 8);
    });

    // 价格折线 + 面积
    var first = points[0].price;
    var last = points[points.length - 1].price;
    var lineColor = last >= first ? "#e5484d" : "#2ea043";
    var area = g.createLinearGradient(0, pad.top, 0, height - pad.bottom);
    area.addColorStop(0, last >= first ? "rgba(229,72,77,0.22)" : "rgba(46,160,67,0.20)");
    area.addColorStop(1, "rgba(0,0,0,0)");
    g.beginPath();
    points.forEach(function (point, index) {
      var x = xFor(index), y = yFor(point.price);
      if (index === 0) { g.moveTo(x, y); } else { g.lineTo(x, y); }
    });
    var lastX = xFor(points.length - 1);
    var baseY = height - pad.bottom;
    g.lineTo(lastX, baseY);
    g.lineTo(xFor(0), baseY);
    g.closePath();
    g.fillStyle = area;
    g.fill();

    g.beginPath();
    points.forEach(function (point, index) {
      var x = xFor(index), y = yFor(point.price);
      if (index === 0) { g.moveTo(x, y); } else { g.lineTo(x, y); }
    });
    g.strokeStyle = lineColor;
    g.lineWidth = 1.8;
    g.stroke();

    // 最新价标记
    var lastY = yFor(last);
    g.fillStyle = lineColor;
    g.beginPath(); g.arc(lastX, lastY, 3, 0, Math.PI * 2); g.fill();
    g.font = "11px ui-monospace, Consolas, monospace";
    var lastText = money(last);
    var tw = g.measureText(lastText).width;
    var tx = Math.min(width - pad.right - tw - 6, lastX + 8);
    var ty = Math.max(pad.top + 12, lastY - 8);
    g.fillText(lastText, tx, ty);

    state.chart = {
      points: points, xFor: xFor, yFor: yFor, pad: pad, width: width, height: height,
      plotW: plotW, plotH: plotH
    };

    if (state.hover >= 0 && state.hover < points.length) {
      drawHover(g, state.chart);
    }
  }

  function shortMoney(value) {
    if (value >= 1000000) { return (value / 1000000).toFixed(1) + "M"; }
    if (value >= 1000) { return (value / 1000).toFixed(value >= 10000 ? 0 : 1) + "k"; }
    return String(Math.round(value));
  }

  function drawChartEmpty(g, width, height, error) {
    g.fillStyle = "#7d8896";
    g.font = "12px Microsoft YaHei, sans-serif";
    var text = error
      ? "历史读取失败：" + error
      : "暂无历史采样点。市场大盘与市场列表共用云端行情；每次成功获取后在本机累积，攒够两次即可显示曲线。";
    wrapText(g, text, 20, height / 2 - 6, width - 40, 18);
  }

  function wrapText(g, text, x, y, maxWidth, lineHeight) {
    var line = "";
    for (var i = 0; i < text.length; i++) {
      var test = line + text[i];
      if (g.measureText(test).width > maxWidth && line) {
        g.fillText(line, x, y);
        line = text[i];
        y += lineHeight;
      } else {
        line = test;
      }
    }
    if (line) { g.fillText(line, x, y); }
  }

  function drawHover(g, chart) {
    var point = chart.points[state.hover];
    if (!point) { return; }
    var x = chart.xFor(state.hover);
    var y = chart.yFor(point.price);
    g.strokeStyle = "rgba(255,255,255,0.35)";
    g.lineWidth = 1;
    g.setLineDash([3, 3]);
    g.beginPath(); g.moveTo(x, chart.pad.top); g.lineTo(x, chart.height - chart.pad.bottom); g.stroke();
    g.beginPath(); g.moveTo(chart.pad.left, y); g.lineTo(chart.width - chart.pad.right, y); g.stroke();
    g.setLineDash([]);
    g.fillStyle = "#f0b429";
    g.beginPath(); g.arc(x, y, 3.5, 0, Math.PI * 2); g.fill();
    if (ui.tip) {
      ui.tip.hidden = false;
      ui.tip.textContent = timeText(point.iso) + " · " + money(point.price) +
        (typeof point.avg === "number" ? " · 24h 均 " + money(point.avg) : "");
      var left = Math.min(chart.width - 200, Math.max(8, x + 12));
      var top = Math.min(chart.height - 40, Math.max(8, y - 34));
      ui.tip.style.left = left + "px";
      ui.tip.style.top = top + "px";
    }
  }

  function onChartMove(ev) {
    var chart = state.chart;
    if (!chart) { return; }
    var rect = ui.canvas.getBoundingClientRect();
    var x = ev.clientX - rect.left;
    var index = 0;
    var best = Infinity;
    for (var i = 0; i < chart.points.length; i++) {
      var distance = Math.abs(chart.xFor(i) - x);
      if (distance < best) { best = distance; index = i; }
    }
    if (state.hover === index) { return; }
    state.hover = index;
    if (chartRaf) { return; }
    chartRaf = window.requestAnimationFrame(function () {
      chartRaf = 0;
      drawChart();
    });
  }

  function onChartLeave() {
    if (state.hover < 0) { return; }
    state.hover = -1;
    if (ui.tip) { ui.tip.hidden = true; }
    drawChart();
  }

  // ---------------------------------------------------------------- 交互
  function selectItem(id, scroll) {
    if (!id) { return; }
    state.selectedId = id;
    state.hover = -1;
    renderSelected();
    renderWatch();
    renderRanks();
    loadSeries();
    if (scroll && state.narrow && ui.chartCard && ui.chartCard.scrollIntoView) {
      ui.chartCard.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  function addWatch(id) {
    if (!id || state.watch.indexOf(id) >= 0) { return; }
    if (state.watch.length >= MAX_WATCH) { setStatus("自选最多 " + MAX_WATCH + " 个物资"); return; }
    state.watch.push(id);
    saveWatch();
    state.selectedId = id;
    closeSearch();
    renderSelected();
    renderWatch();
    load();
  }

  function removeWatch(id) {
    state.watch = state.watch.filter(function (value) { return value !== id; });
    if (state.watchSeries[id]) { delete state.watchSeries[id]; }
    saveWatch();
    renderWatch();
    load();
  }

  function openSearch() {
    if (!ui.search) { return; }
    ui.search.hidden = false;
    ui.searchInput.value = "";
    renderSearch("");
    ui.searchInput.focus();
  }

  function closeSearch() {
    if (!ui.search) { return; }
    ui.search.hidden = true;
    ui.searchResults.textContent = "";
  }

  function renderSearch(query) {
    var box = ui.searchResults;
    if (!box) { return; }
    box.textContent = "";
    var keyword = String(query || "").trim().toLowerCase();
    if (!keyword) {
      box.appendChild(el("div", "mb-search-hint", "输入中文名 / 英文名 / 物品 id 搜索"));
      return;
    }
    var hits = [];
    var items = state.items || {};
    for (var id in items) {
      if (!Object.prototype.hasOwnProperty.call(items, id)) { continue; }
      var rec = items[id] || {};
      var name = String(rec.n || "");
      var shortName = String(rec.sn || "");
      if (name.toLowerCase().indexOf(keyword) >= 0 ||
          shortName.toLowerCase().indexOf(keyword) >= 0 ||
          id.toLowerCase().indexOf(keyword) >= 0) {
        hits.push({ id: id, name: name || id });
        if (hits.length >= 12) { break; }
      }
    }
    if (!hits.length) {
      box.appendChild(el("div", "mb-search-hint", "没有匹配的物资"));
      return;
    }
    hits.forEach(function (hit) {
      var row = el("button", "mb-search-row");
      row.type = "button";
      var img = el("img", "mb-item-icon");
      img.alt = "";
      img.onerror = function () {
        this.onerror = function () { this.style.visibility = "hidden"; };
        this.src = fallbackIcon(hit.id);
      };
      img.src = iconUrl(hit.id);
      row.appendChild(img);
      row.appendChild(el("span", "", hit.name));
      row.addEventListener("click", function () { addWatch(hit.id); });
      box.appendChild(row);
    });
  }

  function setRange(key) {
    if (rangeDef(key).key !== key) { return; }
    state.range = key;
    saveRange();
    state.series = null;
    state.seriesKey = "";
    var buttons = ui.ranges ? ui.ranges.querySelectorAll("[data-range]") : [];
    for (var i = 0; i < buttons.length; i++) {
      var on = buttons[i].getAttribute("data-range") === key;
      buttons[i].classList.toggle("is-active", on);
      buttons[i].setAttribute("aria-selected", String(on));
    }
    loadSeries();
  }

  // ---------------------------------------------------------------- 骨架
  function kpiBox(key, label) {
    return '<div class="mb-kpi"><span class="mb-kpi-label">' + label +
      '</span><strong class="mb-kpi-value" data-kpi="' + key + '">—</strong></div>';
  }

  function buildSkeleton() {
    state.root.innerHTML =
      '<div class="mb-terminal">' +
        '<header class="mb-head">' +
          '<div class="mb-head-title"><h2>市场大盘</h2>' +
            '<span class="mb-chip" data-k="mode">PvP</span>' +
            '<span class="mb-sub" data-k="source">—</span></div>' +
          '<div class="mb-head-right"><span class="mb-cutoff" data-k="cutoff">—</span>' +
            '<button type="button" class="mb-refresh">刷新</button></div>' +
        '</header>' +
        '<div class="mb-note" data-k="note">在售挂单数，非成交量；缺测显示「—」，不插值、不补点。</div>' +
        '<div class="mb-kpis">' +
          kpiBox("items", "有效物资") + kpiBox("up", "上涨") + kpiBox("down", "下跌") +
          kpiBox("avg", "平均 48h 涨跌") + kpiBox("offers", "在售挂单") +
          kpiBox("cutoff", "数据截止") +
        '</div>' +
        '<div class="mb-main">' +
          '<section class="mb-card mb-chart-card">' +
            '<div class="mb-card-head mb-chart-head">' +
              '<div class="mb-selected-info" data-k="selected"></div>' +
              '<div class="mb-ranges" role="tablist" aria-label="时间范围"></div>' +
            '</div>' +
            '<div class="mb-chart-wrap"><canvas class="mb-chart"></canvas>' +
              '<div class="mb-chart-tip" hidden></div></div>' +
            '<div class="mb-chart-foot"><span>价格曲线：跳蚤最新低价</span>' +
              '<span class="mb-muted">历史不足时不画假线</span></div>' +
          '</section>' +
          '<aside class="mb-card mb-watch-card">' +
            '<div class="mb-card-head"><h3>自选行情</h3>' +
              '<button type="button" class="mb-watch-add">+ 添加</button></div>' +
            '<div class="mb-watch-search" hidden>' +
              '<input type="search" class="mb-watch-input" placeholder="搜索物资加入自选…" spellcheck="false">' +
              '<div class="mb-search-results"></div></div>' +
            '<div class="mb-watch-list"></div>' +
          '</aside>' +
        '</div>' +
        '<div class="mb-lower">' +
          rankCard("trend") + rankCard("hot") +
          rankCard("gainers24") + rankCard("losers24") +
          rankCard("gainers48") + rankCard("losers48") +
        '</div>' +
        '<section class="mb-card mb-sector-card">' +
          '<div class="mb-card-head"><h3>板块行情</h3>' +
            '<button type="button" class="mb-sector-chip" data-k="sector" hidden></button></div>' +
          '<div class="mb-sectors" data-k="sectors"></div>' +
        '</section>' +
        '<div class="mb-status" role="status" aria-live="polite"></div>' +
      '</div>';

    ui = {
      source: state.root.querySelector('[data-k="source"]'),
      cutoff: state.root.querySelector('[data-k="cutoff"]'),
      note: state.root.querySelector('[data-k="note"]'),
      modeChip: state.root.querySelector('[data-k="mode"]'),
      kpi_items: state.root.querySelector('[data-kpi="items"]'),
      kpi_up: state.root.querySelector('[data-kpi="up"]'),
      kpi_down: state.root.querySelector('[data-kpi="down"]'),
      kpi_avg: state.root.querySelector('[data-kpi="avg"]'),
      kpi_offers: state.root.querySelector('[data-kpi="offers"]'),
      kpi_cutoff: state.root.querySelector('[data-kpi="cutoff"]'),
      selectedInfo: state.root.querySelector('[data-k="selected"]'),
      ranges: state.root.querySelector(".mb-ranges"),
      chartWrap: state.root.querySelector(".mb-chart-wrap"),
      chartCard: state.root.querySelector(".mb-chart-card"),
      canvas: state.root.querySelector(".mb-chart"),
      tip: state.root.querySelector(".mb-chart-tip"),
      watchList: state.root.querySelector(".mb-watch-list"),
      watchAdd: state.root.querySelector(".mb-watch-add"),
      search: state.root.querySelector(".mb-watch-search"),
      searchInput: state.root.querySelector(".mb-watch-input"),
      searchResults: state.root.querySelector(".mb-search-results"),
      rankCards: (function () {
        var map = {};
        BOARD_KEYS.forEach(function (k) {
          map[k] = state.root.querySelector('[data-rank-card="' + k + '"]');
        });
        return map;
      })(),
      rankNotes: state.root.querySelectorAll(".mb-rank-note"),
      sectorChip: state.root.querySelector('[data-k="sector"]'),
      sectors: state.root.querySelector('[data-k="sectors"]'),
      status: state.root.querySelector(".mb-status")
    };

    // 时间范围按钮
    RANGES.forEach(function (range) {
      var btn = el("button", "mb-range" + (range.key === state.range ? " is-active" : ""), range.label);
      btn.type = "button";
      btn.setAttribute("data-range", range.key);
      btn.setAttribute("role", "tab");
      btn.setAttribute("aria-selected", String(range.key === state.range));
      btn.addEventListener("click", function () { setRange(range.key); });
      ui.ranges.appendChild(btn);
    });
    // 刷新 / 自选 / 榜单 Tab
    state.root.querySelector(".mb-refresh").addEventListener("click", function () {
      state.seriesKey = "";
      load();
      loadWatchSeries();
    });
    ui.watchAdd.addEventListener("click", function () {
      if (ui.search.hidden) { openSearch(); } else { closeSearch(); }
    });
    ui.searchInput.addEventListener("input", function () { renderSearch(ui.searchInput.value); });
    ui.searchInput.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape") { closeSearch(); }
    });
    ui.canvas.addEventListener("mousemove", onChartMove);
    ui.canvas.addEventListener("mouseleave", onChartLeave);
    // 板块筛选 chip 清除
    ui.sectorChip.addEventListener("click", function () {
      state.sector = "";
      load();
    });
  }

  function rankCard(key) {
    return '<section class="mb-card mb-rank-card" data-rank-card="' + key + '">' +
      '<div class="mb-card-head"><h3>' + BOARD_TITLES[key] + '</h3>' +
        '<span class="mb-muted mb-rank-note">在售挂单数 · 非成交量</span></div>' +
      '<div class="mb-table-wrap"><table class="mb-table mb-table-' + key + '">' +
        '<thead><tr>' + BOARD_HEADS[key] + '</tr></thead>' +
        '<tbody></tbody></table></div></section>';
  }

  function applyNarrow() {
    var width = state.root ? state.root.clientWidth : 0;
    var narrow = width > 0 && width < 1180;
    if (narrow === state.narrow) { return; }
    state.narrow = narrow;
    var terminal = state.root.querySelector(".mb-terminal");
    if (terminal) { terminal.classList.toggle("is-narrow", narrow); }
    drawChart();
  }

  function mount() {
    if (state.root) { return; }
    state.root = document.getElementById("market-board-pane");
    if (!state.root) { return; }
    state.mode = currentMode();
    readWatch();
    readRange();
    buildSkeleton();
    ensureItems().then(function (items) {
      state.items = items || {};
      renderWatch();
    });
    if (!modeUnsub && window.GWMarketData && typeof window.GWMarketData.onModeChange === "function") {
      modeUnsub = window.GWMarketData.onModeChange(function () {
        var next = currentMode();
        if (next === state.mode) { return; }
        state.mode = next;
        state.series = null;
        state.seriesKey = "";
        state.watchSeries = {};
        state.data = null;
        state.boards = null;
        state.enrichKey = "";
        if (state.root && !state.root.closest(".view-pane[hidden]")) { load(); }
      });
    }
    if (window.ResizeObserver) {
      resizeObserver = new ResizeObserver(function () {
        applyNarrow();
      });
      resizeObserver.observe(state.root);
    } else {
      window.addEventListener("resize", applyNarrow);
    }
    applyNarrow();
  }

  function open() {
    if (!state.root) { return; }
    state.mode = currentMode();
    // 面板刚从 hidden 变为可见时 clientWidth 才有值；下一帧再量一次，
    // 保证 1024px 下能切到「涨跌榜 Tab + 单列」布局。
    window.requestAnimationFrame(applyNarrow);
    load();
  }

  function isVisible() {
    if (!state.root || state.root.hidden) { return false; }
    return !(state.root.closest && state.root.closest(".view-pane[hidden]"));
  }

  function onPricesUpdated() { if (isVisible()) { load(); } }
  function refreshMeta() { if (isVisible()) { load(); } }

  window.GWMarketBoard = { mount: mount, open: open, onPricesUpdated: onPricesUpdated,
                           refreshMeta: refreshMeta };
})();
