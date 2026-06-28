import requests
from app.config import settings


def send_human_alert(user_id: str, customer_message: str, ai_answer: str) -> bool:
    """
    发送转人工提醒到企业微信群机器人。
    如果没有配置 WECOM_GROUP_WEBHOOK，则直接跳过。
    """

    if not settings.WECOM_GROUP_WEBHOOK:
        return False

    content = (
        "【糖果乒乓AI客服转人工提醒】\n\n"
        f"客户ID：{user_id}\n"
        f"客户问题：{customer_message}\n\n"
        f"AI回复：{ai_answer}"
    )

    payload = {
        "msgtype": "text",
        "text": {
            "content": content
        }
    }

    response = requests.post(
        settings.WECOM_GROUP_WEBHOOK,
        json=payload,
        timeout=10,
    )

    response.raise_for_status()

    return True