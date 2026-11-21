# R280 · 商人头像 / 英文原名 / 识图禁售图标

> 2026-11-14 · 用户三条反馈，均为显示层改动，不动价格数据与识别逻辑。

## 1. 市场界面「Sell to 商人收购价」用任务界面头像

**原来的问题**：`js/market.js` 的 `traderIconSrc()` 读 `items.json traders[].img`，
指向 `assets/icons-traders/*.svg` —— 那是项目自绘的「圆圈＋人形剪影＋缩写」占位图，
不是商人头像。任务界面 `tasks.js::db4Face()` 用的是
`data/tasks/traders.json` 的 `portrait`：`assets/icons-traders/portraits/<id>.webp`
（构建期落盘的游戏素材真人头像，16 位齐全，随包分发）。

**改法**：`traderIconSrc(id)` 直接返回 `assets/icons-traders/portraits/<id>.webp`，
与任务界面同一个文件；`traderIcon()` 挂两级 `onerror` 回退
（任务界面自绘 SVG → `unknown.svg`），头像缺文件也不破图；
`preloadTraderIcons()` 同步预加载头像。市场页所有商人图标（收购价、买价列、
Uses、兑换等）统一换成头像。

## 2. 商人名字统一英文原名

**原来的问题**：`traderNameOf()` 从 `items.json` 的 `n` 取名，其中 5 条是中文，
再按 slug 自己拼英文，产生 `Btr Driver`、`Mr Kerman` 之类与任务界面不一致的机翻名。
任务界面 `tasks.js` 用 `data/tasks/traders.json` 的 `nameEn` 并标 `data-i18n-skip`。

**改法**：market.js 内置 `TRADER_EN` 表（16 条 ID → nameEn），取值与
`data/tasks/traders.json` 逐条一致，`traderNameOf()` 优先查表。
`tests/test_r280_trader_display.py` 会读 tasks.json 比对全表，防止上游改名后漂移。
修正示例：`无线电台 → Radio Station`、`BTR司机 → BTR Driver`、
`竞技场裁判 → Ref`、`Kerman → Mr. Kerman`、`幸存者 → Survivor`。

## 3. 识图浮窗：红色购物车 → 最高收购价商人头像

**范围严格限定**：只替换 `priceSource === "trader"`（跳蚤禁售、按商人收购价显示）
这一档的**红色购物车图标**。蓝色购物车（`traderSell`）、跳蚤价、黄色 `?` 徽章、
价格数字/档位颜色/字号/位置、散装弹与弹药包逻辑一律不动。

- `serve.py::_ocr_resolve_price()` 在该分支已经返回 `price.traderId`
  （`_trader_sell_price()` 取 `sl` 里价格最高的一条 = 最高收购价商人），
  `/api/ocr/overlay/state` 的字段白名单保留整个 `price` dict，链路无需改动。
- `tools/scan.py` 新增 `trader_portrait_id()`、`_trader_portrait()`（按 id+尺寸缓存，
  冻结态从 `_MEIPASS` 找资源）、`_draw_trader_badge()`（圆形贴头像）。
- `_draw_price_line()` 只在 `cart_kind == "buy"` 时改调头像绘制；`sell` 仍走 `_draw_cart()`。
- **占位尺寸仍用 `_cart_metrics()`**，所以 `_fixed_label_font()` 的算宽、右对齐、
  行距完全不变 —— 真正只换了那个图标本身。
- 头像文件缺失时画中性灰圆并记日志，**不退回红色购物车**。
- 市场页识别结果表格的 tooltip 文案同步改成「浮窗显示该商人头像」；
  蓝色购物车文案保持原样。

## 验证

| 项 | 结果 |
| --- | --- |
| `tests/test_r280_trader_display.py` | 10 passed（名字逐条比对 tasks.json、头像路径/文件存在、buy/sell/flea 三分支、真实头像贴图像素） |
| 旧测试 `test_r249_overlay_xp_trader.py` | 红购物车断言改写为「头像替换购物车」，24 passed（两组一起） |
| 相关回归（market / scan / overlay / tier / tasks / loadout） | 112 passed（除下列环境性失败） |
| 开发态 HTTP | `/js/market.js` 200 且含新表、`/data/tasks/traders.json` 200、头像 webp 200 |
| 视觉 | `build/_r280_overlay_preview.png`（三档图标对比）、`build/_r280_trader_names_preview.png`（16 位头像＋英文名） |

**全量测试的环境噪音**：一次全量运行里有 6 个既有「数据管线 round-trip」用例
（`build_i18n.py` / `slotfix` 等）因 D: 盘 `os.replace(tmp, path)` 偶发
`PermissionError [WinError 5]` 失败，与本次改动无关：清掉 `data/*.tmp` 残留后
逐个单独重跑 **6/6 通过**，同目录新文件的 `os.replace` 也正常。
疑与本机 D: 卷过滤驱动（R279-fix 里同样表现出资源写回被拒）有关。

## 生效范围

- 源码 `js/market.js`、`tools/scan.py` 已改；
- 已同步到开发态产物 `dist/EFTMap/_internal/{js/market.js,tools/scan.py}`，
  本地刷新即可看到；
- **`release/` 与 `release-test/` 里的 0.2.7 安装包仍是上一版 payload**，
  三项改动尚未进安装包。需要发布时用已修好的 `build/build_release.ps1 -SkipBase`
  重新生成（脚本会自动把 Setup 构建放到 C: 盘临时目录）。
