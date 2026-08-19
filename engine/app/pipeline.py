from __future__ import annotations

import asyncio
import datetime
import json
import os
import re
import shutil
import subprocess
import threading
import traceback
from pathlib import Path
from typing import Any

import edge_tts
import numpy as np
# pyrefly: ignore [missing-import]
import pyttsx3
import requests
import yt_dlp
from deep_translator import GoogleTranslator
from faster_whisper import WhisperModel
# pyrefly: ignore [missing-import]
from gtts import gTTS
from pydub import AudioSegment

BASE_DIR = Path(__file__).resolve().parents[1]
LOG_ERROR_DIR = BASE_DIR / "logError"
_log_lock = threading.Lock()
_vieneu_instance = None


def log_error_to_file(
    error_msg: str,
    exc: Exception | None = None,
    job_id: str | None = None,
    context: dict[str, Any] | None = None,
):
    try:
        LOG_ERROR_DIR.mkdir(parents=True, exist_ok=True)
        now = datetime.datetime.now()
        filename = now.strftime("%d-%m-%Y.txt")
        log_file = LOG_ERROR_DIR / filename

        timestamp_str = now.strftime("%Y-%m-%d %H:%M:%S")
        entry_lines = [
            f"==================== [{timestamp_str}] ====================",
        ]
        if job_id:
            entry_lines.append(f"Job ID: {job_id}")
        if context:
            entry_lines.append(f"Context: {json.dumps(context, ensure_ascii=False)}")
        entry_lines.append(f"Error: {error_msg}")
        if exc is not None:
            tb = traceback.format_exc()
            if tb and tb.strip() != "NoneType: None":
                entry_lines.append("Traceback:")
                entry_lines.append(tb.strip())
        entry_lines.append("============================================================\n")

        with _log_lock:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write("\n".join(entry_lines) + "\n")
    except Exception as e:
        print(f"Failed to write error log: {e}")


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

            segments = translated.get("segments", [])
            valid_segments = [s for s in segments if s.get("text", "").strip()]

            srt_file = work / "subtitles.srt"
            generate_srt(valid_segments, srt_file)

            sub_style = req.get("subtitle_style", "blur_yellow")
            clean_sub_req = req.get("clean_sub_mode")
            burn_subs_req = req.get("burn_subtitles")

            # Determine clean_sub_mode and ass_style
            if sub_style == "blur_yellow":
                clean_sub_mode = "blur"
                ass_style = "yellow"
                burn_subs = True
            elif sub_style == "blur_white":
                clean_sub_mode = "blur"
                ass_style = "white"
                burn_subs = True
            elif sub_style in ("mask_white", "mask"):
                clean_sub_mode = "mask"
                ass_style = "white"
                burn_subs = True
            elif sub_style == "mask_yellow":
                clean_sub_mode = "mask"
                ass_style = "yellow"
                burn_subs = True
            elif sub_style == "box":
                clean_sub_mode = "none"
                ass_style = "box"
                burn_subs = True
            elif sub_style in ("outline", "outline_yellow"):
                clean_sub_mode = "none"
                ass_style = "yellow"
                burn_subs = True
            elif sub_style in ("white_outline", "outline_white"):
                clean_sub_mode = "none"
                ass_style = "white"
                burn_subs = True
            elif sub_style == "only_remove_sub":
                clean_sub_mode = "blur"
                ass_style = "none"
                burn_subs = False
            elif sub_style == "none":
                clean_sub_mode = "none"
                ass_style = "none"
                burn_subs = False
            else:
                clean_sub_mode = "blur"
                ass_style = "yellow"
                burn_subs = True

            if clean_sub_req is not None:
                clean_sub_mode = str(clean_sub_req).lower()
            if burn_subs_req is not None:
                burn_subs = bool(burn_subs_req)

            ass_file = None
            if burn_subs and valid_segments and ass_style != "none":
                ass_file = work / "subtitles.ass"
                generate_ass(valid_segments, ass_file, style_type=ass_style, video_path=video)

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

            mix_audio(video, speech, output, subtitle_file=ass_file, clean_sub_mode=clean_sub_mode)

            self.update(
                job_id,
                status="completed",
                stage="done",
                progress=100,
                output=str(output),
            )
        except Exception as exc:
            err_msg = f"{type(exc).__name__}: {exc}"
            self.update(
                job_id,
                status="failed",
                stage="error",
                error=err_msg,
            )
            req = job.get("request") if "job" in locals() and job else None
            log_error_to_file(err_msg, exc=exc, job_id=job_id, context=req)

    async def run_product_job(self, job_id: str):
        import random
        import base64
        try:
            job = self.get(job_id)
            req = job["request"]
            work = self.data_dir / job_id
            work.mkdir(parents=True, exist_ok=True)

            self.update(job_id, status="running", stage="download_image", progress=10)

            # Save base image and convert with PIL to ensure valid PNG format for FFmpeg
            raw_img_path = work / "raw_product_img"
            if req.get("product_image_base64"):
                raw_b64 = req["product_image_base64"]
                if "," in raw_b64:
                    raw_b64 = raw_b64.split(",", 1)[1]
                img_bytes = base64.b64decode(raw_b64)
                raw_img_path.write_bytes(img_bytes)
            elif req.get("product_image_url"):
                img_url = req["product_image_url"].strip()
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
                }

                # 1. Parse TikTok link og_info URL parameter if present
                extracted_img_url = None
                try:
                    import urllib.parse
                    parsed_url = urllib.parse.urlparse(img_url)
                    qs = urllib.parse.parse_qs(parsed_url.query)
                    if "og_info" in qs:
                        og_json_str = qs["og_info"][0]
                        og_data = json.loads(og_json_str)
                        if "image" in og_data:
                            extracted_img_url = og_data["image"]
                        if "title" in og_data and (not req.get("product_name") or req.get("product_name") == "Sản phẩm cao cấp"):
                            req["product_name"] = og_data["title"]
                except Exception as ex:
                    print(f"Error parsing og_info parameter: {ex}")

                # If og_info provided direct image URL, fetch it immediately
                if extracted_img_url:
                    try:
                        img_resp = requests.get(extracted_img_url, headers=headers, timeout=15)
                        if img_resp.status_code == 200 and len(img_resp.content) > 500:
                            raw_img_path.write_bytes(img_resp.content)
                    except Exception as e:
                        print(f"Error fetching og_info image: {e}")

                if not raw_img_path.exists() or raw_img_path.stat().st_size < 500:
                    # 2. Check if URL is directly pointing to an image file
                    is_direct_image = any(img_url.lower().rsplit("?", 1)[0].endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif"])
                    if is_direct_image:
                        try:
                            resp = requests.get(img_url, headers=headers, timeout=15)
                            if resp.status_code == 200 and len(resp.content) > 500:
                                raw_img_path.write_bytes(resp.content)
                        except Exception as e:
                            print(f"Direct image fetch exception: {e}")
                    else:
                        # 3. Web Scraper: Parse Webpage HTML for Product Image & Title
                        try:
                            resp = requests.get(img_url, headers=headers, timeout=15)
                            if resp.status_code == 200:
                                html_text = resp.text
                                og_matches = re.findall(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html_text, re.IGNORECASE)
                                if not og_matches:
                                    og_matches = re.findall(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', html_text, re.IGNORECASE)
                                if not og_matches:
                                    og_matches = re.findall(r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']', html_text, re.IGNORECASE)
                                
                                title_match = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', html_text, re.IGNORECASE)
                                if title_match and not req.get("product_name"):
                                    req["product_name"] = title_match.group(1).strip()

                                found_img_url = og_matches[0] if og_matches else None
                                if not found_img_url:
                                    img_srcs = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', html_text, re.IGNORECASE)
                                    for src in img_srcs:
                                        if any(kw in src.lower() for kw in ["product", "goods", "item", "cover", "origin", "720x720", "1080x1080"]):
                                            found_img_url = src
                                            break
                                    if not found_img_url and img_srcs:
                                        found_img_url = img_srcs[0]
                                
                                if found_img_url:
                                    if found_img_url.startswith("//"):
                                        found_img_url = "https:" + found_img_url
                                    elif found_img_url.startswith("/"):
                                        import urllib.parse
                                        found_img_url = urllib.parse.urljoin(img_url, found_img_url)

                                    img_resp = requests.get(found_img_url, headers=headers, timeout=15)
                                    if img_resp.status_code == 200 and len(img_resp.content) > 500:
                                        raw_img_path.write_bytes(img_resp.content)
                        except Exception as e:
                            print(f"Webpage product scraper exception: {e}")

            product_img_path = work / "product_source.png"
            loaded_ok = False
            if raw_img_path.exists() and raw_img_path.stat().st_size > 10:
                try:
                    from PIL import Image
                    with Image.open(raw_img_path) as im:
                        im.convert("RGB").save(product_img_path, "PNG")
                        loaded_ok = True
                except Exception:
                    loaded_ok = False

            if not loaded_ok or not product_img_path.exists():
                # Create an attractive gradient fallback card image
                from PIL import Image, ImageDraw, ImageFont
                img = Image.new("RGB", (1080, 1920), color=(114, 9, 183))
                draw = ImageDraw.Draw(img)
                # Inner border & glow
                draw.rectangle([30, 30, 1050, 1890], outline=(247, 37, 133), width=16)
                draw.rectangle([60, 60, 1020, 1860], fill=(56, 4, 116))
                
                display_title = (p_name or "AI PRODUCT SHOWCASE").upper()
                draw.text((150, 850), "🛍️ SIÊU PHẨM AI REVIEW", fill=(255, 215, 0))
                draw.text((150, 950), display_title[:35], fill=(255, 255, 255))
                img.save(product_img_path, "PNG")

            self.update(job_id, stage="generate_script", progress=30)
            
            # AI script generation based on options
            gender = req.get("gender", "female")
            char_type = req.get("character_type", "real")
            p_name = req.get("product_name", "").strip() or "Sản phẩm cao cấp"
            user_prompt = req.get("prompt", "").strip()
            custom_script = req.get("custom_script", "").strip()

            script_text = ""

            # 1. Nếu người dùng tự nhập Lời Thoại trực tiếp -> Dùng luôn lời thoại đó
            if custom_script:
                script_text = custom_script
            else:
                # 2. Nếu không nhập lời thoại, chuẩn bị kịch bản mặc định
                templates_female_real = [
                    f"Chào cả nhà nha! Hôm nay mình ngoi lên đây để trực tiếp trên tay và review cho mọi người chiếc siêu phẩm {p_name} đang cực kỳ rầm rộ thời gian qua. Cảm nhận đầu tiên của mình khi cầm trên tay là thiết kế cực kỳ tỉ mỉ, chất liệu cao cấp và cảm giác sử dụng vô cùng mượt mà. Phải công nhận là đáng đồng tiền bát gạo luôn cả nhà ạ! Ai mà đang đắn đo thì không phải lo lắng đâu nha. Hiện tại shop đang có chương trình trợ giá khủng số lượng có hạn, mọi người nhanh tay bấm ngay vào giỏ hàng góc trái màn hình để săn deal hời hôm nay nhé!",
                    f"Hi mọi người, thần dược cho cuộc sống hiện đại và nâng tầm trải nghiệm của bạn đây rồi! Hôm nay mình đang cầm trên tay em {p_name} này siêu tiện lợi, giải quyết ngay mọi vấn đề bạn gặp phải hàng ngày. Đã có hàng ngàn khách hàng mua và đánh giá năm sao tuyệt đối luôn đó nha. Chất lượng thì đỉnh khỏi bàn, dùng là mê ngay. Duy nhất trong hôm nay shop dành tặng voucher giảm giá độc quyền cho ai nhanh tay nhất, bấm vào giỏ hàng chốt đơn ngay kẻo hết quà nha!",
                    f"Ôi trời ơi chiếc siêu phẩm {p_name} này hot khủng khiếp luôn cả nhà ơi! Mình đang cầm em nó trên tay để review cho cả nhà đây. Trải nghiệm thực tế suốt tuần qua khiến mình thực sự bị thuyết phục hoàn toàn. Không chỉ đẹp mắt, sang trọng mà công năng còn cực kỳ thông minh vượt trội. Bạn nào muốn sở hữu một sản phẩm chất lượng chuẩn chỉnh với mức giá hời nhất thì chần chừ gì nữa, thả tim và bấm ngay giỏ hàng bên dưới để rinh em nó về nhà ngay hôm nay nha!"
                ]
                templates_male_real = [
                    f"Anh em ơi, đây chính là mẫu {p_name} mà tôi đang cầm trên tay và đã cất công tìm kiếm bấy lâu nay! Trải nghiệm thực tế phải nói là cực kỳ đỉnh, vừa bền bỉ chắc chắn lại mang phong cách vô cùng hiện đại và cá tính. Mọi chi tiết đều được hoàn thiện cực tốt, đáng tiền tới từng đồng. Đảm bảo anh em sở hữu là thích ngay. Số lượng ưu đãi có hạn nên anh em nào quan tâm thì bấm ngay vào giỏ hàng bên dưới để chốt deal ngon ngay nhé!",
                    f"Xin chào anh em, hôm nay trên tay một chiếc {p_name} siêu chất review trực tiếp cho mọi người đây. Cảm giác cầm nắm đầm tay, tính năng thông minh vượt trội hơn hẳn các dòng khác trên thị trường. Đã được thử nghiệm thực tế và đánh giá rất cao. Shop cam kết bảo hành uy tín và hỗ trợ chu đáo. Nhanh tay bấm vào giỏ hàng góc trái để săn ngay mức giá ưu đãi tốt nhất hôm nay nào!",
                    f"Review chân thực về sản phẩm {p_name} trên tay cho các bạn đây. Nếu bạn đang tìm kiếm một sản phẩm vừa bền, vừa tinh tế lại tối ưu hiệu năng thì đây chắc chắn là sự lựa chọn số một. Trải nghiệm thực tế vô cùng mượt mà và hài lòng. Mua ngay hôm nay để nhận thêm mã miễn phí vận chuyển toàn quốc, click ngay vào giỏ hàng bên dưới để nhận ưu đãi nhé anh em!"
                ]
                templates_cat_anime = [
                    f"Meow meow~ Chào các bạn nha! Hôm nay bé mèo AI đáng yêu đang ôm trên tay chiếc {p_name} xinh xắn hết nấc luôn nè! Nhìn là mê ngay từ cái nhìn đầu tiên luôn đó nha. Chất lượng siêu xịn xò, màu sắc tươi tắn tôn lên vẻ cá tính vô cùng. Dùng hàng ngày là thích mê luôn! Đang có ưu đãi hấp dẫn cực lớn dành riêng cho bạn đó, bấm ngay vào giỏ hàng rinh em nó về nhà ngay cùng bé mèo thôi nào, meow~!",
                    f"Konnichiwa meow! Mèo xinh ngoi lên đây review cho cả nhà siêu phẩm {p_name} cực kỳ phong cách và dễ thương nè! Bé mèo đang cầm em nó trên tay mà thích mê luôn đó. Đẹp từ mọi góc nhìn, tính năng thì tiện lợi đỉnh cao. Đừng bỏ lỡ cơ hội săn em nó với giá cực hời hôm nay nha, chốt đơn ngay ở giỏ hàng góc dưới thôi các bạn ơi, meow meow!"
                ]

                if char_type == "anime":
                    script_text = random.choice(templates_cat_anime)
                elif gender == "male":
                    script_text = random.choice(templates_male_real)
                else:
                    script_text = random.choice(templates_female_real)

                # 3. Sử dụng Prompt làm chỉ dẫn cho AI sáng tạo kịch bản nếu có
                gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
                openai_key = os.getenv("OPENAI_API_KEY", "").strip()
                role_desc = "Bé mèo AI hoạt hình đáng yêu meow meow đang ôm trên tay sản phẩm" if char_type=="anime" else f"KOL người {'Nữ' if gender=='female' else 'Nam'} đang cầm trên tay sản phẩm"

                if user_prompt:
                    ai_instruction = f"Viết 1 kịch bản lời thoại review bán hàng TikTok 20-25 giây (60-75 từ) cho sản phẩm: {p_name}. Nhập vai: {role_desc}. YÊU CẦU BỐI CẢNH/NỘI DUNG TỪ NGUỜI DÙNG: '{user_prompt}'. Phải sinh ra LỜI THOẠI ĐỌC REVIEW (có chào hỏi, khen sản phẩm, kêu gọi bấm giỏ hàng mua), KHÔNG ĐƯỢC đọc lại trực tiếp câu yêu cầu của người dùng."
                    if gemini_key:
                        try:
                            res_gem = translate_with_gemini([ai_instruction], "vi", "vi")
                            if res_gem and len(res_gem) > 0 and len(res_gem[0]) > 20:
                                script_text = res_gem[0].strip()
                        except Exception:
                            pass
                    elif openai_key:
                        try:
                            res_gpt = translate_with_openai([ai_instruction], "vi", "vi")
                            if res_gpt and len(res_gpt) > 0 and len(res_gpt[0]) > 20:
                                script_text = res_gpt[0].strip()
                        except Exception:
                            pass
                else:
                    if gemini_key:
                        try:
                            res_gem = translate_with_gemini(
                                [f"Viết 1 kịch bản review bán hàng TikTok thu hút dài 60-75 từ (20-25 giây đọc). Nhập vai: {role_desc} review sản phẩm: {p_name}. Có lời chào lôi cuốn, câu thể hiện đang cầm sản phẩm trên tay review khen chất lượng đỉnh cao và kết thúc bằng câu kêu gọi bấm vào giỏ hàng mua ngay."],
                                "vi", "vi"
                            )
                            if res_gem and len(res_gem) > 0 and len(res_gem[0]) > 20:
                                script_text = res_gem[0].strip()
                        except Exception:
                            pass
                    elif openai_key:
                        try:
                            res_gpt = translate_with_openai(
                                [f"Viết 1 kịch bản review sản phẩm TikTok 60-75 từ (20-25s). Nhập vai: {role_desc} review {p_name}. Có đoạn chào hỏi -> trên tay trải nghiệm thực tế xuất sắc -> kêu gọi mua ngay ở giỏ hàng."],
                                "vi", "vi"
                            )
                            if res_gpt and len(res_gpt) > 0 and len(res_gpt[0]) > 20:
                                script_text = res_gpt[0].strip()
                        except Exception:
                            pass

            self.update(job_id, stage="tts", progress=50)

            # Select Voice based on option choice if not explicitly given
            chosen_voice = req.get("voice_id")
            if not chosen_voice:
                if gender == "male":
                    chosen_voice = "vieneu:Gia Bảo"
                else:
                    chosen_voice = "vieneu:ngoc_huyen"

            speech_file = work / "dub.mp3"
            fake_translated = {
                "segments": [
                    {"start": 0.0, "end": 22.0, "text": script_text}
                ]
            }

            self.tts.synthesize_segments(
                fake_translated,
                speech_file,
                voice_id=chosen_voice,
                target_language="vi"
            )

            self.update(job_id, stage="mix_and_render", progress=85)

            # Get duration of audio speech file
            duration_sec = 20.0
            try:
                from pydub import AudioSegment
                audio_seg = AudioSegment.from_file(speech_file)
                duration_sec = max(5.0, len(audio_seg) / 1000.0)
            except Exception:
                duration_sec = random.uniform(20.0, 25.0)

            # Render Video: Pan & Zoom effect on product image + audio dubbing + burned subtitles
            output_mp4 = work / "output.mp4"

            # Split script into natural short sentences sync-ready
            import re
            raw_sentences = [s.strip() for s in re.split(r'[.!?,;]+', script_text) if len(s.strip()) > 3]
            if not raw_sentences:
                raw_sentences = [script_text]

            # Assign timed segments proportionally matching speech duration
            time_per_sentence = duration_sec / max(1, len(raw_sentences))
            segments_data = []
            curr_t = 0.5
            for sentence in raw_sentences:
                dur = min(4.5, max(1.8, len(sentence) * 0.18))
                end_t = min(duration_sec - 0.2, curr_t + dur)
                segments_data.append({"start": round(curr_t, 2), "end": round(end_t, 2), "text": sentence})
                curr_t = end_t + 0.15

            # Create subtitle file (SRT & ASS at bottom of screen with small clean font)
            sub_srt = work / "subtitles.srt"
            generate_srt(segments_data, sub_srt)

            # Option to burn subtitle or hide (Default: hide or bottom screen)
            burn_sub = req.get("burn_subtitles", False)

            ass_sub_path = work / "subtitles.ass"
            if burn_sub:
                generate_ass(segments_data, ass_sub_path, style_type="yellow")

            # Render Dynamic AI Talking Reviewer Video (Top: Speaking Character, Bottom: Product)
            from .avatar_animator import generate_talking_reviewer_video
            rendered_ok = False
            try:
                rendered_ok = generate_talking_reviewer_video(
                    audio_path=speech_file,
                    product_img_path=product_img_path,
                    output_video_path=output_mp4,
                    char_type=char_type,
                    gender=gender,
                    product_name=p_name,
                    subtitles_ass_path=ass_sub_path if (burn_sub and ass_sub_path.exists()) else None,
                    fps=25
                )
            except Exception as e:
                log_error_to_file(f"Avatar animator error: {e}", job_id=job_id)
                rendered_ok = False

            if not rendered_ok or not output_mp4.exists():
                # Fallback to FFmpeg ZoomPan if animator fails
                zoom_modes = [
                    "zoompan=z='min(zoom+0.0015,1.25)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=125:s=1080x1920",
                    "zoompan=z='max(1.25-0.0015,1.0)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=125:s=1080x1920",
                ]
                vf_filter = f"{random.choice(zoom_modes)},scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
                if burn_sub and ass_sub_path.exists():
                    safe_ass = str(ass_sub_path).replace("\\", "/").replace(":", "\\:")
                    vf_filter += f",ass='{safe_ass}'"

                cmd = [
                    "ffmpeg", "-y",
                    "-loop", "1", "-i", str(product_img_path),
                    "-i", str(speech_file),
                    "-vf", vf_filter,
                    "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k",
                    "-t", f"{duration_sec:.2f}",
                    "-shortest",
                    str(output_mp4)
                ]
                subprocess.run(cmd, capture_output=True, text=True)

            self.update(
                job_id,
                status="completed",
                stage="done",
                progress=100,
                output=str(output_mp4),
            )
        except Exception as exc:
            err_msg = f"{type(exc).__name__}: {exc}"
            self.update(
                job_id,
                status="failed",
                stage="error",
                error=err_msg,
            )
            req = job.get("request") if "job" in locals() and job else None
            log_error_to_file(err_msg, exc=exc, job_id=job_id, context=req)

def transcribe_with_groq(audio: Path, language: str | None = None) -> dict | None:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        return None
    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    headers = {"Authorization": f"Bearer {api_key}"}
    data: dict[str, Any] = {
        "model": "whisper-large-v3-turbo",
        "response_format": "verbose_json",
        "temperature": "0.0",
    }
    if language and language.lower() not in ("auto", ""):
        data["language"] = language.lower()

    try:
        with open(audio, "rb") as f:
            files = {"file": (audio.name, f, "audio/wav")}
            resp = requests.post(url, headers=headers, data=data, files=files, timeout=60)
        
        if resp.status_code == 200:
            res_json = resp.json()
            raw_segs = res_json.get("segments", [])
            segments = []
            for s in raw_segs:
                text = s.get("text", "").strip()
                if text:
                    segments.append({
                        "start": float(s.get("start", 0.0)),
                        "end": float(s.get("end", 0.0)),
                        "text": text,
                    })
            if segments:
                print(f"[Speedup] Groq Whisper Cloud transcribed {len(segments)} segments in ~1s!")
                return {
                    "language": res_json.get("language", language or "auto"),
                    "language_probability": 1.0,
                    "segments": segments,
                }
        else:
            print(f"Groq Whisper notice ({resp.status_code}): {resp.text[:200]}")
    except Exception as e:
        print(f"Groq Whisper exception: {e}")
    return None


def transcribe_with_openai(audio: Path, language: str | None = None) -> dict | None:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    url = "https://api.openai.com/v1/audio/transcriptions"
    headers = {"Authorization": f"Bearer {api_key}"}
    data: dict[str, Any] = {
        "model": "whisper-1",
        "response_format": "verbose_json",
    }
    if language and language.lower() not in ("auto", ""):
        data["language"] = language.lower()

    try:
        with open(audio, "rb") as f:
            files = {"file": (audio.name, f, "audio/wav")}
            resp = requests.post(url, headers=headers, data=data, files=files, timeout=90)
        
        if resp.status_code == 200:
            res_json = resp.json()
            raw_segs = res_json.get("segments", [])
            segments = []
            for s in raw_segs:
                text = s.get("text", "").strip()
                if text:
                    segments.append({
                        "start": float(s.get("start", 0.0)),
                        "end": float(s.get("end", 0.0)),
                        "text": text,
                    })
            if segments:
                print(f"[Speedup] OpenAI Whisper Cloud transcribed {len(segments)} segments!")
                return {
                    "language": res_json.get("language", language or "auto"),
                    "language_probability": 1.0,
                    "segments": segments,
                }
        else:
            print(f"OpenAI Whisper notice ({resp.status_code}): {resp.text[:200]}")
    except Exception as e:
        print(f"OpenAI Whisper exception: {e}")
    return None


def transcribe_with_deepgram(audio: Path, language: str | None = None) -> dict | None:
    api_key = os.getenv("DEEPGRAM_API_KEY", "").strip()
    if not api_key:
        return None
    url = "https://api.deepgram.com/v1/listen?model=nova-2&smart_format=true&utterances=true&punctuate=true"
    if language and language.lower() not in ("auto", ""):
        url += f"&language={language.lower()}"
    headers = {
        "Authorization": f"Token {api_key}",
        "Content-Type": "audio/wav",
    }
    try:
        with open(audio, "rb") as f:
            resp = requests.post(url, headers=headers, data=f.read(), timeout=60)
        if resp.status_code == 200:
            res_json = resp.json()
            results = res_json.get("results", {})
            utterances = results.get("utterances", [])
            segments = []
            for u in utterances:
                t = u.get("transcript", "").strip()
                if t:
                    segments.append({
                        "start": float(u.get("start", 0.0)),
                        "end": float(u.get("end", 0.0)),
                        "text": t,
                    })
            if segments:
                print(f"[Speedup] Deepgram Nova-2 transcribed {len(segments)} utterances!")
                return {
                    "language": language or "auto",
                    "language_probability": 1.0,
                    "segments": segments,
                }
    except Exception as e:
        print(f"Deepgram exception: {e}")
    return None


    def transcribe(self, audio: Path, language: str):
        stt_pref = os.getenv("STT_PROVIDER", "auto").lower()
        lang_code = None if language.lower() in ("auto", "") else language

        # 1. Groq Whisper Cloud (Siêu tốc 1s)
        if stt_pref == "groq" or (stt_pref == "auto" and os.getenv("GROQ_API_KEY")):
            res = transcribe_with_groq(audio, lang_code)
            if res:
                return res

        # 2. OpenAI Whisper Cloud
        if stt_pref == "openai" or (stt_pref == "auto" and os.getenv("OPENAI_API_KEY")):
            res = transcribe_with_openai(audio, lang_code)
            if res:
                return res

        # 3. Deepgram Cloud
        if stt_pref == "deepgram" or (stt_pref == "auto" and os.getenv("DEEPGRAM_API_KEY")):
            res = transcribe_with_deepgram(audio, lang_code)
            if res:
                return res

        # 4. Fallback to Local Faster-Whisper
        if self._whisper is None:
            model_name = os.getenv("WHISPER_MODEL", "base")
            device = os.getenv("WHISPER_DEVICE", "cpu")
            compute = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
            self._whisper = WhisperModel(
                model_name,
                device=device,
                compute_type=compute,
            )

        segments, info = self._whisper.transcribe(
            str(audio),
            language=lang_code,
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

        # 4. OpenAI Neural Cloud Voices (Khi có OpenAI API Key)
        if os.getenv("OPENAI_API_KEY", "").strip():
            voices.extend([
                {"id": "openai:alloy", "name": "🤖 Alloy (OpenAI Cloud - Tự Nhiên & Đa Năng)", "languages": ["vi", "en", "zh", "ja", "ko"], "category": "OpenAI Cloud"},
                {"id": "openai:nova", "name": "🤖 Nova (OpenAI Cloud - Nữ Trẻ Trung & Tươi Tắn)", "languages": ["vi", "en", "zh", "ja", "ko"], "category": "OpenAI Cloud"},
                {"id": "openai:shimmer", "name": "🤖 Shimmer (OpenAI Cloud - Nữ Ngọt Ngào & Trong Sáng)", "languages": ["vi", "en", "zh", "ja", "ko"], "category": "OpenAI Cloud"},
                {"id": "openai:echo", "name": "🤖 Echo (OpenAI Cloud - Nam Ấm Áp & Truyền Cảm)", "languages": ["vi", "en", "zh", "ja", "ko"], "category": "OpenAI Cloud"},
                {"id": "openai:onyx", "name": "🤖 Onyx (OpenAI Cloud - Nam Trầm Hùng & Cuốn Hút)", "languages": ["vi", "en", "zh", "ja", "ko"], "category": "OpenAI Cloud"},
                {"id": "openai:fable", "name": "🤖 Fable (OpenAI Cloud - Kể Chuyện Sinh Động)", "languages": ["vi", "en", "zh", "ja", "ko"], "category": "OpenAI Cloud"},
            ])

        # 5. ElevenLabs AI Voices (Khi có ElevenLabs API Key)
        if os.getenv("ELEVENLABS_API_KEY", "").strip():
            voices.extend([
                {"id": "elevenlabs:21m00Tcm4TlvDq8ikWAM", "name": "🎙️ Rachel (ElevenLabs - Nữ Siêu Thực)", "languages": ["vi", "en"], "category": "ElevenLabs AI"},
                {"id": "elevenlabs:pNInz6obpgDQGcFmaJgB", "name": "🎙️ Adam (ElevenLabs - Nam Thuyết Minh)", "languages": ["vi", "en"], "category": "ElevenLabs AI"},
                {"id": "elevenlabs:EXAVITQu4vr4xnSDxMaL", "name": "🎙️ Bella (ElevenLabs - Nữ Dịu Dàng)", "languages": ["vi", "en"], "category": "ElevenLabs AI"},
                {"id": "elevenlabs:ErXwobaYiN019PkySvjV", "name": "🎙️ Antoni (ElevenLabs - Nam Trầm)", "languages": ["vi", "en"], "category": "ElevenLabs AI"},
            ])

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

            # Option A: OpenAI Cloud TTS
            if not success and target_voice.startswith("openai:"):
                openai_key = os.getenv("OPENAI_API_KEY", "").strip()
                if openai_key:
                    try:
                        voice_name = target_voice.split(":", 1)[1]
                        res = requests.post(
                            "https://api.openai.com/v1/audio/speech",
                            headers={"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"},
                            json={"model": "tts-1", "voice": voice_name, "input": text},
                            timeout=25,
                        )
                        if res.status_code == 200:
                            seg_out.write_bytes(res.content)
                            if seg_out.exists() and seg_out.stat().st_size > 100:
                                success = True
                    except Exception as e:
                        print(f"OpenAI TTS error seg {idx}: {e}")

            # Option B: ElevenLabs Cloud TTS
            if not success and target_voice.startswith("elevenlabs:"):
                eleven_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
                if eleven_key:
                    try:
                        voice_id_param = target_voice.split(":", 1)[1]
                        res = requests.post(
                            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id_param}",
                            headers={"xi-api-key": eleven_key, "Content-Type": "application/json"},
                            json={"text": text, "model_id": "eleven_multilingual_v2"},
                            timeout=30,
                        )
                        if res.status_code == 200:
                            seg_out.write_bytes(res.content)
                            if seg_out.exists() and seg_out.stat().st_size > 100:
                                success = True
                    except Exception as e:
                        print(f"ElevenLabs TTS error seg {idx}: {e}")

            # Option C: VieNeu-TTS
            if not success and tts_vieneu and target_voice.startswith("vieneu:"):
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

            # Option D: Microsoft Edge-TTS
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

            # Option E: Local OS SAPI5 (pyttsx3)
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

            # Option F: Google AI Voice (gTTS fallback)
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


def extract_douyin_video_id(raw_text: str) -> str | None:
    if not raw_text:
        return None
    raw_text = str(raw_text).strip()

    # Check if raw text is already numeric ID
    if re.fullmatch(r"\d{17,22}", raw_text):
        return raw_text

    # Extract any URL embedded in the text
    urls = re.findall(r"https?://[^\s<>\"']+", raw_text)
    target = urls[0] if urls else raw_text

    # Regex matches on modal_id or /video/ or share or note
    m = re.search(r"modal_id=(\d{17,22})", target)
    if m:
        return m.group(1)
    m = re.search(r"/(?:video|share/video|modal|note)/(\d{17,22})", target)
    if m:
        return m.group(1)
    m = re.search(r"\b(\d{18,21})\b", target)
    if m:
        return m.group(1)

    # If it's a short URL (e.g. v.douyin.com), follow redirects
    if "douyin" in target or "iesdouyin" in target:
        try:
            headers_mobile = {
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
            }
            resp = requests.get(target, headers=headers_mobile, allow_redirects=True, timeout=10)
            final_url = resp.url
            m = re.search(r"modal_id=(\d{17,22})", final_url)
            if m:
                return m.group(1)
            m = re.search(r"/(?:video|share/video|modal|note)/(\d{17,22})", final_url)
            if m:
                return m.group(1)
            m = re.search(r"(\d{18,21})", final_url)
            if m:
                return m.group(1)
        except Exception as e:
            print(f"Error following Douyin redirect: {e}")

    return None


def generate_douyin_random_token(length: int = 128) -> str:
    import random
    import string
    chars = string.ascii_letters + string.digits + "_-"
    return "".join(random.choices(chars, k=length))


def find_existing_cookie_file(work_dir: Path | None = None) -> Path | None:
    candidate_paths = [
        Path("cookies.txt"),
        BASE_DIR / "cookies.txt",
        BASE_DIR.parent / "cookies.txt",
        Path.home() / ".douyin_cookies.txt",
        Path.home() / "cookies.txt",
    ]
    if work_dir:
        candidate_paths.insert(0, work_dir / "cookies.txt")
        candidate_paths.insert(1, work_dir.parent / "cookies.txt")

    for p in candidate_paths:
        try:
            if p.exists() and p.is_file() and p.stat().st_size > 10:
                return p
        except Exception:
            pass
    return None


def get_douyin_cookies_dict(session: requests.Session | None = None) -> dict[str, str]:
    import random
    import string
    s = session or requests.Session()
    headers_browser = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Referer": "https://www.douyin.com/",
    }
    cookies: dict[str, str] = {
        "msToken": generate_douyin_random_token(128) + "=",
        "odin_tt": "".join(random.choices(string.hexdigits.lower(), k=64)),
        "passport_csrf_token": "".join(random.choices(string.hexdigits.lower(), k=32)),
        "__ac_nonce": "".join(random.choices("0123456789abcdef", k=21)),
    }

    # Strategy 1: ByteDance official register API
    try:
        register_url = "https://ttwid.bytedance.com/ttwid/union/register/"
        payload = {
            "region": "cn",
            "aid": 1768,
            "needFid": "0",
            "service": "www.ixigua.com",
            "migrate_info": {"ticket": "", "source": "node"},
            "cbUrlProtocol": "https",
            "union": True,
        }
        res = s.post(
            register_url,
            json=payload,
            headers={"Content-Type": "application/json", **headers_browser},
            timeout=5,
        )
        if res.cookies.get("ttwid"):
            cookies["ttwid"] = res.cookies.get("ttwid")
        else:
            set_cookie = res.headers.get("Set-Cookie", "")
            m = re.search(r"ttwid=([^;]+)", set_cookie)
            if m:
                cookies["ttwid"] = m.group(1)
    except Exception:
        pass

    # Strategy 2: live.douyin.com
    if "ttwid" not in cookies:
        try:
            res = s.get("https://live.douyin.com/", headers=headers_browser, timeout=5)
            if res.cookies.get("ttwid"):
                cookies["ttwid"] = res.cookies.get("ttwid")
        except Exception:
            pass

    # Strategy 3: douyin.com
    if "ttwid" not in cookies:
        try:
            res = s.get("https://www.douyin.com/", headers=headers_browser, timeout=5)
            if res.cookies.get("ttwid"):
                cookies["ttwid"] = res.cookies.get("ttwid")
        except Exception:
            pass

    return cookies


def write_netscape_cookie_file(cookies: dict[str, str], filepath: Path) -> Path:
    lines = ["# Netscape HTTP Cookie File", "# https://curl.haxx.se/rfc/cookie_spec.html"]
    for k, v in cookies.items():
        lines.append(f".douyin.com\tTRUE\t/\tFALSE\t2147483647\t{k}\t{v}")
    filepath.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return filepath


def download_douyin(url: str, work: Path) -> Path:
    work.mkdir(parents=True, exist_ok=True)
    video_id = extract_douyin_video_id(url)
    if not video_id:
        raise RuntimeError(f"Could not extract Douyin video ID from: {url}")

    session = requests.Session()
    cookies = get_douyin_cookies_dict(session)
    for k, v in cookies.items():
        session.cookies.set(k, v, domain=".douyin.com")

    # Load custom cookies if available
    custom_cookie_file = find_existing_cookie_file(work)
    if custom_cookie_file:
        try:
            with open(custom_cookie_file, "r", encoding="utf-8", errors="ignore") as cf:
                for line in cf:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        parts = line.split("\t")
                        if len(parts) >= 7:
                            c_domain, _, _, _, _, c_name, c_val = parts[:7]
                            session.cookies.set(c_name, c_val, domain=c_domain)
        except Exception as e:
            print(f"Notice: Failed to parse custom cookie file: {e}")

    cookie_header_str = "; ".join(f"{k}={v}" for k, v in session.cookies.get_dict().items())
    if "ttwid" in cookies and "ttwid" not in session.cookies.get_dict():
        cookie_header_str += f"; ttwid={cookies['ttwid']}"

    headers_browser = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Referer": f"https://www.douyin.com/video/{video_id}",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Cookie": cookie_header_str,
    }

    url_list: list[str] = []

    # Step 1: Query Douyin official web endpoints with multiple aid signatures
    detail_endpoints = [
        f"https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id={video_id}&aid=6383&device_platform=webapp&version_code=170400&version_name=17.4.0",
        f"https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id={video_id}&aid=1128&version_name=23.5.0&device_platform=android&os_version=2333",
        f"https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id={video_id}",
        f"https://www.iesdouyin.com/aweme/v1/web/aweme/detail/?aweme_id={video_id}",
    ]

    for endpoint in detail_endpoints:
        try:
            r_detail = session.get(endpoint, headers=headers_browser, timeout=12)
            if r_detail.status_code == 200:
                data = r_detail.json()
                aweme = data.get("aweme_detail") or {}
                video = aweme.get("video") or {}

                # 1. High quality bitrates sorted descending
                bit_rates = video.get("bit_rate") or []
                try:
                    bit_rates_sorted = sorted(bit_rates, key=lambda b: int(b.get("bit_rate", 0)), reverse=True)
                except Exception:
                    bit_rates_sorted = bit_rates
                for br in bit_rates_sorted:
                    br_urls = (br.get("play_addr") or {}).get("url_list") or []
                    for u in br_urls:
                        if u and u.startswith("http") and u not in url_list:
                            url_list.append(u)

                # 2. H.264 high-compatibility stream
                h264_urls = (video.get("play_addr_h264") or {}).get("url_list") or []
                for u in h264_urls:
                    if u and u.startswith("http") and u not in url_list:
                        url_list.append(u)

                # 3. Standard play_addr
                play_urls = (video.get("play_addr") or {}).get("url_list") or []
                for u in play_urls:
                    if u and u.startswith("http") and u not in url_list:
                        url_list.append(u)

                # 4. Download addr
                dl_urls = (video.get("download_addr") or {}).get("url_list") or []
                for u in dl_urls:
                    if u and u.startswith("http") and u not in url_list:
                        url_list.append(u)

                # 5. URI direct endpoint fallback
                vid_uri = video.get("uri")
                if vid_uri:
                    url_list.append(f"https://aweme.snssdk.com/aweme/v1/play/?video_id={vid_uri}&ratio=1080p&line=0")
                    url_list.append(f"https://api-hl.amemv.com/aweme/v1/play/?video_id={vid_uri}&ratio=1080p&line=0")

                if url_list:
                    break
        except Exception as e:
            print(f"Douyin detail API endpoint error ({endpoint}): {e}")

    # Step 2: Fallback Mobile endpoint if detail API returned nothing
    if not url_list:
        headers_mobile = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
            "Referer": "https://www.iesdouyin.com/",
        }
        for direct_play in [
            f"https://aweme.snssdk.com/aweme/v1/play/?video_id={video_id}&ratio=1080p&line=0",
            f"https://api-hl.amemv.com/aweme/v1/play/?video_id={video_id}&ratio=1080p&line=0",
        ]:
            try:
                r_direct = session.get(direct_play, headers=headers_mobile, allow_redirects=False, timeout=8)
                if r_direct.status_code in (301, 302) and "location" in r_direct.headers:
                    url_list.append(r_direct.headers["location"])
            except Exception:
                pass

    if not url_list:
        raise RuntimeError(f"No downloadable stream found for Douyin video {video_id}")

    # Step 3: Stream download to work directory with retries
    out_file = work / "source.mp4"
    download_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Referer": "https://www.douyin.com/",
        "Accept": "*/*",
    }

    downloaded = False
    for candidate_url in url_list:
        try:
            with session.get(candidate_url, headers=download_headers, stream=True, timeout=30) as r:
                if r.status_code in (200, 206):
                    with open(out_file, "wb") as f:
                        for chunk in r.iter_content(chunk_size=1024 * 1024):
                            if chunk:
                                f.write(chunk)
                    if out_file.exists() and out_file.stat().st_size > 10000:
                        downloaded = True
                        break
        except Exception as e:
            print(f"Douyin candidate download glitch ({e}), trying next stream URL...")

    if not downloaded or not out_file.exists() or out_file.stat().st_size < 10000:
        raise RuntimeError(f"Failed to download complete video stream for Douyin video {video_id}")

    return out_file


