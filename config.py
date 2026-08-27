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

ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', '')

# 称号系统配置
MAX_TITLES_PER_PLAYER = int(os.getenv('MAX_TITLES_PER_PLAYER', 10))  # 每个玩家最大称号数量
MAX_POSITIVE_TITLES = int(os.getenv('MAX_POSITIVE_TITLES', 7))  # 每个玩家最大正面称号数量
MAX_NEGATIVE_TITLES = int(os.getenv('MAX_NEGATIVE_TITLES', 3))  # 每个玩家最大反面称号数量
TITLE_PRIORITY_THRESHOLD = int(os.getenv('TITLE_PRIORITY_THRESHOLD', 2))  # 称号优先级阈值
