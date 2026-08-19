import math
import os
import random
from pathlib import Path
from typing import List, Tuple
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont


def get_audio_rms_envelope(audio_path: Path, fps: int = 25) -> List[float]:
    """
    Extracts RMS volume envelope per frame for mouth-sync animation.
    """
    try:
        from pydub import AudioSegment
        seg = AudioSegment.from_file(str(audio_path))
        seg = seg.set_channels(1).set_frame_rate(16000)
        samples = np.array(seg.get_array_of_samples(), dtype=np.float32)
        
        frame_len = int(16000 / fps)
        num_frames = max(1, int(len(samples) / frame_len))
        rms_list = []
        
        for i in range(num_frames):
            chunk = samples[i * frame_len : (i + 1) * frame_len]
            if len(chunk) == 0:
                rms_list.append(0.0)
            else:
                rms = np.sqrt(np.mean(chunk**2))
                rms_list.append(float(rms))
                
        max_rms = max(rms_list) if (rms_list and max(rms_list) > 0) else 1.0
        normalized = [min(1.0, r / (max_rms * 0.7 + 1e-5)) if r > (max_rms * 0.08) else 0.0 for r in rms_list]
        return normalized
    except Exception as e:
        print(f"Error calculating audio envelope: {e}")
        return [0.5 * (1 + math.sin(i * 0.8)) if (i % 25 > 3) else 0.0 for i in range(100)]


def load_photorealistic_avatar(char_type: str = "real", gender: str = "female") -> Image.Image:
    """
    Loads high-resolution photorealistic avatar asset (Female KOL, Male KOL, or 3D Anime Cat).
    """
    assets_dir = Path(__file__).resolve().parent.parent / "assets" / "avatars"
    
    if char_type == "anime":
        asset_file = assets_dir / "cat_anime.png"
    elif gender == "male":
        asset_file = assets_dir / "male_real.png"
    else:
        asset_file = assets_dir / "female_real.png"

    if asset_file.exists():
        try:
            return Image.open(asset_file).convert("RGBA")
        except Exception:
            pass

    # Fallback to gradient portrait if asset missing
    im = Image.new("RGBA", (1024, 1024), (30, 30, 45, 255))
    draw = ImageDraw.Draw(im)
    draw.ellipse([200, 200, 824, 824], fill=(255, 224, 189, 255), outline=(247, 37, 133, 255), width=8)
    return im


