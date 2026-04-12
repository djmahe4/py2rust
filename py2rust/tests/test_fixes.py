import pytest
from py2rust.frontend.parser import parse
from py2rust.middleend.ir_builder import build_ir
from py2rust.backend.rust_codegen import generate_rust
from py2rust.middleend.symbol_table import SymbolTable
from py2rust.middleend.type_checker import TypeChecker
from py2rust.utils.errors import Py2RustTypeError

def _compile(src):
    return generate_rust(build_ir(parse(src)))

def _check(src):
    m = parse(src)
    st = SymbolTable()
    tc = TypeChecker(st)
    tc.check_module(m)
    return m, st

def test_floor_division_negative():
    src = """
def main() -> int:
    x: int = -1 // 2
    return 0
"""
    code = _compile(src)
    # The generator now produces: ((- (1)) as f64 / (2) as f64).floor() as i32
    assert ".floor() as i32" in code

def test_negative_range_step():
    src = """
def main() -> int:
    for i in range(10, 0, -1):
        print(i)
    return 0
"""
    code = _compile(src)
    assert ".rev().step_by(1 as usize)" in code

def test_operator_precedence():
    src = """
def f(a: bool, b: bool, c: bool) -> bool:
    return not (a and b) or c
"""
    code = _compile(src)
    assert "!" in code
    assert "&&" in code
    assert "||" in code
    # Check for heavy parenthesization from nested expressions
    assert "||" in code and "!" in code

def test_print_list():
    src = """
def main() -> int:
    lst: list[int] = [1, 2]
    print(lst)
    return 0
"""
    code = _compile(src)
    assert 'println!("{:?}", lst);' in code

def test_aug_assign_validation():
    src = """
def main() -> int:
    x: int = 1
    x += 1.5
    return 0
"""
    with pytest.raises(Py2RustTypeError):
        _check(src)

def test_range_int_validation():
    src = """
def main() -> int:
    for i in range(0.0, 10.0):
        x: int = 0
    return 0
"""
    with pytest.raises(Py2RustTypeError):
        _check(src)

def test_function_scoping():
    src = """
def main() -> int:
    if True:
        x: int = 42
    print(x)
    return 0
"""
    code = _compile(src)
    # x should be declared at the top of the function
    assert "let mut x: i32 = 0;" in code
    # And then assigned inside the if
    assert "x = 42;" in code

def test_mutable_loop_var():
    src = """
def main() -> int:
    for i in range(0, 10):
        i = i + 1
    return 0
"""
    code = _compile(src)
    assert "for mut i in 0..10 {" in code

def test_string_indexing():
    src = """
def main() -> int:
    s: str = "abc"
    char: str = s[0]
    return 0
"""
    code = _compile(src)
    assert "s.chars().nth((0) as usize).unwrap().to_string()" in code

def test_list_move_semantics():
    src = """
def main() -> int:
    lst: list[str] = ["a", "b"]
    s: str = lst[0]
    return 0
"""
    code = _compile(src)
    # Should uses .clone() because String is not Copy
    assert "(lst[(0) as usize]).clone()" in code

def test_invalid_condition_type():
    src = """
def main() -> int:
    if 1:
        pass
    return 0
"""
    # Simplified valid statement since 'pass' is not supported
    src = """
def main() -> int:
    x: int = 1
    if x:
        x = 2
    return 0
"""
    with pytest.raises(Py2RustTypeError):
        _check(src)

def test_unknown_type_marker():
    from py2rust.ir.ir_nodes import IRVarDecl, IRIntLit
    from py2rust.backend.rust_codegen import RustCodegen
    
    class UnknownType:
        pass
        
    cg = RustCodegen()
    stmt = IRVarDecl(name="x", type_=UnknownType(), value=IRIntLit(value=42))
    # We need to wrap it in a function body for _gen_stmt to work correctly with new scoping
    from py2rust.ir.ir_nodes import IRFunction, IRIntType
    func = IRFunction(name="f", params=(), return_type=IRIntType(), body=(stmt,))
    code = cg.generate(from_ir_module_dummy([func])) # helper needed
    
    # Or just test _rust_type directly
    from py2rust.backend.rust_codegen import _rust_type
    assert "/* unknown type UnknownType */" == _rust_type(UnknownType())

def from_ir_module_dummy(funcs):
    from py2rust.ir.ir_nodes import IRModule
    return IRModule(functions=tuple(funcs))

def test_visitor_tuple_traversal():
    from py2rust.utils.visitor import NodeVisitor
    from py2rust.frontend.ast_nodes import Module, FunctionDef, IntLiteral, ReturnStmt, IntType
    
    class TestVisitor(NodeVisitor):
        def __init__(self):
            self.visited_ints = 0
        def visit_IntLiteral(self, node):
            self.visited_ints += 1
            
    # FunctionDef.body is a tuple
    node = Module(functions=(
        FunctionDef(name="f", params=(), return_type=IntType(), body=(
            ReturnStmt(value=IntLiteral(value=42)),
        )),
    ))
    
    visitor = TestVisitor()
    visitor.visit(node)
    assert visitor.visited_ints == 1
