"""Train a YOLO11 detector on datasets/bcc."""

import argparse

from ultralytics import YOLO

from common import DATA_YAML, RUNS


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="yolo11n.pt", help="pretrained weights: yolo11n.pt, yolo11s.pt, ...")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--device", default="0", help="GPU index, or 'cpu'")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--name", default="bcc_yolo11n", help="run folder name under runs/")
    parser.add_argument("--resume", action="store_true", help="continue runs/<name> from its last.pt")
    args = parser.parse_args()

    if args.resume:
        last = RUNS / args.name / "weights" / "last.pt"
        if not last.is_file():
            raise SystemExit(f"Nothing to resume: {last} does not exist")
        results = YOLO(last).train(resume=True)
    else:
        if not DATA_YAML.is_file():
            raise SystemExit(f"{DATA_YAML} not found. Run scripts/prepare_dataset.py first.")
        results = YOLO(args.model).train(
            data=str(DATA_YAML),
            epochs=args.epochs,
            batch=args.batch,
            imgsz=args.imgsz,
            device=args.device,
            workers=args.workers,
            patience=30,
            seed=0,
            flipud=0.5,  # dermoscopy images have no up/down
            project=str(RUNS),
            name=args.name,
        )
    print(f"\nBest weights: {results.save_dir / 'weights' / 'best.pt'}")


# The guard is required on Windows: dataloader workers re-import this file.
if __name__ == "__main__":
    main()
