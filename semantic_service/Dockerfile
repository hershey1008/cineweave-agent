FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 USE_TF=0 HF_HOME=/models HF_HUB_DISABLE_XET=1
RUN pip install --no-cache-dir torch==2.6.0 --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . /app/semantic_service
CMD ["uvicorn", "semantic_service.app.main:app", "--host", "0.0.0.0", "--port", "8010"]
