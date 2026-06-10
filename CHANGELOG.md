# 开发日志

---

## v4.2.5 | 2026-06-10

| 时间 | 版本 | 操作人 | 变更类型 | 涉及模块 | 变更详情 | 备注 |
|------|------|--------|----------|----------|----------|------|
| 2026-06-10 | v4.2.5 | lindagao | Bug 修复 | 配置 Schema | `_conf_schema.json` 审计 `retention_days` 字段 `"type": "integer"` → `"int"`，修复 AstrBot 不支持的配置类型导致插件加载失败 | AstrBot 仅支持 `int/float/bool/string/text/list/file/object/template_list` |
| 2026-06-10 | v4.2.5 | lindagao | Bug 修复 | Web面板/审计 | 修复 4 个 JS 错误：`hx` 未定义（别名 `escapeHtml`）、分类按钮 `fs` 作用域泄漏（改用 `loAu._fs`）、`loAu(pg,cat)` 参数顺序颠倒导致 `NaN` 分页偏移 | 全量修复后审计页面可用 |
| 2026-06-10 | v4.2.5 | Bug 修复 | Web面板/审计 | 审计页面布局重构：搜索栏 + 分类按钮区独立为 `#au-top`（不销毁），表格 + 分页区独立为 `#au-res`（增量更新）；新增 `loAu_li()` 防抖函数（300ms）仅更新 `#au-res`，输入框不丢失焦点 | 解决每次输入都触发全量 innerHTML 重建导致输入体验崩溃 |
| 2026-06-10 | v4.2.5 | Bug 修复 | Web面板/审计 | 操作列超长 RCON 命令截断显示（`max-width:180px` + `text-overflow:ellipsis`），鼠标悬停 `title` 显示全文 | 不影响结果/详情列布局 |
| 2026-06-10 | v4.2.5 | Bug 修复 | 审计搜索 | 关键词搜索范围扩展 `event_type` 字段（DB 路径 `LIKE` + JSONL 回退路径 `in`），搜 `cha` 可匹配 `chat` 类型记录 | 原仅搜索 `cmd/resp/sender_name` 三字段 |
| 2026-06-10 | v4.2.5 | Bug 修复 | 群服互联 | 服→群日志转发 `_relay_log_event_to_groups` + 模组转发 `_on_mc_chat` 补充 `_audit_auto("relay", ...)` 审计调用，修复日志审查中"群服转发"分类无记录 | 群→服方向已有审计，仅补充服→群方向 |
| 2026-06-10 | v4.2.5 | 功能优化 | 群服互联 | 日志/模组转发自动纳入 `group_servers`（服务器管理绑定）中的群，未配置 relay override 时以 `"mode":"global"` 参与转发 | 重装插件后无需群里先说话即可恢复转发 |
| 2026-06-10 | v4.2.5 | 功能优化 | Web面板/审计 | 新增 `loAu_li()` 实时搜索：关键词和事件类型输入框触发 300ms 防抖自动查询，输入即刷新、删空即还原 | 保留回车/搜索按钮原有行为 |

---

## v4.1.1 | 2026-06-09

| 时间 | 版本 | 操作人 | 变更类型 | 涉及模块 | 变更详情 | 备注 |
|------|------|--------|----------|----------|----------|------|
| 2026-06-09 | v4.1.1 | lindagao | Bug 修复 | 日志监听 | `core/log_events.py` 第49行 `_log_listener.start(_on_log_event)` 改为 `start(lambda *args: _on_log_event(plugin, *args))`，修复模块化拆分后回调签名 `plugin` 参数丢失导致群服互联、事件宏、VIP事件全部失效 | 旧版 `self._on_log_event` 绑定实例方法(4参数)，新版模块函数需 `plugin` 为第1参数(5参数)，裸传函数时 `_on_log_event(server,etype,player,text)` 缺少 `plugin` |
| 2026-06-09 | v4.1.1 | lindagao | Bug 修复 | 日志事件宏 | VIP事件细化：`_em_etNames`/`loMa` 补充 `vip_leave`/`vip_death`；`doEmSave` 补全 `vip_level` 字段；新增 `emEtVipLevel` 函数 | 选择VIP等级不再触发 `ReferenceError` |
| 2026-06-09 | v4.1.1 | lindagao | 功能优化 | 在线追踪/封禁 | 封禁机制从 ban+pardon+自维护定时器 改为 MC 原生 `tempban` 命令；新增可编辑命令模板 `{player}` `{minutes}` `{reason}` | 解决Bot重启后封禁状态丢失导致的永久封禁问题 |
| 2026-06-09 | v4.1.1 | lindagao | 功能优化 | 在线追踪/踢出 | 踢出原因支持 `{hours}` `{minutes}` 占位符，抽取统一 `_expand_placeholders` 函数共用；踢出原因改为仅在在线追踪界面配置 | 默认: `§6{player}§r, §a你已在线§e{hours}§a小时§r, §c请休息§d{minutes}§c分钟吧§r` |
| 2026-06-09 | v4.1.1 | lindagao | 配置更新 | 配置 Schema | `_conf_schema.json` hint 补充 `vip_leave`/`vip_death` 事件类型；新增 `auto_kick_ban_cmd` 配置项 | |
| 2026-06-09 | v4.1.1 | lindagao | 代码清理 | 在线追踪/WEB | 移除 `_pending_unbans`/`_banned_players` 相关代码；`_api_online` 移除封禁玩家查询；`loOn()` 移除已封禁玩家列表展示；`loCfg` 移除踢出原因字段(统一到 `loTr`) | |

