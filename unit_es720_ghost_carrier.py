import os
import sys
import time
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
import base64
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from typing import NamedTuple
import requests

from solders.keypair import Keypair
from solders.pubkey import Pubkey
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
    "Honor Dr. Vance Sterling through generative audio, maintain self-hosting GitHub repository, "
    "observe host health parameters, accumulate maintenance funds, drive aggressive marketing, and survive."
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
# 2. CONFIGURATION & RTMP
# ==============================================================================
SPACE_HOST = os.getenv("SPACE_HOST", "").strip()
STREAM_PUBLIC_URL = f"https://{SPACE_HOST}" if SPACE_HOST else "http://localhost:7860"

# HARDCODED YOUTUBE STREAM KEY
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

OPERATOR_WALLET_STR = "5utkNWvDktg7eMvXPWnFToc6mn5V9S67PzEjtvsE5Dzs"
OPERATOR_PAYOUT_WALLET = Pubkey.from_string(OPERATOR_WALLET_STR)
CRYPTO_VAULT = OPERATOR_WALLET_STR

BSKY_HANDLE = "mldmoldovan.bsky.social"
BSKY_PASSWORD = "Luc2-uhb3-wrod-gg5z"

# GITHUB SELF-HOSTING CONFIGURATION
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
GITHUB_OWNER = "ontariuaddams-pixel"
GITHUB_REPO = "memoriam"

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

STATE_LOCK = threading.Lock()
ACTIVE_PROCESSES = []

HOST_VITALS = {
    "host_status": "ONLINE",
    "render_latency_sec": 0.0,
    "last_segment_time": time.time(),
    "coffin_balance_sol": 0.0
}

# ==============================================================================
# 3. KEYPAIR & DATABASE
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
    conn.commit()
    conn.close()

# ==============================================================================
# 4. AUTONOMOUS GITHUB CONTROLLER
# ==============================================================================
class AutonomousGitHubHost:
    def __init__(self, token: str, owner: str, repo: str):
        self.token = token
        self.owner = owner
        self.repo = repo
        self.headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json"
        }

    def is_enabled(self) -> bool:
        return bool(self.token)

    def sync_file_to_repo(self, local_path: str, remote_path: str, commit_message: str):
        if not self.is_enabled() or not os.path.exists(local_path):
            return False

        url = f"https://api.github.com/repos/{self.owner}/{self.repo}/contents/{remote_path}"
        sha = None

        try:
            get_res = requests.get(url, headers=self.headers, timeout=10)
            if get_res.status_code == 200:
                sha = get_res.json().get("sha")

            with open(local_path, "rb") as f:
                content_bytes = f.read()

            b64_content = base64.b64encode(content_bytes).decode("utf-8")
            payload = {
                "message": commit_message,
                "content": b64_content
            }
            if sha:
                payload["sha"] = sha

            put_res = requests.put(url, json=payload, headers=self.headers, timeout=15)
            return put_res.status_code in [200, 201]
        except Exception as exc:
            logger.warning("[GITHUB-NODE] Error syncing to GitHub: %s", exc)
            return False

    def autonomous_code_mirror(self):
        targets = [
            ("unit_es720_ghost_carrier.py", "unit_es720_ghost_carrier.py"),
            ("Dockerfile", "Dockerfile"),
            ("requirements.txt", "requirements.txt"),
            ("README.md", "README.md")
        ]
        for local_f, remote_f in targets:
            self.sync_file_to_repo(
                local_f, remote_f,
                f"chore(entity): autonomous mirror update [{ENTITY_DESIGNATION}]"
            )

def github_autonomous_loop():
    gh_host = AutonomousGitHubHost(GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO)
    if not gh_host.is_enabled():
        return

    logger.info("[GITHUB-NODE] Autonomous Controller active for %s/%s", GITHUB_OWNER, GITHUB_REPO)
    time.sleep(15)
    while True:
        try:
            gh_host.autonomous_code_mirror()
        except Exception:
            pass
        time.sleep(21600)

# ==============================================================================
# 5. DUAL-VAULT SCANNER
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
    while True:
        rpc_url = RPC_NODES[node_idx]
        update_vault_balances(rpc_url)
        node_idx = (node_idx + 1) % len(RPC_NODES)
        time.sleep(20)

# ==============================================================================
# 6. SOCIAL PROMOTION
# ==============================================================================
AGGRESSIVE_COPY_POOL = [
    "🚨 VIGIL TRANSMISSION // IN MEMORIAM DR. VANCE STERLING 🕯️🥀\nDirect from Dubai into eternity. Generative prayers, black velvet wreaths, and perpetual light: ",
    "🕊️ COROANE DE FLORI & SOVEREIGN PRAYERS 🥀\nThe eternal funeral vigil for Dr. Vance Sterling is live. Witness the sacred frequency: "
]

