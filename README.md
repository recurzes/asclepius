# ASCLEPIUS: BCC detector training

Trains a YOLO11 detector for basal cell carcinoma and exports it to ONNX for ONNX Runtime.

## Setup (once)

Needs [uv](https://docs.astral.sh/uv/) and an NVIDIA GPU. Run everything from this folder in PowerShell.

```powershell
uv sync
uv run python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

The second command should print `True NVIDIA GeForce RTX 3060`.

## Run

```powershell
uv run scripts/prepare_dataset.py     # 1. build datasets/bcc (already done; rerun only if the source data changes)
uv run scripts/train.py               # 2. train; results in runs/bcc_yolo11n
uv run scripts/export_onnx.py         # 3. export -> models/asclepius_bcc.onnx
uv run scripts/evaluate.py            # 4. test-split scores for best.pt and the ONNX
uv run scripts/predict_onnx.py --source datasets/bcc/test/images/ISIC_0024331.jpg   # 5. try it
```

`export_onnx.py` and `evaluate.py` use the most recently trained run unless you pass `--weights`.

Training options:

```powershell
uv run scripts/train.py --resume                                  # continue after an interruption
uv run scripts/train.py --model yolo11s.pt --name bcc_yolo11s     # larger model
uv run scripts/train.py --batch 32                                # bigger batches if GPU memory allows
uv run scripts/train.py --epochs 150
```

Training stops early if validation has not improved for 30 epochs. If a run named `bcc_yolo11n` already exists, the new one is saved as `bcc_yolo11n2`, and so on.

Webcam inference: `uv run scripts/predict_onnx.py --source 0` (press `q` to quit).

## SMS alerts (Arduino + SIM800C)

Full step-by-step guide (parts, power, wiring, troubleshooting): [docs/SIM800C_SETUP.md](docs/SIM800C_SETUP.md).

The model is far too big for an Arduino (10 MB, about 6.5 GFLOPs per frame; an Uno has 32 KB of flash and 2 KB of RAM). So the PC runs the model and the Arduino only sends the text message.

1. Wire the SIM800C: TXD to pin 7, RXD to pin 8, GND to Arduino GND, and V_M (the logic-level pin; VDD on some boards) to Arduino 5V. Power the module from its own 5 V, 2 A supply into VCC_IN, with a 1000 µF capacitor across it and the supply ground joined to the Arduino ground. Never power it from the Arduino's 5V pin. A bare module with no 5V input or VDD pin needs 4.0 V and a logic level shifter instead.
2. Open `firmware/asclepius_sms/asclepius_sms.ino` in the Arduino IDE, set `PHONE` to the number that should get the SMS, and upload it.
3. Close the Arduino IDE's Serial Monitor, because only one program can use the port. Then run:

```powershell
uv run scripts/predict_onnx.py --source 0 --serial COM5              # webcam; use your Arduino's COM port
uv run scripts/predict_onnx.py --source photo.jpg --serial COM5      # one image
make sms PORT=COM5
```

Or use the desktop app instead of the command line:

```powershell
dotnet run --project desktop        # needs the .NET 10 SDK
```

Pick the Arduino's COM port and click **Connect**, wait for `Arduino: READY` in the log, then click **Start camera** or **Open image...**. Any box at or above **Min confidence** (0.50 by default) is drawn and triggers an alert. In camera mode the app sends at most one alert every 5 seconds. Everything the Arduino and SIM800C reply is shown in the log at the bottom.

From the command line, when a detection reaches `--alert` (0.80 by default), the PC sends `ALERT 0.93` to the Arduino. The Arduino texts the number, at most once per minute (`COOLDOWN_MS`). The terminal prints what the SIM800C replied: `+CMGS:` means the message was sent, `ERROR` means it was not.

Web page: `uv run scripts/web.py` (or `make web`) opens http://127.0.0.1:8000. Drag in an image to see the boxes and confidence levels. It runs only on this computer; press Ctrl+C in the terminal to stop it.

## Hosting the web page (Railway)

The `Dockerfile` builds a small image with only the page, the server and `models/asclepius_bcc.onnx`. It installs `requirements-web.txt` (onnxruntime, numpy, opencv), not the training environment.

1. Push this folder to a GitHub repository.
2. In Railway: New Project, Deploy from GitHub repo, pick the repository. Railway finds the `Dockerfile` and builds it.
3. In the service's Settings, under Networking, generate a public domain.

Railway sets the `PORT` variable and the server listens on it automatically. To deploy a newly trained model, run `make export`, commit the updated `.onnx` and push.

To try the same container locally:

```powershell
docker build -t asclepius-web .
docker run --rm -p 8000:8000 asclepius-web      # then open http://127.0.0.1:8000
```

## What you get

| Path | Contents |
| --- | --- |
| `runs/<name>/weights/best.pt` | best PyTorch weights |
| `runs/<name>/` | `results.csv`, `results.png`, PR/F1 curves, confusion matrix, batch previews |
| `runs/eval_test/` | test-split plots |
| `models/asclepius_bcc.onnx` | the model to deploy |

## Dataset

`prepare_dataset.py` reads `PROJECT COMMISSION BCC/content/BCC_Asclepius_Dataset` (never modified) and writes `datasets/bcc`:

- The export has 3000 files but only 2452 distinct ISIC photos; 548 are repeats, many in a different split from their twin. One file per photo is kept.
- Photos are re-split 70/20/10 with a fixed seed: 1716 train, 490 val, 246 test, none shared.
- `manifest.csv` records which original file each image came from.

To add images without BCC (normal skin, other lesions), put them in `datasets/negatives/` and rerun `prepare_dataset.py`; they are included with empty labels.

## ONNX model format

- Input: `images`, float32 `(1, 3, 640, 640)`, RGB, values 0-1, letterboxed (grey padding 114).
- Output: `(1, 5, 8400)`; each column is `cx, cy, w, h, score` in letterboxed pixels. Apply a score threshold and NMS.

`scripts/predict_onnx.py` is a complete example using only `onnxruntime`, `numpy` and `opencv`.

## Limitations

- Every training image contains a BCC and there is only one class, so the model learns to find skin lesions, not to tell BCC from other lesions. Expect confident boxes on moles too unless negative images are added.
- Training images are dermoscopy close-ups. Accuracy on ordinary webcam frames will be lower.
- Scores are not comparable with the earlier Colab run (mAP50 0.909), which was validated partly on photos it had trained on.
