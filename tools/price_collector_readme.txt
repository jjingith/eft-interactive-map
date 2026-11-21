EFT 跳蚤价格采集器（独立版）

这是一个独立程序：自带 Python 运行时，目标机器不需要安装 Python，
也不需要安装 EFTMap 客户端。

一、文件
  EFTPriceCollector.exe   主程序
  install.bat             安装（注册计划任务）
  uninstall.bat           卸载（删除计划任务与自启项）
  README.txt              本文件

二、安装
  双击 install.bat，或用管理员以外的普通账户打开命令行执行：
      EFTPriceCollector.exe --install
  安装会注册计划任务 EFTPriceCollector：每 30 分钟运行一次
      EFTPriceCollector.exe --once --mode all
  设置：错过触发后补跑（StartWhenAvailable）、多实例忽略（IgnoreNew）、
  允许电池、执行时限 30 分钟。旧的 EFTMap-PriceCollector（pythonw）任务会被删除。

三、卸载
  双击 uninstall.bat。默认只删除计划任务与 HKCU\...\Run 自启项，保留数据；
  按提示输入 y 可连同数据目录一起删除。
  命令行等价：
      EFTPriceCollector.exe --uninstall
      EFTPriceCollector.exe --uninstall --purge

四、数据目录
  %LOCALAPPDATA%\EFTPrice\collect\   采集产物
      raw\        上游原始载荷，每个模式滚动保留 48 份
      snapshots\  精简快照（每 30 分钟），按日期保留 90 天
      daily\      按天锚点（含 lo/hi/b），保留 90 天
      state.json / index.json / heartbeat.json / last-error.json
  %LOCALAPPDATA%\EFTPrice\cache\     运行期缓存 live-prices-{regular,pve}.json

  如果机器上以前用过客户端采集（%LOCALAPPDATA%\EFTMap\price-collect），
  首次运行或安装时会整体搬进 %LOCALAPPDATA%\EFTPrice\collect，并写
  MIGRATION.json 记录来源；搬完旧目录会被删除，不会两套同时写。
  若客户端缓存目录 %LOCALAPPDATA%\EFTMap\cache 存在，程序会在写完后额外
  镜像一份运行期缓存（只写不读，失败不影响采集）；可用 --no-mirror 关闭。

五、查看状态
  双击 EFTPriceCollector.exe（不带参数）能看到人话状态：
  上次运行时间与耗时、本次抓取条数与是否 304、下次计划时间、最近一次错误。
  也可以：
      EFTPriceCollector.exe --status
      EFTPriceCollector.exe --status --json
      EFTPriceCollector.exe --task-status

六、手动抓一轮
      EFTPriceCollector.exe --once
      EFTPriceCollector.exe --once --mode pve
      EFTPriceCollector.exe --once --force        (忽略 20 分钟最小间隔)

七、网络
  默认走本机代理 http://127.0.0.1:7896；没有代理时加 --no-proxy 直连。
  上游 json.tarkov.dev 约 10 分钟更新一版，程序用 ETag 条件请求，
  未变更时返回 304，不重复落盘。

八、质量与保留
  少于 1000 件或少于 500 条有效价格判为失败，失败只记录原因，
  不覆盖已有快照；写盘为临时文件 + 原子替换；同一时刻只允许一个实例抓取。
