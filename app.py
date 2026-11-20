import asyncio
import io
import json
import math
import os
import random
import shutil
import subprocess
import uuid
from pathlib import Path
from urllib.parse import quote

import edge_tts
import requests
import streamlit as st
from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------
# CONFIGURAÇÃO BASE
# ---------------------------------------------------------
st.set_page_config(
    page_title="MiniDrama Studio — Criador de Micro-Séries IA",
    page_icon="🎬",
    layout="wide",
)

WORK_DIR = Path("renders_tmp")
WORK_DIR.mkdir(exist_ok=True)

VOICES = {
    "Português (PT) — Raquel (Feminina)": "pt-PT-RaquelNeural",
    "Português (PT) — Duarte (Masculina)": "pt-PT-DuarteNeural",
    "Português (BR) — Francisca (Feminina)": "pt-BR-FranciscaNeural",
    "Português (BR) — Antonio (Masculina)": "pt-BR-AntonioNeural",
    "Inglês (US) — Jenny (Feminina)": "en-US-JennyNeural",
    "Inglês (US) — Guy (Masculina)": "en-US-GuyNeural",
}

IMAGE_PROVIDERS = [
    "Pollinations.ai — Flux (Grátis, sem chave)",
    "Hugging Face — FLUX.1-schnell (Grátis com token)",
]

DEMO_SCENES = [
    {
        "scene_index": 1,
        "dialogue": "Ele achou que eu não tinha visto o envelope no cofre.",
        "visual_prompt": "Cinematic vertical 9:16 thriller shot, young woman in dark tailored blazer with hair tied back looking intensely at an open hidden wall safe in a dim luxury office, dramatic rim lighting, photorealistic, 35mm film",
    },
    {
        "scene_index": 2,
        "dialogue": "Durante três anos, assinou contratos em meu nome e ficou com os lucros.",
        "visual_prompt": "Cinematic vertical 9:16 close-up of hands of a young woman in a dark blazer flipping through signed corporate financial contracts under a warm desk lamp, moody noir shadows, photorealistic, 35mm film",
    },
    {
        "scene_index": 3,
        "dialogue": "Hoje, às nove da manhã, a auditoria vai entrar pela porta principal.",
        "visual_prompt": "Cinematic vertical 9:16 shot inside a modern glass corporate skyscraper lobby, silhouettes of serious investigators in dark suits walking in decisively through revolving doors, dramatic morning backlight, photorealistic",
    },
    {
        "scene_index": 4,
        "dialogue": "E o único nome que falta na carta de demissão... é o dele.",
        "visual_prompt": "Cinematic vertical 9:16 thriller ending shot, young woman in dark tailored blazer with hair tied back smiling subtly inside a sleek metal elevator mirror holding a red folder, moody blue lighting, photorealistic, 35mm film",
    },
]


# ---------------------------------------------------------
# UTILITÁRIOS DE FONTES (WINDOWS + LINUX / STREAMLIT CLOUD)
# ---------------------------------------------------------
def find_linux_ttf() -> str | None:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return path
    return None


def load_pil_font(size: int):
    for name in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "arial.ttf",
    ]:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


# ---------------------------------------------------------
# GERAÇÃO DE GUIÃO (GEMINI)
# ---------------------------------------------------------
def generate_script_gemini(api_key: str, premise: str, genre: str, lang: str, num_scenes: int) -> list[dict]:
    from google import genai
    from google.genai import types

    client = genai.Client(
        api_key=api_key.strip(),
        http_options=types.HttpOptions(api_version="v1beta"),
    )
    prompt = f"""
Cria um guião viral para um mini-drama vertical (TikTok/Reels) no género "{genre}", em {lang}, com exatamente {num_scenes} cenas.
Premissa: {premise}

Regras obrigatórias:
- Cena 1 tem de ter um gancho forte nos primeiros 2 segundos.
- Última cena tem de terminar num cliffhanger (suspense para o episódio seguinte).
- Cada fala ("dialogue") deve ter entre 10 e 22 palavras, direta e emocional.
- Cada "visual_prompt" deve ser em INGLÊS, fotorealista, estilo cinema 35mm vertical 9:16, SEM texto escrito na imagem.
- Para consistência visual, repete exatamente a mesma descrição física e roupa da personagem principal em todas as cenas onde ela aparece.

Devolve APENAS um JSON válido com uma lista de objetos neste formato:
[
  {{
    "scene_index": 1,
    "dialogue": "Texto falado da cena",
    "visual_prompt": "Cinematic vertical 9:16 photorealistic prompt in English"
  }}
]
"""
    resp = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    raw = (resp.text or "").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    return json.loads(raw)


