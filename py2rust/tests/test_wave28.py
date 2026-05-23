"""
Wave 28: Decorator Support Tests

Tests that the py2rust compiler correctly handles Python decorators:
  - @staticmethod: desugared to a Rust associated function (no self receiver)
  - @classmethod: desugared (cls stripped, method compiled normally)
  - @dataclass: accepted on classes, stored in decorator_list
  - @property, @abstractmethod, @override: silently accepted
  - Unknown decorators: rejected with UnsupportedFeatureError
"""

import pytest
from py2rust.frontend.parser import Parser, parse
from py2rust.frontend.ast_nodes import FunctionDef, ClassDef
from py2rust.utils.errors import UnsupportedFeatureError
from py2rust.middleend.ir_builder import build_ir
from py2rust.backend.rust_codegen import generate_rust


def compile_to_rust(src: str) -> str:
    """Helper: parse -> build IR -> emit Rust (mirrors test_codegen.py pattern)."""
    return generate_rust(build_ir(parse(src)))


# ---------------------------------------------------------------------------
# Parser-level tests
# ---------------------------------------------------------------------------

class TestDecoratorParsing:
    """Ensure the parser correctly collects and desugars decorators."""

    def test_staticmethod_sets_flag(self):
        src = """
class MyClass:
    @staticmethod
    def create(x: int) -> int:
        return x
"""
        mod = Parser(src).parse()
        cls = mod.classes[0]
        method = next(m for m in cls.body if isinstance(m, FunctionDef))
        assert method.is_static is True
        assert method.is_classmethod is False
        # 'self' should NOT be in params (was stripped during desugaring)
        param_names = [p.name for p in method.params]
        assert "self" not in param_names
        assert "x" in param_names

    def test_classmethod_sets_flag(self):
        src = """
class MyClass:
    @classmethod
    def from_string(cls, s: str) -> int:
        return 0
"""
        mod = Parser(src).parse()
        cls = mod.classes[0]
        method = next(m for m in cls.body if isinstance(m, FunctionDef))
        assert method.is_classmethod is True
        assert method.is_static is False
        # 'cls' should NOT be in params (was stripped during desugaring)
        param_names = [p.name for p in method.params]
        assert "cls" not in param_names
        assert "s" in param_names

    def test_staticmethod_no_params(self):
        src = """
class MyClass:
    @staticmethod
    def zero() -> int:
        return 0
"""
        mod = Parser(src).parse()
        cls = mod.classes[0]
        method = next(m for m in cls.body if isinstance(m, FunctionDef))
        assert method.is_static is True
        assert list(method.params) == []

    def test_dataclass_decorator_on_class(self):
        src = """
@dataclass
class Point:
    def __init__(self, x: int, y: int) -> None:
        self.x = x
        self.y = y
"""
        mod = Parser(src).parse()
        cls = mod.classes[0]
        assert "dataclass" in cls.decorator_list

    def test_abstractmethod_accepted(self):
        src = """
class Base:
    @abstractmethod
    def compute(self, x: int) -> int:
        return 0
"""
        mod = Parser(src).parse()
        cls = mod.classes[0]
        method = next(m for m in cls.body if isinstance(m, FunctionDef))
        assert "abstractmethod" in method.decorator_list
        assert method.is_static is False

    def test_unknown_decorator_raises(self):
        src = """
class MyClass:
    @my_custom_deco
    def compute(self, x: int) -> int:
        return x
"""
        with pytest.raises(UnsupportedFeatureError):
            Parser(src).parse()

    def test_unknown_class_decorator_raises(self):
        src = """
@my_custom_class_deco
class MyClass:
    def compute(self, x: int) -> int:
        return x
"""
        with pytest.raises(UnsupportedFeatureError):
            Parser(src).parse()

    def test_regular_method_unaffected(self):
        """Ensure methods without decorators still parse correctly."""
        src = """
class MyClass:
    def compute(self, x: int) -> int:
        return x
"""
        mod = Parser(src).parse()
        cls = mod.classes[0]
        method = next(m for m in cls.body if isinstance(m, FunctionDef))
        assert method.is_static is False
        assert method.is_classmethod is False
        assert method.decorator_list == ()
        param_names = [p.name for p in method.params]
        assert "x" in param_names

    def test_top_level_function_no_decorator_change(self):
        """Top-level functions still work after parser refactor."""
        src = """
def add(a: int, b: int) -> int:
    return a + b
"""
        mod = Parser(src).parse()
        func = mod.functions[0]
        assert func.name == "add"
        assert func.is_static is False


# ---------------------------------------------------------------------------
# Codegen tests
# ---------------------------------------------------------------------------

class TestStaticMethodCodegen:
    """Verify that @staticmethod produces correct Rust code (no self receiver)."""

    def test_staticmethod_no_self_in_rust(self):
        src = """
class MathUtils:
    @staticmethod
    def add(a: int, b: int) -> int:
        return a + b
"""
        rust = compile_to_rust(src)
        assert "fn add" in rust
        lines = rust.splitlines()
        add_lines = [l for l in lines if "fn add" in l]
        assert add_lines, "Expected 'fn add' in generated Rust"
        for line in add_lines:
            assert "&self" not in line, f"Static method should not have &self: {line}"
            assert "&mut self" not in line, f"Static method should not have &mut self: {line}"

    def test_staticmethod_with_regular_method(self):
        """A class can have both regular and static methods."""
        src = """
class Counter:
    def __init__(self, start: int) -> None:
        self.val = start

    def increment(self) -> None:
        self.val = self.val + 1

    @staticmethod
    def default_value() -> int:
        return 0
"""
        rust = compile_to_rust(src)
        assert "fn default_value" in rust
        assert "fn increment" in rust
        lines = rust.splitlines()
        dflt_lines = [l for l in lines if "fn default_value" in l]
        assert dflt_lines
        for line in dflt_lines:
            assert "&self" not in line
            assert "&mut self" not in line

    def test_classmethod_compiles(self):
        """@classmethod (cls stripped) compiles without crashing."""
        src = """
class Factory:
    def __init__(self, val: int) -> None:
        self.val = val

    @classmethod
    def create(cls, x: int) -> int:
        return x
"""
        rust = compile_to_rust(src)
        assert "fn create" in rust
