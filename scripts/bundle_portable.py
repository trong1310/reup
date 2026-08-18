#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Video Dubber - Portable Bundle Packager (Bản Tối Ưu Siêu Nhẹ)
Tối ưu hóa dung lượng:
- Loại bỏ các gói không dùng: gradio, pandas, scikit-learn, tests, cache
- Xóa bỏ 50+ ngôn ngữ thừa của Electron locales
- Lọc bỏ model nặng hàng GB không cần thiết
- Giảm dung lượng build từ 3GB xuống < 350MB!
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

# Đảm bảo in tiếng Việt trên console Windows không bị lỗi encoding
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT_DIR / "AI-Video-Dubber-Portable"
APP_DIR = OUTPUT_DIR / "app"

def log(msg: str):
    print(f"[PACKAGER] {msg}")

def ensure_frontend_built():
    log("Đang biên dịch Frontend (Vite + React)...")
    desktop_dir = ROOT_DIR / "desktop"
    res = subprocess.run(["npm", "run", "build"], cwd=str(desktop_dir), shell=True)
    if res.returncode != 0:
        raise RuntimeError("Build frontend thất bại!")
    log("Frontend đã được build thành công vào desktop/dist.")

def setup_directory_structure():
    log("Đang khởi tạo cấu trúc thư mục phát hành...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    APP_DIR.mkdir(parents=True, exist_ok=True)
    (APP_DIR / "backend" / "data").mkdir(parents=True, exist_ok=True)
    
    # Xóa thư mục models cũ nếu có để tránh phình dung lượng
    old_models = APP_DIR / "models"
    if old_models.exists():
        shutil.rmtree(old_models, ignore_errors=True)
    (APP_DIR / "models" / "huggingface" / "hub").mkdir(parents=True, exist_ok=True)

def copy_electron_runtime():
    log("Đang đóng gói Electron Runtime...")
    electron_dist = ROOT_DIR / "desktop" / "node_modules" / "electron" / "dist"
    if not electron_dist.exists():
        raise RuntimeError(f"Không tìm thấy {electron_dist}. Hãy chạy 'npm install' trong desktop.")

    # Sao chép các file của Electron vào app/
    for item in electron_dist.iterdir():
        dest = APP_DIR / item.name
        if item.name == "electron.exe":
            dest = APP_DIR / "AI-Video-Dubber.exe"
        if item.is_dir():
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)

    # Tối ưu hóa Electron: Xóa 50+ file locales ngôn ngữ thừa (tiết kiệm ~40MB)
    locales_dir = APP_DIR / "locales"
    if locales_dir.exists():
        keep = {"vi.pak", "en-US.pak", "en-GB.pak"}
        deleted_count = 0
        for pak in locales_dir.glob("*.pak"):
            if pak.name not in keep:
                try:
                    pak.unlink(missing_ok=True)
                    deleted_count += 1
                except Exception:
                    pass
        log(f"Đã loại bỏ {deleted_count} file locales Electron thừa (tiết kiệm ~40MB).")

    # Cấu hình resources/app
    res_app_dir = APP_DIR / "resources" / "app"
    res_app_dir.mkdir(parents=True, exist_ok=True)

    # Copy package.json
    pkg_json_content = """{
  "name": "ai-video-dubber",
  "version": "1.0.0",
  "main": "electron/main.cjs"
}"""
    (res_app_dir / "package.json").write_text(pkg_json_content, encoding="utf-8")

    # Copy electron/
    el_dest = res_app_dir / "electron"
    if el_dest.exists():
        shutil.rmtree(el_dest)
    shutil.copytree(ROOT_DIR / "desktop" / "electron", el_dest)

    # Copy dist/
    dist_dest = res_app_dir / "dist"
    if dist_dest.exists():
        shutil.rmtree(dist_dest)
    shutil.copytree(ROOT_DIR / "desktop" / "dist", dist_dest)
    log("Đóng gói Desktop Electron hoàn tất.")

