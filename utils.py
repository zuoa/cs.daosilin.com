import os
import time
from datetime import datetime, timedelta

from flask import jsonify
from flask.cli import load_dotenv
from openai import OpenAI

load_dotenv()


def get_play_day(end_time: str, hours_offset: int = 0):
    # 减去3个小时算日期， end_time：2025-01-01 02:00:00
    if not end_time:
        return None
    try:
        dt = datetime.strptime(end_time, '%Y-%m-%d %H:%M:%S')
        dt_adjusted = dt - timedelta(hours=hours_offset)
        return dt_adjusted.strftime('%Y%m%d')
    except Exception as e:
        print(f"Error parsing date: {e}")
        return None


def json_datetime_handler(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def llm_chat(prompt):
    llm_base_url = os.environ.get('LLM_BASE_URL', 'https://api.deepseek.com/v1')
    llm_model_name = os.environ.get('LLM_MODEL_NAME', 'deepseek-chat')
    llm_api_key = os.environ.get('LLM_API_KEY', '')

    messages = []
    messages.append({"role": "user", "content": prompt})

    data = {
        "model": llm_model_name,
        "messages": messages,
        "stream": False
    }
    print(data)
    try:
        client = OpenAI(
            base_url=llm_base_url,
            api_key=llm_api_key,
        )

        chat_completion = client.chat.completions.create(**data)
        return chat_completion.choices[0].message.content

    except Exception as e:
        print(e)

    return ''


def ts2str(ts):
    """将时间戳转换为字符串"""
    if not ts:
        return ''
    try:
        dt = datetime.fromtimestamp(ts / 1000)
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except Exception as e:
        print(f"Error converting timestamp: {e}")
        return ''



def resp_data(data=None, code=0, message="success"):
    wrapper_data = {
        "success": code == 0,
        "code": code,
        "data": data,
        "message": message,
        "t": int(time.time() * 1000)
    }
    return jsonify(wrapper_data)


def resp_page_list(list_, total, page):
    data = {
        "list": list_,
        "total": total,
        "page": page,
    }

    return resp_data(data)


def success(data=None):
    return resp_data(data)


def error(code, message):
    return resp_data(code=code, message=message)

