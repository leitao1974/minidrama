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
    page_title="MiniDrama Studio — Elenco & Diálogos (v4.2)",
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
    "Leda — Feminina (Jovem e expressiva)": "Leda",
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

DEFAULT_VOICES_BY_GENDER = {
    "Gemini": {
        "female": ["Kore — Feminina (Firme e dramática)", "Aoede — Feminina (Intensa e envolvente)", "Leda — Feminina (Jovem e expressiva)"],
        "male": ["Charon — Masculina (Grave, ideal para thriller)", "Fenrir — Masculina (Enérgica e tensa)", "Puck — Masculina (Natural e ágil)"],
    },
    "ElevenLabs": {
        "female": ["Rachel — Feminina (Narrativa emocional)", "Bella — Feminina (Suave / Suspense)"],
        "male": ["Adam — Masculina (Grave / Thriller)", "Antoni — Masculina (Dramática)"],
    },
    "Edge-TTS": {
        "female": ["Português (PT) — Raquel (Feminina)", "Português (BR) — Francisca (Feminina)"],
        "male": ["Português (PT) — Duarte (Masculina)", "Português (BR) — Antonio (Masculina)"],
    },
}

LANGUAGES = {
    "Português (Portugal)": "European Portuguese (Portugal accent)",
    "Português (Brasil)": "Brazilian Portuguese",
    "Inglês (US)": "American English",
}

EMOTION_PROSODY = {
    "suspense": ("-7%", "-3Hz"),
    "urgencia": ("+7%", "+2Hz"),
    "frieza": ("-5%", "-5Hz"),
    "choque": ("+5%", "+4Hz"),
    "neutro": ("+0%", "+0Hz"),
}

CAMERA_MOTIONS = {
    "push_in": "Aproximação (Zoom In)",
    "pull_out": "Afastamento (Zoom Out)",
    "pan_right": "Panorâmica Direita",
    "pan_left": "Panorâmica Esquerda",
}

CHAR_SUBTITLE_COLORS = ["&H00FFFFFF", "&H0055E6FF", "&H00FFD480", "&H00A8FF99"]

DEMO_EPISODE = {
    "title": "O Cofre da Meia-Noite",
    "characters": [
        {
            "id": "char_1",
            "name": "Sofia",
            "role": "Estagiária",
            "gender": "female",
            "visual_profile": "23-year-old Southern European woman with dark brown hair tied in a neat low ponytail, alert dark eyes, wearing a fitted charcoal grey blazer over a crisp white shirt",
        },
        {
            "id": "char_2",
            "name": "Henrique",
            "role": "Diretor Financeiro",
            "gender": "male",
            "visual_profile": "48-year-old European man with short salt-and-pepper hair, trimmed beard, sharp intense gaze, wearing an expensive navy tailored suit, white shirt and dark silk tie",
        },
    ],
    "scenes": [
        {
            "scene_index": 1,
            "speaker_id": "char_1",
            "characters_in_scene": ["char_1"],
            "dialogue": "Encontrei as transferências fantasmas no cofre... três milhões em contas offshore.",
            "emotion": "suspense",
            "voice_direction": "whispered, tense, breathless realization",
            "camera_motion": "push_in",
            "visual_prompt": "Close-up vertical 9:16 thriller shot inside a dimly lit luxury corporate office at night, Sofia holding confidential financial papers beside an open hidden wall safe, dramatic warm desk lamp lighting, photorealistic 35mm film",
        },
        {
            "scene_index": 2,
            "speaker_id": "char_2",
            "characters_in_scene": ["char_2"],
            "dialogue": "Fica onde estás, Sofia. Não devias ter aberto essa porta a esta hora.",
            "emotion": "frieza",
            "voice_direction": "cold, deep, threatening calm",
            "camera_motion": "pan_right",
            "visual_prompt": "Medium vertical 9:16 suspense shot in a dark corporate office doorway, Henrique standing partially in shadow leaning against the doorframe with a cold menacing expression, blue moonlight rim light, photorealistic 35mm film",
        },
        {
            "scene_index": 3,
            "speaker_id": "char_1",
            "characters_in_scene": ["char_1", "char_2"],
            "dialogue": "O senhor usou a minha assinatura durante dois anos! Acha mesmo que vou ficar calada?",
            "emotion": "urgencia",
            "voice_direction": "defiant, angry, shaking with controlled courage",
            "camera_motion": "pull_out",
            "visual_prompt": "Tense vertical 9:16 two-shot across a mahogany office desk at night, Sofia standing firmly holding a red folder confronting Henrique who steps closer in shadow, high-contrast thriller lighting, photorealistic 35mm film",
        },
        {
            "scene_index": 4,
            "speaker_id": "char_2",
            "characters_in_scene": ["char_2", "char_1"],
            "dialogue": "Ninguém vai acreditar numa estagiária... mas olha para o teu telemóvel antes de ameaçares.",
            "emotion": "suspense",
            "voice_direction": "slow, chilling smirk in voice, dramatic pause before the end",
            "camera_motion": "push_in",
            "visual_prompt": "Dramatic vertical 9:16 over-the-shoulder close-up of Henrique smiling coldly while pointing slightly towards Sofia's glowing smartphone screen on the desk, tense noir thriller cliffhanger atmosphere, photorealistic 35mm film",
        },
    ],
}


# ---------------------------------------------------------
# DETEÇÃO AUTOMÁTICA DE MODELOS GEMINI DA CHAVE
# ---------------------------------------------------------
def _make_gemini_client(api_key: str):
    from google import genai
    from google.genai import types

    return genai.Client(
        api_key=api_key.strip(),
        http_options=types.HttpOptions(api_version="v1beta"),
    )


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for x in items:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


