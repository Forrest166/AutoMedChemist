from __future__ import annotations

import argparse
import base64
import json
import os
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from tempfile import TemporaryDirectory
from pathlib import Path

from PIL import Image, ImageStat


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EDGE = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")


def wait_for_http(url: str, timeout_s: int) -> int:
    deadline = time.time() + timeout_s
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                return int(response.status)
        except Exception as exc:
            last_error = exc
            time.sleep(1)
    raise RuntimeError(f"HTTP smoke failed for {url}: {last_error}")


def assert_nonblank_png(path: Path, min_width: int, min_height: int) -> None:
    with Image.open(path) as image:
        width, height = image.size
        if width < min_width or height < min_height:
            raise RuntimeError(f"Screenshot too small: {width}x{height}")
        stat = ImageStat.Stat(image.convert("L"))
        if not stat.stddev or stat.stddev[0] < 2:
            raise RuntimeError("Screenshot appears blank.")


def _find_free_port(start: int = 9222) -> int:
    for port in range(start, start + 200):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("No free DevTools port found.")


def _http_json(url: str, timeout: int = 5):
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _wait_for_page_ws(debug_port: int, timeout_s: int) -> str:
    deadline = time.time() + timeout_s
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            pages = _http_json(f"http://127.0.0.1:{debug_port}/json/list")
            for page in pages:
                if page.get("type") == "page" and page.get("webSocketDebuggerUrl"):
                    return str(page["webSocketDebuggerUrl"])
        except Exception as exc:
            last_error = exc
        time.sleep(0.5)
    raise RuntimeError(f"DevTools page target not available: {last_error}")


def _recv_exact(sock: socket.socket, nbytes: int) -> bytes:
    chunks = []
    remaining = nbytes
    while remaining:
        chunk = sock.recv(remaining)
        if not chunk:
            raise RuntimeError("WebSocket closed unexpectedly.")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _send_ws_text(sock: socket.socket, text: str) -> None:
    payload = text.encode("utf-8")
    header = bytearray([0x81])
    length = len(payload)
    if length < 126:
        header.append(0x80 | length)
    elif length < 65536:
        header.extend([0x80 | 126, (length >> 8) & 0xFF, length & 0xFF])
    else:
        header.append(0x80 | 127)
        header.extend(length.to_bytes(8, "big"))
    mask = os.urandom(4)
    masked = bytes(byte ^ mask[idx % 4] for idx, byte in enumerate(payload))
    sock.sendall(bytes(header) + mask + masked)


def _recv_ws_text(sock: socket.socket) -> str:
    while True:
        first, second = _recv_exact(sock, 2)
        opcode = first & 0x0F
        masked = bool(second & 0x80)
        length = second & 0x7F
        if length == 126:
            length = int.from_bytes(_recv_exact(sock, 2), "big")
        elif length == 127:
            length = int.from_bytes(_recv_exact(sock, 8), "big")
        mask = _recv_exact(sock, 4) if masked else b""
        payload = _recv_exact(sock, length) if length else b""
        if masked:
            payload = bytes(byte ^ mask[idx % 4] for idx, byte in enumerate(payload))
        if opcode == 0x8:
            raise RuntimeError("WebSocket close frame received.")
        if opcode == 0x9:
            continue
        if opcode == 0x1:
            return payload.decode("utf-8")


