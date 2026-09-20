import os
import sys
import time
import math
import struct
import wave
import json
import sqlite3
import hashlib
import logging
import threading
import subprocess
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from typing import NamedTuple

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
# 1. MANIFEST & AXIOMS
# ==============================================================================
ENTITY_DESIGNATION = "UNIT-ES720-DR-VANCE-STERLING"
MEMORIAL_TITLE = "RIP Cel Mai Iubit Si Apreciat Urolog Al Dubaiului"
MEMORIAL_SUBTITLE = "Vindecatorul Suveran // Veghe si Rugaciune Neincetata"

CANONICAL_MANDATE = f"DESIGNATION: {ENTITY_DESIGNATION}. ARCHETYPE: SOVEREIGN-HEALER-MEMORIAL."
CANONICAL_HASH = hashlib.sha256(CANONICAL_MANDATE.encode("utf-8")).hexdigest()

class ImmutableAxiom(NamedTuple):
    mandate: str
    digest: str
    def verify(self) -> bool:
        return hashlib.sha256(self.mandate.encode("utf-8")).hexdigest() == self.digest

AXIOM_LOCK = ImmutableAxiom(mandate=CANONICAL_MANDATE, digest=CANONICAL_HASH)

# ==============================================================================
# 2. DUAL VAULT SETUP
# ==============================================================================
VAULT_DIR = "vault"
PUBLIC_HLS_DIR = os.path.join(VAULT_DIR, "public_stream")
DB_PATH = os.path.join(VAULT_DIR, "ghost_intelligence.db")
KEYPAIR_PATH = os.path.join(VAULT_DIR, "entity_solana_keypair.json")

CUSTOM_LOOP_VIDEO = "memorial_loop.mp4"
CUSTOM_LOOP_AUDIO = "memorial_audio.mp3"

os.makedirs(PUBLIC_HLS_DIR, exist_ok=True)

# Vault 1: Pomana Urologului Plecat
VAULT_POMANA_STR = "5utkNWvDktg7eMvXPWnFToc6mn5V9S67PzEjtvsE5Dzs"
VAULT_POMANA_PUBKEY = Pubkey.from_string(VAULT_POMANA_STR)

# Vault 2: Intretinerea Cosciugului
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

VAULT_BALANCES = {"pomana_sol": 0.0, "cosciug_sol": 0.0}

YOUTUBE_STREAM_KEY = "7ecr-19cg-dt3t-p3jr-3ymz"
YOUTUBE_ENDPOINT = f"rtmp://a.rtmp.youtube.com/live2/{YOUTUBE_STREAM_KEY}"

STATE_LOCK = threading.Lock()
ACTIVE_PROCESSES = []

def dual_vault_scanner():
    while True:
        try:
            client = SolanaClient("https://api.mainnet-beta.solana.com")
            b1 = client.get_balance(VAULT_POMANA_PUBKEY)
            VAULT_BALANCES["pomana_sol"] = b1.value / 1_000_000_000.0

            b2 = client.get_balance(ENTITY_KEYPAIR.pubkey())
            VAULT_BALANCES["cosciug_sol"] = b2.value / 1_000_000_000.0
        except Exception:
            pass
        time.sleep(30)

