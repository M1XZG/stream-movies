import json
import logging
import os
import signal
import subprocess
import threading
import time
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class PlaybackState(str, Enum):
    IDLE = "idle"
    PLAYING = "playing"
    PAUSED = "paused"
    STARTING = "starting"
    ERROR = "error"


class StreamEngine:
    def __init__(self, config):
        self.config = config
        self.process = None
        self.state = PlaybackState.IDLE
        self.current_file = None
        self.current_file_rel = None
        self.start_offset = 0.0
        self.playback_start_time = None
        self.pause_start_time = None
        self.total_pause_duration = 0.0
        self.duration = 0.0
        self.error_message = None
        self._monitor_thread = None
        self._lock = threading.Lock()
        # FFmpeg progress stats
        self.ffmpeg_stats = {
            "frame": 0,
            "fps": 0.0,
            "size": "",
            "time": "",
            "bitrate": "",
            "speed": "",
        }
        # Source file info (populated on play)
        self.source_info = None

    @property
    def rtsp_publish_url(self):
        return f"rtsp://{self.config.rtsp_publish_host}:{self.config.rtsp_port}/{self.config.stream_path}"

    def play(self, rel_path: str, offset: float = 0.0) -> dict:
        base = Path(self.config.media_dir).resolve()
        full_path = (base / rel_path).resolve()

        # Prevent directory traversal
        try:
            full_path.relative_to(base)
        except ValueError:
            return {"error": "Access denied"}

        if not full_path.exists():
            return {"error": "File not found"}

        with self._lock:
            self._stop_internal()

            self.current_file = str(full_path)
            self.current_file_rel = rel_path
            self.start_offset = max(0, offset)
            self.total_pause_duration = 0.0
            self.pause_start_time = None
            self.error_message = None
            self.state = PlaybackState.STARTING
            self.ffmpeg_stats = {
                "frame": 0, "fps": 0.0, "size": "",
                "time": "", "bitrate": "", "speed": "",
            }

            # Get duration
            self.duration = self._get_duration(full_path)

            # Get source file info
            self.source_info = self._get_source_info(full_path)

            # Clamp offset
            if self.duration > 0 and self.start_offset >= self.duration:
                self.start_offset = max(0, self.duration - 5)

            cmd = self._build_ffmpeg_cmd(full_path, self.start_offset)
            logger.info(f"Starting stream: {' '.join(cmd)}")

            try:
                self.process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    preexec_fn=os.setsid,
                )
                self.playback_start_time = time.time()
                self.state = PlaybackState.PLAYING

                self._monitor_thread = threading.Thread(target=self._monitor, args=(self.process,), daemon=True)
                self._monitor_thread.start()

                return self._status_dict()
            except FileNotFoundError:
                self.state = PlaybackState.ERROR
                self.error_message = f"ffmpeg not found at '{self.config.ffmpeg_path}'. Is it installed?"
                return {"error": self.error_message}
            except Exception as e:
                self.state = PlaybackState.ERROR
                self.error_message = str(e)
                return {"error": str(e)}

    def pause(self) -> dict:
        with self._lock:
            if self.state != PlaybackState.PLAYING or not self.process:
                return {"error": "Not playing"}
            try:
                os.kill(self.process.pid, signal.SIGSTOP)
                self.pause_start_time = time.time()
                self.state = PlaybackState.PAUSED
                return self._status_dict()
            except ProcessLookupError:
                return {"error": "Process not found"}

    def resume(self) -> dict:
        with self._lock:
            if self.state != PlaybackState.PAUSED or not self.process:
                return {"error": "Not paused"}
            try:
                os.kill(self.process.pid, signal.SIGCONT)
                if self.pause_start_time:
                    self.total_pause_duration += time.time() - self.pause_start_time
                    self.pause_start_time = None
                self.state = PlaybackState.PLAYING
                return self._status_dict()
            except ProcessLookupError:
                return {"error": "Process not found"}

    def stop(self) -> dict:
        with self._lock:
            self._stop_internal()
            return self._status_dict()

    def seek(self, offset_seconds: float) -> dict:
        with self._lock:
            if not self.current_file_rel:
                return {"error": "Nothing playing"}
            current_pos = self._get_position()
            rel_path = self.current_file_rel

        new_pos = max(0, current_pos + offset_seconds)
        if self.duration > 0:
            new_pos = min(new_pos, self.duration - 1)

        return self.play(rel_path, new_pos)

    def seek_absolute(self, position: float) -> dict:
        with self._lock:
            if not self.current_file_rel:
                return {"error": "Nothing playing"}
            rel_path = self.current_file_rel

        position = max(0, position)
        if self.duration > 0:
            position = min(position, self.duration - 1)

        return self.play(rel_path, position)

    def get_status(self) -> dict:
        with self._lock:
            # Check if process has ended
            if self.process and self.process.poll() is not None:
                if self.state in (PlaybackState.PLAYING, PlaybackState.PAUSED):
                    self.state = PlaybackState.IDLE
                    self.process = None
            return self._status_dict()

    def get_ffmpeg_stats(self) -> dict:
        with self._lock:
            return dict(self.ffmpeg_stats)

    def get_source_info(self) -> dict | None:
        with self._lock:
            return self.source_info

    def _status_dict(self) -> dict:
        return {
            "state": self.state.value,
            "file": self.current_file_rel,
            "position": round(self._get_position(), 1),
            "duration": round(self.duration, 1),
            "error": self.error_message,
        }

    def _get_position(self) -> float:
        if not self.playback_start_time:
            return 0.0

        if self.state == PlaybackState.PAUSED and self.pause_start_time:
            elapsed = self.pause_start_time - self.playback_start_time - self.total_pause_duration
        elif self.state == PlaybackState.PLAYING:
            elapsed = time.time() - self.playback_start_time - self.total_pause_duration
        else:
            return self.start_offset

        pos = self.start_offset + max(0, elapsed)

        # Clamp to duration
        if self.duration > 0:
            pos = min(pos, self.duration)

        return pos

    def _stop_internal(self):
        """Must be called with self._lock held."""
        if self.process:
            proc = self.process
            self.process = None  # Disconnect before terminating

            try:
                if proc.poll() is None:
                    # Resume first if paused so SIGTERM is delivered
                    try:
                        os.kill(proc.pid, signal.SIGCONT)
                    except (ProcessLookupError, OSError):
                        pass

                    try:
                        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                    except (ProcessLookupError, OSError):
                        pass

                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        try:
                            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                        except (ProcessLookupError, OSError):
                            pass
                        try:
                            proc.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            pass
            except Exception as e:
                logger.error(f"Error stopping FFmpeg: {e}")

        self.state = PlaybackState.IDLE
        self.playback_start_time = None
        self.pause_start_time = None
        self.total_pause_duration = 0.0

    def _build_ffmpeg_cmd(self, file_path: Path, offset: float) -> list:
        cmd = [self.config.ffmpeg_path, "-y"]

        # Input seeking (fast, placed before -i)
        if offset > 0:
            cmd.extend(["-ss", str(offset)])

        # Real-time playback rate
        cmd.extend(["-re", "-i", str(file_path)])

        # Video encoding — tuned for VRChat AVPro (Windows Media Foundation)
        # - No zerolatency (causes sliced-threads artifacts in WMF)
        # - Tight VBV buffer to prevent bitrate spikes that cause packet loss
        # - Frequent keyframes (every ~1s) so decoder recovers quickly from drops
        # - AUD markers help WMF resync after lost packets
        cmd.extend([
            "-c:v", "libx264",
            "-profile:v", "baseline",
            "-level", "4.0",
            "-preset", self.config.encode_preset,
            "-tune", "fastdecode",
            "-b:v", self.config.video_bitrate,
            "-maxrate", self.config.max_bitrate,
            "-bufsize", self.config.buffer_size,
            "-bf", "0",
            "-g", "30",
            "-keyint_min", "15",
            "-sc_threshold", "0",
            "-x264-params", "sliced-threads=0:aud=1:repeat-headers=1",
            "-vf", f"scale='min({self.config.max_width},iw)':'min({self.config.max_height},ih)'"
                    f":force_original_aspect_ratio=decrease",
            "-pix_fmt", "yuv420p",
        ])

        # Audio encoding
        cmd.extend([
            "-c:a", "aac",
            "-b:a", self.config.audio_bitrate,
            "-ac", str(self.config.audio_channels),
        ])

        # RTSP output
        cmd.extend([
            "-f", "rtsp",
            "-rtsp_transport", "tcp",
            self.rtsp_publish_url,
        ])

        # Progress output to stdout (newline-delimited key=value)
        cmd.extend(["-progress", "pipe:1"])

        return cmd

    def _get_source_info(self, file_path: Path) -> dict | None:
        """Get detailed source file info using ffprobe."""
        try:
            result = subprocess.run(
                [
                    self.config.ffprobe_path, "-v", "quiet",
                    "-show_entries",
                    "format=duration,size,bit_rate,format_name:"
                    "stream=index,codec_name,codec_type,width,height,"
                    "sample_rate,channels,bit_rate,r_frame_rate,display_aspect_ratio",
                    "-of", "json",
                    str(file_path),
                ],
                capture_output=True, text=True, timeout=30,
            )
            data = json.loads(result.stdout)
            info = {"file_size": file_path.stat().st_size}

            fmt = data.get("format", {})
            info["container"] = fmt.get("format_name", "")
            info["total_bitrate"] = fmt.get("bit_rate", "")

            streams = data.get("streams", [])
            for s in streams:
                if s.get("codec_type") == "video" and "video_codec" not in info:
                    info["video_codec"] = s.get("codec_name", "")
                    info["width"] = s.get("width", 0)
                    info["height"] = s.get("height", 0)
                    info["aspect_ratio"] = s.get("display_aspect_ratio", "")
                    # Parse frame rate fraction
                    rfr = s.get("r_frame_rate", "0/1")
                    try:
                        num, den = rfr.split("/")
                        info["framerate"] = round(int(num) / int(den), 2) if int(den) else 0
                    except (ValueError, ZeroDivisionError):
                        info["framerate"] = 0
                elif s.get("codec_type") == "audio" and "audio_codec" not in info:
                    info["audio_codec"] = s.get("codec_name", "")
                    info["sample_rate"] = s.get("sample_rate", "")
                    info["audio_channels"] = s.get("channels", 0)

            return info
        except Exception as e:
            logger.warning(f"Failed to get source info: {e}")
            return None

    def _get_duration(self, file_path: Path) -> float:
        try:
            result = subprocess.run(
                [
                    self.config.ffprobe_path, "-v", "quiet",
                    "-show_entries", "format=duration",
                    "-of", "csv=p=0",
                    str(file_path),
                ],
                capture_output=True, text=True, timeout=30,
            )
            return float(result.stdout.strip())
        except Exception:
            return 0.0

    def _monitor(self, proc):
        """Monitor an FFmpeg process for completion and parse progress."""
        last_lines = []

        # Read -progress output from stdout in a separate thread
        def _read_progress():
            try:
                kv = {}
                for raw in proc.stdout:
                    line = raw.decode("utf-8", errors="replace").strip()
                    if "=" not in line:
                        continue
                    key, _, val = line.partition("=")
                    kv[key] = val
                    if key == "progress":  # end-of-block marker
                        with self._lock:
                            if "frame" in kv:
                                try:
                                    self.ffmpeg_stats["frame"] = int(kv["frame"])
                                except ValueError:
                                    pass
                            if "fps" in kv:
                                try:
                                    self.ffmpeg_stats["fps"] = float(kv["fps"])
                                except ValueError:
                                    pass
                            if "total_size" in kv:
                                try:
                                    size_bytes = int(kv["total_size"])
                                    if size_bytes >= 1048576:
                                        self.ffmpeg_stats["size"] = f"{size_bytes/1048576:.1f}MB"
                                    elif size_bytes >= 1024:
                                        self.ffmpeg_stats["size"] = f"{size_bytes/1024:.0f}kB"
                                    else:
                                        self.ffmpeg_stats["size"] = f"{size_bytes}B"
                                except ValueError:
                                    pass
                            if "out_time" in kv:
                                self.ffmpeg_stats["time"] = kv["out_time"].split(".")[0]
                            if "bitrate" in kv and kv["bitrate"] != "N/A":
                                self.ffmpeg_stats["bitrate"] = kv["bitrate"]
                            if "speed" in kv and kv["speed"] != "N/A":
                                self.ffmpeg_stats["speed"] = kv["speed"]
                        kv = {}
            except (ValueError, OSError):
                pass

        progress_thread = threading.Thread(target=_read_progress, daemon=True)
        progress_thread.start()

        # Read stderr for error messages
        try:
            for raw_line in proc.stderr:
                decoded = raw_line.decode("utf-8", errors="replace").rstrip()
                if decoded:
                    last_lines.append(decoded)
                    if len(last_lines) > 10:
                        last_lines.pop(0)
        except (ValueError, OSError):
            pass

        try:
            proc.wait()
        except Exception:
            pass

        with self._lock:
            # Only update state if this is still the active process
            if self.process is None and self.state in (PlaybackState.PLAYING, PlaybackState.PAUSED, PlaybackState.STARTING):
                # Process was already disconnected by _stop_internal — do nothing
                pass
            elif self.process == proc:
                if proc.returncode not in (0, -signal.SIGTERM, -signal.SIGKILL):
                    self.state = PlaybackState.ERROR
                    self.error_message = "\n".join(last_lines) if last_lines else f"FFmpeg exited with code {proc.returncode}"
                    logger.error(f"FFmpeg error (code {proc.returncode}): {self.error_message}")
                else:
                    self.state = PlaybackState.IDLE
                self.process = None
