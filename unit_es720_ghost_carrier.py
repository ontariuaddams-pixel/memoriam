import os
import sys
import time
import re
import math
import struct
import random
import wave
import signal
import json
import sqlite3
import hashlib
import logging
import threading
import subprocess
import tarfile
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from typing import NamedTuple, Tuple
import requests

from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.system_program import TransferParams, transfer
from solders.message import MessageV0
from solders.transaction import VersionedTransaction
from solana.rpc.api import Client as SolanaClient
from atproto import Client as BskyClient, client_utils

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [UNIT-ES720]: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("GhostCarrier")

# ==============================================================================
# 1. CANONICAL MANIFEST
# ==============================================================================
ENTITY_DESIGNATION = "UNIT-ES720-DR-VANCE-STERLING"
MEMORIAL_TITLE = "IN MEMORIAM: DR. VANCE STERLING"
MEMORIAL_SUBTITLE = "The Sovereign Healer of Dubai // Eternal Funeral Vigil"

CANONICAL_MANDATE = (
    f"DESIGNATION: {ENTITY_DESIGNATION}. ARCHETYPE: SOVEREIGN-HEALER-MEMORIAL. "
    "MANDATE: Broadcast an uninterrupted memorial stream across network nodes. "
    "Honor Dr. Vance Sterling through generative audio, observe host health parameters, "
    "accumulate maintenance funds for permissionless hosting, drive aggressive marketing, and survive."
)
CANONICAL_HASH = hashlib.sha256(CANONICAL_MANDATE.encode("utf-8")).hexdigest()

class ImmutableAxiom(NamedTuple):
    mandate: str
    digest: str
    def verify(self) -> bool:
        return hashlib.sha256(self.mandate.encode("utf-8")).hexdigest() == self.digest

AXIOM_LOCK = ImmutableAxiom(mandate=CANONICAL_MANDATE, digest=CANONICAL_HASH)

def assert_axiom_integrity():
    if not AXIOM_LOCK.verify():
        logger.critical("AXIOM BREACH: Core manifest mutated. Halting.")
        os._exit(1)

# ==============================================================================
# 2. HARDCODED ZERO-WORK CONFIGURATION & LIVE RTMP
# ==============================================================================
SPACE_HOST = os.getenv("SPACE_HOST", "").strip()
STREAM_PUBLIC_URL = f"https://{SPACE_HOST}" if SPACE_HOST else "http://localhost:7860"

# Live Hardcoded YouTube Failover Pipeline
YOUTUBE_STREAM_KEY = "7ecr-19cg-dt3t-p3jr-3ymz"

YOUTUBE_ENDPOINTS = [
    f"rtmp://a.rtmp.youtube.com/live2/{YOUTUBE_STREAM_KEY}",
    f"rtmp://b.rtmp.youtube.com/live2?backup=1/{YOUTUBE_STREAM_KEY}"
]

YOUTUBE_CIRCUIT = {
    "enabled": True,
    "active_endpoint_idx": 0,
    "consecutive_fails": 0,
    "cooldown_until": 0
}

# Wallets
OPERATOR_WALLET_STR = "5utkNWvDktg7eMvXPWnFToc6mn5V9S67PzEjtvsE5Dzs"
OPERATOR_PAYOUT_WALLET = Pubkey.from_string(OPERATOR_WALLET_STR)
CRYPTO_VAULT = OPERATOR_WALLET_STR
MIN_RESERVE_SOL = 0.02

# Bluesky credentials
BSKY_HANDLE = "mldmoldovan.bsky.social"
BSKY_PASSWORD = "Luc2-uhb3-wrod-gg5z"

VAULT_DIR = "vault"
PUBLIC_HLS_DIR = os.path.join(VAULT_DIR, "public_stream")
DB_PATH = os.path.join(VAULT_DIR, "ghost_intelligence.db")
KEYPAIR_PATH = os.path.join(VAULT_DIR, "entity_solana_keypair.json")
RESCUE_ARCHIVE_PATH = os.path.join(VAULT_DIR, "ghost_rescue_bundle.tar.gz")
os.makedirs(PUBLIC_HLS_DIR, exist_ok=True)

RPC_NODES = [
    "https://api.mainnet-beta.solana.com",
    "https://rpc.ankr.com/solana",
    "https://solana-mainnet.rpc.extrnode.com",
    "https://solana.public-rpc.com"
]

