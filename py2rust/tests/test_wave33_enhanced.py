from __future__ import annotations
import unittest
import os
import tempfile
import sys
from unittest.mock import Mock, patch
from py2rust.config import CompilerConfig
from py2rust.learning_system.validation.validation_store import ValidationStore
from py2rust.learning_system.validation.semantic_validator import SemanticValidator
from py2rust.learning_system.learning.pattern_store import PatternStore
from py2rust.learning_system.learning.pattern_extractor import PatternExtractor
from py2rust.learning_system.learning.pattern_applicator import PatternApplicator

class TestWave33Enhanced(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_validations.db")
        self.patterns_path = os.path.join(self.temp_dir.name, "test_patterns.jsonl")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_validation_store_sqlite_caching(self):
        # 1. Test SQLite Validation Cache Operations
        store = ValidationStore(self.db_path)
        
        # Check cache miss
        cached = store.get_cached_validation("def test(): pass", "fn test() {}")
        self.assertIsNone(cached)
        
        # Save validation
        record = {
            "symbol_name": "test_func",
            "python_source": "def test(): pass",
            "generated_rust": "fn test() {}",
            "verdict": "PASS",
            "confidence": 0.95,
            "reasoning": "Identical behavior",
            "is_hitl": 0
        }
        store.save_validation(record)
        
        # Check cache hit
        cached = store.get_cached_validation("def test(): pass", "fn test() {}")
        self.assertIsNotNone(cached)
        self.assertEqual(cached["verdict"], "PASS")
        self.assertEqual(cached["symbol_name"], "test_func")
        
        # Check no hit with different code
        different = store.get_cached_validation("def test(): return 1", "fn test() {}")
        self.assertIsNone(different)

    def test_validation_store_hitl_actions(self):
        # 2. Test SQLite HITL Cache Operations
        store = ValidationStore(self.db_path)
        
        # Save a HITL override (e.g., user approved a compile output)
        record = {
            "symbol_name": "hitl_func",
            "python_source": "def hitl_func(): pass",
            "generated_rust": "fn hitl_func() {}",
            "verdict": "PASS",
            "confidence": 1.0,
            "reasoning": "HITL Approved",
            "is_hitl": 1
        }
        store.save_validation(record)
        
        # Verify HITL flag is preserved
        validations = store.get_validations()
        self.assertEqual(len(validations), 1)
        self.assertEqual(validations[0]["is_hitl"], 1)

    def test_interactive_hitl_manager_approval(self):
        # Test human-in-the-loop interactive mode auto-accept (y)
        from py2rust.learning_system.validation.semantic_validator import SemanticValidator
        validator = SemanticValidator(db_path=self.db_path)
        
        # Set up a mock client returning FAIL to trigger HITL prompting
        mock_client = Mock()
        mock_client.generate.return_value = "VERDICT: FAIL\nCONFIDENCE: 0.8\nREASONING: Discrepancy in variable names."
        validator.client = mock_client
        
        # Mocking input to simulate user typing 'y'
        with patch("builtins.input", return_value="y") as mock_input:
            result = validator.validate_equivalence(
                python_code="def my_func(): pass",
                rust_code="fn my_func() {}",
                symbol_name="my_func",
                interactive=True
            )
            self.assertEqual(result["verdict"], "PASS")
            self.assertEqual(result["reasoning"], "User manual override (Approved)")
            self.assertEqual(result["is_hitl"], 1)
            mock_input.assert_called_once()

    def test_interactive_hitl_manager_rejection(self):
        # Test human-in-the-loop interactive mode rejection (n)
        from py2rust.learning_system.validation.semantic_validator import SemanticValidator
        validator = SemanticValidator(db_path=self.db_path)
        
        mock_client = Mock()
        mock_client.generate.return_value = "VERDICT: FAIL\nCONFIDENCE: 0.8\nREASONING: Semantic mismatch."
        validator.client = mock_client
        
        # Mocking input to simulate user typing 'n'
        with patch("builtins.input", return_value="n") as mock_input:
            result = validator.validate_equivalence(
                python_code="def my_func(): pass",
                rust_code="fn my_func() {}",
                symbol_name="my_func",
                interactive=True
            )
            self.assertEqual(result["verdict"], "FAIL")
            self.assertEqual(result["reasoning"], "User manual override (Rejected)")
            self.assertEqual(result["is_hitl"], 1)
            mock_input.assert_called_once()

    def test_neo_patterns_queries(self):
        # Test neo reasoning pattern representations Qname, Qglobal_flow, Qcall
        from py2rust.learning_system.validation.semantic_validator import SemanticValidator
        validator = SemanticValidator(db_path=self.db_path)
        
        # Mock generate call to ensure neo tags are included in prompt
        mock_client = Mock()
        mock_client.generate.return_value = "VERDICT: PASS\nCONFIDENCE: 0.99\nREASONING: Logic matches."
        validator.client = mock_client
        
        result = validator.validate_equivalence(
            python_code="x = 42\nprint(x)",
            rust_code="let x = 42;\nprintln!(\"{}\", x);",
            symbol_name="main"
        )
        
        # Verify call was constructed
        mock_client.generate.assert_called_once()
        prompt_sent = mock_client.generate.call_args[0][0]
        self.assertIn("Qname(x)", prompt_sent)
        self.assertIn("Qcall(print)", prompt_sent)
        self.assertIn("Qglobal_flow", prompt_sent)

    def test_cli_argument_parsing(self):
        # Test cli handles new properties from CompilerConfig
        config = CompilerConfig(
            input_file="test.py",
            output_file="test.rs",
            validate=True,
            ollama_model="deepseek-coder",
            strict_validation=True,
            learn_patterns=True,
            apply_learned_patterns=True,
            review_failures=True
        )
        self.assertTrue(config.validate)
        self.assertEqual(config.ollama_model, "deepseek-coder")
        self.assertTrue(config.strict_validation)
        self.assertTrue(config.learn_patterns)
        self.assertTrue(config.apply_learned_patterns)
        self.assertTrue(config.review_failures)

if __name__ == "__main__":
    unittest.main()
