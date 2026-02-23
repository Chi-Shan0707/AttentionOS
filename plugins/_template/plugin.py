"""
Plugin Template - 插件模板

复制此目录并重命名为你的插件名（如 my_plugin/），
然后修改此文件中的类名和元信息。

使用方法：
  1. cp -r plugins/_template plugins/my_plugin
  2. 编辑 plugins/my_plugin/plugin.py
  3. 重启 Attention OS，插件会自动被发现和加载

可用的事件：
  - monitor.cycle_complete   每个监控周期完成（最常用）
  - monitor.screenshot       截图完成
  - monitor.analysis         分析完成
  - nudge.triggered          提醒触发
  - pomodoro.started         番茄钟开始
  - pomodoro.completed       番茄钟完成
  - goal.added               目标添加
  - goal.completed           目标完成
  - briefing.completed       Briefing 完成
  - review.generated         一日回顾生成

可用的插件基类：
  - BasePlugin       通用插件
  - AnalyzerPlugin   分析插件（监听 cycle_complete）
  - NudgePlugin      提醒插件（监听 nudge.triggered）
  - ReporterPlugin   报告插件（监听 review.generated）
  - ExporterPlugin   导出插件（自定义监听）
"""
from typing import Dict, Any, List

from attention.core.plugin_interface import BasePlugin, PluginMeta


class MyPlugin(BasePlugin):
    """我的自定义插件。"""

    def get_meta(self) -> PluginMeta:
        return PluginMeta(
            name="my-plugin",             # 唯一标识，修改为你的插件名
            display_name="My Plugin",     # 显示名称
            description="这是一个插件模板，请修改为你的插件描述",
            version="0.1.0",
            author="Your Name",
            plugin_type="general",
            tags=["example"],
        )

    def get_default_config(self) -> Dict[str, Any]:
        """返回默认配置，用户可在 Web UI 中修改。"""
        return {
            "example_key": "example_value",
        }

    def get_config_schema(self) -> List[Dict[str, Any]]:
        """配置 UI 描述（可选）。"""
        return [
            {
                "key": "example_key",
                "label": "Example Setting",
                "type": "text",
                "required": False,
            },
        ]

    def activate(self):
        """
        激活插件。在此注册事件监听。

        self.event_bus 已自动注入，可直接使用。
        """
        self.event_bus.on(
            "monitor.cycle_complete",
            self.on_cycle_complete,
            source=self.get_meta().name,
        )

    def deactivate(self):
        """停用插件。事件监听会自动清理，无需手动 off()。"""
        pass

    def on_cycle_complete(self, event: str, data: dict):
        """
        每个监控周期完成时的回调。

        Args:
            event: "monitor.cycle_complete"
            data: {
                "fused_state": {...},      # 融合状态
                "activity_state": {...},   # 活动状态
                "analysis": {...},         # 截图分析
                "timestamp": "2026-02-23 14:30:00",
            }
        """
        fused = data.get("fused_state", {})
        # 在这里实现你的逻辑
        # print(f"[my-plugin] attention: {fused.get('attention_level')}")
