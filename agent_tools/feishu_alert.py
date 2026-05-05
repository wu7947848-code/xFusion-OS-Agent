import requests
import json
import os

class FeishuAlerter:
    def __init__(self, webhook_url: str = None):
        self.webhook_url = webhook_url or os.getenv("FEISHU_WEBHOOK_URL", "")

    def send_alert(self, title: str, content: str, is_success: bool = True) -> str:
        """
        通过飞书机器人发送卡片消息。
        """
        if not self.webhook_url:
            return "飞书 Webhook 未配置，跳过发送。"

        color = "green" if is_success else "red"

        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": title
                    },
                    "template": color
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "content": content,
                            "tag": "lark_md"
                        }
                    }
                ]
            }
        }

        try:
            response = requests.post(self.webhook_url, json=payload, timeout=5)
            if response.status_code == 200:
                return "已成功发送飞书通知。"
            return f"发送失败，HTTP 状态码: {response.status_code}"
        except Exception as e:
            return f"发送飞书请求异常: {str(e)}"

    def send_warning_card(self, title: str, content: str) -> str:
        """
        通过飞书机器人发送告警卡片（红色模板）。
        """
        if not self.webhook_url:
            return "飞书 Webhook 未配置，跳过发送。"

        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": title
                    },
                    "template": "red"
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "content": content,
                            "tag": "lark_md"
                        }
                    },
                    {
                        "tag": "note",
                        "elements": [
                            {
                                "tag": "plain_text",
                                "content": "来自 xFusion OS-Agent 实时告警"
                            }
                        ]
                    }
                ]
            }
        }

        try:
            response = requests.post(self.webhook_url, json=payload, timeout=5)
            if response.status_code == 200:
                return "已成功发送飞书告警卡片。"
            return f"发送失败，HTTP 状态码: {response.status_code}"
        except Exception as e:
            return f"发送飞书请求异常: {str(e)}"
