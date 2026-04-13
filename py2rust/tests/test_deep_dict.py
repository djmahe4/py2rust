import pytest
from py2rust.frontend.parser import Parser
from py2rust.middleend.ir_builder import IRBuilder
from py2rust.backend.rust_codegen import RustCodegen

def test_deep_dict_update():
    source = """
def update_dict() -> int:
    d: dict[str, dict[str, int]] = {"a": {"b": 1}}
    d["a"]["b"] = 2
    return d["a"]["b"]
"""
    parser = Parser(source)
    module = parser.parse()
    
    builder = IRBuilder()
    ir_mod = builder.build(module)
    
    codegen = RustCodegen()
    rust_code = codegen.generate(ir_mod)
    
    # Verify recursively generated mutable access
    assert "(d.get_mut(&\"a\".to_string()).unwrap()).insert(\"b\".to_string(), 2);" in rust_code

def test_deep_list_update():
    source = """
def update_matrix() -> int:
    m: list[list[int]] = [[1, 2], [3, 4]]
    m[0][1] = 5
    return m[0][1]
"""
    parser = Parser(source)
    module = parser.parse()
    
    builder = IRBuilder()
    ir_mod = builder.build(module)
    
    codegen = RustCodegen()
    rust_code = codegen.generate(ir_mod)
    
    # Verify recursively generated mutable indexing
    assert "(&mut m[0 as usize])[1 as usize] = 5;" in rust_code

def test_mixed_deep_update():
    source = """
def update_mixed() -> int:
    d: dict[str, list[int]] = {"a": [1, 2]}
    d["a"][0] = 3
    return d["a"][0]
"""
    parser = Parser(source)
    module = parser.parse()
    
    builder = IRBuilder()
    ir_mod = builder.build(module)
    
    codegen = RustCodegen()
    rust_code = codegen.generate(ir_mod)
    
    assert "(d.get_mut(&\"a\".to_string()).unwrap())[0 as usize] = 3;" in rust_code