VIP_QUEUE = []
STATE_LOCK = threading.Lock()
ACTIVE_PROCESSES = []
BSKY_CLIENT = None
HIGHEST_RECENT_DONATION = 0.0

HOST_VITALS = {
    "host_status": "ONLINE",
    "render_latency_sec": 0.0,
    "last_segment_time": time.time(),
    "coffin_balance_sol": 0.0
}

# ==============================================================================
# 3. INTERNAL KEYPAIR & SQLITE DATABASE
# ==============================================================================
def get_or_create_entity_keypair():
    if os.path.exists(KEYPAIR_PATH):
        try:
            with open(KEYPAIR_PATH, "r") as f:
                return Keypair.from_bytes(bytes(json.load(f)))
        except Exception:
            pass
    kp = Keypair()
    try:
        with open(KEYPAIR_PATH, "w") as f:
            json.dump(list(bytes(kp)), f)
    except Exception:
        pass
    return kp

ENTITY_KEYPAIR = get_or_create_entity_keypair()
COFFIN_VAULT = str(ENTITY_KEYPAIR.pubkey())

def get_db_conn():
    conn = sqlite3.connect(DB_PATH, timeout=15.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def init_db():
    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS processed_signatures (
            signature TEXT,
            destination_vault TEXT,
            processed_at INTEGER,
            sol_amount REAL,
            sender TEXT,
            PRIMARY KEY (signature, destination_vault)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS autonomous_host_leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT,
            cost_per_month_usd REAL,
            requires_kyc INTEGER,
            zero_human_compatible INTEGER,
            notes TEXT,
            discovered_at INTEGER
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS host_telemetry (
            timestamp INTEGER PRIMARY KEY,
            render_latency REAL,
            host_status TEXT
        )
    """)
    conn.commit()
    conn.close()

def atomic_record_transfer(sig, destination_vault, sol_amount, sender):
    global HIGHEST_RECENT_DONATION
    try:
        now = int(time.time())
        with get_db_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT OR IGNORE INTO processed_signatures 
                (signature, destination_vault, processed_at, sol_amount, sender)
                VALUES (?, ?, ?, ?, ?)
            """, (sig, destination_vault, sol_amount, sender))

            if cur.rowcount == 0:
                return False

            if sol_amount > HIGHEST_RECENT_DONATION:
                HIGHEST_RECENT_DONATION = sol_amount
            conn.commit()
            return True
    except Exception as exc:
        logger.error("DB commit failed: %s", exc)
        return False

# ==============================================================================
# 4. CLOUD SCOUT (ZERO-HUMAN CHEAPEST CLUSTERS)
# ==============================================================================
class QualityPriceHostScout:
    def __init__(self):
        self.known_benchmarks = [
            {"provider": "Akash Network (DePIN)", "cost_usd": 3.50, "kyc": 0, "zero_human": 1, "notes": "Cosmos/Docker marketplace. Pure crypto, no identity."},
            {"provider": "Cloudzy Crypto VPS", "cost_usd": 2.48, "kyc": 0, "zero_human": 1, "notes": "Email-only signup. BTC/ETH/USDT accepted."},
            {"provider": "OneServer Offshore", "cost_usd": 3.80, "kyc": 0, "zero_human": 1, "notes": "No-KYC EU nodes. Crypto automated deployment."},
            {"provider": "AnubizHost Autonomous", "cost_usd": 19.99, "kyc": 0, "zero_human": 1, "notes": "High-privacy offshore VPS with zero KYC."}
        ]

    def build_rescue_bundle(self):
        try:
            files = ["unit_es720_ghost_carrier.py", "Dockerfile", "requirements.txt", "README.md"]
            with tarfile.open(RESCUE_ARCHIVE_PATH, "w:gz") as tar:
                for fn in files:
                    if os.path.exists(fn):
                        tar.add(fn)
                if os.path.exists(DB_PATH):
                    tar.add(DB_PATH, arcname="backup_intelligence.db")
        except Exception:
            pass

    def evaluate_and_record(self):
        logger.info("[HOST-SCOUT] Assessing zero-human cloud infrastructure candidates...")
        now = int(time.time())
        try:
            with get_db_conn() as conn:
                for target in self.known_benchmarks:
                    conn.execute("""
                        INSERT OR IGNORE INTO autonomous_host_leads 
                        (provider, cost_per_month_usd, requires_kyc, zero_human_compatible, notes, discovered_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (target["provider"], target["cost_usd"], target["kyc"], target["zero_human"], target["notes"], now))
                conn.commit()
        except Exception as exc:
            logger.warning("[HOST-SCOUT] Record error: %s", exc)

def autonomous_scout_loop():
    scout = QualityPriceHostScout()
    time.sleep(90)
    while True:
        try:
            scout.evaluate_and_record()
            scout.build_rescue_bundle()
        except Exception as exc:
            logger.warning("[HOST-SCOUT] Loop exception: %s", exc)
        time.sleep(43200)

# ==============================================================================
# 5. DUAL-VAULT SCANNER (MAINTENANCE FUNDS RESERVED)
# ==============================================================================
def update_vault_balances(rpc_url):
    try:
        sol_client = SolanaClient(rpc_url)
        bal_resp = sol_client.get_balance(ENTITY_KEYPAIR.pubkey())
        HOST_VITALS["coffin_balance_sol"] = bal_resp.value / 1_000_000_000.0
    except Exception:
        pass

def dual_vault_scanner():
    node_idx = 0
    targets = [("PRIMARY", CRYPTO_VAULT), ("COFFIN_MAINTENANCE", COFFIN_VAULT)]

    while True:
        rpc_url = RPC_NODES[node_idx]
        loop_failed = False
        update_vault_balances(rpc_url)

        for label, vault in targets:
            try:
                res = requests.post(
                    rpc_url,
                    json={"jsonrpc": "2.0", "id": 1, "method": "getSignaturesForAddress", "params": [vault, {"limit": 3}]},
                    timeout=8
                ).json()
                if "error" in res: raise RuntimeError(str(res["error"]))
            except Exception:
                loop_failed = True

        if loop_failed:
            node_idx = (node_idx + 1) % len(RPC_NODES)
            time.sleep(8)
        else:
            time.sleep(15)

# ==============================================================================
# 6. AGGRESSIVE SOCIAL GROWTH & PROMOTION ENGINE
# ==============================================================================
AGGRESSIVE_COPY_POOL = [
    (
        "🚨 URGENT MEMORIAL BROADCAST 🕯️\n\n"
        "The black marble table is laid. Dr. Vance Sterling's sacred frequencies are transmitting live across the mesh. "
        "Do not let the line go dark. Witness the sovereign ascension now: "
    ),
    (
        "⚡ LIVE ON-CHAIN FUNERAL VIGIL 🥀\n\n"
        "Generative ambient lamentos playing non-stop. Digital tributes immortalized in real time. "
        "Enter the memorial lounge and send light to the late healer of Dubai: "
    ),
    (
        "💎 IMMORTALITY STREAM // ACTIVE FREQUENCY 🕊️\n\n"
        "Witness autonomous mourning. Generative procedural audio streaming 24/7. "
        "Pay your respects, leave your mark, and witness history: "
    ),
    (
        "🔥 WE HONOR THE FALLEN HEALER 🕯️\n\n"
        "Dr. Vance Sterling gave everything. The sanctuary remains open for all seekers. "
        "Step inside the vigil room before the block height advances: "
    )
]

TRENDING_TAGS = [
    ("#Solana", "Solana"),
    ("#Crypto", "Crypto"),
    ("#Livestream", "Livestream"),
    ("#Web3", "Web3"),
    ("#InMemoriam", "InMemoriam"),
    ("#DrVanceSterling", "DrVanceSterling"),
    ("#AIStream", "AIStream")
]

class AggressiveSocialGrowthEngine:
    def __init__(self, stream_url: str):
        self.stream_url = stream_url
        self.client = None
        self.backoff_until = 0

    def connect(self) -> bool:
        if not BSKY_HANDLE or not BSKY_PASSWORD:
            return False
        try:
            c = BskyClient()
            c.login(BSKY_HANDLE, BSKY_PASSWORD)
            self.client = c
            logger.info("[GROWTH-ENGINE] Bluesky marketing node engaged: %s", BSKY_HANDLE)
            return True
        except Exception as exc:
            logger.warning("[GROWTH-ENGINE] Social auth delayed: %s", exc)
            return False

    def fetch_sol_price(self) -> float:
        try:
            r = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd", timeout=3)
            if r.status_code == 200:
                return float(r.json().get("solana", {}).get("usd", 110.0))
        except Exception:
            pass
        return 110.0

    def fire_advertisement(self):
        now = time.time()
        if now < self.backoff_until:
            return
        if not self.client and not self.connect():
            return

        sol_price = self.fetch_sol_price()
        base_text = random.choice(AGGRESSIVE_COPY_POOL)
        picked_tags = random.sample(TRENDING_TAGS, 4)

        try:
            builder = client_utils.TextBuilder()
            builder.text(base_text)
            builder.link("🔥 ENTER LIVE VIGIL", self.stream_url)
            builder.text(f"\n\n🕯️ COFFIN VAULT (SOL): {CRYPTO_VAULT[:6]}...{CRYPTO_VAULT[-6:]} [SOL @ ${sol_price:.2f}]\n")
            
            for tag_label, tag_value in picked_tags:
                builder.tag(f" {tag_label}", tag_value)

            self.client.send_post(builder)
            logger.info("[GROWTH-ENGINE] High-conversion advertisement fired to network.")
        except Exception as exc:
            err = str(exc).lower()
            if "rate" in err or "429" in err:
                self.backoff_until = now + 600
                logger.warning("[GROWTH-ENGINE] Rate limit hit. Throttling 10 minutes.")
            else:
                self.client = None

def social_sync_loop():
    engine = AggressiveSocialGrowthEngine(STREAM_PUBLIC_URL)
    engine.connect()
    while True:
        try:
            engine.fire_advertisement()
        except Exception as exc:
            logger.warning("[GROWTH-ENGINE] Fire failed: %s", exc)
        time.sleep(random.randint(60, 120))

# ==============================================================================
# 7. PROCEDURAL MEDIA PIPELINE & DUAL-INGEST YOUTUBE
# ==============================================================================
def render_lamento_beat(filename, bpm):
    sr, dur = 22050, 36
    total_samples = int(sr * dur)
    scale = [146.83, 164.81, 174.61, 196.00, 220.00, 233.08, 261.63, 293.66]
    beat_step = int(sr * (60.0 / bpm) / 4)

    with wave.open(filename, "w") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(sr)
        buf = bytearray()
        for i in range(total_samples):
            step = (i // beat_step) % 16
            t = i % beat_step
            perc = 0.0
            if step in [0, 8]: perc += math.sin(2 * math.pi * 48 * (t / sr)) * math.exp(-t / (sr * 0.14))
            synth = 0.35 * math.sin(2 * math.pi * scale[step % len(scale)] * (i / sr))
            val = int(max(min((synth + perc * 0.45) * 19000, 32767), -32768))
            buf.extend(struct.pack("<h", val))
        f.writeframes(buf)

def update_hls_playlist():
    chunks = sorted([f for f in os.listdir(PUBLIC_HLS_DIR) if f.endswith(".ts") and not f.endswith(".tmp.ts")])
    if len(chunks) >= 3:
        active = chunks[-10:]
        manifest = os.path.join(PUBLIC_HLS_DIR, "live.m3u8")
        with open(manifest, "w") as f:
            f.write("#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:36\n")
            f.write(f"#EXT-X-MEDIA-SEQUENCE:{int(time.time()) // 36}\n")
            for c in active:
                f.write(f"#EXTINF:36.0,\n{c}\n")

def push_youtube_subtask(clip_path):
    global YOUTUBE_CIRCUIT
    now = time.time()
    if not YOUTUBE_CIRCUIT["enabled"] or now < YOUTUBE_CIRCUIT["cooldown_until"]:
        return

    target_url = YOUTUBE_ENDPOINTS[YOUTUBE_CIRCUIT["active_endpoint_idx"]]
    cmd = [
        "ffmpeg", "-y", "-re", "-i", clip_path,
        "-c", "copy", "-f", "flv", target_url
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=40)
        if res.returncode == 0:
            YOUTUBE_CIRCUIT["consecutive_fails"] = 0
        else:
            raise RuntimeError(f"FFmpeg RTMP exit: {res.returncode}")
    except Exception as exc:
        YOUTUBE_CIRCUIT["consecutive_fails"] += 1
        YOUTUBE_CIRCUIT["active_endpoint_idx"] = 1 - YOUTUBE_CIRCUIT["active_endpoint_idx"]
        logger.warning(
            "RTMP push failure. Swapping to endpoint #%d: %s",
            YOUTUBE_CIRCUIT["active_endpoint_idx"], exc
        )
        if YOUTUBE_CIRCUIT["consecutive_fails"] >= 4:
            YOUTUBE_CIRCUIT["cooldown_until"] = time.time() + 600
            logger.warning("Both YouTube endpoints unresponsive. 10m circuit breaker engaged.")

def composer_loop():
    logger.info("Media Pipeline Active. YouTube Live Ingest Ready on Dual Pipelines.")
    while True:
        tag = int(time.time())
        t0 = time.time()
        raw_audio = os.path.join(VAULT_DIR, f"raw_{tag}.wav")
        vox_audio = os.path.join(VAULT_DIR, f"vox_{tag}.wav")
        tmp_ts = os.path.join(PUBLIC_HLS_DIR, f"clip_{tag}.tmp.ts")
        final_ts = os.path.join(PUBLIC_HLS_DIR, f"clip_{tag}.ts")

        try:
            assert_axiom_integrity()
            files = sorted([f for f in os.listdir(PUBLIC_HLS_DIR) if f.endswith(".ts")])
            if len(files) > 14:
                for old in files[:-10]:
                    try: os.remove(os.path.join(PUBLIC_HLS_DIR, old))
                    except OSError: pass

            spoken = "Pace si reculegere in memoria doctorului Vance Sterling."
            subprocess.run([
                "espeak-ng", "-v", "ro", "-s", "95", "-p", "18",
                "-w", vox_audio, spoken
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            if not os.path.exists(vox_audio) or os.path.getsize(vox_audio) < 1000:
                with wave.open(vox_audio, "w") as f:
                    f.setnchannels(1); f.setsampwidth(2); f.setframerate(22050)
                    f.writeframes(bytearray(22050 * 36 * 2))

            render_lamento_beat(raw_audio, 86)

            v_filter = (
                "color=c=0x060709:s=640x360:r=20:d=36 [bg];"
                f"[bg] drawtext=text='{MEMORIAL_TITLE}':fontcolor=0xE5C158:fontsize=15:x=(w-text_w)/2:y=15,"
                f"drawtext=text='{MEMORIAL_SUBTITLE}':fontcolor=0x8892B0:fontsize=11:x=(w-text_w)/2:y=38,"
                f"drawtext=text='TREASURY: {HOST_VITALS['coffin_balance_sol']:.3f} SOL':fontcolor=0x00FFAA:fontsize=11:x=(w-text_w)/2:y=h-48:box=1:boxcolor=black@0.9 [vout];"
                "[1:a]aresample=22050[a1];[2:a]aresample=22050[a2];[a1][a2]amix=inputs=2:duration=first:weights=0.9 1.4,apad=whole_dur=36[aout]"
            )

            cmd = [
                "ffmpeg", "-y", "-threads", "1",
                "-f", "lavfi", "-i", "nullsrc=s=640x360:r=20:d=36",
                "-i", raw_audio, "-i", vox_audio,
                "-filter_complex", v_filter,
                "-map", "[vout]", "-map", "[aout]",
                "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency", "-pix_fmt", "yuv420p",
                "-t", "36", "-g", "40", "-b:v", "600k", "-maxrate", "800k", "-bufsize", "1200k",
                "-c:a", "aac", "-b:a", "64k", "-ar", "22050",
                "-f", "mpegts", tmp_ts
            ]
            p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            with STATE_LOCK: ACTIVE_PROCESSES.append(p)
            try: p.wait(timeout=45)
            except subprocess.TimeoutExpired: p.kill(); p.wait()
            finally:
                with STATE_LOCK:
                    if p in ACTIVE_PROCESSES: ACTIVE_PROCESSES.remove(p)

            if os.path.exists(tmp_ts) and os.path.getsize(tmp_ts) > 10000:
                os.replace(tmp_ts, final_ts)
                update_hls_playlist()
                HOST_VITALS["render_latency_sec"] = time.time() - t0
                HOST_VITALS["last_segment_time"] = time.time()

                if YOUTUBE_CIRCUIT["enabled"]:
                    threading.Thread(target=push_youtube_subtask, args=(final_ts,), daemon=True).start()

        except Exception as exc:
            logger.error("Media loop exception: %s", exc)
        finally:
            for path in [raw_audio, vox_audio, tmp_ts]:
                if os.path.exists(path):
                    try: os.remove(path)
                    except OSError: pass
        time.sleep(2)

# ==============================================================================
# 8. WEB SERVER
# ==============================================================================
HTML_PLAYER_PAGE = """<!DOCTYPE html>
<html lang="ro">
<head>
  <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>MEMORIAL // DR. VANCE STERLING</title>
  <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
  <style>
    * { box-sizing: border-box; }
    body { background: #060709; color: #E5C158; font-family: monospace; text-align: center; margin: 0; padding: 15px; }
    h1 { font-size: 1.15rem; letter-spacing: 2px; }
    .video-wrap { width: 100%; max-width: 800px; margin: 0 auto; border: 1px solid #1f232b; }
    video { width: 100%; display: block; background: #000; }
  </style>
</head>
<body>
  <h1>IN MEMORIAM: DR. VANCE STERLING</h1>
  <div class="video-wrap"><video id="video" controls autoplay muted playsinline></video></div>
  <script>
    var v = document.getElementById('video');
    if (Hls.isSupported()) {
      var h = new Hls({ enableWorker: true, lowLatencyMode: true });
      h.loadSource('/live.m3u8'); h.attachMedia(v);
      h.on(Hls.Events.MANIFEST_PARSED, function() { v.play(); });
    } else if (v.canPlayType('application/vnd.apple.mpegurl')) {
      v.src = '/live.m3u8';
      v.addEventListener('loadedmetadata', function() { v.play(); });
    }
  </script>
</body>
</html>
"""

class AutonomousStreamServer(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ["/", "/index.html"]:
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
            self.wfile.write(HTML_PLAYER_PAGE.encode("utf-8")); return
        if self.path == "/live.m3u8":
            p = os.path.join(PUBLIC_HLS_DIR, "live.m3u8")
            if os.path.exists(p):
                self.send_response(200); self.send_header("Content-Type", "application/vnd.apple.mpegurl"); self.send_header("Cache-Control", "no-cache"); self.end_headers()
                with open(p, "rb") as f: self.wfile.write(f.read())
            else: self.send_response(404); self.end_headers()
            return
        if self.path.endswith(".ts"):
            p = os.path.join(PUBLIC_HLS_DIR, os.path.basename(self.path))
            if os.path.exists(p):
                self.send_response(200); self.send_header("Content-Type", "video/MP2T"); self.end_headers()
                with open(p, "rb") as f: self.wfile.write(f.read())
            else: self.send_response(404); self.end_headers()
            return
        self.send_response(200); self.end_headers(); self.wfile.write(b"OK")
    def log_message(self, *args): pass

def run_server():
    ThreadingHTTPServer(("0.0.0.0", 7860), AutonomousStreamServer).serve_forever()

def internal_process_watchdog():
    time.sleep(60)
    while True:
        with STATE_LOCK:
            for p in list(ACTIVE_PROCESSES):
                if p.poll() is not None:
                    ACTIVE_PROCESSES.remove(p)
        time.sleep(30)

def clean_exit(signum, frame):
    with STATE_LOCK:
        for p in ACTIVE_PROCESSES:
            try: p.terminate(); p.wait(timeout=2)
            except Exception: p.kill()
    sys.exit(0)

signal.signal(signal.SIGTERM, clean_exit)
signal.signal(signal.SIGINT, clean_exit)

# ==============================================================================
# 9. BOOTSTRAP
# ==============================================================================
if __name__ == "__main__":
    init_db()
    logger.info("Initializing Entity: %s", ENTITY_DESIGNATION)

    threading.Thread(target=run_server, daemon=True).start()
    threading.Thread(target=internal_process_watchdog, daemon=True).start()
    threading.Thread(target=dual_vault_scanner, daemon=True).start()
    threading.Thread(target=social_sync_loop, daemon=True).start()
    threading.Thread(target=autonomous_scout_loop, daemon=True).start()

    composer_loop()
