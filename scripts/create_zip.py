#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tạo file nén ZIP từ thư mục AI-Video-Dubber-Portable nhanh chóng và ổn định.
"""
import sys
import shutil
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT_DIR / "AI-Video-Dubber-Portable"
ZIP_DEST = ROOT_DIR / "AI-Video-Dubber-Portable"

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

def main():
    if not SOURCE_DIR.exists():
        print(f"[ERROR] Chua tim thay thu muc {SOURCE_DIR}. Hay chay 'build-portable.bat' truoc!")
        return

    print(f"[*] Dang nen thu muc thanh file {ZIP_DEST.name}.zip...")
    shutil.make_archive(str(ZIP_DEST), "zip", root_dir=str(ROOT_DIR), base_dir="AI-Video-Dubber-Portable")
    zip_file = ROOT_DIR / f"{ZIP_DEST.name}.zip"
    if zip_file.exists():
        size_mb = round(zip_file.stat().st_size / (1024 * 1024), 2)
        print(f"[OK] Da tao thanh cong file: {zip_file.name} ({size_mb} MB)!")

if __name__ == "__main__":
    main()
