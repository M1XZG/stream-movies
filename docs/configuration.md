# Configuration Reference

All settings are controlled via environment variables. Copy `.env.example` to `.env` and adjust as needed.

## Environment Variables

| Variable            | Default       | Description                                    |
|---------------------|---------------|------------------------------------------------|
| `MEDIA_DIR`         | `/media`      | Path to movie files                            |
| `WEB_PORT`          | `10090`       | Web UI port                                    |
| `RTSP_PORT`         | `8554`        | RTSP server port                               |
| `STREAM_PATH`       | `stream`      | RTSP stream path (e.g. `rtsp://host:8554/stream`) |
| `RTSP_EXTERNAL_URL` | *(empty)*     | External RTSP URL shown in the web UI          |
| `VIDEO_BITRATE`     | `2500k`       | Video encoding bitrate                         |
| `MAX_BITRATE`       | `3500k`       | Video max bitrate (VBV ceiling)                |
| `BUFFER_SIZE`       | `3500k`       | VBV buffer size                                |
| `AUDIO_BITRATE`     | `192k`        | Audio encoding bitrate                         |
| `AUDIO_CHANNELS`    | `2`           | Audio channels (2 = stereo)                    |
| `MAX_WIDTH`         | `1920`        | Max output width                               |
| `MAX_HEIGHT`        | `1080`        | Max output height                              |
| `ENCODE_PRESET`     | `veryfast`    | x264 encoding preset                           |
| `MEDIAMTX_PATH`     | `./mediamtx`  | Path to MediaMTX binary                        |
| `MANAGE_MEDIAMTX`   | `true`        | Auto-start MediaMTX subprocess                 |
| `MEDIAMTX_API_PORT` | `9997`        | MediaMTX REST API port                         |
| `RTSP_PUBLISH_HOST` | `localhost`   | Host FFmpeg publishes RTSP to                  |
| `FFMPEG_PATH`       | `ffmpeg`      | Path to ffmpeg                                 |
| `FFPROBE_PATH`      | `ffprobe`     | Path to ffprobe                                |
| `LOG_LEVEL`         | `INFO`        | Logging level (DEBUG, INFO, WARNING, ERROR)    |

## Docker Configuration

The `docker-compose.yml` reads from `.env` automatically. You can also set variables directly:

```yaml
environment:
  - VIDEO_BITRATE=2000k
  - RTSP_EXTERNAL_URL=rtsp://my-domain.com/stream
```

## Supported Video Formats

`.mp4`, `.mkv`, `.avi`, `.mov`, `.wmv`, `.flv`, `.webm`, `.m4v`, `.ts`, `.mts`, `.m2ts`

All output is transcoded to H.264 + AAC for maximum VR client compatibility.
