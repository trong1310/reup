from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict
import requests
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = BASE_DIR / ".env"


def mask_key(val: str | None) -> str:
    if not val or not val.strip():
        return ""
    val = val.strip()
    if len(val) <= 8:
        return "********"
    return f"{val[:4]}...{val[-4:]}"


def load_current_env():
    if ENV_FILE.exists():
        load_dotenv(ENV_FILE, override=True)


def get_all_settings() -> Dict[str, Any]:
    load_current_env()
    groq_key = os.getenv("GROQ_API_KEY", "")
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    openai_key = os.getenv("OPENAI_API_KEY", "")
    eleven_key = os.getenv("ELEVENLABS_API_KEY", "")
    deepgram_key = os.getenv("DEEPGRAM_API_KEY", "")
    hf_token = os.getenv("HF_TOKEN", "")

    return {
        "groq_api_key": mask_key(groq_key),
        "gemini_api_key": mask_key(gemini_key),
        "openai_api_key": mask_key(openai_key),
        "elevenlabs_api_key": mask_key(eleven_key),
        "deepgram_api_key": mask_key(deepgram_key),
        "hf_token": mask_key(hf_token),
        
        "has_groq": bool(groq_key.strip()),
        "has_gemini": bool(gemini_key.strip()),
        "has_openai": bool(openai_key.strip()),
        "has_elevenlabs": bool(eleven_key.strip()),
        "has_deepgram": bool(deepgram_key.strip()),
        "has_hf": bool(hf_token.strip()),

        "stt_provider": os.getenv("STT_PROVIDER", "auto"),
        "translate_provider": os.getenv("TRANSLATE_PROVIDER", "auto"),
        "whisper_model": os.getenv("WHISPER_MODEL", "base"),
        "whisper_device": os.getenv("WHISPER_DEVICE", "cpu"),
        "whisper_compute_type": os.getenv("WHISPER_COMPUTE_TYPE", "int8"),
        "tts_rate": os.getenv("TTS_RATE", "170"),
    }


def save_settings_to_env(updates: Dict[str, Any]) -> Dict[str, Any]:
    load_current_env()

    key_map = {
        "groq_api_key": "GROQ_API_KEY",
        "gemini_api_key": "GEMINI_API_KEY",
        "openai_api_key": "OPENAI_API_KEY",
        "elevenlabs_api_key": "ELEVENLABS_API_KEY",
        "deepgram_api_key": "DEEPGRAM_API_KEY",
        "hf_token": "HF_TOKEN",
        "stt_provider": "STT_PROVIDER",
        "translate_provider": "TRANSLATE_PROVIDER",
        "whisper_model": "WHISPER_MODEL",
        "whisper_device": "WHISPER_DEVICE",
        "whisper_compute_type": "WHISPER_COMPUTE_TYPE",
        "tts_rate": "TTS_RATE",
    }

    current_lines: list[str] = []
    if ENV_FILE.exists():
        current_lines = ENV_FILE.read_text(encoding="utf-8").splitlines()

    env_dict: dict[str, str] = {}
    for line in current_lines:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env_dict[k.strip()] = v.strip()

    for ui_key, env_var in key_map.items():
        if ui_key in updates:
            val = str(updates[ui_key]).strip()
            # If user sent masked string like "sk-1...cdef", don't change existing value
            if "..." in val and val == mask_key(os.getenv(env_var, "")):
                continue
            if val == "__CLEAR__":
                env_dict.pop(env_var, None)
                os.environ.pop(env_var, None)
            elif val != "":
                env_dict[env_var] = val
                os.environ[env_var] = val
            elif ui_key.endswith("_api_key") or ui_key == "hf_token":
                # Empty string on API key means keep unchanged if not explicitly cleared
                pass
            else:
                env_dict[env_var] = val
                os.environ[env_var] = val

    # Format new .env content
    new_content_lines = [
        "# AI Video Dubber Configuration",
        f"WHISPER_MODEL={env_dict.get('WHISPER_MODEL', 'base')}",
        f"WHISPER_DEVICE={env_dict.get('WHISPER_DEVICE', 'cpu')}",
        f"WHISPER_COMPUTE_TYPE={env_dict.get('WHISPER_COMPUTE_TYPE', 'int8')}",
        f"TTS_RATE={env_dict.get('TTS_RATE', '170')}",
        "",
        "# 3rd Party Acceleration APIs",
        f"STT_PROVIDER={env_dict.get('STT_PROVIDER', 'auto')}",
        f"TRANSLATE_PROVIDER={env_dict.get('TRANSLATE_PROVIDER', 'auto')}",
        f"GROQ_API_KEY={env_dict.get('GROQ_API_KEY', '')}",
        f"GEMINI_API_KEY={env_dict.get('GEMINI_API_KEY', '')}",
        f"OPENAI_API_KEY={env_dict.get('OPENAI_API_KEY', '')}",
        f"ELEVENLABS_API_KEY={env_dict.get('ELEVENLABS_API_KEY', '')}",
        f"DEEPGRAM_API_KEY={env_dict.get('DEEPGRAM_API_KEY', '')}",
        f"HF_TOKEN={env_dict.get('HF_TOKEN', '')}",
        "HF_XET_HIGH_PERFORMANCE=1",
    ]

    ENV_FILE.write_text("\n".join(new_content_lines) + "\n", encoding="utf-8")
    return get_all_settings()


