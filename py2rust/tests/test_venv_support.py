import pytest
import os
import subprocess
from py2rust.cli import main
from py2rust.config import CompilerConfig
from py2rust.middleend.ir_builder import build_ir
from py2rust.backend.rust_codegen import generate_rust
from py2rust.frontend.parser import Parser

def test_venv_boilerplate_generation():
    source = """
import numpy as np
def f() -> None:
    x = np.array([1, 2])
"""
    parser = Parser(source)
    module = parser.parse()
    
    config = CompilerConfig(mock_mode=True)
    ir_module = build_ir(module, config=config)
    rust_code = generate_rust(ir_module)
    
    # Check if venv logic is present
    assert "PY2RUST_VENV" in rust_code
    assert "init_venv" in rust_code
    assert "site-packages" in rust_code
    assert "env::var" in rust_code

def test_big_lib_compilation():
    # Verify that we can compile the big_lib_test.py without errors
    example_path = "examples/big_lib_test.py"
    output_path = "examples/big_lib_test.rs"
    
    # Run CLI
    result = subprocess.run(
        ["python3", "-m", "py2rust.cli", example_path, "-o", output_path, "--mock-mode"],
        capture_output=True,
        text=True
    )
    
    assert result.returncode == 0
    # The message "[INFO] Written: ..." goes to stderr
    expected_path = os.path.normpath("examples/big_lib_test.rs")
    assert f"Written: {expected_path}" in result.stderr
    
    with open(output_path, "r") as f:
        content = f.read()
        assert "ExternalObject" in content
        assert "numpy" in content
        assert "cv2" in content
        assert 'call_method("imshow"' in content
        assert 'call_method("waitKey"' in content
        assert 'call_method("destroyAllWindows"' in content
