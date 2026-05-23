from __future__ import annotations
import unittest
import os
import tempfile
from py2rust.config import CompilerConfig

def test_compiler_config_validation_fields():
    # Attempt to initialize config with new validation-learning properties
    config = CompilerConfig(
        validate=True,
        ollama_model="deepseek-coder",
        strict_validation=True,
        learn_patterns=True,
        apply_learned_patterns=True,
        review_failures=True
    )
    assert config.validate is True
    assert config.ollama_model == "deepseek-coder"
    assert config.strict_validation is True
    assert config.learn_patterns is True
    assert config.apply_learned_patterns is True
    assert config.review_failures is True

def test_ollama_client_generate():
    from py2rust.learning_system.validation.ollama_client import OllamaClient
    client = OllamaClient(model="deepseek-coder")
    # Mocking standard post requests to bypass external service
    import unittest.mock as mock
    with mock.patch("requests.post") as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"response": "VERDICT: PASS"}
        res = client.generate("test prompt")
        assert "VERDICT: PASS" in res

def test_semantic_validator_format_and_context():
    from py2rust.learning_system.validation.semantic_validator import SemanticValidator
    validator = SemanticValidator()
    # verify context retrieval handles Windows/Unix tools and fallback safely
    context = validator.get_symbol_context("my_func")
    assert context is not None
    
    # Mocking client response for validator equivalence check
    import unittest.mock as mock
    mock_client = mock.Mock()
    mock_client.generate.return_value = "VERDICT: PASS\nCONFIDENCE: 0.95\nREASONING: Code matches exactly."
    validator.client = mock_client
    
    res = validator.validate_equivalence("def my_func(): pass", "fn my_func() {}", "my_func")
    assert res["verdict"] == "PASS"
    assert res["confidence"] == 0.95
    assert "matches exactly" in res["reasoning"].lower()

def test_validation_store_persistence():
    from py2rust.learning_system.validation.validation_store import ValidationStore
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "validations.jsonl")
        store = ValidationStore(db_path)
        
        # Save validation record
        record = {
            "symbol_name": "calc_sum",
            "python_source": "def calc_sum(a, b): return a + b",
            "generated_rust": "fn calc_sum(a: i32, b: i32) -> i32 { a + b }",
            "verdict": "PASS",
            "confidence": 0.98,
            "reasoning": "Behaviorally identical."
        }
        store.save_validation(record)
        
        # Verify persistence and retrieval
        records = store.get_validations()
        assert len(records) == 1
        assert records[0]["symbol_name"] == "calc_sum"
        assert records[0]["verdict"] == "PASS"
        assert records[0]["confidence"] == 0.98

def test_pattern_store_persistence():
    from py2rust.learning_system.learning.pattern_store import PatternStore
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "patterns.jsonl")
        store = PatternStore(db_path)
        
        pattern = {
            "pattern_id": "float_division",
            "trigger_pattern": "a / b",
            "target_rust": "a / b",
            "replacement_rust": "a as f64 / b as f64",
            "evidence_count": 2,
            "confidence": 0.92
        }
        store.save_pattern(pattern)
        
        patterns = store.get_patterns()
        assert len(patterns) == 1
        assert patterns[0]["pattern_id"] == "float_division"
        assert patterns[0]["evidence_count"] == 2

def test_pattern_extractor():
    from py2rust.learning_system.learning.pattern_extractor import PatternExtractor
    from py2rust.learning_system.learning.pattern_store import PatternStore
    
    with tempfile.TemporaryDirectory() as tmpdir:
        patterns_path = os.path.join(tmpdir, "patterns.jsonl")
        pattern_store = PatternStore(patterns_path)
        extractor = PatternExtractor(pattern_store=pattern_store, evidence_threshold=2)
        
        # Aggregated validation failures
        failures = [
            {
                "symbol_name": "divide",
                "python_source": "def divide(a, b): return a / b",
                "generated_rust": "fn divide(a: i32, b: i32) -> f64 { a / b }",
                "verdict": "FAIL",
                "confidence": 0.9,
                "reasoning": "Integer division truncates, but return type is f64."
            },
            {
                "symbol_name": "divide_floats",
                "python_source": "def divide_floats(x, y): return x / y",
                "generated_rust": "fn divide_floats(x: i32, y: i32) -> f64 { x / y }",
                "verdict": "FAIL",
                "confidence": 0.9,
                "reasoning": "Integer division truncates instead of float output."
            }
        ]
        
        # Mock client to return generalized pattern
        import unittest.mock as mock
        mock_client = mock.Mock()
        mock_client.generate.return_value = """PATTERN_ID: int_to_float_div
TRIGGER_PATTERN: /
TARGET_RUST: a / b
REPLACEMENT_RUST: a as f64 / b as f64
CONFIDENCE: 0.88"""
        
        extractor.client = mock_client
        extractor.extract_from_failures(failures)
        
        patterns = pattern_store.get_patterns()
        assert len(patterns) == 1
        assert patterns[0]["pattern_id"] == "int_to_float_div"
        assert patterns[0]["trigger_pattern"] == "/"
        assert patterns[0]["replacement_rust"] == "a as f64 / b as f64"

def test_pattern_applicator_format():
    from py2rust.learning_system.learning.pattern_applicator import PatternApplicator
    
    pattern = {
        "pattern_id": "int_to_float_div",
        "trigger_pattern": "/",
        "target_rust": "a / b",
        "replacement_rust": "a as f64 / b as f64",
        "confidence": 0.88
    }
    
    applicator = PatternApplicator(patterns=[pattern])
    
    # Check if mismatch/incorrect code triggers suggestion
    original_rust = "fn divide(a: i32, b: i32) -> f64 { a / b }"
    suggestion = applicator.suggest_fix(original_rust, "divide")
    
    assert suggestion is not None
    assert "PROPOSED RUST COMPILATION IMPROVEMENT" in suggestion
    assert "```rust" in suggestion
    assert "a as f64 / b as f64" in suggestion
    # Verify no autonomous changes are made; code is unchanged
    assert original_rust == "fn divide(a: i32, b: i32) -> f64 { a / b }"

def test_pipeline_integration():
    from py2rust.main import compile_file
    
    with tempfile.TemporaryDirectory() as tmpdir:
        input_file = os.path.join(tmpdir, "test.py")
        output_file = os.path.join(tmpdir, "test.rs")
        
        with open(input_file, "w", encoding="utf-8") as f:
            f.write("def my_func(): return 42\n")
            
        config = CompilerConfig(
            input_file=input_file,
            output_file=output_file,
            validate=True,
            strict_validation=True,
            learn_patterns=True,
            apply_learned_patterns=True
        )
        
        # Mock client to return semantic mismatch
        import unittest.mock as mock
        mock_client = mock.Mock()
        mock_client.generate.return_value = "VERDICT: FAIL\nCONFIDENCE: 0.99\nREASONING: Semantic mismatch detected.\nSUGGESTED_FIX: return 43"
        
        # Patch main module references to validator, store, extractor, applicator
        with mock.patch("py2rust.learning_system.validation.semantic_validator.OllamaClient") as mock_ollama_cls:
            mock_ollama_cls.return_value = mock_client
            
            # Since strict_validation is active, mismatch should cause compile_file to return False
            success = compile_file(config)
            assert success is False






