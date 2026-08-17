#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Video Dubber - macOS Packager
Đóng gói bộ phần mềm AI Video Dubber dành riêng cho macOS (Apple Silicon M1/M2/M3/M4 & Intel).
Tạo thư mục AI-Video-Dubber-macOS và file nén zip sẵn sàng chuyển sang Mac sử dụng.
"""

import os
import sys
import shutil
import zipfile
import subprocess
from pathlib import Path

# Fix console encoding on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT_DIR / "AI-Video-Dubber-macOS"
APP_DIR = OUTPUT_DIR / "app"

def log(msg: str):
    print(f"[MAC-PACKAGER] {msg}")

def ensure_frontend_built():
    log("Đang biên dịch Frontend (Vite + React)...")
    desktop_dir = ROOT_DIR / "desktop"
    res = subprocess.run(["npm", "run", "build"], cwd=str(desktop_dir), shell=True)
    if res.returncode != 0:
        raise RuntimeError("Build frontend thất bại!")
    log("Frontend đã được build thành công vào desktop/dist.")

def setup_directory_structure():
    log("Đang khởi tạo cấu trúc thư mục phát hành macOS...")
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR, ignore_errors=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    APP_DIR.mkdir(parents=True, exist_ok=True)
    (APP_DIR / "backend" / "data").mkdir(parents=True, exist_ok=True)
    (APP_DIR / "desktop").mkdir(parents=True, exist_ok=True)

def copy_macos_assets():
    log("Đang đóng gói mã nguồn Desktop và Backend tương thích macOS...")
    
    # 1. Sao chép desktop (dist, electron, package.json)
    desktop_src = ROOT_DIR / "desktop"
    desktop_dest = APP_DIR / "desktop"
    
    # Copy dist
    shutil.copytree(desktop_src / "dist", desktop_dest / "dist")
    # Copy electron
    shutil.copytree(desktop_src / "electron", desktop_dest / "electron")
    # Copy package.json & package-lock if any
    shutil.copy2(desktop_src / "package.json", desktop_dest / "package.json")
    
    # 2. Sao chép backend (app, voices, requirements, .env)
    engine_src = ROOT_DIR / "engine"
    backend_dest = APP_DIR / "backend"
    
    shutil.copytree(
        engine_src / "app",
        backend_dest / "app",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "logError", "data")
    )
    
    if (engine_src / "voices").exists():
        shutil.copytree(engine_src / "voices", backend_dest / "voices")
        
    if (engine_src / "requirements.txt").exists():
        shutil.copy2(engine_src / "requirements.txt", backend_dest / "requirements.txt")
        
    if (engine_src / ".env").exists():
        shutil.copy2(engine_src / ".env", backend_dest / ".env")
    elif (engine_src / ".env.example").exists():
        shutil.copy2(engine_src / ".env.example", backend_dest / ".env")

def create_macos_launchers():
    log("Đang tạo các script khởi chạy 1-Click cho macOS...")
    
    # File run_app.command (Người dùng Mac chỉ cần nhấp đúp để chạy)
    command_content = """#!/bin/bash
# ==============================================================================
# AI Video Dubber - 1-Click Launcher for macOS
# ==============================================================================

# Chuyển về đúng thư mục chứa script
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

echo "================================================================"
echo "          AI VIDEO DUBBER & DỊCH THUẬT (macOS EDITION)          "
echo "================================================================"
echo ""

# Kiểm tra Python 3
if command -v python3 &>/dev/null; then
    PY_CMD="python3"
elif command -v python &>/dev/null; then
    PY_CMD="python"
else
    echo "[!] Lỗi: Chưa tìm thấy Python 3 trên máy Mac của bạn."
    echo "[*] Vui lòng cài Python 3 qua Homebrew: 'brew install python' hoặc tải từ python.org"
    read -p "Nhấn Enter để thoát..."
    exit 1
fi

echo "[*] Đang sử dụng: $($PY_CMD --version)"

