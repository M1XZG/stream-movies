# Connecting a VR Headset

## VRChat

1. Use a world with an AVPro-based video player (e.g. VideoTXL, ProTV, USharpVideo)
2. Paste the RTSP URL `rtsp://<server-ip>:8554/stream` into the video player input
3. Users must enable **Allow Untrusted URLs** in VRChat settings for non-allowlisted hosts
4. The stream is encoded with baseline profile H.264 — optimized for VRChat's AVPro/Windows Media Foundation decoder

For a deep dive on VRChat-specific encoding, troubleshooting, and compatibility, see [vrchat-streaming.md](vrchat-streaming.md).

## Meta Quest (standalone)

1. Install **SKYBOX VR Player** or **DeoVR** from the Quest Store
2. Open the app → Network / RTSP streams
3. Enter `rtsp://<server-ip>:8554/stream`

## PCVR (SteamVR / Virtual Desktop)

1. Use **DeoVR**, **Virtual Desktop**, or **Bigscreen**
2. Open the RTSP URL in the player's network stream input

## External RTSP URL

If you want to share a public-facing URL, set the `RTSP_EXTERNAL_URL` environment variable. The web UI will display both local and external URLs, each click-to-copy.

## Troubleshooting

**Stream not playing** — Ensure port 8554 is reachable from the headset's network. Check that the headset and server are on the same subnet / VLAN.

**Choppy playback** — Lower `VIDEO_BITRATE` (e.g. `2000k`) or switch `ENCODE_PRESET` to `ultrafast`. WiFi 5GHz is strongly recommended for VR headsets.

**Video artifacts in VRChat** — The stream uses H.264 baseline profile, `-tune fastdecode`, and no sliced-threads. If you still see corruption, lower `VIDEO_BITRATE` to reduce packet loss. See [vrchat-streaming.md](vrchat-streaming.md) for details.

**MediaMTX not starting** — Verify the binary exists at the configured path. Download manually from [mediamtx releases](https://github.com/bluenviron/mediamtx/releases) or rebuild the Docker image.

**No video files shown** — Confirm `MEDIA_DIR` points to the correct path and contains files with supported extensions.
