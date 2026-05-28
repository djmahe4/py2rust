from __future__ import annotations
from ..ir.ir_nodes import (
    IRModule,
    IRFunction,
    IRParam,
    IRIntType,
    IRFloatType,
    IRBoolType,
    IRStrType,
    IRUnitType,
    IRListType,
    IRDictType,
    IRTupleType,
    IRFileType,
    IRSetType,
    IRDequeType,
    IRHeapType,
    IRFunctionType,
    IRClassType,
    IRExternalPythonType,
    IROptionType,
    IRSumType,
    IRUnknownType,
    IRIntLit,
    IRFloatLit,
    IRBoolLit,
    IRStrLit,
    IRTupleLit,
    IRName,
    IRBinOp,
    IRUnaryOpExpr,
    IRCompare,
    IRBoolOp,
    IRListLit,
    IRDictLit,
    IRContains,
    IRSlice,
    IRSubscript,
    IRSubscriptAssign,
    IRFunctionCall,
    IRFileOpen,
    IRFileMethod,
    IRVarDecl,
    IRAssign,
    IRFieldAssign,
    IRAugAssign,
    IRIf,
    IRWhile,
    IRForRange,
    IRForIter,
    IRTryExcept,
    IRRaise,
    IRReturn,
    IRPrint,
    IRBreak,
    IRContinue,
    IRDictDelete,
    IRStructAccess,
    IRMethodCall,
    IRNew,
    IRSelf,
    IRTupleLit,
    IRTupleUnpack,
    IRClassDefinition,
    IRTraitDefinition,
    IRTraitMethod,
    IRAwait,
    IREnumType,
    IREnumDef,
    IRMatchStmt,
    IRMatchCase,
    IRMatchPattern,
    IRValuePattern,
    IRNamePattern,
    IRClassPattern,
    IRWildcardPattern,
    IROrPattern,
    IRAsPattern,
    IRLambda,
    IRComprehension,
    IRListComp,
    IRDictComp,
    IRSetComp,
    IRWith,
    IRAssert,
    IRGlobal,
    IRNonlocal,
    IRFormattedValue,
    IRJoinedStr,
    IRTraitImpl,
    IRTypeParam,
    IRGenericType,
    IRExpr,
    IRType,
    IRStmt,
    IRSome,
    IRSumWrap,
    IRNoneLit,
    IRIsInstance,
    IRIteratorType,
    IRIterableType,
    IRGeneratorType,
    IRYield,
    IRYieldFrom,
    IRGeneratorExp,
    IRMap,
    IRFilter,
    IRSorted,
    IRReduce,
)
from ..config import CompilerConfig, AsyncRuntime
from typing import Optional

from .expr_codegen import ExprCodegenMixin
from .generator_codegen import GeneratorCodegenMixin

from .codegen_helpers import (
    _RUST_KEYWORDS,
    _mangle,
    _get_var_name,
    _get_names,
    _collect_vars_from_expr,
    _get_reachable_if_branches,
    _collect_mutated_vars,
    _collect_decls,
    _vars_declared_in_loop,
    PYTHON_BOILERPLATE_LINES,
)


