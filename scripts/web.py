"""Local web page for the ONNX model: drag in an image, see boxes and confidence.

    uv run scripts/web.py        then open http://127.0.0.1:8000

On a host that sets the PORT environment variable (Railway, Docker) it listens
on all interfaces at that port instead.
"""

import argparse
import json
import os
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

from predict_onnx import ONNX_MODEL, ROOT, detect

PAGE = ROOT / "web" / "index.html"
MAX_UPLOAD = 25 * 1024 * 1024


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", type=Path, default=ONNX_MODEL)
    hosted = "PORT" in os.environ
    parser.add_argument("--host", default="0.0.0.0" if hosted else "127.0.0.1", help="0.0.0.0 to accept outside connections")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
    parser.add_argument("--conf", type=float, default=0.25, help="minimum score to report a detection")
    parser.add_argument("--iou", type=float, default=0.45, help="NMS overlap threshold")
    parser.add_argument("--alert", type=float, default=0.80, help="score that counts as an alert")
    parser.add_argument("--no-browser", action="store_true", help="do not open the page automatically")
    args = parser.parse_args()

    if not args.model.is_file():
        raise SystemExit(f"{args.model} not found. Run scripts/export_onnx.py first, or pass --model.")
    session = ort.InferenceSession(str(args.model), providers=["CPUExecutionProvider"])

    class Handler(BaseHTTPRequestHandler):
        def reply(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def reply_json(self, status: int, data: dict) -> None:
            self.reply(status, json.dumps(data).encode(), "application/json")

        def do_GET(self) -> None:
            if self.path in ("/", "/index.html"):
                self.reply(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            else:
                self.reply(404, b"Not found", "text/plain")

        def do_POST(self) -> None:
            if self.path != "/predict":
                return self.reply(404, b"Not found", "text/plain")
            length = int(self.headers.get("Content-Length", 0))
            if not 0 < length <= MAX_UPLOAD:
                return self.reply_json(413, {"error": "Image is empty or larger than 25 MB."})
            image = cv2.imdecode(np.frombuffer(self.rfile.read(length), np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                return self.reply_json(400, {"error": "That file could not be read as an image."})
            detections = sorted(detect(session, image, args.conf, args.iou), key=lambda d: -d[4])
            self.reply_json(
                200,
                {
                    "alert": args.alert,
                    "detections": [{"box": list(d[:4]), "confidence": round(d[4], 4)} for d in detections],
                },
            )

    # Uploaded images are decoded in memory and never written to disk.
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}"
    print(f"ASCLEPIUS is running at {url}  (Ctrl+C to stop)")
    if args.host == "127.0.0.1" and not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
