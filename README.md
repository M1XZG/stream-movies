# Stream Movies

RTSP streaming server with a web UI for browsing and playing movie files. Designed for VR headsets (VRChat, Meta Quest, PCVR) but works with any RTSP client.

## Quick Start (Docker)

```bash
# 1. Copy and edit your config
cp .env.example .env

# 2. Edit docker-compose.yml to mount your media directory
#    volumes:
#      - /your/movies:/media:ro

# 3. Start
docker compose up -d
```

Open **http://\<server-ip\>:10090** to browse and stream.

## How It Works

1. Open the web UI and browse your movie files
2. Click a movie to start streaming — FFmpeg transcodes it to H.264 and pushes to an RTSP server
3. Copy the RTSP URL from the header bar
4. Paste it into your VR headset's video player (or VLC, mpv, etc.)

Use the playback controls to play, pause, seek, and stop. The web UI shows real-time encoding stats, source file info, RTSP server status, and per-viewer connection details.

## Ports

| Port  | Service          |
|-------|------------------|
| 10090 | Web UI           |
| 8554  | RTSP stream      |
| 9997  | MediaMTX API     |

## Configuration

All settings are environment variables. Copy `.env.example` to `.env` — see [docs/configuration.md](docs/configuration.md) for the full reference.

Key settings:

| Variable            | Default  | Description                           |
|---------------------|----------|---------------------------------------|
| `MEDIA_DIR`         | `/media` | Path to your movie files              |
| `VIDEO_BITRATE`     | `2500k`  | Video encoding bitrate                |
| `MAX_BITRATE`       | `3500k`  | Max bitrate cap                       |
| `RTSP_EXTERNAL_URL` | *(empty)* | Public RTSP URL shown in the web UI  |
| `ENCODE_PRESET`     | `veryfast` | x264 speed preset                   |

## Documentation

| Document | Description |
|----------|-------------|
| [docs/configuration.md](docs/configuration.md) | Full configuration reference |
| [docs/encoding.md](docs/encoding.md) | FFmpeg encoding settings and bitrate budgets |
| [docs/vr-setup.md](docs/vr-setup.md) | Connecting VR headsets (VRChat, Quest, PCVR) |
| [docs/vrchat-streaming.md](docs/vrchat-streaming.md) | VRChat-specific RTSP streaming deep dive |
| [docs/architecture.md](docs/architecture.md) | System architecture and API reference |

## Supported Formats

`.mp4` `.mkv` `.avi` `.mov` `.wmv` `.flv` `.webm` `.m4v` `.ts` `.mts` `.m2ts`

All output is transcoded to H.264 + AAC.

## License

[MIT](LICENSE)
