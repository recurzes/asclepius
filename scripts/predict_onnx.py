"""Run the exported ONNX model with ONNX Runtime on an image or a webcam.

Needs only onnxruntime, numpy and opencv, so it can be reused in the desktop / Pi app.

    uv run scripts/predict_onnx.py --source photo.jpg
    uv run scripts/predict_onnx.py --source 0          # webcam, press q to quit
    uv run scripts/predict_onnx.py --source 0 --serial COM5   # also text alerts via Arduino + SIM800C
"""

import argparse
import time
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

ROOT = Path(__file__).resolve().parents[1]
ONNX_MODEL = ROOT / "models" / "asclepius_bcc.onnx"
LABEL = "BCC"


def letterbox(image: np.ndarray, size: int) -> tuple[np.ndarray, float, int, int]:
    """Resize keeping aspect ratio and pad to size x size. Returns image, scale, pad_x, pad_y."""
    h, w = image.shape[:2]
    scale = min(size / h, size / w)
    new_w, new_h = round(w * scale), round(h * scale)
    pad_x, pad_y = (size - new_w) // 2, (size - new_h) // 2
    canvas = np.full((size, size, 3), 114, dtype=np.uint8)
    canvas[pad_y : pad_y + new_h, pad_x : pad_x + new_w] = cv2.resize(image, (new_w, new_h))
    return canvas, scale, pad_x, pad_y


def detect(session: ort.InferenceSession, image: np.ndarray, conf: float, iou: float) -> list[tuple[int, int, int, int, float]]:
    """Returns [(x1, y1, x2, y2, score), ...] in pixels of the original image."""
    model_input = session.get_inputs()[0]
    size = model_input.shape[2] if isinstance(model_input.shape[2], int) else 640
    padded, scale, pad_x, pad_y = letterbox(image, size)
    blob = padded[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255.0  # BGR -> RGB, NCHW

    output = session.run(None, {model_input.name: blob})[0][0].T  # (8400, 4 + classes)
    scores = output[:, 4:].max(axis=1)
    keep = scores >= conf
    boxes, scores = output[keep, :4], scores[keep]

    # cx, cy, w, h (letterboxed) -> x, y, w, h (original image)
    boxes[:, 0] = (boxes[:, 0] - boxes[:, 2] / 2 - pad_x) / scale
    boxes[:, 1] = (boxes[:, 1] - boxes[:, 3] / 2 - pad_y) / scale
    boxes[:, 2:] /= scale

    detections = []
    for i in np.array(cv2.dnn.NMSBoxes(boxes.tolist(), scores.tolist(), conf, iou)).flatten():
        x, y, w, h = boxes[i]
        detections.append((int(x), int(y), int(x + w), int(y + h), float(scores[i])))
    return detections


def draw(image: np.ndarray, detections: list, alert: float) -> np.ndarray:
    for x1, y1, x2, y2, score in detections:
        is_alert = score >= alert
        color = (0, 0, 255) if is_alert else (0, 200, 255)
        text = f"{LABEL} {score:.2f}" + (" ALERT" if is_alert else "")
        cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)
        cv2.putText(image, text, (x1, max(y1 - 8, 16)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    return image


def open_serial(port: str):
    import serial  # only needed with --serial, keeps the web image free of pyserial

    link = serial.Serial(port, 9600, timeout=0)
    time.sleep(2)  # opening the port resets Uno/Nano; wait for the sketch to start
    return link


def send_alert(link, detections: list, alert: float) -> bool:
    """Sends "ALERT <score>" if any detection reaches the alert score. Returns True if sent."""
    best = max((d[4] for d in detections), default=0.0)
    if link is None or best < alert:
        return False
    link.write(f"ALERT {best:.2f}\n".encode())
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", required=True, help="image path, or webcam index such as 0")
    parser.add_argument("--model", type=Path, default=ONNX_MODEL)
    parser.add_argument("--conf", type=float, default=0.25, help="minimum score to draw a box")
    parser.add_argument("--iou", type=float, default=0.45, help="NMS overlap threshold")
    parser.add_argument("--alert", type=float, default=0.80, help="score that counts as an alert")
    parser.add_argument("--show", action="store_true", help="open a window for image sources")
    parser.add_argument("--serial", help="Arduino port such as COM5; sends ALERT lines for the SMS sketch")
    args = parser.parse_args()

    session = ort.InferenceSession(str(args.model), providers=["CPUExecutionProvider"])
    link = open_serial(args.serial) if args.serial else None

    if args.source.isdigit():
        camera = cv2.VideoCapture(int(args.source))
        if not camera.isOpened():
            raise SystemExit(f"Cannot open webcam {args.source}")
        last_alert = 0.0
        while True:
            ok, frame = camera.read()
            if not ok:
                break
            detections = detect(session, frame, args.conf, args.iou)
            # Throttle to one line per 5 s so the Arduino is not flooded; the sketch enforces the SMS cooldown.
            if time.monotonic() - last_alert >= 5 and send_alert(link, detections, args.alert):
                last_alert = time.monotonic()
            if link is not None and link.in_waiting:
                print(link.read(link.in_waiting).decode(errors="replace"), end="")
            cv2.imshow("ASCLEPIUS", draw(frame, detections, args.alert))
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
        camera.release()
        cv2.destroyAllWindows()
        return

    image = cv2.imread(args.source)
    if image is None:
        raise SystemExit(f"Cannot read image {args.source}")
    detections = detect(session, image, args.conf, args.iou)
    for x1, y1, x2, y2, score in detections:
        print(f"{LABEL} {score:.2f} box=({x1}, {y1}, {x2}, {y2})" + ("  ALERT" if score >= args.alert else ""))
    if not detections:
        print("No detections")
    if send_alert(link, detections, args.alert):
        time.sleep(7)  # let the SMS go out, then show what the Arduino replied
        print(link.read(link.in_waiting).decode(errors="replace"), end="")

    out = ROOT / "runs" / "predict_onnx" / Path(args.source).name
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), draw(image, detections, args.alert))
    print(f"Saved {out}")
    if args.show:
        cv2.imshow("ASCLEPIUS", image)
        cv2.waitKey(0)


if __name__ == "__main__":
    main()
