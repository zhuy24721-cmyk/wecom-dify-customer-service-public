import re
import time

from app.wecom_kf_client import get_access_token, send_kf_text_message, sync_kf_messages
import xml.etree.ElementTree as ET
from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from app.config import settings
from app.dify_client import call_dify
from app.notify_client import send_human_alert
from app.wecom_crypto import verify_signature, decrypt_message

_processed_msg_ids = set()
_warmed_open_kfids = set()
_server_start_time = int(time.time())
_MAX_PREHEAT_PAGES = 20
HUMAN_HANDOFF_MESSAGE = "已为您通知人工客服，请您稍等，工作人员会尽快处理。"

app = FastAPI()


def clean_ai_reply(text: str) -> str:
    if not text:
        return ""

    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def should_need_human(answer: str) -> bool:
    return (
        "转人工" in answer
        or "转人工客服" in answer
        or "需要人工客服" in answer
        or "请人工客服介入" in answer
    )


def normalize_send_time(send_time) -> int:
    try:
        send_time = int(send_time or 0)
    except (TypeError, ValueError):
        return 0

    if send_time and send_time > 1000000000000:
        return send_time // 1000

    return send_time


def preheat_kf_messages(kf_token: str, open_kfid: str) -> bool:
    cursor = ""
    last_cursor = None
    total_pages = 0
    total_messages = 0

    for _ in range(_MAX_PREHEAT_PAGES):
        sync_result = sync_kf_messages(kf_token, open_kfid, cursor=cursor)
        if sync_result.get("errcode", 0) != 0:
            return False

        msg_list = sync_result.get("msg_list", [])
        next_cursor = sync_result.get("next_cursor", "")

        total_pages += 1
        total_messages += len(msg_list)

        for msg in msg_list:
            msg_id = msg.get("msgid")
            if msg_id:
                _processed_msg_ids.add(msg_id)

        if not msg_list or not next_cursor or next_cursor == last_cursor:
            break

        last_cursor = next_cursor
        cursor = next_cursor

    _warmed_open_kfids.add(open_kfid)
    print(f"首次同步预热完成，已跳过历史消息，总页数：{total_pages}，总消息数：{total_messages}")
    return True


class CustomerMessage(BaseModel):
    user_id: str
    message: str


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/config-check")
def config_check():
    return {
        "safe_mode": settings.SAFE_MODE,
        "dify_api_key_loaded": bool(settings.DIFY_API_KEY),
        "dify_api_url_loaded": bool(settings.DIFY_API_URL),

        "wechat_corp_id_loaded": bool(settings.WECHAT_CORP_ID),
        "wechat_kf_secret_loaded": bool(settings.WECHAT_KF_SECRET),
        "wechat_token_loaded": bool(settings.WECHAT_TOKEN),
        "wechat_encoding_aes_key_loaded": bool(settings.WECHAT_ENCODING_AES_KEY),

        "wecom_group_webhook_loaded": bool(settings.WECOM_GROUP_WEBHOOK),
        "database_url_loaded": bool(settings.DATABASE_URL),
    }


@app.get("/dify-test")
def dify_test(message: str = "你好"):
    answer = call_dify(message=message, user_id="local-test-user")

    return {
        "message": message,
        "answer": answer,
    }


@app.post("/mock-customer-message")
def mock_customer_message(data: CustomerMessage):
    answer = call_dify(message=data.message, user_id=data.user_id)

    need_human = should_need_human(answer)
    alert_sent = False

    if need_human:
        alert_sent = send_human_alert(
            user_id=data.user_id,
            customer_message=data.message,
            ai_answer=answer,
        )
        print("需要人工介入，已通知企业微信群机器人")

    return {
        "user_id": data.user_id,
        "customer_message": data.message,
        "ai_answer": answer,
        "need_human": need_human,
        "alert_sent": alert_sent,
    }


@app.get("/wecom/callback", response_class=PlainTextResponse)
def wecom_callback_verify(
    msg_signature: str = Query(...),
    timestamp: str = Query(...),
    nonce: str = Query(...),
    echostr: str = Query(...),
):
    """
    企业微信微信客服 URL 验证接口。
    用于企业微信后台首次配置回调 URL 时验证服务器。
    """

    if not settings.WECHAT_TOKEN or not settings.WECHAT_ENCODING_AES_KEY:
        raise HTTPException(status_code=500, detail="WeCom callback config missing")

    is_valid = verify_signature(
        token=settings.WECHAT_TOKEN,
        timestamp=timestamp,
        nonce=nonce,
        encrypt=echostr,
        msg_signature=msg_signature,
    )

    if not is_valid:
        raise HTTPException(status_code=403, detail="Invalid signature")

    plain_text = decrypt_message(
        encoding_aes_key=settings.WECHAT_ENCODING_AES_KEY,
        encrypted_text=echostr,
    )

    return plain_text

