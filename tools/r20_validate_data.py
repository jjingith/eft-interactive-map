#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""R20 只读数据校验器（R20 后续任务书 · 第四步；R20.1 语义与路径安全修正）。

职责边界（任务书 4.1 / 二.9）：
  - 仅使用 Python 标准库；不发起任何网络请求；不修改/删除/格式化任何被检查文件。
  - 校验失败输出明确的问题位置与原因；全部硬性检查通过返回 0，存在错误返回 1，
    用法/报告写冲突返回 2。

检查项状态语义（R20.1 统一约定，报告 checks[].result 取值）：
  - pass    当前检查通过，没有发现该项问题；
  - warning 存在非阻断问题，需要人工关注（issues[].severity=warning 对应）；
  - fail    存在硬性错误，或该检查明确无法满足必要条件（issues[].severity=error 对应）；
  - skipped 因前置条件不满足而未执行。
  汇总 status：存在硬性错误 → fail；仅警告无硬性错误 → pass（warnings 数保留）。

meta.json 的哈希契约（依据 tools/fetch_data.py:981 与实际结构核实，详见 docs/r20/data-lineage.md）：
  - meta.sources[].sha256 是**抓取时上游响应字节**的哈希，不是本地文件哈希，
    离线不可重验（本轮禁止联网），因此只做格式校验，不做比对；
  - meta.items / meta.gunslots / meta.gunPresets 引用本地文件，但契约里只有
    bytes/count/schema，**没有 sha256**；bytes 不一致按 warning 报告（生成后漂移），
    缺哈希按契约现状记录为既有缺口，不升级为错误；若出现 sha256 字段则比对，
    不匹配为 error（检查项 fail，退出码非零）；
  - sources 中 sha256 == sha256(b"") 且 bytes == 0 的条目是"无下载物"条目
    （底图 SVG / 瓦片 / 图标 / 自绘素材），属正常形态。

meta 本地引用的路径契约（R20.1 严格解析，依据 meta.json 实际结构只支持该形式）：
  - 必须是形如 "data/<文件名>.json" 的相对字符串；拒绝绝对路径、盘符、任何 ".."
    或 "." 段、多级子目录、空段与非字符串值；不允许丢弃目录部分把非法引用
    转换成其他有效文件。错误信息同时给出原始引用与拒绝原因。

用法：
  python tools/r20_validate_data.py
  python tools/r20_validate_data.py --report docs/r20/validation-report.json
