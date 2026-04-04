/* ── API helpers ────────────────────────────────── */
const API = {
    listFiles: (path) =>
        fetch(`/api/files?path=${encodeURIComponent(path)}`).then(r => r.json()),

    play: (path, offset = 0) =>
        fetch("/api/stream/play", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ path, offset }),
        }).then(r => r.json()),

    pause: () =>
        fetch("/api/stream/pause", { method: "POST" }).then(r => r.json()),

    resume: () =>
        fetch("/api/stream/resume", { method: "POST" }).then(r => r.json()),

    stop: () =>
        fetch("/api/stream/stop", { method: "POST" }).then(r => r.json()),

    seek: (offset) =>
        fetch("/api/stream/seek", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ offset }),
        }).then(r => r.json()),

    seekAbsolute: (position) =>
        fetch("/api/stream/seek_absolute", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ position }),
        }).then(r => r.json()),

    status: () =>
        fetch("/api/stream/status").then(r => r.json()),

    config: () =>
        fetch("/api/config").then(r => r.json()),

    search: (query, path = "") =>
        fetch(`/api/files/search?q=${encodeURIComponent(query)}&path=${encodeURIComponent(path)}`).then(r => r.json()),

    stats: () =>
        fetch("/api/stream/stats").then(r => r.json()),
};


/* ── State ─────────────────────────────────────── */
let currentPath = "";
let statusInterval = null;
let isSeeking = false;   // true while user drags progress bar
let searchTimeout = null;
let isSearchActive = false;


/* ── DOM refs ──────────────────────────────────── */
const $fileList      = document.getElementById("file-list");
const $breadcrumbs   = document.getElementById("breadcrumbs");
const $nowPlaying    = document.getElementById("now-playing-file");
const $statusBadge   = document.getElementById("status-badge");
const $timeCurrent   = document.getElementById("time-current");
const $timeTotal     = document.getElementById("time-total");
const $progressBar   = document.getElementById("progress-bar");
const $errorDisplay  = document.getElementById("error-display");
const $rtspUrl       = document.getElementById("rtsp-url");
const $copyRtsp      = document.getElementById("copy-rtsp");
const $searchInput   = document.getElementById("search-input");
const $searchClear   = document.getElementById("search-clear");
const $connPanel     = document.getElementById("connections-panel");
const $connUnavail   = document.getElementById("conn-unavailable");


/* ── File browser ──────────────────────────────── */
async function navigateTo(path) {
    currentPath = path;
    // Clear search when navigating
    $searchInput.value = "";
    $searchClear.classList.add("hidden");
    isSearchActive = false;
    const data = await API.listFiles(path);

    renderBreadcrumbs(path);
    $fileList.innerHTML = "";

    if (data.items && data.items.length === 0) {
        const li = document.createElement("li");
        li.className = "empty-msg";
        li.textContent = "No video files found";
        $fileList.appendChild(li);
        return;
    }

    // Parent directory link
    if (path) {
        const li = document.createElement("li");
        li.innerHTML = `<span class="icon">⬆</span><span class="name">..</span>`;
        li.addEventListener("click", () => {
            const parent = path.split("/").slice(0, -1).join("/");
            navigateTo(parent);
        });
        $fileList.appendChild(li);
    }

    for (const item of data.items || []) {
        const li = document.createElement("li");

        if (item.is_dir) {
            li.innerHTML = `<span class="icon">📁</span><span class="name">${esc(item.name)}</span>`;
            li.addEventListener("click", () => navigateTo(item.path));
        } else {
            li.innerHTML =
                `<span class="icon">🎬</span>` +
                `<span class="name">${esc(item.name)}</span>` +
                `<span class="size">${formatSize(item.size)}</span>`;
            li.addEventListener("click", () => playFile(item.path));
        }

        $fileList.appendChild(li);
    }
}


function renderBreadcrumbs(path) {
    $breadcrumbs.innerHTML = "";
    const link = document.createElement("a");
    link.href = "#";
    link.textContent = "Root";
    link.addEventListener("click", (e) => { e.preventDefault(); navigateTo(""); });
    $breadcrumbs.appendChild(link);

    if (!path) return;

    const parts = path.split("/");
    let running = "";
    for (const part of parts) {
        running += (running ? "/" : "") + part;
        const sep = document.createElement("span");
        sep.className = "sep";
        sep.textContent = " / ";
        $breadcrumbs.appendChild(sep);

        const a = document.createElement("a");
        a.href = "#";
        a.textContent = part;
        const target = running;
        a.addEventListener("click", (e) => { e.preventDefault(); navigateTo(target); });
        $breadcrumbs.appendChild(a);
    }
}


