# Stream Movies — RTSP Streaming for VR Headsets

## Overview

A self-contained RTSP streaming system that serves movie files from an NFS mount to PCVR and Meta Quest headsets. Includes a web UI for browsing and controlling playback.

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  NFS Mount (/nfs-mount/ENTERTAINMENT)                            │
│    └── Movie files (.mkv, .mp4, .avi, etc.)                      │
└────────────────────┬─────────────────────────────────────────────┘
                     │ read
                     ▼
┌──────────────────────────────────────────────────────────────────┐
│  Python App (FastAPI) — port 10090                               │
│  ┌────────────────┐  ┌────────────────┐  ┌──────────────────┐   │
│  │  Web UI Server  │  │  REST API       │  │  FFmpeg Manager   │  │
│  │  (static files) │  │  (controls)     │  │  (subprocess)     │  │
│  └────────────────┘  └────────────────┘  └──────┬───────────┘   │
│                                                  │ rtsp push     │
│  ┌───────────────────────────────────────────────▼───────────┐   │
│  │  MediaMTX (RTSP Server) — port 8554                       │   │
│  │  Receives stream from FFmpeg, serves to RTSP clients       │   │
│  └───────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
                     │ rtsp://host:8554/stream
                     ▼
┌──────────────────────────────────────────────────────────────────┐
│  VR Headset (Meta Quest / PCVR)                                  │
│  App: SKYBOX, DeoVR, Pigasus, Virtual Desktop, etc.              │
└──────────────────────────────────────────────────────────────────┘
```

## Components

### 1. MediaMTX (RTSP Server)
- Lightweight Go binary, zero dependencies
- Receives RTSP stream from FFmpeg and rebroadcasts to clients
- Runs on port 8554 (default RTSP port)
- Managed as a subprocess by the Python app

### 2. FFmpeg (Transcoder/Streamer)
- Reads movie files from the NFS mount
- Transcodes to H.264 Baseline + AAC (maximum VR client compatibility)
- Tuned for VRChat AVPro / Windows Media Foundation decoders
- Pushes RTSP stream to MediaMTX
- Managed as a subprocess with SIGSTOP/SIGCONT for pause/resume
- Seeking implemented by restarting FFmpeg at the new position

### 3. FastAPI (Web Server + API)
- Serves the web UI on port 10090
- Provides REST API for file browsing and playback control
- Manages both MediaMTX and FFmpeg lifecycles

### 4. Web UI (Frontend)
- Movie file browser with folder navigation
- Live search across all subdirectories (debounced, 300ms)
- Now Playing panel with progress bar
- Controls: Play, Pause, Resume, Stop, Seek ±30s, progress bar seeking
- Displays local and external RTSP URLs for VR headset connection (click to copy)
- Always-visible stream stats: encoding metrics, source file info, RTSP server stats
- Per-viewer connection details: IP, transport, data sent, RTP packets, packet loss, jitter, duration
- Separate connections panel: viewer count with detailed per-session metrics

## API Endpoints

| Method | Endpoint                | Description                        |
|--------|-------------------------|------------------------------------|
| GET    | `/`                     | Serve web UI                       |
| GET    | `/api/files?path=`      | List files/folders                 |
| GET    | `/api/files/search?q=`  | Recursive filename search          |
| GET    | `/api/files/info?path=` | Get media file info (duration etc) |
| POST   | `/api/stream/play`      | Start streaming a file             |
| POST   | `/api/stream/pause`     | Pause playback (SIGSTOP)           |
| POST   | `/api/stream/resume`    | Resume playback (SIGCONT)          |
| POST   | `/api/stream/stop`      | Stop playback                      |
| POST   | `/api/stream/seek`      | Seek relative (±seconds)           |
| POST   | `/api/stream/seek_absolute` | Seek to absolute position      |
| GET    | `/api/stream/status`    | Get playback state + position      |
| GET    | `/api/stream/stats`     | Encoding, source, connection stats |
| GET    | `/api/config`           | Get RTSP URL and config            |

## Playback Control Implementation

- **Play**: Start FFmpeg subprocess reading file at given offset, push to RTSP
- **Pause**: Send `SIGSTOP` to FFmpeg process (stream freezes on last frame)
- **Resume**: Send `SIGCONT` to FFmpeg process (stream continues)
- **Stop**: Send `SIGTERM` to FFmpeg process group
- **Seek ±30s**: Kill current FFmpeg, restart at `current_position ± 30s`
- **Progress bar seek**: Kill current FFmpeg, restart at clicked position
- **Position tracking**: Wall-clock time calculation with pause duration accounting
  - `position = start_offset + (now - playback_start - total_pause_time)`
  - Works because FFmpeg runs with `-re` (real-time / 1x speed)

## FFmpeg Command

```bash
ffmpeg -y -ss <offset> -re -i <input_file> \
    -c:v libx264 -profile:v baseline -level 4.0 \
    -preset veryfast -tune fastdecode \
    -b:v 2500k -maxrate 3500k -bufsize 3500k \
    -bf 0 -g 30 -keyint_min 15 -sc_threshold 0 \
    -x264-params sliced-threads=0:aud=1:repeat-headers=1 \
    -vf "scale='min(1920,iw)':'min(1080,ih)':force_original_aspect_ratio=decrease" \
    -pix_fmt yuv420p \
    -c:a aac -b:a 192k -ac 2 \
    -f rtsp -rtsp_transport tcp rtsp://localhost:8554/stream \
    -progress pipe:1