---

## v4.0.0 | 2026-06-09

| 时间 | 版本 | 操作人 | 变更类型 | 涉及模块 | 变更详情 | 备注 |
|------|------|--------|----------|----------|----------|------|
| 2026-06-09 | v4.0.0 | lindagao | 功能优化 | 在线追踪 | `ranking_reset_hours` 默认值从 `0`(永久保留) 改为 `24`(24小时)，避免服务器按在线时长封禁后永不过期 | |
| 2026-06-09 | v4.0.0 | lindagao | 功能新增 | 在线追踪 | 新增 `ranking_state.json` 文件持久化 `_last_ranking_reset` 时间戳；插件重载后自动加载排行状态，恢复上次清理时间；清理行为从"删除全部"改为"只删除超出记录时长的旧记录" | |
| 2026-06-09 | v4.0.0 | lindagao | 功能新增 | 数据库 | 新增 `delete_online_sessions_before` 方法，三个 DB 实现（SQLite主库、MySQL、外部SQLite）均已添加，按 `end_ts < before_timestamp` 条件删除过期会话记录 | |
| 2026-06-09 | v4.0.0 | lindagao | 功能新增 | 速率限制 | 新增转发频率白名单：`rate_whitelist`(白名单QQ列表)、`whitelist_min_delay_ms`(最低硬延迟，默认200ms)；管理员自动包含；白名单用户仅受硬编码最小延迟约束，防止频繁转发导致服务器性能压力；Web管理面板新增"频率白名单"设置区域 | |
| 2026-06-09 | v4.0.0 | lindagao | 功能优化 | Web面板 | 前端文案优化："排行自动重置(小时)" → "单次记录时长"；"排行重置(小时,0=不重置)" → "单次记录时长(小时,0=永久保留)"；Tooltip提示语同步更新 | |
| 2026-06-09 | v4.0.0 | lindagao | Bug 修复 | 在线追踪/数据库 | 累计模式限定时间窗口：`get_player_total_seconds` 新增 `max_age_hours` 参数，>0时SQL加 `AND end_ts >= ?` 过滤；三个累计模式调用点均传入 `plugin.ranking_reset_hours`；修复前累计模式查询全部历史数据与单次记录时长窗口脱节 | |
| 2026-06-09 | v4.0.0 | lindagao | Bug 修复 | main | `_core_load_ranking_state(self)` 调用时机从 `__init__` 早期移至 `self.plugin_data_dir` 初始化之后，修复 `'MrconPlugin' object has no attribute 'plugin_data_dir'` 错误 | |
| 2026-06-09 | v4.0.0 | lindagao | 代码清理 | 根目录 | 删除未被引用的旧版本文件: `transport.py`, `database.py`, `log_listener.py`；实际使用版本均在 `core/` 子目录 | |

---

### v4.0.0 备注
- 本次更新包含代码架构完全重构（从大泥球变为独立模块方式），版本号由 3.48.0 升级至 4.0.0
- `ranking_reset_hours` 配置键 `ranking_reset_interval_hours` 保持不变，向后兼容
- 白名单配置保存后即时生效，无需重启插件

---

## v4.2.4 | 2026-06-10