/* ── Search ────────────────────────────────────── */
$searchInput.addEventListener("input", () => {
    clearTimeout(searchTimeout);
    const query = $searchInput.value.trim();

    if (query.length === 0) {
        $searchClear.classList.add("hidden");
        if (isSearchActive) {
            isSearchActive = false;
            navigateTo(currentPath);
        }
        return;
    }

    $searchClear.classList.remove("hidden");

    if (query.length < 2) return;

    searchTimeout = setTimeout(async () => {
        const data = await API.search(query, currentPath);
        isSearchActive = true;
        renderSearchResults(data);
    }, 300);
});

$searchClear.addEventListener("click", () => {
    $searchInput.value = "";
    $searchClear.classList.add("hidden");
    isSearchActive = false;
    navigateTo(currentPath);
});

function renderSearchResults(data) {
    $fileList.innerHTML = "";

    if (!data.items || data.items.length === 0) {
        const li = document.createElement("li");
        li.className = "empty-msg";
        li.textContent = `No results for "${data.query}"`;
        $fileList.appendChild(li);
        return;
    }

    for (const item of data.items) {
        const li = document.createElement("li");

        if (item.is_dir) {
            li.innerHTML = `<span class="icon">📁</span><span class="name">${esc(item.name)}</span>`;
            li.addEventListener("click", () => {
                $searchInput.value = "";
                $searchClear.classList.add("hidden");
                isSearchActive = false;
                navigateTo(item.path);
            });
        } else {
            const parentLabel = item.parent ? `<span class="parent-path">(${esc(item.parent)})</span>` : "";
            li.innerHTML =
                `<span class="icon">🎬</span>` +
                `<span class="name">${esc(item.name)}${parentLabel}</span>` +
                `<span class="size">${formatSize(item.size)}</span>`;
            li.addEventListener("click", () => playFile(item.path));
        }

        $fileList.appendChild(li);
    }

    if (data.truncated) {
        const li = document.createElement("li");
        li.className = "empty-msg";
        li.textContent = "More results available — refine your search";
        $fileList.appendChild(li);
    }
}


/* ── Playback ──────────────────────────────────── */
async function playFile(path) {
    await API.play(path);
    pollStatus();
}


async function pollStatus() {
    try {
        const s = await API.status();
        updatePlayerUI(s);
    } catch { /* ignore transient errors */ }
}


function updatePlayerUI(s) {
    // File name
    $nowPlaying.textContent = s.file ? s.file.split("/").pop() : "No file selected";

    // Badge
    $statusBadge.textContent = s.state;
    $statusBadge.className = `badge ${s.state}`;

    // Time
    $timeCurrent.textContent = formatTime(s.position || 0);
    $timeTotal.textContent = formatTime(s.duration || 0);

    // Progress bar (skip if user is dragging)
    if (!isSeeking && s.duration > 0) {
        $progressBar.max = s.duration;
        $progressBar.value = s.position || 0;
    }

    // Error
    if (s.error) {
        $errorDisplay.textContent = s.error;
        $errorDisplay.classList.remove("hidden");
    } else {
        $errorDisplay.classList.add("hidden");
    }
}


/* ── Controls ──────────────────────────────────── */
document.getElementById("btn-play").addEventListener("click", async () => {
    const s = await API.status();
    if (s.state === "paused") {
        await API.resume();
    }
    // If idle and there's a file, we can't resume — user should pick a file
});

document.getElementById("btn-pause").addEventListener("click", async () => {
    const s = await API.status();
    if (s.state === "playing") {
        await API.pause();
    } else if (s.state === "paused") {
        await API.resume();
    }
    pollStatus();
});

document.getElementById("btn-stop").addEventListener("click", async () => {
    await API.stop();
    pollStatus();
});

document.getElementById("btn-back30").addEventListener("click", async () => {
    await API.seek(-30);
    pollStatus();
});

document.getElementById("btn-fwd30").addEventListener("click", async () => {
    await API.seek(30);
    pollStatus();
});

// Progress bar seeking
$progressBar.addEventListener("mousedown", () => { isSeeking = true; });
$progressBar.addEventListener("touchstart", () => { isSeeking = true; });

