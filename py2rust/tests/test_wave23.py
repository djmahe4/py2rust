import tempfile
from pathlib import Path
import pytest
from py2rust.project.project_config import ProjectConfig
from py2rust.project.package_scanner import PackageScanner
from py2rust.backend.workspace_generator import WorkspaceGenerator

def test_project_config_load():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        toml_file = tmp_path / "pyproject.toml"
        toml_file.write_text("""
[project]
name = "my_awesome_project"
version = "1.2.3"

[tool.py2rust]
name = "overridden_name"
entry_point = "main"
package_dir = "src"
exclude = ["tests/*", "**/dummy.py"]
dependencies = { serde = "1.0", pyo3 = "0.21" }
""")
        config = ProjectConfig.load_from_toml(toml_file)
        assert config.name == "overridden_name"
        assert config.version == "1.2.3"
        assert config.entry_point == "main"
        assert config.package_dir == "src"
        assert "tests/*" in config.exclude
        assert config.dependencies == {"serde": "1.0", "pyo3": "0.21"}

def test_package_scanner_src_layout():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        
        # Setup src layout
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        
        pkg_dir = src_dir / "my_pkg"
        pkg_dir.mkdir()
        
        (pkg_dir / "__init__.py").write_text("# init")
        (pkg_dir / "core.py").write_text("# core")
        (pkg_dir / "utils.py").write_text("# utils")
        
        sub_dir = pkg_dir / "sub"
        sub_dir.mkdir()
        (sub_dir / "__init__.py").write_text("# sub init")
        (sub_dir / "helper.py").write_text("# helper")
        
        scanner = PackageScanner(tmp_path)
        modules = scanner.scan()
        
        assert "my_pkg.core" in modules
        assert "my_pkg.utils" in modules
        assert "my_pkg.sub.helper" in modules
        # The __init__.py files are skipped or represented by parent package namespace
        assert "my_pkg" in modules
        assert "my_pkg.sub" in modules

def test_package_scanner_exclusions():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        (tmp_path / "main.py").write_text("# main")
        (tmp_path / "test_main.py").write_text("# test")
        
        sub_dir = tmp_path / "my_pkg"
        sub_dir.mkdir()
        (sub_dir / "utils.py").write_text("# utils")
        (sub_dir / "dummy.py").write_text("# dummy")
        
        scanner = PackageScanner(tmp_path, exclude_patterns=["**/dummy.py", "test_*.py"])
        modules = scanner.scan()
        
        assert "main" in modules
        assert "my_pkg.utils" in modules
        assert "my_pkg.dummy" not in modules
        assert "test_main" not in modules

def test_workspace_generator_mod_hierarchy():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        
        gen = WorkspaceGenerator(tmp_path, project_name="my_crate", version="0.5.0")
        
        modules = {
            "my_pkg": "pub fn hello() {}",
            "my_pkg.core": "pub fn core_func() {}",
            "my_pkg.utils": "pub fn utils_func() {}",
            "my_pkg.sub.helper": "pub fn helper_func() {}",
        }
        
        gen.generate_mod_hierarchy(modules)
        
        src_dir = tmp_path / "src"
        assert (src_dir / "lib.rs").exists()
        assert (src_dir / "my_pkg.rs").exists()
        assert (src_dir / "my_pkg" / "core.rs").exists()
        assert (src_dir / "my_pkg" / "utils.rs").exists()
        assert (src_dir / "my_pkg" / "sub" / "helper.rs").exists()
        
        # Check lib.rs content has top level module declaration
        lib_content = (src_dir / "lib.rs").read_text()
        assert "pub mod my_pkg;" in lib_content
        
        # Check parent file my_pkg.rs declares core, utils, and sub
        my_pkg_content = (src_dir / "my_pkg.rs").read_text()
        assert "pub mod core;" in my_pkg_content
        assert "pub mod utils;" in my_pkg_content
        assert "pub mod sub;" in my_pkg_content
        assert "pub fn hello() {}" in my_pkg_content
        
        # Check Cargo.toml was written correctly
        cargo_content = (tmp_path / "Cargo.toml").read_text()
        assert 'name = "my_crate"' in cargo_content
        assert 'version = "0.5.0"' in cargo_content
