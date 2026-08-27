FROM node:22-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json* ./
RUN npm install
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
ENV FLASK_APP=app.py
RUN apt-get update && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt
COPY . .
COPY --from=web /web/dist /app/web/dist
RUN chmod +x ./entrypoint.sh
ENV TZ=Asia/Shanghai
ENV PYTHONPATH="/app:$PYTHONPATH"
EXPOSE 5001/tcp
VOLUME /data
ENTRYPOINT ["/app/entrypoint.sh"]