$progressBar.addEventListener("change", async () => {
    isSeeking = false;
    await API.seekAbsolute(parseFloat($progressBar.value));
    pollStatus();
});

$progressBar.addEventListener("mouseup", () => { isSeeking = false; });
$progressBar.addEventListener("touchend", () => { isSeeking = false; });

// Copy RTSP URL
// Clipboard helper — works over plain HTTP (no secure context needed)
function copyToClipboard(text, feedbackBtn) {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.left = "-9999px";
    document.body.appendChild(ta);
    ta.select();
    try {
        document.execCommand("copy");
        feedbackBtn.textContent = "Copied!";
        setTimeout(() => { feedbackBtn.textContent = "Copy"; }, 1500);
    } catch {
        feedbackBtn.textContent = "Failed";
        setTimeout(() => { feedbackBtn.textContent = "Copy"; }, 1500);
    }
    document.body.removeChild(ta);
}

function copyRtspUrl() {
    copyToClipboard($rtspUrl.textContent, $copyRtsp);
}

$copyRtsp.addEventListener("click", copyRtspUrl);
$rtspUrl.addEventListener("click", copyRtspUrl);

// Copy external RTSP URL
const $copyRtspExt = document.getElementById("copy-rtsp-ext");
const $rtspExtUrl = document.getElementById("rtsp-ext-url");

function copyExtUrl() {
    copyToClipboard($rtspExtUrl.textContent, $copyRtspExt);
}

$copyRtspExt.addEventListener("click", copyExtUrl);
$rtspExtUrl.addEventListener("click", copyExtUrl);


