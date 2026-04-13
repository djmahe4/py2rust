import pytest
from py2rust.frontend.parser import Parser
from py2rust.middleend.symbol_table import SymbolTable
from py2rust.middleend.type_checker import TypeChecker
from py2rust.middleend.ir_builder import IRBuilder
from py2rust.backend.rust_codegen import RustCodegen

def test_nested_classes_in_class():
    source = """
class Outer:
    val: int = 10
    class Inner:
        x: int = 1
        def get_x(self) -> int:
            return self.x
    
    def get_inner(self) -> int:
        i = Inner()
        return i.get_x()
"""
    parser = Parser(source)
    module = parser.parse()
    
    st = SymbolTable()
    builder = IRBuilder(symbol_table=st)
    ir_mod = builder.build(module)
    
    # Check classes
    class_names = [c.name for c in ir_mod.classes]
    assert "Outer" in class_names
    assert "Outer_Inner" in class_names
    
    codegen = RustCodegen()
    rust_code = codegen.generate(ir_mod)
    
    assert "struct Outer {" in rust_code
    assert "struct Outer_Inner {" in rust_code
    assert "impl Outer_InnerTrait for Outer_Inner {" in rust_code
    assert "let i: Outer_Inner = Outer_Inner::new(" in rust_code

def test_nested_classes_in_function():
    source = """
def func() -> int:
    class Local:
        y: int = 5
        def get_y(self) -> int:
            return self.y
    
    obj = Local()
    return obj.get_y()
"""
    parser = Parser(source)
    module = parser.parse()
    
    st = SymbolTable()
    builder = IRBuilder(symbol_table=st)
    ir_mod = builder.build(module)
    
    class_names = [c.name for c in ir_mod.classes]
    assert "func_Local" in class_names
    
    codegen = RustCodegen()
    rust_code = codegen.generate(ir_mod)
    
    assert "struct func_Local {" in rust_code
    assert "let obj: func_Local = func_Local::new(" in rust_code
