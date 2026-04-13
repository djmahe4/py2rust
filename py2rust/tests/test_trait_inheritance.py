
import pytest
from py2rust.frontend.parser import parse
from py2rust.middleend.type_checker import TypeChecker
from py2rust.middleend.ir_builder import IRBuilder
from py2rust.backend.rust_codegen import generate_rust
from py2rust.middleend.symbol_table import SymbolTable

def test_trait_generation_basic():
    code = """
class Base:
    def greet(self) -> str:
        return "Hello"

class Derived(Base):
    def greet(self) -> str:
        return "Hi"
    
    def work(self) -> str:
        return "Working"
"""
    ast = parse(code)
    st = SymbolTable()
    tc = TypeChecker(st)
    tc.check_module(ast)
    
    builder = IRBuilder(st)
    ir_mod = builder.build(ast)
    
    rust_code = generate_rust(ir_mod)
    
    # Check for traits
    assert "pub trait BaseTrait {" in rust_code
    assert "fn greet(&self) -> Result<String, PyError>;" in rust_code
    assert "pub trait DerivedTrait: BaseTrait {" in rust_code
    assert "fn work(&self) -> Result<String, PyError>;" in rust_code
    
    # Check for struct implementations
    assert "impl BaseTrait for Base {" in rust_code
    assert "impl BaseTrait for Derived {" in rust_code
    assert "impl DerivedTrait for Derived {" in rust_code
    
    # Verify method bodies in implementations
    # Derived.greet should return "Hi"
    assert 'Ok("Hi".to_string())' in rust_code

def test_trait_multi_inheritance():
    code = """
class A:
    def foo(self) -> int: return 1

class B:
    def bar(self) -> int: return 2

class C(A, B):
    def baz(self) -> int: return 3
"""
    ast = parse(code)
    st = SymbolTable()
    tc = TypeChecker(st)
    tc.check_module(ast)
    
    builder = IRBuilder(st)
    ir_mod = builder.build(ast)
    
    rust_code = generate_rust(ir_mod)
    
    assert "pub trait CTrait: ATrait + BTrait {" in rust_code
    assert "impl ATrait for C {" in rust_code
    assert "impl BTrait for C {" in rust_code
    assert "impl CTrait for C {" in rust_code

if __name__ == "__main__":
    pytest.main([__file__])
