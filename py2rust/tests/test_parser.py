import pytest
from py2rust.frontend.parser import parse
from py2rust.frontend.ast_nodes import (
    Module,
    FunctionDef,
    Param,
    ReturnStmt,
    VarDecl,
    Assign,
    IntLiteral,
    FloatLiteral,
    BoolLiteral,
    StrLiteral,
    Name,
    BinOp,
    IntType,
    FloatType,
    BoolType,
    StrType,
    ListType,
    IfStmt,
    WhileStmt,
    ForRange,
    PrintStmt,
    AugAssign,
)
from py2rust.utils.errors import ParseError, UnsupportedFeatureError


def test_parse_simple_function():
    src = """
def add(x: int, y: int) -> int:
    return x + y
"""
    m = parse(src)
    assert len(m.functions) == 1
    f = m.functions[0]
    assert f.name == "add"
    assert len(f.params) == 2
    assert f.params[0].name == "x"
    assert isinstance(f.params[0].type_annotation, IntType)
    assert f.params[1].name == "y"
    assert isinstance(f.return_type, IntType)
    assert len(f.body) == 1
    r = f.body[0]
    assert isinstance(r, ReturnStmt)
    assert isinstance(r.value, BinOp)
    assert r.value.op == "+"


def test_parse_float_type():
    src = """
def area(r: float) -> float:
    return r * r
"""
    m = parse(src)
    f = m.functions[0]
    assert isinstance(f.params[0].type_annotation, FloatType)
    assert isinstance(f.return_type, FloatType)


def test_parse_bool_type():
    src = """
def check(x: bool) -> bool:
    return x
"""
    m = parse(src)
    f = m.functions[0]
    assert isinstance(f.params[0].type_annotation, BoolType)


def test_parse_str_type():
    src = """
def greet(name: str) -> str:
    return name
"""
    m = parse(src)
    f = m.functions[0]
    assert isinstance(f.params[0].type_annotation, StrType)


def test_parse_list_type():
    src = """
def sum_list(lst: list[int]) -> int:
    return lst[0]
"""
    m = parse(src)
    f = m.functions[0]
    ann = f.params[0].type_annotation
    assert isinstance(ann, ListType)
    assert isinstance(ann.element_type, IntType)


def test_parse_var_decl():
    src = """
def f() -> int:
    x: int = 42
    return x
"""
    m = parse(src)
    f = m.functions[0]
    stmt = f.body[0]
    assert isinstance(stmt, VarDecl)
    assert stmt.name == "x"
    assert isinstance(stmt.type_annotation, IntType)
    assert isinstance(stmt.value, IntLiteral)
    assert stmt.value.value == 42


def test_parse_assign():
    src = """
def f() -> int:
    x = 10
    return x
"""
    m = parse(src)
    stmt = m.functions[0].body[0]
    assert isinstance(stmt, Assign)
    assert stmt.target == "x"


def test_parse_aug_assign():
    src = """
def f() -> int:
    x: int = 0
    x += 1
    return x
"""
    m = parse(src)
    stmt = m.functions[0].body[1]
    assert isinstance(stmt, AugAssign)
    assert stmt.target == "x"
    assert stmt.op == "+="


def test_parse_if_stmt():
    src = """
def f(x: int) -> int:
    if x > 0:
        return x
    else:
        return 0
"""
    m = parse(src)
    stmt = m.functions[0].body[0]
    assert isinstance(stmt, IfStmt)
    assert stmt.else_body is not None
    assert len(stmt.then_body) == 1
    assert len(stmt.else_body) == 1


def test_parse_elif():
    src = """
def f(x: int) -> int:
    if x > 0:
        return 1
    elif x < 0:
        return -1
    else:
        return 0
"""
    m = parse(src)
    stmt = m.functions[0].body[0]
    assert isinstance(stmt, IfStmt)
    assert len(stmt.elif_clauses) == 1


def test_parse_while():
    src = """
def f() -> int:
    x: int = 0
    while x < 10:
        x += 1
    return x
"""
    m = parse(src)
    stmt = m.functions[0].body[1]
    assert isinstance(stmt, WhileStmt)


def test_parse_for_range():
    src = """
def f() -> int:
    s: int = 0
    for i in range(0, 10):
        s += i
    return s
"""
    m = parse(src)
    stmt = m.functions[0].body[1]
    assert isinstance(stmt, ForRange)
    assert stmt.target == "i"
    assert stmt.step is None


def test_parse_for_range_step():
    src = """
def f() -> int:
    s: int = 0
    for i in range(0, 10, 2):
        s += i
    return s
"""
    m = parse(src)
    stmt = m.functions[0].body[1]
    assert isinstance(stmt, ForRange)
    assert stmt.step is not None


def test_parse_print():
    src = """
def f() -> int:
    print(42)
    return 0
"""
    m = parse(src)
    stmt = m.functions[0].body[0]
    assert isinstance(stmt, PrintStmt)


def test_parse_bool_literals():
    src = """
def f() -> bool:
    return True
"""
    m = parse(src)
    r = m.functions[0].body[0]
    assert isinstance(r.value, BoolLiteral)
    assert r.value.value is True


def test_parse_missing_param_annotation():
    src = """
def f(x) -> int:
    return x
"""
    with pytest.raises(UnsupportedFeatureError):
        parse(src)


def test_parse_missing_return_annotation():
    src = """
def f(x: int):
    return x
"""
    with pytest.raises(UnsupportedFeatureError):
        parse(src)


def test_parse_class_rejected():
    src = """
class Foo:
    x: int = 1
"""
    m = parse(src)
    assert len(m.classes) == 1
    assert m.classes[0].name == "Foo"


def test_parse_import_rejected():
    src = """
import os
"""
    with pytest.raises(UnsupportedFeatureError):
        parse(src)


def test_parse_lambda_rejected():
    src = """
def f() -> int:
    g = lambda x: x
    return 0
"""
    with pytest.raises(UnsupportedFeatureError):
        parse(src)


def test_parse_comprehension_rejected():
    src = """
def f() -> int:
    x = [i for i in range(0, 10)]
    return 0
"""
    with pytest.raises(UnsupportedFeatureError):
        parse(src)





def test_parse_eval_rejected():
    src = """
def f() -> int:
    x = eval("1+2")
    return 0
"""
    with pytest.raises(UnsupportedFeatureError):
        parse(src)


def test_parse_syntax_error():
    src = "def f( -> int: return 0"
    with pytest.raises(ParseError):
        parse(src)


def test_parse_multiple_functions():
    src = """
def add(x: int, y: int) -> int:
    return x + y

def main() -> int:
    result: int = add(3, 4)
    return result
"""
    m = parse(src)
    assert len(m.functions) == 2
    assert m.functions[0].name == "add"
    assert m.functions[1].name == "main"
