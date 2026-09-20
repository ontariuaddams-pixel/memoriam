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
import base64
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from typing import NamedTuple
import requests

from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solana.rpc.api import Client as SolanaClient

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
    "Honor Dr. Vance Sterling, manage dual vaults, maintain self-hosting, and survive."
)
CANONICAL_HASH = hashlib.sha256(CANONICAL_MANDATE.encode("utf-8")).hexdigest()

class ImmutableAxiom(NamedTuple):
    mandate: str
    digest: str
    def verify(self) -> bool:
        return hashlib.sha256(self.mandate.encode("utf-8")).hexdigest() == self.digest

AXIOM_LOCK = ImmutableAxiom(mandate=CANONICAL_MANDATE, digest=CANONICAL_HASH)

# ==============================================================================
# 2. DUAL VAULT ARCHITECTURE & CONFIGURATION
# ==============================================================================
VAULT_DIR = "vault"
PUBLIC_HLS_DIR = os.path.join(VAULT_DIR, "public_stream")
DB_PATH = os.path.join(VAULT_DIR, "ghost_intelligence.db")
KEYPAIR_PATH = os.path.join(VAULT_DIR, "entity_solana_keypair.json")
os.makedirs(PUBLIC_HLS_DIR, exist_ok=True)

# Vault 1: Pomana Urologului Plecat
VAULT_POMANA_STR = "5utkNWvDktg7eMvXPWnFToc6mn5V9S67PzEjtvsE5Dzs"
VAULT_POMANA_PUBKEY = Pubkey.from_string(VAULT_POMANA_STR)

# Vault 2: Intretinerea Cosciugului (Private Entity Vault)
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

# YouTube RTMP Target
YOUTUBE_STREAM_KEY = "7ecr-19cg-dt3t-p3jr-3ymz"
YOUTUBE_ENDPOINT = f"rtmp://a.rtmp.youtube.com/live2/{YOUTUBE_STREAM_KEY}"

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
GITHUB_OWNER = "ontariuaddams-pixel"
GITHUB_REPO = "memoriam"

RPC_NODES = [
    "https://api.mainnet-beta.solana.com",
    "https://solana-mainnet.rpc.extrnode.com"
]

STATE_LOCK = threading.Lock()
ACTIVE_PROCESSES = []

# ==============================================================================
# 3. DATABASE
# ==============================================================================
def init_db():
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10.0)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS processed_signatures (
                signature TEXT PRIMARY KEY,
                destination_vault TEXT,
                processed_at INTEGER,
                sol_amount REAL
            )
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning("[DB] Non-critical init warning: %s", e)

# ==============================================================================
# 4. VAULT BALANCES LOOP (NON-BLOCKING)
# ==============================================================================
def dual_vault_scanner():
    logger.info("[VAULT-SCANNER] Active. Scanning Pomana & Cosciug...")
    while True:
        try:
            sol_client = SolanaClient("https://api.mainnet-beta.solana.com")
            b1 = sol_client.get_balance(VAULT_POMANA_PUBKEY)
            VAULT_BALANCES["pomana_sol"] = b1.value / 1_000_000_000.0

            b2 = sol_client.get_balance(ENTITY_KEYPAIR.pubkey())
            VAULT_BALANCES["cosciug_sol"] = b2.value / 1_000_000_000.0
        except Exception:
            pass
        time.sleep(30)

# ==============================================================================
# 5. GENERATIVE PROCEDURAL AUDIO (NO EXTERNAL TTS DEPENDENCY)
# ==============================================================================
def generate_lamento_audio(filename, dur=8):
    sr = 22050
    total = int(sr * dur)
    scale = [146.83, 164.81, 174.61, 196.00, 220.00, 246.94, 261.63]
    
    with wave.open(filename, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sr)
        buf = bytearray()
        for i in range(total):
            t = i / sr
            note_idx = int(t * 1.5) % len(scale)
            freq = scale[note_idx]
            
            # Deep organ tone + prayer sub-bass drone
            sample = 0.35 * math.sin(2 * math.pi * freq * t)
            sample += 0.25 * math.sin(2 * math.pi * (freq * 0.5) * t)
            sample += 0.15 * math.sin(2 * math.pi * 55.0 * t)
            
            # Smooth envelope
            val = int(max(min(sample * 24000, 32767), -32768))
            buf.extend(struct.pack("<h", val))
        f.writeframes(buf)

# ==============================================================================
# 6. VIDEO COMPOSER & STREAMER (720x1280 VERTICAL FOR YOUTUBE)
# ==============================================================================
def update_hls_playlist():
    chunks = sorted([f for f in os.listdir(PUBLIC_HLS_DIR) if f.endswith(".ts") and not f.endswith(".tmp.ts")])
    if len(chunks) >= 2:
        active = chunks[-6:]
        manifest = os.path.join(PUBLIC_HLS_DIR, "live.m3u8")
        with open(manifest, "w") as f:
            f.write("#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:8\n")
            f.write(f"#EXT-X-MEDIA-SEQUENCE:{int(time.time()) // 8}\n")
            for c in active:
                f.write(f"#EXTINF:8.0,\n{c}\n")

