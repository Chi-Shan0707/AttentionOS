"""
Attention OS 插件接口定义

所有插件必须实现 BasePlugin 接口。
根据功能不同，可以继承更具体的子类：

  - AnalyzerPlugin    分析插件（处理 FusedState，增加自定义字段）
  - NudgePlugin       提醒策略插件（自定义提醒方式：弹窗、微信、声音等）
  - ReporterPlugin    报告插件（自定义报告格式/输出目标：Notion、CSV 等）
  - ExporterPlugin    数据导出插件（同步数据到第三方平台）
  - ProviderPlugin    LLM 提供商插件（接入新的 AI 模型）

插件开发指南：
  1. 在 plugins/ 目录下创建子目录，如 plugins/my_plugin/
  2. 在其中创建 plugin.py，定义一个继承 BasePlugin 的类
  3. 实现 activate() / deactivate() 方法
  4. 在 activate() 中注册事件监听器
  5. 在 deactivate() 中清理资源
"""
import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class PluginMeta:
    """插件元信息。"""

    def __init__(
        self,
        name: str,
        display_name: str,
        description: str,
        version: str = "0.1.0",
        author: str = "",
        plugin_type: str = "general",
        homepage: str = "",
        tags: Optional[List[str]] = None,
    ):
        self.name = name                  # 唯一标识（如 "wechat-nudge"）
        self.display_name = display_name  # 显示名称（如 "微信提醒"）
        self.description = description    # 简短描述
        self.version = version
        self.author = author
        self.plugin_type = plugin_type    # general / analyzer / nudge / reporter / exporter / provider
        self.homepage = homepage
        self.tags = tags or []

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "plugin_type": self.plugin_type,
            "homepage": self.homepage,
            "tags": self.tags,
        }


class BasePlugin(ABC):
    """
    插件基类。所有插件必须继承此类。

    生命周期：
      1. __init__()     → 构造（PluginManager 自动调用）
      2. activate()     → 激活（注册事件监听、初始化资源）
      3. deactivate()   → 停用（清理事件监听、释放资源）

    插件可通过 self.event_bus 访问事件总线，
    通过 self.config 访问插件专属配置。
    """

    def __init__(self):
        self.event_bus = None  # 由 PluginManager 注入
        self.config: Dict[str, Any] = {}  # 由 PluginManager 注入

    @abstractmethod
    def get_meta(self) -> PluginMeta:
        """返回插件元信息。"""
        ...

    @abstractmethod
    def activate(self):
        """
        激活插件。

        在此方法中注册事件监听：
            self.event_bus.on("monitor.cycle_complete", self.on_cycle, source=self.get_meta().name)
        """
        ...

    @abstractmethod
    def deactivate(self):
        """
        停用插件。

        在此方法中清理资源。
        事件监听会由 PluginManager 自动移除，通常不需要手动 off()。
        """
        ...

    def get_default_config(self) -> Dict[str, Any]:
        """
        返回插件的默认配置。

        用户可在 Web UI 中修改这些配置。
        格式：{"key": default_value, ...}
        """
        return {}

    def get_config_schema(self) -> List[Dict[str, Any]]:
        """
        返回配置项的 UI 描述（可选）。

        格式示例：
        [
            {"key": "webhook_url", "label": "Webhook URL", "type": "text", "required": True},
            {"key": "quiet_hours", "label": "免打扰时段", "type": "text", "required": False},
        ]
        """
        return []

    def on_config_changed(self, new_config: Dict[str, Any]):
        """配置变更时的回调（可选重写）。"""
        self.config = new_config


# ============================================================
# 具体插件类型
# ============================================================

class AnalyzerPlugin(BasePlugin):
    """
    分析插件：在每个监控周期接收 FusedState，可以添加自定义分析维度。

    典型用途：
    - 情感状态分析
    - 自定义应用分类
    - 工作模式识别
    """

    def get_meta(self) -> PluginMeta:
        meta = self._get_meta()
        meta.plugin_type = "analyzer"
        return meta

    @abstractmethod
    def _get_meta(self) -> PluginMeta:
        ...

    @abstractmethod
    def analyze(self, event: str, data: dict):
        """
        分析回调。

        Args:
            event: 事件名（通常是 "monitor.cycle_complete"）
            data:  {"fused_state": dict, "activity_state": dict, ...}
        """
        ...

    def activate(self):
        self.event_bus.on(
            "monitor.cycle_complete",
            self.analyze,
            source=self.get_meta().name,
            priority=50,  # 分析插件优先级较高
        )

    def deactivate(self):
        pass  # 事件监听由 PluginManager 清理


class NudgePlugin(BasePlugin):
    """
    提醒策略插件：自定义提醒方式。

    典型用途：
    - 微信/Slack/Telegram 提醒
    - 声音提醒
    - 自定义弹窗样式
    """

    def get_meta(self) -> PluginMeta:
        meta = self._get_meta()
        meta.plugin_type = "nudge"
        return meta

    @abstractmethod
    def _get_meta(self) -> PluginMeta:
        ...

    @abstractmethod
    def handle_nudge(self, event: str, data: dict):
        """
        提醒回调。

        Args:
            event: 事件名（"nudge.triggered"）
            data:  {"message": str, "priority": str, "context": dict}
        """
        ...

    def activate(self):
        self.event_bus.on(
            "nudge.triggered",
            self.handle_nudge,
            source=self.get_meta().name,
        )

    def deactivate(self):
        pass


class ReporterPlugin(BasePlugin):
    """
    报告插件：自定义报告输出。

    典型用途：
    - 生成 Notion 页面
    - 导出为 PDF/CSV
    - 同步到 Google Sheets
    """

    def get_meta(self) -> PluginMeta:
        meta = self._get_meta()
        meta.plugin_type = "reporter"
        return meta

    @abstractmethod
    def _get_meta(self) -> PluginMeta:
        ...

    @abstractmethod
    def handle_review(self, event: str, data: dict):
        """
        报告回调。

        Args:
            event: "review.generated"
            data:  {"review": dict}  完整的一日回顾数据
        """
        ...

    def activate(self):
        self.event_bus.on(
            "review.generated",
            self.handle_review,
            source=self.get_meta().name,
        )

    def deactivate(self):
        pass


class ExporterPlugin(BasePlugin):
    """
    数据导出插件：实时或定期同步数据到外部平台。

    典型用途：
    - 同步到 Toggl / RescueTime
    - 同步到 Google Calendar
    - 推送到自定义 API
    """

    def get_meta(self) -> PluginMeta:
        meta = self._get_meta()
        meta.plugin_type = "exporter"
        return meta

    @abstractmethod
    def _get_meta(self) -> PluginMeta:
        ...

    @abstractmethod
    def export(self, event: str, data: dict):
        """
        导出回调。监听的事件由子类在 activate() 中自行决定。
        """
        ...

    def deactivate(self):
        pass
