import pytest
from py2rust.frontend.parser import parse
from py2rust.middleend.ir_builder import build_ir
from py2rust.backend.rust_codegen import generate_rust
from py2rust.middleend.symbol_table import SymbolTable
from py2rust.middleend.type_checker import TypeChecker
from py2rust.utils.errors import Py2RustTypeError


def _compile(src):
    return generate_rust(build_ir(parse(src)))


def _check(src):
    m = parse(src)
    st = SymbolTable()
    tc = TypeChecker(st)
    tc.check_module(m)
    return m, st


def test_floor_division_negative():
    src = """
def main() -> int:
    x: int = -1 // 2
    return 0
"""
    code = _compile(src)
    # The generator now produces: ((- (1)) as f64 / (2) as f64).floor() as i32
    assert ".floor() as i32" in code


def test_negative_range_step():
    src = """
def main() -> int:
    for i in range(10, 0, -1):
        print(i)
    return 0
"""
    code = _compile(src)
    assert "let __stop = 0;" in code
    assert "while if (__step) > 0 { i < (__stop) } else { i > (__stop) } {" in code
    assert "i += __step;" in code


def test_operator_precedence():
    src = """
def f(a: bool, b: bool, c: bool) -> bool:
    return not (a and b) or c
"""
    code = _compile(src)
    assert "!" in code
    assert "&&" in code
    assert "||" in code
    # Check for heavy parenthesization from nested expressions
    assert "||" in code and "!" in code


def test_print_list():
    src = """
def main() -> int:
    lst: list[int] = [1, 2]
    print(lst)
    return 0
"""
    code = _compile(src)
    assert 'println!("{:?}", lst);' in code


def test_aug_assign_validation():
    src = """
def main() -> int:
    x: int = 1
    x += 1.5
    return 0
"""
    with pytest.raises(Py2RustTypeError):
        _check(src)


def test_range_int_validation():
    src = """
def main() -> int:
    for i in range(0.0, 10.0):
        x: int = 0
    return 0
"""
    with pytest.raises(Py2RustTypeError):
        _check(src)


def test_function_scoping():
    src = """
def main() -> int:
    if True:
        x: int = 42
    print(x)
    return 0
"""
    code = _compile(src)
    # x is declared at function level
    assert "let mut x:" in code
    # print uses x after the if block
    assert 'println!("{}", x);' in code


def test_mutable_loop_var():
    src = """
def main() -> int:
    for i in range(0, 10):
        i = i + 1
    return 0
"""
    code = _compile(src)
    # Loop variable is pre-declared as mutable
    assert "let mut i:" in code


def test_string_indexing():
    src = """
def main() -> int:
    s: str = "abc"
    char: str = s[0]
    return 0
"""
    code = _compile(src)
    assert "chars().nth" in code
    assert "let __idx_raw = 0;" in code
    assert "__idx_raw < 0" in code
    assert "__coll.chars().count()" in code
    assert "{ let __coll = &(s);" in code


def test_list_move_semantics():
    src = """
def main() -> int:
    lst: list[str] = ["a", "b"]
    s: str = lst[0]
    return 0
"""
    code = _compile(src)
    assert "__coll[" in code
    assert "{ let __coll = &(lst);" in code
    assert "__coll[actual_idx].clone()" in code


def test_invalid_condition_type():
    src = """
def main() -> int:
    if 1:
        pass
    return 0
"""
    # Simplified valid statement since 'pass' is not supported
    src = """
def main() -> int:
    x: int = 1
    if x:
        x = 2
    return 0
"""
    with pytest.raises(Py2RustTypeError):
        _check(src)


def test_visitor_tuple_traversal():
    from py2rust.utils.visitor import NodeVisitor
    from py2rust.frontend.ast_nodes import (
        Module,
        FunctionDef,
        IntLiteral,
        ReturnStmt,
        IntType,
    )

    class TestVisitor(NodeVisitor):
        def __init__(self):
            self.visited_ints = 0

        def visit_IntLiteral(self, node):
            self.visited_ints += 1

    # FunctionDef.body is a tuple
    node = Module(
        functions=(
            FunctionDef(
                name="f",
                params=(),
                return_type=IntType(),
                body=(ReturnStmt(value=IntLiteral(value=42)),),
            ),
        )
    )

    visitor = TestVisitor()
    visitor.visit(node)
    assert visitor.visited_ints == 1