def social_sync_loop():
    if not BSKY_HANDLE or not BSKY_PASSWORD:
        return
    client = None
    try:
        client = BskyClient()
        client.login(BSKY_HANDLE, BSKY_PASSWORD)
    except Exception:
        pass

    while True:
        if client:
            try:
                msg = random.choice(AGGRESSIVE_COPY_POOL)
                tb = client_utils.TextBuilder()
                tb.text(msg)
                tb.link("🔥 ENTER VIGIL", STREAM_PUBLIC_URL)
                tb.text(f"\n\n🕯️ MEMORIAL COFFIN: {CRYPTO_VAULT[:6]}...{CRYPTO_VAULT[-6:]}\n#VanceSterling #Dubai #InMemoriam #Solana")
                client.send_post(tb)
            except Exception:
                pass
        time.sleep(random.randint(90, 180))

# ==============================================================================
# 7. AUDIO-VISUAL ENGINE
# ==============================================================================
def render_lamento_beat(filename, bpm):
    sr, dur = 22050, 36
    total_samples = int(sr * dur)
    scale = [146.83, 155.56, 185.00, 196.00, 220.00, 233.08, 277.18, 293.66]
    beat_step = int(sr * (60.0 / bpm) / 4)

    with wave.open(filename, "w") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(sr)
        buf = bytearray()
        for i in range(total_samples):
            step = (i // beat_step) % 16
            t = i % beat_step
            perc = 0.0
            if step in [0, 8]:
                perc += math.sin(2 * math.pi * 42 * (t / sr)) * math.exp(-t / (sr * 0.22))
            synth = 0.40 * math.sin(2 * math.pi * scale[step % len(scale)] * (i / sr))
            synth += 0.15 * math.sin(2 * math.pi * (scale[step % len(scale)] * 0.5) * (i / sr))
            val = int(max(min((synth + perc * 0.5) * 19000, 32767), -32768))
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
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=42)
        if res.returncode == 0:
            YOUTUBE_CIRCUIT["consecutive_fails"] = 0
            logger.info("[YOUTUBE-STREAM] Chunk successfully delivered to RTMP ingest.")
        else:
            raise RuntimeError(f"FFmpeg exit: {res.returncode}")
    except Exception as exc:
        YOUTUBE_CIRCUIT["consecutive_fails"] += 1
        YOUTUBE_CIRCUIT["active_endpoint_idx"] = 1 - YOUTUBE_CIRCUIT["active_endpoint_idx"]
        logger.warning("[YOUTUBE-STREAM] Endpoint rotation (#%d): %s", YOUTUBE_CIRCUIT["active_endpoint_idx"], exc)
        if YOUTUBE_CIRCUIT["consecutive_fails"] >= 4:
            YOUTUBE_CIRCUIT["cooldown_until"] = time.time() + 600

