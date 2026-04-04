# Streaming RTSP Video to VRChat — Reference Guide

A compilation of findings, gotchas, and encoding settings for reliably streaming RTSP video into VRChat worlds.

---

## How VRChat Plays Video

- VRChat uses **AVPro Video** as its video player backend on PCVR
- AVPro delegates to **Windows Media Foundation (WMF)** for RTSP/H.264 decoding
- WMF is significantly less tolerant than VLC/mpv — it expects strictly compliant streams
- Quest (Android) uses a different decoder stack but has similar constraints

### Video Player Prefabs

VRChat worlds use community-created video player prefabs. Common ones that support RTSP:

- **[VideoTXL](https://github.com/vrctxl/VideoTXL)** — full-featured, widely used
- **[ProTV](https://gitlab.com/techanon/protv)** — another popular choice
- **[USharpVideo](https://github.com/MerlinVR/USharpVideo)** — lightweight option
- **iwaSync3** — common in public worlds (supports RTSP but has high/variable latency)

All of these rely on AVPro for RTSP playback.

---

## URL Allowlist

VRChat maintains an allowlist of trusted video hosts. Self-hosted RTSP streams are **not** on this list.

- Users must enable **"Allow Untrusted URLs"** in VRChat Settings for your stream to work
- Quest/Android requires HTTPS for non-allowlisted hosts (RTSP is exempt from this)
- The full allowlist is at: https://creators.vrchat.com/worlds/udon/video-players/www-whitelist

### Allowlisted services (as of 2026)

| Service | Domains |
|---------|---------|
| YouTube | `*.youtube.com`, `youtu.be` |
| Twitch | `*.twitch.tv`, `*.ttvnw.net` |
| Vimeo | `*.vimeo.com` |
| VRCDN | `*.vrcdn.live`, `*.vrcdn.video` |
| Topaz Chat | `*.topaz.chat` |
| NicoNico | `*.nicovideo.jp` |

Self-hosted RTSP is not on this list — users need Untrusted URLs enabled.

---

## RTSP Server: MediaMTX

[MediaMTX](https://github.com/bluenviron/mediamtx) is the recommended RTSP server:

- Lightweight single-binary Go server
- Receives RTSP/RTMP push from FFmpeg, rebroadcasts to clients
- Actively maintained with VRChat-specific bug fixes

### Version Requirements

- **Use v1.15.4 or later** — earlier versions have a timeout bug where WMF's keep-alive arrives at exactly 60 seconds but the server timeout is also 60 seconds, causing periodic stream drops
- This was fixed in [gortsplib#932](https://github.com/bluenviron/gortsplib/pull/932) (merged Nov 2025)
- If you see streams dropping/reconnecting every 1–3 minutes, upgrade MediaMTX

### Known Issues

| Issue | Versions Affected | Fix |
|-------|-------------------|-----|
| WMF timeout (stream drops every 60s) | v1.14.0 – v1.15.3 | Upgrade to v1.15.4+ |
| RTP reorderer causing stuttering | v1.14.0+ | Fixed in later releases |
| NAT loopback instability | All | Use split DNS or hosts file for local access |

### NAT Loopback / Hairpin NAT

If your server and VR headset are on the same network but you're using an external hostname:

- Many consumer routers don't support NAT loopback (hairpin NAT)
- VRChat resolves the hostname to your public IP, but the router can't route it back internally
- **Fix**: Use split DNS or add the hostname to your local DNS/hosts file pointing to the LAN IP

---

## FFmpeg Encoding Settings

This is the critical part. WMF is very particular about what it can decode.

### Working FFmpeg Command

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

### Settings Explained

#### Profile & Level

| Setting | Value | Why |
|---------|-------|-----|
| `-profile:v baseline` | Baseline profile | Simplest H.264 profile — no B-frames, no CABAC. WMF decodes this reliably. |
| `-level 4.0` | Level 4.0 | Caps complexity. All modern decoders support this. |
| `-bf 0` | No B-frames | Explicit — baseline forbids them, but this is belt-and-suspenders. |

#### Tune & Threading

| Setting | Value | Why |
|---------|-------|-----|
| `-tune fastdecode` | Fast decode | Disables deblocking loop filter and CABAC — lighter decoding for VR headsets. |
| `sliced-threads=0` | Disabled | **CRITICAL** — sliced-threads splits frames into horizontal strips encoded in parallel. WMF cannot reassemble them correctly, producing **vertical streak/smear artifacts**. |

> **WARNING**: Do NOT use `-tune zerolatency`. It enables `sliced-threads`, which causes severe vertical streak corruption in VRChat. This is the single most common cause of broken video.

#### Bitrate & VBV Buffer

| Setting | Value | Why |
|---------|-------|-----|
| `-b:v 2500k` | 2.5 Mbps target | Comfortable average — leaves headroom under the cap. |
| `-maxrate 3500k` | 3.5 Mbps cap | VRChat over WiFi struggles above this. Higher rates cause packet loss. |
| `-bufsize 3500k` | 1x maxrate | Tight buffer prevents bitrate spikes during complex scenes. A loose buffer (e.g. 2x) lets the encoder spike, which causes network congestion and packet loss → macro-blocking artifacts. |

> **Total stream bitrate**: ~2500k video + 192k audio ≈ 2.7 Mbps average, 3.7 Mbps peak.
> Keep total under ~3.5–4 Mbps for reliable WiFi delivery to VR headsets.

#### Keyframes & Recovery

| Setting | Value | Why |
|---------|-------|-----|
| `-g 30` | Keyframe every 30 frames (~1 sec) | When a packet is lost, the decoder shows corruption until the next keyframe. Shorter intervals = faster recovery. |
| `-keyint_min 15` | Min 15 frames between keyframes | Prevents wasteful back-to-back keyframes. |
| `-sc_threshold 0` | No scene-change keyframes | Scene-change detection inserts extra keyframes unpredictably, causing bitrate spikes. Disabled for stable bitrate. |

#### NAL Unit Headers

| Setting | Value | Why |
|---------|-------|-----|
| `aud=1` | Access Unit Delimiters | Helps WMF find frame boundaries and resync after packet loss. |
| `repeat-headers=1` | Repeat SPS/PPS | Sends codec configuration with every keyframe so the decoder can rejoin mid-stream without needing the original handshake headers. |

#### Output

| Setting | Value | Why |
|---------|-------|-----|
| `-f rtsp` | RTSP output | VRChat AVPro supports RTSP natively. |
| `-rtsp_transport tcp` | TCP transport | More reliable than UDP over WiFi — no packet loss from the encoder to MediaMTX. Clients can still use UDP from MediaMTX. |
| `-re` | Real-time rate | Streams at 1x playback speed — essential for live streaming. |

---

## Common Problems & Solutions

### Vertical streak / smear artifacts

**Symptom**: Video looks like vertical colored bars/streaks, audio is fine.

**Cause**: `-tune zerolatency` enables `sliced-threads` in x264. WMF can't reassemble sliced frames.

**Fix**: Use `-tune fastdecode` and add `-x264-params sliced-threads=0`.

### Macro-blocking / corruption that recovers

**Symptom**: Video plays cleanly, then suddenly becomes blocky/garbled, then recovers after a second or two.

**Cause**: Packet loss — a network packet is dropped, and the decoder shows corruption until the next keyframe arrives.

**Fix**:
- Lower bitrate (reduce `-b:v` and `-maxrate`) to prevent network congestion
- Tighten VBV buffer (`-bufsize` = `-maxrate`) to prevent bitrate spikes
- Increase keyframe frequency (lower `-g` value) for faster recovery
- Disable scene-change keyframes (`-sc_threshold 0`) to prevent spikes

### Stream drops / reconnects every 1–3 minutes

**Symptom**: Video plays for a minute, goes black, then restarts.

**Cause**: MediaMTX timeout bug — WMF sends keep-alive at exactly 60 seconds, matching the server timeout.

**Fix**: Upgrade MediaMTX to v1.15.4 or later.

### Stream won't play at all (works in VLC)

**Symptom**: RTSP URL works in VLC but not in VRChat.

**Possible causes**:
- "Allow Untrusted URLs" not enabled in VRChat settings
- Using High profile or Main profile H.264 (switch to Baseline)
- RTSP server not reachable from the VR headset's network
- NAT loopback issue (see above)

### Stuttering on initial connect

**Symptom**: Stream stutters for the first few seconds after connecting, then stabilizes (or doesn't).

**Cause**: RTP reorderer in MediaMTX (fixed in newer versions) or bitrate too high for the network path.

**Fix**: Upgrade MediaMTX; reduce bitrate if on congested WiFi.

---

## What NOT to Do

| Don't | Why |
|-------|-----|
| Use `-tune zerolatency` | Enables sliced-threads → vertical streak artifacts |
| Use High or Main profile | WMF has issues with B-frames and CABAC in RTSP |
| Set bitrate above 4 Mbps | WiFi packet loss → macro-blocking |
| Use a large VBV buffer (e.g. 16M) | Allows bitrate spikes → packet loss |
| Use HEVC/H.265 | AVPro RTSP doesn't support it |
| Use VP8/VP9 | Not supported over RTSP in VRChat |
| Skip `repeat-headers` | Clients that join mid-stream won't get SPS/PPS → no video |
| Use old MediaMTX (< 1.15.4) | Timeout bug causes periodic stream drops |

---

## Recommended MediaMTX Config

```yaml
logLevel: warn
logDestinations: [stdout]

api: true
apiAddress: :9997

rtsp: true
rtspAddress: :8554

# Prefer TCP for WiFi reliability
protocols: [tcp, udp]

paths:
  all_others:
```

---

## Testing

1. **VLC**: Test your RTSP URL in VLC first — if it doesn't work here, it won't work in VRChat
2. **VRChat**: Join a world with a video player, paste the URL, verify playback
3. **ffprobe**: Verify your stream settings:
   ```bash
   ffprobe -v quiet -show_streams rtsp://localhost:8554/stream
   ```
   Check that `profile=Baseline`, `level=40`, and there are no B-frames.

---

## References

- [VRChat Video Players documentation](https://creators.vrchat.com/worlds/udon/video-players/)
- [VRChat Video Player Allowlist](https://creators.vrchat.com/worlds/udon/video-players/www-whitelist)
- [MediaMTX GitHub](https://github.com/bluenviron/mediamtx)
- [MediaMTX VRChat blackout fix (issue #5090)](https://github.com/bluenviron/mediamtx/issues/5090)
- [MediaMTX AVPro RTSP issue (#3585)](https://github.com/bluenviron/mediamtx/issues/3585)
- [VideoTXL](https://github.com/vrctxl/VideoTXL)
- [ProTV](https://gitlab.com/techanon/protv)
- [USharpVideo](https://github.com/MerlinVR/USharpVideo)