# Khởi tạo Virtualenv nếu chưa có
if [ ! -d "app/backend/.venv" ]; then
    echo "[*] Lần đầu khởi chạy: Đang tạo môi trường ảo Python (.venv)..."
    $PY_CMD -m venv app/backend/.venv
    source app/backend/.venv/bin/activate
    echo "[*] Đang cài đặt các thư viện AI thiết yếu..."
    pip install -r app/backend/requirements.txt
else
    source app/backend/.venv/bin/activate
fi

# Khởi động Backend Engine FastAPI ở chế độ nền
echo "[*] Đang khởi động Backend Engine AI trên cổng 8787..."
export PYTHONPATH="$DIR/app/backend"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8787 --app-dir "$DIR/app/backend" &
BACKEND_PID=$!

# Đảm bảo tắt backend khi đóng cửa sổ
cleanup() {
    echo ""
    echo "[*] Đang tắt Backend Engine (PID: $BACKEND_PID)..."
    kill -9 $BACKEND_PID 2>/dev/null
    exit 0
}
trap cleanup EXIT INT TERM

# Đợi backend sẵn sàng
sleep 2

# Khởi động Desktop App (Electron hoặc mở trình duyệt nếu chưa cài Node/Electron)
cd "$DIR/app/desktop"
if [ ! -d "node_modules" ]; then
    if command -v npm &>/dev/null; then
        echo "[*] Đang cài đặt giao diện Desktop Electron..."
        npm install --omit=dev
    fi
fi

if command -v npx &>/dev/null; then
    echo "[*] Đang mở giao diện ứng dụng Desktop..."
    npx electron electron/main.cjs
else
    echo "[*] Mở giao diện trên trình duyệt web..."
    open "http://127.0.0.1:8787/docs"
fi

# Chờ tiến trình kết thúc
wait $BACKEND_PID
"""
    
    run_command_file = OUTPUT_DIR / "run_app.command"
    # Write LF line endings for Unix/macOS
    with open(run_command_file, "w", newline="\n", encoding="utf-8") as f:
        f.write(command_content)
        
    # File cài đặt 1 lần cho macOS
    setup_sh_content = """#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

echo "=== CÀI ĐẶT MÔI TRƯỜNG CHO MAC OS ==="
chmod +x run_app.command
xattr -cr "$DIR" 2>/dev/null

if command -v brew &>/dev/null; then
    echo "[*] Kiểm tra FFmpeg qua Homebrew..."
    if ! command -v ffmpeg &>/dev/null; then
        brew install ffmpeg
    fi
fi

echo "[*] Đang tạo môi trường Python..."
python3 -m venv app/backend/.venv
source app/backend/.venv/bin/activate
pip install --upgrade pip
pip install -r app/backend/requirements.txt

cd app/desktop
npm install

echo "=== CÀI ĐẶT HOÀN TẤT! NHẤP ĐÚP VÀO run_app.command ĐỂ CHẠY ==="
"""
    setup_sh_file = OUTPUT_DIR / "setup_mac.sh"
    with open(setup_sh_file, "w", newline="\n", encoding="utf-8") as f:
        f.write(setup_sh_content)

    # Hướng dẫn chi tiết cho người dùng Mac
    readme_mac = """================================================================
AI VIDEO DUBBER & DỊCH THUẬT TỰ ĐỘNG - PHIÊN BẢN MAC OS
================================================================

1. YÊU CẦU HỆ THỐNG:
   - macOS Catalina, Big Sur, Monterey, Ventura, Sonoma hoặc Sequoia.
   - Hỗ trợ cả chip Apple Silicon (M1/M2/M3/M4) lẫn chip Intel.
   - Đã cài Python 3 và Homebrew/Node.js (khuyên dùng).

2. CÁCH SỬ DỤNG (RẤT ĐƠN GIẢN):
   - Bước 1: Nhấp đúp chuột vào file "run_app.command".
   - Bước 2: Ứng dụng sẽ tự động chạy Backend AI và mở cửa sổ Desktop.
   - Khi bạn đóng cửa sổ ứng dụng, Backend cũng sẽ tự động tắt giải phóng RAM.

