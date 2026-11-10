"""Score a trained model on the held-out test split (and the ONNX export, if present)."""

import argparse
from pathlib import Path

from ultralytics import YOLO

from common import DATA_YAML, ONNX_MODEL, RUNS, latest_weights


def evaluate(weights: Path, split: str, imgsz: int, device: str, name: str) -> None:
    metrics = YOLO(weights, task="detect").val(
        data=str(DATA_YAML), split=split, imgsz=imgsz, device=device, project=str(RUNS), name=name, exist_ok=True
    )
    print(f"\n{weights}  [{split} split]")
    print(f"  precision  {metrics.box.mp:.3f}")
    print(f"  recall     {metrics.box.mr:.3f}")
    print(f"  mAP50      {metrics.box.map50:.3f}")
    print(f"  mAP50-95   {metrics.box.map:.3f}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weights", type=Path, help="default: best.pt of the latest run")
    parser.add_argument("--onnx", type=Path, default=ONNX_MODEL)
    parser.add_argument("--split", default="test", choices=["train", "val", "test"])
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--device", default="0", help="GPU index, or 'cpu'")
    args = parser.parse_args()

    evaluate(args.weights or latest_weights(), args.split, args.imgsz, args.device, f"eval_{args.split}")
    if args.onnx.is_file():
        # onnxruntime here is the CPU build, the same runtime the deployed app uses.
        evaluate(args.onnx, args.split, args.imgsz, "cpu", f"eval_{args.split}_onnx")
    else:
        print(f"{args.onnx} not found; run scripts/export_onnx.py to evaluate the ONNX model too.")


if __name__ == "__main__":
    main()
