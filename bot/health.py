import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class HealthServer:
    def __init__(self, host, port, readiness):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path not in {"/", "/health"}:
                    self.send_error(404)
                    return
                try:
                    ready = readiness()
                except Exception:
                    ready = False
                data = json.dumps({"service": "LibraryBot", "ready": ready}).encode()
                self.send_response(200 if ready else 503)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *_):
                pass

        self.server = ThreadingHTTPServer((host, port), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self):
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
