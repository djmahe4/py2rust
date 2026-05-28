import pytest
from py2rust.frontend.parser import Parser
from py2rust.middleend.symbol_table import SymbolTable
from py2rust.middleend.type_checker import TypeChecker
from py2rust.middleend.ir_builder import IRBuilder
from py2rust.backend.rust_codegen import RustCodegen

def test_multi_inheritance_detection():
    source = """
class A:
    x: int = 1
    def fa(self) -> int:
        return self.x

class B:
    y: int = 2
    def fb(self) -> int:
        return self.y

class C(A, B):
    def fc(self) -> int:
        return self.fa() + self.fb()
"""
    parser = Parser(source)
    module = parser.parse()
    
    st = SymbolTable()
    checker = TypeChecker(st)
    checker.check_module(module)
    
    builder = IRBuilder(symbol_table=st)
    ir_mod = builder.build(module)
    
    # Find class C
    class_c = next(c for c in ir_mod.classes if c.name == "C")
    assert class_c.bases == ("A", "B")
    
    # Verify flattening: C should have x, y, fa, fb, fc
    field_names = [f[0] for f in class_c.fields]
    assert "x" in field_names
    assert "y" in field_names
    
    method_names = [m.name for m in class_c.methods]
    assert "fa" in method_names
    assert "fb" in method_names
    assert "fc" in method_names

    codegen = RustCodegen()
    rust_code = codegen.generate(ir_mod)
    
    assert "struct C {" in rust_code
    assert "x: i32," in rust_code
    assert "y: i32," in rust_code
    assert "fn fa(&self) -> Result<i32, PyError>" in rust_code
    assert "fn fb(&self) -> Result<i32, PyError>" in rust_code
    assert "fn fc(&self) -> Result<i32, PyError>" in rust_code
