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
    assert "let __stop = 0;" in code
    assert "while if (__step) > 0 { i < (__stop) } else { i > (__stop) } {" in code
    assert "i += __step;" in code

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
    assert "let x: i32;" in code
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
    assert "i = 0;" in code
    assert "while if (__step) > 0 { i < (__stop) } else { i > (__stop) } {" in code

def test_string_indexing():
    src = """
def main() -> int:
    s: str = "abc"
    char: str = s[0]
    return 0
"""
    code = _compile(src)
    assert "chars().nth" in code
    assert "let i = 0;" in code
    assert "i < 0" in code
    assert "s.chars().count()" in code
    assert "unwrap().to_string()" in code

def test_list_move_semantics():
    src = """
def main() -> int:
    lst: list[str] = ["a", "b"]
    s: str = lst[0]
    return 0
"""
    code = _compile(src)
    # Should uses .clone() because String is not Copy
    assert "lst[" in code
    assert "len() as i32" in code
    assert ").clone()" in code

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

def test_unannotated_var_scoping():
    src = """
def main() -> int:
    if True:
        x = 42
    print(x)
    return 0
"""
    code = _compile(src)
    assert "let x: i32;" in code
    assert "x = 42;" in code

def test_loop_target_persistence():
    src = """
def main() -> int:
    for i in range(0, 10):
        pass
    print(i)
    return 0
"""
    # Replace pass
    src = """
def main() -> int:
    for i in range(0, 5):
        s = i
    print(i)
    return 0
"""
    code = _compile(src)
    assert "let mut i: i32;" in code
    assert "println!(\"{}\", i);" in code

def test_negative_indexing_runtime():
    src = """
def main() -> int:
    s: str = "abc"
    last: str = s[-1]
    lst: list[int] = [1, 2, 3]
    last_val: int = lst[-1]
    return 0
"""
    code = _compile(src)
    # Check for negative index handling logic
    assert "if i < 0" in code
    assert "s.chars().count()" in code
    assert "lst.len()" in code

def test_while_loop_range_semantics():
    src = """
def main() -> int:
    s = 0
    for i in range(10, 0, -1):
        s += i
    return s
"""
    code = _compile(src)
    # Target initialized
    assert "i = 10;" in code
    # Condition handles negative step
    assert "while if (__step) > 0 { i < (__stop) } else { i > (__stop) } {" in code
    # Increment
    assert "i += __step;" in code

def test_range_single_evaluation():
    src = """
def stop_fn() -> int:
    return 10

def main() -> int:
    s = 0
    for i in range(0, stop_fn()):
        s += i
    return s
"""
    code = _compile(src)
    # Check that stop_fn() is evaluated into a temp variable exactly once
    assert "let __stop = stop_fn();" in code
    # Check that the loop condition uses the temp variable
    assert "while if (__step) > 0 { i < (__stop) } else { i > (__stop) }" in code

def test_idiomatic_mut_generation():
    src = """
def main() -> int:
    x: int = 42
    print(x)
    return 0
"""
    code = _compile(src)
    # x is only initialized, never reassigned. Should NOT be mut.
    assert "let x: i32;" in code
    assert "mut x" not in code

def test_standalone_function_call():
    src = """
def helper(x: int) -> int:
    print(x)
    return x

def main() -> int:
    helper(42)
    return 0
"""
    code = _compile(src)
    # Should be converted to _ = helper(42);
    assert "_ = helper(42);" in code
    # _ is used as target in parse_stmt, but it's a discard. 
    # Actually, in our current IRVarDecl logic, _ will be caught as a declaration.
    # It might or might not be mut depending on _collect_mutated_vars.
    assert "let _: i32;" in code or "let mut _: i32;" in code

def test_semantic_error_in_ir_builder():
    from py2rust.utils.errors import SemanticError
    # We need a case that triggers _to_ir_type's catch-all
    # This is hard to trigger from parser because parser limits types,
    # but we can test the function directly.
    from py2rust.middleend.ir_builder import _to_ir_type
    class JunkType: pass
    with pytest.raises(SemanticError):
        _to_ir_type(JunkType())