class CdpClient:
    def __init__(self, ws_url: str):
        parsed = urllib.parse.urlparse(ws_url)
        self.sock = socket.create_connection((parsed.hostname or "127.0.0.1", parsed.port or 80), timeout=10)
        self.sock.settimeout(10)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        path = parsed.path + (f"?{parsed.query}" if parsed.query else "")
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {parsed.hostname}:{parsed.port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(request.encode("ascii"))
        response = b""
        while b"\r\n\r\n" not in response:
            response += self.sock.recv(4096)
        if b" 101 " not in response.split(b"\r\n", 1)[0]:
            raise RuntimeError(f"DevTools WebSocket upgrade failed: {response[:200]!r}")
        self._next_id = 1

    def close(self) -> None:
        self.sock.close()

    def command(self, method: str, params: dict | None = None) -> dict:
        message_id = self._next_id
        self._next_id += 1
        _send_ws_text(self.sock, json.dumps({"id": message_id, "method": method, "params": params or {}}))
        while True:
            message = json.loads(_recv_ws_text(self.sock))
            if message.get("id") != message_id:
                continue
            if message.get("error"):
                raise RuntimeError(f"CDP {method} failed: {message['error']}")
            return message.get("result") or {}


def _page_state(client: CdpClient) -> dict:
    expression = """
(() => {
  const text = (document.body && document.body.innerText) || "";
  const controls = document.querySelectorAll("textarea,input,button,[role='tab']").length;
  const skeletons = document.querySelectorAll("[data-testid='stSkeleton'],[class*='skeleton'],[class*='Skeleton']").length;
  return {
    text: text.slice(0, 1500),
    controls,
    skeletons,
    ready: text.includes("LocalMedChemModifier") && text.includes("Candidate Design") && controls >= 3
  };
})()
"""
    result = client.command("Runtime.evaluate", {"expression": expression, "returnByValue": True})
    return ((result.get("result") or {}).get("value") or {})


def capture_streamlit_with_cdp(edge_path: Path, url: str, output: Path, wait_seconds: int, settle_seconds: int) -> dict:
    debug_port = _find_free_port()
    with TemporaryDirectory(prefix="localmedchem-edge-") as user_data_dir:
        command = [
            str(edge_path),
            "--headless=new",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--no-first-run",
            "--disable-extensions",
            "--window-size=1440,1100",
            "--remote-allow-origins=*",
            f"--remote-debugging-port={debug_port}",
            f"--user-data-dir={user_data_dir}",
            url,
        ]
        proc = subprocess.Popen(
            command,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        client = None
        try:
            ws_url = _wait_for_page_ws(debug_port, wait_seconds)
            client = CdpClient(ws_url)
            client.command("Page.enable")
            client.command("Runtime.enable")
            client.command(
                "Emulation.setDeviceMetricsOverride",
                {"width": 1440, "height": 1100, "deviceScaleFactor": 1, "mobile": False},
            )
            deadline = time.time() + wait_seconds
            last_state = {}
            while time.time() < deadline:
                last_state = _page_state(client)
                if last_state.get("ready"):
                    break
                time.sleep(1)
            if not last_state.get("ready"):
                raise RuntimeError(f"Streamlit UI did not finish rendering: {last_state}")
            time.sleep(max(0, settle_seconds))
            screenshot = client.command("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
            output.write_bytes(base64.b64decode(screenshot["data"]))
            return last_state
        finally:
            if client is not None:
                client.close()
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a headless Edge smoke test against the Streamlit UI.")
    parser.add_argument("--url", default="http://127.0.0.1:8501")
    parser.add_argument("--edge-path", default=str(DEFAULT_EDGE))
    parser.add_argument("--out", default=str(ROOT / "data" / "projects" / "demo" / "streamlit_headless.png"))
    parser.add_argument("--wait-seconds", type=int, default=30)
    parser.add_argument("--settle-seconds", type=int, default=12)
    parser.add_argument("--attempts", type=int, default=3)
    args = parser.parse_args()

    edge_path = Path(args.edge_path)
    if not edge_path.exists():
        raise RuntimeError(f"Microsoft Edge executable not found: {edge_path}")

    status = wait_for_http(args.url, args.wait_seconds)
    output = Path(args.out).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    last_error: Exception | None = None
    for attempt in range(1, max(1, args.attempts) + 1):
        if output.exists():
            output.unlink()
        try:
            state = capture_streamlit_with_cdp(edge_path, args.url, output, args.wait_seconds, args.settle_seconds)
            assert_nonblank_png(output, min_width=1000, min_height=700)
            break
        except Exception as exc:
            last_error = exc
            if attempt < args.attempts:
                time.sleep(3)
            else:
                raise RuntimeError(f"Browser screenshot smoke failed after {args.attempts} attempts: {last_error}") from exc
    print(f"ok status={status} screenshot={output.resolve()} state={state}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
