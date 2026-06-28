# 企业微信微信客服接入 Dify AI 客服

这是一个 FastAPI 项目，用于把企业微信微信客服真实客户消息接入 Dify，并根据 Dify 回复在安全模式下打印 AI 回复或提醒人工介入。`SAFE_MODE=true` 是默认安全测试模式，只有设置为 `SAFE_MODE=false` 才会真实自动回复客户。

正式链路：

```text
客户微信客服消息 -> FastAPI /wecom/callback -> 企业微信 sync_msg -> Dify
-> 清洗 AI 回复 -> SAFE_MODE 控制自动回复 / 企业微信群机器人人工提醒
```

## 目录结构

```text
wecom-dify-customer-service/
├─ app/
│  ├─ main.py
│  ├─ config.py
│  ├─ dify_client.py
│  ├─ notify_client.py
│  ├─ wecom_crypto.py
│  └─ wecom_kf_client.py
├─ .env
├─ .env.example
├─ requirements.txt
└─ README.md
```

## 安装依赖

```bash
pip install -r requirements.txt
```

## 配置环境变量

项目会从根目录 `.env` 文件读取配置。可以参考 `.env.example`：

```env
SAFE_MODE=true
DIFY_API_KEY=
DIFY_API_URL=https://api.dify.ai/v1/chat-messages

WECHAT_CORP_ID=
WECHAT_KF_SECRET=
WECHAT_TOKEN=
WECHAT_ENCODING_AES_KEY=

WECOM_GROUP_WEBHOOK=
DATABASE_URL=
```

说明：

- `SAFE_MODE`：默认 `true`，只打印 AI 回复，不真实发送客户；设为 `false` 才会调用微信客服接口自动回复客户。
- `DIFY_API_KEY`：Dify 应用 API Key。
- `DIFY_API_URL`：Dify Chat Messages API 地址。
- `WECHAT_CORP_ID`：企业微信企业 ID。
- `WECHAT_KF_SECRET`：微信客服 Secret。
- `WECHAT_TOKEN`：企业微信回调 Token。
- `WECHAT_ENCODING_AES_KEY`：企业微信回调 EncodingAESKey。
- `WECOM_GROUP_WEBHOOK`：企业微信群机器人 Webhook，用于人工介入提醒。

## 启动项目

```bash
python -m uvicorn app.main:app --reload
```

本地调试企业微信回调时，可以用 cpolar 暴露 8000 端口：

```bash
cpolar http 8000
```

然后把 cpolar 提供的公网地址配置到企业微信微信客服回调 URL：

```text
https://你的-cpolar-域名/wecom/callback
```

## 测试步骤

1. 本地健康检查：

```text
GET http://127.0.0.1:8000/health
```

2. 配置检查：

```text
GET http://127.0.0.1:8000/config-check
```

确认 Dify、企业微信、群机器人相关配置显示为已加载，并确认 `safe_mode` 当前值。

3. 企业微信 access_token 检查：

```text
GET http://127.0.0.1:8000/wecom-token-test
```

4. 公网健康检查：

```text
GET https://你的-cpolar-域名/health
```

5. 企业微信后台验证回调 URL：

在企业微信微信客服后台配置 `/wecom/callback`，确认 GET 验证通过。

6. 第一次真实微信客服消息预热：

- 客户在微信客服入口发送第一条文本消息。
- FastAPI 会执行首次同步预热，不调用 Dify，不发送客户。
- 终端应打印：

```text
当前 open_kfid：
sync_msg 使用 cursor：
sync_msg 返回 next_cursor：
首次同步预热完成，已跳过历史消息，总页数：x，总消息数：y
```

7. 第二次真实微信客服消息进入 Dify：

- 客户再发送一条新的文本消息。
- FastAPI 终端应打印：

```text
当前 open_kfid：
sync_msg 使用 cursor：
sync_msg 返回 next_cursor：
本次拉取到的消息数量：
客户ID：
客户消息：
AI回复：
【安全模式】AI回复暂未发送给微信客服客户
```

此时客户窗口不会收到 AI 回复。

8. 最后关闭安全模式真实发送：

- 确认测试稳定后，在 `.env` 中设置：

```env
SAFE_MODE=false
```

- 重启 FastAPI。
- 再发一条新的微信客服消息，终端应打印：

```text
AI回复已发送给微信客服客户
```

- 如果 Dify 回复命中转人工关键词，终端应打印：

```text
需要人工介入，已通知企业微信群机器人
```

并且企业微信群机器人会收到提醒。

## 运行说明

- 当前 V1 使用内存 `_processed_msg_ids` 做消息去重，服务重启后内存会清空。
- 当前 V1 使用企业微信 `sync_msg` 的 cursor 缓存减少重复拉取，缓存也在内存中。
- 服务启动后，某个 `open_kfid` 第一次同步只做预热：保存 cursor、标记历史 `msgid`，不调用 Dify、不发送客户。
- `SAFE_MODE=true` 时不会真实调用企业微信客服发送接口给客户。
- `SAFE_MODE=false` 时才会调用企业微信客服发送接口真实回复客户。
- 正式长期部署建议后续把已处理 `msgid` 或 cursor 存到 Redis / 数据库。
