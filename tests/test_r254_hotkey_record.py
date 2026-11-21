# -*- coding: utf-8 -*-
"""R254：热键改游戏式按键记录 + 强制修饰键（修「单键被全局吞掉」事故）。

用户反馈（2026-11-12 15:34）：
  「这个功能的快捷键 你改成和游戏里一样 按按钮然后记录 这样的修改，
    刚才不小心按到了 a 和 d 中间的按钮 我现在按不了那个键了」

事故链：旧 UI 是手打文本框 → 用户误触存进单键 → 宿主 RegisterHotKey 全局
注册 → 那个游戏按键被系统吞掉。修复：
  ① UI：点按钮 → 「按下新快捷键…」→ keydown 记录 → Esc 取消；**单键拒绝**
    （提示须含 Ctrl/Alt/Shift）；
  ② 宿主：配置被手改出单键时 hotkey_requires_mod() 拒绝注册（热更新与启动
    都防），不吞键。
"""

import os
import sys

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TEST_DIR)
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import scan  # noqa: E402


# ------------------------------------------------------------ 宿主防护

def test_hotkey_requires_mod():
    assert scan.hotkey_requires_mod(((0x0002, 0x50))) is True      # ctrl+p
    assert scan.hotkey_requires_mod(((0x0001, 0x50))) is True      # alt+p
    assert scan.hotkey_requires_mod(((0, 0x53))) is False          # 裸 S
    assert scan.hotkey_requires_mod(((0, 0xDC))) is False          # 裸 \（事故键）
    assert scan.hotkey_requires_mod(None) is False


def test_resolve_hotkey_rejects_bare_key(monkeypatch, tmp_path):
    """配置被手改成单键：不崩、不注册单键，回退默认 ctrl+alt+p。"""
    import config
    import overlay

    cfg = tmp_path / "eftmap.config.json"
    cfg.write_text('{"ocrScan": {"hotkey": "s"}}', encoding="utf-8")
    monkeypatch.setattr(config, "load", lambda d=None: {"ocrScan": {"hotkey": "s"}})

    class Args:
        hotkey = None

    hk = scan.resolve_hotkey(Args, None)
    assert hk == overlay.parse_hotkey(scan.DEFAULT_HOTKEY), \
        "单键配置应回退默认热键"
    assert scan.hotkey_requires_mod(hk), "回退的热键必须带修饰键"


def test_resolve_hotkey_normal(monkeypatch):
    import config

    monkeypatch.setattr(config, "load",
                        lambda d=None: {"ocrScan": {"hotkey": "ctrl+alt+p"}})

    class Args:
        hotkey = None

    assert scan.resolve_hotkey(Args, None) == (0x0003, 0x50)   # ctrl+alt+p
    assert scan.resolve_hotkey(type("A", (), {"hotkey": "ctrl+f8"})(), None) == (0x0002, 0x77)


def test_watch_reload_rejects_bare_key():
    """两处热更新循环都必须先过 hotkey_requires_mod 再注册。"""
    src = open(os.path.join(TOOLS, "scan.py"), encoding="utf-8").read()
    assert src.count("hotkey_requires_mod(parsed)") >= 2, \
        "watch_native 与 legacy 循环都要拒绝单键热键"
    assert src.count('parsed = "invalid"') >= 2


# ------------------------------------------------------------ 前端契约

def test_page_hotkey_button_contract():
    html = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    assert 'button type="button" class="ocr-hotkey-btn" id="ocr-hotkey"' in html, \
        "热键 UI 必须是按钮（游戏式按键记录）"
    assert 'type="text" id="ocr-hotkey"' not in html, "手打文本框必须移除"


def test_app_records_keystroke_and_rejects_bare_key():
    js = open(os.path.join(ROOT, "app.js"), encoding="utf-8").read()
    for marker in (
            "function hkName", "function hkMods", "function hkOnKey",
            "function hkStop", "function hkError",
            'e.key === "Escape"',                      # Esc 取消
            'document.addEventListener("keydown", hkOnKey, true)',
            "hkError(\"须含 Ctrl/Alt/Shift（避免占用游戏键）\")",
            'queuePrefs({ ocrScan: { hotkey: text } })',
            '"is-listening"', '"is-error"'):
        assert marker in js, "app.js 缺 %s" % marker


def test_styles_for_listening_state():
    css = open(os.path.join(ROOT, "style.css"), encoding="utf-8").read()
    for marker in (".ocr-hotkey-btn", ".ocr-hotkey-btn.is-listening",
                   ".ocr-hotkey-btn.is-error"):
        assert marker in css, "style.css 缺 %s" % marker
