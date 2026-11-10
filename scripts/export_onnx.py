"""Export trained weights to ONNX for ONNX Runtime (Windows desktop / Raspberry Pi).

Output tensor is (1, 5, 8400): rows are cx, cy, w, h, score in 640x640 letterboxed
pixels. NMS is not embedded; see scripts/predict_onnx.py for the decoding.
"""

import argparse
import shutil
from pathlib import Path

from ultralytics import YOLO

from common import ONNX_MODEL, latest_weights


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weights", type=Path, help="default: best.pt of the latest run")
    parser.add_argument("--out", type=Path, default=ONNX_MODEL)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--opset", type=int, help="ONNX opset; lower it if the target's onnxruntime is old")
    parser.add_argument("--dynamic", action="store_true", help="allow variable input size")
    args = parser.parse_args()

    weights = args.weights or latest_weights()
    exported = YOLO(weights).export(
        format="onnx", imgsz=args.imgsz, opset=args.opset, dynamic=args.dynamic, simplify=True, device="cpu"
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(exported, args.out)
    print(f"\n{weights} -> {args.out}")


if __name__ == "__main__":
    main()
