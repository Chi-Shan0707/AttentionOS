"""
Sound Nudge Plugin - 声音提醒插件

当触发 nudge 时播放系统提示音，而不仅依赖弹窗。
支持 macOS / Windows / Linux。
"""
import logging
import platform
import subprocess
import threading
from typing import Dict, Any, List

from attention.core.plugin_interface import NudgePlugin, PluginMeta

logger = logging.getLogger(__name__)


class SoundNudgePlugin(NudgePlugin):
    """分心时播放系统声音提醒。"""

    def _get_meta(self) -> PluginMeta:
        return PluginMeta(
            name="sound-nudge",
            display_name="Sound Nudge",
            description="分心时播放系统声音提醒，支持 macOS / Windows / Linux",
            version="1.0.0",
            author="AttentionOS",
            tags=["nudge", "sound", "built-in"],
        )

    def get_default_config(self) -> Dict[str, Any]:
        return {
            "sound_type": "default",  # default / custom
            "custom_sound_path": "",  # 自定义音频文件路径
            "volume": 0.7,            # 音量 (0.0 ~ 1.0)
            "only_high_priority": False,  # 仅高优先级 nudge 时播放
        }

    def get_config_schema(self) -> List[Dict[str, Any]]:
        return [
            {
                "key": "sound_type",
                "label": "Sound Type",
                "type": "select",
                "options": ["default", "custom"],
                "required": True,
            },
            {
                "key": "custom_sound_path",
                "label": "Custom Sound Path",
                "type": "text",
                "required": False,
            },
            {
                "key": "only_high_priority",
                "label": "Only High Priority",
                "type": "boolean",
                "required": False,
            },
        ]

    def handle_nudge(self, event: str, data: dict):
        """播放提醒声音。"""
        if self.config.get("only_high_priority") and data.get("priority") != "high":
            return

        # 在后台线程播放，避免阻塞主循环
        threading.Thread(target=self._play_sound, daemon=True).start()

    def _play_sound(self):
        """根据平台播放声音。"""
        try:
            custom_path = self.config.get("custom_sound_path", "")
            system = platform.system()

            if custom_path:
                self._play_file(custom_path, system)
            else:
                self._play_system_sound(system)

        except Exception as e:
            logger.warning(f"[sound-nudge] 播放声音失败: {e}")

    def _play_system_sound(self, system: str):
        """播放系统默认提示音。"""
        if system == "Darwin":
            # macOS: 使用 afplay 播放系统音
            subprocess.run(
                ["afplay", "/System/Library/Sounds/Glass.aiff"],
                capture_output=True, timeout=5,
            )
        elif system == "Windows":
            # Windows: 使用 PowerShell 播放系统音
            subprocess.run(
                ["powershell", "-c", "[System.Media.SystemSounds]::Exclamation.Play()"],
                capture_output=True, timeout=5,
            )
        else:
            # Linux: 使用 paplay 或 aplay
            for cmd in [
                ["paplay", "/usr/share/sounds/freedesktop/stereo/bell.oga"],
                ["aplay", "/usr/share/sounds/sound-icons/glass-water-1.wav"],
            ]:
                try:
                    subprocess.run(cmd, capture_output=True, timeout=5)
                    return
                except FileNotFoundError:
                    continue
            # Fallback: terminal bell
            print("\a", end="", flush=True)

    def _play_file(self, path: str, system: str):
        """播放指定音频文件。"""
        if system == "Darwin":
            subprocess.run(["afplay", path], capture_output=True, timeout=10)
        elif system == "Windows":
            subprocess.run(
                ["powershell", "-c", f'(New-Object Media.SoundPlayer "{path}").PlaySync()'],
                capture_output=True, timeout=10,
            )
        else:
            subprocess.run(["aplay", path], capture_output=True, timeout=10)

    def activate(self):
        super().activate()
        logger.info("[sound-nudge] 声音提醒插件已激活")

    def deactivate(self):
        logger.info("[sound-nudge] 声音提醒插件已停用")
