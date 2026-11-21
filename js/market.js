/* R97 市场视图（对照 db4tarkov.com/market 的信息架构）
 *
 * 第一块：列表 + 工具栏 + 筛选（搜索 / Lv / 价格口径 / 类型 / 排序 / 列断点 / 空态）。
 * 数据只读既有 data/items.json；行情按**当前游戏模式**经 window.GWMarketData.snapshot / quote
 * 读取，来源由服务端分层决定：
 *   · 免费 / 登录用户 → 云端行情：免费账号延迟 12 小时、每日 24 次、CD 59:59；
 *   · 会员 → 云端最新行情，CD 30 秒、每日不限次；
 *   · 未登录 → 只显示登录引导，不请求云端；
 *   · 云端不可达 → 本机上次成功结果，明确标「缓存（非实时）」。
 * 运行期不联网（只有本机 127.0.0.1 的 BFF 请求），也不新建价格数据层。
 *
 * 诚实边界：
 *   · 只显示当前模式行情里真实存在的字段；缺值一律「—」，不估算、不插值、不用别的字段冒充。
 *   · 当前模式没有可用数据时明确显示空态，绝不用其他模式的价格顶替。
 *   · Avg 7d：云端 history 提供；免费账号整体延迟 12 小时，缺日不插值。
 *   · 历史 72h 缩略图：会员读云端 /v1/prices/series（采集机真实采样点）；
 *     采样不足 2 点显示「—」，非会员 / 未登录显示「会员功能」，绝不画伪曲线。
 *   · 数据截止时间显式标注；免费 / 缓存数据明确标「延迟 12 小时 / 缓存」，超过 2 小时另加过期提示。
 */
