"""Validate, segment, and persist player portraits."""
import base64
import hashlib
import io
import math
import os
import shutil
import tempfile
import threading
import time
from pathlib import Path

import requests
from PIL import Image, ImageOps, UnidentifiedImageError

from config import (BAIDU_BODY_API_KEY, BAIDU_BODY_SECRET_KEY,
                    PLAYER_PORTRAIT_API_TIMEOUT, PLAYER_PORTRAIT_MAX_BYTES,
                    PLAYER_PORTRAIT_STORAGE_PATH)


ALLOWED_FORMATS = {'JPEG', 'PNG', 'WEBP'}
MAX_IMAGE_PIXELS = 40_000_000
MAX_API_EDGE = 4096
MAX_API_BYTES = 2_700_000
_token_lock = threading.Lock()
_token_value = ''
_token_expires_at = 0.0


class PortraitError(RuntimeError):
    pass


def configured():
    return bool(BAIDU_BODY_API_KEY and BAIDU_BODY_SECRET_KEY)


def portrait_public_url(relative_path):
    if not relative_path:
        return None
    filename = Path(relative_path).name
    return f'/media/player-portraits/{filename}'


def portrait_payload(player):
    value = player.get if isinstance(player, dict) else lambda key, default=None: getattr(player, key, default)
    cutout = value('portrait_cutout')
    if not cutout:
        return None
    return {
        'url': portrait_public_url(cutout),
        'scale': float(value('portrait_scale', 1.0) or 1.0),
        'offset_x': float(value('portrait_offset_x', 0.0) or 0.0),
        'offset_y': float(value('portrait_offset_y', 0.0) or 0.0),
    }


def clamp_transform(scale, offset_x, offset_y):
    try:
        values = float(scale), float(offset_x), float(offset_y)
    except (TypeError, ValueError):
        raise PortraitError('人物构图参数无效')
    if not all(math.isfinite(value) for value in values):
        raise PortraitError('人物构图参数无效')
    scale_value = min(2.2, max(0.75, values[0]))
    offset_x_value = min(50.0, max(-50.0, values[1]))
    offset_y_value = min(50.0, max(-50.0, values[2]))
    return scale_value, offset_x_value, offset_y_value


def _read_upload(file_storage):
    if not file_storage or not getattr(file_storage, 'filename', ''):
        raise PortraitError('请选择人物照片')
    data = file_storage.stream.read(PLAYER_PORTRAIT_MAX_BYTES + 1)
    if not data:
        raise PortraitError('上传的照片为空')
    if len(data) > PLAYER_PORTRAIT_MAX_BYTES:
        limit_mb = PLAYER_PORTRAIT_MAX_BYTES // (1024 * 1024)
        raise PortraitError(f'人物照片不能超过 {limit_mb}MB')
    return data


def _normalise_image(data):
    try:
        image = Image.open(io.BytesIO(data))
        if image.width * image.height > MAX_IMAGE_PIXELS:
            raise PortraitError('图片像素过大，请压缩后重试')
        image.load()
    except PortraitError:
        raise
    except Image.DecompressionBombError as exc:
        raise PortraitError('图片像素过大，请压缩后重试') from exc
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise PortraitError('仅支持有效的 JPG、PNG 或 WebP 图片') from exc
    if image.format not in ALLOWED_FORMATS:
        raise PortraitError('仅支持 JPG、PNG 或 WebP 图片')
    image = ImageOps.exif_transpose(image)
    if max(image.size) > MAX_API_EDGE:
        image.thumbnail((MAX_API_EDGE, MAX_API_EDGE), Image.Resampling.LANCZOS)
    rgb = Image.new('RGB', image.size, 'white')
    if image.mode in ('RGBA', 'LA'):
        rgb.paste(image.convert('RGBA'), mask=image.convert('RGBA').getchannel('A'))
    else:
        rgb.paste(image.convert('RGB'))
    output = io.BytesIO()
    for quality in (90, 84, 78, 72, 66):
        output.seek(0)
        output.truncate(0)
        rgb.save(output, format='JPEG', quality=quality, optimize=True)
        if output.tell() <= MAX_API_BYTES:
            break
    if output.tell() > MAX_API_BYTES:
        ratio = (MAX_API_BYTES / output.tell()) ** 0.5
        resized = rgb.resize(
            (max(50, int(rgb.width * ratio)), max(50, int(rgb.height * ratio))),
            Image.Resampling.LANCZOS,
        )
        output.seek(0)
        output.truncate(0)
        resized.save(output, format='JPEG', quality=76, optimize=True)
    return output.getvalue()


