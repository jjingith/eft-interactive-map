# R19.5 交互验收（interaction-acceptance）

数据来源：`tools/r195_accept.py`（真实 Chrome + CDP 输入事件），`_accept.json`。

## 三枪 × 7 步流程（v1920 / v1264 双视口）

| 步骤 | AK-74 | M4A1 | MP5 |
|---|---|---|---|
| 加载默认装配 | ✅ 9 根卡+4 子卡，官方预设标签 | ✅ 6 根卡+12 子卡 | ✅ 3 根卡+6 子卡 |
| 点 3 个不同分区槽位 | muzzle(左链)16 候选→stock(右链)15→magazine(底带)13，焦点/候选即时切换 | （结构断言覆盖） | （结构断言覆盖） |
| 安装新配件 | ✅ 点候选行"6L18 45发弹匣"→焦点卡图标变化（iconChanged=true） | — | ✅ 20发弹匣 iconChanged=true |
| 右键卸载 | ✅ CDP 右键→人机 47.0→48.5 实时更新 | — | ✅ 72.0→73.0 |
| 有子槽的配件 | ✅ 子卡 4 张（gas_block/handguard、reciever/mount 等） | ✅ 12 子卡 | ✅ 6 子卡 |
| 恢复默认 | ✅ 标签回到"官方预设：AK-74…默认" | — | ✅ |
| 切枪无残留 | — | ✅ 无 AK gas_block 根卡残留 | ✅ 无 M4 残留 |

## 分区断言（浏览器实测 getBoundingClientRect）

- AK-74：mod_muzzle 左链（枪左侧）、mod_stock 右链、mod_magazine 底带、
  mod_gas_block 左链、mod_reciever 中带左——全部符合参考站物理关系。
- 连接线：AK-74 9 条 / M4A1 6 条 / MP5 3 条（=根卡数，elbow 折线连至枪盒边缘）。
- 空槽占位标签：AK-74 5 个 / M4A1 6 个 / MP5 2 个。
- 横向溢出：两视口均 false；控制台 0 错误；0 外部请求。

## 键盘与浮窗

卡片 focus 事件显示与 hover 相同的浮窗（R19.4 契约保留，pytest 断言 + 浮窗截图见 R19.4 轮）。