class RustCodegen(ExprCodegenMixin, GeneratorCodegenMixin):
    def __init__(self, dependency_manager=None, config: CompilerConfig = None):
        self._indent = 0
        self._lines: list = []
        self._mutated_vars: set = set()
        self._in_main: bool = False
        self._at_top_level: bool = True
        self._loop_vars: set = set()
        self._uses_hashmap = False
        self._uses_file_handle = False
        self._uses_py_error = False
        self._uses_async = False
        self._inside_try = 0
        self._loop_depth = 0
        self._current_fn_return_type = "()"
        self._uses_try_result = False
        self._uses_python_wrappers = (config or CompilerConfig()).mock_mode
        self.dependency_manager = dependency_manager
        self.config = config or CompilerConfig()
        self._sum_types: dict[tuple, str] = {} # variants tuple -> enum name

    def _is_protocol(self, name: str) -> bool:
        """Check if a name corresponds to a defined Protocol/Trait."""
        if not hasattr(self, "_current_module"):
            return False
        for trait in self._current_module.traits:
            if trait.name == name:
                return True
        return False

    def _get_rust_type(self, t) -> str:
        if t is None:
            return "()"
        if isinstance(t, IRIntType):
            return "i32"
        if isinstance(t, IRFloatType):
            return "f64"
        if isinstance(t, IRBoolType):
            return "bool"
        if isinstance(t, IRStrType):
            return "String"
        if isinstance(t, IRUnitType):
            return "()"
        if isinstance(t, IRListType):
            elem_t = self._get_rust_type(t.element_type)
            if isinstance(t.element_type, IRClassType) and self._is_protocol(t.element_type.name):
                return f"Vec<Box<dyn {t.element_type.name}>>"
            return f"Vec<{elem_t}>"
        if isinstance(t, IRDictType):
            self._uses_hashmap = True
            return f"HashMap<{self._get_rust_type(t.key_type)}, {self._get_rust_type(t.value_type)}>"
        if isinstance(t, IRFileType):
            if self._uses_python_wrappers:
                return "ExternalObject"
            self._uses_file_handle = True
            return "FileHandle"
        if isinstance(t, IRClassType):
            # If the class name corresponds to a known trait, use a trait object reference
            if hasattr(self, "_current_module"):
                for trait in self._current_module.traits:
                    if trait.name == t.name:
                        return f"&dyn {t.name}"
            return t.name
        if isinstance(t, IRTupleType):
            types = ", ".join(self._get_rust_type(et) for et in t.element_types)
            return f"({types})"
        if isinstance(t, IROptionType):
            return f"Option<{self._get_rust_type(t.inner_type)}>"
        if isinstance(t, IRSumType):
            return self._get_sum_type_name(t)
        if isinstance(t, IRSetType):
            self._uses_hashset = True
            return f"HashSet<{self._get_rust_type(t.element_type)}>"
        if isinstance(t, IRDequeType):
            self._uses_deque = True
            return f"VecDeque<{self._get_rust_type(t.element_type)}>"
        if isinstance(t, IRHeapType):
            self._uses_heap = True
            # We use Reverse to match Python's min-heap behavior
            return f"BinaryHeap<Reverse<{self._get_rust_type(t.element_type)}>>"
        if isinstance(t, IRFunctionType):
            return "_"  # Let Rust infer closure types
        if isinstance(t, IRIteratorType):
            elem = self._get_rust_type(t.element_type)
            return f"Box<dyn Iterator<Item = {elem}>>"
        if isinstance(t, IRIterableType):
            elem = self._get_rust_type(t.element_type)
            return f"Box<dyn Iterator<Item = {elem}>>"
        if isinstance(t, IRGeneratorType):
            yield_t = self._get_rust_type(t.yield_type)
            return f"Box<dyn Iterator<Item = {yield_t}>>"
        if isinstance(t, IRUnknownType):
            return "_"  # Fallback for polymorphic None or untyped nodes
        if isinstance(t, IRTypeParam):
            return t.name
        if isinstance(t, IRGenericType):
            base = self._get_rust_type(t.base)
            params = ", ".join(self._get_rust_type(p) for p in t.params)
            return f"{base}<{params}>"
        if isinstance(t, IRExternalPythonType):
            if t.is_local:
                return t.name if t.name else t.module.split(".")[-1]
            self._uses_python_wrappers = True
            return "ExternalObject"
        raise ValueError(f"Unknown type {type(t).__name__}")

    def _get_sum_type_name(self, t: IRSumType) -> str:
        if t.name:
            return t.name
        
        # Consistent variants: Tuple of rust type strings (sorted)
        variants = tuple(sorted(self._get_rust_type(v) for v in t.variants))
        if variants in self._sum_types:
            return self._sum_types[variants]
        
        # Helper to make valid Rust identifier
        def to_ident(s: str) -> str:
            return s.replace("<", "Of").replace(">", "").replace(" ", "").replace(",", "And").replace("(", "Tuple").replace(")", "").replace("::", "Of").replace("&", "Ref")
        
        # Generate a name: IntOrFloatOrStr etc.
        name_parts = []
        for v in variants:
            p = v.replace("i32", "Int").replace("f64", "Float").replace("String", "Str").replace("bool", "Bool")
            name_parts.append(to_ident(p))
        
        name = "Or".join(name_parts) + "Union"
        self._sum_types[variants] = name
        return name

    def _get_variant_name(self, v: str) -> str:
        """Generate a valid Rust enum variant name from a Rust type string."""
        v_name = v.replace("i32", "Int").replace("f64", "Float").replace("String", "Str").replace("bool", "Bool")
        v_name = v_name.replace("Vec<Int>", "IntList").replace("Vec<Float>", "FloatList").replace("Vec<Str>", "StrList")
        v_name = v_name.replace("<", "Of").replace(">", "").replace(" ", "").replace(",", "And").replace("(", "Tuple").replace(")", "").replace("::", "Of").replace("&", "Ref")
        return v_name

    def _generate_sum_type_definitions(self) -> list[str]:
        lines = []
        # Sort by name for deterministic output
        for variants, name in sorted(self._sum_types.items(), key=lambda x: x[1]):
            lines.append(f"#[derive(Debug, Clone, PartialEq)]")
            lines.append(f"pub enum {name} {{")
            for v in variants:
                # Variant name should be descriptive
                v_name = self._get_variant_name(v)
                lines.append(f"    {v_name}({v}),")
            lines.append("}")
            lines.append("")
        return lines

    def _emit(self, line: str) -> None:
        self._lines.append("    " * self._indent + line)

    def _emit_blank(self) -> None:
        self._lines.append("")

    def _strip_parens(self, s: str) -> str:
        """Strip outer parentheses from an expression string."""
        s = s.strip()
        if s.startswith("(") and s.endswith(")"):
            count = 1
            for i in range(1, len(s) - 1):
                if s[i] == "(":
                    count += 1
                elif s[i] == ")":
                    count -= 1
                    if count == 0:
                        return s
            return s[1:-1]
        return s

    def generate(self, ir_mod: IRModule) -> str:
        # Reset state
        self._current_module = ir_mod
        self._lines = []
        if hasattr(self.config, "translation_context") and self.config.translation_context:
            self.config.translation_context.add_global_flow("All Python functions return Result<T, PyError> wrappers in Rust for safe error handling.")
            self.config.translation_context.add_global_flow("Exception handling uses standard try/catch blocks translated to Rust Result matching / early return using the ? operator.")

        self._uses_hashmap = False
        self._uses_hashset = False
        self._uses_file_handle = False
        self._uses_py_error = False
        self._uses_async = False
        self._uses_python_wrappers = self.config.mock_mode
        self._uses_serde_json = False
        self._uses_pythonize = False
        self._uses_csv = False
        self._uses_deque = False
        self._uses_heap = False
        self._decl_types = {}

        # Compute needed traits (omit standalone companion traits unless in repo mode)
        companion_traits = {f"{cls.name}Trait": cls for cls in ir_mod.classes}
        needed_companion_traits = set()
        
        all_bases = set()
        for cls in ir_mod.classes:
            for base in cls.bases:
                all_bases.add(base)
                
        is_repo = bool(self.config and self.config.repo_root)
        for cls in ir_mod.classes:
            if cls.bases or cls.name in all_bases or is_repo:
                needed_companion_traits.add(f"{cls.name}Trait")
                
        changed = True
        while changed:
            changed = False
            new_needed = set(needed_companion_traits)
            for t_name in needed_companion_traits:
                if t_name in companion_traits:
                    cls = companion_traits[t_name]
                    for base in cls.bases:
                        base_trait = f"{base}Trait"
                        if base_trait not in new_needed:
                            new_needed.add(base_trait)
                            changed = True
            needed_companion_traits = new_needed
            
        self._needed_traits = set()
        for trait in ir_mod.traits:
            if trait.name not in companion_traits:
                self._needed_traits.add(trait.name)
            elif trait.name in needed_companion_traits:
                self._needed_traits.add(trait.name)

        # Pre-pass: Generate Traits
        trait_lines = []
        local_classes = {cls.name for cls in ir_mod.classes}
        for trait in ir_mod.traits:
            if trait.name not in self._needed_traits:
                continue
            if trait.name.endswith("Trait"):
                class_name = trait.name[:-5]
                if class_name not in local_classes:
                    continue
            trait_lines.append(self._gen_trait(trait))
            trait_lines.append("")

        # Generate Trait Impls
        trait_impl_lines = []
        for impl_def in ir_mod.trait_impls:
            if impl_def.trait_name not in self._needed_traits:
                continue
            self._gen_trait_impl(impl_def)
            trait_impl_lines.extend(self._lines)
            self._lines = []
            trait_impl_lines.append("")

        # First pass: Generate classes and functions to detect feature usage
        # We store them in separate buffers
        class_lines = []
        for cls in ir_mod.classes:
            self._gen_class(cls)
            class_lines.extend(self._lines)
            self._lines = []
            class_lines.append("")

        func_lines = []
        for i, func in enumerate(ir_mod.functions):
            self._gen_function(func)
            func_lines.extend(self._lines)
            self._lines = []
            if i < len(ir_mod.functions) - 1:
                func_lines.append("")

        # Generate global statements
        stmt_lines = []
        if hasattr(ir_mod, "statements"):
            for stmt in ir_mod.statements:
                self._gen_stmt(stmt)
                stmt_lines.extend(self._lines)
                self._lines = []
                stmt_lines.append("")

        # Generate Enums
        enum_lines = []
        for enum_def in ir_mod.enums:
            self._gen_enum(enum_def)
            enum_lines.extend(self._lines)
            self._lines = []
            enum_lines.append("")
            
        # Generate Sum Type Enums (populated during previous passes)
        sum_type_lines = self._generate_sum_type_definitions()
        enum_lines.extend(sum_type_lines)
        if enum_lines and enum_lines[-1] != "":
            enum_lines.append("")
            
        # Second pass: Emit header and boilerplate based on detected usage
        final_lines = ["// Generated by py2rust"]
        
        # Emit dependency info for Cargo.toml
        if self.dependency_manager:
            if self._uses_python_wrappers:
                self.dependency_manager.add_dependency("pyo3", version="0.20", features=["extension-module", "abi3-py310"])
            if self._uses_serde_json or self._uses_pythonize:
                self.dependency_manager.add_dependency("serde", version="1.0", features=["derive"])
            if self._uses_serde_json:
                self.dependency_manager.add_dependency("serde_json", version="1.0")
            if self._uses_pythonize:
                self.dependency_manager.add_dependency("pythonize", version="0.20")
            if self._uses_csv:
                self.dependency_manager.add_dependency("csv", version="1.1")
            final_lines.append("//")
            final_lines.append("// Required dependencies for Cargo.toml:")
            for line in self.dependency_manager.get_cargo_dependencies().splitlines():
                final_lines.append(f"// {line}")
            final_lines.append("//")
            final_lines.append("")

        # Imports
        imports = []

        # Local Module Imports from DependencyManager
        resolver = None
        repo_root = getattr(self.config, "repo_root", None)
        if repo_root:
            package_dir = getattr(self.config, "package_dir", None)
            from py2rust.project.import_resolver import ImportResolver
            from pathlib import Path
            resolver = ImportResolver(
                repo_root=Path(repo_root),
                package_dir=package_dir
            )

        current_module = None
        if resolver and ir_mod.filename:
            from pathlib import Path
            current_module = resolver.get_module_for_file(Path(ir_mod.filename))

        if self.dependency_manager and current_module:
            use_statements = self.dependency_manager.get_module_imports(current_module)
            for stmt in use_statements:
                imports.append(stmt)

        if self._uses_hashmap:
            imports.append("use std::collections::HashMap;")
        if self._uses_hashset:
            imports.append("use std::collections::HashSet;")
        if self._uses_deque:
            imports.append("use std::collections::VecDeque;")
        if self._uses_heap:
            imports.append("use std::collections::BinaryHeap;")
            imports.append("use std::cmp::Reverse;")
        if self._uses_file_handle:
            imports.append("use std::fs::{File, OpenOptions};")
            imports.append("use std::io::{self, Read, Write, BufRead, BufReader, Seek, SeekFrom};")
        if self._uses_python_wrappers:
            imports.append("use pyo3::prelude::*;")
            imports.append("use pyo3::types::{PyDict, PyList, PyTuple};")
        if self._uses_serde_json:
            imports.append("use serde_json;")
        if self._uses_pythonize:
            imports.append("use pythonize;")
        if self._uses_csv:
            imports.append("use csv;")
        
        if imports:
            final_lines.extend(imports)
            # Only add extra padding if there are more sections coming up
            if self._uses_py_error or ir_mod.functions or ir_mod.classes or ir_mod.enums:
                final_lines.append("")

        # Async handling
        if self._uses_async:
            if self.config.async_runtime == AsyncRuntime.FUTURES:
                if "use futures::executor::block_on;" not in final_lines:
                    final_lines.insert(0, "use futures::executor::block_on;")
                if self.dependency_manager:
                    self.dependency_manager.add_dependency("futures", "0.3")
        is_submodule = bool(self.config and self.config.repo_root)
        if self._uses_py_error:
            if is_submodule:
                final_lines.append("use crate::errors::PyError;")
            else:
                final_lines.append("#[derive(Debug, Clone)]")
                final_lines.append("pub enum PyError {")
                final_lines.append("    Exception(String),")
                final_lines.append("    ValueError(String),")
                final_lines.append("    TypeError(String),")
                final_lines.append("    KeyError(String),")
                final_lines.append("    IndexError(String),")
                final_lines.append("    IOError(String),")
                final_lines.append("}")
                final_lines.append("")
                final_lines.append("impl std::fmt::Display for PyError {")
                final_lines.append("    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {")
                final_lines.append("        match self {")
                final_lines.append('            PyError::Exception(s) => write!(f, "Exception: {}", s),')
                final_lines.append('            PyError::ValueError(s) => write!(f, "ValueError: {}", s),')
                final_lines.append('            PyError::TypeError(s) => write!(f, "TypeError: {}", s),')
                final_lines.append('            PyError::KeyError(s) => write!(f, "KeyError: {}", s),')
                final_lines.append('            PyError::IndexError(s) => write!(f, "IndexError: {}", s),')
                final_lines.append('            PyError::IOError(s) => write!(f, "IOError: {}", s),')
                final_lines.append("        }")
                final_lines.append("    }")
                final_lines.append("}")
                final_lines.append("")
                final_lines.append("impl From<std::io::Error> for PyError {")
                final_lines.append("    fn from(err: std::io::Error) -> Self {")
                final_lines.append("        PyError::IOError(err.to_string())")
                final_lines.append("    }")
                final_lines.append("}")
                final_lines.append("")
                final_lines.append("impl From<std::num::ParseIntError> for PyError {")
                final_lines.append("    fn from(err: std::num::ParseIntError) -> Self {")
                final_lines.append("        PyError::ValueError(err.to_string())")
                final_lines.append("    }")
                final_lines.append("}")
                final_lines.append("")
                final_lines.append("impl From<std::num::ParseFloatError> for PyError {")
                final_lines.append("    fn from(err: std::num::ParseFloatError) -> Self {")
                final_lines.append("        PyError::ValueError(err.to_string())")
                final_lines.append("    }")
                final_lines.append("}")
                final_lines.append("")
                if self._uses_python_wrappers:
                    final_lines.append("impl From<PyError> for pyo3::PyErr {")
                    final_lines.append("    fn from(err: PyError) -> Self {")
                    final_lines.append("        match err {")
                    final_lines.append("            PyError::Exception(s) => pyo3::exceptions::PyException::new_err(s),")
                    final_lines.append("            PyError::ValueError(s) => pyo3::exceptions::PyValueError::new_err(s),")
                    final_lines.append("            PyError::TypeError(s) => pyo3::exceptions::PyTypeError::new_err(s),")
                    final_lines.append("            PyError::KeyError(s) => pyo3::exceptions::PyKeyError::new_err(s),")
                    final_lines.append("            PyError::IndexError(s) => pyo3::exceptions::PyIndexError::new_err(s),")
                    final_lines.append("            PyError::IOError(s) => pyo3::exceptions::PyOSError::new_err(s),")
                    final_lines.append("        }")
                    final_lines.append("    }")
                    final_lines.append("}")
                    final_lines.append("")

        if self._uses_try_result:
            if is_submodule:
                final_lines.append("use crate::errors::TryResult;")
            else:
                final_lines.append("pub enum TryResult<T> {")
                final_lines.append("    Normal,")
                final_lines.append("    Return(T),")
                final_lines.append("    Break,")
                final_lines.append("    Continue,")
                final_lines.append("}")
                final_lines.append("")

        if self._uses_file_handle:
            final_lines.append("struct FileHandle {")
            final_lines.append("    file: File,")
            final_lines.append("}")
            final_lines.append("")

        # Traits
        if self._uses_async:
            if self.config.async_runtime == AsyncRuntime.TOKIO:
                if self.dependency_manager:
                    self.dependency_manager.add_dependency("tokio", version="1.0", features=["full"])
            self._emit_async_runtime()
            final_lines.extend(self._lines)
            self._lines = []
            final_lines.append("")

        final_lines.extend(trait_lines)

        if self._uses_file_handle:
            final_lines.append("impl FileHandle {")
            final_lines.append("    fn open(path: &str, mode: &str) -> std::io::Result<Self> {")
            final_lines.append("        let file = match mode {")
            final_lines.append('            "r" => File::open(path)?,')
            final_lines.append('            "w" => File::create(path)?,')
            final_lines.append('            "a" => OpenOptions::new().append(true).open(path)?,')
            final_lines.append('            "rb" => File::open(path)?,')
            final_lines.append('            "wb" => File::create(path)?,')
            final_lines.append('            "ab" => OpenOptions::new().append(true).open(path)?,')
            final_lines.append("            _ => File::open(path)?,")
            final_lines.append("        };")
            final_lines.append("        Ok(FileHandle { file })")
            final_lines.append("    }")
            final_lines.append("")
            final_lines.append("    fn read(&mut self) -> std::io::Result<String> {")
            final_lines.append("        let mut contents = String::new();")
            final_lines.append("        self.file.read_to_string(&mut contents)?;")
            final_lines.append("        Ok(contents)")
            final_lines.append("    }")
            final_lines.append("")
            final_lines.append("    fn readline(&mut self) -> std::io::Result<String> {")
            final_lines.append("        let mut reader = BufReader::new(&self.file);")
            final_lines.append("        let mut line = String::new();")
            final_lines.append("        reader.read_line(&mut line)?;")
            final_lines.append("        Ok(line)")
            final_lines.append("    }")
            final_lines.append("")
            final_lines.append("    fn write(&mut self, content: &str) -> std::io::Result<()> {")
            final_lines.append("        self.file.write_all(content.as_bytes())")
            final_lines.append("    }")
            final_lines.append("")
            final_lines.append("    fn close(self) -> std::io::Result<()> {")
            final_lines.append("        Ok(())")
            final_lines.append("    }")
            final_lines.append("")
            final_lines.append("    fn tell(&mut self) -> std::io::Result<u64> {")
            final_lines.append("        self.file.stream_position()")
            final_lines.append("    }")
            final_lines.append("")
            final_lines.append("    fn seek(&mut self, pos: u64) -> std::io::Result<u64> {")
            final_lines.append("        self.file.seek(SeekFrom::Start(pos))")
            final_lines.append("    }")
            final_lines.append("}")
            final_lines.append("")

        final_lines.extend(class_lines)
        final_lines.extend(trait_impl_lines)
        final_lines.extend(enum_lines)
        final_lines.extend(func_lines)
        has_main_fn = any(f.name == "main" for f in self._current_module.functions)
        if stmt_lines or has_main_fn:
            # Python's main is always renamed to __py_main in Rust to avoid collision with entrypoint
            main_ir_name = "__py_main" if has_main_fn else ""
            
            if self._uses_async:
                if self.config.async_runtime == AsyncRuntime.TOKIO:
                    final_lines.append("#[tokio::main]")
                    final_lines.append("async fn main() -> Result<(), PyError> {")
                else:
                    final_lines.append("fn main() -> Result<(), PyError> {")
                    final_lines.append("    block_on(async {")
            else:
                final_lines.append("fn main() -> Result<(), PyError> {")
            
            # Indent statements and call __py_main
            indent = "        " if self._uses_async and self.config.async_runtime == AsyncRuntime.FUTURES else "    "
            for line in stmt_lines:
                final_lines.append(f"{indent}{line}")
            
            if main_ir_name:
                already_called = any(f"{main_ir_name}()" in line for line in stmt_lines)
                if not already_called:
                    call_kw = ".await" if self._uses_async else ""
                    final_lines.append(f"{indent}{main_ir_name}(){call_kw}?;")

            final_lines.append(f"{indent}Ok(())")
            
            # Close block_on if needed
            if self._uses_async and self.config.async_runtime == AsyncRuntime.FUTURES:
                final_lines.append("    })")

            final_lines.append("}")
            final_lines.append("")
        else:
            final_lines.extend(stmt_lines)

        if self._uses_python_wrappers:
            self._emit_python_boilerplate()
            final_lines.extend(self._lines)
            self._lines = []

        # Clean trailing whitespaces on each line, and drop trailing empty lines
        cleaned_lines = []
        for line in final_lines:
            cleaned_lines.append(line.rstrip())
        
        while cleaned_lines and not cleaned_lines[-1]:
            cleaned_lines.pop()
            
        return "\n".join(cleaned_lines) + "\n"

    def _gen_trait(self, trait: IRTraitDefinition) -> str:
        bases_str = " + ".join(trait.bases) if trait.bases else ""
        header = f"pub trait {trait.name}"
        if bases_str:
            header += f": {bases_str}"
        
        res = [f"{header} {{"]
        for method in trait.methods:
            params_str = ", ".join(
                f"{p.name}: {self._get_rust_type(p.type_)}" for p in method.params
            )
            self_ref = "&mut self" if method.mutates_self else "&self"
            if method.is_async:
                self._uses_async = True
            async_kw = "async " if method.is_async else ""
            sig = f"    {async_kw}fn {_mangle(method.name)}({self_ref}"
            if params_str:
                sig += f", {params_str}"
            # Traits always return Result<T, PyError> for Python-to-Rust mapping
            ret = self._get_rust_type(method.return_type)
            sig += f") -> Result<{ret}, PyError>;"
            res.append(sig)
        res.append("}")
        return "\n".join(res)

    def _gen_trait_impl(self, impl_def: IRTraitImpl) -> None:
        self._emit(f"impl {impl_def.trait_name} for {impl_def.target_name} {{")
        self._indent += 1
        for method in impl_def.methods:
            self._gen_method(method, is_trait_impl=True)
            self._emit("")
        self._indent -= 1
        self._emit("}")

    def _gen_class(self, cls: IRClassDefinition) -> None:
        type_params_str = ""
        if cls.type_params:
            tp_list = ", ".join(str(tp) for tp in cls.type_params)
            type_params_str = f"<{tp_list}>"

        if self._uses_serde_json:
            self._emit(f"#[derive(Clone, Debug, Serialize, Deserialize)]")
        else:
            self._emit(f"#[derive(Clone, Debug)]")
        self._emit(f"pub struct {cls.name}{type_params_str} {{")
        self._indent += 1
        for field_name, field_type in cls.fields:
            self._emit(f"pub {_mangle(field_name)}: {self._get_rust_type(field_type)},")
        self._indent -= 1
        self._emit("}")
        self._emit("")

        # Inherent Impl (Constructors and inherent methods)
        has_inherent_methods = (f"{cls.name}Trait" not in self._needed_traits) and any(m.name != "__init__" for m in cls.methods)
        if cls.constructors or has_inherent_methods:
            self._emit(f"impl{type_params_str} {cls.name}{type_params_str} {{")
            self._indent += 1
            for ctor in cls.constructors:
                self._gen_method(ctor, is_init=True)
            if has_inherent_methods:
                for m in cls.methods:
                    if m.name != "__init__":
                        self._gen_method(m)
            self._indent -= 1
            self._emit("}")
            self._emit("")

        # Trait Impls (Implement all traits in the hierarchy)
        # 1. Map trait names to their definitions for easy lookup
        all_trait_defs = {t.name: t for t in self._current_module.traits if t.name in self._needed_traits}
        
        # 2. Get all traits this class must implement (recursively)
        traits_to_impl = []
        queue = []
        if f"{cls.name}Trait" in self._needed_traits:
            queue.append(f"{cls.name}Trait")
        visited = set()
        while queue:
            t_name = queue.pop(0)
            if t_name in visited: continue
            visited.add(t_name)
            if t_name in all_trait_defs:
                traits_to_impl.append(all_trait_defs[t_name])
                queue.extend(all_trait_defs[t_name].bases)
        
        # 3. For each trait, find implementing methods in the class
        # Map method names in this class for easy lookup
        class_methods = {m.name: m for m in cls.methods}
        
        for trait in traits_to_impl:
            self._emit(f"impl {trait.name} for {cls.name} {{")
            self._indent += 1
            for tm in trait.methods:
                if tm.name in class_methods:
                    self._gen_method(class_methods[tm.name], is_trait_impl=True)
            self._indent -= 1
            self._emit("}")
            self._emit("")

        # 4. Handle magic methods -> std::fmt::Display / std::ops etc.
        if "__str__" in class_methods:
            self._emit(f"impl{type_params_str} std::fmt::Display for {cls.name}{type_params_str} {{")
            self._indent += 1
            self._emit("fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {")
            self._indent += 1
            self._emit("match self.__str__() {")
            self._indent += 1
            self._emit("Ok(s) => write!(f, \"{}\", s),")
            self._emit("Err(_) => Err(std::fmt::Error),")
            self._indent -= 1
            self._emit("}")
            self._indent -= 1
            self._emit("}")
            self._indent -= 1
            self._emit("}")
            self._emit("")

        # Arithmetic Mappings
        arith_maps = {
            "__add__": ("std::ops::Add", "add", "Output", "rhs"),
            "__sub__": ("std::ops::Sub", "sub", "Output", "rhs"),
            "__mul__": ("std::ops::Mul", "mul", "Output", "rhs"),
            "__truediv__": ("std::ops::Div", "div", "Output", "rhs"),
            "__mod__": ("std::ops::Rem", "rem", "Output", "rhs"),
        }
        for dunder, (trait, method, assoc_type, rhs_name) in arith_maps.items():
            if dunder in class_methods:
                m_def = class_methods[dunder]
                # Assume binary operator (self, other)
                rhs_type = self._get_rust_type(m_def.params[0].type_) if m_def.params else cls.name
                ret_type = self._get_rust_type(m_def.return_type)
                
                self._emit(f"impl{type_params_str} {trait}<{rhs_type}> for {cls.name}{type_params_str} {{")
                self._indent += 1
                self._emit(f"type {assoc_type} = {ret_type};")
                self._emit(f"fn {method}(self, rhs: {rhs_type}) -> Self::{assoc_type} {{")
                self._indent += 1
                # Call the dunder method. Dunder methods are fallible in Py2Rust.
                self._emit(f"self.{dunder}(rhs).unwrap()")
                self._indent -= 1
                self._emit("}")
                self._indent -= 1
                self._emit("}")
                self._emit("")

        # Comparison Mappings
        if "__eq__" in class_methods:
            m_def = class_methods["__eq__"]
            rhs_type = self._get_rust_type(m_def.params[0].type_) if m_def.params else cls.name
            self._emit(f"impl{type_params_str} PartialEq<{rhs_type}> for {cls.name}{type_params_str} {{")
            self._indent += 1
            self._emit(f"fn eq(&self, other: &{rhs_type}) -> bool {{")
            self._indent += 1
            # Call __eq__. Since it takes self by reference in Python, and returns PyResult<bool>
            # we need to handle the conversion.
            self._emit(f"self.__eq__(other.clone()).unwrap_or(false)")
            self._indent -= 1
            self._emit("}")
            self._indent -= 1
            self._emit("}")
            self._emit("")

        # Comparison Mappings: PartialOrd
        if "__lt__" in class_methods:
            m_def = class_methods["__lt__"]
            rhs_type = self._get_rust_type(m_def.params[0].type_) if m_def.params else cls.name
            self._emit(f"impl{type_params_str} PartialOrd<{rhs_type}> for {cls.name}{type_params_str} {{")
            self._indent += 1
            self._emit(f"fn partial_cmp(&self, other: &{rhs_type}) -> Option<std::cmp::Ordering> {{")
            self._indent += 1
            self._emit("if self.__lt__(other.clone()).unwrap_or(false) {")
            self._emit("    Some(std::cmp::Ordering::Less)")
            self._emit("} else if self == other {")
            self._emit("    Some(std::cmp::Ordering::Equal)")
            self._emit("} else {")
            self._emit("    Some(std::cmp::Ordering::Greater)")
            self._emit("}")
            self._indent -= 1
            self._emit("}")
            self._indent -= 1
            self._emit("}")
            self._emit("")

        # Hash Mapping
        if "__hash__" in class_methods:
            self._emit(f"impl{type_params_str} std::hash::Hash for {cls.name}{type_params_str} {{")
            self._indent += 1
            self._emit("fn hash<H: std::hash::Hasher>(&self, state: &mut H) {")
            self._indent += 1
            self._emit("let h = self.__hash__().unwrap_or(0);")
            self._emit("h.hash(state);")
            self._indent -= 1
            self._emit("}")
            self._indent -= 1
            self._emit("}")
            self._emit("")

    def _gen_method(self, func: IRFunction, is_init: bool = False, is_trait_impl: bool = False) -> None:
        self._uses_py_error = True
        self._mutated_vars = _collect_mutated_vars(func.body)
        decls, pre_declare = _collect_decls(func.body, self._uses_python_wrappers)

        # Wave 28: static methods have no self receiver
        is_static = getattr(func, "is_static", False)

        if is_init:
            param_strs = []
        elif is_static:
            param_strs = []  # no &self for @staticmethod
        elif "self" in self._mutated_vars:
            param_strs = ["&mut self"]
        else:
            param_strs = ["&self"]
        for p in func.params:
            mut = "mut " if p.name in func.mutated_params else ""
            param_strs.append(f"{mut}{_mangle(p.name)}: {self._get_rust_type(p.type_)}")
        params = ", ".join(param_strs)

        type_params_str = ""
        if func.type_params:
            tp_list = ", ".join(str(tp) for tp in func.type_params)
            type_params_str = f"<{tp_list}>"

        if is_init:
            self._emit(f"pub fn new({params}) -> Result<Self, PyError> {{")
        else:
            ret = self._get_rust_type(func.return_type)
            if func.is_async:
                self._uses_async = True
            async_kw = "async " if func.is_async else ""
            pub_kw = "" if is_trait_impl else "pub "
            self._emit(f"{pub_kw}{async_kw}fn {_mangle(func.name)}{type_params_str}({params}) -> Result<{ret}, PyError> {{")

        self._indent += 1

        self._decl_types = dict(decls)
        # We need to track which variables have been pre-declared to avoid double-declaring
        self._pre_declared = set()

        # Pre-declare only variables that need it (nested definitions)
        for name in pre_declare:
            if name == "_":
                continue
            if name not in self._decl_types:
                continue
            type_ = self._decl_types[name]
            mut = "mut " if name in self._mutated_vars else ""
            default = self._default_value(type_)
            rust_t = self._get_rust_type(type_)
            if not default or not str(default).strip():
                self._emit(f"let {mut}{_mangle(name)}: {rust_t};")
            else:
                self._emit(f"let {mut}{_mangle(name)}: {rust_t} = {default};")
            self._pre_declared.add(name)

        if self._pre_declared:
            self._emit_blank()

        if is_init:
            self._gen_init_body(func)
        else:
            self._at_top_level = True
            for stmt in func.body:
                self._gen_stmt(stmt)
            
            if not func.body or not isinstance(func.body[-1], IRReturn):
                dv = self._default_value(func.return_type)
                self._emit(f"Ok({dv})")

        self._indent -= 1
        self._emit("}")

    def _gen_init_body(self, func: IRFunction) -> None:
        field_values = {}
        other_stmts = []
        for stmt in func.body:
            if isinstance(stmt, IRFieldAssign):
                field_values[_mangle(stmt.field)] = self._strip_parens(
                    self._gen_expr(stmt.value)
                )
            else:
                other_stmts.append(stmt)
        for stmt in other_stmts:
            self._gen_stmt(stmt)
        
        # Build the struct
        fields = ", ".join(f"{f}: {v}" for f, v in field_values.items())
        self._emit(f"Ok(Self {{ {fields} }})")

    def _gen_function(self, func: IRFunction) -> None:
        if self._has_yield(func.body):
            # First, emit the struct and its implementation!
            self._gen_generator_struct(func)
            
            # Now, generate the original function which simply returns Ok(Box::new(Struct::new(...)))!
            is_main = func.name == "main"
            t_params = f"<{', '.join(p.name + ': Clone' for p in func.type_params)}>" if func.type_params else ""
            ret_type_str = self._get_rust_type(func.return_type)
            
            param_strs = []
            for p in func.params:
                mut = "mut " if p.name in func.mutated_params else ""
                param_strs.append(f"{mut}{_mangle(p.name)}: {self._get_rust_type(p.type_)}")
            params = ", ".join(param_strs)
            
            self._emit(f"pub fn {func.name}{t_params}({params}) -> Result<{ret_type_str}, PyError> {{")
            self._indent += 1
            
            struct_name = "".join(part.capitalize() for part in func.name.split("_")) + "Generator"
            args = ", ".join(_mangle(p.name) for p in func.params)
            self._emit(f"Ok(Box::new({struct_name}::new({args})))")
            
            self._indent -= 1
            self._emit("}")
            return

        self._uses_py_error = True
        self._mutated_vars = _collect_mutated_vars(func.body)
        decls, pre_declare = _collect_decls(func.body, self._uses_python_wrappers)

        param_strs = []
        for p in func.params:
            mut = "mut " if p.name in func.mutated_params else ""
            param_strs.append(f"{mut}{_mangle(p.name)}: {self._get_rust_type(p.type_)}")
        params = ", ".join(param_strs)

        is_main = func.name == "main"
        self._in_main = is_main
        t_params = f"<{', '.join(p.name + ': Clone' for p in func.type_params)}>" if func.type_params else ""
        
        if is_main:
            ret_type_str = "()"
            self._current_fn_return_type = ret_type_str
            fn_name = "__py_main" 
            if hasattr(self.config, "translation_context") and self.config.translation_context:
                self.config.translation_context.add_name_mapping("main", "__py_main")
            async_kw = "async " if func.is_async else ""

            self._emit(f"pub {async_kw}fn {fn_name}{t_params}({params}) -> Result<{ret_type_str}, PyError> {{")
            if func.is_async:
                self._uses_async = True
        else:
            ret_type_str = self._get_rust_type(func.return_type)
            self._current_fn_return_type = ret_type_str
            if func.is_async:
                self._uses_async = True
            async_kw = "async " if func.is_async else ""
            self._emit(f"pub {async_kw}fn {func.name}{t_params}({params}) -> Result<{ret_type_str}, PyError> {{")

        self._indent += 1

        self._decl_types = dict(decls)
        # We need to track which variables have been pre-declared to avoid double-declaring
        self._pre_declared = set()

        # Pre-declare only for/while loop targets
        for name in pre_declare:
            if name == "_":
                continue
            if name not in self._decl_types:
                continue
            type_ = self._decl_types[name]
            mut = "mut " if name in self._mutated_vars else ""
            # For now, keep default values for safety (Python dynamic initialization)
            default = self._default_value(type_)
            rust_t = self._get_rust_type(type_)
            if not default or not str(default).strip():
                self._emit(f"let {mut}{_mangle(name)}: {rust_t};")
            else:
                self._emit(f"let {mut}{_mangle(name)}: {rust_t} = {default};")
            self._pre_declared.add(name)

        if self._pre_declared:
            self._emit_blank()

        self._at_top_level = True
        for stmt in func.body:
            self._gen_stmt(stmt)

        if not func.body or not isinstance(func.body[-1], IRReturn):
            if self._in_main:
                self._emit("Ok(())")
            else:
                dv = self._default_value(func.return_type)
                self._emit(f"Ok({dv})")

        if is_main and func.is_async:
            pass # The wrapper handles the closing brace for the function body already

        self._indent -= 1
        self._emit("}")

        if not is_main and func.name.startswith("test_") and not func.params:
            self._emit_blank()
            self._emit("#[cfg(test)]")
            self._emit("#[test]")
            self._emit(f"fn _test_wrapper_{func.name}() {{")
            self._indent += 1
            self._emit(f"{func.name}().unwrap();")
            self._indent -= 1
            self._emit("}")

    def _default_value(self, ir_type) -> str:
        if isinstance(ir_type, IRUnitType):
            return "()"
        if isinstance(ir_type, IRIntType):
            return "0"
        if isinstance(ir_type, IRFloatType):
            return "0.0"
        if isinstance(ir_type, IRBoolType):
            return "false"
        if isinstance(ir_type, IRStrType):
            return "String::new()"
        if isinstance(ir_type, IRListType):
            return f"Vec::<{self._get_rust_type(ir_type.element_type)}>::new()"
        if isinstance(ir_type, IRDictType):
            return f"HashMap::<{self._get_rust_type(ir_type.key_type)}, {self._get_rust_type(ir_type.value_type)}>::new()"
        if isinstance(ir_type, IRClassType):
            rust_type = self._get_rust_type(ir_type)
            if "dyn " in rust_type:
                # Trait objects cannot be easily instantiated with a default.
                # Return empty string to signal uninitialized pre-declaration.
                return ""
            return f"{rust_type}::new()"
        if isinstance(ir_type, IRFileType):
            if self._uses_python_wrappers:
                return "ExternalObject::default()"
            return 'FileHandle::open("", "r").unwrap()'
        if isinstance(ir_type, IRExternalPythonType):
            if ir_type.is_local:
                rust_type = self._get_rust_type(ir_type)
                return f"{rust_type}::new()"
            return "ExternalObject::default()"
        return "0"

    def _gen_stmt(self, stmt) -> None:
        if isinstance(stmt, IRVarDecl):
            if hasattr(self, "_generator_fields") and self._generator_fields and stmt.name in self._generator_fields:
                val = self._gen_expr(stmt.value, stmt.type_)
                self._emit(f"self.{_mangle(stmt.name)} = {val};")
                return
            # Skip if variable was pre-declared at function level
            if stmt.name in self._pre_declared:
                # Still need to perform the assignment if there is one
                val = self._gen_expr(stmt.value, stmt.type_)
                self._emit(f"{_mangle(stmt.name)} = {val};")
                return
            expr_val = self._gen_expr(stmt.value, stmt.type_)
            val = expr_val if isinstance(stmt.value, IRTupleLit) else self._strip_parens(expr_val)
            is_collection = isinstance(stmt.type_, (IRDequeType, IRHeapType))
            if stmt.name == "_":
                self._emit(f"{val};")
            elif stmt.name in self._mutated_vars or is_collection:
                if val:
                    self._emit(f"let mut {_mangle(stmt.name)}: {self._get_rust_type(stmt.type_)} = {val};")
                else:
                    self._emit(f"let mut {_mangle(stmt.name)}: {self._get_rust_type(stmt.type_)};")
            else:
                if val:
                    self._emit(f"let {_mangle(stmt.name)}: {self._get_rust_type(stmt.type_)} = {val};")
                else:
                    self._emit(f"let {_mangle(stmt.name)}: {self._get_rust_type(stmt.type_)};")

        elif isinstance(stmt, IRAssign):
            target_type = self._decl_types.get(stmt.target)
            if isinstance(target_type, IRFloatType):
                val = self._gen_expr_as_float(stmt.value)
            else:
                val = self._gen_expr(stmt.value)
                if not isinstance(stmt.value, IRTupleLit):
                    val = self._strip_parens(val)
            target_name = _mangle(stmt.target)
            if hasattr(self, "_generator_fields") and self._generator_fields and stmt.target in self._generator_fields:
                target_name = f"self.{target_name}"
            self._emit(f"{target_name} = {val};")

        elif isinstance(stmt, IRFieldAssign):
            e = self._gen_expr(stmt.value)
            val = e if isinstance(stmt.value, IRTupleLit) else self._strip_parens(e)
            obj_name = "self" if stmt.obj == "self" else _mangle(stmt.obj)
            
            # Check if object is ExternalObject
            obj_type = self._decl_types.get(stmt.obj)
            is_ext = False
            if isinstance(obj_type, IRClassType) and obj_type.name == "ExternalObject":
                is_ext = True
            elif isinstance(obj_type, IRExternalPythonType) and not obj_type.is_local:
                is_ext = True
            
            if is_ext:
                self._emit(f"{obj_name}.setattr(\"{stmt.field}\", {val})?;")
            else:
                self._emit(f"{obj_name}.{_mangle(stmt.field)} = {val};")

        elif isinstance(stmt, IRAugAssign):
            val = self._gen_expr(stmt.value)
            if not isinstance(stmt.value, IRTupleLit):
                val = self._strip_parens(val)
            target_name = _mangle(stmt.target)
            if hasattr(self, "_generator_fields") and self._generator_fields and stmt.target in self._generator_fields:
                target_name = f"self.{target_name}"
            self._emit(f"{target_name} {stmt.op} {val};")

        elif isinstance(stmt, IRIf):
            reachable = _get_reachable_if_branches(stmt)
            if not reachable:
                pass
            else:
                first_cond, first_body = reachable[0]
                if first_cond is None:
                    cond = "true"
                elif isinstance(first_cond, IRBoolLit) and first_cond.value:
                    cond = "true"
                else:
                    cond = self._strip_parens(self._gen_condition(first_cond))
                
                self._emit(f"if {cond} {{")
                self._indent += 1
                old_top_level = self._at_top_level
                self._at_top_level = False
                for s in first_body:
                    self._gen_stmt(s)
                self._at_top_level = old_top_level
                self._indent -= 1
                
                for cond_expr, body in reachable[1:]:
                    if cond_expr is None:
                        self._emit("} else {")
                    elif isinstance(cond_expr, IRBoolLit) and cond_expr.value:
                        self._emit("} else if true {")
                    else:
                        ec = self._strip_parens(self._gen_condition(cond_expr))
                        self._emit(f"}} else if {ec} {{")
                    
                    self._indent += 1
                    self._at_top_level = False
                    for s in body:
                        self._gen_stmt(s)
                    self._at_top_level = old_top_level
                    self._indent -= 1
                self._emit("}")

        elif isinstance(stmt, IRWhile):
            self._loop_depth += 1
            cond = self._strip_parens(self._gen_condition(stmt.condition))
            label = getattr(stmt, "label", "") or f"__loop_{id(stmt)}"
            self._emit(f"'{label}: while {cond} {{")
            self._indent += 1
            old_top_level = self._at_top_level
            self._at_top_level = False
            for s in stmt.body:
                self._gen_stmt(s)
            self._at_top_level = old_top_level
            self._indent -= 1
            self._emit("}")
            self._loop_depth -= 1

        elif isinstance(stmt, IRForRange):
            start = self._gen_expr(stmt.start)
            stop = self._gen_expr(stmt.stop)
            step_is_one = stmt.step is None
            
            # ForRange always has exactly one target name
            target_names = _get_names(stmt.target)
            target_name = target_names[0] if target_names else "unknown"

            # Use a more readable internal loop variable to avoid shadowing outer scope
            loop_var = f"__i_{target_name}"

            if step_is_one:
                # Wrap in a block so the inner loop variable doesn't leak
                self._emit("{")
                self._loop_depth += 1
                self._indent += 1
                # DO NOT redeclare the target here if it already exists in parent scope
                self._emit(f"for {loop_var} in {start}..{stop} {{")
                self._indent += 1
                self._emit(f"{_mangle(target_name)} = {loop_var};")
                old_top_level = self._at_top_level
                self._at_top_level = False
                for s in stmt.body:
                    self._gen_stmt(s)
                self._at_top_level = old_top_level
                self._indent -= 1
                self._emit("}")
                self._loop_depth -= 1
                self._indent -= 1
                self._emit("}")
            else:
                step = self._gen_expr(stmt.step)
                label = getattr(stmt, "label", "") or f"__loop_{id(stmt)}"
                self._emit("{")
                self._loop_depth += 1
                self._indent += 1
                self._emit(f"let __stop = {stop};")
                self._emit(f"let __step = {step};")
                # Update target directly instead of redeclaring
                self._emit(f"{_mangle(target_name)} = {start};")
                self._emit(
                    f"'{label}: while if (__step) > 0 {{ {_mangle(target_name)} < (__stop) }} else {{ {_mangle(target_name)} > (__stop) }} {{"
                )
                self._indent += 1
                old_top_level = self._at_top_level
                self._at_top_level = False
                for s in stmt.body:
                    self._gen_stmt(s)
                self._at_top_level = old_top_level
                self._emit(f"{_mangle(target_name)} += __step;")
                self._indent -= 1
                self._emit("}")
                self._loop_depth -= 1
                self._indent -= 1
                self._emit("}")

        elif isinstance(stmt, IRTupleUnpack):
            val = self._gen_expr(stmt.value)
            targets = ", ".join(_mangle(t) for t in stmt.targets)
            self._emit(f"let ({targets}) = {val};")

        elif isinstance(stmt, IRForIter):
            iterable = self._gen_expr(stmt.iterable)
            is_direct_iter = False
            if isinstance(stmt.iterable, IRFunctionCall):
                if stmt.iterable.name in ("zip", "enumerate", "map", "reversed"):
                    is_direct_iter = True
            elif isinstance(stmt.iterable, (IRMap, IRFilter, IRGeneratorExp)):
                is_direct_iter = True
            elif isinstance(stmt.iterable_type, (IRIteratorType, IRGeneratorType)):
                is_direct_iter = True

            is_ext = False
            if isinstance(stmt.iterable_type, IRClassType) and stmt.iterable_type.name == "ExternalObject":
                is_ext = True
            elif isinstance(stmt.iterable_type, IRExternalPythonType) and not stmt.iterable_type.is_local:
                is_ext = True

            if isinstance(stmt.iterable_type, IRDictType):
                iter_expr = f"{iterable}.keys()"
            elif isinstance(stmt.iterable_type, IRStrType):
                iter_expr = f"{iterable}.chars().map(|c| c.to_string())"
            elif is_direct_iter:
                iter_expr = iterable
            elif is_ext:
                iter_expr = f"{iterable}.iter()?"
            else:
                # Assuming list or generic collection
                iter_expr = f"&{iterable}"

            label = getattr(stmt, "label", "") or f"__loop_{id(stmt)}"
            self._emit("{")
            self._loop_depth += 1
            self._indent += 1
            
            loop_var = "__loop_val"
            self._emit(f"'{label}: for {loop_var} in {iter_expr} {{")
            self._indent += 1

            if isinstance(stmt.target, (str, IRName)):
                t_name = stmt.target.name if isinstance(stmt.target, IRName) else stmt.target
                t_type = self._decl_types.get(t_name)
                rust_t = self._get_rust_type(t_type) if t_type else ""
                
                if "dyn " in rust_t and not rust_t.startswith("Box<"):
                    # Trait object reference: usually from a Boxed collection
                    it_t_str = self._get_rust_type(stmt.iterable_type) if stmt.iterable_type else ""
                    if "Box<dyn " in it_t_str:
                        self._emit(f"{_mangle(t_name)} = &**{loop_var};")
                    else:
                        self._emit(f"{_mangle(t_name)} = {loop_var};")
                else:
                    self._emit(f"{_mangle(t_name)} = {loop_var}.clone();")
            elif isinstance(stmt.target, IRTupleLit):
                temp_names = [f"__tmp_{i}" for i in range(len(stmt.target.elements))]
                temps_str = ", ".join(temp_names)
                self._emit(f"let ({temps_str}) = {loop_var}.clone();")
                for i, e in enumerate(stmt.target.elements):
                    if isinstance(e, IRName):
                        self._emit(f"{_mangle(e.name)} = {temp_names[i]}.clone();")

            old_top_level = self._at_top_level
            self._at_top_level = False
            for s in stmt.body:
                self._gen_stmt(s)
            self._at_top_level = old_top_level

            self._indent -= 1
            self._emit("}")
            self._loop_depth -= 1
            self._indent -= 1
            self._emit("}")

        elif isinstance(stmt, IRReturn):
            val_str = ""
            if self._in_main:
                if stmt.value is not None:
                    e = self._gen_expr(stmt.value)
                    val = e if isinstance(stmt.value, IRTupleLit) else self._strip_parens(e)
                    
                    import re
                    is_simple = re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', val.strip()) or val.strip().isdigit() or val.strip() in ("true", "false", "None", "()", '""', "''")
                    if is_simple:
                        val_str = "()"
                    else:
                        val_str = f"{{ {val}; () }}"
                else:
                    val_str = "()"
            elif stmt.value is None:
                val_str = self._default_value(stmt.result_type)
            else:
                if isinstance(stmt.result_type, IRFloatType):
                    val_str = self._gen_expr_as_float(stmt.value)
                else:
                    e = self._gen_expr(stmt.value)
                    val_str = e if isinstance(stmt.value, IRTupleLit) else self._strip_parens(e)
            
            if self._inside_try > 0:
                self._emit(f"return Ok(TryResult::Return(({val_str})));")
            else:
                self._emit(f"return Ok({val_str});")

        elif isinstance(stmt, IRTryExcept):
            self._uses_py_error = True
            self._uses_try_result = True
            self._emit("{")
            self._indent += 1
            self._emit(f"let __result = (|| -> Result<TryResult<{self._current_fn_return_type}>, PyError> {{")
            self._inside_try += 1
            self._indent += 1
            for s in stmt.body:
                self._gen_stmt(s)
            self._emit("Ok(TryResult::Normal)")
            self._indent -= 1
            self._inside_try -= 1
            self._emit("})();")
            
            self._emit("match __result {")
            self._indent += 1
            self._emit("Ok(TryResult::Return(v)) => return Ok(v),")
            if self._loop_depth > 0:
                self._emit("Ok(TryResult::Break) => break,")
                self._emit("Ok(TryResult::Continue) => continue,")
            else:
                self._emit('Ok(TryResult::Break) => panic!("break outside loop"),')
                self._emit('Ok(TryResult::Continue) => panic!("continue outside loop"),')
            self._emit("Ok(TryResult::Normal) => {}")
            
            # Catch-all for now
            if stmt.handlers:
                h_type, h_name, h_body = stmt.handlers[0]
                binder = _mangle(h_name) if h_name else "_"
                self._emit(f"Err({binder}) => {{")
                self._indent += 1
                if h_name:
                    self._emit(f"let {binder} = {binder}.clone();")
                for s in h_body:
                    self._gen_stmt(s)
                self._indent -= 1
                self._emit("}")
            else:
                self._emit("Err(e) => return Err(e),")
                
            self._indent -= 1
            self._emit("}")
            self._indent -= 1
            self._emit("}")

        elif isinstance(stmt, IRRaise):
            self._uses_py_error = True
            if stmt.value:
                val = self._gen_expr(stmt.value)
                if getattr(stmt, "cause", None):
                    cause_val = self._gen_expr(stmt.cause)
                    if "PyError::" in val:
                        self._emit(f"return Err({val}); /* warning: cause lost */")
                    else:
                        self._emit(f'return Err(PyError::Exception(format!("{{}} (caused by {{}})", {val}, {cause_val})));')
                else:
                    if "PyError::" in val:
                        self._emit(f"return Err({val});")
                    else:
                        self._emit(f"return Err(PyError::Exception({val}));")
            else:
                self._emit('return Err(PyError::Exception("Exception raised".to_string()));')

        elif isinstance(stmt, IRPrint):
            vals = [self._gen_expr(v) for v in stmt.values]
            
            sep_expr = self._gen_expr(stmt.sep) if stmt.sep else None
            end_expr = self._gen_expr(stmt.end) if stmt.end else None

            # Optimization: simple case print(v1, v2, ...) or print()
            if not sep_expr and (not end_expr or (isinstance(stmt.end, IRStrLit) and stmt.end.value == "\n")):
                if not vals:
                    self._emit('println!("");')
                else:
                    fmts = []
                    for val_type in stmt.value_types:
                        fmts.append("{:?}" if isinstance(val_type, (IRListType, IRDictType)) else "{}")
                    fmt_str = " ".join(fmts)
                    vals_str = ", ".join(vals)
                    self._emit(f'println!("{fmt_str}", {vals_str});')
            else:
                # Complex case with sep or custom end
                for i, (val, vtype) in enumerate(zip(vals, stmt.value_types)):
                    if i > 0:
                        if sep_expr:
                            self._emit(f'print!("{{}}", {sep_expr});')
                        else:
                            self._emit(f'print!(" ");')
                    
                    fmt = "{:?}" if isinstance(vtype, (IRListType, IRDictType)) else "{}"
                    self._emit(f'print!("{fmt}", {val});')
                
                if end_expr:
                    self._emit(f'print!("{{}}", {end_expr});')
                else:
                    self._emit('println!("");')

        elif isinstance(stmt, IRWith):
            self._gen_with(stmt)

        elif isinstance(stmt, IRAssert):
            self._gen_assert(stmt)

        elif isinstance(stmt, IRGlobal):
            self._gen_global(stmt)

        elif isinstance(stmt, IRNonlocal):
            self._gen_nonlocal(stmt)

        elif isinstance(stmt, IRBreak):
            label = stmt.label if hasattr(stmt, "label") and stmt.label else None
            if self._inside_try > 0:
                self._emit("return Ok(TryResult::Break);")
            else:
                if label:
                    self._emit(f"break '{label};")
                else:
                    self._emit("break;")

        elif isinstance(stmt, IRContinue):
            label = stmt.label if hasattr(stmt, "label") and stmt.label else None
            if self._inside_try > 0:
                self._emit("return Ok(TryResult::Continue);")
            else:
                if label:
                    self._emit(f"continue '{label};")
                else:
                    self._emit("continue;")

        elif isinstance(stmt, IRDictDelete):
            target = self._gen_expr(stmt.target)
            key = self._gen_expr(stmt.key)
            self._emit(f"{target}.remove(&{key});")

        elif isinstance(stmt, IRSubscriptAssign):
            final_idx = self._strip_parens(self._gen_expr(stmt.index))
            value_val = self._gen_expr(stmt.value)

            # Handle ExternalObject indexing
            target_type = self._decl_types.get(stmt.target) if isinstance(stmt.target, str) else getattr(stmt.target, "result_type", None)
            is_ext = False
            if isinstance(target_type, IRClassType) and target_type.name == "ExternalObject":
                is_ext = True
            elif isinstance(target_type, IRExternalPythonType) and not target_type.is_local:
                is_ext = True
            
            if is_ext:
                target = self._gen_expr(stmt.target)
                self._emit(f"{target}.setitem({final_idx}, {value_val})?;")
                return

            # Handle user-defined assignment via dunder methods
            if stmt.trait_info and stmt.trait_info[0] == "IndexMut":
                target = self._gen_expr(stmt.target)
                self._emit(f"{target}.__setitem__({final_idx}, {value_val})?;")
                return
            
            # Recursive target generation for deep updates
            def get_mut_target(node):
                if isinstance(node, IRName):
                    self._mutated_vars.add(node.name)
                    return _mangle(node.name)
                if isinstance(node, IRSubscript):
                    inner = get_mut_target(node.value)
                    idx = self._strip_parens(self._gen_expr(node.index))
                    if isinstance(node.value_type, IRDictType):
                        return f"({inner}.get_mut(&{idx}).unwrap())"
                    return f"(&mut {inner}[{idx} as usize])"
                return self._gen_expr(node)

            target_expr = get_mut_target(stmt.target)
            
            # Check the type of the IMMEDIATE container being updated
            container_type = stmt.value_type # This is set in IRBuilder to the container's element/value type?
            # Wait, IRSubscriptAssign.value_type is the type of the VALUE being assigned?
            # No, let's check IR node definition.

            # Actually, we can check the target's type if it's a subscript
            target_is_dict = False
            if isinstance(stmt.target, IRSubscript):
                # If target is d[k], and we assign d[k][final_idx] = v, 
                # then target_expr refers to d[k] (mutably).
                # We need to know if d[k] is a dict.
                if isinstance(stmt.value_type, IRDictType):
                     # This is confusing. Let's use a simpler check.
                     pass

            # Fallback: if we are assigning to a dict, use .insert()
            # We can use the type info from the IR builder if available.
            # For now, let's check if the target expr "looks like" a call that returns a dict.
            # Better: IRSubscriptAssign should carry information about whether the target is a dict.
            
            # Re-evaluating: let's use the same logic as existing shallow assignment but recursive
            if isinstance(stmt.target, IRSubscript):
                # Target is d[k], so we are doing d[k][final_idx] = value
                # get_mut_target(stmt.target) returns "d.get_mut(&k).unwrap()"
                # We need to know if d[k] is a dict to use .insert()
                # IRSubscript has result_type.
                if isinstance(stmt.target.result_type, IRDictType):
                    self._emit(f"{target_expr}.insert({final_idx}, {value_val});")
                elif isinstance(stmt.target.result_type, IRStrType):
                    adjusted_idx = f"(if {final_idx} < 0 {{ {final_idx} + {target_expr}.chars().count() as i32 }} else {{ {final_idx} }})"
                    byte_start = f"{target_expr}.chars().take({adjusted_idx} as usize).map(|c| c.len_utf8()).sum::<usize>()"
                    byte_end = f"{target_expr}.chars().take(({adjusted_idx} + 1) as usize).map(|c| c.len_utf8()).sum::<usize>()"
                    self._emit(f"{target_expr}.replace_range({byte_start}..{byte_end}, &{value_val});")
                else:
                    self._emit(f"{target_expr}[{final_idx} as usize] = {value_val};")
            else:
                # Shallow assignment: container[final_idx] = value
                target_expr = self._gen_expr(stmt.target)
                is_dict = False
                if isinstance(stmt.target, IRName):
                    self._mutated_vars.add(stmt.target.name)
                    target_type = self._decl_types.get(stmt.target.name)
                    if isinstance(target_type, IRDictType):
                        is_dict = True
                
                if is_dict:
                    self._emit(f"{target_expr}.insert({final_idx}, {value_val});")
                else:
                    self._emit(f"{target_expr}[{final_idx} as usize] = {value_val};")

        elif isinstance(stmt, IRMatchStmt):
            self._gen_match_stmt(stmt)

        elif isinstance(stmt, IREnumDef):
            # Already handled in top-level generation
            pass

        elif isinstance(stmt, IRExpr):
            expr = self._gen_expr(stmt)
            self._emit(f"{expr};")

        else:
            raise ValueError(f"Unsupported IR statement: {type(stmt).__name__}")

    def _gen_enum(self, enum_def: IREnumDef):
        self._emit("#[derive(Debug, Clone, PartialEq)]")
        self._emit(f"pub enum {enum_def.name} {{")
        self._indent += 1
        for name, _ in enum_def.variants:
            self._emit(f"{name},")
        self._indent -= 1
        self._emit("}")
        self._emit("")

    def _gen_match_stmt(self, match_stmt: IRMatchStmt):
        subject = self._gen_expr(match_stmt.subject)
        self._emit(f"match {subject} {{")
        self._indent += 1
        has_catch_all = False
        for case in match_stmt.cases:
            pattern = self._gen_match_pattern(case.pattern)
            # Check if this case is a catch-all (no guard and wildcard/name pattern)
            if not case.guard and isinstance(
                case.pattern, (IRWildcardPattern, IRNamePattern)
            ):
                has_catch_all = True

            guard = f" if {self._gen_expr(case.guard)}" if case.guard else ""
            self._emit(f"{pattern}{guard} => {{")
            self._indent += 1
            for stmt in case.body:
                self._gen_stmt(stmt)
            self._indent -= 1
            self._emit("},")

        # Ensure exhaustiveness if no catch-all was found
        if not has_catch_all:
            self._emit("_ => {},")

        self._indent -= 1
        self._emit("}")

    def _gen_with(self, stmt: IRWith):
        self._emit("{")
        self._indent += 1
        for item in stmt.items:
            ctx_expr = self._gen_expr(item.context_expr)
            kind = item.ctx_kind

            if kind == "file":
                # RAII via FileHandle: let [mut] <var> = FileHandle::open(...)?;
                if item.optional_vars:
                    target_names = _get_names(item.optional_vars)
                    is_mut = any(name in self._mutated_vars for name in target_names)
                    mut_prefix = "mut " if is_mut else ""
                    var = self._gen_expr(item.optional_vars)
                    self._emit(f"let {mut_prefix}{var} = {ctx_expr};")
                else:
                    self._emit(f"let _ = {ctx_expr};")

            elif kind == "mutex":
                # RAII via MutexGuard: let _guard = <lock>.lock().unwrap();
                if item.optional_vars:
                    guard_name = self._gen_expr(item.optional_vars)
                    self._emit(f"let {guard_name} = {ctx_expr}.lock().unwrap();")
                else:
                    self._emit(f"let _guard = {ctx_expr}.lock().unwrap();")

            else:
                # Generic context manager: __enter__() on enter, __exit__() on scope exit
                if item.optional_vars:
                    target_names = _get_names(item.optional_vars)
                    is_mut = any(name in self._mutated_vars for name in target_names)
                    mut_prefix = "mut " if is_mut else ""
                    var = self._gen_expr(item.optional_vars)
                    self._emit(f"// Python context manager: __enter__/__exit__ via RAII")
                    self._emit(f"let {mut_prefix}{var} = {ctx_expr};")
                else:
                    self._emit(f"// Python context manager: __enter__/__exit__ via RAII")
                    self._emit(f"let _ = {ctx_expr};")

        for s in stmt.body:
            self._gen_stmt(s)

        self._indent -= 1
        self._emit("}")

    def _gen_assert(self, stmt: IRAssert) -> None:
        test = self._gen_expr(stmt.test)
        if stmt.msg:
            msg = self._gen_expr(stmt.msg)
            self._emit(f'assert!({test}, "{{}}", {msg});')
        else:
            self._emit(f"assert!({test});")

    def _gen_global(self, stmt: IRGlobal) -> None:
        names = ", ".join(stmt.names)
        self._emit(f"// WARNING: Python 'global' for [{names}] is not fully supported in Rust's ownership model.")
        self._emit(f"// It usually indicates shared state which should be handled via Arc<Mutex<T>> or passed as arguments.")

    def _gen_nonlocal(self, stmt: IRNonlocal) -> None:
        names = ", ".join(stmt.names)
        self._emit(f"// WARNING: Python 'nonlocal' for [{names}] is not fully supported in Rust's ownership model.")
        self._emit(f"// Consider using a mutable closure capture or Cell/RefCell if mutation is needed.")

    def _gen_match_pattern(self, pattern: IRMatchPattern) -> str:
        if isinstance(pattern, IRValuePattern):
            return self._gen_expr(pattern.value)
        elif isinstance(pattern, IRNamePattern):
            return _mangle(pattern.name)
        elif isinstance(pattern, IRWildcardPattern):
            return "_"
        elif isinstance(pattern, IROrPattern):
            return " | ".join(self._gen_match_pattern(p) for p in pattern.patterns)
        elif isinstance(pattern, IRAsPattern):
            inner = self._gen_match_pattern(pattern.pattern)
            return f"{inner} @ {_mangle(pattern.name)}"
        elif isinstance(pattern, IRClassPattern):
            # For ADTs (Enums), it's variant name
            return f"{pattern.class_name}"
        return "_"

    def _emit_python_boilerplate(self):
        self._lines.extend(PYTHON_BOILERPLATE_LINES)
        self._lines.append("")

    def _emit_async_runtime(self) -> None:
        self._emit("mod py_async {")
        self._indent += 1
        self._emit("use std::future::Future;")
        self._emit("use std::pin::Pin;")
        self._emit("use std::task::{Context, Poll, RawWaker, RawWakerVTable, Waker};")
        self._emit("")
        self._emit("pub fn block_on<F: Future>(mut future: F) -> F::Output {")
        self._indent += 1
        self._emit("let mut future = unsafe { Pin::new_unchecked(&mut future) };")
        self._emit("let waker = unsafe { Waker::from_raw(null_waker()) };")
        self._emit("let mut cx = Context::from_waker(&waker);")
        self._emit("loop {")
        self._indent += 1
        self._emit("match future.as_mut().poll(&mut cx) {")
        self._indent += 1
        self._emit("Poll::Ready(val) => return val,")
        self._emit("Poll::Pending => {}")
        self._indent -= 1
        self._emit("}")
        self._indent -= 1
        self._emit("}")
        self._indent -= 1
        self._emit("}")
        self._emit("")
        self._emit("fn null_waker() -> RawWaker {")
        self._indent += 1
        self._emit("fn clone(_: *const ()) -> RawWaker { null_waker() }")
        self._emit("fn wake(_: *const ()) {}")
        self._emit("fn wake_by_ref(_: *const ()) {}")
        self._emit("fn drop(_: *const ()) {}")
        self._emit("static VTABLE: RawWakerVTable = RawWakerVTable::new(clone, wake, wake_by_ref, drop);")
        self._emit("RawWaker::new(std::ptr::null(), &VTABLE)")
        self._indent -= 1
        self._emit("}")
        self._indent -= 1
        self._emit("}")


def generate_rust(module: IRModule, dependency_manager=None, config: CompilerConfig = None) -> str:
    cg = RustCodegen(dependency_manager=dependency_manager, config=config)
    return cg.generate(module)
