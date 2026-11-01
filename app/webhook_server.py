"""Part 4 student implementation."""

from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from app.integration import process_request
from app.webex_client import WEBEX_API_BASE, WebexClient


class WebexEventHandler:
    def __init__(self, client, bot_person_id, processor=None):
        self.client = client
        self.bot_person_id = bot_person_id
        self.processor = processor if processor is not None else process_request

    def handle_event(self, event):
        if not isinstance(event, dict):
            return None
        if event.get("resource") != "messages" or event.get("event") != "created":
            return None

        data = event.get("data")
        if not isinstance(data, dict):
            return None

        message_id = data.get("id")
        if not isinstance(message_id, str) or not message_id.strip():
            return None

        if data.get("personId") == self.bot_person_id:
            return None

        message = self.client.get_message(message_id)
        if not isinstance(message, dict):
            return None

        if message.get("personId") == self.bot_person_id:
            return None

        room_id = message.get("roomId")
        if not isinstance(room_id, str) or not room_id.strip():
            return None

        mentioned_people = message.get("mentionedPeople", [])
        files = message.get("files") or []

        if len(files) > 1:
            result = {
                "status": "error",
                "result": "multiple_attachments",
            }
        elif len(files) == 0:
            result = self.processor(
                mentioned_people,
                None,
                self.bot_person_id,
            )
        else:
            with TemporaryDirectory() as tmp_dir:
                attachment_path = Path(tmp_dir) / "request.yaml"
                content = self.client.download_file(files[0])
                attachment_path.write_bytes(content)
                result = self.processor(
                    mentioned_people,
                    attachment_path,
                    self.bot_person_id,
                )

        self.client.send_message(room_id, json.dumps(result))
        return result


def make_http_handler(submit_event):
    class WebhookHTTPHandler(BaseHTTPRequestHandler):
        def _send_json(self, status_code, payload):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/health":
                self._send_json(200, {"status": "ok", "result": "healthy"})
            else:
                self._send_json(404, {"status": "error", "result": "not_found"})

        def do_POST(self):
            if self.path != "/webhook":
                self._send_json(404, {"status": "error", "result": "not_found"})
                return

            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                content_length = 0

            if content_length < 1 or content_length > 1_000_000:
                self._send_json(400, {"status": "error", "result": "invalid_event"})
                return

            raw_body = self.rfile.read(content_length)
            try:
                event = json.loads(raw_body.decode("utf-8"))
            except Exception:
                self._send_json(400, {"status": "error", "result": "invalid_event"})
                return

            if not isinstance(event, dict):
                self._send_json(400, {"status": "error", "result": "invalid_event"})
                return

            submit_event(event)
            self._send_json(200, {"status": "ok", "result": "accepted"})

        def log_message(self, format, *args):
            return

    return WebhookHTTPHandler


def _resolve_bot_person_id(client):
    response = client.session.get(
        f"{WEBEX_API_BASE}/people/me",
        headers=client.headers,
        timeout=10,
    )
    response.raise_for_status()
    return response.json()["id"]


def main():
    logging.basicConfig(level=logging.INFO)
    host = os.environ.get("WEBHOOK_HOST", "0.0.0.0")
    port = int(os.environ.get("WEBHOOK_PORT", "8000"))

    handler_instance = None

    def _get_handler():
        nonlocal handler_instance
        if handler_instance is None:
            client = WebexClient()
            bot_person_id = _resolve_bot_person_id(client)
            handler_instance = WebexEventHandler(client, bot_person_id)
        return handler_instance

    def _process_in_background(event):
        try:
            handler = _get_handler()
            handler.handle_event(event)
        except Exception:
            logging.exception("Failed to handle Webex event")

    with ThreadPoolExecutor(max_workers=1) as executor:
        http_handler = make_http_handler(
            lambda evt: executor.submit(_process_in_background, evt)
        )
        server = ThreadingHTTPServer((host, port), http_handler)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()


if __name__ == "__main__":
    main()
