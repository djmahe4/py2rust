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
                code = result.stdout.decode()
        except (subprocess.TimeoutExpired, OSError):
            pass
            
    # Post-process: strip trailing whitespace on each line, strip trailing blank lines, end with exactly one newline
    lines = [line.rstrip() for line in code.splitlines()]
    while lines and not lines[-1]:
        lines.pop()
        
    return "\n".join(lines) + "\n" if lines else ""
