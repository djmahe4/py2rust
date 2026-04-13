"""
Wave 10 update includes: 
- Exception handling
- Membership operators
- Tuple destructuring
- Collection iteration
"""

import pytest
from ..frontend.parser import Parser
from ..middleend.ir_builder import build_ir
from ..backend.rust_codegen import RustCodegen

def compile_to_rust(source: str) -> str:
    parser = Parser(source)
    module = parser.parse()
    ir = build_ir(module)
    codegen = RustCodegen()
    return codegen.generate(ir)

def test_collection_iteration():
    source = """
def f() -> int:
    items = [1, 2, 3]
    total = 0
    for x in items:
        total += x
    return total
"""
    rust = compile_to_rust(source)
    assert "for __val_" in rust
    assert "total = total + x" in rust or "total += x" in rust

def test_membership_operators():
    source = """
def f(x: int) -> bool:
    items = [1, 2, 3]
    return x in items
"""
    rust = compile_to_rust(source)
    assert "items.contains(&x)" in rust

def test_tuple_destructuring():
    source = """
def f() -> int:
    x, y = 1, 2
    return x + y
"""
    rust = compile_to_rust(source)
    assert "let (x, y) = (1, 2);" in rust

def test_exception_handling():
    source = """
def f(x: int) -> int:
    try:
        if x < 0:
            raise ValueError("negative")
        return x * 2
    except ValueError as e:
        print(e)
        return -1
"""
    rust = compile_to_rust(source)
    assert "Result<i32, PyError>" in rust
    assert "let __result = (|| -> Result<(), PyError>" in rust
    assert "PyError::ValueError(\"negative\".to_string())" in rust
    assert "if let Err(__exc) = __result" in rust
    # When caught, it's cloned for the handler
    assert "let e = __exc.clone();" in rust
