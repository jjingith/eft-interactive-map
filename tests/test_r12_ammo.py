"""第十二轮阶段 A（弹药页面 + 详情弹窗）数据级 / 静态结构 / 弹道模型测试。

四层：
1. **数据完整性**：`data/ammo.json` 覆盖 `items.json` 里**全部** pt=Ammo 的物品，
   字段覆盖、口径 / 分组 / 筹码一致性；跳蚤市场价全部缺失时必须显式标记不可用（不得按 0）。
2. **弹道模型**：按 app.js 里**实际使用的常数**（AM_DRAG_C / AM_C_SOUND / AM_GRAVITY /
   AM_DT / AM_HOB / AM_ZERO / AM_SAMPLE_STEP）与 G1 阻力表在 Python 里复算，
   对齐参考站公开的 51 行 LRNPC 表并给出误差上限；同时验证曲线**不是**线性占位。
3. **页面接线（静态）**：视图白名单、index.html 容器、表格列集、详情弹窗、
   搜索 / 筛选 / 排序语义、距离衰减因子 0.5 + 0.5·v/v0。
4. **离线**：app.js 不含运行期外部 URL；图库 / 数据全部走本地相对路径。

只读仓库内文件，不联网、不引入第三方依赖。
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_JS = ROOT / "app.js"
INDEX_HTML = ROOT / "index.html"
AMMO_JSON = ROOT / "data" / "ammo.json"
ITEMS_JSON = ROOT / "data" / "items.json"
REF_TABLE = ROOT / "docs" / "r12-ammo" / "reference" / "lrnpc-reference-table.json"
CONFIG_PY = ROOT / "tools" / "config.py"

REQUIRED_NUM_FIELDS = ("dmg", "ard", "pen", "v0", "bc", "m", "dia", "frag", "ric",
                       "acc", "rec", "pc", "stack", "pch", "w", "base")
VALID_TYPES = {"bullet", "buckshot", "grenade", "flashbang"}
VALID_GROUPS = {"pistol", "rifle", "pdw", "shot", "gl"}

LRNPC_ID = "573602322459776445391df1"   # 7.62x25mm TT LRNPC（参考站公开表的同一发弹）


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _ammo() -> dict:
    return json.loads(_read(AMMO_JSON))


def _items() -> dict:
    return json.loads(_read(ITEMS_JSON))["items"]


# ---------------------------------------------------------------- 弹道模型复算
def _js_const(name: str) -> float:
    m = re.search(r"var\s+" + name + r"\s*=\s*([\d.]+)", _read(APP_JS))
    assert m, "app.js 里找不到常数 %s" % name
    return float(m.group(1))


def _g1_table() -> list[tuple[float, float]]:
    js = _read(APP_JS)
    i = js.index("var AM_G1 = [")
    block = js[i:js.index("];", i)]
    pairs = re.findall(r"\[\s*([\d.]+)\s*,\s*([\d.]+)\s*\]", block)
    assert len(pairs) >= 40, "AM_G1 阻力表提取失败"
    return [(float(a), float(b)) for a, b in pairs]


def _cd(mach: float, table: list[tuple[float, float]]) -> float:
    if mach <= table[0][0]:
        return table[0][1]
    if mach >= table[-1][0]:
        return table[-1][1]
    for i in range(1, len(table)):
        if mach <= table[i][0]:
            m0, v0 = table[i - 1]
            m1, v1 = table[i]
            return v0 + (v1 - v0) * (mach - m0) / (m1 - m0)
    return table[-1][1]


def _simulate(v0: float, bc: float, mass_g: float, dia_mm: float, max_dist: float = 500.0):
    """与 app.js 的 amSimulate 逐步等价：G1 阻力 + 重力 + 0.01 s 步长 + 50 m 二分归零。"""
    c = _js_const("AM_DRAG_C")
    c_sound = _js_const("AM_C_SOUND")
    grav = _js_const("AM_GRAVITY")
    dt = _js_const("AM_DT")
    hob = _js_const("AM_HOB")
    zero = _js_const("AM_ZERO")
    step = _js_const("AM_SAMPLE_STEP")
    table = _g1_table()
    mass = mass_g / 1000.0
    dia = dia_mm / 1000.0
    k = mass * c / bc / (dia * dia)

    def run(angle: float):
        x, y = 0.0, -hob
        vx, vy = v0 * math.cos(angle), v0 * math.sin(angle)
        t = 0.0
        out = [[0.0, y * 100.0, v0, 0.0]]
        nxt, guard = step, 0
        while x < max_dist + 0.5 and guard < 40000:
            sp = math.hypot(vx, vy)
            if sp > 0:
                ad = k * _cd(sp / c_sound, table) * sp
                vx -= ad * vx / sp * dt
                vy -= ad * vy / sp * dt
            vy -= grav * dt
            x += vx * dt
            y += vy * dt
            t += dt
            guard += 1
            while x >= nxt and nxt <= max_dist + 0.5:
                out.append([nxt, y * 100.0, sp, t])
                nxt += step
        return out

    lo, hi = -0.08, 0.08
    for _ in range(32):
        mid = (lo + hi) / 2
        samples = run(mid)
        s_zero = [r for r in samples if r[0] == zero][0]
        if s_zero[1] > 0:
            hi = mid
        else:
            lo = mid
    return run((lo + hi) / 2)


def _by_id(aid: str) -> dict:
    for row in _ammo()["ammo"]:
        if row["id"] == aid:
            return row
    raise AssertionError("弹药 %s 不在 data/ammo.json" % aid)


# ---------------------------------------------------------------- 1. 数据完整性
def test_ammo_json_shape_and_count():
    data = _ammo()
    for key in ("schema", "count", "groups", "chips", "calibers", "traders", "ammo", "audit"):
        assert key in data, "ammo.json 缺顶层键 %s" % key
    assert data["count"] == len(data["ammo"]) == 200
    assert data["audit"]["count"] == 200, "审计条数与数据条数必须一致"


def test_ammo_covers_every_ammo_item_in_items_json():
    rows = _ammo()["ammo"]
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids)), "弹药 id 重复"
    items = _items()
    ammo_items = {k for k, v in items.items() if v.get("pt") == "Ammo"}
    assert set(ids) == ammo_items, "弹药列表必须覆盖 items.json 中全部 Ammo 物品"
    for aid in ids:
        tags = items[aid].get("ts") or []
        assert "ammo" in tags, "非弹药物品混入弹药表：%s" % items[aid].get("n")


def test_ammo_rows_have_full_ballistic_fields():
    rows = _ammo()["ammo"]
    for r in rows:
        assert r["t"] in VALID_TYPES, "未知弹药类型：%s" % r["t"]
        assert r["g"] in VALID_GROUPS, "未知分组：%s" % r["g"]
        assert isinstance(r["caln"], str) and r["caln"], "口径名缺失"
        for key in REQUIRED_NUM_FIELDS:
            assert isinstance(r[key], (int, float)) and not isinstance(r[key], bool), \
                "%s 的 %s 不是数字" % (r["n"], key)
        assert isinstance(r["tr"], bool), "%s 的曳光标记必须是布尔值" % r["n"]
        assert r["pen"] >= 0, "%s 的穿透必须非负（信号弹可为 0）" % r["n"]
        assert r["ard"] >= 0, "%s 的护甲伤害必须非负（20x1 塑料片为 0）" % r["n"]
        assert r["dmg"] >= 0, "%s 的伤害必须非负（闪光弹为 0）" % r["n"]
        if r["t"] in ("bullet", "buckshot"):
            assert r["dmg"] > 0, "%s 是实弹，伤害不应为 0" % r["n"]
        for key in ("v0", "bc", "m", "dia"):
            assert r[key] > 0, "%s 的 %s 必须为正数" % (r["n"], key)


def test_flea_price_is_marked_unavailable_not_zero():
    data = _ammo()
    rows = data["ammo"]
    assert all(r["flea"] is None for r in rows), "跳蚤价缺失时不得填 0 或编造数值"
    assert data["audit"]["coverage"]["flea"] == 0
    note = data["audit"]["unavailable"]["flea"]
    assert "—" in note and "不得按 0" in note, "缺口必须在审计里写明处理方式"
    assert all(r["sell"] and isinstance(r["sell"].get("rub"), (int, float)) for r in rows)
    assert sum(1 for r in rows if r["buy"]) == data["audit"]["coverage"]["buy"]


def test_calibers_groups_and_chips_are_consistent():
    data = _ammo()
    rows = data["ammo"]
    cals = set(r["caln"] for r in rows)
    assert len(cals) == data["audit"]["calibers"] == 31
    assert not data["audit"]["calibersMissingLabel"]

    # chips 是「按参考站分组的口径筹码」：[{g, items: [{k, cal, atyp}]}]
    # 霰弹口径被参考站拆成 12g Shot / 12g Slugs 两个筹码（atyp 区分 buckshot / slug），
    # 所以不能用「筹码名 == caln」去等值比对，必须按 cal + atyp 的匹配规则验证覆盖。
    def chip_hit(row: dict, item: dict) -> bool:
        if item.get("cal") and row["cal"] != item["cal"]:
            return False
        atyp = item.get("atyp")
        if atyp == "buckshot":
            return row["t"] == "buckshot"
        if atyp == "slug":
            return row["t"] == "bullet"
        return True

    chip_items = []
    for g in data["chips"]:
        assert g["g"] in VALID_GROUPS, "未知筹码分组：%s" % g["g"]
        chip_items.extend(g["items"])
    assert len(chip_items) == 32
    keys = [it["k"] for it in chip_items]
    assert len(keys) == len(set(keys)), "口径筹码名重复"

    hit_count = {r["id"]: 0 for r in rows}
    for it in chip_items:
        hits = [r for r in rows if chip_hit(r, it)]
        assert hits, "筹码 %s 匹配不到任何弹药" % it["k"]
        for r in hits:
            hit_count[r["id"]] += 1
    assert all(v == 1 for v in hit_count.values()), \
        "每发弹药必须且只能被一个筹码覆盖：%s" % {k: v for k, v in hit_count.items() if v != 1}
    for g in data["groups"]:
        assert g["k"] in VALID_GROUPS
        assert any(c["g"] == g["k"] for c in data["chips"]), "分组 %s 缺筹码定义" % g["k"]
    assert sum(1 for r in rows if r["g"] not in VALID_GROUPS) == 0
    by_type = {}
    for r in rows:
        by_type[r["t"]] = by_type.get(r["t"], 0) + 1
    assert by_type == data["audit"]["byType"]


# ---------------------------------------------------------------- 2. 弹道模型
def test_ballistic_model_matches_reference_table():
    """参考站公开的 51 行数据：速度 / 下沉 / 飞行时间的误差上限（标定记录见 report.md）。"""
    ref = json.loads(_read(REF_TABLE))["rows"]
    a = _by_id(LRNPC_ID)
    samples = _simulate(a["v0"], a["bc"], a["m"], a["dia"])
    by_m = {round(s[0]): s for s in samples}
    err_v, err_d, err_t = [], [], []
    for row in ref:
        m = int(row["m"])
        if m not in by_m:
            continue
        _, y, sp, t = by_m[m]
        err_v.append(abs(sp - row["speed"]))
        err_d.append(abs(y - row["drop_cm"]))
        err_t.append(abs(t - row["tof"]))
    assert len(err_v) == 51, "参考表 0–500 m 每 10 m 一行，共 51 行"
    assert sum(err_v) / len(err_v) <= 8.0, "速度平均误差过大：%.2f" % (sum(err_v) / len(err_v))
    assert max(err_v) <= 26.0
    assert sum(err_d) / len(err_d) <= 5.5, "下沉平均误差过大：%.2f cm" % (sum(err_d) / len(err_d))
    assert max(err_d) <= 20.0
    assert sum(err_t) / len(err_t) <= 0.012, "飞行时间平均误差过大"
    assert max(err_t) <= 0.035


def test_zeroing_and_muzzle_height_are_physical():
    a = _by_id(LRNPC_ID)
    samples = _simulate(a["v0"], a["bc"], a["m"], a["dia"])
    by_m = {round(s[0]): s for s in samples}
    assert abs(by_m[0][1] + 6.858) < 0.01, "0 m 处下沉必须等于瞄高 -6.858 cm"
    assert abs(by_m[50][1]) < 0.05, "50 m 归零，下沉应≈0"
    assert by_m[500][1] < -500, "500 m 处下沉必须是物理上的大负值"


def test_drop_curve_is_not_a_linear_placeholder():
    a = _by_id(LRNPC_ID)
    samples = _simulate(a["v0"], a["bc"], a["m"], a["dia"])
    by_m = {round(s[0]): s for s in samples}
    linear_400 = by_m[0][1] + (by_m[500][1] - by_m[0][1]) * 400 / 500
    assert abs(by_m[400][1] - linear_400) > 50, "400 m 处与线性插值差距过小，疑似线性假曲线"
    # 速度衰减也必须单调递减（阻力模型）
    speeds = [s[2] for s in samples]
    assert all(speeds[i] > speeds[i + 1] for i in range(len(speeds) - 1))


def test_curves_differ_between_ammo_no_cross_talk():
    picks = ["573602322459776445391df1", "5cde8864d7f00c0010373be1", "59e6542b86f77411dc52a77a"]
    seen = {}
    for aid in picks:
        try:
            a = _by_id(aid)
        except AssertionError:
            continue
        samples = _simulate(a["v0"], a["bc"], a["m"], a["dia"])
        by_m = {round(s[0]): s for s in samples}
        seen[aid] = (round(by_m[400][1], 3), round(by_m[500][2], 3))
    assert len(seen) >= 2, "至少要有两种弹药可对比"
    values = list(seen.values())
    for i in range(len(values)):
        for j in range(i + 1, len(values)):
            assert values[i] != values[j], "不同弹药使用了同一条曲线（串号）"


# ---------------------------------------------------------------- 3. 页面接线
def test_ammo_view_is_wired_in_index_and_app():
    html = _read(INDEX_HTML)
    assert 'id="view-btn-ammo"' in html and 'data-view="ammo"' in html
    assert 'id="ammo-view"' in html and 'class="view-pane"' in html
    for el_id in ("am-tabs", "am-search", "am-count", "am-groups", "am-range",
                  "am-maxdist", "am-table", "am-graph", "am-detail", "am-detail-body"):
        assert 'id="%s"' % el_id in html, "弹药页缺容器 #%s" % el_id
    js = _read(APP_JS)
    # R19.22 升级：视图表允许继续扩展（新增 tasks），但四个既有视图必须都在
    m = re.search(r'var VIEWS = \[([^\]]*)\]', js)
    assert m, "找不到 VIEWS 声明"
    for view in ("map", "loadout", "gun", "ammo"):
        assert '"%s"' % view in m.group(1), "VIEWS 缺 %s：%s" % (view, m.group(1))
    assert "function bindAmmoUI" in js and "bindAmmoUI();" in js
    assert "function openAmmoDetail" in js and 'AMMO_URL = "data/ammo.json"' in js
    assert "function closeAmmoDetail" in js
    conf = _read(CONFIG_PY)
    assert '"ammo"' in conf, "config.py 的 view 白名单必须包含 ammo（否则配置回声会把视图切回去）"


def test_ammo_table_columns_and_sort_semantics():
    js = _read(APP_JS)
    for key in ("caln", "n", "pen", "dmg", "ard", "acc", "rec", "frag", "v0", "ric"):
        assert 'key: "%s"' % key in js, "弹药表缺列 %s" % key
    # db4 弹药表为 11 列：DROP 是含 1–6 级穿透概率的【单列】（不是 C1..C6 六列）。
    # 单列 key 固定为 "drop"，其 render 内部按 for (var lv = 1; lv <= 6; lv++) 循环渲染 6 个子值。
    assert 'key: "drop"' in js, "弹药表缺 DROP 单列（db4 为 11 列，DROP 是含 1–6 级穿透概率的单列）"
    assert 'for (var lv = 1; lv <= 6; lv++)' in js, "DROP 必须按 1–6 级循环渲染穿透概率子值"
    assert 'amPenChance(r.pen, lvl)' in js, "DROP 子值需调用穿透概率计算"
    assert 'searchKeys: ["n", "caln", "t"]' in js, "搜索必须覆盖名称 / 口径 / 类型"
    assert "function amRows" in js and "f.search" in js, "搜索词必须参与行筛选（计数才会一致）"
    assert "function amPenChance" in js, "C1..C6 需要穿透概率计算"
    assert "0.5 + 0.5 * (v / a.v0)" in js, "距离衰减必须是 0.5 + 0.5·v/v0"


def test_search_semantics_on_real_data():
    rows = _ammo()["ammo"]

    def search(q):
        q = q.lower()
        return [r for r in rows
                if q in (r["n"] + " " + r["caln"] + " " + r["t"]).lower()]

    assert len(search("M995")) == 2
    assert len(search("BS")) == 3
    assert len(search("5.45x39")) == 13
    # 与口径筛选组合：5.45x39 里再搜 7N39
    hit = [r for r in search("7N39") if r["caln"] == "5.45x39"]
    assert len(hit) == 1 and hit[0]["n"].endswith("7N39“针刺”")
    # 排序（数值列）语义：pen 升 / 降序都必须是单调的
    asc = sorted(rows, key=lambda r: r["pen"])
    desc = sorted(rows, key=lambda r: -r["pen"])
    assert all(asc[i]["pen"] <= asc[i + 1]["pen"] for i in range(len(asc) - 1))
    assert all(desc[i]["pen"] >= desc[i + 1]["pen"] for i in range(len(desc) - 1))


def test_detail_payload_covers_audited_fields():
    """弹窗字段必须全部来自数据（跳蚤价缺失只能显示「—」）。"""
    js = _read(APP_JS)
    for label in ("伤害 Dmg", "穿透 Pen", "护甲伤害 ArD", "初速", "弹道系数 BC",
                  "弹丸质量", "弹径", "碎裂概率", "跳弹概率", "精准度修正",
                  "后坐力修正", "堆叠上限", "曳光弹", "商人买入", "商人卖出",
                  "基础价格", "跳蚤市场"):
        assert '"%s"' % label in js, "详情弹窗缺字段 %s" % label
    assert '"跳蚤市场", "—"' in js or '"跳蚤市场", "—"' in js.replace("'", '"')
    for head in ("m", "Pen", "Dmg", "Speed", "Drop", "TOF"):
        assert '"%s"' % head in js, "详情距离表缺表头 %s" % head


# ---------------------------------------------------------------- 4. 离线
def test_no_runtime_external_network():
    js = _read(APP_JS)
    urls = re.findall(r"https?://[^\s\"']+", js)
    external = [u for u in urls if "127.0.0.1" not in u and "localhost" not in u
                and "www.w3.org" not in u]
    assert not external, "app.js 出现外部地址：%s" % external
    assert 'AMMO_URL = "data/ammo.json"' in js