/* ── Utilities ─────────────────────────────────── */
function formatTime(seconds) {
    seconds = Math.max(0, Math.floor(seconds));
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function formatSize(bytes) {
    if (!bytes) return "";
    const units = ["B", "KB", "MB", "GB", "TB"];
    let i = 0;
    let size = bytes;
    while (size >= 1024 && i < units.length - 1) {
        size /= 1024;
        i++;
    }
    return `${size.toFixed(i > 0 ? 1 : 0)} ${units[i]}`;
}

function esc(str) {
    const d = document.createElement("div");
    d.textContent = str;
    return d.innerHTML;
}

function formatBitrate(bps) {
    if (!bps) return "—";
    const n = parseInt(bps, 10);
    if (isNaN(n)) return bps;
    if (n >= 1e6) return (n / 1e6).toFixed(1) + " Mbps";
    if (n >= 1e3) return (n / 1e3).toFixed(0) + " kbps";
    return n + " bps";
}

function formatElapsed(isoString) {
    if (!isoString) return "—";
    try {
        const start = new Date(isoString);
        const now = new Date();
        let secs = Math.floor((now - start) / 1000);
        if (secs < 0) secs = 0;
        if (secs < 60) return secs + "s";
        const mins = Math.floor(secs / 60);
        const remSecs = secs % 60;
        if (mins < 60) return `${mins}m ${remSecs}s`;
        const hrs = Math.floor(mins / 60);
        const remMins = mins % 60;
        return `${hrs}h ${remMins}m`;
    } catch { return "—"; }
}


/* ── Stats polling ─────────────────────────────── */
async function pollStats() {
    try {
        const data = await API.stats();
        renderStats(data);
    } catch { /* ignore */ }
}

function renderStats(data) {
    // Encoding stats
    {
        const enc = data.encoding || {};
        document.getElementById("stat-fps").textContent = enc.fps || "—";
        document.getElementById("stat-bitrate").textContent = enc.bitrate || "—";
        document.getElementById("stat-speed").textContent = enc.speed || "—";
        document.getElementById("stat-frames").textContent = enc.frame ? enc.frame.toLocaleString() : "—";
        document.getElementById("stat-outsize").textContent = enc.size || "—";

        // Source info
        const src = data.source || {};
        document.getElementById("stat-container").textContent = src.container || "—";
        document.getElementById("stat-video-codec").textContent = src.video_codec || "—";
        document.getElementById("stat-resolution").textContent =
            (src.width && src.height) ? `${src.width}x${src.height}${src.aspect_ratio ? " (" + src.aspect_ratio + ")" : ""}` : "—";
        document.getElementById("stat-src-fps").textContent = src.framerate ? src.framerate + " fps" : "—";
        document.getElementById("stat-audio-codec").textContent =
            src.audio_codec ? `${src.audio_codec}${src.audio_channels ? " (" + src.audio_channels + "ch)" : ""}${src.sample_rate ? " " + src.sample_rate + "Hz" : ""}` : "—";
        document.getElementById("stat-filesize").textContent = src.file_size ? formatSize(src.file_size) : "—";
    }

    // RTSP Server / Path stats
    {
        const conn = data.connections || {};
        const path = conn.path || {};
        const server = conn.server || {};

        document.getElementById("stat-path-status").textContent = path.online ? "Online" : "Offline";
        document.getElementById("stat-path-status").className = path.online ? "stat-online" : "stat-offline";
        document.getElementById("stat-server-version").textContent = server.version ? `v${server.version}` : "—";
        document.getElementById("stat-path-inbound").textContent = path.inbound_bytes ? formatSize(path.inbound_bytes) : "—";
        document.getElementById("stat-path-outbound").textContent = path.outbound_bytes ? formatSize(path.outbound_bytes) : "—";
        document.getElementById("stat-path-frame-errors").textContent =
            path.inbound_frames_error !== undefined ? path.inbound_frames_error.toLocaleString() : "—";

        // Tracks summary
        const tracks = path.tracks || [];
        if (tracks.length > 0) {
            const parts = tracks.map(t => {
                if (t.width && t.height) return `${t.codec || "video"} ${t.width}x${t.height}`;
                if (t.channels) return `${t.codec || "audio"} ${t.channels}ch${t.sample_rate ? " " + t.sample_rate + "Hz" : ""}`;
                return t.codec || "unknown";
            });
            document.getElementById("stat-path-tracks").textContent = parts.join(", ");
        } else {
            document.getElementById("stat-path-tracks").textContent = "—";
        }
    }

    // Connections — always update (separate panel)
    const conn = data.connections || {};
    const count = conn.reader_count || 0;
    document.getElementById("stat-conn-count").textContent = `— ${count} viewer${count !== 1 ? "s" : ""}`;

    // Show/hide connections panel
    if (count > 0 || conn.available) {
        $connPanel.classList.remove("hidden");
    } else {
        $connPanel.classList.add("hidden");
    }

    const tbody = document.getElementById("stats-clients-body");
    tbody.innerHTML = "";
    $connUnavail.classList.add("hidden");

    if (conn.readers && conn.readers.length > 0) {
        for (const r of conn.readers) {
            const tr = document.createElement("tr");
            const lossRate = (r.rtp_packets_sent > 0 && r.rtp_packets_lost > 0)
                ? ` (${(r.rtp_packets_lost / r.rtp_packets_sent * 100).toFixed(2)}%)`
                : "";
            const jitter = r.rtp_packets_jitter ? r.rtp_packets_jitter.toFixed(3) + " ms" : "—";
            const connected = r.created ? formatElapsed(r.created) : "—";

            tr.innerHTML =
                `<td>${esc(r.ip || r.id || "—")}</td>` +
                `<td>${esc(r.transport || "—")}</td>` +
                `<td>${r.outbound_bytes ? formatSize(r.outbound_bytes) : "—"}</td>` +
                `<td>${r.rtp_packets_sent ? r.rtp_packets_sent.toLocaleString() : "—"}</td>` +
                `<td class="${r.rtp_packets_lost > 0 ? "stat-warn" : ""}">${r.rtp_packets_lost ? r.rtp_packets_lost.toLocaleString() + lossRate : "0"}</td>` +
                `<td>${jitter}</td>` +
                `<td>${connected}</td>`;
            tbody.appendChild(tr);
        }
    } else if (!conn.available) {
        $connUnavail.classList.remove("hidden");
    }
}


/* ── Init ──────────────────────────────────────── */
(async function init() {
    // Load config (RTSP URL + external URL)
    try {
        const cfg = await API.config();
        $rtspUrl.textContent = cfg.rtsp_url;
        if (cfg.rtsp_external_url) {
            $rtspExtUrl.textContent = cfg.rtsp_external_url;
            document.getElementById("rtsp-ext-bar").classList.remove("hidden");
        }
    } catch {
        $rtspUrl.textContent = "rtsp://<host>:8554/stream";
    }

    // Load file browser
    navigateTo("");

    // Poll status every second
    statusInterval = setInterval(pollStatus, 1000);
    setInterval(pollStats, 2000);
    pollStatus();
})();
