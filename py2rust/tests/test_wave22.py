"""
Test wave 22:
Advanced Dunder mapping (Add, Sub, Mul, PartialEq, PartialOrd).
"""

import pytest
from py2rust.frontend.parser import parse
from py2rust.middleend.ir_builder import build_ir
from py2rust.backend.rust_codegen import generate_rust

def _compile(src):
    return generate_rust(build_ir(parse(src)))

def test_dunder_add():
    src = """
class Point:
    x: int = 0
    y: int = 0
    def __init__(self, x: int, y: int) -> None:
        self.x = x
        self.y = y
    def __add__(self, other: "Point") -> "Point":
        return Point(self.x + other.x, self.y + other.y)

def test() -> None:
    p1 = Point(1, 2)
    p2 = Point(3, 4)
    p3 = p1 + p2
"""
    code = _compile(src)
    assert "impl std::ops::Add<Point> for Point" in code
    assert "fn add(self, rhs: Point) -> Self::Output {" in code
    # Check for cloning to satisfy borrow checker
    assert "p1.clone() + p2.clone()" in code

def test_dunder_eq():
    src = """
class Point:
    x: int = 0
    def __eq__(self, other: "Point") -> bool:
        return self.x == other.x
"""
    code = _compile(src)
    assert "impl PartialEq<Point> for Point" in code
    assert "self.__eq__(other.clone()).unwrap_or(false)" in code

def test_dunder_lt():
    src = """
class Point:
    x: int = 0
    def __lt__(self, other: "Point") -> bool:
        return self.x < other.x
"""
    code = _compile(src)
    assert "impl PartialOrd<Point> for Point" in code
    assert "fn partial_cmp(&self, other: &Point) -> Option<std::cmp::Ordering>" in code

def test_dunder_mul_scalar():
    src = """
class Point:
    x: int = 0
    y: int = 0
    def __mul__(self, factor: int) -> "Point":
        return Point(self.x * factor, self.y * factor)
"""
    code = _compile(src)
    assert "impl std::ops::Mul<i32> for Point" in code

def test_dunder_hash():
    src = """
class Point:
    x: int = 0
    def __hash__(self) -> int:
        return self.x
"""
    code = _compile(src)
    assert "impl std::hash::Hash for Point" in code
    assert "let h = self.__hash__().unwrap_or(0);" in code

def test_dunder_indexing():
    src = """
class Container:
    items: list[int] = [0, 0, 0]
    def __getitem__(self, idx: int) -> int:
        return self.items[idx]
    def __setitem__(self, idx: int, val: int) -> None:
        self.items[idx] = val

def test() -> None:
    c = Container()
    x = c[0]
    c[1] = 10
"""
    code = _compile(src)
    assert "c.__getitem__(0)?" in code
    assert "c.__setitem__(1, 10)?;" in code
