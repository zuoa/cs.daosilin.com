import os
from datetime import datetime, timedelta

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


if __name__ == '__main__':
    print(decode_zip_base64(
        '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'))
