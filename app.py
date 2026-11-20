import asyncio
import base64
import io
import json
import math
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
import uuid
import wave
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

VOICE_ENGINES = [
    "Gemini — Voz Dramática / Direção de Atores (usa a chave Gemini)",
    "ElevenLabs — Qualidade Cinema (plano grátis / SaaS Pro)",
    "Edge-TTS — Leitura Rápida com Emoção (grátis ilimitado)",
]

GEMINI_VOICES = {
    "Kore — Feminina (Firme e dramática)": "Kore",
    "Aoede — Feminina (Intensa e envolvente)": "Aoede",
    "Charon — Masculina (Grave, ideal para thriller)": "Charon",
    "Fenrir — Masculina (Enérgica e tensa)": "Fenrir",
    "Puck — Masculina (Natural e ágil)": "Puck",
}

ELEVEN_VOICES = {
    "Rachel — Feminina (Narrativa emocional)": "21m00Tcm4TlvDq8ikWAM",
    "Bella — Feminina (Suave / Suspense)": "EXAVITQu4vr4xnSDxMaL",
    "Adam — Masculina (Grave / Thriller)": "pNInz6obpgDQGcFmaJgB",
    "Antoni — Masculina (Dramática)": "ErXwobaYiN019PkySvjV",
}

EDGE_VOICES = {
    "Português (PT) — Raquel (Feminina)": "pt-PT-RaquelNeural",
    "Português (PT) — Duarte (Masculina)": "pt-PT-DuarteNeural",
    "Português (BR) — Francisca (Feminina)": "pt-BR-FranciscaNeural",
    "Português (BR) — Antonio (Masculina)": "pt-BR-AntonioNeural",
    "Inglês (US) — Jenny (Feminina)": "en-US-JennyNeural",
    "Inglês (US) — Guy (Masculina)": "en-US-GuyNeural",
}

LANGUAGES = {
    "Português (Portugal)": "European Portuguese (Portugal accent)",
    "Português (Brasil)": "Brazilian Portuguese",
    "Inglês (US)": "American English",
}

EMOTION_PROSODY = {
    "suspense": ("-8%", "-4Hz"),
    "urgencia": ("+7%", "+2Hz"),
    "frieza": ("-5%", "-6Hz"),
    "choque": ("+4%", "+4Hz"),
    "neutro": ("+0%", "+0Hz"),
}

IMAGE_PROVIDERS = [
    "Google Gemini — Imagens (usa a chave Gemini)",
    "Hugging Face — FLUX / SDXL (requer token com créditos)",
]

