# mrcon — MC 综合管理插件

[![GitHub](https://img.shields.io/badge/GitHub-rogergzl%2Fastrbot__plugin__mrconop-blue?logo=github)](https://github.com/rogergzl/astrbot_plugin_mrconop)
![Version](https://img.shields.io/badge/version-v3.47.0-green)
![Author](https://img.shields.io/badge/author-lindagao-orange)

> **作者**: [lindagao](https://github.com/rogergzl) · **仓库**: [astrbot_plugin_mrconop](https://github.com/rogergzl/astrbot_plugin_mrconop)

RCON 命令转发 + 服务器并发查询 + SQLite/MySQL 双引擎玩家数据库 + 在线追踪 + 签到 + 补偿 + 积分兑换 + 抽奖 + 群服消息互联（RCON tellraw + 日志监听）

## 安装

本目录作为 AstrBot 插件加载。依赖 `mcstatus`（首次运行自动安装）。

> 手动安装：
> ```
> pip install mcstatus Pillow
> ```
> `Pillow` 可选，安装后「在线列表渲染为图片」功能可用，`/rchelp` 为纯文本返回。

## 架构

```
mrcon/
├── main.py           # 插件入口（命令路由 + 业务逻辑）
├── database.py       # SQLite 数据层（玩家/会话/补偿）
├── transport.py      # RCON 协议传输层
├── web_panel.py      # Web 管理面板（原生 asyncio TCP，无外部依赖）
├── _conf_schema.json # 配置 Schema
├── metadata.yaml     # 元数据
```

**数据文件**（自动创建于 `data/plugin_data/mrcon/`）：

| 文件 | 类型 | 说明 |
|------|------|------|
| `mrcon.db` | SQLite | 玩家绑定、签到积分、在线会话记录、补偿申请、抽奖数据 |
| `audit.log` | JSONL | RCON 审计日志 |
| `mcserv_{群号}.json` | JSON | 分群 MC 服务器列表 |
| `scripts/` | 目录 | Python 脚本文件 |
| `quick_cmd_settings.json` | JSON | 快捷命令开关状态 |
| `script_settings.json` | JSON | 脚本开关状态 |

## 全部命令速查

### MC 查询

| 命令 | 别名 | 权限 | 说明 |
|------|------|------|------|
| `/mc` | `/查询` | 全员 | 查询所有服务器状态（含在线玩家） |
| `/mcget <名>` | `/服详情` | 全员 | 单个服务器详情 |
| `/mclist` | `/服列表` | 全员 | 列出本群所有服务器 |
| `/mcset <项> 1\|0` | `/查询设置` | 管理员 | 设置查询显示项 |
| `/在线时长 [服名\|玩家名]` | `/onlinetime` | 全员 | 在线时长排行（默认本群） |
| `/在线提醒` | — | 管理员 | 查看/配置本群在线提醒与踢出 |

### 服务器管理

| 命令 | 别名 | 权限 | 说明 |
|------|------|------|------|
| `/mcadd <名> <IP:端口>` | `/加服` | 管理员 | 添加 MC 服务器 |
| `/mcdel <名>` | `/删服` | 管理员 | 删除服务器 |
| `/mcup <名> [新名] [新址]` | `/改服` | 管理员 | 更新服务器 |
| `/mcshare <名> <目标群>` | `/共享服` | 超管 | 共享服务器到其他群 |
| `/mcunshare <名> <目标群>` | `/取消共享` | 超管 | 取消共享 |
| `/mccleanup` | `/清理服` | 管理员 | 清理失效服务器 |

### RCON 命令

| 命令 | 别名 | 权限 | 说明 |
|------|------|------|------|
| `/mrcon <命令>` | `/执行` `/mcmd` | 白名单 | 转发命令到 MC 服务器 |
| `/选服 <编号>` | `/rcsel` | 白名单 | 选择 RCON 目标服务器 |
| `/宏 <名称> [参数]` | `/rcmacro` | 白名单 | 执行预设宏（支持开关） |
| `/脚本 <文件名>` | `/rcscript` | 白名单 | 执行脚本文件（支持开关） |
| `/rc赞同` `/rc反对` | — | 全员 | 投票 |
| `/rc通过` `/rc否决` | — | 管理员 | 裁决 |

### 玩家功能

| 命令 | 别名 | 权限 | 说明 |
|------|------|------|------|
| `/绑定 <MC_ID>` | `/bind` | 全员 | 绑定 MC 账号（新玩家注册） |
| `/签到` | `/checkin` | 全员 | 每日签到（需先绑定） |
| `/我的` | `/mystats` | 全员 | 查看个人积分/签到/绑定信息 |
| `/理赔 <RCON命令>` | `/赔` `/comp` | 全局/白名单 | 申请物品补偿（开=全局 \| 关=仅白名单） |
| `/理赔列表` | `/赔单` | 管理员 | 查看待审批补偿申请 |
| `/同意理赔 <ID>` | `/comp_approve` | 管理员 | 批准并自动执行 RCON |
| `/拒绝理赔 <ID>` | `/comp_reject` | 管理员 | 拒绝申请 |

### 积分 & 抽奖

| 命令 | 别名 | 权限 | 说明 |
|------|------|------|------|
| `/兑换列表` | `/shop` | 全员 | 查看可用兑换项 |
| `/兑换 <编号>` | `/ex` `/buy` | 全员 | 积分兑换物品 |
| `/抽奖` | `/lottery` | 全员 | 消耗积分抽取奖品 |
| `/奖品列表` | `/prizes` | 全员 | 查看当前群奖品池 |
| `/兑奖 <编号>` | `/claim` | 全员 | 兑换中奖奖品 |
| `/我的中奖` | `/mywins` | 全员 | 查看我的中奖记录 |

### 群服互联

| 命令 | 别名 | 权限 | 说明 |
|------|------|------|------|
| `/msay <消息>` | `/群说` `/服说` | 全员 | 发送消息到 MC 公屏 |
| `/消息互通` | `/relay` | 管理员 | 查看/配置本群消息互通 |
| `/消息互通 开\|关` | — | 管理员 | 开关互通 |
| `/消息互通 模式 off\|global\|custom` | — | 管理员 | 设置模式（不互通/全局/独立） |
| `/消息互通 群到服\|服到群 开\|关` | — | 管理员 | 独立配置转发方向 |
| `/消息互通 服 <名称>` | — | 管理员 | 指定目标服务器 |
| `/消息互通 格式 <文本>` | — | 管理员 | 自定义转发格式 `{name}/{msg}` |
| `/消息互通 重置` | — | 管理员 | 恢复默认 |

### 日志事件与宏

| 命令 | 别名 | 权限 | 说明 |
|------|------|------|------|
| `/rc自定 <别名>` | — | 按服务器白名单 | 执行自定义 RCON 命令映射 |
| `日志监听 + 事件宏` | — | 管理员(Web) | 监控 latest.log 触发 RCON（死亡/进出/成就→命令） |
| `MC→群(日志) ~0.5s 延迟` | — | 管理员(Web) | 变相服→群互通，无需 MC 模组，支持按日志类型过滤 |

> 在全局设置中开启 "RCON日志监听" + "MC→群(日志)"，并在服务器管理中填写日志路径，即可通过日志文件变相实现服→群消息转发，延迟约 0.5~1 秒。支持聊天/进出/死亡/成就/系统事件，UI 复选框完全控制。

### 帮助

| 命令 | 别名 | 权限 | 说明 |
|------|------|------|------|
| `/rchelp` | `/帮助` `/help` | 全员 | 纯文本命令帮助 |

> `/rchelp` 返回纯文本命令速查摘要，避免图片渲染阻塞事件循环。

## Web 管理面板

启用后通过浏览器图形化管理所有配置（基于原生 `asyncio` TCP，零外部依赖）：

| 页面 | 端口 | 权限 | 说明 |
|------|------|------|------|
| Web 面板 | `9949`（可配置） | 本地访问 | 14 个功能模块的图形化管理 |

> 配置 `web_panel.enabled = true` 即可启动，无需额外安装依赖。

**面板功能模块：**

| 模块 | 说明 |
|------|------|
| 📊 仪表盘 | 在线/服务器/玩家/命令等总览，卡片点击跳转对应页面，危险命令黑名单可视化 |
| 🖥️ 服务器管理 | 图形化增删改查 RCON 槽位（含所有参数），📋 模板管理（支持从已有服务器/群聊下拉选择快速填充），🏷️ 群名称配置（群号→别名映射） |
| 💬 群服互联 | 全局开关+格式+前缀+仅msay配置 / 群模式选择（不互通/全局/独立） / 群→服 & 服→群独立开关 / 日志类型过滤 / 多服绑定 / 按群独立前缀 |
| ⏱️ 在线追踪 | 全局可编辑 + 按群覆盖配置，支持排行自动重置 |
| 👤 玩家管理 | 手动增删改玩家数据、导入在线玩家、支持修改QQ号和MC ID |
| 🎁 补偿管理 | 待处理/已通过/已拒绝分类管理 |
| 💱 积分兑换 | 按群配置兑换项、编辑消耗积分与RCON命令 |
| 🎰 抽奖管理 | 按群配置奖品池（概率/数量/命令）、开关控制 |
| 🟢 在线列表 | 卡片式展示 + 在线时段横向柱状图（可滚动） + 在线时长排行（支持手动重置） |
| 📋 审计日志 | 分类筛选（命令/Web操作/Web命令）+ 自动刷新，显示群聊名称和操作类别 |
| ⚡ 宏命令 | 管理预设宏命令，支持启用/禁用开关 |
| 📜 脚本与触发器 | 管理 Python 脚本 + 上线触发器，均支持启用/禁用开关（示例默认关闭） |
| ⚡ 快捷命令 | 服务器预设命令 + 每玩家独立快捷命令 + FTB 命令，支持带参数命令点击后填写参数再发送，支持启用/禁用开关（示例默认关闭） |
| ⚙️ 全局设置 | 双列卡片布局，配置文件中所有参数均可图形化修改 |

**近期更新：**

- ✅ 日志转发类型前缀可自定义（全局 + 按群独立配置），支持 emoji/文字前缀
- ✅ 日志监听驱动的服→群转发，无需 MC 模组，延迟 ~0.5-1s
- ✅ 日志类型复选框完全控制转发，支持聊天/命令/死亡/进出/成就/系统/其他
- ✅ 群名称自动从服务器管理读取，各处统一显示别名
- ✅ 事件去重防重复转发（5秒窗口）
- ✅ `/rchelp` 重构为纯文本回执，不再阻塞事件循环
- ✅ 所有脚本、宏、快捷命令、上线触发器均支持开关，示例默认关闭
- ✅ 合并上线触发器到脚本页面、命令配置到快捷命令页面
- ✅ 带参数命令弹窗填写后发送
- ✅ 服务器/群聊下拉选择快速填充（模板与新建）
- ✅ 群号→群名称图形化映射配置（服务器模板页）

---

## 配置示例

### 1. admin — 管理员与安全

```json
{
  "bot_admin_qqs": ["你的QQ号"],
  "dangerous_commands_blacklist": ["stop", "restart", "op ", "deop ", "kick "],
  "rate_limit": {
    "enabled": false,
    "base_interval_ms": 1000,
    "window_minutes": 5,
    "threshold_count": 10,
    "increment_ms": 500,
    "max_interval_ms": 10000,
    "auto_recovery": true,
    "recovery_minutes": 10
  }
}
```

### 2. general — 通用设置

```json
{
  "select_ttl": 30,
  "scripts_dir": "scripts"
}
```

### 3. query — 服务器查询显示

```json
{
  "show_address_port": true,
  "show_version": true,
  "show_latency": true,
  "show_online_count": true,
  "show_players_detail": true,
  "render_online_image": false,
  "auto_cleanup_days": 10
}
```

### 4. online_tracker — 在线时长监控

```json
{
  "enabled": false,
  "poll_interval_seconds": 60,
  "query_method": "rcon",
  "notify_enabled": false,
  "notify_target": "group",
  "notify_intervals": [480, 360, 240],
  "notify_in_game": false,
  "notify_game_format": "§e[在线提醒] {player} 已连续在线 {duration}，注意休息！",
  "auto_kick_enabled": false,
  "auto_kick_threshold": 480,
  "auto_kick_reason": "你已连续在线过久，请休息一下！",
  "auto_kick_ban_minutes": 30
}
```

> **群内覆盖**：管理员可通过 `/在线提醒` 命令按群覆盖以上配置，无覆盖时回退全局默认。
> 
> **批量配置**: `/在线提醒 开,游戏提醒=开,踢出=开,阈值=720,封禁=30,原因=休息`
> 
> **游戏格式**占位符 `{player}` `{duration}`，支持 Minecraft 颜色码：`§a绿 §b青 §c红 §e黄 §l粗体 §n下划线` 等

### 5. relay — 群服消息互联

```json
{
  "enabled": false,
  "group_to_mc": false,
  "mc_to_group": false,
  "mc_to_group_log": false,
  "require_msay": false,
  "format_group": "[QQ] {name}: {msg}",
  "format_mc": "[MC] {player}: {msg}",
  "log_type_prefixes": {
    "chat": "💬",
    "command": "⌨️",
    "player_death": "💀",
    "player_join": "🚪",
    "player_leave": "🚪",
    "player_advancement": "⭐",
    "system": "⚙️",
    "other": "📎"
  }
}
```

> **主动转发**：使用 `/msay <消息>`（别名 `/群说` `/服说`）可主动将消息发送到 MC 公屏。
> 
> **群内覆盖**：管理员可通过 `/消息互通` 命令按群覆盖以上配置（开关/格式/目标服务器），无覆盖时回退全局默认。Web 面板支持按群独立配置前缀与日志类型。
>
> **子命令**: `开|关|模式|群到服|服到群|仅msay|格式|服|重置`，直接 `/消息互通` 查看当前状态。
>
> **🔊 日志监听转发**：无需 MC 模组！开启 `日志监听` + `mc_to_group_log`，在服务器管理中配置日志路径，即可通过日志文件实现服→群转发，延迟 ~0.5-1s，支持聊天/进出/死亡/成就/系统事件。
>
> **🏷️ 前缀自定义**：每种日志类型可自定义转发前缀（全局 + 按群独立），留空不添加前缀。
>
> **⚠ 温馨提示**：使用日志方式互联需要在目标群里先发任意一条消息，否则机器人无法获取群信息。

### 6. player_db — 玩家数据库

```json
{
  "enabled": false,
  "checkin_points": 10,
  "checkin_streak_bonus": 2,
  "new_player_points": 50,
  "compensation_enabled": false,
  "compensation_whitelist": [],
  "compensation_require_admin": true,
  "compensation_blacklist": []
}
```

> **补偿模式**：`compensation_enabled = true` → 全局可用（任何人可申请）；`false` → 仅 `compensation_whitelist` 列表中的 QQ + 管理员可用。

### 7. servers — 服务器槽位（核心）

```json
[
  {
    "group_id": "你的QQ群号",
    "name": "生存一区",
    "rcon_host": "服务器IP",
    "rcon_port": "25575",
    "rcon_password": "RCON密码",
    "game_port": "25565",
    "whitelist_qqs": ["白名单QQ"],
    "public_commands": ["list", "say"],
    "vote_enabled": false,
    "vote_threshold": 3,
    "vote_ttl": 60,
    "vote_min_agree_on_timeout": 1,
    "vote_tie_strategy": "fail",
    "admin_decide_ttl": 120,
    "relay_enabled": false,
    "query_enabled": true
  }
]
```

### 8. web_panel — Web 管理面板

```json
{
  "enabled": false,
  "port": 9949
}
```

> **基于原生 asyncio TCP，无需额外依赖**，启动后日志会显示 URL。

---

## servers 字段速查

### 必填项

| 字段 | 填什么 | 示例 |
|------|--------|------|
| `group_id` | QQ 群号 | `"123456789"` |
| `name` | 服务器名 | `"生存一区"` |
| `rcon_host` | IP/域名 | `"mc.example.com"` |
| `rcon_port` | RCON 端口 | `"25575"` |
| `rcon_password` | RCON 密码 | `"abc123"` |
| `game_port` | 游戏端口 | `"25565"` |

### 常用场景

**A：全员可查，不投票** — `public_commands: ["list"]`, `vote_enabled: false`

**B：白名单模式** — `whitelist_qqs: ["QQ1","QQ2"]`, `public_commands: []`

**C：全员可查+投票** — `public_commands: ["list","say"]`, `vote_enabled: true`, `vote_threshold: 3`

### 平票策略

| 值 | 含义 |
|----|------|
| `"fail"` | 否决 |
| `"pass"` | 通过 |
| `"admin"` | 等管理员裁决 |

---

## 玩家数据库 (SQLite)

数据存储在 `data/plugin_data/mrcon/mrcon.db`：

| 表 | 字段 | 说明 |
|----|------|------|
| `players` | qq_id, mc_id, points, checkin_streak, last_checkin_date | 玩家绑定和积分 |
| `online_sessions` | server_name, player_name, start_ts, end_ts | 每次上下线会话记录 |
| `compensations` | qq_id, mc_id, description, status | 物品补偿申请 |

旧 JSON 文件 (player_db.json / online_sessions.json) 首次启动时自动迁移到 SQLite，迁移后源文件备份为 `.bak.{timestamp}`。

## 速率限制机制（rate_limit）

```
用户发来命令 → 清理窗口外旧时间戳
    → 窗口内无命令 & auto_recovery & 冷却到？ → 间隔恢复为基础值
    → 窗口内命令数 ≥ threshold？ → 间隔 += increment_ms（不超 max_interval_ms）
    → 距上次执行 ≥ 当前间隔？ → 否: 返回等待时间 / 是: 执行
```

## 审计日志

位置：`data/plugin_data/mrcon/audit.log`

---

> ⚠️ **免责声明**：本插件代码由 AI 辅助生成，亲测可用。功能更新随缘，不保证长期维护。如遇问题请提 [Issue](https://github.com/rogergzl/astrbot_plugin_mrconop/issues)。

---

> 📝 **文档说明**：本文档更新可能滞后于代码实际版本，部分新增/修改的功能可能未及时收录。建议以 `metadata.yaml` 中的版本号为准，结合 Web 管理面板体验完整功能。如有遗漏还请包涵。
