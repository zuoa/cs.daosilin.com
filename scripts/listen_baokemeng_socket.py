#!/usr/bin/env python3
"""Capture every Engine.IO / Socket.IO frame from baokemeng to a JSONL file.

The script follows the same connection sequence as the browser client:

1. Create an Engine.IO session with HTTP long-polling.
2. Upgrade that session to WebSocket with the newly issued sid.
3. Connect the default Socket.IO namespace.
4. Emit the site's ``loading`` login event.

Received payloads are never filtered or truncated in the JSONL output.  Console
output is intentionally summarized so a long-running capture remains readable.
"""

from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import json
import os
import signal
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlsplit

import requests
import websocket


ENGINE_PACKET_NAMES = {
    "0": "open",
    "1": "close",
    "2": "ping",
    "3": "pong",
    "4": "message",
    "5": "upgrade",
    "6": "noop",
}

SOCKET_PACKET_NAMES = {
    "0": "connect",
    "1": "disconnect",
    "2": "event",
    "3": "ack",
    "4": "connect_error",
    "5": "binary_event",
    "6": "binary_ack",
}


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def parse_args() -> argparse.Namespace:
    default_name = f"baokemeng_socket_{datetime.now():%Y%m%d_%H%M%S}.jsonl"
    parser = argparse.ArgumentParser(
        description="Log all baokemeng Socket.IO frames without payload filtering."
    )
    parser.add_argument(
        "--server",
        default="https://www.baokemeng.xyz",
        help="Site origin (default: %(default)s)",
    )
    parser.add_argument(
        "--password",
        help="Login password. If omitted, BAOKEMENG_PASSWORD or a hidden prompt is used.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("logs") / default_name,
        help="JSONL destination; existing files are appended to (default: %(default)s)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=0,
        help="Stop after this many seconds; 0 means run until Ctrl+C (default: 0)",
    )
    parser.add_argument(
        "--reconnect-delay",
        type=float,
        default=2.0,
        help="Seconds before reconnecting after an error (default: %(default)s)",
    )
    parser.add_argument(
        "--print-payloads",
        action="store_true",
        help="Also print complete decoded event payloads to the terminal.",
    )
    return parser.parse_args()


def resolve_password(cli_password: str | None) -> str:
    password = cli_password or os.environ.get("BAOKEMENG_PASSWORD")
    if password is None:
        password = getpass.getpass("Baokemeng 口令（输入不会显示）: ")
    if not password:
        raise ValueError("口令不能为空")
    return password


def server_endpoints(server: str) -> tuple[str, str, str]:
    parsed = urlsplit(server.rstrip("/"))
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("--server 必须是完整的 http(s) 地址")

    origin = f"{parsed.scheme}://{parsed.netloc}"
    base_path = parsed.path.rstrip("/")
    polling_url = f"{origin}{base_path}/socket.io/"
    ws_scheme = "wss" if parsed.scheme == "https" else "ws"
    websocket_url = f"{ws_scheme}://{parsed.netloc}{base_path}/socket.io/"
    return origin, polling_url, websocket_url


def parse_socket_packet(payload: str) -> dict[str, Any]:
    result: dict[str, Any] = {"socketio_raw": payload}
    if not payload or payload[0] not in SOCKET_PACKET_NAMES:
        result["socketio_parse_error"] = "unknown or missing packet type"
        return result

    packet_type = payload[0]
    result["socketio_type"] = int(packet_type)
    result["socketio_type_name"] = SOCKET_PACKET_NAMES[packet_type]
    remainder = payload[1:]

    if packet_type in {"5", "6"}:
        separator = remainder.find("-")
        if separator >= 0 and remainder[:separator].isdigit():
            result["attachments"] = int(remainder[:separator])
            remainder = remainder[separator + 1 :]

    namespace = "/"
    if remainder.startswith("/"):
        comma = remainder.find(",")
        if comma < 0:
            namespace = remainder
            remainder = ""
        else:
            namespace = remainder[:comma]
            remainder = remainder[comma + 1 :]
    result["namespace"] = namespace

    ack_end = 0
    while ack_end < len(remainder) and remainder[ack_end].isdigit():
        ack_end += 1
    if ack_end:
        result["ack_id"] = int(remainder[:ack_end])
        remainder = remainder[ack_end:]

    if remainder:
        try:
            data = json.loads(remainder)
            result["data"] = data
            if packet_type in {"2", "5"} and isinstance(data, list) and data:
                result["event"] = data[0]
                result["args"] = data[1:]
        except json.JSONDecodeError as exc:
            result["socketio_parse_error"] = str(exc)
            result["socketio_data_raw"] = remainder
    return result