DEMO_SCENES = [
    {
        "scene_index": 1,
        "dialogue": "Ele achou que eu não tinha visto o envelope escondido no cofre...",
        "emotion": "suspense",
        "voice_direction": "sussurrado, tenso e conspiratório, com uma ligeira pausa antes do fim",
        "visual_prompt": "Cinematic vertical 9:16 thriller shot, young woman in dark tailored blazer with hair tied back looking intensely at an open hidden wall safe in a dim luxury office, dramatic rim lighting, photorealistic, 35mm film, no text",
    },
    {
        "scene_index": 2,
        "dialogue": "Durante três anos, assinou contratos em meu nome e ficou com todos os lucros!",
        "emotion": "urgencia",
        "voice_direction": "voz indignada, firme e carregada de raiva contida",
        "visual_prompt": "Cinematic vertical 9:16 close-up of hands of a young woman in a dark blazer flipping through signed corporate financial contracts under a warm desk lamp, moody noir shadows, photorealistic, 35mm film, no text",
    },
    {
        "scene_index": 3,
        "dialogue": "Mas hoje, às nove da manhã, a auditoria entra pela porta principal.",
        "emotion": "frieza",
        "voice_direction": "tom calmo, frio e calculista, confiante na vingança",
        "visual_prompt": "Cinematic vertical 9:16 shot inside a modern glass corporate skyscraper lobby, silhouettes of serious investigators in dark suits walking in decisively through revolving doors, dramatic morning backlight, photorealistic, no text",
    },
    {
        "scene_index": 4,
        "dialogue": "E o único nome que falta na carta de demissão... é o dele.",
        "emotion": "suspense",
        "voice_direction": "lento, dramático, com pausa forte nas reticências e sorriso subtil na voz",
        "visual_prompt": "Cinematic vertical 9:16 thriller ending shot, young woman in dark tailored blazer with hair tied back smiling subtly inside a sleek metal elevator mirror holding a red folder, moody blue lighting, photorealistic, 35mm film, no text",
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
# GERAÇÃO DE GUIÃO COM DIREÇÃO DE ATORES (GEMINI)
# ---------------------------------------------------------
def generate_script_gemini(api_key: str, premise: str, genre: str, lang_label: str, num_scenes: int) -> list[dict]:
    from google import genai
    from google.genai import types

    client = genai.Client(
        api_key=api_key.strip(),
        http_options=types.HttpOptions(api_version="v1beta"),
    )
    prompt = f"""
Cria um guião viral para um mini-drama vertical (TikTok/Reels) no género "{genre}", escrito em {lang_label}, com exatamente {num_scenes} cenas.
Premissa: {premise}

Regras obrigatórias:
- Cena 1 tem de ter um gancho imediato nos primeiros 2 segundos.
- Última cena tem de terminar num cliffhanger forte.
- Cada fala ("dialogue") deve ter entre 10 e 20 palavras, com pontuação dramática (reticências, exclamações ou perguntas para dar ritmo à voz).
- Cada cena inclui "emotion" (escolhe APENAS um: "suspense", "urgencia", "frieza", "choque").
- Cada cena inclui "voice_direction" em inglês curto (ex.: "whispered, tense, breathless thriller tone" ou "cold, calm, vengeful confidence") para dirigir o ator de voz IA.
- Cada "visual_prompt" deve ser em INGLÊS, fotorealista, cinema 35mm vertical 9:16, SEM texto escrito na imagem, repetindo exatamente a mesma aparência física e roupa da personagem principal em todas as cenas.

Devolve APENAS um JSON válido com uma lista de objetos neste formato:
[
  {{
    "scene_index": 1,
    "dialogue": "Texto falado dramático",
    "emotion": "suspense",
    "voice_direction": "whispered, tense, slow dramatic delivery",
    "visual_prompt": "Cinematic vertical 9:16 photorealistic prompt in English, no text"
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
# GERAÇÃO DE IMAGENS IA
# ---------------------------------------------------------
def normalize_image_bytes(raw_bytes: bytes) -> bytes:
    img = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def generate_image_gemini(prompt: str, api_key: str) -> bytes:
    from google import genai
    from google.genai import types

    if not api_key.strip():
        raise RuntimeError("Cola a tua chave API Google Gemini na barra lateral.")

    client = genai.Client(
        api_key=api_key.strip(),
        http_options=types.HttpOptions(api_version="v1beta"),
    )
    last_err = None

    for model_id in ["gemini-2.5-flash-image", "gemini-2.0-flash-exp-image-generation"]:
        try:
            resp = client.models.generate_content(
                model=model_id,
                contents=f"Generate a vertical 9:16 cinematic photorealistic frame with no text: {prompt}",
                config=types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
            )
            for candidate in getattr(resp, "candidates", []) or []:
                content = getattr(candidate, "content", None)
                for part in getattr(content, "parts", []) or []:
                    inline = getattr(part, "inline_data", None)
                    data = getattr(inline, "data", None) if inline else None
                    if data:
                        if isinstance(data, str):
                            data = base64.b64decode(data)
                        return normalize_image_bytes(data)
        except Exception as e:
            last_err = e
            continue

    for imagen_model in ["imagen-3.0-generate-002", "imagen-4.0-generate-001"]:
        try:
            resp = client.models.generate_images(
                model=imagen_model,
                prompt=prompt,
                config=types.GenerateImagesConfig(number_of_images=1, aspect_ratio="9:16"),
            )
            if resp.generated_images:
                return normalize_image_bytes(resp.generated_images[0].image.image_bytes)
        except Exception as e:
            last_err = e
            continue

    raise RuntimeError(f"A chave Gemini não conseguiu gerar imagem: {last_err}")


def generate_image_huggingface(prompt: str, hf_token: str) -> bytes:
    from huggingface_hub import InferenceClient

    if not hf_token.strip():
        raise RuntimeError("Cola o teu token do Hugging Face na barra lateral.")
    client = InferenceClient(provider="auto", api_key=hf_token.strip())
    img = client.text_to_image(prompt, model="black-forest-labs/FLUX.1-schnell")
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def generate_scene_image(prompt: str, provider: str, hf_token: str, gemini_key: str) -> bytes:
    if provider.startswith("Google Gemini"):
        return generate_image_gemini(prompt, gemini_key)
    return generate_image_huggingface(prompt, hf_token)


def create_placeholder_card(path: Path, scene_num: int, prompt_text: str):
    img = Image.new("RGB", (1080, 1920), (16, 18, 28))
    draw = ImageDraw.Draw(img)
    for y in range(1920):
        tone = int(16 + (y / 1920) * 28)
        draw.line([(0, y), (1080, y)], fill=(tone, tone + 2, tone + 16))
    draw.rectangle([70, 120, 1010, 1800], outline=(90, 105, 150), width=3)
    draw.text((120, 260), f"CENA {scene_num:02d}", fill=(240, 200, 110), font=load_pil_font(72))
    img.save(path, format="JPEG", quality=92)


# ---------------------------------------------------------
# MOTORES DE VOZ DRAMÁTICA
# ---------------------------------------------------------
def estimate_weighted_timings(text: str, audio_dur_sec: float, words_per_chunk: int = 4):
    """Sincroniza legendas proporcionalmente ao comprimento das palavras e pausas de pontuação."""
    words = text.split()
    if not words:
        return []
    parts = [" ".join(words[i : i + words_per_chunk]) for i in range(0, len(words), words_per_chunk)]

    def weight(chunk_txt: str) -> float:
        w = float(len(chunk_txt))
        w += chunk_txt.count(",") * 4.0
        w += chunk_txt.count("...") * 9.0
        w += (chunk_txt.count(".") + chunk_txt.count("!") + chunk_txt.count("?")) * 5.0
        return max(w, 4.0)

    weights = [weight(p) for p in parts]
    total_w = sum(weights)
    total_ms = audio_dur_sec * 1000.0
    timings = []
    cursor = 0.0
    for p, w in zip(parts, weights):
        dur = (w / total_w) * total_ms
        timings.append((cursor, cursor + dur, p))
        cursor += dur
    return timings


def generate_tts_gemini_dramatic(
    text: str,
    voice_direction: str,
    lang_hint: str,
    voice_name: str,
    api_key: str,
    out_wav: Path,
):
    from google import genai
    from google.genai import types

    if not api_key.strip():
        raise RuntimeError("Cola a tua chave API Google Gemini na barra lateral para usar a Voz Dramática.")

    client = genai.Client(
        api_key=api_key.strip(),
        http_options=types.HttpOptions(api_version="v1beta"),
    )

    direction = voice_direction.strip() or "dramatic thriller tone, expressive and intense"
    tts_prompt = (
        f"Speak in {lang_hint}, acting with this exact emotional direction ({direction}): "
        f"{text}"
    )

    resp = client.models.generate_content(
        model="gemini-2.5-flash-preview-tts",
        contents=tts_prompt,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name)
                )
            ),
        ),
    )

    audio_bytes = None
    for candidate in getattr(resp, "candidates", []) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", []) or []:
            inline = getattr(part, "inline_data", None)
            data = getattr(inline, "data", None) if inline else None
            if data:
                audio_bytes = base64.b64decode(data) if isinstance(data, str) else data
                break

    if not audio_bytes:
        raise RuntimeError("O modelo de voz Gemini não devolveu áudio para esta cena.")

    if audio_bytes[:4] == b"RIFF":
        out_wav.write_bytes(audio_bytes)
    else:
        with wave.open(str(out_wav), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(24000)
            wf.writeframes(audio_bytes)


def generate_tts_elevenlabs(text: str, voice_id: str, api_key: str, out_mp3: Path):
    if not api_key.strip():
        raise RuntimeError("Cola a tua chave API do ElevenLabs na barra lateral.")

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id.strip()}"
    payload = json.dumps(
        {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.32,
                "similarity_boost": 0.78,
                "style": 0.60,
                "use_speaker_boost": True,
            },
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "xi-api-key": api_key.strip(),
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            out_mp3.write_bytes(resp.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="ignore")[:220]
        raise RuntimeError(f"Erro ElevenLabs ({e.code}): {detail}")


async def generate_tts_edge(text: str, voice: str, emotion: str, out_mp3: Path, words_per_chunk: int = 4):
    rate, pitch = EMOTION_PROSODY.get(emotion, ("+0%", "+0Hz"))
    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch=pitch)
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


# ---------------------------------------------------------
# MOTOR DE VÍDEO E AMBIENTE SONORO (FFMPEG)
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


def build_suspense_drone(out_audio: Path, duration_sec: float, cwd: Path):
    """Cria uma base sonora grave e pulsante de thriller sem depender de ficheiros externos."""
    dur = f"{duration_sec + 1.0:.2f}"
    run_cmd(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"sine=frequency=55:sample_rate=44100:duration={dur}",
            "-f", "lavfi", "-i", f"sine=frequency=82.4:sample_rate=44100:duration={dur}",
            "-filter_complex",
            "[0:a][1:a]amix=inputs=2:duration=shortest,"
            "tremolo=f=0.35:d=0.65,lowpass=f=220,"
            "afade=t=in:st=0:d=1.2[out]",
            "-map", "[out]",
            "-c:a", "aac", "-b:a", "128k",
            out_audio.name,
        ],
        cwd=cwd,
    )


def render_episode(
    scenes: list[dict],
    ai_images: dict[int, bytes],
    uploaded_images: dict,
    voice_cfg: dict,
    bgm_mode: str,
    bgm_file,
    bgm_volume: float,
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
        clip_vid = job_dir / f"{prefix}_vid.mp4"
        merged_vid = job_dir / f"{prefix}_merged.mp4"

        dialogue = scene.get("dialogue", "").strip()
        emotion = scene.get("emotion", "suspense")
        voice_direction = scene.get("voice_direction", "tense dramatic thriller tone")
        visual_prompt = scene.get("visual_prompt", "")

        # 1. Imagem
        if idx in uploaded_images and uploaded_images[idx] is not None:
            Image.open(uploaded_images[idx]).convert("RGB").save(img_path, format="JPEG", quality=92)
        elif idx in ai_images and ai_images[idx]:
            img_path.write_bytes(ai_images[idx])
        else:
            create_placeholder_card(img_path, idx + 1, visual_prompt)

        # 2. Voz dramática conforme motor escolhido
        progress_bar.progress(
            int((idx / total) * 70) + 2,
            text=f"A gravar voz dramática da Cena {idx + 1}/{total}...",
        )
        engine = voice_cfg["engine"]
        timings = []

        if engine.startswith("Gemini"):
            audio_path = job_dir / f"{prefix}.wav"
            generate_tts_gemini_dramatic(
                text=dialogue,
                voice_direction=voice_direction,
                lang_hint=voice_cfg["lang_hint"],
                voice_name=voice_cfg["voice_id"],
                api_key=voice_cfg["gemini_key"],
                out_wav=audio_path,
            )
            if idx < total - 1:
                time.sleep(1.2)
        elif engine.startswith("ElevenLabs"):
            audio_path = job_dir / f"{prefix}.mp3"
            generate_tts_elevenlabs(
                text=dialogue,
                voice_id=voice_cfg["voice_id"],
                api_key=voice_cfg["eleven_key"],
                out_mp3=audio_path,
            )
        else:
            audio_path = job_dir / f"{prefix}.mp3"
            timings = asyncio.run(
                generate_tts_edge(dialogue, voice_cfg["voice_id"], emotion, audio_path)
            )

        audio_dur = get_duration(audio_path)
        scene_dur = audio_dur + 0.40

        if not timings:
            timings = estimate_weighted_timings(dialogue, audio_dur, words_per_chunk=4)

        for s_ms, e_ms, txt in timings:
            srt_entries.append(
                f"{srt_idx}\n"
                f"{format_srt_time(offset_ms + s_ms)} --> {format_srt_time(offset_ms + e_ms)}\n"
                f"{txt.upper()}\n"
            )
            srt_idx += 1

        # 3. Movimento suave de câmara (Zoompan)
        fps = 30
        frames = max(1, math.ceil(scene_dur * fps))
        zoom_expr = "min(zoom+0.0009,1.14)" if idx % 2 == 0 else "max(1.12-0.0008*on,1.0)"
        vf = (
            "scale=1440:2560:force_original_aspect_ratio=increase,"
            "crop=1440:2560,"
            f"zoompan=z='{zoom_expr}':"
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

        # 4. Fundir vídeo e voz normalizada
        run_cmd(
            [
                "ffmpeg", "-y",
                "-i", clip_vid.name, "-i", audio_path.name,
                "-af", "apad=pad_dur=0.40",
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

    # 5. Concatenar cenas
    (job_dir / "concat.txt").write_text(
        "\n".join(f"file '{v.name}'" for v in scene_videos), encoding="utf-8"
    )
    (job_dir / "captions.srt").write_text("\n".join(srt_entries), encoding="utf-8")

    stitched_mp4 = job_dir / "stitched.mp4"
    run_cmd(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "concat.txt", "-c", "copy", stitched_mp4.name],
        cwd=job_dir,
    )
    total_dur = get_duration(stitched_mp4)
    progress_bar.progress(86, text="A misturar ambiente sonoro e legendas...")

    # 6. Preparar música de fundo (opcional)
    bgm_path = None
    if bgm_mode == "Atmosfera Suspense Automática (integrada)":
        bgm_path = job_dir / "bgm_auto.m4a"
        build_suspense_drone(bgm_path, total_dur, cwd=job_dir)
    elif bgm_mode == "Carregar música própria (MP3/WAV)" and bgm_file is not None:
        ext = Path(bgm_file.name).suffix or ".mp3"
        bgm_path = job_dir / f"bgm_custom{ext}"
        bgm_path.write_bytes(bgm_file.getvalue())

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
    if bgm_path is not None:
        cmd = [
            "ffmpeg", "-y",
            "-i", stitched_mp4.name,
            "-stream_loop", "-1", "-i", bgm_path.name,
            "-filter_complex",
            f"[0:v]{','.join(filters)}[v];"
            f"[1:a]volume={bgm_volume:.2f}[bgm];"
            "[0:a][bgm]amix=inputs=2:duration=first:normalize=0[a]",
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            final_mp4.name,
        ]
    else:
        cmd = [
            "ffmpeg", "-y", "-i", stitched_mp4.name,
            "-vf", ",".join(filters),
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-c:a", "copy", "-movflags", "+faststart",
            final_mp4.name,
        ]

    run_cmd(cmd, cwd=job_dir)
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

st.title("🎬 MiniDrama Studio — Protótipo v3")
st.caption("Guião com Direção de Atores + Imagens IA + Voz Dramática e Ambiente de Suspense.")

if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
    st.error("FFmpeg não encontrado no sistema. Confirma se o ficheiro packages.txt contém 'ffmpeg'.")
    st.stop()

with st.sidebar:
    st.header("Configurações")
    gemini_key = st.text_input("Chave API Google Gemini", type="password")
    lang_label = st.selectbox("Idioma / Sotaque do Episódio", list(LANGUAGES.keys()))

    st.divider()
    st.subheader("🎭 Motor de Voz")
    voice_engine = st.selectbox("Escolher motor de voz", VOICE_ENGINES)

    eleven_key = ""
    if voice_engine.startswith("Gemini"):
        g_voice_label = st.selectbox("Voz dramática (Gemini)", list(GEMINI_VOICES.keys()))
        selected_voice_id = GEMINI_VOICES[g_voice_label]
        st.caption("Usa a direção emocional de cada cena para atuar o texto.")
    elif voice_engine.startswith("ElevenLabs"):
        eleven_key = st.text_input("Chave API ElevenLabs", type="password")
        e_voice_label = st.selectbox("Voz ElevenLabs", list(ELEVEN_VOICES.keys()))
        selected_voice_id = ELEVEN_VOICES[e_voice_label]
        st.caption("Conta gratuita inclui ~10.000 caracteres/mês em elevenlabs.io.")
    else:
        edge_label = st.selectbox("Voz Edge-TTS", list(EDGE_VOICES.keys()))
        selected_voice_id = EDGE_VOICES[edge_label]

    st.divider()
    st.subheader("🎵 Ambiente Sonoro")
    bgm_mode = st.selectbox(
        "Música / Atmosfera de fundo",
        [
            "Atmosfera Suspense Automática (integrada)",
            "Carregar música própria (MP3/WAV)",
            "Sem música de fundo",
        ],
    )
    bgm_file = None
    if bgm_mode == "Carregar música própria (MP3/WAV)":
        bgm_file = st.file_uploader("Carregar música", type=["mp3", "wav"])
    bgm_volume = st.slider("Volume do fundo sonoro", 0.05, 0.35, 0.14, 0.01)

    st.divider()
    st.subheader("🖼️ Motor de Imagens")
    img_provider = st.selectbox("Serviço de imagem", IMAGE_PROVIDERS)
    hf_token = ""
    if "Hugging Face" in img_provider:
        hf_token = st.text_input("Token Hugging Face", type="password")

    watermark = st.checkbox("Incluir marca d'água (plano grátis)", value=True)

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
    if st.button("✨ Gerar Guião Dramático (Gemini)", type="primary", use_container_width=True):
        if not gemini_key:
            st.warning("Cola a tua chave Gemini na barra lateral ou usa o guião de demonstração.")
        else:
            with st.spinner("A escrever o guião e a direção de atores..."):
                try:
                    st.session_state.scenes = generate_script_gemini(
                        gemini_key, premise, genre, lang_label, num_scenes
                    )
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

# PASSO 2: STORYBOARD + DIREÇÃO DE ATORES + IMAGENS IA
if st.session_state.scenes:
    st.divider()
    st.subheader("2. Storyboard, Direção de Voz e Imagens (9:16)")

    if st.button("🎨 Gerar Imagens IA para Todas as Cenas", type="primary"):
        img_bar = st.progress(0, text="A gerar imagens...")
        total_s = len(st.session_state.scenes)
        had_error = False
        for i, scene in enumerate(st.session_state.scenes):
            img_bar.progress(int((i / total_s) * 100), text=f"A gerar imagem da Cena {i + 1}/{total_s}...")
            try:
                st.session_state.scene_images[i] = generate_scene_image(
                    scene.get("visual_prompt", ""), img_provider, hf_token, gemini_key
                )
            except Exception as e:
                had_error = True
                img_bar.empty()
                st.error(f"Cena {i + 1}: {e}")
                break
        if not had_error:
            img_bar.progress(100, text="Todas as imagens foram geradas!")
            st.rerun()

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
                    height=70,
                )
                d_col1, d_col2 = st.columns([2, 1])
                with d_col1:
                    scene["voice_direction"] = st.text_input(
                        "🎭 Direção de representação (tom da voz)",
                        value=scene.get("voice_direction", "tense dramatic whisper"),
                        key=f"dir_{ver}_{i}",
                    )
                with d_col2:
                    emo_list = list(EMOTION_PROSODY.keys())
                    cur_emo = scene.get("emotion", "suspense")
                    emo_idx = emo_list.index(cur_emo) if cur_emo in emo_list else 0
                    scene["emotion"] = st.selectbox(
                        "Intensidade", emo_list, index=emo_idx, key=f"emo_{ver}_{i}"
                    )

                scene["visual_prompt"] = st.text_area(
                    "Prompt visual (em inglês)",
                    value=scene.get("visual_prompt", ""),
                    key=f"vis_{ver}_{i}",
                    height=70,
                )
                if st.button(f"🔄 Gerar / Regenerar só a Cena {i + 1}", key=f"regen_{ver}_{i}"):
                    with st.spinner(f"A gerar imagem da Cena {i + 1}..."):
                        try:
                            st.session_state.scene_images[i] = generate_scene_image(
                                scene["visual_prompt"], img_provider, hf_token, gemini_key
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
    if st.button("🎥 Gerar Vídeo Completo com Voz Dramática", type="primary"):
        bar = st.progress(5, text="A iniciar produção do episódio...")
        try:
            voice_cfg = {
                "engine": voice_engine,
                "voice_id": selected_voice_id,
                "lang_hint": LANGUAGES[lang_label],
                "gemini_key": gemini_key,
                "eleven_key": eleven_key,
            }
            out_path = render_episode(
                scenes=st.session_state.scenes,
                ai_images=st.session_state.scene_images,
                uploaded_images=uploaded_images,
                voice_cfg=voice_cfg,
                bgm_mode=bgm_mode,
                bgm_file=bgm_file,
                bgm_volume=bgm_volume,
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
