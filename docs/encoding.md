# Encoding Settings

These settings are tuned for VRChat AVPro (Windows Media Foundation) compatibility but work well with any RTSP client.

## Video

| Setting | Flag | Value | Description |
|---------|------|-------|-------------|
| Codec | `-c:v` | `libx264` | H.264 software encoder |
| Profile | `-profile:v` | `baseline` | Simplest H.264 profile, no B-frames/CABAC |
| Level | `-level` | `4.0` | Max decoder complexity cap |
| Preset | `-preset` | `veryfast` | Encoding speed vs compression tradeoff |
| Tune | `-tune` | `fastdecode` | Lighter decoding, no sliced-threads |
| Target Bitrate | `-b:v` | `2500k` | Average video bitrate — configurable via `VIDEO_BITRATE` |
| Max Bitrate | `-maxrate` | `3500k` | Hard bitrate ceiling — configurable via `MAX_BITRATE` |
| VBV Buffer | `-bufsize` | `3500k` | Tight buffer (1x maxrate) — configurable via `BUFFER_SIZE` |
| B-Frames | `-bf` | `0` | Disabled |
| Keyframe Interval | `-g` | `30` | Max 30 frames between keyframes (~1 sec) |
| Min Keyframe Interval | `-keyint_min` | `15` | At least 15 frames between keyframes |
| Scene Change Detection | `-sc_threshold` | `0` | Disabled (prevents bitrate spikes) |
| Sliced Threads | `sliced-threads` | `0` | Disabled (prevents WMF artifacts) |
| Access Unit Delimiters | `aud` | `1` | Helps decoder resync after packet loss |
| Repeat Headers | `repeat-headers` | `1` | SPS/PPS sent with every keyframe |
| Max Resolution | `-vf scale` | `1920×1080` | Downscales if source is larger |
| Pixel Format | `-pix_fmt` | `yuv420p` | Universal compatibility |
| Playback Rate | `-re` | enabled | Real-time (1x speed) |

## Audio

| Setting | Flag | Value | Description |
|---------|------|-------|-------------|
| Codec | `-c:a` | `aac` | AAC audio |
| Bitrate | `-b:a` | `192k` | Audio bitrate |
| Channels | `-ac` | `2` | Stereo — configurable via `AUDIO_CHANNELS` |

## Transport

| Setting | Flag | Value | Description |
|---------|------|-------|-------------|
| Format | `-f` | `rtsp` | RTSP output |
| Transport | `-rtsp_transport` | `tcp` | TCP (reliable over WiFi) |
| Input Seeking | `-ss` | before `-i` | Fast seek to nearest keyframe |

## Total Stream Budget

| Component | Bitrate |
|-----------|---------|
| Video (average) | ~2,500 kbps |
| Video (peak) | ~3,500 kbps |
| Audio | 192 kbps |
| **Total (average)** | **~2,700 kbps** |
| **Total (peak)** | **~3,700 kbps** |

## Full FFmpeg Command

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
    -f rtsp -rtsp_transport tcp rtsp://localhost:8554/stream
```
