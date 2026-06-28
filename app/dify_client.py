import requests
from app.config import settings


# 临时保存每个用户对应的 Dify conversation_id
# 本地测试够用，正式部署后再换成数据库或 Redis
conversation_map = {}


def call_dify(message: str, user_id: str = "test-user") -> str:
    """
    调用 Dify Chat API，并返回 AI 回复文本
    """

    headers = {
        "Authorization": f"Bearer {settings.DIFY_API_KEY}",
        "Content-Type": "application/json",
    }

    conversation_id = conversation_map.get(user_id, "")

    payload = {
        "inputs": {},
        "query": message,
        "response_mode": "blocking",
        "conversation_id": conversation_id,
        "user": user_id,
    }

    try:
        response = requests.post(
            settings.DIFY_API_URL,
            headers=headers,
            json=payload,
            timeout=30,
        )
    except requests.exceptions.Timeout as exc:
        print("Dify 调用失败原因：", exc)
        return ""
    except requests.exceptions.ConnectionError as exc:
        print("Dify 调用失败原因：", exc)
        return ""
    except requests.exceptions.RequestException as exc:
        print("Dify 调用失败原因：", exc)
        return ""

    if response.status_code != 200:
        print(f"Dify 调用失败原因：HTTP {response.status_code}: {response.text[:200]}")
        return ""

    try:
        data = response.json()
    except ValueError as exc:
        print("Dify 调用失败原因：响应不是合法 JSON", exc)
        return ""

    # 保存 Dify 返回的新 conversation_id
    new_conversation_id = data.get("conversation_id", "")
    if new_conversation_id:
        conversation_map[user_id] = new_conversation_id

    # Dify chat-messages 接口通常返回 answer 字段
    answer = data.get("answer", "")

    return answer