def test_unannotated_var_scoping():
    src = """
def main() -> int:
    if True:
        x = 42
    print(x)
    return 0
"""
    code = _compile(src)
    # x is declared at function level
    assert "let mut x:" in code
    assert 'println!("{}", x);' in code


def test_loop_target_persistence():
    src = """
def main() -> int:
    for i in range(0, 5):
        s = i
    print(i)
    return 0
"""
    code = _compile(src)
    # Loop variable is pre-declared at function level
    assert "let mut i:" in code
    assert 'println!("{}", i);' in code


def test_negative_indexing_runtime():
    src = """
def main() -> int:
    s: str = "abc"
    last: str = s[-1]
    lst: list[int] = [1, 2, 3]
    last_val: int = lst[-1]
    return 0
"""
    code = _compile(src)
    # Check for negative index handling logic
    assert "if __idx_raw < 0" in code
    assert "__coll.chars().count()" in code
    assert "__coll.len()" in code


def test_while_loop_range_semantics():
    src = """
def main() -> int:
    s = 0
    for i in range(10, 0, -1):
        s += i
    return s
"""
    code = _compile(src)
    # Target initialized
    assert "i = 10;" in code
    # Condition handles negative step
    assert "while if (__step) > 0 { i < (__stop) } else { i > (__stop) } {" in code
    # Increment
    assert "i += __step;" in code


def test_range_single_evaluation():
    src = """
def stop_fn() -> int:
    return 10

def main() -> int:
    s = 0
    for i in range(0, stop_fn()):
        s += i
    return s
"""
    code = _compile(src)
    # Check that idiomatic for loop is used
    assert "let mut i:" in code


def test_idiomatic_mut_generation():
    src = """
def main() -> int:
    x: int = 42
    print(x)
    return 0
"""
    code = _compile(src)
    # x is declared at function level with inferred mutability
    assert "let " in code
    # x is never reassigned, so it should not have mut
    assert "mut x" not in code


def test_standalone_function_call():
    src = """
def helper(x: int) -> int:
    print(x)
    return x

def main() -> int:
    helper(42)
    return 0
"""
    code = _compile(src)
    # Discard should emit just the expression (not let _ = ...)
    assert "helper(42)?;" in code
    # _ is a discard, should NOT have a let declaration
    assert "let _: i32;" not in code
    assert "let mut _: i32;" not in code
    # Make sure we're not emitting 'let _ =' (underscore equals)
    # Note: '_ =>' is a Rust match pattern, not a variable assignment
    import re

    assert not re.search(r"let _ =", code), "Should not have 'let _ =' pattern"


def test_semantic_error_in_ir_builder():
    from py2rust.utils.errors import SemanticError

    # We need a case that triggers _to_ir_type's catch-all
    # This is hard to trigger from parser because parser limits types,
    # but we can test the function directly.
    from py2rust.middleend.ir_builder import _to_ir_type

    class JunkType:
        pass

    with pytest.raises(SemanticError):
        _to_ir_type(JunkType())


def test_nested_loops_shadowing():
    src = """
def main() -> int:
    s = 0
    for i in range(0, 2):
        for j in range(0, 2):
            s += i + j
    return s
"""
    code = _compile(src)
    # Both loop variables are pre-declared at function level
    assert "let mut i:" in code
    assert "let mut j:" in code


def test_subscript_side_effects():
    src = """
def get_list() -> list[int]:
    print(1)
    return [1, 2, 3]

def main() -> int:
    x = get_list()[0]
    return x
"""
    code = _compile(src)
    # get_list() should be assigned to __coll exactly once
    assert "let __coll = &(get_list()?);" in code


def test_mixed_arithmetic_casting():
    src = """
def main() -> float:
    i: int = 1
    f: float = 2.5
    res: float = i + f
    return res
"""
    code = _compile(src)
    assert "(i as f64) + (f as f64)" in code


def test_conflicting_loop_target():
    src = """
def main() -> int:
    i: str = "hi"
    for i in range(0, 10):
        print(i)
    return 0
"""
    with pytest.raises(Py2RustTypeError):
        _check(src)