def decode_frame(frame: str | bytes) -> dict[str, Any]:
    if isinstance(frame, bytes):
        return {
            "frame_kind": "binary",
            "size": len(frame),
            "raw_base64": base64.b64encode(frame).decode("ascii"),
        }

    result: dict[str, Any] = {
        "frame_kind": "text",
        "size": len(frame.encode("utf-8")),
        "raw": frame,
    }
    if not frame:
        result["engine_parse_error"] = "empty frame"
        return result

    packet_type = frame[0]
    result["engine_type"] = int(packet_type) if packet_type.isdigit() else packet_type
    result["engine_type_name"] = ENGINE_PACKET_NAMES.get(packet_type, "unknown")
    result["engine_payload"] = frame[1:]
    if packet_type == "4":
        result.update(parse_socket_packet(frame[1:]))
    return result


def safe_console_summary(record: dict[str, Any], print_payloads: bool) -> str:
    stamp = record["timestamp"]
    direction = record["direction"].upper()
    if record.get("frame_kind") == "binary":
        return f"[{stamp}] {direction} binary {record['size']} bytes"

    event = record.get("event")
    if event is not None:
        args = record.get("args", [])
        if print_payloads:
            payload = json.dumps(args, ensure_ascii=False, separators=(",", ":"))
            return f"[{stamp}] {direction} event={event!r} args={payload}"
        shapes = []
        for value in args:
            if isinstance(value, dict):
                shapes.append(f"dict(keys={list(value.keys())})")
            elif isinstance(value, list):
                shapes.append(f"list(len={len(value)})")
            elif isinstance(value, str):
                shapes.append(f"str(len={len(value)})")
            else:
                shapes.append(type(value).__name__)
        return f"[{stamp}] {direction} event={event!r} args=[{', '.join(shapes)}]"

    socket_name = record.get("socketio_type_name")
    if socket_name:
        return f"[{stamp}] {direction} socket.io={socket_name} namespace={record.get('namespace')}"
    return f"[{stamp}] {direction} engine.io={record.get('engine_type_name')}"


class JsonlCapture:
    def __init__(self, path: Path, print_payloads: bool) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path.resolve()
        self.file = self.path.open("a", encoding="utf-8", buffering=1)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass
        self.print_payloads = print_payloads
        self.frame_count = 0
        self.event_counts: Counter[str] = Counter()

    def metadata(self, kind: str, **values: Any) -> None:
        record = {"timestamp": now_iso(), "record_type": kind, **values}
        self.file.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")

    def frame(
        self,
        direction: str,
        transport: str,
        frame: str | bytes,
        *,
        print_console: bool = True,
        redact: bool = False,
    ) -> dict[str, Any]:
        if redact:
            decoded: dict[str, Any] = {
                "frame_kind": "text",
                "raw": "<redacted login frame>",
                "event": "loading",
                "args": ["<redacted password hash>", {"attendanceCode": "<redacted>"}],
            }
        else:
            decoded = decode_frame(frame)
        record = {
            "timestamp": now_iso(),
            "record_type": "frame",
            "direction": direction,
            "transport": transport,
            **decoded,
        }
        self.file.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        self.frame_count += 1
        if direction == "received" and "event" in record:
            self.event_counts[str(record["event"])] += 1
        if print_console:
            print(safe_console_summary(record, self.print_payloads), flush=True)
        return record

    def close(self) -> None:
        self.metadata(
            "capture_end",
            frames=self.frame_count,
            events=dict(self.event_counts),
        )
        self.file.close()


def polling_open_packet(body: str) -> dict[str, Any]:
    for packet in body.split("\x1e"):
        if packet.startswith("0"):
            return json.loads(packet[1:])
    raise RuntimeError(f"polling 响应中没有 Engine.IO open 包: {body[:200]!r}")


