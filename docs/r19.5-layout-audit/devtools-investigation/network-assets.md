# 参考站网络资源（network-assets.md）

- 资源总数（performance entries）：**180**
- 分类计数：`{"early-hints": 1, "script": 14, "link": 1, "fetch": 48, "img": 108, "xmlhttprequest": 5, "other": 2, "iframe": 1}`

## 关键脚本

- `[`
- `"`
- `h`
- `t`
- `t`
- `p`

## 其它发现

- 无独立 CSS 文件（样式全部编译进 `main.dart.js`；Flutter 用 CanvasKit 绘制）。
- 数据由同一个 Dart 包内联加载，未见公开 REST/GraphQL 接口请求（`byType` 中无 xhr/fetch 条目）。
- **运行期**：参考站资源仅在构建/调查期通过代理加载；本地项目运行期仍完全离线
  （每次浏览器验收均为 0 外部请求）。