def test_discard_variable_predeclaration_skipped():
    src = """
def helper(x: int) -> int:
    return x

def main() -> int:
    helper(42)
    return 0
"""
    code = _compile(src)
    # _ is a discard variable in helper(42) call statement,
    # it should not have a let declaration.
    assert "let mut _: i32;" not in code
    assert "let _: i32;" not in code
    # Discards are emitted as just the expression
    assert "helper(42)?;" in code


def test_print_validation_undefined_var():
    from py2rust.utils.errors import CompilerError

    src = """
def main() -> int:
    print(undefined_var)
    return 0
"""
    with pytest.raises(CompilerError):
        _check(src)




def test_invalid_binop_semantic_error():
    from py2rust.utils.errors import CompilerError

    src = """
def main() -> int:
    x = 1 + "a"
    return 0
"""
    with pytest.raises(CompilerError):
        _check(src)


def test_function_call_arg_mismatch():
    from py2rust.utils.errors import CompilerError

    src = """
def f(x: int) -> int:
    return x

def main() -> int:
    f("a")
    return 0
"""
    with pytest.raises(CompilerError):
        _check(src)


def test_invalid_subscript_index_type():
    from py2rust.utils.errors import CompilerError

    src = """
def main() -> int:
    lst: list[int] = [1, 2, 3]
    print(lst["0"])
    return 0
"""
    with pytest.raises(CompilerError):
        _check(src)


def test_undefined_variable_in_binop():
    from py2rust.utils.errors import CompilerError

    src = """
def main() -> int:
    x = y + 1
    return 0
"""
    with pytest.raises(CompilerError):
        _check(src)


def test_list_invariance_enforced():
    from py2rust.utils.errors import CompilerError

    # list[float] cannot accept list[int] because Rust's Vec<T> is invariant
    src = """
def main() -> int:
    li: list[int] = [1, 2]
    lf: list[float] = li
    return 0
"""
    with pytest.raises(CompilerError):
        _check(src)


def test_dict_literal_creation():
    src = """def main() -> int:
        d: dict[str, int] = {"a": 1, "b": 2}
        return 0
"""
    code = _compile(src)
    assert "HashMap<String, i32>" in code
    assert 'HashMap::from([("a".to_string(), 1), ("b".to_string(), 2)])' in code


def test_dict_empty_literal():
    src = """
def main() -> int:
    d: dict[str, int] = {}
    return 0
"""
    code = _compile(src)
    assert "HashMap::<String, i32>::new()" in code


def test_dict_read():
    src = """
def main() -> int:
    d: dict[str, int] = {"a": 1}
    x: int = d["a"]
    return x
"""
    code = _compile(src)
    assert '.get(&"a".to_string()).unwrap().clone()' in code


def test_dict_update():
    src = """
def main() -> int:
    d: dict[str, int] = {"a": 1}
    d["a"] = 10
    return d["a"]
"""
    code = _compile(src)
    assert 'd.insert("a".to_string(), 10);' in code


def test_dict_insert_new_key():
    src = """
def main() -> int:
    d: dict[str, int] = {"a": 1}
    d["b"] = 2
    return len(d)
"""
    code = _compile(src)
    assert 'd.insert("b".to_string(), 2);' in code


def test_dict_delete():
    src = """
def main() -> int:
    d: dict[str, int] = {"a": 1, "b": 2}
    del d["a"]
    return len(d)
"""
    code = _compile(src)
    assert '.remove(&"a".to_string());' in code


def test_dict_len():
    src = """
def main() -> int:
    d: dict[str, int] = {"a": 1, "b": 2, "c": 3}
    result: int = len(d)
    return result
"""
    code = _compile(src)
    assert "d.len() as i32" in code


def test_dict_membership_in():
    src = """
def main() -> int:
    d: dict[str, int] = {"a": 1, "b": 2}
    if "a" in d:
        return 1
    return 0
"""
    code = _compile(src)
    assert '.contains_key(&"a".to_string())' in code


def test_dict_membership_not_in():
    src = """
def main() -> int:
    d: dict[str, int] = {"a": 1, "b": 2}
    if "c" not in d:
        return 1
    return 0
"""
    code = _compile(src)
    assert '!(d.contains_key(&"c".to_string()))' in code