@app.post("/wecom/callback")
async def wecom_callback(
    request: Request,
    msg_signature: str = Query(...),
    timestamp: str = Query(...),
    nonce: str = Query(...),
):
    body = await request.body()
    xml_text = body.decode("utf-8", errors="ignore")

    root = ET.fromstring(xml_text)
    encrypt = root.findtext("Encrypt")

    # print("收到企业微信 POST 回调 Encrypt：")
    # print(encrypt)

    is_valid = verify_signature(
        token=settings.WECHAT_TOKEN,
        timestamp=timestamp,
        nonce=nonce,
        encrypt=encrypt,
        msg_signature=msg_signature,
    )

    if not is_valid:
        raise HTTPException(status_code=403, detail="Invalid WeCom signature")

    plain_text = decrypt_message(
        encoding_aes_key=settings.WECHAT_ENCODING_AES_KEY,
        encrypted_text=encrypt,
    )

    # print("解密后的企业微信回调内容：")
    # print(plain_text)

    plain_root = ET.fromstring(plain_text)

    msg_type = plain_root.findtext("MsgType")
    event = plain_root.findtext("Event")
    kf_token = plain_root.findtext("Token")
    open_kfid = plain_root.findtext("OpenKfId")

    # print("解析后的企业微信事件：")
    # print("MsgType:", msg_type)
    # print("Event:", event)
    # print("Token:", kf_token)
    # print("OpenKfId:", open_kfid)

    if kf_token and open_kfid:
        if open_kfid not in _warmed_open_kfids:
            preheat_kf_messages(kf_token, open_kfid)
            return "success"

        sync_result = sync_kf_messages(kf_token, open_kfid)

        if sync_result.get("errcode", 0) != 0:
            return "success"

        msg_list = sync_result.get("msg_list", [])

        print("本次拉取到的消息数量：", len(msg_list))

        for msg in msg_list:
            msgtype = msg.get("msgtype")
            external_userid = msg.get("external_userid")
            msg_id = msg.get("msgid")
            send_time = normalize_send_time(msg.get("send_time", 0))
            content = msg.get("text", {}).get("content")

            if not msg_id:
                continue

            if msg_id in _processed_msg_ids:
                continue

            _processed_msg_ids.add(msg_id)

            if send_time < _server_start_time:
                continue

            if msgtype != "text":
                continue

            if not external_userid:
                continue

            if not content:
                continue

            print("客户ID：", external_userid)
            print("客户消息：", content)
            answer = call_dify(
                message=content,
                user_id=external_userid
            )
            answer = clean_ai_reply(answer)
            if not answer:
                print("Dify 无有效回复，已跳过")
                continue

            print("AI回复：", answer)

            need_human = should_need_human(answer)
            if need_human:
                send_human_alert(
                    user_id=external_userid,
                    customer_message=content,
                    ai_answer=answer,
                )
                print("需要人工介入，已通知企业微信群机器人")
                if settings.SAFE_MODE:
                    print("【安全模式】转人工提示暂未发送给微信客服客户")
                    continue

                access_token = get_access_token()
                sent = send_kf_text_message(
                    access_token=access_token,
                    open_kfid=open_kfid,
                    external_userid=external_userid,
                    content=HUMAN_HANDOFF_MESSAGE,
                )
                if sent:
                    print("转人工提示语已发送给微信客服客户")
                    print("实际发送内容：", HUMAN_HANDOFF_MESSAGE)
                continue

            if settings.SAFE_MODE:
                print("【安全模式】AI回复暂未发送给微信客服客户")
                continue

            access_token = get_access_token()
            sent = send_kf_text_message(
                access_token=access_token,
                open_kfid=open_kfid,
                external_userid=external_userid,
                content=answer,
            )
            if sent:
                print("AI回复已发送给微信客服客户")

    return "success"


@app.get("/wecom-token-test")
def wecom_token_test():
    token = get_access_token()

    return {
        "access_token_loaded": bool(token),
        "access_token_preview": token[:10] + "..." if token else ""
    }
