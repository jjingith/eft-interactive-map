"""`tools/shot_selftest.py` 的测试：只测纯逻辑，**绝不真的发键或碰别人的窗口**。

自检脚本的价值全在「结论准不准」：它把「自动截图没反应」拆成 9 步，每步都要给出
正确的下一步。所以这里重点验三件事：

1. 日志门（`_log_phase`）能真的从日志尾推出现在是不是在战局里——
   这道门是**我方独有**的（参考实现没有），判错就会「开关开着、一张都不发」；
2. 截图键的取值顺序（配置 > 日志）与解析失败时的说法；
3. 报告的结论只认**第一个 FAIL**，不会被后面的行覆盖。

真发键那条路（`--send` / `--manual`）不测：它会按键、抢焦点，测试不能干这种事。
"""

from __future__ import annotations

import os

import pytest

import config
import shot_selftest as S


# --------------------------------------------------------------- 日志门

def make_session(root, name="log_2026.11.02_10-00-00_1.3.0.0.48484", lines=()):
    """造一个「游戏目录 + Logs + 会话 + application 日志」的假结构。"""
    game = root / "EFT"
    session = game / "Logs" / name
    session.mkdir(parents=True)
    base = name[len("log_"):]
    log = session / ("%s application_000.log" % base)
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(game), base


def test_log_phase_reads_spawn_event(tmp_path):
    game, base = make_session(tmp_path, lines=[
        "2026-11-02 10:00:01.000 | 0.1.0 | INFO | scene preset path:maps/RezervBase_preset.bundle",
        "2026-11-02 10:00:02.000 | 0.1.0 | INFO | LocationLoaded",
        "2026-11-02 10:00:03.000 | 0.1.0 | INFO | PlayerSpawnEvent:",
    ])
    phase, note = S._log_phase(game)
    assert phase == "start", note            # 最后一条是出生事件 → 在战局中
    assert base in note


def test_log_phase_stops_at_loading_when_not_spawned_yet(tmp_path):
    """已经进图但还没出生 → phase 停在 loading，自检要说「不在战局中，会暂停发键」。"""
    game, _ = make_session(tmp_path, lines=[
        "2026-11-02 10:00:01.000 | 0.1.0 | INFO | scene preset path:maps/RezervBase_preset.bundle",
        "2026-11-02 10:00:02.000 | 0.1.0 | INFO | LocationLoaded",
    ])
    phase, _note = S._log_phase(game)
    assert phase == "loading"


def test_log_phase_none_when_no_raid_events(tmp_path):
    game, _ = make_session(tmp_path, lines=["2026-11-02 10:00:00.000 | 0.1.0 | INFO | 启动"])
    phase, note = S._log_phase(game)
    assert phase is None
    assert "没读到战局阶段" in note


def test_log_phase_explains_missing_dirs(tmp_path):
    assert S._log_phase("")[0] is None
    assert "没有游戏目录" in S._log_phase("")[1]
    assert "找不到 Logs" in S._log_phase(str(tmp_path / "ghost"))[1]


def test_log_phase_survives_garbage_log(tmp_path):
    """日志里混着二进制垃圾也不能抛异常——自检崩了比给错结论更糟。"""
    game, base = make_session(tmp_path, lines=["\x00\xff 乱码 PlayerSpawnEvent: 还在"])
    phase, _note = S._log_phase(game)
    assert phase == "start"          # 关键词还在，仍能识别


# --------------------------------------------------------------- 截图键

def test_key_prefers_config_over_log(tmp_path, monkeypatch):
    config.save({"auto_screenshot": {"key": "F10"}}, str(tmp_path))
    monkeypatch.setattr(config, "app_dir", lambda: str(tmp_path))
    assert S._key_from_config_or_log("") == "F10"


def test_key_falls_back_to_none_without_config_or_game_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "app_dir", lambda: str(tmp_path))
    assert S._key_from_config_or_log("") is None


# --------------------------------------------------------------- 报告结论

def test_report_keeps_first_blocking_item():
    """结论只认第一个 FAIL：后面的失败大多是它的连锁反应，先说根因才有用。"""
    report = S.Report()
    report.add(S.OK, "平台", "Windows")
    report.add(S.FAIL, "权限对等", "游戏管理员、工具普通")
    report.add(S.FAIL, "截图目录", "不存在")
    assert report.blocking == "权限对等"


def test_report_without_fail_has_no_blocking():
    report = S.Report()
    report.add(S.OK, "平台", "Windows")
    report.add(S.WARN, "游戏进程", "没检测到")
    assert report.blocking is None


def test_report_show_states_whether_keys_were_sent(capsys):
    report = S.Report()
    report.add(S.OK, "平台", "Windows")
    report.show()
    out = capsys.readouterr().out
    assert "未发送任何按键" in out


def test_cli_help_does_not_touch_windows(capsys):
    """`--help` 只打印说明：不读日志、不查权限、不发键。"""
    with pytest.raises(SystemExit) as exc:
        S.main(["--help"])
    assert exc.value.code == 0
    assert "--manual" in capsys.readouterr().out


# ------------------------------------------------- R32.8：PrtSc 被系统截屏工具抢走
# 实测（2026-11-02）：游戏内截图绑的是 SysReq，自检九项全绿、--send 也"发送成功"，
# 但截图目录一直没图 —— 因为 Windows 11 默认把 PrtSc 拿去开截屏工具。
# 这条警告存在的意义就是别再让人去查注入层。

def test_snapshot_key_is_flagged():
    for name in ("SysReq", "PrintScreen", "PrtSc"):
        note = S._snapshot_key_warning(name)
        assert note, "%s 应该报警" % name
        assert "截屏工具" in note and "F10" in note


def test_ordinary_screenshot_keys_are_not_flagged():
    for name in ("F10", "V", "Ctrl+F10", "F9"):
        assert S._snapshot_key_warning(name) is None, name


def test_missing_or_broken_key_is_not_flagged():
    """没键 / 认不出的键由「截图键」那一行自己报错，这里不重复喊。"""
    for name in (None, "", "Ctrl+Whatever"):
        assert S._snapshot_key_warning(name) is None
