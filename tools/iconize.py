#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""iconize.py — 把《逃离塔科夫》截图图标抠成统一 64x64 透明 PNG。

用法:
    python iconize.py            # 处理 JOBS 里的全部槽位, 写入 assets/icons
    python iconize.py --sheet    # 处理后再输出一张自检拼图 (_debug_sheet.png)

原理:
    1) 采样图像边框像素估计底色(底色渐变时取多个底色簇);
    2) 对底色做阈值分割 -> 前景掩膜; 长条图再按"最宽的空白列"切掉右侧文字;
    3) 连通域筛选: 只保留主体块(+与其包围盒重叠的碎块);
    4) 可选填洞(保留原像素色, 用于卡片/箱体这类实心物品);
    5) 前景色向透明区外扩(decontaminate, 避免缩放出现黑边/灰边);
    6) 裁到包围盒 -> 等比缩放 -> 居中贴到 64x64 透明画布。
"""
import os
import sys
import math
import argparse
from collections import Counter, deque

from PIL import Image, ImageDraw, ImageFilter

SRC = r"D:\personal\trae\02-塔科夫\ui图标"
DST = r"D:\personal\trae\02-塔科夫\eft-interactive-map\assets\icons"

CANVAS = 64          # 输出画布边长
DEF_FRAC = 0.86      # 内容占画布比例
DEF_FEATHER = 0.7    # alpha 羽化半径(px), 消除硬锯齿
DEF_BLEED = 3        # 前景色向外扩张的像素数

# (源文件, 输出文件, 模式, 参数)
#   strip = 图标+中文长条; item = 单物品截图; card = 彩色钥匙卡截图; dark = 深色物品(按暗度抠)
#   band  = [起, 止](0~1 纵向比例): 只取这一段落。图例图一张里有多行时, 用它按行切开。
JOBS = [
    ("QQ_1792318305559.png",                        "loot-safe.png",            "strip", {"T": 30, "fill": True}),
    ("753be7e1-c83f-40aa-b9ca-91b4a1bc7e24.png",    "loot-jacket.png",          "strip", {"T": 30}),
    ("221572ea-f601-4773-a301-fe59e402da3c.png",    "loot-pcblock.png",         "strip", {"T": 30}),
    ("ffda2530-33db-4227-9e43-bedd6a764d45.png",    "loot-scavbody.png",        "strip", {"T": 30}),
    ("2665da1a-d40b-4091-bdf2-ef835f750ca8.png",    "loot-drawer.png",          "strip", {"T": 30}),
    ("QQ_1792318336959.png",                        "loot-duffle.png",          "strip", {"T": 30}),
    ("彩蛋点.png",                                   "loot-cache.png",           "item",  {"T": 45, "fill": True, "frac": 0.88}),
    ("df5adb29-0461-4dab-894a-c874490efeb3.png",    "loot-med.png",             "strip", {"T": 30}),
    ("20838828-4731-4bc4-ab9e-456107ba4c86.png",    "loot-supply.png",          "strip", {"T": 30}),
    ("7fff1aac-0891-4b2f-b13d-cefb8c6017e8.png",    "loot-toolbox.png",         "strip", {"T": 30}),
    ("277c8e44-6598-4fa5-8a3d-8cadf1c6776a.png",    "loot-grenade.png",         "strip", {"T": 30}),
    ("武器箱.png",                                   "loot-weapon.png",          "item",  {"T": 25, "fill": True}),
    ("比特币.png",                                   "val-btc.png",              "item",  {"T": 55, "fill": True}),
    ("黄卡.png",                                     "val-keycard-yellow.png",   "card",  {"B": 165, "S": 90, "fill": True}),
    ("红卡.png",                                     "val-keycard-red.png",      "item",  {"T": 65, "fill": True}),
    ("绿卡.png",                                     "val-keycard-green.png",    "card",  {"B": 168, "S": 95, "fill": True}),
    ("蓝卡.png",                                     "val-keycard-blue.png",     "card",  {"B": 165, "S": 90, "fill": True}),
    ("紫卡.png",                                     "val-keycard-purple.png",   "card",  {"B": 165, "S": 90, "fill": True}),
    ("生活区卡.png",                                 "val-keycard-living.png",   "card",  {"B": 165, "S": 90, "fill": True}),
    ("ledx.png",                                     "val-ledx.png",             "dark",  {"vmax": 68, "fill": True}),
    # 2026-10-18 追加：私酒 / 除颤器 / 通用钥匙(生锈的带血钥匙) / 实验室黑卡 / Object 两张卡
    ("0efcb47e-ef69-46e9-adab-01295310a37c.png",    "val-bottle.png",           "item",  {"T": 60, "fill": True}),
    ("7174249c-390b-49f9-9b0c-10be0da08b36.png",    "val-defib.png",            "item",  {"T": 60, "fill": True}),
    ("0d4cc684-ca72-4f0d-bed6-9c61b160b365.png",    "val-key.png",              "strip", {"T": 30, "band": [0.548, 0.70]}),
    ("e510a141-b24e-444a-bff5-8161b1714327.png",    "val-keycard-black.png",    "strip", {"T": 30, "band": [0.00, 0.075]}),
    ("dc31b82e-b043-465f-bf61-62391db88f18.png",    "val-card-11sr.png",        "strip", {"T": 30, "band": [0.00, 0.40], "fill": True}),
    ("dc31b82e-b043-465f-bf61-62391db88f18.png",    "val-card-21ws.png",        "strip", {"T": 30, "band": [0.40, 0.88], "fill": True}),
    # 2026-10-19 第十五轮：显卡换成实拍截图（原「其他高价值」子类撤销，改为「情报」+「蓝色文件夹」两子类）
    #   val-folder.png = TerraGroup「蓝色文件夹」材料，改用本轮新截图的干净卡片渲染（替换旧 cb95b76e 那张）
    ("441cb534-42c9-4ea2-9278-cce72d4a28b6.png",    "val-gpu.png",              "item",  {"T": 30, "band": [0.18, 0.53], "fill": True}),
    ("f28c1aba-d1eb-416b-abad-2d0c7f384de8.png",    "val-intel.png",            "strip", {"T": 30}),
    ("c7e682a9-5122-4298-bfb0-f2ed5c83b73b.png",    "val-folder.png",           "strip", {"T": 30}),
    # 2026-10-18 第四批：上锁的门所需钥匙（含本轮新增的固定刷新钥匙）——wiki 截图逐行抠图
    #   源图里每行 = [图标][中文名][地图名]；band 按行切开，ring=0 让图标贴住 band 上下边界。
    ("449458ca-2663-44e8-a923-2913f669f7a8.png",      "key-64ce5723.png", "strip", {"T": 30, "ring": 0, "band": [0.2656, 0.3266]}),
    ("097abb32-473e-478f-b410-1ea2c25ac304.png",      "key-68cc0987.png", "strip", {"T": 30, "ring": 0, "band": [0.955, 0.9893]}),
    ("6b958ad1-aca1-4d9b-a522-284025747808.png",      "key-68c165f1.png", "strip", {"T": 30, "ring": 0, "band": [0.7187, 0.7434]}),
    ("6b958ad1-aca1-4d9b-a522-284025747808.png",      "key-63a39fc0.png", "strip", {"T": 30, "ring": 0, "band": [0.7692, 0.7917]}),
    ("6b958ad1-aca1-4d9b-a522-284025747808.png",      "key-64ccc1ec.png", "strip", {"T": 30, "ring": 0, "band": [0.0107, 0.0333]}),
    ("6b958ad1-aca1-4d9b-a522-284025747808.png",      "key-63a71e78.png", "strip", {"T": 30, "ring": 0, "band": [0.0612, 0.0843]}),
    ("6b958ad1-aca1-4d9b-a522-284025747808.png",      "key-63a39c79.png", "strip", {"T": 30, "ring": 0, "band": [0.1106, 0.1385]}),
    ("6b958ad1-aca1-4d9b-a522-284025747808.png",      "key-64ccc1d4.png", "strip", {"T": 30, "ring": 0, "band": [0.1621, 0.1852]}),
    ("097abb32-473e-478f-b410-1ea2c25ac304.png",      "key-5ad5db37.png", "strip", {"T": 30, "ring": 0, "band": [0.1342, 0.1658]}),
    ("6b958ad1-aca1-4d9b-a522-284025747808.png",      "key-68e95d71.png", "strip", {"T": 30, "ring": 0, "band": [0.8191, 0.847]}),
    ("097abb32-473e-478f-b410-1ea2c25ac304.png",      "key-664d3dd5.png", "strip", {"T": 30, "ring": 0, "band": [0.8919, 0.9228]}),
    ("097abb32-473e-478f-b410-1ea2c25ac304.png",      "key-5ad7242b.png", "strip", {"T": 30, "ring": 0, "band": [0.2611, 0.2926]}),
    ("097abb32-473e-478f-b410-1ea2c25ac304.png",      "key-5addaffe.png", "strip", {"T": 30, "ring": 0, "band": [0.3242, 0.3557]}),
    ("097abb32-473e-478f-b410-1ea2c25ac304.png",      "key-5ad5d7d2.png", "strip", {"T": 30, "ring": 0, "band": [0.3866, 0.4188]}),
    ("a8e78077-b0cb-4f8e-80e6-48c2ed413672.png",      "key-679b9716.png", "strip", {"T": 30, "ring": 0, "band": [0.2584, 0.7303]}),
    ("f601c1d1-01c8-4f68-b1f8-f0faee6b8ea5.png",      "key-664d3de8.png", "strip", {"T": 30, "ring": 0, "band": [0.747, 0.8152]}),
    ("f601c1d1-01c8-4f68-b1f8-f0faee6b8ea5.png",      "key-61aa5b51.png", "strip", {"T": 30, "ring": 0, "band": [0.0318, 0.1106]}),
    ("097abb32-473e-478f-b410-1ea2c25ac304.png",      "key-5ad5ccd1.png", "strip", {"T": 30, "ring": 0, "band": [0.5141, 0.5423]}),
    ("449458ca-2663-44e8-a923-2913f669f7a8.png",      "key-63a39e1d.png", "strip", {"T": 30, "ring": 0, "band": [0.7778, 0.8388]}),
    ("6b958ad1-aca1-4d9b-a522-284025747808.png",      "key-63a71eb5.png", "strip", {"T": 30, "ring": 0, "band": [0.2126, 0.2356]}),
    ("2fec001a-e451-451e-8c65-e15749ce5671.png",      "key-5d80c60f.png", "strip", {"T": 30, "ring": 0, "band": [0.7751, 0.8181]}),
    ("f170a1cf-b18a-47a8-951d-1c8e70020592.png",      "key-5d947d4e.png", "strip", {"T": 30, "ring": 0, "band": [0.3116, 0.3375]}),
    ("f170a1cf-b18a-47a8-951d-1c8e70020592.png",      "key-5d80c930.png", "strip", {"T": 30, "ring": 0, "band": [0.3623, 0.3865]}),
    ("f170a1cf-b18a-47a8-951d-1c8e70020592.png",      "key-5d80c959.png", "strip", {"T": 30, "ring": 0, "band": [0.4135, 0.4377]}),
    ("f170a1cf-b18a-47a8-951d-1c8e70020592.png",      "key-5d80cbd8.png", "strip", {"T": 30, "ring": 0, "band": [0.4642, 0.4884]}),
    ("f170a1cf-b18a-47a8-951d-1c8e70020592.png",      "key-5d80ca90.png", "strip", {"T": 30, "ring": 0, "band": [0.5148, 0.5391]}),
    ("f170a1cf-b18a-47a8-951d-1c8e70020592.png",      "key-5d80ccac.png", "strip", {"T": 30, "ring": 0, "band": [0.7186, 0.7429]}),
    ("f170a1cf-b18a-47a8-951d-1c8e70020592.png",      "key-5d80ccdd.png", "strip", {"T": 30, "ring": 0, "band": [0.7693, 0.7935]}),
    ("f170a1cf-b18a-47a8-951d-1c8e70020592.png",      "key-5d80cd1a.png", "strip", {"T": 30, "ring": 0, "band": [0.8199, 0.8442]}),
    ("2fec001a-e451-451e-8c65-e15749ce5671.png",      "key-5ede7a82.png", "strip", {"T": 30, "ring": 0, "band": [0.8593, 0.9023]}),
    ("2fec001a-e451-451e-8c65-e15749ce5671.png",      "key-68e9654d.png", "strip", {"T": 30, "ring": 0, "band": [0.6873, 0.7348]}),
    ("f170a1cf-b18a-47a8-951d-1c8e70020592.png",      "key-5d80cb38.png", "strip", {"T": 30, "ring": 0, "band": [0.9261, 0.9445]}),
    ("2fec001a-e451-451e-8c65-e15749ce5671.png",      "key-5d80cb56.png", "strip", {"T": 30, "ring": 0, "band": [0.0224, 0.0538]}),
    ("2fec001a-e451-451e-8c65-e15749ce5671.png",      "key-5ede7b0c.png", "strip", {"T": 30, "ring": 0, "band": [0.2679, 0.3082]}),
    ("2fec001a-e451-451e-8c65-e15749ce5671.png",      "key-5d947d38.png", "strip", {"T": 30, "ring": 0, "band": [0.4364, 0.4794]}),
    ("2fec001a-e451-451e-8c65-e15749ce5671.png",      "key-5d80c62a.png", "strip", {"T": 30, "ring": 0, "band": [0.9427, 0.9839]}),
    ("077581b8-fe8d-4ce5-9b36-d08ce22893c7.png",      "key-68e95f4f.png", "strip", {"T": 30, "ring": 0, "band": [0.6945, 0.726]}),
    ("adffc1ab-72ce-4485-9d65-575aa824f039.png",      "key-5a0eb38b.png", "strip", {"T": 30, "ring": 0, "band": [0.7175, 0.7606]}),
    ("d7402bd4-a3a4-4341-9c35-78eae0181c07.png",      "key-664d3db6.png", "strip", {"T": 30, "ring": 0, "band": [0.5378, 0.6223]}),
    ("379e6bc7-8332-4791-a307-52e5ae317a20.png",      "key-66acd670.png", "strip", {"T": 30, "ring": 0, "band": [0.7984, 0.9401]}),
    ("c1a7da85-b0c4-4b19-97d8-2604f40fbe53.png",      "key-5c1f79a0.png", "strip", {"T": 30, "ring": 0, "band": [0.0917, 0.1394]}),
    ("6b958ad1-aca1-4d9b-a522-284025747808.png",      "key-67ee7680.png", "strip", {"T": 30, "ring": 0, "band": [0.8717, 0.8943]}),
    ("6b958ad1-aca1-4d9b-a522-284025747808.png",      "key-64ccc206.png", "strip", {"T": 30, "ring": 0, "band": [0.263, 0.2872]}),
    ("c1a7da85-b0c4-4b19-97d8-2604f40fbe53.png",      "key-5c94bbff.png", "strip", {"T": 30, "ring": 0, "band": [0.9379, 0.9865]}),
    ("50b9284d-1a5a-4836-a283-63e32aecaca5.png",      "key-658199aa.png", "strip", {"T": 30, "ring": 0, "band": [0.6939, 0.8469]}),
    ("097abb32-473e-478f-b410-1ea2c25ac304.png",      "key-5e42c715.png", "strip", {"T": 30, "ring": 0, "band": [0.702, 0.7376]}),
    ("077581b8-fe8d-4ce5-9b36-d08ce22893c7.png",      "key-5da743f5.png", "strip", {"T": 30, "ring": 0, "band": [0.5902, 0.6167]}),
    ("f601c1d1-01c8-4f68-b1f8-f0faee6b8ea5.png",      "key-66265d7b.png", "strip", {"T": 30, "ring": 0, "band": [0.4621, 0.5303]}),
    ("f601c1d1-01c8-4f68-b1f8-f0faee6b8ea5.png",      "key-61aa5b7d.png", "strip", {"T": 30, "ring": 0, "band": [0.3212, 0.3924]}),
    ("f601c1d1-01c8-4f68-b1f8-f0faee6b8ea5.png",      "key-61aa5ba8.png", "strip", {"T": 30, "ring": 0, "band": [0.1773, 0.2485]}),
    ("50b9284d-1a5a-4836-a283-63e32aecaca5.png",      "key-65819980.png", "strip", {"T": 30, "ring": 0, "band": [0.3707, 0.5238]}),
    ("adffc1ab-72ce-4485-9d65-575aa824f039.png",      "key-664d3ddf.png", "strip", {"T": 30, "ring": 0, "band": [0.8741, 0.9138]}),
    ("6b958ad1-aca1-4d9b-a522-284025747808.png",      "key-64ccc246.png", "strip", {"T": 30, "ring": 0, "band": [0.3639, 0.3897]}),
    ("d7402bd4-a3a4-4341-9c35-78eae0181c07.png",      "key-591afe01.png", "strip", {"T": 30, "ring": 0, "band": [0.1978, 0.2788]}),
    ("077581b8-fe8d-4ce5-9b36-d08ce22893c7.png",      "key-6aa2f656.png", "strip", {"T": 30, "ring": 0, "band": [0.6426, 0.6719]}),
    ("6b958ad1-aca1-4d9b-a522-284025747808.png",      "key-63a39dfe.png", "strip", {"T": 30, "ring": 0, "band": [0.4149, 0.438]}),
    ("6b958ad1-aca1-4d9b-a522-284025747808.png",      "key-63a39df1.png", "strip", {"T": 30, "ring": 0, "band": [0.4654, 0.4885]}),
    ("6b958ad1-aca1-4d9b-a522-284025747808.png",      "key-68e960db.png", "strip", {"T": 30, "ring": 0, "band": [0.9179, 0.9474]}),
    ("449458ca-2663-44e8-a923-2913f669f7a8.png",      "key-6582dbf0.png", "strip", {"T": 30, "ring": 0, "band": [0.1382, 0.1992]}),
    ("b1eaf462-bec9-4cd0-b3bc-4a68fff37ad7.png",      "key-62987cb9.png", "strip", {"T": 30, "ring": 0, "band": [0.192, 0.2376]}),
    ("6b958ad1-aca1-4d9b-a522-284025747808.png",      "key-68e63b56.png", "strip", {"T": 30, "ring": 0, "band": [0.5668, 0.5926]}),
    ("077581b8-fe8d-4ce5-9b36-d08ce22893c7.png",      "key-6761a6f9.png", "strip", {"T": 30, "ring": 0, "band": [0.7503, 0.774]}),
    ("077581b8-fe8d-4ce5-9b36-d08ce22893c7.png",      "key-664d4b01.png", "strip", {"T": 30, "ring": 0, "band": [0.9092, 0.9357]}),
    ("17be163f-01b9-43f5-83b6-ed42857930b4.png",      "key-59139158.png", "strip", {"T": 30, "ring": 0, "band": [0.4113, 0.4449]}),
    ("6c115b6a-d7b5-4268-9c89-ba660c035001.png",      "key-5a0eb6ac.png", "strip", {"T": 30, "ring": 0, "band": [0.0726, 0.1042]}),
    ("17be163f-01b9-43f5-83b6-ed42857930b4.png",      "key-5913877a.png", "strip", {"T": 30, "ring": 0, "band": [0.2089, 0.2411]}),
    ("097abb32-473e-478f-b410-1ea2c25ac304.png",      "key-5ad5d498.png", "strip", {"T": 30, "ring": 0, "band": [0.0081, 0.0369]}),
    ("f601c1d1-01c8-4f68-b1f8-f0faee6b8ea5.png",      "key-62987dfc.png", "strip", {"T": 30, "ring": 0, "band": [0.6045, 0.6742]}),
    ("b1eaf462-bec9-4cd0-b3bc-4a68fff37ad7.png",      "key-61a64492.png", "strip", {"T": 30, "ring": 0, "band": [0.4656, 0.5112]}),
    ("b1eaf462-bec9-4cd0-b3bc-4a68fff37ad7.png",      "key-61aa81fc.png", "strip", {"T": 30, "ring": 0, "band": [0.5567, 0.6023]}),
    ("b1eaf462-bec9-4cd0-b3bc-4a68fff37ad7.png",      "key-62a9cb93.png", "strip", {"T": 30, "ring": 0, "band": [0.6479, 0.6935]}),
    ("50b9284d-1a5a-4836-a283-63e32aecaca5.png",      "key-65819997.png", "strip", {"T": 30, "ring": 0, "band": [0.051, 0.2041]}),
    ("449458ca-2663-44e8-a923-2913f669f7a8.png",      "key-6398fd8a.png", "strip", {"T": 30, "ring": 0, "band": [0.3943, 0.458]}),
    ("17be163f-01b9-43f5-83b6-ed42857930b4.png",      "key-59389945.png", "strip", {"T": 30, "ring": 0, "band": [0.4785, 0.5122]}),
    ("17be163f-01b9-43f5-83b6-ed42857930b4.png",      "key-591383f1.png", "strip", {"T": 30, "ring": 0, "band": [0.5451, 0.578]}),
    ("17be163f-01b9-43f5-83b6-ed42857930b4.png",      "key-591382d9.png", "strip", {"T": 30, "ring": 0, "band": [0.6123, 0.6452]}),
    ("17be163f-01b9-43f5-83b6-ed42857930b4.png",      "key-59145780.png", "strip", {"T": 30, "ring": 0, "band": [0.681, 0.7146]}),
    ("17be163f-01b9-43f5-83b6-ed42857930b4.png",      "key-59136e1e.png", "strip", {"T": 30, "ring": 0, "band": [0.7468, 0.7797]}),
    ("17be163f-01b9-43f5-83b6-ed42857930b4.png",      "key-59387a49.png", "strip", {"T": 30, "ring": 0, "band": [0.814, 0.8469]}),
    ("17be163f-01b9-43f5-83b6-ed42857930b4.png",      "key-5672c92d.png", "strip", {"T": 30, "ring": 0, "band": [0.8834, 0.917]}),
    ("17be163f-01b9-43f5-83b6-ed42857930b4.png",      "key-59385041.png", "strip", {"T": 30, "ring": 0, "band": [0.9506, 0.9843]}),
    ("077581b8-fe8d-4ce5-9b36-d08ce22893c7.png",      "key-59148c8a.png", "strip", {"T": 30, "ring": 0, "band": [0.0068, 0.0333]}),
    ("077581b8-fe8d-4ce5-9b36-d08ce22893c7.png",      "key-5938603e.png", "strip", {"T": 30, "ring": 0, "band": [0.0592, 0.0846]}),
    ("077581b8-fe8d-4ce5-9b36-d08ce22893c7.png",      "key-5780cf94.png", "strip", {"T": 30, "ring": 0, "band": [0.1127, 0.1392]}),
    ("077581b8-fe8d-4ce5-9b36-d08ce22893c7.png",      "key-5780cf9e.png", "strip", {"T": 30, "ring": 0, "band": [0.1663, 0.1928]}),
    ("077581b8-fe8d-4ce5-9b36-d08ce22893c7.png",      "key-5780cfa5.png", "strip", {"T": 30, "ring": 0, "band": [0.2193, 0.2458]}),
    ("077581b8-fe8d-4ce5-9b36-d08ce22893c7.png",      "key-593aa4be.png", "strip", {"T": 30, "ring": 0, "band": [0.2723, 0.2988]}),
    ("077581b8-fe8d-4ce5-9b36-d08ce22893c7.png",      "key-5780cda0.png", "strip", {"T": 30, "ring": 0, "band": [0.3253, 0.3517]}),
    ("077581b8-fe8d-4ce5-9b36-d08ce22893c7.png",      "key-5780cf72.png", "strip", {"T": 30, "ring": 0, "band": [0.3782, 0.4047]}),
    ("077581b8-fe8d-4ce5-9b36-d08ce22893c7.png",      "key-5780cf69.png", "strip", {"T": 30, "ring": 0, "band": [0.4312, 0.4577]}),
    ("077581b8-fe8d-4ce5-9b36-d08ce22893c7.png",      "key-5780cf7f.png", "strip", {"T": 30, "ring": 0, "band": [0.8038, 0.8292]}),
    ("077581b8-fe8d-4ce5-9b36-d08ce22893c7.png",      "key-59136a44.png", "strip", {"T": 30, "ring": 0, "band": [0.4842, 0.5096]}),
    ("b1eaf462-bec9-4cd0-b3bc-4a68fff37ad7.png",      "key-61a6444b.png", "strip", {"T": 30, "ring": 0, "band": [0.7401, 0.7856]}),
    ("379e6bc7-8332-4791-a307-52e5ae317a20.png",      "key-5448ba0b.png", "strip", {"T": 30, "ring": 0, "band": [0.5477, 0.6757]}),
    ("6b958ad1-aca1-4d9b-a522-284025747808.png",      "key-63a3a93f.png", "strip", {"T": 30, "ring": 0, "band": [0.9705, 0.9952]}),
    ("b1eaf462-bec9-4cd0-b3bc-4a68fff37ad7.png",      "key-62987da9.png", "strip", {"T": 30, "ring": 0, "band": [0.8312, 0.8768]}),
    ("077581b8-fe8d-4ce5-9b36-d08ce22893c7.png",      "key-5913611c.png", "strip", {"T": 30, "ring": 0, "band": [0.5383, 0.5643]}),
    ("d7402bd4-a3a4-4341-9c35-78eae0181c07.png",      "key-6761a6cc.png", "strip", {"T": 30, "ring": 0, "band": [0.3813, 0.4442]}),
    ("077581b8-fe8d-4ce5-9b36-d08ce22893c7.png",      "key-593962ca.png", "strip", {"T": 30, "ring": 0, "band": [0.9622, 0.9876]}),
    ("077581b8-fe8d-4ce5-9b36-d08ce22893c7.png",      "key-5937ee64.png", "strip", {"T": 30, "ring": 0, "band": [0.8568, 0.8844]}),
    ("17be163f-01b9-43f5-83b6-ed42857930b4.png",      "key-6aa2f730.png", "strip", {"T": 30, "ring": 0, "band": [0.2747, 0.3126]}),
    ("adffc1ab-72ce-4485-9d65-575aa824f039.png",      "key-5d8e15b6.png", "strip", {"T": 30, "ring": 0, "band": [0.5617, 0.6015]}),
    ("b1eaf462-bec9-4cd0-b3bc-4a68fff37ad7.png",      "key-62987e26.png", "strip", {"T": 30, "ring": 0, "band": [0.9224, 0.968]}),
    ("17be163f-01b9-43f5-83b6-ed42857930b4.png",      "key-5780d053.png", "strip", {"T": 30, "ring": 0, "band": [0.073, 0.1059]}),
    ("b1eaf462-bec9-4cd0-b3bc-4a68fff37ad7.png",      "key-61a64428.png", "strip", {"T": 30, "ring": 0, "band": [0.0087, 0.0543]}),
    ("f601c1d1-01c8-4f68-b1f8-f0faee6b8ea5.png",      "key-6a8d581f.png", "strip", {"T": 30, "ring": 0, "band": [0.8864, 0.9667]}),
    ("b1eaf462-bec9-4cd0-b3bc-4a68fff37ad7.png",      "key-61aa5aed.png", "strip", {"T": 30, "ring": 0, "band": [0.1009, 0.1484]}),
    ("449458ca-2663-44e8-a923-2913f669f7a8.png",      "key-64d4b23d.png", "strip", {"T": 30, "ring": 0, "band": [0.6491, 0.7141]}),
    ("6c115b6a-d7b5-4268-9c89-ba660c035001.png",      "key-5a0ea647.png", "strip", {"T": 30, "ring": 0, "band": [0.2628, 0.293]}),
    ("6c115b6a-d7b5-4268-9c89-ba660c035001.png",      "key-5a144bdb.png", "strip", {"T": 30, "ring": 0, "band": [0.3878, 0.4187]}),
    ("6c115b6a-d7b5-4268-9c89-ba660c035001.png",      "key-5a0ee4b5.png", "strip", {"T": 30, "ring": 0, "band": [0.4509, 0.4819]}),
    ("6c115b6a-d7b5-4268-9c89-ba660c035001.png",      "key-5a13f241.png", "strip", {"T": 30, "ring": 0, "band": [0.7043, 0.7352]}),
    ("6c115b6a-d7b5-4268-9c89-ba660c035001.png",      "key-5a13f352.png", "strip", {"T": 30, "ring": 0, "band": [0.7675, 0.7984]}),
    ("6c115b6a-d7b5-4268-9c89-ba660c035001.png",      "key-5a145d47.png", "strip", {"T": 30, "ring": 0, "band": [0.8313, 0.8622]}),
    ("6c115b6a-d7b5-4268-9c89-ba660c035001.png",      "key-5a145d7b.png", "strip", {"T": 30, "ring": 0, "band": [0.8945, 0.9254]}),
    ("6c115b6a-d7b5-4268-9c89-ba660c035001.png",      "key-5a0eec96.png", "strip", {"T": 30, "ring": 0, "band": [0.9577, 0.9886]}),
    ("8bfa3a51-cfba-472e-a030-2c359960a6bc.png",      "key-5a0eecf6.png", "strip", {"T": 30, "ring": 0, "band": [0.007, 0.0318]}),
    ("8bfa3a51-cfba-472e-a030-2c359960a6bc.png",      "key-5a0eed43.png", "strip", {"T": 30, "ring": 0, "band": [0.0577, 0.0825]}),
    ("8bfa3a51-cfba-472e-a030-2c359960a6bc.png",      "key-5a145ebb.png", "strip", {"T": 30, "ring": 0, "band": [0.1089, 0.1337]}),
    ("8bfa3a51-cfba-472e-a030-2c359960a6bc.png",      "key-5a0eee14.png", "strip", {"T": 30, "ring": 0, "band": [0.2102, 0.235]}),
    ("adffc1ab-72ce-4485-9d65-575aa824f039.png",      "key-5a0ea79b.png", "strip", {"T": 30, "ring": 0, "band": [0.3289, 0.3662]}),
    ("8bfa3a51-cfba-472e-a030-2c359960a6bc.png",      "key-5a0dc455.png", "strip", {"T": 30, "ring": 0, "band": [0.3127, 0.3369]}),
    ("8bfa3a51-cfba-472e-a030-2c359960a6bc.png",      "key-5a0dc95c.png", "strip", {"T": 30, "ring": 0, "band": [0.3633, 0.3876]}),
    ("8bfa3a51-cfba-472e-a030-2c359960a6bc.png",      "key-5a144dfd.png", "strip", {"T": 30, "ring": 0, "band": [0.4135, 0.4383]}),
    ("8bfa3a51-cfba-472e-a030-2c359960a6bc.png",      "key-5a0ec6d2.png", "strip", {"T": 30, "ring": 0, "band": [0.4642, 0.4889]}),
    ("8bfa3a51-cfba-472e-a030-2c359960a6bc.png",      "key-5a0ee307.png", "strip", {"T": 30, "ring": 0, "band": [0.5655, 0.5903]}),
    ("8bfa3a51-cfba-472e-a030-2c359960a6bc.png",      "key-5a13eebd.png", "strip", {"T": 30, "ring": 0, "band": [0.6162, 0.641]}),
    ("8bfa3a51-cfba-472e-a030-2c359960a6bc.png",      "key-5a13ef06.png", "strip", {"T": 30, "ring": 0, "band": [0.6674, 0.6922]}),
    ("8bfa3a51-cfba-472e-a030-2c359960a6bc.png",      "key-5a0ee345.png", "strip", {"T": 30, "ring": 0, "band": [0.7181, 0.7429]}),
    ("8bfa3a51-cfba-472e-a030-2c359960a6bc.png",      "key-5a0ee37f.png", "strip", {"T": 30, "ring": 0, "band": [0.7687, 0.7935]}),
    ("8bfa3a51-cfba-472e-a030-2c359960a6bc.png",      "key-5a1452ee.png", "strip", {"T": 30, "ring": 0, "band": [0.8194, 0.8442]}),
    ("8bfa3a51-cfba-472e-a030-2c359960a6bc.png",      "key-5a13ef7e.png", "strip", {"T": 30, "ring": 0, "band": [0.8701, 0.8949]}),
    ("8bfa3a51-cfba-472e-a030-2c359960a6bc.png",      "key-5a13f463.png", "strip", {"T": 30, "ring": 0, "band": [0.972, 0.9968]}),
    ("df5e4310-cdd9-4c6a-9ea4-d40711e7cd6d.png",      "key-6866adbe.png", "strip", {"T": 30, "ring": 0, "band": [0.5503, 0.6614]}),
    ("449458ca-2663-44e8-a923-2913f669f7a8.png",      "key-64ccc25f.png", "strip", {"T": 30, "ring": 0, "band": [0.0122, 0.0732]}),
    ("adffc1ab-72ce-4485-9d65-575aa824f039.png",      "key-5eff09cd.png", "strip", {"T": 30, "ring": 0, "band": [0.6404, 0.6785]}),
    ("097abb32-473e-478f-b410-1ea2c25ac304.png",      "key-5ad5d644.png", "strip", {"T": 30, "ring": 0, "band": [0.0711, 0.1]}),
    ("6b958ad1-aca1-4d9b-a522-284025747808.png",      "key-63a39fdf.png", "strip", {"T": 30, "ring": 0, "band": [0.6173, 0.6425]}),
    ("449458ca-2663-44e8-a923-2913f669f7a8.png",      "key-63a397d3.png", "strip", {"T": 30, "ring": 0, "band": [0.5203, 0.584]}),
    ("6b958ad1-aca1-4d9b-a522-284025747808.png",      "key-63a39919.png", "strip", {"T": 30, "ring": 0, "band": [0.5158, 0.54]}),
    ("6b958ad1-aca1-4d9b-a522-284025747808.png",      "key-68e96180.png", "strip", {"T": 30, "ring": 0, "band": [0.6672, 0.6914]}),
    ("17be163f-01b9-43f5-83b6-ed42857930b4.png",      "key-5780d065.png", "strip", {"T": 30, "ring": 0, "band": [0.0064, 0.0386]}),
    ("17be163f-01b9-43f5-83b6-ed42857930b4.png",      "key-5780d07a.png", "strip", {"T": 30, "ring": 0, "band": [0.1423, 0.176]}),
    ("b1eaf462-bec9-4cd0-b3bc-4a68fff37ad7.png",      "key-62987c65.png", "strip", {"T": 30, "ring": 0, "band": [0.2832, 0.3288]}),
    ("df5e4310-cdd9-4c6a-9ea4-d40711e7cd6d.png",      "key-6866ad38.png", "strip", {"T": 30, "ring": 0, "band": [0.2884, 0.4206]}),
    # 2026-10-18 第五批：补齐仍缺图的门钥匙 + 只在高级资源点出现的 3 把钥匙（wiki 截图逐行抠图）
    ("QQ_1792331022791.png",      "key-5d80c787.png", "strip", {"T": 30, "ring": 0, "band": [0.0450, 0.1033]}),  # RB-AK钥匙
    ("QQ_1792331022791.png",      "key-5d80c88d.png", "strip", {"T": 30, "ring": 0, "band": [0.1695, 0.2278]}),  # RB-AM钥匙
    ("QQ_1792331022791.png",      "key-5d80c66d.png", "strip", {"T": 30, "ring": 0, "band": [0.2874, 0.3603]}),  # RB-AO钥匙
    ("QQ_1792331022791.png",      "key-5d8e3ecc.png", "strip", {"T": 30, "ring": 0, "band": [0.4185, 0.4768]}),  # RB-GN钥匙
    ("QQ_1792331022791.png",      "key-5d8e0db5.png", "strip", {"T": 30, "ring": 0, "band": [0.5497, 0.6026]}),  # RB-KORL钥匙
    ("QQ_1792331022791.png",      "key-5d8e0e0e.png", "strip", {"T": 30, "ring": 0, "band": [0.6742, 0.7272]}),  # RB-KPRL钥匙
    ("QQ_1792331030601.png",      "key-5d80cab0.png", "strip", {"T": 30, "ring": 0, "band": [0.4209, 0.4746]}),  # RB-MP22钥匙
    ("QQ_1792331030601.png",      "key-5d80c6c5.png", "strip", {"T": 30, "ring": 0, "band": [0.5502, 0.6039]}),  # RB-OB钥匙
    ("QQ_1792331030601.png",      "key-5d80c8f5.png", "strip", {"T": 30, "ring": 0, "band": [0.6795, 0.7331]}),  # RB-OP钥匙
    ("QQ_1792331042163.png",      "key-5d95d6fa.png", "strip", {"T": 30, "ring": 0, "band": [0.4104, 0.4624]}),  # RB-PSP2钥匙
    ("QQ_1792331042163.png",      "key-5d95d6be.png", "strip", {"T": 30, "ring": 0, "band": [0.6676, 0.7209]}),  # RB-PSV2钥匙
    ("QQ_1792331042163.png",      "key-5da5cdcd.png", "strip", {"T": 30, "ring": 0, "band": [0.7811, 0.8577]}),  # RB-RH钥匙
    ("QQ_1792331050798.png",      "key-5da46e38.png", "strip", {"T": 30, "ring": 0, "band": [0.0396, 0.0929]}),  # RB-RS钥匙
    ("QQ_1792331050798.png",      "key-5d9f1fa6.png", "strip", {"T": 30, "ring": 0, "band": [0.2828, 0.3579]}),  # RB-ST钥匙
    ("QQ_1792331050798.png",      "key-5d80c6fc.png", "strip", {"T": 30, "ring": 0, "band": [0.4262, 0.4795]}),  # RB-TB钥匙
    ("QQ_1792331121651.png",      "key-59136519.png", "strip", {"T": 30, "ring": 0, "band": [0.1807, 0.2404]}),  # VAZ 车钥匙
    ("bbc3c44e-0e3f-4270-b7f9-5ace103865d3.png", "key-59136f6f.png", "strip", {"T": 30, "ring": 0, "band": [0.6119, 0.6728]}),  # 折叠车钥匙
    ("bbc3c44e-0e3f-4270-b7f9-5ace103865d3.png", "key-658199a0.png", "strip", {"T": 30, "ring": 0, "band": [0.7549, 0.8113]}),  # Horse饭店厕所钥匙
    ("QQ_1792331657129.png",      "key-63a39f08.png", "strip", {"T": 30, "ring": 0, "band": [0.1676, 0.2234]}),  # 酒店215房间钥匙
    ("QQ_1792331657129.png",      "key-63a39fd1.png", "strip", {"T": 30, "ring": 0, "band": [0.2956, 0.3515]}),  # 楼梯间钥匙
    ("QQ_1792331657129.png",      "key-6582dc4b.png", "strip", {"T": 30, "ring": 0, "band": [0.4251, 0.4796]}),  # 内务部学院门厅警卫室钥匙
    ("QQ_1792331657129.png",      "key-63a39c69.png", "strip", {"T": 30, "ring": 0, "band": [0.5531, 0.6076]}),  # 商店经理钥匙
    ("QQ_1792331657129.png",      "key-64ccc211.png", "strip", {"T": 30, "ring": 0, "band": [0.6826, 0.7357]}),  # 塔科夫银行现金区钥匙
    ("QQ_1792331657129.png",      "key-64ccc268.png", "strip", {"T": 30, "ring": 0, "band": [0.8093, 0.8638]}),  # 体育教师办公室钥匙
    ("QQ_1792331657129.png",      "key-63a39f6e.png", "strip", {"T": 30, "ring": 0, "band": [0.9387, 0.9932]}),  # 铁门钥匙
    ("QQ_1792331697135.png",      "key-64ccc1f4.png", "strip", {"T": 30, "ring": 0, "band": [0.0280, 0.0828]}),  # Concordia 63号公寓钥匙
    ("QQ_1792331697135.png",      "key-63a71e86.png", "strip", {"T": 30, "ring": 0, "band": [0.1549, 0.2083]}),  # Concordia 64号公寓办公室钥匙
    ("QQ_1792331697135.png",      "key-63a71e92.png", "strip", {"T": 30, "ring": 0, "band": [0.2804, 0.3338]}),  # Concordia 64号公寓钥匙
    ("QQ_1792331705395.png",      "key-64ccc24d.png", "strip", {"T": 30, "ring": 0, "band": [0.1890, 0.2515]}),  # TerraGroup军械库钥匙
    ("QQ_1792331716300.png",      "key-64ce5723.png", "strip", {"T": 30, "ring": 0, "band": [0.2702, 0.3333]}),  # "Aspect"公司办公区钥匙
    ("b7e0293d-c68b-408c-9d10-6df57b740e41.png", "key-64ccc1fe.png", "strip", {"T": 30, "ring": 0, "band": [0.0251, 0.0895]}),  # “白鲸”餐厅经理办公室钥匙
    ("b7e0293d-c68b-408c-9d10-6df57b740e41.png", "key-6582dbe4.png", "strip", {"T": 30, "ring": 0, "band": [0.1758, 0.2370]}),  # "调解室"钥匙
    ("b7e0293d-c68b-408c-9d10-6df57b740e41.png", "key-6582dc57.png", "strip", {"T": 30, "ring": 0, "band": [0.3218, 0.3846]}),  # 不动产管理处办公室钥匙
    ("b7e0293d-c68b-408c-9d10-6df57b740e41.png", "key-63a39e49.png", "strip", {"T": 30, "ring": 0, "band": [0.4710, 0.5322]}),  # 档案室钥匙
    ("b7e0293d-c68b-408c-9d10-6df57b740e41.png", "key-63a39ce4.png", "strip", {"T": 30, "ring": 0, "band": [0.6170, 0.6813]}),  # 供应部门主管办公室钥匙
    ("b7e0293d-c68b-408c-9d10-6df57b740e41.png", "key-63a39cb1.png", "strip", {"T": 30, "ring": 0, "band": [0.7661, 0.8289]}),  # 建筑工地工棚钥匙
    ("b7e0293d-c68b-408c-9d10-6df57b740e41.png", "key-63a71ed2.png", "strip", {"T": 30, "ring": 0, "band": [0.9137, 0.9765]}),  # 金融办公室小房间钥匙
    ("ee90937d-a6ab-41dd-a93d-fc33fb95bba5.png", "key-5ad5d205.png", "strip", {"T": 30, "ring": 0, "band": [0.0617, 0.1662]}),  # OLI超市杂物间钥匙
    ("ee90937d-a6ab-41dd-a93d-fc33fb95bba5.png", "key-5ad72171.png", "strip", {"T": 30, "ring": 0, "band": [0.5657, 0.6756]}),  # OLI收银机钥匙
    ("ee90937d-a6ab-41dd-a93d-fc33fb95bba5.png", "key-5ad5cfbd.png", "strip", {"T": 30, "ring": 0, "band": [0.8177, 0.9249]}),  # OLI物流部钥匙
    ("169a98a4-5040-4f3e-8e47-1b828e8d592d.png", "key-63a39667.png", "strip", {"T": 30, "ring": 0, "band": [0.6149, 0.8621]}),  # 金融办公室钥匙
    ("9105834d-41a1-42e6-bc96-0385977af181.png", "key-5c1e2a1e.png", "strip", {"T": 30, "ring": 0, "band": [0.0769, 0.2346]}),  # TerraGroup 实验室经理办公室钥匙
    ("9105834d-41a1-42e6-bc96-0385977af181.png", "key-5c1e2d1f.png", "strip", {"T": 30, "ring": 0, "band": [0.8038, 0.9577]}),  # TerraGroup 实验室武器测试区域钥匙
    ("55ea5a01-0495-45bf-98c5-69cc964a8d50.png", "key-6939948d.png", "strip", {"T": 30, "ring": 0, "band": [0.2432, 0.8108]}),  # 旧屋厕所钥匙
    ("f74a2149-b1e6-450d-957c-6fb02613141c.png", "key-59381445.png", "strip", {"T": 30, "ring": 0, "band": [0.2584, 0.7640]}),  # 简易工棚钥匙
    ("9d1afb4f-d637-40b4-ab4a-8204cc8e0a8b.png", "key-61a6446f.png", "strip", {"T": 30, "ring": 0, "band": [0.3158, 0.8553]}),  # 冷库钥匙
]


# ----------------------------------------------------------------------------- 工具
def sat(p):
    mx, mn = max(p), min(p)
    return 0 if mx == 0 else (mx - mn) * 255 // mx


def brightness(p):
    return (p[0] + p[1] + p[2]) // 3


def border_colors(im, ring=1, topn=4):
    """取边框像素中最主要的若干种颜色作为底色样本。"""
    px = im.load()
    w, h = im.size
    cols = []
    for y in list(range(ring)) + list(range(h - ring, h)):
        cols += [px[x, y] for x in range(w)]
    for x in list(range(ring)) + list(range(w - ring, w)):
        cols += [px[x, y] for y in range(h)]
    c = Counter(cols)
    # 先按 12 为步长聚簇, 再取簇内均值
    cl = Counter()
    acc = {}
    for col, n in c.items():
        k = (col[0] // 12, col[1] // 12, col[2] // 12)
        cl[k] += n
        a = acc.setdefault(k, [0, 0, 0, 0])
        a[0] += col[0] * n
        a[1] += col[1] * n
        a[2] += col[2] * n
        a[3] += n
    return [(acc[k][0] / acc[k][3], acc[k][1] / acc[k][3], acc[k][2] / acc[k][3])
            for k, _ in cl.most_common(topn)]


def label(mask, w, h, ya=0, yb=None):
    """8-邻域连通域标记, 返回 [ [(x,y), ...], ... ]。

    ya/yb 可限定只扫描这一段行(长条图例按 band 切开后, 其余行全是空 mask,
    跳过它们能把耗时从「整图」降到「一行」)。
    """
    yb = h if yb is None else yb
    seen = set()
    comps = []
    for y0 in range(ya, yb):
        for x0 in range(w):
            if mask[y0][x0] and (x0, y0) not in seen:
                seen.add((x0, y0))
                stack = [(x0, y0)]
                pix = []
                while stack:
                    x, y = stack.pop()
                    pix.append((x, y))
                    for dy in (-1, 0, 1):
                        for dx in (-1, 0, 1):
                            nx, ny = x + dx, y + dy
                            if 0 <= nx < w and 0 <= ny < h and mask[ny][nx] and (nx, ny) not in seen:
                                seen.add((nx, ny))
                                stack.append((nx, ny))
                comps.append(pix)
    return comps


def bbox(pix):
    xs = [p[0] for p in pix]
    ys = [p[1] for p in pix]
    return min(xs), min(ys), max(xs), max(ys)


def select_main(mask, w, h, px, mode, min_area=3, pad=2):
    """保留主体连通域 + 与其包围盒重叠的碎块, 返回新的 mask 与包围盒。

    card 模式: 钥匙卡本体是"白卡面+彩色条", 用">=190 的亮像素数"当种子
    (背景的彩色虚化/亮斑饱和但不够亮, 会被排除)。
    """
    comps = [c for c in label(mask, w, h) if len(c) >= min_area]
    if not comps:
        return None, None
    if mode == "card":
        def score(c):
            return (sum(1 for (x, y) in c if brightness(px[x, y]) >= 190),
                    sum(1 for (x, y) in c if sat(px[x, y]) > 90),
                    len(c))
        main = max(comps, key=score)
    else:
        main = max(comps, key=len)
    b = bbox(main)
    keep = set(main)
    for c in comps:
        if c is main:
            continue
        cb = bbox(c)
        if cb[0] <= b[2] + pad and cb[2] >= b[0] - pad and cb[1] <= b[3] + pad and cb[3] >= b[1] - pad:
            keep.update(c)
    newmask = [[False] * w for _ in range(h)]
    xs, ys = [], []
    for (x, y) in keep:
        newmask[y][x] = True
        xs.append(x)
        ys.append(y)
    return newmask, (min(xs), min(ys), max(xs), max(ys))


def fill_holes(mask, w, h):
    """把不与画布边缘相连的空洞补上(保留原始像素色, 只改 alpha)。"""
    outside = [[False] * w for _ in range(h)]
    q = deque()
    for x in range(w):
        for y in (0, h - 1):
            if not mask[y][x] and not outside[y][x]:
                outside[y][x] = True
                q.append((x, y))
    for y in range(h):
        for x in (0, w - 1):
            if not mask[y][x] and not outside[y][x]:
                outside[y][x] = True
                q.append((x, y))
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and not mask[ny][nx] and not outside[ny][nx]:
                outside[ny][nx] = True
                q.append((nx, ny))
    return [[mask[y][x] or not outside[y][x] for x in range(w)] for y in range(h)]


def build_mask(im, mode, p, ya=0, yb=None):
    px = im.load()
    w, h = im.size
    yb = h if yb is None else yb
    if mode == "dark":
        vmax = p["vmax"]
        return [[brightness(px[x, y]) < vmax if ya <= y < yb else False
                 for x in range(w)] for y in range(h)]
    if mode == "card":
        B, S = p["B"], p["S"]
        return [[(brightness(px[x, y]) > B or sat(px[x, y]) > S) if ya <= y < yb else False
                 for x in range(w)] for y in range(h)]
    bgs = border_colors(im, ring=1, topn=p.get("nbg", 4))
    T = p["T"]
    out = [[False] * w for _ in range(h)]
    for y in range(ya, yb):
        row = out[y]
        for x in range(w):
            c = px[x, y]
            best = math.dist(c, bgs[0])
            for bg in bgs[1:]:
                d = math.dist(c, bg)
                if d < best:
                    best = d
            row[x] = best > T
    return out


def keep_left_icon(mask, w, h, cl_gap=3, absorb=6, min_w=7, min_area=12, ya=0, yb=None):
    """长条图: 把前景连通域按 x 相邻聚簇, 取最左侧宽度足够的那簇(图标), 丢弃右侧文字。

    顺带吸收紧跟其后的碎块(容忍图标内部 ≤absorb 的小断缝), 返回 mask 与包围盒。
    """
    comps = [c for c in label(mask, w, h, ya, yb) if len(c) >= 2]
    if not comps:
        return None, None
    boxes = sorted(((bbox(c), c) for c in comps), key=lambda t: t[0][0])
    clusters = []
    for b, c in boxes:
        if clusters and b[0] <= clusters[-1]["x1"] + cl_gap:
            cl = clusters[-1]
            cl["x1"] = max(cl["x1"], b[2])
            cl["x0"] = min(cl["x0"], b[0])
            cl["y0"] = min(cl["y0"], b[1])
            cl["y1"] = max(cl["y1"], b[3])
            cl["pix"].extend(c)
        else:
            clusters.append(dict(x0=b[0], x1=b[2], y0=b[1], y1=b[3], pix=list(c)))
    cands = [cl for cl in clusters
             if (cl["x1"] - cl["x0"] + 1) >= min_w and len(cl["pix"]) >= min_area]
    if not cands:
        cands = clusters
    icon = min(cands, key=lambda cl: cl["x0"])
    keep = list(icon["pix"])
    big = max(min_area, int(0.08 * len(icon["pix"])))
    for cl in clusters:
        if cl is icon:
            continue
        # 只吸收"够大且与图标包围盒相邻"的碎块, 不吸收零散噪点(否则会把包围盒撑大)
        if icon["x0"] <= cl["x1"] and cl["x0"] <= icon["x1"] + absorb and len(cl["pix"]) >= big:
            keep.extend(cl["pix"])
    newmask = [[False] * w for _ in range(h)]
    xs, ys = [], []
    for (x, y) in keep:
        newmask[y][x] = True
        xs.append(x)
        ys.append(y)
    return newmask, (min(xs), min(ys), max(xs), max(ys))


def bleed_colors(im, mask, w, h, iters):
    """把前景色向外扩张若干像素, 避免缩放时透明区把底色带进来。"""
    src = im.load()
    out = [list(src[x, y]) for y in range(h) for x in range(w)]
    out = [out[y * w:(y + 1) * w] for y in range(h)]
    cur = [row[:] for row in mask]
    for _ in range(iters):
        nxt = [row[:] for row in cur]
        for y in range(h):
            for x in range(w):
                if cur[y][x]:
                    continue
                acc = [0, 0, 0, 0]
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < w and 0 <= ny < h and cur[ny][nx]:
                        c = out[ny][nx]
                        acc[0] += c[0]
                        acc[1] += c[1]
                        acc[2] += c[2]
                        acc[3] += 1
                if acc[3]:
                    out[y][x] = [acc[0] // acc[3], acc[1] // acc[3], acc[2] // acc[3]]
                    nxt[y][x] = True
        cur = nxt
    return out


def compose(mask, box, frac, feather, bleed_iters, src_im, w, h):
    """裁到 box -> 羽化 alpha -> 预乘等比缩放 -> 反预乘 -> 居中贴进 64x64。

    前景色外扩只在 box 外扩 bleed_iters 像素的小窗口里做(整图做一遍等于白算)。
    """
    x0, y0, x1, y1 = box
    rx0, ry0 = max(0, x0 - bleed_iters), max(0, y0 - bleed_iters)
    rx1, ry1 = min(w, x1 + 1 + bleed_iters), min(h, y1 + 1 + bleed_iters)
    sub = src_im.crop((rx0, ry0, rx1, ry1))
    submask = [mask[y][rx0:rx1] for y in range(ry0, ry1)]
    rows = bleed_colors(sub, submask, rx1 - rx0, ry1 - ry0, bleed_iters)
    cw, ch = x1 - x0 + 1, y1 - y0 + 1
    buf = []
    for y in range(ch):
        for x in range(cw):
            c = rows[y + y0 - ry0][x + x0 - rx0]
            on = mask[y + y0][x + x0]
            buf.append((c[0], c[1], c[2], 255 if on else 0))
    rgba = Image.new("RGBA", (cw, ch))
    rgba.putdata(buf)
    if feather > 0:
        rgba.putalpha(rgba.getchannel("A").filter(ImageFilter.GaussianBlur(feather)))
    # 预乘 -> LANCZOS 缩放 -> 反预乘
    sp = rgba.load()
    prem = Image.new("RGBA", (cw, ch))
    pp = prem.load()
    for y in range(ch):
        for x in range(cw):
            r, g, b, al = sp[x, y]
            f = al / 255.0
            pp[x, y] = (int(r * f + 0.5), int(g * f + 0.5), int(b * f + 0.5), al)
    target = CANVAS * frac
    s = target / max(cw, ch)
    nw, nh = max(1, round(cw * s)), max(1, round(ch * s))
    tmp = prem.resize((nw, nh), Image.LANCZOS)
    res = Image.new("RGBA", (nw, nh))
    tp = tmp.load()
    rp = res.load()
    for y in range(nh):
        for x in range(nw):
            r, g, b, al = tp[x, y]
            if al == 0:
                rp[x, y] = (0, 0, 0, 0)
            else:
                k = 255.0 / al
                rp[x, y] = (min(255, int(r * k + 0.5)), min(255, int(g * k + 0.5)),
                            min(255, int(b * k + 0.5)), al)
    canvas = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    canvas.paste(res, ((CANVAS - nw) // 2, (CANVAS - nh) // 2))
    return canvas


def process(src, dst, mode, p):
    im = Image.open(src).convert("RGB")
    w, h = im.size
    # band: 只保留纵向的这一段落(图例图一张多行时, 按行切开)。
    # 提前算出来, 让 mask 与连通域都只扫这一段, 长条图例才不会按整图算。
    band = p.get("band")
    ya, yb = (int(band[0] * h), int(band[1] * h)) if band else (0, h)
    mask = build_mask(im, mode, p, ya, yb)
    px = im.load()
    split = None
    if mode == "strip":
        # 长条截图的最外 2 圈常带 UI 边框亮线, 直接屏蔽掉(band 的上下边界同样屏蔽)
        ring = p.get("ring", 2)
        for y in range(ya, yb):
            for x in range(w):
                if x < ring or y < ya + ring or x >= w - ring or y >= yb - ring:
                    mask[y][x] = False
        mask, box = keep_left_icon(mask, w, h, ya=ya, yb=yb)
        split = box[0] if box else None
        if mask is None:
            raise RuntimeError("%s: 未找到图标" % src)
    else:
        if band:
            for y in range(h):
                if y < ya or y >= yb:
                    mask[y] = [False] * w
        mask, box = select_main(mask, w, h, px, mode, min_area=p.get("min_area", 3))
    if mask is None:
        raise RuntimeError("%s: 未找到前景" % src)
    if p.get("fill"):
        mask = fill_holes(mask, w, h)
    out = compose(mask, box, p.get("frac", DEF_FRAC), p.get("feather", DEF_FEATHER),
                  p.get("bleed", DEF_BLEED), im, w, h)
    out.save(dst)
    return out, dict(size=(w, h), split=split, box=box,
                     content=(box[2] - box[0] + 1, box[3] - box[1] + 1))


def make_sheet(items, path, scale=3, dark=False):
    cell = CANVAS * scale + 6
    cols = 5
    rows = (len(items) + cols - 1) // cols
    if dark:
        sh = Image.new("RGB", (cols * cell, rows * cell + 20), (34, 34, 38))
    else:
        sh = Image.new("RGB", (cols * cell, rows * cell + 20), (245, 245, 245))
    d = ImageDraw.Draw(sh)
    if not dark:
        for y in range(0, sh.height, 8):
            for x in range(0, sh.width, 8):
                if (x // 8 + y // 8) % 2 == 0:
                    d.rectangle([x, y, x + 7, y + 7], fill=(210, 210, 210))
    for i, (name, im) in enumerate(items):
        cx = (i % cols) * cell + 3
        cy = (i // cols) * cell + 3
        big = im.resize((CANVAS * scale, CANVAS * scale), Image.NEAREST)
        sh.paste(big, (cx, cy), big)
        d.text((cx, cy + CANVAS * scale), name, fill=(255, 255, 0) if dark else (0, 0, 0))
    sh.save(path)
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet", action="store_true", help="额外输出自检拼图")
    args = ap.parse_args()
    os.makedirs(DST, exist_ok=True)
    made = []
    for src_name, dst_name, mode, p in JOBS:
        src = os.path.join(SRC, src_name)
        dst = os.path.join(DST, dst_name)
        if not os.path.exists(src):
            print("缺失源文件:", src)
            continue
        im, info = process(src, dst, mode, p)
        made.append((dst_name, im))
        print("%-26s %-10s src=%sx%s split=%s box=%s content=%s" %
              (dst_name, mode, info["size"][0], info["size"][1], info["split"],
               info["box"], info["content"]))
    print("共输出 %d 个文件到 %s" % (len(made), DST))
    if args.sheet:
        base = os.path.join(os.path.dirname(DST), "..", "tools")
        p = make_sheet(made, os.path.join(base, "_debug_sheet.png"), dark=False)
        q = make_sheet(made, os.path.join(base, "_debug_sheet_dark.png"), dark=True)
        print("自检拼图:", p, q)


if __name__ == "__main__":
    main()
