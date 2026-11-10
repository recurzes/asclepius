# Web version of ASCLEPIUS: the ONNX model plus the drag-and-drop page.
FROM python:3.12-slim

WORKDIR /app

COPY requirements-web.txt .
RUN pip install --no-cache-dir -r requirements-web.txt

COPY scripts/predict_onnx.py scripts/web.py scripts/
COPY web/ web/
COPY models/asclepius_bcc.onnx models/

# Railway replaces PORT with its own value; 8000 is the default elsewhere.
ENV PORT=8000 PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["python", "scripts/web.py"]
