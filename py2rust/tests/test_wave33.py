from __future__ import annotations
import unittest
import os
import tempfile
from py2rust.config import CompilerConfig, AsyncRuntime

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


