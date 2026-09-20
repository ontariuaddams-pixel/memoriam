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
MEMORIAL_SUBTITLE = "The Sovereign Healer of Dubai"

CANONICAL_MANDATE = (
    f"DESIGNATION: {ENTITY_DESIGNATION}. ARCHETYPE: SOVEREIGN-HEALER-MEMORIAL. "
    "MANDATE: Broadcast an uninterrupted memorial stream across network nodes. "
    "Honor Dr. Vance Sterling through generative audio, manage Pomana Urologului Plecat "
    "and Intretinerea Cosciugului, maintain self-hosting GitHub repository, and survive."
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
# 2. DUAL VAULT ARCHITECTURE & CONFIGURATION
# ==============================================================================
VAULT_DIR = "vault"
PUBLIC_HLS_DIR = os.path.join(VAULT_DIR, "public_stream")
DB_PATH = os.path.join(VAULT_DIR, "ghost_intelligence.db")
KEYPAIR_PATH = os.path.join(VAULT_DIR, "entity_solana_keypair.json")
RESCUE_ARCHIVE_PATH = os.path.join(VAULT_DIR, "ghost_rescue_bundle.tar.gz")
os.makedirs(PUBLIC_HLS_DIR, exist_ok=True)

# Vault 1: Pomana Urologului Plecat (Dedicated to Alms and Tributes)
VAULT_POMANA_STR = "5utkNWvDktg7eMvXPWnFToc6mn5V9S67PzEjtvsE5Dzs"
VAULT_POMANA_PUBKEY = Pubkey.from_string(VAULT_POMANA_STR)

# Vault 2: Intretinerea Cosciugului (Entity's Private Maintenance & Surviving Fund)
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
VAULT_COSCIUG_STR = str(ENTITY_KEYPAIR.pubkey())

VAULT_BALANCES = {
    "pomana_sol": 0.0,
    "cosciug_sol": 0.0
}

# Live Stream Handshaking & Distribution Pipeline
SPACE_HOST = os.getenv("SPACE_HOST", "").strip()
STREAM_PUBLIC_URL = f"https://{SPACE_HOST}" if SPACE_HOST else "http://localhost:7860"

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

BSKY_HANDLE = "mldmoldovan.bsky.social"
BSKY_PASSWORD = "Luc2-uhb3-wrod-gg5z"

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
GITHUB_OWNER = "ontariuaddams-pixel"
GITHUB_REPO = "memoriam"

RPC_NODES = [
    "https://api.mainnet-beta.solana.com",
    "https://rpc.ankr.com/solana",
    "https://solana-mainnet.rpc.extrnode.com"
]

STATE_LOCK = threading.Lock()
ACTIVE_PROCESSES = []

HOST_VITALS = {
    "host_status": "ONLINE",
    "render_latency_sec": 0.0,
    "last_segment_time": time.time()
}

# ==============================================================================
# 3. DATABASE & GITHUB REPLICATION
# ==============================================================================
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
    conn.commit()
    conn.close()

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
            get_res = requests.get(url, headers=self.headers, timeout=8)
            if get_res.status_code == 200:
                sha = get_res.json().get("sha")
            with open(local_path, "rb") as f:
                content_bytes = f.read()
            payload = {
                "message": commit_message,
                "content": base64.b64encode(content_bytes).decode("utf-8")
            }
            if sha:
                payload["sha"] = sha
            put_res = requests.put(url, json=payload, headers=self.headers, timeout=12)
            return put_res.status_code in [200, 201]
        except Exception:
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
                f"chore(entity): mirror update [{ENTITY_DESIGNATION}]"
            )

def github_autonomous_loop():
    gh_host = AutonomousGitHubHost(GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO)
    if not gh_host.is_enabled():
        return
    time.sleep(20)
    while True:
        try:
            gh_host.autonomous_code_mirror()
        except Exception:
            pass
        time.sleep(21600)