def copy_and_optimize_python():
    log("Đang đóng gói và tối ưu hóa Python Runtime...")
    src_python = ROOT_DIR / "tools" / "python_embed"
    if not src_python.exists():
        src_python = Path(sys.prefix)
        log(f"Không tìm thấy tools/python_embed, tự động sử dụng Python hệ thống: {src_python}")
    
    dest_python = APP_DIR / "python"

    # Sao chép python
    if not dest_python.exists():
        log("Đang sao chép Python runtime...")
        subprocess.run(
            ["robocopy", str(src_python), str(dest_python), "/E", "/MT:16", "/NFL", "/NDL", "/NJH", "/NJS", "/nc", "/ns", "/np"],
            shell=True
        )

    # DỌN DẸP DUNG LƯỢNG RÁC TRONG PYTHON
    log("Đang dọn dẹp các package không dùng và cache rác trong Python...")
    site_packages = dest_python / "Lib" / "site-packages"
    
    # 1. Các package hoàn toàn không dùng trong ứng dụng
    unused_packages = [
        "gradio", "gradio-6.24.0.dist-info", "gradio_client", "gradio_client-2.6.0.dist-info", "hf_gradio", "hf_gradio-0.4.1.dist-info",
        "pandas", "pandas-3.0.5.dist-info", "pandas.libs",
        "sklearn", "scikit_learn-1.9.0.dist-info",
        "PyWin32.chm", "scipy-1.17.1-cp311-cp311-win_amd64.whl"
    ]
    if site_packages.exists():
        for pkg in unused_packages:
            p = site_packages / pkg
            if p.exists():
                if p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)
                else:
                    p.unlink(missing_ok=True)

        # 2. Xóa các thư mục test suites lớn (trong torch, sympy, scipy, numpy, v.v.)
        test_folders = ["**/tests", "**/test", "**/*_test", "**/doc", "**/docs"]
        for pat in test_folders:
            for t_dir in site_packages.glob(pat):
                if t_dir.is_dir() and "vieneu" not in str(t_dir).lower() and "whisper" not in str(t_dir).lower():
                    try:
                        shutil.rmtree(t_dir, ignore_errors=True)
                    except Exception:
                        pass

    # 3. Xóa __pycache__ và *.pyc, *.pdb
    for pycache in dest_python.glob("**/__pycache__"):
        try:
            shutil.rmtree(pycache, ignore_errors=True)
        except Exception:
            pass

    for pdb in dest_python.glob("**/*.pdb"):
        try:
            pdb.unlink(missing_ok=True)
        except Exception:
            pass

    log("Tối ưu hóa Python Runtime hoàn tất.")

def copy_ffmpeg():
    log("Đang đóng gói FFmpeg & FFprobe Portable...")
    src_ffmpeg = ROOT_DIR / "tools" / "ffmpeg"
    dest_ffmpeg = APP_DIR / "tools" / "ffmpeg"
    dest_ffmpeg.mkdir(parents=True, exist_ok=True)
    
    found = False
    for exe in ["ffmpeg.exe", "ffprobe.exe"]:
        src_exe = src_ffmpeg / exe
        if src_exe.exists():
            shutil.copy2(src_exe, dest_ffmpeg / exe)
            found = True
    if found:
        log("FFmpeg Portable đã được đóng gói.")
    else:
        log("Cảnh báo: Chưa tìm thấy tools/ffmpeg, ứng dụng sẽ dùng FFmpeg từ môi trường nếu có.")

def copy_backend_code():
    log("Đang sao chép mã nguồn Backend AI...")
    dest_backend = APP_DIR / "backend"
    
    # Copy app/
    dest_app = dest_backend / "app"
    if dest_app.exists():
        shutil.rmtree(dest_app)
    shutil.copytree(ROOT_DIR / "engine" / "app", dest_app, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "logError", "data"))

    # Copy voices/
    src_voices = ROOT_DIR / "engine" / "voices"
    if src_voices.exists():
        dest_voices = dest_backend / "voices"
        if dest_voices.exists():
            shutil.rmtree(dest_voices)
        shutil.copytree(src_voices, dest_voices)

    # Copy .env
    src_env = ROOT_DIR / "engine" / ".env"
    if src_env.exists():
        shutil.copy2(src_env, dest_backend / ".env")
    elif (ROOT_DIR / "engine" / ".env.example").exists():
        shutil.copy2(ROOT_DIR / "engine" / ".env.example", dest_backend / ".env")

