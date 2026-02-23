"""
Webhook Nudge Plugin - Webhook 提醒插件

将 nudge 消息通过 HTTP webhook 发送到外部服务。
支持：企业微信机器人、飞书机器人、Slack Incoming Webhook、
Telegram Bot、Discord Webhook 等任何接受 POST JSON 的服务。
"""
import json
import logging
import threading
from typing import Dict, Any, List

import requests

from attention.core.plugin_interface import NudgePlugin, PluginMeta

logger = logging.getLogger(__name__)


class WebhookNudgePlugin(NudgePlugin):
    """通过 Webhook 将提醒发送到外部消息平台。"""

    def _get_meta(self) -> PluginMeta:
        return PluginMeta(
            name="webhook-nudge",
            display_name="Webhook Nudge",
            description="通过 Webhook 将提醒发送到微信/飞书/Slack/Telegram 等平台",
            version="1.0.0",
            author="AttentionOS",
            tags=["nudge", "webhook", "wechat", "slack", "built-in"],
        )

    def get_default_config(self) -> Dict[str, Any]:
        return {
            "webhook_url": "",
            "platform": "generic",  # generic / wechat_work / feishu / slack / discord
            "timeout": 5,
        }

    def get_config_schema(self) -> List[Dict[str, Any]]:
        return [
            {
                "key": "webhook_url",
                "label": "Webhook URL",
                "type": "text",
                "required": True,
            },
            {
                "key": "platform",
                "label": "Platform",
                "type": "select",
                "options": ["generic", "wechat_work", "feishu", "slack", "discord"],
                "required": True,
            },
        ]

    def handle_nudge(self, event: str, data: dict):
        """通过 webhook 发送提醒。"""
        url = self.config.get("webhook_url", "")
        if not url:
            logger.debug("[webhook-nudge] 未配置 webhook URL，跳过")
            return

        # 在后台线程发送
        threading.Thread(
            target=self._send_webhook,
            args=(url, data),
            daemon=True,
        ).start()

    def _send_webhook(self, url: str, data: dict):
        """根据平台格式发送 webhook。"""
        message = data.get("message", "Attention OS 提醒")
        platform = self.config.get("platform", "generic")
        timeout = self.config.get("timeout", 5)

        try:
            payload = self._build_payload(platform, message)
            resp = requests.post(
                url,
                json=payload,
                timeout=timeout,
                headers={"Content-Type": "application/json"},
            )
            if resp.status_code >= 400:
                logger.warning(f"[webhook-nudge] 发送失败 HTTP {resp.status_code}: {resp.text[:200]}")
            else:
                logger.debug(f"[webhook-nudge] 发送成功: {resp.status_code}")
        except Exception as e:
            logger.warning(f"[webhook-nudge] 发送异常: {e}")

    def _build_payload(self, platform: str, message: str) -> dict:
        """根据平台构建不同的请求体。"""
        if platform == "wechat_work":
            return {
                "msgtype": "text",
                "text": {"content": message},
            }
        elif platform == "feishu":
            return {
                "msg_type": "text",
                "content": {"text": message},
            }
        elif platform == "slack":
            return {"text": message}
        elif platform == "discord":
            return {"content": message}
        else:
            # 通用格式
            return {
                "text": message,
                "source": "AttentionOS",
                "type": "nudge",
            }

    def activate(self):
        super().activate()
        url = self.config.get("webhook_url", "")
        if url:
            logger.info(f"[webhook-nudge] Webhook 提醒插件已激活 (platform={self.config.get('platform')})")
        else:
            logger.warning("[webhook-nudge] 已激活，但 webhook URL 未配置")

    def deactivate(self):
        logger.info("[webhook-nudge] Webhook 提醒插件已停用")
