from __future__ import annotations
import tempfile
from pathlib import Path
import pytest
import subprocess
import os

from py2rust.project.repo_compiler import compile_repo
from py2rust.config import CompilerConfig, AsyncRuntime

def run_cargo_cmd(workspace_dir: Path, cmd: list[str]) -> subprocess.CompletedProcess:
    """Helper to run a cargo command with standard system cargo paths."""
    env = os.environ.copy()
    cargo_bin = os.path.expanduser("~/.cargo/bin")
    if cargo_bin not in env.get("PATH", ""):
        env["PATH"] = f"{cargo_bin}:{env.get('PATH', '')}"
    env["PYO3_USE_ABI3_FORWARD_COMPATIBILITY"] = "1"
    
    return subprocess.run(
        cmd,
        cwd=workspace_dir,
        env=env,
        capture_output=True,
        text=True
    )

def test_repo_simple():
    """
    Test 1: Simple Cross-Imports (math_ops -> utils -> main)
    Verifies modular package compilation, cargo check, and cargo run.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        
        pkg_dir = tmp_path / "pkg_simple"
        pkg_dir.mkdir()
        
        # 1. Write the package modules
        (pkg_dir / "__init__.py").write_text("")
        (pkg_dir / "math_ops.py").write_text(
            "def add_numbers(a: int, b: int) -> int:\n"
            "    return a + b\n"
        )
        (pkg_dir / "utils.py").write_text(
            "from .math_ops import add_numbers\n"
            "def format_sum(a: int, b: int) -> str:\n"
            "    s = add_numbers(a, b)\n"
            "    return f\"Sum is {s}\"\n"
        )
        (pkg_dir / "main.py").write_text(
            "from .utils import format_sum\n"
            "def main() -> None:\n"
            "    msg = format_sum(5, 7)\n"
            "    print(msg)\n"
        )
        
        # 2. Write the pyproject.toml
        (tmp_path / "pyproject.toml").write_text(
            "[project]\n"
            "name = \"pkg_simple\"\n"
            "version = \"0.1.0\"\n"
            "\n"
            "[tool.py2rust]\n"
            "package_dir = \"pkg_simple\"\n"
            "entry_point = \"pkg_simple.main\"\n"
        )
        
        out_dir = tmp_path / "dist"
        
        # 3. Compile the package
        config = CompilerConfig(
            input_file=str(tmp_path),
            output_file=str(out_dir),
            verbose=True,
            verify=False
        )
        
        success = compile_repo(config)
        assert success is True
        
        # 4. Verify generated file existence
        assert (out_dir / "Cargo.toml").exists()
        assert (out_dir / "src" / "main.rs").exists()
        assert (out_dir / "src" / "pkg_simple" / "math_ops.rs").exists()
        assert (out_dir / "src" / "pkg_simple" / "utils.rs").exists()
        
        # 5. Run cargo check
        check_res = run_cargo_cmd(out_dir, ["cargo", "check"])
        assert check_res.returncode == 0, f"Cargo check failed:\n{check_res.stderr}"
        
        # 6. Run cargo run
        run_res = run_cargo_cmd(out_dir, ["cargo", "run"])
        assert run_res.returncode == 0, f"Cargo run failed:\n{run_res.stderr}"
        assert "Sum is 12" in run_res.stdout

def test_repo_classes():
    """
    Test 2: Cross-Module Class Hierarchy (base -> derived -> main)
    Verifies modular class inheritance, compilation, and execution.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        
        pkg_dir = tmp_path / "pkg_classes"
        pkg_dir.mkdir()
        
        # 1. Write the package modules
        (pkg_dir / "__init__.py").write_text("")
        (pkg_dir / "base.py").write_text(
            "class Shape:\n"
            "    def __init__(self, name: str) -> None:\n"
            "        self.name = name\n"
            "    def get_name(self) -> str:\n"
            "        return self.name\n"
        )
        (pkg_dir / "derived.py").write_text(
            "from .base import Shape\n"
            "class Circle(Shape):\n"
            "    def __init__(self, name: str, radius: float) -> None:\n"
            "        self.name = name\n"
            "        self.radius = radius\n"
            "    def get_area(self) -> float:\n"
            "        return 3.14159 * self.radius * self.radius\n"
        )
        (pkg_dir / "main.py").write_text(
            "from .derived import Circle\n"
            "def main() -> None:\n"
            "    c = Circle(\"circle1\", 2.0)\n"
            "    print(c.get_name())\n"
            "    area = c.get_area()\n"
            "    print(f\"Area: {area}\")\n"
        )
        
        # 2. Write the pyproject.toml
        (tmp_path / "pyproject.toml").write_text(
            "[project]\n"
            "name = \"pkg_classes\"\n"
            "version = \"0.1.0\"\n"
            "\n"
            "[tool.py2rust]\n"
            "package_dir = \"pkg_classes\"\n"
            "entry_point = \"pkg_classes.main\"\n"
        )
        
        out_dir = tmp_path / "dist"
        
        # 3. Compile the package
        config = CompilerConfig(
            input_file=str(tmp_path),
            output_file=str(out_dir),
            verbose=True,
            verify=False
        )
        
        success = compile_repo(config)
        assert success is True
        
        # 4. Verify generated file existence
        assert (out_dir / "Cargo.toml").exists()
        assert (out_dir / "src" / "main.rs").exists()
        assert (out_dir / "src" / "pkg_classes" / "base.rs").exists()
        assert (out_dir / "src" / "pkg_classes" / "derived.rs").exists()
        
        # 5. Run cargo check
        check_res = run_cargo_cmd(out_dir, ["cargo", "check"])
        assert check_res.returncode == 0, f"Cargo check failed:\n{check_res.stderr}"
        
        # 6. Run cargo run
        run_res = run_cargo_cmd(out_dir, ["cargo", "run"])
        assert run_res.returncode == 0, f"Cargo run failed:\n{run_res.stderr}"
        assert "circle1" in run_res.stdout
        assert "Area: 12.566" in run_res.stdout