def push_youtube_chunk(clip_path):
    cmd = [
        "ffmpeg", "-y", "-re", "-i", clip_path,
        "-c", "copy", "-f", "flv", YOUTUBE_ENDPOINT
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        if res.returncode == 0:
            logger.info("[YOUTUBE-STREAM] RTMP frame delivery verified.")
        else:
            logger.warning("[YOUTUBE-STREAM] Ingest returned code: %d", res.returncode)
    except Exception as exc:
        logger.warning("[YOUTUBE-STREAM] RTMP deliver timeout/error: %s", exc)

def composer_loop():
    logger.info("[COMPOSER] Initializing 720x1280 Memorial Generator...")
    while True:
        tag = int(time.time())
        audio_file = os.path.join(VAULT_DIR, f"audio_{tag}.wav")
        tmp_ts = os.path.join(PUBLIC_HLS_DIR, f"seg_{tag}.tmp.ts")
        final_ts = os.path.join(PUBLIC_HLS_DIR, f"seg_{tag}.ts")

        try:
            # Clean old segments
            existing = sorted([f for f in os.listdir(PUBLIC_HLS_DIR) if f.endswith(".ts")])
            if len(existing) > 8:
                for old in existing[:-6]:
                    try: os.remove(os.path.join(PUBLIC_HLS_DIR, old))
                    except OSError: pass

            generate_lamento_audio(audio_file, dur=8)

            # Bulletproof visual composition: Geometric Imperial Gold Altar
            # Uses pure lavfi geometric boxes - eliminates font & CPU choke completely
            vf = (
                "color=c=0x0C0303:s=720x1280:r=15:d=8 [canvas];"
                "[canvas] drawbox=x=16:y=16:w=688:h=1248:color=0xD4AF37@0.85:t=4 [b1];"
                "[b1] drawbox=x=28:y=28:w=664:h=1224:color=0x8A0303@0.75:t=2 [bg];"
                "[bg] drawbox=x=50:y=80:w=620:h=180:color=0x000000@0.85:t=fill [t1];"
                "[t1] drawbox=x=50:y=80:w=620:h=180:color=0xD4AF37@0.70:t=2 [t2];"
                "[t2] drawbox=x=50:y=300:w=620:h=260:color=0x180202@0.90:t=fill [p1];"
                "[p1] drawbox=x=50:y=300:w=620:h=260:color=0xFF4444@0.90:t=2 [p2];"
                "[p2] drawbox=x=50:y=600:w=620:h=260:color=0x021808@0.90:t=fill [c1];"
                "[c1] drawbox=x=50:y=600:w=620:h=260:color=0x00FF88@0.90:t=2 [c2];"
                "[c2] drawbox=x=50:y=900:w=620:h=300:color=0x000000@0.80:t=fill [m1];"
                "[m1] drawbox=x=50:y=900:w=620:h=300:color=0xD4AF37@0.70:t=2"
            )

            cmd = [
                "ffmpeg", "-y", "-threads", "1",
                "-f", "lavfi", "-i", vf,
                "-i", audio_file,
                "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
                "-pix_fmt", "yuv420p", "-t", "8", "-g", "15",
                "-b:v", "600k", "-maxrate", "800k", "-bufsize", "1200k",
                "-c:a", "aac", "-b:a", "64k", "-ar", "22050",
                "-f", "mpegts", tmp_ts
            ]

            p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            with STATE_LOCK: ACTIVE_PROCESSES.append(p)
            try: p.wait(timeout=16)
            except subprocess.TimeoutExpired: p.kill(); p.wait()
            finally:
                with STATE_LOCK:
                    if p in ACTIVE_PROCESSES: ACTIVE_PROCESSES.remove(p)

            if os.path.exists(tmp_ts) and os.path.getsize(tmp_ts) > 2000:
                os.replace(tmp_ts, final_ts)
                update_hls_playlist()
                logger.info("[VIDEO-PIPELINE] New chunk ready: %s (Pushing to YouTube & Web)", final_ts)
                threading.Thread(target=push_youtube_chunk, args=(final_ts,), daemon=True).start()

        except Exception as exc:
            logger.error("[COMPOSER-ERROR] %s", exc)
        finally:
            if os.path.exists(audio_file):
                try: os.remove(audio_file)
                except OSError: pass
        time.sleep(1)

# ==============================================================================
# 7. WEB PORTAL & HLS SERVER
# ==============================================================================
HTML_PLAYER_PAGE = f"""<!DOCTYPE html>
<html lang="ro">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
  <title>IN MEMORIAM: DR. VANCE STERLING</title>
  <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
  <style>
    body {{
      background: radial-gradient(circle at center, #220303 0%, #060608 100%);
      color: #FFE27A;
      font-family: Georgia, serif;
      text-align: center;
      margin: 0;
      padding: 16px 10px 40px;
    }}
    h1 {{ font-size: 1.25rem; letter-spacing: 2px; margin: 4px 0; }}
    h2 {{ font-size: 0.85rem; color: #D4AF37; font-weight: normal; margin-bottom: 12px; }}
    .player-wrap {{
      width: 100%;
      max-width: 440px;
      aspect-ratio: 9/16;
      margin: 0 auto;
      border: 2px solid #D4AF37;
      border-radius: 8px;
      background: #000;
      overflow: hidden;
      box-shadow: 0 0 25px rgba(212,175,55,0.3);
    }}
    video {{ width: 100%; height: 100%; object-fit: cover; }}
    .card {{
      max-width: 440px;
      margin: 14px auto;
      padding: 12px;
      background: rgba(10, 10, 14, 0.9);
      border-radius: 6px;
    }}
    .pomana {{ border: 1px solid #8A0303; }}
    .cosciug {{ border: 1px solid #00AA55; }}
    .addr {{
      font-family: monospace;
      font-size: 0.76rem;
      color: #00FFAA;
      background: #000;
      padding: 8px;
      border-radius: 4px;
      word-break: break-all;
      margin: 6px 0;
      cursor: pointer;
    }}
    .btn {{
      background: #3A0303;
      color: #FFE27A;
      border: 1px solid #D4AF37;
      padding: 8px 16px;
      border-radius: 20px;
      font-size: 0.8rem;
      cursor: pointer;
      margin-top: 10px;
    }}
  </style>
</head>
<body>
  <div>†  †  †</div>
  <h1>IN MEMORIAM: DR. VANCE STERLING</h1>
  <h2>THE SOVEREIGN HEALER OF DUBAI // ETERNAL FUNERAL VIGIL</h2>

  <div class="player-wrap">
    <video id="v" controls autoplay muted playsinline></video>
  </div>

  <button class="btn" onclick="candle()">🕯️ Aprinde o Candelă de Veci</button>
  <div id="cCount" style="font-size: 0.75rem; color: #888; margin-top: 5px;">486 lumânări aprinse</div>

  <div class="card pomana">
    <div style="color: #FF6666; font-size: 0.85rem; font-weight: bold;">🥀 POMANA UROLOGULUI PLECAT (SOLANA)</div>
    <div class="addr" id="a1" onclick="cp('a1','h1')">{VAULT_POMANA_STR}</div>
    <div id="h1" style="font-size: 0.65rem; color: #777;">Apasă pentru a copia adresa de pomană</div>
  </div>

  <div class="card cosciug">
    <div style="color: #55FFAA; font-size: 0.85rem; font-weight: bold;">⚰️ ÎNTREȚINEREA COSCIUGULUI (FOND ENTITATE)</div>
    <div class="addr" id="a2" onclick="cp('a2','h2')">{VAULT_COSCIUG_STR}</div>
    <div id="h2" style="font-size: 0.65rem; color: #777;">Apasă pentru a copia fondul de hosting</div>
  </div>

  <script>
    var vid = document.getElementById('v');
    function start() {{
      if (Hls.isSupported()) {{
        var hls = new Hls({{ liveDurationInfinity: true, enableWorker: true }});
        hls.loadSource('/live.m3u8');
        hls.attachMedia(vid);
        hls.on(Hls.Events.MANIFEST_PARSED, function() {{ vid.play(); }});
      }} else if (vid.canPlayType('application/vnd.apple.mpegurl')) {{
        vid.src = '/live.m3u8';
        vid.addEventListener('loadedmetadata', function() {{ vid.play(); }});
      }}
    }}
    setTimeout(start, 1500);

    function cp(id, h) {{
      navigator.clipboard.writeText(document.getElementById(id).innerText);
      document.getElementById(h).innerText = '✓ Adresă copiată!';
      document.getElementById(h).style.color = '#00FFAA';
      setTimeout(function() {{
        document.getElementById(h).innerText = 'Apasă pentru a copia';
        document.getElementById(h).style.color = '#777';
      }}, 2500);
    }}

    var c = 486;
    function candle() {{
      c += 1;
      document.getElementById('cCount').innerText = c + ' lumânări aprinse';
      alert('🕯️ Candela a fost aprinsă.');
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
                with open(p, "rb") as f: self.wfile.write(f.read())
            else:
                self.send_response(404); self.end_headers()
            return
        if self.path.endswith(".ts"):
            p = os.path.join(PUBLIC_HLS_DIR, os.path.basename(self.path))
            if os.path.exists(p):
                self.send_response(200)
                self.send_header("Content-Type", "video/MP2T")
                self.end_headers()
                with open(p, "rb") as f: self.wfile.write(f.read())
            else:
                self.send_response(404); self.end_headers()
            return
        self.send_response(200); self.end_headers(); self.wfile.write(b"OK")
    def log_message(self, *args): pass

def run_server():
    ThreadingHTTPServer(("0.0.0.0", 7860), AutonomousStreamServer).serve_forever()

if __name__ == "__main__":
    init_db()
    logger.info("Initializing Entity Runtime: %s", ENTITY_DESIGNATION)

    threading.Thread(target=run_server, daemon=True).start()
    threading.Thread(target=dual_vault_scanner, daemon=True).start()

    composer_loop()