# ---------------------------------------------------------
# GERAÇÃO GRATUITA DE IMAGENS IA (TESTES)
# ---------------------------------------------------------
def normalize_image_bytes(raw_bytes: bytes) -> bytes:
    img = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def generate_image_pollinations(prompt: str, seed: int | None = None) -> bytes:
    clean_prompt = " ".join(prompt.split())[:420]
    seed_val = seed if seed is not None else random.randint(1, 999999)
    url = (
        f"https://image.pollinations.ai/prompt/{quote(clean_prompt)}"
        f"?width=720&height=1280&nologo=true&model=flux&seed={seed_val}"
    )
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    resp = requests.get(url, headers=headers, timeout=90)
    if resp.status_code != 200:
        raise RuntimeError(
            f"Pollinations respondeu com código {resp.status_code}. "
            "Tenta novamente dentro de segundos ou muda para Hugging Face na barra lateral."
        )
    if "image" not in resp.headers.get("Content-Type", ""):
        raise RuntimeError("O serviço gratuito não devolveu uma imagem válida (possível limite temporário).")
    return normalize_image_bytes(resp.content)


def generate_image_huggingface(prompt: str, hf_token: str) -> bytes:
    if not hf_token.strip():
        raise RuntimeError("Cola o teu token gratuito do Hugging Face na barra lateral.")
    url = "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell"
    headers = {
        "Authorization": f"Bearer {hf_token.strip()}",
        "Accept": "image/jpeg",
    }
    payload = {
        "inputs": prompt,
        "parameters": {"width": 768, "height": 1344},
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=90)
    if resp.status_code == 503:
        raise RuntimeError("O modelo gratuito no Hugging Face está a acordar. Aguarda 15 segundos e tenta novamente.")
    if resp.status_code != 200:
        raise RuntimeError(f"Erro Hugging Face ({resp.status_code}): {resp.text[:250]}")
    return normalize_image_bytes(resp.content)


def generate_scene_image(prompt: str, provider: str, hf_token: str) -> bytes:
    if provider.startswith("Pollinations"):
        return generate_image_pollinations(prompt)
    return generate_image_huggingface(prompt, hf_token)


def create_placeholder_card(path: Path, scene_num: int, prompt_text: str):
    img = Image.new("RGB", (1080, 1920), (16, 18, 28))
    draw = ImageDraw.Draw(img)

    for y in range(1920):
        tone = int(16 + (y / 1920) * 28)
        draw.line([(0, y), (1080, y)], fill=(tone, tone + 2, tone + 16))

    draw.rectangle([70, 120, 1010, 1800], outline=(90, 105, 150), width=3)

    font_title = load_pil_font(72)
    font_body = load_pil_font(34)

    draw.text((120, 260), f"CENA {scene_num:02d}", fill=(240, 200, 110), font=font_title)

    words = prompt_text.split()
    lines, current = [], []
    for w in words:
        current.append(w)
        if len(" ".join(current)) > 36:
            lines.append(" ".join(current))
            current = []
    if current:
        lines.append(" ".join(current))

    y_pos = 420
    for line in lines[:10]:
        draw.text((120, y_pos), line, fill=(210, 215, 230), font=font_body)
        y_pos += 52

    img.save(path, format="JPEG", quality=92)


# ---------------------------------------------------------
# MOTOR DE ÁUDIO E VÍDEO (EDGE-TTS + FFMPEG)
# ---------------------------------------------------------
def run_cmd(cmd: list[str], cwd: Path):
    res = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Erro no comando {' '.join(cmd[:3])}:\n{res.stderr[-600:]}")
    return res


def get_duration(media_path: Path) -> float:
    res = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(media_path),
        ],
        capture_output=True,
        text=True,
    )
    return float(res.stdout.strip())


