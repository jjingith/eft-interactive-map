"""R32 关于菜单 + 任务文案修正。

两件事各测一头：

1. **任务等待时间的语义**（用户报的 bug）：`availableDelaySeconds` 是「可**接取**之前还要等多久」，
   早期生成脚本写成「接取后需等待…才可完成/交付」，把前置等待说成了交付等待。
   测试从三处夹住它：生成脚本的文案、已落盘的数据、页面渲染。
2. **来源说明集中到「关于」**：数据来源 / 复核状态 / 使用说明以前散落在任务详情、数据概览、
   模式说明条、地图弹窗里，正经看内容时会被反复打断。现在只留在顶部菜单「关于」。
   这里既验「关于里确实有」，也验「别处确实没了」——只验前者会漏掉回潮。
"""

from __future__ import annotations

import json
import os
import re

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app.js")
TASKS = os.path.join(ROOT, "tasks.js")
INDEX = os.path.join(ROOT, "index.html")
STYLE = os.path.join(ROOT, "style.css")
APP_CSS = os.path.join(ROOT, "assets", "xp-ui", "xp-ui-app.css")
FETCH = os.path.join(ROOT, "tools", "fetch_tasks.py")
GUIDES = [os.path.join(ROOT, "data", "tasks", "guides.%s.json" % m)
          for m in ("regular", "pve", "pvps")]


def _text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


# --------------------------------------------------------------- 1. 时间语义

def test_generator_uses_the_correct_meaning():
    """`availableDelaySeconds` = 「可接取前的等待」，不是「接取后的交付等待」。"""
    src = _text(FETCH)
    # 注释里会引用旧说法（说明为什么改），所以只看真正的代码行
    code = "\n".join(line for line in src.splitlines()
                     if not line.lstrip().startswith("#"))
    assert "接取后需等待" not in code, "生成脚本仍在用错误的语义"
    assert "才可接取此任务" in code
    # 说明里要点明「前置条件满足后」这层意思，否则还是会被读成「接取后」
    assert "前置条件满足后" in code


@pytest.mark.parametrize("path", GUIDES)
def test_shipped_guide_data_has_no_stale_wording(path):
    raw = _text(path)
    assert "接取后需等待" not in raw, "%s 里还有旧文案" % os.path.basename(path)


@pytest.mark.parametrize("path", GUIDES)
def test_shipped_guide_data_has_the_new_wording_and_is_valid_json(path):
    data = json.loads(_text(path))
    hits = [note for guide in (data.get("guides") or {}).values()
            for note in (guide.get("notes") or []) if "才可接取此任务" in note]
    assert hits, "%s 里没有新文案——可能没重新生成" % os.path.basename(path)
    for note in hits:
        assert re.search(r"前置条件满足后需再等待约 \d+ 分钟才可接取此任务。", note), note


def test_task_detail_does_not_claim_waiting_blocks_handin():
    """详情页正文里不该再出现「接取后才可完成/交付」这种说法。"""
    assert "才可完成/交付" not in _text(TASKS)


# --------------------------------------------------------------- 2. 关于菜单

def test_about_lives_in_app_menu():
    """第一阶段：关于面板归入顶部「应用菜单」的 about 分区。"""
    html = _text(INDEX)
    panel_start = html.index('id="am-app-panel"')
    panel_end = html.index('id="context-bar"')
    panel = html[panel_start:panel_end]
    assert 'id="app-sec-about"' in panel
    assert 'data-sec="about"' in panel
    assert 'id="about-block"' in panel, "关于面板必须在应用菜单的 about 分区里"
    # 旧按钮仍保留为隐藏锚点，避免 app.js 的 id 选择器失效
    assert 'id="menu-about"' in html
    assert 'aria-controls="about-block"' in html