@st.cache_data(ttl=300, show_spinner=False)
def list_key_models(api_key: str) -> dict[str, list[str]]:
    """Consulta a API Gemini e classifica os modelos realmente ativos nesta chave."""
    if not api_key or len(api_key.strip()) < 10:
        return {"all": [], "text": [], "image": [], "tts": []}

    client = _make_gemini_client(api_key)
    all_names: list[str] = []
    try:
        for m in client.models.list():
            raw = getattr(m, "name", "") or ""
            short = raw.replace("models/", "").strip()
            if short:
                all_names.append(short)
    except Exception:
        return {"all": [], "text": [], "image": [], "tts": []}

    blocked_text = (
        "image", "tts", "embedding", "aqa", "audio", "veo", "imagen",
        "live", "native", "robotics", "computer-use", "lyria", "banana",
    )
    flash_text = sorted(
        [m for m in all_names if m.startswith("gemini-") and "flash" in m and not any(b in m for b in blocked_text)],
        reverse=True,
    )
    other_text = sorted(
        [m for m in all_names if m.startswith("gemini-") and "flash" not in m and not any(b in m for b in blocked_text)],
        reverse=True,
    )

    # Prioriza modelos nativos de imagem Gemini (funcionam no AI Studio) antes de Imagen
    gemini_imgs = sorted(
        [m for m in all_names if ("image" in m or "banana" in m) and not m.startswith("imagen-")],
        reverse=True,
    )
    imagen_imgs = sorted(
        [m for m in all_names if m.startswith("imagen-")],
        reverse=True,
    )
    tts_models = sorted([m for m in all_names if "tts" in m], reverse=True)

    return {
        "all": sorted(all_names),
        "text": _dedupe(flash_text + other_text),
        "image": _dedupe(gemini_imgs + imagen_imgs),
        "tts": _dedupe(tts_models),
    }


def get_text_candidates(api_key: str, preferred: str = "Automático") -> list[str]:
    info = list_key_models(api_key)
    base = info["text"] if info["text"] else ["gemini-3.8-flash", "gemini-3.0-flash", "gemini-2.5-flash"]
    if preferred and preferred != "Automático":
        return _dedupe([preferred] + base)
    return _dedupe(base + ["gemini-3.8-flash"])


def get_image_candidates(api_key: str, preferred: str = "Automático") -> list[str]:
    info = list_key_models(api_key)
    # Se a chave devolveu lista real de modelos, usa primeiro os dela
    if info["image"]:
        base = info["image"]
    else:
        base = [
            "gemini-3.8-flash-image",
            "gemini-3.0-flash-image",
            "gemini-2.5-flash-image",
            "gemini-2.0-flash-exp-image-generation",
        ]
    if preferred and preferred != "Automático":
        return _dedupe([preferred] + base)
    return _dedupe(base)


def get_tts_candidates(api_key: str) -> list[str]:
    info = list_key_models(api_key)
    return _dedupe(
        info["tts"]
        + [
            "gemini-2.5-flash-preview-tts",
            "gemini-3.8-flash-preview-tts",
            "gemini-3.0-flash-preview-tts",
        ]
    )


# ---------------------------------------------------------
# UTILITÁRIOS DE FONTES E VOZES
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


def get_engine_short_name(engine_label: str) -> str:
    if engine_label.startswith("Gemini"):
        return "Gemini"
    if engine_label.startswith("ElevenLabs"):
        return "ElevenLabs"
    return "Edge-TTS"


def get_voice_catalog(engine_label: str) -> dict[str, str]:
    short = get_engine_short_name(engine_label)
    if short == "Gemini":
        return GEMINI_VOICES
    if short == "ElevenLabs":
        return ELEVEN_VOICES
    return EDGE_VOICES


def pick_default_voice_label(engine_label: str, gender: str, char_idx: int) -> str:
    short = get_engine_short_name(engine_label)
    g = "female" if str(gender).lower().startswith("f") else "male"
    pool = DEFAULT_VOICES_BY_GENDER[short][g]
    return pool[char_idx % len(pool)]