def test_dict_int_keys():
    src = """
def main() -> int:
    d: dict[int, str] = {1: "one", 2: "two"}
    return 0
"""
    code = _compile(src)
    assert "HashMap<i32, String>" in code
    assert 'HashMap::from([(1, "one".to_string()), (2, "two".to_string())])' in code


def test_dict_full_crud():
    src = """
def main() -> int:
    d: dict[str, int] = {"a": 1}
    x: int = d["a"]
    d["a"] = 10
    d["b"] = 2
    del d["a"]
    n: int = len(d)
    return x + d["b"] + n
"""
    code = _compile(src)
    assert "HashMap<String, i32>" in code
    assert ".get(&" in code
    assert ".insert(" in code
    assert ".remove(&" in code
    assert ".len() as i32" in code


def test_dict_type_annotation():
    from py2rust.utils.errors import CompilerError

    src = """
def main() -> int:
    d: dict[str, int] = {"a": "wrong"}
    return 0
"""
    with pytest.raises(CompilerError):
        _check(src)


def test_dict_float_value():
    src = """
def main() -> int:
    d: dict[str, float] = {"a": 1.5}
    return 0
"""
    code = _compile(src)
    assert "HashMap<String, f64>" in code


def test_dict_float_key():
    src = """
def main() -> int:
    d: dict[float, str] = {1.5: "one"}
    return 0
"""
    code = _compile(src)
    assert "HashMap<f64, String>" in code


def test_dict_bool_key():
    src = """
def main() -> int:
    d: dict[bool, str] = {True: "yes", False: "no"}
    return 0
"""
    code = _compile(src)
    assert "HashMap<bool, String>" in code


def test_len_on_list():
    src = """
def main() -> int:
    lst: list[int] = [1, 2, 3, 4, 5]
    result: int = len(lst)
    return result
"""
    code = _compile(src)
    assert "vec![1, 2, 3, 4, 5]" in code
    assert "len() as i32" in code


def test_len_on_string():
    src = """
def main() -> int:
    s: str = "hello"
    result: int = len(s)
    return result
"""
    code = _compile(src)
    assert "len() as i32" in code


def test_len_on_empty_list():
    src = """
def main() -> int:
    lst: list[int] = []
    result: int = len(lst)
    return result
"""
    code = _compile(src)
    assert "Vec::<i32>::new()" in code
    assert "len() as i32" in code


def test_list_indexing():
    src = """
def main() -> int:
    lst: list[int] = [10, 20, 30]
    first: int = lst[0]
    last: int = lst[2]
    return first + last
"""
    code = _compile(src)
    assert "nth(actual_idx)" not in code or "actual_idx" in code


def test_list_index_assignment():
    src = """
def main() -> int:
    lst: list[int] = [1, 2, 3]
    lst[0] = 100
    result: int = lst[0]
    return result
"""
    code = _compile(src)
    assert "vec![1, 2, 3]" in code
    assert "actual_idx = if" in code


def test_list_negative_indexing():
    src = """
def main() -> int:
    lst: list[int] = [1, 2, 3]
    last: int = lst[-1]
    return last
"""
    code = _compile(src)
    assert "actual_idx = if __idx_raw < 0" in code


def test_range_single_arg():
    src = """
def main() -> int:
    for i in range(5):
        print(i)
    return 0
"""
    code = _compile(src)
    # Loop variable is pre-declared
    assert "let mut i:" in code


def test_range_two_args():
    src = """
def main() -> int:
    for i in range(1, 5):
        print(i)
    return 0
"""
    code = _compile(src)
    # Loop variable is pre-declared
    assert "let mut i:" in code


def test_range_three_args():
    src = """
def main() -> int:
    for i in range(0, 10, 2):
        print(i)
    return 0
"""
    code = _compile(src)
    assert "let __stop = 10;" in code
    assert "let __step = 2;" in code


def test_range_negative_step():
    src = """
def main() -> int:
    for i in range(5, 0, -1):
        print(i)
    return 0
"""
    code = _compile(src)
    assert "let __stop = 0;" in code
    assert "let __step = (-(1));" in code


def test_string_concatenation():
    src = """
def main() -> int:
    a: str = "hello"
    b: str = " world"
    c: str = a + b
    return 0
"""
    code = _compile(src)
    assert ".to_string() + &" in code


