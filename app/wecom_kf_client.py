import time
import requests
from app.config import settings


_access_token_cache = {
    "access_token": "",
    "expires_at": 0,
}


_sync_cursor_cache = {}

def get_access_token() -> str:
    """
    获取企业微信 access_token。
    后续调用微信客服 sync_msg、send_msg 都需要用它。
    """

    now = int(time.time())

    # 如果缓存里的 token 还没过期，直接复用
    if _access_token_cache["access_token"] and _access_token_cache["expires_at"] > now:
        return _access_token_cache["access_token"]

    url = "https://qyapi.weixin.qq.com/cgi-bin/gettoken"

    params = {
        "corpid": settings.WECHAT_CORP_ID,
        "corpsecret": settings.WECHAT_KF_SECRET,
    }

    response = requests.get(url, params=params, timeout=10)
    data = response.json()

    if data.get("errcode") != 0:
        raise Exception(f"获取企业微信 access_token 失败: {data}")

    access_token = data["access_token"]
    expires_in = data.get("expires_in", 7200)

    _access_token_cache["access_token"] = access_token
    _access_token_cache["expires_at"] = now + expires_in - 300

    return access_token


def sync_kf_messages(kf_token: str, open_kfid: str, cursor: str = ""):
    access_token = get_access_token()

    if not cursor:
        cursor = _sync_cursor_cache.get(open_kfid, "")

    print("当前 open_kfid：", open_kfid)
    print("sync_msg 使用 cursor：", cursor)

    url = f"https://qyapi.weixin.qq.com/cgi-bin/kf/sync_msg?access_token={access_token}"

    payload = {
        "cursor": cursor,
        "token": kf_token,
        "limit": 5,
        "voice_format": 0,
        "open_kfid": open_kfid
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        data = response.json()
    except requests.exceptions.RequestException as exc:
        print("企业微信 sync_msg 失败：", exc)
        return {"errcode": -1, "errmsg": str(exc), "msg_list": []}
    except ValueError as exc:
        print("企业微信 sync_msg 失败：响应不是合法 JSON", exc)
        return {"errcode": -1, "errmsg": str(exc), "msg_list": []}

    if data.get("errcode", 0) != 0:
        print("企业微信 sync_msg 失败：", data.get("errcode"), data.get("errmsg"))
        return data

    next_cursor = data.get("next_cursor")
    print("sync_msg 返回 next_cursor：", next_cursor)
    if next_cursor:
        _sync_cursor_cache[open_kfid] = next_cursor


    return data


def send_kf_text_message(
    access_token: str,
    open_kfid: str,
    external_userid: str,
    content: str,
):
    if not content:
        print("企业微信发送失败：content 为空")
        return False

    content = content[:1800]

    url = f"https://qyapi.weixin.qq.com/cgi-bin/kf/send_msg?access_token={access_token}"

    payload = {
        "touser": external_userid,
        "open_kfid": open_kfid,
        "msgtype": "text",
        "text": {
            "content": content
        }
    }

    response = requests.post(url, json=payload, timeout=10)
    data = response.json()

    if data.get("errcode") == 0:
        return True

    print("企业微信发送失败：", data.get("errcode"), data.get("errmsg"))
    return False