def test_about_panel_carries_every_disclaimer():
    html = _text(INDEX)
    start = html.index('id="about-block"')
    panel = html[start:html.index("</section>", start)]
    # R70：面板瘦身为「短标签 + 链接」清单，但许可署名与必要说明一条都不能少。
    for must in ("数据来源", "底图", "图标", "任务", "行情", "商标", "公式",
                 "tarkov.dev", "the-hideout/tarkov-dev", "MIT",
                 "tarkov-dev-svg-maps", "CC BY-NC-SA 4.0", "非商业",
                 "Battlestate Games", "永久免费", "严禁售卖",
                 "未逐条复核", "构建期快照", "随右上角 PvP / PvE / PvPS 与价格档", "运行期不联网",
                 'id="about-meta-line"'):
        assert must in panel, "关于面板缺少：%s" % must


def test_about_menu_is_owned_by_app_menu():
    """第一阶段：关于不再走 app.js 的旧下拉绑定，由应用菜单分区控制。"""
    src = _text(APP)
    assert 'el.menuAbout = $("menu-about")' in src
    assert 'el.aboutBlock = $("about-block")' in src
    assert "{ btn: el.menuAbout, panel: el.aboutBlock }" not in src, \
        "关于面板已迁入应用菜单，不应再进旧 bindMenu 列表"

    menu_src = _text(os.path.join(ROOT, "js", "app-menubar.js"))
    assert "function bindAppMenu" in menu_src
    assert "am-app-panel" in menu_src
    assert "app-app-sec" in menu_src


def test_about_panel_is_static_inside_app_menu():
    """旧下拉的绝对定位必须被设置弹层覆盖，否则会浮出面板外。"""
    css = _text(APP_CSS)
    block = css[css.index("html body .app-app-body .app-menu-panel,"):]
    block = block[:block.index("}")]
    assert "position: static" in block


# --------------------------------------------------------------- 3. 别处不再重复

@pytest.mark.parametrize("phrase", [
    "待人工复核", "攻略由任务数据派生", "攻略已人工整理",
    "数据来源：tarkov.dev 端点", "上游端点",
])
def test_task_ui_no_longer_repeats_the_disclaimers(phrase):
    src = _text(TASKS)
    # 允许出现在注释里（说明「已收进关于」），但不允许出现在渲染用的字符串里
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("*") or stripped.startswith("/*"):
            continue
        assert phrase not in line, "任务界面里仍在渲染：%s（%s）" % (phrase, line.strip()[:80])


def test_map_popup_drops_the_source_line():
    """地图上的任务弹窗以前跟着一行「攻略数据来源：tarkov.dev（开源 MIT）」。"""
    src = _text(APP)
    assert "攻略数据来源" not in src


def test_season_notice_moved_to_about_by_r217():
    """R217：用户要求把**赛季说明**从任务详情底部搬到「关于」——详情页不再重复。

    这里同时验两头：关于面板里确实有这句，任务详情里确实没了（只验一头会漏掉回潮）。
    """
    html = _text(INDEX)
    start = html.index('id="about-block"')
    panel = html[start:html.index("</section>", start)]
    assert 'id="about-season-note"' in panel, "关于面板缺少赛季说明节点"
    for must in ("赛季服说明", "pvp-season", "旧赛季的完成状态当作新赛季进度"):
        assert must in panel, "关于面板缺少：%s" % must

    src = _text(TASKS)
    detail = src[src.index("function renderDetail()"):src.index("function condLabel")]
    assert "赛季服说明" not in detail, "任务详情仍在渲染赛季说明"
    assert "tk-detail-foot" not in src, "详情页 footer 已随 R217 移除"
    assert "tk-detail-warn" not in src


def test_season_notice_period_comes_from_data_not_hardcoded():
    """周期必须由 season.json 填；写死日期会在数据更新后自相矛盾。"""
    src = _text(TASKS)
    assert "function syncAboutSeasonNote" in src
    assert '"about-season-note"' in src
    fn = src[src.index("function syncAboutSeasonNote"):]
    fn = fn[:fn.index("\n  }\n")]
    assert "state.season" in fn
    assert "startISO" in fn and "endISO" in fn
    assert not re.search(r"20\d\d-\d\d-\d\d", fn), "不要在文案里写死赛季日期"
