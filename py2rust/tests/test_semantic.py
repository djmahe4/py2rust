import pytest
from py2rust.frontend.parser import parse
from py2rust.middleend.symbol_table import SymbolTable
from py2rust.middleend.type_checker import TypeChecker
from py2rust.middleend.ir_builder import build_ir
from py2rust.frontend.ast_nodes import IntType, FloatType, BoolType
from py2rust.utils.errors import Py2RustTypeError, SemanticError


def _check(src):
    m = parse(src)
    st = SymbolTable()
    tc = TypeChecker(st)
    tc.check_module(m)
    return m, st


def test_type_check_simple():
    src = """
def f(x: int) -> int:
    return x
"""
    _check(src)  # should not raise


def test_type_check_var_decl_ok():
    src = """
def f() -> int:
    x: int = 42
    return x
"""
    _check(src)


def test_type_check_var_decl_mismatch():
    src = """
def f() -> int:
    x: int = 3.14
    return 0
"""
    with pytest.raises(Py2RustTypeError):
        _check(src)


def test_type_check_float_accepts_int():
    src = """
def f() -> float:
    x: float = 42
    return x
"""
    _check(src)  # int literal is compatible with float


def test_symbol_table_define_lookup():
    st = SymbolTable()
    st.define("x", IntType())
    t = st.lookup("x")
    assert isinstance(t, IntType)


def test_symbol_table_scope():
    st = SymbolTable()
    st.define("x", IntType())
    st.enter_scope("func")
    st.define("y", FloatType())
    assert st.lookup("x") is not None  # visible from parent
    assert st.lookup("y") is not None
    st.exit_scope()
    assert st.lookup("y") is None  # no longer in scope
    assert st.lookup("x") is not None


def test_symbol_table_function():
    st = SymbolTable()
    st.define_function("add", [IntType(), IntType()], IntType())
    sig = st.lookup_function("add")
    assert sig is not None
    param_types, ret, is_async, _ = sig
    assert len(param_types) == 2
    assert isinstance(ret, IntType)


def test_undefined_variable_in_aug_assign():
    src = """
def f() -> int:
    x += 1
    return 0
"""
    with pytest.raises((Py2RustTypeError, SemanticError)):
        _check(src)


def test_for_loop_defines_variable():
    src = """
def f() -> int:
    s: int = 0
    for i in range(0, 5):
        s += i
    return s
"""
    _check(src)  # should not raise


def test_build_ir_simple():
    src = """
def add(x: int, y: int) -> int:
    return x + y
"""
    m = parse(src)
    ir = build_ir(m)
    assert len(ir.functions) == 1
    assert ir.functions[0].name == "add"


def test_build_ir_undefined_function():
    src = """
def f() -> int:
    return unknown_func(1)
"""
    m = parse(src)
    with pytest.raises(SemanticError):
        build_ir(m)
