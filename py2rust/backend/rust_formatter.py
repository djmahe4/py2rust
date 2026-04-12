from __future__ import annotations
import subprocess
import shutil


def format_rust(code: str) -> str:
    if shutil.which("rustfmt"):
        try:
            result = subprocess.run(
                ["rustfmt", "--edition", "2021"],
                input=code.encode(),
                capture_output=True,
                timeout=10,
            )
            if result.returncode == 0:
                return result.stdout.decode()
        except (subprocess.TimeoutExpired, OSError):
            pass
    return code
