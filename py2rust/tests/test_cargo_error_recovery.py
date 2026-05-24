from unittest.mock import patch, MagicMock
import pytest
import os
from py2rust.learning_system.validation.ollama_client import OllamaClient
from py2rust.main import compile_file
from py2rust.config import CompilerConfig
from py2rust.utils.errors import UnsupportedFeatureError

def test_ollama_client_is_available():
    client = OllamaClient(host="http://localhost:11434")
    
    # Mocking successful server ping
    mock_res = MagicMock()
    mock_res.status_code = 200
    with patch("requests.get", return_value=mock_res) as mock_get:
        assert client.is_available() is True
        mock_get.assert_called_once_with("http://localhost:11434", timeout=2)
        
    # Mocking server offline
    with patch("requests.get", side_effect=Exception("Connection refused")):
        assert client.is_available() is False

@patch("subprocess.run")
@patch("py2rust.learning_system.validation.ollama_client.OllamaClient.is_available", return_value=True)
@patch("py2rust.learning_system.validation.ollama_client.OllamaClient.generate")
def test_cargo_check_failure_with_llm_reasoning(mock_generate, mock_is_available, mock_run, tmp_path):
    mock_generate.return_value = "EXPLANATION: Lifetime borrowing issue.\nSUGGESTED_FIX: fn x<'a>()"
    
    # Mock cargo init success, but cargo check failure
    mock_run_init = MagicMock()
    mock_run_init.returncode = 0
    
    mock_run_check = MagicMock()
    mock_run_check.returncode = 1
    mock_run_check.stderr = "error[E0106]: missing lifetime specifier"
    
    def run_side_effect(args, **kwargs):
        if len(args) > 1 and args[1] == 'init':
            import os
            os.makedirs(os.path.join(args[-1], "src"), exist_ok=True)
            return mock_run_init
        return mock_run_check
        
    mock_run.side_effect = run_side_effect
    
    input_file = tmp_path / "dummy.py"
    import uuid
    func_name = f"test_{uuid.uuid4().hex[:8]}"
    input_file.write_text(f"def {func_name}() -> None:\n    pass")
    output_file = tmp_path / "dummy.rs"
    
    config = CompilerConfig(
        input_file=str(input_file),
        output_file=str(output_file),
        verify=True,
        validate=True,
        review_failures=False # Auto print without interactive prompt in test
    )
    
    success = compile_file(config)
    assert success is False
    assert mock_generate.call_count == 2
    assert "missing lifetime specifier" in mock_generate.call_args_list[1][0][0]

@patch("py2rust.main.parse")
@patch("py2rust.learning_system.validation.ollama_client.OllamaClient.is_available", return_value=True)
@patch("py2rust.learning_system.validation.ollama_client.OllamaClient.generate")
def test_py2rust_compiler_error_recovery(mock_generate, mock_is_available, mock_parse, tmp_path):
    mock_generate.return_value = "EXPLANATION: Ternary operators not supported.\nSUGGESTED_FIX: Use if-else block statement."
    
    # Mock compile error
    mock_parse.side_effect = UnsupportedFeatureError("Ternary expressions strictly rejected", filename="dummy.py", line=2, column=5)
    
    input_file = tmp_path / "dummy.py"
    input_file.write_text("x = 1 if True else 0")
    
    config = CompilerConfig(
        input_file=str(input_file),
        verify=False,
        validate=True,
        review_failures=False
    )
    
    success = compile_file(config)
    assert success is False
    mock_generate.assert_called_once()
    assert "Ternary expressions" in mock_generate.call_args[0][0]