def connect_and_listen(
    *,
    origin: str,
    polling_url: str,
    websocket_url: str,
    password: str,
    capture: JsonlCapture,
    should_stop: Any,
) -> None:
    session = requests.Session()
    session.headers.update(
        {
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Origin": origin,
        }
    )

    response = session.get(
        polling_url,
        params={"EIO": "4", "transport": "polling", "t": str(int(time.time() * 1000))},
        timeout=20,
    )
    response.raise_for_status()
    capture.frame("received", "polling", response.text)
    open_packet = polling_open_packet(response.text)
    engine_sid = open_packet["sid"]
    capture.metadata("session_open", engine_sid=engine_sid)
    print(f"Engine.IO session: {engine_sid}", flush=True)

    ws_url = websocket_url + "?" + urlencode(
        {"EIO": "4", "transport": "websocket", "sid": engine_sid}
    )
    cookies = "; ".join(f"{key}={value}" for key, value in session.cookies.items())
    headers = ["Cache-Control: no-cache", "Pragma: no-cache"]
    if cookies:
        headers.append("Cookie: " + cookies)

    ws = websocket.create_connection(
        ws_url,
        origin=origin,
        header=headers,
        timeout=20,
        enable_multithread=True,
    )
    try:
        capture.metadata("websocket_open", http_status=ws.getstatus())
        capture.frame("sent", "websocket", "2probe")
        ws.send("2probe")
        probe = ws.recv()
        capture.frame("received", "websocket", probe)
        if probe != "3probe":
            raise RuntimeError(f"WebSocket upgrade probe 失败: {probe!r}")

        capture.frame("sent", "websocket", "5")
        ws.send("5")
        capture.frame("sent", "websocket", "40")
        ws.send("40")

        namespace_connected = False
        login_sent = False
        # A short timeout keeps --duration and Ctrl+C responsive while the
        # Engine.IO connection itself remains alive through application pings.
        ws.settimeout(2)
        while not should_stop():
            try:
                frame = ws.recv()
            except websocket.WebSocketTimeoutException:
                continue
            if frame == "":
                capture.frame("received", "websocket", frame)
                raise ConnectionError("服务端关闭了 WebSocket")

            record = capture.frame("received", "websocket", frame)
            if isinstance(frame, str) and frame.startswith("2"):
                pong = "3" + frame[1:]
                ws.send(pong)
                capture.frame("sent", "websocket", pong, print_console=False)
                continue

            if (
                record.get("socketio_type_name") == "connect"
                and record.get("namespace") == "/"
            ):
                namespace_connected = True

            if namespace_connected and not login_sent:
                password_hash = hashlib.md5(password.encode("utf-8")).hexdigest()
                login = "42" + json.dumps(
                    ["loading", password_hash, {"attendanceCode": password}],
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                ws.send(login)
                capture.frame(
                    "sent",
                    "websocket",
                    login,
                    redact=True,
                    print_console=False,
                )
                login_sent = True
                print("已发送 loading 登录事件，开始捕获全部服务端数据。", flush=True)
    finally:
        try:
            ws.close()
        except Exception:
            pass


def main() -> int:
    args = parse_args()
    if args.duration < 0:
        raise ValueError("--duration 不能小于 0")
    if args.reconnect_delay < 0:
        raise ValueError("--reconnect-delay 不能小于 0")

    password = resolve_password(args.password)
    origin, polling_url, websocket_url = server_endpoints(args.server)
    capture = JsonlCapture(args.output, args.print_payloads)
    started = time.monotonic()
    interrupted = False

    def stop_requested() -> bool:
        return interrupted or bool(args.duration and time.monotonic() - started >= args.duration)

    def request_stop(_signum: int, _frame: Any) -> None:
        nonlocal interrupted
        interrupted = True

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    capture.metadata(
        "capture_start",
        server=args.server,
        output=str(capture.path),
        payloads_complete=True,
        outbound_login_credentials_redacted=True,
    )
    print(f"完整日志写入: {capture.path}", flush=True)
    print("按 Ctrl+C 停止。服务端 payload 在文件中不会被截断。", flush=True)

    connection_number = 0
    try:
        while not stop_requested():
            connection_number += 1
            capture.metadata("connection_attempt", number=connection_number)
            try:
                connect_and_listen(
                    origin=origin,
                    polling_url=polling_url,
                    websocket_url=websocket_url,
                    password=password,
                    capture=capture,
                    should_stop=stop_requested,
                )
            except Exception as exc:
                capture.metadata(
                    "connection_error",
                    number=connection_number,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
                print(f"连接异常: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
                if not stop_requested():
                    print(f"{args.reconnect_delay:g} 秒后重连……", flush=True)
                    end = time.monotonic() + args.reconnect_delay
                    while not stop_requested() and time.monotonic() < end:
                        time.sleep(min(0.2, end - time.monotonic()))
    finally:
        capture.close()

    print(
        f"监听结束：{capture.frame_count} 帧；事件统计 {dict(capture.event_counts)}",
        flush=True,
    )
    print(f"日志文件: {capture.path}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, requests.RequestException) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        raise SystemExit(2)
