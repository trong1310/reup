import os
import sys
import shutil
import subprocess
import zipfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT_DIR / "AI-Video-Dubber-Portable"
ZIP_FILE = ROOT_DIR / "AI-Video-Dubber-Portable.zip"

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

def create_zip_archive(source_dir: Path, zip_file: Path):
    if not source_dir.exists():
        print(f"[ERROR] Chua tim thay thu muc {source_dir.name}. Hay chay 'build-portable.bat' truoc!")
        return False

    if zip_file.exists():
        try:
            zip_file.unlink()
        except Exception as e:
            print(f"[WARN] Khong the xoa file zip cu: {e}")

    print(f"[*] Dang nen thu muc '{source_dir.name}' thanh '{zip_file.name}'...")

    # Cach 1: Dung system tar (bsdtar) tren Windows/macOS/Linux - Rất nhanh & ổn định
    tar_cmd = shutil.which("tar")
    if tar_cmd:
        try:
            print("[*] Dang dung tar he thong de nen toc do cao...")
            res = subprocess.run(
                [tar_cmd, "-a", "-c", "-f", zip_file.name, source_dir.name],
                cwd=str(ROOT_DIR),
                capture_output=True,
                text=True
            )
            if res.returncode == 0 and zip_file.exists():
                size_mb = round(zip_file.stat().st_size / (1024 * 1024), 2)
                print(f"[OK] Da nen thanh cong file: {zip_file.name} ({size_mb} MB)!")
                return True
        except Exception as e:
            print(f"[WARN] Dail tar me loi ({e}), chuyen sang zipfile Python...")

    # Cach 2: Dung zipfile Python (Fallback)
    try:
        count = 0
        with zipfile.ZipFile(zip_file, "w", zipfile.ZIP_DEFLATED, compresslevel=5) as zf:
            for root, _, files in os.walk(source_dir):
                for file in files:
                    file_path = Path(root) / file
                    arcname = file_path.relative_to(ROOT_DIR)
                    try:
                        zf.write(file_path, arcname=str(arcname))
                        count += 1
                        if count % 1000 == 0:
                            print(f"    - Da nen {count} file...")
                    except Exception as fe:
                        pass

        if zip_file.exists():
            size_mb = round(zip_file.stat().st_size / (1024 * 1024), 2)
            print(f"[OK] Da nen thanh cong file: {zip_file.name} ({size_mb} MB)!")
            return True
    except Exception as e:
        print(f"[ERROR] Loi khi nen ZIP: {e}")
        return False

def main():
    success = create_zip_archive(SOURCE_DIR, ZIP_FILE)
    if not success:
        sys.exit(1)

if __name__ == "__main__":
    main()

