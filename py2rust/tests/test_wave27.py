import pytest
from py2rust.middleend.cross_module_symbol_table import CrossModuleSymbolTable
from py2rust.middleend.symbol_table import SymbolTable
from py2rust.middleend.ir_builder import build_ir
from py2rust.middleend.type_checker import TypeChecker
from py2rust.middleend.type_inferencer import TypeInferencer
from py2rust.frontend.parser import parse
from py2rust.utils.errors import SemanticError
from py2rust.backend.rust_codegen import RustCodegen

def test_wave27_function_return_type_propagation():
    cm_table = CrossModuleSymbolTable()
    
    # 1. Compile math_utils
    code_math = "def add(x: int) -> int: return x"
    ast_math = parse(code_math)
    ast_math.filename = "math_utils.py"
    build_ir(ast_math, filename="math_utils.py", cross_module_table=cm_table, module_name="math_utils")
    
    # 2. Compile main
    code_main = "from math_utils import add\ndef main() -> int:\n    y = add(1)\n    return y"
    ast_main = parse(code_main)
    ast_main.filename = "main.py"
    
    ir_main = build_ir(ast_main, filename="main.py", cross_module_table=cm_table, module_name="main")
    assert ir_main is not None
    
    # Verify return type in main function
    func = ir_main.functions[0]
    assert func.name == "main"
    # The variable y should have type IRIntType
    y_body = func.body[0] # y = add(1)
    assert y_body.value.return_type.__class__.__name__ == "IRIntType"

def test_wave27_class_field_method_resolution():
    cm_table = CrossModuleSymbolTable()
    
    # 1. Compile models module
    code_models = """
class Point:
    def __init__(self, x: float) -> None:
        self.x = x
    def get_x(self) -> float:
        return self.x
"""
    ast_models = parse(code_models)
    ast_models.filename = "models.py"
    build_ir(ast_models, filename="models.py", cross_module_table=cm_table, module_name="models")
    
    # 2. Compile main module using models
    code_main = """
from models import Point
def run() -> float:
    p = Point(1.0)
    y = p.x
    z = p.get_x()
    return y + z
"""
    ast_main = parse(code_main)
    ast_main.filename = "main.py"
    
    ir_main = build_ir(ast_main, filename="main.py", cross_module_table=cm_table, module_name="main")
    assert ir_main is not None
    
    # Check that method call get_x and field access x are typed as float
    func = ir_main.functions[0]
    # y = p.x (struct access)
    y_assign = func.body[1]
    assert y_assign.value.__class__.__name__ == "IRStructAccess"
    assert y_assign.value.result_type.__class__.__name__ == "IRFloatType"
    
    # z = p.get_x() (method call)
    z_assign = func.body[2]
    assert z_assign.value.__class__.__name__ == "IRMethodCall"
    assert z_assign.value.result_type.__class__.__name__ == "IRFloatType"

def test_wave27_transitive_module_chains():
    cm_table = CrossModuleSymbolTable()
    
    # C imports nothing
    code_c = """
class C:
    def __init__(self) -> None:
        pass
    def get_str(self) -> str:
        return "hello"
"""
    ast_c = parse(code_c)
    ast_c.filename = "c.py"
    build_ir(ast_c, filename="c.py", cross_module_table=cm_table, module_name="c")
    
    # B imports C
    code_b = """
from c import C
def make_c() -> C:
    return C()
"""
    ast_b = parse(code_b)
    ast_b.filename = "b.py"
    build_ir(ast_b, filename="b.py", cross_module_table=cm_table, module_name="b")
    
    # A imports B
    code_a = """
from b import make_c
def main() -> str:
    c_obj = make_c()
    return c_obj.get_str()
"""
    ast_a = parse(code_a)
    ast_a.filename = "a.py"
    
    ir_a = build_ir(ast_a, filename="a.py", cross_module_table=cm_table, module_name="a")
    assert ir_a is not None
    
    func = ir_a.functions[0]
    c_assign = func.body[0] # c_obj = make_c()
    assert c_assign.value.return_type.__class__.__name__ == "IRClassType"
    assert c_assign.value.return_type.name == "C"
    
    ret_stmt = func.body[1] # return c_obj.get_str()
    assert ret_stmt.value.result_type.__class__.__name__ == "IRStrType"

def test_wave27_method_call_lowering_and_codegen():
    cm_table = CrossModuleSymbolTable()
    
    code_math = "def compute(x: float) -> float: return x + 1.0"
    ast_math = parse(code_math)
    ast_math.filename = "math_utils.py"
    build_ir(ast_math, filename="math_utils.py", cross_module_table=cm_table, module_name="math_utils")
    
    code_main = """
import math_utils
def test() -> float:
    return math_utils.compute(2.0)
"""
    ast_main = parse(code_main)
    ast_main.filename = "main.py"
    
    ir_main = build_ir(ast_main, filename="main.py", cross_module_table=cm_table, module_name="main")
    assert ir_main is not None
    
    # Verify the method call was lowered to an IRMethodCall
    func = ir_main.functions[0]
    ret_stmt = func.body[0]
    assert ret_stmt.value.__class__.__name__ == "IRMethodCall"
    assert ret_stmt.value.method == "compute"
    
    # Generate Rust code
    codegen = RustCodegen()
    rust_code = codegen.generate(ir_main)
    assert "math_utils::compute" in rust_code

def test_wave27_validation_missing_imported_members():
    cm_table = CrossModuleSymbolTable()
    
    code_math = "def compute(x: float) -> float: return x"
    ast_math = parse(code_math)
    ast_math.filename = "math_utils.py"
    build_ir(ast_math, filename="math_utils.py", cross_module_table=cm_table, module_name="math_utils")
    
    # 1. Missing function call check
    code_main_func = """
import math_utils
def test() -> float:
    return math_utils.non_existent(2.0)
"""
    ast_main_func = parse(code_main_func)
    ast_main_func.filename = "main.py"
    
    with pytest.raises(SemanticError) as exc:
        build_ir(ast_main_func, filename="main.py", cross_module_table=cm_table, module_name="main")
    assert "has no function or class 'non_existent'" in str(exc.value)
    
    # 2. Missing attribute check
    code_main_attr = """
import math_utils
def test() -> float:
    return math_utils.invalid_var
"""
    ast_main_attr = parse(code_main_attr)
    ast_main_attr.filename = "main.py"
    
    with pytest.raises(SemanticError) as exc:
        build_ir(ast_main_attr, filename="main.py", cross_module_table=cm_table, module_name="main")
    assert "has no attribute 'invalid_var'" in str(exc.value)
