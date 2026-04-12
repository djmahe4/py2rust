import pytest
from py2rust.frontend.parser import parse
from py2rust.middleend.ir_builder import build_ir
from py2rust.backend.rust_codegen import generate_rust


def _compile(src):
    return generate_rust(build_ir(parse(src)))


def test_codegen_simple_function():
    src = """
def add(x: int, y: int) -> int:
    return x + y
"""
    code = _compile(src)
    assert "fn add(x: i32, y: i32) -> i32 {" in code
    assert "return x + y;" in code


def test_codegen_main_function():
    src = """
def add(x: int, y: int) -> int:
    return x + y

def main() -> int:
    result: int = add(3, 4)
    print(result)
    return 0
"""
    code = _compile(src)
    assert "fn add(x: i32, y: i32) -> i32 {" in code
    # Rust's main() can return i32 for exit code
    assert "fn main() -> i32 {" in code
    assert "result = add(3, 4);" in code
    assert 'println!("{}", result);' in code
    # return value is preserved
    assert "return 0;" in code


def test_codegen_float_division():
    src = """
def f() -> float:
    return 10 / 3
"""
    code = _compile(src)
    # Should generate float division
    assert "f64" in code
    assert "/" in code


def test_codegen_integer_floor_division():
    src = """
def f(a: int, b: int) -> int:
    return a // b
"""
    code = _compile(src)
    # Python floor division: (a as f64 / b as f64).floor() as i32
    assert ".floor() as i32" in code


def test_codegen_var_decl_types():
    src = """
def f() -> int:
    x: int = 1
    y: float = 2.0
    z: bool = True
    return x
"""
    code = _compile(src)
    assert "x = 1;" in code
    assert "y = 2.0;" in code
    assert "z = true;" in code


def test_codegen_if_else():
    src = """
def abs_val(x: int) -> int:
    if x < 0:
        return -x
    else:
        return x
"""
    code = _compile(src)
    assert "if x < 0 {" in code
    assert "} else {" in code


def test_codegen_while_loop():
    src = """
def f() -> int:
    x: int = 0
    while x < 10:
        x += 1
    return x
"""
    code = _compile(src)
    assert "while x < 10 {" in code
    assert "x += 1;" in code


def test_codegen_for_range():
    src = """
def f() -> int:
    s: int = 0
    for i in range(0, 10):
        s += i
    return s
"""
    code = _compile(src)
    assert "i = 0;" in code
    assert "while if (__step) > 0 { i < (__stop) } else { i > (__stop) } {" in code


def test_codegen_for_range_step():
    src = """
def f() -> int:
    s: int = 0
    for i in range(0, 10, 2):
        s += i
    return s
"""
    code = _compile(src)
    assert "let __stop = 10;" in code
    assert "while if (__step) > 0 { i < (__stop) } else { i > (__stop) } {" in code


def test_codegen_bool_ops():
    src = """
def f(a: bool, b: bool) -> bool:
    return a and b
"""
    code = _compile(src)
    assert "a && b" in code


def test_codegen_or_op():
    src = """
def f(a: bool, b: bool) -> bool:
    return a or b
"""
    code = _compile(src)
    assert "||" in code


def test_codegen_not_op():
    src = """
def f(a: bool) -> bool:
    return not a
"""
    code = _compile(src)
    assert "!" in code


def test_codegen_list_type():
    src = """
def f() -> int:
    lst: list[int] = [1, 2, 3]
    return lst[0]
"""
    code = _compile(src)
    assert "vec![1, 2, 3]" in code
    assert "let lst" in code


def test_codegen_empty_list():
    src = """
def f() -> int:
    lst: list[int] = []
    return 0
"""
    code = _compile(src)
    assert "Vec::<i32>::new()" in code


def test_codegen_str_type():
    src = """
def f() -> str:
    s: str = "hello"
    return s
"""
    code = _compile(src)
    assert "String" in code
    assert '"hello".to_string()' in code


def test_codegen_print_stmt():
    src = """
def f() -> int:
    print(42)
    return 0
"""
    code = _compile(src)
    assert 'println!("{}", 42);' in code


def test_codegen_fibonacci():
    src = """
def fib(n: int) -> int:
    if n <= 1:
        return n
    a: int = 0
    b: int = 1
    i: int = 2
    while i <= n:
        temp: int = a + b
        a = b
        b = temp
        i += 1
    return b
"""
    code = _compile(src)
    assert "fn fib(n: i32) -> i32 {" in code
    assert "while i <= n {" in code