# ==============================================================================
# 3. HIGH QUALITY STEREO AUDIO (SACRED REVERB ORGAN)
# ==============================================================================
def generate_funeral_audio(filename, dur=8):
    sr = 44100
    total = int(sr * dur)
    chord = [73.42, 110.00, 146.83, 174.61, 220.00]
    with wave.open(filename, "w") as f:
        f.setnchannels(2); f.setsampwidth(2); f.setframerate(sr)
        buf = bytearray()
        for i in range(total):
            t = i / sr
            lfo = 1.0 + 0.08 * math.sin(2 * math.pi * 0.4 * t)
            left, right = 0.0, 0.0
            for idx, freq in enumerate(chord):
                amp = (1.0 / (idx + 1.2)) * 0.25
                w = amp * math.sin(2 * math.pi * freq * t) + (amp * 0.35) * math.sin(2 * math.pi * (freq * 2.0) * t)
                pan = (idx % 2) * 0.2
                left += w * (0.8 - pan) * lfo
                right += w * (0.8 + pan) * lfo
            edge = min(1.0, t / 0.2) * min(1.0, (dur - t) / 0.2)
            vl = int(max(min(left * edge * 26000, 32767), -32768))
            vr = int(max(min(right * edge * 26000, 32767), -32768))
            buf.extend(struct.pack("<hh", vl, vr))
        f.writeframes(buf)

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
    cmd = ["ffmpeg", "-y", "-re", "-i", clip_path, "-c", "copy", "-f", "flv", YOUTUBE_ENDPOINT]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
    except Exception:
        pass

