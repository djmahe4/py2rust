import pytest
from py2rust.frontend.parser import Parser
from py2rust.middleend.type_checker import TypeChecker
from py2rust.middleend.symbol_table import SymbolTable
from py2rust.config import CompilerConfig
from py2rust.frontend.ast_nodes import ExternalPythonType

def test_external_import_wrapping():
    source = """
import non_existent_module
from another_fake_module import some_func

# Use global statements to avoid scope issues in tests
x = non_existent_module.some_attr
y = some_func(1, 2)
"""
    parser = Parser(source)
    module = parser.parse()
    
    st = SymbolTable(config=CompilerConfig(mock_mode=True))
    checker = TypeChecker(st)
    
    # This should not raise SemanticError/TypeError for missing modules
    checker.check_module(module)
    
    # Check if symbols are registered as ExternalPythonType
    x_type = st.lookup("x")
    assert isinstance(x_type, ExternalPythonType)
    assert "some_attr" in x_type.name
    
    y_type = st.lookup("y")
    assert isinstance(y_type, ExternalPythonType)
    assert "some_func()" in y_type.name

def test_mock_call_inference():
    source = """
import requests

resp = requests.get("http://example.com")
data = resp.json()
"""
    parser = Parser(source)
    module = parser.parse()
    
    st = SymbolTable(config=CompilerConfig(mock_mode=True))
    checker = TypeChecker(st)
    
    checker.check_module(module)
    
    # 'requests' should be ExternalPythonType
    assert isinstance(st.lookup("requests"), ExternalPythonType)
    
    # 'resp' should be ExternalPythonType
    resp_type = st.lookup("resp")
    assert isinstance(resp_type, ExternalPythonType)
    assert "get()" in resp_type.name
    
    # 'data' should be ExternalPythonType
    data_type = st.lookup("data")
    assert isinstance(data_type, ExternalPythonType)
    assert "json()" in data_type.name
