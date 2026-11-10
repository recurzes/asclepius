"""Paths shared by the scripts."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_YAML = ROOT / "datasets" / "bcc" / "data.yaml"
RUNS = ROOT / "runs"
ONNX_MODEL = ROOT / "models" / "asclepius_bcc.onnx"


def latest_weights() -> Path:
    """best.pt of the most recently trained run."""
    candidates = sorted(RUNS.glob("*/weights/best.pt"), key=lambda p: p.stat().st_mtime)
    if not candidates:
        raise SystemExit(f"No trained weights found in {RUNS}. Run scripts/train.py first, or pass --weights.")
    return candidates[-1]
