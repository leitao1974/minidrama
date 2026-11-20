import asyncio
import json
import math
import os
import shutil
import subprocess
import uuid
from pathlib import Path

import edge_tts
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

DEMO_SCENES = [
    {
        "scene_index": 1,
        "dialogue": "Ele achou que eu não tinha visto o envelope no cofre.",
        "visual_prompt": "Close-up of a woman in dark office lighting looking at a hidden safe, cinematic suspense, 9:16",
    },
    {
        "scene_index": 2,
        "dialogue": "Durante três anos, assinou contratos em meu nome e ficou com os lucros.",
        "visual_prompt": "Hands flipping through signed corporate documents under a desk lamp, moody noir shadows, 9:16",
    },
    {
        "scene_index": 3,
        "dialogue": "Hoje, às nove da manhã, a auditoria vai entrar pela porta principal.",
        "visual_prompt": "Glass skyscraper lobby with silhouettes walking in decisively, dramatic morning light, 9:16",
    },
    {
        "scene_index": 4,
        "dialogue": "E o único nome que falta na carta de demissão... é o dele.",
        "visual_prompt": "Woman smiling subtly in an elevator mirror holding a red folder, thriller ending, 9:16",
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
# FUNÇÕES DO MOTOR DE IA E VÍDEO
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
- Cada "visual_prompt" deve ser em inglês, detalhado, estilo cinematográfico vertical 9:16, mantendo consistência visual das personagens.

Devolve APENAS um JSON válido com uma lista de objetos neste formato:
[
  {{
    "scene_index": 1,
    "dialogue": "Texto falado da cena",
    "visual_prompt": "Cinematic prompt in English"
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


def create_placeholder_card(path: Path, scene_num: int, prompt_text: str):
    """Gera uma imagem cinematográfica escura temporária caso o utilizador não carregue foto."""
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


def render_episode(scenes: list[dict], uploaded_images: dict, voice_id: str, watermark: bool, progress_bar) -> Path:
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

        # 1. Imagem da cena (carregada ou cartão temporário)
        if idx in uploaded_images and uploaded_images[idx] is not None:
            img = Image.open(uploaded_images[idx]).convert("RGB")
            img.save(img_path, format="JPEG", quality=92)
        else:
            create_placeholder_card(img_path, idx + 1, visual_prompt)

        # 2. Voz neural + tempos de legenda
        timings = asyncio.run(generate_tts(dialogue, voice_id, audio_path))
        audio_dur = get_duration(audio_path)
        scene_dur = audio_dur + 0.35

        # Fallback automático caso o serviço TTS não envie tempos palavra-a-palavra
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

        # 3. Movimento suave de câmara (Modo Rápido FFmpeg)
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

        # 4. Juntar vídeo e voz da cena com formato de áudio normalizado
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

    # 5. Unir todas as cenas
    (job_dir / "concat.txt").write_text(
        "\n".join(f"file '{v.name}'" for v in scene_videos), encoding="utf-8"
    )
    (job_dir / "captions.srt").write_text("\n".join(srt_entries), encoding="utf-8")

    run_cmd(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "concat.txt", "-c", "copy", "stitched.mp4"],
        cwd=job_dir,
    )
    progress_bar.progress(88, text="A aplicar legendas e acabamento final...")

    # 6. Queimar legendas e marca d'água opcional
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
if "last_video" not in st.session_state:
    st.session_state.last_video = None

st.title("🎬 MiniDrama Studio — Protótipo v1")
st.caption("Cria episódios verticais 9:16 com guião IA, voz neural e legendas automáticas.")

if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
    st.error("FFmpeg não encontrado no sistema. Confirma se o ficheiro packages.txt contém 'ffmpeg'.")
    st.stop()

with st.sidebar:
    st.header("Configurações")
    gemini_key = st.text_input("Chave API Google Gemini (opcional)", type="password")
    voice_label = st.selectbox("Voz do narrador", list(VOICES.keys()))
    watermark = st.checkbox("Incluir marca d'água (plano grátis)", value=True)
    st.divider()
    st.info("Sem chave Gemini? Usa o botão **Carregar Guião de Demonstração** para testar o motor de vídeo imediatamente.")

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
            st.warning("Cola a tua chave Gemini na barra lateral ou usa o guião de demonstração ao lado.")
        else:
            with st.spinner("A escrever o guião estruturado..."):
                try:
                    lang = "Português" if "Português" in voice_label else "Inglês"
                    st.session_state.scenes = generate_script_gemini(gemini_key, premise, genre, lang, num_scenes)
                except Exception as e:
                    st.error(f"Erro ao chamar a API Gemini: {e}")
with b2:
    if st.button("⚡ Carregar Guião de Demonstração", use_container_width=True):
        st.session_state.scenes = [dict(s) for s in DEMO_SCENES]

# PASSO 2: EDITAR CENAS E IMAGENS
if st.session_state.scenes:
    st.divider()
    st.subheader("2. Rever Falas e Imagens (Storyboard)")
    st.caption("Podes carregar uma imagem tua por cena ou deixar em branco para gerar cartões de teste automáticos.")

    uploaded_images = {}
    for i, scene in enumerate(st.session_state.scenes):
        with st.expander(f"Cena {i + 1}", expanded=True):
            c_txt, c_img = st.columns([2, 1])
            with c_txt:
                scene["dialogue"] = st.text_area(
                    "Fala / Narração", value=scene.get("dialogue", ""), key=f"diag_{i}", height=75
                )
                scene["visual_prompt"] = st.text_input(
                    "Prompt visual (usado na Etapa 2 para gerar imagem IA)",
                    value=scene.get("visual_prompt", ""),
                    key=f"vis_{i}",
                )
            with c_img:
                uploaded_images[i] = st.file_uploader(
                    "Imagem opcional (JPG/PNG)", type=["jpg", "jpeg", "png"], key=f"img_{i}"
                )

    # PASSO 3: RENDERIZAR
    st.divider()
    st.subheader("3. Produzir Episódio Vertical (9:16)")
    if st.button("🎥 Gerar Vídeo Completo (Modo Rápido)", type="primary"):
        bar = st.progress(5, text="A iniciar motor de renderização...")
        try:
            out_path = render_episode(
                scenes=st.session_state.scenes,
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