def animate_photorealistic_face(
    base_img: Image.Image,
    mouth_open: float,
    blink: bool,
    char_type: str = "real",
    gender: str = "female"
) -> Image.Image:
    """
    Applies realistic photorealistic mouth movement and natural eye blinking to human/avatar photos.
    """
    frame = base_img.copy()
    w, h = frame.size

    # Mouth Coordinates based on avatar type (normalized on 1024x1024)
    if char_type == "anime":
        mx, my = int(w * 0.50), int(h * 0.65)
        mw, mh_base = int(w * 0.12), int(h * 0.05)
    elif gender == "male":
        mx, my = int(w * 0.50), int(h * 0.67)
        mw, mh_base = int(w * 0.14), int(h * 0.05)
    else:
        mx, my = int(w * 0.50), int(h * 0.66)
        mw, mh_base = int(w * 0.13), int(h * 0.05)

    # 1. Realistic Lip Movement / Mouth Opening
    if mouth_open > 0.08:
        open_h = int(mh_base + mouth_open * (h * 0.065))
        open_w = int(mw + mouth_open * (w * 0.02))

        # Sample local skin/lip color from existing mouth region
        try:
            sample_lip = frame.getpixel((mx, my))
        except Exception:
            sample_lip = (200, 70, 90, 255)

        # Create feathered mouth opening layer
        mouth_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        m_draw = ImageDraw.Draw(mouth_layer)

        # Inner dark cavity
        m_draw.ellipse(
            [mx - open_w // 2, my - open_h // 3, mx + open_w // 2, my + open_h],
            fill=(45, 12, 18, 240)
        )
        # Upper teeth highlight
        m_draw.rounded_rectangle(
            [mx - open_w // 3, my - open_h // 4, mx + open_w // 3, my + max(2, open_h // 4)],
            radius=4,
            fill=(245, 245, 250, 230)
        )
        # Lower lip contour
        lip_r, lip_g, lip_b = sample_lip[0], sample_lip[1], sample_lip[2]
        m_draw.arc(
            [mx - open_w // 2 - 2, my, mx + open_w // 2 + 2, my + open_h + 3],
            start=10, end=170,
            fill=(lip_r, lip_g, lip_b, 220),
            width=max(3, int(h * 0.005))
        )

        # Soft blur edges of mouth layer for photorealistic blend
        mouth_blurred = mouth_layer.filter(ImageFilter.GaussianBlur(radius=1.5))
        frame.alpha_composite(mouth_blurred)

    # 2. Realistic Eye Blinking
    if blink:
        # Eye coordinates (left and right eyes)
        if char_type == "anime":
            eyes = [(int(w * 0.38), int(h * 0.48)), (int(w * 0.62), int(h * 0.48))]
            ew, eh = int(w * 0.12), int(h * 0.06)
        else:
            eyes = [(int(w * 0.42), int(h * 0.47)), (int(w * 0.58), int(h * 0.47))]
            ew, eh = int(w * 0.08), int(h * 0.04)

        blink_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        b_draw = ImageDraw.Draw(blink_layer)

        for ex, ey in eyes:
            try:
                skin_col = frame.getpixel((ex, ey - int(h * 0.04)))
            except Exception:
                skin_col = (250, 220, 200, 255)

            # Eyelid smooth cover
            b_draw.ellipse(
                [ex - ew // 2, ey - eh // 2, ex + ew // 2, ey + eh // 2],
                fill=(skin_col[0], skin_col[1], skin_col[2], 235)
            )
            # Eyelash line
            b_draw.arc(
                [ex - ew // 2, ey - eh // 4, ex + ew // 2, ey + eh // 2],
                start=0, end=180,
                fill=(40, 25, 20, 220),
                width=3
            )

        blink_blurred = blink_layer.filter(ImageFilter.GaussianBlur(radius=1.2))
        frame.alpha_composite(blink_blurred)

    return frame


def generate_talking_reviewer_video(
    audio_path: Path,
    product_img_path: Path,
    output_video_path: Path,
    char_type: str = "real",
    gender: str = "female",
    product_name: str = "SIÊU PHẨM AI",
    subtitles_ass_path: Path = None,
    fps: int = 25
) -> bool:
    """
    Generates a full 1080x1920 Split-Screen TikTok Reviewer Video:
    - Top Section (1080x960): Photorealistic Real Person KOL speaking & lip-synced to audio
    - Bottom Section (1080x960): Product Showcase with dynamic zoom & high conversion badges
    """
    import subprocess
    import tempfile
    import shutil

    envelope = get_audio_rms_envelope(audio_path, fps=fps)
    total_frames = len(envelope)
    if total_frames <= 0:
        total_frames = int(20 * fps)
        envelope = [0.4] * total_frames

    # Load Photorealistic Portrait
    base_avatar = load_photorealistic_avatar(char_type=char_type, gender=gender)

    temp_dir = Path(tempfile.mkdtemp(prefix="avatar_real_frames_"))
    try:
        # Load Product Image
        try:
            prod_img_raw = Image.open(product_img_path).convert("RGBA")
        except Exception:
            prod_img_raw = Image.new("RGBA", (800, 800), (247, 37, 133, 255))

        for frame_idx in range(total_frames):
            rms_val = envelope[frame_idx]
            blink = (frame_idx % 80 in [0, 1, 2])
            
            # Subtle natural sway for photorealistic human influencer
            sway_y = int(math.sin(frame_idx * 0.12) * 5)
            sway_x = int(math.cos(frame_idx * 0.08) * 3)

            # Generate animated face frame
            face_frame = animate_photorealistic_face(
                base_avatar,
                mouth_open=rms_val,
                blink=blink,
                char_type=char_type,
                gender=gender
            )

            # Compose Full Vertical 1080x1920 Frame
            canvas = Image.new("RGB", (1080, 1920), (15, 15, 24))
            draw = ImageDraw.Draw(canvas)

            # 1. TOP HALF: PHOTOREALISTIC INFLUENCER STUDIO (1080x960)
            # Crop/Resize Face Frame to top half 1080x960
            face_top = face_frame.resize((1080, 1080), Image.Resampling.LANCZOS)
            # Position with subtle natural sway
            crop_y = max(0, min(120, 60 + sway_y))
            crop_x = max(0, min(60, 30 + sway_x))
            face_cropped = face_top.crop((0, crop_y, 1080, crop_y + 960))
            canvas.paste(face_cropped.convert("RGB"), (0, 0))

            # Header Badge Overlay
            draw.rectangle([0, 0, 1080, 100], fill=(20, 20, 30, 180))
            role_title = "🐱 BÉ MÈO AI REVIEW" if char_type == "anime" else ("👩 KOL REVIEW TRÊN TAY" if gender == "female" else "👨 CHUYÊN GIA REVIEW")
            draw.text((50, 32), f"🔴 LIVE • {role_title}", fill=(255, 255, 255))
            draw.rectangle([850, 25, 1030, 75], fill=(247, 37, 133), outline=(255, 255, 255), width=2)
            draw.text((875, 38), "⭐ CHÍNH HÃNG", fill=(255, 255, 255))

            # Center Divider Bar
            draw.line([(0, 960), (1080, 960)], fill=(255, 215, 0), width=8)
            draw.rectangle([320, 935, 760, 985], fill=(255, 215, 0))
            draw.text((345, 948), "⬇️ SẢN PHẨM TRỰC TIẾP ⬇️", fill=(0, 0, 0))

            # 2. BOTTOM HALF: PRODUCT SHOWCASE WITH DYNAMIC FOCUS (1080x960)
            zoom_factor = 1.0 + (frame_idx / float(total_frames)) * 0.15
            pw = int(820 * zoom_factor)
            ph = int(820 * zoom_factor)
            prod_zoomed = prod_img_raw.resize((pw, ph), Image.Resampling.BILINEAR)
            
            left = max(0, (pw - 800) // 2)
            top = max(0, (ph - 800) // 2)
            prod_cropped = prod_zoomed.crop((left, top, left + 800, top + 800))

            # Product frame background
            draw.rectangle([120, 1020, 960, 1840], fill=(28, 28, 42), outline=(139, 92, 246), width=6)
            canvas.paste(prod_cropped.convert("RGB"), (140, 1030))

            # Bottom Call-to-action Banner
            draw.rectangle([80, 1720, 1000, 1840], fill=(18, 18, 28, 235), outline=(255, 215, 0), width=4)
            draw.text((110, 1740), f"🏷️ {product_name[:36].upper()}", fill=(255, 255, 255))
            draw.text((110, 1785), "👉 BẤM NGAY VÀO GIỎ HÀNG GÓC TRÁI ĐỂ MUA DEAL HỜI!", fill=(255, 215, 0))

            frame_file = temp_dir / f"f_{frame_idx:05d}.jpg"
            canvas.save(frame_file, quality=88)

        # Compile Video using FFmpeg
        vf_filter = "format=yuv420p"
        if subtitles_ass_path and subtitles_ass_path.exists():
            safe_ass = str(subtitles_ass_path).replace("\\", "/").replace(":", "\\:")
            vf_filter += f",ass='{safe_ass}'"

        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(fps),
            "-i", str(temp_dir / "f_%05d.jpg"),
            "-i", str(audio_path),
            "-vf", vf_filter,
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            str(output_video_path)
        ]

        res = subprocess.run(cmd, capture_output=True, text=True)
        return output_video_path.exists() and output_video_path.stat().st_size > 1000
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
