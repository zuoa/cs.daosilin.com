"""Admin session login with image captcha."""
import io
import os
import random
import secrets
import string
import time
from datetime import datetime
from functools import wraps

from flask import Response, current_app, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from ajlog import logger
from config import REDIS_URL
from database import AdminUser, Config
from utils import error

CAPTCHA_LEN = 4
CAPTCHA_TTL = 180
MAX_FAILS = 8
LOCK_SECONDS = 600
EXTERNAL_TOKEN_HASH_KEY = 'external_api_token_hash'
EXTERNAL_TOKEN_HINT_KEY = 'external_api_token_hint'
EXTERNAL_TOKEN_MIN_LENGTH = 32

_redis = None


def _get_redis():
    global _redis
    if _redis is False:
        return None
    if _redis is not None:
        return _redis
    if not REDIS_URL:
        _redis = False
        return None
    try:
        import redis
        _redis = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        _redis.ping()
        return _redis
    except Exception as e:
        logger.warning(f"Redis 不可用，登录限流回退到 session: {e}")
        _redis = False
        return None


def current_admin():
    return session.get('admin_user')


def login_admin(user: AdminUser):
    session['admin_user'] = user.username
    session.pop('login_fails', None)
    session.pop('login_lock_until', None)
    user.last_login_at = datetime.now()
    user.save()


def logout_admin():
    session.pop('admin_user', None)


def _fail_key():
    return f"login_fail:{request.remote_addr or 'unknown'}"


def _lock_key():
    return f"login_lock:{request.remote_addr or 'unknown'}"


def login_locked():
    r = _get_redis()
    if r:
        ttl = r.ttl(_lock_key())
        return ttl > 0, max(ttl, 0)
    until = session.get('login_lock_until') or 0
    remain = int(until - time.time())
    return remain > 0, max(remain, 0)


def record_login_fail():
    r = _get_redis()
    if r:
        n = r.incr(_fail_key())
        r.expire(_fail_key(), LOCK_SECONDS)
        if n >= MAX_FAILS:
            r.setex(_lock_key(), LOCK_SECONDS, '1')
        return n
    n = int(session.get('login_fails') or 0) + 1
    session['login_fails'] = n
    if n >= MAX_FAILS:
        session['login_lock_until'] = time.time() + LOCK_SECONDS
    return n


def clear_login_fail():
    r = _get_redis()
    if r:
        r.delete(_fail_key(), _lock_key())
    session.pop('login_fails', None)
    session.pop('login_lock_until', None)


def verify_password(username, password) -> AdminUser | None:
    user = AdminUser.get_or_none(AdminUser.username == username)
    if not user or not check_password_hash(user.password_hash, password or ''):
        return None
    return user


def _font(size=36):
    from PIL import ImageFont
    candidates = [
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
        '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
        '/System/Library/Fonts/Supplemental/Arial Bold.ttf',
        '/System/Library/Fonts/Supplemental/Arial.ttf',
        '/Library/Fonts/Arial.ttf',
    ]
    for path in candidates:
        if os.path.isfile(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def generate_captcha_image() -> bytes:
    from PIL import Image, ImageDraw, ImageFilter
    chars = string.ascii_uppercase + string.digits
    code = ''.join(random.choice(chars) for _ in range(CAPTCHA_LEN))
    session['captcha_code'] = code
    session['captcha_at'] = time.time()

    width, height = 140, 48
    img = Image.new('RGB', (width, height), (18, 24, 32))
    draw = ImageDraw.Draw(img)
    font = _font(32)
    for _ in range(8):
        draw.line(
            [(random.randint(0, width), random.randint(0, height)),
             (random.randint(0, width), random.randint(0, height))],
            fill=(40, 70, 90), width=1,
        )
    x = 12
    for ch in code:
        y = random.randint(4, 12)
        draw.text((x, y), ch, font=font, fill=(180, 230, 160))
        x += 30
    for _ in range(80):
        draw.point((random.randint(0, width - 1), random.randint(0, height - 1)),
                   fill=(80, 120, 90))
    img = img.filter(ImageFilter.SMOOTH)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def captcha_ok(value: str) -> bool:
    expected = (session.get('captcha_code') or '').strip().upper()
    issued = session.get('captcha_at') or 0
    session.pop('captcha_code', None)
    session.pop('captcha_at', None)
    if not expected or (time.time() - issued) > CAPTCHA_TTL:
        return False
    return (value or '').strip().upper() == expected


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_admin():
            if request.path.startswith('/api/'):
                return error(401, "未登录"), 401
            nxt = request.full_path if request.query_string else request.path
            return redirect(url_for('admin_login', next=nxt))
        return fn(*args, **kwargs)
    return wrapper


def external_api_token_status():
    """Return safe token metadata without ever exposing a stored token."""
    environment_token = (current_app.config.get('EXTERNAL_API_TOKEN') or '').strip()
    database_hash = Config.get_value(EXTERNAL_TOKEN_HASH_KEY) or ''
    database_hint = Config.get_value(EXTERNAL_TOKEN_HINT_KEY) or ''
    if environment_token:
        return {
            'configured': True,
            'source': 'environment',
            'hint': f'••••••••{environment_token[-4:]}',
            'environment_locked': True,
            'database_fallback_configured': bool(database_hash),
        }
    if database_hash:
        return {
            'configured': True,
            'source': 'database',
            'hint': f'••••••••{database_hint}' if database_hint else '••••••••',
            'environment_locked': False,
            'database_fallback_configured': True,
        }
    return {
        'configured': False,
        'source': 'none',
        'hint': '',
        'environment_locked': False,
        'database_fallback_configured': False,
    }


def save_external_api_token(token):
    if not isinstance(token, str):
        raise ValueError('API token 必须是字符串')
    token = token.strip()
    if len(token) < EXTERNAL_TOKEN_MIN_LENGTH:
        raise ValueError(f'API token 至少需要 {EXTERNAL_TOKEN_MIN_LENGTH} 个字符')
    Config.set_value(EXTERNAL_TOKEN_HASH_KEY, generate_password_hash(token))
    Config.set_value(EXTERNAL_TOKEN_HINT_KEY, token[-4:])


def revoke_database_external_api_token():
    Config.delete().where(Config.key.in_([
        EXTERNAL_TOKEN_HASH_KEY,
        EXTERNAL_TOKEN_HINT_KEY,
    ])).execute()


def external_api_token_required(fn):
    """Require the configured token for read-only external API routes."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        environment_token = (current_app.config.get('EXTERNAL_API_TOKEN') or '').strip()
        stored_hash = '' if environment_token else (Config.get_value(EXTERNAL_TOKEN_HASH_KEY) or '')
        if not environment_token and not stored_hash:
            logger.error('对外 API token 未配置，接口已关闭')
            return error(503, "对外 API 未配置"), 503

        authorization = (request.headers.get('Authorization') or '').strip()
        scheme, separator, credentials = authorization.partition(' ')
        provided = credentials.strip() if separator and scheme.lower() == 'bearer' else ''
        if not provided:
            provided = (request.headers.get('X-API-Token') or '').strip()

        valid = (
            secrets.compare_digest(provided, environment_token)
            if environment_token else bool(provided and check_password_hash(stored_hash, provided))
        )
        if not valid:
            response = error(401, "无效或缺失的 API token")
            response.headers['WWW-Authenticate'] = 'Bearer'
            return response, 401
        return fn(*args, **kwargs)
    return wrapper


def captcha_response():
    png = generate_captcha_image()
    resp = Response(png, mimetype='image/png')
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
    return resp