def download_video(url: str, work: Path) -> Path:
    work.mkdir(parents=True, exist_ok=True)
    url_clean = str(url).strip().strip('"').strip("'")

    # 0. Local file check
    if Path(url_clean).exists() and Path(url_clean).is_file():
        dest = work / f"source{Path(url_clean).suffix}"
        if Path(url_clean).resolve() != dest.resolve():
            shutil.copy2(url_clean, dest)
        return dest

    # 1. Douyin handler
    video_id = extract_douyin_video_id(url_clean)
    is_douyin = (
        "douyin" in url_clean.lower()
        or "iesdouyin" in url_clean.lower()
        or (url_clean.isdigit() and len(url_clean) >= 17)
        or (video_id is not None and ("douyin" in url_clean.lower() or "modal_id=" in url_clean.lower() or url_clean.isdigit()))
    )

    if is_douyin or video_id:
        try:
            return download_douyin(url_clean, work)
        except Exception as e:
            print(f"Direct Douyin download failed ({e}), trying yt-dlp with Netscape cookiefile fallback...")

    # 2. General yt-dlp handler
    yt_url = url_clean
    if video_id and ("douyin" in url_clean.lower() or url_clean.isdigit() or "modal_id=" in url_clean.lower()):
        yt_url = f"https://www.douyin.com/video/{video_id}"

    output_template = str(work / "source.%(ext)s")
    options = {
        "outtmpl": output_template,
        "format": "bv*+ba/b",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
    }

    # Setup Netscape cookie file for yt-dlp to avoid "Passing cookies as a header is a potential security risk"
    cookie_file = find_existing_cookie_file(work)
    temp_cookie_path = None
    if cookie_file:
        options["cookiefile"] = str(cookie_file)
    elif is_douyin or video_id:
        try:
            dy_cookies = get_douyin_cookies_dict()
            temp_cookie_path = work / ".yt_dlp_cookies.txt"
            write_netscape_cookie_file(dy_cookies, temp_cookie_path)
            options["cookiefile"] = str(temp_cookie_path)
        except Exception as e:
            print(f"Notice: Failed to create temporary cookie file for yt-dlp: {e}")

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(yt_url, download=True)
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
    finally:
        if temp_cookie_path and temp_cookie_path.exists():
            temp_cookie_path.unlink(missing_ok=True)


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


