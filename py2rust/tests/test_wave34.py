from __future__ import annotations
import tempfile
from pathlib import Path
import pytest
from py2rust.config import CompilerConfig

def test_compiler_config_force_field():
    config = CompilerConfig(force=True)
    assert config.force is True
    
    config_default = CompilerConfig()
    assert config_default.force is False

def test_build_cache_file_hashing():
    from py2rust.project.build_cache import BuildCache
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        test_file = tmp_path / "test.py"
        
        # Missing file should return empty string
        assert BuildCache.get_file_hash(test_file) == ""
        
        test_file.write_text("print('hello')", encoding="utf-8")
        hash1 = BuildCache.get_file_hash(test_file)
        assert len(hash1) == 64  # SHA-256 is 64 characters hex
        
        test_file.write_text("print('hello world')", encoding="utf-8")
        hash2 = BuildCache.get_file_hash(test_file)
        assert hash1 != hash2

def test_build_cache_load_save_operations():
    from py2rust.project.build_cache import BuildCache
    
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_file = Path(tmpdir) / "cache.json"
        
        cache = BuildCache(cache_file)
        # Should start empty
        assert cache.data == {}
        
        # Set an entry
        test_file = Path(tmpdir) / "mod.py"
        test_file.write_text("x = 42")
        content_hash = BuildCache.get_file_hash(test_file)
        
        cache.set_entry(
            module_name="mod",
            file_path=test_file,
            content_hash=content_hash,
            dependency_hashes={"dep": "dephash123"},
            rust_code="const x: i32 = 42;"
        )
        
        # Verify stored data
        assert cache.data["mod"]["content_hash"] == content_hash
        assert cache.data["mod"]["rust_code"] == "const x: i32 = 42;"
        
        # Load in a new cache instance to verify persistence
        cache2 = BuildCache(cache_file)
        entry = cache2.get_entry("mod")
        assert entry is not None
        assert entry["content_hash"] == content_hash
        assert entry["dependency_hashes"] == {"dep": "dephash123"}
        assert entry["rust_code"] == "const x: i32 = 42;"
        
        # Clear cache
        cache2.clear()
        assert cache2.data == {}
        assert not cache_file.exists()


def test_incremental_compilation_workflow():
    from py2rust.project.repo_compiler import compile_repo
    from py2rust.project.build_cache import BuildCache
    import shutil
    import unittest.mock as mock

    with tempfile.TemporaryDirectory() as tmpdir:
        repo_dir = Path(tmpdir) / "my_repo"
        repo_dir.mkdir()
        
        # pyproject.toml
        toml = repo_dir / "pyproject.toml"
        toml.write_text("""
[project]
name = "my_repo"
version = "0.1.0"
package-dir = "src"
entry-point = "src/a.py"
""", encoding="utf-8")
        
        src_dir = repo_dir / "src"
        src_dir.mkdir()
        
        a_py = src_dir / "a.py"
        a_py.write_text("import b\ndef run() -> int:\n    return b.val()", encoding="utf-8")
        
        b_py = src_dir / "b.py"
        b_py.write_text("def val() -> int:\n    return 42", encoding="utf-8")
        
        # Initial compilation
        config = CompilerConfig(
            input_file=str(repo_dir),
            repo_root=str(repo_dir),
            output_file=str(repo_dir / "dist"),
            format_output=True,
        )
        
        success = compile_repo(config)
        assert success is True
        
        cache_file = repo_dir / ".py2rust" / "cache.json"
        assert cache_file.exists()
        
        cache = BuildCache(cache_file)
        assert "a" in cache.data
        assert "b" in cache.data
        
        original_rust_a = cache.data["a"]["rust_code"]
        original_rust_b = cache.data["b"]["rust_code"]
        
        # Let's mock generate_rust to verify when it's called
        import py2rust.project.repo_compiler
        
        # Run 2: No changes, should not recompile anything (recompiled_modules empty)
        with mock.patch("py2rust.project.repo_compiler.generate_rust", side_effect=py2rust.project.repo_compiler.generate_rust) as mock_gen:
            success = compile_repo(config)
            assert success is True
            # Since both modules are cached and unchanged, generate_rust should be skipped!
            assert mock_gen.call_count == 0
            
        # Run 3: Modify a.py (leaf/downstream). Only a.py should be recompiled, b.py should be cached!
        a_py.write_text("import b\ndef run() -> int:\n    return b.val() + 1", encoding="utf-8")
        with mock.patch("py2rust.project.repo_compiler.generate_rust", side_effect=py2rust.project.repo_compiler.generate_rust) as mock_gen:
            success = compile_repo(config)
            assert success is True
            # Only a.py is recompiled (1 call)
            assert mock_gen.call_count == 1
            
        # Run 4: Modify b.py (dependency). Both b.py AND a.py (transitive) should be recompiled!
        b_py.write_text("def val() -> int:\n    return 100", encoding="utf-8")
        with mock.patch("py2rust.project.repo_compiler.generate_rust", side_effect=py2rust.project.repo_compiler.generate_rust) as mock_gen:
            success = compile_repo(config)
            assert success is True
            # Both b and a are recompiled (2 calls)
            assert mock_gen.call_count == 2

        # Run 5: Using --force. Both b.py and a.py should be recompiled regardless of no changes.
        config_force = CompilerConfig(
            input_file=str(repo_dir),
            repo_root=str(repo_dir),
            output_file=str(repo_dir / "dist"),
            format_output=True,
            force=True,
        )
        with mock.patch("py2rust.project.repo_compiler.generate_rust", side_effect=py2rust.project.repo_compiler.generate_rust) as mock_gen:
            success = compile_repo(config_force)
            assert success is True
            # Both recompiled due to --force
            assert mock_gen.call_count == 2