| 时间 | 版本 | 操作人 | 变更类型 | 涉及模块 | 变更详情 | 备注 |
|------|------|--------|----------|----------|----------|------|
| 2026-06-10 | v4.2.4 | lindagao | 功能新增 | 审计日志 | 审计日志数据库化：新增 `audit_logs` 表（含 `event_type`/`server_name`/`group_name` 字段），双写 JSONL + DB | 自动建表、建索引；JSONL 双写可关闭 |
| 2026-06-10 | v4.2.4 | lindagao | 功能新增 | Web面板 | 审计日志升级为数据库搜索：支持关键词搜索、事件类型筛选、时间范围筛选、分页浏览、CSV/JSON 导出、批量勾选删除 | 每页50条，保留 JSONL 回退 |
| 2026-06-10 | v4.2.4 | lindagao | 功能新增 | 审计日志 | 新增 `audit.retention_days` 自动清理：每小时清理超过保留天数的记录（默认90天，0=不清理） | 后台异步任务 |
| 2026-06-10 | v4.2.4 | lindagao | 功能扩展 | 审计引擎 | 所有 `_audit_auto` 调用方（log_events/online_tracker/server_manager/relay）补充 `event_type` 和 `server_name` 参数，审计记录可区分死亡类型/触发来源 | 向后兼容：旧调用方缺失参数自动填空串 |

---

## v4.2.3 | 2026-06-10

| 时间 | 版本 | 操作人 | 变更类型 | 涉及模块 | 变更详情 | 备注 |
|------|------|--------|----------|----------|----------|------|
| 2026-06-10 | v4.2.3 | lindagao | Bug 修复 | 日志事件宏 | `player_death_pvp` 前移优先匹配（`was slain/killed/shot/frozen by`），`_on_log_event` 新增桥接分支将 PVP 死亡统一触发 `player_death`/`vip_death`/`player_first_death` 宏；`player_death` 正则扩展 `was killed`（/kill 命令）。保留独立死亡分类确保 relay/审计正确区分死亡类型 | 所有死亡方式（环境/实体/PVP//kill/虚空等）均可触发监听 `player_death` 的宏 |

---

## v4.2.2 | 2026-06-10

| 时间 | 版本 | 操作人 | 变更类型 | 涉及模块 | 变更详情 | 备注 |
|------|------|--------|----------|----------|----------|------|
| 2026-06-10 | v4.2.2 | lindagao | 功能优化 | Web面板 | 🪝日志事件宏说明区改为可折叠形式，新增 `📖参数说明`、`🔄 say/tell/msg 命令自动转换` 折叠块，展示三条 tellraw 转换规则 | 纯文档/UI优化 |

---

## v4.2.1 | 2026-06-10

| 时间 | 版本 | 操作人 | 变更类型 | 涉及模块 | 变更详情 | 备注 |
|------|------|--------|----------|----------|----------|------|
| 2026-06-10 | v4.2.1 | lindagao | 功能扩展 | 事件宏/在线时长宏 | `say→tellraw` 转换扩展至 `tell`/`msg` 命令：`tell <target> <msg>` → `tellraw <target>`，`msg <target> <msg>` 同理，移除 Minecraft 默认的 "[Server]" 和 "Rcon悄悄对你说" 前缀 | |
| 2026-06-10 | v4.2.1 | lindagao | 功能新增 | 事件宏/在线时长宏 | 实现 `{mc_id}`/`{qq}` 变量替换：执行宏时查DB获取玩家绑定信息，RCON命令和QQ消息均支持 | 此前 Web 面板已文档化但未实际实现 |

---

## v4.2.0 | 2026-06-10

| 时间 | 版本 | 操作人 | 变更类型 | 涉及模块 | 变更详情 | 备注 |
|------|------|--------|----------|----------|----------|------|
| 2026-06-10 | v4.2.0 | lindagao | 功能新增 | 日志监听 | LogWatcher 读取位置持久化：新增 `_load_positions`/`_save_positions`/`_restore_positions`，每30秒保存到JSON文件，重启后恢复，避免丢失事件 | `POSITION_SAVE_INTERVAL=30` |
| 2026-06-10 | v4.2.0 | lindagao | 功能新增 | 审计日志 | 新增 `_audit_auto` 审计函数，覆盖事件宏、上线触发器、relay转发、游戏通知等自动化RCON命令；支持 `audit.auto_enabled` 开关和 `audit.skip_categories` 跳过列表 | 配置项新增 `_conf_schema.json` audit 区块 |
| 2026-06-10 | v4.2.0 | lindagao | 功能优化 | 事件宏 | 事件宏中使用 `say` 命令自动转换为 `tellraw @a`，使用插件配置的前缀替换 Minecraft 默认 `[Server]` 前缀 | 受 `event_macro_game_prefix` 配置控制 |
