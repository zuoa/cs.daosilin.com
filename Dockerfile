FROM python:3.12-slim
WORKDIR /app

ENV FLASK_APP=app.py

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt;
COPY . .
RUN chmod +x ./entrypoint.sh

ENV TZ=Asia/Shanghai
ENV PYTHONPATH="/app:$PYTHONPATH"
EXPOSE 7082/tcp
VOLUME /data
ENTRYPOINT ["/app/entrypoint.sh"]
