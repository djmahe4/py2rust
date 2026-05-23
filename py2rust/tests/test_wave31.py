"""
Wave 31: Comprehension Expansion Tests

Verifies that the py2rust compiler correctly compiles:
  - Simple list comprehensions
  - List comprehensions with filters/conditions
  - Dictionary comprehensions with key/value mapping
  - Set comprehensions
  - Nested comprehensions (multi-generator loop structures)
  - Tuple target unpacking destructuring within comprehensions
"""

import pytest
from py2rust.frontend.parser import parse
from py2rust.middleend.ir_builder import build_ir
from py2rust.backend.rust_codegen import generate_rust

def compile_to_rust(src: str) -> str:
    """Helper to run the full compilation pipeline from Python source to Rust."""
    return generate_rust(build_ir(parse(src)))

class TestComprehensionExpansion:
    def test_list_comp_simple(self):
        src = """
def double_list(lst: list[int]) -> list[int]:
    return [x * 2 for x in lst]
"""
        rust_code = compile_to_rust(src)
        
        # Verify the creation of intermediate variable and vector creation
        assert "let mut __res = Vec::<i32>::new();" in rust_code
        # Verify the owned into_iter iterator
        assert ".clone().into_iter()" in rust_code
        # Verify the push code inside loop
        assert "__res.push(" in rust_code

    def test_list_comp_with_condition(self):
        src = """
def positive_list(lst: list[int]) -> list[int]:
    return [x for x in lst if x > 0]
"""
        rust_code = compile_to_rust(src)
        
        # Verify nested loops and condition checks
        assert "let mut __res = Vec::<i32>::new();" in rust_code
        assert "if x > 0" in rust_code

    def test_dict_comp(self):
        src = """
def pair_to_dict(pairs: list[tuple[str, int]]) -> dict[str, int]:
    return {k: v for k, v in pairs}
"""
        rust_code = compile_to_rust(src)
        
        # Verify standard library HashMap and key/value types are parsed/generated
        assert "let mut __res = HashMap::<String, i32>::new();" in rust_code
        assert "__res.insert(" in rust_code

    def test_set_comp(self):
        src = """
def unique_elements(lst: list[int]) -> set[int]:
    return {x for x in lst}
"""
        rust_code = compile_to_rust(src)
        
        # Verify HashSet structure
        assert "let mut __res = HashSet::<i32>::new();" in rust_code
        assert "__res.insert(" in rust_code

    def test_nested_list_comp(self):
        src = """
def nested_add(lst1: list[int], lst2: list[int]) -> list[int]:
    return [x + y for x in lst1 for y in lst2]
"""
        rust_code = compile_to_rust(src)
        
        # Verify that multiple loops nested inside each other are emitted
        assert "for __tmp in lst1.clone().into_iter()" in rust_code
        assert "for __tmp in lst2.clone().into_iter()" in rust_code

    def test_tuple_target_unpacking(self):
        src = """
def sum_tuples(tuple_list: list[tuple[int, int]]) -> list[int]:
    return [a + b for a, b in tuple_list]
"""
        rust_code = compile_to_rust(src)
        
        # Verify the unpacking binding is present in loop definition
        assert "let (a, b) = __tmp;" in rust_code