```

Key flags:
- `-re`: Read input at native rate (1x speed) — essential for live streaming
- `-ss` before `-i`: Fast input seeking (seeks to nearest keyframe)
- `-profile:v baseline -level 4.0`: Simplest H.264 profile — no B-frames, no CABAC, maximum decoder compatibility
- `-tune fastdecode`: Simplifies decoding without enabling sliced-threads (unlike `zerolatency` which breaks VRChat/WMF decoders)
- `-bf 0`: Explicitly disables B-frames
- `-g 30 -keyint_min 15`: Keyframe every ~1 second for fast recovery from packet loss
- `-sc_threshold 0`: Disables scene-change keyframes to prevent unpredictable bitrate spikes
- `-maxrate 3500k -bufsize 3500k`: Tight VBV buffer prevents bitrate spikes that cause network congestion
- `sliced-threads=0`: Disables slice threading (causes vertical streak artifacts in WMF-based decoders)
- `aud=1`: Access Unit Delimiters help WMF resync after packet loss
- `repeat-headers=1`: Repeats SPS/PPS with every keyframe so decoder can rejoin mid-stream
- `-rtsp_transport tcp`: Reliable over WiFi (VR headsets)
- `-progress pipe:1`: Outputs encoding stats as newline-delimited key=value pairs to stdout

## Configuration (Environment Variables)

See `.env.example` for a template. All settings have sensible defaults.

| Variable            | Default       | Description                                    |
|---------------------|---------------|------------------------------------------------|
| `MEDIA_DIR`         | `/media`      | Path to movie files                            |
| `WEB_PORT`          | `10090`       | Web UI port                                    |
| `RTSP_PORT`         | `8554`        | MediaMTX RTSP port                             |
| `STREAM_PATH`       | `stream`      | RTSP stream path                               |
| `RTSP_EXTERNAL_URL` | *(empty)*     | External RTSP URL shown in web UI              |
| `VIDEO_BITRATE`     | `2500k`       | Video encoding bitrate                         |
| `MAX_BITRATE`       | `3500k`       | Video max bitrate (VBV ceiling)                |
| `BUFFER_SIZE`       | `3500k`       | VBV buffer size                                |
| `AUDIO_BITRATE`     | `192k`        | Audio encoding bitrate                         |
| `AUDIO_CHANNELS`    | `2`           | Audio channel count                            |
| `MAX_WIDTH`         | `1920`        | Max output width                               |
| `MAX_HEIGHT`        | `1080`        | Max output height                              |
| `ENCODE_PRESET`     | `veryfast`    | x264 encoding preset                           |
| `MEDIAMTX_PATH`     | `./mediamtx`  | Path to MediaMTX binary                        |
| `MANAGE_MEDIAMTX`   | `true`        | Auto-start MediaMTX subprocess                 |
| `MEDIAMTX_API_PORT` | `9997`        | MediaMTX REST API port                         |
| `RTSP_PUBLISH_HOST` | `localhost`   | Host FFmpeg publishes RTSP to                  |
| `FFMPEG_PATH`       | `ffmpeg`      | Path to ffmpeg                                 |
| `FFPROBE_PATH`      | `ffprobe`     | Path to ffprobe                                |
| `LOG_LEVEL`         | `INFO`        | Logging level                                  |

## VR Headset Setup

### VRChat
1. Use a world with an AVPro-based video player (e.g. VideoTXL, ProTV, USharpVideo)
2. Paste the RTSP URL into the video player URL input
3. Enable **Allow Untrusted URLs** in VRChat settings for non-allowlisted hosts
4. Stream is encoded with baseline profile H.264, optimized for AVPro/Windows Media Foundation

### Meta Quest (standalone)
1. Install **SKYBOX VR Player** or **DeoVR** from the Quest Store
2. Open the app and navigate to Network/RTSP streams
3. Enter the RTSP URL: `rtsp://<server-ip>:8554/stream`
4. The movie plays on a virtual cinema screen

