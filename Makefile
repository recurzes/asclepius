# Shortcuts for the ASCLEPIUS pipeline. Run `make` to list them.
# Extra options go in ARGS, e.g.  make train ARGS="--epochs 150 --batch 32"

ARGS ?=
PORT ?= COM5
SOURCE ?= datasets/bcc/test/images/ISIC_0024331.jpg

.PHONY: help setup check data train resume train-s export eval predict webcam sms web all

help:
	@echo make setup     install the environment
	@echo make check     confirm the GPU is visible
	@echo make data      build datasets/bcc
	@echo make train     train yolo11n
	@echo make resume    continue an interrupted training run
	@echo make train-s   train the larger yolo11s
	@echo make export    export the latest run to models/asclepius_bcc.onnx
	@echo make eval      score best.pt and the ONNX on the test split
	@echo make predict   run the ONNX on one image: make predict SOURCE=photo.jpg
	@echo make webcam    run the ONNX on the webcam, q to quit
	@echo make sms      webcam + SMS alerts via Arduino: make sms PORT=COM5
	@echo make web       open the drag-and-drop web page
	@echo make all       train, export, eval

setup:
	uv sync

check:
	uv run python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"

data:
	uv run scripts/prepare_dataset.py $(ARGS)

train:
	uv run scripts/train.py $(ARGS)

resume:
	uv run scripts/train.py --resume $(ARGS)

train-s:
	uv run scripts/train.py --model yolo11s.pt --name bcc_yolo11s $(ARGS)

export:
	uv run scripts/export_onnx.py $(ARGS)

eval:
	uv run scripts/evaluate.py $(ARGS)

predict:
	uv run scripts/predict_onnx.py --source $(SOURCE) $(ARGS)

webcam:
	uv run scripts/predict_onnx.py --source 0 $(ARGS)

sms:
	uv run scripts/predict_onnx.py --source 0 --serial $(PORT) $(ARGS)

web:
	uv run scripts/web.py $(ARGS)

all: train export eval
