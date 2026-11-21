# -*- coding: utf-8 -*-
"""生成地图 POI 中文名表（R19.22）。

data/maps.json 里的地名（labels + 图层条目）大量是英文（Big Red / Dorms / White Pawn …），
这些名字会直接画在底图上，属于任务书明确要求处理的「地图目标与地点名称」。

本脚本：
  1) 扫描 maps.json，收集所有「无汉字」的地名；
  2) 用下面的对照表给出中文显示名（品牌/商场名保留原名 + 中文类目，其余按社区通行叫法）；
  3) 断言**没有遗漏**——新增地图/地名时这里会直接报错，避免悄悄退回英文；
  4) 写 data/i18n/poi-zh.json（i18n.js 启动时并入界面词表）。

用法：
    python tools/build_poi_zh.py            # 生成 + 校验
    python tools/build_poi_zh.py --check     # 只校验
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(DATA, "i18n", "poi-zh.json")
CJK = re.compile(r"[\u4e00-\u9fff]")
LATIN = re.compile(r"[A-Za-z]{2,}")

# ---------------------------------------------------------------- 译名表
# 说明：品牌商铺保留原名（玩家按招牌找店），后面加中文类目；地形/建筑按社区通行叫法意译。
ZH = {
    # ==== 海关 customs
    "Big Red": "大红房",
    "Bus Station": "公交站",
    "Crackhouse": "毒窝",
    "Depot": "货场",
    "Dorms": "宿舍",
    "Fortress": "堡垒",
    "Junk Bridge": "废料桥",
    "Main Bridge": "主桥",
    "Military Checkpoint": "军事检查站",
    "New Gas": "新加油站",
    "Old Gas": "老加油站",
    "Old Construction": "旧工地",
    "Powerline Tower": "电线塔",
    "Repair Shop": "维修店",
    "Skeleton": "骨架楼",
    "Sniper Hill": "狙击山",
    "Sniper Ridge": "狙击岭",
    "Storage": "仓储区",
    "Streamer House": "主播屋",
    "Trailer Park": "拖车营地",
    "Warehouse 3": "3 号仓库",
    "Warehouse 4": "4 号仓库",
    "Warehouse 7": "7 号仓库",
    "Warehouse 17": "17 号仓库",
    # ==== 森林 woods
    "Bus Stop": "公交站",
    "Checkpoint": "检查站",
    "Convoy": "车队残骸",
    "Crash Site": "坠机点",
    "Cultist Village": "邪教徒村",
    "Jaeger's Camp": "猎人营地",
    "Lumber": "木料场",
    "Military Camp": "军营",
    "Old Sawmill": "老锯木厂",
    "Ponds": "池塘",
    "Sawmill": "锯木厂",
    "Scav Town": "Scav 镇",
    "Shack": "小屋",
    "Sniper Rock": "狙击岩",
    "USEC Camp": "USEC 营地",
    # ==== 海岸线 shoreline
    "Admin": "行政楼",
    "Bunker": "地堡",
    "Cabins": "木屋区",
    "Construction": "工地",
    "Cottages": "小屋区",
    "Crane": "吊车",
    "East Wing": "东楼",
    "Gas Station": "加油站",
    "Pier": "码头",
    "Power Station": "发电站",
    "Radio Tower": "无线电塔",
    "Resort": "疗养院",
    "Scav Farm": "Scav 农场",
    "Scav Island": "Scav 岛",
    "Swamp": "沼泽",
    "Tank Bridge": "坦克桥",
    "Village": "村庄",
    "Weather Station": "气象站",
    "West Wing": "西楼",
    # ==== 灯塔 lighthouse
    "Boathouses": "船屋",
    "Convenience": "便利店",
    "Dead Tree": "枯树",
    "Drug Lab": "制毒厂",
    "Grand Chalet": "大木屋",
    "Gunner Nest": "机枪巢",
    "Hillside": "山坡",
    "Island": "岛屿",
    "Lightkeeper Island": "灯塔看守岛",
    "Pikes Peak Resort": "派克峰度假村",
    "Pipes": "管道区",
    "Plant 1": "1 号厂区",
    "Plant 2": "2 号厂区",
    "Plant 3": "3 号厂区",
    "Red Brick": "红砖楼",
    "Tennis Court": "网球场",
    "Train Yard": "铁路场",
    "Water Treatment": "水处理厂",
    # ==== 储备站 reserve
    "Barracks": "兵营",
    "Black Bishop": "黑主教楼",
    "Black Knight": "黑骑士楼",
    "Black Pawn": "黑兵楼",
    "Dome": "圆顶",
    "E1 Bunkers": "E1 地堡群",
    "E2 Bunkers": "E2 地堡群",
    "Garage": "车库",
    "K Buildings": "K 楼群",
    "Mechanic": "机修区",
    "Shipping Yard": "货运场",
    "Tarmac": "停机坪",
    "Train Station": "火车站",
    "White Bishop": "白主教楼",
    "White King": "白王楼",
    "White Knight": "白骑士楼",
    "White Pawn": "白兵楼",
    "White Queen": "白后楼",
    "White Rook": "白车楼",
    "д - Warehouse Bunkers": "仓库地堡区",
    # ==== 工厂 factory
    "Blue Containers": "蓝色集装箱区",
    "Boilers": "锅炉区",
    "Breach Room": "破拆房",
    "Connector": "连接通道",
    "East Halls": "东侧走廊",
    "Forklifts": "叉车区",
    "Glass Hall": "玻璃大厅",
    "Heli Crash": "直升机残骸",
    "Hole": "地洞",
    "Locked Office": "上锁办公室",
    "Locker Rooms": "更衣室",
    "Main Office": "主办公室",
    "Med Tent": "医疗帐篷",
    "North Stairs": "北楼梯",
    "Office Building": "办公楼",
    "Pit": "深坑",
    "Platform": "站台",
    "Pumping Station": "泵站",
    "Rafters": "屋顶桁架",
    "Scav Bunker": "Scav 地堡",
    "Servers": "服务器房",
    "Silos": "筒仓",
    "Sinks": "水池区",
    "Sky Bridge": "天桥",
    "South Stairs": "南楼梯",
    "Underground Stash": "地下储藏点",
    "Wood Room": "木料间",
    # ==== 实验室 the-lab
    "Administrative Office": "行政办公室",
    "Boiler Room": "锅炉房",
    "Cafeteria": "自助餐厅",
    "Conference Room": "会议室",
    "Control Room": "控制室",
    "Corridor To Building #2": "通往 2 号楼走廊",
    "Gym": "健身房",
    "Infirmary Lvl 1": "1 层医务室",
    "Infirmary Lvl 2": "2 层医务室",
    "Lecture Hall": "讲堂",
    "Main Working Area": "主工作区",
    "Men's Locker Room": "男更衣室",
    "Negotiation Room": "谈判室",
    "Offices #1": "1 号办公室",
    "Offices #2": "2 号办公室",
    "Parking": "停车场",
    "Reception": "前台",
    "Recreation Area": "休闲区",
    "Security #1": "1 号安保室",
    "Security #2": "2 号安保室",
    "Security Barracks": "安保宿舍",
    "Security Office": "安保办公室",
    "Server Room": "服务器机房",
    "Sterile Laboratory": "无菌实验室",
    "Test Room": "测试间",
    "Vestibules #1": "1 号前厅",
    "Vestibules #2": "2 号前厅",
    "Warehouse": "仓库",
    "Warehouse Gate": "仓库大门",
    "Warehouse Tunnels": "仓库隧道",
    "Women's Locker Room": "女更衣室",
    # ==== 立交桥 interchange（商场品牌保留招牌名 + 中文类目）
    "ADIK": "ADIK 运动店",
    "Arena": "Arena 场馆",
    "Avokado": "Avokado 店",
    "Bizarro": "Bizarro 店",
    "Book Store": "书店",
    "Boots 4 Life": "Boots 4 Life 鞋店",
    "Brutal": "Brutal 店",
    "Burger House": "汉堡屋",
    "Burger Spot": "汉堡店",
    "Cargo Containers": "货运集装箱",
    "Coffee Joy": "Coffee Joy 咖啡",
    "Dino Clothes": "Dino 服装店",
    "Dom": "Dom 商场",
    "Eastland": "Eastland 商场",
    "EMERCOM": "紧急情况部",
    "FCK": "FCK 店",
    "Fashion Store": "时装店",
    "Father & Sons": "父子商店",
    "Figaro": "Figaro 店",
    "Four Camp": "四营区",
    "Garage A": "A 车库",
    "Garage B": "B 车库",
    "Garage C": "C 车库",
    "Garage D": "D 车库",
    "Generic": "Generic 店",
    "German": "German 店",
    "Go Kart": "卡丁车场",
    "Goshan": "Goshan 大卖场",
    "Highway Construction": "公路施工区",
    "IDEA": "IDEA 家具城",
    "Idea Tower": "IDEA 塔楼",
    "Intourist": "Intourist 酒店",
    "Jacob & Jacob": "Jacob & Jacob 店",
    "Kiba": "Kiba 武器店",
    "Kostin": "Kostin 店",
    "Mantis": "Mantis 军品店",
    "McDaniels": "McDaniels 店",
    "Mode7": "Mode7 店",
    "Nortex": "Nortex 店",
    "OLI": "OLI 超市",
    "Oli Tower": "OLI 塔楼",
    "Papillon": "Papillon 店",
    "Philly Cute": "Philly Cute 店",
    "Pretty Lights": "Pretty Lights 店",
    "Ramps": "坡道区",
    "Rasmussen": "Rasmussen 店",
    "Revis": "Revis 店",
    "SARA": "SARA 店",
    "Scav Camp": "Scav 营地",
    "Shiccos": "Shiccos 店",
    "Spiel": "Spiel 店",
    "Sports": "体育用品店",
    "Sushi Huyushi": "Sushi Huyushi 寿司店",
    "TECHLIGHT": "TECHLIGHT 电器行",
    "TRend": "TRend 店",
    "TTS": "TTS 店",
    "Tarducks": "Tarducks 店",
    "Tarkovstar": "Tarkovstar 店",
    "Telespot": "Telespot 店",
    "Texho": "Texho 店",
    "The National": "The National 店",
    "Top Brand": "Top Brand 店",
    "Underway": "Underway 店",
    "Urban Clothes": "Urban 服装店",
    "Viking": "Viking 店",
    "Voyage": "Voyage 店",
    "Wall Break": "破墙通道",
    "Yushka": "Yushka 店",
    # ==== 中心区 ground-zero
    "ASAP Winery": "ASAP 酒庄",
    "Capital Insight": "Capital Insight 大楼",
    "Elemental Global": "Elemental Global 大楼",
    "Empire": "帝国大厦",
    "Fusion": "Fusion 大楼",
    "GAGRIN Hotel": "加加林酒店",
    "M Showroom": "M 展厅",
    "Nakatani": "中谷大楼",
    "Oasis": "绿洲",
    "Science Office": "科研办公室",
    "Skyside": "天际大楼",
    "TerraGroup": "TerraGroup 大楼",
    "Tarbank": "塔科夫银行",
    # ==== 塔科夫街区 streets-of-tarkov
    "Abandon Factory": "废弃工厂",
    "Beluga": "白鲸餐厅",
    "Bilbo Coffee": "比尔博咖啡",
    "Cardinal Apartments": "卡迪纳尔公寓",
    "Cardinal Bank": "卡迪纳尔银行",
    "Chekannaya St.": "契卡纳娅街",
    "Cinema": "电影院",
    "Concordia": "康科迪亚",
    "Corner Restaurant": "街角餐厅",
    "Diner": "餐馆",
    "Family Market": "家庭超市",
    "Hive": "蜂巢",
    "Kamchatskaya St.": "堪察加街",
    "Kilmov Shopping Mall": "基尔莫夫购物中心",
    "Kilmov St.": "基尔莫夫街",
    "LERM Expo": "LERM 会展中心",
    "Lexos": "莱克索斯酒店",
    "Malevecha St.": "马列维奇街",
    "Marked Hotel": "标记酒店",
    "Nikitskaya St.": "尼基茨卡娅街",
    "Nizhnyaya St.": "下街",
    "Office": "办公室",
    "Pharmacy 1": "药店 1",
    "Pharmacy 2": "药店 2",
    "Pharmacy 3": "药店 3",
    "Pinewood Hotel": "松木酒店",
    "Post Office": "邮局",
    "Prestigio Cafe": "普雷斯蒂吉奥咖啡馆",
    "Primorskij 49": "滨海路 49 号",
    "Primorsky Ave.": "滨海大道",
    "Razvedchikov St.": "侦察兵街",
    "School": "学校",
    "Shestyorochka": "六号便利店",
    "South Hotel": "南方酒店",
    "Sparja Express": "斯帕贾快捷店",
    "Sparja Grocery": "斯帕贾杂货店",
    "Teppakot / Koener": "特帕科特 / 科纳",
    "Verhnyaya St.": "上街",
    "Vet Clinic": "兽医诊所",
    "Zmejskij Alley": "蛇巷",
    # ==== 迷宫 the-labyrinth / 其它
    "ZB-1013": "ZB-1013 撤离点",
    "ZB-1011": "ZB-1011 撤离点",
    "ZB-014": "ZB-014 撤离点",
    "ZB-016": "ZB-016 撤离点",
    "Crossroads": "十字路口",
    "Railroad to Reserve": "通往储备站的铁路",
}


# Boss 代号：专有名词，玩家按代号称呼（翻译反而失去辨识度）→ 明确保留英文，
# 不当中文缺口；i18n.js 的 keptEnglish 白名单与此保持一致。
KEEP_PROPER = {
    "Reshala", "Killa", "Glukhar", "Shturman", "Sanitar", "Tagilla", "Knight",
    "Kollontay", "Kaban", "Scourge", "The Wedge",
    # 2026-11-15 上游新增：万圣节「感染」事件的 Boss 代号与灯塔 Boss，
    # 与其它 Boss 代号同口径保留英文（见上方 KEEP_PROPER 说明）。
    "Infected Tagilla", "Zryachiy",
}


def collect() -> dict:
    with open(os.path.join(DATA, "maps.json"), encoding="utf-8") as fh:
        maps = json.load(fh)["maps"]
    out = {}
    for mp in maps:
        for lab in mp.get("labels") or []:
            name = lab.get("text") or lab.get("name") or ""
            if LATIN.search(name) and not CJK.search(name):
                out.setdefault(name, set()).add(mp["key"])
        # 图层有两种形态：{items:[…]} 与直接是列表（extracts / bosses 就是这样）
        for _key, layer in (mp.get("layers") or {}).items():
            if isinstance(layer, dict):
                items = layer.get("items") or []
            elif isinstance(layer, list):
                items = layer
            else:
                continue
            for it in items:
                if not isinstance(it, dict):
                    continue
                name = it.get("name") or it.get("n") or ""
                if LATIN.search(name) and not CJK.search(name):
                    out.setdefault(name, set()).add(mp["key"])
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    found = collect()
    missing = sorted(n for n in found if n not in ZH and n not in KEEP_PROPER)
    kept = sorted(n for n in found if n in KEEP_PROPER)
    extra = sorted(n for n in ZH if n not in found)
    print("地图英文地名 %d 个；译名表 %d 条；合理保留 %d（Boss 代号）；缺译 %d；多余 %d"
          % (len(found), len(ZH), len(kept), len(missing), len(extra)))
    for n in missing:
        print("  MISSING:", n, "|", ",".join(sorted(found[n])))
    if extra:
        print("  多余（数据里已不存在，可清理）：", extra[:10])
    payload = {
        "schema": 1,
        "note": "地图 POI 中文名（显示层）。品牌商铺保留招牌名 + 中文类目；数据本身不改。",
        "generatedBy": "tools/build_poi_zh.py",
        "count": len(ZH),
        "entries": ZH,
        "byMap": {k: sorted(v) for k, v in found.items()},
    }
    if not args.check:
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=1)
        print("wrote", OUT)
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
