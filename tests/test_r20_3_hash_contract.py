# -*- coding: utf-8 -*-
"""R20.3 本地 SHA-256 完整性契约测试。

范围（任务书第八节 14 项）：
  - 全部在 pytest 临时目录里构造"迷你工程"（17 个白名单文件 + meta.json），
    复制校验器到该目录后以子进程执行，**不触碰正式业务数据**；
  - 验证真实输出（报告 JSON + stdout + 退出码），不以"脚本没抛异常"作为通过依据；
  - 末尾断言正式业务文件哈希在整轮测试前后一致（证明测试未改动真实数据）。

不依赖网络：本文件不发起任何网络请求，也不调用任何会写正式 data/ 的脚本。
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
VALIDATOR = ROOT / "tools" / "r20_validate_data.py"
FETCH = ROOT / "tools" / "fetch_data.py"
REAL_DATA_FILES = ["data/items.json", "data/gunslots.json", "data/gun-presets.json",
                   "data/maps.json", "data/ammo.json"]

WHITE = ["ammo", "barriers", "bosses", "caliber-groups", "combat-targets", "forge-constraints",
         "gun-compat", "gun-layout-calibration", "gun-platforms", "gun-presets", "gun-rates",
         "gun-stats", "gunslots", "items", "maps", "meta", "roadnet"]


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_project(tmp_path, blocks=None, sources=None, payloads=None):
    """构造迷你工程：复制校验器 + 17 个白名单 JSON + meta.json。"""
    proj = tmp_path / "proj"
    (proj / "tools").mkdir(parents=True)
    (proj / "data").mkdir()
    shutil.copy2(VALIDATOR, proj / "tools" / VALIDATOR.name)
    for n in WHITE:
        body = payloads.get(n) if payloads else None
        if body is None:
            body = json.dumps({"schema": 1})
        (proj / "data" / (n + ".json")).write_text(body, encoding="utf-8")
    if blocks is None:
        blocks = {}
        for key, fname in (("items", "items.json"), ("gunslots", "gunslots.json"),
                           ("gunPresets", "gun-presets.json")):
            p = proj / "data" / fname
            blocks[key] = {"file": "data/" + fname, "schema": 6, "count": 1,
                           "bytes": p.stat().st_size,
                           "sha256": sha256_file(p)}
    if sources is None:
        sources = [{"name": "fixture", "url": "https://example.invalid/x",
                    "license": "MIT", "sha256": "0" * 64, "bytes": 5},
                   {"name": "nodl", "url": "", "license": "项目内自制",
                    "sha256": hashlib.sha256(b"").hexdigest(), "bytes": 0}]
    meta = {"schema": 8, "generatedAt": "2026-10-29T00:00:00Z", "gameMode": "regular",
            "tool": "tools/fetch_data.py", "sources": sources, "counts": {},
            "items": blocks.get("items"), "gunslots": blocks.get("gunslots"),
            "gunPresets": blocks.get("gunPresets")}
    (proj / "data" / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1),
                                              encoding="utf-8")
    return proj


def run_validator(proj, report="docs/r20/r.json", cwd=None):
    args = [sys.executable, str(proj / "tools" / VALIDATOR.name)]
    if report:
        args += ["--report", report]
    proc = subprocess.run(args, capture_output=True, text=True,
                          cwd=str(cwd or proj))
    data = None
    if report:
        rp = proj / report
        if rp.exists():
            data = json.loads(rp.read_text(encoding="utf-8"))
    return proc, data


def c5_of(report, scope):
    for c in report["checks"]:
        if c["id"] == "C5_meta_file_refs" and c["scope"] == scope:
            return c
    return None


def issues_of(report, scope_sub=None, severity=None):
    out = []
    for i in report["issues"]:
        if scope_sub and scope_sub not in i["message"] and scope_sub not in str(i["file"]):
            continue
        if severity and i["severity"] != severity:
            continue
        out.append(i)
    return out


# ---------------------------------------------------------------- 1 正确哈希可通过
def test_matching_hash_passes(tmp_path):
    proj = build_project(tmp_path)
    proc, rep = run_validator(proj)
    c5 = c5_of(rep, "meta.items")
    assert c5["result"] == "pass", c5
    assert "sha256 一致" in c5["detail"], c5
    assert rep["summary"]["errors"] == 0, rep["summary"]
    assert proc.returncode == 0, proc.stdout


# ---------------------------------------------------------------- 2 内容改变被检测
def test_content_change_detected(tmp_path):
    proj = build_project(tmp_path)
    p = proj / "data" / "items.json"
    p.write_text(json.dumps({"schema": 1, "x": "modified"}), encoding="utf-8")
    proc, rep = run_validator(proj)
    assert rep["status"] == "fail", rep["status"]
    assert rep["summary"]["errors"] >= 1
    assert proc.returncode == 1, proc.returncode
    errs = issues_of(rep, severity="error")
    assert any("sha256" in e["message"] for e in errs), errs
    assert c5_of(rep, "meta.items")["result"] == "fail"


# ---------------------------------------------------------------- 3 内容变但字节数不变
def test_same_size_content_change_detected(tmp_path):
    proj = build_project(tmp_path)
    p = proj / "data" / "items.json"
    before_size = p.stat().st_size
    body = p.read_text(encoding="utf-8").replace('"schema": 1', '"schema": 2')
    assert len(body.encode("utf-8")) == before_size, "前提：字节数不变"
    p.write_text(body, encoding="utf-8")
    assert p.stat().st_size == before_size
    proc, rep = run_validator(proj)
    # bytes 未漂移 → 没有 bytes 警告；只有 sha256 能发现
    assert not issues_of(rep, "bytes 漂移"), rep["issues"]
    assert rep["status"] == "fail" and proc.returncode == 1
    assert any("sha256" in e["message"] for e in issues_of(rep, severity="error"))


# ---------------------------------------------------------------- 4 文件缺失
def test_missing_file_is_hard_error(tmp_path):
    proj = build_project(tmp_path)
    (proj / "data" / "items.json").unlink()
    proc, rep = run_validator(proj)
    assert rep["status"] == "fail" and proc.returncode == 1
    c5 = c5_of(rep, "meta.items")
    assert c5["result"] == "fail", c5
    assert any("不可达" in e["message"] or "文件不存在" in e["message"]
               for e in issues_of(rep, severity="error"))


# ---------------------------------------------------------------- 5 哈希字段缺失
def test_missing_hash_field_is_warning_not_silent_pass(tmp_path):
    proj = build_project(tmp_path)
    meta = json.loads((proj / "data" / "meta.json").read_text(encoding="utf-8"))
    meta["items"].pop("sha256", None)
    (proj / "data" / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1),
                                              encoding="utf-8")
    proc, rep = run_validator(proj)
    c5 = c5_of(rep, "meta.items")
    assert c5["result"] == "warning", c5
    warns = issues_of(rep, severity="warning")
    assert any("sha256" in w["message"] for w in warns), warns
    # 不得静默宣称"已完成哈希验证"
    assert rep["summary"]["errors"] == 0
    assert rep["summary"]["warnings"] >= 1
    assert proc.returncode == 0, "仅警告不应导致非零退出"


# ---------------------------------------------------------------- 6 哈希格式非法
def test_malformed_hash_is_hard_error(tmp_path):
    proj = build_project(tmp_path)
    meta = json.loads((proj / "data" / "meta.json").read_text(encoding="utf-8"))
    meta["items"]["sha256"] = "NOT-A-HASH"
    (proj / "data" / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1),
                                              encoding="utf-8")
    proc, rep = run_validator(proj)
    assert rep["status"] == "fail" and proc.returncode == 1
    assert any("格式非法" in e["message"] for e in issues_of(rep, severity="error"))
    assert c5_of(rep, "meta.items")["result"] == "fail"


# ---------------------------------------------------------------- 7 不匹配的报告明细
def test_mismatch_report_detail(tmp_path):
    proj = build_project(tmp_path)
    meta = json.loads((proj / "data" / "meta.json").read_text(encoding="utf-8"))
    meta["items"]["sha256"] = "a" * 64
    (proj / "data" / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1),
                                              encoding="utf-8")
    proc, rep = run_validator(proj)
    errs = issues_of(rep, severity="error")
    assert len(errs) == 1, errs
    assert errs[0]["check"] == "C5_meta_file_refs"
    assert "sha256" in errs[0]["message"]
    assert rep["summary"]["errors"] == 1
    assert proc.returncode == 1


# ---------------------------------------------------------------- 8 bytes warning + 哈希 error 优先级
def test_bytes_warning_and_hash_error_priority(tmp_path):
    proj = build_project(tmp_path)
    meta = json.loads((proj / "data" / "meta.json").read_text(encoding="utf-8"))
    meta["items"]["bytes"] = 999999            # bytes 漂移 → warning
    meta["items"]["sha256"] = "b" * 64          # 哈希不匹配 → error
    (proj / "data" / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1),
                                              encoding="utf-8")
    proc, rep = run_validator(proj)
    assert any("bytes" in w["message"] and "与实际" in w["message"]
               for w in issues_of(rep, severity="warning")), issues_of(rep, severity="warning")
    assert "bytes 漂移" in c5_of(rep, "meta.items")["detail"]
    assert any("sha256" in e["message"] for e in issues_of(rep, severity="error"))
    # error 不得被 warning 覆盖
    assert rep["status"] == "fail" and proc.returncode == 1
    assert rep["summary"]["errors"] >= 1 and rep["summary"]["warnings"] >= 1
    assert c5_of(rep, "meta.items")["result"] == "fail"


# ---------------------------------------------------------------- 9 字节漂移但哈希匹配
def test_bytes_drift_with_matching_hash_keeps_hash_pass(tmp_path):
    proj = build_project(tmp_path)
    meta = json.loads((proj / "data" / "meta.json").read_text(encoding="utf-8"))
    meta["items"]["bytes"] = 999999            # 仅 bytes 漂移，哈希仍是当前文件真实值
    (proj / "data" / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1),
                                              encoding="utf-8")
    proc, rep = run_validator(proj)
    c5 = c5_of(rep, "meta.items")
    assert c5["result"] == "warning", c5
    assert "sha256 一致" in c5["detail"], c5
    assert rep["status"] == "pass" and proc.returncode == 0
    assert rep["summary"]["warnings"] >= 1


# ---------------------------------------------------------------- 10 哈希与落盘字节一致
def test_hash_matches_final_on_disk_bytes(tmp_path):
    """模拟 fetch_data 的"先算字节、再写盘、再哈希"流程：哈希必须等于磁盘文件哈希。"""
    proj = build_project(tmp_path)
    payload = {"schema": 1, "items": {"a": {"n": "x"}}}
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    target = proj / "data" / "items.json"
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_bytes(raw)
    os.replace(tmp, target)                    # 与 write_atomic 同样的 tmp+replace
    digest = hashlib.sha256(raw).hexdigest()
    assert digest == sha256_file(target), "哈希必须对应最终落盘字节"
    meta = json.loads((proj / "data" / "meta.json").read_text(encoding="utf-8"))
    meta["items"]["sha256"] = digest
    meta["items"]["bytes"] = len(raw)
    (proj / "data" / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1),
                                              encoding="utf-8")
    proc, rep = run_validator(proj)
    assert c5_of(rep, "meta.items")["result"] == "pass"
    assert proc.returncode == 0


# ---------------------------------------------------------------- 11 落盘后重读元数据
def test_metadata_field_shape_after_reload(tmp_path):
    proj = build_project(tmp_path)
    meta = json.loads((proj / "data" / "meta.json").read_text(encoding="utf-8"))
    for key, fname in (("items", "items.json"), ("gunslots", "gunslots.json"),
                       ("gunPresets", "gun-presets.json")):
        assert key in meta
        block = meta[key]
        assert isinstance(block, dict)
        assert isinstance(block["sha256"], str), "sha256 必须是字符串"
        assert len(block["sha256"]) == 64
        assert block["sha256"] == block["sha256"].lower()
        int(block["sha256"], 16)                          # 必须是合法十六进制
        assert block["file"] == "data/" + fname
        assert block["sha256"] == sha256_file(proj / "data" / fname)


# ---------------------------------------------------------------- 12 上游哈希语义未变
def test_upstream_sources_semantics_unchanged():
    src = FETCH.read_text(encoding="utf-8")
    # 上游响应哈希仍是对下载原始字节计算
    assert '"sha256": hashlib.sha256(raw).hexdigest(),' in src
    # 本地哈希是新增的独立字段，取自最终落盘字节变量
    assert '"sha256": hashlib.sha256(items_bytes).hexdigest(),' in src
    assert 'hashlib.sha256(gunslots_bytes).hexdigest()' in src
    assert 'hashlib.sha256(gun_presets_bytes).hexdigest()' in src
    # 两类哈希来源不同：本地用 *_bytes 变量，上游用 raw
    assert "items_bytes" in src and "raw" in src


# ---------------------------------------------------------------- 13 schema 兼容
def test_schema_not_bumped_and_optional_field_tolerated():
    meta = json.loads((ROOT / "data" / "meta.json").read_text(encoding="utf-8"))
    assert meta["schema"] == 8, "本轮不改 schema（数据代次由 maps.json 共享，见报告 §4）"
    sys.path.insert(0, str(ROOT / "tools"))
    import fetch_data as fd
    assert fd.SCHEMA == 8
    # 新字段为可选：旧 meta（无 sha256）不得让校验器判为通过而静默
    assert "sha256" in meta["items"], "本轮应为三个业务文件建立本地哈希"


# ---------------------------------------------------------------- 14 无网络依赖
def test_no_network_dependency_introduced():
    v = VALIDATOR.read_text(encoding="utf-8")
    for bad in ("urllib", "socket", "http.client", "requests", "urlopen"):
        assert bad not in v, "校验器不得引入网络依赖: %s" % bad
    src = FETCH.read_text(encoding="utf-8")
    # fetch_data 本轮只增加哈希计算：哈希取自本地变量，且发生在对应写盘之后，其间无网络调用
    pairs = [('write_atomic(DATA_DIR / "items.json", items_bytes)',
              'hashlib.sha256(items_bytes).hexdigest()'),
             ('write_atomic(DATA_DIR / "gunslots.json", gunslots_bytes)',
              'hashlib.sha256(gunslots_bytes).hexdigest()'),
             ('write_atomic(gun_presets_file, gun_presets_bytes)',
              'hashlib.sha256(gun_presets_bytes).hexdigest()')]
    for w, h in pairs:
        iw, ih = src.index(w), src.index(h)
        assert iw < ih, "哈希应在写盘之后计算: %s" % w
        between = src[iw:ih]
        assert "urlopen" not in between and "http" not in between.lower(), between


# ---------------------------------------------------------------- 15 未改动真实业务数据
def test_real_business_data_untouched(tmp_path):
    """对比测试开始/结束时的真实业务文件哈希（防止夹具写穿到正式目录）。"""
    before = {f: sha256_file(ROOT / f) for f in REAL_DATA_FILES}
    proj = build_project(tmp_path)
    proc, rep = run_validator(proj)
    assert proc.returncode == 0
    after = {f: sha256_file(ROOT / f) for f in REAL_DATA_FILES}
    assert before == after, "测试期间真实业务数据被改动：%s" % (before,)


# ---------------------------------------------------------------- 真实 meta 与真实文件一致
def test_real_meta_hash_matches_real_files():
    meta = json.loads((ROOT / "data" / "meta.json").read_text(encoding="utf-8"))
    for key in ("items", "gunslots", "gunPresets"):
        block = meta[key]
        f = ROOT / block["file"]
        assert block["sha256"] == sha256_file(f), "%s 记录的哈希与磁盘文件不一致" % key
        assert len(block["sha256"]) == 64
    # sources[].sha256 仍是上游响应哈希（与本地文件哈希不同源，不应等于本地文件哈希）
    assert meta["sources"][0]["sha256"] != meta["items"]["sha256"]
