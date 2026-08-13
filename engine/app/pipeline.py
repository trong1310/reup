from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any

import edge_tts
import numpy as np
import pyttsx3
import requests
import yt_dlp
from deep_translator import GoogleTranslator
from faster_whisper import WhisperModel
from gtts import gTTS
from pydub import AudioSegment

BASE_DIR = Path(__file__).resolve().parents[1]
_vieneu_instance = None


def get_vieneu_instance():
    global _vieneu_instance
    if _vieneu_instance is None:
        from vieneu import Vieneu
        _vieneu_instance = Vieneu(mode="v3turbo")
    return _vieneu_instance


def normalize_lang_code(code: str | None) -> str:
    if not code or code.lower() in ("auto", ""):
        return "auto"
    c = code.lower().strip()
    mapping = {
        "zh": "zh-CN",
        "zh-cn": "zh-CN",
        "zh-tw": "zh-TW",
        "en": "en",
        "vi": "vi",
        "ja": "ja",
        "ko": "ko",
        "fr": "fr",
        "es": "es",
        "de": "de",
        "ru": "ru",
    }
    return mapping.get(c, c)


def get_media_duration(file_path: Path) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(file_path)
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0 and res.stdout.strip():
            return float(res.stdout.strip())
    except Exception:
        pass
    return 0.0


