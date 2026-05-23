from __future__ import annotations
import tempfile
from pathlib import Path
import pytest
import subprocess
import os

from py2rust.project.repo_compiler import compile_repo
from py2rust.config import CompilerConfig
from py2rust.utils.errors import SemanticError

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

def test_stress_invalid_relative_import():
    """
    Test 1: Relative Import Boundary Violations
    Verify that importing with too many parent dots (going beyond the package root)
    is caught and fails with a clear SemanticError.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        
        pkg_dir = tmp_path / "pkg_invalid_rel"
        pkg_dir.mkdir()
        
        (pkg_dir / "__init__.py").write_text("")
        # Deeply nested module attempting to go up 3 levels, which is beyond the pkg_invalid_rel boundary
        (pkg_dir / "main.py").write_text(
            "from ...outside import something\n"
            "def main() -> None:\n"
            "    pass\n"
        )
        
        (tmp_path / "pyproject.toml").write_text(
            "[project]\n"
            "name = \"pkg_invalid_rel\"\n"
            "version = \"0.1.0\"\n"
            "\n"
            "[tool.py2rust]\n"
            "package_dir = \"pkg_invalid_rel\"\n"
            "entry_point = \"pkg_invalid_rel.main\"\n"
        )
        
        out_dir = tmp_path / "dist"
        
        config = CompilerConfig(
            input_file=str(tmp_path),
            output_file=str(out_dir),
            verbose=True,
            verify=False
        )
        
        # Should raise a SemanticError during compilation
        with pytest.raises(SemanticError) as exc_info:
            compile_repo(config)
        
        assert "Relative import level" in str(exc_info.value) or "exceeds current module depth" in str(exc_info.value)


def test_stress_undefined_import_symbol():
    """
    Test 2: Undefined Name Error at Import
    Verify that importing a non-existent name from an existing module
    raises a SemanticError ("cannot import name").
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        
        pkg_dir = tmp_path / "pkg_undef_sym"
        pkg_dir.mkdir()
        
        (pkg_dir / "__init__.py").write_text("")
        (pkg_dir / "utils.py").write_text(
            "def real_function() -> int:\n"
            "    return 42\n"
        )
        (pkg_dir / "main.py").write_text(
            "from .utils import real_function, imaginary_function\n"
            "def main() -> None:\n"
            "    x = real_function()\n"
            "    y = imaginary_function()\n"
        )
        
        (tmp_path / "pyproject.toml").write_text(
            "[project]\n"
            "name = \"pkg_undef_sym\"\n"
            "version = \"0.1.0\"\n"
            "\n"
            "[tool.py2rust]\n"
            "package_dir = \"pkg_undef_sym\"\n"
            "entry_point = \"pkg_undef_sym.main\"\n"
        )
        
        out_dir = tmp_path / "dist"
        
        config = CompilerConfig(
            input_file=str(tmp_path),
            output_file=str(out_dir),
            verbose=True,
            verify=False
        )
        
        with pytest.raises(SemanticError) as exc_info:
            compile_repo(config)
            
        assert "cannot import name 'imaginary_function'" in str(exc_info.value)


def test_stress_cross_module_attribute_name_error():
    """
    Test 3: Undefined Name Error at Attribute Usage
    Verify that accessing a non-existent attribute or function on an imported module
    raises a SemanticError ("has no attribute" or "has no function").
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        
        pkg_dir = tmp_path / "pkg_cross_attr_err"
        pkg_dir.mkdir()
        
        (pkg_dir / "__init__.py").write_text("")
        (pkg_dir / "utils.py").write_text(
            "def real_fun() -> None:\n"
            "    pass\n"
        )
        (pkg_dir / "main.py").write_text(
            "import pkg_cross_attr_err.utils as u\n"
            "def main() -> None:\n"
            "    u.real_fun()\n"
            "    u.phantom_fun()\n"
        )
        
        (tmp_path / "pyproject.toml").write_text(
            "[project]\n"
            "name = \"pkg_cross_attr_err\"\n"
            "version = \"0.1.0\"\n"
            "\n"
            "[tool.py2rust]\n"
            "package_dir = \"pkg_cross_attr_err\"\n"
            "entry_point = \"pkg_cross_attr_err.main\"\n"
        )
        
        out_dir = tmp_path / "dist"
        
        config = CompilerConfig(
            input_file=str(tmp_path),
            output_file=str(out_dir),
            verbose=True,
            verify=False
        )
        
        with pytest.raises(SemanticError) as exc_info:
            compile_repo(config)
            
        assert "has no function or class 'phantom_fun'" in str(exc_info.value) or "has no attribute 'phantom_fun'" in str(exc_info.value)


def test_stress_mismatched_method_call_arguments():
    """
    Test 4: Mismatched Method Call / Constructor Arguments
    Verify that calling an imported constructor or method with wrong arity
    raises a SemanticError during compilation.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        
        pkg_dir = tmp_path / "pkg_mismatch_args"
        pkg_dir.mkdir()
        
        (pkg_dir / "__init__.py").write_text("")
        (pkg_dir / "helper.py").write_text(
            "class Worker:\n"
            "    def __init__(self, name: str) -> None:\n"
            "        self.name = name\n"
            "    def work(self) -> None:\n"
            "        pass\n"
        )
        # Calling Worker constructor with wrong arity (expects name, got none, or got multiple)
        (pkg_dir / "main.py").write_text(
            "from .helper import Worker\n"
            "def main() -> None:\n"
            "    w = Worker()  # Mismatch! Expects 1 argument, got 0\n"
            "    w.work()\n"
        )
        
        (tmp_path / "pyproject.toml").write_text(
            "[project]\n"
            "name = \"pkg_mismatch_args\"\n"
            "version = \"0.1.0\"\n"
            "\n"
            "[tool.py2rust]\n"
            "package_dir = \"pkg_mismatch_args\"\n"
            "entry_point = \"pkg_mismatch_args.main\"\n"
        )
        
        out_dir = tmp_path / "dist"
        
        config = CompilerConfig(
            input_file=str(tmp_path),
            output_file=str(out_dir),
            verbose=True,
            verify=False
        )
        
        with pytest.raises(SemanticError) as exc_info:
            compile_repo(config)
            
        assert "constructor expects arities" in str(exc_info.value) or "No constructor found" in str(exc_info.value)


