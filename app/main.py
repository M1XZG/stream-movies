import json
import logging
import subprocess
import urllib.request
import urllib.error
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import Config
from .scanner import list_directory, get_media_info, search_files
from .streamer import StreamEngine

logger = logging.getLogger(__name__)

config = Config()
logging.basicConfig(level=getattr(logging, config.log_level.upper(), logging.INFO),
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

engine = StreamEngine(config)

# MediaMTX subprocess handle
_mediamtx_proc = None


def _start_mediamtx():
    global _mediamtx_proc
    if not config.manage_mediamtx:
        logger.info("MediaMTX management disabled (MANAGE_MEDIAMTX=false)")
        return

    mtx_path = Path(config.mediamtx_path)
    if not mtx_path.exists():
        logger.warning(
            f"MediaMTX binary not found at '{mtx_path}'. "
            "RTSP server will NOT start. Run setup.sh or set MEDIAMTX_PATH."
        )
        return

    mediamtx_config = Path(__file__).parent.parent / "mediamtx.yml"
    cmd = [str(mtx_path)]
    if mediamtx_config.exists():
        cmd.append(str(mediamtx_config))

    logger.info(f"Starting MediaMTX: {' '.join(cmd)}")
    _mediamtx_proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    logger.info(f"MediaMTX started (PID {_mediamtx_proc.pid})")


def _stop_mediamtx():
    global _mediamtx_proc
    if _mediamtx_proc:
        logger.info("Stopping MediaMTX...")
        _mediamtx_proc.terminate()
        try:
            _mediamtx_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _mediamtx_proc.kill()
            _mediamtx_proc.wait(timeout=2)
        _mediamtx_proc = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    _start_mediamtx()
    media_dir = Path(config.media_dir)
    if not media_dir.exists():
        logger.warning(f"Media directory not found: {media_dir}")
    else:
        logger.info(f"Media directory: {media_dir}")
    logger.info(f"Web UI: http://0.0.0.0:{config.web_port}")
    logger.info(f"RTSP stream will be at: rtsp://<this-host>:{config.rtsp_port}/{config.stream_path}")
    # Give MediaMTX a moment to start before the idle stream connects
    import asyncio
    await asyncio.sleep(1)
    engine.start_idle_stream()
    yield
    engine.stop_idle_stream()
    engine.stop()
    _stop_mediamtx()


app = FastAPI(title="Stream Movies", lifespan=lifespan)

# Mount static files
static_dir = Path(__file__).parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# ── Request models ──────────────────────────────────────────────


class PlayRequest(BaseModel):
    path: str
    offset: float = 0.0


class SeekRequest(BaseModel):
    offset: float


class SeekAbsoluteRequest(BaseModel):
    position: float


# ── Routes ──────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def index():
    index_file = static_dir / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="Web UI not found")
    return index_file.read_text()


@app.get("/api/files")
async def api_list_files(path: str = ""):
    result = list_directory(config.media_dir, path)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/api/files/search")
async def api_search_files(q: str, path: str = ""):
    if len(q) < 2:
        raise HTTPException(status_code=400, detail="Query must be at least 2 characters")
    result = search_files(config.media_dir, q, path)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/api/files/info")
async def api_file_info(path: str):
    result = get_media_info(config.media_dir, path, config.ffprobe_path)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/api/stream/play")
async def api_play(req: PlayRequest):
    result = engine.play(req.path, req.offset)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/api/stream/pause")
async def api_pause():
    result = engine.pause()
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/api/stream/resume")
async def api_resume():
    result = engine.resume()
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/api/stream/stop")
async def api_stop():
    return engine.stop()


@app.post("/api/stream/seek")
async def api_seek(req: SeekRequest):
    result = engine.seek(req.offset)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.post("/api/stream/seek_absolute")
async def api_seek_absolute(req: SeekAbsoluteRequest):
    result = engine.seek_absolute(req.position)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/api/stream/status")
async def api_status():
    return engine.get_status()


@app.get("/api/stream/stats")
async def api_stats():
    """Comprehensive stream stats: FFmpeg encoding, MediaMTX connections, source info."""
    stats = {
        "encoding": engine.get_ffmpeg_stats(),
        "source": engine.get_source_info(),
        "connections": _get_mediamtx_connections(),
    }
    return stats


