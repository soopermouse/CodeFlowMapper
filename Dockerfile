FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng git \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN pip install --no-cache-dir .

ENV CODEMAPPER_HOST=0.0.0.0 \
    CODEMAPPER_PORT=8080 \
    CODEMAPPER_DATA=/data
VOLUME ["/data"]
EXPOSE 8080

CMD ["codemapper", "serve"]