# ---------------------------------------------------------
# GERAÇÃO DE GUIÃO MULTI-PERSONAGEM (GEMINI)
# ---------------------------------------------------------
def generate_episode_script_gemini(
    api_key: str,
    premise: str,
    genre: str,
    lang_label: str,
    num_scenes: int,
    num_chars: int,
    preferred_model: str = "Automático",
) -> dict:
    from google.genai import types

    client = _make_gemini_client(api_key)
    candidates = get_text_candidates(api_key, preferred_model)

    prompt = f"""
Cria um guião viral para um mini-drama vertical (TikTok/Reels) no género "{genre}", em {lang_label}, com exatamente {num_chars} personagens principais em diálogo direto e {num_scenes} cenas.
Premissa: {premise}

Regras obrigatórias:
1. "characters": lista com exatamente {num_chars} personagens com IDs "char_1", "char_2" (e "char_3" se aplicável).
   - Cada personagem tem "name", "role", "gender" ("female" ou "male"), e "visual_profile" em INGLÊS muito específico (idade, rosto, cabelo, roupa exata).
2. "scenes": lista com exatamente {num_scenes} cenas com diálogo real alternado entre as personagens (não é apenas um narrador).
   - Cena 1 tem gancho imediato nos primeiros 2 segundos; última cena termina em cliffhanger forte.
   - "speaker_id": ID da personagem que fala nesta cena ("char_1", "char_2", etc.).
   - "characters_in_scene": lista dos IDs das personagens visíveis no enquadramento (1 ou 2 personagens).
   - "dialogue": fala direta entre 10 e 20 palavras, com pontuação dramática.
   - "emotion": escolhe APENAS um de ["suspense", "urgencia", "frieza", "choque"].
   - "voice_direction": direção de ator curta em inglês (ex.: "cold threatening whisper").
   - "camera_motion": escolhe APENAS um de ["push_in", "pull_out", "pan_right", "pan_left"].
   - "visual_prompt": descrição cinematográfica vertical 9:16 em INGLÊS, fotorrealista 35mm, SEM texto na imagem, referindo as personagens pelo nome e ação exata.

Devolve APENAS um objeto JSON válido neste formato exato:
{{
  "title": "Título curto do episódio",
  "characters": [
    {{
      "id": "char_1",
      "name": "Nome",
      "role": "Papel",
      "gender": "female",
      "visual_profile": "Detailed physical and clothing description in English"
    }}
  ],
  "scenes": [
    {{
      "scene_index": 1,
      "speaker_id": "char_1",
      "characters_in_scene": ["char_1"],
      "dialogue": "Fala dramática da personagem",
      "emotion": "suspense",
      "voice_direction": "whispered tense thriller delivery",
      "camera_motion": "push_in",
      "visual_prompt": "Cinematic vertical 9:16 photorealistic scene in English, no text"
    }}
  ]
}}
"""
    errors = []
    for model_id in candidates[:5]:
        try:
            try:
                resp = client.models.generate_content(
                    model=model_id,
                    contents=prompt,
                    config=types.GenerateContentConfig(response_mime_type="application/json"),
                )
            except Exception as inner_e:
                if "JSON mode" in str(inner_e) or "response_mime_type" in str(inner_e):
                    resp = client.models.generate_content(model=model_id, contents=prompt)
                else:
                    raise

            raw = (resp.text or "").strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            s_i, e_i = raw.find("{"), raw.rfind("}")
            if s_i != -1 and e_i != -1:
                raw = raw[s_i : e_i + 1]

            data = json.loads(raw)
            if isinstance(data, dict) and data.get("characters") and data.get("scenes"):
                return data
        except Exception as e:
            errors.append(f"{model_id}: {str(e)[:180]}")
            continue

    raise RuntimeError("Nenhum modelo de texto respondeu.\n" + "\n".join(errors))


# ---------------------------------------------------------
# GERAÇÃO DE IMAGENS IA (COM DIAGNÓSTICO TRANSPARENTE)
# ---------------------------------------------------------
def normalize_image_bytes(raw_bytes: bytes) -> bytes:
    img = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def _extract_gemini_image(resp) -> bytes | None:
    for candidate in getattr(resp, "candidates", []) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", []) or []:
            inline = getattr(part, "inline_data", None)
            data = getattr(inline, "data", None) if inline else None
            if data:
                if isinstance(data, str):
                    data = base64.b64decode(data)
                return normalize_image_bytes(data)
    return None


def _call_single_image_model(client, model_id: str, contents, text_only_prompt: str) -> bytes:
    from google.genai import types

    if model_id.startswith("imagen-"):
        resp = client.models.generate_images(
            model=model_id,
            prompt=text_only_prompt,
            config=types.GenerateImagesConfig(number_of_images=1, aspect_ratio="9:16"),
        )
        if resp.generated_images:
            return normalize_image_bytes(resp.generated_images[0].image.image_bytes)
        raise RuntimeError("Modelo Imagen não devolveu imagem.")

    resp = client.models.generate_content(
        model=model_id,
        contents=contents,
        config=types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
    )
    img_bytes = _extract_gemini_image(resp)
    if img_bytes:
        return img_bytes
    raise RuntimeError("Resposta sem imagem (apenas texto ou bloqueio de segurança).")


def generate_portrait_gemini(char: dict, api_key: str, preferred_model: str = "Automático") -> bytes:
    if not api_key.strip():
        raise RuntimeError("Cola a tua chave API Google Gemini na barra lateral.")

    client = _make_gemini_client(api_key)
    candidates = get_image_candidates(api_key, preferred_model)

    prompt = (
        f"Generate a clean vertical 9:16 cinematic character reference portrait photo of {char['name']}. "
        f"Appearance: {char['visual_profile']}. "
        "Upper body / head and shoulders framing looking towards camera, neutral moody dark studio background, "
        "cinematic 35mm film lighting, photorealistic, sharp focus, NO text, NO watermarks."
    )

    errors = []
    for model_id in candidates[:6]:
        try:
            return _call_single_image_model(client, model_id, prompt, prompt)
        except Exception as e:
            errors.append(f"• {model_id} → {str(e)[:200]}")
            continue

    raise RuntimeError(
        f"Não foi possível gerar o retrato de {char['name']}. Modelos tentados:\n" + "\n".join(errors)
    )


