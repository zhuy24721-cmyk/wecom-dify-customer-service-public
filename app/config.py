import os
from dotenv import load_dotenv

# 读取项目根目录下的 .env 文件
load_dotenv()


class Settings:
    SAFE_MODE = os.getenv("SAFE_MODE", "true").lower() in ("1", "true", "yes", "on")

    # Dify configuration
    DIFY_API_KEY = os.getenv("DIFY_API_KEY", "")
    DIFY_API_URL = os.getenv("DIFY_API_URL", "")

    # WeCom customer service configuration
    WECHAT_CORP_ID = os.getenv("WECHAT_CORP_ID", "")
    WECHAT_KF_SECRET = os.getenv("WECHAT_KF_SECRET", "")
    WECHAT_TOKEN = os.getenv("WECHAT_TOKEN", "")
    WECHAT_ENCODING_AES_KEY = os.getenv("WECHAT_ENCODING_AES_KEY", "")

    # WeCom group robot
    WECOM_GROUP_WEBHOOK = os.getenv("WECOM_GROUP_WEBHOOK", "")

    # Database
    DATABASE_URL = os.getenv("DATABASE_URL", "")


settings = Settings()
