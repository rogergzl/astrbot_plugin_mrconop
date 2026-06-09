import os

from astrbot.api.event import AstrMessageEvent
from astrbot.api.message_components import Plain


async def cmd_help(plugin, event: AstrMessageEvent):
    yield event.plain_result(
        "━━━  MRCon 命令帮助  v" + _get_version() + "  ━━━\n\n"
        "🖥️ MC 查询\n"
        "  /mc              所有服务器状态 + 在线玩家\n"
        "  /mcget <名>      单服详情\n"
        "  /mclist          服务器列表\n"
        "  /mcset <项> 1|0  设置显示项\n"
        "  /在线时长 [服|玩家] 在线排行\n"
        "  /在线提醒         配置提醒与踢出\n\n"
        "⚙️ 服务器\n"
        "  /mcadd <名> <IP:端口>  添加\n"
        "  /mcdel <名>             删除\n"
        "  /mcup <名> [新名] [新址] 更新\n"
        "  /mcshare|mcunshare <名> <群>  共享 / 取消\n"
        "  /mccleanup              清理失效服务器\n\n"
        "🎯 RCON\n"
        "  /mrcon <命令>    执行 RCON 命令\n"
        "  /选服 <编号>      选择目标服务器\n"
        "  /宏 <名> [参数]   执行预设宏\n"
        "  /脚本 <文件名>    执行脚本\n"
        "  /rc赞同|反对  /rc通过|否决  投票 + 裁决\n\n"
        "👤 玩家\n"
        "  /绑定 <MC_ID>    绑定 MC 账号\n"
        "  /签到            每日签到\n"
        "  /我的            积分与统计\n"
        "  /理赔 <命令>      申请物品补偿\n"
        "  /理赔列表 | 同意|拒绝理赔  审批管理\n\n"
        "💱 积分 & 🎰 抽奖\n"
        "  /兑换列表 /兑换 <编号>  积分兑换\n"
        "  /抽奖 /奖品列表         积分抽奖\n"
        "  /兑奖 <编号> /我的中奖   兑奖 / 中奖记录\n\n"
        "🔗 群服互联\n"
        "  /msay <消息>             发消息到 MC 公屏\n"
        "  /消息互通 开|关          开关互通\n"
        "  /消息互通 模式 off|global|custom  转发模式\n"
        "  /消息互通 群到服|服到群 开|关      方向开关\n"
        "  /消息互通 服到群日志 开|关        日志驱动服→群\n"
        "  /消息互通 服 <名>        指定目标服务器\n"
        "  /消息互通 格式 <文本>    自定义格式 {name}/{msg}\n"
        "  /消息互通 日志格式 <文本> 日志格式 {player}/{msg}\n"
        "  /消息互通 重置           恢复默认\n\n"
        "📡 日志 & 🌐 Web 面板\n"
        "  /rc自定 <别名>           自定义 RCON 命令\n"
        "  http://localhost:9949     Web 管理面板\n\n"
        "输入  /rchelp  随时查看此帮助"
    )


def _get_version() -> str:
    try:
        import yaml
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "metadata.yaml")
        with open(p, "r", encoding="utf-8") as f:
            m = yaml.safe_load(f)
            return str(m.get("version", "?"))
    except Exception:
        return "?"
