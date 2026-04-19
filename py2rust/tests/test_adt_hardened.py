import pytest
from py2rust.frontend.parser import parse
from py2rust.middleend.ir_builder import build_ir
from py2rust.backend.rust_codegen import generate_rust

def _compile(src):
    return generate_rust(build_ir(parse(src)))

def test_optional_implicit_wrapping():
    src = """
from typing import Optional

def f(x: Optional[int]) -> int:
    if x is not None:
        return x
    return 0

def test() -> int:
    return f(10)
"""
    code = _compile(src)
    # The call f(10) should be wrapped in Some(10)
    assert "f(Some(10))?" in code

def test_optional_none_init():
    src = """
from typing import Optional

def test() -> None:
    x: Optional[int] = None
    y: Optional[str] = None
"""
    code = _compile(src)
    assert "let x: Option<i32> = None;" in code
    assert "let y: Option<String> = None;" in code

def test_isinstance_union():
    src = """
from typing import Union

def check(x: Union[int, str]) -> bool:
    if isinstance(x, int):
        return True
    return False
"""
    code = _compile(src)
    # Should use matches! on the generated enum
    # The enum name is generated based on variants: StrOrIntUnion
    assert "matches!(x, StrOrIntUnion::Int(_))" in code

def test_isinstance_none():
    src = """
from typing import Optional, Any

def is_none(x: Optional[int]) -> bool:
    return isinstance(x, type(None))
"""
    code = _compile(src)
    assert "x.is_none()" in code

def test_isinstance_optional_some():
    src = """
from typing import Optional

def is_int(x: Optional[int]) -> bool:
    return isinstance(x, int)
"""
    code = _compile(src)
    # isinstance(x, int) where x is Option<i32> should be x.is_some()
    assert "x.is_some()" in code

def test_isinstance_list():
    src = """
def is_list(x: list[int]) -> bool:
    return isinstance(x, list)
"""
    code = _compile(src)
    assert "true" in code # Compile-time known for now if types match

if __name__ == "__main__":
    pytest.main([__file__])
