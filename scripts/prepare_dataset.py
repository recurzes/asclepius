"""Build a clean copy of the BCC dataset in datasets/bcc.

The Roboflow export contains the same ISIC photo up to three times, often in
different splits. This keeps one file per photo and re-splits 70/20/10 so no
photo is shared between train, val and test. The original folder is not modified.
"""

import argparse
import csv
import random
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "PROJECT COMMISSION BCC" / "content" / "BCC_Asclepius_Dataset"
OUT = ROOT / "datasets" / "bcc"
NEGATIVES = ROOT / "datasets" / "negatives"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}
CLASS_NAMES = ["BasalCellCarcinoma"]


def photo_id(filename: str) -> str:
    """ISIC_0024331_jpg.rf.<hash>.jpg -> ISIC_0024331"""
    match = re.match(r"(.+?)_(?:jpg|jpeg|png)\.rf\.", filename)
    return match.group(1) if match else Path(filename).stem


def split_items(items: list, seed: int) -> dict[str, list]:
    items = sorted(items)
    random.Random(seed).shuffle(items)
    n_train = round(len(items) * 0.7)
    n_val = round(len(items) * 0.2)
    return {
        "train": items[:n_train],
        "val": items[n_train : n_train + n_val],
        "test": items[n_train + n_val :],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    # One image per photo id: the first file by name wins, with its own label.
    files = sorted(
        (p for split in ("train", "valid", "test") for p in (args.source / split / "images").iterdir()),
        key=lambda p: p.name,
    )
    if not files:
        raise SystemExit(f"No images found under {args.source}")
    chosen: dict[str, Path] = {}
    for image in files:
        chosen.setdefault(photo_id(image.name), image)
    print(f"{len(files)} files -> {len(chosen)} unique photos ({len(files) - len(chosen)} duplicates dropped)")

    for split in ("train", "val", "test"):
        shutil.rmtree(args.out / split, ignore_errors=True)
        (args.out / split / "images").mkdir(parents=True)
        (args.out / split / "labels").mkdir(parents=True)

    rows = []
    splits = split_items(list(chosen), args.seed)
    for split, ids in splits.items():
        for pid in ids:
            image = chosen[pid]
            label = image.parent.parent / "labels" / f"{image.stem}.txt"
            if not label.is_file():
                raise SystemExit(f"Missing label for {image}")
            shutil.copy2(image, args.out / split / "images" / f"{pid}{image.suffix.lower()}")
            shutil.copy2(label, args.out / split / "labels" / f"{pid}.txt")
            rows.append((pid, split, image.relative_to(args.source).as_posix()))

    # Optional background images (no lesion / not BCC): copied with empty labels.
    negatives = sorted(p for p in NEGATIVES.glob("*") if p.suffix.lower() in IMAGE_EXTS) if NEGATIVES.is_dir() else []
    for split, images in split_items(negatives, args.seed).items():
        for image in images:
            name = f"neg_{image.stem}"
            shutil.copy2(image, args.out / split / "images" / f"{name}{image.suffix.lower()}")
            (args.out / split / "labels" / f"{name}.txt").write_text("")
            rows.append((name, split, f"negatives/{image.name}"))
    if negatives:
        print(f"Added {len(negatives)} negative images from {NEGATIVES}")

    with open(args.out / "manifest.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "split", "original_file"])
        writer.writerows(sorted(rows))

    (args.out / "data.yaml").write_text(
        f"path: {args.out.resolve().as_posix()}\n"
        "train: train/images\n"
        "val: val/images\n"
        "test: test/images\n"
        f"nc: {len(CLASS_NAMES)}\n"
        f"names: {CLASS_NAMES}\n"
    )

    # Checks: every image has a label, and no photo is in two splits.
    seen: dict[str, str] = {}
    for split in ("train", "val", "test"):
        images = {p.stem for p in (args.out / split / "images").iterdir()}
        labels = {p.stem for p in (args.out / split / "labels").iterdir()}
        assert images == labels, f"{split}: images and labels do not match"
        for stem in images:
            assert stem not in seen, f"{stem} is in both {seen[stem]} and {split}"
            seen[stem] = split
        print(f"{split:5s} {len(images):5d} images ({len(images) / len(rows):.0%})")
    assert len(seen) == len(rows)
    print(f"total {len(seen):5d} images, no photo shared between splits")
    print(f"Dataset written to {args.out}")


if __name__ == "__main__":
    main()
