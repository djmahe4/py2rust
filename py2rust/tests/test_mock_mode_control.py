import pytest
from py2rust.cli import main
import sys
import os
from unittest.mock import patch

def test_mock_mode_disabled_fails_on_missing_import(tmp_path):
    py_file = tmp_path / "test_import.py"
    py_file.write_text("import unknown_module\n")
    
    with patch.object(sys, 'argv', ['py2rust', str(py_file)]):
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code != 0

def test_mock_mode_enabled_succeeds_on_missing_import(tmp_path):
    py_file = tmp_path / "test_import.py"
    py_file.write_text("import unknown_module\n")
    
    # We need to set PYTHONPATH to include current dir to find py2rust
    os.environ['PYTHONPATH'] = os.getcwd()
    
    with patch.object(sys, 'argv', ['py2rust', str(py_file), '--mock-mode']):
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 0

def test_typevar_elimination(tmp_path):
    py_file = tmp_path / "test_typevar.py"
    py_file.write_text("from typing import TypeVar\nT = TypeVar('T')\n")
    rs_file = tmp_path / "test_typevar.rs"
    
    with patch.object(sys, 'argv', ['py2rust', str(py_file), '-o', str(rs_file)]):
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 0
    
    rs_content = rs_file.read_text()
    assert "TypeVar" not in rs_content
    assert "T =" not in rs_content
