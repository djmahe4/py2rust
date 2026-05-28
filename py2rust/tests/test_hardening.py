from __future__ import annotations
import sys
import unittest
from unittest.mock import Mock, patch
from py2rust.main import extract_rust_fn
from py2rust.config import CompilerConfig
from py2rust.learning_system.validation.semantic_validator import SemanticValidator


def test_extract_rust_fn_robust_braces_in_comments():
    rust_code = """
    fn my_function() {
        // This is a line comment with } brace
        /* This is a block comment with } brace */
        let x = 42;
    }
    """
    fn_body = extract_rust_fn(rust_code, "my_function")
    assert fn_body is not None
    assert "let x = 42;" in fn_body
    assert fn_body.strip().endswith("}")


def test_extract_rust_fn_robust_braces_in_strings():
    rust_code = r"""
    fn test_func() {
        let s = "brace } inside string";
        let c = '}';
        let escaped = "escaped \" } brace";
    }
    """
    fn_body = extract_rust_fn(rust_code, "test_func")
    assert fn_body is not None
    assert 'brace } inside string' in fn_body
    assert fn_body.strip().endswith("}")


def test_compiler_config_ollama_host():
    config_default = CompilerConfig()
    assert config_default.ollama_host == "http://localhost:11434"

    config_custom = CompilerConfig(ollama_host="http://my-custom-host:8000")
    assert config_custom.ollama_host == "http://my-custom-host:8000"


def test_semantic_validator_custom_host():
    validator = SemanticValidator(host="http://my-custom-host:8000")
    assert validator.client.host == "http://my-custom-host:8000"


@patch("shutil.which")
@patch("subprocess.run")
def test_semantic_validator_powershell_hardening(mock_run, mock_which):
    # Setup mock to simulate Windows environment with powershell available
    mock_which.side_effect = lambda x: "/usr/bin/powershell" if x == "powershell" else None
    mock_run.return_value = Mock(stdout="Context content", returncode=0)

    # Temporarily set sys.platform to 'win32'
    original_platform = sys.platform
    try:
        sys.platform = "win32"
        validator = SemanticValidator()

        # Case 1: Unsafe symbol name should bypass subprocess shell tool execution and fall back safely
        context_unsafe = validator.get_symbol_context("vuln_func'; injection; '")
        assert not mock_run.called

        # Case 2: Safe, valid symbol name should invoke powershell with parameterized arguments
        context_safe = validator.get_symbol_context("safe_func")
        assert mock_run.called
        args, kwargs = mock_run.call_args
        cmd_list = args[0]
        
        # Verify the command list has NoProfile and safely parameterized query
        assert cmd_list[0] == "powershell"
        assert "-NoProfile" in cmd_list
        assert "& {param($p) Select-String -Pattern $p -Path * -Context 5}" in cmd_list
        assert cmd_list[-1] == "def safe_func"
    finally:
        sys.platform = original_platform


def test_extract_rust_fn_complex_nested():
    rust_code = """
    // Pre-declaration comment
    fn complex_nested_func() {
        let raw_val = r##"
            nested {
                unbalanced braces: } {
            "##;
        let c = '}';
        /*
        nested comment {
            comment block
        }
        */
        if true {
            println!("test");
        }
    }
    """
    fn_body = extract_rust_fn(rust_code, "complex_nested_func")
    assert fn_body is not None
    assert "complex_nested_func" in fn_body
    assert 'unbalanced braces' in fn_body
    assert fn_body.strip().endswith("}")


def test_extract_rust_fn_trait_semicolon():
    rust_code = """
    pub trait MyTrait {
        fn trait_fn(x: i32) -> String;
        fn implemented_fn() {
            println!("trait impl");
        }
    }
    """
    fn_body = extract_rust_fn(rust_code, "trait_fn")
    assert fn_body is not None
    assert "trait_fn" in fn_body
    assert fn_body.strip().endswith(";")


def test_type_mapping_registry():
    from py2rust.middleend.type_mapping import map_type_to_ir
    from py2rust.frontend.ast_nodes import IntType, ListType, OptionalType, StrType
    from py2rust.ir.ir_nodes import IRIntType, IRListType, IROptionType, IRStrType

    # Test basic type mapping
    ast_int = IntType()
    ir_int = map_type_to_ir(ast_int)
    assert isinstance(ir_int, IRIntType)

    # Test nested list type mapping
    ast_list = ListType(element_type=IntType())
    ir_list = map_type_to_ir(ast_list)
    assert isinstance(ir_list, IRListType)
    assert isinstance(ir_list.element_type, IRIntType)

    # Test nested optional type mapping
    ast_opt = OptionalType(inner_type=StrType())
    ir_opt = map_type_to_ir(ast_opt)
    assert isinstance(ir_opt, IROptionType)
    assert isinstance(ir_opt.inner_type, IRStrType)


def test_pattern_store_sqlite_migration():
    import tempfile
    import os
    import json
    from py2rust.learning_system.learning.pattern_store import PatternStore

    with tempfile.TemporaryDirectory() as tmpdir:
        jsonl_path = os.path.join(tmpdir, "patterns.jsonl")
        db_path = os.path.join(tmpdir, "patterns.db")

        # Create a legacy jsonl file
        pattern_record = {
            "pattern_id": "test_migrated_pattern",
            "timestamp": "2026-05-28T00:00:00Z",
            "trigger_pattern": "x / y",
            "target_rust": "x / y",
            "replacement_rust": "x as f64 / y as f64",
            "evidence_count": 5,
            "confidence": 0.99
        }
        with open(jsonl_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(pattern_record) + "\n")

        # Use as context manager so connection is closed before tmpdir is deleted
        with PatternStore(db_path) as store:
            # Verify jsonl is gone and database has the record
            assert not os.path.exists(jsonl_path)
            patterns = store.get_patterns()
            assert len(patterns) == 1
            assert patterns[0]["pattern_id"] == "test_migrated_pattern"
            assert patterns[0]["evidence_count"] == 5
            assert patterns[0]["confidence"] == 0.99


def test_pattern_store_concurrent_writes():
    import tempfile
    import os
    import threading
    from py2rust.learning_system.learning.pattern_store import PatternStore

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "patterns.db")
        with PatternStore(db_path) as store:
            def write_pattern(idx):
                pattern = {
                    "pattern_id": f"pattern_{idx}",
                    "trigger_pattern": "trigger",
                    "target_rust": "target",
                    "replacement_rust": "replacement",
                    "evidence_count": 1,
                    "confidence": 0.5
                }
                store.save_pattern(pattern)

            # Spawn multiple threads writing to the database concurrently
            threads = []
            for i in range(10):
                t = threading.Thread(target=write_pattern, args=(i,))
                threads.append(t)
                t.start()

            for t in threads:
                t.join()

            # Verify all patterns were stored safely
            patterns = store.get_patterns()
            assert len(patterns) == 10
            pattern_ids = {p["pattern_id"] for p in patterns}
            for i in range(10):
                assert f"pattern_{i}" in pattern_ids


