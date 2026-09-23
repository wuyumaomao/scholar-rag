FROM python:3.12-slim

WORKDIR /app

RUN sed -i \
    -e 's|http://deb.debian.org/debian|https://mirrors.aliyun.com/debian|g' \
    -e 's|http://deb.debian.org/debian-security|https://mirrors.aliyun.com/debian-security|g' \
    /etc/apt/sources.list.d/debian.sources

RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libgl1 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libxcb1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir https://mirrors.aliyun.com/pytorch-wheels/cpu/torch-2.5.1%2Bcpu-cp312-cp312-linux_x86_64.whl
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p uploads

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