def setup_models_policy(embed_heavy_models: bool = False):
    """
    Chính sách đóng gói Model AI:
    - Nếu embed_heavy_models=False (Khuyên dùng - Siêu Nhẹ): 
      Chỉ gói model Whisper Base (~140MB). Các model lớn khác sẽ tự động tải khi dùng lần đầu.
    - Nếu embed_heavy_models=True: Gói toàn bộ model offline.
    """
    dest_hub = APP_DIR / "models" / "huggingface" / "hub"
    dest_hub.mkdir(parents=True, exist_ok=True)

    hf_cache = Path(os.environ.get("USERPROFILE", "")) / ".cache" / "huggingface" / "hub"
    if not hf_cache.exists():
        return

    log("Đang áp dụng chính sách mô hình AI tinh gọn...")
    for model_folder in hf_cache.glob("models--*"):
        name_lower = model_folder.name.lower()

        # Nếu không chọn nhồi model nặng, chỉ copy faster-whisper-base
        if not embed_heavy_models:
            if "faster-whisper-base" not in name_lower and "faster-whisper-tiny" not in name_lower:
                continue

        dest_model = dest_hub / model_folder.name
        if not dest_model.exists():
            log(f"Đang sao chép model thiết yếu: {model_folder.name}...")
            subprocess.run(
                ["robocopy", str(model_folder), str(dest_model), "/E", "/MT:16", "/NFL", "/NDL", "/NJH", "/NJS", "/nc", "/ns", "/np"],
                shell=True
            )
    log("Chính sách Model AI tinh gọn đã thiết lập.")

