# R209 · Kaedeori「装备构筑 / 登录与会员」逆向对照

对象：`D:\personal\trae\02-塔科夫\逆向参考\tarkov.kaedeori\tarkov-kaedeori-client`
对照：`d:\personal\trae\02-塔科夫\eft-interactive-map`
日期：2026-11-07 · 只分析，不改源码

---

## 0. 结论速览

| 问题 | 结论 |
|---|---|
| 装备构筑能不能借鉴 | **可借鉴，但不值得整体照搬**。它的槽位模型、指标联动我们已经有且更细；真正值得抄的是 **线上分享码 / 社区公开页 / 构筑图复制 / 必需槽完整性标记** 这四件“产品化外壳”。枪械分析深度（ADS、臂力、爆头距离、优化器、组合链、对比、MOA 建模）我们领先。 |
| 它的构筑是不是收费点 | **不是**。装备构筑的查看、公开列表、分享页全部匿名可用；只有“新建/编辑并保存到账号”需要登录。会员权益是去广告、去标记频率限制、专属工具、miniRadar/QuickSearch，构筑本身不在付费墙内。 |
| 我们能不能做登录 | **技术上能做**，但它不是“做一个登录框”，而是接入了自家跨产品 Passport（SSO）+ 支付宝/微信 + CDK。我们如果只做账号，最小路径是“邮箱验证码 + Session Cookie + 云预设同步”。 |
| 值不值得做成会员收费 | **现阶段不建议做重会员体系**。纯本地功能收费必被复制；只有云端数据、跨设备同步、公开构筑库、持续更新与客服这些“服务端价值”收得住钱。短期最合理的是 **免费核心 + 爱发电/赞助码**，中期再考虑正式支付。 |
| D 加密（Denuvo）能不能仿 | **不建议**。Denuvo 的核心是“服务端签发的硬件绑定许可证 + 代码虚拟化 + 完整性校验 + 反调试”，需要专门 DRM 后端和逐版本处理，且它本身也只能拖延破解。对 Python/JS 本地应用，投入产出比极低。详见 §3.6。 |

---

## 1. 分析方法与证据边界

### 1.1 客户端结构（rea MCP）

- `rea.open_binary` 打开 `resources\app.asar`：`format=asar`，sha256 `60347702d4e325ab2f7c0b37f69360d6ed205bf3028cf0874c3b4852b564265d`。
- `rea.inspect_artifact`（summary）：**36,313 个条目**，`source_coverage=complete`。
- `rea.extract_artifact`：解出到临时目录（本次 `D:\Temp\2\rea-extracted-75b4f706-5bea-4064-a02f-ee14ec68f52d`），`node_count=11582` / `occurrence_count=12366`。
- 结论：Electron 客户端本身只是 **壳 + 启动器 + 悬浮窗**，真正的塔科夫助手界面是远程网页。

关键证据（本机解包文件）：