"""

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

# 显式业务文件白名单（2026-10-29 实扫 data/*.json 后逐一确认，证据见 data-lineage.md）。
# 排除规则：data/ 下其余 *.json 均为备份/快照（文件名含 ".bak.json" 或以 ".prev.json"
# 结尾），以及校验器自身报告；白名单之外若出现新的非备份 JSON，报 warning 要求人工归类，
# 不静默遗漏。
BUSINESS_FILES = [
    "ammo.json",
    "barriers.json",
    "bosses.json",
    "caliber-groups.json",
    "combat-targets.json",
    "flea-levels.json",      # R20.6b：跳蚤上架等级 sidecar（tools/r20_fetch_flea_levels.py 生成）
    "flea-prices.json",      # R20.5：跳蚤行情缓存（tools/r20_fetch_prices.py 生成）
    "forge-constraints.json",
    "gun-compat.json",
    "gun-layout-calibration.json",
    "gun-platforms.json",
    "gun-presets.json",
    "gun-rates.json",
    "gun-stats.json",
    "gunsmith.json",         # R20.8：枪匠任务装配约束（tools/build_gunsmith.py 生成）
    "gunslots.json",
    "items.json",
    "maps.json",
    "meta.json",
    "roadnet.json",
]

# 可选 sidecar：由独立工具按需生成、应用缺失时会自动降级的文件。
# 缺了不算错误（应用照常运行），出现了仍走同一套结构校验；白名单里登记是为了避免被
# C2 当成「未归类 JSON」静默遗漏。
OPTIONAL_FILES = {
    "flea-levels.json",   # R20.6b：跳蚤上架等级（tools/r20_fetch_flea_levels.py）
    "flea-prices.json",   # R20.5：跳蚤行情缓存（tools/r20_fetch_prices.py）
    "gunsmith.json",      # R20.8：枪匠任务（tools/build_gunsmith.py）；缺了 Gunsmith 页签自动降级
}

# meta.json 必备顶层键（依据 2026-10-29 实测结构与 fetch_data.py 写入逻辑）。
META_REQUIRED_KEYS = ["schema", "generatedAt", "gameMode", "tool", "sources"]

# meta 顶层值中带 "file" 键的子对象引用本地数据文件（实测：items/gunslots/gunPresets）。
META_FILE_REF_KEYS = ["items", "gunslots", "gunPresets"]


def is_backup_name(name):
    return ".bak.json" in name or name.endswith(".prev.json")


def parse_meta_ref(rel):
    """严格解析 meta 本地引用（R20.1，任务书五）。

    契约：必须是形如 "data/<文件名>.json" 的相对字符串。
    拒绝：非字符串/空串、绝对路径、盘符、任何 ".." 与 "." 段、空段、
    多级子目录、文件名带分隔符。**不做** name() 截取——非法引用必须原样拒绝，
    不允许丢弃目录部分把非法引用转换成其他有效文件。

    返回 (文件名, None) 或 (None, 拒绝原因字符串)。原因均含原始引用。
    """
    if not isinstance(rel, str) or not rel.strip():
        return None, "引用不是非空字符串: %r" % (rel,)
    raw = rel
    if raw.startswith("/") or raw.startswith("\\"):
        return None, "拒绝绝对路径引用: %r" % raw
    if re.match(r"^[A-Za-z]:", raw):
        return None, "拒绝盘符绝对路径引用: %r" % raw
    parts = re.split(r"[\\/]+", raw)
    if any(seg == "" for seg in parts):
        return None, "拒绝含空路径段的引用: %r" % raw
    if any(seg == ".." for seg in parts):
        return None, "拒绝路径穿越（'..'）引用: %r" % raw
    if any(seg == "." for seg in parts):
        return None, "拒绝含 '.' 路径段的引用: %r" % raw
    if len(parts) != 2 or parts[0] != "data":
        return None, "拒绝不符合 'data/<文件名>.json' 契约的引用: %r" % raw
    name = parts[1]
    if not name.endswith(".json"):
        return None, "拒绝非 .json 文件名的引用: %r" % raw
    return name, None


def safe_data_path(name):
    """解析 data/<name> 并做安全边界检查（任务书 4.2.4）。

    返回 (Path, None) 或 (None, 原因字符串)。不跟随指向项目外的符号链接。
    """
    if not isinstance(name, str) or not name or "/" in name or "\\" in name or name in (".", ".."):
        return None, "非法文件名: %r" % (name,)
    p = DATA_DIR / name
    # 先判符号链接再 resolve：否则链接目标在项目外时会被误报成"路径越界"，
    # 归因错误（R20.1 复核发现）。
    if p.is_symlink():
        return None, "符号链接，按保守策略跳过: %s" % p
    try:
        rp = p.resolve()
    except OSError as e:  # pragma: no cover - 平台相关
        return None, "路径解析失败: %s" % e
    try:
        rp.relative_to(ROOT)
    except ValueError:
        return None, "路径越界（解析到项目根目录之外）: %s" % p
    if rp.is_symlink():
        return None, "符号链接，按保守策略跳过: %s" % p
    if not rp.is_file():
        return None, "文件不存在"
    return rp, None


class Report:
    def __init__(self):
        self.checks = []
        self.issues = []

    def check(self, cid, scope, result, detail):
        self.checks.append({"id": cid, "scope": scope, "result": result, "detail": detail})

    def issue(self, severity, file_, check, message):
        self.issues.append({
            "severity": severity, "file": file_, "check": check, "message": message,
        })

    @property
    def errors(self):
        return sum(1 for i in self.issues if i["severity"] == "error")

    @property
    def warnings(self):
        return sum(1 for i in self.issues if i["severity"] == "warning")


def load_json(path):
    """返回 (obj, None) 或 (None, 错误信息)。"""
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh), None
    except json.JSONDecodeError as e:
        return None, "JSON 解析失败（%s @ 行 %d 列 %d）" % (e.msg, e.lineno, e.colno)
    except (OSError, UnicodeDecodeError) as e:
        return None, "读取失败: %s" % e


def validate(rep):
    """执行全部检查，结果记入 rep。"""
    parsed = {}

    # ---- C1: 白名单文件存在性 / 安全边界 / JSON 可解析 / 顶层类型 ----------------
    for name in BUSINESS_FILES:
        # 可选 sidecar 缺失：应用会自动降级（如「跳蚤等级」筛选变灰），不是数据损坏。
        # 必须在 safe_data_path 之前判：它把「文件不存在」也当作 err 返回。
        if name in OPTIONAL_FILES and not (DATA_DIR / name).is_file():
            rep.check("C1_file_parse", "data/" + name, "skipped",
                      "可选 sidecar 未生成（缺失时应用自动降级，不算错误）")
            continue
        p, err = safe_data_path(name)
        if err:
            rep.issue("error", "data/" + name, "C1_file_parse", err)
            rep.check("C1_file_parse", "data/" + name, "fail", err)
            continue
        obj, jerr = load_json(p)
        if jerr:
            rep.issue("error", "data/" + name, "C1_file_parse", jerr)
            rep.check("C1_file_parse", "data/" + name, "fail", jerr)
            continue
        if not isinstance(obj, dict):
            rep.issue("error", "data/" + name, "C1_file_parse",
                      "顶层类型为 %s，预期 dict（依据 2026-10-29 全量实测）" % type(obj).__name__)
            rep.check("C1_file_parse", "data/" + name, "fail", "顶层非 dict")
            continue
        parsed[name] = obj
        rep.check("C1_file_parse", "data/" + name, "pass",
                  "可解析；顶层 dict；顶层键 %d 个" % len(obj))

    # ---- C2: 白名单之外的 data/*.json 必须都能被归类（防静默遗漏） --------------
    unclassified = []
    if DATA_DIR.is_dir():
        for p in sorted(DATA_DIR.glob("*.json")):
            if p.name in BUSINESS_FILES or is_backup_name(p.name):
                continue
            unclassified.append(p.name)
    if unclassified:
        for n in unclassified:
            rep.issue("warning", "data/" + n, "C2_coverage",
                      "不在业务白名单且不匹配备份命名规则，需人工归类")
        # R20.1 统一语义：非阻断问题 → 检查项 warning（不是 fail），严重级别不变
        rep.check("C2_coverage", "data/*.json", "warning",
                  "%d 个未归类 JSON: %s" % (len(unclassified), ", ".join(unclassified)))
    else:
        rep.check("C2_coverage", "data/*.json", "pass",
                  "白名单 17 个 + 备份文件之外无未归类 JSON")

    # ---- C3: 每个业务文件带 schema / schemaVersion 字段 ------------------------
    for name, obj in parsed.items():
        if "schema" not in obj and "schemaVersion" not in obj:
            rep.issue("error", "data/" + name, "C3_schema_field",
                      "缺少 schema / schemaVersion 字段（实测 17 个业务文件均应具备其一）")
            rep.check("C3_schema_field", "data/" + name, "fail", "缺 schema 标记")
        else:
            rep.check("C3_schema_field", "data/" + name, "pass",
                      "schema=%r / schemaVersion=%r" % (obj.get("schema"), obj.get("schemaVersion")))

    # ---- C4: meta.json 自身结构 -------------------------------------------------
    if "meta.json" not in parsed:
        rep.check("C4_meta_structure", "data/meta.json", "skipped", "meta.json 未能解析")
        rep.check("C5_meta_file_refs", "data/meta.json", "skipped", "meta.json 未能解析")
        rep.check("C6_sources", "data/meta.json", "skipped", "meta.json 未能解析")
        return parsed

    meta = parsed["meta.json"]
    missing = [k for k in META_REQUIRED_KEYS if k not in meta]
    if missing:
        for k in missing:
            rep.issue("error", "data/meta.json", "C4_meta_structure", "缺少必备顶层键 %r" % k)
        rep.check("C4_meta_structure", "data/meta.json", "fail", "缺键: %s" % missing)
    else:
        rep.check("C4_meta_structure", "data/meta.json", "pass",
                  "必备键齐备；schema=%r; generatedAt=%r; gameMode=%r" % (
                      meta.get("schema"), meta.get("generatedAt"), meta.get("gameMode")))

    # ---- C5: meta 引用的本地文件（存在性 / bytes / 可选 sha256 比对） -----------
    for key in META_FILE_REF_KEYS:
        sub = meta.get(key)
        if not isinstance(sub, dict) or "file" not in sub:
            rep.check("C5_meta_file_refs", "meta." + key, "pass",
                      "无 file 引用（不检查）")
            continue
        rel = sub["file"]
        name, ref_err = parse_meta_ref(rel)
        if ref_err:
            rep.issue("error", "data/meta.json", "C5_meta_file_refs",
                      "meta.%s 引用被拒绝: %s" % (key, ref_err))
            rep.check("C5_meta_file_refs", "meta." + key, "fail", ref_err)
            continue
        p, err = safe_data_path(name)
        if err:
            rep.issue("error", "data/meta.json", "C5_meta_file_refs",
                      "meta.%s 引用 %r 不可达: %s" % (key, rel, err))
            rep.check("C5_meta_file_refs", "meta." + key, "fail",
                      "引用 %r: %s" % (rel, err))
            continue
        actual_bytes = p.stat().st_size
        declared = sub.get("bytes")
        notes = []
        local_fail = False
        drift = False
        missing_hash = False
        hash_state = None          # "match" / "mismatch" / "invalid" / None(缺失)
        if declared is not None and declared != actual_bytes:
            drift = True
            notes.append("bytes 漂移 %d -> %d" % (declared, actual_bytes))
        if "sha256" in sub:
            want = sub["sha256"]
            if not isinstance(want, str) or not SHA256_RE.match(want):
                rep.issue("error", "data/" + name, "C5_meta_file_refs",
                          "meta.%s.sha256 格式非法（应为 64 位小写十六进制）: %r"
                          % (key, want if isinstance(want, str) else type(want).__name__))
                notes.append("sha256 格式非法")
                hash_state = "invalid"
                local_fail = True
            else:
                got = hashlib.sha256(p.read_bytes()).hexdigest()
                if want != got:
                    rep.issue("error", "data/" + name, "C5_meta_file_refs",
                              "meta.%s.sha256 与实际文件哈希不一致（引用 %r）" % (key, rel))
                    notes.append("sha256 不匹配")
                    hash_state = "mismatch"
                    local_fail = True
                else:
                    notes.append("sha256 一致")
                    hash_state = "match"
        else:
            # R20.3：没有本地哈希 = 尚未完成哈希验证，必须显式告警，不得静默当作已验证。
            rep.issue("warning", "data/" + name, "C5_meta_file_refs",
                      "meta.%s 缺少本地文件 sha256：未完成哈希验证（内容是否被改动无法判定）"
                      % key)
            notes.append("缺 sha256（未完成哈希验证）")
            missing_hash = True
        if drift:
            # 漂移原因按哈希比对结果区分：哈希一致 → 只是 bytes 记录停留在生成时刻；
            # 哈希不一致 → 另有 error 指出真实内容差异；无哈希 → 漂移无法定性。
            if hash_state == "match":
                why = ("bytes 记录停留在生成时刻（meta 只保存了当时的文件大小），"
                       "本地 sha256 与当前文件一致，说明内容未偏离哈希基线")
            elif hash_state in ("mismatch", "invalid"):
                why = "bytes 与实际不一致，且本地 sha256 校验失败，内容差异见 error 项"
            else:
                why = ("bytes 与实际不一致，且该引用缺少本地 sha256，"
                       "无法判断是合法更新还是内容漂移")
            rep.issue("warning", "data/" + name, "C5_meta_file_refs",
                      "meta.%s.bytes=%d 与实际 %d 不一致（%s）"
                      % (key, declared, actual_bytes, why))
        # R20.1 统一语义：硬失败→fail；仅 bytes 漂移/缺哈希→warning；干净→pass
        result = "fail" if local_fail else ("warning" if (drift or missing_hash) else "pass")
        rep.check("C5_meta_file_refs", "meta." + key, result,
                  "file=%s; declared_bytes=%r; actual_bytes=%d; %s"
                  % (rel, declared, actual_bytes, "; ".join(notes) or "bytes 一致"))

    # meta.icons 是 assets 目录引用（非 JSON），只查目录存在性
    icons = meta.get("icons")
    if isinstance(icons, dict) and "dir" in icons:
        d = ROOT / icons["dir"]
        if d.is_dir():
            rep.check("C5_meta_file_refs", "meta.icons", "pass",
                      "assets 目录存在: %s（逐文件审计未执行，超本轮范围）" % icons["dir"])
        else:
            rep.issue("error", icons["dir"], "C5_meta_file_refs", "meta.icons 目录不存在")
            rep.check("C5_meta_file_refs", "meta.icons", "fail", "目录不存在")

    # ---- C6: sources[] 条目（格式校验；上游快照哈希离线不可重验） ----------------
    sources = meta.get("sources")
    if not isinstance(sources, list) or not sources:
        rep.issue("error", "data/meta.json", "C6_sources", "sources 缺失或为空")
        rep.check("C6_sources", "data/meta.json", "fail", "sources 缺失或为空")
        return parsed

    n_err = 0
    n_warn = 0
    empty_artifacts = 0
    for i, s in enumerate(sources):
        where = "meta.sources[%d]" % i
        if not isinstance(s, dict):
            rep.issue("error", "data/meta.json", "C6_sources", where + " 不是对象")
            n_err += 1
            continue
        for f in ("name", "license"):
            if not str(s.get(f) or "").strip():
                rep.issue("warning", "data/meta.json", "C6_sources",
                          "%s.%s 为空" % (where, f))
                n_warn += 1
        sha = s.get("sha256") or ""
        if not SHA256_RE.match(sha):
            rep.issue("error", "data/meta.json", "C6_sources",
                      "%s.sha256 不是 64 位小写十六进制: %r" % (where, sha[:20]))
            n_err += 1
        is_no_download = sha == EMPTY_SHA256 and s.get("bytes") == 0
        # url 允许为空的唯一形态：自绘/无下载物条目（fetch_data.py:1948,1970 有意写空 url）
        if not str(s.get("url") or "").strip() and not is_no_download:
            rep.issue("warning", "data/meta.json", "C6_sources",
                      "%s.url 为空（且不是无下载物条目）" % where)
            n_warn += 1
        if is_no_download:
            empty_artifacts += 1  # 无下载物条目（底图/图标/自绘素材），正常形态
    # R20.1 统一语义：有 error→fail；仅 warning→warning；干净→pass
    if n_err:
        rep.check("C6_sources", "data/meta.json", "fail",
                  "error %d 条 / warning %d 条" % (n_err, n_warn))
    elif n_warn:
        rep.check("C6_sources", "data/meta.json", "warning",
                  "warning %d 条（无硬性错误）" % n_warn)
    else:
        rep.check("C6_sources", "data/meta.json", "pass",
                  "%d 条 sources 格式合法；其中 %d 条为无下载物条目(sha256=空串哈希,bytes=0)。"
                  "注意：其余 sha256 是抓取时上游响应哈希（fetch_data.py:981），"
                  "离线不可重验，本轮仅格式校验" % (len(sources), empty_artifacts))
    return parsed


def not_executed():
    """显式列出未执行的检查及原因（任务书 4.5）。"""
    return [
        {"check": "上游快照 sha256 重验",
         "reason": "sources[].sha256 是抓取时上游响应哈希；重验必须重新下载，本轮禁止联网"},
        {"check": "业务文件内 count/条目数一致性核对",
         "reason": "items.count / gunslots.count 等计数的统计口径未逐一定位到生成代码，"
                   "按任务书 4.3 不猜测规则，列为待人工审查"},
        {"check": "逐字段枚举值校验（如 pt/_caliber 合法值域）",
         "reason": "合法值域需以生成器代码为准逐一定位，本轮范围只做结构级校验"},
        {"check": "assets/icons-items 等图标目录逐文件审计",
         "reason": "涉及 5000+ 文件的哈希与许可核对，超出本轮只读校验范围"},
        {"check": "gun-layout-calibration.json 人工校准记录合法性",
         "reason": "校准语义由应用层（gwApplyCalibToLayout）判定，静态校验器不重复实现业务规则"},
    ]


def main(argv=None):
    ap = argparse.ArgumentParser(description="R20 只读数据校验器（不联网、不写数据）")
    ap.add_argument("--report", metavar="PATH", default=None,
                    help="将 JSON 校验报告写到指定路径；目标已存在时拒绝写入")
    args = ap.parse_args(argv)

    rep = Report()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if not DATA_DIR.is_dir():
        print("FATAL: 数据目录不存在: %s" % DATA_DIR)
        return 2

    parsed = validate(rep)

    errors = rep.errors
    warnings = rep.warnings
    status = "pass" if errors == 0 else "fail"

    report = {
        "validator": "r20_validate_data.py",
        "checkedAt": now,
        "status": status,
        "summary": {
            "files_checked": len([c for c in rep.checks if c["id"] == "C1_file_parse"]),
            "errors": errors,
            "warnings": warnings,
        },
        "checks": rep.checks,
        "issues": rep.issues,
        "not_executed": not_executed(),
        "statusSemantics": {
            "pass": "当前检查通过，没有发现该项问题",
            "warning": "存在非阻断问题，需要人工关注",
            "fail": "存在硬性错误，或该检查明确无法满足必要条件",
            "skipped": "因前置条件不满足而未执行",
            "summaryStatus": "存在硬性错误时为 fail；只有警告而无硬性错误时为 pass（warnings 数保留）",
        },
        "notes": [
            "时间戳仅记录本次校验发生时间，不代表源数据更新时间。",
            "严重级别契约：error=结构损坏/引用不可达/哈希格式或比对失败；"
            "warning=生成后漂移或需人工归类（不阻断）；"
            "info 仅存在于检查明细文本中。",
            "检查项 result 与 issues[].severity 对应：fail↔error、warning↔warning。",
        ],
    }

    # ---- stdout 人工可读摘要 -----------------------------------------------------
    print("=== R20 只读数据校验器 ===")
    print("项目根: %s" % ROOT)
    print("检查文件: %d 个业务 JSON（白名单制；备份 *.bak.json / *.prev.json 已排除）"
          % len(BUSINESS_FILES))
    print("结果: %s   errors=%d   warnings=%d" % (status.upper(), errors, warnings))
    for i in rep.issues:
        print("  [%s] %s  (%s)  %s" % (i["severity"].upper(), i["file"], i["check"], i["message"]))
    if status == "pass":
        print("全部硬性检查通过。未执行检查 %d 项（见报告 not_executed）。"
              % len(report["not_executed"]))

    # ---- 报告写盘（拒绝覆盖） ----------------------------------------------------
    if args.report:
        out = (ROOT / args.report) if not Path(args.report).is_absolute() else Path(args.report)
        if out.exists():
            print("FATAL: 报告目标已存在，拒绝覆盖: %s" % out)
            return 2
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8", newline="\n") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        print("报告已写入: %s" % out)

    return 0 if status == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
