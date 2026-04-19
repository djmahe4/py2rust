import pytest
from py2rust.frontend.parser import parse
from py2rust.middleend.ir_builder import build_ir
from py2rust.backend.rust_codegen import generate_rust
from py2rust.config import CompilerConfig

def _compile(src, mock_mode=False):
    config = CompilerConfig(mock_mode=mock_mode)
    return generate_rust(build_ir(parse(src), config=config))

def test_import_as_aliasing():
    src = """
import math as m
def f() -> float:
    return m.sqrt(16.0)
"""
    code = _compile(src, mock_mode=True)
    # math is an ExternalObject. 
    # m.sqrt(16.0) should generate call_method("sqrt", (16.0,)) on the math ExternalObject
    assert 'ExternalObject::load_module("math")?.call_method("sqrt", (16.0,))?' in code

def test_from_import_as_aliasing():
    src = """
from math import sqrt as s
def f() -> float:
    return s(16.0)
"""
    code = _compile(src, mock_mode=True)
    # s is sqrt from math.
    assert 'ExternalObject::from_module("math", "sqrt").call((16.0,))?' in code

def test_print_multi_args():
    src = """
def f() -> None:
    a = 1
    b = 2.0
    print(a, b, "hello")
"""
    code = _compile(src)
    assert 'println!("{} {} {}", a, b, "hello".to_string());' in code

def test_print_sep_end():
    src = """
def f() -> None:
    print(1, 2, sep="|", end="!!!")
"""
    code = _compile(src)
    assert 'print!("{}", 1);' in code
    assert 'print!("{}", "|".to_string());' in code
    assert 'print!("{}", 2);' in code
    assert 'print!("{}", "!!!".to_string());' in code

def test_assert_with_message_expression():
    src = """
def f(x: int) -> None:
    assert x > 0, f"x must be positive, got {x}"
"""
    code = _compile(src)
    # fstng should be handled by gen_expr
    assert 'assert!(x > 0, "{}", format!("x must be positive, got {}", x));' in code

def test_with_multiple_items_mut():
    src = """
def f() -> None:
    with open("a.txt", "r") as f1, open("b.txt", "w") as f2:
        f2.write(f1.read())
"""
    code = _compile(src)
    assert 'let mut f1' in code
    assert 'let mut f2' in code
    assert 'f2.write(&f1.read()?)' in code

def test_global_warning():
    src = """
def f() -> None:
    global x
    x = 1
"""
    code = _compile(src)
    assert '// WARNING: Python \'global\'' in code

def test_with_nested_reassignment():
    src = """
def f() -> None:
    with open("a.txt", "r") as f:
        f = open("b.txt", "r") # re-assignment
        with f as f2:
            print(f2.read())
"""
    code = _compile(src)
    # The variable 'f' should be mut because of re-assignment
    assert 'let mut f' in code
    # The nested 'with' uses 'f'
    assert 'let mut f2' in code

def test_complex_import_aliasing():
    src = """
import math as m
from collections import deque as dq
import os.path as p

def f() -> None:
    x = m.sqrt(dq([1, 2]).pop())
    y = p.join("a", "b")
"""
    code = _compile(src, mock_mode=True)
    assert 'ExternalObject::load_module("math")?' in code
    assert 'ExternalObject::from_module("collections", "deque")' in code
    assert 'ExternalObject::load_module("os.path")?' in code
    assert 'call_method("join", ("a".to_string(), "b".to_string(),))' in code
