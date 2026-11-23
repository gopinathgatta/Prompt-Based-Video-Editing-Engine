FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-liberation2 ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY app ./app
COPY docs ./docs
ENV PS2_HOST=0.0.0.0 PS2_PORT=8000 PS2_DATA_DIR=/data PS2_MAX_UPLOAD_BYTES=209715200 PS2_FONT_FILE=/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf
EXPOSE 8000
VOLUME ["/data"]
CMD ["python", "-m", "app.server"]
