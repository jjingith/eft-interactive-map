# R237 · 真实游戏截图调优：OCR 短名表 + 碎片守卫

## 用户原话（2026-11-11 15:21）

> 「D:\personal\trae\02-塔科夫\ui图标 我在这放了一张专用的截图」

样本：`ui图标/ocr测试专用游戏内截图.png`（**3524×1738**，角色装备界面，
三栏穿戴/胸挂/背部武器，中文界面、物品显示**短名**）。

## 三个迭代的效果线（同一张真实截图）

| 版本 | 结果 |
| --- | --- |
| R236（分块后，用户实测「只认出几个」的场景） | 27 匹配，其中 ~12 条真命中；Specter→Aspect 钥匙、T30→丰和基座、Robber→Bomber 帽子等短名错配 |
| + 匹配器数字守卫 / 短 latin 碎片守卫 | 46-48 匹配，`un`/`EC` 消失 |
| **R237 最终（+ 短名表索引）** | **53 匹配 / 20s，HUD 碎片误报清零**，真值命中 ~48 条 |

## 根因与修法

1. **游戏显示短名，索引里没有**。items.json 的 `sn` 上游全部退化成
   "<id> ShortName" 占位符（fetch_data.py:1668 透传的 `shortName` 字段本身就是
   被污染的数据——EN 侧无效；**items_zh 翻译表的 `<id> ShortName` 才是真的**，
   游戏中文界面显示的正是它）。
   - 新增 `tools/build_ocr_names.py`：复用 fetch_data 的抓取器（UA 变体 + curl
     回退 + build-cache，Cloudflare 稳过），拉 `items` + `items_zh`，生成
     **data/ocr-item-names.json**（5480 条 id→中文短名，占位符过滤）。不动
     items.json。
   - `serve.py::_ocr_catalog` 短名并入索引与 name_to_ids 反查（mtime 缓存）。
   - 效果立竿见影：CF→Cold Fear 头套、LBCR→LBT-1961A 胸挂、OTV→Interceptor
     防弹衣、T30→Gruppa 99 背包、狗牌→狗牌包、臂带/绷带/夹板/止血剂/止痛药/
     洛芬/绒布/绳索/洗发水 全部**精确**命中；ComTac VI（新版物品 id 66b5f698）
     也进来了。
2. **HUD 碎片误配**：'un'→RUN 海报、'EC'→EMERCOM 钥匙、'S1'→SJ1 兴奋剂。
   修：token 层与整串层同规则——**无 CJK 且 <3 字符的碎片跳过**（中文碎片
   不过滤：'洛芬'→布洛芬 0.80 是正确路径）。
3. **token 数字守卫**：'mk17' 曾错配 'Mk47 双侧拉机柄'。修：token 含数字段时
   候选键须含至少一段（ANY 语义；O/0 误读 'GL0CK17' 仍可配 Glock 17）。
4. **试过又回退的**：整串模糊阈值 0.60→0.70 想杀 EXPIE 误配——实测正确乱串
   （'宿舍118房间钥起'→0.667、'上洛关9x18pm手柜'→0.696）与坏乱串（EXPIE 0.67）
   落在同一分数带，ratio 无法区分，0.70 连杀三条正确路径 → 回退 0.60，碎片
   守卫是主要防线，残余 2 条误报如实标注。

## 真值命中清单（节选，全部来自标注图核对）

A-2607 匕首、CF 面罩、LBCR 胸挂、EXFIL 盔罩、OTV 防弹衣、SpecterDR、
Mk 17 整枪（FN SCAR-H）+ 上机匣×3、GLOCK17、SR-3M、STANAG 弹匣×3、
M856A1 弹药包（OCR 还纠正了我对 M855A1 的误读）、M67、AFAK、AI-2×2、
Esmarch、狗牌包、臂带、军用绷带、固定夹板×2、CALOK-B 止血剂、安乃近、
布洛芬、UVSR 针叶林-1、Gruppa 99 T30、绒布布料、尼龙绳索、Schaman 洗发水、
45+ 模块化背包、NICE 承重系统、Mutkevich 玩偶、9x19 Pst / 9x39 SP-5。

**残余误报（2 条，如实）**：'EXPIE'（EXFIL 误读）→ 鹿弹包、'SDSK'（背包内
MSDK 布乱串）→ Shturman 钥匙——ratio 带内无法与正确乱串区分，待真实样本
积累后再调（如接入用户纠正记忆）。

## 改动清单

| 文件 | 内容 |
| --- | --- |
| `tools/build_ocr_names.py` | **新增**：短名表构建（一次性，运行期不联网） |
| `data/ocr-item-names.json` | **新增**：5480 条 id→中文短名 |
| `tools/serve.py` | `_ocr_shortnames` + `_ocr_catalog` 并入短名索引/反查 |
| `tools/ocr.py` | token/整串碎片守卫、token 数字段守卫（ANY） |
| `tests/test_r234_ocr.py` / `test_r236_ocr_tiling.py` | 全部保持通过（改向不放宽） |

## 验收

- 真实截图 HTTP 端到端：139 行 / **53 匹配** / 19.5s（3524×1738，72 块），
  标注图 `build/_ocr_game_annotated3.png`。
- OCR 用例回归：bundled 29+3skip、314 全 32。
- 全量 pytest：见 `AGENT_HANDOFF.md`（`build/_pytest_r237.xml`）。
