import tempfile
from pathlib import Path
import pytest
import subprocess
import os

from py2rust.project.import_resolver import ImportResolver
from py2rust.project.module_graph import ModuleGraph
from py2rust.project.repo_compiler import compile_repo
from py2rust.config import CompilerConfig, AsyncRuntime

def test_topological_sort_simple():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        
        # A imports B, B imports C
        # Therefore, C must compile before B, and B before A.
        # Order: C, B, A
        (tmp_path / "A.py").write_text("import B")
        (tmp_path / "B.py").write_text("import C")
        (tmp_path / "C.py").write_text("pass")
        
        resolver = ImportResolver(repo_root=tmp_path)
        graph = ModuleGraph(resolver)
        for mod in ["A", "B", "C"]:
            graph.add_module(mod, tmp_path / f"{mod}.py")
            
        graph.build_graph()
        order = graph.topological_sort()
        
        assert order == ["C", "B", "A"]

def test_topological_sort_diamond():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        
        # A imports B and C
        # B imports D
        # C imports D
        # Order: D must be first, then B and C (in alphabetical order), then A.
        (tmp_path / "A.py").write_text("import B\nimport C")
        (tmp_path / "B.py").write_text("import D")
        (tmp_path / "C.py").write_text("import D")
        (tmp_path / "D.py").write_text("pass")
        
        resolver = ImportResolver(repo_root=tmp_path)
        graph = ModuleGraph(resolver)
        for mod in ["A", "B", "C", "D"]:
            graph.add_module(mod, tmp_path / f"{mod}.py")
            
        graph.build_graph()
        order = graph.topological_sort()
        
        assert order == ["D", "B", "C", "A"]

def test_cycle_breaks_compilation():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        
        # Bilateral cycle: A imports B, B imports A
        # Should raise ValueError
        (tmp_path / "A.py").write_text("import B")
        (tmp_path / "B.py").write_text("import A")
        
        resolver = ImportResolver(repo_root=tmp_path)
        graph = ModuleGraph(resolver)
        graph.add_module("A", tmp_path / "A.py")
        graph.add_module("B", tmp_path / "B.py")
        graph.build_graph()
        
        with pytest.raises(ValueError) as excinfo:
            graph.topological_sort()
        assert "Circular dependency detected" in str(excinfo.value)

def test_large_cycle_is_broken_gracefully():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        
        # Complex cycle of length > 2:
        # A imports B
        # B imports C
        # C imports A
        # This cycle of length 3 should be broken by removing an edge, allowing compilation to succeed!
        (tmp_path / "A.py").write_text("import B")
        (tmp_path / "B.py").write_text("import C")
        (tmp_path / "C.py").write_text("import A")
        
        resolver = ImportResolver(repo_root=tmp_path)
        graph = ModuleGraph(resolver)
        for mod in ["A", "B", "C"]:
            graph.add_module(mod, tmp_path / f"{mod}.py")
        graph.build_graph()
        
        # Should sort without raising ValueError because cycle > 2 is broken!
        order = graph.topological_sort()
        assert len(order) == 3
        assert set(order) == {"A", "B", "C"}

def test_repo_compiler_produces_workspace():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        
        # Let's create a modular package:
        # pkg/
        #   __init__.py
        #   math_utils.py
        #   calc.py
        pkg_dir = tmp_path / "pkg"
        pkg_dir.mkdir()
        (pkg_dir / "__init__.py").write_text("")
        (pkg_dir / "math_utils.py").write_text("def add(x: int, y: int) -> int:\n    return x + y\n")
        (pkg_dir / "calc.py").write_text("from .math_utils import add\n\ndef run() -> int:\n    return add(10, 20)\n\ndef main() -> None:\n    print(run())\n")
        
        # Create pyproject.toml
        pyproject_content = """[project]
name = "my_calc_project"
version = "0.2.0"

[tool.py2rust]
package_dir = "pkg"
entry_point = "pkg.calc"
"""
        (tmp_path / "pyproject.toml").write_text(pyproject_content)
        
        out_dir = tmp_path / "dist"
        
        config = CompilerConfig(
            input_file=str(tmp_path),
            output_file=str(out_dir),
            verbose=True,
            verify=False
        )
        
        success = compile_repo(config)
        assert success is True
        
        # Verify workspace files were created
        assert (out_dir / "Cargo.toml").exists()
        assert (out_dir / "src" / "main.rs").exists()
        assert (out_dir / "src" / "pkg" / "math_utils.rs").exists()
        
        # Let's verify compilation of generated workspace using cargo check!
        env = os.environ.copy()
        cargo_bin = os.path.expanduser("~/.cargo/bin")
        if cargo_bin not in env.get("PATH", ""):
            env["PATH"] = f"{cargo_bin}:{env.get('PATH', '')}"
        env["PYO3_USE_ABI3_FORWARD_COMPATIBILITY"] = "1"
        
        result = subprocess.run(
            ["cargo", "check"],
            cwd=out_dir,
            env=env,
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"Cargo check failed:\n{result.stderr}"