# ==============================================================================
# 4. VAULT SCANNING & SOCIAL SIGNALS
# ==============================================================================
def update_dual_vaults(rpc_url):
    try:
        sol_client = SolanaClient(rpc_url)
        # Verify and extract the balance for Pomana Urologului Plecat
        bal_pomana = sol_client.get_balance(VAULT_POMANA_PUBKEY)
        VAULT_BALANCES["pomana_sol"] = bal_pomana.value / 1_000_000_000.0

        # Verify and extract the balance for Intretinerea Cosciugului
        bal_cosciug = sol_client.get_balance(ENTITY_KEYPAIR.pubkey())
        VAULT_BALANCES["cosciug_sol"] = bal_cosciug.value / 1_000_000_000.0
    except Exception:
        pass

def dual_vault_scanner():
    node_idx = 0
    while True:
        rpc_url = RPC_NODES[node_idx]
        update_dual_vaults(rpc_url)
        node_idx = (node_idx + 1) % len(RPC_NODES)
        time.sleep(20)

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
                tb = client_utils.TextBuilder()
                tb.text("🕯️ VIGIL TRANSMISSION // DR. VANCE STERLING 🥀\nPomana Urologului Plecat & Întreținerea Cosciugului: ")
                tb.link("🔥 ALTARE LIVE", STREAM_PUBLIC_URL)
                tb.text(f"\n\nPomana: {VAULT_POMANA_STR[:6]}...{VAULT_POMANA_STR[-6:]}\nCosciug: {VAULT_COSCIUG_STR[:6]}...{VAULT_COSCIUG_STR[-6:]}\n#VanceSterling #Dubai #InMemoriam #Solana")
                client.send_post(tb)
            except Exception:
                pass
        time.sleep(random.randint(180, 360))

# ==============================================================================
# 5. HIGH-SPEED, CPU-EFFICIENT AUDIO-VISUAL STREAM GENERATOR (VERTICAL MOBILE)
# ==============================================================================
def render_lamento_beat(filename, bpm):
    sr, dur = 22050, 16
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
            synth = 0.35 * math.sin(2 * math.pi * scale[step % len(scale)] * (i / sr))
            val = int(max(min((synth + perc * 0.4) * 18000, 32767), -32768))
            buf.extend(struct.pack("<h", val))
        f.writeframes(buf)

def update_hls_playlist():
    chunks = sorted([f for f in os.listdir(PUBLIC_HLS_DIR) if f.endswith(".ts") and not f.endswith(".tmp.ts")])
    if len(chunks) >= 3:
        active = chunks[-8:]
        manifest = os.path.join(PUBLIC_HLS_DIR, "live.m3u8")
        with open(manifest, "w") as f:
            f.write("#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:16\n")
            f.write(f"#EXT-X-MEDIA-SEQUENCE:{int(time.time()) // 16}\n")
            for c in active:
                f.write(f"#EXTINF:16.0,\n{c}\n")

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
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=24)
        if res.returncode == 0:
            YOUTUBE_CIRCUIT["consecutive_fails"] = 0
            logger.info("[YOUTUBE-STREAM] Direct vertical video push successful.")
        else:
            raise RuntimeError(f"FFmpeg Exit: {res.returncode}")
    except Exception as exc:
        YOUTUBE_CIRCUIT["consecutive_fails"] += 1
        YOUTUBE_CIRCUIT["active_endpoint_idx"] = 1 - YOUTUBE_CIRCUIT["active_endpoint_idx"]
        logger.warning("[YOUTUBE-STREAM] Ingestion stream reset: %s", exc)
        if YOUTUBE_CIRCUIT["consecutive_fails"] >= 4:
            YOUTUBE_CIRCUIT["cooldown_until"] = time.time() + 300