def format_srt_time(ms: float) -> str:
    total_ms = max(0, int(ms))
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    seconds, millis = divmod(rem, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


async def generate_tts(text: str, voice: str, out_mp3: Path, words_per_chunk: int = 4):
    communicate = edge_tts.Communicate(text=text, voice=voice)
    word_events = []

    with open(out_mp3, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start_ms = chunk["offset"] / 10_000
                end_ms = (chunk["offset"] + chunk["duration"]) / 10_000
                word_events.append((start_ms, end_ms, chunk["text"]))

    chunks = []
    for i in range(0, len(word_events), words_per_chunk):
        grp = word_events[i : i + words_per_chunk]
        chunks.append((grp[0][0], grp[-1][1], " ".join(w[2] for w in grp)))
    return chunks


def render_episode(
    scenes: list[dict],
    ai_images: dict[int, bytes],
    uploaded_images: dict,
    voice_id: str,
    watermark: bool,
    progress_bar,
) -> Path:
    job_id = uuid.uuid4().hex[:10]
    job_dir = WORK_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    scene_videos = []
    srt_entries = []
    srt_idx = 1
    offset_ms = 0.0
    total = len(scenes)

    for idx, scene in enumerate(scenes):
        prefix = f"scene_{idx + 1:02d}"
        img_path = job_dir / f"{prefix}.jpg"
        audio_path = job_dir / f"{prefix}.mp3"
        clip_vid = job_dir / f"{prefix}_vid.mp4"
        merged_vid = job_dir / f"{prefix}_merged.mp4"

        dialogue = scene.get("dialogue", "").strip()
        visual_prompt = scene.get("visual_prompt", "")

        # Prioridade: 1) Upload manual -> 2) Imagem IA gerada -> 3) Cartão temporário
        if idx in uploaded_images and uploaded_images[idx] is not None:
            img = Image.open(uploaded_images[idx]).convert("RGB")
            img.save(img_path, format="JPEG", quality=92)
        elif idx in ai_images and ai_images[idx]:
            img_path.write_bytes(ai_images[idx])
        else:
            create_placeholder_card(img_path, idx + 1, visual_prompt)

        # Voz neural + tempos de legenda
        timings = asyncio.run(generate_tts(dialogue, voice_id, audio_path))
        audio_dur = get_duration(audio_path)
        scene_dur = audio_dur + 0.35

        if not timings:
            words = dialogue.split()
            parts = [" ".join(words[i : i + 4]) for i in range(0, len(words), 4)]
            slot = (audio_dur * 1000) / max(1, len(parts))
            timings = [(i * slot, (i + 1) * slot, p) for i, p in enumerate(parts)]

        for s_ms, e_ms, txt in timings:
            srt_entries.append(
                f"{srt_idx}\n"
                f"{format_srt_time(offset_ms + s_ms)} --> {format_srt_time(offset_ms + e_ms)}\n"
                f"{txt.upper()}\n"
            )
            srt_idx += 1

        # Movimento suave de câmara (Zoompan FFmpeg)
        fps = 30
        frames = max(1, math.ceil(scene_dur * fps))
        vf = (
            "scale=1440:2560:force_original_aspect_ratio=increase,"
            "crop=1440:2560,"
            f"zoompan=z='min(zoom+0.0008,1.12)':"
            "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={frames}:s=1080x1920:fps={fps},"
            "format=yuv420p"
        )
        run_cmd(
            [
                "ffmpeg", "-y", "-loop", "1", "-i", img_path.name,
                "-vf", vf, "-t", f"{scene_dur:.3f}",
                "-c:v", "libx264", "-preset", "veryfast", "-an",
                clip_vid.name,
            ],
            cwd=job_dir,
        )

        # Juntar vídeo e voz da cena
        run_cmd(
            [
                "ffmpeg", "-y",
                "-i", clip_vid.name, "-i", audio_path.name,
                "-af", "apad=pad_dur=0.35",
                "-c:v", "copy",
                "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
                "-t", f"{scene_dur:.3f}",
                merged_vid.name,
            ],
            cwd=job_dir,
        )

        actual_dur = get_duration(merged_vid)
        offset_ms += actual_dur * 1000
        scene_videos.append(merged_vid)
        progress_bar.progress(int(((idx + 1) / total) * 75), text=f"Cena {idx + 1}/{total} montada...")

    (job_dir / "concat.txt").write_text(
        "\n".join(f"file '{v.name}'" for v in scene_videos), encoding="utf-8"
    )
    (job_dir / "captions.srt").write_text("\n".join(srt_entries), encoding="utf-8")

    run_cmd(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "concat.txt", "-c", "copy", "stitched.mp4"],
        cwd=job_dir,
    )
    progress_bar.progress(88, text="A aplicar legendas e acabamento final...")

    sub_style = (
        "FontName=DejaVu Sans,FontSize=15,Bold=1,"
        "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
        "Outline=2,Shadow=1,Alignment=2,MarginV=85"
    )
    filters = [f"subtitles=captions.srt:force_style='{sub_style}'"]

    if watermark:
        font_opt = ""
        if os.name != "nt":
            linux_ttf = find_linux_ttf()
            if linux_ttf:
                font_opt = f"fontfile={linux_ttf}:"
        filters.append(
            f"drawtext={font_opt}text='MiniDrama Studio':fontcolor=white@0.45:fontsize=28:x=w-tw-36:y=48"
        )

    final_mp4 = job_dir / "episodio_final.mp4"
    run_cmd(
        [
            "ffmpeg", "-y", "-i", "stitched.mp4",
            "-vf", ",".join(filters),
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-c:a", "copy", "-movflags", "+faststart",
            final_mp4.name,
        ],
        cwd=job_dir,
    )
    progress_bar.progress(100, text="Episódio concluído!")
    return final_mp4


# ---------------------------------------------------------
# INTERFACE WEB
# ---------------------------------------------------------
if "scenes" not in st.session_state:
    st.session_state.scenes = []
if "scene_images" not in st.session_state:
    st.session_state.scene_images = {}
if "last_video" not in st.session_state:
    st.session_state.last_video = None
if "script_ver" not in st.session_state:
    st.session_state.script_ver = 0

st.title("🎬 MiniDrama Studio — Protótipo v2")
st.caption("Guião IA + Imagens IA gratuitas (9:16) + Voz neural e legendas sincronizadas.")

if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
    st.error("FFmpeg não encontrado no sistema. Confirma se o ficheiro packages.txt contém 'ffmpeg'.")
    st.stop()

with st.sidebar:
    st.header("Configurações")
    gemini_key = st.text_input("Chave API Google Gemini (guião)", type="password")
    voice_label = st.selectbox("Voz do narrador", list(VOICES.keys()))
    watermark = st.checkbox("Incluir marca d'água (plano grátis)", value=True)

    st.divider()
    st.subheader("Motor de Imagens (Testes)")
    img_provider = st.selectbox("Serviço gratuito", IMAGE_PROVIDERS)
    hf_token = ""
    if "Hugging Face" in img_provider:
        hf_token = st.text_input("Token Hugging Face (gratuito)", type="password")
        st.caption("Cria um token grátis (Read) em huggingface.co/settings/tokens.")

# PASSO 1: GERAR GUIÃO
st.subheader("1. Ideia do Episódio")
col1, col2, col3 = st.columns([3, 1, 1])
with col1:
    premise = st.text_input(
        "Premissa do mini-drama",
        value="Uma estagiária descobre que o diretor financeiro está a desviar fundos da empresa.",
    )
with col2:
    genre = st.selectbox("Género", ["Suspense Corporativo", "Vingança", "Drama Familiar", "Mistério"])
with col3:
    num_scenes = st.slider("N.º de cenas", 3, 6, 4)

b1, b2 = st.columns([1, 1])
with b1:
    if st.button("✨ Gerar Guião com IA (Gemini)", type="primary", use_container_width=True):
        if not gemini_key:
            st.warning("Cola a tua chave Gemini na barra lateral ou usa o guião de demonstração.")
        else:
            with st.spinner("A escrever o guião estruturado..."):
                try:
                    lang = "Português" if "Português" in voice_label else "Inglês"
                    st.session_state.scenes = generate_script_gemini(gemini_key, premise, genre, lang, num_scenes)
                    st.session_state.scene_images = {}
                    st.session_state.last_video = None
                    st.session_state.script_ver += 1
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao chamar a API Gemini: {e}")
with b2:
    if st.button("⚡ Carregar Guião de Demonstração", use_container_width=True):
        st.session_state.scenes = [dict(s) for s in DEMO_SCENES]
        st.session_state.scene_images = {}
        st.session_state.last_video = None
        st.session_state.script_ver += 1
        st.rerun()

# PASSO 2: STORYBOARD + IMAGENS IA GRATUITAS
if st.session_state.scenes:
    st.divider()
    st.subheader("2. Storyboard e Imagens IA (9:16)")

    if st.button("🎨 Gerar Imagens IA para Todas as Cenas (Grátis)", type="primary"):
        img_bar = st.progress(0, text="A gerar imagens...")
        total_s = len(st.session_state.scenes)
        for i, scene in enumerate(st.session_state.scenes):
            img_bar.progress(int((i / total_s) * 100), text=f"A gerar imagem da Cena {i + 1}/{total_s}...")
            try:
                st.session_state.scene_images[i] = generate_scene_image(
                    scene.get("visual_prompt", ""), img_provider, hf_token
                )
            except Exception as e:
                st.error(f"Cena {i + 1}: {e}")
                break
        img_bar.progress(100, text="Imagens geradas!")

    uploaded_images = {}
    ver = st.session_state.script_ver
    for i, scene in enumerate(st.session_state.scenes):
        with st.expander(f"Cena {i + 1}", expanded=True):
            c_txt, c_prev = st.columns([2, 1])
            with c_txt:
                scene["dialogue"] = st.text_area(
                    "Fala / Narração",
                    value=scene.get("dialogue", ""),
                    key=f"diag_{ver}_{i}",
                    height=75,
                )
                scene["visual_prompt"] = st.text_area(
                    "Prompt visual (em inglês)",
                    value=scene.get("visual_prompt", ""),
                    key=f"vis_{ver}_{i}",
                    height=75,
                )
                if st.button(f"🔄 Gerar / Regenerar só a Cena {i + 1}", key=f"regen_{ver}_{i}"):
                    with st.spinner(f"A gerar imagem da Cena {i + 1}..."):
                        try:
                            st.session_state.scene_images[i] = generate_scene_image(
                                scene["visual_prompt"], img_provider, hf_token
                            )
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro na Cena {i + 1}: {e}")

            with c_prev:
                if i in st.session_state.scene_images:
                    st.image(st.session_state.scene_images[i], caption=f"Cena {i + 1} (IA)", width=200)
                else:
                    st.info("Ainda sem imagem gerada.")
                uploaded_images[i] = st.file_uploader(
                    "Ou substituir manualmente (JPG/PNG)",
                    type=["jpg", "jpeg", "png"],
                    key=f"img_{ver}_{i}",
                )

    # PASSO 3: RENDERIZAR VÍDEO
    st.divider()
    st.subheader("3. Produzir Episódio Vertical (9:16)")
    if st.button("🎥 Gerar Vídeo Completo (Modo Rápido)", type="primary"):
        bar = st.progress(5, text="A iniciar motor de renderização...")
        try:
            out_path = render_episode(
                scenes=st.session_state.scenes,
                ai_images=st.session_state.scene_images,
                uploaded_images=uploaded_images,
                voice_id=VOICES[voice_label],
                watermark=watermark,
                progress_bar=bar,
            )
            st.session_state.last_video = out_path
        except Exception as e:
            st.error(f"Ocorreu um erro na renderização: {e}")

if st.session_state.last_video and Path(st.session_state.last_video).exists():
    st.divider()
    v_col, d_col = st.columns([1, 2])
    with v_col:
        st.video(str(st.session_state.last_video))
    with d_col:
        st.success("Vídeo pronto a publicar em formato 1080×1920!")
        with open(st.session_state.last_video, "rb") as f:
            st.download_button(
                "⬇️ Descarregar MP4",
                data=f.read(),
                file_name="minidrama_episodio.mp4",
                mime="video/mp4",
                type="primary",
            )
