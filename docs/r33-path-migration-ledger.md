# R33 逆向素材路径迁移留痕

host=HOMONAS user=MASTERJJ at=2026-11-03T10:00:00+08:00 round=R33-path-migration

> 本工作区为局域网共享目录。本文件记录本轮「旧逆向素材路径 → 逆向参考」的引用替换、
> 校验结果与文件哈希，便于其他操作者核对。后续改动请沿用同样的头部格式。

## 1. 迁移事实

- `D:\personal\trae\02-塔科夫\build-re-xiaomeow` → `D:\personal\trae\02-塔科夫\逆向参考\build-re-xiaomeow`
- `D:\personal\trae\02-塔科夫\build-re-gunsmith` → `D:\personal\trae\02-塔科夫\逆向参考\build-re-gunsmith`
- `D:\personal\trae\02-塔科夫\tarkov.kaedeori` → `D:\personal\trae\02-塔科夫\逆向参考\tarkov.kaedeori`
- `db4tarkov-local`、`XiaoMeowToolbox-win-Setup-1.5.3 (1).exe`、`减伤公式*.png`、
  `子弹对护甲耐久伤害.png`、`游戏内截图*.png`、`塔科夫护甲.mp4` 同目录移入 `逆向参考`。
- 旧根目录路径已确认不存在；新目录已确认存在。

## 2. 改动清单（文件 → 修改条数）

| 文件 | 修改条数 | SHA256 |
|---|---:|---|
| `AGENT_HANDOFF.md` | 3 处路径（2 行） | `CE3284180DFD68FC4E4590103E2A598EB710FCD2A1D63F3E47EDE5DFBCDF2ACB` |
| `docs/r32-xiaomeow-re/REPORT.md` | 8 处（8 行） | `9A08FDBCF079BB01A3C6139627EF5290D2C855C04D427C9CBB63DA5EA1B14A2F` |
| `tools/host/vendor/PROVENANCE.txt` | 1 处 | `5CFA3CDB7EF9A9BD176C3214605203E92EE0244D00453E7DA5463FA165B682B3` |
| `tools/r208_scan_kaedeori.py` | 1 处 | `D1F7228FE92C0157ED598A1B2FBE12C9CA645B6734B41A6D5E2C9F1C113BEC4A` |
| `tools/r208_unpack_asar.py` | 2 处 | `283D3093E3BFD6421919549DB1A777EE67221E2EF457A2A95403A240E727B2B9` |

合计 5 个文件、15 处路径替换。`README.md` 搜索无命中，未改。

## 3. 命中与替换明细