3. CÁCH LẤY API KEY ĐỂ TĂNG TỐC XỬ LÝ VIDEO GẤP 10 LẦN:
   (Lưu ý: Mọi API Key đều là TÙY CHỌN. Nếu để trống, app vẫn chạy Offline bằng CPU)

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

4. CÁCH NHẬP API KEY VÀO ỨNG DỤNG:
   - Bước 1: Mở app qua file "run_app.command".
   - Bước 2: Bấm vào nút "⚡ Cấu Hình API Key (Tăng Tốc 10x)" ở góc trên màn hình.
   - Bước 3: Dán Groq Key và Gemini Key vào ô tương ứng.
   - Bước 4: Bấm "⚡ Test Kết Nối" để kiểm tra, sau đó bấm "💾 Lưu & Áp Dụng Ngay".

5. LƯU Ý KHI GẶP LỖI BẢO MẬT TRÊN MAC (GATEKEEPER):
   Nếu Mac hiển thị thông báo "run_app.command cannot be opened because it is from an unidentified developer":
   - Nhấp chuột phải (hoặc giữ Control + Click) vào file "run_app.command" -> Chọn "Open".
   - Hoặc mở Terminal, gõ lệnh:
     chmod +x run_app.command
     xattr -cr .

6. TÍNH NĂNG CHÍNH:
   - Dán link Douyin, TikTok, YouTube -> Tải và bóc âm thanh.
   - Nhận diện giọng nói siêu tốc qua Groq Whisper Cloud (~1s) hoặc Faster-Whisper.
   - Dịch thuật AI chuẩn ngữ cảnh lồng tiếng qua Gemini Flash / Llama 3.3.
   - Lồng tiếng AI (VieNeu, OpenAI Neural, ElevenLabs, Edge-TTS).
   - Xuất video MP4 lồng tiếng và file phụ đề .SRT.
================================================================
"""
    (OUTPUT_DIR / "Huong-Dan-Mac.txt").write_text(readme_mac, encoding="utf-8")
    (OUTPUT_DIR / "Huong-Dan-Su-Dung.txt").write_text(readme_mac, encoding="utf-8")
    log("Đã tạo đầy đủ launcher và hướng dẫn cho macOS.")

def create_zip_archive():
    zip_path = ROOT_DIR / "AI-Video-Dubber-macOS.zip"
    log(f"Đang nén toàn bộ thư mục thành file: {zip_path.name}...")
    
    if zip_path.exists():
        zip_path.unlink(missing_ok=True)
        
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for root, dirs, files in os.walk(OUTPUT_DIR):
            for file in files:
                file_path = Path(root) / file
                arcname = file_path.relative_to(ROOT_DIR)
                
                # Set executable permissions in zip for .command and .sh
                zinfo = zipfile.ZipInfo.from_file(file_path, arcname=str(arcname))
                if file.endswith((".command", ".sh")):
                    zinfo.external_attr = 0o755 << 16  # rwxr-xr-x permissions
                zf.writestr(zinfo, file_path.read_bytes())
                
    size_mb = zip_path.stat().st_size / (1024 * 1024)
    log(f"Nén file zip hoàn tất! Dung lượng: {size_mb:.2f} MB")

def main():
    print("\n" + "="*65)
    print("      ĐÓNG GÓI BẢN PHÁT HÀNH DÀNH RIÊNG CHO MAC OS")
    print("="*65 + "\n")
    
    ensure_frontend_built()
    setup_directory_structure()
    copy_macos_assets()
    create_macos_launchers()
    create_zip_archive()
    
    print("\n" + "="*65)
    print("      ĐÓNG GÓI CHO MAC OS HOÀN TẤT 100%!")
    print(f"      - Thư mục: {OUTPUT_DIR}")
    print(f"      - File nén: {ROOT_DIR / 'AI-Video-Dubber-macOS.zip'}")
    print("="*65 + "\n")

if __name__ == "__main__":
    main()