def test_repo_async():
    """
    Test 3: Async Package (db -> main) with Tokio Runtime
    Verifies modular async compilation, cargo check, and cargo run.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        
        pkg_dir = tmp_path / "pkg_async"
        pkg_dir.mkdir()
        
        # 1. Write the package modules
        (pkg_dir / "__init__.py").write_text("")
        (pkg_dir / "db.py").write_text(
            "async def get_data() -> int:\n"
            "    return 42\n"
        )
        (pkg_dir / "main.py").write_text(
            "from .db import get_data\n"
            "async def main() -> None:\n"
            "    val = await get_data()\n"
            "    print(val)\n"
        )
        
        # 2. Write the pyproject.toml
        (tmp_path / "pyproject.toml").write_text(
            "[project]\n"
            "name = \"pkg_async\"\n"
            "version = \"0.1.0\"\n"
            "\n"
            "[tool.py2rust]\n"
            "package_dir = \"pkg_async\"\n"
            "entry_point = \"pkg_async.main\"\n"
        )
        
        out_dir = tmp_path / "dist"
        
        # 3. Compile the package
        config = CompilerConfig(
            input_file=str(tmp_path),
            output_file=str(out_dir),
            verbose=True,
            verify=False,
            async_runtime=AsyncRuntime.TOKIO
        )
        
        success = compile_repo(config)
        assert success is True
        
        # 4. Verify generated file existence
        assert (out_dir / "Cargo.toml").exists()
        assert (out_dir / "src" / "main.rs").exists()
        assert (out_dir / "src" / "pkg_async" / "db.rs").exists()
        
        # 5. Run cargo check
        check_res = run_cargo_cmd(out_dir, ["cargo", "check"])
        assert check_res.returncode == 0, f"Cargo check failed:\n{check_res.stderr}"
        
        # 6. Run cargo run
        run_res = run_cargo_cmd(out_dir, ["cargo", "run"])
        assert run_res.returncode == 0, f"Cargo run failed:\n{run_res.stderr}"
        assert "42" in run_res.stdout

def test_repo_stdlib():
    """
    Test 4: Heavy Stdlib Usage (main using collections.deque and heapq)
    Verifies modular standard library integration, compilation, and execution.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        
        pkg_dir = tmp_path / "pkg_stdlib"
        pkg_dir.mkdir()
        
        # 1. Write the package modules
        (pkg_dir / "__init__.py").write_text("")
        (pkg_dir / "main.py").write_text(
            "from collections import deque\n"
            "import heapq\n"
            "def main() -> None:\n"
            "    d = deque([10, 20, 30])\n"
            "    d.append(40)\n"
            "    v1 = d.popleft()\n"
            "    print(v1)\n"
            "    \n"
            "    h = []\n"
            "    heapq.heappush(h, 15)\n"
            "    heapq.heappush(h, 5)\n"
            "    heapq.heappush(h, 25)\n"
            "    v2 = heapq.heappop(h)\n"
            "    print(v2)\n"
        )
        
        # 2. Write the pyproject.toml
        (tmp_path / "pyproject.toml").write_text(
            "[project]\n"
            "name = \"pkg_stdlib\"\n"
            "version = \"0.1.0\"\n"
            "\n"
            "[tool.py2rust]\n"
            "package_dir = \"pkg_stdlib\"\n"
            "entry_point = \"pkg_stdlib.main\"\n"
        )
        
        out_dir = tmp_path / "dist"
        
        # 3. Compile the package
        config = CompilerConfig(
            input_file=str(tmp_path),
            output_file=str(out_dir),
            verbose=True,
            verify=False
        )
        
        success = compile_repo(config)
        assert success is True
        
        # 4. Verify generated file existence
        assert (out_dir / "Cargo.toml").exists()
        assert (out_dir / "src" / "main.rs").exists()
        
        # 5. Run cargo check
        check_res = run_cargo_cmd(out_dir, ["cargo", "check"])
        assert check_res.returncode == 0, f"Cargo check failed:\n{check_res.stderr}"
        
        # 6. Run cargo run
        run_res = run_cargo_cmd(out_dir, ["cargo", "run"])
        assert run_res.returncode == 0, f"Cargo run failed:\n{run_res.stderr}"
        assert "10" in run_res.stdout
        assert "5" in run_res.stdout
