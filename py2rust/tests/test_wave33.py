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

