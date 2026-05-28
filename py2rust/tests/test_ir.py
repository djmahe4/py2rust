import pytest
from py2rust.frontend.parser import parse
from py2rust.middleend.ir_builder import build_ir
from py2rust.ir.ir_nodes import (
    IRModule, IRFunction, IRIntType, IRFloatType, IRBoolType,
    IRVarDecl, IRReturn, IRBinOp, IRIntLit, IRFloatLit, IRName,
    IRIf, IRWhile, IRForRange, IRPrint, IRAugAssign, IRFunctionCall,
)


def _build(src):
    return build_ir(parse(src))


def test_ir_module_structure():
    src = """
def f() -> int:
    return 0
"""
    ir = _build(src)
    assert isinstance(ir, IRModule)
    assert len(ir.functions) == 1


def test_ir_function_params():
    src = """
def add(x: int, y: int) -> int:
    return x + y
"""
    ir = _build(src)
    f = ir.functions[0]
    assert f.name == "add"
    assert len(f.params) == 2
    assert f.params[0].name == "x"
    assert isinstance(f.params[0].type_, IRIntType)
    assert isinstance(f.return_type, IRIntType)


def test_ir_var_decl():
    src = """
def f() -> int:
    x: int = 42
    return x
"""
    ir = _build(src)
    stmt = ir.functions[0].body[0]
    assert isinstance(stmt, IRVarDecl)
    assert stmt.name == "x"
    assert isinstance(stmt.type_, IRIntType)
    assert isinstance(stmt.value, IRIntLit)
    assert stmt.value.value == 42


def test_ir_float_type():
    src = """
def f() -> float:
    x: float = 3.14
    return x
"""
    ir = _build(src)
    stmt = ir.functions[0].body[0]
    assert isinstance(stmt, IRVarDecl)
    assert isinstance(stmt.type_, IRFloatType)
    assert isinstance(stmt.value, IRFloatLit)


def test_ir_int_to_float_promotion():
    src = """
def f() -> float:
    x: float = 42
    return x
"""
    ir = _build(src)
    stmt = ir.functions[0].body[0]
    assert isinstance(stmt.value, IRFloatLit)
    assert stmt.value.value == 42.0


def test_ir_binop():
    src = """
def f() -> int:
    return 1 + 2
"""
    ir = _build(src)
    ret = ir.functions[0].body[0]
    assert isinstance(ret, IRReturn)
    assert isinstance(ret.value, IRBinOp)
    assert ret.value.op == '+'


def test_ir_float_division():
    src = """
def f() -> float:
    return 10 / 3
"""
    ir = _build(src)
    ret = ir.functions[0].body[0]
    assert isinstance(ret.value, IRBinOp)
    assert ret.value.op == '/'
    assert isinstance(ret.value.result_type, IRFloatType)


def test_ir_if():
    src = """
def f(x: int) -> int:
    if x > 0:
        return x
    else:
        return 0
"""
    ir = _build(src)
    stmt = ir.functions[0].body[0]
    assert isinstance(stmt, IRIf)
    assert len(stmt.then_body) == 1
    assert stmt.else_body is not None


def test_ir_while():
    src = """
def f() -> int:
    x: int = 0
    while x < 10:
        x += 1
    return x
"""
    ir = _build(src)
    stmt = ir.functions[0].body[1]
    assert isinstance(stmt, IRWhile)


def test_ir_for_range():
    src = """
def f() -> int:
    s: int = 0
    for i in range(0, 10):
        s += i
    return s
"""
    ir = _build(src)
    stmt = ir.functions[0].body[1]
    assert isinstance(stmt, IRForRange)
    assert stmt.target == IRName(name="i")
    assert stmt.step is None


def test_ir_for_range_step():
    src = """
def f() -> int:
    s: int = 0
    for i in range(0, 10, 2):
        s += i
    return s
"""
    ir = _build(src)
    stmt = ir.functions[0].body[1]
    assert isinstance(stmt, IRForRange)
    assert stmt.step is not None


def test_ir_print():
    src = """
def f() -> int:
    print(42)
    return 0
"""
    ir = _build(src)
    stmt = ir.functions[0].body[0]
    assert isinstance(stmt, IRPrint)


def test_ir_function_call():
    src = """
def add(x: int, y: int) -> int:
    return x + y

def main() -> int:
    result: int = add(1, 2)
    return result
"""
    ir = _build(src)
    main_f = ir.functions[1]
    stmt = main_f.body[0]
    assert isinstance(stmt, IRVarDecl)
    assert isinstance(stmt.value, IRFunctionCall)
    assert stmt.value.name == "add"