| 文件:行 | 原文 | 新文 |
|---|---|---|
| `AGENT_HANDOFF.md:1258` | `D:\...\tarkov.kaedeori\extracted\report\HANDOFF.md` | `D:\...\逆向参考\tarkov.kaedeori\extracted\report\HANDOFF.md` |
| `AGENT_HANDOFF.md:1830` | `D:/.../游戏内截图.png`、`游戏内截图2.png` | `D:/.../逆向参考/游戏内截图.png`、`D:/.../逆向参考/游戏内截图2.png` |
| `docs/r32-xiaomeow-re/REPORT.md:3` | `D:\...\XiaoMeowToolbox-win-Setup-1.5.3 (1).exe` | `D:\...\逆向参考\XiaoMeowToolbox-win-Setup-1.5.3 (1).exe` |
| `docs/r32-xiaomeow-re/REPORT.md:5` | `D:\...\build-re-xiaomeow\` | `D:\...\逆向参考\build-re-xiaomeow\` |
| `docs/r32-xiaomeow-re/REPORT.md:39` | `build-re-xiaomeow/`（相对） | `逆向参考/build-re-xiaomeow/` |
| `docs/r32-xiaomeow-re/REPORT.md:651` | `build-re-xiaomeow/dump_il.py` | `逆向参考/build-re-xiaomeow/dump_il.py` |
| `docs/r32-xiaomeow-re/REPORT.md:652` | `build-re-xiaomeow/il_autoshot.txt` | `逆向参考/build-re-xiaomeow/il_autoshot.txt` |
| `docs/r32-xiaomeow-re/REPORT.md:653` | `build-re-xiaomeow/il_dump.txt` | `逆向参考/build-re-xiaomeow/il_dump.txt` |
| `docs/r32-xiaomeow-re/REPORT.md:654` | `build-re-xiaomeow/il_minimapwin.txt` | `逆向参考/build-re-xiaomeow/il_minimapwin.txt` |
| `docs/r32-xiaomeow-re/REPORT.md:655` | `build-re-xiaomeow/ocr_summary.txt` | `逆向参考/build-re-xiaomeow/ocr_summary.txt` |
| `tools/host/vendor/PROVENANCE.txt:8` | `d:\...\build-re-xiaomeow\app\` | `d:\...\逆向参考\build-re-xiaomeow\app\` |
| `tools/r208_scan_kaedeori.py:20` | `D:\...\tarkov.kaedeori\extracted\app\dist` | `D:\...\逆向参考\tarkov.kaedeori\extracted\app\dist` |
| `tools/r208_unpack_asar.py:26` | `D:\...\tarkov.kaedeori\tarkov-kaedeori-client` | `D:\...\逆向参考\tarkov.kaedeori\tarkov-kaedeori-client` |
| `tools/r208_unpack_asar.py:28` | `D:\...\tarkov.kaedeori\extracted\app` | `D:\...\逆向参考\tarkov.kaedeori\extracted\app` |

## 4. 抽查（新路径真实存在）

| # | 新路径 | 结果 |
|---:|---|---|
| 1 | `逆向参考\build-re-xiaomeow\app` | 存在（目录） |
| 2 | `逆向参考\build-re-xiaomeow\dump_il.py` | 存在 |
| 3 | `逆向参考\tarkov.kaedeori\extracted\report\HANDOFF.md` | 存在 |
| 4 | `逆向参考\tarkov.kaedeori\tarkov-kaedeori-client` | 存在（目录） |
| 5 | `逆向参考\XiaoMeowToolbox-win-Setup-1.5.3 (1).exe` | 存在 |
| 附加 | `逆向参考\游戏内截图.png`、`游戏内截图2.png` | 均存在 |

## 5. 未改动的命中（非路径 / 非素材引用）

- `.workbuddy/memory/2026-10-30.md:6`：`tarkov.kaedeori-client` 是项目名，不是路径。
- `docs/superpowers/specs/2026-10-17-eft-interactive-map-design.md:77`、
  `tools/fetch_data.py:566`：`tarkov.kaedeori.com` 是参考站域名，不是本地路径。
- `docs/r32-xiaomeow-re/REPORT.md:23` 是安装包文件名清单，不是路径。
- `docs/r32-xiaomeow-re/REPORT.md:167`、`docs/USAGE.md:338`、
  `docs/superpowers/specs/...:34/123/529`、`tests/test_r18_1_round.py:56`、
  `tests/test_r18_2_round.py:183`、`tests/test_shot_selftest.py:126`、
  `tools/eftlog.py`、`tools/launcher.py`、`tools/keyinput.py`、`tools/shot_selftest.py`、
  `tools/serve.py` 的「游戏内截图」均为功能词，不是文件路径。
- `build-cache/kaedeori-assets/main.js` 命中仅为 `tarkov.kaedeori.com` 域名，生成缓存，未改。
- `release/` 搜索无命中，未改。

## 6. 已知缺口

- `docs/r32-xiaomeow-re/REPORT.md:653` 指向的
  `逆向参考\build-re-xiaomeow\il_dump.txt` 在新目录中**不存在**（新目录只有
  `dump_il.py`、`il_autoshot.txt`、`il_minimap.txt`、`il_minimapwin.txt`、`ocr_summary.txt` 等）。
  路径已按迁移规则更新，但目标文件缺失，未伪造替换文件。

## 7. 边界

- 只改路径引用，未改报告正文、未删文件。
- 未改 `release/`、未 git 提交。
- 改动前已核对目标文件 mtime（均为 11/2 及更早，无本轮并行修改迹象）；
  如其他操作者随后改动，请以本文件哈希为基线复核。
