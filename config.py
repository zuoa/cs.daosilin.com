import os
from unittest.mock import DEFAULT

from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()

# Database configuration
DB_PATH = os.getenv('DB_PATH', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cs.db'))

AUTH_CODE = os.getenv('AUTH_CODE', '123')

CUP_NAME = os.getenv('CUP_NAME', '斗鱼CSGO鲨鱼major S1')
CUP_TEAM_NUM = int(os.getenv('CUP_TEAM_NUM', 8))

DEFAULT_CRAWL_PLAYER_IDS = os.getenv('DEFAULT_CRAWL_PLAYER_IDS', '76561198068647788')

# 称号系统配置
MAX_TITLES_PER_PLAYER = int(os.getenv('MAX_TITLES_PER_PLAYER', 10))  # 每个玩家最大称号数量
MAX_POSITIVE_TITLES = int(os.getenv('MAX_POSITIVE_TITLES', 7))  # 每个玩家最大正面称号数量
MAX_NEGATIVE_TITLES = int(os.getenv('MAX_NEGATIVE_TITLES', 3))  # 每个玩家最大反面称号数量
TITLE_PRIORITY_THRESHOLD = int(os.getenv('TITLE_PRIORITY_THRESHOLD', 2))  # 称号优先级阈值