def test_stress_circular_dependency_fail():
    """
    Test 5: Circular Dependency Rejection
    Verify that a tight circular dependency cycle raises a ValueError during compilation.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        
        pkg_dir = tmp_path / "pkg_circular"
        pkg_dir.mkdir()
        
        (pkg_dir / "__init__.py").write_text("")
        (pkg_dir / "a.py").write_text(
            "from .b import get_b\n"
            "def get_a() -> int:\n"
            "    return get_b() + 1\n"
        )
        (pkg_dir / "b.py").write_text(
            "from .a import get_a\n"
            "def get_b() -> int:\n"
            "    return get_a() + 1\n"
        )
        (pkg_dir / "main.py").write_text(
            "from .a import get_a\n"
            "def main() -> None:\n"
            "    print(get_a())\n"
        )
        
        (tmp_path / "pyproject.toml").write_text(
            "[project]\n"
            "name = \"pkg_circular\"\n"
            "version = \"0.1.0\"\n"
            "\n"
            "[tool.py2rust]\n"
            "package_dir = \"pkg_circular\"\n"
            "entry_point = \"pkg_circular.main\"\n"
        )
        
        out_dir = tmp_path / "dist"
        
        config = CompilerConfig(
            input_file=str(tmp_path),
            output_file=str(out_dir),
            verbose=True,
            verify=False
        )
        
        with pytest.raises(ValueError) as exc_info:
            compile_repo(config)
            
        assert "Circular dependency detected" in str(exc_info.value)


def test_stress_duplicate_name_conflict():
    """
    Test 6: Duplicate Names with Aliasing
    Verify that two modules defining same-named functions can be imported into main.py
    using separate aliases, resolved correctly, compile to valid Rust, and run successfully.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        
        pkg_dir = tmp_path / "pkg_dup_names"
        pkg_dir.mkdir()
        
        (pkg_dir / "__init__.py").write_text("")
        (pkg_dir / "utils_a.py").write_text(
            "def get_val() -> int:\n"
            "    return 100\n"
        )
        (pkg_dir / "utils_b.py").write_text(
            "def get_val() -> int:\n"
            "    return 200\n"
        )
        (pkg_dir / "main.py").write_text(
            "from .utils_a import get_val as get_a\n"
            "from .utils_b import get_val as get_b\n"
            "def main() -> None:\n"
            "    val_a = get_a()\n"
            "    val_b = get_b()\n"
            "    print(f\"a: {val_a}, b: {val_b}\")\n"
        )
        
        (tmp_path / "pyproject.toml").write_text(
            "[project]\n"
            "name = \"pkg_dup_names\"\n"
            "version = \"0.1.0\"\n"
            "\n"
            "[tool.py2rust]\n"
            "package_dir = \"pkg_dup_names\"\n"
            "entry_point = \"pkg_dup_names.main\"\n"
        )
        
        out_dir = tmp_path / "dist"
        
        config = CompilerConfig(
            input_file=str(tmp_path),
            output_file=str(out_dir),
            verbose=True,
            verify=False
        )
        
        success = compile_repo(config)
        assert success is True
        
        # Verify it generates valid Rust that compiles and runs
        check_res = run_cargo_cmd(out_dir, ["cargo", "check"])
        assert check_res.returncode == 0, f"Cargo check failed:\n{check_res.stderr}"
        
        run_res = run_cargo_cmd(out_dir, ["cargo", "run"])
        assert run_res.returncode == 0, f"Cargo run failed:\n{run_res.stderr}"
        assert "a: 100, b: 200" in run_res.stdout