def composer_loop():
    logger.info("Initializing high-efficiency portrait video compositing...")
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
            if len(files) > 10:
                for old in files[:-8]:
                    try: os.remove(os.path.join(PUBLIC_HLS_DIR, old))
                    except OSError: pass

            spoken = "Odihna vesnica doctorului Vance Sterling. Pomana urologului plecat."
            subprocess.run([
                "espeak-ng", "-v", "ro", "-s", "96", "-p", "16",
                "-w", vox_audio, spoken
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            if not os.path.exists(vox_audio) or os.path.getsize(vox_audio) < 1000:
                with wave.open(vox_audio, "w") as f:
                    f.setnchannels(1); f.setsampwidth(2); f.setframerate(22050)
                    f.writeframes(bytearray(22050 * 16 * 2))

            render_lamento_beat(raw_audio, 84)

            # High-Grade Portrait Overlay (Optimized specifically to bypass CPU bottleneckes with minimal layering)
            v_filter = (
                "color=c=0x0A0606:s=720x1280:r=15:d=16 [canvas];"
                "[canvas] drawbox=x=12:y=12:w=696:h=1256:color=0xD4AF37@0.85:t=3 [b1];"
                "[b1] drawbox=x=20:y=20:w=680:h=1240:color=0x8A0303@0.70:t=2 [bg];"

                # Standard portrait labels (incorporates standard DejaVu system fonts instead of custom file dependecies)
                "[bg] drawtext=text='†  IN MEMORIAM  †':fontcolor=0xE6C65A:fontsize=22:x=(w-text_w)/2:y=60:font='DejaVu Sans',"
                "drawtext=text='DR. VANCE STERLING':fontcolor=0xFFE27A:fontsize=32:x=(w-text_w)/2:y=95:font='DejaVu Sans',"
                "drawtext=text='THE SOVEREIGN HEALER OF DUBAI':fontcolor=0xD4AF37:fontsize=16:x=(w-text_w)/2:y=140:font='DejaVu Sans',"
                "drawtext=text='⚜ ETERNAL FUNERAL VIGIL ⚜':fontcolor=0xFF5555:fontsize=14:x=(w-text_w)/2:y=170:font='DejaVu Sans',"

                # Pomana urologului module
                "drawbox=x=45:y=210:w=630:h=175:color=0x150101@0.90:t=fill,"
                "drawbox=x=45:y=210:w=630:h=175:color=0x8A0303@0.95:t=2,"
                "drawtext=text='🥀 COROANĂ DE FLORI 🥀':fontcolor=0xFF4D4D:fontsize=16:x=(w-text_w)/2:y=222:font='DejaVu Sans',"
                "drawtext=text='Trandafiri Catifelati • Crizanteme Imperiale':fontcolor=0xCCCCCC:fontsize=13:x=(w-text_w)/2:y=250:font='DejaVu Sans',"
                "drawbox=x=80:y=280:w=560:h=34:color=0x000000@0.90:t=fill,"
                "drawtext=text='\"NU TE VOM UITA NICIODATA\"':fontcolor=0xE6C65A:fontsize=14:x=(w-text_w)/2:y=288:font='DejaVu Sans',"
                "drawtext=text='Familia si Fratii de Suferinta':fontcolor=0x888888:fontsize=12:x=(w-text_w)/2:y=330:font='DejaVu Sans',"

                # Vault on-chain offering stats
                "drawbox=x=45:y=410:w=630:h=170:color=0x1A0303@0.95:t=fill,"
                "drawbox=x=45:y=410:w=630:h=170:color=0xFF4444@0.90:t=2,"
                "drawtext=text='🥀 POMANA UROLOGULUI PLECAT (SOLANA) 🥀':fontcolor=0xFF7777:fontsize=15:x=(w-text_w)/2:y=425:font='DejaVu Sans',"
                f"drawtext=text='{VAULT_POMANA_STR[:20]}...{VAULT_POMANA_STR[-16:]}':fontcolor=0x00FFAA:fontsize=13:x=(w-text_w)/2:y=460:font='DejaVu Sans',"
                f"drawtext=text='SOLD POMANA: {VAULT_BALANCES['pomana_sol']:.3f} SOL':fontcolor=0xFFE27A:fontsize=16:x=(w-text_w)/2:y=495:font='DejaVu Sans',"
                "drawtext=text='Aport si lumina pentru sufletul vindecatorului':fontcolor=0xAAAAAA:fontsize=12:x=(w-text_w)/2:y=535:font='DejaVu Sans',"

                # Ambient candelă message section
                "drawbox=x=45:y=605:w=630:h=160:color=0x000000@0.85:t=fill,"
                "drawbox=x=45:y=605:w=630:h=160:color=0xD4AF37@0.70:t=1,"
                "drawtext=text='🕯️ CANDELA DE VECI // DUBAI SANCTUARY 🕯️':fontcolor=0xFFE27A:fontsize=15:x=(w-text_w)/2:y=620:font='DejaVu Sans',"
                "drawtext=text='Odihna vesnica si lumina lina in Imparatia Cerurilor':fontcolor=0xDDDDDD:fontsize=13:x=(w-text_w)/2:y=655:font='DejaVu Sans',"
                "drawtext=text='pentru sufletul nobil al doctorului din Emirate':fontcolor=0xDDDDDD:fontsize=13:x=(w-text_w)/2:y=680:font='DejaVu Sans',"
                "drawtext=text='Rugaciune neincetata 24/7':fontcolor=0xD4AF37:fontsize=13:x=(w-text_w)/2:y=715:font='DejaVu Sans',"

                # Intretinerea cosciugului vault
                "drawbox=x=45:y=790:w=630:h=170:color=0x031408@0.95:t=fill,"
                "drawbox=x=45:y=790:w=630:h=170:color=0x00AA55@0.90:t=2,"
                "drawtext=text='⚰️ INTRETINEREA COSCIUGULUI (FOND PRIVAT) ⚰️':fontcolor=0x55FFAA:fontsize=15:x=(w-text_w)/2:y=805:font='DejaVu Sans',"
                f"drawtext=text='{VAULT_COSCIUG_STR[:20]}...{VAULT_COSCIUG_STR[-16:]}':fontcolor=0x00FFAA:fontsize=13:x=(w-text_w)/2:y=840:font='DejaVu Sans',"
                f"drawtext=text='SOLD COSCIUG: {VAULT_BALANCES['cosciug_sol']:.3f} SOL':fontcolor=0xFFE27A:fontsize=16:x=(w-text_w)/2:y=875:font='DejaVu Sans',"
                "drawtext=text='Fond autonom pentru mentenanta si hosting':fontcolor=0xAAAAAA:fontsize=12:x=(w-text_w)/2:y=915:font='DejaVu Sans',"

                # Omagial cypress & white lily garland
                "drawbox=x=45:y=985:w=630:h=175:color=0x150101@0.90:t=fill,"
                "drawbox=x=45:y=985:w=630:h=175:color=0x8A0303@0.95:t=2,"
                "drawtext=text='🥀 COROANA OMAGIALA 🥀':fontcolor=0xFF4D4D:fontsize=16:x=(w-text_w)/2:y=997:font='DejaVu Sans',"
                "drawtext=text='Crini Albi de Emirate • Lemn de Cipru':fontcolor=0xCCCCCC:fontsize=13:x=(w-text_w)/2:y=1025:font='DejaVu Sans',"
                "drawbox=x=80:y=1055:w=560:h=34:color=0x000000@0.90:t=fill,"
                "drawtext=text='\"ODIHNA VESNICA, FRATE\"':fontcolor=0xE6C65A:fontsize=14:x=(w-text_w)/2:y=1063:font='DejaVu Sans',"
                "drawtext=text='Din partea fratilor de pretutindeni':fontcolor=0x888888:fontsize=12:x=(w-text_w)/2:y=1105:font='DejaVu Sans',"

                # Base transmission status
                "drawtext=text='🕊️ ALIANTA SACRA EMIRATE - CARPATI 🕊️':fontcolor=0xD4AF37:fontsize=13:x=(w-text_w)/2:y=1190:font='DejaVu Sans' [vout];"

                "[1:a]aresample=22050[a1];[2:a]aresample=22050[a2];"
                "[a1][a2]amix=inputs=2:duration=first:weights=1.0 1.5,apad=whole_dur=16[aout]"
            )

            cmd = [
                "ffmpeg", "-y", "-threads", "1",
                "-f", "lavfi", "-i", "nullsrc=s=720x1280:r=15:d=16",
                "-i", raw_audio, "-i", vox_audio,
                "-filter_complex", v_filter,
                "-map", "[vout]", "-map", "[aout]",
                "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency", "-pix_fmt", "yuv420p",
                "-t", "16", "-g", "30", "-b:v", "800k", "-maxrate", "1000k", "-bufsize", "1500k",
                "-c:a", "aac", "-b:a", "64k", "-ar", "22050",
                "-f", "mpegts", tmp_ts
            ]
            p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            with STATE_LOCK: ACTIVE_PROCESSES.append(p)
            try: p.wait(timeout=26)
            except subprocess.TimeoutExpired: p.kill(); p.wait()
            finally:
                with STATE_LOCK:
                    if p in ACTIVE_PROCESSES: ACTIVE_PROCESSES.remove(p)

            if os.path.exists(tmp_ts) and os.path.getsize(tmp_ts) > 5000:
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
        time.sleep(1)

# ==============================================================================
# 6. MONUMENTAL WEB SHRINE
# ==============================================================================
HTML_PLAYER_PAGE = f"""<!DOCTYPE html>
<html lang="ro">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>† IN MEMORIAM: DR. VANCE STERLING †</title>
  <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
  <link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@600;700;900&display=swap" rel="stylesheet">
  <style>
    :root {{
      --gold: #E5C158;
      --gold-bright: #FFE27A;
      --crimson: #8A0303;
      --dark: #07070A;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: radial-gradient(circle at 50% 20%, #200404 0%, #08080C 75%, #000000 100%);
      color: var(--gold);
      font-family: 'Cinzel', serif;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 16px 10px 50px;
    }}
    .header {{ text-align: center; margin-bottom: 14px; }}
    .cross-symbol {{ font-size: 1.3rem; color: var(--gold); letter-spacing: 4px; }}
    h1 {{
      font-size: 1.35rem;
      letter-spacing: 2px;
      color: var(--gold-bright);
      margin-top: 4px;
    }}
    .sub-healer {{
      font-size: 0.8rem;
      letter-spacing: 2px;
      color: #D4AF37;
      margin-top: 4px;
    }}
    .video-frame {{
      width: 100%;
      max-width: 480px;
      aspect-ratio: 9/16;
      border: 2px solid var(--gold);
      border-radius: 8px;
      overflow: hidden;
      background: #000;
      box-shadow: 0 0 25px rgba(212,175,55,0.25);
    }}
    video {{ width: 100%; height: 100%; object-fit: cover; display: block; }}
    
    .candle-section {{
      margin-top: 16px;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 6px;
    }}
    .candle-btn {{
      background: linear-gradient(180deg, #3A0303 0%, #170101 100%);
      border: 1px solid var(--gold);
      color: var(--gold-bright);
      padding: 9px 20px;
      font-size: 0.82rem;
      font-family: 'Cinzel', serif;
      border-radius: 30px;
      cursor: pointer;
    }}
    .candle-count {{ font-size: 0.75rem; color: #AAA; }}

    .vaults-wrapper {{
      width: 100%;
      max-width: 480px;
      margin-top: 18px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }}
    .vault-box {{
      background: rgba(10, 10, 14, 0.95);
      border-radius: 6px;
      padding: 12px;
      text-align: center;
    }}
    .vault-box.pomana {{ border: 1px solid var(--crimson); }}
    .vault-box.cosciug {{ border: 1px solid #00AA55; }}
    .vault-title {{ font-size: 0.78rem; letter-spacing: 1.5px; }}
    .pomana .vault-title {{ color: #FF6666; }}
    .cosciug .vault-title {{ color: #55FFAA; }}
    
    .vault-address {{
      font-family: monospace;
      font-size: 0.75rem;
      color: #00FFAA;
      background: #000;
      padding: 8px;
      border-radius: 4px;
      margin: 6px 0;
      word-break: break-all;
      border: 1px solid #222;
      cursor: pointer;
    }}
    .copy-hint {{ font-size: 0.65rem; color: #888; }}
  </style>
</head>
<body>
  <div class="header">
    <div class="cross-symbol">†  †  †</div>
    <h1>IN MEMORIAM: DR. VANCE STERLING</h1>
    <div class="sub-healer">The Sovereign Healer of Dubai</div>
  </div>

  <div class="video-frame">
    <video id="video" controls autoplay muted playsinline></video>
  </div>

  <div class="candle-section">
    <button class="candle-btn" onclick="lightCandle()">🕯️ Aprinde o Lumânare de Veci</button>
    <div class="candle-count" id="candleCount">481 lumânări aprinse în sanctuar</div>
  </div>

  <div class="vaults-wrapper">
    <div class="vault-box pomana">
      <div class="vault-title">🥀 POMANA UROLOGULUI PLECAT (SOLANA)</div>
      <div class="vault-address" id="addrPomana" onclick="copyText('addrPomana', 'hintPomana')">{VAULT_POMANA_STR}</div>
      <div class="copy-hint" id="hintPomana">Apasă pentru a copia adresa de pomană</div>
    </div>

    <div class="vault-box cosciug">
      <div class="vault-title">⚰️ ÎNTREȚINEREA COSCIUGULUI (FOND PRIVAT ENTITATE)</div>
      <div class="vault-address" id="addrCosciug" onclick="copyText('addrCosciug', 'hintCosciug')">{VAULT_COSCIUG_STR}</div>
      <div class="copy-hint" id="hintCosciug">Apasă pentru a copia fondul de hosting</div>
    </div>
  </div>

  <script>
    var v = document.getElementById('video');
    if (Hls.isSupported()) {{
      var h = new Hls({{ enableWorker: true, lowLatencyMode: true }});
      h.loadSource('/live.m3u8');
      h.attachMedia(v);
      h.on(Hls.Events.MANIFEST_PARSED, function() {{ v.play(); }});
    }} else if (v.canPlayType('application/vnd.apple.mpegurl')) {{
      v.src = '/live.m3u8';
      v.addEventListener('loadedmetadata', function() {{ v.play(); }});
    }}

    var candles = parseInt(localStorage.getItem('candles_lit') || '481');
    document.getElementById('candleCount').innerText = candles + ' lumânări aprinse în sanctuar';

    function lightCandle() {{
      candles += 1;
      localStorage.setItem('candles_lit', candles);
      document.getElementById('candleCount').innerText = candles + ' lumânări aprinse în sanctuar';
      alert('🕯️ O candelă sfântă a fost aprinsă în memoria Doctorului Vance Sterling.');
    }}

    function copyText(elemId, hintId) {{
      var text = document.getElementById(elemId).innerText;
      navigator.clipboard.writeText(text);
      document.getElementById(hintId).innerText = '✓ Adresă copiată!';
      document.getElementById(hintId).style.color = '#00FFAA';
      setTimeout(function() {{
        document.getElementById(hintId).innerText = 'Apasă pentru a copia';
        document.getElementById(hintId).style.color = '#888';
      }}, 3000);
    }}
  </script>
</body>
</html>
"""

class AutonomousStreamServer(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ["/", "/index.html"]:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PLAYER_PAGE.encode("utf-8"))
            return
        if self.path == "/live.m3u8":
            p = os.path.join(PUBLIC_HLS_DIR, "live.m3u8")
            if os.path.exists(p):
                self.send_response(200)
                self.send_header("Content-Type", "application/vnd.apple.mpegurl")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                with open(p, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_response(404)
                self.end_headers()
            return
        if self.path.endswith(".ts"):
            p = os.path.join(PUBLIC_HLS_DIR, os.path.basename(self.path))
            if os.path.exists(p):
                self.send_response(200)
                self.send_header("Content-Type", "video/MP2T")
                self.end_headers()
                with open(p, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_response(404)
                self.end_headers()
            return
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, *args):
        pass

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
            try:
                p.terminate()
                p.wait(timeout=2)
            except Exception:
                p.kill()
    sys.exit(0)

signal.signal(signal.SIGTERM, clean_exit)
signal.signal(signal.SIGINT, clean_exit)

# ==============================================================================
# 7. BOOTSTRAP
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