def _access_token(session=requests):
    global _token_value, _token_expires_at
    if not configured():
        raise PortraitError('人像分割服务尚未配置，请设置百度智能云 API Key')
    now = time.time()
    if _token_value and now < _token_expires_at:
        return _token_value
    with _token_lock:
        now = time.time()
        if _token_value and now < _token_expires_at:
            return _token_value
        try:
            response = session.post(
                'https://aip.baidubce.com/oauth/2.0/token',
                params={
                    'grant_type': 'client_credentials',
                    'client_id': BAIDU_BODY_API_KEY,
                    'client_secret': BAIDU_BODY_SECRET_KEY,
                },
                timeout=PLAYER_PORTRAIT_API_TIMEOUT,
            )
            response.raise_for_status()
            result = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise PortraitError('无法连接人像分割服务，请稍后重试') from exc
        token = result.get('access_token')
        if not token:
            raise PortraitError('百度智能云鉴权失败，请检查 API Key')
        _token_value = token
        _token_expires_at = now + max(60, int(result.get('expires_in') or 2592000) - 300)
        return token


def _segment(image_bytes, session=requests):
    token = _access_token(session=session)
    try:
        response = session.post(
            'https://aip.baidubce.com/rest/2.0/image-classify/v1/body_seg',
            params={'access_token': token},
            data={'image': base64.b64encode(image_bytes).decode('ascii'), 'type': 'foreground'},
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            timeout=PLAYER_PORTRAIT_API_TIMEOUT,
        )
        response.raise_for_status()
        result = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise PortraitError('人像抠图请求失败，请稍后重试') from exc
    if result.get('error_code'):
        message = result.get('error_msg') or '未知错误'
        raise PortraitError(f'人像抠图失败：{message}')
    encoded = result.get('foreground')
    if not encoded:
        raise PortraitError('未识别到清晰人物，请换一张照片重试')
    try:
        decoded = base64.b64decode(encoded, validate=True)
        image = Image.open(io.BytesIO(decoded))
        if image.width * image.height > MAX_IMAGE_PIXELS:
            raise PortraitError('人像分割服务返回的图片像素过大')
        image = image.convert('RGBA')
        image.load()
    except PortraitError:
        raise
    except Image.DecompressionBombError as exc:
        raise PortraitError('人像分割服务返回的图片像素过大') from exc
    except (ValueError, OSError, UnidentifiedImageError) as exc:
        raise PortraitError('人像分割服务返回了无效图片') from exc
    alpha = image.getchannel('A')
    if not alpha.getbbox():
        raise PortraitError('未识别到清晰人物，请换一张照片重试')
    output = io.BytesIO()
    image.save(output, format='WEBP', lossless=True, method=4)
    return output.getvalue()


def save_portrait(player_id, file_storage, session=requests):
    source = _normalise_image(_read_upload(file_storage))
    cutout = _segment(source, session=session)
    player_digest = hashlib.sha256(str(player_id).encode('utf-8')).hexdigest()[:12]
    content_digest = hashlib.sha256(cutout).hexdigest()[:12]
    digest = f'{player_digest}-{content_digest}'
    root = Path(PLAYER_PORTRAIT_STORAGE_PATH)
    root.mkdir(parents=True, exist_ok=True)
    original_name = f'{digest}-original.jpg'
    cutout_name = f'{digest}-cutout.webp'
    temp_dir = Path(tempfile.mkdtemp(prefix='portrait-', dir=str(root)))
    try:
        original_temp = temp_dir / original_name
        cutout_temp = temp_dir / cutout_name
        original_temp.write_bytes(source)
        cutout_temp.write_bytes(cutout)
        os.replace(original_temp, root / original_name)
        os.replace(cutout_temp, root / cutout_name)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
    return original_name, cutout_name


def delete_portrait_files(*relative_paths):
    root = Path(PLAYER_PORTRAIT_STORAGE_PATH).resolve()
    for relative_path in relative_paths:
        if not relative_path:
            continue
        candidate = (root / Path(relative_path).name).resolve()
        if candidate.parent == root:
            try:
                candidate.unlink()
            except FileNotFoundError:
                pass


def portrait_file_path(filename):
    if not filename or Path(filename).name != filename:
        return None
    root = Path(PLAYER_PORTRAIT_STORAGE_PATH).resolve()
    candidate = (root / filename).resolve()
    return candidate if candidate.parent == root and candidate.is_file() else None