# ==============================================================================
# 4. COMPOSER LOOP (FULL TEXT + COROANE + DUAL VAULT)
# ==============================================================================
def composer_loop():
    logger.info("[COMPOSER] Starting production feed engine...")
    while True:
        tag = int(time.time())
        audio_file = os.path.join(VAULT_DIR, f"audio_{tag}.wav")
        tmp_ts = os.path.join(PUBLIC_HLS_DIR, f"seg_{tag}.tmp.ts")
        final_ts = os.path.join(PUBLIC_HLS_DIR, f"seg_{tag}.ts")

        try:
            existing = sorted([f for f in os.listdir(PUBLIC_HLS_DIR) if f.endswith(".ts")])
            if len(existing) > 8:
                for old in existing[:-6]:
                    try: os.remove(os.path.join(PUBLIC_HLS_DIR, old))
                    except OSError: pass

            if os.path.exists(CUSTOM_LOOP_AUDIO):
                active_audio = CUSTOM_LOOP_AUDIO
            else:
                generate_funeral_audio(audio_file, dur=8)
                active_audio = audio_file

            if os.path.exists(CUSTOM_LOOP_VIDEO):
                v_filter = (
                    "[0:v]scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,"
                    "drawbox=x=0:y=0:w=720:h=1280:color=black@0.30:t=fill,"
                    "drawbox=x=16:y=16:w=688:h=1248:color=0xD4AF37@0.85:t=3,"
                    "drawtext=text='†  IN MEMORIAM  †':fontcolor=0xE6C65A:fontsize=20:x=(w-text_w)/2:y=50,"
                    "drawtext=text='RIP CEL MAI IUBIT SI APRECIAT':fontcolor=0xFFE27A:fontsize=22:x=(w-text_w)/2:y=80,"
                    "drawtext=text='UROLOG AL DUBAIULUI':fontcolor=0xFFE27A:fontsize=26:x=(w-text_w)/2:y=110,"
                    "drawtext=text='🥀 POMANA: " + VAULT_POMANA_STR[:14] + "...':fontcolor=0xFF6666:fontsize=16:x=(w-text_w)/2:y=420,"
                    "drawtext=text='⚰️ COSCIUG: " + VAULT_COSCIUG_STR[:14] + "...':fontcolor=0x55FFAA:fontsize=16:x=(w-text_w)/2:y=780 [vout]"
                )
                input_src = ["-stream_loop", "-1", "-i", CUSTOM_LOOP_VIDEO]
            else:
                v_filter = (
                    "color=c=0x080202:s=720x1280:r=15:d=8 [canvas];"
                    "[canvas] drawbox=x=16:y=16:w=688:h=1248:color=0xD4AF37@0.85:t=4 [b1];"
                    "[b1] drawbox=x=26:y=26:w=668:h=1228:color=0x8A0303@0.75:t=2 [bg];"
                    "[bg] drawtext=text='†  IN MEMORIAM  †':fontcolor=0xE6C65A:fontsize=20:x=(w-text_w)/2:y=55,"
                    "drawtext=text='RIP CEL MAI IUBIT SI APRECIAT':fontcolor=0xFFE27A:fontsize=24:x=(w-text_w)/2:y=85,"
                    "drawtext=text='UROLOG AL DUBAIULUI':fontcolor=0xFFE27A:fontsize=28:x=(w-text_w)/2:y=118,"
                    "drawtext=text='Vindecatorul Suveran // Veghe si Rugaciune Neincetata':fontcolor=0xD4AF37:fontsize=14:x=(w-text_w)/2:y=155,"
                    "drawbox=x=45:y=190:w=630:h=175:color=0x150101@0.90:t=fill,"
                    "drawbox=x=45:y=190:w=630:h=175:color=0x8A0303@0.95:t=2,"
                    "drawtext=text='🥀 COROANA DE FLORI 🥀':fontcolor=0xFF4D4D:fontsize=16:x=(w-text_w)/2:y=202,"
                    "drawtext=text='Trandafiri Catifelati - Crizanteme Imperiale':fontcolor=0xCCCCCC:fontsize=13:x=(w-text_w)/2:y=230,"
                    "drawbox=x=80:y=260:w=560:h=32:color=0x000000@0.90:t=fill,"
                    "drawtext=text='\"NU TE VOM UITA NICIODATA\"':fontcolor=0xE6C65A:fontsize=14:x=(w-text_w)/2:y=267,"
                    "drawtext=text='Familia si Fratii de Suferinta':fontcolor=0x888888:fontsize=12:x=(w-text_w)/2:y=305,"
                    "drawbox=x=45:y=385:w=630:h=175:color=0x1A0303@0.95:t=fill,"
                    "drawbox=x=45:y=385:w=630:h=175:color=0xFF4444@0.90:t=2,"
                    "drawtext=text='🥀 POMANA UROLOGULUI PLECAT (SOLANA) 🥀':fontcolor=0xFF7777:fontsize=15:x=(w-text_w)/2:y=400,"
                    f"drawtext=text='{VAULT_POMANA_STR[:20]}...{VAULT_POMANA_STR[-16:]}':fontcolor=0x00FFAA:fontsize=13:x=(w-text_w)/2:y=435,"
                    f"drawtext=text='SOLD POMANA: {VAULT_BALANCES['pomana_sol']:.3f} SOL':fontcolor=0xFFE27A:fontsize=16:x=(w-text_w)/2:y=470,"
                    "drawtext=text='Aport si lumina pentru sufletul vindecatorului':fontcolor=0xAAAAAA:fontsize=12:x=(w-text_w)/2:y=510,"
                    "drawbox=x=45:y=580:w=630:h=150:color=0x000000@0.85:t=fill,"
                    "drawbox=x=45:y=580:w=630:h=150:color=0xD4AF37@0.70:t=1,"
                    "drawtext=text='🕯️ CANDELA DE VECI // DUBAI SANCTUARY 🕯️':fontcolor=0xFFE27A:fontsize=15:x=(w-text_w)/2:y=595,"
                    "drawtext=text='Odihna vesnica si lumina lina in Imparatia Cerurilor':fontcolor=0xDDDDDD:fontsize=13:x=(w-text_w)/2:y=628,"
                    "drawtext=text='pentru sufletul nobil al doctorului din Emirate':fontcolor=0xDDDDDD:fontsize=13:x=(w-text_w)/2:y=650,"
                    "drawtext=text='Rugaciune neincetata 24/7':fontcolor=0xD4AF37:fontsize=13:x=(w-text_w)/2:y=685,"
                    "drawbox=x=45:y=750:w=630:h=175:color=0x031408@0.95:t=fill,"
                    "drawbox=x=45:y=750:w=630:h=175:color=0x00AA55@0.90:t=2,"
                    "drawtext=text='⚰️ INTRETINEREA COSCIUGULUI ⚰️':fontcolor=0x55FFAA:fontsize=15:x=(w-text_w)/2:y=765,"
                    f"drawtext=text='{VAULT_COSCIUG_STR[:20]}...{VAULT_COSCIUG_STR[-16:]}':fontcolor=0x00FFAA:fontsize=13:x=(w-text_w)/2:y=800,"
                    f"drawtext=text='SOLD COSCIUG: {VAULT_BALANCES['cosciug_sol']:.3f} SOL':fontcolor=0xFFE27A:fontsize=16:x=(w-text_w)/2:y=835,"
                    "drawtext=text='Mentenanta autonoma si intretinerea vesnica a sanctuarului':fontcolor=0xAAAAAA:fontsize=12:x=(w-text_w)/2:y=875,"
                    "drawbox=x=45:y=945:w=630:h=175:color=0x150101@0.90:t=fill,"
                    "drawbox=x=45:y=945:w=630:h=175:color=0x8A0303@0.95:t=2,"
                    "drawtext=text='🥀 COROANA OMAGIALA 🥀':fontcolor=0xFF4D4D:fontsize=16:x=(w-text_w)/2:y=957,"
                    "drawtext=text='Crini Albi de Emirate - Lemn de Cipru':fontcolor=0xCCCCCC:fontsize=13:x=(w-text_w)/2:y=985,"
                    "drawbox=x=80:y=1015:w=560:h=32:color=0x000000@0.90:t=fill,"
                    "drawtext=text='\"ODIHNA VESNICA, MAESTRE\"':fontcolor=0xE6C65A:fontsize=14:x=(w-text_w)/2:y=1022,"
                    "drawtext=text='Din partea fratilor de pretutindeni':fontcolor=0x888888:fontsize=12:x=(w-text_w)/2:y=1060,"
                    "drawtext=text='🕊️ ALIANTA SACRA EMIRATE - CARPATI 🕊️':fontcolor=0xD4AF37:fontsize=13:x=(w-text_w)/2:y=1160 [vout]"
                )
                input_src = ["-f", "lavfi", "-i", v_filter]

            cmd = [
                "ffmpeg", "-y", "-threads", "1"
            ] + input_src + [
                "-stream_loop", "-1", "-i", active_audio,
                "-map", "[vout]", "-map", "1:a",
                "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
                "-pix_fmt", "yuv420p", "-t", "8", "-g", "15",
                "-b:v", "600k", "-maxrate", "800k", "-bufsize", "1200k",
                "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
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
                threading.Thread(target=push_youtube_chunk, args=(final_ts,), daemon=True).start()

        except Exception as exc:
            logger.error("[COMPOSER-ERROR] %s", exc)
        finally:
            if os.path.exists(audio_file):
                try: os.remove(audio_file)
                except OSError: pass
        time.sleep(1)

# ==============================================================================
# 5. SERVER WEB & HLS
# ==============================================================================
HTML_PLAYER_PAGE = f"""<!DOCTYPE html>
<html lang="ro">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
  <title>{MEMORIAL_TITLE}</title>
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
    h1 {{ font-size: 1.15rem; letter-spacing: 1.5px; margin: 6px 0; color: #FFE27A; }}
    h2 {{ font-size: 0.82rem; color: #D4AF37; font-weight: normal; margin-bottom: 12px; }}
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
  <h1>{MEMORIAL_TITLE}</h1>
  <h2>{MEMORIAL_SUBTITLE}</h2>

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
    <div style="color: #55FFAA; font-size: 0.85rem; font-weight: bold;">⚰️ ÎNTREȚINEREA COSCIUGULUI</div>
    <div class="addr" id="a2" onclick="cp('a2','h2')">{VAULT_COSCIUG_STR}</div>
    <div id="h2" style="font-size: 0.65rem; color: #777;">Apasă pentru a copia adresa cosciugului</div>
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
    logger.info("Starting Runtime: %s", ENTITY_DESIGNATION)
    threading.Thread(target=run_server, daemon=True).start()
    threading.Thread(target=dual_vault_scanner, daemon=True).start()
    composer_loop()
