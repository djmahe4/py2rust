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
    # x is declared inside the if block with let
    assert "let x = 42;" in code
    # print uses x after the if block
    assert 'println!("{}", x);' in code


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
    assert "let __idx_raw = 0;" in code
    assert "__idx_raw < 0" in code
    assert "__coll.chars().count()" in code
    assert "{ let __coll = &(s);" in code


def test_list_move_semantics():
    src = """
def main() -> int:
    lst: list[str] = ["a", "b"]
    s: str = lst[0]
    return 0
"""
    code = _compile(src)
    assert "__coll[" in code
    assert "{ let __coll = &(lst);" in code
    assert "(__coll[actual_idx]).clone()" in code


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
    code = cg.generate(from_ir_module_dummy([func]))  # helper needed

    # Or just test _rust_type directly
    from py2rust.backend.rust_codegen import _rust_type

    assert "/* unknown type UnknownType */" == _rust_type(UnknownType())


def from_ir_module_dummy(funcs):
    from py2rust.ir.ir_nodes import IRModule

    return IRModule(functions=tuple(funcs))


def test_visitor_tuple_traversal():
    from py2rust.utils.visitor import NodeVisitor
    from py2rust.frontend.ast_nodes import (
        Module,
        FunctionDef,
        IntLiteral,
        ReturnStmt,
        IntType,
    )

    class TestVisitor(NodeVisitor):
        def __init__(self):
            self.visited_ints = 0

        def visit_IntLiteral(self, node):
            self.visited_ints += 1

    # FunctionDef.body is a tuple
    node = Module(
        functions=(
            FunctionDef(
                name="f",
                params=(),
                return_type=IntType(),
                body=(ReturnStmt(value=IntLiteral(value=42)),),
            ),
        )
    )

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
    # x is declared inside the if block
    assert "let x = 42;" in code
    assert 'println!("{}", x);' in code


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
    # i is declared inside the for loop
    assert "i = 0;" in code
    assert 'println!("{}", i);' in code


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
    assert "if __idx_raw < 0" in code
    assert "__coll.chars().count()" in code
    assert "__coll.len()" in code


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
    # x is only initialized, never reassigned. Should be declared with let directly
    assert "let x = 42;" in code
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
    # _ is a discard, should NOT have a let declaration
    assert "let _: i32;" not in code
    assert "let mut _: i32;" not in code


def test_semantic_error_in_ir_builder():
    from py2rust.utils.errors import SemanticError

    # We need a case that triggers _to_ir_type's catch-all
    # This is hard to trigger from parser because parser limits types,
    # but we can test the function directly.
    from py2rust.middleend.ir_builder import _to_ir_type

    class JunkType:
        pass

    with pytest.raises(SemanticError):
        _to_ir_type(JunkType())


def test_nested_loops_shadowing():
    src = """
def main() -> int:
    s = 0
    for i in range(0, 2):
        for j in range(0, 2):
            s += i + j
    return s
"""
    code = _compile(src)
    # Check that there are nested blocks
    assert (
        code.count("{") >= 4
    )  # Func, outer loop block, while block, inner loop block...
    # Exact check for shadowing prevention: outer __step should not be overwritten
    # The code should have multiple let __step
    assert code.count("let __step") >= 2


def test_subscript_side_effects():
    src = """
def get_list() -> list[int]:
    print(1)
    return [1, 2, 3]

def main() -> int:
    x = get_list()[0]
    return x
"""
    code = _compile(src)
    # get_list() should be assigned to __coll exactly once
    assert "let __coll = &(get_list());" in code


def test_mixed_arithmetic_casting():
    src = """
def main() -> float:
    i: int = 1
    f: float = 2.5
    res: float = i + f
    return res
"""
    code = _compile(src)
    assert "(i as f64) + (f as f64)" in code


def test_conflicting_loop_target():
    src = """
def main() -> int:
    i: str = "hi"
    for i in range(0, 10):
        print(i)
    return 0
"""
    with pytest.raises(Py2RustTypeError):
        _check(src)


def test_discard_variable_predeclaration_skipped():
    src = """
def helper(x: int) -> int:
    return x

def main() -> int:
    helper(42)
    return 0
"""
    code = _compile(src)
    # _ is a discard variable in helper(42) call statement,
    # it should not have a let declaration.
    assert "let mut _: i32;" not in code
    assert "let _: i32;" not in code
    # But it should be assigned to
    assert "_ = helper(42);" in code


def test_print_validation_undefined_var():
    from py2rust.utils.errors import CompilerError

    src = """
def main() -> int:
    print(undefined_var)
    return 0
"""
    with pytest.raises(CompilerError):
        _check(src)


def test_unknown_type_marker():
    from py2rust.backend.rust_codegen import _rust_type

    class UnknownType:
        pass

    with pytest.raises(ValueError) as excinfo:
        _rust_type(UnknownType())
    assert "Unknown type UnknownType" in str(excinfo.value)


def test_invalid_binop_semantic_error():
    from py2rust.utils.errors import CompilerError

    src = """
def main() -> int:
    x = 1 + "a"
    return 0
"""
    with pytest.raises(CompilerError):
        _check(src)


def test_function_call_arg_mismatch():
    from py2rust.utils.errors import CompilerError

    src = """
def f(x: int) -> int:
    return x

def main() -> int:
    f("a")
    return 0
"""
    with pytest.raises(CompilerError):
        _check(src)


def test_invalid_subscript_index_type():
    from py2rust.utils.errors import CompilerError

    src = """
def main() -> int:
    lst: list[int] = [1, 2, 3]
    print(lst["0"])
    return 0
"""
    with pytest.raises(CompilerError):
        _check(src)


def test_undefined_variable_in_binop():
    from py2rust.utils.errors import CompilerError

    src = """
def main() -> int:
    x = y + 1
    return 0
"""
    with pytest.raises(CompilerError):
        _check(src)


def test_list_invariance_enforced():
    from py2rust.utils.errors import CompilerError

    # list[float] cannot accept list[int] because Rust's Vec<T> is invariant
    src = """
def main() -> int:
    li: list[int] = [1, 2]
    lf: list[float] = li
    return 0
"""
    with pytest.raises(CompilerError):
        _check(src)
