#!/usr/bin/env python3
"""Long-running Baokemeng Socket.IO listener that stores finalized drafts."""
from __future__ import annotations

import hashlib
import json
import random
import signal
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any
from urllib.parse import urlencode, urlsplit

import requests
import websocket

from ajlog import logger
from baokemeng_service import DraftTracker, DraftValidationError, persist_final_draft
from cache_service import invalidate_cache
from config import BAOKEMENG_PASSWORD, BAOKEMENG_SERVER, BAOKEMENG_STABLE_SECONDS


def _endpoints(server: str) -> tuple[str, str, str]:
    parsed = urlsplit(server.rstrip('/'))
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
        raise ValueError('BAOKEMENG_SERVER 必须是完整的 http(s) 地址')
    origin = f'{parsed.scheme}://{parsed.netloc}'
    base_path = parsed.path.rstrip('/')
    polling = f'{origin}{base_path}/socket.io/'
    ws_scheme = 'wss' if parsed.scheme == 'https' else 'ws'
    websocket_url = f'{ws_scheme}://{parsed.netloc}{base_path}/socket.io/'
    return origin, polling, websocket_url


def _polling_open(body: str) -> dict[str, Any]:
    for packet in body.split('\x1e'):
        if packet.startswith('0'):
            return json.loads(packet[1:])
    raise RuntimeError('polling 响应中没有 Engine.IO open 包')


def _socket_event(frame: str | bytes) -> tuple[str | None, list[Any]]:
    if not isinstance(frame, str) or not frame.startswith('42'):
        return None, []
    try:
        payload = json.loads(frame[2:])
    except json.JSONDecodeError:
        return None, []
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], str):
        return None, []
    return payload[0], payload[1:]


def _commit_ready(tracker: DraftTracker) -> None:
    snapshot = tracker.poll(datetime.now())
    if snapshot is None:
        return
    try:
        session, created = persist_final_draft(snapshot)
    except Exception:
        tracker.commit_failed()
        logger.exception('宝可梦终稿写入失败，将继续重试')
        return
    tracker.commit_succeeded()
    invalidate_cache('draft')
    logger.info(
        f'宝可梦终稿 {"已保存" if created else "已存在"}: '
        f'session={session.id} play_day={session.play_day} teams={session.team_count} '
        f'fingerprint={session.roster_fingerprint[:12]}'
    )


class _ReconnectBackoff:
    def __init__(self) -> None:
        self.failures = 0

    def connected(self) -> None:
        self.failures = 0

    def failed_delay(self) -> float:
        self.failures += 1
        return min(60.0, 2 ** min(self.failures, 6)) + random.uniform(0, 1)


def _listen_once(
    tracker: DraftTracker,
    should_stop: Callable[[], bool],
    on_connected: Callable[[], None] | None = None,
) -> None:
    origin, polling_url, websocket_url = _endpoints(BAOKEMENG_SERVER)
    session = requests.Session()
    session.headers.update({
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
        'Origin': origin,
    })
    response = session.get(
        polling_url,
        params={'EIO': '4', 'transport': 'polling', 't': str(int(time.time() * 1000))},
        timeout=20,
    )
    response.raise_for_status()
    engine_sid = _polling_open(response.text)['sid']
    ws_url = websocket_url + '?' + urlencode({
        'EIO': '4', 'transport': 'websocket', 'sid': engine_sid,
    })
    cookies = '; '.join(f'{key}={value}' for key, value in session.cookies.items())
    headers = ['Cache-Control: no-cache', 'Pragma: no-cache']
    if cookies:
        headers.append('Cookie: ' + cookies)
    ws = websocket.create_connection(
        ws_url, origin=origin, header=headers, timeout=20, enable_multithread=True
    )
    try:
        ws.send('2probe')
        if ws.recv() != '3probe':
            raise RuntimeError('WebSocket upgrade probe 失败')
        ws.send('5')
        ws.send('40')
        ws.settimeout(1)
        login_sent = False
        healthy = False
        while not should_stop():
            try:
                frame = ws.recv()
            except websocket.WebSocketTimeoutException:
                _commit_ready(tracker)
                continue
            if frame == '':
                raise ConnectionError('服务端关闭了 WebSocket')
            if isinstance(frame, str) and frame.startswith('2'):
                ws.send('3' + frame[1:])
                _commit_ready(tracker)
                continue
            if isinstance(frame, str) and frame.startswith('40') and not login_sent:
                password_hash = hashlib.md5(BAOKEMENG_PASSWORD.encode('utf-8')).hexdigest()
                ws.send('42' + json.dumps(
                    ['loading', password_hash, {'attendanceCode': BAOKEMENG_PASSWORD}],
                    ensure_ascii=False,
                    separators=(',', ':'),
                ))
                login_sent = True
                logger.info('宝可梦 Socket.IO 已连接并完成登录')
                continue
            event, args = _socket_event(frame)
            try:
                if event == 'loading':
                    tracker.ingest_loading(args, datetime.now())
                    if not healthy:
                        healthy = True
                        if on_connected is not None:
                            on_connected()
                    logger.info('宝可梦盘面基线已加载')
                elif event == 'updatePlayerPosition':
                    tracker.ingest_update(args, datetime.now())
            except DraftValidationError as exc:
                logger.warning(f'忽略无法解析的宝可梦事件: {exc}')
            _commit_ready(tracker)
    finally:
        ws.close()


def main() -> int:
    if not BAOKEMENG_PASSWORD:
        raise SystemExit('BAOKEMENG_PASSWORD is required for baokemeng-worker')
    tracker = DraftTracker(BAOKEMENG_STABLE_SECONDS)
    backoff = _ReconnectBackoff()
    stopped = False

    def stop(_signum=None, _frame=None):
        nonlocal stopped
        stopped = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    while not stopped:
        try:
            _listen_once(tracker, lambda: stopped, backoff.connected)
        except Exception as exc:
            delay = backoff.failed_delay()
            logger.error(
                f'宝可梦连接异常: {type(exc).__name__}: {exc}; {delay:.1f} 秒后重连'
            )
            deadline = time.monotonic() + delay
            while not stopped and time.monotonic() < deadline:
                time.sleep(min(0.25, deadline - time.monotonic()))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