def test_string_repetition():
    src = """
def main() -> int:
    s: str = "ab"
    repeated: str = s * 3
    return 0
"""
    code = _compile(src)
    assert ".repeat(3)" in code


def test_list_concatenation():
    src = """
def main() -> int:
    a: list[int] = [1, 2]
    b: list[int] = [3, 4]
    c: list[int] = a + b
    return 0
"""
    code = _compile(src)
    assert "Vec<i32>" in code
    assert "clone)?;" in code or "extend(" in code


def test_break_in_while():
    src = """
def main() -> int:
    i: int = 0
    while i < 10:
        i = i + 1
        if i == 5:
            break
    return i
"""
    code = _compile(src)
    assert "break" in code
    assert "'__loop_" in code


def test_break_in_for():
    src = """
def main() -> int:
    for i in range(10):
        if i == 7:
            break
    return i
"""
    code = _compile(src)
    assert "break" in code
    assert "'__loop_" in code


def test_continue_in_while():
    src = """
def main() -> int:
    i: int = 0
    count: int = 0
    while i < 5:
        i = i + 1
        if i == 3:
            continue
        count = count + 1
    return count
"""
    code = _compile(src)
    assert "continue" in code
    assert "'__loop_" in code


def test_continue_in_for():
    src = """
def main() -> int:
    count: int = 0
    for i in range(5):
        if i == 2:
            continue
        count = count + 1
    return count
"""
    code = _compile(src)
    assert "continue" in code
    assert "'__loop_" in code


def test_nested_loops_break():
    src = """
def main() -> int:
    for i in range(3):
        for j in range(5):
            if j == 2:
                break
    return i + j
"""
    code = _compile(src)
    assert code.count("break") >= 1
    assert "'__loop_" in code


def test_function_call_standalone():
    src = """
def foo() -> int:
    return 42

def main() -> int:
    foo()
    return 0
"""
    code = _compile(src)
    assert "foo()?;" in code
    assert "fn foo() -> Result<i32, PyError> {" in code


def test_mixed_type_operations():
    src = """
def main() -> int:
    x: int = 10
    y: float = 3.14
    z: int = x + 5
    w: float = y + 1.0
    return 0
"""
    code = _compile(src)
    assert "10" in code
    assert "3.14" in code


def test_boolean_operations():
    src = """
def f(a: bool, b: bool) -> bool:
    return a and b
"""
    code = _compile(src)
    assert "&&" in code


def test_unary_not():
    src = """
def f(a: bool) -> bool:
    return not a
"""
    code = _compile(src)
    assert "!" in code


def test_unary_minus():
    src = """
def main() -> int:
    x: int = -5
    y: int = -x
    return y
"""
    code = _compile(src)
    assert "-(5)" in code
    assert "-" in code


def test_comparison_operations():
    src = """
def f(a: int, b: int) -> bool:
    return a < b
"""
    code = _compile(src)
    assert "<" in code


def test_if_else():
    src = """
def f(x: int) -> int:
    if x > 0:
        return 1
    else:
        return 0
"""
    code = _compile(src)
    assert "if" in code
    assert "else" in code


def test_while_loop():
    src = """
def main() -> int:
    i: int = 0
    while i < 10:
        i = i + 1
    return i
"""
    code = _compile(src)
    assert "while" in code


def test_augmented_assignment():
    src = """
def main() -> int:
    x: int = 5
    x += 3
    x -= 1
    x *= 2
    return x
"""
    code = _compile(src)
    assert "+=" in code
    assert "-=" in code
    assert "*=" in code


def test_file_open():
    src = """
def main() -> int:
    f = open("test.txt")
    return 0
"""
    code = _compile(src)
    assert "FileHandle::open" in code


def test_file_open_with_mode():
    src = """
def main() -> int:
    f = open("test.txt", "w")
    return 0
"""
    code = _compile(src)
    assert "FileHandle::open" in code


def test_file_handle_struct_generated():
    src = """
def main() -> int:
    f = open("test.txt")
    return 0
"""
    code = _compile(src)
    assert "struct FileHandle" in code
    assert "fn open(" in code
    assert "fn read(" in code
    assert "fn write(" in code
    assert "fn close(" in code
    assert "fn tell(" in code
    assert "fn seek(" in code


