"""Resilient response caching and cross-process cache invalidation."""

import functools
import hashlib
import json
import secrets
import threading
import time
from typing import Callable, Iterable

from flask import make_response, request
from flask_caching import Cache

from ajlog import logger
from config import REDIS_URL


cache = Cache()
_local_versions = {}
_local_lock = threading.RLock()
_redis = None


def init_cache(app) -> None:
    config = {
        'CACHE_DEFAULT_TIMEOUT': 900,
        'CACHE_KEY_PREFIX': 'cs:',
    }
    if REDIS_URL:
        config.update({
            'CACHE_TYPE': 'RedisCache',
            'CACHE_REDIS_URL': REDIS_URL,
        })
    else:
        config['CACHE_TYPE'] = 'SimpleCache'
    cache.init_app(app, config=config)


def _redis_client():
    global _redis
    if not REDIS_URL:
        return None
    if _redis is None:
        from redis import Redis
        _redis = Redis.from_url(
            REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=0.2,
            socket_timeout=0.2,
        )
    return _redis


def _version_key(scope: str) -> str:
    return f'cs:version:{scope}'


def _scope_version(scope: str) -> str:
    client = _redis_client()
    if client is not None:
        try:
            return client.get(_version_key(scope)) or '0'
        except Exception as exc:
            logger.warning(f'Redis 版本读取失败，跳过响应缓存: {exc}')
            return secrets.token_hex(8)
    with _local_lock:
        return _local_versions.get(scope, '0')


def invalidate_cache(*scopes: str) -> None:
    """Invalidate logical scopes without scanning or clearing unrelated keys."""
    normalized = tuple(dict.fromkeys(str(scope) for scope in scopes if scope))
    if not normalized:
        return
    values = {scope: secrets.token_hex(8) for scope in normalized}
    client = _redis_client()
    if client is not None:
        try:
            with client.pipeline(transaction=False) as pipeline:
                for scope, value in values.items():
                    pipeline.set(_version_key(scope), value)
                pipeline.execute()
            return
        except Exception as exc:
            # Database writes must never fail merely because Redis is unavailable.
            logger.warning(f'Redis 缓存失效失败，等待 TTL 兜底: {exc}')
            return
    with _local_lock:
        _local_versions.update(values)


def season_scope(cup_name: str) -> str:
    return f'season:{cup_name}'


def invalidate_season(cup_name: str, *, seasons=False, external=True) -> None:
    scopes = [season_scope(cup_name)] if cup_name else []
    if seasons:
        scopes.append('seasons')
    if external:
        scopes.append('external')
    invalidate_cache(*scopes)


def invalidate_profiles(*, external=True) -> None:
    scopes = ['profiles']
    if external:
        scopes.append('external')
    invalidate_cache(*scopes)


def _resolved_scopes(scope_resolver) -> tuple[str, ...]:
    scopes = scope_resolver() if callable(scope_resolver) else scope_resolver
    if isinstance(scopes, str):
        scopes = (scopes,)
    return tuple(str(scope) for scope in (scopes or ()) if scope)


def _response_key(scopes: Iterable[str]) -> str:
    query = sorted((key, value) for key, values in request.args.lists() for value in values)
    identity = json.dumps({
        'method': request.method,
        'path': request.path,
        'query': query,
        'versions': [(scope, _scope_version(scope)) for scope in scopes],
    }, ensure_ascii=False, separators=(',', ':'), sort_keys=True)
    return 'api-response:' + hashlib.sha256(identity.encode('utf-8')).hexdigest()


def _safe_get(key):
    try:
        return cache.get(key)
    except Exception as exc:
        logger.warning(f'Redis 响应缓存读取失败，回退数据库: {exc}')
        return None


def _safe_set(key, value, timeout):
    try:
        cache.set(key, value, timeout=timeout)
    except Exception as exc:
        logger.warning(f'Redis 响应缓存写入失败: {exc}')


def _cached_flask_response(stored, started):
    body, status, headers = stored
    response = make_response(body, status)
    for name, value in headers:
        response.headers[name] = value
    response.headers['X-Cache'] = 'HIT'
    response.headers['Server-Timing'] = (
        f'cache;dur={(time.perf_counter() - started) * 1000:.2f}'
    )
    return response


def _acquire_fill_lock(key):
    client = _redis_client()
    if client is None:
        return None, False
    token = secrets.token_hex(12)
    try:
        acquired = client.set(f'cs:fill-lock:{key}', token, nx=True, ex=10)
        return (token if acquired else None), not bool(acquired)
    except Exception:
        return None, False


def _release_fill_lock(key, token):
    if not token:
        return
    client = _redis_client()
    if client is None:
        return
    script = (
        "if redis.call('get', KEYS[1]) == ARGV[1] then "
        "return redis.call('del', KEYS[1]) else return 0 end"
    )
    try:
        client.eval(script, 1, f'cs:fill-lock:{key}', token)
    except Exception:
        pass


def cached_response(timeout: int = 900, scopes=()):
    """Cache successful GET responses while preserving auth and response headers.

    This decorator belongs inside authentication decorators so authorization is
    always evaluated before a cached response can be returned.
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if request.method != 'GET':
                return func(*args, **kwargs)
            key = _response_key(_resolved_scopes(scopes))
            started = time.perf_counter()
            stored = _safe_get(key)
            if stored is not None:
                return _cached_flask_response(stored, started)

            lock_token, contended = _acquire_fill_lock(key)
            if contended:
                # Let the winning worker fill the key; bound the wait so a dead
                # worker or slow database never stalls the request indefinitely.
                for _ in range(5):
                    time.sleep(0.03)
                    stored = _safe_get(key)
                    if stored is not None:
                        return _cached_flask_response(stored, started)
            try:
                response = make_response(func(*args, **kwargs))
                response.headers['X-Cache'] = 'MISS'
                response.headers['Server-Timing'] = (
                    f'app;dur={(time.perf_counter() - started) * 1000:.2f}'
                )
                if 200 <= response.status_code < 300:
                    preserved = [
                        (name, value) for name, value in response.headers.items()
                        if name.lower() in ('content-type', 'cache-control', 'www-authenticate')
                    ]
                    _safe_set(key, (response.get_data(), response.status_code, preserved), timeout)
                return response
            finally:
                _release_fill_lock(key, lock_token)
        return wrapper
    return decorator
