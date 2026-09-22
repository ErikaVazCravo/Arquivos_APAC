"""Execute com Python no Windows para gerar Editor_APAC.exe sem console."""
from pathlib import Path
import subprocess
import sys


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    subprocess.run([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--onefile", "--windowed", "--name", "Editor_APAC",
        "--add-data", f"{root / 'web_ui'};web_ui",
        "--distpath", str(root), "--workpath", str(root / "build"),
        "--specpath", str(root / "build"), str(root / "Editor_APAC.py"),
    ], cwd=root, check=True)
