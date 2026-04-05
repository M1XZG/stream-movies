import os
from dataclasses import dataclass


@dataclass
class Config:
    media_dir: str = os.getenv("MEDIA_DIR", "/media")
    web_port: int = int(os.getenv("WEB_PORT", "10090"))
    rtsp_port: int = int(os.getenv("RTSP_PORT", "8554"))
    mediamtx_path: str = os.getenv("MEDIAMTX_PATH", "./mediamtx")
    ffmpeg_path: str = os.getenv("FFMPEG_PATH", "ffmpeg")
    ffprobe_path: str = os.getenv("FFPROBE_PATH", "ffprobe")
    video_bitrate: str = os.getenv("VIDEO_BITRATE", "2500k")
    max_bitrate: str = os.getenv("MAX_BITRATE", "3500k")
    buffer_size: str = os.getenv("BUFFER_SIZE", "3500k")
    audio_bitrate: str = os.getenv("AUDIO_BITRATE", "192k")
    audio_channels: int = int(os.getenv("AUDIO_CHANNELS", "2"))
    max_width: int = int(os.getenv("MAX_WIDTH", "1920"))
    max_height: int = int(os.getenv("MAX_HEIGHT", "1080"))
    encode_preset: str = os.getenv("ENCODE_PRESET", "veryfast")
    rtsp_external_url: str = os.getenv("RTSP_EXTERNAL_URL", "")
    stream_path: str = os.getenv("STREAM_PATH", "stream")
    hls_port: int = int(os.getenv("HLS_PORT", "8888"))
    hls_external_url: str = os.getenv("HLS_EXTERNAL_URL", "")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    idle_enabled: bool = os.getenv("IDLE_STREAM", "true").lower() in ("true", "1", "yes")
    idle_image: str = os.getenv("IDLE_IMAGE", "/app/assets/idle.png")
    manage_mediamtx: bool = os.getenv("MANAGE_MEDIAMTX", "true").lower() in ("true", "1", "yes")
    rtsp_publish_host: str = os.getenv("RTSP_PUBLISH_HOST", "localhost")
    mediamtx_api_port: int = int(os.getenv("MEDIAMTX_API_PORT", "9997"))
