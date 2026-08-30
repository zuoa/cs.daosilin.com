import os
from unittest.mock import DEFAULT

from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()

# Database configuration
DB_PATH = os.getenv('DB_PATH', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cs.db'))
DATABASE_URL = (os.getenv('DATABASE_URL') or '').strip()
HISTORY_SQL_PATH = os.getenv(
    'HISTORY_SQL_PATH',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bootstrap', 'cs_history.sql'),
)

REDIS_URL = (os.getenv('REDIS_URL') or '').strip()
SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-change-me')
SITE_NAME = os.getenv('SITE_NAME', '熊掌CS Major')

# DeepSeek-backed player season summaries. Credentials stay in the deployment
# environment and are never persisted by the application.
LLM_API_KEY = (os.getenv('LLM_API_KEY') or '').strip()
LLM_BASE_URL = (os.getenv('LLM_BASE_URL') or 'https://api.deepseek.com').strip()
LLM_MODEL_NAME = (os.getenv('LLM_MODEL_NAME') or 'deepseek-v4-flash').strip()
LLM_REQUEST_TIMEOUT = int(os.getenv('LLM_REQUEST_TIMEOUT', '45'))
PLAYER_SUMMARY_PROMPT_VERSION = (
    os.getenv('PLAYER_SUMMARY_PROMPT_VERSION') or 'v1'
).strip()

ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', '')

# Optional environment override for the external API token. When empty, an
# administrator can configure a database-backed token from the control panel.
EXTERNAL_API_TOKEN = (os.getenv('EXTERNAL_API_TOKEN') or '').strip()

# WMPVP crawl credential from .env. A database-encrypted credential saved in
# the admin panel takes precedence for Demo downloading.
WMPVP_ACCESS_TOKEN = (os.getenv('WMPVP_ACCESS_TOKEN') or '').strip()
WMPVP_STEAM_ID = (os.getenv('WMPVP_STEAM_ID') or '').strip()

# Demo analysis is isolated from the normal crawl path. A Fernet key is
# required before the admin panel is allowed to persist a PWA access token.
DEMO_CREDENTIAL_ENCRYPTION_KEY = (
    os.getenv('DEMO_CREDENTIAL_ENCRYPTION_KEY') or ''
).strip()
DEMO_STORAGE_PATH = os.getenv(
    'DEMO_STORAGE_PATH',
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'demos'),
)
DEMO_MAX_BYTES = int(os.getenv('DEMO_MAX_BYTES', str(1024 * 1024 * 1024)))
DEMO_ANALYZER_PATH = os.getenv('DEMO_ANALYZER_PATH', '/usr/local/bin/cs-demo-analyzer')
DEMO_ANALYZER_TIMEOUT = int(os.getenv('DEMO_ANALYZER_TIMEOUT', '840'))
DEMO_METRIC_VERSION = os.getenv('DEMO_METRIC_VERSION', 'v1').strip() or 'v1'
DEMO_BACKFILL_DAYS = int(os.getenv('DEMO_BACKFILL_DAYS', '30'))

# 完美段位每天定时刷新。Cron 小时列表使用逗号分隔，例如 2,8,14,20。
PERFECT_RANK_REFRESH_HOURS = (
    os.getenv('PERFECT_RANK_REFRESH_HOURS') or '2,8,14,20'
).strip()
PERFECT_RANK_REQUEST_INTERVAL = float(os.getenv('PERFECT_RANK_REQUEST_INTERVAL', '0.2'))

# 称号系统配置
MAX_TITLES_PER_PLAYER = int(os.getenv('MAX_TITLES_PER_PLAYER', 3))  # 主荣誉、打法、故事各最多一个
MAX_POSITIVE_TITLES = int(os.getenv('MAX_POSITIVE_TITLES', 3))  # 兼容旧配置
MAX_NEGATIVE_TITLES = int(os.getenv('MAX_NEGATIVE_TITLES', 0))  # 赛季档案不展示羞辱性称号
TITLE_PRIORITY_THRESHOLD = int(os.getenv('TITLE_PRIORITY_THRESHOLD', 2))  # 称号优先级阈值
