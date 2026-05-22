import tempfile
from pathlib import Path
import pytest

from py2rust.project.import_resolver import ImportResolver
from py2rust.middleend.dependency_manager import DependencyManager
from py2rust.middleend.type_checker import TypeChecker
from py2rust.config import CompilerConfig, AsyncRuntime
from py2rust.frontend.parser import parse
from py2rust.middleend.ir_builder import build_ir
from py2rust.backend.rust_codegen import generate_rust

def test_import_resolver_basic_and_relative():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        
        # Set up a package structure:
        # my_pkg/
        #   __init__.py
        #   core.py
        #   utils.py
        #   sub/
        #     __init__.py
        #     helper.py
        pkg_dir = tmp_path / "my_pkg"
        pkg_dir.mkdir()
        (pkg_dir / "__init__.py").write_text("# init")
        (pkg_dir / "core.py").write_text("def add(x: int, y: int) -> int:\n    return x + y")
        (pkg_dir / "utils.py").write_text("def mult(x: int, y: int) -> int:\n    return x * y")
        
        sub_dir = pkg_dir / "sub"
        sub_dir.mkdir()
        (sub_dir / "__init__.py").write_text("# sub init")
        (sub_dir / "helper.py").write_text("def run() -> None:\n    pass")

        resolver = ImportResolver(repo_root=tmp_path)
        
        # Test file to module mapping
        assert resolver.get_module_for_file(pkg_dir / "core.py") == "my_pkg.core"
        assert resolver.get_module_for_file(sub_dir / "helper.py") == "my_pkg.sub.helper"
        assert resolver.get_module_for_file(pkg_dir / "__init__.py") == "my_pkg"

        # Test intra-repo check
        assert resolver.is_intra_repo("my_pkg.core") is True
        assert resolver.is_intra_repo("my_pkg.sub.helper") is True
        assert resolver.is_intra_repo("os") is False
        assert resolver.is_intra_repo("sys") is False

        # Test relative import resolution
        # E.g. from . import helper (level=1, module="helper" from "my_pkg.sub.other")
        resolved = resolver.resolve_relative_import("my_pkg.sub.other", level=1, from_module_name="helper")
        assert resolved == "my_pkg.sub.helper"

        # E.g. from .. import utils (level=2, module="utils" from "my_pkg.sub.helper")
        resolved = resolver.resolve_relative_import("my_pkg.sub.helper", level=2, from_module_name="utils")
        assert resolved == "my_pkg.utils"

        # E.g. from ..core import add (level=2, module="core" from "my_pkg.sub.helper")
        resolved = resolver.resolve_relative_import("my_pkg.sub.helper", level=2, from_module_name="core")
        assert resolved == "my_pkg.core"


def test_dependency_manager_cycle_detection():
    dm = DependencyManager()
    
    # Simple linear dependency: A -> B -> C
    dm.add_import_edge("my_pkg.A", "my_pkg.B")
    dm.add_import_edge("my_pkg.B", "my_pkg.C")
    # No circular dependency
    assert dm.check_circular_dependencies() is None
    
    # Introducing a loop: C -> A
    dm.add_import_edge("my_pkg.C", "my_pkg.A")
    
    cycle = dm.check_circular_dependencies()
    assert cycle is not None
    assert "my_pkg.A" in cycle
    assert "my_pkg.B" in cycle
    assert "my_pkg.C" in cycle
    
    # Registering an edge that creates a cycle raises ValueError
    dm2 = DependencyManager()
    dm2.add_import_edge("my_pkg.X", "my_pkg.Y")
    with pytest.raises(ValueError) as excinfo:
        dm2.add_import_edge("my_pkg.Y", "my_pkg.X")
    assert "Circular dependency detected" in str(excinfo.value)


def test_compiler_end_to_end_imports():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        
        # Set up a package structure:
        # my_pkg/
        #   __init__.py
        #   core.py
        #   utils.py
        pkg_dir = tmp_path / "my_pkg"
        pkg_dir.mkdir()
        (pkg_dir / "__init__.py").write_text("# init")
        
        core_src = """from .utils import mult

def calc(x: int) -> int:
    return mult(x, 2)
"""
        (pkg_dir / "core.py").write_text(core_src)
        
        utils_src = """def mult(a: int, b: int) -> int:
    return a * b
"""
        (pkg_dir / "utils.py").write_text(utils_src)

        # Let's compile core.py using py2rust compiler pipeline!
        config = CompilerConfig(
            input_file=str(pkg_dir / "core.py"),
            repo_root=str(tmp_path),
            mock_mode=False
        )

        dep_manager = DependencyManager()
        
        # Parse
        module = parse(core_src, filename=str(pkg_dir / "core.py"))
        
        # Build IR (Type Checking occurs inside build_ir)
        ir_module = build_ir(
            module,
            filename=str(pkg_dir / "core.py"),
            source_lines=core_src.splitlines(),
            config=config,
            dependency_manager=dep_manager
        )

        # Generate Rust Code
        rust_code = generate_rust(ir_module, dependency_manager=dep_manager, config=config)

        # Check emitted imports in generated Rust
        assert "use crate::my_pkg::utils::mult;" in rust_code
        assert "fn calc(x: i32) -> Result<i32, PyError>" in rust_code
