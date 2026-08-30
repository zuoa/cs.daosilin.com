FROM node:22-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json* ./
RUN npm install
COPY web/ ./
COPY tokens.css /tokens.css
RUN npm run build

FROM golang:1.26.6-bookworm AS demo-analyzer
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
RUN git init \
    && git remote add origin https://github.com/taua-almeida/cs2-analyser-tool.git \
    && git fetch --depth=1 origin 88cb54ea0267fc8f4a8ae8d03987b50aec2a0653 \
    && git checkout --detach FETCH_HEAD
COPY demo_analyzer/main.go /src/cmd/cs-site-demo/main.go
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/cs-demo-analyzer ./cmd/cs-site-demo

FROM python:3.12-slim
WORKDIR /app
ENV FLASK_APP=app.py
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt
COPY . .
COPY --from=web /web/dist /app/web/dist
COPY --from=demo-analyzer /out/cs-demo-analyzer /usr/local/bin/cs-demo-analyzer
RUN chmod +x ./entrypoint.sh
ENV TZ=Asia/Shanghai
ENV PYTHONPATH=/app
EXPOSE 5001/tcp
VOLUME /data
ENTRYPOINT ["/app/entrypoint.sh"]
