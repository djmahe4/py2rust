import pytest
import tempfile
from pathlib import Path
from py2rust.middleend.cross_module_symbol_table import CrossModuleSymbolTable
from py2rust.middleend.symbol_table import SymbolTable
from py2rust.middleend.ir_builder import build_ir
from py2rust.frontend.parser import parse
from py2rust.frontend.ast_nodes import ExternalPythonType, FloatType, Name, FunctionCall, ClassType
from py2rust.utils.errors import SemanticError
from py2rust.backend.workspace_generator import WorkspaceGenerator

def test_cross_module_table_basic():
    cm_table = CrossModuleSymbolTable()
    st = SymbolTable()
    st.define_function("add", [object, object], object)
    cm_table.register_module("math_utils", st)
    
    sig = cm_table.lookup_symbol("math_utils", "add", "functions")
    assert sig is not None
    assert sig[0] == [object, object]

def test_build_ir_accepts_cross_module_table():
    cm_table = CrossModuleSymbolTable()
    code = "def double(x: int) -> int: return x * 2"
    ast_tree = parse(code)
    
    ir_mod = build_ir(ast_tree, filename="math_utils.py", cross_module_table=cm_table, module_name="math_utils")
    assert ir_mod is not None
    assert cm_table.has_module("math_utils")
    sig = cm_table.lookup_symbol("math_utils", "double", "functions")
    assert sig is not None

def test_symbol_table_delegation():
    cm_table = CrossModuleSymbolTable()
    
    # 1. Register a dependency module "math_utils" with function, class, enum, trait
    st_dep = SymbolTable()
    st_dep.define_function("add", [object, object], object)
    st_dep.define_class("Point", (), {"x": object}, {}, {})
    st_dep.define_enum("Status", {"OK": 1})
    st_dep.define_trait("Serializable", [], {})
    
    cm_table.register_module("math_utils", st_dep)
    
    # 2. Local SymbolTable imports those from "math_utils"
    st_local = SymbolTable(cross_module_table=cm_table, module_name="main")
    
    st_local.define("add", ExternalPythonType(module="math_utils", name="add", is_local=True))
    st_local.define("Point", ExternalPythonType(module="math_utils", name="Point", is_local=True))
    st_local.define("Status", ExternalPythonType(module="math_utils", name="Status", is_local=True))
    st_local.define("Serializable", ExternalPythonType(module="math_utils", name="Serializable", is_local=True))
    
    # 3. Lookup should delegate successfully!
    func_sig = st_local.lookup_function("add")
    assert func_sig is not None
    assert func_sig[0] == [object, object]
    
    cls_info = st_local.lookup_class("Point")
    assert cls_info is not None
    assert cls_info.name == "Point"
    
    enum_info = st_local.lookup_enum("Status")
    assert enum_info is not None
    assert enum_info.name == "Status"
    
    trait_info = st_local.lookup_trait("Serializable")
    assert trait_info is not None
    assert trait_info.name == "Serializable"

def test_typechecker_local_import_validation():
    cm_table = CrossModuleSymbolTable()
    
    # Register "other" with "valid_fn"
    st_other = SymbolTable()
    st_other.define_function("valid_fn", [], None)
    cm_table.register_module("other", st_other)
    
    # 1. Valid import should succeed
    code_valid = "from other import valid_fn"
    ast_valid = parse(code_valid)
    ast_valid.filename = "main.py"
    ir_valid = build_ir(ast_valid, filename="main.py", cross_module_table=cm_table, module_name="main")
    assert ir_valid is not None
    
    # 2. Invalid import (missing symbol) should raise SemanticError
    code_invalid = "from other import missing_fn"
    ast_invalid = parse(code_invalid)
    ast_invalid.filename = "main.py"
    with pytest.raises(SemanticError) as excinfo:
        build_ir(ast_invalid, filename="main.py", cross_module_table=cm_table, module_name="main")
    assert "cannot import name 'missing_fn' from 'other'" in str(excinfo.value)

def test_cross_module_function_call_type():
    cm_table = CrossModuleSymbolTable()
    
    # 1. Compile math_utils
    code_math = "def compute(x: float) -> float: return x + 1.0"
    ast_math = parse(code_math)
    ast_math.filename = "math_utils.py"
    build_ir(ast_math, filename="math_utils.py", cross_module_table=cm_table, module_name="math_utils")
    
    # 2. Compile main which imports compute and calls it
    code_main = "from math_utils import compute\ndef main() -> float:\n    return compute(2.0)"
    ast_main = parse(code_main)
    ast_main.filename = "main.py"
    ir_main = build_ir(ast_main, filename="main.py", cross_module_table=cm_table, module_name="main")
    assert ir_main is not None

def test_cross_module_class_type_resolution():
    cm_table = CrossModuleSymbolTable()
    
    # 1. Compile models defining class Point
    code_models = "class Point:\n    def __init__(self, x: float) -> None:\n        self.x = x\n    def get_x(self) -> float:\n        return self.x"
    ast_models = parse(code_models)
    ast_models.filename = "models.py"
    build_ir(ast_models, filename="models.py", cross_module_table=cm_table, module_name="models")
    
    # 2. Compile main which imports Point, accesses field, and calls method
    code_main = "from models import Point\ndef test_field(p: Point) -> float:\n    return p.x\ndef test_method(p: Point) -> float:\n    return p.get_x()"
    ast_main = parse(code_main)
    ast_main.filename = "main.py"
    ir_main = build_ir(ast_main, filename="main.py", cross_module_table=cm_table, module_name="main")
    assert ir_main is not None

def test_workspace_reexports_and_mod_decls():
    with tempfile.TemporaryDirectory() as tmp_dir:
        output_path = Path(tmp_dir)
        generator = WorkspaceGenerator(output_path)
        
        modules = {
            "math_utils": "// math_utils rust code",
            "models": "// models rust code",
            "a.b.c": "// c rust code",
            "a.b": "// b rust code",
            "a": "// a rust code",
        }
        
        # Generate mod hierarchy (no explicit entry_point to make it a library)
        generator.generate_mod_hierarchy(modules)
        
        # 1. Verify src/lib.rs contains root-level module declarations and pub use re-exports
        lib_file = output_path / "src" / "lib.rs"
        assert lib_file.exists()
        lib_content = lib_file.read_text()
        
        # Top-level mod declarations
        assert "pub mod a;" in lib_content
        assert "pub mod errors;" in lib_content
        assert "pub mod math_utils;" in lib_content
        assert "pub mod models;" in lib_content
        
        # Root-level pub use re-exports
        assert "pub use a::*;" in lib_content
        assert "pub use math_utils::*;" in lib_content
        assert "pub use models::*;" in lib_content
        
        # 2. Verify nested re-exports in src/a.rs
        a_file = output_path / "src" / "a.rs"
        assert a_file.exists()
        a_content = a_file.read_text()
        assert "pub mod b;" in a_content
        assert "pub use b::*;" in a_content
        
        # 3. Verify nested re-exports in src/a/b.rs
        b_file = output_path / "src" / "a" / "b.rs"
        assert b_file.exists()
        b_content = b_file.read_text()
        assert "pub mod c;" in b_content
        assert "pub use c::*;" in b_content
        
        # 4. Verify src/a/b/c.rs is generated correctly
        c_file = output_path / "src" / "a" / "b" / "c.rs"
        assert c_file.exists()
        assert c_file.read_text() == "// c rust code"
