/* EFT 互动地图 · 前端（原生 JS，零依赖）
 *
 * 设计要点：
 * - 底图 SVG 整体注入 <svg id="map-svg">，与其共享同一套用户坐标系（viewBox）。
 *   上游每张图把每一层放在一个**顶层** <g id="…">（Ground_Level / Second_Floor / Basement…），
 *   层内元素是它的子组，所以「换层」只需切换顶层组的 display，不必碰嵌套结构。
 * - 标注点的世界坐标 (x, z) 经 data/maps.json 里的 worldToSvg 系数直接落到用户坐标，
 *   与底图天然对齐，无需任何校准；朝向箭头也要过同一套仿射（各图系数符号不一致）。
 * - 缩放走 SVG viewBox（相机），不用 #viewport 的 CSS transform：
 *   后者会把整张 SVG 栅格化再放大位图，越放越糊。标注点用 1/z 反向补偿保持屏幕大小恒定。
 * - 多楼层图：楼层波段（y 区间 + 可选 x/z 矩形）在上游 maps.json 里就有，
 *   由它推出「截图的 y 落在哪一层」，从而自动切层；标记也按所在层过滤。
 */

(function () {
  "use strict";

  var SVG_NS = "http://www.w3.org/2000/svg";
  var LS_MAP = "eftmap.map";
  var LS_LAYERS = "eftmap.layers";
  var LS_FOLLOW = "eftmap.follow";          // 兼容旧键名：现在存的是「点位自动居中」的本地偏好
  var LS_FLOOR_AUTO = "eftmap.floor.auto";
  var LS_FLOOR_FILTER = "eftmap.floor.filter";
  var LS_ZOOM = "eftmap.zoom";              // 最近一次手动缩放比例（自动缩放沿用它的值）
  var LS_PINS = "eftmap.pins";              // 钉选的「类型」集合（与服务端 ui.pins 同构）
  var LS_ROUTE = "eftmap.route";            // 导航路线的途经点
  var LS_ROUTE_PLAYER = "eftmap.route.fromPlayer";
  var LS_ICON_SCALE = "eftmap.icon.scale";  // 地图图标的整体缩放（与服务端 ui.icon_scale 同构）
  var PIN_MAX = 300;                        // 钉选上限（与 tools/config.py 的 PIN_MAX 对齐）
  var ROUTE_MAX = 60;                       // 途经点上限
  var ZOOM_MIN = 0.5;
  var ZOOM_MAX = 20;
  // 图标整体缩放的滑条区间（0.5×～3×；4K 屏上图标偏小，往右拖即可整体放大）
  var ICON_SCALE_MIN = 0.5;
  var ICON_SCALE_MAX = 3;
  var DEFAULT_AUTO_ZOOM = 4;                // 自动缩放首次使用的倍数
  // 底图矩形最多向外扩这么多比例，用来容纳紧贴边缘的标注点
  var PAD_RATIO = 0.12;

  /**
   * 游戏日志里的地图 id → 本项目 data/maps.json 的 key（大小写不敏感）。
   * id 来自 `scene preset path:maps/<id>_preset.bundle`（见 tools/eftlog.py）。
   * 没列出的 id（laboratory / Labyrinth / Icebreaker 等）本工具没有收录底图，
   * 识别得到但不会切图，只在侧栏提示。
   */
  var MAP_ID_ALIASES = {
    bigmap: "customs",
    customs: "customs",
    woods: "woods",
    shoreline: "shoreline",
    interchange: "interchange",
    shopping_mall: "interchange",
    rezervbase: "reserve",
    reserve: "reserve",
    lighthouse: "lighthouse",
    tarkovstreets: "streets-of-tarkov",
    city: "streets-of-tarkov",
    factory4_day: "factory",
    factory4_night: "factory",
    factory: "factory",
    sandbox_high: "ground-zero",
    sandbox: "ground-zero",
    terminal: "terminal"
  };

  /** 战局阶段 → 中文（顺序即游戏里的发生顺序） */
  var RAID_PHASE_TEXT = {
    matching: "开始匹配",
    map: "识别到地图",
    loading: "开始加载战局",
    start: "战局开始",
    end: "战局结束"
  };

  /** 事件流里显示的任务动作 */
  var QUEST_ACTION_TEXT = { started: "接取任务", completed: "完成任务", failed: "任务失败" };

  /** 战局阶段 → 对应哪个提示音（各子开关在启动器里单独控制） */
  var PHASE_SOUND = { matching: "matching", loading: "location_loading", start: "raid_start" };

  /** 没选自定义音频时用的默认提示音：每项若干 (频率 Hz, 起始秒, 时长秒) 的音 */
  var DEFAULT_TONES = {
    matching: [[620, 0, 0.11], [830, 0.12, 0.11]],
    location_loading: [[430, 0, 0.16], [430, 0.19, 0.16]],
    raid_start: [[523, 0, 0.13], [784, 0.14, 0.22]]
  };
  var QUEST_LOG_MAX = 40;                   // 事件流面板只留最近这么多条

  /** 图层开关表：ui 上的每一项 = 一种 kind + 一个筛选条件 */
  function hasCat(cat) {
    return function (item) { return (item.categories || []).indexOf(cat) !== -1; };
  }
  function isFaction(faction) {
    return function (item) { return (item.faction || "shared") === faction; };
  }

  // 物资容器类别：key 与 tools/fetch_data.py 的 CONTAINER_GROUPS 一一对应（前端只负责显示）
  var CONTAINER_GROUPS = [
    { key: "safe", label: "保险箱" },
    { key: "jacket", label: "夹克衫" },
    { key: "pcblock", label: "机箱" },
    { key: "scavbody", label: "Scav尸体" },
    { key: "drawer", label: "抽屉" },
    { key: "duffle", label: "旅行包" },
    { key: "cache", label: "彩蛋点" },
    { key: "med", label: "医疗物资" },
    { key: "supply", label: "物资箱" },
    { key: "suitcase", label: "塑料手提箱" },
    { key: "toolbox", label: "工具箱" },
    { key: "register", label: "收银机" },
    { key: "grenade", label: "手雷箱" },
    { key: "weapon", label: "武器箱" }
  ];

  var CONTAINER_FALLBACK = { key: "misc", label: "其他容器" };

  function containerLabel(key) {
    for (var i = 0; i < CONTAINER_GROUPS.length; i++) {
      if (CONTAINER_GROUPS[i].key === (key || CONTAINER_FALLBACK.key)) { return CONTAINER_GROUPS[i].label; }
    }
    return CONTAINER_FALLBACK.label;
  }

  /** 筛选出某一类别的容器（每个容器只属于一个类别，所以各开关不会重复计数） */
  function isContainer(group) {
    return function (item) { return (item.group || CONTAINER_FALLBACK.key) === group; };
  }

  // 高级资源点的子类（2026-10-19 第七轮）：原来「高级资源点」是一个大开关，一开几百个点糊在一起。
  // 现在按物品名拆成 8 类分别开关；一个刷点可能同时命中多类（渲染时按「启用的子类并集」各点只画一次）。
  // 判定顺序有讲究：「钥匙卡」必须排在「钥匙」前面，否则钥匙卡会被「钥匙」那条正则先吃掉。
  var VALUABLE_CATS = [
    { key: "btc", label: "比特币", icon: "valuable_btc", match: /比特币|BTC/i },
    { key: "moonshine", label: "私酒", icon: "valuable_bottle", match: /私酒|酒/ },
    { key: "gpu", label: "显卡", icon: "valuable_gpu", match: /显卡|显示卡/ },
    { key: "keycard", label: "钥匙卡类", icon: "valuable_keycard", match: /钥匙卡/ },
    { key: "key", label: "钥匙类", icon: "valuable_key", match: /钥匙/ },
    { key: "ledx", label: "LEDX", icon: "valuable_med", match: /LEDX|透照/i },
    { key: "defib", label: "除颤器", icon: "valuable_defib", match: /除颤/ },
    { key: "other", label: "其他高价值", icon: "valuable", match: null }
  ];

  /** 子类开关的 state.layers 键名 */
  function valuableCatKey(cat) { return "valuable_" + cat; }

  /** 一个高级资源点属于哪几类：按物品名判定；一件都对不上的（如蓝色文件夹）归「其他高价值」 */
  function valuableCatsOf(item) {
    var names = (item && item.items) || [];
    var out = [], unmatched = false;
    names.forEach(function (n) {
      for (var i = 0; i < VALUABLE_CATS.length; i++) {
        var cat = VALUABLE_CATS[i];
        if (!cat.match) { continue; }
        if (cat.match.test(n)) {
          if (out.indexOf(cat.key) === -1) { out.push(cat.key); }
          return;
        }
      }
      unmatched = true;
    });
    if (unmatched) { out.push("other"); }
    return out;
  }

  /** 生成某个子类开关的筛选条件（供 LAYER_SPEC 的 where 用） */
  function isValuableCat(cat) {
    return function (item) { return valuableCatsOf(item).indexOf(cat) !== -1; };
  }

  // 分组与命名对齐参考站的图例（物资 / 出生点 / 其他…），每项右侧显示当前地图的计数
  var LAYER_SPEC = [
    { group: "撤离点 / 转移点", items: [
      { key: "extract_shared", label: "共用撤离点", kind: "extracts", where: isFaction("shared"), dot: "dot-extract-shared", badge: "shared" },
      { key: "extract_pmc", label: "PMC 撤离点", kind: "extracts", where: isFaction("pmc"), dot: "dot-extract-pmc", badge: "pmc" },
      { key: "extract_scav", label: "Scav 撤离点", kind: "extracts", where: isFaction("scav"), dot: "dot-extract-scav", badge: "scav" },
      { key: "transits", label: "转移点（去别的图）", kind: "transits", dot: "dot-transit", badge: "transit" }
    ] },
    { group: "物资", items: [
      // 高级资源点：只在固定刷点上「有概率」刷出的高价值物品（BTC / 显卡 / 私酒 / LEDX / 除颤器 / 钥匙卡…）。
      // 第一行是「总开关」（master，一键全开 / 全关），下面按物品分成 8 个子类各自开关。
      { key: "valuables", label: "高级资源点（全部）", kind: "valuables", master: true, dot: "dot-valuable" }
    ].concat(VALUABLE_CATS.map(function (cat) {
      return { key: valuableCatKey(cat.key), label: cat.label, kind: "valuables", sub: true,
               icon: cat.icon, where: isValuableCat(cat.key), dot: "dot-valuable" };
    })).concat(CONTAINER_GROUPS.map(function (c) {
      return { key: "container_" + c.key, label: c.label, kind: "containers",
               where: isContainer(c.key), dot: "dot-loot-" + c.key };
    })).concat([
      // 上游新 slug 的兜底开关：默认开启且一定会被渲染，但侧栏只在真有这类容器时才显示这一行
      { key: "container_" + CONTAINER_FALLBACK.key, label: CONTAINER_FALLBACK.label,
        kind: "containers", where: isContainer(CONTAINER_FALLBACK.key),
        dot: "dot-loot-" + CONTAINER_FALLBACK.key },
      { key: "loose", label: "散落物资（地面物品）", kind: "loose", dot: "dot-loot-loose" }
    ]) },
    { group: "出生点", items: [
      { key: "spawn_player", label: "玩家出生点", kind: "spawns", where: hasCat("player"), dot: "dot-spawn-player", icon: "spawn" },
      { key: "spawn_scav", label: "Scav 出生点", kind: "spawns", where: hasCat("bot"), dot: "dot-spawn-scav", icon: "spawn" },
      { key: "spawn_pmc", label: "AI PMC 出生点", kind: "spawns", where: hasCat("botpmc"), dot: "dot-spawn-pmc", icon: "spawn" },
      { key: "spawn_sniper", label: "狙击手", kind: "spawns", where: hasCat("sniper"), dot: "dot-spawn-sniper", icon: "sniper" },
      { key: "bosses", label: "Boss 刷新点", kind: "bosses", dot: "dot-boss", icon: "boss" }
    ] },
    { group: "钥匙与门", items: [
      { key: "locks_door", label: "上锁的门", kind: "locks", where: function (i) { return (i.type || "door") !== "trunk"; }, dot: "dot-lock", icon: "lock" },
      { key: "locks_trunk", label: "汽车后备箱", kind: "locks", where: function (i) { return i.type === "trunk"; }, dot: "dot-lock", icon: "lock" }
    ] },
    { group: "危险区域", items: [
      { key: "hazards", label: "雷区 / 危险区", kind: "hazards", dot: "dot-hazard" },
      { key: "artillery", label: "炮击区（地图边界外）", kind: "artillery", dot: "dot-artillery" }
    ] },
    { group: "其他", items: [
      { key: "stationary", label: "固定武器", kind: "stationary", dot: "dot-stationary" },
      { key: "btr", label: "BTR 停靠点", kind: "btr", dot: "dot-btr", icon: "btr" },
      { key: "labels", label: "地名标注", kind: "labels", dot: "dot-label" }
    ] }
  ];

  /** 各开关的默认状态（只列非默认关闭的；其余一律默认关） */
  // 默认开启的开关。物资容器在 defaultLayers() 里单独全开，不在这个表里逐个列。
  // 高级资源点默认只开「比特币 / 私酒 / 显卡 / 钥匙卡类」这四个最值钱的子类（钥匙类有 48 种、点位密，默认关，免得一开糊一片）。
  var DEFAULT_ON = {
    extract_shared: true, extract_pmc: true, extract_scav: true, transits: true,
    valuable_btc: true, valuable_moonshine: true, valuable_gpu: true, valuable_keycard: true,
    hazards: true, bosses: true, labels: true, stationary: true
  };

  function defaultLayers() {
    var out = {};
    LAYER_SPEC.forEach(function (group) {
      group.items.forEach(function (item) { out[item.key] = !!DEFAULT_ON[item.key]; });
    });
    // 高级资源点总开关：状态由 7 个子类推出来（全开才算开），这里按子类先算一次
    out.valuables = VALUABLE_CATS.every(function (c) { return out[valuableCatKey(c.key)]; });
    // 物资容器按参考站口径默认全部开启：否则打开地图看不到物资点（曾因此被当成「物资点丢了」）
    CONTAINER_GROUPS.forEach(function (c) { out["container_" + c.key] = true; });
    out["container_" + CONTAINER_FALLBACK.key] = true;
    return out;
  }

  /** 数据里是否真有没归类的容器（决定侧栏要不要显示「其他容器」这一行） */
  function hasUnknownContainers() {
    return (state.maps || []).some(function (map) {
      return ((map.layers && map.layers.containers) || []).some(function (c) {
        return (c.group || CONTAINER_FALLBACK.key) === CONTAINER_FALLBACK.key;
      });
    });
  }

  /** kind → 该 kind 的所有开关项（搜索聚焦时要用） */
  function specItemsOfKind(kind) {
    var out = [];
    LAYER_SPEC.forEach(function (group) {
      group.items.forEach(function (item) { if (item.kind === kind) { out.push(item); } });
    });
    return out;
  }

  // ---------------------------------------------------------------- 楼层
  // 楼层全部来自 data/maps.json 的 floors 字段（构建期由 tools/floors.py 算好），
  // 前端只做三件事：按高度排好列表、切顶层组显隐、按 y 判定标记属于哪一层。

  /** 选中地图时把楼层信息摊平成好用的形态：可选楼层（由下到上）+ id → 中文名 */
  function buildFloorMeta(map) {
    var floors = map.floors || {};
    var rootId = (floors.root && floors.root.svgLayer) || map.svgLayer;
    var entries = floors.selectable;
    if (!entries || !entries.length) {
      // 兜底：旧数据没有 selectable，就用主层 + 上游登记的层
      entries = [{ svgLayer: rootId, label: (floors.root && floors.root.label) || "主层" }]
        .concat(floors.switchable || []);
    }
    var ids = [];
    var labels = {};
    entries.forEach(function (entry) {
      if (!entry.svgLayer || labels[entry.svgLayer]) { return; }
      ids.push(entry.svgLayer);
      labels[entry.svgLayer] = entry.label || entry.svgLayer;
    });
    return { ids: ids, labels: labels, rootId: rootId };
  }

  function floorLabel(id) {
    return (state.floorLabels && state.floorLabels[id]) || id || "主层";
  }

  /** 该图所有可显示的楼层顶层组（由下到上） */
  function mapFloorTops(map) {
    return (map && state.floorMeta && state.floorMeta.ids) || [];
  }

  /** 该图默认显示的楼层（取上游 default，取不到就回主层） */
  function mapDefaultFloors(map) {
    var tops = mapFloorTops(map);
    var def = ((map.floors && map.floors.default) || []).filter(function (id) {
      return tops.indexOf(id) !== -1;
    });
    if (def.length) { return def; }
    var rootId = state.floorMeta ? state.floorMeta.rootId : null;
    return rootId ? [rootId] : tops.slice(0, 1);
  }

  /** (x, y, z) 落在哪个楼层波段；命中不了返回 null（= 主层） */
  function bandOfPosition(map, pos) {
    if (pos.y === null || pos.y === undefined || pos.y === "") { return null; }
    var y = Number(pos.y);
    if (isNaN(y)) { return null; }
    var bands = (map.floors && map.floors.bands) || [];
    for (var i = 0; i < bands.length; i++) {
      var band = bands[i];
      if (!(band.minY <= y && y < band.maxY)) { continue; }
      var areas = band.areas || [];
      if (!areas.length) { return band; }
      if (pos.x === null || pos.z === null || pos.x === undefined || pos.z === undefined) { continue; }
      for (var j = 0; j < areas.length; j++) {
        var a = areas[j];
        if (a[0] <= pos.x && pos.x <= a[2] && a[1] <= pos.z && pos.z <= a[3]) { return band; }
      }
    }
    return null;
  }

  /** 某个点属于哪一层：命中波段用它的 svgLayer，否则算主层 */
  function floorOfPosition(map, pos) {
    var band = bandOfPosition(map, pos);
    return (band && band.svgLayer) ? band.svgLayer : (map.svgLayer || null);
  }

  var state = {
    maps: [],            // data/maps.json 的地图数组
    mapsLoaded: false,   // 地图数组是否已就绪（日志事件可能先于它到达）
    meta: null,          // data/meta.json
    map: null,           // 当前地图条目
    layers: defaultLayers(),
    floorAuto: true,     // 跟随截图自动切层
    floorFilter: true,   // 按楼层过滤标记
    floorSet: [],        // 当前显示哪些楼层（底图顶层组 id 的集合）
    floorNote: "",
    floorMeta: null,     // 当前图的楼层信息：{ids: [由下到上], labels, rootId}
    floorLabels: {},     // 楼层 id → 中文名
    // 相机：z 是相对「整图适配」的放大倍数，cx/cy 是屏幕中心所在的地图坐标。
    // 缩放走 viewBox 而不是 CSS transform —— 后者会把 SVG 栅格化再放大，越放越糊。
    z: 1, cx: 0, cy: 0,
    baseVb: [0, 0, 1, 1],// z=1 时的 viewBox（底图矩形 + 外边距）
    fit: 1,              // z=1 时每用户单位对应多少屏幕像素
    vb: [0, 0, 1, 1],    // 当前实际使用的 viewBox（随相机变化）
    svgCache: {},        // 每张图的 SVG 文本缓存
    markerScaleNodes: [],// 需要随缩放反向补偿的节点
    selected: null,
    pins: [],            // 钉选的「类型」：{kind, name} —— 命中的标记在地图上高亮描边
    route: [],           // 导航路线途经点：{kind, name, x, z, y?}
    routeFromPlayer: false,   // 路线是否从实时定位当前位置出发
    searchCache: null,   // {mapKey, entries} 当前地图的搜索索引缓存
    player: null,        // 实时定位：最新解析到的玩家位置 {x, y, z, yaw, name, mtime}
    positionInfo: { available: false, reason: null },
    playerNode: null,    // 玩家标记节点（renderOverlay 清空时会一并丢掉）
    cfg: null,           // 启动器里的运行期配置（/api/config）
    autoZoom: false,     // 定位自动缩放：拿到位置后按「最近一次手动比例」缩放
    autoCenter: true,    // 点位自动居中：拿到位置后把地图平移到该点
    iconScale: 1,        // 地图图标的整体缩放（滑条调节；1 = 原始大小）
    cfgAutoCenter: null, // 服务端配置里的 auto_center 上一次的值（只在其真的变化时才覆盖本地视角）
    logs: null,          // 日志监控状态 {available, reason, session, gameDir, logDir}
    raid: null,          // 最近一次战局事件 {phase, mapId, mapKey, raidId, ts}
    raidNote: "",        // 战局相关提示（如「识别到地图但本工具没收录」）
    quests: [],          // 任务事件流（最近 QUEST_LOG_MAX 条，新的在前）
    questCounts: { started: 0, completed: 0 },   // 本局计数
    sound: null,         // 声音提示配置（含 enabled 与三个子开关）
    shot: null,          // 自动截图状态 {enabled, intervalMs, key, sent, available, reason}
    clean: null,         // 自动删除截图状态 {enabled, since, deleted, available, reason}
    soundUnlocked: false,
    soundCtx: null,
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
    el.centerBtn = $("follow");
    el.error = $("error");
    el.svg = $("map-svg");
    el.viewport = $("viewport");
    // #stage 不被 transform 影响，尺寸/坐标换算一律以它为准（#viewport 会被平移缩放改变 rect）
    el.stage = $("stage");
    el.layerToggles = $("layer-toggles");
    el.floorBlock = $("floor-block");
    el.floorList = $("floor-list");
    el.floorAuto = $("floor-auto");
    el.floorFilter = $("floor-filter");
    el.floorNote = $("floor-note");
    el.raidBlock = $("raid-block");
    el.menuRaid = $("menu-raid");
    el.raidStatus = $("raid-status");
    el.raidNote = $("raid-note");
    el.questLog = $("quest-log");
    el.questDone = $("quest-done");
    el.questStarted = $("quest-started");
    el.shotStatus = $("shot-status");
    el.cleanStatus = $("clean-status");
    el.menuNav = $("menu-nav");
    el.navBlock = $("nav-block");
    el.routeList = $("route-list");
    el.routeSummary = $("route-summary");
    el.routeClear = $("route-clear");
    el.routeReverse = $("route-reverse");
    el.routeFromPlayerBox = $("route-from-player");
    el.routeAddCurrent = $("detail-add-route");
    el.iconScale = $("icon-scale");
    el.iconScaleValue = $("icon-scale-value");

    restorePrefs();
    bindUI();
    bindMenu();
    bindRouteUI();
    initRealtime();
    initConfig();
    initLogs();
    // 浏览器要求先有用户手势才能出声，首次点击/按键时解锁音频上下文
    document.addEventListener("click", unlockAudio);
    document.addEventListener("keydown", unlockAudio);

    Promise.all([
      loadJSON("data/maps.json"),
      loadJSON("data/meta.json").catch(function () { return null; })
    ]).then(function (results) {
      var data = results[0];
      state.meta = results[1];
      state.maps = data.maps || [];
      if (!state.maps.length) { throw new Error("data/maps.json 里没有任何地图"); }
      state.mapsLoaded = true;
      renderMetaLine();
      renderMapList();
      renderLayerToggles();    // 数据到位后才能判断要不要显示「其他容器」这一行
      onMapsLoaded();          // 日志事件可能比地图数据先到，这里复核一次
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
      " · " + (counts.maps || 0) + " 张图 / " + (counts.extracts || 0) + " 个撤离点 / " +
      (counts.containers || 0) + " 个物资点 / " + (counts.bosses || 0) + " 个 Boss 点";
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
      count.textContent = (map.layers.extracts || []).length + " 撤离 · " +
        ((map.layers.containers || []).length + (map.layers.loose || []).length) + " 物资";
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

  /** 某个图例项在当前地图上的计数：只看地图，不看楼层过滤（数字要稳，别随切层跳） */
  function countOfSpec(spec) {
    var map = state.map;
    if (!map) { return 0; }
    if (spec.kind === "labels") { return (map.labels || []).length; }
    return (map.layers[spec.kind] || []).reduce(function (n, it) {
      return n + ((!spec.where || spec.where(it)) ? 1 : 0);
    }, 0);
  }

  /** 按 LAYER_SPEC 生成图例：分组标题 + 彩色小图标 + 名称 + 右侧计数 */
  function renderLayerToggles() {
    el.layerToggles.innerHTML = "";
    LAYER_SPEC.forEach(function (group) {
      var heading = document.createElement("div");
      heading.className = "toggle-group";
      heading.textContent = group.group;
      el.layerToggles.appendChild(heading);
      group.items.forEach(function (item) {
        if (item.key === "container_" + CONTAINER_FALLBACK.key && !hasUnknownContainers()) { return; }
        var label = document.createElement("label");
        // 高级资源点的 7 个子类推到总开关下面（缩进），一眼看出从属关系
        label.className = "toggle legend-item" + (item.sub ? " legend-sub" : "");
        label.title = item.label;
        var box = document.createElement("input");
        box.type = "checkbox";
        box.dataset.layer = item.key;
        box.checked = !!state.layers[item.key];
        // 图标统一由 legendIcon 决定：物资 / 高级资源点是图标、撤离点是徽章、其余是色点
        var dot = legendIcon(item);
        var name = document.createElement("span");
        name.className = "legend-name";
        name.textContent = item.label;
        var count = document.createElement("span");
        count.className = "legend-count";
        count.textContent = state.map ? String(countOfSpec(item)) : "—";
        label.appendChild(box);
        label.appendChild(dot);
        label.appendChild(name);
        label.appendChild(count);
        el.layerToggles.appendChild(label);
      });
    });
    syncLegendState();
  }

  /** 高级资源点总开关的勾选状态：子类全开 = 勾上；部分开 = 半勾；全关 = 空 */
  function syncValuableMaster() {
    var allOn = true, anyOn = false;
    VALUABLE_CATS.forEach(function (c) {
      var on = !!state.layers[valuableCatKey(c.key)];
      allOn = allOn && on;
      anyOn = anyOn || on;
    });
    state.layers.valuables = allOn;
    var box = el.layerToggles.querySelector('input[data-layer="valuables"]');
    if (box) { box.checked = allOn; box.indeterminate = anyOn && !allOn; }
  }

  /** 未勾选的图例行压暗，让人一眼看出哪些图层关着 */
  function syncLegendState() {
    syncValuableMaster();
    var rows = el.layerToggles.querySelectorAll(".legend-item");
    for (var i = 0; i < rows.length; i++) {
      var box = rows[i].querySelector("input");
      // 半勾（总开关部分子类开着）也算「开」，整行不压暗
      var on = box ? (box.checked || box.indeterminate) : false;
      rows[i].dataset.on = on ? "true" : "false";
    }
  }

  /** 恢复本地偏好：图层开关、楼层开关、点位自动居中（服务端配置到达后会再覆盖一次） */
  function restorePrefs() {
    var saved = null;
    try { saved = JSON.parse(localStorage.getItem(LS_LAYERS) || "null"); }
    catch (e) { /* 损坏的本地存储忽略即可 */ }
    state.layers = mergeLayers(state.layers, saved);
    renderLayerToggles();

    state.floorAuto = localStorage.getItem(LS_FLOOR_AUTO) !== "0";
    state.floorFilter = localStorage.getItem(LS_FLOOR_FILTER) !== "0";
    el.floorAuto.checked = state.floorAuto;
    el.floorFilter.checked = state.floorFilter;

    state.autoCenter = localStorage.getItem(LS_FOLLOW) !== "0";
    syncCenterButton();

    // 图标整体缩放：本地兜底恢复（服务端配置到达后再覆盖一次），这里不写回，免得多发一次请求
    var iconScaleSaved = parseFloat(localStorage.getItem(LS_ICON_SCALE));
    setIconScale(isFinite(iconScaleSaved) ? iconScaleSaved : 1, false);

    // 钉选与导航路线：本地兜底恢复，服务端配置到达后再合并一次
    var pins = null, route = null;
    try { pins = JSON.parse(localStorage.getItem(LS_PINS) || "null"); } catch (e) { /* 忽略 */ }
    setPins(pins);
    try { route = JSON.parse(localStorage.getItem(LS_ROUTE) || "null"); } catch (e) { /* 忽略 */ }
    if (Array.isArray(route)) {
      state.route = route.filter(function (p) { return p && p.x !== undefined && p.z !== undefined; }).slice(-ROUTE_MAX);
    }
    state.routeFromPlayer = localStorage.getItem(LS_ROUTE_PLAYER) === "1";
    renderRoutePanel();
  }

  // ---------------------------------------------------------------- 界面偏好写回
  /** 当前界面偏好快照（字段与 config.py 里的 ui 块一一对应） */
  function uiPatch() {
    return {
      layers: state.layers,
      floor_auto: !!state.floorAuto,
      floor_filter: !!state.floorFilter,
      pins: state.pins,
      icon_scale: state.iconScale
    };
  }

  /** 图标整体缩放系数（只作用于标记/路线编号/玩家标记；地名不乘它，见 renderLabels） */
  function iconScale() { return state.iconScale || 1; }

  /**
   * 应用地图图标整体缩放：滑条位置、百分比标签与已画在底图上的标记一起更新。
   * 只乘进 `updateCounterScale()` 的补偿系数，**不给 SVG 元素添 CSS transform/animation**
   * ——那会让整张 svg 被栅格化，放大就糊（见项目铁律）。
   */
  function setIconScale(value, persist) {
    var number = Number(value);
    var v = Math.max(ICON_SCALE_MIN, Math.min(ICON_SCALE_MAX, isFinite(number) ? number : 1));
    state.iconScale = v;
    if (el.iconScale) { el.iconScale.value = String(v); }
    if (el.iconScaleValue) { el.iconScaleValue.textContent = Math.round(v * 100) + "%"; }
    updateCounterScale();
    if (!persist) { return; }
    try { localStorage.setItem(LS_ICON_SCALE, String(v)); } catch (e) { /* 隐私模式忽略 */ }
    queuePrefs({ ui: uiPatch() });
  }

  var PREF_DEBOUNCE = 400;     // 连续改动合并成一次写盘，避免勾一串开关就发一串请求
  var prefTimer = null;
  var prefPending = null;

  /** 把偏好改动排队写回配置文件；同一批里的键自动合并（失败静默，本地存储已兜底） */
  function queuePrefs(patch) {
    prefPending = prefPending || {};
    for (var key in patch) { prefPending[key] = patch[key]; }
    if (prefTimer) { clearTimeout(prefTimer); }
    prefTimer = setTimeout(flushPrefs, PREF_DEBOUNCE);
  }

  function flushPrefs() {
    prefTimer = null;
    var body = prefPending;
    prefPending = null;
    if (!body) { return; }
    fetch("api/prefs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    }).catch(function () { /* 没起本地服务时静默失败，下次仍从本地存储恢复 */ });
  }

  /** 本地图层偏好 与 服务端保存的合并：服务端只覆盖它确实给了的键 */
  function mergeLayers(current, saved) {
    var out = {}, key;
    for (key in current) { out[key] = !!current[key]; }
    if (saved) { for (key in saved) { if (key in out) { out[key] = !!saved[key]; } } }
    return out;
  }

  function sameLayers(a, b) {
    var key;
    for (key in a) { if (!!a[key] !== !!(b && b[key])) { return false; } }
    for (key in b) { if (!(key in a) && b[key]) { return false; } }
    return true;
  }

  /** 应用服务端保存的界面偏好；值没变就跳过重绘，免得每次 config 广播都闪一下 */
  function applyUiPrefs(ui) {
    if (!ui) { return; }
    if (ui.layers) {
      var merged = mergeLayers(state.layers, ui.layers);
      if (!sameLayers(state.layers, merged)) {
        state.layers = merged;
        try { localStorage.setItem(LS_LAYERS, JSON.stringify(merged)); } catch (e) { /* 忽略 */ }
        renderLayerToggles();
        renderOverlay();
      }
    }
    if (typeof ui.floor_auto === "boolean" && ui.floor_auto !== state.floorAuto) {
      state.floorAuto = ui.floor_auto;
      el.floorAuto.checked = ui.floor_auto;
      if (state.floorAuto && state.player) { maybeAutoFloor(state.player); }
      else if (!state.floorAuto) { setFloors(state.floorSet, "手动"); }
    }
    if (typeof ui.floor_filter === "boolean" && ui.floor_filter !== state.floorFilter) {
      state.floorFilter = ui.floor_filter;
      el.floorFilter.checked = ui.floor_filter;
      renderOverlay();
    }
    if (Array.isArray(ui.pins)) {
      var incoming = [];
      ui.pins.forEach(function (p) {
        if (p && p.kind && p.name) { incoming.push({ kind: String(p.kind), name: String(p.name) }); }
      });
      if (!samePins(state.pins, incoming)) {
        setPins(incoming);
        try { localStorage.setItem(LS_PINS, JSON.stringify(state.pins)); } catch (e) { /* 忽略 */ }
        renderOverlay();
        renderSearchResults();
      }
    }
    if (typeof ui.icon_scale === "number" && ui.icon_scale !== state.iconScale) {
      setIconScale(ui.icon_scale, true);
    }
  }

  // ---------------------------------------------------------------- 顶部菜单
  /** 顶部菜单栏：点按钮展开对应面板，点面板外或按 Esc 收起（互斥，一次只开一个） */
  function bindMenu() {
    var menus = [
      { btn: el.menuRaid, panel: el.raidBlock },
      { btn: el.menuNav, panel: el.navBlock }
    ].filter(function (m) { return m.btn && m.panel; });
    if (!menus.length) { return; }

    function closeAll(except) {
      menus.forEach(function (m) {
        if (m === except) { return; }
        m.panel.hidden = true;
        m.btn.setAttribute("aria-expanded", "false");
        m.btn.classList.remove("open");
      });
    }
    menus.forEach(function (m) {
      m.btn.addEventListener("click", function (ev) {
        ev.stopPropagation();
        var open = m.panel.hidden;
        closeAll(m);
        m.panel.hidden = !open;
        m.btn.setAttribute("aria-expanded", open ? "true" : "false");
        m.btn.classList.toggle("open", open);
        if (open && m.panel === el.navBlock) { renderRoutePanel(); }
      });
      m.panel.addEventListener("click", function (ev) { ev.stopPropagation(); });
    });
    document.addEventListener("click", function () { closeAll(null); });
    document.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape") { closeAll(null); }
    });
    closeAll(null);
  }

  // ---------------------------------------------------------------- 楼层界面
  /** 楼层列表：单层图不显示这一块，多层图给出「全部」+ 每一层 */
  function renderFloors() {
    var map = state.map;
    if (!map) { return; }
    var tops = mapFloorTops(map);
    if (tops.length < 2) {
      el.floorBlock.hidden = true;
      state.floorSet = tops.slice();
      el.floorNote.textContent = "";
      applyFloorVisibility();
      return;
    }
    el.floorBlock.hidden = false;
    el.floorList.innerHTML = "";
    el.floorList.appendChild(floorButton("全部", tops.length, function () {
      return state.floorSet.length === tops.length;
    }, function () { setFloors(tops.slice(), "手动：显示全部楼层"); }));
    tops.forEach(function (id) {
      el.floorList.appendChild(floorButton(floorLabel(id), null, function () {
        return state.floorSet.length === 1 && state.floorSet[0] === id;
      }, function () { setFloors([id], "手动：" + floorLabel(id)); }));
    });
    syncFloorButtons();
    el.floorNote.textContent = state.floorNote;
  }

  function floorButton(text, count, isOn, onClick) {
    var btn = document.createElement("button");
    btn.className = "floor-item";
    btn.__isOn = isOn;
    btn.textContent = count === null ? text : text + "（" + count + " 层）";
    btn.addEventListener("click", onClick);
    return btn;
  }

  function syncFloorButtons() {
    var items = el.floorList.querySelectorAll(".floor-item");
    for (var i = 0; i < items.length; i++) {
      items[i].dataset.on = items[i].__isOn() ? "true" : "false";
    }
  }

  /** 切换要显示的楼层：同步按钮、底图显隐与标记过滤 */
  function setFloors(ids, note) {
    state.floorSet = ids.slice();
    state.floorNote = note || "";
    el.floorNote.textContent = state.floorNote;
    applyFloorVisibility();
    syncFloorButtons();
    renderOverlay();
  }

  /**
   * 底图显隐：选中的楼层全亮，比它低的楼层半透明垫在下面，比它高的直接隐藏。
   * 判定「哪些是楼层」不看名字，就看 data 里的可选楼层表——
   * 这样底图里上游没登记、但确实是一层的组（如海关的一层）也会被正确地切掉或显示，
   * 而楼梯这类跨层共用的组（Shoreline 的 Stairs_Common）不在表里，自然一直可见。
   */
  var GHOST_OPACITY = 0.25;

  function applyFloorVisibility() {
    if (!el.base || !state.map) { return; }
    var tops = mapFloorTops(state.map);
    // 只选了一层时才知道「下面」是哪些层；「全部」或默认多层显示时不做半透明
    var focus = state.floorSet.length === 1 ? tops.indexOf(state.floorSet[0]) : -1;
    var children = el.base.children;
    for (var i = 0; i < children.length; i++) {
      var node = children[i];
      if (node.tagName !== "g" || !node.id) { continue; }
      var idx = tops.indexOf(node.id);
      if (idx === -1) { continue; }             // 楼梯等跨层共用的组：始终可见
      if (state.floorSet.indexOf(node.id) !== -1) {
        node.style.display = "";
        node.style.opacity = "";
      } else if (focus >= 0 && idx < focus) {
        node.style.display = "";
        node.style.opacity = String(GHOST_OPACITY);
      } else {
        node.style.display = "none";
        node.style.opacity = "";
      }
    }
  }

  /** 跟随截图自动切层（只在多层图 + 有高度 y 时生效） */
  function maybeAutoFloor(pos) {
    var map = state.map;
    if (!map || !state.floorAuto || !pos) { return; }
    var tops = mapFloorTops(map);
    if (tops.length < 2) { return; }
    var band = bandOfPosition(map, pos);
    if (band && band.svgLayer && tops.indexOf(band.svgLayer) !== -1) {
      if (state.floorSet.length !== 1 || state.floorSet[0] !== band.svgLayer) {
        setFloors([band.svgLayer], "跟随截图自动切层：" + floorLabel(band.svgLayer) + "（y " + pos.y + "）");
      }
      return;
    }
    if (band) {
      el.floorNote.textContent = "截图高度 y=" + pos.y + " 落在「" + (band.label || "未命名层") +
        "」，该层没有矢量底图，仍显示当前楼层";
      return;
    }
    var def = mapDefaultFloors(map);
    if (state.floorSet.slice().sort().join() !== def.slice().sort().join()) {
      setFloors(def, "跟随截图自动切层：" + def.map(floorLabel).join(" / "));
    }
  }

  function bindUI() {
    // 图例会随地图/数据重绘，监听必须挂在容器上（绑到 checkbox 节点会在重绘后一起丢掉，
    // 表现为「取消勾选地图上却还画着」——这正是之前那个 bug）
    el.layerToggles.addEventListener("change", function (ev) {
      var box = ev.target;
      if (!box || box.type !== "checkbox" || !box.dataset.layer) { return; }
      var key = box.dataset.layer;
      var isMaster = (key === "valuables");
      // 「高级资源点（全部）」是总开关：一键把下面 7 个子类全开 / 全关
      if (isMaster) {
        VALUABLE_CATS.forEach(function (c) { state.layers[valuableCatKey(c.key)] = box.checked; });
      }
      state.layers[key] = box.checked;
      localStorage.setItem(LS_LAYERS, JSON.stringify(state.layers));
      // 总开关会连带改子类，必须整块重画图例（否则子类的勾选框还停在旧状态）
      if (isMaster) { renderLayerToggles(); } else { syncLegendState(); }
      renderOverlay();
      queuePrefs({ ui: uiPatch() });   // 勾选结果同时写回配置文件
    });

    $("zoom-in").addEventListener("click", function () { zoomAt(centerX(), centerY(), 1.25); });
    $("zoom-out").addEventListener("click", function () { zoomAt(centerX(), centerY(), 1 / 1.25); });
    $("reset").addEventListener("click", function () { resetView(); });
    if (el.centerBtn) {
      el.centerBtn.addEventListener("click", function () { setAutoCenter(!state.autoCenter, true); });
    }

    el.floorAuto.addEventListener("change", function () {
      state.floorAuto = el.floorAuto.checked;
      localStorage.setItem(LS_FLOOR_AUTO, state.floorAuto ? "1" : "0");
      if (state.floorAuto && state.player) { maybeAutoFloor(state.player); }
      else if (!state.floorAuto) { setFloors(state.floorSet, "手动"); }
      queuePrefs({ ui: uiPatch() });
    });
    el.floorFilter.addEventListener("change", function () {
      state.floorFilter = el.floorFilter.checked;
      localStorage.setItem(LS_FLOOR_FILTER, state.floorFilter ? "1" : "0");
      renderOverlay();
      queuePrefs({ ui: uiPatch() });
    });

    // 图标整体缩放滑条：拖动时立刻改变已画标记的大小，松手后由防抖写回配置文件
    if (el.iconScale) {
      el.iconScale.addEventListener("input", function () { setIconScale(el.iconScale.value, true); });
    }

    el.search.addEventListener("input", renderSearchResults);
    el.search.addEventListener("keydown", function (ev) {
      if (ev.key === "Enter") {
        var first = el.searchResults.querySelector(".search-hit");
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
        setAutoCenter(false);                  // 用户接管视角
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

    // 光标锚点缩放；自动居中开启时改为以屏幕中心（也就是玩家所在处）为锚点，避免把玩家甩出视野
    el.viewport.addEventListener("wheel", function (ev) {
      ev.preventDefault();
      var rect = el.stage.getBoundingClientRect();
      var factor = ev.deltaY < 0 ? 1.15 : 1 / 1.15;
      if (state.autoCenter && state.player) {
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
    state.searchCache = null;   // 搜索索引与地图绑定，换图即失效
    state.floorMeta = buildFloorMeta(map);
    state.floorLabels = state.floorMeta.labels;
    el.detailBlock.hidden = true;
    localStorage.setItem(LS_MAP, key);
    markSelectedMap();
    hideMarkerPopup();       // 换图了，上一张图的标记浮窗不该留着
    renderLayerToggles();    // 图例计数按当前地图刷新
    el.statusMap.textContent = "正在载入 " + map.name + " …";

    return svgText(map).then(function (text) {
      buildSvg(text, map);
      renderFloors();
      // 换图时如果已经有定位，直接落到定位所在的那一层，省得用户手动再切一次
      maybeAutoFloor(state.player);
      renderOverlay();
      resetView();
      // 换了图之后如果定位/开关都已就绪，直接把视角摆到玩家身上（自动缩放 + 自动居中）
      if (state.autoZoom && state.player) { applyAutoZoom(); }
      else if (state.autoCenter && state.player) { centerOnPlayer(); }
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

  /** 注入底图：所有顶层组先都进来，楼层显隐交给 applyFloorVisibility 控制 */
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
    el.base = base;

    var overlay = svgEl("g", { id: "emk-overlay" });
    // 标记可能有上千个，逐个挂监听太亏：整个覆盖层走一次事件委托
    overlay.addEventListener("click", onOverlayClick);
    el.svg.appendChild(overlay);
    el.overlay = overlay;

    state.floorSet = mapDefaultFloors(map);
    state.floorNote = "";
    applyFloorVisibility();

    updateMetrics();
  }

  function onOverlayClick(ev) {
    var target = ev.target;
    var node = target && target.closest ? target.closest(".emk-marker, .emk-area") : null;
    if (!node || !node.__emkHit || !state.map) { return; }
    ev.stopPropagation();
    showDetail(state.map, node.__emkHit.kind, node.__emkHit.item, node);
    // 点任意标记都在**地图区左上角的固定位置**弹一个小浮窗（淡入淡出）；左侧详情面板仍给完整信息。
    // 上锁的门要哪把钥匙也在同一个浮窗里（见 detailRows 的「需要钥匙」行），不再另弹一个跟随图标的浮窗
    // （2026-10-19 第十一轮：以前门会同时冒出两个浮窗，用户反馈容易看乱）。
    showMarkerPopup(state.map, node.__emkHit.kind, node.__emkHit.item);
  }

  // ---------------------------------------------------------------- 标记小浮窗
  // 点地图上的任意标记（物资点 / 出生点 / Boss / 撤离点 / 上锁的门…）时，在**地图区左上角的固定位置**
  // 弹一个小浮窗，显示简略信息（与左侧详情面板同源的 detailRows）；固定位置 = 不跟图标跑，不会随平移缩放乱动。
  // 淡入淡出走 CSS opacity 过渡：浮窗本身是 HTML <div>，不是 SVG 图元，
  // 不碰「SVG 加动画会被栅格化」的老坑。
  var markerPopTimer = null;
  var markerPopNode = null;          // 当前那个浮窗（用变量记着，淡出期间旧的还能留在 DOM 里）
  var POP_FADE_MS = 180;             // 与 style.css 里 .marker-pop 的过渡时长对齐

  /** 关掉标记小浮窗（换图、换选另一个标记、超时都会用到）：先淡出再从 DOM 摘掉 */
  function hideMarkerPopup() {
    if (markerPopTimer) { window.clearTimeout(markerPopTimer); markerPopTimer = null; }
    var host = markerPopNode;
    markerPopNode = null;
    if (!host) { return; }
    host.classList.remove("show");
    window.setTimeout(function () { if (host.parentNode) { host.remove(); } }, POP_FADE_MS);
  }

  function showMarkerPopup(map, kind, item) {
    hideMarkerPopup();
    var host = document.createElement("div");
    host.id = "marker-pop";
    host.className = "marker-pop";

    var title = document.createElement("div");
    title.className = "marker-pop-title";
    title.textContent = item.name || KIND_LABEL[kind] || kind;
    host.appendChild(title);

    detailRows(map, kind, item).forEach(function (row) {
      if (row[0] === "名称") { return; }      // 名称已作标题，不重复
      var line = document.createElement("div");
      line.className = "marker-pop-row";
      var k = document.createElement("span");
      k.className = "marker-pop-k";
      k.textContent = row[0];
      var v = document.createElement("span");
      v.className = "marker-pop-v";
      // 像「上锁的门」浮窗那样带上小图标：物资容器贴该类别的图标、高级资源点贴物品图标、钥匙贴钥匙图标
      if (row[2]) { v.appendChild(inlineIconAny(row[2])); }
      v.appendChild(document.createTextNode(row[1]));
      line.appendChild(k);
      line.appendChild(v);
      host.appendChild(line);
    });

    markerPopNode = host;
    document.body.appendChild(host);

    // 固定位置：地图区左上角往里 12px（position:fixed，不随地图平移 / 缩放移动）
    var stage = el.stage.getBoundingClientRect();
    host.style.left = Math.round(stage.left + 12) + "px";
    host.style.top = Math.round(stage.top + 12) + "px";

    // 下一帧再上 .show：先让浏览器算完 opacity:0 的初始态，过渡才会真的跑起来
    window.requestAnimationFrame(function () { host.classList.add("show"); });

    markerPopTimer = window.setTimeout(hideMarkerPopup, 8000);
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

  /** 所有会落到地图上的点（用于视图外扩；含新图层，但不含地名） */
  var POINT_KINDS = ["extracts", "transits", "spawns", "hazards", "locks",
                     "containers", "loose", "bosses", "artillery", "btr", "stationary"];

  function eachPoint(map, fn) {
    POINT_KINDS.forEach(function (kind) {
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

  /** 标注点在屏幕上大小恒定：内部再乘 1/z 反向补偿，另外乘上滑条给的「整体图标缩放」 */
  function updateCounterScale() {
    var inv = iconScale() / state.z;
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
    rememberManualZoom();                   // 自动缩放要「沿用最近一次手动比例」
  }

  /** 记下用户手动缩放的比例；自动缩放开启时会用它，而不是写死的倍数 */
  function rememberManualZoom() {
    try { localStorage.setItem(LS_ZOOM, String(state.z)); } catch (e) { /* 隐私模式下写入会失败 */ }
  }

  function storedZoom() {
    var value = parseFloat(localStorage.getItem(LS_ZOOM));
    if (!isFinite(value) || value <= 0) { return DEFAULT_AUTO_ZOOM; }
    return Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, value));
  }

  /** 定位自动缩放：把地图缩放到「最近一次手动比例」（没手动调过就用默认 4×），并保持玩家在视野中心 */
  function applyAutoZoom() {
    if (!state.map) { return; }
    state.z = storedZoom();
    if (state.player) { centerOnPlayer(); } else { applyView(); }
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

  // ---------------------------------------------------------------- 钉选
  // 钉选按「类型」维度记录：kind + name（如 containers + 物资埋藏桶）。
  // 命中的标记统一加高亮描边；钉选跨会话保存在 localStorage 与服务端配置的 ui.pins 里。

  /** 钉选的唯一键（同名不同类型算两条） */
  function pinId(kind, name) { return kind + "|" + name; }

  function hasPin(kind, name) {
    var id = pinId(kind, name);
    for (var i = 0; i < state.pins.length; i++) {
      if (pinId(state.pins[i].kind, state.pins[i].name) === id) { return true; }
    }
    return false;
  }

  /** 某个标记是否被钉选：类型名一致即命中。
   *  高级资源点没有 name，改按 items 里的物品名比对；上锁的门按钥匙名比对。 */
  function isPinnedItem(kind, item) {
    for (var i = 0; i < state.pins.length; i++) {
      var pin = state.pins[i];
      if (pin.kind !== kind || !pin.name) { continue; }
      if (item.name === pin.name || item.keyName === pin.name || item.text === pin.name) { return true; }
      if (item.items && item.items.indexOf(pin.name) !== -1) { return true; }
    }
    return false;
  }

  /** 钉选 / 取消钉选一个类型；返回操作后是否处于「已钉选」 */
  function togglePin(kind, name) {
    if (!kind || !name) { return false; }
    var id = pinId(kind, name), found = -1, i;
    for (i = 0; i < state.pins.length; i++) {
      if (pinId(state.pins[i].kind, state.pins[i].name) === id) { found = i; break; }
    }
    var now;
    if (found >= 0) { state.pins.splice(found, 1); now = false; }
    else {
      state.pins.push({ kind: kind, name: name });
      if (state.pins.length > PIN_MAX) { state.pins.shift(); }
      now = true;
    }
    persistPins();
    renderOverlay();          // 覆盖层重建时会一并重画路线
    renderSearchResults();
    return now;
  }

  function persistPins() {
    try { localStorage.setItem(LS_PINS, JSON.stringify(state.pins)); } catch (e) { /* 隐私模式忽略 */ }
    queuePrefs({ ui: uiPatch() });
  }

  /** 用一份外部钉选列表替换当前钉选（服务端配置 / 本地存储恢复时用） */
  function setPins(list) {
    var out = [];
    (list || []).forEach(function (p) {
      if (p && p.kind && p.name) { out.push({ kind: String(p.kind), name: String(p.name) }); }
    });
    state.pins = out.slice(-PIN_MAX);
  }

  function samePins(a, b) {
    if (a.length !== b.length) { return false; }
    for (var i = 0; i < a.length; i++) {
      if (pinId(a[i].kind, a[i].name) !== pinId(b[i].kind, b[i].name)) { return false; }
    }
    return true;
  }

  // ---------------------------------------------------------------- 导航路线
  // 本工具没有导航网格（NavMesh），路线按各途经点的世界坐标直线连接：
  // 距离是直线距离，仅供方向参考；跨楼层的点直接相连会「穿墙」，需自行判断。

  /** 路线的实际点序列（可能带上实时定位作为起点） */
  function routePoints() {
    var pts = [];
    if (state.routeFromPlayer && state.player) {
      pts.push({ name: "实时定位位置", x: state.player.x, z: state.player.z, y: state.player.y });
    }
    state.route.forEach(function (p) { pts.push(p); });
    return pts;
  }

  function routeDistance() {
    var pts = routePoints(), total = 0;
    for (var i = 1; i < pts.length; i++) {
      var dx = pts[i].x - pts[i - 1].x, dz = pts[i].z - pts[i - 1].z;
      total += Math.sqrt(dx * dx + dz * dz);
    }
    return total;
  }

  function persistRoute() {
    try {
      localStorage.setItem(LS_ROUTE, JSON.stringify(state.route));
      localStorage.setItem(LS_ROUTE_PLAYER, state.routeFromPlayer ? "1" : "0");
    } catch (e) { /* 忽略 */ }
  }

  function addRoutePoint(kind, name, item) {
    if (!item || item.x === undefined || item.x === null) { return; }
    state.route.push({ kind: kind || "", name: name || "", x: item.x, z: item.z, y: item.y });
    if (state.route.length > ROUTE_MAX) { state.route.shift(); }
    persistRoute();
    renderOverlay();
    renderRoutePanel();
  }

  function clearRoute() {
    state.route = [];
    persistRoute();
    renderOverlay();
    renderRoutePanel();
  }

  function reverseRoute() {
    state.route.reverse();
    persistRoute();
    renderOverlay();
    renderRoutePanel();
  }

  /** 路线折线 + 编号圆点（编号用 1 起；起点若是实时定位也算 1 号） */
  function renderRoute() {
    if (!el.overlay || !state.map) { return; }
    var pts = routePoints();
    if (pts.length < 2) { return; }
    var map = state.map;
    var unit = 1 / state.fit;
    var g = svgEl("g", { class: "emk-route-layer", "pointer-events": "none" });
    g.appendChild(svgEl("polyline", {
      class: "emk-route-line",
      "vector-effect": "non-scaling-stroke",
      points: pts.map(function (p) {
        return svgX(map, p.x, p.z).toFixed(2) + "," + svgY(map, p.x, p.z).toFixed(2);
      }).join(" ")
    }));
    pts.forEach(function (p, i) {
      var sx = svgX(map, p.x, p.z), sy = svgY(map, p.x, p.z);
      var node = svgEl("g", { class: "emk-route-node" });
      node.__emkBase = { sx: sx, sy: sy };
      node.setAttribute("transform", "translate(" + sx + " " + sy + ") scale(1)");
      node.appendChild(svgEl("circle", { r: 9 * unit, "vector-effect": "non-scaling-stroke" }));
      var num = svgEl("text", {
        class: "emk-route-num", "font-size": 11 * unit,
        "text-anchor": "middle", "dominant-baseline": "central", x: 0, y: 0
      });
      num.textContent = String(i + 1);
      node.appendChild(num);
      g.appendChild(node);
      state.markerScaleNodes.push(node);   // 随缩放反向补偿，屏幕上大小恒定
    });
    el.overlay.appendChild(g);
  }

  /** 导航面板：途经点列表 + 总距离；起点若来自实时定位则不可删 */
  function renderRoutePanel() {
    if (!el.routeList) { return; }
    var fromPlayer = !!(state.routeFromPlayer && state.player);
    var offset = fromPlayer ? 1 : 0;
    var pts = routePoints();
    el.routeList.innerHTML = "";
    pts.forEach(function (p, i) {
      var li = document.createElement("li");
      li.className = "route-item";
      var idx = document.createElement("span");
      idx.className = "route-index";
      idx.textContent = String(i + 1);
      var nm = document.createElement("span");
      nm.className = "route-name";
      nm.textContent = p.name || "途经点";
      li.appendChild(idx);
      li.appendChild(nm);
      if (i < offset) {
        var tag = document.createElement("span");
        tag.className = "route-tag";
        tag.textContent = "定位";
        li.appendChild(tag);
      } else {
        var del = document.createElement("button");
        del.type = "button";
        del.className = "route-del";
        del.textContent = "×";
        del.title = "移除该途经点";
        (function (routeIdx) {
          del.addEventListener("click", function () {
            state.route.splice(routeIdx, 1);
            persistRoute();
            renderOverlay();
            renderRoutePanel();
          });
        })(i - offset);
        li.appendChild(del);
      }
      el.routeList.appendChild(li);
    });
    if (el.routeSummary) {
      el.routeSummary.textContent = pts.length
        ? "共 " + pts.length + " 个点 · 直线距离约 " + Math.round(routeDistance()) + " 米"
        : "路线为空：在搜索结果或标记详情里点「路线」加入途经点";
    }
    if (el.routeFromPlayerBox) { el.routeFromPlayerBox.checked = !!state.routeFromPlayer; }
  }

  /** 导航面板上的按钮与开关 */
  function bindRouteUI() {
    if (el.routeClear) { el.routeClear.addEventListener("click", clearRoute); }
    if (el.routeReverse) {
      el.routeReverse.addEventListener("click", function () {
        reverseRoute();
        renderRoutePanel();
      });
    }
    if (el.routeFromPlayerBox) {
      el.routeFromPlayerBox.addEventListener("change", function () {
        state.routeFromPlayer = el.routeFromPlayerBox.checked;
        persistRoute();
        renderOverlay();
        renderRoutePanel();
      });
    }
    if (el.routeAddCurrent) {
      el.routeAddCurrent.addEventListener("click", function () {
        if (!state.selected) { return; }
        addRoutePoint(state.selected.kind, selectedName(state.selected), state.selected.item);
      });
    }
  }

  /** 选中项的名字（详情面板「加入路线」按钮用） */
  function selectedName(sel) {
    if (!sel || !sel.item) { return ""; }
    return entryNameOf(sel.kind, sel.item) || "";
  }

  // ---------------------------------------------------------------- 覆盖层
  /** 各点状标记的屏幕半径（px）；画图标的图层（撤离/转移/物资/高级资源点/出生点/门/Boss/BTR）不走这里 */
  var MARKER_RADIUS = {
    loose: 2.4, hazards: 3.2, artillery: 3.2, stationary: 4.4
  };
  // 可以点开详情的图层
  var CLICKABLE_KINDS = ["extracts", "transits", "spawns", "containers", "loose", "valuables", "locks",
                         "hazards", "artillery", "bosses", "btr", "stationary"];
  /** 画图标（而非半径圆点）的图层：选中高亮环的外接半径要另算 */
  var ICON_KINDS = ["containers", "valuables", "spawns", "bosses", "locks", "btr"];

  /** 标记是否该出现在当前显示的楼层里（没有高度信息的一律显示，不猜） */
  function isItemVisible(map, item, kind) {
    if (!state.floorFilter) { return true; }
    if (item.y === undefined || item.y === null) { return true; }
    if (FLOOR_AGNOSTIC_KINDS.indexOf(kind) !== -1) { return true; }   // 炮击区是整图级的
    var floor = floorOfPosition(map, item);
    if (!floor) { return true; }          // 落在没有矢量底图的层：不隐藏，免得凭空消失
    return state.floorSet.indexOf(floor) !== -1;
  }
  // 不随楼层过滤的图层：炮击区在地图外沿，跟楼层无关；撤离/转移点是地面出口，
  // 上游的高度（y）常落在建筑物的某一层，按楼层过滤会把同名的另一阵营点藏起来。
  var FLOOR_AGNOSTIC_KINDS = ["artillery", "extracts", "transits"];

  /** 高级资源点的合并渲染规格：只要该点属于任一「已开启」的子类就画（各点只画一次，不重复） */
  function valuableUnionSpec() {
    var on = VALUABLE_CATS.filter(function (c) { return state.layers[valuableCatKey(c.key)]; })
                          .map(function (c) { return c.key; });
    return {
      key: "valuables", kind: "valuables",
      where: function (item) {
        var cats = valuableCatsOf(item);
        for (var i = 0; i < cats.length; i++) { if (on.indexOf(cats[i]) !== -1) { return true; } }
        return false;
      }
    };
  }

  function renderOverlay() {
    if (!el.overlay || !state.map) { return; }
    var map = state.map;
    var unit = 1 / state.fit;         // 目标屏幕像素 → 用户单位（1/z 的反向补偿在节点 transform 里）

    while (el.overlay.firstChild) { el.overlay.removeChild(el.overlay.firstChild); }
    state.markerScaleNodes = [];

    // 先画面状图层（危险区/炮击区），再画点状标记，最后叠地名
    renderAreas(map, "hazards", unit);
    renderAreas(map, "artillery", unit);

    var drewValuables = false;
    LAYER_SPEC.forEach(function (group) {
      group.items.forEach(function (spec) {
        // 高级资源点：7 个子类的筛选条件会互相重叠，不能按开关逐个画（同一点会叠两层图标），
        // 改成「启用的子类并集」整体画一次——走到第一个（总开关）那行时画。
        if (spec.kind === "valuables") {
          if (!drewValuables) { drewValuables = true; renderMarkerKind(map, valuableUnionSpec(), unit); }
          return;
        }
        if (!state.layers[spec.key]) { return; }
        if (spec.kind === "labels" || spec.kind === "hazards" || spec.kind === "artillery") { return; }
        renderMarkerKind(map, spec, unit);
      });
    });

    if (state.layers.labels) { renderLabels(map, unit); }

    renderRoute();             // 路线叠在最上面（编号圆点也要进 markerScaleNodes）
    updateCounterScale();
    renderPlayer();            // 覆盖层被重建，玩家标记要跟着回来
    updatePositionStatus();
  }

  /** 一种 kind 下、符合该开关筛选条件的标记 */
  function itemsOfSpec(map, spec) {
    var out = [];
    (map.layers[spec.kind] || []).forEach(function (item) {
      if (spec.where && !spec.where(item)) { return; }
      if (!isItemVisible(map, item, spec.kind)) { return; }
      out.push(item);
    });
    return out;
  }

  function renderMarkerKind(map, spec, unit) {
    var items = itemsOfSpec(map, spec);
    if (!items.length) { return; }
    var clickable = CLICKABLE_KINDS.indexOf(spec.kind) !== -1;
    var group = svgEl("g", {
      class: "emk-layer emk-" + spec.kind, "data-layer": spec.key,
      "pointer-events": clickable ? "visiblePainted" : "none"
    });
    var radius = (MARKER_RADIUS[spec.kind] || 3) * unit;
    items.forEach(function (item) {
      var node = makeMarker(map, spec.kind, item, radius, spec.icon);
      if (clickable) { node.__emkHit = { kind: spec.kind, item: item }; }
      group.appendChild(node);
    });
    el.overlay.appendChild(group);
  }

  /** 面状标记（雷区/炮击区）：有轮廓就画多边形，只有坐标就退化成点 */
  function renderAreas(map, kind, unit) {
    if (!state.layers[kind]) { return; }
    var group = svgEl("g", {
      class: "emk-layer emk-" + kind, "data-layer": kind, "pointer-events": "visiblePainted"
    });
    var drawn = 0;
    (map.layers[kind] || []).forEach(function (item) {
      if (!isItemVisible(map, item, kind)) { return; }
      drawn += 1;
      if (!item.outline || item.outline.length < 3) {
        var node = makeMarker(map, kind, item, (MARKER_RADIUS[kind] || 3) * unit);
        node.__emkHit = { kind: kind, item: item };
        group.appendChild(node);
        return;
      }
      var poly = svgEl("polygon", {
        class: "emk-area emk-area-" + kind,
        points: item.outline.map(function (pt) {
          return svgX(map, pt[0], pt[1]).toFixed(2) + "," + svgY(map, pt[0], pt[1]).toFixed(2);
        }).join(" ")
      });
      poly.__emkHit = { kind: kind, item: item };
      group.appendChild(poly);
    });
    if (drawn) { el.overlay.appendChild(group); }
  }

  function renderLabels(map, unit) {
    var labels = svgEl("g", { id: "emk-labels" });
    (map.labels || []).forEach(function (label) {
      var sx = svgX(map, label.x, label.z);
      var sy = svgY(map, label.x, label.z);
      // 地名**跟地图绑死**（2026-10-19 第十一轮改）：不做 1/z 反向补偿，缩放多少字号就跟着缩放多少，
      // 与底图比例一致；也因此不受「图标滑条」影响——滑条只调图标。字号仍乘 unit：z=1 时约 12 屏幕像素。
      var g = svgEl("g", { "pointer-events": "none" });
      g.setAttribute("transform", "translate(" + sx + " " + sy + ")");
      var text = svgEl("text", {
        class: "emk-label",
        "font-size": 12 * unit,
        // 描边宽度同样乘 unit：写死在 CSS 里的话，小图（fit 大）会把描边放大成黑块
        "stroke-width": 2.4 * unit,
        "paint-order": "stroke",
        "text-anchor": "middle",
        "dominant-baseline": "central",
        x: 0,
        y: 0
      });
      text.textContent = label.text;
      g.appendChild(text);
      labels.appendChild(g);
    });
    el.overlay.appendChild(labels);
  }

  // ---------------------------------------------------------------- 图标素材
  /**
   * 图片素材图标：用户提供的 PNG 经构建期抠图、统一成 64×64 透明底，放在 assets/icons/。
   * 命中这些 key 的图层直接贴图；其余仍用手画的 SVG 图标（见 LOOT_ICONS / SIGN_ICONS）。
   */
  var ICON_PNG = {
    // 物资容器（14 类里 12 类有素材；手提箱 / 收银机 / 其他容器仍用手画）
    safe: "assets/icons/loot-safe.png",
    jacket: "assets/icons/loot-jacket.png",
    pcblock: "assets/icons/loot-pcblock.png",
    scavbody: "assets/icons/loot-scavbody.png",
    drawer: "assets/icons/loot-drawer.png",
    duffle: "assets/icons/loot-duffle.png",
    cache: "assets/icons/loot-cache.png",
    med: "assets/icons/loot-med.png",
    supply: "assets/icons/loot-supply.png",
    toolbox: "assets/icons/loot-toolbox.png",
    grenade: "assets/icons/loot-grenade.png",
    weapon: "assets/icons/loot-weapon.png",
    // 高级资源点按物品分（只剩「兜底宝石」仍用手画）
    valuable_btc: "assets/icons/val-btc.png",
    valuable_bottle: "assets/icons/val-bottle.png",
    valuable_defib: "assets/icons/val-defib.png",
    valuable_key: "assets/icons/val-key.png",
    valuable_med: "assets/icons/val-ledx.png",
    valuable_keycard: "assets/icons/val-keycard-yellow.png",
    valuable_card_yellow: "assets/icons/val-keycard-yellow.png",
    valuable_card_red: "assets/icons/val-keycard-red.png",
    valuable_card_green: "assets/icons/val-keycard-green.png",
    valuable_card_blue: "assets/icons/val-keycard-blue.png",
    valuable_card_purple: "assets/icons/val-keycard-purple.png",
    valuable_card_black: "assets/icons/val-keycard-black.png",
    valuable_card_living: "assets/icons/val-keycard-living.png",
    valuable_card_11sr: "assets/icons/val-card-11sr.png",
    valuable_card_21ws: "assets/icons/val-card-21ws.png",
    // 2026-10-18 第四批：上锁的门所需钥匙 + 固定刷新钥匙的图标（wiki 截图逐行抠图）
    //   key 名 = "key_" + 物品 id 前 8 位；对应表见下方 KEY_ICONS（中文名 → key）。
    key_5448ba0b: "assets/icons/key-5448ba0b.png",
    key_5672c92d: "assets/icons/key-5672c92d.png",
    key_5780cda0: "assets/icons/key-5780cda0.png",
    key_5780cf69: "assets/icons/key-5780cf69.png",
    key_5780cf72: "assets/icons/key-5780cf72.png",
    key_5780cf7f: "assets/icons/key-5780cf7f.png",
    key_5780cf94: "assets/icons/key-5780cf94.png",
    key_5780cf9e: "assets/icons/key-5780cf9e.png",
    key_5780cfa5: "assets/icons/key-5780cfa5.png",
    key_5780d053: "assets/icons/key-5780d053.png",
    key_5780d065: "assets/icons/key-5780d065.png",
    key_5780d07a: "assets/icons/key-5780d07a.png",
    key_5913611c: "assets/icons/key-5913611c.png",
    key_59136a44: "assets/icons/key-59136a44.png",
    key_59136e1e: "assets/icons/key-59136e1e.png",
    key_591382d9: "assets/icons/key-591382d9.png",
    key_591383f1: "assets/icons/key-591383f1.png",
    key_5913877a: "assets/icons/key-5913877a.png",
    key_59139158: "assets/icons/key-59139158.png",
    key_59145780: "assets/icons/key-59145780.png",
    key_59148c8a: "assets/icons/key-59148c8a.png",
    key_591afe01: "assets/icons/key-591afe01.png",
    key_5937ee64: "assets/icons/key-5937ee64.png",
    key_59385041: "assets/icons/key-59385041.png",
    key_5938603e: "assets/icons/key-5938603e.png",
    key_59387a49: "assets/icons/key-59387a49.png",
    key_59389945: "assets/icons/key-59389945.png",
    key_593962ca: "assets/icons/key-593962ca.png",
    key_593aa4be: "assets/icons/key-593aa4be.png",
    key_5a0dc455: "assets/icons/key-5a0dc455.png",
    key_5a0dc95c: "assets/icons/key-5a0dc95c.png",
    key_5a0ea647: "assets/icons/key-5a0ea647.png",
    key_5a0ea79b: "assets/icons/key-5a0ea79b.png",
    key_5a0eb38b: "assets/icons/key-5a0eb38b.png",
    key_5a0eb6ac: "assets/icons/key-5a0eb6ac.png",
    key_5a0ec6d2: "assets/icons/key-5a0ec6d2.png",
    key_5a0ee307: "assets/icons/key-5a0ee307.png",
    key_5a0ee345: "assets/icons/key-5a0ee345.png",
    key_5a0ee37f: "assets/icons/key-5a0ee37f.png",
    key_5a0ee4b5: "assets/icons/key-5a0ee4b5.png",
    key_5a0eec96: "assets/icons/key-5a0eec96.png",
    key_5a0eecf6: "assets/icons/key-5a0eecf6.png",
    key_5a0eed43: "assets/icons/key-5a0eed43.png",
    key_5a0eee14: "assets/icons/key-5a0eee14.png",
    key_5a13eebd: "assets/icons/key-5a13eebd.png",
    key_5a13ef06: "assets/icons/key-5a13ef06.png",
    key_5a13ef7e: "assets/icons/key-5a13ef7e.png",
    key_5a13f241: "assets/icons/key-5a13f241.png",
    key_5a13f352: "assets/icons/key-5a13f352.png",
    key_5a13f463: "assets/icons/key-5a13f463.png",
    key_5a144bdb: "assets/icons/key-5a144bdb.png",
    key_5a144dfd: "assets/icons/key-5a144dfd.png",
    key_5a1452ee: "assets/icons/key-5a1452ee.png",
    key_5a145d47: "assets/icons/key-5a145d47.png",
    key_5a145d7b: "assets/icons/key-5a145d7b.png",
    key_5a145ebb: "assets/icons/key-5a145ebb.png",
    key_5ad5ccd1: "assets/icons/key-5ad5ccd1.png",
    key_5ad5d498: "assets/icons/key-5ad5d498.png",
    key_5ad5d644: "assets/icons/key-5ad5d644.png",
    key_5ad5d7d2: "assets/icons/key-5ad5d7d2.png",
    key_5ad5db37: "assets/icons/key-5ad5db37.png",
    key_5ad7242b: "assets/icons/key-5ad7242b.png",
    key_5addaffe: "assets/icons/key-5addaffe.png",
    key_5c1f79a0: "assets/icons/key-5c1f79a0.png",
    key_5c94bbff: "assets/icons/key-5c94bbff.png",
    key_5d80c60f: "assets/icons/key-5d80c60f.png",
    key_5d80c62a: "assets/icons/key-5d80c62a.png",
    key_5d80c930: "assets/icons/key-5d80c930.png",
    key_5d80c959: "assets/icons/key-5d80c959.png",
    key_5d80ca90: "assets/icons/key-5d80ca90.png",
    key_5d80cb38: "assets/icons/key-5d80cb38.png",
    key_5d80cb56: "assets/icons/key-5d80cb56.png",
    key_5d80cbd8: "assets/icons/key-5d80cbd8.png",
    key_5d80ccac: "assets/icons/key-5d80ccac.png",
    key_5d80ccdd: "assets/icons/key-5d80ccdd.png",
    key_5d80cd1a: "assets/icons/key-5d80cd1a.png",
    key_5d8e15b6: "assets/icons/key-5d8e15b6.png",
    key_5d947d38: "assets/icons/key-5d947d38.png",
    key_5d947d4e: "assets/icons/key-5d947d4e.png",
    key_5da743f5: "assets/icons/key-5da743f5.png",
    key_5e42c715: "assets/icons/key-5e42c715.png",
    key_5ede7a82: "assets/icons/key-5ede7a82.png",
    key_5ede7b0c: "assets/icons/key-5ede7b0c.png",
    key_5eff09cd: "assets/icons/key-5eff09cd.png",
    key_61a64428: "assets/icons/key-61a64428.png",
    key_61a6444b: "assets/icons/key-61a6444b.png",
    key_61a64492: "assets/icons/key-61a64492.png",
    key_61aa5aed: "assets/icons/key-61aa5aed.png",
    key_61aa5b51: "assets/icons/key-61aa5b51.png",
    key_61aa5b7d: "assets/icons/key-61aa5b7d.png",
    key_61aa5ba8: "assets/icons/key-61aa5ba8.png",
    key_61aa81fc: "assets/icons/key-61aa81fc.png",
    key_62987c65: "assets/icons/key-62987c65.png",
    key_62987cb9: "assets/icons/key-62987cb9.png",
    key_62987da9: "assets/icons/key-62987da9.png",
    key_62987dfc: "assets/icons/key-62987dfc.png",
    key_62987e26: "assets/icons/key-62987e26.png",
    key_62a9cb93: "assets/icons/key-62a9cb93.png",
    key_6398fd8a: "assets/icons/key-6398fd8a.png",
    key_63a397d3: "assets/icons/key-63a397d3.png",
    key_63a39919: "assets/icons/key-63a39919.png",
    key_63a39c79: "assets/icons/key-63a39c79.png",
    key_63a39df1: "assets/icons/key-63a39df1.png",
    key_63a39dfe: "assets/icons/key-63a39dfe.png",
    key_63a39e1d: "assets/icons/key-63a39e1d.png",
    key_63a39fc0: "assets/icons/key-63a39fc0.png",
    key_63a39fdf: "assets/icons/key-63a39fdf.png",
    key_63a3a93f: "assets/icons/key-63a3a93f.png",
    key_63a71e78: "assets/icons/key-63a71e78.png",
    key_63a71eb5: "assets/icons/key-63a71eb5.png",
    key_64ccc1d4: "assets/icons/key-64ccc1d4.png",
    key_64ccc1ec: "assets/icons/key-64ccc1ec.png",
    key_64ccc206: "assets/icons/key-64ccc206.png",
    key_64ccc246: "assets/icons/key-64ccc246.png",
    key_64ccc25f: "assets/icons/key-64ccc25f.png",
    key_64ce5723: "assets/icons/key-64ce5723.png",
    key_64d4b23d: "assets/icons/key-64d4b23d.png",
    key_65819980: "assets/icons/key-65819980.png",
    key_65819997: "assets/icons/key-65819997.png",
    key_658199aa: "assets/icons/key-658199aa.png",
    key_6582dbf0: "assets/icons/key-6582dbf0.png",
    key_66265d7b: "assets/icons/key-66265d7b.png",
    key_664d3db6: "assets/icons/key-664d3db6.png",
    key_664d3dd5: "assets/icons/key-664d3dd5.png",
    key_664d3ddf: "assets/icons/key-664d3ddf.png",
    key_664d3de8: "assets/icons/key-664d3de8.png",
    key_664d4b01: "assets/icons/key-664d4b01.png",
    key_66acd670: "assets/icons/key-66acd670.png",
    key_6761a6cc: "assets/icons/key-6761a6cc.png",
    key_6761a6f9: "assets/icons/key-6761a6f9.png",
    key_679b9716: "assets/icons/key-679b9716.png",
    key_67ee7680: "assets/icons/key-67ee7680.png",
    key_6866ad38: "assets/icons/key-6866ad38.png",
    key_6866adbe: "assets/icons/key-6866adbe.png",
    key_68c165f1: "assets/icons/key-68c165f1.png",
    key_68cc0987: "assets/icons/key-68cc0987.png",
    key_68e63b56: "assets/icons/key-68e63b56.png",
    key_68e95d71: "assets/icons/key-68e95d71.png",
    key_68e95f4f: "assets/icons/key-68e95f4f.png",
    key_68e960db: "assets/icons/key-68e960db.png",
    key_68e96180: "assets/icons/key-68e96180.png",
    key_68e9654d: "assets/icons/key-68e9654d.png",
    key_6a8d581f: "assets/icons/key-6a8d581f.png",
    key_6aa2f656: "assets/icons/key-6aa2f656.png",
    key_6aa2f730: "assets/icons/key-6aa2f730.png",
    // 2026-10-18 第五批：补齐仍缺图的门钥匙 + 只在高级资源点出现的 3 把钥匙
    key_5d80c787: "assets/icons/key-5d80c787.png",
    key_5d80c88d: "assets/icons/key-5d80c88d.png",
    key_5d80c66d: "assets/icons/key-5d80c66d.png",
    key_5d8e3ecc: "assets/icons/key-5d8e3ecc.png",
    key_5d8e0db5: "assets/icons/key-5d8e0db5.png",
    key_5d8e0e0e: "assets/icons/key-5d8e0e0e.png",
    key_5d80cab0: "assets/icons/key-5d80cab0.png",
    key_5d80c6c5: "assets/icons/key-5d80c6c5.png",
    key_5d80c8f5: "assets/icons/key-5d80c8f5.png",
    key_5d95d6fa: "assets/icons/key-5d95d6fa.png",
    key_5d95d6be: "assets/icons/key-5d95d6be.png",
    key_5da5cdcd: "assets/icons/key-5da5cdcd.png",
    key_5da46e38: "assets/icons/key-5da46e38.png",
    key_5d9f1fa6: "assets/icons/key-5d9f1fa6.png",
    key_5d80c6fc: "assets/icons/key-5d80c6fc.png",
    key_59136519: "assets/icons/key-59136519.png",
    key_59136f6f: "assets/icons/key-59136f6f.png",
    key_658199a0: "assets/icons/key-658199a0.png",
    key_63a39f08: "assets/icons/key-63a39f08.png",
    key_63a39fd1: "assets/icons/key-63a39fd1.png",
    key_6582dc4b: "assets/icons/key-6582dc4b.png",
    key_63a39c69: "assets/icons/key-63a39c69.png",
    key_64ccc211: "assets/icons/key-64ccc211.png",
    key_64ccc268: "assets/icons/key-64ccc268.png",
    key_63a39f6e: "assets/icons/key-63a39f6e.png",
    key_64ccc1f4: "assets/icons/key-64ccc1f4.png",
    key_63a71e86: "assets/icons/key-63a71e86.png",
    key_63a71e92: "assets/icons/key-63a71e92.png",
    key_64ccc24d: "assets/icons/key-64ccc24d.png",
    key_64ccc1fe: "assets/icons/key-64ccc1fe.png",
    key_6582dbe4: "assets/icons/key-6582dbe4.png",
    key_6582dc57: "assets/icons/key-6582dc57.png",
    key_63a39e49: "assets/icons/key-63a39e49.png",
    key_63a39ce4: "assets/icons/key-63a39ce4.png",
    key_63a39cb1: "assets/icons/key-63a39cb1.png",
    key_63a71ed2: "assets/icons/key-63a71ed2.png",
    key_5ad5d205: "assets/icons/key-5ad5d205.png",
    key_5ad72171: "assets/icons/key-5ad72171.png",
    key_5ad5cfbd: "assets/icons/key-5ad5cfbd.png",
    key_63a39667: "assets/icons/key-63a39667.png",
    key_5c1e2a1e: "assets/icons/key-5c1e2a1e.png",
    key_5c1e2d1f: "assets/icons/key-5c1e2d1f.png",
    key_6939948d: "assets/icons/key-6939948d.png",
    key_59381445: "assets/icons/key-59381445.png",
    key_61a6446f: "assets/icons/key-61a6446f.png",
    valuable_folder: "assets/icons/val-folder.png"
  };

  /** 贴图版图标：坐标同手画图标（±8 屏幕像素），外面乘 unit、靠父级 scale(1/z) 保持屏幕大小恒定 */
  function pngIcon(key, unit) {
    var g = svgEl("g", { class: "emk-png emk-png-" + key, transform: "scale(" + unit + ")" });
    g.appendChild(pngImage(key));
    return g;
  }

  /** 左侧图例里的同款贴图图标：内联 <svg>（HTML 元素） */
  function pngIconSvg(key) {
    var svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("class", "emk-png ico-dot emk-png-" + key);
    svg.setAttribute("viewBox", "-8-8 16 16");
    svg.setAttribute("width", "15");
    svg.setAttribute("height", "15");
    svg.appendChild(pngImage(key));
    return svg;
  }

  function pngImage(key) {
    return svgEl("image", {
      href: ICON_PNG[key], x: -8, y: -8, width: 16, height: 16,
      preserveAspectRatio: "xMidYMid meet"
    });
  }

  /** 给 HTML 文案（如「需要钥匙：…」）前面贴一个内联图标的小容器 */
  function inlineIcon(key) {
    var span = document.createElement("span");
    span.className = "inline-ico";
    if (key && ICON_PNG[key]) { span.appendChild(pngIconSvg(key)); }
    return span;
  }

  /**
   * 详情行 / 浮窗行前面的内联图标：字符串按图标表取贴图（钥匙那种），
   * 已经画好的 SVG 元素（物资容器 / 高级资源点那套手画图标）直接塞进去。
   */
  function inlineIconAny(value) {
    if (typeof value === "string") { return inlineIcon(value); }
    var span = document.createElement("span");
    span.className = "inline-ico";
    if (value) { span.appendChild(value); }
    return span;
  }

  // ---------------------------------------------------------------- 物资图标
  /**
   * 物资点的小图标：形状贴近实物（保险箱有转盘、工具箱有提手、尸体是骷髅…）。
   * 坐标以原点为中心、单位是「屏幕像素」（约 -8…8），外面统一乘 unit（=1/fit）
   * 换算成底图用户单位；再靠父级 transform 里的 scale(1/z) 让图标在屏幕上大小恒定。
   * 形状分三类：body（类别配色，--c 由 JS 注入）、mark（浅色高光/标识）、hole（深色缝隙）。
   */
  var LOOT_ICONS = {
    safe: [
      { t: "rect", x: -6.4, y: -7, w: 12.8, h: 14, r: 1.2, c: "body" },
      { t: "circle", cx: 0, cy: -0.4, r: 2.4, c: "mark" },
      { t: "rect", x: 4.2, y: -1.6, w: 1.3, h: 3.2, r: 0.4, c: "hole" }
    ],
    jacket: [
      { t: "path", d: "M-2.2-7h4.4l4.6 2.4-1.7 3.8-2.1-1v9.8h-6v-9.8l-2.1 1-1.7-3.8z", c: "body" },
      { t: "path", d: "M0-6.4v9.2", c: "mark", thin: true }
    ],
    pcblock: [
      { t: "rect", x: -5, y: -7, w: 10, h: 14, r: 1, c: "body" },
      { t: "rect", x: -2.6, y: -5, w: 5.2, h: 1.2, r: 0.4, c: "mark" },
      { t: "rect", x: -2.6, y: -2.6, w: 5.2, h: 1.2, r: 0.4, c: "mark" },
      { t: "circle", cx: 0, cy: 3.4, r: 1.7, c: "hole" }
    ],
    scavbody: [
      { t: "path", d: "M0-6.6c-3.7 0-6.1 2.4-6.1 5.5 0 2.2 1.2 3.5 2.7 4.2l.4 3.5h6l.4-3.5c1.5-.7 2.7-2 2.7-4.2 0-3.1-2.4-5.5-6.1-5.5z", c: "body" },
      { t: "circle", cx: -2.3, cy: -0.6, r: 1.7, c: "hole" },
      { t: "circle", cx: 2.3, cy: -0.6, r: 1.7, c: "hole" },
      { t: "rect", x: -1.5, y: 3.2, w: 3, h: 1.2, r: 0.3, c: "hole" }
    ],
    drawer: [
      { t: "rect", x: -6, y: -4.6, w: 12, h: 9.2, r: 0.8, c: "body" },
      { t: "rect", x: -6, y: 1.2, w: 12, h: 1.1, c: "hole" },
      { t: "rect", x: -1.8, y: 2.9, w: 3.6, h: 1.3, r: 0.4, c: "mark" }
    ],
    duffle: [
      { t: "rect", x: -6.6, y: -3, w: 13.2, h: 8.6, r: 2.6, c: "body" },
      { t: "path", d: "M-2.6-3v-1.1a2.6 2.6 0 0 1 5.2 0v1.1", c: "mark", thin: true },
      { t: "path", d: "M-6.2-0.2h12.4", c: "hole", thin: true }
    ],
    cache: [
      { t: "rect", x: -4.4, y: -3.4, w: 8.8, h: 9.4, r: 1.4, c: "body" },
      { t: "ellipse", cx: 0, cy: -3.4, rx: 4.4, ry: 1.6, c: "mark" },
      { t: "path", d: "M-7.6 7.6c2.1-1.9 4.2-2.8 7.6-2.8s5.5.9 7.6 2.8", c: "hole", thin: true }
    ],
    med: [
      { t: "rect", x: -6, y: -4.4, w: 12, h: 9, r: 1.6, c: "body" },
      { t: "path", d: "M-2.8-4.4v-1.2a2.8 2.8 0 0 1 5.6 0v1.2", c: "mark", thin: true },
      { t: "path", d: "M-1.1-2.8h2.2v2.2h2.2v2.2h-2.2v2.2h-2.2V1.6h-2.2V-0.6h2.2z", c: "mark" }
    ],
    supply: [
      { t: "rect", x: -6.2, y: -4.8, w: 12.4, h: 9.6, r: 0.7, c: "body" },
      { t: "rect", x: -6.2, y: -6.6, w: 12.4, h: 1.9, r: 0.5, c: "mark" },
      { t: "path", d: "M-6.2-1h12.4M-.6-4.8v9.6", c: "hole", thin: true }
    ],
    suitcase: [
      { t: "rect", x: -6.6, y: -3.6, w: 13.2, h: 8.4, r: 1.6, c: "body" },
      { t: "path", d: "M-2.2-3.6v-1.2a2.2 2.2 0 0 1 4.4 0v1.2", c: "mark", thin: true },
      { t: "path", d: "M-3.4-3.6v8.4M3.4-3.6v8.4", c: "hole", thin: true }
    ],
    toolbox: [
      { t: "rect", x: -6.2, y: -2.4, w: 12.4, h: 7.6, r: 1, c: "body" },
      { t: "rect", x: -6.2, y: -5, w: 12.4, h: 2.6, r: 1, c: "mark" },
      { t: "path", d: "M-2.4-5v-1a2.4 2.4 0 0 1 4.8 0v1", c: "hole", thin: true },
      { t: "rect", x: -1.1, y: 0.4, w: 2.2, h: 1.6, r: 0.4, c: "hole" }
    ],
    register: [
      { t: "rect", x: -6.2, y: -1.2, w: 12.4, h: 7.6, r: 0.8, c: "body" },
      { t: "rect", x: -5.4, y: -6.4, w: 10.8, h: 5.4, r: 0.8, c: "mark" },
      { t: "rect", x: -3.8, y: -5.4, w: 7.6, h: 2.2, r: 0.3, c: "hole" }
    ],
    grenade: [
      { t: "circle", cx: 0, cy: 0.9, r: 4.5, c: "body" },
      { t: "rect", x: -1.6, y: -5.9, w: 3.2, h: 2.5, r: 0.6, c: "mark" },
      { t: "path", d: "M1.6-5.2l2.9-1.1", c: "mark", thin: true },
      { t: "path", d: "M-4.2 0.9h8.4M0-3.2v8.2", c: "hole", thin: true }
    ],
    weapon: [
      { t: "rect", x: -7, y: -3.6, w: 14, h: 7.2, r: 0.6, c: "body" },
      { t: "rect", x: -7, y: -5.4, w: 14, h: 2.4, r: 0.6, c: "mark" },
      { t: "rect", x: -3.2, y: -4.6, w: 6.4, h: 1.2, r: 0.3, c: "hole" }
    ],
    valuable: [
      { t: "path", d: "M0-7.2L6.2-1.8L0 7.2L-6.2-1.8Z", c: "body" },
      { t: "path", d: "M-6.2-1.8H6.2", c: "mark", thin: true },
      { t: "path", d: "M0-7.2L-2.6-1.8L0 7.2L2.6-1.8Z", c: "hole", thin: true }
    ],
    misc: [
      { t: "rect", x: -5.6, y: -5.6, w: 11.2, h: 11.2, r: 1, c: "body" },
      { t: "path", d: "M-5.6-1.8h11.2M0-5.6v11.2", c: "hole", thin: true }
    ]
  };

  /** 由一个部件定义造出 SVG 节点（物资图标与位置图标共用） */
  function iconPrimitive(s) {
    var node;
    if (s.t === "rect") {
      node = svgEl("rect", { x: s.x, y: s.y, width: s.w, height: s.h, rx: s.r || 0 });
    } else if (s.t === "circle") {
      node = svgEl("circle", { cx: s.cx, cy: s.cy, r: s.r });
    } else if (s.t === "ellipse") {
      node = svgEl("ellipse", { cx: s.cx, cy: s.cy, rx: s.rx, ry: s.ry });
    } else {
      node = svgEl("path", { d: s.d });
    }
    node.setAttribute("class", s.c + (s.thin ? " thin" : ""));
    return node;
  }

  /** 画一个物资图标：返回可直接挂到标记节点上的 <g>（unit 是「1 屏幕像素」对应的用户单位） */
  function lootIcon(group, unit) {
    var key = LOOT_ICONS[group] ? group : CONTAINER_FALLBACK.key;
    if (ICON_PNG[key]) { return pngIcon(key, unit); }
    var g = svgEl("g", { class: "emk-ico emk-ico-" + key, transform: "scale(" + unit + ")" });
    g.style.setProperty("--c", "var(--loot-" + key + ")");
    LOOT_ICONS[key].forEach(function (s) { g.appendChild(iconPrimitive(s)); });
    return g;
  }

  /** 同一套图标也要出现在左侧图例里：返回一个内联 <svg>（HTML 元素） */
  function lootIconSvg(group) {
    var key = LOOT_ICONS[group] ? group : CONTAINER_FALLBACK.key;
    if (ICON_PNG[key]) { return pngIconSvg(key); }
    var svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("class", "emk-ico ico-dot emk-ico-" + key);
    svg.setAttribute("viewBox", "-8-8 16 16");
    svg.setAttribute("width", "15");
    svg.setAttribute("height", "15");
    svg.style.setProperty("--c", "var(--loot-" + key + ")");
    LOOT_ICONS[key].forEach(function (s) { svg.appendChild(iconPrimitive(s)); });
    return svg;
  }

  // ---------------------------------------------------------------- 位置类图标
  /**
   * 出生点 / Boss / 狙击手 / 上锁的门 / BTR / 高级资源点的图标（照参考站款式手画的 SVG，不引第三方素材）。
   * 部件 class 对应 style.css 里的 `.emk-sign .xxx`：solid=主体色、light=浅色、dark=深色、
   * disc/cross=狙击圈与准星、bar/lockbody=挂锁、stroke/line=细描边。
   * 坐标同样是屏幕像素尺度（约 ±7），外面乘 unit 换算，再靠父级 scale(1/z) 保持屏幕上恒定大小。
   */
  var SIGN_ICONS = {
    // 出生点：向下的三角标（照截图）
    spawn: [
      { t: "path", d: "M0 6.6L5.9-5.2H-5.9Z", c: "solid" }
    ],
    // 狙击手 Scav：圆环 + 内嵌 X 的准星
    sniper: [
      { t: "circle", cx: 0, cy: 0, r: 5.6, c: "disc" },
      { t: "path", d: "M-3.3-3.3L3.3 3.3M3.3-3.3L-3.3 3.3", c: "cross" }
    ],
    // Boss：骷髅头（白骨骷髅 + 深色眼窝与鼻孔）
    boss: [
      { t: "path", d: "M0-6.5c-3.6 0-6.2 2.3-6.2 5.4 0 1.9 1 3.4 2.5 4.2l.3 2.6c.05.6.6 1 1.2 1h4.4c.6 0 1.15-.4 1.2-1l.3-2.6c1.5-.8 2.5-2.3 2.5-4.2 0-3.1-2.6-5.4-6.2-5.4z", c: "light" },
      { t: "circle", cx: -2.3, cy: -0.5, r: 1.7, c: "dark" },
      { t: "circle", cx: 2.3, cy: -0.5, r: 1.7, c: "dark" },
      { t: "path", d: "M0 1.9l-1.1 1.9h2.2z", c: "dark" }
    ],
    // 上锁的门 / 汽车后备箱：黄色挂锁 + 深灰锁梁（照截图）
    lock: [
      { t: "path", d: "M-2.7-2.4v-1.6a2.7 2.7 0 0 1 5.4 0v1.6", c: "bar" },
      { t: "rect", x: -5.4, y: -2.4, w: 10.8, h: 8.8, r: 1.4, c: "lockbody" },
      { t: "circle", cx: 0, cy: 1.3, r: 1.3, c: "dark" },
      { t: "rect", x: -0.6, y: 1.9, w: 1.2, h: 2.5, r: 0.4, c: "dark" }
    ],
    // BTR 停靠点：红色八边形（照截图的停车标志）
    btr: [
      { t: "path", d: "M-2.5-6H2.5L6-2.5V2.5L2.5 6H-2.5L-6 2.5V-2.5Z", c: "solid" }
    ],
    // 高级资源点：按物品取各自对应的图标（BTC / 钥匙卡 / 钥匙 / 私酒 / 医疗）
    valuable_btc: [
      { t: "circle", cx: 0, cy: 0, r: 6, c: "solid" },
      { t: "path", d: "M-1.6-3.5v7M-1.6-3.5h2.5a1.75 1.75 0 0 1 0 3.5h-2.5M-1.6 0h3.1a1.75 1.75 0 0 1 0 3.5h-3.1", c: "line" }
    ],
    valuable_keycard: [
      { t: "rect", x: -6, y: -4.2, w: 12, h: 8.4, r: 1.2, c: "solid" },
      { t: "rect", x: -4.7, y: -2.7, w: 3.2, h: 2.6, r: 0.4, c: "dark" },
      { t: "path", d: "M-4.7 2.1h7.4", c: "line" }
    ],
    valuable_key: [
      { t: "circle", cx: -3.6, cy: 0, r: 2.6, c: "stroke" },
      { t: "path", d: "M-1 0h8.5M4.1 0v2.4M6.5 0v2.4", c: "stroke" }
    ],
    valuable_bottle: [
      { t: "rect", x: -2.4, y: -0.8, w: 4.8, h: 6.6, r: 0.9, c: "solid" },
      { t: "rect", x: -1, y: -5, w: 2, h: 4.4, r: 0.3, c: "solid" },
      { t: "rect", x: -1.6, y: -6.4, w: 3.2, h: 1.4, r: 0.5, c: "dark" }
    ],
    valuable_med: [
      { t: "rect", x: -5.6, y: -4.8, w: 11.2, h: 9.6, r: 1.4, c: "solid" },
      { t: "path", d: "M-1.1-2.9h2.2v2.2h2.2v2.2h-2.2v2.2h-2.2V1.5h-2.2V-0.7h2.2z", c: "dark" }
    ],
    // 显卡（2026-10-19 第十一轮新增，无实拍素材，照实物手画）：卡身 + 大风扇 + 散热片 + 金手指
    valuable_gpu: [
      { t: "rect", x: -6.6, y: -4.6, w: 13.2, h: 8.4, r: 0.8, c: "solid" },
      { t: "circle", cx: -1.6, cy: -0.4, r: 3.4, c: "dark" },
      { t: "circle", cx: -1.6, cy: -0.4, r: 0.9, c: "solid" },
      { t: "path", d: "M-1.6-3.8v3.4M1.2-1.3l-2.8 1.4M-4.4-1.3l2.8 1.4", c: "solid" },
      { t: "rect", x: 3.4, y: -2.6, w: 1.8, h: 5.2, r: 0.3, c: "dark" },
      { t: "rect", x: -6.6, y: 3.8, w: 9.4, h: 1.4, r: 0.3, c: "light" }
    ],
    // 兜底：宝石（原来的高级资源点图标）
    valuable: [
      { t: "path", d: "M0-7.2L6.2-1.8L0 7.2L-6.2-1.8Z", c: "solid" },
      { t: "path", d: "M-6.2-1.8H6.2", c: "line" }
    ]
  };

  // 只有高级资源点自带配色（同一个图层里按物品区分）；出生点/Boss/挂锁/BTR 的颜色由图层的 CSS 规则给
  var SIGN_COLORS = {
    valuable_btc: "#f0b93c",
    valuable_keycard: "#7fb6e8",
    valuable_key: "#d8c05a",
    valuable_bottle: "#c98f3c",
    valuable_gpu: "#8ab6a0",
    valuable_med: "#d4788a",
    valuable: "var(--loot-valuable)"
  };

  // 具体钥匙名 → 专属图标（中文物品名精确匹配，2026-10-18 从 wiki 截图逐行抠出）。
  // 在 VALUABLE_ICON_RULES 的同一价值层里优先命中，让「公寓管理员钥匙」这类有实物图的
  // 直接贴真图，而不是退化成通用钥匙。key 名 = "key_" + 物品 id 前 8 位（见 ICON_PNG）。
  var KEY_ICONS = {
    "工厂紧急出口钥匙": "key_5448ba0b",
    "宿舍118房间钥匙": "key_5672c92d",
    "宿舍306房间钥匙": "key_5780cda0",
    "宿舍315房间钥匙": "key_5780cf69",
    "宿舍308房间钥匙": "key_5780cf72",
    "宿舍楼 314 房间符号钥匙": "key_5780cf7f",
    "宿舍214房间钥匙": "key_5780cf94",
    "宿舍218房间钥匙": "key_5780cf9e",
    "宿舍220房间钥匙": "key_5780cfa5",
    "海关 Tarcone 主管办公室钥匙": "key_5780d053",
    "隔间钥匙": "key_5780d065",
    "集装箱宿舍钥匙": "key_5780d07a",
    "拖车停车场工棚钥匙": "key_5913611c",
    "宿舍门卫室钥匙": "key_59136a44",
    "宿舍110房间钥匙": "key_59136e1e",
    "宿舍105房间钥匙": "key_591382d9",
    "宿舍104房间钥匙": "key_591383f1",
    "加油站储藏室钥匙": "key_5913877a",
    "军事基地检查站钥匙": "key_59139158",
    "宿舍108房间钥匙": "key_59145780",
    "宿舍204房间钥匙": "key_59148c8a",
    "ZB-014钥匙": "key_591afe01",
    "机械钥匙": "key_5937ee64",
    "宿舍203房间钥匙": "key_59385041",
    "宿舍206房间钥匙": "key_5938603e",
    "宿舍114房间钥匙": "key_59387a49",
    "宿舍103房间钥匙": "key_59389945",
    "未知钥匙": "key_593962ca",
    "宿舍303房间钥匙": "key_593aa4be",
    "疗养院西楼 104 办公室钥匙": "key_5a0dc455",
    "疗养院西楼 112 办公室钥匙": "key_5a0dc95c",
    "疗养院东楼 107 办公室钥匙": "key_5a0ea647",
    "疗养院杂物间钥匙": "key_5a0ea79b",
    "SMW车钥匙": "key_5a0eb38b",
    "别墅后门钥匙": "key_5a0eb6ac",
    "疗养院西楼 205 房间钥匙": "key_5a0ec6d2",
    "疗养院西楼 216 房间钥匙": "key_5a0ee307",
    "疗养院西楼 220 房间钥匙": "key_5a0ee345",
    "疗养院西楼 221 房间钥匙": "key_5a0ee37f",
    "疗养院东楼 206 房间钥匙": "key_5a0ee4b5",
    "疗养院东楼 310 房间钥匙": "key_5a0eec96",
    "疗养院东楼 313 房间钥匙": "key_5a0eecf6",
    "疗养院东楼 314 房间钥匙": "key_5a0eed43",
    "疗养院东楼 328 房间钥匙": "key_5a0eee14",
    "疗养院西楼 218 房间钥匙": "key_5a13eebd",
    "疗养院西楼 219 房间钥匙": "key_5a13ef06",
    "疗养院西楼 301 房间钥匙": "key_5a13ef7e",
    "疗养院东楼 222 房间钥匙": "key_5a13f241",
    "疗养院东楼 226 房间钥匙": "key_5a13f352",
    "疗养院西楼 306 房间钥匙": "key_5a13f463",
    "疗养院东楼 205 房间钥匙": "key_5a144bdb",
    "疗养院西楼 203 房间钥匙": "key_5a144dfd",
    "疗养院西楼 222 房间钥匙": "key_5a1452ee",
    "疗养院东楼 306 房间钥匙": "key_5a145d47",
    "疗养院东楼 308 房间钥匙": "key_5a145d7b",
    "疗养院东楼 316 房间钥匙": "key_5a145ebb",
    "OLI管理员办公室钥匙": "key_5ad5ccd1",
    "变电站杂物间钥匙": "key_5ad5d498",
    "药房钥匙": "key_5ad5d644",
    "Kiba 商店外门钥匙": "key_5ad5d7d2",
    "EMERCOM医疗区钥匙": "key_5ad5db37",
    "IDEA收银机钥匙": "key_5ad7242b",
    "Kiba 商店内侧格栅门钥匙": "key_5addaffe",
    "TerraGroup 实验室军械库钥匙": "key_5c1f79a0",
    "TerraGroup实验室访问钥匙卡": "key_5c94bbff",
    "RB-BK 符号钥匙": "key_5d80c60f",
    "RB-VO 符号钥匙": "key_5d80c62a",
    "RB-MP11钥匙": "key_5d80c930",
    "RB-MP12钥匙": "key_5d80c959",
    "RB-MP21钥匙": "key_5d80ca90",
    "RB-PSP1钥匙": "key_5d80cb38",
    "RB-PSV1钥匙": "key_5d80cb56",
    "RB-MP13钥匙": "key_5d80cbd8",
    "RB-ORB1钥匙": "key_5d80ccac",
    "RB-ORB2钥匙": "key_5d80ccdd",
    "RB-ORB3钥匙": "key_5d80cd1a",
    "水电站仓库钥匙": "key_5d8e15b6",
    "RB-SMP钥匙": "key_5d947d38",
    "RB-KSM钥匙": "key_5d947d4e",
    "USEC 仓库钥匙": "key_5da743f5",
    "ULTRA 医疗仓库钥匙": "key_5e42c715",
    "RB-PKPM 符号钥匙": "key_5ede7a82",
    "RB-RLSA 钥匙": "key_5ede7b0c",
    "粘有胶带的疗养院办公室钥匙": "key_5eff09cd",
    "灯塔便利店储藏室": "key_61a64428",
    "山边小屋钥匙": "key_61a6444b",
    "叛乱USEC仓库钥匙": "key_61a64492",
    "灯塔警用卡车驾驶室钥匙": "key_61aa5aed",
    "Merin小轿车后备箱钥匙": "key_61aa5b51",
    "USEC灯塔一号保险箱钥匙": "key_61aa5b7d",
    "USEC灯塔二号保险箱钥匙": "key_61aa5ba8",
    "叛乱USEC工作间钥匙": "key_61aa81fc",
    "雷达站指挥室钥匙": "key_62987c65",
    "会议室钥匙": "key_62987cb9",
    "手术室钥匙": "key_62987da9",
    "变电站符号钥匙": "key_62987dfc",
    "污水处理厂储藏室钥匙": "key_62987e26",
    "叛乱USEC营房钥匙": "key_62a9cb93",
    "备用藏身处钥匙": "key_6398fd8a",
    "车行封闭区域钥匙": "key_63a397d3",
    "车行负责人办公室钥匙": "key_63a39919",
    "Concordia 安保处钥匙": "key_63a39c79",
    "Zmeevsky 5公寓20号钥匙": "key_63a39df1",
    "Zmeevsky 3公寓8号钥匙": "key_63a39dfe",
    "Primorsky 46-48号天桥钥匙": "key_63a39e1d",
    "Chekannaya 15号公寓钥匙": "key_63a39fc0",
    "货物网格门钥匙": "key_63a39fdf",
    "废弃工厂符号钥匙": "key_63a3a93f",
    "Concordia 8号公寓钥匙": "key_63a71e78",
    "Primorsky 48 公寓钥匙": "key_63a71eb5",
    "Concordia34号公寓房间钥匙": "key_64ccc1d4",
    "Concordia 8号公寓家庭影院钥匙": "key_64ccc1ec",
    "TerraGroup会议室钥匙": "key_64ccc206",
    "X光检查室钥匙": "key_64ccc246",
    "神秘房间符号钥匙": "key_64ccc25f",
    "\"Aspect\"公司办公区钥匙": "key_64ce5723",
    "生锈的带血钥匙": "key_64d4b23d",
    "Unity Credit银行现金收纳机钥匙": "key_65819980",
    "地下停车场杂物间钥匙": "key_65819997",
    "TerraGroup科学家办公室钥匙": "key_658199aa",
    "休息室钥匙": "key_6582dbf0",
    "USEC小屋房间钥匙": "key_66265d7b",
    "Shatun的藏身处钥匙": "key_664d3db6",
    "Grumpy的藏身处钥匙": "key_664d3dd5",
    "Voron的藏身处钥匙": "key_664d3ddf",
    "Leon的藏身处钥匙": "key_664d3de8",
    "公寓管理员钥匙": "key_664d4b01",
    "TerraGroup 仓库钥匙卡": "key_66acd670",
    "旧屋钥匙": "key_6761a6cc",
    "公司主管办公室钥匙": "key_6761a6f9",
    "Knossos LLC 设施钥匙": "key_679b9716",
    "TerraGroup 集团公寓钥匙": "key_67ee7680",
    "黑色军团钥匙卡": "key_6866ad38",
    "码头大门钥匙": "key_6866adbe",
    "Cardinal 公寓钥匙": "key_68c165f1",
    "14-4 KORD 站点 K.Arshavin 钥匙卡 (修复)": "key_68cc0987",
    "俄罗斯邮政快递车钥匙": "key_68e63b56",
    "Elektronik 的钥匙": "key_68e95d71",
    "Reshala 窝棚钥匙": "key_68e95f4f",
    "Zmeisky 巷 3 号公寓钥匙": "key_68e960db",
    "邪教受害者公寓钥匙": "key_68e96180",
    "RB-PKPTS 钥匙": "key_68e9654d",
    "灯塔岛藏匿点钥匙": "key_6a8d581f",
    "ZB-1013 钥匙": "key_6aa2f656",
    "检查哨站钥匙": "key_6aa2f730",
    // 两张 Object 钥匙卡此前已用单独的清晰截图抠好，这里直接复用既有图标
    "Object #11SR 钥匙卡": "valuable_card_11sr",
    "Object #21WS 钥匙卡": "valuable_card_21ws",
    "TerraGroup \"蓝色文件夹\" 材料": "valuable_folder",
    // 重新编码后的 A.P. 公寓门锁钥匙卡 (绿) 复用既有的绿卡素材，不另抠图
    "重新编码后的 A.P. 公寓门锁钥匙卡 (绿)": "valuable_card_green",
    // 2026-10-18 第五批：补齐仍缺图的 44 把门钥匙 + 3 把只在高级资源点出现的钥匙
    "RB-AK钥匙": "key_5d80c787",
    "RB-AM钥匙": "key_5d80c88d",
    "RB-AO钥匙": "key_5d80c66d",
    "RB-GN钥匙": "key_5d8e3ecc",
    "RB-KORL钥匙": "key_5d8e0db5",
    "RB-KPRL钥匙": "key_5d8e0e0e",
    "RB-MP22钥匙": "key_5d80cab0",
    "RB-OB钥匙": "key_5d80c6c5",
    "RB-OP钥匙": "key_5d80c8f5",
    "RB-PSP2钥匙": "key_5d95d6fa",
    "RB-PSV2钥匙": "key_5d95d6be",
    "RB-RH钥匙": "key_5da5cdcd",
    "RB-RS钥匙": "key_5da46e38",
    "RB-ST钥匙": "key_5d9f1fa6",
    "RB-TB钥匙": "key_5d80c6fc",
    "VAZ 车钥匙": "key_59136519",
    "折叠车钥匙": "key_59136f6f",
    "Horse饭店厕所钥匙": "key_658199a0",
    "酒店215房间钥匙": "key_63a39f08",
    "楼梯间钥匙": "key_63a39fd1",
    "内务部学院门厅警卫室钥匙": "key_6582dc4b",
    "商店经理钥匙": "key_63a39c69",
    "塔科夫银行现金区钥匙": "key_64ccc211",
    "体育教师办公室钥匙": "key_64ccc268",
    "铁门钥匙": "key_63a39f6e",
    "Concordia 63号公寓钥匙": "key_64ccc1f4",
    "Concordia 64号公寓办公室钥匙": "key_63a71e86",
    "Concordia 64号公寓钥匙": "key_63a71e92",
    "TerraGroup军械库钥匙": "key_64ccc24d",
    "“白鲸”餐厅经理办公室钥匙": "key_64ccc1fe",
    "\"调解室\"钥匙": "key_6582dbe4",
    "不动产管理处办公室钥匙": "key_6582dc57",
    "档案室钥匙": "key_63a39e49",
    "供应部门主管办公室钥匙": "key_63a39ce4",
    "建筑工地工棚钥匙": "key_63a39cb1",
    "金融办公室小房间钥匙": "key_63a71ed2",
    "OLI超市杂物间钥匙": "key_5ad5d205",
    "OLI收银机钥匙": "key_5ad72171",
    "OLI物流部钥匙": "key_5ad5cfbd",
    "金融办公室钥匙": "key_63a39667",
    "TerraGroup 实验室经理办公室钥匙": "key_5c1e2a1e",
    "TerraGroup 实验室武器测试区域钥匙": "key_5c1e2d1f",
    "旧屋厕所钥匙": "key_6939948d",
    "简易工棚钥匙": "key_59381445",
    "冷库钥匙": "key_61a6446f"
  };

  // 高级资源点的物品名 → 图标。**按价值从高到低分层匹配**（2026-10-19 第十一轮改）：
  // 同一个刷点常常同时刷几种物品（如「私酒 + 某把钥匙」「LEDX + 除颤器」），旧逻辑「先查钥匙精确表、
  // 再按正则首命中」会让价值低的物品抢到图标——私酒点画成钥匙点、LEDX 点画成除颤器。
  // 现在改成：外层按价值从高到低遍历规则，内层扫物品名，命中即止；同层里若有该物品的专属素材图
  // （KEY_ICONS）就贴真图，否则用该层的通用图标。
  var VALUABLE_ICON_RULES = [
    // 硬通货 / 单件高价值（最值钱的放最前）
    [/比特币|BTC/i, "valuable_btc"],
    [/私酒|酒/, "valuable_bottle"],
    [/显卡|显示卡/, "valuable_gpu"],
    // 医疗类：LEDX 比除颤器值钱，必须排在除颤器前面
    [/LEDX|透照|注射/, "valuable_med"],
    [/除颤/, "valuable_defib"],
    // 六色钥匙卡 + 黑卡 + 生活区 + Object 两张卡，各自用对应颜色的素材图标
    [/实验室钥匙卡·黄/, "valuable_card_yellow"],
    [/实验室钥匙卡·红/, "valuable_card_red"],
    [/实验室钥匙卡·绿/, "valuable_card_green"],
    [/实验室钥匙卡·蓝/, "valuable_card_blue"],
    [/实验室钥匙卡·紫/, "valuable_card_purple"],
    [/实验室钥匙卡·黑/, "valuable_card_black"],
    [/生活区/, "valuable_card_living"],
    [/Object #11SR/i, "valuable_card_11sr"],
    [/Object #21WS/i, "valuable_card_21ws"],
    // 剩下的钥匙卡（无专属素材的）统一用黄色卡兜底
    [/钥匙卡/, "valuable_keycard"],
    [/钥匙/, "valuable_key"],
    [/文件夹|材料/, "valuable_folder"]
  ];

  function valuableIconKey(names) {
    var list = names || [];
    for (var r = 0; r < VALUABLE_ICON_RULES.length; r++) {
      for (var i = 0; i < list.length; i++) {
        if (!VALUABLE_ICON_RULES[r][0].test(list[i])) { continue; }
        // 有专属实拍图（KEY_ICONS 精确表）就贴真图，否则用这一层的通用图标
        return KEY_ICONS[list[i]] || VALUABLE_ICON_RULES[r][1];
      }
    }
    // 兜底：物品名对不上任何规则、但有专属素材图的，仍贴真图（如「灯塔便利店储藏室」）
    for (var e = 0; e < list.length; e++) {
      if (KEY_ICONS[list[e]]) { return KEY_ICONS[list[e]]; }
    }
    return "valuable";
  }

  /** 地图上的位置类图标（unit 是「1 屏幕像素」对应的用户单位） */
  function signIcon(key, unit, colorVar) {
    if (ICON_PNG[key]) { return pngIcon(key, unit); }
    var parts = SIGN_ICONS[key] || SIGN_ICONS.valuable;
    var g = svgEl("g", { class: "emk-sign emk-sign-" + key, transform: "scale(" + unit + ")" });
    var color = colorVar || SIGN_COLORS[key];
    if (color) { g.style.setProperty("--c", color); }
    parts.forEach(function (s) { g.appendChild(iconPrimitive(s)); });
    return g;
  }

  /** 左侧图例里的同款位置图标：内联 <svg> */
  function signIconSvg(key, colorVar) {
    if (ICON_PNG[key]) { return pngIconSvg(key); }
    var parts = SIGN_ICONS[key] || SIGN_ICONS.valuable;
    var svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("class", "emk-sign ico-dot emk-sign-" + key);
    svg.setAttribute("viewBox", "-8-8 16 16");
    svg.setAttribute("width", "15");
    svg.setAttribute("height", "15");
    var color = colorVar || SIGN_COLORS[key];
    if (color) { svg.style.setProperty("--c", color); }
    parts.forEach(function (s) { svg.appendChild(iconPrimitive(s)); });
    return svg;
  }

  // ---------------------------------------------------------------- 撤离点徽章
  /**
   * 撤离点 / 转移点的款式（照参考站）：彩色盾牌 + 奔跑小人，下面带名字。
   * 坐标同样是「屏幕像素」尺度（约 ±7），外面统一乘 unit 换算成底图用户单位，
   * 再靠父级 transform 的 scale(1/z) 保证放大缩小都在屏幕上一样大。
   * 颜色由 CSS 的 `.emk-badge-<阵营>` 给，这里只画形状。
   */
  // 撤离点 / 转移点的徽章比别的图层小一圈（玩家反馈），整体放大一档：
  // 徽章与它下面的名字一起乘这个系数，屏幕尺寸恒定的机制不变。
  var BADGE_SCALE = 1.5;
  var BADGE_SHAPE = "M-4.4-6.7h8.8c.6 0 1.1.5 1.1 1.1v3.4c0 3.9-2.3 7.1-5.5 9-3.2-1.9-5.5-5.1-5.5-9v-3.4c0-.6.5-1.1 1.1-1.1z";
  // 小人朝右奔跑：躯干前倾 + 一前一后的手臂与腿（多段子路径，用描边画）
  var BADGE_RUNNER = "M1-1.95L-0.35 0.1M0.95-1.85L2.5-1.2M1-1.9L-1.4-1.05M-0.35 0.1L1.5 1.3L2.35 2.05M-0.35 0.1L-1.25 1.3L-2.1 1.95";

  function badgeChildren() {
    return [
      svgEl("path", { class: "badge-bg", d: BADGE_SHAPE }),
      svgEl("path", { class: "badge-man", d: BADGE_RUNNER }),
      svgEl("circle", { class: "badge-head", cx: 1.45, cy: -2.95, r: 1.1 })
    ];
  }

  /** 地图上的徽章（unit 是「1 屏幕像素」对应的用户单位） */
  function badgeIcon(variant, unit) {
    var scale = unit * BADGE_SCALE;
    var g = svgEl("g", { class: "emk-badge emk-badge-" + variant, transform: "scale(" + scale + ")" });
    badgeChildren().forEach(function (node) { g.appendChild(node); });
    return g;
  }

  /** 左侧图例里的同款徽章：内联 <svg> */
  function badgeIconSvg(variant) {
    var svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("class", "emk-badge ico-dot emk-badge-" + variant);
    svg.setAttribute("viewBox", "-7.6-7.6 15.2 15.2");
    svg.setAttribute("width", "15");
    svg.setAttribute("height", "15");
    badgeChildren().forEach(function (node) { svg.appendChild(node); });
    return svg;
  }

  /** 徽章下面的名字：和参考站一样按阵营着色，字号 / 描边都按 unit 换算，屏幕上恒定 */
  function badgeLabel(text, variant, unit) {
    var size = unit * BADGE_SCALE;
    var tag = svgEl("text", {
      class: "emk-tag emk-tag-" + variant,
      x: 0, y: 9.6 * size,
      "font-size": 11 * size,
      "stroke-width": 2.6 * size,
      "text-anchor": "middle",
      "dominant-baseline": "hanging"
    });
    tag.textContent = text;
    return tag;
  }

  /** 图例每行前面的小图标：物资 / 高级资源点 / 出生点等用图标，撤离点 / 转移点用徽章，其余还是色点 */
  var LEGEND_COLORS = {
    "dot-spawn-player": "var(--spawn-player)",
    "dot-spawn-scav": "var(--spawn-scav)",
    "dot-spawn-pmc": "var(--spawn-pmc)",
    "dot-spawn-sniper": "var(--spawn-sniper)",
    "dot-boss": "var(--boss)",
    "dot-lock": "var(--lock)",
    "dot-btr": "var(--btr)"
  };

  function legendIcon(spec) {
    // spec.icon 优先：高级资源点的每个子类要显各自的图标（BTC 金币 / 私酒瓶 / 钥匙卡 / 钥匙 / 医疗…）
    if (spec.icon) { return signIconSvg(spec.icon, LEGEND_COLORS[spec.dot]); }
    if (spec.kind === "containers") { return lootIconSvg(spec.dot.replace("dot-loot-", "")); }
    if (spec.kind === "valuables") { return signIconSvg("valuable"); }
    if (spec.badge) { return badgeIconSvg(spec.badge); }
    var dot = document.createElement("span");
    dot.className = "dot legend-ico " + spec.dot;
    return dot;
  }

  function makeMarker(map, kind, item, radius, iconKey) {
    var c = map.worldToSvg;
    var sx = c.a * item.x + c.b * item.z + c.c;
    var sy = c.d * item.x + c.e * item.z + c.f;
    var cls = "emk-marker emk-" + kind;
    if (kind === "extracts") { cls += " emk-extract-" + (item.faction || "shared"); }
    if (kind === "containers") { cls += " emk-loot-" + (item.group || CONTAINER_FALLBACK.key); }
    if (kind === "hazards" && item.type) { cls += " emk-hazard-" + token(item.type); }
    var g = svgEl("g", { class: cls });
    g.__emkBase = { sx: sx, sy: sy };
    g.setAttribute("transform", "translate(" + sx + " " + sy + ") scale(1)");
    var unit = 1 / state.fit;         // 1 屏幕像素 = unit 个用户单位
    // 被钉选的类型：在图标／圆点底下垫一圈高亮描边环（画在最前面，避免盖住图标）
    if (isPinnedItem(kind, item)) {
      g.classList.add("emk-pinned");
      g.appendChild(svgEl("circle", {
        class: "emk-pin-ring",
        r: pinRingRadius(kind, radius)
      }));
    }
    if (kind === "extracts" || kind === "transits") {
      // 撤离点 / 转移点：彩色盾牌 + 奔跑小人，下面带名字（照参考站款式）
      var variant = kind === "transits" ? "transit" : (item.faction || "shared");
      g.appendChild(badgeIcon(variant, unit));
      if (item.name) { g.appendChild(badgeLabel(item.name, variant, unit)); }
    } else if (kind === "containers") {
      // 物资点是贴近实物的小图标
      g.appendChild(lootIcon(item.group, unit));
    } else if (kind === "valuables") {
      // 高级资源点按物品取各自对应的图标（BTC / 钥匙卡 / 钥匙 / 私酒 / 医疗…）
      g.appendChild(signIcon(valuableIconKey(item.items), unit));
    } else if (iconKey) {
      // 出生点 / Boss / 狙击手 / 上锁的门 / BTR：位置类图标
      // BTR 停靠点是停车标志，实测偏小，按玩家反馈放大一倍
      g.appendChild(signIcon(iconKey, kind === "btr" ? unit * 2 : unit));
    } else {
      g.appendChild(svgEl("circle", { r: radius }));
    }
    state.markerScaleNodes.push(g);
    return g;
  }

  /** 把上游的任意字符串变成能进 class 的 token（hazardType 之类可能是复合词） */
  function token(text) {
    return String(text).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  }

  /** 钉选高亮环的半径（用户单位）：图标类按外接尺寸，纯圆点按点半径放大 */
  function pinRingRadius(kind, radius) {
    var unit = 1 / state.fit;
    // 撤离 / 转移点的徽章放大后外接半径约 12 屏幕像素
    if (kind === "extracts" || kind === "transits") { return 12 * unit * iconScale(); }
    if (ICON_KINDS.indexOf(kind) !== -1) { return 10 * unit * iconScale(); }
    return radius * 2.6;   // radius 已是「点半径 × unit」，再放大一档
  }

  // ---------------------------------------------------------------- 详情与搜索
  var KIND_LABEL = {
    extracts: "撤离点", transits: "转移点", spawns: "出生点", containers: "物资容器",
    loose: "散落物资", valuables: "高级资源点", hazards: "危险区", artillery: "炮击区",
    locks: "钥匙门", bosses: "Boss 刷新点", btr: "BTR 停靠点", stationary: "固定武器", labels: "地名"
  };
  var FACTION_LABEL = { pmc: "USEC / PMC", scav: "Scav", shared: "通用", all: "全部阵营" };
  var CATEGORY_LABEL = { player: "玩家出生", bot: "AI Scav", botpmc: "AI PMC", boss: "Boss 护卫", sniper: "狙击手" };
  var HAZARD_LABEL = {
    minefield: "雷区", sniper: "狙击区", sniperZone: "狙击区",
    gas: "毒气区", radiation: "辐射区", hazard: "危险区"
  };

  /** 标记的语义化信息行（不含世界坐标/所在层/地图），供小浮窗与左侧详情面板共用 */
  function detailRows(map, kind, item) {
    var rows = [];
    if (item.name) { rows.push(["名称", item.name]); }
    rows.push(["类型", KIND_LABEL[kind] || kind]);

    if (kind === "extracts") {
      rows.push(["阵营", FACTION_LABEL[item.faction] || item.faction || "通用"]);
    } else if (kind === "spawns") {
      rows.push(["阵营", (item.sides || []).map(function (s) { return FACTION_LABEL[s] || s; }).join(" / ") || "未标注"]);
      rows.push(["类别", (item.categories || []).map(function (c) { return CATEGORY_LABEL[c] || c; }).join(" / ") || "未标注"]);
    } else if (kind === "locks") {
      rows.push(["锁类型", item.type === "trunk" ? "汽车后备箱" : "上锁的门"]);
      if (item.needsPower) { rows.push(["需要通电", "是"]); }
      if (item.keyName) {
        rows.push(["需要钥匙", item.keyName + (item.keyShort ? "（" + item.keyShort + "）" : ""),
                   valuableIconKey([item.keyName])]);
      }
      else if (item.key) { rows.push(["钥匙 id", item.key]); }
    } else if (kind === "containers") {
      rows.push(["容器类别", containerLabel(item.group), lootIconSvg(item.group)]);
    } else if (kind === "valuables") {
      if (item.items && item.items.length) {
        // 行首贴该点在地图上用的那颗图标（BTC / 钥匙卡 / 私酒…），浮窗里一眼对得上地图
        rows.push(["可能刷出", item.items.join(" / "), signIconSvg(valuableIconKey(item.items))]);
      }
    } else if (kind === "bosses") {
      if (item.where) { rows.push(["刷新位置", item.where]); }
      if (item.chance !== undefined && item.chance !== null) {
        rows.push(["刷新概率", Math.round(item.chance * 100) + "%"]);
      }
    } else if (kind === "hazards" || kind === "artillery") {
      rows.push(["危险类型", HAZARD_LABEL[item.type] || item.type || KIND_LABEL[kind]]);
      if (item.outline && item.outline.length >= 3) {
        rows.push(["范围", "多边形（" + item.outline.length + " 个顶点）"]);
      }
    }

    return rows;
  }

  function showDetail(map, kind, item, node) {
    state.selected = { kind: kind, item: item };
    var rows = detailRows(map, kind, item);
    rows.push(["世界坐标", "x " + item.x + " ／ z " + item.z +
      (item.y === undefined || item.y === null ? "" : " ／ y " + item.y)]);
    if (item.y !== undefined && item.y !== null && state.floorSet.length) {
      rows.push(["所在层", floorLabel(floorOfPosition(map, item))]);
    }
    rows.push(["地图", map.name]);

    el.detail.innerHTML = "";
    rows.forEach(function (row) {
      var dt = document.createElement("dt");
      dt.textContent = row[0];
      var dd = document.createElement("dd");
      // row[2] 是可选的内联图标（字符串=贴图 key，SVG 元素=手画的物资/资源点图标）
      if (row[2]) { dd.appendChild(inlineIconAny(row[2])); }
      dd.appendChild(document.createTextNode(row[1]));
      el.detail.appendChild(dt);
      el.detail.appendChild(dd);
    });
    el.detailBlock.hidden = false;

    // 选中环：普通标记用点半径；图标 / 徽章没有 r，就按各自的外接尺寸取（屏幕像素换算成用户单位）
    // 被钉选的标记底下垫着高亮环，跳过它再取实际图形
    var first = node && node.firstChild;
    while (first && first.classList && first.classList.contains("emk-pin-ring")) { first = first.nextSibling; }
    var ringR = first && first.getAttribute("r");
    if (first && !ringR) {
      if (kind === "extracts" || kind === "transits") { ringR = 12 * iconScale() / state.fit; }
      else if (ICON_KINDS.indexOf(kind) !== -1) { ringR = 10 * iconScale() / state.fit; }
    }
    if (first && ringR) {
      node.querySelectorAll(".emk-ring").forEach(function (ring) { ring.remove(); });
      var ring = svgEl("circle", { class: "emk-ring", r: ringR });
      node.appendChild(ring);
      window.setTimeout(function () { if (ring.parentNode) { ring.remove(); } }, 3400);
    }
  }

  // ---------------------------------------------------------------- 搜索
  // 搜索按「类型」聚合：同名的点合并成一条（如「物资埋藏桶」= 全图 209 个点合成一条），
  // 结果行可以直接定位、钉选（高亮描边）、加入导航路线。
  // 高级资源点没有 name，改按它可能刷出的物品名（如「实体比特币」）建索引，搜「比特币」即可命中。

  /** 可搜索的图层（出生点 / 散落物资 / 危险区没有名字，不可搜） */
  var SEARCH_KINDS = ["extracts", "transits", "containers", "valuables", "locks", "bosses", "btr", "stationary"];

  /** 某数据项对应的「类型名」：上锁的门用钥匙名、地名用文本，其余用 name */
  function entryNameOf(kind, item) {
    if (kind === "labels") { return item.text; }
    if (kind === "locks") { return item.keyName || item.name; }
    return item.name;
  }

  /** 当前地图的搜索索引：按「类型 + 名字」聚合成条目（与地图绑定，随图切换失效） */
  function searchIndex(map) {
    if (state.searchCache && state.searchCache.mapKey === map.key) { return state.searchCache.entries; }
    var groups = {};
    function add(kind, name, item, sub) {
      if (!name) { return; }
      var key = kind + "|" + name;
      var g = groups[key];
      if (!g) { g = groups[key] = { kind: kind, name: name, count: 0, sample: item, subs: {} }; }
      g.count += 1;
      if (sub) { g.subs[sub] = 1; }
    }
    SEARCH_KINDS.forEach(function (kind) {
      (map.layers[kind] || []).forEach(function (it) {
        if (kind === "valuables") {
          // 高资点一条点里可能列了多种物品，拆成多条按物品名的类型条目
          (it.items || []).forEach(function (nm) { add(kind, nm, it, null); });
          return;
        }
        if (kind === "extracts") { add(kind, it.name, it, FACTION_LABEL[it.faction] || "通用"); return; }
        if (kind === "locks") { add(kind, it.keyName || it.name, it, it.type === "trunk" ? "汽车后备箱" : "上锁的门"); return; }
        add(kind, entryNameOf(kind, it), it, null);
      });
    });
    (map.labels || []).forEach(function (it) { add("labels", it.text, it, null); });

    var entries = [];
    for (var k in groups) { entries.push(groups[k]); }
    state.searchCache = { mapKey: map.key, entries: entries };
    return entries;
  }

  /** 匹配打分：完全相同 0 / 以它开头 1 / 含它 2；不匹配 -1 */
  function scoreMatch(name, query) {
    var n = name.toLowerCase();
    if (n === query) { return 0; }
    if (n.indexOf(query) === 0) { return 1; }
    if (n.indexOf(query) !== -1) { return 2; }
    return -1;
  }

  function renderSearchResults() {
    var map = state.map;
    if (!map) { return; }
    var query = el.search.value.trim().toLowerCase();
    el.searchResults.innerHTML = "";
    if (!query) { el.searchResults.hidden = true; return; }

    var hits = [];
    searchIndex(map).forEach(function (entry) {
      var score = scoreMatch(entry.name, query);
      if (score >= 0) { hits.push({ entry: entry, score: score }); }
    });
    hits.sort(function (a, b) {
      if (a.score !== b.score) { return a.score - b.score; }
      if (a.entry.count !== b.entry.count) { return b.entry.count - a.entry.count; }
      return a.entry.name < b.entry.name ? -1 : 1;
    });
    var shown = hits.slice(0, 30);

    if (!shown.length) {
      var empty = document.createElement("div");
      empty.className = "search-empty";
      empty.textContent = "没有匹配的标记";
      el.searchResults.appendChild(empty);
      el.searchResults.hidden = false;
      return;
    }

    shown.forEach(function (hit) { el.searchResults.appendChild(searchRow(hit.entry)); });
    el.searchResults.hidden = false;
  }

  /** 结果行的副标题：类型 + 子类（物资类别 / 撤离阵营…）+ 该类型在全图的点数 */
  function entrySubtitle(entry) {
    var text = KIND_LABEL[entry.kind] || entry.kind;
    var subs = [], s;
    for (s in entry.subs) { subs.push(s); }
    if (subs.length) { text += " · " + subs.join(" / "); }
    return text + " · " + entry.count + " 处";
  }

  /** 构造一条搜索结果：主按钮（定位）+ 钉选 + 加入路线 */
  function searchRow(entry) {
    var row = document.createElement("div");
    row.className = "search-item";

    var hit = document.createElement("button");
    hit.type = "button";
    hit.className = "search-hit";
    var name = document.createElement("span");
    name.className = "s-name";
    name.textContent = entry.name;
    var kind = document.createElement("span");
    kind.className = "kind";
    kind.textContent = entrySubtitle(entry);
    hit.appendChild(name);
    hit.appendChild(kind);
    hit.addEventListener("click", function () { focusEntry(entry); });
    row.appendChild(hit);

    var pinned = hasPin(entry.kind, entry.name);
    var pin = document.createElement("button");
    pin.type = "button";
    pin.className = "search-act search-pin" + (pinned ? " on" : "");
    pin.textContent = pinned ? "已钉" : "钉选";
    pin.title = pinned ? "取消钉选" : "钉选：地图上该类型的图标高亮描边";
    pin.addEventListener("click", function (ev) {
      ev.stopPropagation();
      enableLayersFor(entry.kind, entry.sample);   // 先让目标图层可见，钉选的高亮才有东西可描
      togglePin(entry.kind, entry.name);
    });
    row.appendChild(pin);

    var route = document.createElement("button");
    route.type = "button";
    route.className = "search-act search-route";
    route.textContent = "路线";
    route.title = "把该点加入导航路线";
    route.addEventListener("click", function (ev) {
      ev.stopPropagation();
      addRoutePoint(entry.kind, entry.name, entry.sample);
    });
    row.appendChild(route);

    return row;
  }

  /** 点搜索结果的「类型」条目：定位到它的第一个点并打开详情 */
  function focusEntry(entry) {
    focusItem({ kind: entry.kind, name: entry.name, item: entry.sample });
  }

  /** 打开命中某个数据项所需的图层开关（搜索结果定位 / 钉选时共用）；返回是否发生了改动 */
  function enableLayersFor(kind, item) {
    var specs = specItemsOfKind(kind).filter(function (spec) {
      // 总开关（高级资源点）不参与：它只是子类的汇总，勾上它并不会让某个点出现
      return !spec.master && (!spec.where || spec.where(item));
    });
    if (!specs.length) { specs = [{ key: kind }]; }
    var changed = false;
    specs.forEach(function (spec) {
      if (state.layers[spec.key]) { return; }
      state.layers[spec.key] = true;
      var box = document.querySelector('#layer-toggles input[data-layer="' + spec.key + '"]');
      if (box) { box.checked = true; }
      changed = true;
    });
    if (changed) {
      try { localStorage.setItem(LS_LAYERS, JSON.stringify(state.layers)); } catch (e) { /* 忽略 */ }
      syncLegendState();
      renderOverlay();
    }
    return changed;
  }

  function focusItem(hit) {
    var map = state.map;
    // 目标图层若被关闭则自动打开，否则用户会“找不到”搜出来的东西
    var turnedOn = enableLayersFor(hit.kind, hit.item);

    // 搜到的标记若在别的楼层，跟着切过去，否则过滤模式下面它还是看不见
    if (!isItemVisible(map, hit.item, hit.kind)) {
      var floor = floorOfPosition(map, hit.item);
      if (floor) { setFloors([floor], "搜索跳转：" + floorLabel(floor)); }
    } else if (turnedOn) {
      renderOverlay();
    }

    var node = findMarkerNode(map, hit);
    if (node) { centerOnPoint(node.__emkBase.sx, node.__emkBase.sy); }
    else {
      var sx = svgX(map, hit.item.x, hit.item.z);
      var sy = svgY(map, hit.item.x, hit.item.z);
      centerOnPoint(sx, sy);
    }
    if (hit.kind === "labels") { showDetail(map, "labels", { name: hit.item.text, x: hit.item.x, z: hit.item.z }, null); }
    else { showDetail(map, hit.kind, hit.item, node); }
  }

  function findMarkerNode(map, hit) {
    var nodes = el.overlay.querySelectorAll(".emk-" + hit.kind + " .emk-marker");
    var sx = svgX(map, hit.item.x, hit.item.z);
    var sy = svgY(map, hit.item.x, hit.item.z);
    for (var i = 0; i < nodes.length; i++) {
      // 先按数据项身份认（同一坐标可能有多个标记），认不到再退回坐标比对
      if (nodes[i].__emkHit && nodes[i].__emkHit.item === hit.item) { return nodes[i]; }
    }
    for (var j = 0; j < nodes.length; j++) {
      var b = nodes[j].__emkBase;
      if (b && Math.abs(b.sx - sx) < 0.01 && Math.abs(b.sy - sy) < 0.01) { return nodes[j]; }
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

  /** 点位自动居中开关（原「跟随」；与启动器里的同名勾选共用一份偏好）
   *
   * `persist` 只为「点 HUD 按钮」这条路径而设：拖图也会切到锁定视角，
   * 但那只是当下的临时动作，不该把「自动居中＝关」永久写进配置（下次启动就不再跟随）。
   */
  function setAutoCenter(on, persist) {
    if (state.autoCenter === on) { return; }
    state.autoCenter = on;
    try { localStorage.setItem(LS_FOLLOW, on ? "1" : "0"); } catch (e) { /* 隐私模式忽略 */ }
    syncCenterButton();
    if (on) { centerOnPlayer(); }
    if (persist) { queuePrefs({ auto_center: on }); }
  }

  function syncCenterButton() {
    if (!el.centerBtn) { return; }
    el.centerBtn.classList.toggle("on", state.autoCenter);
    el.centerBtn.textContent = state.autoCenter ? "自动居中" : "已锁定";
    el.centerBtn.title = state.autoCenter
      ? "实时定位自动居中（拖动地图会切到「已锁定」按手动视角）"
      : "已手动锁定视角，点击恢复自动居中到玩家位置";
  }

  function centerOnPlayer() {
    if (!state.map || !state.player) { return; }
    centerOnPoint(svgX(state.map, state.player.x, state.player.z),
                  svgY(state.map, state.player.x, state.player.z));
  }

  // ---------------------------------------------------------------- 启动器配置
  /** 先问一次 `/api/config`，再订阅 SSE 的 `config` 事件（启动器里改开关会立刻生效） */
  function initConfig() {
    fetch("api/config", { cache: "no-store" }).then(function (res) {
      return res.ok ? res.json() : null;
    }).then(function (payload) {
      if (payload) { applyConfig(payload); }
    }).catch(function () { /* 无服务时保留本地偏好 */ });
  }

  function applyConfig(payload) {
    var cfg = payload && payload.config;
    if (!cfg) { return; }
    state.cfg = cfg;
    state.autoZoom = !!cfg.auto_zoom;
    // auto_center 只在服务端值「真的变了」时才覆盖本地视角：否则每次写回图层偏好都会广播一次
    // config，把用户刚拖图锁定的视角又弹回玩家位置（本地视角与磁盘值本就可能是不同步的）。
    var serverAuto = !!cfg.auto_center;
    if (state.cfgAutoCenter !== serverAuto) {
      state.cfgAutoCenter = serverAuto;
      setAutoCenter(serverAuto);
    }
    state.sound = cfg.sound || null;
    applyUiPrefs(cfg.ui);          // 页面保存的图层 / 楼层偏好
    // 注意：这里**不能**再调 applyAutoZoom()。配置事件（含页面自己写回图层偏好）与截图无关，
    // 一调就会把用户刚拖好的视角弹回玩家位置（2026-10-19 第十一轮修）。定位只由「新截图」触发，见 applyPosition。
  }

  // ---------------------------------------------------------------- 日志监控
  /** 战局事件与任务事件（自动切图、事件流、提示音） */
  function initLogs() {
    fetch("api/logstate", { cache: "no-store" }).then(function (res) {
      return res.ok ? res.json() : null;
    }).then(function (payload) {
      if (payload) { applyLogState(payload); }
    }).catch(function () { /* 无服务时静默 */ });

    if (!state.events) {
      el.raidStatus.textContent = "日志监控不可用（未启用本地服务或浏览器不支持 SSE）";
      return;
    }
    state.events.addEventListener("state", function (ev) {
      applyLogState(parse(ev));
    });
    state.events.addEventListener("config", function (ev) {
      applyConfig(parse(ev));
    });
    state.events.addEventListener("raid", function (ev) {
      applyRaidEvent(parse(ev));
    });
    state.events.addEventListener("quest", function (ev) {
      applyQuestEvent(parse(ev));
    });
    state.events.addEventListener("shot", function (ev) {
      renderShotStatus(parse(ev));
    });
    state.events.addEventListener("clean", function (ev) {
      renderCleanStatus(parse(ev));
    });
  }

  function parse(ev) {
    try { return JSON.parse(ev.data); } catch (e) { return null; }
  }

  /** `/api/logstate` 与 SSE `state` 事件：日志跟随状态 + 已累积的战局/任务 */
  function applyLogState(payload) {
    if (!payload) { return; }
    state.logs = {
      available: !!payload.available,
      reason: payload.reason || null,
      session: payload.session || null,
      gameDir: payload.gameDir || null,
      logDir: payload.logDir || null
    };
    if (payload.raid) { state.raid = mergeRaid(payload.raid); }
    if (payload.shot) { renderShotStatus(payload.shot); }
    if (payload.clean) { renderCleanStatus(payload.clean); }
    if (payload.quests && payload.quests.length) {
      state.quests = payload.quests.slice(-QUEST_LOG_MAX).reverse();
      recountQuests();
    }
    renderRaidPanel();
    renderQuestLog();
  }

  function mergeRaid(ev) {
    var prev = state.raid || {};
    var mapId = ev.mapId || prev.mapId || null;
    return {
      phase: ev.phase || prev.phase || null,
      mapId: mapId,
      mapKey: resolveMapKey(mapId),
      raidId: ev.raidId || prev.raidId || null,
      ts: ev.ts || prev.ts || null
    };
  }

  /** 日志里的地图 id → 本项目收录的地图 key；没收录（或本工具没有这张图）返回 null */
  function resolveMapKey(mapId) {
    if (!mapId) { return null; }
    var key = MAP_ID_ALIASES[String(mapId).toLowerCase()];
    if (!key) { return null; }
    // 地图数组还没载入时先按约定映射，等数据到位后由 onMapsLoaded 复核一次
    if (!state.mapsLoaded) { return key; }
    for (var i = 0; i < state.maps.length; i++) {
      if (state.maps[i].key === key) { return key; }
    }
    return null;
  }

  /** 地图数据到位后复核战局状态：日志事件可能比 data/maps.json 先到 */
  function onMapsLoaded() {
    if (!state.raid) { renderRaidPanel(); return; }
    state.raid.mapKey = resolveMapKey(state.raid.mapId);
    if (state.raid.mapKey && (state.raid.phase === "map" || state.raid.phase === "loading" ||
                              state.raid.phase === "start")) {
      autoSwitchMap(state.raid.mapKey);
    } else if (state.raid.mapId && !state.raid.mapKey) {
      state.raidNote = "识别到地图「" + state.raid.mapId + "」，但本工具没有收录这张图的底图，请手动选择。";
    }
    renderRaidPanel();
  }

  function applyRaidEvent(ev) {
    if (!ev) { return; }
    state.raidNote = "";
    // 新一轮匹配/出生 = 本局开始，本局计数归零
    if (ev.phase === "matching" || ev.phase === "start") {
      state.questCounts = { started: 0, completed: 0 };
    }
    state.raid = mergeRaid(ev);

    if (ev.phase === "map") {
      if (state.raid.mapKey) {
        autoSwitchMap(state.raid.mapKey);
      } else {
        state.raidNote = "识别到地图「" + ev.mapId + "」，但本工具没有收录这张图的底图，请手动选择。";
      }
    }

    playPrompt(ev.phase);      // matching / location_loading / start 三种提示音
    renderRaidPanel();
    renderQuestLog();
  }

  /** 进图自动切图：已在该图则不重复切换（避免把用户的视角重置掉） */
  function autoSwitchMap(key) {
    if (state.map && state.map.key === key) { return; }
    var item = null;
    for (var i = 0; i < state.maps.length; i++) { if (state.maps[i].key === key) { item = state.maps[i]; } }
    if (!item) { return; }
    selectMap(item.key);
    state.raidNote = "已按日志自动切换到《" + item.name + "》";
  }

  function applyQuestEvent(ev) {
    if (!ev || (ev.action !== "started" && ev.action !== "completed" && ev.action !== "failed")) { return; }
    state.quests.unshift(ev);
    if (state.quests.length > QUEST_LOG_MAX) { state.quests.length = QUEST_LOG_MAX; }
    if (ev.action === "started") { state.questCounts.started += 1; }
    else if (ev.action === "completed") { state.questCounts.completed += 1; }
    renderQuestLog();
    renderRaidPanel();
  }

  function recountQuests() {
    state.questCounts = { started: 0, completed: 0 };
    for (var i = 0; i < state.quests.length; i++) {
      if (state.quests[i].action === "started") { state.questCounts.started += 1; }
      else if (state.quests[i].action === "completed") { state.questCounts.completed += 1; }
    }
  }

  function renderRaidPanel() {
    if (!el.raidStatus) { return; }
    var logs = state.logs;
    if (!logs) {
      el.raidStatus.textContent = "正在读取日志监控状态…";
    } else if (!logs.available) {
      el.raidStatus.textContent = logs.reason || "日志监控未启用（请在启动器里填游戏目录）";
      el.raidStatus.classList.add("raid-off");
      el.raidStatus.classList.remove("raid-on");
      el.raidNote.textContent = "";
      renderQuestLog();
      return;
    } else {
      el.raidStatus.classList.add("raid-on");
      el.raidStatus.classList.remove("raid-off");
      var raid = state.raid;
      var parts = [];
      if (raid && raid.phase) { parts.push(RAID_PHASE_TEXT[raid.phase] || raid.phase); }
      if (raid && raid.mapId) {
        var suffix = state.mapsLoaded ? "（未收录）" : "…";
        var name = raid.mapKey ? mapName(raid.mapKey) : raid.mapId + suffix;
        parts.push("地图：" + name);
      }
      if (raid && raid.raidId) { parts.push("RaidId " + raid.raidId.slice(0, 8)); }
      if (logs.session) { parts.push("会话 " + logs.session.slice(4, 23)); }
      el.raidStatus.textContent = parts.length ? parts.join(" · ") : "日志监控已开启，等待战局开始…";
    }
    el.raidNote.textContent = state.raidNote || "";
    el.questDone.textContent = String(state.questCounts.completed);
    el.questStarted.textContent = String(state.questCounts.started);
  }

  /** 自动截图状态：间隔 / 按键 / 已发送张数，以及没在截图的原因 */
  function renderShotStatus(shot) {
    if (!el.shotStatus) { return; }
    if (!shot) { return; }
    state.shot = shot;
    el.shotStatus.classList.remove("shot-on", "shot-warn");
    if (!shot.enabled) {
      el.shotStatus.textContent = "自动截图：未开启（在启动器里开启，默认关闭）";
      return;
    }
    var key = shot.key ? shot.key : "（未取到按键）";
    var parts = ["自动截图：每 " + shot.intervalMs + " ms 发送 " + key, "已发送 " + shot.sent + " 张"];
    el.shotStatus.textContent = parts.join(" · ");
    if (shot.available) {
      el.shotStatus.classList.add("shot-on");
    } else {
      el.shotStatus.classList.add("shot-warn");
      el.shotStatus.textContent += "（" + (shot.reason || "暂不可用") + "）";
    }
  }

  /** 自动删除截图状态：已删张数与「为什么现在没删」 */
  function renderCleanStatus(clean) {
    if (!el.cleanStatus) { return; }
    if (!clean) { return; }
    state.clean = clean;
    el.cleanStatus.classList.remove("shot-on", "shot-warn");
    if (!clean.enabled) {
      el.cleanStatus.textContent = "自动删除截图：未开启（在启动器里开启）";
      return;
    }
    el.cleanStatus.textContent = "自动删除截图：已删除 " + clean.deleted + " 张"
      + "（保留最新 " + (clean.keepNewest || 1) + " 张供定位）";
    if (clean.available) {
      el.cleanStatus.classList.add("shot-on");
    } else {
      el.cleanStatus.classList.add("shot-warn");
      el.cleanStatus.textContent += "（" + (clean.reason || "暂不可用") + "）";
    }
  }

  function mapName(key) {
    for (var i = 0; i < state.maps.length; i++) { if (state.maps[i].key === key) { return state.maps[i].name; } }
    return key;
  }

  /** 任务事件流：新的在上；日志只给得出任务 id，拿不到任务中文名与条件级进度 */
  function renderQuestLog() {
    if (!el.questLog) { return; }
    el.questDone.textContent = String(state.questCounts.completed);
    el.questStarted.textContent = String(state.questCounts.started);
    el.questLog.innerHTML = "";      // 每次整体重建，避免重复追加
    if (!state.quests.length) {
      var empty = document.createElement("li");
      empty.className = "quest-empty";
      empty.textContent = state.logs && state.logs.available
        ? "本局还没有任务事件（日志只记录推送通知）"
        : "任务进度来自游戏日志，需在启动器里配置游戏目录";
      el.questLog.appendChild(empty);
      return;
    }
    var frag = document.createDocumentFragment();
    for (var i = 0; i < state.quests.length; i++) {
      var q = state.quests[i];
      var li = document.createElement("li");
      li.className = "quest-item quest-" + q.action;
      var when = document.createElement("span");
      when.className = "quest-time";
      when.textContent = q.ts ? q.ts.slice(11, 19) : "--:--:--";
      var what = document.createElement("span");
      what.className = "quest-what";
      what.textContent = QUEST_ACTION_TEXT[q.action] || q.action;
      var id = document.createElement("span");
      id.className = "quest-id";
      id.textContent = q.questId || "";
      id.title = q.questId || "";
      li.appendChild(when);
      li.appendChild(what);
      li.appendChild(id);
      if (q.action === "completed" && q.rewards) {
        var rewards = document.createElement("span");
        rewards.className = "quest-rewards";
        rewards.textContent = "奖励 " + q.rewards + " 件";
        li.appendChild(rewards);
      }
      frag.appendChild(li);
    }
    el.questLog.appendChild(frag);
  }

  // ---------------------------------------------------------------- 声音提示
  /** 复现一个 Web Audio 音（用户第一次点击/按键后才能出声，见 unlockAudio） */
  function playTone(key) {
    var ctx = audioContext();
    if (!ctx) { return; }
    var tones = DEFAULT_TONES[key] || [];
    for (var i = 0; i < tones.length; i++) {
      var freq = tones[i][0], at = ctx.currentTime + tones[i][1], dur = tones[i][2];
      var osc = ctx.createOscillator(), gain = ctx.createGain();
      osc.type = "triangle";
      osc.frequency.value = freq;
      // 简单包络：起音快、收尾软，避免爆音
      gain.gain.setValueAtTime(0.0001, at);
      gain.gain.exponentialRampToValueAtTime(0.22, at + 0.015);
      gain.gain.exponentialRampToValueAtTime(0.0001, at + dur);
      osc.connect(gain).connect(ctx.destination);
      osc.start(at);
      osc.stop(at + dur + 0.02);
    }
  }

  function audioContext() {
    if (state.soundCtx) { return state.soundCtx; }
    var Ctor = window.AudioContext || window.webkitAudioContext;
    if (!Ctor) { return null; }
    try { state.soundCtx = new Ctor(); } catch (e) { return null; }
    return state.soundCtx;
  }

  /** 浏览器的自动播放策略要求先有用户手势，这里在首次点击/按键时解锁音频 */
  function unlockAudio() {
    if (state.soundUnlocked) { return; }
    state.soundUnlocked = true;
    var ctx = audioContext();
    if (ctx && ctx.state === "suspended" && ctx.resume) { ctx.resume(); }
  }

  /** 播放某个提示音：总开关关着、该子开关关着、或阶段无对应提示音时都不出声 */
  function playPrompt(phase) {
    var key = PHASE_SOUND[phase];
    if (!key) { return; }
    var sound = state.sound;
    if (!sound || !sound.enabled) { return; }
    var sub = sound[key];
    if (!sub || !sub.on) { return; }
    if (sub.file) {
      var audio = new Audio("sounds/" + sub.file.split("/").map(encodeURIComponent).join("/"));
      var played = audio.play();
      if (played && played.catch) { played.catch(function () { /* 自动播放被拦或文件缺失 */ }); }
      return;
    }
    playTone(key);              // 没选自定义音频就用默认提示音
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
    // 只有**真的出现了一张新截图**（文件名或 mtime 变了）才算「新」，才自动定位一次；
    // 服务端本来也只在截图变化时才推位置帧，这里是双保险，别的来源（如换图 / 配置事件）不会再触发定位。
    var fresh = !!pos && (!state.player || state.player.name !== pos.name ||
                          state.player.mtime !== pos.mtime);
    state.player = pos;
    if (state.map) {
      maybeAutoFloor(pos);       // 截图里的高度 y → 自动切到对应楼层
      renderPlayer();
    }
    updatePositionStatus();
    if (!fresh) { return; }
    if (state.autoZoom) { applyAutoZoom(); }        // 自动缩放（内部会顺带居中）
    else if (state.autoCenter) { centerOnPlayer(); }
  }

  function insideMap(map, pos) {
    var vb = map.viewBox;
    var sx = svgX(map, pos.x, pos.z), sy = svgY(map, pos.x, pos.z);
    return sx >= vb[0] && sx <= vb[0] + vb[2] && sy >= vb[1] && sy <= vb[1] + vb[3];
  }

  function positionStatusText() {
    var pos = state.player;
    if (!pos) { return "定位：" + (state.positionInfo.reason || "不可用"); }
    var text = "定位：x " + Math.round(pos.x) + " / z " + Math.round(pos.z) +
      (pos.y === undefined || pos.y === null ? "" : " / y " + Math.round(pos.y));
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
