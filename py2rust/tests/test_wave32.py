"""
Wave 32: Functional Primitives & Lambda Tests

Verifies that the py2rust compiler correctly compiles:
  - First-class lambda functions translated to Rust closures.
  - Built-in map() lowered to IRMap and compiled to Iterator pipelines.
  - Built-in filter() lowered to IRFilter and compiled to Iterator pipelines.
  - Built-in sorted() lowered to IRSorted and compiled to sort/sort_by_key.
  - Built-in reduce() lowered to IRReduce and compiled to fold/reduce.
  - Nested functional primitives (e.g. map inside filter).
"""

import pytest
from py2rust.frontend.parser import parse
from py2rust.middleend.ir_builder import build_ir
from py2rust.backend.rust_codegen import generate_rust

from py2rust.config import CompilerConfig

def compile_to_rust(src: str) -> str:
    """Helper to run the full compilation pipeline from Python source to Rust."""
    cfg = CompilerConfig(mock_mode=True)
    return generate_rust(build_ir(parse(src), config=cfg))

class TestFunctionalPrimitives:
    def test_map_lambda(self):
        src = """
def scale_elements(lst: list[int]) -> list[int]:
    return list(map(lambda x: x * 2, lst))
"""
        rust_code = compile_to_rust(src)
        assert ".map(|x|" in rust_code
        assert ".collect::<Vec<_>>()" in rust_code

    def test_map_function(self):
        src = """
def double(x: int) -> int:
    return x * 2

def scale_elements(lst: list[int]) -> list[int]:
    return list(map(double, lst))
"""
        rust_code = compile_to_rust(src)
        assert ".map(|x| (double)(x).unwrap())" in rust_code
        assert ".collect::<Vec<_>>()" in rust_code

    def test_filter_lambda(self):
        src = """
def even_elements(lst: list[int]) -> list[int]:
    return list(filter(lambda x: x % 2 == 0, lst))
"""
        rust_code = compile_to_rust(src)
        assert ".filter(move |__x|" in rust_code
        assert ".collect::<Vec<_>>()" in rust_code

    def test_filter_function(self):
        src = """
def is_even(x: int) -> bool:
    return x % 2 == 0

def even_elements(lst: list[int]) -> list[int]:
    return list(filter(is_even, lst))
"""
        rust_code = compile_to_rust(src)
        assert ".filter(move |__x| { let x = __x.clone(); (is_even)(x).unwrap() })" in rust_code
        assert ".collect::<Vec<_>>()" in rust_code

    def test_sorted_simple(self):
        src = """
def sort_elements(lst: list[int]) -> list[int]:
    return sorted(lst)
"""
        rust_code = compile_to_rust(src)
        assert "let mut __tmp =" in rust_code
        assert ".sort();" in rust_code

    def test_sorted_key_lambda(self):
        src = """
def sort_elements(lst: list[int]) -> list[int]:
    return sorted(lst, key=lambda x: -x)
"""
        rust_code = compile_to_rust(src)
        assert ".sort_by_key(|__x|" in rust_code

    def test_sorted_key_function(self):
        src = """
def negate(x: int) -> int:
    return -x

def sort_elements(lst: list[int]) -> list[int]:
    return sorted(lst, key=negate)
"""
        rust_code = compile_to_rust(src)
        assert ".sort_by_key(|__x| { let x = __x.clone(); (negate)(x).unwrap() })" in rust_code

    def test_reduce_simple(self):
        src = """
from functools import reduce

def sum_elements(lst: list[int]) -> int:
    return reduce(lambda x, y: x + y, lst)
"""
        rust_code = compile_to_rust(src)
        assert ".reduce(|x, y|" in rust_code

    def test_reduce_initial(self):
        src = """
from functools import reduce

def sum_elements(lst: list[int]) -> int:
    return reduce(lambda x, y: x + y, lst, 0)
"""
        rust_code = compile_to_rust(src)
        assert ".fold(0," in rust_code

    def test_nested_map_filter(self):
        src = """
def double_evens(lst: list[int]) -> list[int]:
    return list(map(lambda x: x * 2, filter(lambda x: x % 2 == 0, lst)))
"""
        rust_code = compile_to_rust(src)
        assert ".filter(" in rust_code
        assert ".map(" in rust_code
        assert ".collect::<Vec<_>>()" in rust_code
