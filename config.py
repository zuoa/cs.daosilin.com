import os
from unittest.mock import DEFAULT

from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()

# Database configuration
DB_PATH = os.getenv('DB_PATH', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cs.db'))


CUP_NAME = os.getenv('CUP_NAME', '斗鱼CSGO鲨鱼major S1')
CUP_TEAM_NUM = int(os.getenv('CUP_TEAM_NUM', 8))

DEFAULT_CRAWL_PLAYER_IDS = os.getenv('DEFAULT_CRAWL_PLAYER_IDS', '76561198068647788')