(function () {
  "use strict";

  var LS_MARKET = "eftmap.market.v1";
  var CHUNK = 120;
  var STALE_HOURS = 2;

  var root = null;
  var api = null;
  var loading = false;
  var loaded = false;
  var modeUnsub = null;
  var rows = [];
  var filtered = [];
  var shown = 0;
  var ui = {};
  var rowById = {};
  /** 反向兑换索引：物品 id → [{outId, need, qty, trader}]（来自其他物品的 barter 配方） */
  var usesIndex = {};
  /** 行选中（按物品 id，跨筛选保留） */
  var selectedIds = {};
  var toastTimer = 0;
  var modalOpen = false;
  var modalRow = null;
  var modalTab = "obtain";

  // R218/R278 历史价格曲线：本机快照 + 云端历史（会员）双来源，按模式 / 物品 / 时间窗缓存一次请求。
  var HIST_RANGES = [
    { days: 1, label: "24h" },
    { days: 7, label: "7 天" },
    { days: 30, label: "30 天" },
    { days: 0, label: "全部" }
  ];
  var histState = { key: "", days: 7, phase: "idle", data: null, error: null, token: 0 };
  var modalLastFocus = null;
  var preloadedIcons = [];
  /** 任务目标反向索引：物品 id → [{taskId, taskName, traderId, kindZh, descZh, count, kinds, optional}] */
  var questIndex = {};
  var questState = { mode: null, loading: false, loaded: false, error: null, tasks: 0, objectives: 0 };
  /** Sell to 默认只显示最高收购，展开后才列出全部商人 */
  var sellToExpanded = false;

  var PRICE_MODES = [
    { key: "last", label: "最新", en: "Last", hint: "lastLowPrice：最近一次跳蚤最低挂单" },
    { key: "avg24h", label: "24h 均价", en: "Avg 24h", hint: "avg24hPrice：24 小时历史均价" },
    { key: "avg7d", label: "7 日均价", en: "Avg 7d", hint: "云端价格缓存过去 7 天均价（中位数×5 剔除天价）；无采样时显示积累中，不插值" },
    { key: "slot", label: "每格", en: "Price/Slot", hint: "基准价 ÷ 格数（gw × gh）；基准价 = 最新低价，缺失时用 24h 均价" },
    { key: "kg", label: "每公斤", en: "Price/Kg", hint: "基准价 ÷ 重量（kg）；基准价 = 最新低价，缺失时用 24h 均价" }
  ];

  var TYPE_FILTERS = [
    { key: "barter", label: "以物易物", types: ["barter"] },
    { key: "keys", label: "钥匙", types: ["keys"] },
    { key: "gun", label: "武器", types: ["gun"] },
    { key: "armor", label: "护甲装备", types: ["armor", "helmet", "armorPlate", "rig"] },
    { key: "meds", label: "医疗", types: ["meds", "injectors"] },
    { key: "food", label: "食品饮料", types: ["provisions"] },
    { key: "container", label: "容器", types: ["container", "backpack"] }
  ];

  var SORT_DEFAULT = { key: "profit", dir: -1 };

  // Lv 上限默认取满 40：实测 db4 截图（02/07）滑杆手柄停在最右刻度，且列表里 Lv 25/30 的行
  // 照常显示；把默认当成 20 会把 Lv 25+ 整段藏起来（连 ledX 都搜不到），与对照站行为不符。
  var LV_MAX = 40;

  var st = {
    query: "",
    lv: LV_MAX,
    priceMode: "last",
    types: [],
    sortKey: SORT_DEFAULT.key,
    sortDir: SORT_DEFAULT.dir,
    modeMismatch: false
  };

  // ---------------------------------------------------------------- 小工具
  function num(v) {
    return (typeof v === "number" && isFinite(v)) ? v : null;
  }

  function fmt(n) {
    if (typeof n !== "number" || !isFinite(n)) { return "—"; }
    return String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  }

  function pad2(n) { return n < 10 ? "0" + n : String(n); }

  function parseTime(ts) {
    if (!ts || ts === "live") { return null; }
    var d = new Date(ts);
    return isNaN(d.getTime()) ? null : d;
  }

  function shortAge(ts) {
    var d = parseTime(ts);
    if (!d) { return ""; }
    var sec = Math.max(0, Math.round((Date.now() - d.getTime()) / 1000));
    if (sec < 60) { return "刚刚"; }
    var min = Math.round(sec / 60);
    if (min < 60) { return min + " 分钟前"; }
    var hr = Math.round(min / 60);
    if (hr < 24) { return hr + " 小时前"; }
    return Math.round(hr / 24) + " 天前";
  }

  function clockText(d) {
    return pad2(d.getHours()) + ":" + pad2(d.getMinutes());
  }

  /** 秒 → 「2 小时 5 分钟」（用于「数据已过期 N」这类明确提示）。 */
  function agePhrase(sec) {
    if (sec === null || sec === undefined || !isFinite(+sec)) { return "未知时长"; }
    sec = Math.max(0, Math.round(+sec));
    if (sec < 60) { return "不到 1 分钟"; }
    var min = Math.floor(sec / 60);
    if (min < 60) { return min + " 分钟"; }
    var hr = Math.floor(min / 60);
    var restMin = min % 60;
    return hr + " 小时" + (restMin ? " " + restMin + " 分钟" : "");
  }

  /**
   * R220：数据年龄一律按「当前时间 − snapshotAt」现算。
   * 服务端返回的 ageSec 只在缺少可解析时间戳时兜底——旧版会把 ageSec 连同快照一起缓存，
   * 于是同一行出现「数据截止 11-09 15:01（20 小时前）· 已过期 8 小时 54 分钟」这种自相矛盾。
   */
  function liveAgeSec(snap) {
    if (!snap) { return null; }
    var d = parseTime(snap.snapshotAt);
    if (d) {
      return Math.max(0, Math.round((Date.now() - d.getTime()) / 1000));
    }
    return (typeof snap.ageSec === "number" && isFinite(snap.ageSec)) ? snap.ageSec : null;
  }

  /** 过期判定同样现算，阈值优先用服务端给的 staleAfterSec。 */
  function liveStale(snap) {
    if (!snap) { return false; }
    var age = liveAgeSec(snap);
    if (age === null) { return !!snap.stale; }
    var limit = (typeof snap.staleAfterSec === "number" && isFinite(snap.staleAfterSec))
      ? snap.staleAfterSec : (STALE_HOURS * 3600);
    return age > limit;
  }

  function normalizeQuery(q) {
    return String(q || "").trim().toLowerCase();
  }

  /**
   * 从中文全名推出短名（与 app.js 的 shortNameOf 完全同一套规则）。
   * 本地 items.json 的 `sn` 实测是 "5a16b8a9fcdbcb00165aa6ca ShortName" 这种
   * 「id + 字段名」占位串，不能直接显示；数据已进 SHA-256 契约，不在前端改数据，只在显示层推导。
   */
  function shortNameOf(name) {
    var head = String(name || "").split("（")[0];
    var m = head.match(/[A-Za-z0-9][A-Za-z0-9._-]*(?:[ ][A-Za-z0-9][A-Za-z0-9._-]*)*/);
    return m ? m[0] : "";
  }

  // ---------------------------------------------------------------- 商人 / 计数 / 剪贴板
  /** R280：商人显示名与任务界面**同一口径** —— data/tasks/traders.json 的 nameEn。
   *  任务界面（tasks.js 的 tk-trader-card）用 tr.nameEn 且标记 data-i18n-skip，
   *  不做中文机翻。市场页以前用 items.json 的 n（其中 5 条是中文）再按 slug
   *  自己拼英文，拼出 "Btr Driver" / "Mr Kerman" 这种和任务界面不一致的名字。
   *  这里以 tasks.json 的英文原名为准；缺记录的 id 才退回 items.json 的英文 n。
   *  测试 test_r280_trader_display.py 会逐条比对本表与 tasks.json，防止数据漂移。 */
  var TRADER_EN = {
    "54cb50c76803fa8b248b4571": "Prapor",
    "54cb57776803fa99248b456e": "Therapist",
    "579dc571d53a0658a154fbec": "Fence",
    "58330581ace78e27b8b10cee": "Skier",
    "5935c25fb3acc3127c3d8cd9": "Peacekeeper",
    "5a7c2eca46aef81a7ca2145d": "Mechanic",
    "5ac3b934156ae10c4430e83c": "Ragman",
    "5c0647fdd443bc2504c2d371": "Jaeger",
    "638f541a29ffd1183d187f57": "Lightkeeper",
    "68fe15910f29ba3fdbba9d54": "Taran",
    "68fe15990f29ba3fdbba9d55": "Radio Station",
    "656f0f98d80a697f855d34b1": "BTR Driver",
    "6617beeaa9cfa777ca915b7c": "Ref",
    "688246518448b05efd61d461": "Mr. Kerman",
    "688246958448b05efd61d462": "Voevoda",
    "69e0d6cc77b63940375b9173": "Survivor"
  };

  /** 任务界面用的商人头像（游戏素材，构建期落盘）：portraits/<id>.webp。
   *  自绘 SVG（items.json traders[].img）只在头像缺失时兜底。 */
  var TRADER_PORTRAIT_DIR = "assets/icons-traders/portraits/";
  var TRADER_ICON_DIR = "assets/icons-traders/";

  function traderNameOf(id) {
    if (TRADER_EN[id]) { return TRADER_EN[id]; }
    var t = (api && api.traders) ? api.traders()[id] : null;
    if (!t || !t.n) { return "商人未确认"; }
    // 兜底：items.json 里已是英文就直接用；仍是中文则按 slug 还原，绝不显示中文机翻名。
    if (/[\u4e00-\u9fff]/.test(t.n) && t.nn) {
      return String(t.nn).split("-").map(function (w) {
        if (!w) { return w; }
        if (w === "btr") { return "BTR"; }
        return w.charAt(0).toUpperCase() + w.slice(1);
      }).join(" ");
    }
    return t.n;
  }

  /** 商人头像路径：与任务界面 db4Face 的 tr.portrait 完全同一个文件。 */
  function traderIconSrc(id) {
    if (!id) { return TRADER_ICON_DIR + "unknown.svg"; }
    return TRADER_PORTRAIT_DIR + id + ".webp";
  }

  function traderIconFallbackSrc(id) {
    var t = (api && api.traders) ? api.traders()[id] : null;
    var nn = t && t.nn;
    return nn ? (TRADER_ICON_DIR + nn + ".svg") : (TRADER_ICON_DIR + "unknown.svg");
  }

  function traderIcon(id, size, cls) {
    var img = document.createElement("img");
    img.className = cls || "mk-trader";
    img.width = size;
    img.height = size;
    img.alt = "";
    img.title = traderNameOf(id);
    var fallback = traderIconFallbackSrc(id);
    // 头像缺文件（离线/裁剪包）时回落任务界面的自绘 SVG，只回退一次，避免 404 死循环。
    img.onerror = function () {
      this.onerror = function () { this.onerror = null; this.src = TRADER_ICON_DIR + "unknown.svg"; };
      this.src = fallback;
    };
    img.src = traderIconSrc(id);
    return img;
  }

  /** 先发商人头像请求，避免 120 行同时创建 img 时被地图资源挤到队尾（实测有图标晚 1s+ 才出现）。 */
  function preloadTraderIcons() {
    var map = (api && api.traders) ? api.traders() : null;
    if (!map) { return; }
    var srcs = [TRADER_ICON_DIR + "unknown.svg"];
    Object.keys(map).forEach(function (k) {
      srcs.push(traderIconSrc(k));
      srcs.push(traderIconFallbackSrc(k));
    });
    srcs.forEach(function (src) {
      var im = new Image();
      im.src = src;
      preloadedIcons.push(im);
    });
  }

  function showToast(text) {
    if (!ui.toast) { return; }
    ui.toast.textContent = text;
    ui.toast.hidden = false;
    ui.toast.classList.add("is-on");
    if (toastTimer) { clearTimeout(toastTimer); }
    toastTimer = setTimeout(function () {
      ui.toast.classList.remove("is-on");
      ui.toast.hidden = true;
    }, 1800);
  }

  /** 复制纯文本：优先 Clipboard API；不可用时退回隐藏 textarea + execCommand。
   *  两条路径都只操作本机剪贴板，不发起任何网络请求。 */
  function copyText(text, okText) {
    var done = function () { showToast(okText || "已复制"); };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, function () { legacyCopy(text, done); });
      return;
    }
    legacyCopy(text, done);
  }

  function legacyCopy(text, done) {
    var ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.left = "-9999px";
    document.body.appendChild(ta);
    ta.select();
    var ok = false;
    try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
    document.body.removeChild(ta);
    if (ok) { done(); } else { showToast("复制失败：浏览器拒绝了剪贴板访问"); }
  }

  function rowCopyLine(row) {
    var name = row.name + (row.short && row.short !== row.name ? "（" + row.short + "）" : "");
    var price = row.quote.lastLow === null ? "最新价缺失" : (fmt(row.quote.lastLow) + " ₽");
    return name + " — " + price;
  }

  function readPrefs() {
    try {
      var raw = localStorage.getItem(LS_MARKET);
      if (!raw) { return; }
      var p = JSON.parse(raw);
      if (!p || typeof p !== "object") { return; }
      if (typeof p.lv === "number" && p.lv >= 0 && p.lv <= 40) { st.lv = p.lv; }
      if (PRICE_MODES.some(function (m) { return m.key === p.priceMode; })) { st.priceMode = p.priceMode; }
      if (Array.isArray(p.types)) {
        st.types = p.types.filter(function (k) {
          return TYPE_FILTERS.some(function (f) { return f.key === k; });
        });
      }
      if (typeof p.sortKey === "string") { st.sortKey = p.sortKey; }
      if (p.sortDir === 1 || p.sortDir === -1) { st.sortDir = p.sortDir; }
    } catch (e) { /* 隐私模式 / 旧值忽略 */ }
  }

  function savePrefs() {
    try {
      localStorage.setItem(LS_MARKET, JSON.stringify({
        lv: st.lv, priceMode: st.priceMode, types: st.types,
        sortKey: st.sortKey, sortDir: st.sortDir
      }));
    } catch (e) { /* 忽略 */ }
  }

  // ---------------------------------------------------------------- 数据
  function traderBuyOf(rec) {
    var best = null;
    (rec.trade || []).forEach(function (t) {
      if (!t || t.k !== "buy") { return; }
      var p = num(t.p);
      if (p === null || p <= 0) { return; }
      if (best === null || p < best.price) { best = { price: p, trader: t.t || null, lv: t.l || null, c: t.c || "RUB" }; }
    });
    return best;
  }

  /** 当前模式的市场行情（未就绪 / 模式不符 / 不可用时返回 null）。 */
  function snapshotPayload() {
    var snap = api && api.snapshot ? api.snapshot() : null;
    if (!snap) { return null; }
    // 切模式后 app.js 的旧 payload 仍在内存里：模式不符一律当没有，绝不跨模式展示。
    return snap.mode === st.scopeMode() ? snap : null;
  }

  /** 行情来源的人话标签（免费 / 会员都来自云端）。 */
  function sourceLabel(snap) {
    if (!snap) { return "行情"; }
    if (snap.cached) { return "云端缓存（非实时）"; }
    if (snap.dataDelayed) { return "云端行情（延迟 12 小时）"; }
    return "云端行情";
  }

  /** 当前来源是否「非实时」（免费内置或会员离线回退）。 */
  function sourceNonLive(snap) {
    return !snap || snap.live !== true;
  }

  function buildRows() {
    // 清掉上次会员会话遗留的本地均价档位；免费档只展示云端最新价。
    if (api && typeof api.isMember === "function" && !api.isMember()) {
      st.priceMode = "last";
    }
    var items = api.items() || {};
    var snap = snapshotPayload();
    var fItems = (snap && snap.available && snap.items) || {};
    rows = [];
    rowById = {};
    usesIndex = {};
    Object.keys(fItems).forEach(function (id) {
      var rec = items[id];
      if (!rec) { return; }
      var quote = api.quote(id);
      if (!quote) { return; }
      var buy = traderBuyOf(rec);
      var sell = quote.lastLow;
      var profit = (buy && sell !== null) ? (sell - buy.price) : null;
      var base = (quote.lastLow !== null) ? quote.lastLow : quote.avg24h;
      var gw = num(rec.gw);
      var gh = num(rec.gh);
      var weight = num(rec.w);
      var perSlot = (base !== null && gw !== null && gh !== null && gw > 0 && gh > 0) ? (base / (gw * gh)) : null;
      var perKg = (base !== null && weight !== null && weight > 0) ? (base / weight) : null;
      var typeSet = {};
      (rec.ts || []).forEach(function (t) { typeSet[t] = true; });
      var row = {
        id: id,
        rec: rec,
        name: rec.n || id,
        short: shortNameOf(rec.n),
        lv: api.level(id),
        quote: quote,
        buy: buy,
        sell: sell,
        profit: profit,
        perSlot: perSlot,
        perKg: perKg,
        types: typeSet,
        noFlea: !!typeSet.noFlea,
        sellTo: (rec.sl || []).filter(function (x) {
          return Array.isArray(x) && x[0] && typeof x[1] === "number" && x[1] > 0;
        })
      };
      rows.push(row);
      rowById[id] = row;
    });

    // 反向兑换索引（真实数据）：别的物品的 barter 配方里需要本物品。
    rows.forEach(function (row) {
      (row.rec.trade || []).forEach(function (t) {
        if (!t || t.k !== "barter" || !Array.isArray(t.r)) { return; }
        t.r.forEach(function (need) {
          if (!Array.isArray(need) || !need[0]) { return; }
          var n = num(need[1]);
          if (n === null || n <= 0) { return; }
          if (!usesIndex[need[0]]) { usesIndex[need[0]] = []; }
          usesIndex[need[0]].push({
            outId: row.id,
            need: n,
            qty: num(t.o) || 1,
            trader: t.t || null
          });
        });
      });
    });
  }

  function resetQuestIndex() {
    questIndex = {};
    questState = { mode: null, loading: false, loaded: false, error: null, tasks: 0, objectives: 0 };
  }

  /** 从本地任务数据反算「哪些任务把该物品列为目标物品」。
   *  只读 objectives[].items[].id / item / questItem 这些真实字段，不做语义猜测：
   *  同一目标里并列多个物品是上游「任一」语义，界面按「N 种任一」标注，不假装全部必需。 */
  function buildQuestIndex(doc, mode) {
    var tasks = (doc && doc.tasks) || {};
    var idx = {};
    var taskCount = 0;
    var objCount = 0;
    Object.keys(tasks).forEach(function (tid) {
      var t = tasks[tid] || {};
      taskCount += 1;
      var seen = {};
      (t.objectives || []).forEach(function (o) {
        objCount += 1;
        var ids = [];
        (o.items || []).forEach(function (x) {
          if (x && x.id && ids.indexOf(x.id) < 0) { ids.push(x.id); }
        });
        ["item", "questItem"].forEach(function (k) {
          if (o[k] && o[k].id && ids.indexOf(o[k].id) < 0) { ids.push(o[k].id); }
        });
        var kinds = ids.length;
        // 「卖任何物品给某人」这类目标会把上千种物品都列进 items：它对每件物品都成立，
        // 但不针对单一物品。归为「通用目标」单独汇总，避免把 Uses 刷成一屏噪声。
        var generic = kinds >= 1000;
        ids.forEach(function (iid) {
          var key = iid + "@" + tid + ":" + (o.id || "");
          if (seen[key]) { return; }
          seen[key] = true;
          if (!idx[iid]) { idx[iid] = []; }
          idx[iid].push({
            taskId: tid,
            taskName: t.nameZh || t.englishName || t.nameEn || tid,
            traderId: t.traderId || null,
            kindZh: o.kindZh || o.type || "目标",
            descZh: o.descZh || "",
            count: num(o.count),
            kinds: kinds,
            generic: generic,
            optional: !!o.optional
          });
        });
      });
    });
    questIndex = idx;
    questState.mode = mode;
    questState.loaded = true;
    questState.loading = false;
    questState.error = null;
    questState.tasks = taskCount;
    questState.objectives = objCount;
  }

  /** 首次打开 Uses 时才读任务数据（tasks.<mode>.json 约 3 MB，不放在市场视图启动路径上）。 */
  function ensureQuestIndex() {
    if (questState.loaded || questState.loading) { return; }
    if (!api || !api.loadTasks) {
      questState.loaded = true;
      questState.error = "本页没有提供任务数据读取接口（GWMarketData.loadTasks）";
      return;
    }
    var mode = st.scopeMode();
    questState.loading = true;
    questState.mode = mode;
    questState.error = null;
    api.loadTasks(mode).then(function (doc) {
      // 模式可能在读取期间被切换；旧模式的结果不能混进当前模式。
      if (st.scopeMode() !== mode) { resetQuestIndex(); return; }
      buildQuestIndex(doc, mode);
      repaintUses();
    }).catch(function (err) {
      if (st.scopeMode() !== mode) { resetQuestIndex(); return; }
      questState.loading = false;
      questState.loaded = true;
      questState.error = String((err && err.message) || err);
      repaintUses();
    });
  }

  function repaintUses() {
    if (!modalOpen || modalTab !== "uses" || !ui.tabPane) { return; }
    ui.tabPane.textContent = "";
    renderUses();
  }

  function priceOf(row, mode) {
    switch (mode) {
      case "avg24h": return row.quote.avg24h;
      case "avg7d": return row.quote.avg7d;
      case "slot": return row.perSlot;
      case "kg": return row.perKg;
      default: return row.quote.lastLow;
    }
  }

  function matchType(row) {
    if (!st.types.length) { return true; }
    for (var i = 0; i < st.types.length; i++) {
      var f = null;
      for (var j = 0; j < TYPE_FILTERS.length; j++) {
        if (TYPE_FILTERS[j].key === st.types[i]) { f = TYPE_FILTERS[j]; break; }
      }
      if (!f) { continue; }
      for (var k = 0; k < f.types.length; k++) {
        if (row.types[f.types[k]]) { return true; }
      }
    }
    return false;
  }

  function compare(a, b) {
    var key = st.sortKey;
    var dir = st.sortDir;
    if (key === "name") {
      return dir * String(a.name).localeCompare(String(b.name), "zh-CN");
    }
    var av;
    var bv;
    if (key === "price") { av = priceOf(a, st.priceMode); bv = priceOf(b, st.priceMode); }
    else if (key === "offers") { av = a.quote.offers; bv = b.quote.offers; }
    else if (key === "lv") { av = a.lv; bv = b.lv; }
    else if (key === "buy") { av = a.buy ? a.buy.price : null; bv = b.buy ? b.buy.price : null; }
    else if (key === "sell") { av = a.sell; bv = b.sell; }
    else { av = a.profit; bv = b.profit; }
    if (av === null && bv === null) { return 0; }
    if (av === null) { return 1; }        // 缺值永远排最后，不受方向影响
    if (bv === null) { return -1; }
    return dir * (av - bv);
  }

  function applyFilters() {
    if (!loaded || !ui.table) { return; }
    if (gateModeMismatch()) { return; }
    closeModal();
    var q = normalizeQuery(st.query);
    filtered = rows.filter(function (row) {
      if (row.lv !== null && row.lv > st.lv) { return false; }
      if (!matchType(row)) { return false; }
      if (!q) { return true; }
      return (row.name + " " + row.short + " " + row.id).toLowerCase().indexOf(q) >= 0;
    });
    filtered.sort(compare);
    shown = 0;
    ui.tbody.textContent = "";
    ui.table.hidden = false;
    ui.empty.hidden = true;
    ui.empty.classList.remove("is-loading");
    ui.host.scrollTop = 0;
    appendChunk();
    updateToolbar();
    if (!filtered.length) { showSearchEmpty(); }
  }

  // -------------------------------------------------- 历史 72h 缩略曲线（R290）
  // 数据源：本机 BFF 的 /api/cloud/prices/series → 云端 /v1/prices/series（会员）。
  // 只有服务端真的返回采样点才画；1 个点画不成线，如实显示「1 点」。
  var HIST_DAYS = 3;
  var histCache = {};       // key = mode + "|" + itemId → points（数组，空数组=确认无数据）
  var histPending = {};
  var histToken = 0;        // 表格重绘 / 切模式后让在途请求失效

  function histKey(mode, id) { return String(mode) + "|" + String(id); }

  function histBadge(td, text, tip) {
    td.textContent = "";
    var badge = document.createElement("span");
    badge.className = "mk-hist-badge";
    badge.textContent = text;
    td.appendChild(badge);
    td.title = tip || "";
  }

  function drawHistSpark(td, mode, id) {
    var key = histKey(mode, id);
    var points = histCache[key];
    if (!points || !points.length) {
      histBadge(td, "—", "该物资在历史 72h 窗口内没有采样点；不插值、不画假线");
      return;
    }
    if (points.length < 2) {
      histBadge(td, "1 点", "只有 1 个采样点，画不出曲线；时间：" + points[0][0]);
      return;
    }
    var vals = [];
    for (var i = 0; i < points.length; i++) {
      var v = points[i] && points[i][1];
      if (typeof v === "number" && isFinite(v) && v > 0) { vals.push(v); }
    }
    if (vals.length < 2) { histBadge(td, "—", "采样点里没有可用价格"); return; }
    var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
    if (hi === lo) { hi = lo * 1.01 + 1; lo = Math.max(0, lo * 0.99 - 1); }
    var W = 68, H = 22, pad = 2;
    var canvas = document.createElement("canvas");
    canvas.className = "mk-spark";
    canvas.width = W; canvas.height = H;
    canvas.setAttribute("role", "img");
    var g = canvas.getContext && canvas.getContext("2d");
    if (!g) { histBadge(td, points.length + " 点", "浏览器不支持 canvas"); return; }
    var rising = vals[vals.length - 1] >= vals[0];
    g.strokeStyle = rising ? "#a11b1b" : "#0b6b3a";   // A 股口径：涨红跌绿
    g.lineWidth = 1.4;
    g.beginPath();
    var drawn = 0;
    for (var j = 0; j < points.length; j++) {
      var p = points[j];
      if (!p || typeof p[1] !== "number" || !isFinite(p[1]) || p[1] <= 0) { continue; }
      var x = pad + (drawn === 0 ? 0 : drawn * (W - pad * 2) / (vals.length - 1));
      var y = H - pad - (p[1] - lo) / (hi - lo) * (H - pad * 2);
      if (drawn === 0) { g.moveTo(x, y); } else { g.lineTo(x, y); }
      drawn++;
    }
    g.stroke();
    td.textContent = "";
    td.appendChild(canvas);
    td.title = "历史 72h 价格缩略图：云端采样 " + points.length + " 点\n" +
               "起：" + points[0][0] + "  " + fmt(points[0][1]) + " ₽\n" +
               "末：" + points[points.length - 1][0] + "  " +
               fmt(points[points.length - 1][1]) + " ₽\n采样不足不补点";
  }

  function loadHistSparks() {
    if (!ui || !ui.tbody || !st || typeof st.scopeMode !== "function") { return; }
    var mode = st.scopeMode();
    var cells = ui.tbody.querySelectorAll("td.mk-col-hist[data-id]");
    var need = [], seen = {};
    var i, id, key;
    for (i = 0; i < cells.length; i++) {
      id = cells[i].getAttribute("data-id") || "";
      if (!id || seen[id]) { continue; }
      seen[id] = true;
      key = histKey(mode, id);
      if (histCache[key] !== undefined) { drawHistSpark(cells[i], mode, id); continue; }
      if (!histPending[key]) { need.push(id); }
    }
    if (!need.length) { return; }
    var token = ++histToken;
    for (var start = 0; start < need.length; start += 12) {
      (function (batch) {
        batch.forEach(function (bid) { histPending[histKey(mode, bid)] = true; });
        var url = "api/cloud/prices/series?mode=" + encodeURIComponent(mode) +
                  "&days=" + HIST_DAYS + "&itemIds=" + encodeURIComponent(batch.join(","));
        fetch(url, { cache: "no-store" })
          .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, status: r.status, d: d }; }); })
          .then(function (res) {
            if (token !== histToken) { return; }   // 表格已重绘，别把旧数据画上去
            if (!res.ok) {
              var blocked = res.status === 401 || res.status === 403;
              batch.forEach(function (bid) {
                histCache[histKey(mode, bid)] = [];
                var cell = ui.tbody.querySelector('td.mk-col-hist[data-id="' + bid + '"]');
                if (cell) {
                  histBadge(cell, blocked ? "会员功能" : "—",
                            blocked ? "历史曲线是会员功能（服务端鉴权）" : "历史曲线读取失败");
                }
              });
              return;
            }
            var pts = (res.d && res.d.points) || {};
            batch.forEach(function (bid) {
              var list = pts[bid] || [];
              histCache[histKey(mode, bid)] = list;
              var cell = ui.tbody.querySelector('td.mk-col-hist[data-id="' + bid + '"]');
              if (cell) { drawHistSpark(cell, mode, bid); }
            });
          })
          .catch(function () {
            if (token !== histToken) { return; }
            batch.forEach(function (bid) {
              histCache[histKey(mode, bid)] = [];
              var cell = ui.tbody.querySelector('td.mk-col-hist[data-id="' + bid + '"]');
              if (cell) { histBadge(cell, "—", "历史曲线读取失败"); }
            });
          })
          .then(function () {
            batch.forEach(function (bid) { delete histPending[histKey(mode, bid)]; });
          });
      })(need.slice(start, start + 12));
    }
  }

  function appendChunk() {
    var end = Math.min(shown + CHUNK, filtered.length);
    var frag = document.createDocumentFragment();
    for (var i = shown; i < end; i++) { frag.appendChild(renderRow(filtered[i])); }
    ui.tbody.appendChild(frag);
    shown = end;
    updateFooter();
    // 历史曲线是异步补绘：先出表，再按每批 12 个物品取真实采样点，不阻塞首屏。
    loadHistSparks();
  }

  // ---------------------------------------------------------------- 行渲染
  function cell(td, text, cls) {
    td.textContent = text;
    if (cls) { td.className = cls; }
    return td;
  }

  function renderRow(row) {
    var tr = document.createElement("tr");
    tr.className = "mk-row" + (selectedIds[row.id] ? " is-selected" : "");
    tr.setAttribute("data-id", row.id);
    tr.title = row.name + "（" + row.id + "）";

    var td = document.createElement("td");
    td.className = "mk-col-check";
    var cb = document.createElement("input");
    cb.type = "checkbox";
    cb.className = "mk-check";
    cb.setAttribute("aria-label", "选择 " + row.name);
    cb.checked = !!selectedIds[row.id];
    td.appendChild(cb);
    tr.appendChild(td);

    td = document.createElement("td");
    td.className = "mk-col-item";
    var img = document.createElement("img");
    img.className = "mk-icon";
    img.width = 32;
    img.height = 32;
    img.alt = "";
    if (api.icon) { api.icon(img, row.id); } else { img.src = "assets/icons-transparent/" + row.id + ".png"; }
    td.appendChild(img);
    var box = document.createElement("span");
    box.className = "mk-item-text";
    var name = document.createElement("span");
    name.className = "mk-name";
    name.textContent = row.name;
    box.appendChild(name);

    // 第二行：短名 · 来源标记 · 逐物品更新时间（db4 是两行小字，我们用一行紧凑版）
    var sub = document.createElement("span");
    sub.className = "mk-sub";
    if (row.short && row.short !== row.name) {
      var shortEl = document.createElement("span");
      shortEl.className = "mk-sub-short";
      shortEl.textContent = row.short;
      sub.appendChild(shortEl);
    }
    var upd = row.quote.updated || row.quote.rowFetchedAt;
    var ageEl = document.createElement("span");
    ageEl.className = "mk-age";
    ageEl.textContent = upd ? shortAge(upd) : "更新时间未知";
    if (upd) { ageEl.title = "数据时间：" + upd; }
    sub.appendChild(ageEl);
    var srcEl = document.createElement("span");
    srcEl.className = "mk-src";
    var snap = snapshotPayload();
    srcEl.textContent = sourceLabel(snap);
    srcEl.title = "逐行来源：" + sourceLabel(snap) + "（" + modeLabel(st.scopeMode()) + "）" +
      (snap && snap.snapshotAt ? "\n数据时间：" + snap.snapshotAt : "") +
      (snap && snap.live === true ? "\n会员云端最新数据" :
        (snap && snap.cached ? "\n云端缓存（非实时）" : "\n免费云端数据（延迟 12 小时）")) +
      (upd ? "\n该物品数据时间：" + upd : "\n该行没有逐物品更新时间");
    sub.appendChild(srcEl);
    box.appendChild(sub);
    td.appendChild(box);
    tr.appendChild(td);

    tr.appendChild(cell(document.createElement("td"), row.lv === null ? "—" : String(row.lv), "mk-col-lv"));

    td = document.createElement("td");
    var pv = priceOf(row, st.priceMode);
    if (pv === null) {
      td.className = "mk-col-price is-muted";
      td.textContent = st.priceMode === "avg7d" ? "积累中" : "—";
      td.title = st.priceMode === "avg7d" ? "云端缓存里没有该物品近 7 天采样；不估算、不插值" : "该口径缺数据";
    } else {
      td.className = "mk-col-price";
      td.textContent = fmt(pv) + " ₽";
    }
    tr.appendChild(td);

    // 在售挂单数：上游 lastOfferCount 原值；0 显示 0，缺测显示「—」。
    td = document.createElement("td");
    td.className = "mk-col-offers" + (row.quote.offers === null ? " is-muted" : "");
    td.textContent = row.quote.offers === null ? "—" : fmt(row.quote.offers);
    td.title = "在售挂单数（lastOfferCount），不是成交笔数；缺测不补 0";
    tr.appendChild(td);

    td = document.createElement("td");
    td.className = "mk-col-hist";
    td.setAttribute("data-id", row.id);
    var badge = document.createElement("span");
    badge.className = "mk-hist-badge";
    badge.textContent = "读取中…";   // 异步补绘前的占位；失败会替换成「会员功能」或「—」
    td.appendChild(badge);
    td.title = "正在读取历史 72h 真实采样点；不足 2 点不画曲线";
    tr.appendChild(td);

    td = document.createElement("td");
    td.className = "mk-col-buy" + (row.buy ? "" : " is-muted");
    if (row.buy) {
      // 商人图标：仓库内自绘 SVG（不是对照站的素材，也不是上游头像）
      var tIcon = traderIcon(row.buy.trader, 16, "mk-trader");
      tIcon.title = traderNameOf(row.buy.trader) + " · 忠诚 l" +
        (row.buy.lv === null ? "—" : row.buy.lv) + " · " + fmt(row.buy.price) + " ₽";
      td.appendChild(tIcon);
      var buyVal = document.createElement("span");
      buyVal.textContent = fmt(row.buy.price) + " ₽";
      td.appendChild(buyVal);
      td.title = traderNameOf(row.buy.trader) + " 的最低买价（忠诚 l" +
        (row.buy.lv === null ? "—" : row.buy.lv) + "）；取上游 priceRUB（已换算卢布" +
        (row.buy.c !== "RUB" ? "，原报价 " + row.buy.c : "") + "），是商人卖给玩家的价格";
    } else {
      td.textContent = "—";
      td.title = "无商人买价数据";
    }
    tr.appendChild(td);

    td = document.createElement("td");
    td.className = "mk-col-sell" + (row.sell === null ? " is-muted" : "");
    td.textContent = row.sell === null ? "—" : (fmt(row.sell) + " ₽");
    td.title = "跳蚤最新最低挂单（lastLowPrice）；不是商人收购价";
    tr.appendChild(td);

    td = document.createElement("td");
    td.className = "mk-col-profit" + (row.profit === null ? " is-muted" : (row.profit >= 0 ? " is-pos" : " is-neg"));
    td.textContent = row.profit === null ? "—" : ((row.profit >= 0 ? "+" : "") + fmt(row.profit));
    td.title = "卖价 − 买价（未扣跳蚤手续费；上游没有手续费/成交价，故不称净利润）";
    tr.appendChild(td);

    return tr;
  }

  // ---------------------------------------------------------------- 工具栏 / 状态
  function updateToolbar() {
    if (ui.lvOut) { ui.lvOut.textContent = "≤ " + st.lv; }
    if (ui.modeBtns) {
      ui.modeBtns.forEach(function (b) {
        b.setAttribute("aria-selected", String(b.getAttribute("data-mode") === st.priceMode));
      });
    }
    if (ui.priceSub) {
      for (var i = 0; i < PRICE_MODES.length; i++) {
        if (PRICE_MODES[i].key === st.priceMode) {
          ui.priceSub.textContent = PRICE_MODES[i].label + " · " + PRICE_MODES[i].en;
          break;
        }
      }
    }
    if (ui.typeBtns) {
      ui.typeBtns.forEach(function (b) {
        var on = st.types.indexOf(b.getAttribute("data-type")) >= 0;
        b.setAttribute("aria-pressed", String(on));
        b.classList.toggle("is-on", on);
      });
    }
    if (ui.typeClear) { ui.typeClear.hidden = !st.types.length; }
    if (ui.count) {
      ui.count.textContent = loaded
        ? ("筛选结果 " + filtered.length + " 条 / 有行情 " + rows.length + " 条")
        : "正在读取本地行情…";
    }
    updateSortHeads();
    updateCutoff();
  }

  function updateFooter() {
    if (!ui.footCount) { return; }
    ui.footCount.textContent = filtered.length
      ? ("已显示 " + shown + " / " + filtered.length + " 条")
      : "0 条";
    updateSelectionUI();
  }

  /** 选中数 / 全选态 / 底部操作按钮（不重渲染表格，避免滚动位置跳动）。 */
  function updateSelectionUI() {
    if (!ui.checkAll) { return; }
    var n = Object.keys(selectedIds).length;
    var filteredAll = filtered.length > 0 && filtered.every(function (row) { return !!selectedIds[row.id]; });
    ui.checkAll.checked = filteredAll;
    ui.checkAll.indeterminate = n > 0 && !filteredAll;
    ui.checkAll.title = filteredAll ? "取消全选当前筛选结果" : "全选当前筛选结果（不只是已渲染的 " + shown + " 行）";
    if (ui.footSel) {
      ui.footSel.hidden = !n;
      ui.footSel.textContent = "已选 " + n + " 件";
      ui.footSel.title = "按物品 id 记录，跨筛选保留；复制只影响已选中的物品";
    }
    if (ui.copySel) { ui.copySel.hidden = !n; ui.copySel.disabled = !n; }
    if (ui.selClear) { ui.selClear.hidden = !n; }
  }

  function updateSortHeads() {
    if (!ui.thead) { return; }
    var ths = ui.thead.querySelectorAll("th[data-sort]");
    for (var i = 0; i < ths.length; i++) {
      var key = ths[i].getAttribute("data-sort");
      ths[i].setAttribute("aria-sort", key === st.sortKey ? (st.sortDir === 1 ? "ascending" : "descending") : "none");
      var mark = ths[i].querySelector(".mk-sort-mark");
      if (mark) {
        mark.textContent = key === st.sortKey ? (st.sortDir === 1 ? " ▲" : " ▼") : "";
      }
    }
  }

  var SNAPSHOT_ERRORS = {
    "login_required": "尚未登录账号；行情只能从云端获取，请先登录",
    "unauthorized": "登录已失效，请重新登录",
    "quota_exhausted": "今日行情额度已用完，明天 00:00（北京时间）重置",
    "offline": "云端暂时连不上",
    "network": "云端暂时连不上",
    "no_price_data": "云端还没有该模式的行情数据",
    "data_delayed": "免费版行情延迟 12 小时，云端还没有到可见时间的数据",
    "fetch-failed": "本机服务没有响应",
    "bad-mode": "模式参数不被接受"
  };

  function snapshotErrorText(payload) {
    var code = (payload && payload.error) || "offline";
    var message = (payload && payload.message) || "";
    return SNAPSHOT_ERRORS[code] || message || ("读取失败（" + code + "）");
  }

  /** 数据截止时间的人话形式（同日只显示时分，跨日补月-日）。 */
  function cutoffTimeText(snap) {
    var d = parseTime(snap && snap.snapshotAt);
    if (!d) { return ""; }
    var today = new Date();
    var sameDay = d.getFullYear() === today.getFullYear() && d.getMonth() === today.getMonth() && d.getDate() === today.getDate();
    return (sameDay ? "" : (pad2(d.getMonth() + 1) + "-" + pad2(d.getDate()) + " ")) + clockText(d);
  }

  // R268：云端采集机每小时 **:01 / :31** 各采集上传一次，所以不再用「固定 20 分钟」
  // 拦人——点「获取最新数据」时先看已缓存的 snapshotAt 是否已覆盖最近采集时刻：
  //   · 缓存已到最近采集时刻 → 云端不可能有更新的数据，直接提示「已是最新」，不发请求；
  //   · 缓存落后 → 才真的去拉（服务端还会做同样的判定兜底）。
  var COLLECT_MINUTES = [1, 31];
  var manualFetchBusy = false;

  /** 最近一个**已到达**的采集时刻（本地时间 :01 / :31）。 */
  function latestCollectSlot(now) {
    now = now || new Date();
    for (var i = COLLECT_MINUTES.length - 1; i >= 0; i--) {
      var m = COLLECT_MINUTES[i];
      if (now.getMinutes() >= m) {
        var same = new Date(now.getTime());
        same.setMinutes(m, 0, 0);
        return same;
      }
    }
    var prev = new Date(now.getTime() - 3600000);
    prev.setMinutes(COLLECT_MINUTES[COLLECT_MINUTES.length - 1], 0, 0);
    return prev;
  }

  /** 下一个采集时刻（本地时间 :01 / :31）。 */
  function nextCollectSlot(now) {
    now = now || new Date();
    for (var i = 0; i < COLLECT_MINUTES.length; i++) {
      var m = COLLECT_MINUTES[i];
      if (now.getMinutes() < m) {
        var same = new Date(now.getTime());
        same.setMinutes(m, 0, 0);
        return same;
      }
    }
    var next = new Date(now.getTime() + 3600000);
    next.setMinutes(COLLECT_MINUTES[0], 0, 0);
    return next;
  }

  /** 「下次云端采集 22:01」；服务端给了 nextCollectAt 就用服务端的。 */
  function nextCollectText(payload) {
    var d = parseTime(payload && payload.nextCollectAt) || nextCollectSlot(new Date());
    return clockText(d);
  }

  function setFetchBusy(on) {
    if (!ui.cutoffFetch) { return; }
    ui.cutoffFetch.classList.toggle("is-busy", !!on);
    ui.cutoffFetch.textContent = on ? "获取中…" : "获取最新数据";
  }

  function manualFetch() {
    if (manualFetchBusy) { return; }
    if (!api || !api.ensureSnapshot) {
      showFetchWarn("行情接口还没就绪，请稍后再试");
      return;
    }
    var snap = snapshotPayload();
    if (snap && snap.loginRequired) {
      showFetchWarn("请先登录账号，再获取云端行情");
      return;
    }
    manualFetchBusy = true;
    setFetchBusy(true);
    var done = function () {
      manualFetchBusy = false;
      setFetchBusy(false);
      refreshMeta();
    };
    api.ensureSnapshot({ reason: "manual", force: true }).then(function (payload) {
      done();
      var quota = (payload && payload.quota) || {};
      if (!payload || payload.ok === false) {
        if (payload && payload.error === "quota_exhausted") {
          var reset = parseTime(quota.reset_at);
          showFetchWarn("今日 24 次行情额度已用完" + (reset ? "，明天 " + clockText(reset) + " 重置" : ""));
        } else if (payload && payload.loginRequired) {
          showFetchWarn("登录已失效，请重新登录后再获取行情");
        } else {
          showFetchWarn(snapshotErrorText(payload));
        }
        reload();
        return;
      }
      var next = parseTime(quota.next_allowed_at);
      if (payload.status === "cd") {
        showFetchInfo("冷却中，返回上次云端数据（截止 "
          + (cutoffTimeText(payload) || "—") + "）"
          + (next ? "；下次可获取 " + clockText(next) : ""));
      } else if (payload.cached) {
        if (payload.cacheReason === "quota_exhausted") {
          var resetAt = parseTime(quota.reset_at);
          showFetchWarn("今日 24 次行情额度已用完"
            + (resetAt ? "，明天 " + clockText(resetAt) + " 重置" : "")
            + "；当前显示上次成功获取的云端数据（截止 "
            + (cutoffTimeText(payload) || "—") + "）");
        } else {
          showFetchWarn("云端暂时取不到新数据，仍显示上次成功获取的云端行情（截止 "
            + (cutoffTimeText(payload) || "—") + "）");
        }
      } else if (quota.remaining_today !== null && quota.remaining_today !== undefined) {
        showFetchInfo("已更新（截止 " + (cutoffTimeText(payload) || "—") + "）· 今日剩余 "
          + quota.remaining_today + " 次");
      } else {
        hideFetchWarn();
      }
      reload();
    }).catch(function () {
      done();
      showFetchWarn("获取失败，请稍后再试");
    });
  }

  function showFetchWarn(text, kind) {
    if (!ui.cutoffWarn) { return; }
    var info = kind === "info";
    ui.cutoffWarn.classList.toggle("is-info", info);
    ui.cutoffWarn.textContent = text;
    ui.cutoffWarn.hidden = false;
    clearTimeout(showFetchWarn._t);
    showFetchWarn._t = setTimeout(hideFetchWarn, info ? 6000 : 5000);
  }

  /** 中性提示（不是错误）：例如「已是最新行情」。 */
  function showFetchInfo(text) { showFetchWarn(text, "info"); }

  function hideFetchWarn() {
    if (ui.cutoffWarn) { ui.cutoffWarn.hidden = true; }
  }

  function updateCutoff() {
    if (!ui.cutoff) { return; }
    var snap = snapshotPayload();
    var quota = (snap && snap.quota) || {};
    var stale = false;
    var text;
    if (!snap || !snap.available) {
      var phase = api.snapshotPhase ? api.snapshotPhase() : null;
      if (snap && snap.loginRequired) {
        text = "数据截止 —（登录后从云端获取）";
      } else {
        text = phase === "loading" ? "数据截止 —（正在读取当前模式行情…）" : "数据截止 —（当前模式暂无可用的行情数据）";
      }
      stale = true;
    } else {
      var when = cutoffTimeText(snap);
      if (!when) {
        text = "数据截止 —（行情缺少时间戳）";
        stale = true;
      } else {
        text = "数据截止 " + when + "（" + shortAge(snap.snapshotAt) + "）";
        if (snap.cached) {
          text += " · 缓存（非实时）";
        } else if (snap.dataDelayed) {
          text += " · 免费延迟 12 小时";
        } else {
          text += " · 近实时";
        }
        if (typeof quota.remaining_today === "number") {
          text += " · 今日剩余 " + quota.remaining_today + " 次";
        }
        stale = liveStale(snap) && !(snap.dataDelayed && !snap.cached);
        if (stale) { text += " · 已过期 " + agePhrase(liveAgeSec(snap)); }
      }
    }
    ui.cutoff.textContent = text;
    ui.cutoff.classList.toggle("is-stale", stale);

    if (ui.cutoffFetch) {
      ui.cutoffFetch.classList.remove("is-fresh");
      var freeTier = snap && snap.tier && snap.tier !== "member";
      var remaining = typeof quota.remaining_today === "number"
        ? "，今日剩余 " + quota.remaining_today + " 次" : "";
      ui.cutoffFetch.title = freeTier
        ? "获取最新数据（免费：每日 24 次，CD 59:59，数据延迟 12 小时" + remaining + "）"
        : "获取最新数据（会员：CD 30 秒，不限次数）";
    }

    var lines = [
      "会员：云端最新快照 · CD 30 秒，每日不限次数",
      "免费：云端快照延迟 12 小时 · 每日 24 次 · CD 59:59",
      "额度与 CD 均记录在云端账号上；断网时显示本机上次成功结果"
    ];
    if (!snap || !snap.available) {
      lines.push("当前模式暂无可用行情");
    } else if (snap.cached) {
      lines.push("当前：云端暂不可用，显示本机上次成功获取的缓存");
    } else if (snap.dataDelayed) {
      lines.push("当前：免费版数据（比会员延迟 12 小时）");
    }
    ui.cutoff.title = lines.join("\n");

    // 过期 / 延迟 / 缓存不能只在颜色上表达：给一条不依赖悬停的文字横幅。
    if (ui.stale) {
      var show = stale || (snap && snap.available && (sourceNonLive(snap) || snap.cached || snap.dataDelayed));
      ui.stale.hidden = !show;
      if (show) {
        if (!snap || !snap.available) {
          awaitSnapshotBanner();
        } else {
          var whenText = cutoffTimeText(snap) || "未知";
          var age = liveAgeSec(snap);
          if (snap.cached) {
            if (snap.cacheReason === "quota_exhausted") {
              ui.stale.textContent = "今日 24 次行情额度已用完（北京时间 00:00 重置），当前显示上次成功获取的云端数据（截止 "
                + whenText + "），不是实时行情。";
            } else {
              ui.stale.textContent = "云端暂时取不到新数据，当前显示上次成功获取的云端行情（截止 "
                + whenText + "），不是实时行情。恢复联网后点「获取最新数据」即可更新。";
            }
          } else if (snap.dataDelayed) {
            ui.stale.textContent = "免费版行情比会员延迟 12 小时（数据截止 " + whenText
              + "）。每日可获取 " + (quota.daily_limit || 24) + " 次，每次成功后 CD 59 分 59 秒。";
          } else if (stale) {
            ui.stale.textContent = "云端行情已过期" +
              (age !== null ? " " + agePhrase(age) : "") +
              "；采集机可能尚未完成本轮上传，下面是最近一次可用的数据。";
          }
        }
      }
    }
  }

  function awaitSnapshotBanner() {
    var phase = api.snapshotPhase ? api.snapshotPhase() : null;
    var cur = st.scopeMode();
    var payload = snapshotPayload();
    if (payload && payload.loginRequired) {
      // 登录引导只在空态里显示一次，这里不再重复同一句话
      if (ui.stale) { ui.stale.hidden = true; ui.stale.textContent = ""; }
      return;
    }
    if (ui.stale) { ui.stale.hidden = false; }
    ui.stale.textContent = phase === "loading"
      ? "正在从云端读取 " + modeLabel(cur) + " 的行情…"
      : "当前模式（" + modeLabel(cur) + "）暂无可用的行情数据：" +
        snapshotErrorText(payload) + "。不会用其他模式的价格顶替。";
  }

  // ---------------------------------------------------------------- 空态 / 模式门
  /** 装载中空态：行情来自云端，不显示任何假行。 */
  function showLoading(title, detail) {
    if (!ui.empty) { return; }
    ui.table.hidden = true;
    ui.empty.hidden = false;
    ui.empty.classList.remove("is-error");
    ui.empty.classList.add("is-loading");
    ui.emptyTitle.textContent = title || "正在从云端读取当前模式行情…";
    ui.emptyDetail.textContent = detail || "免费版数据比会员延迟 12 小时；登录后才会请求云端。";
    ui.emptyBtn.textContent = "";
    ui.emptyBtn.hidden = true;
    ui.emptyBtn.onclick = null;
  }

  // kind === "error" 时加上 is-error（红边 + 淡红底），与普通空态区分；不传则保持原样。
  function showEmpty(title, detail, actionLabel, actionFn, kind) {
    ui.empty.classList.remove("is-loading");
    ui.empty.classList.toggle("is-error", kind === "error");
    ui.table.hidden = true;
    ui.empty.hidden = false;
    ui.emptyTitle.textContent = title;
    ui.emptyDetail.textContent = detail;
    ui.emptyBtn.textContent = actionLabel;
    ui.emptyBtn.onclick = actionFn;
    ui.emptyBtn.hidden = !actionLabel;
  }

  function resetFilters() {
    st.query = "";
    st.lv = LV_MAX;
    st.types = [];
    st.priceMode = "last";
    st.sortKey = SORT_DEFAULT.key;
    st.sortDir = SORT_DEFAULT.dir;
    if (ui.search) { ui.search.value = ""; }
    if (ui.lvRange) { ui.lvRange.value = String(LV_MAX); }
    savePrefs();
    applyFilters();
  }

  function typeLabels() {
    return st.types.map(function (k) {
      var f = TYPE_FILTERS.filter(function (x) { return x.key === k; })[0];
      return f ? f.label : k;
    }).join(" / ");
  }

  function showSearchEmpty() {
    // 先看「搜索/类型都命中、只是被 Lv 上限挡住」的行：直接把原因说出来，
    // 否则用户会以为物品不存在（db4 这里是一片纯黑，我们的差异点就是明确空态）。
    var q = normalizeQuery(st.query);
    var fellByLv = 0;
    if (q && st.lv < LV_MAX) {
      rows.forEach(function (row) {
        if (row.lv === null || row.lv <= st.lv) { return; }
        if (!matchType(row)) { return; }
        if ((row.name + " " + row.short + " " + row.id).toLowerCase().indexOf(q) >= 0) { fellByLv++; }
      });
    }
    if (fellByLv > 0) {
      showEmpty("没有匹配的物品",
        "有 " + fellByLv + " 条命中搜索，但跳蚤上架等级高于当前 Lv 上限 " + st.lv + "，被过滤掉了。",
        "把 Lv 上限放宽到 " + LV_MAX, function () {
          st.lv = LV_MAX;
          if (ui.lvRange) { ui.lvRange.value = String(LV_MAX); }
          savePrefs();
          applyFilters();
        });
      return;
    }
    if (!q && st.types.length) {
      showEmpty("该类型下没有可用行情",
        "类型筛选「" + typeLabels() + "」在当前模式行情里没有可显示的行（不是没有该物品，而是这批物品没有行情数据）。",
        "清除类型筛选", function () {
          st.types = [];
          savePrefs();
          applyFilters();
        });
      return;
    }
    if (q && st.types.length) {
      showEmpty("没有匹配的物品",
        "搜索「" + st.query.trim() + "」与类型筛选「" + typeLabels() + "」同时生效，结果是 0 条；可能命中的物品被类型筛选挡住了。",
        "清空搜索与类型", function () {
          st.query = "";
          st.types = [];
          if (ui.search) { ui.search.value = ""; }
          savePrefs();
          applyFilters();
        });
      return;
    }
    showEmpty("没有匹配的物品",
      "当前搜索 / Lv / 类型的组合结果是 0 条。可以清空条件后重新筛选。",
      "清空搜索与筛选", resetFilters);
  }

  function snapMode() {
    var snap = snapshotPayload();
    return (snap && snap.mode) || null;
  }

  function modeLabel(key) {
    var info = (window.GWGameMode && window.GWGameMode.info) ? window.GWGameMode.info(key) : null;
    return info ? info.label : (key || "?");
  }

  /**
   * 当前模式没有可用行情 → 明确空态。
   * 绝不用其他模式（尤其 PvP）的价格顶替，也不把「切到别的模式」甩给用户：
   * 未登录只显示登录引导；登录后云端不可用时如实说明，不再回退离线快照。
   */
  function gateModeMismatch() {
    if (!loaded) { return false; }
    var payload = snapshotPayload();
    if (payload && payload.available) {
      st.modeMismatch = false;
      if (ui.banner) { ui.banner.hidden = true; }
      return false;
    }
    st.modeMismatch = true;
    var cur = st.scopeMode();
    var phase = api.snapshotPhase ? api.snapshotPhase() : null;
    if (phase === "loading") {
      if (ui.banner) { ui.banner.hidden = true; }
      updateCutoff();   // 旧模式的截止时间不能留在当前模式上
      showLoading("正在从云端读取 " + modeLabel(cur) + " 的行情…",
        "免费版数据比会员延迟 12 小时；登录后才会请求云端。");
      if (ui.count) { ui.count.textContent = "正在读取 " + modeLabel(cur) + " 行情…"; }
      return true;
    }
    if (payload && payload.loginRequired) {
      // 只保留空态里这一句，不再同时压一条 banner
      if (ui.banner) { ui.banner.hidden = true; ui.banner.textContent = ""; }
      if (ui.stale) { ui.stale.hidden = true; ui.stale.textContent = ""; }
      showEmpty("市场行情来自云端，需登录账号获取", "", "重试", function () { reload(); });
      if (ui.count) { ui.count.textContent = "请先登录账号"; }
      updateCutoff();
      return true;
    }
    if (ui.banner) {
      ui.banner.hidden = false;
      ui.banner.textContent = "当前模式 " + modeLabel(cur) + " 没有可用的行情数据；" +
        "页面不会拿其他模式的价格冒充。";
    }
    showEmpty("当前模式暂无可用的行情数据",
      modeLabel(cur) + " 的行情不可用：" + snapshotErrorText(payload) + "。" +
      "可用时页面只展示云端返回的真实数据，不会用其他模式的价格顶替当前模式。",
      "重试", function () { reload(); });
    if (ui.count) { ui.count.textContent = "暂无 " + modeLabel(cur) + " 行情：0 条（不跨模式冒充）"; }
    updateCutoff();   // 旧模式的截止时间 / 过期提示一并清掉
    return true;
  }

  // ---------------------------------------------------------------- 数据装载
  function reload() {
    if (!api) { return; }
    loading = true;
    var cur = modeLabel(st.scopeMode());
    if (ui.count) { ui.count.textContent = "正在读取 " + cur + " 行情…"; }
    if (!rows.length) { showLoading("正在从云端读取当前模式行情…", "免费版数据比会员延迟 12 小时。"); }
    var done = function () {
      loading = false;
      loaded = true;
      buildRows();
      applyFilters();
    };
    var p = api.ensureSnapshot ? api.ensureSnapshot({ reason: "reload" })
      : Promise.resolve(api.snapshot ? api.snapshot() : null);
    Promise.resolve(p).then(done).catch(function (err) {
      loading = false;
      showEmpty("读取行情失败", String((err && err.message) || err), "重试", reload, "error");
    });
  }

  function load() {
    if (!api || loading || loaded) { return; }
    loading = true;
    if (ui.count) { ui.count.textContent = "正在读取当前模式行情…"; }
    if (!rows.length) { showLoading("正在从云端读取当前模式行情…", "免费版数据比会员延迟 12 小时。"); }
    var snapshotReady = api.ensureSnapshot ? api.ensureSnapshot({ reason: "load" })
      : Promise.resolve(api.snapshot ? api.snapshot() : null);
    Promise.resolve(snapshotReady).then(function () {
      api.ensure().then(function () {
        var snap = snapshotPayload();
        if (!snap || !snap.available) {
          // 物品表已就绪但当前模式没有可用行情：交给 gateModeMismatch 显示明确空态。
          loading = false;
          loaded = true;
          buildRows();
          applyFilters();
          return;
        }
        loading = false;
        loaded = true;
        buildRows();
        applyFilters();
      }).catch(function (err) {
        loading = false;
        loaded = true;
        showEmpty("物品数据读取失败", String((err && err.message) || err), "重试", load, "error");
      });
    }).catch(function (err) {
      loading = false;
      loaded = true;
      showEmpty("读取行情失败", String((err && err.message) || err), "重试", load, "error");
    });
  }

  // ---------------------------------------------------------------- 骨架
  function buildSkeleton() {
    var html = [];
    html.push('<div class="mk-app">');
    html.push('  <div class="mk-toolbar">');
    html.push('    <div class="mk-tb-main">');
    html.push('      <label class="mk-search"><span class="mk-search-ico" aria-hidden="true">⌕</span>');
    html.push('        <input type="search" class="mk-search-input" placeholder="搜索物品（中文 / 短名 / id）" aria-label="搜索物品">');
    html.push('      </label>');
    html.push('      <div class="mk-lvbox" title="只显示跳蚤上架等级 ≤ 设定值的物品；Lv 来自上游 minLevelForFlea">');
    html.push('        <span class="mk-tb-label">Lv</span>');
    html.push('        <input type="range" class="mk-lv-range" min="0" max="40" step="1" value="40" aria-label="跳蚤上架等级上限">');
    html.push('        <output class="mk-lv-out">≤ 40</output>');
    html.push('      </div>');
    html.push('      <div class="mk-modes" role="tablist" aria-label="价格口径"></div>');
    html.push('      <button type="button" class="mk-btn mk-reset" title="恢复默认筛选（Lv 40、最新价、无类型筛选）">重置</button>');
    html.push('      <button type="button" class="mk-btn mk-ocr-btn" title="截图识别物品与跳蚤价（支持粘贴 / 拖拽 / 框选区域；R234）">截图识别</button>');
    html.push('    </div>');
    html.push('    <div class="mk-tb-sub">');
    html.push('      <span class="mk-tb-label">类型</span>');
    html.push('      <div class="mk-types" role="group" aria-label="物品类型筛选"></div>');
    html.push('      <button type="button" class="mk-link mk-type-clear" hidden>清除类型</button>');
    html.push('      <span class="mk-count" role="status" aria-live="polite"></span>');
    html.push('    </div>');
    html.push('  </div>');
    html.push('  <div class="mk-banner" hidden></div>');
    html.push('  <div class="mk-stale" role="status" hidden></div>');
    html.push('  <div class="mk-tablehost" tabindex="0">');
    html.push('    <table class="mk-table">');
    html.push('      <colgroup>');
    html.push('        <col class="mk-w-check"><col><col class="mk-w-lv"><col class="mk-w-price"><col class="mk-w-offers">');
    html.push('        <col class="mk-w-hist"><col class="mk-w-buy"><col class="mk-w-sell"><col class="mk-w-profit">');
    html.push('      </colgroup>');
    html.push('      <thead><tr>');
    html.push('        <th class="mk-col-check"><input type="checkbox" class="mk-check-all" aria-label="全选当前筛选结果"></th>');
    html.push('        <th class="mk-col-item" data-sort="name" tabindex="0">物品<span class="mk-sort-mark"></span></th>');
    html.push('        <th class="mk-col-lv" data-sort="lv" tabindex="0">Lv<span class="mk-sort-mark"></span></th>');
    html.push('        <th class="mk-col-price" data-sort="price" tabindex="0">价格 <span class="mk-price-sub">最新 · Last</span><span class="mk-sort-mark"></span></th>');
    html.push('        <th class="mk-col-offers" data-sort="offers" tabindex="0">在售<span class="mk-sort-mark"></span></th>');
    html.push('        <th class="mk-col-hist">历史 72h</th>');
    html.push('        <th class="mk-col-buy" data-sort="buy" tabindex="0">买价<span class="mk-sort-mark"></span></th>');
    html.push('        <th class="mk-col-sell" data-sort="sell" tabindex="0">卖价<span class="mk-sort-mark"></span></th>');
    html.push('        <th class="mk-col-profit" data-sort="profit" tabindex="0">价差 / 件<span class="mk-sort-mark"></span></th>');
    html.push('      </tr></thead>');
    html.push('      <tbody class="mk-tbody"></tbody>');
    html.push('    </table>');
    html.push('    <div class="mk-empty" hidden><h3 class="mk-empty-title"></h3><p class="mk-empty-detail"></p><button type="button" class="mk-btn mk-empty-btn" hidden></button></div>');
    html.push('  </div>');
    html.push('  <div class="mk-foot">');
    html.push('    <span class="mk-foot-count">0 条</span>');
    html.push('    <span class="mk-foot-sel" hidden>已选 0 件</span>');
    html.push('    <button type="button" class="mk-btn mk-copy-sel" hidden>复制所选</button>');
    html.push('    <button type="button" class="mk-link mk-sel-clear" hidden>清除选择</button>');
    html.push('    <span class="mk-foot-note">按游戏模式自动跟随 · 云端行情 · 免费延迟 12 小时 / 会员 30 秒 CD · 不做伪实时</span>');
    html.push('  </div>');
    html.push('  <div class="mk-toast" role="status" aria-live="polite" hidden></div>');
    html.push('  <div class="mk-modal" hidden>');
    html.push('    <div class="mk-modal-shade" data-mk-close></div>');
    html.push('    <div class="mk-modal-panel" role="dialog" aria-modal="true" aria-labelledby="mk-modal-name">');
    html.push('      <div class="mk-modal-head">');
    html.push('        <img class="mk-modal-icon" width="48" height="48" alt="">');
    html.push('        <div class="mk-modal-headtext">');
    html.push('          <h3 class="mk-modal-name" id="mk-modal-name"></h3>');
    html.push('          <div class="mk-modal-meta"></div>');
    html.push('        </div>');
    html.push('        <button type="button" class="mk-modal-x" data-mk-close aria-label="关闭详情">✕</button>');
    html.push('      </div>');
    html.push('      <div class="mk-modal-tabs" role="tablist" aria-label="详情分组">');
    html.push('        <button type="button" role="tab" data-tab="obtain" aria-selected="true">Obtain<span>获取</span></button>');
    html.push('        <button type="button" role="tab" data-tab="uses" aria-selected="false">Uses<span>用途</span></button>');
    html.push('        <button type="button" role="tab" data-tab="banned" aria-selected="false">Banned<span>禁售</span></button>');
    html.push('      </div>');
    html.push('      <div class="mk-modal-body">');
    html.push('        <div class="mk-modal-left">');
    html.push('          <div class="mk-priceblock"></div>');
    html.push('          <div class="mk-sellto"></div>');
    html.push('        </div>');
    html.push('        <div class="mk-modal-right">');
    html.push('          <div class="mk-tabpane"></div>');
    html.push('          <div class="mk-hist72"></div>');
    html.push('        </div>');
    html.push('      </div>');
    html.push('    </div>');
    html.push('  </div>');
    // R234 截图识别面板（独立程序打包后同款入口；网页阶段用文件/粘贴喂图）
    html.push('  <div class="mk-ocr" hidden>');
    html.push('    <div class="mk-modal-shade" data-ocr-close></div>');
    html.push('    <div class="mk-modal-panel mk-ocr-panel" role="dialog" aria-modal="true" aria-label="截图识别价格">');
    html.push('      <div class="mk-modal-head">');
    html.push('        <div class="mk-modal-headtext">');
    html.push('          <h3 class="mk-modal-name">截图识别价格</h3>');
    html.push('          <div class="mk-ocr-sub">选图 / 粘贴 → 框选物品名区域（小框识别更准）→ 识别后按当前模式显示跳蚤价</div>');
    html.push('        </div>');
    html.push('        <button type="button" class="mk-modal-x" data-ocr-close aria-label="关闭截图识别">✕</button>');
    html.push('      </div>');
    html.push('      <div class="mk-ocr-body">');
    html.push('        <div class="mk-ocr-left">');
    html.push('          <div class="mk-ocr-drop" tabindex="0" role="button" aria-label="选择或粘贴截图">');
    html.push('            <span class="mk-ocr-drop-ico">⧉</span>');
    html.push('            <span>点击选择截图，或直接 <b>Ctrl+V</b> 粘贴</span>');
    html.push('            <input type="file" class="mk-ocr-file" accept="image/png,image/jpeg" hidden>');
    html.push('          </div>');
    html.push('          <div class="mk-ocr-cropwrap" hidden>');
    html.push('            <canvas class="mk-ocr-canvas"></canvas>');
    html.push('            <div class="mk-ocr-crophint">在图上拖拽，框选包含物品名的区域（可整图不框）</div>');
    html.push('          </div>');
    html.push('          <div class="mk-ocr-actions">');
    html.push('            <button type="button" class="mk-btn mk-ocr-run" disabled>识别</button>');
    html.push('            <button type="button" class="mk-link mk-ocr-repick" hidden>重选图片</button>');
    html.push('            <span class="mk-ocr-status" role="status" aria-live="polite"></span>');
    html.push('          </div>');
    html.push('        </div>');
    html.push('        <div class="mk-ocr-right">');
    html.push('          <div class="mk-ocr-empty">识别结果会显示在这里</div>');
    html.push('          <table class="mk-ocr-table" hidden>');
    html.push('            <thead><tr><th>物品</th><th>匹配</th><th class="mk-ocr-th-price">最新价</th><th class="mk-ocr-th-slot">每格</th></tr></thead>');
    html.push('            <tbody class="mk-ocr-tbody"></tbody>');
    html.push('          </table>');
    html.push('          <img class="mk-ocr-annotated" alt="识别区域标注" hidden>');
    html.push('        </div>');
    html.push('      </div>');
    html.push('    </div>');
    html.push('  </div>');
    html.push('</div>');
    root.innerHTML = html.join("");

    ui.app = root.querySelector(".mk-app");
    ui.search = root.querySelector(".mk-search-input");
    ui.lvRange = root.querySelector(".mk-lv-range");
    ui.lvOut = root.querySelector(".mk-lv-out");
    ui.modeBox = root.querySelector(".mk-modes");
    ui.reset = root.querySelector(".mk-reset");
    ui.types = root.querySelector(".mk-types");
    ui.typeClear = root.querySelector(".mk-type-clear");
    ui.count = root.querySelector(".mk-count");
    ui.banner = root.querySelector(".mk-banner");
    ui.stale = root.querySelector(".mk-stale");
    ui.host = root.querySelector(".mk-tablehost");
    ui.table = root.querySelector(".mk-table");
    ui.thead = root.querySelector("thead");
    ui.tbody = root.querySelector(".mk-tbody");
    ui.empty = root.querySelector(".mk-empty");
    ui.emptyTitle = root.querySelector(".mk-empty-title");
    ui.emptyDetail = root.querySelector(".mk-empty-detail");
    ui.emptyBtn = root.querySelector(".mk-empty-btn");
    ui.cutoff = root.querySelector(".mk-cutoff");
    ui.priceSub = root.querySelector(".mk-price-sub");
    ui.footCount = root.querySelector(".mk-foot-count");
    ui.footSel = root.querySelector(".mk-foot-sel");
    ui.copySel = root.querySelector(".mk-copy-sel");
    ui.selClear = root.querySelector(".mk-sel-clear");
    ui.checkAll = root.querySelector(".mk-check-all");
    ui.toast = root.querySelector(".mk-toast");
    // R234 截图识别面板
    ui.ocr = root.querySelector(".mk-ocr");
    ui.ocrBtn = root.querySelector(".mk-ocr-btn");
    ui.ocrDrop = root.querySelector(".mk-ocr-drop");
    ui.ocrFile = root.querySelector(".mk-ocr-file");
    ui.ocrCropWrap = root.querySelector(".mk-ocr-cropwrap");
    ui.ocrCanvas = root.querySelector(".mk-ocr-canvas");
    ui.ocrRun = root.querySelector(".mk-ocr-run");
    ui.ocrRepick = root.querySelector(".mk-ocr-repick");
    ui.ocrStatus = root.querySelector(".mk-ocr-status");
    ui.ocrEmpty = root.querySelector(".mk-ocr-empty");
    ui.ocrTable = root.querySelector(".mk-ocr-table");
    ui.ocrTbody = root.querySelector(".mk-ocr-tbody");
    ui.ocrAnnotated = root.querySelector(".mk-ocr-annotated");
    ui.ocrSub = root.querySelector(".mk-ocr-sub");
    ui.modal = root.querySelector(".mk-modal");
    ui.modalName = root.querySelector(".mk-modal-name");
    ui.modalMeta = root.querySelector(".mk-modal-meta");
    ui.modalIcon = root.querySelector(".mk-modal-icon");
    ui.modalTabs = root.querySelector(".mk-modal-tabs");
    ui.modalRight = root.querySelector(".mk-modal-right");
    ui.priceBlock = root.querySelector(".mk-priceblock");
    ui.sellto = root.querySelector(".mk-sellto");
    ui.tabPane = root.querySelector(".mk-tabpane");
    ui.hist72 = root.querySelector(".mk-hist72");
    ui.modalX = root.querySelector(".mk-modal-x");

    // 数据截止徽标放在主工具栏末尾（不挤占搜索/Lv/价格口径）
    ui.cutoff = document.createElement("span");
    ui.cutoff.className = "mk-cutoff";
    ui.cutoff.setAttribute("role", "status");
    ui.cutoff.setAttribute("aria-live", "polite");
    // R255/R268：「获取最新数据」按钮放在截止徽标左边；云端拉取统一走这个按钮，
    // 判定规则是「缓存是否已覆盖最近采集时刻（:01 / :31）」，不再按固定 20 分钟拦人。
    ui.cutoffFetch = document.createElement("button");
    ui.cutoffFetch.type = "button";
    ui.cutoffFetch.className = "mk-cutoff-fetch";
    ui.cutoffFetch.textContent = "获取最新数据";
    ui.cutoffFetch.title = "从云端获取行情（免费：每日 24 次、CD 59:59；会员：CD 30 秒）";
    ui.cutoffFetch.addEventListener("click", manualFetch);
    var cutoffWrap = document.createElement("span");
    cutoffWrap.className = "mk-cutoff-wrap";
    cutoffWrap.appendChild(ui.cutoffFetch);
    cutoffWrap.appendChild(ui.cutoff);
    ui.cutoffWarn = document.createElement("span");
    ui.cutoffWarn.className = "mk-cutoff-warn";
    ui.cutoffWarn.hidden = true;   // 初始没有提示：否则会留下一个空的红色小方框
    cutoffWrap.appendChild(ui.cutoffWarn);
    // R266：截止徽标 + 「获取最新数据」上移到二级工具条最右侧（全站可见）；
    // 容器缺失时回退到市场自己的工具栏，保证按钮不丢。
    var cutoffHost = document.getElementById("vt-market-meta") || root.querySelector(".mk-tb-main");
    cutoffHost.appendChild(cutoffWrap);

    buildModeButtons();
    buildTypeButtons();
    bindEvents();
  }

  function buildModeButtons() {
    ui.modeBtns = [];
    PRICE_MODES.forEach(function (m) {
      // R265：最新 / 24h / 7日 三档已上移到二级工具条（#vt-prices），市场页只保留
      // 本地附加的「每格 / 每公斤」两个口径（由 window.GWMarket.setBasis 接收基准）。
      if (m.key === "last" || m.key === "avg24h" || m.key === "avg7d") { return; }
      var b = document.createElement("button");
      b.type = "button";
      b.className = "mk-mode";
      b.setAttribute("role", "tab");
      b.setAttribute("data-mode", m.key);
      b.setAttribute("aria-selected", String(m.key === st.priceMode));
      b.title = m.hint;
      var t = document.createElement("span");
      t.className = "mk-mode-label";
      t.textContent = m.label;
      var e = document.createElement("span");
      e.className = "mk-mode-en";
      e.textContent = m.en;
      b.appendChild(t);
      b.appendChild(e);
      b.addEventListener("click", function () {
        if (st.priceMode === m.key) { return; }
        st.priceMode = m.key;
        savePrefs();
        applyFilters();
      });
      ui.modeBox.appendChild(b);
      ui.modeBtns.push(b);
    });
  }

  function buildTypeButtons() {
    ui.typeBtns = [];
    TYPE_FILTERS.forEach(function (f) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "mk-type";
      b.setAttribute("data-type", f.key);
      b.setAttribute("aria-pressed", String(st.types.indexOf(f.key) >= 0));
      b.classList.toggle("is-on", st.types.indexOf(f.key) >= 0);
      b.textContent = f.label;
      b.title = "按上游 type 判定：" + f.types.join(" / ");
      b.addEventListener("click", function () {
        var i = st.types.indexOf(f.key);
        if (i >= 0) { st.types.splice(i, 1); } else { st.types.push(f.key); }
        savePrefs();
        applyFilters();
      });
      ui.types.appendChild(b);
      ui.typeBtns.push(b);
    });
    ui.typeClear.addEventListener("click", function () {
      st.types = [];
      savePrefs();
      applyFilters();
    });
  }

  // ---------------------------------------------------------------- R234 截图识别
  var ocrState = { img: null, url: "", crop: null, dragging: false, dragStart: null, busy: false };

  function ocrOpen() {
    if (!ui.ocr) { return; }
    ui.ocr.hidden = false;
    if (root) { root.classList.add("mk-modal-open"); }
    if (ui.ocrBtn) { ui.ocrBtn.focus(); }
  }

  function ocrClose() {
    if (!ui.ocr || ui.ocr.hidden) { return; }
    ui.ocr.hidden = true;
    if (root) { root.classList.remove("mk-modal-open"); }
    ocrResetImage();
  }

  function ocrResetImage() {
    ocrState.img = null;
    if (ocrState.url) { URL.revokeObjectURL(ocrState.url); }
    ocrState.url = "";
    ocrState.crop = null;
    ocrState.dragging = false;
    ui.ocrCropWrap.hidden = true;
    ui.ocrRun.disabled = true;
    ui.ocrRepick.hidden = true;
    ui.ocrFile.value = "";
    ocrSetStatus("");
    ui.ocrEmpty.hidden = false;
    ui.ocrTable.hidden = true;
    ui.ocrTbody.innerHTML = "";
    ui.ocrAnnotated.hidden = true;
    ui.ocrAnnotated.removeAttribute("src");
  }

  function ocrSetStatus(text, isErr) {
    ui.ocrStatus.textContent = text || "";
    ui.ocrStatus.classList.toggle("mk-ocr-status-err", !!isErr);
  }

  function ocrLoadBlob(blob) {
    if (!blob || blob.type.indexOf("image/") !== 0) {
      ocrSetStatus("不是图片文件", true);
      return;
    }
    var url = URL.createObjectURL(blob);
    var im = new Image();
    im.onload = function () {
      ocrResetImage();               // 清上一张（含 revoke）
      ocrState.img = im;
      ocrState.url = url;            // reset 后重新持有
      ui.ocrCropWrap.hidden = false;
      ui.ocrRun.disabled = false;
      ui.ocrRepick.hidden = false;
      ocrSetStatus("已载入 " + im.naturalWidth + "×" + im.naturalHeight);
      ocrDrawCanvas();
    };
    im.onerror = function () {
      URL.revokeObjectURL(url);
      ocrSetStatus("图片载入失败", true);
    };
    im.src = url;
  }

  function ocrDrawCanvas() {
    var im = ocrState.img;
    if (!im) { return; }
    var maxW = ui.ocrCropWrap.clientWidth || 420;
    var scale = Math.min(1, maxW / im.naturalWidth);
    var w = Math.max(1, Math.round(im.naturalWidth * scale));
    var h = Math.max(1, Math.round(im.naturalHeight * scale));
    ui.ocrCanvas.width = w;
    ui.ocrCanvas.height = h;
    var ctx = ui.ocrCanvas.getContext("2d");
    ctx.drawImage(im, 0, 0, w, h);
    ocrState.scale = scale;
    if (ocrState.crop) {
      var c = ocrState.crop;
      ctx.strokeStyle = "#69b6e1";
      ctx.lineWidth = 2;
      ctx.strokeRect(c.x * scale, c.y * scale, c.w * scale, c.h * scale);
      ctx.fillStyle = "rgba(105,182,225,0.15)";
      ctx.fillRect(c.x * scale, c.y * scale, c.w * scale, c.h * scale);
    }
  }

  function ocrCanvasPos(ev) {
    var r = ui.ocrCanvas.getBoundingClientRect();
    return { x: (ev.clientX - r.left) / (ocrState.scale || 1),
             y: (ev.clientY - r.top) / (ocrState.scale || 1) };
  }

  function ocrCropPayload() {
    var im = ocrState.img;
    if (!im) { return null; }
    var src;
    if (ocrState.crop) {
      var c = ocrState.crop;
      // 收敛到图像边界，且最小 8px，避免误拖
      var x = Math.max(0, Math.min(im.naturalWidth - 8, Math.round(c.x)));
      var y = Math.max(0, Math.min(im.naturalHeight - 8, Math.round(c.y)));
      var w = Math.max(8, Math.min(im.naturalWidth - x, Math.round(c.w)));
      var h = Math.max(8, Math.min(im.naturalHeight - y, Math.round(c.h)));
      src = { x: x, y: y, w: w, h: h };
    } else {
      src = { x: 0, y: 0, w: im.naturalWidth, h: im.naturalHeight };
    }
    var cv = document.createElement("canvas");
    cv.width = src.w;
    cv.height = src.h;
    cv.getContext("2d").drawImage(im, src.x, src.y, src.w, src.h, 0, 0, src.w, src.h);
    return cv.toDataURL("image/png");
  }

  function ocrRun() {
    if (ocrState.busy || !ocrState.img) { return; }
    var payload = ocrCropPayload();
    if (!payload) { return; }
    ocrState.busy = true;
    ui.ocrRun.disabled = true;
    ocrSetStatus("识别中…（整图分块约 5-15 秒，首次另需 1-2 秒装载）");
    fetch("api/ocr/recognize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ image: payload, annotate: true })
    }).then(function (res) {
      return res.json().then(function (data) { return { status: res.status, data: data }; });
    }).then(function (r) {
      var d = r.data || {};
      if (r.status === 503) {
        ocrSetStatus("OCR 不可用：" + (d.hint || d.error || "缺少依赖或模型"), true);
        return;
      }
      if (!r.data || d.ok !== true) {
        ocrSetStatus(d.error || ("识别失败（HTTP " + r.status + "）"), true);
        return;
      }
      ocrRenderResult(d);
    }).catch(function (err) {
      ocrSetStatus("请求失败：" + (err && err.message || err), true);
    }).finally(function () {
      ocrState.busy = false;
      ui.ocrRun.disabled = false;
    });
  }

  function ocrRenderResult(d) {
    // R19.81：未登录只识别物品名，价格一律留空（服务端已抹掉目录基线价）
    ocrSetStatus(d.counts.matched + " / " + d.counts.lines +
      " 行匹配 · OCR " + d.tookMs + " ms" +
      (d.loginRequired ? " · 市场行情来自云端，需登录账号获取（当前只识别物品名）"
        : d.offline ? " · 云端离线，用本机缓存"
        : d.nonLive ? " · 云端行情（非实时）" : ""));
    ui.ocrEmpty.hidden = true;
    ui.ocrTable.hidden = false;
    ui.ocrTbody.innerHTML = "";
    d.matches.forEach(function (m, i) {
      var tr = document.createElement("tr");
      tr.className = "mk-ocr-row";
      tr.title = "OCR「" + m.text + "」 → " + m.tier + "（置信 " + Math.round(m.ocrScore * 100) + "%）";
      var tdName = el("td", "mk-ocr-name");
      var icon = el("img", "mk-ocr-icon");
      icon.width = 28; icon.height = 28; icon.alt = "";
      if (api.icon) { api.icon(icon, m.id); }
      else { icon.src = "assets/icons-transparent/" + m.id + ".png"; }
      var nameBox = el("div", "mk-ocr-nametext");
      nameBox.appendChild(el("div", "mk-ocr-n", m.name));
      if (m.short && m.short !== m.name) { nameBox.appendChild(el("div", "mk-ocr-short", m.short)); }
      tdName.appendChild(icon);
      tdName.appendChild(nameBox);
      var badge = el("span", "mk-ocr-idx", String(i + 1));
      tdName.insertBefore(badge, icon);
      tr.appendChild(tdName);
      tr.appendChild(el("td", "mk-ocr-tier", m.tier));
      // 价格：优先市场页同源 quote()（随模式/会员态），缺失时用服务端返回
      var q = (typeof api.quote === "function") ? api.quote(m.id) : null;
      // R258：三档价格优先级 —— 跳蚤价 → 商人售卖价（玩家从商人处买）→ 商人收购价（卖给商人）
      var kind = (m.price && m.price.priceSource) || "flea";
      var isTraderSell = kind === "traderSell";
      var isTraderBuy = kind === "trader";
      var trader = isTraderSell || isTraderBuy;
      var lastLow, base;
      if (isTraderSell) {
        lastLow = base = m.price.traderSell;
      } else if (isTraderBuy) {
        lastLow = base = m.price.trader;
      } else {
        lastLow = (q && q.lastLow !== undefined && q.lastLow !== null) ? q.lastLow : m.price.lastLow;
        base = (q && q.lastLow) ? q.lastLow
          : (lastLow !== null && lastLow !== undefined ? lastLow : m.price.base);
        if (lastLow === null || lastLow === undefined) { lastLow = m.price.base; }
      }
      var gw = m.gw, gh = m.gh;
      var perSlot = (typeof base === "number" && base > 0 && gw > 0 && gh > 0) ? (base / (gw * gh)) : null;
      var priceTd = el("td", "mk-ocr-price" + (trader ? " mk-ocr-price-trader" : ""),
        typeof lastLow === "number" ? fmt(lastLow) + " ₽" : "—");
      if (trader) {
        priceTd.title = isTraderSell
          ? "跳蚤不卖，显示从商人处购买的价格（浮窗会标蓝购物车）"
          : "禁止在跳蚤市场挂单，显示卖给商人的最高收购价（浮窗显示该商人头像）";
        priceTd.appendChild(el("span", "mk-ocr-trader", isTraderSell ? "商售价" : "商人价"));
      }
      // R250：弹药名按格子右下角数量形态区分弹药包（xx/xx）与散装堆叠（纯数字）
      if (m.ammoKind) {
        var loose = m.ammoKind === "loose";
        var badge = el("span", "mk-ocr-ammo" + (loose ? " mk-ocr-ammo-loose" : ""),
          loose ? ("散弹×" + (m.qty || 1)) : ("弹药包" + (m.qty ? " " + m.qty + "发" : "")));
        var p = m.price || {};
        badge.title = loose
          ? ("未识别到 xx/xx → 散装子弹；整堆价 = 单发商人收购价 "
             + (p.unitPrice !== undefined ? p.unitPrice + " ₽" : "—") + " × " + (m.qty || 1) + " 发"
             + (p.qtyFound === false ? "（数量行未识别到，按 1 发保守计算）" : ""))
          : "识别到 xx/xx → 弹药包，显示该弹药包的价格";
        if (loose) { priceTd.title = badge.title; }
        tdName.appendChild(badge);
        // R251：同短名多口径（.338 AP vs .300 AP、50 发装 .300/.45 撞车…）——
        // 游戏内显示名完全相同，截图上无法区分，标「?」并把候选价目写进 tooltip
        if (m.price && m.price.ambiguous) {
          var cands = (m.price.candidates || []).map(function (c) {
            return c.name + "  " + (typeof c.price === "number" ? fmt(c.price) + " ₽" : "无价")
              + (c.kind === "loose" ? "/发" : "");
          }).join("\n");
          var amb = el("span", "mk-ocr-ambig", "?");
          amb.title = "短名相同、口径不同（游戏内显示名一样，截图上无法区分）。\n"
            + "当前显示的是 " + m.name + " 的价；全部候选：\n" + cands;
          priceTd.appendChild(amb);
          priceTd.title = amb.title;
        }
      }
      // R-fix：撞名徽记（与弹药同款）——**一个显示名对应多个不同物品**时标注。
      // 例：实验室白卡 / 蓝色记号钥匙卡 / 钥匙卡收纳盒在游戏里都显示「钥匙卡」，
      // 截图看不出区别；旧逻辑按「每格价最高」直接挑，白卡会被显示成收纳盒的价。
      if (m.ambiguous && !(m.price && m.price.ambiguous)) {
        var icands = (m.candidates || []).map(function (c) {
          return c.name + "  " + (typeof c.price === "number" ? fmt(c.price) + " ₽" : "无价");
        }).join("\n");
        var iamb = el("span", "mk-ocr-ambig", "?");
        iamb.title = "显示名相同、物品不同（游戏内显示名一样，截图上无法区分）。\n"
          + "当前显示的是 " + m.name + " 的价；全部候选：\n" + icands;
        nameBox.appendChild(iamb);      // 挂在名字后面：一眼看出「这名字有歧义」
        priceTd.classList.add("mk-ocr-price-ambig");
        priceTd.title = iamb.title;
        tdName.title = iamb.title;
      }
      tr.appendChild(priceTd);
      tr.appendChild(el("td", "mk-ocr-slot", perSlot !== null ? fmt(perSlot) : "—"));
      tr.addEventListener("click", function () { openModal(m.id); });
      ui.ocrTbody.appendChild(tr);
    });
    if (d.annotated) {
      ui.ocrAnnotated.src = d.annotated;
      ui.ocrAnnotated.hidden = false;
    } else {
      ui.ocrAnnotated.hidden = true;
    }
    if (!d.matches.length) {
      ui.ocrEmpty.textContent = d.counts.lines
        ? "识别到 " + d.counts.lines + " 行文字，但没有匹配到物品（试一下框小一点、对准物品名）"
        : "没有识别到文字（战局空白画面属正常；换一张带物品名的截图）";
      ui.ocrEmpty.hidden = false;
      ui.ocrTable.hidden = true;
    }
  }

  function bindOcr() {
    ui.ocrBtn.addEventListener("click", ocrOpen);
    root.addEventListener("click", function (ev) {
      var t = ev.target;
      var closer = t.closest ? t.closest("[data-ocr-close]") : null;
      if (closer) { ocrClose(); return; }
      if (t.closest && t.closest(".mk-ocr-btn")) { return; }
    });
    ui.ocrDrop.addEventListener("click", function () { ui.ocrFile.click(); });
    ui.ocrDrop.addEventListener("dragover", function (ev) { ev.preventDefault(); });
    ui.ocrDrop.addEventListener("drop", function (ev) {
      ev.preventDefault();
      if (ev.dataTransfer && ev.dataTransfer.files && ev.dataTransfer.files[0]) {
        ocrLoadBlob(ev.dataTransfer.files[0]);
      }
    });
    ui.ocrFile.addEventListener("change", function () {
      if (this.files && this.files[0]) { ocrLoadBlob(this.files[0]); }
    });
    ui.ocrRepick.addEventListener("click", ocrResetImage);
    ui.ocrRun.addEventListener("click", ocrRun);
    // Ctrl+V 粘贴截图（面板打开时）
    document.addEventListener("paste", function (ev) {
      if (ui.ocr.hidden) { return; }
      var items = ev.clipboardData && ev.clipboardData.items;
      if (!items) { return; }
      for (var i = 0; i < items.length; i++) {
        if (items[i].type.indexOf("image/") === 0) {
          ocrLoadBlob(items[i].getAsFile());
          ev.preventDefault();
          return;
        }
      }
    });
    // 画布框选
    ui.ocrCanvas.addEventListener("mousedown", function (ev) {
      ocrState.dragging = true;
      ocrState.dragStart = ocrCanvasPos(ev);
      ocrState.crop = null;
    });
    ui.ocrCanvas.addEventListener("mousemove", function (ev) {
      if (!ocrState.dragging) { return; }
      var p = ocrCanvasPos(ev);
      var s = ocrState.dragStart;
      ocrState.crop = { x: Math.min(s.x, p.x), y: Math.min(s.y, p.y),
                        w: Math.abs(p.x - s.x), h: Math.abs(p.y - s.y) };
      ocrDrawCanvas();
    });
    document.addEventListener("mouseup", function () {
      if (ocrState.dragging) {
        ocrState.dragging = false;
        if (ocrState.crop && (ocrState.crop.w < 8 || ocrState.crop.h < 8)) {
          ocrState.crop = null;   // 太小当误拖
          ocrDrawCanvas();
        }
      }
    });
    // Escape 关面板（放冒泡前端，避免同时触发详情弹窗）
    ui.ocr.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape") {
        ev.stopPropagation();
        ocrClose();
      }
    });
  }

  function bindEvents() {
    bindOcr();
    ui.search.value = st.query;
    ui.lvRange.value = String(st.lv);
    ui.search.addEventListener("input", function () {
      st.query = this.value;
      applyFilters();
    });
    ui.search.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape" && this.value) {
        ev.stopPropagation();
        this.value = "";
        st.query = "";
        applyFilters();
      }
    });
    ui.lvRange.addEventListener("input", function () {
      st.lv = parseInt(this.value, 10) || 0;
      savePrefs();
      applyFilters();
    });
    ui.reset.addEventListener("click", resetFilters);
    ui.host.addEventListener("scroll", function () {
      if (this.scrollTop + this.clientHeight >= this.scrollHeight - 180) { appendChunk(); }
    });
    var ths = ui.thead.querySelectorAll("th[data-sort]");
    for (var i = 0; i < ths.length; i++) {
      ths[i].addEventListener("click", function () { sortBy(this.getAttribute("data-sort")); });
      ths[i].addEventListener("keydown", function (ev) {
        if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); sortBy(this.getAttribute("data-sort")); }
      });
    }
    ui.checkAll.addEventListener("change", function () {
      setFilteredSelected(this.checked);
    });
    ui.tbody.addEventListener("change", function (ev) {
      var cb = ev.target;
      if (!cb || !cb.classList || !cb.classList.contains("mk-check")) { return; }
      var tr = cb.closest ? cb.closest("tr") : null;
      if (!tr) { return; }
      setRowSelected(tr.getAttribute("data-id"), cb.checked);
    });
    ui.tbody.addEventListener("click", function (ev) {
      var t = ev.target;
      if (!t) { return; }
      if (t.classList && t.classList.contains("mk-check")) { return; }
      if (t.closest && t.closest(".mk-col-check")) { return; }
      var tr2 = t.closest ? t.closest("tr.mk-row") : null;
      if (tr2) { openModal(tr2.getAttribute("data-id")); }
    });
    ui.copySel.addEventListener("click", function () {
      var picked = Object.keys(selectedIds).filter(function (id) { return rowById[id]; });
      if (!picked.length) { return; }
      var text = picked.map(function (id) { return rowCopyLine(rowById[id]); }).join("\n");
      copyText(text, "已复制 " + picked.length + " 件物品（名称 + 最新价）");
    });
    ui.selClear.addEventListener("click", function () { clearSelection(); });
    ui.modal.addEventListener("click", function (ev) {
      var t = ev.target;
      if (!t) { return; }
      var closer = t.closest ? t.closest("[data-mk-close]") : null;
      if (closer) { closeModal(); return; }
      var sellToggle = t.closest ? t.closest("[data-mk-sellto-toggle]") : null;
      if (sellToggle) {
        sellToExpanded = !sellToExpanded;
        renderSellTo();
        return;
      }
      var tab = t.closest ? t.closest("[data-tab]") : null;
      if (tab && modalRow) {
        modalTab = tab.getAttribute("data-tab");
        syncModalTabs();
        renderTabPane();
      }
    });
    // 只在详情打开且市场视图可见时吃掉 Esc，避免影响既有页面的 Esc 行为。
    document.addEventListener("keydown", function (ev) {
      if (!modalOpen || !root || root.hidden) { return; }
      if (ev.key === "Escape") {
        ev.preventDefault();
        ev.stopPropagation();
        closeModal();
      }
    }, true);
  }

  function setRowSelected(id, on) {
    if (!id) { return; }
    if (on) { selectedIds[id] = true; } else { delete selectedIds[id]; }
    var tr = ui.tbody.querySelector('tr[data-id="' + id + '"]');
    if (tr) { tr.classList.toggle("is-selected", !!on); }
    updateSelectionUI();
  }

  function setFilteredSelected(on) {
    filtered.forEach(function (row) {
      if (on) { selectedIds[row.id] = true; } else { delete selectedIds[row.id]; }
    });
    var trs = ui.tbody.querySelectorAll("tr.mk-row");
    for (var i = 0; i < trs.length; i++) {
      var id = trs[i].getAttribute("data-id");
      trs[i].classList.toggle("is-selected", !!selectedIds[id]);
      var cb = trs[i].querySelector(".mk-check");
      if (cb) { cb.checked = !!selectedIds[id]; }
    }
    updateSelectionUI();
  }

  function clearSelection() {
    selectedIds = {};
    var trs = ui.tbody.querySelectorAll("tr.mk-row");
    for (var i = 0; i < trs.length; i++) {
      trs[i].classList.remove("is-selected");
      var cb = trs[i].querySelector(".mk-check");
      if (cb) { cb.checked = false; }
    }
    updateSelectionUI();
  }

  // ---------------------------------------------------------------- 详情弹窗
  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) { node.className = cls; }
    if (text !== undefined && text !== null) { node.textContent = text; }
    return node;
  }

  function srcLabel(key) {
    var map = {
      flea: "跳蚤市场购买",
      trader: "商人购买",
      barter: "商人兑换",
      quest: "任务奖励",
      craft: "藏身处制作",
      none: "上游标记为不可获得",
      unknown: "上游未确认获取方式"
    };
    return map[key] || key;
  }

  function openModal(id) {
    var row = rowById[id];
    if (!row || !ui.modal) { return; }
    modalRow = row;
    modalTab = "obtain";
    sellToExpanded = false;
    modalLastFocus = document.activeElement;
    modalOpen = true;
    ui.modal.hidden = false;
    if (root) { root.classList.add("mk-modal-open"); }

    ui.modalIcon.src = "";
    if (api.icon) {
      api.icon(ui.modalIcon, row.id);
    } else {
      ui.modalIcon.src = "assets/icons-transparent/" + row.id + ".png";
    }
    ui.modalName.textContent = row.name;
    ui.modalMeta.textContent = "";
    if (row.short && row.short !== row.name) { ui.modalMeta.appendChild(el("span", "mk-mm", row.short)); }
    ui.modalMeta.appendChild(el("span", "mk-mm", "Lv " + (row.lv === null ? "—" : row.lv)));
    (row.rec.ts || []).slice(0, 4).forEach(function (t) {
      ui.modalMeta.appendChild(el("span", "mk-mm", t));
    });
    var snap = api && typeof api.snapshot === "function" ? (api.snapshot() || {}) : {};
    var upd = row.quote.updated || row.quote.rowFetchedAt;
    var srcMeta = el("span", "mk-mm mk-mm-src",
      (snap.cached ? "云端缓存" : "云端行情") +
      (upd ? " · 截止 " + shortAge(upd) : " · 更新时间未知"));
    srcMeta.title = upd ? ("数据时间：" + upd) : "该物品没有可用的更新时间";
    ui.modalMeta.appendChild(srcMeta);
    if (row.noFlea) { ui.modalMeta.appendChild(el("span", "mk-mm mk-mm-ban", "Banned")); }

    renderPriceBlock();
    renderSellTo();
    syncModalTabs();
    renderTabPane();
    ensureHistory();
    if (ui.modalX) { ui.modalX.focus(); }
  }

  function closeModal() {
    if (!modalOpen || !ui.modal) { return; }
    modalOpen = false;
    modalRow = null;
    histState.token += 1;      // 让在途请求的回包失效，别写进下一个物品的弹窗
    histState.phase = "idle";
    histState.key = "";
    histState.data = null;
    histState.error = null;
    ui.modal.hidden = true;
    if (root) { root.classList.remove("mk-modal-open"); }
    if (modalLastFocus && modalLastFocus.focus) {
      try { modalLastFocus.focus(); } catch (e) { /* 元素可能已不在 DOM */ }
    }
    modalLastFocus = null;
  }

  function syncModalTabs() {
    var tabs = ui.modalTabs.querySelectorAll("[data-tab]");
    for (var i = 0; i < tabs.length; i++) {
      tabs[i].setAttribute("aria-selected", String(tabs[i].getAttribute("data-tab") === modalTab));
    }
  }

  function renderPriceBlock() {
    if (!modalRow) { return; }
    ui.priceBlock.textContent = "";
    ui.priceBlock.appendChild(el("div", "mk-block-title", "价格口径（与列表同一份行情）"));
    var q = modalRow.quote;
    var rows = [
      { label: "Last 最新", value: q.lastLow, note: "跳蚤最近一次最低挂单（lastLowPrice）" },
      { label: "Avg 24h", value: q.avg24h, note: "上游 24 小时历史均价（avg24hPrice）" },
      { label: "Avg 7d", value: q.avg7d, note: "云端价格缓存过去 7 天均价；无采样时不插值、不估算" }
    ];
    var list = el("div", "mk-price-list");
    var member = !!(api && typeof api.isMember === "function" && api.isMember());
    rows.forEach(function (r) {
      var item = el("div", "mk-price-row");
      item.appendChild(el("span", "mk-pr-label", r.label));
      var locked = !member && r.label !== "Last 最新";
      var val = el("span", "mk-pr-value" + (r.value === null ? " is-muted" : ""),
        locked ? "会员功能" :
          (r.value === null ? (r.label.indexOf("7d") >= 0 ? "积累中" : "—") : (fmt(r.value) + " ₽")));
      item.appendChild(val);
      item.appendChild(el("span", "mk-pr-note", locked ? "仅有效会员可查看此口径" : r.note));
      list.appendChild(item);
    });
    ui.priceBlock.appendChild(list);
    var rec = modalRow.rec;
    var gw = num(rec.gw);
    var gh = num(rec.gh);
    var wt = num(rec.w);
    if (gw !== null || gh !== null || wt !== null) {
      var size = el("div", "mk-sizechips");
      if (gw !== null && gh !== null) { size.appendChild(el("span", "mk-mm", "尺寸 " + gw + "×" + gh)); }
      if (wt !== null) { size.appendChild(el("span", "mk-mm", "重量 " + (Math.round(wt * 100) / 100) + " kg")); }
      ui.priceBlock.appendChild(size);
    }
    var snap = api && typeof api.snapshot === "function" ? (api.snapshot() || {}) : {};
    var upd = q.updated || q.rowFetchedAt;
    var updEl = el("div", "mk-price-upd",
      upd ? ("数据时间：" + upd + "（" + shortAge(upd) + "）") :
        "该物品没有逐物品更新时间");
    if (upd) { updEl.title = upd; }
    ui.priceBlock.appendChild(updEl);
  }

  function renderSellTo() {
    if (!modalRow) { return; }
    ui.sellto.textContent = "";
    ui.sellto.appendChild(el("div", "mk-block-title", "Sell to 卖给谁（商人收购价）"));
    var list = modalRow.sellTo;
    if (!list.length) {
      ui.sellto.appendChild(el("p", "mk-note", "上游没有该物品的商人收购价（sellToTrader）；不显示 0，也不拿跳蚤价冒充。"));
      return;
    }
    var best = list[0];
    list.forEach(function (pair) {
      if (pair[1] > best[1]) { best = pair; }
    });
    var bestEl = el("div", "mk-sellto-best");
    bestEl.appendChild(el("span", "mk-note", "最高收购"));
    bestEl.appendChild(traderIcon(best[0], 20, "mk-trader"));
    bestEl.appendChild(el("b", null, traderNameOf(best[0])));
    bestEl.appendChild(el("b", "mk-sellto-price", fmt(best[1]) + " ₽"));
    ui.sellto.appendChild(bestEl);

    // 默认只给最高值，避免详情弹窗被 7 行商人列表撑长；需要时再展开。
    if (list.length > 1) {
      var toggle = el("button", "mk-link mk-sellto-toggle",
        sellToExpanded ? "收起，只看最高" : ("展开全部 " + list.length + " 个商人"));
      toggle.type = "button";
      toggle.setAttribute("data-mk-sellto-toggle", "1");
      toggle.setAttribute("aria-expanded", String(!!sellToExpanded));
      ui.sellto.appendChild(toggle);
    }
    if (sellToExpanded) {
      list.forEach(function (pair) {
        var tid = pair[0];
        var price = pair[1];
        var line = el("div", "mk-sellto-row");
        line.appendChild(traderIcon(tid, 18, "mk-trader"));
        line.appendChild(el("span", "mk-sellto-name", traderNameOf(tid)));
        line.appendChild(el("span", "mk-sellto-price", fmt(price) + " ₽"));
        line.title = traderNameOf(tid) + " 收购价 " + fmt(price) + " ₽";
        ui.sellto.appendChild(line);
      });
    }
    ui.sellto.appendChild(el("p", "mk-note", "来自上游 sellToTrader（已换算卢布）；与「卖价」列的跳蚤最低挂单不是同一口径。"));
  }

  function renderTabPane() {
    if (!modalRow || !ui.tabPane) { return; }
    ui.tabPane.textContent = "";
    if (modalTab === "uses") { renderUses(); }
    else if (modalTab === "banned") { renderBanned(); }
    else { renderObtain(); }
  }

  function renderObtain() {
    var row = modalRow;
    ui.tabPane.appendChild(el("div", "mk-block-title", "Obtain 获取途径"));
    var srcs = row.rec.src || [];
    var chips = el("div", "mk-src-chips");
    if (srcs.length) {
      srcs.forEach(function (s) { chips.appendChild(el("span", "mk-src-chip", srcLabel(s))); });
    } else {
      chips.appendChild(el("span", "mk-src-chip", "上游没有 src 字段"));
    }
    ui.tabPane.appendChild(chips);

    var flea = el("p", "mk-tab-line");
    if (row.noFlea) {
      flea.appendChild(el("span", "mk-chip-ban", "禁止上跳蚤"));
      flea.appendChild(el("span", null, "不能在跳蚤挂单或购买。"));
    } else {
      flea.appendChild(el("span", "mk-chip-ok", "可上跳蚤"));
      flea.appendChild(el("span", null, "上架等级 Lv " + (row.lv === null ? "—" : row.lv)));
    }
    ui.tabPane.appendChild(flea);

    var buys = (row.rec.trade || []).filter(function (t) { return t && t.k === "buy"; });
    if (buys.length) {
      ui.tabPane.appendChild(el("div", "mk-sub-title", "商人买价（上游 priceRUB，已换算卢布；商人卖给玩家）"));
      buys.forEach(function (t) {
        var p = num(t.p);
        var line = el("div", "mk-tab-row");
        line.appendChild(traderIcon(t.t, 18, "mk-trader"));
        line.appendChild(el("span", "mk-tab-name", traderNameOf(t.t)));
        line.appendChild(el("span", "mk-tab-meta",
          "忠诚 l" + (t.l === null || t.l === undefined ? "—" : t.l) +
          (t.c && t.c !== "RUB" ? " · 原报价 " + t.c : "")));
        line.appendChild(el("span", "mk-tab-price", (p === null ? "—" : fmt(p) + " ₽")));
        if (t.c && t.c !== "RUB") {
          line.title = "上游字段是 priceRUB（已换算成卢布），原币种为 " + t.c;
        }
        ui.tabPane.appendChild(line);
      });
    }

    var barters = (row.rec.trade || []).filter(function (t) { return t && t.k === "barter"; });
    if (barters.length) {
      ui.tabPane.appendChild(el("div", "mk-sub-title", "商人兑换（消耗物品，不是卢布价格）"));
      barters.forEach(function (t) {
        var line = el("div", "mk-tab-row mk-tab-row-block");
        line.appendChild(traderIcon(t.t, 18, "mk-trader"));
        line.appendChild(el("span", "mk-tab-name", traderNameOf(t.t)));
        line.appendChild(el("span", "mk-tab-meta", "忠诚 l" + (t.l === null || t.l === undefined ? "—" : t.l)));
        line.appendChild(el("span", "mk-tab-price", "产出 " + (num(t.o) || 1) + " 件"));
        var need = el("div", "mk-tab-req");
        (t.r || []).forEach(function (pair, idx) {
          if (!Array.isArray(pair) || !pair[0]) { return; }
          var rec = api.item ? api.item(pair[0]) : null;
          var nm = rec && rec.n ? rec.n : pair[0];
          if (idx) { need.appendChild(document.createTextNode("、")); }
          need.appendChild(el("span", "mk-req-item", (num(pair[1]) || 1) + "× " + nm));
        });
        line.appendChild(need);
        ui.tabPane.appendChild(line);
      });
    }

    if (!buys.length && !barters.length) {
      ui.tabPane.appendChild(el("p", "mk-note", "当前模式行情没有该物品的商人买价或兑换配方。"));
    }
  }

  function renderUses() {
    var row = modalRow;
    ensureQuestIndex();
    ui.tabPane.appendChild(el("div", "mk-block-title", "Uses 用途（谁需要它）"));

    // ---- 任务目标：从本地 tasks.<mode>.json 的 objectives 反查，真实可算
    //      具体目标（列出有限几种物品）与通用目标（「任意物品」上千种）分开呈现。
    var quests = questIndex[row.id] || [];
    var specific = [];
    var generic = [];
    quests.forEach(function (q) { (q.generic ? generic : specific).push(q); });
    ui.tabPane.appendChild(el("div", "mk-sub-title",
      "任务目标（反查本地 tasks." + (questState.mode || st.scopeMode()) + ".json）"));
    if (questState.loading) {
      ui.tabPane.appendChild(el("p", "mk-note", "任务数据读取中…（只读本地 data/tasks 目录，不联网）"));
    } else if (questState.error) {
      ui.tabPane.appendChild(el("p", "mk-note",
        "任务数据读取失败：" + questState.error +
        "。任务类引用暂时未覆盖，这不等于「没有引用」。"));
    } else if (!specific.length) {
      ui.tabPane.appendChild(el("p", "mk-note",
        "没有任务把该物品列为具体目标（已检查 " + questState.tasks + " 个任务 / " +
        questState.objectives + " 条目标）。"));
    } else {
      var qlist = el("div", "mk-use-list");
      specific.slice(0, 12).forEach(function (q) {
        var line = el("div", "mk-use-row");
        if (q.traderId) { line.appendChild(traderIcon(q.traderId, 18, "mk-trader")); }
        var txt = el("span", "mk-use-text");
        txt.appendChild(el("b", null, q.taskName));
        txt.appendChild(document.createTextNode(" · " + q.kindZh +
          (q.count !== null && q.count > 1 ? " ×" + q.count : "")));
        if (q.kinds > 1) {
          txt.appendChild(el("span", "mk-use-tag", q.kinds + " 种任一"));
        }
        if (q.optional) {
          txt.appendChild(el("span", "mk-use-tag", "可选目标"));
        }
        if (q.descZh) {
          txt.appendChild(el("span", "mk-use-desc", q.descZh));
        }
        line.appendChild(txt);
        line.title = q.taskName + " · " + q.kindZh + (q.descZh ? "：" + q.descZh : "");
        qlist.appendChild(line);
      });
      ui.tabPane.appendChild(qlist);
      if (specific.length > 12) {
        ui.tabPane.appendChild(el("p", "mk-note", "另有 " + (specific.length - 12) + " 条具体任务引用未展开。"));
      }
    }
    if (!questState.loading && !questState.error && generic.length) {
      // 同一任务可能有多条「任意物品」目标（不同商人/不同计数），按任务去重后再展示。
      var seenTask = {};
      var taskNames = [];
      generic.forEach(function (q) {
        if (seenTask[q.taskId]) { return; }
        seenTask[q.taskId] = true;
        taskNames.push(q.taskName + (q.traderId ? "（" + traderNameOf(q.traderId) + "）" : ""));
      });
      ui.tabPane.appendChild(el("p", "mk-note",
        "通用目标 " + generic.length + " 条，涉及 " + taskNames.length + " 个任务" +
        "（上游把「任意物品」列出上千种可选，对每件物品都成立，不逐条列出）：" +
        taskNames.slice(0, 3).join("、") + (taskNames.length > 3 ? " 等" : "") + "。"));
    }

    // ---- 兑换引用：其他物品的商人兑换配方需要本物品
    var uses = usesIndex[row.id] || [];
    ui.tabPane.appendChild(el("div", "mk-sub-title", "兑换引用（其他物品的商人配方需要它）"));
    if (!uses.length) {
      ui.tabPane.appendChild(el("p", "mk-note", "没有其他物品的商人兑换配方引用它。"));
    } else {
      var list = el("div", "mk-use-list");
      uses.slice(0, 12).forEach(function (u) {
        var rec = api.item ? api.item(u.outId) : null;
        var line = el("div", "mk-use-row");
        line.appendChild(traderIcon(u.trader, 18, "mk-trader"));
        var txt = el("span", "mk-use-text");
        txt.appendChild(el("b", null, rec && rec.n ? rec.n : u.outId));
        txt.appendChild(document.createTextNode(" ×" + u.qty + "，需 " + u.need + "× 本物品"));
        line.appendChild(txt);
        line.title = traderNameOf(u.trader) + " 处兑换：" + (rec && rec.n ? rec.n : u.outId) + " ×" + u.qty;
        list.appendChild(line);
      });
      ui.tabPane.appendChild(list);
      if (uses.length > 12) {
        ui.tabPane.appendChild(el("p", "mk-note", "另有 " + (uses.length - 12) + " 条兑换引用未展开。"));
      }
    }

    // ---- 结论要分开写：「真的没有引用」vs「只有通用目标」vs「这一类暂不覆盖」
    var targeted = specific.length + (usesIndex[row.id] || []).length;
    if (!questState.loading && !questState.error) {
      if (!targeted && !generic.length) {
        ui.tabPane.appendChild(el("p", "mk-note mk-note-strong",
          "没有找到引用：任务目标与商人兑换这两类本地数据里都没有提到该物品。"));
      } else if (!targeted) {
        ui.tabPane.appendChild(el("p", "mk-note mk-note-strong",
          "没有针对性引用：没有任务把该物品列为具体目标，也没有兑换配方引用它；" +
          "只有上面 " + generic.length + " 条「任意物品」通用目标。"));
      }
    }
    ui.tabPane.appendChild(el("p", "mk-note",
      "暂不覆盖：藏身处制作、藏身处升级需求等配方不在本地数据中；这类引用不列出、不猜，也不拿名称相近的物品顶替。"));
  }

  function renderBanned() {
    var row = modalRow;
    ui.tabPane.appendChild(el("div", "mk-block-title", "Banned 禁售判定"));
    var badge = el("span", row.noFlea ? "mk-chip-ban" : "mk-chip-ok", row.noFlea ? "Banned" : "未标记 noFlea");
    var p = el("p", "mk-tab-line");
    p.appendChild(badge);
    p.appendChild(el("span", null, row.noFlea
      ? "上游 types 含 noFlea：禁止在跳蚤市场挂单/购买。"
      : "上游 types 未含 noFlea：允许上跳蚤。快照里没有挂单时最新价会是「—」，但这不等于禁售。"));
    ui.tabPane.appendChild(p);
    ui.tabPane.appendChild(el("p", "mk-note",
      "本视图没有 Stock / Restock / manualPrice / sellPrice 这些上游自有字段，语义未确认，因此不显示、也不填假值。"));
  }

  // ------------------------------------------------------------ R218 价格走势
  // 两个来源：本机采集器快照 + 云端历史（采集机每 30 分钟上传的那份，会员）。
  // 云端只补本机没有的时段，按时间戳去重；都没有就明说，不插值、不补点、
  // 不拿别的模式顶替，也不把单点画成一条曲线。
  function histMode() {
    var s = (api && api.scope) ? (api.scope() || {}) : {};
    return s.mode || "regular";
  }

  function fmtCompact(n) {
    if (typeof n !== "number" || !isFinite(n)) { return "—"; }
    if (Math.abs(n) >= 1e6) { return (n / 1e6).toFixed(2) + "M"; }
    return fmt(n);
  }

  function histStamp(iso, withTime) {
    var d = parseTime(iso);
    if (!d) { return "—"; }
    return histStampMs(d.getTime(), withTime);
  }

  function histStampMs(ms, withTime) {
    var d = new Date(ms);
    if (isNaN(d.getTime())) { return "—"; }
    var day = pad2(d.getMonth() + 1) + "-" + pad2(d.getDate());
    return withTime ? (day + " " + pad2(d.getHours()) + ":" + pad2(d.getMinutes())) : day;
  }

  /**
   * 时间轴窗口：选了区间就按「区间起点 → 区间终点」铺满整条轴，
   * 绝不拿数据首尾当轴（否则 7 天与 30 天会把同一批数据拉成两条一模一样的线）。
   * days = 0（全部）才退回数据首尾。
   */
  function histWindow(windowStart, days, points) {
    var lastMs = null;
    if (points && points.length) {
      var lastD = parseTime(points[points.length - 1][0]);
      if (lastD) { lastMs = lastD.getTime(); }
    }
    if (days > 0) {
      var startD = parseTime(windowStart);
      if (startD) {
        return { t0: startD.getTime(), t1: startD.getTime() + days * 86400000, days: days, kind: "window" };
      }
      var endMs = lastMs === null ? Date.now() : lastMs;
      return { t0: endMs - days * 86400000, t1: endMs, days: days, kind: "window-est" };
    }
    var firstD = points && points.length ? parseTime(points[0][0]) : null;
    var t0 = firstD ? firstD.getTime() : (lastMs === null ? Date.now() : lastMs);
    return { t0: t0, t1: lastMs === null ? t0 : lastMs, days: 0, kind: "data" };
  }

  /** 断档阈值：以采样间隔中位数为基准，至少 45 分钟；超过就视为「这段时间没采集」。 */
  function histGapMs(times) {
    var diffs = [];
    for (var i = 1; i < times.length; i++) { diffs.push(times[i] - times[i - 1]); }
    if (!diffs.length) { return 45 * 60000; }
    diffs.sort(function (a, b) { return a - b; });
    // 取偏低的中位数：点很少时（如「1 个孤立点 + 1 段连续」）不能被那段大空档本身带跑
    var med = diffs[Math.floor((diffs.length - 1) / 2)];
    return Math.max(45 * 60000, med * 2.5);
  }

  /** 按断档把点分成若干段：段与段之间不连线、不补点。 */
  function histSegments(times, gapMs) {
    var out = [];
    var cur = null;
    for (var i = 0; i < times.length; i++) {
      if (!cur || times[i] - times[i - 1] > gapMs) {
        cur = [];
        out.push(cur);
      }
      cur.push(i);
    }
    return out;
  }

  function ensureHistory() {
    if (!modalRow) { return; }
    if (api && typeof api.isMember === "function" && !api.isMember()) {
      histState.token += 1;
      histState.key = "member-required";
      histState.phase = "error";
      histState.data = null;
      histState.error = "member-required";
      renderHist72();
      return;
    }
    var key = histMode() + "|" + modalRow.id + "|" + histState.days;
    if (histState.key === key && histState.phase !== "idle") {
      renderHist72();
      return;
    }
    var token = histState.token + 1;
    histState.token = token;
    histState.key = key;
    histState.phase = "loading";
    histState.data = null;
    histState.error = null;
    renderHist72();
    var url = "api/price-history?mode=" + encodeURIComponent(histMode()) +
      "&itemId=" + encodeURIComponent(modalRow.id) + "&days=" + histState.days;
    fetch(url, { cache: "no-store" }).then(function (res) {
      if (!res.ok) { throw new Error("HTTP " + res.status); }
      return res.json();
    }).then(function (data) {
      if (token !== histState.token) { return; }
      histState.phase = "ready";
      histState.data = data || null;
      renderHist72();
    }).catch(function (err) {
      if (token !== histState.token) { return; }
      histState.phase = "error";
      histState.error = String((err && err.message) || err);
      renderHist72();
    });
  }

  // ---- R279 云端价格缓存：登录后整包下载，点「获取最新数据」只拉增量 ----
  // 状态来源是 /api/price-cache/status（同时带回 member），不额外打云请求。
  var cacheState = { loaded: false, busy: false, member: false, data: null, error: "" };

  function cacheModeEntry() {
    var st = cacheState.data;
    if (!st || !st.modes) { return null; }
    return st.modes[histMode()] || null;
  }

  function fmtCacheTime(sec) {
    if (!sec) { return "尚未同步"; }
    var d = new Date(sec * 1000);
    var pad = function (n) { return (n < 10 ? "0" : "") + n; };
    return (d.getMonth() + 1) + "-" + pad(d.getDate()) + " " +
      pad(d.getHours()) + ":" + pad(d.getMinutes());
  }

  function loadCacheStatus() {
    return fetch("api/price-cache/status", { cache: "no-store" })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        cacheState.loaded = true;
        cacheState.data = data || null;
        cacheState.member = !!(data && data.member);
        cacheState.error = "";
        return cacheState.data;
      })
      .catch(function (err) {
        cacheState.loaded = true;
        cacheState.error = String((err && err.message) || err);
        return null;
      });
  }

  /** 同步云端缓存：本地没有就整包，有 cursor 就增量。 */
  function syncCache(mode) {
    if (cacheState.busy) { return Promise.resolve(null); }
    cacheState.busy = true;
    renderCacheBar();
    return fetch("api/price-cache/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: mode || histMode() })
    }).then(function (res) { return res.json(); }).then(function (data) {
      cacheState.busy = false;
      if (!data || data.ok !== true) {
        cacheState.error = (data && (data.hint || data.error)) || "同步失败";
        return loadCacheStatus().then(function () {
          renderCacheBar();
          return data;
        });
      }
      cacheState.error = "";
      return loadCacheStatus().then(function () {
        renderCacheBar();
        // 强制重画：同步完缓存后曲线数据变了，同一个 key 也要重新取。
        histState.phase = "idle";
        histState.key = "";
        ensureHistory();
        return data;
      });
    }).catch(function (err) {
      cacheState.busy = false;
      cacheState.error = String((err && err.message) || err);
      renderCacheBar();
      return null;
    });
  }

  function renderCacheBar() {
    if (!ui.hist72) { return; }
    var old = ui.hist72.querySelector(".mk-cache-bar");
    if (old) { old.parentNode.removeChild(old); }
    if (!cacheState.loaded) { return; }
    if (!cacheState.member && !cacheState.error) { return; }

    var bar = el("div", "mk-cache-bar");
    var entry = cacheModeEntry();
    var text;
    if (cacheState.busy) {
      text = "正在从云端下载…（首次会一次性拉全部历史，稍等几秒）";
    } else if (cacheState.error) {
      text = cacheState.error;
    } else if (entry && entry.snapshots > 0) {
      text = "云端缓存：" + entry.snapshots + " 份快照 · 更新于 " + fmtCacheTime(entry.updated_at);
    } else {
      text = "云端缓存还没下载（会员登录后自动下载，也可以点右侧按钮）";
    }
    var label = el("span", "mk-cache-text", text);
    bar.appendChild(label);

    var btn = el("button", "mk-cache-sync", cacheState.busy ? "下载中…" : "获取最新数据");
    btn.type = "button";
    btn.disabled = cacheState.busy || !cacheState.member;
    btn.addEventListener("click", function () { syncCache(); });
    bar.appendChild(btn);
    ui.hist72.insertBefore(bar, ui.hist72.children[1] || null);
  }

  function histEmptyBox(title, notes) {    var box = el("div", "mk-hist-empty");
    box.appendChild(el("div", "mk-hist-main", title));
    (notes || []).forEach(function (text) {
      box.appendChild(el("p", "mk-note", text));
    });
    return box;
  }

  function histRangeLabel() {
    var label = "";
    HIST_RANGES.forEach(function (r) { if (r.days === histState.days) { label = r.label; } });
    return label || (histState.days + " 天");
  }

  /** 把 points 画成 SVG；返回容器里的关键位置，供悬浮命中用。 */
  function drawHistoryChart(wrap, series, win) {
    var W = 560, H = 180, L = 70, R = 12, T = 12, B = 26;
    var rows = [];
    var i;
    for (i = 0; i < series.points.length; i++) {
      var p = series.points[i];
      var last = num(p[1]);
      var avg = num(p[2]);
      var value = last === null ? avg : last;
      if (value === null) { continue; }
      var when = parseTime(p[0]);
      if (!when) { continue; }
      rows.push({ t: p[0], tTm: when.getTime(), l: last, a: avg, v: value });
    }
    if (!rows.length) { return null; }

    var vals = rows.map(function (r) { return r.v; });
    var rawMin = Math.min.apply(Math, vals);
    var rawMax = Math.max.apply(Math, vals);
    if (rawMax === rawMin) {
      var bump = Math.max(1, Math.abs(rawMax) * 0.04);
      rawMin -= bump;
      rawMax += bump;
    }
    // 让刻度落在整数上（10/20/50 的倍数），避免出现 384 987 这种读数
    var niceStep = (function (raw) {
      var pow = Math.pow(10, Math.floor(Math.log(raw) / Math.LN10));
      var f = raw / pow;
      var m = f <= 1 ? 1 : (f <= 2 ? 2 : (f <= 5 ? 5 : 10));
      return m * pow;
    }((rawMax - rawMin) / 3));
    var min = Math.floor(rawMin / niceStep) * niceStep;
    var max = Math.ceil(rawMax / niceStep) * niceStep;
    if (max === min) { max = min + niceStep; }
    var ticks = Math.round((max - min) / niceStep);
    if (ticks < 2) { ticks = 2; }
    if (ticks > 5) {
      niceStep = (max - min) / 4;
      ticks = 4;
    }
    var times = [];
    for (i = 0; i < rows.length; i++) { times.push(rows[i].tTm); }
    var winT0 = (win && isFinite(win.t0)) ? win.t0 : times[0];
    var winT1 = (win && isFinite(win.t1)) ? win.t1 : times[times.length - 1];
    var flatX = !(winT1 > winT0);

    function X(t) {
      if (flatX) { return L + (W - L - R) / 2; }
      var x = L + (t - winT0) / (winT1 - winT0) * (W - L - R);
      // 窗口外的点贴边，不画到框外（时钟漂移等异常值不扩大时间轴）
      return Math.max(L, Math.min(W - R, x));
    }
    function Y(v) {
      return T + (max - v) / (max - min) * (H - T - B);
    }

    var pos = rows.map(function (r) { return { x: X(r.tTm), y: Y(r.v) }; });

    // 采样断档就断开：段与段之间不连线、不补点，空白就是空白
    var gapMs = histGapMs(times);
    var segs = histSegments(times, gapMs);
    var baseY = (H - B).toFixed(1);
    var linePaths = [];
    var areaPaths = [];
    var lonely = [];
    segs.forEach(function (seg) {
      if (seg.length < 2) { lonely.push(pos[seg[0]]); return; }
      var d = [];
      seg.forEach(function (idx, k) {
        d.push((k ? "L" : "M") + pos[idx].x.toFixed(1) + " " + pos[idx].y.toFixed(1));
      });
      linePaths.push(d.join(" "));
      areaPaths.push(d.join(" ") + " L" + pos[seg[seg.length - 1]].x.toFixed(1) + " " + baseY +
        " L" + pos[seg[0]].x.toFixed(1) + " " + baseY + " Z");
    });

    var trend = "is-flat";
    if (rows.length >= 2) {
      trend = rows[rows.length - 1].v > rows[0].v ? "is-up"
        : (rows[rows.length - 1].v < rows[0].v ? "is-down" : "is-flat");
    }

    var out = [];
    out.push('<svg class="mk-hist-svg ' + trend + '" viewBox="0 0 ' + W + " " + H +
      '" width="100%" height="' + H + '" role="img" aria-label="' +
      ("价格走势：区间 " + histStampMs(winT0, true) + " 到 " + histStampMs(winT1, true) +
        "，共 " + rows.length + " 个快照") + '">');
    // 网格 + 纵轴刻度
    for (i = 0; i <= ticks; i++) {
      var gy = T + (H - T - B) * i / ticks;
      var gv = max - (max - min) * i / ticks;
      out.push('<line class="mk-hist-grid" x1="' + L + '" y1="' + gy.toFixed(1) +
        '" x2="' + (W - R) + '" y2="' + gy.toFixed(1) + '"></line>');
      out.push('<text class="mk-hist-axis" x="' + (L - 6) + '" y="' + (gy + 3).toFixed(1) +
        '" text-anchor="end">' + fmtCompact(gv) + "</text>");
    }
    // 横轴：按区间铺满，起点 / 中点 / 终点三个刻度（单点时只标一次）
    if (flatX) {
      out.push('<text class="mk-hist-axis mk-hist-axis-x" x="' + (pos[0].x.toFixed(1)) + '" y="' + (H - 8) +
        '" text-anchor="middle">' + histStampMs(winT0, true) + "</text>");
    } else {
      var midT = winT0 + (winT1 - winT0) / 2;
      out.push('<text class="mk-hist-axis mk-hist-axis-x" x="' + L + '" y="' + (H - 8) +
        '" text-anchor="start">' + histStampMs(winT0, true) + "</text>");
      out.push('<text class="mk-hist-axis mk-hist-axis-x mk-hist-axis-mid" x="' + ((L + (W - R)) / 2).toFixed(1) +
        '" y="' + (H - 8) + '" text-anchor="middle">' + histStampMs(midT, true) + "</text>");
      out.push('<text class="mk-hist-axis mk-hist-axis-x" x="' + (W - R) + '" y="' + (H - 8) +
        '" text-anchor="end">' + histStampMs(winT1, true) + "</text>");
    }
    if (rows.length === 1) {
      // 单点：只画这个采样点。不拉横贯全宽的参考线——没有文字解释时，
      // 那条线会被读成「价格一直是这个数」。
      out.push('<circle class="mk-hist-dot" cx="' + pos[0].x.toFixed(1) +
        '" cy="' + pos[0].y.toFixed(1) + '" r="3"></circle>');
    } else {
      areaPaths.forEach(function (d) {
        out.push('<path class="mk-hist-area" d="' + d + '"></path>');
      });
      linePaths.forEach(function (d) {
        out.push('<path class="mk-hist-line" d="' + d + '"></path>');
      });
      // 孤立采样（前后都断档）也留一个点，不装作那里没有数据
      lonely.forEach(function (pt) {
        out.push('<circle class="mk-hist-dot mk-hist-dot-lone" cx="' + pt.x.toFixed(1) +
          '" cy="' + pt.y.toFixed(1) + '" r="2"></circle>');
      });
      out.push('<circle class="mk-hist-dot" cx="' + pos[pos.length - 1].x.toFixed(1) +
        '" cy="' + pos[pos.length - 1].y.toFixed(1) + '" r="3"></circle>');
    }
    // 悬浮层
    out.push('<line class="mk-hist-cross" x1="0" y1="' + T + '" x2="0" y2="' + (H - B) +
      '" style="display:none"></line>');
    out.push('<circle class="mk-hist-focus" cx="0" cy="0" r="3.5" style="display:none"></circle>');
    out.push('<rect class="mk-hist-hit" x="' + L + '" y="' + T + '" width="' + (W - L - R) +
      '" height="' + (H - T - B) + '" fill="transparent"></rect>');
    out.push("</svg>");
    wrap.innerHTML = out.join("");

    var svg = wrap.querySelector("svg");
    var cross = wrap.querySelector(".mk-hist-cross");
    var focus = wrap.querySelector(".mk-hist-focus");
    var hit = wrap.querySelector(".mk-hist-hit");
    var tip = el("div", "mk-hist-tip");
    tip.hidden = true;
    wrap.appendChild(tip);
    if (!hit) { return { rows: rows }; }

    function showAt(idx) {
      var row = rows[idx];
      var xy = pos[idx];
      cross.setAttribute("x1", xy.x.toFixed(1));
      cross.setAttribute("x2", xy.x.toFixed(1));
      focus.setAttribute("cx", xy.x.toFixed(1));
      focus.setAttribute("cy", xy.y.toFixed(1));
      cross.style.display = "";
      focus.style.display = "";
      tip.textContent = "";
      tip.appendChild(el("div", "mk-hist-tip-t", histStamp(row.t, true)));
      tip.appendChild(el("div", "mk-hist-tip-v",
        (row.l === null ? "—" : fmt(row.l) + " ₽") + " 最近低价"));
      if (row.a !== null) {
        tip.appendChild(el("div", "mk-hist-tip-a", fmt(row.a) + " ₽ 24h 均价"));
      }
      tip.hidden = false;
      var pct = Math.max(8, Math.min(78, xy.x / W * 100));
      tip.style.left = pct + "%";
      tip.style.top = (xy.y / H * 100) + "%";
    }

    hit.addEventListener("mousemove", function (ev) {
      var rect = svg.getBoundingClientRect();
      if (!rect.width) { return; }
      var x = (ev.clientX - rect.left) / rect.width * W;
      var best = 0;
      var bestGap = Infinity;
      for (var k = 0; k < pos.length; k++) {
        var gap = Math.abs(pos[k].x - x);
        if (gap < bestGap) { bestGap = gap; best = k; }
      }
      showAt(best);
    });
    hit.addEventListener("mouseleave", function () {
      cross.style.display = "none";
      focus.style.display = "none";
      tip.hidden = true;
    });
    return { rows: rows };
  }

  function renderHist72() {
    if (!ui.hist72) { return; }
    ui.hist72.textContent = "";
    var head = el("div", "mk-hist-head");
    head.appendChild(el("div", "mk-block-title mk-hist-title", "价格走势"));
    var ranges = el("div", "mk-hist-ranges");
    HIST_RANGES.forEach(function (r) {
      var b = el("button", "mk-hist-range", r.label);
      b.type = "button";
      b.setAttribute("aria-pressed", String(histState.days === r.days));
      b.addEventListener("click", function () {
        if (histState.days === r.days) { return; }
        histState.days = r.days;
        ensureHistory();
      });
      ranges.appendChild(b);
    });
    head.appendChild(ranges);
    ui.hist72.appendChild(head);

    // R279：缓存状态条（含「获取最新数据」）。第一次打开先拉一次状态，
    // 会员且本地还没有缓存时顺手整包下载。
    if (!cacheState.loaded) {
      loadCacheStatus().then(function () {
        renderCacheBar();
        var entry = cacheModeEntry();
        if (cacheState.member && (!entry || !entry.exists)) { syncCache(); }
      });
    } else {
      renderCacheBar();
    }

    var data = histState.data;
    if (histState.phase === "loading" || histState.phase === "idle") {
      ui.hist72.appendChild(histEmptyBox("读取价格历史…", [
        "先读本机累积的云端行情快照；不额外联网、不消耗每日额度。"
      ]));
      return;
    }
    if (histState.phase === "error") {
      if (histState.error === "member-required") {
        ui.hist72.appendChild(histEmptyBox("价格历史是会员功能", [
          "免费账户可在市场大盘查看延迟 12 小时的云端行情；逐物品完整曲线需要会员。"
        ]));
        return;
      }
      ui.hist72.appendChild(histEmptyBox("历史数据读取失败", [
        "接口返回：" + (histState.error || "未知错误"),
        "曲线拿不到就空着，不拿当前价冒充历史。"
      ]));
      return;
    }
    if (!data || data.error === "no-index" || data.snapshotsUsed === 0) {
      var other = (data && data.availableModes) || null;
      var otherKeys = other ? Object.keys(other) : [];
      if (otherKeys.length) {
        // 本机其实有快照，只是不属于当前模式：说清楚，不跨模式拿数据顶上。
        ui.hist72.appendChild(histEmptyBox("当前模式还没有历史快照", [
          "本机已有：" + otherKeys.map(function (key) {
            return modeLabel(key) + " " + other[key] + " 份";
          }).join(" · ") + "。",
          "切到对应模式后这里才会出线；不拿其他模式的价格顶替。"
        ]));
        return;
      }
      if (data && data.snapshotsTotal > 0) {
        ui.hist72.appendChild(histEmptyBox("所选区间没有历史快照", [
          "共 " + data.snapshotsTotal + " 份快照，但都不在最近 " + histRangeLabel() + " 内。",
          "换一个更大的区间，或者等下一轮采集。"
        ]));
        return;
      }
      var cloudState = (data && data.cloud && data.cloud.status) || "";
      if (cloudState === "member_required") {
        ui.hist72.appendChild(histEmptyBox("云端历史是会员数据", [
          "本机还没有采集到快照。开通会员后这里会直接显示采集机上传的完整曲线，不用等本机攒样本。",
          "价格每 30 分钟更新一次，缺的时段就是没有采样，不插值。"
        ]));
        return;
      }
      if (cloudState === "offline") {
        ui.hist72.appendChild(histEmptyBox("云端历史暂时连不上", [
          "本机也还没有可用快照，所以这里画不出线。",
          "检查网络后重开这个面板即可；云端恢复后曲线会直接补齐。"
        ]));
        return;
      }
      ui.hist72.appendChild(histEmptyBox("还没有历史快照", [
        "价格每 30 分钟采集一次：采集机上传到云端，会员的客户端打开这里就能直接看到曲线。",
        "本机与云端都没有可用样本，所以这里不画线。"
      ]));
      return;
    }
    var series = (data.series && data.series[modalRow.id]) || null;
    if (!series || !series.count) {
      ui.hist72.appendChild(histEmptyBox("该物品没有历史价格", [
        "窗口内有 " + data.snapshotsUsed + " 份采样，但这个物品在每份里都没有可用价格。",
        "可能原因：上游没给 lastLowPrice / avg24hPrice，或该物品当时没有挂单。"
      ]));
      return;
    }

    // 时间轴按所选区间铺满：24h / 7 天 / 30 天 是三条不同宽度的轴，
    // 数据不够就有空白，空白处不连线
    var win = histWindow(data.windowStart, histState.days, series.points);
    var wrap = el("div", "mk-hist-wrap");
    ui.hist72.appendChild(wrap);
    drawHistoryChart(wrap, series, win);

    // 图表下面的解释性文案一律不显示（用户 2026-11-10 明确要求去掉）：
    // 区间 / 样本数 / 有数据时长 / 断档说明 / 口径说明全部不再渲染。
    // 只保留「数据被截断」这一条——那是数据缺失的边界，不说就会读成「没有更早数据」。
    if (data.truncated) {
      ui.hist72.appendChild(el("p", "mk-note",
        "区间内共 " + data.collectorWindowTotal + " 份快照，这里只画最近 " +
        data.sources.collector + " 份（上限）。"));
    }
  }

  function sortBy(key) {
    if (!key) { return; }
    if (st.sortKey === key) {
      st.sortDir = -st.sortDir;
    } else {
      st.sortKey = key;
      st.sortDir = key === "name" ? 1 : -1;
    }
    savePrefs();
    applyFilters();
  }

  // ---------------------------------------------------------------- 挂载 / 打开
  function mount() {
    if (root) { return; }
    root = document.getElementById("market-list-pane");
    if (!root) { return; }
    api = window.GWMarketData || null;
    if (!api) {
      root.innerHTML = '<div class="mk-app"><div class="mk-empty"><h3>市场数据接口不可用</h3>' +
        '<p>请确认 app.js 已加载；本视图不自行请求任何外部接口。</p></div></div>';
      return;
    }
    st.scopeMode = function () {
      var s = api.scope ? api.scope() : null;
      return (s && s.mode) || "regular";
    };
    readPrefs();
    preloadTraderIcons();
    buildSkeleton();
    startMetaTick();
    refreshMeta();   // 骨架刚建好就先画一次徽标，别等市场表格首次渲染
    load();
    if (api.onModeChange) {
      modeUnsub = api.onModeChange(function () {
        histToken++; histPending = {};
        // 任务数据是按模式分文件的：模式一变就作废已建的反查索引。
        resetQuestIndex();
        if (!loaded || loading) { return; }
        // 模式变了：先判断快照是否匹配；不匹配则换成模式门，匹配则恢复列表。
        if (gateModeMismatch()) { return; }
        applyFilters();
      });
    }
  }

  function open() {
    if (!root) { return; }
    if (!loaded && !loading) { load(); }
    if (ui.search) { ui.host.scrollTop = 0; }
  }

  /**
   * app.js 每次读取当前模式行情（启动 / 模式切换 / 手动刷新）后回调：
   * 按当前模式重建行，市场自动跟随游戏模式，不需要用户刷新页面。
   */
  function onPricesUpdated() {
    // R269：截止徽标 + 「获取最新数据」按钮已经搬到二级工具条（全站可见），
    // 不能再只在市场表格渲染时更新——否则人在配装 / 配枪 / 子弹页按按钮，
    // 数据其实拉到了但徽标不动，看起来像「没反应」。
    refreshMeta();
    if (!root || !api || !loaded || loading) { return; }
    buildRows();
    applyFilters();
  }

  /** 只刷新二级工具条上的市场元信息（截止徽标 / 按钮状态），不碰市场表格。
   *  与视图、与市场是否已加载都无关，任何页面调用都安全。 */
  function refreshMeta() {
    try {
      updateCutoff();
    } catch (e) { /* 尚未挂载或元素缺失时忽略 */ }
  }

  /** 徽标里的「N 分钟前」会随时间变旧，而它已经不在市场页里了，不能等市场重绘。
   *  这里给徽标自己一条 30 秒的轻量心跳（只改文本；页面不可见时跳过），
   *  顺带问一次 app.js「行情是不是该补拉了」（app.js 那边不新增定时器）。 */
  var metaTick = null;
  function startMetaTick() {
    if (metaTick) { return; }
    metaTick = setInterval(function () {
      if (document.hidden) { return; }
      refreshMeta();
      if (api && typeof api.maybeSyncPrices === "function") {
        try { api.maybeSyncPrices(); } catch (e) { /* 忽略 */ }
      }
    }, 30000);
  }

  /** R265：由二级工具条的全局价格口径调用，设置三档基准（最新/24h/7日）。
   *  「每格 / 每公斤」仍是市场页本地附加项，不在此列。 */
  function setBasis(key) {
    var ok = false;
    for (var i = 0; i < PRICE_MODES.length; i++) {
      if (PRICE_MODES[i].key === key) { ok = true; break; }
    }
    if (!ok || st.priceMode === key) { return; }
    st.priceMode = key;
    savePrefs();
    applyFilters();
  }

  window.GWMarket = { mount: mount, open: open, pricesUpdated: onPricesUpdated,
                      setBasis: setBasis, refreshMeta: refreshMeta };

  // R279：登录 / 会员态变化后立刻探一次缓存——会员且本地没有就整包下载。
  // 「登录后一次性把云端数据下载到本地」就是这一条，不用等用户去开价格详情。
  window.addEventListener("eftmap:member-changed", function () {
    loadCacheStatus().then(function () {
      renderCacheBar();
      if (!cacheState.member) {
        // 清掉当前详情页仍驻留内存的会员历史曲线与在途响应。
        histState.token += 1;
        histState.phase = "idle";
        histState.key = "";
        histState.data = null;
        histState.error = null;
        renderHist72();
      }
      var entry = cacheModeEntry();
      if (cacheState.member && (!entry || !entry.exists)) { syncCache(); }
    });
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mount);
  } else {
    mount();
  }
})();