def generate_scene_image_with_refs_gemini(
    prompt: str,
    api_key: str,
    ref_chars: list[tuple[str, str, bytes]],
    preferred_model: str = "Automático",
) -> bytes:
    from google.genai import types

    if not api_key.strip():
        raise RuntimeError("Cola a tua chave API Google Gemini na barra lateral.")

    client = _make_gemini_client(api_key)
    candidates = get_image_candidates(api_key, preferred_model)

    contents = []
    if ref_chars:
        contents.append(
            "Use the following character reference portrait(s) to keep exact facial identity, hair, age, and clothing consistent in the final movie frame:"
        )
        for name, visual_profile, img_bytes in ref_chars:
            contents.append(f"Character '{name}' ({visual_profile}):")
            contents.append(types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"))

    final_instruction = (
        "Generate ONE vertical 9:16 photorealistic 35mm cinematic movie frame matching the exact face(s) and outfit(s) above. "
        "Do NOT include any text, logos, captions, or split screens. "
        f"Scene description: {prompt}"
    )
    contents.append(final_instruction)

    desc_block = "; ".join(f"{n}: {vp}" for n, vp, _ in ref_chars)
    text_fallback_prompt = f"{prompt}. Characters appearance: {desc_block}" if desc_block else prompt

    errors = []
    for model_id in candidates[:6]:
        try:
            return _call_single_image_model(client, model_id, contents, text_fallback_prompt)
        except Exception as e:
            errors.append(f"• {model_id} → {str(e)[:200]}")
            continue

    raise RuntimeError("Não foi possível gerar a imagem da cena. Modelos tentados:\n" + "\n".join(errors))


def create_placeholder_card(path: Path, scene_num: int, speaker_name: str, prompt_text: str):
    img = Image.new("RGB", (1080, 1920), (16, 18, 28))
    draw = ImageDraw.Draw(img)
    for y in range(1920):
        tone = int(16 + (y / 1920) * 28)
        draw.line([(0, y), (1080, y)], fill=(tone, tone + 2, tone + 16))
    draw.rectangle([70, 120, 1010, 1800], outline=(90, 105, 150), width=3)
    draw.text((120, 240), f"CENA {scene_num:02d}", fill=(240, 200, 110), font=load_pil_font(72))
    draw.text((120, 340), f"Fala: {speaker_name}", fill=(160, 210, 255), font=load_pil_font(44))

    words = prompt_text.split()
    lines, cur = [], []
    for w in words:
        cur.append(w)
        if len(" ".join(cur)) > 36:
            lines.append(" ".join(cur))
            cur = []
    if cur:
        lines.append(" ".join(cur))
    y_pos = 460
    body_font = load_pil_font(32)
    for line in lines[:9]:
        draw.text((120, y_pos), line, fill=(210, 215, 230), font=body_font)
        y_pos += 48

    img.save(path, format="JPEG", quality=92)


# ---------------------------------------------------------
# MOTORES DE VOZ DRAMÁTICA
# ---------------------------------------------------------
def estimate_weighted_timings(text: str, audio_dur_sec: float, words_per_chunk: int = 4):
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
    from google.genai import types

    if not api_key.strip():
        raise RuntimeError("Cola a tua chave API Google Gemini na barra lateral para usar a Voz Dramática.")

    client = _make_gemini_client(api_key)
    tts_candidates = get_tts_candidates(api_key)

    direction = voice_direction.strip() or "dramatic thriller tone, expressive and intense"
    tts_prompt = (
        f"Speak ONLY the dialogue below in {lang_hint}, acting with this exact emotional direction ({direction}). "
        f"Do not add extra words:\n{text}"
    )

    errors = []
    audio_bytes = None

    for model_id in tts_candidates[:4]:
        try:
            resp = client.models.generate_content(
                model=model_id,
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
            for candidate in getattr(resp, "candidates", []) or []:
                content = getattr(candidate, "content", None)
                for part in getattr(content, "parts", []) or []:
                    inline = getattr(part, "inline_data", None)
                    data = getattr(inline, "data", None) if inline else None
                    if data:
                        audio_bytes = base64.b64decode(data) if isinstance(data, str) else data
                        break
            if audio_bytes:
                break
        except Exception as e:
            errors.append(f"{model_id}: {str(e)[:160]}")
            continue

    if not audio_bytes:
        raise RuntimeError(
            "O motor de voz Gemini falhou:\n" + "\n".join(errors) +
            "\n\nDica: podes mudar o Motor de Voz na barra lateral para Edge-TTS (grátis) ou ElevenLabs."
        )

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
# MOTOR DE LEGENDAS ASS + VÍDEO (FFMPEG)
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


def format_ass_time(ms: float) -> str:
    total_cs = max(0, int(round(ms / 10.0)))
    hours, rem = divmod(total_cs, 360_000)
    minutes, rem = divmod(rem, 6_000)
    seconds, cs = divmod(rem, 100)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{cs:02d}"


def sanitize_ass_text(text: str) -> str:
    return text.replace("\n", " ").replace("{", "").replace("}", "").strip()


def build_ass_file(characters: list[dict], dialogue_rows: list[tuple[float, float, str, str]], color_by_char: bool) -> str:
    header = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1080",
        "PlayResY: 1920",
        "WrapStyle: 0",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
    ]

    style_map = {}
    for idx, ch in enumerate(characters):
        color = CHAR_SUBTITLE_COLORS[idx % len(CHAR_SUBTITLE_COLORS)] if color_by_char else "&H00FFFFFF"
        style_name = f"Char{idx}"
        style_map[ch["id"]] = style_name
        header.append(
            f"Style: {style_name},DejaVu Sans,58,{color},&H000000FF,&H00000000,&H80000000,"
            "-1,0,0,0,100,100,0,0,1,4,2,2,80,80,260,1"
        )

    header.append(
        "Style: Default,DejaVu Sans,58,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,"
        "-1,0,0,0,100,100,0,0,1,4,2,2,80,80,260,1"
    )
    header += [
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    for start_ms, end_ms, speaker_id, text in dialogue_rows:
        st_name = style_map.get(speaker_id, "Default")
        clean_txt = sanitize_ass_text(text).upper()
        header.append(
            f"Dialogue: 0,{format_ass_time(start_ms)},{format_ass_time(end_ms)},{st_name},,0,0,0,,{clean_txt}"
        )

    return "\n".join(header) + "\n"


def build_zoompan_filter(motion: str, frames: int, fps: int = 30) -> str:
    safe_frames = max(1, frames)
    if motion == "pull_out":
        zp = "zoompan=z='max(1.14-0.0009*on,1.0)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    elif motion == "pan_right":
        zp = f"zoompan=z='1.12':x='(iw-iw/zoom)*(on/{safe_frames})':y='ih/2-(ih/zoom/2)'"
    elif motion == "pan_left":
        zp = f"zoompan=z='1.12':x='(iw-iw/zoom)*(1-on/{safe_frames})':y='ih/2-(ih/zoom/2)'"
    else:
        zp = "zoompan=z='min(zoom+0.0009,1.14)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"

    return (
        "scale=1440:2560:force_original_aspect_ratio=increase,"
        "crop=1440:2560,"
        f"{zp}:d={safe_frames}:s=1080x1920:fps={fps},"
        "format=yuv420p"
    )


def build_suspense_drone(out_audio: Path, duration_sec: float, cwd: Path):
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
    characters: list[dict],
    scenes: list[dict],
    ai_images: dict[int, bytes],
    uploaded_images: dict,
    char_voice_ids: dict[str, str],
    voice_cfg: dict,
    bgm_mode: str,
    bgm_file,
    bgm_volume: float,
    color_by_char: bool,
    watermark: bool,
    progress_bar,
) -> Path:
    job_id = uuid.uuid4().hex[:10]
    job_dir = WORK_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    char_map = {c["id"]: c for c in characters}
    scene_videos = []
    ass_rows: list[tuple[float, float, str, str]] = []
    offset_ms = 0.0
    total = len(scenes)

    for idx, scene in enumerate(scenes):
        prefix = f"scene_{idx + 1:02d}"
        img_path = job_dir / f"{prefix}.jpg"
        clip_vid = job_dir / f"{prefix}_vid.mp4"
        merged_vid = job_dir / f"{prefix}_merged.mp4"

        speaker_id = scene.get("speaker_id") or characters[0]["id"]
        speaker = char_map.get(speaker_id, characters[0])
        speaker_voice_id = char_voice_ids.get(speaker_id) or next(iter(char_voice_ids.values()))

        dialogue = scene.get("dialogue", "").strip()
        emotion = scene.get("emotion", "suspense")
        voice_direction = scene.get("voice_direction", "tense dramatic thriller tone")
        camera_motion = scene.get("camera_motion", "push_in")
        visual_prompt = scene.get("visual_prompt", "")

        if idx in uploaded_images and uploaded_images[idx] is not None:
            Image.open(uploaded_images[idx]).convert("RGB").save(img_path, format="JPEG", quality=92)
        elif idx in ai_images and ai_images[idx]:
            img_path.write_bytes(ai_images[idx])
        else:
            create_placeholder_card(img_path, idx + 1, speaker["name"], visual_prompt)

        progress_bar.progress(
            int((idx / total) * 70) + 2,
            text=f"Cena {idx + 1}/{total}: a gravar fala de {speaker['name']}...",
        )
        engine = voice_cfg["engine"]
        timings = []

        if engine.startswith("Gemini"):
            audio_path = job_dir / f"{prefix}.wav"
            generate_tts_gemini_dramatic(
                text=dialogue,
                voice_direction=voice_direction,
                lang_hint=voice_cfg["lang_hint"],
                voice_name=speaker_voice_id,
                api_key=voice_cfg["gemini_key"],
                out_wav=audio_path,
            )
            if idx < total - 1:
                time.sleep(1.2)
        elif engine.startswith("ElevenLabs"):
            audio_path = job_dir / f"{prefix}.mp3"
            generate_tts_elevenlabs(
                text=dialogue,
                voice_id=speaker_voice_id,
                api_key=voice_cfg["eleven_key"],
                out_mp3=audio_path,
            )
        else:
            audio_path = job_dir / f"{prefix}.mp3"
            timings = asyncio.run(
                generate_tts_edge(dialogue, speaker_voice_id, emotion, audio_path)
            )

        audio_dur = get_duration(audio_path)
        scene_dur = audio_dur + 0.30

        if not timings:
            timings = estimate_weighted_timings(dialogue, audio_dur, words_per_chunk=4)

        for s_ms, e_ms, txt in timings:
            ass_rows.append((offset_ms + s_ms, offset_ms + e_ms, speaker_id, txt))

        fps = 30
        frames = max(1, math.ceil(scene_dur * fps))
        vf = build_zoompan_filter(camera_motion, frames, fps=fps)
        run_cmd(
            [
                "ffmpeg", "-y", "-loop", "1", "-i", img_path.name,
                "-vf", vf, "-t", f"{scene_dur:.3f}",
                "-c:v", "libx264", "-preset", "veryfast", "-an",
                clip_vid.name,
            ],
            cwd=job_dir,
        )

        run_cmd(
            [
                "ffmpeg", "-y",
                "-i", clip_vid.name, "-i", audio_path.name,
                "-af", "apad=pad_dur=0.30",
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
    ass_content = build_ass_file(characters, ass_rows, color_by_char=color_by_char)
    (job_dir / "captions.ass").write_text(ass_content, encoding="utf-8")

    stitched_mp4 = job_dir / "stitched.mp4"
    run_cmd(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", "concat.txt", "-c", "copy", stitched_mp4.name],
        cwd=job_dir,
    )
    total_dur = get_duration(stitched_mp4)
    progress_bar.progress(86, text="A aplicar legendas de diálogo e ambiente sonoro...")

    bgm_path = None
    if bgm_mode == "Atmosfera Suspense Automática (integrada)":
        bgm_path = job_dir / "bgm_auto.m4a"
        build_suspense_drone(bgm_path, total_dur, cwd=job_dir)
    elif bgm_mode == "Carregar música própria (MP3/WAV)" and bgm_file is not None:
        ext = Path(bgm_file.name).suffix or ".mp3"
        bgm_path = job_dir / f"bgm_custom{ext}"
        bgm_path.write_bytes(bgm_file.getvalue())

    filters = ["subtitles=captions.ass"]
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
# ESTADO DA SESSÃO
# ---------------------------------------------------------
if "episode_title" not in st.session_state:
    st.session_state.episode_title = ""
if "characters" not in st.session_state:
    st.session_state.characters = []
if "cast_images" not in st.session_state:
    st.session_state.cast_images = {}
if "scenes" not in st.session_state:
    st.session_state.scenes = []
if "scene_images" not in st.session_state:
    st.session_state.scene_images = {}
if "last_video" not in st.session_state:
    st.session_state.last_video = None
if "script_ver" not in st.session_state:
    st.session_state.script_ver = 0

st.title("🎬 MiniDrama Studio — v4.2 (Elenco Fixo & Diálogos)")
st.caption("Várias personagens com retrato-referência consistente, vozes individuais e diálogo dramático em 9:16.")

if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
    st.error("FFmpeg não encontrado no sistema. Confirma se o ficheiro packages.txt contém 'ffmpeg'.")
    st.stop()

# ---------------------------------------------------------
# BARRA LATERAL
# ---------------------------------------------------------
with st.sidebar:
    st.header("Configurações")
    gemini_key = st.text_input("Chave API Google Gemini", type="password")
    lang_label = st.selectbox("Idioma / Sotaque", list(LANGUAGES.keys()))

    key_models = list_key_models(gemini_key) if gemini_key else {"all": [], "text": [], "image": [], "tts": []}
    preferred_text_model = "Automático"
    preferred_image_model = "Automático"

    with st.expander("🔍 Modelos ativos nesta chave", expanded=False):
        if not gemini_key:
            st.caption("Cola a chave Gemini acima para listar os modelos.")
        elif not key_models["all"]:
            st.warning("Não foi possível listar modelos desta chave (verifica se é válida).")
        else:
            preferred_text_model = st.selectbox(
                "Modelo de Guião (Texto)",
                ["Automático"] + key_models["text"],
            )
            preferred_image_model = st.selectbox(
                "Modelo de Imagens",
                ["Automático"] + key_models["image"],
            )
            st.caption(f"Encontrados: {len(key_models['text'])} texto | {len(key_models['image'])} imagem | {len(key_models['tts'])} voz")
            if not key_models["image"]:
                st.warning("Esta chave não devolveu nenhum modelo de geração de imagem ativo.")

    st.divider()
    st.subheader("🎭 Motor de Vozes do Elenco")
    voice_engine = st.selectbox("Motor de voz", VOICE_ENGINES)
    eleven_key = ""
    if voice_engine.startswith("ElevenLabs"):
        eleven_key = st.text_input("Chave API ElevenLabs", type="password")
    st.caption("A voz de cada ator é escolhida individualmente no Passo 2 (Elenco).")

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
    st.subheader("💬 Estilo do Episódio")
    color_by_char = st.checkbox("Cor de legenda diferente por personagem", value=True)
    watermark = st.checkbox("Incluir marca d'água (plano grátis)", value=True)

# ---------------------------------------------------------
# PASSO 1: IDEIA DO EPISÓDIO
# ---------------------------------------------------------
st.subheader("1. Ideia do Episódio")
c1, c2, c3, c4 = st.columns([3, 1.3, 1, 1])
with c1:
    premise = st.text_input(
        "Premissa do mini-drama",
        value="Uma estagiária confronta o diretor financeiro à meia-noite depois de descobrir contratos falsificados no cofre.",
    )
with c2:
    genre = st.selectbox("Género", ["Suspense Corporativo", "Vingança", "Drama Familiar", "Mistério", "Romance Tenso"])
with c3:
    num_chars = st.selectbox("Personagens", [2, 3], index=0)
with c4:
    num_scenes = st.slider("N.º de cenas", 4, 8, 4)

b1, b2 = st.columns([1, 1])
with b1:
    if st.button("✨ Gerar Elenco + Guião de Diálogo (Gemini)", type="primary", use_container_width=True):
        if not gemini_key:
            st.warning("Cola a tua chave Gemini na barra lateral ou carrega o episódio de demonstração.")
        else:
            with st.spinner("A criar o elenco e o diálogo entre personagens..."):
                try:
                    ep = generate_episode_script_gemini(
                        gemini_key, premise, genre, lang_label, num_scenes, num_chars, preferred_text_model
                    )
                    st.session_state.episode_title = ep.get("title", "Novo Episódio")
                    st.session_state.characters = ep["characters"]
                    st.session_state.scenes = ep["scenes"]
                    st.session_state.cast_images = {}
                    st.session_state.scene_images = {}
                    st.session_state.last_video = None
                    st.session_state.script_ver += 1
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao gerar guião: {e}")
with b2:
    if st.button("⚡ Carregar Episódio de Demonstração (2 Personagens)", use_container_width=True):
        st.session_state.episode_title = DEMO_EPISODE["title"]
        st.session_state.characters = [dict(c) for c in DEMO_EPISODE["characters"]]
        st.session_state.scenes = [dict(s) for s in DEMO_EPISODE["scenes"]]
        st.session_state.cast_images = {}
        st.session_state.scene_images = {}
        st.session_state.last_video = None
        st.session_state.script_ver += 1
        st.rerun()

# ---------------------------------------------------------
# PASSO 2: ELENCO FIXO (RETRATOS + VOZES INDIVIDUAIS)
# ---------------------------------------------------------
ver = st.session_state.script_ver
voice_catalog = get_voice_catalog(voice_engine)
voice_labels_list = list(voice_catalog.keys())
char_voice_ids: dict[str, str] = {}
uploaded_cast: dict[str, bytes] = {}

if st.session_state.characters:
    st.divider()
    st.subheader(f"2. Elenco Fixo — {st.session_state.episode_title}")
    st.caption(
        "Gera primeiro os retratos-referência do elenco. No Passo 3, a IA vai usar exatamente estes rostos em todas as cenas."
    )

    if st.button("🎭 Gerar Retratos-Referência de Todo o Elenco (Gemini)", type="primary"):
        if not gemini_key:
            st.warning("Cola a tua chave Gemini na barra lateral para gerar os retratos.")
        else:
            pbar = st.progress(0, text="A fotografar o elenco...")
            n_ch = len(st.session_state.characters)
            ok = True
            for ci, ch in enumerate(st.session_state.characters):
                pbar.progress(int((ci / n_ch) * 100), text=f"A gerar retrato de {ch['name']}...")
                try:
                    st.session_state.cast_images[ch["id"]] = generate_portrait_gemini(
                        ch, gemini_key, preferred_image_model
                    )
                    if ci < n_ch - 1:
                        time.sleep(1.0)
                except Exception as e:
                    ok = False
                    pbar.empty()
                    st.error(str(e))
                    break
            if ok:
                pbar.progress(100, text="Elenco pronto!")
                st.rerun()

    cols = st.columns(len(st.session_state.characters))
    eng_short = get_engine_short_name(voice_engine)

    for ci, ch in enumerate(st.session_state.characters):
        cid = ch["id"]
        with cols[ci]:
            with st.container(border=True):
                st.markdown(f"### {ch['name']} — *{ch.get('role', '')}*")
                ch["name"] = st.text_input("Nome", value=ch["name"], key=f"cname_{ver}_{cid}")

                default_v = pick_default_voice_label(voice_engine, ch.get("gender", "female"), ci)
                v_idx = voice_labels_list.index(default_v) if default_v in voice_labels_list else 0
                chosen_v_label = st.selectbox(
                    "Voz desta personagem",
                    voice_labels_list,
                    index=v_idx,
                    key=f"cvoice_{ver}_{eng_short}_{cid}",
                )
                char_voice_ids[cid] = voice_catalog[chosen_v_label]

                ch["visual_profile"] = st.text_area(
                    "Aparência fixa (inglês)",
                    value=ch.get("visual_profile", ""),
                    key=f"cvis_{ver}_{cid}",
                    height=85,
                )

                up_p = st.file_uploader(
                    "Ou carregar foto-referência",
                    type=["jpg", "jpeg", "png"],
                    key=f"cup_{ver}_{cid}",
                )
                if up_p is not None:
                    img_b = normalize_image_bytes(up_p.getvalue())
                    uploaded_cast[cid] = img_b
                    st.image(img_b, caption=f"Referência de {ch['name']} (Upload)", width=180)
                elif cid in st.session_state.cast_images:
                    st.image(st.session_state.cast_images[cid], caption=f"Referência de {ch['name']} (IA)", width=180)
                else:
                    st.info("Sem retrato-referência ainda.")

                if st.button(f"🔄 Gerar / Refazer retrato de {ch['name']}", key=f"cregen_{ver}_{cid}"):
                    with st.spinner(f"A gerar retrato de {ch['name']}..."):
                        try:
                            st.session_state.cast_images[cid] = generate_portrait_gemini(
                                ch, gemini_key, preferred_image_model
                            )
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))

active_cast_portraits = dict(st.session_state.cast_images)
active_cast_portraits.update(uploaded_cast)
char_map = {c["id"]: c for c in st.session_state.characters}
char_ids_list = [c["id"] for c in st.session_state.characters]

# ---------------------------------------------------------
# PASSO 3: STORYBOARD COM CONSISTÊNCIA VISUAL
# ---------------------------------------------------------
if st.session_state.scenes and st.session_state.characters:
    st.divider()
    st.subheader("3. Storyboard de Diálogos (com Referência do Elenco)")

    if not active_cast_portraits:
        st.info("Dica: gera os retratos no Passo 2 antes de gerar as cenas para que os rostos fiquem consistentes entre planos.")

    if st.button("🎨 Gerar Imagens de Todas as Cenas (com Elenco Fixo)", type="primary"):
        if not gemini_key:
            st.warning("Cola a tua chave Gemini na barra lateral.")
        else:
            img_bar = st.progress(0, text="A compor cenas com o elenco...")
            total_s = len(st.session_state.scenes)
            ok = True
            for i, scene in enumerate(st.session_state.scenes):
                img_bar.progress(int((i / total_s) * 100), text=f"A gerar Cena {i + 1}/{total_s}...")
                refs = []
                for cid in scene.get("characters_in_scene", []):
                    if cid in char_map and cid in active_cast_portraits:
                        refs.append((char_map[cid]["name"], char_map[cid]["visual_profile"], active_cast_portraits[cid]))
                try:
                    st.session_state.scene_images[i] = generate_scene_image_with_refs_gemini(
                        scene.get("visual_prompt", ""), gemini_key, refs, preferred_image_model
                    )
                    if i < total_s - 1:
                        time.sleep(1.0)
                except Exception as e:
                    ok = False
                    img_bar.empty()
                    st.error(f"Cena {i + 1}: {e}")
                    break
            if ok:
                img_bar.progress(100, text="Storyboard completo!")
                st.rerun()

    uploaded_images = {}
    motion_keys = list(CAMERA_MOTIONS.keys())
    emo_keys = list(EMOTION_PROSODY.keys())

    for i, scene in enumerate(st.session_state.scenes):
        spk_id = scene.get("speaker_id")
        if spk_id not in char_map:
            spk_id = char_ids_list[0]
            scene["speaker_id"] = spk_id
        spk_name = char_map[spk_id]["name"]

        with st.expander(f"Cena {i + 1} — Fala: {spk_name}", expanded=True):
            c_txt, c_prev = st.columns([2, 1])
            with c_txt:
                s_col1, s_col2 = st.columns([1, 1.5])
                with s_col1:
                    scene["speaker_id"] = st.selectbox(
                        "Quem fala nesta cena",
                        char_ids_list,
                        index=char_ids_list.index(spk_id),
                        format_func=lambda cid: f"{char_map[cid]['name']} ({char_map[cid].get('role', '')})",
                        key=f"spk_{ver}_{i}",
                    )
                with s_col2:
                    raw_in_scene = [cid for cid in scene.get("characters_in_scene", [spk_id]) if cid in char_map]
                    if not raw_in_scene:
                        raw_in_scene = [scene["speaker_id"]]
                    scene["characters_in_scene"] = st.multiselect(
                        "Personagens visíveis no plano",
                        char_ids_list,
                        default=raw_in_scene,
                        format_func=lambda cid: char_map[cid]["name"],
                        key=f"inscene_{ver}_{i}",
                    )

                scene["dialogue"] = st.text_area(
                    "Fala da personagem",
                    value=scene.get("dialogue", ""),
                    key=f"diag_{ver}_{i}",
                    height=68,
                )

                d1, d2, d3 = st.columns([2, 1, 1.2])
                with d1:
                    scene["voice_direction"] = st.text_input(
                        "🎭 Direção de representação",
                        value=scene.get("voice_direction", "tense dramatic delivery"),
                        key=f"dir_{ver}_{i}",
                    )
                with d2:
                    cur_emo = scene.get("emotion", "suspense")
                    scene["emotion"] = st.selectbox(
                        "Intensidade",
                        emo_keys,
                        index=emo_keys.index(cur_emo) if cur_emo in emo_keys else 0,
                        key=f"emo_{ver}_{i}",
                    )
                with d3:
                    cur_mot = scene.get("camera_motion", "push_in")
                    scene["camera_motion"] = st.selectbox(
                        "Movimento de câmara",
                        motion_keys,
                        index=motion_keys.index(cur_mot) if cur_mot in motion_keys else 0,
                        format_func=lambda m: CAMERA_MOTIONS[m],
                        key=f"mot_{ver}_{i}",
                    )

                scene["visual_prompt"] = st.text_area(
                    "Prompt visual da cena (inglês)",
                    value=scene.get("visual_prompt", ""),
                    key=f"vis_{ver}_{i}",
                    height=68,
                )

                linked_names = [
                    char_map[cid]["name"]
                    for cid in scene["characters_in_scene"]
                    if cid in active_cast_portraits
                ]
                if linked_names:
                    st.caption(f"🔗 Retratos-referência ligados a esta cena: **{', '.join(linked_names)}**")
                else:
                    st.caption("⚠️ Sem retrato-referência ligado (gera o retrato no Passo 2 para manter o rosto fixo).")

                if st.button(f"🔄 Gerar / Regenerar Cena {i + 1}", key=f"regen_{ver}_{i}"):
                    with st.spinner(f"A gerar imagem da Cena {i + 1} com o elenco..."):
                        try:
                            refs = [
                                (char_map[cid]["name"], char_map[cid]["visual_profile"], active_cast_portraits[cid])
                                for cid in scene["characters_in_scene"]
                                if cid in char_map and cid in active_cast_portraits
                            ]
                            st.session_state.scene_images[i] = generate_scene_image_with_refs_gemini(
                                scene["visual_prompt"], gemini_key, refs, preferred_image_model
                            )
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro na Cena {i + 1}: {e}")

            with c_prev:
                if i in st.session_state.scene_images:
                    st.image(st.session_state.scene_images[i], caption=f"Cena {i + 1} (IA)", width=210)
                else:
                    st.info("Ainda sem imagem gerada.")
                uploaded_images[i] = st.file_uploader(
                    "Substituir manualmente (JPG/PNG)",
                    type=["jpg", "jpeg", "png"],
                    key=f"img_{ver}_{i}",
                )

    # ---------------------------------------------------------
    # PASSO 4: RENDERIZAR EPISÓDIO
    # ---------------------------------------------------------
    st.divider()
    st.subheader("4. Produzir Mini-Drama (9:16)")
    if st.button("🎥 Gerar Episódio Completo com Diálogo", type="primary"):
        bar = st.progress(5, text="A iniciar estúdio de produção...")
        try:
            voice_cfg = {
                "engine": voice_engine,
                "lang_hint": LANGUAGES[lang_label],
                "gemini_key": gemini_key,
                "eleven_key": eleven_key,
            }
            out_path = render_episode(
                characters=st.session_state.characters,
                scenes=st.session_state.scenes,
                ai_images=st.session_state.scene_images,
                uploaded_images=uploaded_images,
                char_voice_ids=char_voice_ids,
                voice_cfg=voice_cfg,
                bgm_mode=bgm_mode,
                bgm_file=bgm_file,
                bgm_volume=bgm_volume,
                color_by_char=color_by_char,
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
        st.success("Episódio multi-personagem pronto em 1080×1920!")
        with open(st.session_state.last_video, "rb") as f:
            st.download_button(
                "⬇️ Descarregar MP4",
                data=f.read(),
                file_name="minidrama_episodio_v4.mp4",
                mime="video/mp4",
                type="primary",
            )
