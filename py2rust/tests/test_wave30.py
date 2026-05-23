"""
Wave 30: Python Generator & Iterator Support Tests

Tests that the py2rust compiler correctly compiles:
  - Simple yielding functions to Iterator-implementing state machine structs
  - Generator expressions to boxed chains of into_iter(), map(), filter()
  - Chained iterators using `yield from`
  - Yield functions within loop structures
  - Safety warning comments emitted when complex generator control flows are detected
"""

import pytest
from py2rust.frontend.parser import parse
from py2rust.middleend.ir_builder import build_ir
from py2rust.backend.rust_codegen import generate_rust

def compile_to_rust(src: str) -> str:
    """Helper to run the full compilation pipeline from Python source to Rust."""
    return generate_rust(build_ir(parse(src)))

class TestGeneratorsAndIterators:
    def test_simple_yield_function_to_iterator(self):
        src = """
def gen_numbers() -> Generator[int, None, None]:
    yield 10
    yield 20
    yield 30
"""
        rust_code = compile_to_rust(src)
        
        # Verify state machine struct and fields are generated
        assert "pub struct GenNumbersGenerator" in rust_code
        assert "__state: i32," in rust_code
        
        # Verify Iterator trait implementation
        assert "impl Iterator for GenNumbersGenerator" in rust_code
        assert "type Item = i32;" in rust_code
        
        # Verify that original function returns the boxed generator struct wrapped in a Result
        assert "pub fn gen_numbers() -> Result<Box<dyn Iterator<Item = i32>>, PyError>" in rust_code
        assert "Ok(Box::new(GenNumbersGenerator::new()))" in rust_code

    def test_yield_range_equivalent(self):
        src = """
def custom_range(n: int) -> Generator[int, None, None]:
    for i in range(n):
        yield i
"""
        rust_code = compile_to_rust(src)
        
        # Verify loop iterator initialization and next handling in the generator struct
        assert "pub struct CustomRangeGenerator" in rust_code
        assert any("__for_iter_" in line for line in rust_code.splitlines())
        assert "impl Iterator for CustomRangeGenerator" in rust_code
        assert "iter.next()" in rust_code

    def test_yield_from_chaining(self):
        src = """
def chain_generators(lst: list[int]) -> Generator[int, None, None]:
    yield from lst
"""
        rust_code = compile_to_rust(src)
        
        # Verify delegator state management and iterator chaining
        assert "pub struct ChainGeneratorsGenerator" in rust_code
        assert "__sub_iter: Option<Box<dyn Iterator<Item = i32>>>," in rust_code
        assert "iter.next()" in rust_code or "sub_iter" in rust_code

    def test_generator_expression_to_map_filter(self):
        src = """
def square_evens(numbers: list[int]) -> Generator[int, None, None]:
    return (x * x for x in numbers if x % 2 == 0)
"""
        rust_code = compile_to_rust(src)
        
        # Verify generator expression lowers to map/filter chains in Rust
        assert ".filter" in rust_code
        assert ".map" in rust_code
        assert "Box::new" in rust_code

    def test_complex_generator_warns_partial(self):
        src = """
def complex_gen(n: int) -> Generator[int, None, None]:
    while n > 0:
        yield n
        n -= 1
        if n == 5:
            break
"""
        rust_code = compile_to_rust(src)
        
        # Verify warning comment is correctly emitted due to complex flow inside generator
        assert "// WARNING: Generator contains complex control flow" in rust_code