def test_api_key(provider: str, key: str | None = None) -> Dict[str, Any]:
    load_current_env()
    p = provider.lower().strip()
    
    # If no key provided, get from env
    if not key or "..." in key:
        env_map = {
            "groq": "GROQ_API_KEY",
            "gemini": "GEMINI_API_KEY",
            "openai": "OPENAI_API_KEY",
            "elevenlabs": "ELEVENLABS_API_KEY",
            "deepgram": "DEEPGRAM_API_KEY",
            "huggingface": "HF_TOKEN",
            "hf": "HF_TOKEN",
        }
        key = os.getenv(env_map.get(p, ""), "").strip()

    if not key:
        return {"ok": False, "error": f"Chưa nhập API Key cho {provider}"}

    start_t = time.time()
    try:
        if p == "groq":
            res = requests.get(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {key}"},
                timeout=10,
            )
            lat = int((time.time() - start_t) * 1000)
            if res.status_code == 200:
                return {"ok": True, "latency_ms": lat, "message": "Kết nối Groq Cloud thành công (Whisper & Llama 3 sẵn sàng)"}
            else:
                return {"ok": False, "error": f"Lỗi Groq ({res.status_code}): {res.text[:200]}"}

        elif p == "gemini":
            res = requests.get(
                f"https://generativelanguage.googleapis.com/v1beta/models?key={key}",
                timeout=10,
            )
            lat = int((time.time() - start_t) * 1000)
            if res.status_code == 200:
                return {"ok": True, "latency_ms": lat, "message": "Kết nối Google Gemini thành công (Flash & Pro sẵn sàng)"}
            else:
                return {"ok": False, "error": f"Lỗi Gemini ({res.status_code}): {res.text[:200]}"}

        elif p == "openai":
            res = requests.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {key}"},
                timeout=10,
            )
            lat = int((time.time() - start_t) * 1000)
            if res.status_code == 200:
                return {"ok": True, "latency_ms": lat, "message": "Kết nối OpenAI thành công (Whisper-1 & GPT-4o & TTS sẵn sàng)"}
            else:
                return {"ok": False, "error": f"Lỗi OpenAI ({res.status_code}): {res.text[:200]}"}

        elif p == "elevenlabs":
            res = requests.get(
                "https://api.elevenlabs.io/v1/voices",
                headers={"xi-api-key": key},
                timeout=10,
            )
            lat = int((time.time() - start_t) * 1000)
            if res.status_code == 200:
                voices_cnt = len(res.json().get("voices", []))
                return {"ok": True, "latency_ms": lat, "message": f"Kết nối ElevenLabs thành công ({voices_cnt} giọng đọc)"}
            else:
                return {"ok": False, "error": f"Lỗi ElevenLabs ({res.status_code}): {res.text[:200]}"}

        elif p == "deepgram":
            res = requests.get(
                "https://api.deepgram.com/v1/projects",
                headers={"Authorization": f"Token {key}"},
                timeout=10,
            )
            lat = int((time.time() - start_t) * 1000)
            if res.status_code == 200:
                return {"ok": True, "latency_ms": lat, "message": "Kết nối Deepgram thành công"}
            else:
                return {"ok": False, "error": f"Lỗi Deepgram ({res.status_code}): {res.text[:200]}"}

        elif p in ("huggingface", "hf"):
            res = requests.get(
                "https://huggingface.co/api/whoami-v2",
                headers={"Authorization": f"Bearer {key}"},
                timeout=10,
            )
            lat = int((time.time() - start_t) * 1000)
            if res.status_code == 200:
                username = res.json().get("name", "User")
                return {"ok": True, "latency_ms": lat, "message": f"Kết nối Hugging Face thành công (Tài khoản: {username})"}
            else:
                return {"ok": False, "error": f"Lỗi Hugging Face ({res.status_code}): {res.text[:200]}"}

        else:
            return {"ok": False, "error": f"Nhà cung cấp '{provider}' không được hỗ trợ"}

    except Exception as e:
        return {"ok": False, "error": f"Không thể kết nối đến {provider}: {str(e)}"}