| 事实 | 位置 |
|---|---|
| 主窗口加载远程页面 | [background.js#L2694] `${baseUrl}/interactive` |
| 默认服务端 | [background.js#L811] `https://member.kaedeori.com` |
| 可信来源白名单 | [background.js#L812] `member/svip/tarkov/dev.kaedeori.com` |
| 版本 | `package.json` → `1.5.8`，`electron-updater ^6.1.1` |
| 更新源 | `resources\app-update.yml` → generic provider，`cdn.kaedeori.com/distro/tarkov` |

### 1.2 远程网页（因为界面不在 asar 里）

- 入口 `https://member.kaedeori.com/interactive`，资源版本 **4.13.4**。
- 实际下载并分析：
  - `https://cdn.kaedeori.com/assets/tarkov/static/4.13.4/main.js` — 2,975,988 B（业务代码，压缩未混淆）
  - `https://cdn.kaedeori.com/assets/tarkov/static/4.13.4/global.js` — 550,316 B（i18n + 公共库）
  - `https://cdn.tiltysola.com/assets/passport-v2/static/index.js` — 2,807,542 B（统一账号 Passport）
- 无 source map（`main.js.map` / `global.js.map` 均 404），所以证据以 **可检索的函数名 / 接口路径 / i18n key** 为主。
- 网络：本机经本地代理出网（响应头出现 `HTTP/1.1 200 Connection established`），目标站点实际返回 **HTTP 200**；未出现证书绕过或访问失败。
- 运行时边界：**没有登录账号**，因此套餐价格、支付下单、后台管理只做了静态确认，未端到端走通；文中会标注“静态推断”。

---

## 2. 装备构筑

> 它自己的中文名：导航项 **“装备构筑”**（`nav.items.loadoutBuilder`），单件武器页叫 **“武器改装”**。
> 一条构筑 = 最多 10 个根槽位：`weapon / weapon2 / sidearm / helmet / headset / bodyArmor / rig / faceCover / eyewear / backpack`（`Mq` 常量；公开构筑实测也是这 10 个 key）。

### 2.1 能力清单（逐项有证据）

| 能力 | 有没有 | 证据 |
|---|---|---|
| 选枪/选甲/选头盔（基础物品） | 有 | `GET /api/tarkov/build/bases?kind=weapon&page=&pageSize=&name=&lang=&gameMode=`；`UYe` 基础物品选择器 |
| 槽位树 + 配件安装 | 有 | `GET /api/tarkov/build/detail?id=&lang=&gameMode=` 返回 `slots[]`（`key` 形如 `mod_pistol_grip:5c6beec0...`、`nameId`、`required`、`allowedItemIds`、`compatibleItems`） |
| 属性联动（整枪/整身） | 有 | `Aq` 汇总：`itemCount / totalPrice / totalWeight / requiredSlots / filledRequiredSlots / ergonomics / recoilVertical / recoilHorizontal / centerOfImpact / muzzleVelocity / sightingRange / durability / armorClass / armorZones / speedPenalty / turnPenalty / ergoPenalty` |
| 必需槽位提示 | 有（但保存不拦） | `Aq` 计算 `requiredSlots/filledRequiredSlots`；i18n `loadoutBuilder.incomplete`、`required-slot` |
| 兼容性校验 | 有（服务端数据驱动） | 载入时 `Fq` 逐槽检查 `allowedItemIds`，不匹配抛 `Equipment slot is no longer compatible`，i18n `loadoutBuilder.invalid` |
| 冲突提示 | 有（只提示不阻断） | `conflictingItems / conflictingSlotIds / blocksHeadphones / blocksEyewear / blocksHeadwear`；i18n `loadoutBuilder.conflicts` |
| 保存预设 | 有（存服务端账号） | `POST /api/tarkov/equipmentBuild/create`、`/update`；字段 `title / description / isPublic / gameMode / equipment` |
| 预设列表 | 有 | `GET /api/tarkov/equipmentBuild/list?scope=mine|public&query=&page=&pageSize=20` |
| 分享 / 导入 | 有 | `shareCode` 12 位（字母表 `23456789ABCDEFGHJKLMNPQRSTUVWXYZ`，排除易混字符）；公开页 `/equipment-build/:code`；导入 `/app/loadoutbuilder/new?preset=CODE` → `GET /api/tarkov/equipmentBuild/share?code=` |
| 公开/私密 | 有 | `PATCH /api/tarkov/equipmentBuild/visibility`；卡片显示“公开构筑” |
| 删除 | 有 | `POST /api/tarkov/equipmentBuild/delete` + 确认弹窗 |
| 构筑图复制到剪贴板 | 有 | `copyToClipboard` 生成 PNG，`ClipboardItem` + `image/png`；`html-to-image` 在依赖表中 |
| 解锁条件（商人等级/任务） | 有 | `GET /api/tarkov/item/unlock` + `GET /api/tarkov/trader/barters`；i18n `loadoutBuilder.inspect-unlocks`、`unlock.trader/task/unknown` |
| 单件武器/护甲小组件 | 有 | 路由 `/app/loadoutbuilder/single`，i18n `loadoutBuilder.single.*` |
| 枪匠参考图/任务预设 | 有（内置静态） | `$qe` 内置表：`sourceArchive:"枪匠(1).rar"`，条目带 `shareCode/taskName/images` |
| 对比两套构筑 | **没有** | 全包检索 `compare` 未命中构筑相关代码 |
| 随机/自动配装 | **没有** | 全包检索 `random`/`auto build` 未命中构筑相关代码 |
| 跨模式 | 有 | 每个接口都带 `gameMode`（实测 `pvp` 有效；`pve` 是另一套） |
| 游客可用 | 有 | 匿名 `GET /api/tarkov/equipmentBuild/list?scope=public` 实际返回 200；只有 `new`/`:id/edit` 路由套了登录守卫 |

**匿名实测样本**（本次探测时公开区共 3 条）：

```
GET /api/tarkov/equipmentBuild/list?scope=public&page=1&pageSize=2&lang=zh&gameMode=pvp
→ code 200, total 3
条目：E3DS4P6MTDHL  valid  "爱国力作"  19 件
      7FMGB7AL6PXY  valid  "扮猪吃饲料" 20 件
slots = weapon, weapon2, sidearm, helmet, headset, bodyArmor, rig, faceCover, eyewear, backpack
author.avatar = passport.mahoutsukai.cn / cdn.tiltysola.com
```

### 2.2 数据从哪来

- **不是内置 JSON，也不是构建期快照**：每次打开构筑都打服务端接口。
  - 基础物品：`/api/tarkov/build/bases`（分页 + 名称搜索 + `kind`）
  - 单件详情/槽位/兼容项：`/api/tarkov/build/detail`（返回 `slots`、`allowedItemIds`、`compatibleItems`、`defaultPreset`）
  - 可选项搜索：`/api/tarkov/equipmentBuild/options`（按槽位/页）
  - 解锁：`/api/tarkov/item/unlock`、`/api/tarkov/trader/barters`
  - 用户构筑：`/api/tarkov/equipmentBuild/*`
- 图标走 CDN：`cdn.kaedeori.com/uploads/tarkov/icons/{id}-icon|grid-image|image.webp`。
- 好处：数据可热更、PvE/PvP 可分别维护、兼容关系（`allowedItemIds`）由服务端一处计算。
- 代价：离线不可用；每次点击都依赖网络与账号会话；服务端是唯一事实源。

### 2.3 交互流程

```
列表页 /app/loadoutbuilder
  ├─ 我的 / 公开 两个 scope，搜索 + 每页 20 + 上拉加载
  └─ 卡片：标题、描述、作者、槽位摘要、件数、总价、重量、有效状态、公开开关、删除
新建 /app/loadoutbuilder/new（需登录）
  ├─ 选基础物品（弹层，分页/搜索/按 kind）
  ├─ 逐槽展开：必需槽标 *，兼容项列表带图标/名称/价格
  ├─ 选中后即时重算：件数 / 总价 / 重量 / 人机 / 后坐 / MOA / 初速 / 防护
  ├─ 冲突区提示（不阻断）
  ├─ 保存：标题必填 + 至少一个根物品；可选公开
  └─ 分享：生成 12 位码 / 复制链接 / 复制构筑图
详情 /app/loadoutbuilder/:id（只读视图）
  ├─ 分槽展示 + 指标 + 解锁条件
  └─ 作者可编辑/删除/改可见性；他人可“复制为己用”
公开页 /equipment-build/:code（匿名可看）
  └─ 复制预设码 / 复制分享链接
单件 /app/loadoutbuilder/single
  └─ 只改装一把枪或一件甲，用于嵌入其他页面
```

**校验做到什么程度**（静态代码 + i18n）：

- 保存前只校验 **标题非空 + 至少一个根物品**；不校验必需槽是否填满。
- `requiredSlots` 只用于 UI 标记与“不完整”提示。
- 载入旧构筑时做兼容校验：槽位 `allowedItemIds` 不含当前件 → 标记失效（`invalid`），不会自动替换。
- 上游数据同步期间有 `sync-notice`；价格缺失有 `price-missing` 文案。
- 冲突（耳机/眼镜/头盔互斥、`conflictingItems`）只聚合展示，不阻止保存。

### 2.4 与我们的实现对照

我们的模型（源码）：

| 维度 | Kaedeori | 我们 | 结论 |
|---|---|---|---|
| 根槽位 | 10 个（含 2 把主武器 + 手枪） | **11 个**：头盔/耳机/眼镜/护面/护甲/胸挂/背包/主武器1/主武器2/手枪/近战 [app.js#L8705](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/app.js#L8705) | 我们更全（多近战，护面/眼镜分类更细） |
| 子槽 | 有，嵌套树 | 有，卡片紧跟父装备的子槽条 [app.js#L9143-L9145](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/app.js#L9143-L9145) | 持平 |
| 枪械槽位 | 直接选基础枪 | 引用本地枪械预设 `@wp:<presetId>`（[index.html#L698](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/index.html#L698) 附近的配装栏） | **我们更实用**：整枪方案可复用 |
| 数据来源 | 服务端每次请求 | 构建期快照，运行期不联网（R74 台账：`data/*.json` + 本地后端） | 各有取舍；我们离线是优势 |
| 指标 | 件数/总价/重量/人机/后坐/MOA/初速/防护区/惩罚 | 移动/转身/人机 + 总重 [app.js#L11317](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/app.js#L11317)，枪械侧另有 ADS/臂力/爆头距离/MOA/成本 [gun_builder.js#L214](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/gun_builder.js#L214) | **枪械分析我们领先**；整身“防护区汇总”我们只有逐件列 |
| 保存 | 服务端账号 + 可见性 | 本地原子写盘 `%APPDATA%\EFTMap\*.json` [tools/presets.py#L49](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/tools/presets.py#L49) | 我们缺云与社区 |
| 分享 | 12 位码 + 公开页 | 本地文件导入/导出 [index.html#L706](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/index.html#L706) | **最值得补** |
| 优化/对比/组合链 | 无 | 有：`optimize` / `compare` / `chains` [gun_builder.js#L1032](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/gun_builder.js#L1032) / [#L680](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/gun_builder.js#L680) / [#L643](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/gun_builder.js#L643) | **我们领先，不要退步去学它** |
| 预设结构 | 嵌套 `{itemId, children:[{slotKey, node}]}` | 扁平 `slots:{path→itemId}` [gun_builder.js#L610](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/gun_builder.js#L610) / [L623](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/gun_builder.js#L623) | 扁平更易校验/合并；嵌套更适合跨版本迁移 |
| 合法性 | 保存弱校验，载入强校验 | 解析即严格校验（kind/gunId/slots）[gun_builder.js#L623](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/gun_builder.js#L623) | 我们更严 |

补充：我们的枪械结构是“兼容图 + 安装链”，不是固定清单（`buildTree` [gun_builder.js#L66](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/gun_builder.js#L66)）。他们每个 `slot` 直接给 `allowedItemIds`，更像“服务端裁好的白名单”。两者结论等价，但我们的可解释性更强。

### 2.5 借鉴分级与改动量

#### A. 已经不比它差（不建议动）

- 槽位模型、子槽、兼容校验、预设本地持久化、候选表 20+ 列、价格 24h/7d、枪械工作台。
- 我们的枪械指标与优化器是核心资产，**不要为了对齐它的 UI 而简化**。

#### B. 明显值得抄（低成本、用户可感知）

| 项 | 为什么值 | 改动量 | 备注 |
|---|---|---|---|
| **构筑分享码 + 导入** | 我们没有“发一个码给别人”的路径 | **1–2 天** | 关键取舍：它 12 位码靠 **服务端注册表**；纯本地做不到 12 位装下 19 件，需改成“压缩 JSON 的长码”（约 120–300 字符）或后端起服务 |
| **构筑图导出/复制** | 社区传播最强的一环 | **1–2 天** | 用 DOM→Canvas 或离屏布局，本地图标直接可用，不依赖网络 |
| **必需槽完成度 + 失效/过期徽标** | 现在只有解析报错，没有状态化 UI | **0.5–1 天** | 数据已有（`slots` / `required`），只需加状态与文案 |
| **解锁条件汇总面板** | 我们已有商人等级/任务解锁数据 | **0.5 天** | 在枪械工作台候选/构筑详情里聚合展示，无需新数据源 |
| **公开构筑库** | 真正能形成社区 | **2–4 周 + 后端** | 需要账号、审核、举报、存储；不建议在没有账号体系时做 |

#### C. 抄了代价大收益小（不做）

- **每次点击都请求服务端拿物品详情**：会把我们“纯本地离线”的根基拆掉，换来只是热更；我们的构建期快照已经覆盖需求。
- **重写整套构筑数据模型为嵌套树**：迁移成本高，收益只是“看起来像它”。
- **`/single` 嵌入式小组件**：我们的枪械工作台已经能覆盖，额外抽象价值低。
- **服务端裁白名单**：我们本地兼容图更透明，且可离线解释。

**短期净改动量估算：3–5 个工作日**（分享码长码 + 图片导出 + 状态徽标 + 解锁面板），不改数据层、不改打包。

---

## 3. 登录与会员

### 3.1 它自己的登录是怎么做的

**它不是“给这个工具写了个登录”，而是复用了自家跨产品 Passport。**

| 环节 | 事实 | 证据 |
|---|---|---|
| 客户端登录入口 | 主窗口直接加载远程页，未登录时页面跳转登录 | `background.js` L2694 加载 `/interactive`；网页内 `new URL('/api/passport/auth/login')` + `redirect_uri` |
| 账号体系 | 自建 Passport（TiltySola），非第三方托管 | `cdn.tiltysola.com/assets/passport-v2`；接口 `/api/passport/*` |
| 支持的登录方式 | 邮箱/手机号 + 密码；QQ / Steam / Natayark OAuth | `/api/passport/auth/login`、`/auth/register`、`/auth/acquire/mail|sms`、`/auth/recovery`、`/auth/qq|steam|natayark/login`；客户端白名单含 `passport.mahoutsukai.cn`、`graph.qq.com` |
| 人机验证 | Geetest v4 | Passport bundle 内 `geetest` 初始化与 `captcha` 校验 |
| 二次验证 | TOTP（2FA） | `/api/passport/user/totp/setup|enable|disable|regenerate`、`/auth/totp/verify` |
| 设备管理 | 有（列表/单端登出/全端登出） | `/api/passport/user/device/list|logout|logout-all` |
| SSO | 有（授权确认/查看/撤销 + 客户端管理） | `/api/passport/sso/authorize/info|confirm`、`/sso/user/authorizations|revoke`、`/sso/admin/clients|register|reset-secret` |
| 账号运营 | 优惠券/积分/礼包抽奖 | `/api/passport/user/coupon/log`、`/credit/log`、`/gift/prize/list|lottery|exchange` |
| 鉴权方式 | **服务端 Session Cookie `accessToken`**，不是客户端 JWT | 网页从 `document.cookie` 读 `accessToken`；Profile 走 `/api/passport/user/profile`；WebSocket 用 cookie token + `md5(channel+version+token)` 做 query 参数 |
| 会话维持 | 30 秒轮询 profile + 1 秒 cookie 比对 + Electron `cookie_changed_client` IPC + 焦点/上线刷新 | `main.js` session store；`background.js` L700 监听 `accessToken` cookie；L326 退出时 flush |
| 客户端 VIP 判定 | 读服务端 profile：`uuid` + `premium.level>0` + `endAt` | `background.js` L661 `isTarkovVipProfile`；L773/L832 |
| 离线校验/机器绑定 | **没有** | 客户端只信服务端 profile；无本地 license、无硬件指纹校验 |
| 退出登录 | 调 `/api/passport/user/logout` 后跳转 | `main.js` `logout` 逻辑 |

**结论**：登录是“平台级 SSO + 服务端会话”，客户端只是浏览器壳。它不是为单机离线设计的，也没有做任何本地授权。

### 3.2 支付 / 订阅痕迹

| 事实 | 证据 |
|---|---|
| 支付网关自建，接口 `/api/payment/v2/*` | `meta` / `good/list` / `order/create` / `order/invoke/wechat` / `order/invoke/alipay_page` / `order/status` / `order/result` |
| 支付方式 | `meta` 实测 `alipay=true`、`wechat=true`；前端有 `wechat_jsapi` / `alipay_page` 分支 |
| 微信 | 公众号 OAuth `appid=wx97c14877302cf192`，`redirect_uri=internal.kaedeori.com/payment?orderId=` |
| 支付宝 | 前端提示“支付宝密钥未配置前不可用”（代码内文案） |
| 价格/套餐 | **服务端 SKU 下发，未登录不可见**：实测 `GET /api/payment/v2/good/list` → `{"code":20028,"error":"USER_NOT_LOGIN"}` |
| 订阅模型 | `premium.level / startAt / endAt`；前端有周/月/季/年/折扣标签（i18n） |
| CDK | `/api/passport/cdkey/activate`；用户中心“激活 CDK”菜单 |
| 邀新/分成 | `/api/passport/referral/*`（邀请码、返利记录） |
| 后台 | 网页内嵌 `/api/passport/admin/*`（用户/订单/CDK/公告） |
| 合规痕迹 | 页脚 ICP：`鄂ICP备15011876号-4`；独立支付子域 `internal.kaedeori.com` |

**会员权益**（i18n 明确三项）：

1. `noMarkerLimit`：移除地图标记频率限制  
2. `noAds`：隐藏界面广告  
3. `exclusiveTools`：会员专属功能与工具  

**客户端侧真正被 VIP 门控的功能**：`miniRadar`（迷你雷达悬浮窗）与 `quickSearch`（快捷搜索），服务端下发 `{miniRadar, quickSearch, expiresAt}`，客户端 45 秒重验；促销期两者临时免费（`CLIENT_FEATURE_FREE_START/END`）。

**关键结论：装备构筑不在付费墙内。** 构筑列表/公开页匿名可看；只有“新建/编辑保存”需要登录。它把收费放在“限制类 + 悬浮窗 + 去广告”上，而不是数据本身。

### 3.3 我们项目现状

- 纯本地、单机、无账号（`eft-interactive-map`）。
- 预设是本地 JSON，后端 `tools/presets.py` 原子写盘，`/api/presets` **无鉴权**（本机回环即可读写）[tools/serve.py#L2068](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/tools/serve.py#L2068)。
- 分发形态：PyInstaller + Inno Setup，安装包约 127 MiB（R74 台账）；`data/*.json`、前端 JS 均为明文。
- 这决定了：**任何“本地开关式”收费都能被改**，详见 §3.5。

### 3.4 最小可行路径（如果要做）

**路径 A：只做账号 + 云同步（不收费，2–3 周）**

1. 后端：一台小 VPS + 域名 + HTTPS（国内需备案；海外可先不备案但延迟/支付受限）。
2. 账号：邮箱验证码登录（最省事）或 OAuth；`HttpOnly + Secure + SameSite` 的 Session Cookie。
3. 数据：SQLite 起步（用户、预设、分享码、审计），迁移到 Postgres 再优化。
4. 同步：本地预设双向同步，冲突按 `updatedAt` + 设备 id 解决；离线可用，联网时合并。
5. 分享：短码必须服务端注册；本地模式只能长码。
6. 客户端：登录页、令牌存 DPAPI、退出/切换账号、隐私政策入口。

**路径 B：赞助 + CDK（在 A 之上再加 1–2 周）**

- 支付渠道用 **爱发电 / 面包多 / 淘宝自动发货** 这类个人可行的方式，服务端只做 **CDK 校验 → 权益**。
- 权益只给“服务端价值”：云同步额度、公开构筑库发布权、更新通道、专属数据源。
- 不做本地功能锁；否则一改就破。

**路径 C：正式支付（1–2 个月，需资质）**

- 个体户/公司 + 微信商户号 + 公众号（JSAPI 需认证，约 300 元/年）+ 支付宝开放平台。
- 订单状态机、幂等、回调验签、退款、对账、发票。
- 合规：隐私政策、用户协议、退款规则、个人信息清单、未成年人提示、数据删除入口。

**必须新增的东西（清单）**：服务端进程、数据库、账号/会话、邮件或短信、支付回调、权益服务、CDN/对象存储、更新签名、日志与监控、客服与退款流程。

### 3.5 诚实的风险评估

#### 1) 本地应用发出去后能不能被复制/破解

| 防护手段 | 实际效果 | 成本 |
|---|---|---|
| 明文 JSON/JS | 直接读、直接改 | 0 |
| PyInstaller 打包 | `pyinstxtractor` 可解包，`.pyc` 可反编译；数据文件原样 | 低 |
| PyArmor / Nuitka | 提高门槛，仍可动态 dump/补丁；对“改一个 if”无效 | 中 |
| 自写完整性校验 | 可被 patch 掉校验函数；只能挡小白 | 低-中 |
| 硬件指纹 + 在线校验 | 能挡“拷给别人直接用”，挡不住“破一次再分发补丁” | 中-高 |
| Denuvo 式代码虚拟化 | 需专门 DRM 团队/后端；仍会被攻破 | 极高 |

**结论**：本地-only 的付费功能，**默认假设 100% 可被绕过**；区别只是“多久”和“多少人会”。所以不要把“本地数据/本地功能”当商品。

#### 2) 支付渠道在国内个人开发者的实际门槛

- **微信支付**：需要商户号；商户号需要营业执照（个体户可）。公众号 JSAPI 还需认证（约 300 元/年）+ 域名备案 + 支付授权目录。
- **支付宝**：电脑网站支付/APP 支付需要企业或个体工商户资质；个人一般只能走当面付/收款码，不适合自动开通会员。
- **个人可行替代**：爱发电（订阅/赞助，平台抽成，提现到支付宝）、面包多、知识星球、淘宝虚拟商品自动发货（CDK）。缺点是：无标准化回调、退款/发票由平台规则决定、用户体验割裂。
- **隐性成本**：域名/备案（1–3 周）、服务器（约 100–300 元/月起）、CDN/存储、客服时间、退款纠纷、发票。

#### 3) 退款、发票、合规、用户数据

- **退款**：数字商品/服务需在用户协议里明确“虚拟内容交付后不适用七天无理由”的边界，但仍有争议与平台介入成本。
- **发票**：个人无法规范开票；个体户/公司要税务登记、申报、开票系统。
- **合规**：PIPL（告知-同意、最小必要、删除权）、网络安全、未成年人保护；账号/手机号/支付信息都是个人信息。
- **数据**：必须做备份、访问控制、泄露应急；一旦收费，用户对可用性和数据安全的要求会显著提高。
- **IP**：EFT 物品图标/数据版权归 BSG 或上游；收费产品要重新评估素材授权与 EFT ToS，避免“售卖游戏内容/作弊功能”的合规风险。

#### 4) 哪些价值放服务端才收得住钱

| 放服务端（可收费） | 放本地（必然白送） |
|---|---|
| 云预设同步、跨设备 | 本地预设文件 |
| 公开构筑库、分享码、审核/举报 | 本地导入导出 |
| 持续更新的数据源（PvE/PvP、价格、任务） | 随包 JSON 快照 |
| 账号权益、更新通道、客服 | 单机功能开关 |
| 社区/榜单/订阅 | 本地计算与优化器 |

一句话：**卖“持续服务”，不要卖“一个文件”。**

### 3.6 D 加密（Denuvo）原理与可行性

**原理（公开逆向研究归纳）**：

1. **构建期改写**：把选定的热路径函数抽成自定义字节码，由内置虚拟机解释执行；原指令被移除，内存 dump 拿不到原始代码。
2. **“被偷走的常量”**：把部分指令常量拆走，运行时用许可证数据重组；没有正确 license 就跑不起来。
3. **硬件指纹**：CPU/主板/BIOS/磁盘序列号/GPU/MAC/系统参数哈希成 Machine ID。
4. **在线激活**：首次启动把指纹 + 购买凭证发给许可服务器，返回**硬件绑定的签名 token**并落盘。
5. **完整性/反调试**：校验可执行文件与运行环境，检测调试器/虚拟机/注入。
6. **逐版本差异化**：每个 build 的保护形态不同，提高通用破解工具的复用成本。
7. **目标**：不是“不可破”，而是**把破解推迟到发行窗口之后**；事实上多个 Denuvo 作品仍被攻破。

**我们能不能实现类似功能**：

| 方案 | 可行性 | 说明 |
|---|---|---|
| 完整 Denuvo 式（自研 VM + 许可后端 + 逐版本） | **不建议** | 需要专门的 DRM 工程与长期维护；对 Python/JS 应用还要先解决“字节码/源码本身可读” |
| 部分仿制：服务端签发“账号+机器”短期 token，客户端定期校验 | 可做 | 能挡复制分发；但可被补丁绕过，适合作为“服务端权益”的配套，而非核心 |
| PyArmor/Nuitka + 完整性自检 + 混淆 | 可做但收益低 | 提高门槛，不改变“可被破”的事实 |
| 纯本地 license 文件/注册码 | **等于白送** | 一个 keygen 或补丁即失效 |

**结论**：不要把 D 加密当成商业模式。它解决的是“发行首周的收入保护”，不是“长期授权”。我们的体量更适合把价值放到服务端，用“账号 + 云数据 + 更新”形成留存；本地只做**轻量完整性提示**，不做重 DRM。

### 3.7 分档建议

| 档 | 做什么 | 前提 | 工作量 |
|---|---|---|---|
| **短期可做（1–2 周）** | 免费核心不变；加“赞助/爱发电”入口 + CDK 兑换云权益（先不做支付 API）；补分享码（长码）、构筑图导出、必需槽徽标、解锁面板 | 有域名/一台服务器（甚至先手工发码） | 3–7 天客户端 + 3–5 天服务端（若只做手工 CDK 可更短） |
| **中期值得做（1–3 个月）** | 账号 + 云预设同步 + 公开构筑库 + 分享短码 + CDN 更新通道 + 会员权益（云额度/发布权/去广告式体验） | 个体户或公司、备案域名、微信/支付宝或爱发电、客服与退款流程 | 4–8 周（含资质与联调） |
| **不建议做** | 本地功能收费、Denuvo 式 DRM、强制在线校验、无客服的硬件锁、售卖纯数据包 | — | — |

**最终判断**：

- **装备构筑**：值得做“产品化外壳”，不值得换数据架构。先做 3–5 天的低成本项，观察分享/传播数据再决定是否上社区。
- **登录/会员**：技术上完全可做，但**当前阶段做成“重会员”不划算**；如果要做，先做“账号 + 云同步 + 赞助码”，把收费点放在服务端价值上。等你验证有稳定付费意愿（例如有几十个愿意按月付费的用户）再上正式支付与发票体系。

---

## 4. 证据附录

### 4.1 客户端（rea）

- 目标：`resources\app.asar`，sha256 `60347702d4e325ab2f7c0b37f69360d6ed205bf3028cf0874c3b4852b564265d`
- `inspect_artifact`：36,313 entries；`extract_artifact`：node 11,582 / occurrence 12,366
- 关键文件：
  - `dist\main\background.js`：L2694 `/interactive`、L811-812 服务端/白名单、L700 cookie、L326 flush、L661 VIP、L832-839 功能授权
  - `dist\render\index.html`（启动器壳）
  - `package.json`：`1.5.8`、`electron-updater ^6.1.1`
  - `resources\app-update.yml`：generic provider `cdn.kaedeori.com/distro/tarkov`
- 复现：`rea.open_binary` → `inspect_artifact(detail=summary)` → `extract_artifact`

### 4.2 远程网页（本次实际拉取）

- `https://member.kaedeori.com/interactive` → 200，资源版本 4.13.4
- `https://cdn.kaedeori.com/assets/tarkov/static/4.13.4/main.js` → 2,975,988 B
- `https://cdn.kaedeori.com/assets/tarkov/static/4.13.4/global.js` → 550,316 B
- `https://cdn.tiltysola.com/assets/passport-v2/static/index.js` → 2,807,542 B
- 无 source map；复现检索：
  - `grep -o "/api/tarkov/[a-zA-Z0-9_/-]*" main.js`
  - `grep -n "loadoutBuilder\|equipmentBuild" main.js`
  - `grep -n "passport\|oauth\|geetest\|2fa" passport.js`

### 4.3 匿名实测接口（只读 GET）

| 接口 | 结果 |
|---|---|
| `/api/tarkov/equipmentBuild/list?scope=public&page=1&pageSize=2&lang=zh&gameMode=pvp` | 200，`total=3`，含 `shareCode/validationStatus/summary` |
| `/api/tarkov/build/detail?id=<枪>&lang=zh&gameMode=pvp` | 200，含 `slots/allowedItemIds/compatibleItems/defaultPreset` |
| `/api/tarkov/build/bases?kind=weapon&page=1&pageSize=4&lang=zh&gameMode=pvp` | 200 |
| `/api/payment/v2/good/list` | 200，`code=20028 USER_NOT_LOGIN` |
| `/api/payment/v2/meta` | 200，`alipay/wechat` 可用 |
| `/api/passport/user/profile` | 401（未登录） |

### 4.4 本项目引用

- [gun_builder.js#L66](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/gun_builder.js#L66) `buildTree`
- [gun_builder.js#L214](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/gun_builder.js#L214) `adsTimeFromErgo`
- [gun_builder.js#L242](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/gun_builder.js#L242) `compute`
- [gun_builder.js#L610](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/gun_builder.js#L610) `serialize`
- [gun_builder.js#L623](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/gun_builder.js#L623) `parse`
- [gun_builder.js#L643](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/gun_builder.js#L643) `chains`
- [gun_builder.js#L680](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/gun_builder.js#L680) `compare`
- [gun_builder.js#L1032](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/gun_builder.js#L1032) `optimize`
- [app.js#L8705](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/app.js#L8705) `ROOT_SLOTS`
- [app.js#L11317](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/app.js#L11317) `renderLwStats`
- [tools/presets.py#L49](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/tools/presets.py#L49) 本地存储路径
- [tools/presets.py#L101](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/tools/presets.py#L101) `normalize_preset`
- [tools/serve.py#L1991](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/tools/serve.py#L1991) `/api/presets`（GET；POST 在 L2075）
- [tools/serve.py#L2068](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/tools/serve.py#L2068) 无鉴权注释
- [index.html#L698](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/index.html#L698) 配装工作台
- [index.html#L706](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/index.html#L706) 预设/导入导出
- [index.html#L832](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/index.html#L832) `#gear-table`
- [index.html#L839](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/index.html#L839) 配枪工作台
- [index.html#L925](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/index.html#L925) `#gw-buildpage`
- [index.html#L1001](file:///d:/personal/trae/02-塔科夫/eft-interactive-map/index.html#L1001) `#gw-table`

### 4.5 不确定与推断边界

- **未登录**，所以没有验证：付费套餐实际价格、支付回调、订单退款、后台管理；这些只从代码/i18n/接口存在性确认。
- 未做真实 UI 点击（没有账号），流程来自路由与组件代码 + 匿名公开页数据；标注为“静态推断”的段落不做运行期保证。
- 公开构筑数量（3 条）是本次探测时的快照，会变化。
- `gameMode` 取值实测 `pvp` 有效；`pve` 数据未逐条核对（接口接受 `gameMode` 参数，前端有 PvP/PvE 切换）。
- 远程 bundle 会随版本更新；本结论绑定 `4.13.4` 与客户端 `1.5.8`。

### 4.6 网络与代理说明

- 本次访问全程走本机代理（响应头 `HTTP/1.1 200 Connection established`），目标站点实际 200。
- 未关闭 TLS 校验，未使用“配置了代理就算成功”的判定；以上接口均为实际抓取到响应体。
- 本地临时产物（解包目录、下载的 bundle）只用于分析，未写入项目源码目录。

---

## 5. 证据一致性复核（2026-11-08 03:48，MASTERJJ@HOMONAS，只读复核）

对本文档全部本项目源码引用（§2.4、§4.4 共 21 处行号）逐条对照当前工作区源码实读复核，**全部命中，无漂移**：

| 引用 | 复核结果 |
|---|---|
| app.js L7517 `ROOT_SLOTS` / L9949 `renderLwStats` / L10004 子槽注释 | ✅ 命中；L7517 实读确认 11 根槽（头盔/耳机/眼镜/护面/护甲/胸挂/背包/主武器1/主武器2/手枪/近战），与 §2.4 表一致 |
| gun_builder.js L66 `buildTree` / L214 `adsTimeFromErgo` / L242 `compute` / L607 `serialize` / L620 `parse` / L640 `chains` / L677 `compare` / L1029 `optimize` | ✅ 全部命中 |
| tools/presets.py L49 `store_path` / L101 `normalize_preset` | ✅ 命中 |
| tools/serve.py L1704 `/api/presets` / L1744 无鉴权注释 | ✅ 命中；L1744 原文「本地单机服务不做鉴权」与 §3.3 描述一致 |
| index.html L531 配装工作台 / L540 预设导入导出 / L667 `#gear-table` / L674 配枪工作台 / L798 `#gw-buildpage` / L874 `#gw-table` | ✅ 全部命中 |

复核范围说明：仅核对**本项目侧**引用与行号一致性；Kaedeori 侧证据（§4.1–4.3）绑定其客户端 `1.5.8` 与 bundle `4.13.4`，属外部快照，不在本次复核范围内。源码文件最近修改时间均早于本文档交付时间（app.js/index.html 2026-11-07 23:44，gun_builder.js 17:40，文档 2026-11-08 00:02），无文档后改动导致的行号漂移。复核方式：PowerShell 按行号实读比对，只读，未改动任何源码。

## 6. 证据一致性复核·二（2026-11-09 00:03–00:07，MASTERJJ@HOMONAS，只读快照）

§5 的"无漂移"结论基于 2026-11-08 03:48 的源码状态。此后 R19 系列改动重写了 `app.js` / `index.html` / `tools/serve.py`，行号已发生位移。本轮按 §4.4 的 21 条引用逐行实读，结果如下。

**未漂移（10 条，仍命中）**

| 文件 | 引用 | 依据 |
|---|---|---|
| `gun_builder.js` | L66 `buildTree`、L214 `adsTimeFromErgo`、L242 `compute`、L607 `serialize`、L620 `parse`、L640 `chains`、L677 `compare`、L1029 `optimize` | 文件自 2026-11-07 17:40 起未变，8 条全部命中 |
| `tools/presets.py` | L49 `store_path`、L101 `normalize_preset` | 文件自 2026-10-20 22:03 起未变，2 条全部命中 |

**已漂移（快照行号，符号语义不变）**

| 引用 | §5 行号 | 本轮快照行号 |
|---|---|---|
| `app.js` `ROOT_SLOTS` | 7517 | **7582** |
| `app.js` `renderLwStats` | 9949 | **10016** |
| `app.js` 子槽条注释 | 10004 | **8021–8023** |
| `index.html` 配装工作台 | 531 | **560** |
| `index.html` 预设导入/导出按钮 | 540 | **569** |
| `index.html` `#gear-table` | 667 | **696** |
| `index.html` 配枪工作台 | 674 | **703** |
| `index.html` `#gw-buildpage` | 798 | **827** |
| `index.html` `#gw-table` | 874 | **903** |
| `tools/serve.py` `/api/presets` | 1704 | **1368 / 1417**（快照，仍在变动） |
| `tools/serve.py` 无鉴权注释 | 1744 | **约 1405**（快照，仍在变动） |

**处理决策（按最稳妥方案）**：本工作树正处于 R19 活跃并行写入状态——复核期间 `tools/serve.py` 仍在被改写（mtime 00:04:55 → 00:05:30，`/api/presets` 行号从 1366 移到 1368），`app.js` / `index.html` 也已较 §5 时点重写。为避免与并行会话抢写，本轮**不回填**正文 §2.4 / §4.4 的链接，只在本文记录快照；待该会话收尾、三个文件停止变动后统一回填并复跑本节核对。当前判断：所有引用指向的符号仍然存在且语义一致，属**行号位移，不是结论漂移**。

- 机器 / 时间：`MASTERJJ@HOMONAS`，2026-11-09 00:03–00:07，只读。
- 快照文件 mtime：`app.js` 2026-11-08 23:59:36、`index.html` 23:59:35、`serve.py` 2026-11-09 00:05:30。
- 改动范围：仅本文件（追加本节），未改动任何源码。

## 7. 证据一致性复核·三：漂移已回填（2026-11-09 01:05–01:09，MASTERJJ@HOMONAS，只读复核 + 仅改本文件）

§6 记录 11 条引用行号漂移并决定「等源码停改后再回填」。本轮判定停改条件已满足，回填完成。

### 7.1 停改判定依据（实测 mtime）

| 文件 | mtime | 距本轮复核 | 结果 |
|---|---|---|---|
| `app.js` | 2026-11-09 00:11:40 | ≥ 60 分钟未变 | 视为稳定 |
| `index.html` | 2026-11-09 00:11:39 | ≥ 60 分钟未变 | 视为稳定 |
| `tools/serve.py` | 2026-11-09 00:15:24 | ≥ 55 分钟未变 | 视为稳定 |
| `gun_builder.js` / `tools/presets.py` | 2026-11-07 17:40 / 2026-10-20 22:03 | 未变 | 稳定 |

旁证：该工作树 00:22–00:23 有一轮数据重生成与 pytest 运行（`.pytest_cache`、`data/i18n/*`、`docs/r19.*/*.json` 同批更新），此后四个引用文件无写入，符合「一轮收尾后停写」。

### 7.2 回填结果（§2.4 表与 §4.4 引用清单同步更新）

| 引用 | 旧 | 回填后 | 实读依据 |
|---|---|---|---|
| `app.js` `ROOT_SLOTS` | 7517 | **7582** | `var ROOT_SLOTS = [`，11 根槽 |
| `app.js` `renderLwStats` | 9949 | **10016** | `function renderLwStats() {` |
| `app.js` 子槽条注释 | 10004 | **8021–8023** | 「卡片板是 CSS grid…每张卡片后面紧跟它自己的子槽条」 |
| `index.html` 配装工作台 | 531 | **560** | `<section id="loadout-view" … aria-label="配装工作台">` |
| `index.html` 预设/导入导出 | 540 | **568**（起始行；569 为同一 `<button>` 的 `title=` 续行） | `<button … class="lw-preset" id="lw-preset"` |
| `index.html` `#gear-table` | 667 | **696** | `<div id="gear-table" class="lw-table">` |
| `index.html` 配枪工作台 | 674 | **703** | `<section id="gun-view" … aria-label="配枪工作台">` |
| `index.html` `#gw-buildpage` | 798 | **827** | `<section id="gw-buildpage" …>`（798 现为 `#gw-tablepage`，注意勿混） |
| `index.html` `#gw-table` | 874 | **903** | `<div id="gw-table" class="lw-table">` |
| `tools/serve.py` `/api/presets` | 1704 | **1368**（GET）/ **1417**（POST） | 两处 `if path == "/api/presets":` |
| `tools/serve.py` 无鉴权注释 | 1744 | **1410** | `do_POST` docstring 内「`/api/prefs` 只写本机配置（无鉴权…」 |

未漂移 10 条（`gun_builder.js` 8 条、`tools/presets.py` 2 条）本轮抽检仍命中，未改动。

### 7.3 复核结论

- 21 条本项目侧引用现已**全部可跳到当前源码的正确行**；文档结论（槽位 11 根、本地 JSON 无鉴权、导入导出缺口）无一条因行号位移而改变。
- Kaedeori 侧证据（§4.1–4.3）仍绑定其客户端 `1.5.8` / bundle `4.13.4` 快照，不属行号复核范围，结论维持 §4.5 的不确定边界。
- 留痕：机器 `MASTERJJ@HOMONAS`，2026-11-09 01:05–01:09；仅改本文件，未动源码与数据；若源码再次重写导致漂移，按 §6 同样方式记录快照，不静默改数。

## 8. 证据一致性复核·四：21 条引用逐条复读，修正 1 处 1 行偏移（2026-11-09 06:35–06:50，MASTERJJ@HOMONAS，只读复核 + 仅改本文件）

§7 的「全部可跳到正确行」是在 01:09 判定的；此后该工作树又跑了多轮 UI 收尾（handoff 记录到 R29.3）。本轮先确认源码是否再次变动，再把 21 条引用逐条按行实读，避免结论随时间失效。

### 8.1 前置：源码停改确认（实测 mtime）

| 文件 | mtime | 与 §7 判定时（00:11–00:15）相比 |
|---|---|---|
| `app.js` | 2026-11-09 00:11:40 | 未变 |
| `index.html` | 2026-11-09 00:11:39 | 未变 |
| `tools/serve.py` | 2026-11-09 00:15:24 | 未变 |
| `gun_builder.js` | 2026-11-07 17:40:33 | 未变 |
| `tools/presets.py` | 2026-10-20 23:03:05 | 未变 |
| `style.css`（非引用文件，旁证） | 2026-11-08 23:01:18 | 未变 |

结论：§7 回填后源码未再改动（≥6 小时），本轮复读的是同一份代码，因此「漂移」类风险为零，本轮只校正 §7 自身的行号精度问题。

### 8.2 逐条复读结果（PowerShell 按行号实读，21 条）

| 引用 | 文档行号 | 实读到的内容 | 结果 |
|---|---|---|---|
| `app.js` `ROOT_SLOTS` | 7582 | `var ROOT_SLOTS = [` | ✅ |
| `app.js` `renderLwStats` | 10016 | `function renderLwStats() {` | ✅ |
| `app.js` 子槽条注释 | 8021–8023 | 「卡片板是 CSS grid…每张卡片后面紧跟它自己的子槽条」 | ✅ |
| `index.html` 配装工作台 | 560 | `<section id="loadout-view" … aria-label="配装工作台">` | ✅ |
| `index.html` 预设/导入导出 | 568（569 为续行） | `<button … class="lw-preset" id="lw-preset"` | ⚠️ 已修正（原记 569） |
| `index.html` `#gear-table` | 696 | `<div id="gear-table" class="lw-table">` | ✅ |
| `index.html` 配枪工作台 | 703 | `<section id="gun-view" … aria-label="配枪工作台">` | ✅ |
| `index.html` `#gw-buildpage` | 827 | `<section id="gw-buildpage" …>` | ✅ |
| `index.html` `#gw-table` | 903 | `<div id="gw-table" class="lw-table">` | ✅ |
| `tools/serve.py` `/api/presets` | 1368（GET）/ 1417（POST） | 两处 `if path == "/api/presets":` | ✅ |
| `tools/serve.py` 无鉴权注释 | 1410 | do_POST docstring「`/api/prefs` 只写本机配置（无鉴权…」 | ✅ |
| `gun_builder.js` `buildTree` | 66 | `function buildTree(ctx, gunId, installed) {` | ✅ |
| `gun_builder.js` `adsTimeFromErgo` | 214 | `function adsTimeFromErgo(ergo) {` | ✅ |
| `gun_builder.js` `compute` | 242 | `function compute(ctx, gunId, installed, opts) {` | ✅ |
| `gun_builder.js` `serialize` | 607 | `function serialize(gunId, installed, meta) {` | ✅ |
| `gun_builder.js` `parse` | 620 | `function parse(text) {` | ✅ |
| `gun_builder.js` `chains` | 640 | `function chains(ctx, gunId, installed, opts) {` | ✅ |
| `gun_builder.js` `compare` | 677 | `function compare(a, b) {` | ✅ |
| `gun_builder.js` `optimize` | 1029 | `function optimize(ctx, gunId, installed, opts) {` | ✅ |
| `tools/presets.py` `store_path` | 49 | `def store_path(kind: str, directory: str \| None = None) -> str:` | ✅ |
| `tools/presets.py` `normalize_preset` | 101 | `def normalize_preset(kind: str, raw: Any) -> dict:` | ✅ |

### 8.3 本轮修正与结论

- **唯一改动**：`index.html` 预设/导入导出由 `#L569` 精确为 `#L568`。原因：该 `<button>` 是两行标签，`id="lw-preset"` 在第 568 行，第 569 行只是 `title=` 续行；按锚点跳到 569 仍落在同一元素内，不影响阅读，但不符合本文「跳到正确行」的自定标准。正文 §2.4（第 147 行）与 §4.4（第 395 行）两处 anchor 已同步为 `#L568`，§7.2 表格已注明续行关系。
- **其余 20 条**与 §7 一致，无结论漂移：槽位 11 根、`/api/presets` 无鉴权、导入导出缺口三条核心结论均不受影响。
- Kaedeori 侧（§4.1–4.3）仍绑定其客户端 `1.5.8` / bundle `4.13.4` 外部快照，本机无该客户端二进制，**无法现场复验**，结论维持 §4.5 的不确定边界（这是本线唯一的硬边界）。
- 复核方式与边界：只读实读源码，未运行服务、未改源码与数据；改动范围仅本文件。机器 `MASTERJJ@HOMONAS`，2026-11-09 06:35–06:50。

## 9. 证据一致性复核·五：R19–R246 重写后再次漂移，21 条符号全在、仅行号位移（2026-11-11 23:05–23:09，文件 mtime 23:08:59，MASTERJJ@HOMONAS，只读复核 + 仅改本文件）

§8 判定时定格在 2026-11-09 00:11–00:15 的源码快照。此后该工作树连续跑了 R19–R246（`app.js` / `index.html` / `tools/serve.py` 均在 2026-11-11 22:18 被整体重写），§8 的行号已再次失效。本轮按 §4.4 的 21 条引用逐条重新定位。

### 9.1 前置：源码仍在活跃写入

| 文件 | 当前 mtime | 本轮判定 |
|---|---|---|
| `app.js` | 2026-11-11 22:18:24（1,304,336 B） | 仍在变动 |
| `index.html` | 2026-11-11 22:18:30（83,482 B） | 仍在变动 |
| `tools/serve.py` | 2026-11-11 22:18:44（125,859 B） | 仍在变动 |
| `gun_builder.js` | 2026-11-11 22:18:28（69,323 B） | 仍在变动 |
| `tools/presets.py` | 2026-10-20 23:03:05（10,291 B） | 未变 |

旁证：该工作树的截图识别宿主 22:42:26 重启（pid=21720、热键注册成功），R246 刚收尾，会话仍在推进。因此本轮**沿用 §6 的处理决策：只记快照，不回填正文链接**，避免与并行会话抢写后又立刻失效。

### 9.2 逐条重新定位（21 条）

| 引用 | §8 行号 | 本轮实测行号 | 实读内容 | 结果 |
|---|---|---|---|---|
| `app.js` `ROOT_SLOTS` | 7582 | **8074** | `var ROOT_SLOTS = [`，仍为 11 根槽 | ✅ 语义不变 |
| `app.js` `renderLwStats` | 10016 | **10610** | `function renderLwStats()` | ✅ |
| `app.js` 子槽条注释 | 8021–8023 | **8512–8514** | 「卡片板是 CSS grid…每张卡片后面紧跟它自己的子槽条」 | ✅ |
| `index.html` 配装工作台 | 560 | **657** | `<section id="loadout-view" … aria-label="配装工作台">` | ✅ |
| `index.html` 预设/导入导出 | 568 | **665** | `<button … class="lw-preset" id="lw-preset"`（仍是两行标签，`title=` 在 666） | ✅ |
| `index.html` `#gear-table` | 696 | **794** | `<div id="gear-table" class="lw-table">` | ✅ |
| `index.html` 配枪工作台 | 703 | **801** | `<section id="gun-view" … aria-label="配枪工作台">` | ✅ |
| `index.html` `#gw-buildpage` | 827 | **925** | `<section id="gw-buildpage" … aria-label="枪械装配工作台">` | ✅ |
| `index.html` `#gw-table` | 903 | **1001** | `<div id="gw-table" class="lw-table">` | ✅ |
| `tools/serve.py` `/api/presets` | 1368 / 1417 | **1516（GET）/ 1573（POST）** | 两处 `if path == "/api/presets":` | ✅ |
| `tools/serve.py` 无鉴权注释 | 1410 | **1566** | 「`/api/prefs` 只写本机配置（无鉴权，限制在 MAX_PREFS_BODY）；」 | ✅ 原文未改 |
| `gun_builder.js` `buildTree` | 66 | **66** | 未漂移 | ✅ |
| `gun_builder.js` `adsTimeFromErgo` | 214 | **214** | 未漂移 | ✅ |
| `gun_builder.js` `compute` | 242 | **242** | 未漂移 | ✅ |
| `gun_builder.js` `serialize` | 607 | **610** | `function serialize(...)` | ✅ |
| `gun_builder.js` `parse` | 620 | **623** | `function parse(...)` | ✅ |
| `gun_builder.js` `chains` | 640 | **643** | `function chains(...)` | ✅ |
| `gun_builder.js` `compare` | 677 | **680** | `function compare(...)` | ✅ |
| `gun_builder.js` `optimize` | 1029 | **1032** | `function optimize(...)` | ✅ |
| `tools/presets.py` `store_path` | 49 | **49** | 文件未变 | ✅ |
| `tools/presets.py` `normalize_preset` | 101 | **101** | 文件未变 | ✅ |

### 9.3 结论

- **21 条符号全部仍然存在**，无一条被删除、改名或迁移到别的文件；差异只有行号位移（`app.js` +492/+594，`index.html` +97/+98，`serve.py` +148/+156，`gun_builder.js` +3）。
- 三条核心结论均不受影响：槽位仍是 11 根（头盔/耳机/眼镜/护面/护甲/胸挂/背包/主武器 1/主武器 2/手枪/近战）；`/api/presets` 仍是本机 JSON 读写且 `do_POST` 明确写着无鉴权；导入/导出缺口仍在。
- **未回填**正文 §2.4 / §4.4 的 anchor：源码自 22:18 起仍在被 R246 之后的改动写入，回填即失效。等该线停写（连续 ≥60 分钟无写入）后按 §7 方式一次性回填并复跑本节。（2026-11-11 23:36 条件已满足，回填完成，见 §10）
- Kaedeori 侧（§4.1–4.3）无变化：仍绑定客户端 `1.5.8` / bundle `4.13.4` 外部快照，本机无该二进制，无法现场复验——这是本线唯一硬边界。
- 留痕：机器 `MASTERJJ@HOMONAS`，2026-11-11 23:05–23:09（文件 mtime 23:08:59，原记 23:10–23:35 系预估窗口，本轮按实际时间校正）；只读实读源码，未改源码/数据，改动范围仅本文件；复核方式为 `Select-String` 按符号定位 + 按行号实读比对。

## 10. 正文 anchor 回填完成：21 处改为当前行号（2026-11-11 23:33–23:39，MASTERJJ@HOMONAS，只读复读 + 仅改本文件）

### 10.1 触发条件达成

§9.3 设定的回填条件是「源码连续 ≥60 分钟无写入」。本轮 23:36 实测：

| 文件 | mtime（实测） | 距回填时 |
|---|---|---|
| `app.js` | 2026-11-11 22:18:24 | 78 分钟无写入 |
| `index.html` | 2026-11-11 22:18:30 | 78 分钟 |
| `tools/serve.py` | 2026-11-11 22:18:44 | 78 分钟 |
| `gun_builder.js` | 2026-11-11 22:18:28 | 78 分钟 |
| `combat_sim.js` | 2026-11-11 22:18:26 | 78 分钟 |

服务侧旁证：`http://127.0.0.1:8080/` 实测 **HTTP 200**（返回 24,291 B），即服务在跑但未改写源码。条件满足，按 §7 方式一次性回填。

### 10.2 回填内容（21 处）

回填前逐条用 `Get-Content` 按目标行号实读，确认「行号 → 内容」匹配后才改，不以 §9.2 表格为准直接抄录：

| 引用 | 旧行号 | 新行号 | 实读确认 |
|---|---|---|---|
| `app.js` `ROOT_SLOTS` | 7582 | **8074** | `var ROOT_SLOTS = [` |
| `app.js` `renderLwStats` | 10016 | **10610** | `function renderLwStats() {` |
| `app.js` 子槽条注释 | 8021–8023 | **8512–8514** | 「卡片板是 CSS grid…每张卡片后面紧跟它自己的子槽条」 |
| `index.html` 配装工作台 | 560 | **657** | `<section id="loadout-view" … aria-label="配装工作台">` |
| `index.html` 预设/导入导出 | 568 | **665** | `<button … id="lw-preset"` |
| `index.html` `#gear-table` | 696 | **794** | `<div id="gear-table" class="lw-table">` |
| `index.html` 配枪工作台 | 703 | **801** | `<section id="gun-view" … aria-label="配枪工作台">` |
| `index.html` `#gw-buildpage` | 827 | **925** | `<section id="gw-buildpage" … aria-label="枪械装配工作台">` |
| `index.html` `#gw-table` | 903 | **1001** | `<div id="gw-table" class="lw-table">` |
| `tools/serve.py` `/api/presets` | 1368 | **1516**（GET） | `if path == "/api/presets":`；POST 在 1573 |
| `tools/serve.py` 无鉴权注释 | 1410 | **1566** | 「`/api/prefs` 只写本机配置（无鉴权，限制在 MAX_PREFS_BODY）；」 |
| `gun_builder.js` `buildTree` | 66 | 66 | 未漂移 |
| `gun_builder.js` `adsTimeFromErgo` | 214 | 214 | 未漂移 |
| `gun_builder.js` `compute` | 242 | 242 | 未漂移 |
| `gun_builder.js` `serialize` | 607 | **610** | `function serialize(gunId, installed, meta) {` |
| `gun_builder.js` `parse` | 620 | **623** | `function parse(text) {` |
| `gun_builder.js` `chains` | 640 | **643** | `function chains(ctx, gunId, installed, opts) {` |
| `gun_builder.js` `compare` | 677 | **680** | `function compare(a, b) {` |
| `gun_builder.js` `optimize` | 1029 | **1032** | `function optimize(ctx, gunId, installed, opts) {` |
| `tools/presets.py` `store_path` | 49 | 49 | 未漂移 |
| `tools/presets.py` `normalize_preset` | 101 | 101 | 未漂移 |

改动落点：§2.4 表 9 处、§3.3 一处（无鉴权注释）、§4.4 清单 11 处，共 21 处 anchor。

### 10.3 复核与边界

- 21/21 命中，语义与 §8 一致，三条核心结论（11 根槽位 / `/api/presets` 无鉴权 / 导入导出缺口）未变。
- §5–§9 历史章节中的旧行号**保持原样**：它们记录的是当轮快照，改写会破坏留痕；本次只回填正文。
- 若该线再次整体重写，本节 anchor 仍会失效；判定阈值不变（连续 ≥60 分钟无写入再回填）。
- Kaedeori 侧仍无变化：绑定客户端 `1.5.8` / bundle `4.13.4` 外部快照，本机无该二进制，无法现场复验。

### 10.4 留痕

- 机器/时间：`MASTERJJ@HOMONAS`，2026-11-11 23:33–23:39。
- 只读对象：`app.js`、`index.html`、`tools/serve.py`、`gun_builder.js`、`tools/presets.py`。
- 违规检查：未改源码、未改数据、未重启服务、未写项目目录以外文件；改动范围仅本文件（anchor 行号 + 本节日志）。

## 11. 二次 anchor 回填：源码今日整体重写，10 处漂移（2026-11-15 22:10–22:20，MASTERJJ@HOMONAS，只读复读 + 仅改本文件）

### 11.1 触发情况

塔科夫线今日整体重写，§10.2 的 anchor 再次失效。实测 mtime（2026-11-15 22:10）：

| 文件 | mtime（实测） | 距回填时 |
|---|---|---|
| `app.js` | 2026-11-15 17:02:59 | 约 5 小时 7 分 |
| `index.html` | 2026-11-15 16:59:21 | 约 5 小时 11 分 |
| `tools/serve.py` | 2026-11-15 21:26:39 | **53 分钟** |
| `gun_builder.js` | 2026-11-12 12:12:46 | 3 天 |
| `tools/presets.py` | 2026-10-20 23:03:05 | 未变动 |

`serve.py` 的 53 分钟**低于** §10.3 的 60 分钟阈值，本次仍执行回填，理由是：该次写入属 0.2.7.7 构建配套改动（`release/` 三件套 21:49 落盘，构建已结束），且回填前后各复读一次 mtime 未变。**若夜间该文件再次写入，本节同样失效，需按同一阈值重做。**

### 11.2 回填内容（10 处漂移，11 处未漂移）

| 引用 | §10.2 值 | 本次实测 | 实读确认 |
|---|---|---|---|
| `app.js` `ROOT_SLOTS` | 8074 | **8705** | `var ROOT_SLOTS = [` |
| `app.js` `renderLwStats` | 10610 | **11317** | `function renderLwStats() {` |
| `app.js` 子槽条注释 | 8512–8514 | **9143–9145** | 「卡片板是 CSS grid（7 条轨道…」起，含「每张卡片后面紧跟它自己的子槽条」 |
| `index.html` 配装工作台 | 657 | **698** | `<section id="loadout-view"` |
| `index.html` 预设/导入导出 | 665 | **706** | `id="lw-preset"` |
| `index.html` `#gear-table` | 794 | **832** | `<div id="gear-table"` |
| `index.html` 配枪工作台 | 801 | **839** | `<section id="gun-view"` |
| `tools/serve.py` `/api/presets` GET | 1516 | **1991** | `if path == "/api/presets":` → `_handle_presets_get` |
| `tools/serve.py` `/api/presets` POST | 1573 | **2075** | `if path == "/api/presets":` → `_handle_presets_post` |
| `tools/serve.py` 无鉴权注释 | 1566 | **2068** | 「`/api/prefs` 只写本机配置（无鉴权，限制在 MAX_PREFS_BODY）；」 |

未漂移（复读命中，不改）：`index.html` `#gw-buildpage` 925、`#gw-table` 1001；`gun_builder.js` 66/214/242/610/623/643/680/1032 共 8 处；`tools/presets.py` 49/101 共 2 处。

### 11.3 结论与边界

- 三条核心结论**未变**：11 根槽位（`ROOT_SLOTS`）、`/api/presets` 无鉴权、导入/导出仍是本地文件而非 12 位码。
- 只改本文件正文：§2.4（4 处）、§3.3（1 处）、§4.4（5 处）；§5–§10 历史章节保留当轮行号，不改写。
- 未改源码、未改数据、未重启服务；服务侧旁证：今日 8787 端口服务正常（构建产物 `0.2.7.7`，21:49 落盘）。
- 遗留不变：Kaedeori 外部客户端 `1.5.8` / bundle `4.13.4` 仍无二进制，本机无法复验。

### 11.4 留痕

- 机器/时间：`MASTERJJ@HOMONAS`，2026-11-15 22:10–22:20（文件 mtime 22:20）。
- 只读对象：`app.js`、`index.html`、`tools/serve.py`、`gun_builder.js`、`tools/presets.py`（按 §10.2 的 pattern 逐条 `Select-String` 定位 + 按行号实读比对，未以旧表直接抄录）。
- 改动范围：本文件 §2.4 / §3.3 / §4.4 anchor 行号 + 新增 §11。
