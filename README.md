# mrcon — MC 综合管理插件

[![GitHub](https://img.shields.io/badge/GitHub-rogergzl%2Fastrbot__plugin__mrconop-blue?logo=github)](https://github.com/rogergzl/astrbot_plugin_mrconop)
![Version](https://img.shields.io/badge/version-v3.1.0-green)

RCON 命令转发 + 服务器并发查询 + SQLite 玩家数据库 + 会话级在线追踪 + 签到 + 补偿 + 群服消息互联（RCON tellraw）

## 安装

本目录作为 AstrBot 插件加载。依赖 `mcstatus` 库。

```
pip install mcstatus
```

## 架构

```
mrcon/
├── main.py           # 插件入口（命令路由 + 业务逻辑）
├── database.py       # SQLite 数据层（玩家/会话/补偿）
├── transport.py      # RCON 协议传输层
├── _conf_schema.json # 配置 Schema
├── metadata.yaml     # 元数据
└── README.md
```

**数据文件**（自动创建于 `data/plugin_data/mrcon/`）：

| 文件 | 类型 | 说明 |
|------|------|------|
| `mrcon.db` | SQLite | 玩家绑定、签到积分、在线会话记录、补偿申请 |
| `audit.log` | JSONL | RCON 审计日志 |
| `mcserv_{群号}.json` | JSON | 分群 MC 服务器列表 |

## 全部命令速查

### RCON 命令

| 命令 | 权限 | 说明 |
|------|------|------|
| `/mrcon <命令>` 或 `/mcmd` | 白名单 | 转发命令到 MC 服务器 |
| `/rcmacro <名称> [参数]` | 白名单 | 执行预定义宏 |
| `/rcscript <文件名>` | 白名单 | 执行脚本文件 |
| `rc赞同` / `rc反对` | 全员 | 投票 |
| `rc通过` / `rc否决` | 管理员 | 裁决 |

### 服务器查询

| 命令 | 权限 | 说明 |
|------|------|------|
| `/mc` | 全员 | 查询所有服务器状态 |
| `/mcget <名称>` | 全员 | 查询单个服务器 |
| `/mclist` | 全员 | 列出所有服务器 |
| `/mcadd <名称> <地址>` | 管理员 | 添加服务器 |
| `/mcdel <名称>` | 管理员 | 删除服务器 |
| `/mcup <名称> [新名] [新址]` | 管理员 | 更新服务器 |
| `/mcshare <名称> <目标群ID>` | 超管 | 共享服务器到其他群 |
| `/mcunshare <名称> <目标群ID>` | 超管 | 取消共享 |
| `/mccleanup` | 管理员 | 清理失效服务器 |
| `/mcset <项名> <0\|1>` | 管理员 | 设置显示项 |
| `/online` | 全员 | 查看在线玩家 |

### 玩家数据库

| 命令 | 说明 |
|------|------|
| `/bind <MC_ID>` | 绑定 MC 账号，获新玩家奖励积分 |
| `/checkin` | 每日签到，连续签到额外积分 |
| `/mystats` | 查看个人积分/签到天数/绑定信息 |
| `/onlinetime [玩家名]` | 查看在线时长排行或指定玩家 |
| `/comp <RCON命令>` | 白名单 | 申请物品补偿（输入完整RCON命令） |
| `/comp_list` | 管理 | 查看待审批补偿 |
| `/comp_approve <ID>` | 管理 | 批准并
| `/relay <on\|off>` | 开关本群群服消息互联 |

---

## 配置示例（复制后修改即可）

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
  "query_method": "rcon"
}
```

### 5. relay — 群服消息互联

```json
{
  "enabled": false,
  "group_to_mc": true,
  "mc_to_group": false,
  "format_group": "[QQ] {name}: {msg}",
  "format_mc": "[MC] {player}: {msg}"
}
```

### 6. player_db — 玩家数据库

```json
{
  "enabled": false,
  "checkin_points": 10,
  "checkin_streak_bonus": 2,
  "new_player_points": 50,
  "compensation_enabled": false,
  "compensation_require_admin": true
}
```

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

---

## 速率限制机制（rate_limit）

```
用户发来命令 → 清理窗口外旧时间戳
    → 窗口内无命令 & auto_recovery & 冷却到？ → 间隔恢复为基础值
    → 窗口内命令数 ≥ threshold？ → 间隔 += increment_ms（不超 max_interval_ms）
    → 距上次执行 ≥ 当前间隔？ → 否: 返回等待时间 / 是: 执行
```

## servers 字段速查（无脑填）

### 必填项

| 字段 | 填什么 | 示例 |
|------|--------|------|
| `group_id` | QQ 群号 | `"123456789"` |
| `name` | 服务器名 | `"生存一区"` |
| `rcon_host` | IP/域名 | `"mc.example.com"` |
| `rcon_port` | RCON 端口 | `"25575"` |
| `rcon_password` | RCON 密码 | `"abc123"` |
| `game_port` | 游戏端口 | `"25565"` |

### 常用场景速抄

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

## 在线时长数据

## 审计日志

位置：`data/plugin_data/mrcon/audit.log`

---

> ⚠️ **免责声明**：本插件代码由 AI 辅助生成，亲测可用。功能更新随缘，不保证长期维护。如遇问题请提 [Issue](https://github.com/rogergzl/astrbot_plugin_mrconop/issues)。
