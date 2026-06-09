"""
MRCon Web 管理面板调度入口 - 委托给 web 子模块管理所有 Web 功能
"""
from .web.server import WebServer, _get_panel_version

__all__ = ["WebServer", "_get_panel_version"]