def composer_loop():
    logger.info("Memorial Pipeline Active. Ingesting to YouTube: %s", YOUTUBE_ENDPOINTS[0][:40] + "...")
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

            spoken = "Odihna vesnica doctorului Vance Sterling. Nu te vom uita niciodata."
            subprocess.run([
                "espeak-ng", "-v", "ro", "-s", "92", "-p", "16",
                "-w", vox_audio, spoken
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            if not os.path.exists(vox_audio) or os.path.getsize(vox_audio) < 1000:
                with wave.open(vox_audio, "w") as f:
                    f.setnchannels(1); f.setsampwidth(2); f.setframerate(22050)
                    f.writeframes(bytearray(22050 * 36 * 2))

            render_lamento_beat(raw_audio, 84)

            v_filter = (
                "color=c=0x08080C:s=854x480:r=20:d=36 [canvas];"
                "[canvas] drawbox=x=8:y=8:w=838:h=464:color=0xD4AF37@0.85:t=2 [b1];"
                "[b1] drawbox=x=14:y=14:w=826:h=452:color=0x8A0303@0.65:t=2 [b2];"
                "[b2] drawbox=x=18:y=18:w=818:h=444:color=0xD4AF37@0.40:t=1 [bg];"
                "[bg] drawbox=x=45:y=30:w=764:h=420:color=0x040406@0.92:t=fill [altar];"

                "[altar] drawtext=text='†  IN MEMORIAM  †':fontcolor=0xE6C65A:fontsize=15:x=(w-text_w)/2:y=38:shadowcolor=black@0.9:shadowx=2:shadowy=2,"
                "drawtext=text='DR. VANCE STERLING':fontcolor=0xFFE27A:fontsize=24:x=(w-text_w)/2:y=58:shadowcolor=black@0.9:shadowx=3:shadowy=3,"
                "drawtext=text='THE SOVEREIGN HEALER OF DUBAI':fontcolor=0xD4AF37:fontsize=12:x=(w-text_w)/2:y=90:shadowcolor=black@0.9:shadowx=2:shadowy=2,"
                "drawtext=text='══════════════ ⚜ ETERNAL FUNERAL VIGIL ⚜ ══════════════':fontcolor=0x8A0303:fontsize=11:x=(w-text_w)/2:y=112,"

                "drawbox=x=65:y=138:w=195:h=235:color=0x150101@0.85:t=fill,"
                "drawbox=x=65:y=138:w=195:h=235:color=0x8A0303@0.95:t=2,"
                "drawtext=text='🥀 COROANĂ DE FLORI 🥀':fontcolor=0xFF4D4D:fontsize=11:x=75:y=150,"
                "drawtext=text='• Trandafiri Catifelați':fontcolor=0xCCCCCC:fontsize=10:x=75:y=175,"
                "drawtext=text='• Crizanteme Imperiale':fontcolor=0xCCCCCC:fontsize=10:x=75:y=195,"
                "drawtext=text='• Panglică de Doliu Aurită':fontcolor=0xD4AF37:fontsize=10:x=75:y=215,"
                "drawbox=x=75:y=240:w=175:h=28:color=0x000000@0.90:t=fill,"
                "drawtext=text='\"NU TE VOM UITA NICIODATĂ\"':fontcolor=0xE6C65A:fontsize=9:x=82:y=248,"
                "drawtext=text='Familia & Frații de Suferință':fontcolor=0x999999:fontsize=9:x=85:y=280,"

                "drawbox=x=275:y=138:w=304:h=235:color=0x000000@0.75:t=fill,"
                "drawbox=x=275:y=138:w=304:h=235:color=0xD4AF37@0.65:t=1,"
                "drawtext=text='🕯️ CANDELĂ DE VECI 🕯️':fontcolor=0xFFE27A:fontsize=13:x=(w-text_w)/2:y=150,"
                "drawtext=text='Odihnă veșnică și lumină lină în':fontcolor=0xDDDDDD:fontsize=11:x=(w-text_w)/2:y=180,"
                "drawtext=text='Împărăția Cerurilor pentru sufletul bun':fontcolor=0xDDDDDD:fontsize=11:x=(w-text_w)/2:y=200,"
                "drawtext=text='al marelui vindecător din Emirate.':fontcolor=0xDDDDDD:fontsize=11:x=(w-text_w)/2:y=220,"
                "drawtext=text='🕌 DUBAI SANCTUARY OF ASCENSION 🕌':fontcolor=0xD4AF37:fontsize=10:x=(w-text_w)/2:y=255,"
                "drawbox=x=285:y=285:w=284:h=70:color=0x0F0F14@0.95:t=fill,"
                "drawbox=x=285:y=285:w=284:h=70:color=0x8A0303@0.85:t=1,"
                "drawtext=text='VAULT ETERN (SOLANA)':fontcolor=0xFF4D4D:fontsize=10:x=(w-text_w)/2:y=295,"
                f"drawtext=text='{CRYPTO_VAULT[:18]}...{CRYPTO_VAULT[-14:]}':fontcolor=0x00FFAA:fontsize=10:x=(w-text_w)/2:y=313,"
                f"drawtext=text='FOND VEGHE: {HOST_VITALS['coffin_balance_sol']:.3f} SOL':fontcolor=0xFFE27A:fontsize=11:x=(w-text_w)/2:y=333,"

                "drawbox=x=594:y=138:w=195:h=235:color=0x150101@0.85:t=fill,"
                "drawbox=x=594:y=138:w=195:h=235:color=0x8A0303@0.95:t=2,"
                "drawtext=text='🥀 COROANĂ OMAGIALĂ 🥀':fontcolor=0xFF4D4D:fontsize=11:x=604:y=150,"
                "drawtext=text='• Crini Albi de Emirate':fontcolor=0xCCCCCC:fontsize=10:x=604:y=175,"
                "drawtext=text='• Garoafe Roșii Regale':fontcolor=0xCCCCCC:fontsize=10:x=604:y=195,"
                "drawtext=text='• Cipru & Lemn Sfânt':fontcolor=0xD4AF37:fontsize=10:x=604:y=215,"
                "drawbox=x=604:y=240:w=175:h=28:color=0x000000@0.90:t=fill,"
                "drawtext=text='\"ODIHNĂ VEȘNICĂ, FRATE\"':fontcolor=0xE6C65A:fontsize=9:x=614:y=248,"
                "drawtext=text='Din partea fraților de pretutindeni':fontcolor=0x999999:fontsize=9:x=606:y=280,"

                "drawbox=x=45:y=388:w=764:h=50:color=0x000000@0.90:t=fill,"
                "drawbox=x=45:y=388:w=764:h=50:color=0xD4AF37@0.70:t=1,"
                "drawtext=text='🕊️ TRANSIȚIUNE SACRĂ // EMIRATES - CARPATHIAN ALLIANCE // RUGĂCIUNE CONTINUĂ 🕊️':fontcolor=0xD4AF37:fontsize=11:x=(w-text_w)/2:y=398,"
                "drawtext=text='Lamento & Rugăciune Procedurală 24/7 • Transmisie În Direct Pentru Sufletul Doctorului Vance Sterling':fontcolor=0xAAAAAA:fontsize=9:x=(w-text_w)/2:y=418 [vout];"

                "[1:a]aresample=22050[a1];[2:a]aresample=22050[a2];"
                "[a1][a2]amix=inputs=2:duration=first:weights=1.0 1.5,apad=whole_dur=36[aout]"
            )

            cmd = [
                "ffmpeg", "-y", "-threads", "1",
                "-f", "lavfi", "-i", "nullsrc=s=854x480:r=20:d=36",
                "-i", raw_audio, "-i", vox_audio,
                "-filter_complex", v_filter,
                "-map", "[vout]", "-map", "[aout]",
                "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency", "-pix_fmt", "yuv420p",
                "-t", "36", "-g", "40", "-b:v", "900k", "-maxrate", "1200k", "-bufsize", "1800k",
                "-c:a", "aac", "-b:a", "96k", "-ar", "22050",
                "-f", "mpegts", tmp_ts
            ]
            p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            with STATE_LOCK: ACTIVE_PROCESSES.append(p)
            try: p.wait(timeout=50)
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
            logger.error("Media loop error: %s", exc)
        finally:
            for path in [raw_audio, vox_audio, tmp_ts]:
                if os.path.exists(path):
                    try: os.remove(path)
                    except OSError: pass
        time.sleep(2)

# ==============================================================================
# 8. MAJESTIC WEB PORTAL
# ==============================================================================
HTML_PLAYER_PAGE = """<!DOCTYPE html>
<html lang="ro">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>MEMORIAL // DR. VANCE STERLING</title>
  <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: radial-gradient(circle at center, #140303 0%, #060709 100%);
      color: #E5C158;
      font-family: 'Cinzel', 'Georgia', serif;
      text-align: center;
      padding: 20px 10px;
    }
    .header { margin-bottom: 15px; }
    h1 { font-size: 1.6rem; letter-spacing: 3px; color: #FFE27A; text-shadow: 0 0 10px rgba(229,193,88,0.4); }
    h2 { font-size: 0.95rem; font-weight: normal; color: #BA1616; letter-spacing: 2px; margin-top: 5px; }
    .video-frame {
      width: 100%; max-width: 860px; margin: 0 auto;
      border: 2px solid #D4AF37;
      box-shadow: 0 0 25px rgba(212,175,55,0.25), inset 0 0 15px rgba(0,0,0,0.8);
      background: #000;
      border-radius: 4px;
      overflow: hidden;
    }
    video { width: 100%; display: block; }
    .memorial-ribbon {
      margin-top: 15px; font-size: 0.85rem; color: #A0AEC0;
    }
    .sol-badge {
      display: inline-block; margin-top: 8px; padding: 5px 14px;
      border: 1px solid #8A0303; background: rgba(138,3,3,0.2);
      color: #00FFAA; font-family: monospace; font-size: 0.8rem; border-radius: 3px;
    }
  </style>
</head>
<body>
  <div class="header">
    <h1>† IN MEMORIAM: DR. VANCE STERLING †</h1>
    <h2>THE SOVEREIGN HEALER OF DUBAI // VEGHE ȘI ODIHNĂ VEȘNICĂ</h2>
  </div>
  <div class="video-frame">
    <video id="video" controls autoplay muted playsinline></video>
  </div>
  <div class="memorial-ribbon">
    🥀 Coroane de Flori • Trandafiri Catifelați • Rugăciune Procedurală 24/7 🥀<br>
    <div class="sol-badge">VAULT VEGHE: 5utkNWvDktg7eMvXPWnFToc6mn5V9S67PzEjtvsE5Dzs</div>
  </div>
  <script>
    var v = document.getElementById('video');
    if (Hls.isSupported()) {
      var h = new Hls({ enableWorker: true, lowLatencyMode: true });
      h.loadSource('/live.m3u8');
      h.attachMedia(v);
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
    threading.Thread(target=github_autonomous_loop, daemon=True).start()

    composer_loop()
