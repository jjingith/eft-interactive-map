"""R270：一级菜单栏顶部多出一条 16px 空白行 —— 元凶是文件开头叠了 8 个 BOM。

现象（2026-11-13 11:53）：`.app-menubar` 的 top 是 20 而不是 0，最上面多一条空白。

原因：`index.html` 开头连续 8 个 `EF BB BF`。HTML 解析器只把**第一个**当 BOM 吃掉，
剩下 7 个 U+FEFF 成为 body 里的一个文本节点；U+FEFF 不是可折叠空白，会撑出一个
行盒（实测 16px）→ 正是那条空行。`app.js` 同样叠了 8 个（JS 里 U+FEFF 属于空白，
无害，但一并收敛）。

这里锁死「开头最多 1 个 BOM」，避免以后再被逐次写文件叠上去。
"""

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOM = b"\xef\xbb\xbf"

FILES = ["index.html", "app.js", "js/market.js", "js/app-menubar.js",
         "style.css", "market.css", "assets/xp-ui/xp-ui-app.css",
         "theme-windows-xp.css"]


def _leading_boms(path):
    data = open(path, "rb").read()
    n = 0
    while data[n * 3:(n + 1) * 3] == BOM:
        n += 1
    return n, data


def test_no_duplicate_bom_at_top_of_assets():
    bad = {}
    for rel in FILES:
        path = os.path.join(ROOT, rel)
        if not os.path.exists(path):
            continue
        n, _ = _leading_boms(path)
        if n > 1:
            bad[rel] = n
    assert not bad, "文件开头叠了多个 BOM，会在 HTML 里变成一条空白行：%s" % bad


def test_index_html_has_document_marker_after_bom():
    """跳过开头的 BOM 后，第一个有效内容必须是 <!DOCTYPE html>。"""
    n, data = _leading_boms(os.path.join(ROOT, "index.html"))
    head = data[n * 3: n * 3 + 32].decode("utf-8", "replace")
    assert head.lstrip().lower().startswith("<!doctype html>"), head


def test_no_stray_bom_run_inside_index_html():
    """BOM 只允许出现在文件开头；正文里再出现会被渲染成零宽字符或空行。"""
    n, data = _leading_boms(os.path.join(ROOT, "index.html"))
    rest = data[n * 3:]
    assert rest.count(BOM) == 0, "正文里还有 %d 个 BOM" % rest.count(BOM)