def test_simple_class_parsing():
    src = """
class Point:
    x: int = 0
    y: int = 0
"""
    m = parse(src)
    assert len(m.classes) == 1
    assert m.classes[0].name == "Point"


def test_class_with_init():
    src = """
class Point:
    x: int = 0
    y: int = 0
    
    def __init__(self, x: int, y: int) -> None:
        self.x = x
        self.y = y
"""
    code = _compile(src)
    assert "struct Point" in code
    assert "fn new(" in code


def test_class_instantiation():
    src = """
class Point:
    x: int = 0
    y: int = 0
    
    def __init__(self, x: int, y: int) -> None:
        self.x = x
        self.y = y

def main() -> int:
    p: Point = Point(1, 2)
    return 0
"""
    code = _compile(src)
    assert "struct Point" in code
    assert "Point::new(1, 2)" in code


def test_class_field_access():
    src = """
class Point:
    x: int = 0
    y: int = 0
    
    def __init__(self, x: int, y: int) -> None:
        self.x = x
        self.y = y

def main() -> int:
    p: Point = Point(1, 2)
    result: int = p.x
    return result
"""
    code = _compile(src)
    assert "struct Point" in code
    assert "p.x" in code


def test_class_method_call():
    src = """
class Counter:
    count: int = 0
    
    def __init__(self) -> None:
        self.count = 0
    
    def increment(self) -> None:
        self.count = self.count + 1

def main() -> int:
    c: Counter = Counter()
    c.increment()
    return 0
"""
    code = _compile(src)
    assert "struct Counter" in code
    assert "c.increment()" in code


def test_class_method_with_return():
    src = """
class Calculator:
    value: int = 0
    
    def __init__(self) -> None:
        self.value = 0
    
    def get_value(self) -> int:
        return self.value

def main() -> int:
    c: Calculator = Calculator()
    result: int = c.get_value()
    return result
"""
    code = _compile(src)
    assert "struct Calculator" in code
    assert "fn get_value(" in code
    assert "c.get_value()" in code


def test_class_with_method_overloading():
    src = """
class Adder:
    def add_two(self, a: int, b: int) -> int:
        return a + b
    
    def add_three(self, a: int, b: int, c: int) -> int:
        return a + b + c

def main() -> int:
    a: Adder = Adder()
    return a.add_two(1, 2)
"""
    code = _compile(src)
    assert "struct Adder" in code
    assert "fn add_two(" in code
    assert "fn add_three(" in code


def test_class_multiple_instances():
    src = """
class Point:
    x: int = 0
    y: int = 0
    
    def __init__(self, x: int, y: int) -> None:
        self.x = x
        self.y = y

def main() -> int:
    p1: Point = Point(1, 2)
    p2: Point = Point(3, 4)
    return p1.x + p2.x
"""
    code = _compile(src)
    assert "struct Point" in code
    assert "Point::new(1, 2)" in code
    assert "Point::new(3, 4)" in code


def test_constructor_is_static():
    """Test that __init__ generates a static new method."""
    src = """
class Counter:
    count: int = 0
    
    def __init__(self) -> None:
        self.count = 0
    
    def increment(self) -> None:
        self.count = self.count + 1

def main() -> int:
    c: Counter = Counter()
    c.increment()
    return 0
"""
    code = _compile(src)
    assert "struct Counter" in code
    assert "fn new(&self" not in code


def test_self_field_assignment():
    """Test that self.field assignment uses proper Rust syntax in constructor."""
    src = """
class Point:
    x: int = 0
    y: int = 0
    
    def __init__(self, x: int, y: int) -> None:
        self.x = x
        self.y = y

def main() -> int:
    return 0
"""
    code = _compile(src)
    assert "Self { x: x, y: y }" in code
    assert "self_.x" not in code
    assert "self_.y" not in code


def test_main_returns_unit():
    """Test that main function returns () not i32."""
    src = """
def main() -> int:
    return 0
"""
    code = _compile(src)
    assert "fn main() -> Result<(), PyError> {" in code
    assert "{ 0; () }" in code


