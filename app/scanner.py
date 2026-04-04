import json
import subprocess
from pathlib import Path

VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv",
    ".webm", ".m4v", ".ts", ".mts", ".m2ts",
}


def list_directory(base_dir: str, rel_path: str = "") -> dict:
    """List video files and directories at the given path."""
    base = Path(base_dir).resolve()
    target = (base / rel_path).resolve() if rel_path else base

    # Prevent directory traversal
    try:
        target.relative_to(base)
    except ValueError:
        return {"error": "Access denied"}

    if not target.exists():
        return {"error": "Path not found"}
    if not target.is_dir():
        return {"error": "Not a directory"}

    items = []
    try:
        for entry in sorted(target.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
            if entry.name.startswith("."):
                continue
            if entry.is_dir():
                items.append({
                    "name": entry.name,
                    "path": str(entry.relative_to(base)),
                    "is_dir": True,
                })
            elif entry.suffix.lower() in VIDEO_EXTENSIONS:
                items.append({
                    "name": entry.name,
                    "path": str(entry.relative_to(base)),
                    "is_dir": False,
                    "is_video": True,
                    "size": entry.stat().st_size,
                })
    except PermissionError:
        return {"error": "Permission denied"}

    return {"path": rel_path, "items": items}


def search_files(base_dir: str, query: str, rel_path: str = "", max_results: int = 50) -> dict:
    """Recursively search for video files matching the query."""
    base = Path(base_dir).resolve()
    search_root = (base / rel_path).resolve() if rel_path else base

    try:
        search_root.relative_to(base)
    except ValueError:
        return {"error": "Access denied"}

    if not search_root.exists() or not search_root.is_dir():
        return {"error": "Path not found"}

    query_lower = query.lower()
    results = []

    try:
        for entry in search_root.rglob("*"):
            if len(results) >= max_results:
                break
            if entry.name.startswith("."):
                continue
            if entry.is_dir() and query_lower in entry.name.lower():
                results.append({
                    "name": entry.name,
                    "path": str(entry.relative_to(base)),
                    "is_dir": True,
                })
            elif entry.is_file() and entry.suffix.lower() in VIDEO_EXTENSIONS and query_lower in entry.name.lower():
                results.append({
                    "name": entry.name,
                    "path": str(entry.relative_to(base)),
                    "is_dir": False,
                    "is_video": True,
                    "size": entry.stat().st_size,
                    "parent": str(entry.parent.relative_to(base)) if entry.parent != base else "",
                })
    except PermissionError:
        pass

    results.sort(key=lambda x: (not x.get("is_dir", False), x["name"].lower()))
    return {"query": query, "search_root": rel_path, "items": results, "truncated": len(results) >= max_results}


def get_media_info(base_dir: str, rel_path: str, ffprobe_path: str = "ffprobe") -> dict:
    """Get media file information using ffprobe."""
    base = Path(base_dir).resolve()
    target = (base / rel_path).resolve()

    try:
        target.relative_to(base)
    except ValueError:
        return {"error": "Access denied"}

    if not target.exists() or not target.is_file():
        return {"error": "File not found"}

    try:
        result = subprocess.run(
            [
                ffprobe_path, "-v", "quiet",
                "-show_entries", "format=duration,size,bit_rate:stream=codec_name,codec_type,width,height",
                "-of", "json",
                str(target),
            ],
            capture_output=True, text=True, timeout=30,
        )
        data = json.loads(result.stdout)
        return {"path": rel_path, "name": target.name, "info": data}
    except subprocess.TimeoutExpired:
        return {"error": "Probe timed out"}
    except (json.JSONDecodeError, Exception) as e:
        return {"error": str(e)}