def _get_mediamtx_connections() -> dict:
    """Query MediaMTX API for active RTSP connections and path stats."""
    api_base = f"http://localhost:{config.mediamtx_api_port}"
    result = {
        "readers": [],
        "reader_count": 0,
        "available": False,
        "path": None,
    }

    # Get path-level stats (inbound/outbound bytes, online status, tracks)
    try:
        req = urllib.request.Request(
            f"{api_base}/v3/paths/get/{config.stream_path}",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read())
            result["available"] = True
            readers = data.get("readers", []) or []
            result["reader_count"] = len(readers)
            is_online = data.get("online", data.get("ready", False))
            result["path"] = {
                "online": is_online,
                "online_since": data.get("onlineTime", ""),
                "inbound_bytes": data.get("inboundBytes", data.get("bytesReceived", 0)),
                "outbound_bytes": data.get("outboundBytes", data.get("bytesSent", 0)),
                "inbound_frames_error": data.get("inboundFramesInError", 0),
            }
            # Extract track info
            tracks = data.get("tracks2", data.get("tracks", [])) or []
            track_list = []
            for t in tracks:
                track_list.append({
                    "codec": t.get("codec", ""),
                    "width": t.get("width"),
                    "height": t.get("height"),
                    "channels": t.get("channelCount"),
                    "sample_rate": t.get("sampleRate"),
                })
            result["path"]["tracks"] = track_list
    except (urllib.error.URLError, json.JSONDecodeError, Exception):
        pass

    # Get per-session stats (IPs, bytes, packet loss, jitter, transport)
    try:
        req = urllib.request.Request(
            f"{api_base}/v3/rtspsessions/list",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read())
            sessions = data.get("items", []) or []
            result["available"] = True
            client_details = []
            for s in sessions:
                if s.get("state") == "read":
                    remote = s.get("remoteAddr", "")
                    ip = remote.rsplit(":", 1)[0] if ":" in remote else remote
                    client_details.append({
                        "id": s.get("id", ""),
                        "ip": ip,
                        "transport": s.get("transport", ""),
                        "state": s.get("state", ""),
                        "created": s.get("created", ""),
                        "inbound_bytes": s.get("inboundBytes", s.get("bytesReceived", 0)),
                        "outbound_bytes": s.get("outboundBytes", s.get("bytesSent", 0)),
                        "rtp_packets_sent": s.get("outboundRTPPackets", 0),
                        "rtp_packets_lost": s.get("outboundRTPPacketsReportedLost", 0),
                        "rtp_packets_discarded": s.get("outboundRTPPacketsDiscarded", 0),
                        "rtp_packets_jitter": s.get("inboundRTPPacketsJitter", 0),
                        "rtcp_packets_sent": s.get("outboundRTCPPackets", 0),
                        "rtcp_packets_received": s.get("inboundRTCPPackets", 0),
                    })
            if client_details:
                result["readers"] = client_details
                result["reader_count"] = len(client_details)
    except (urllib.error.URLError, json.JSONDecodeError, Exception):
        pass

    # Get HLS muxer info
    try:
        req = urllib.request.Request(
            f"{api_base}/v3/hlsmuxers/list",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read())
            items = data.get("items", []) or []
            for h in items:
                if h.get("path") == config.stream_path:
                    hls_reader = {
                        "id": "hls-muxer",
                        "ip": "HLS Viewer(s)",
                        "transport": "HLS",
                        "state": "read",
                        "created": h.get("created", ""),
                        "outbound_bytes": h.get("bytesSent", 0),
                        "rtp_packets_sent": 0,
                        "rtp_packets_lost": 0,
                        "rtp_packets_discarded": 0,
                        "rtp_packets_jitter": 0,
                        "rtcp_packets_sent": 0,
                        "rtcp_packets_received": 0,
                    }
                    result["readers"].append(hls_reader)
                    result["reader_count"] = len(result["readers"])
    except (urllib.error.URLError, json.JSONDecodeError, Exception):
        pass

    # Get server info
    try:
        req = urllib.request.Request(
            f"{api_base}/v3/info",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = json.loads(resp.read())
            result["server"] = {
                "version": data.get("version", ""),
            }
    except (urllib.error.URLError, json.JSONDecodeError, Exception):
        pass

    return result


@app.get("/api/config")
async def api_config(request: Request):
    host = request.headers.get("host", "localhost").split(":")[0]
    resp = {
        "rtsp_url": f"rtsp://{host}:{config.rtsp_port}/{config.stream_path}",
        "hls_url": f"http://{host}:{config.hls_port}/{config.stream_path}/index.m3u8",
        "web_port": config.web_port,
        "rtsp_port": config.rtsp_port,
        "hls_port": config.hls_port,
    }
    if config.rtsp_external_url:
        resp["rtsp_external_url"] = config.rtsp_external_url
    if config.hls_external_url:
        resp["hls_external_url"] = config.hls_external_url
    return resp
