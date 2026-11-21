# -*- coding: utf-8 -*-
"""R248：修「改 ShareX 后 OCR 结果不出现 / 耗时 39 秒」。

用户反馈（2026-11-12 12:16 / 12:19）：
  「截图很流畅 但是现在怎么不会出现ocr的结果了」
  「我是用游戏内的截图试的 为什么耗时会这么久 昨天成功的那个版本基本上
    五六秒就行了 现在把截屏改成sharex反而不行了」

定位（分段计时，非猜测）：
  · BFF `tookMs` 只有 0.5~4s，HTTP 墙钟却 19~24s；
  · `price_history.series()` 对每个 (快照 gz, 物品 id) 组合调用 `_gz_rows` →
    同一个 gz 被解压 `len(wanted)` 遍：60 物品 × 142 快照 ≈ 8500 次 ≈ 24s；
  · 昨天 21 件匹配约 5s、今天 81 件匹配 39s —— 成本随匹配数线性爆炸；
  · 松手后**零反馈**，用户等不及再按热键，热键把刚出现的浮窗关掉（日志 12:11:03
    「透明浮窗已显示 81 件」与「选区窗已显示」同秒）。

修复：
  1. `_gz_rows_batch()`：一份 gz 只解压一次、批量取行；按 (path,mtime,size) 缓存文本；
  2. `serve.py`：3 天 / 30 天合并为一次 `series(days=30)`，本地按时间戳切 72h；
  3. `watch_native()`：识别放后台线程 + 立即显示「识别中」提示 + 防重入，
    结果回主线程创建浮窗（避免热键误关）。
"""

import os
import sys

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TEST_DIR)
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

sys.path.insert(0, TOOLS)
import price_history  # noqa: E402


def test_batch_gz_rows_exists_and_series_uses_it():
    src = open(os.path.join(TOOLS, "price_history.py"), encoding="utf-8").read()
    assert "def _gz_rows_batch(" in src
    body = src[src.index("def series("):src.index("def clear_cache")]
    assert "_gz_rows_batch(ref, wanted)" in body, "series 必须走批量解压"
    assert "_gz_rows(ref, item_id)" not in body, "不允许再对每份 gz 按 id 逐个解压"
    assert "_gz_text_cache" in src and "clear_cache" in src


def test_batch_gz_rows_one_read_for_many_items(tmp_path):
    """批量接口对 N 个物品只解压一次（用 monkeypatch 计数 gzip.open）。"""
    import gzip
    import json

    path = tmp_path / "snapshot.json.gz"
    rows = {"aaa": {"l": 100}, "bbb": {"l": 200}, "ccc": {"l": 300}}
    with gzip.open(str(path), "wt", encoding="utf-8") as fh:
        json.dump(rows, fh)

    calls = {"n": 0}
    real_open = gzip.open

    def counting(*args, **kwargs):
        calls["n"] += 1
        return real_open(*args, **kwargs)

    gzip.open = counting
    try:
        price_history.clear_cache()
        status, got = price_history._gz_rows_batch(str(path), {"aaa", "bbb", "ccc", "zzz"})
        assert status == "ok"
        assert got["aaa"] == {"l": 100}
        assert got["zzz"] is None
        assert calls["n"] == 1, "同一个 gz 只能解压一次，实际 %d 次" % calls["n"]
        # 第二次（缓存命中）连解压都不需要
        price_history._gz_rows_batch(str(path), {"aaa", "bbb"})
        assert calls["n"] == 1
    finally:
        gzip.open = real_open
        price_history.clear_cache()


def test_serve_calls_history_series_once():
    src = open(os.path.join(TOOLS, "serve.py"), encoding="utf-8").read()
    block = src[src.index("if match_ids and logged_in:"):src.index("out_matches = []")]
    assert block.count("price_history.series(") == 1, "30 天/72h 只能扫一次历史"
    assert "days=30" in block and "cutoff3" in block


def test_watch_native_gives_progress_and_keeps_ui_responsive():
    src = open(os.path.join(TOOLS, "scan.py"), encoding="utf-8").read()
    body = src[src.index("def watch_native"):src.index("# 演示模式")]
    assert "threading.Thread(target=worker" in body, "识别不能阻塞消息循环"
    assert "show_status(" in body and "hide_status(" in body
    assert "recognizing[\"flag\"]" in body, "识别中要防重入/防热键误关浮窗"
    assert "_gz_rows_batch" not in body  # 宿主侧不碰历史文件