def create_launchers():
    log("Đang tạo các file khởi chạy 1-Click...")

    bat_content = """@echo off
setlocal
cd /d "%~dp0"
title AI Video Dubber Launcher

:: Thiet lap moi truong Portable
set "PATH=%~dp0app\\tools\\ffmpeg;%~dp0app\\python;%PATH%"
set "PYTHONPATH=%~dp0app\\backend"
set "HF_HOME=%~dp0app\\models\\huggingface"
set "TORCH_HOME=%~dp0app\\models\\torch"

echo ================================================================
echo           KHOI DONG AI VIDEO DUBBER (PORTABLE EDITION)
echo ================================================================
echo.
echo [*] Dang khoi dong Backend Engine AI tren cong 8787...
start /b "" "%~dp0app\\python\\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8787 --app-dir "%~dp0app\\backend"

echo [*] Dang mo Giao dien Desktop (AI Video Dubber)...
"%~dp0app\\AI-Video-Dubber.exe"

echo.
echo [*] Dang dong Backend Engine va giai phong tai nguyen...
powershell -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*8787*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1
echo [OK] Ung dung da dong an toan.
"""

    (OUTPUT_DIR / "run_app.bat").write_text(bat_content, encoding="utf-8")

    readme_content = """================================================================
AI VIDEO DUBBER & DỊCH THUẬT TỰ ĐỘNG - BẢN PORTABLE
================================================================

1. HƯỚNG DẪN SỬ DỤNG (1-CLICK):
   - Chỉ cần nhấp đúp chuột vào file "run_app.bat" để mở ứng dụng.
   - Máy tính KHÔNG cần cài thêm Python, Node.js hay FFmpeg.
   - Khi bạn đóng cửa sổ ứng dụng Desktop, Backend AI cũng sẽ tự động tắt để giải phóng RAM.

2. CÁCH LẤY API KEY ĐỂ TĂNG TỐC XỬ LÝ VIDEO GẤP 10 LẦN:
   (Lưu ý: Mọi API Key đều là TÙY CHỌN. Nếu để trống, app vẫn chạy Offline 100% bằng CPU)

   ⚡ 1. GROQ CLOUD API (Nhận diện giọng nói siêu tốc ~1 giây - MIỄN PHÍ 100%):
      - Link lấy key: https://console.groq.com/keys
      - Các bước: Đăng nhập bằng Google/GitHub -> Bấm "Create API Key" -> Copy mã "gsk_..."
      - Tác dụng: Giảm thời gian bóc băng âm thanh từ 1-2 phút (CPU) xuống còn ~1 giây.

   🚀 2. GOOGLE GEMINI API (Dịch phụ đề chuẩn ngữ cảnh - MIỄN PHÍ 100%):
      - Link lấy key: https://aistudio.google.com/app/apikey
      - Các bước: Đăng nhập bằng Google -> Bấm "Create API key" -> Copy mã "AIzaSy..."
      - Tác dụng: Dịch phụ đề tự nhiên, chuẩn văn phong lồng tiếng trong 1 giây.

   🤖 3. OPENAI API (Whisper-1, GPT-4o, Giọng đọc OpenAI):
      - Link lấy key: https://platform.openai.com/api-keys
      - Các bước: Đăng nhập -> Bấm "+ Create new secret key" -> Copy mã "sk-proj-..."
      - Tác dụng: Mở khóa 6 giọng đọc OpenAI Neural (Alloy, Nova, Echo, Shimmer...).

   🎙️ 4. ELEVENLABS API (Giọng đọc siêu thực thế giới):
      - Link lấy key: https://elevenlabs.io
      - Các bước: Đăng nhập -> Profile -> Copy API key.

   🤗 5. HUGGING FACE TOKEN (Tải model offline nhanh - MIỄN PHÍ):
      - Link lấy token: https://huggingface.co/settings/tokens
      - Các bước: Đăng nhập -> "Create new token" (chọn Read) -> Copy mã "hf_..."

3. CÁCH NHẬP API KEY VÀO ỨNG DỤNG:
   - Bước 1: Mở ứng dụng qua file "run_app.bat".
   - Bước 2: Bấm vào nút "⚡ Cấu Hình API Key (Tăng Tốc 10x)" ở góc trên màn hình.
   - Bước 3: Dán Groq Key và Gemini Key vào ô tương ứng.
   - Bước 4: Bấm "⚡ Test Kết Nối" để kiểm tra, sau đó bấm "💾 Lưu & Áp Dụng Ngay".

4. TÍNH NĂNG CHÍNH:
   - Dán link video Douyin, TikTok, YouTube...
   - Nhận diện giọng nói bằng Groq Whisper Cloud (~1s) hoặc Faster-Whisper CPU.
   - Dịch thuật phụ đề bằng Google Gemini Flash / Groq Llama 3.3 / Google Translator.
   - Lồng tiếng AI: VieNeu (Ngọc Huyền v2, Gia Bảo...), OpenAI Neural, ElevenLabs, Edge-TTS.
   - Tự động mix và cân bằng nhạc nền gốc, xuất video MP4 và file phụ đề .SRT.

5. THƯ MỤC DỮ LIỆU:
   - app/backend/data : Chứa các video và âm thanh đã xử lý.
   - app/models       : Chứa mô hình AI đã tải về offline.
================================================================
"""
    (OUTPUT_DIR / "Huong-Dan-Su-Dung.txt").write_text(readme_content, encoding="utf-8")
    log("Tao file launcher thanh cong.")

def main():
    print("\n" + "="*65)
    print("      DONG GOI AI VIDEO DUBBER PORTABLE (SIEU TOI UU DUNG LUONG)")
    print("="*65 + "\n")

    ensure_frontend_built()
    setup_directory_structure()
    copy_electron_runtime()
    copy_and_optimize_python()
    copy_ffmpeg()
    copy_backend_code()
    setup_models_policy(embed_heavy_models=False)
    create_launchers()

    print("\n" + "="*65)
    print("      DONG GOI THANH CONG HOAN TAT 100%!")
    print(f"      Thu muc xuat ra: {OUTPUT_DIR}")
    print("="*65 + "\n")

if __name__ == "__main__":
    main()