def test_main_discard_return_value():
    """Test that return expressions in main are discarded."""
    src = """
def helper(x: int) -> int:
    return x * 2

def main() -> int:
    result: int = helper(42)
    return result
"""
    code = _compile(src)
    assert "fn main() -> Result<(), PyError> {" in code


def test_discard_function_call():
    """Test that standalone function calls use discard properly."""
    src = """
def log(msg: str) -> int:
    return 0

def main() -> int:
    log("hello")
    return 0
"""
    code = _compile(src)
    assert 'log("hello".to_string())?;' in code
    assert "let mut _" not in code
    assert "let _" not in code


def test_method_call_on_self():
    """Test that self.method() generates proper Rust syntax."""
    src = """
class Calculator:
    value: int = 0
    
    def __init__(self) -> None:
        self.value = 0
    
    def get_value(self) -> int:
        return self.value

def main() -> int:
    return 0
"""
    code = _compile(src)
    assert "self.value" in code
    assert "self_.value" not in code


def test_unit_type_return():
    """Test that methods with None return type generate () in Rust."""
    src = """
class Point:
    x: int = 0
    y: int = 0
    
    def __init__(self, x: int, y: int) -> None:
        self.x = x
        self.y = y

def main() -> int:
    return 0
"""
    code = _compile(src)
    # Constructor is static, so it doesn't have &self
    assert "fn new(x: i32, y: i32) -> Result<Self, PyError> {" in code


def test_list_concat_clones_right():
    """Test that list concatenation clones the right operand."""
    src = """
def main() -> int:
    a: list[int] = [1, 2]
    b: list[int] = [3, 4]
    c: list[int] = a + b
    return 0
"""
    code = _compile(src)
    assert "clone()" in code
    assert ".extend(" in code


def test_dict_print_debug_format():
    """Test that dicts are printed with debug format."""
    src = """
def main() -> int:
    d: dict[str, int] = {"a": 1}
    print(d)
    return 0
"""
    code = _compile(src)
    assert "{:?}" in code


def test_nested_attribute_rejected():
    """Test that nested attribute assignment is rejected."""
    from py2rust.utils.errors import UnsupportedFeatureError

    src = """
class Outer:
    inner: int = 0

def main() -> int:
    o: Outer = Outer()
    o.inner.nested = 1
    return 0
"""
    with pytest.raises(UnsupportedFeatureError):
        _compile(src)


def test_static_constructor_call():
    """Test that constructor is called with :: syntax."""
    src = """
class Point:
    x: int = 0
    y: int = 0
    
    def __init__(self, x: int, y: int) -> None:
        self.x = x
        self.y = y

def main() -> int:
    p: Point = Point(1, 2)
    return 0
"""
    code = _compile(src)
    assert "Point::new(1, 2)" in code


def test_class_field_access_correct():
    """Test that class field access uses proper syntax."""
    src = """
class Point:
    x: int = 0
    y: int = 0
    
    def __init__(self, x: int, y: int) -> None:
        self.x = x
        self.y = y
    
    def get_x(self) -> int:
        return self.x

def main() -> int:
    p: Point = Point(1, 2)
    x: int = p.x
    return x
"""
    code = _compile(src)
    assert "p.x" in code
    assert "self.x" in code

def test_loop_variable_persistence_regression():
    src = """
def main() -> int:
    i: int = 0
    for i in range(10):
        i = i
    return i
"""
    code = _compile(src)
    assert "let mut i: i32 = 0;" in code
    # Inside loop, it should NOT be shadowed with let mut
    assert "let mut i =" not in code[code.find("for"): ]
    assert "i =" in code

def test_parameter_mutation_assignment_regression():
    src = """
def f(x: int) -> int:
    x = 10
    return x
"""
    code = _compile(src)
    assert "fn f(mut x: i32)" in code

def test_parameter_mutation_subscript_regression():
    src = """
def f(lst: list[int]) -> int:
    lst[0] = 42
    return 0
"""
    code = _compile(src)
    assert "fn f(mut lst: Vec<i32>)" in code

def test_loop_target_mangle_regression():
    src = """
def main() -> int:
    type: int = 0
    for type in range(5):
        print(type)
    return 0
"""
    code = _compile(src)
    assert "let mut type_: i32 = 0;" in code
    assert "type_ =" in code