class JobManager:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.jobs: dict[str, dict[str, Any]] = {}
        self.lock = threading.Lock()
        self._whisper: WhisperModel | None = None
        self.tts = HybridTTS()

    def create(self, job_id: str, request: dict[str, Any]):
        with self.lock:
            self.jobs[job_id] = {
                "id": job_id,
                "job_id": job_id,
                "status": "queued",
                "progress": 0,
                "stage": "queued",
                "request": request,
                "output": None,
                "error": None,
            }

    def get(self, job_id: str):
        with self.lock:
            return self.jobs.get(job_id)

    def update(self, job_id: str, **values):
        with self.lock:
            if job_id in self.jobs:
                self.jobs[job_id].update(values)

    async def run(self, job_id: str):
        try:
            job = self.get(job_id)
            req = job["request"]
            work = self.data_dir / job_id
            work.mkdir(parents=True, exist_ok=True)

            self.update(job_id, status="running", stage="download", progress=5)
            video = download_video(req["url"], work)

            self.update(job_id, stage="extract_audio", progress=20)
            source_audio = work / "source.wav"
            ffmpeg_extract_audio(video, source_audio)

            self.update(job_id, stage="transcribe", progress=40)
            transcript = self.transcribe(source_audio, req.get("source_language", "auto"))

            (work / "transcript.json").write_text(
                json.dumps(transcript, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            self.update(job_id, stage="translate", progress=60)
            translated = translate_segments(
                transcript,
                req.get("source_language", "auto"),
                req.get("target_language", "vi"),
            )

            (work / "translated.json").write_text(
                json.dumps(translated, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            srt_file = work / "subtitles.srt"
            generate_srt(translated.get("segments", []), srt_file)

            self.update(job_id, stage="tts", progress=70)
            speech = work / "dub.mp3"

            def on_tts_progress(idx, total):
                prog = 70 + int((idx / max(1, total)) * 18)
                self.update(job_id, stage="tts", progress=prog)

            self.tts.synthesize_segments(
                translated,
                speech,
                voice_id=req.get("voice_id"),
                target_language=req.get("target_language", "vi"),
                source_video=video,
                progress_callback=on_tts_progress,
            )

            self.update(job_id, stage="mix_and_render", progress=90)
            output = work / "output.mp4"

            mix_audio(video, speech, output)

            self.update(
                job_id,
                status="completed",
                stage="done",
                progress=100,
                output=str(output),
            )
        except Exception as exc:
            self.update(
                job_id,
                status="failed",
                stage="error",
                error=f"{type(exc).__name__}: {exc}",
            )

    def transcribe(self, audio: Path, language: str):
        if self._whisper is None:
            model_name = os.getenv("WHISPER_MODEL", "base")
            device = os.getenv("WHISPER_DEVICE", "cpu")
            compute = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
            self._whisper = WhisperModel(
                model_name,
                device=device,
                compute_type=compute,
            )

        lang = None if language.lower() in ("auto", "") else language
        segments, info = self._whisper.transcribe(
            str(audio),
            language=lang,
            vad_filter=True,
        )

        result = []
        for segment in segments:
            result.append(
                {
                    "start": float(segment.start),
                    "end": float(segment.end),
                    "text": segment.text.strip(),
                }
            )
        return {
            "language": info.language,
            "language_probability": float(info.language_probability),
            "segments": result,
        }


class HybridTTS:
    def __init__(self):
        self.engine_lock = threading.Lock()

    def list_voices(self):
        voices = [
            # 1. VieNeu-TTS AI Voices (Cao cấp - Offline)
            {"id": "vieneu:ngoc_huyen", "name": "🌟 Ngọc Huyền v2 (Giọng Đọc AI Cao Cấp - Vbee Clone)", "languages": ["vi"], "category": "VieNeu AI"},
            {"id": "vieneu:Ngọc Lan", "name": "🌸 Ngọc Lan (Giọng Nữ Dịu Dàng - VieNeu AI)", "languages": ["vi"], "category": "VieNeu AI"},
            {"id": "vieneu:Trúc Ly", "name": "✨ Trúc Ly (Giọng Nữ Trẻ Trung - VieNeu AI)", "languages": ["vi"], "category": "VieNeu AI"},
            {"id": "vieneu:Mỹ Duyên", "name": "🌺 Mỹ Duyên (Giọng Nữ Mượt Mà - VieNeu AI)", "languages": ["vi"], "category": "VieNeu AI"},
            {"id": "vieneu:Ngọc Linh", "name": "🌼 Ngọc Linh (Giọng Nữ Tươi Sáng - VieNeu AI)", "languages": ["vi"], "category": "VieNeu AI"},
            {"id": "vieneu:Gia Bảo", "name": "🎙️ Gia Bảo (Giọng Nam Trầm Ấm - VieNeu AI)", "languages": ["vi"], "category": "VieNeu AI"},
            {"id": "vieneu:Thái Sơn", "name": "⚡ Thái Sơn (Giọng Nam Chắc Khỏe - VieNeu AI)", "languages": ["vi"], "category": "VieNeu AI"},
            {"id": "vieneu:Đức Trí", "name": "📘 Đức Trí (Giọng Nam Rõ Ràng - VieNeu AI)", "languages": ["vi"], "category": "VieNeu AI"},
            {"id": "vieneu:Xuân Vĩnh", "name": "🎉 Xuân Vĩnh (Giọng Nam Vui Tươi - VieNeu AI)", "languages": ["vi"], "category": "VieNeu AI"},
            {"id": "vieneu:Trọng Hữu", "name": "📜 Trọng Hữu (Giọng Nam Uyên Bác - VieNeu AI)", "languages": ["vi"], "category": "VieNeu AI"},
            {"id": "vieneu:Bình An", "name": "🌿 Bình An (Giọng Nam Điềm Đạm - VieNeu AI)", "languages": ["vi"], "category": "VieNeu AI"},

            # 2. Microsoft Edge-TTS Neural Voices
            {"id": "vi-VN-HoaiMyNeural", "name": "Hoài My (Microsoft Edge-TTS - Nữ)", "languages": ["vi"], "category": "Edge Neural"},
            {"id": "vi-VN-NamMinhNeural", "name": "Nam Minh (Microsoft Edge-TTS - Nam)", "languages": ["vi"], "category": "Edge Neural"},
            {"id": "en-US-JennyNeural", "name": "Jenny (Microsoft Edge-TTS - English US)", "languages": ["en"], "category": "Edge Neural"},
            {"id": "en-US-GuyNeural", "name": "Guy (Microsoft Edge-TTS - English US)", "languages": ["en"], "category": "Edge Neural"},
            {"id": "zh-CN-XiaoxiaoNeural", "name": "Xiaoxiao (Microsoft Edge-TTS - Chinese)", "languages": ["zh"], "category": "Edge Neural"},
            {"id": "ja-JP-NanamiNeural", "name": "Nanami (Microsoft Edge-TTS - Japanese)", "languages": ["ja"], "category": "Edge Neural"},
            {"id": "ko-KR-SunHiNeural", "name": "Sun-Hi (Microsoft Edge-TTS - Korean)", "languages": ["ko"], "category": "Edge Neural"},

            # 3. Google AI Voices
            {"id": "gtts_vi", "name": "Google AI Voice (Tiếng Việt)", "languages": ["vi"], "category": "Google AI"},
            {"id": "gtts_en", "name": "Google AI Voice (English)", "languages": ["en"], "category": "Google AI"},
            {"id": "gtts_zh", "name": "Google AI Voice (Chinese)", "languages": ["zh"], "category": "Google AI"},
        ]

        with self.engine_lock:
            try:
                engine = pyttsx3.init()
                for v in engine.getProperty("voices"):
                    voices.append(
                        {
                            "id": v.id,
                            "name": f"Local OS: {getattr(v, 'name', v.id)}",
                            "languages": [str(x) for x in getattr(v, "languages", [])],
                            "category": "Local OS",
                        }
                    )
                engine.stop()
            except Exception:
                pass
        return voices

    def synthesize_segments(
        self,
        translated: dict,
        output: Path,
        voice_id: str | None = None,
        target_language: str = "vi",
        source_video: Path | None = None,
        progress_callback: Any = None,
    ):
        segments = translated.get("segments", [])
        valid_segments = [s for s in segments if s.get("text", "").strip()]
        if not valid_segments:
            raise RuntimeError("No translated speech was produced")

        # 1. Determine timeline duration
        total_duration = 0.0
        if source_video and source_video.exists():
            total_duration = get_media_duration(source_video)
        if total_duration <= 0:
            total_duration = max(float(s.get("end", 0.0)) for s in valid_segments) + 3.0

        total_ms = int(total_duration * 1000) + 1500
        dubbed_track = AudioSegment.silent(duration=total_ms)

        target_voice = voice_id or ("vieneu:ngoc_huyen" if target_language == "vi" else "gtts_" + target_language)
        temp_dir = output.parent / "temp_segments"
        temp_dir.mkdir(parents=True, exist_ok=True)

        # Pre-load VieNeu instance if used
        tts_vieneu = None
        ref_audio = None
        if target_voice.startswith("vieneu:"):
            try:
                tts_vieneu = get_vieneu_instance()
                voice_choice = target_voice.split(":", 1)[1]
                if voice_choice == "ngoc_huyen":
                    ref_audio = BASE_DIR / "voices" / "ngoc_huyen_ref.wav"
                    if not ref_audio.exists():
                        ref_audio = Path("voices") / "ngoc_huyen_ref.wav"
            except Exception as e:
                print(f"Failed to load Vieneu ({e}), will fallback...")

        total_count = len(valid_segments)
        for idx, seg in enumerate(valid_segments, start=1):
            text = seg.get("text", "").strip()
            start_ms = max(0, int(float(seg.get("start", 0.0)) * 1000))
            end_ms = int(float(seg.get("end", 0.0)) * 1000)
            target_dur_ms = max(500, end_ms - start_ms)

            seg_out = temp_dir / f"seg_{idx}.wav"
            success = False

            # Option A: VieNeu-TTS
            if tts_vieneu and target_voice.startswith("vieneu:"):
                try:
                    voice_choice = target_voice.split(":", 1)[1]
                    if voice_choice == "ngoc_huyen" and ref_audio and ref_audio.exists():
                        audio = tts_vieneu.infer(text=text, ref_audio=str(ref_audio))
                    else:
                        audio = tts_vieneu.infer(text=text, voice=voice_choice)
                    tts_vieneu.save(audio, str(seg_out))
                    if seg_out.exists() and seg_out.stat().st_size > 100:
                        success = True
                except Exception as e:
                    print(f"Vieneu seg {idx} error: {e}")

            # Option B: Microsoft Edge-TTS
            if not success and (target_voice.startswith("vi-VN-") or target_voice.startswith("en-US-") or target_voice.startswith("zh-CN-") or target_voice.startswith("ja-JP-") or target_voice.startswith("ko-KR-")):
                try:
                    async def _gen_edge():
                        communicate = edge_tts.Communicate(text, target_voice)
                        await communicate.save(str(seg_out))
                    asyncio.run(_gen_edge())
                    if seg_out.exists() and seg_out.stat().st_size > 100:
                        success = True
                except Exception as e:
                    print(f"Edge seg {idx} error: {e}")

            # Option C: Local OS SAPI5 (pyttsx3)
            if not success and (target_voice.startswith("HKEY_") or "TTS_MS_" in target_voice):
                with self.engine_lock:
                    try:
                        engine = pyttsx3.init()
                        engine.setProperty("voice", target_voice)
                        engine.setProperty("rate", int(os.getenv("TTS_RATE", "170")))
                        engine.save_to_file(text, str(seg_out))
                        engine.runAndWait()
                        engine.stop()
                        if seg_out.exists() and seg_out.stat().st_size > 100:
                            success = True
                    except Exception as e:
                        print(f"pyttsx3 seg {idx} error: {e}")

            # Option D: Google AI Voice (gTTS fallback)
            if not success:
                try:
                    lang = normalize_lang_code(target_language)
                    if lang == "auto":
                        lang = "vi"
                    tts_g = gTTS(text=text, lang=lang)
                    tts_g.save(str(seg_out))
                    if seg_out.exists() and seg_out.stat().st_size > 100:
                        success = True
                except Exception as e:
                    print(f"gTTS seg {idx} error: {e}")

            if success and seg_out.exists():
                try:
                    seg_audio = AudioSegment.from_file(str(seg_out))
                    actual_dur_ms = len(seg_audio)

                    # If the translated sentence is longer than speaking duration, speed it up smoothly with atempo
                    if actual_dur_ms > target_dur_ms * 1.15 and target_dur_ms > 600:
                        speed = min(1.35, actual_dur_ms / target_dur_ms)
                        fast_out = temp_dir / f"seg_{idx}_fast.wav"
                        run_ffmpeg(["-y", "-i", str(seg_out), "-filter:a", f"atempo={speed:.2f}", str(fast_out)])
                        if fast_out.exists() and fast_out.stat().st_size > 100:
                            seg_audio = AudioSegment.from_file(str(fast_out))
                            fast_out.unlink(missing_ok=True)

                    # Overlay at the EXACT start millisecond of the character
                    dubbed_track = dubbed_track.overlay(seg_audio, position=start_ms)
                except Exception as e:
                    print(f"Overlay seg {idx} error: {e}")

                seg_out.unlink(missing_ok=True)

            if progress_callback:
                progress_callback(idx, total_count)

        # Cleanup temp directory
        shutil.rmtree(temp_dir, ignore_errors=True)

        # Export synchronized audio track
        dubbed_track.export(str(output), format="mp3", bitrate="192k")
        if not output.exists() or output.stat().st_size == 0:
            raise RuntimeError("TTS engine failed to create synchronized audio track")


def extract_douyin_video_id(url: str) -> str | None:
    m = re.search(r'modal_id=(\d+)', url)
    if m:
        return m.group(1)
    m = re.search(r'/(?:video|share/video|modal)/(\d+)', url)
    if m:
        return m.group(1)
    m = re.search(r'(\d{18,20})', url)
    if m:
        return m.group(1)
    return None


def download_douyin(url: str, work: Path) -> Path:
    session = requests.Session()
    headers_mobile = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
        "Referer": "https://www.iesdouyin.com/",
    }

    video_id = extract_douyin_video_id(url)
    if not video_id:
        resp = session.get(url, headers=headers_mobile, allow_redirects=True, timeout=10)
        video_id = extract_douyin_video_id(resp.url)

    if not video_id:
        raise RuntimeError(f"Could not extract Douyin video ID from URL: {url}")

    share_url = f"https://www.iesdouyin.com/share/video/{video_id}/"
    session.get(share_url, headers=headers_mobile, timeout=10)
    ttwid = session.cookies.get("ttwid", "")

    headers_pc = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.douyin.com/",
        "Cookie": f"ttwid={ttwid}",
    }
    detail_url = f"https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id={video_id}"
    r_detail = requests.get(detail_url, headers=headers_pc, timeout=10)
    data = r_detail.json()
    aweme = data.get("aweme_detail", {})
    play_addr = aweme.get("video", {}).get("play_addr", {})
    url_list = play_addr.get("url_list", [])

    if not url_list:
        raise RuntimeError("No downloadable video stream URL found for this Douyin video")

    download_url = url_list[0]
    out_file = work / "source.mp4"
    with requests.get(download_url, headers=headers_pc, stream=True, timeout=30) as r:
        r.raise_for_status()
        with open(out_file, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)

    if not out_file.exists() or out_file.stat().st_size == 0:
        raise RuntimeError("Failed to download Douyin video file")

    return out_file


def download_video(url: str, work: Path) -> Path:
    if "douyin.com" in url or "iesdouyin.com" in url:
        try:
            return download_douyin(url, work)
        except Exception as e:
            print(f"Direct Douyin download failed ({e}), trying yt-dlp fallback...")

    output_template = str(work / "source.%(ext)s")
    options = {
        "outtmpl": output_template,
        "format": "bv*+ba/b",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=True)
        requested = Path(ydl.prepare_filename(info))
        mp4 = requested.with_suffix(".mp4")
        if mp4.exists():
            return mp4
        if requested.exists():
            return requested

        candidates = list(work.glob("source.*"))
        if not candidates:
            raise RuntimeError("Downloaded video was not found")
        return candidates[0]


def ffmpeg_extract_audio(video: Path, audio: Path):
    run_ffmpeg(
        [
            "-y",
            "-i",
            str(video),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            str(audio),
        ]
    )


def mix_audio(video: Path, speech: Path, output: Path):
    filter_complex = (
        "[0:a]volume=0.15[bg];"
        "[1:a]volume=1.0[voice];"
        "[bg][voice]amix=inputs=2:duration=first:dropout_transition=2[mix]"
    )

    run_ffmpeg(
        [
            "-y",
            "-i",
            str(video),
            "-i",
            str(speech),
            "-filter_complex",
            filter_complex,
            "-map",
            "0:v:0",
            "-map",
            "[mix]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-shortest",
            str(output),
        ]
    )


def run_ffmpeg(args: list[str]):
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("FFmpeg was not found on PATH")

    process = subprocess.run(
        ["ffmpeg", *args],
        capture_output=True,
        text=True,
    )
    if process.returncode != 0:
        raise RuntimeError(process.stderr[-4000:])


def format_srt_time(seconds: float) -> str:
    millis = int((seconds - int(seconds)) * 1000)
    mins, secs = divmod(int(seconds), 60)
    hours, mins = divmod(mins, 60)
    return f"{hours:02d}:{mins:02d}:{secs:02d},{millis:03d}"


def generate_srt(segments: list[dict], out_path: Path):
    lines = []
    for idx, seg in enumerate(segments, start=1):
        start = format_srt_time(seg.get("start", 0))
        end = format_srt_time(seg.get("end", 0))
        text = seg.get("text", "").strip()
        lines.append(f"{idx}\n{start} --> {end}\n{text}\n")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def translate_segments(
    transcript: dict,
    source_language: str,
    target_language: str,
) -> dict:
    src = normalize_lang_code(source_language)
    tgt = normalize_lang_code(target_language) if target_language else "vi"

    segments = transcript.get("segments", [])
    if not segments:
        return transcript

    texts = [seg.get("text", "").strip() for seg in segments]
    combined_text = "\n###\n".join([t if t else "..." for t in texts])

    try:
        translated_combined = GoogleTranslator(source=src, target=tgt).translate(combined_text)
        translated_lines = [l.strip() for l in translated_combined.split("\n###\n")]
        if len(translated_lines) != len(texts):
            translated_lines = [l.strip() for l in translated_combined.split("\n") if l.strip()]

        translated_segments = []
        for i, seg in enumerate(segments):
            t_text = translated_lines[i] if i < len(translated_lines) else seg.get("text", "")
            translated_segments.append({**seg, "text": t_text})
        return {**transcript, "segments": translated_segments}
    except Exception as e:
        print(f"Batch translation fallback ({e})")
        translated_segments = []
        translator = GoogleTranslator(source=src, target=tgt)
        for seg in segments:
            txt = seg.get("text", "").strip()
            if not txt:
                translated_segments.append(seg)
                continue
            try:
                translated_segments.append({**seg, "text": translator.translate(txt)})
            except Exception:
                translated_segments.append(seg)
        return {**transcript, "segments": translated_segments}
