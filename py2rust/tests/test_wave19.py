"""
Test wave 19:
Tests for f-strings, protocols, and capitalized typing aliases.
"""

import pytest
from py2rust.frontend.parser import parse
from py2rust.middleend.ir_builder import build_ir
from py2rust.backend.rust_codegen import generate_rust

def _compile(src):
    return generate_rust(build_ir(parse(src)))

def test_fstring_simple():
    src = """
def greet(name: str) -> str:
    return f"Hello, {name}!"
"""
    code = _compile(src)
    assert 'format!("Hello, {}!", name)' in code

def test_fstring_with_repr():
    src = """
def debug_val(val: int) -> str:
    return f"Value: {val!r}"
"""
    code = _compile(src)
    # !r should map to {:?} in Rust format string
    assert 'format!("Value: {:?}", val)' in code

def test_fstring_with_spec():
    src = """
def format_float(val: float) -> str:
    return f"Val: {val:.2f}"
"""
    code = _compile(src)
    assert 'format!("Val: {:.2f}", val)' in code

def test_protocol_discovery():
    src = """
from typing import Protocol

class Drawable(Protocol):
    def draw(self) -> str:
        ...

class Circle:
    def __init__(self, radius: int) -> None:
        self.radius = radius
    def draw(self) -> str:
        return f"Circle({self.radius})"

def render(item: Drawable) -> None:
    print(item.draw())
"""
    code = _compile(src)
    assert "pub trait Drawable {" in code
    assert "fn draw(&self) -> Result<String, PyError>;" in code
    assert "impl Drawable for Circle {" in code
    assert 'fn render(item: &dyn Drawable) -> Result<(), PyError> {' in code

def test_capitalized_typing_aliases():
    src = """
from typing import List, Dict, Tuple, Set

def process(items: List[int], mapping: Dict[str, float]) -> None:
    pass
"""
    code = _compile(src)
    assert "fn process(items: Vec<i32>, mapping: HashMap<String, f64>) -> Result<(), PyError> {" in code
