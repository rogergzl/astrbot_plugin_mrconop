# 开发日志

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