### PCVR (SteamVR / Virtual Desktop)
1. Use **DeoVR**, **Virtual Desktop**, or **Bigscreen**
2. Open the RTSP stream URL in the player
3. Alternatively, open VLC in desktop mode within VR

## File Structure

```
stream-movies/
├── docs/                # Documentation
├── requirements.txt     # Python dependencies
├── mediamtx.yml         # MediaMTX RTSP server configuration
├── Dockerfile           # Docker image build (MediaMTX v1.15.4)
├── docker-compose.yml   # Docker Compose deployment
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI app entry point + routes
│   ├── config.py        # Configuration dataclass
│   ├── streamer.py      # FFmpeg streaming engine
│   └── scanner.py       # Media file discovery + ffprobe
└── static/
    ├── index.html       # Web UI
    ├── style.css        # Styles (dark theme)
    └── app.js           # Frontend JavaScript
```

## Supported Video Formats

Containers: `.mp4`, `.mkv`, `.avi`, `.mov`, `.wmv`, `.flv`, `.webm`, `.m4v`, `.ts`, `.mts`, `.m2ts`

Output: H.264 video + AAC audio (maximum client compatibility)

## Future Enhancements

- [ ] Hardware-accelerated encoding (NVENC, QSV, VAAPI)
- [ ] Multiple simultaneous streams / stream selection
- [ ] Subtitle support (burn-in via FFmpeg `-vf subtitles=`)
- [ ] 3D/VR content metadata detection (SBS, Over-Under)
- [ ] Thumbnail generation for movie browser
- [ ] Resume playback (persist last position per file)
- [ ] HLS fallback stream for web browser playback
- [ ] Volume control
- [ ] Audio track selection
- [ ] Codec passthrough mode (`-c:v copy`) for compatible sources
- [ ] Queue / playlist support
- [ ] GPU encoding auto-detection

## Development Notes

- Single-stream design (one movie at a time) — suited for personal use
- Position tracking uses wall-clock time (not FFmpeg progress parsing)
- SIGSTOP/SIGCONT used for pause/resume — RTSP clients see frozen frame during pause
- Seeking causes brief stream interruption (FFmpeg restart)
- MediaMTX managed as subprocess for single-command startup
- MediaMTX REST API (port 9997) used for comprehensive stats:
  - Path-level: online status, bytes in/out, frame errors, track details
  - Per-session: viewer IP, transport, RTP packets sent/lost/discarded, jitter, connection time
  - Server info: MediaMTX version
- MediaMTX v1.15.4 used in Docker (fixes WMF timeout bug, adds `online` field and per-session RTP stats)
- Clipboard copy uses `document.execCommand('copy')` fallback for plain HTTP (navigator.clipboard requires HTTPS)
- FFmpeg progress parsed via `-progress pipe:1` (stdout) — reliable newline output vs \r-based stderr
- Search is recursive filesystem walk with case-insensitive filename matching, capped at 50 results
- Connections panel auto-shows when viewers are connected, hides when idle
- Stream stats always visible (no toggle) for at-a-glance monitoring
- External RTSP URL displayed in header alongside local URL, both click-to-copy

## VRChat Compatibility Notes

- VRChat uses AVPro Video backed by Windows Media Foundation (WMF) for RTSP decoding
- **Do NOT use `-tune zerolatency`** — it enables `sliced-threads` which causes vertical streak artifacts in WMF decoders
- Use `-tune fastdecode` instead — simplifies decoding without slice threading
- H.264 Baseline profile required — WMF has issues with B-frames and CABAC
- Keep total bitrate under 3500kbps — higher rates cause packet loss and macro-blocking corruption
- Tight VBV buffer (bufsize = maxrate) prevents bitrate spikes during complex scenes
- AUD markers (`aud=1`) and repeated headers (`repeat-headers=1`) help WMF resync after packet loss
- Frequent keyframes (~1 per second) minimize recovery time when frames are lost
- MediaMTX v1.15.4+ recommended — earlier versions have timeout bugs with WMF keep-alive behavior