def get_video_dimensions(file_path: Path) -> tuple[int, int]:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "csv=s=x:p=0",
        str(file_path),
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0 and "x" in res.stdout.strip():
            parts = res.stdout.strip().split("x")
            return int(parts[0]), int(parts[1])
    except Exception:
        pass
    return 1080, 1920


def check_has_audio(file_path: Path) -> bool:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=codec_type",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(file_path),
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        return res.returncode == 0 and bool(res.stdout.strip())
    except Exception:
        return True


def format_ass_time(seconds: float) -> str:
    total_cs = int(round(max(0.0, float(seconds)) * 100))
    cs = total_cs % 100
    total_s = total_cs // 100
    s = total_s % 60
    total_m = total_s // 60
    m = total_m % 60
    h = total_m // 60
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def generate_ass(
    segments: list[dict],
    out_path: Path,
    style_type: str = "yellow",
    video_path: Path | None = None,
):
    width, height = (1080, 1920)
    if video_path and video_path.exists():
        width, height = get_video_dimensions(video_path)

    # Adaptive font size and margin according to aspect ratio and resolution
    if height > width:  # Vertical video (9:16 - Douyin / TikTok / Reels)
        fontsize = max(24, int(width * 0.046))
        margin_v = int(height * 0.10)  # Position centered inside the cleaned hardsub area
        margin_lr = int(width * 0.05)
    else:  # Horizontal video (16:9 - YouTube / Facebook)
        fontsize = max(22, int(height * 0.052))
        margin_v = int(height * 0.075)
        margin_lr = int(width * 0.04)

    # ASS Styles:
    # Yellow font: &H0000FFFF (ABGR format -> 00 FFFF is Yellow)
    # White font: &H00FFFFFF
    # Black Outline: &H00000000
    # Shadow: &H80000000
    if style_type in ("yellow", "blur_yellow", "outline", "outline_yellow"):
        # Vibrant Yellow with thick black border and soft shadow
        style_line = (
            f"Style: Default,Arial,{fontsize},&H0000FFFF,&H000000FF,&H00000000,&H80000000,"
            f"-1,0,0,0,100,100,0,0,1,3.5,2,2,{margin_lr},{margin_lr},{margin_v},1"
        )
    elif style_type in ("white", "blur_white", "mask_white", "outline_white", "white_outline"):
        # Crisp White with thick black border and soft shadow
        style_line = (
            f"Style: Default,Arial,{fontsize},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,"
            f"-1,0,0,0,100,100,0,0,1,3.5,2,2,{margin_lr},{margin_lr},{margin_v},1"
        )
    elif style_type == "box":
        # Crisp White text inside an elegant dark translucent box (&HA0000000)
        box_padding = max(4, int(fontsize * 0.18))
        style_line = (
            f"Style: Default,Arial,{fontsize},&H00FFFFFF,&H000000FF,&H00000000,&HA0000000,"
            f"-1,0,0,0,100,100,0,0,3,{box_padding},0,2,{margin_lr},{margin_lr},{margin_v},1"
        )
    else:
        # Default yellow
        style_line = (
            f"Style: Default,Arial,{fontsize},&H0000FFFF,&H000000FF,&H00000000,&H80000000,"
            f"-1,0,0,0,100,100,0,0,1,3.5,2,2,{margin_lr},{margin_lr},{margin_v},1"
        )

    lines = [
        "[Script Info]",
        "Title: Vietnamese Subtitles",
        "ScriptType: v4.00+",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        "YCbCr Matrix: TV.601",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        style_line,
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    for seg in segments:
        text = str(seg.get("text", "")).strip()
        if not text:
            continue
        start = format_ass_time(seg.get("start", 0))
        end = format_ass_time(seg.get("end", 0))
        clean_text = text.replace("\r", "").replace("\n", "\\N")
        lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{clean_text}")

    out_path.write_text("\n".join(lines), encoding="utf-8")


def mix_audio(
    video: Path,
    speech: Path,
    output: Path,
    subtitle_file: Path | None = None,
    clean_sub_mode: str = "blur",
):
    has_audio = check_has_audio(video)
    width, height = get_video_dimensions(video)

    # Calculate bounding box coordinates for hardsub removal
    if height > width:  # Vertical video (9:16)
        w_box = int(width * 0.94)
        h_box = int(height * 0.13)
        x_box = int((width - w_box) / 2)
        y_box = int(height * 0.77)
    else:  # Horizontal video (16:9)
        w_box = int(width * 0.90)
        h_box = int(height * 0.13)
        x_box = int((width - w_box) / 2)
        y_box = int(height * 0.81)

    # Ensure even integers for FFmpeg filters
    w_box = (w_box // 2) * 2
    h_box = (h_box // 2) * 2
    x_box = (x_box // 2) * 2
    y_box = (y_box // 2) * 2

    # Step 1: Video filtering (Clean hardsub + Subtitle burn-in)
    filter_complex_parts = []
    has_video_filter = False
    v_target = "0:v:0"

    if clean_sub_mode == "blur":
        filter_complex_parts.append(
            f"[0:v]split[v_base][v_crop];"
            f"[v_crop]crop={w_box}:{h_box}:{x_box}:{y_box},avgblur=sizeX=25:sizeY=25[v_blur];"
            f"[v_base][v_blur]overlay={x_box}:{y_box}[v_clean]"
        )
        v_target = "[v_clean]"
        has_video_filter = True
    elif clean_sub_mode == "mask":
        filter_complex_parts.append(
            f"[0:v]drawbox=x={x_box}:y={y_box}:w={w_box}:h={h_box}:color=black@0.75:t=fill[v_clean]"
        )
        v_target = "[v_clean]"
        has_video_filter = True

    if subtitle_file and subtitle_file.exists():
        escaped_sub = str(subtitle_file.resolve()).replace("\\", "/").replace(":", "\\:")
        if has_video_filter:
            filter_complex_parts.append(f"{v_target}ass=filename='{escaped_sub}'[v_out]")
        else:
            filter_complex_parts.append(f"[0:v]ass=filename='{escaped_sub}'[v_out]")
        v_target = "[v_out]"
        has_video_filter = True
    elif has_video_filter:
        filter_complex_parts.append(f"{v_target}null[v_out]")
        v_target = "[v_out]"

    # Step 2: Audio mixing
    if has_audio:
        filter_complex_parts.append(
            "[0:a]volume=0.15[bg];"
            "[1:a]volume=1.0[voice];"
            "[bg][voice]amix=inputs=2:duration=first:dropout_transition=2[a_out]"
        )
        a_target = "[a_out]"
    else:
        filter_complex_parts.append("[1:a]volume=1.0[a_out]")
        a_target = "[a_out]"

    full_filter = ";".join(filter_complex_parts)

    args = [
        "-y",
        "-i", str(video),
        "-i", str(speech),
        "-filter_complex", full_filter,
        "-map", v_target,
        "-map", a_target,
    ]

    if has_video_filter:
        args.extend([
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "20",
        ])
    else:
        args.extend([
            "-c:v", "copy",
        ])

    args.extend([
        "-c:a", "aac",
        "-b:a", "192k",
        "-sn",  # Drop all existing soft subtitle tracks
        "-shortest",
        str(output),
    ])

    run_ffmpeg(args)


def run_ffmpeg(args: list[str]):
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("FFmpeg was not found on PATH")

    cmd = ["ffmpeg"]
    if "-nostdin" not in args:
        cmd.append("-nostdin")
    cmd.extend(args)

    process = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
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


def translate_with_gemini(texts: list[str], source_lang: str, target_lang: str) -> list[str] | None:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None
    
    prompt = (
        f"You are an expert video dubbing and subtitling translator. "
        f"Translate the following list of subtitle sentences from {source_lang} into {target_lang}. "
        f"Requirements:\n"
        f"1. Make the translation sound completely natural, engaging, and suitable for spoken video dubbing.\n"
        f"2. Keep the sentence length concise so it fits video timing.\n"
        f"3. Return ONLY a valid JSON object in this exact format: {{\"translations\": [\"translated line 1\", \"translated line 2\", ...]}}.\n"
        f"4. The output array MUST contain exactly {len(texts)} elements corresponding 1:1 to the input array.\n\n"
        f"Input sentences array:\n{json.dumps(texts, ensure_ascii=False)}"
    )

    models_to_try = ["gemini-1.5-flash", "gemini-2.0-flash", "gemini-1.5-pro"]
    for model_name in models_to_try:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "temperature": 0.3,
                },
            }
            resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=30)
            if resp.status_code == 200:
                res_json = resp.json()
                text_out = res_json["candidates"][0]["content"]["parts"][0]["text"]
                parsed = json.loads(text_out)
                translations = parsed.get("translations") if isinstance(parsed, dict) else parsed
                if isinstance(translations, list) and len(translations) == len(texts):
                    print(f"[Speedup] Google Gemini {model_name} translated {len(texts)} subtitle segments in ~1s!")
                    return [str(t).strip() for t in translations]
                elif isinstance(translations, list) and len(translations) > 0:
                    while len(translations) < len(texts):
                        translations.append(texts[len(translations)])
                    return [str(t).strip() for t in translations[:len(texts)]]
            else:
                print(f"Gemini {model_name} notice ({resp.status_code}): {resp.text[:200]}")
        except Exception as e:
            print(f"Gemini {model_name} exception: {e}")
    return None


def translate_with_groq(texts: list[str], source_lang: str, target_lang: str) -> list[str] | None:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        return None
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    
    prompt = (
        f"Translate the following array of {len(texts)} subtitle sentences from {source_lang} to {target_lang} for video dubbing. "
        f"Output ONLY valid JSON with key 'translations' containing an array of exactly {len(texts)} translated strings."
    )
    
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps({"texts": texts}, ensure_ascii=False)},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=20)
        if resp.status_code == 200:
            content = resp.json()["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            translations = parsed.get("translations") if isinstance(parsed, dict) else parsed
            if isinstance(translations, list):
                while len(translations) < len(texts):
                    translations.append(texts[len(translations)])
                print(f"[Speedup] Groq Llama 3.3 translated {len(texts)} segments in sub-second!")
                return [str(t).strip() for t in translations[:len(texts)]]
    except Exception as e:
        print(f"Groq translation error: {e}")
    return None


def translate_with_openai(texts: list[str], source_lang: str, target_lang: str) -> list[str] | None:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": f"You are a professional video dubbing translator. Translate {len(texts)} sentences from {source_lang} to {target_lang}. Return ONLY a JSON object: {{\"translations\": [\"...\"]}}."},
            {"role": "user", "content": json.dumps({"texts": texts}, ensure_ascii=False)},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.3,
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=25)
        if resp.status_code == 200:
            content = resp.json()["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            translations = parsed.get("translations") if isinstance(parsed, dict) else parsed
            if isinstance(translations, list):
                while len(translations) < len(texts):
                    translations.append(texts[len(translations)])
                print(f"[Speedup] OpenAI GPT-4o-mini translated {len(texts)} segments!")
                return [str(t).strip() for t in translations[:len(texts)]]
    except Exception as e:
        print(f"OpenAI translation error: {e}")
    return None


def translate_segments(
    transcript: dict,
    source_language: str,
    target_language: str,
) -> dict:
    import time

    src = normalize_lang_code(source_language)
    tgt = normalize_lang_code(target_language) if target_language else "vi"

    segments = transcript.get("segments", [])
    if not segments:
        return transcript

    texts = [seg.get("text", "").strip() for seg in segments]
    trans_pref = os.getenv("TRANSLATE_PROVIDER", "auto").lower()

    translated_lines: list[str] | None = None

    # 1. Google Gemini Flash (Tự nhiên nhất & Chuẩn ngữ cảnh)
    if trans_pref == "gemini" or (trans_pref == "auto" and os.getenv("GEMINI_API_KEY")):
        translated_lines = translate_with_gemini(texts, src, tgt)

    # 2. Groq Llama 3.3 (Siêu tốc <1s)
    if not translated_lines and (trans_pref == "groq" or (trans_pref == "auto" and os.getenv("GROQ_API_KEY"))):
        translated_lines = translate_with_groq(texts, src, tgt)

    # 3. OpenAI GPT-4o-mini
    if not translated_lines and (trans_pref == "openai" or (trans_pref == "auto" and os.getenv("OPENAI_API_KEY"))):
        translated_lines = translate_with_openai(texts, src, tgt)

    # 4. Fallback to GoogleTranslator (Batch processing)
    if not translated_lines:
        batches: list[list[str]] = []
        current_batch: list[str] = []
        current_length = 0

        for text in texts:
            t = text if text else "..."
            item_len = len(t) + 5
            if current_length + item_len > 1500 and current_batch:
                batches.append(current_batch)
                current_batch = [t]
                current_length = len(t)
            else:
                current_batch.append(t)
                current_length += item_len

        if current_batch:
            batches.append(current_batch)

        translated_lines = []
        translator = GoogleTranslator(source=src, target=tgt)

        def safe_translate(text: str, retries: int = 3) -> str | None:
            for attempt in range(retries):
                try:
                    res = translator.translate(text)
                    if res:
                        return res
                except Exception:
                    time.sleep(1.0 * (attempt + 1))
            return None

        for batch in batches:
            combined_text = "\n###\n".join(batch)
            res = safe_translate(combined_text)
            
            if res:
                parts = [p.strip() for p in res.split("\n###\n")]
                if len(parts) == len(batch):
                    translated_lines.extend(parts)
                else:
                    for single_text in batch:
                        translated = safe_translate(single_text)
                        translated_lines.append(translated if translated else single_text)
                        time.sleep(0.2)
            else:
                print("Batch translate failed after retries, translating single items...")
                for single_text in batch:
                    translated = safe_translate(single_text)
                    translated_lines.append(translated if translated else single_text)
                    time.sleep(0.2)

            time.sleep(0.5)

    translated_segments = []
    for i, seg in enumerate(segments):
        t_text = translated_lines[i] if i < len(translated_lines) else seg.get("text", "")
        translated_segments.append({**seg, "text": t_text})

    return {**transcript, "segments": translated_segments}
