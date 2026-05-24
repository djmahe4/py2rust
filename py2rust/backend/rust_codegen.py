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



# Rust reserved keywords that must be escaped if used as variable names
_RUST_KEYWORDS = frozenset(
    {
        "as",
        "async",
        "await",
        "break",
        "const",
        "continue",
        "crate",
        "dyn",
        "else",
        "enum",
        "extern",
        "false",
        "fn",
        "for",
        "if",
        "impl",
        "in",
        "let",
        "loop",
        "match",
        "mod",
        "move",
        "mut",
        "pub",
        "ref",
        "return",
        "self",
        "Self",
        "static",
        "struct",
        "super",
        "trait",
        "true",
        "type",
        "union",
        "unsafe",
        "use",
        "where",
        "while",
    }
)


def _mangle(name) -> str:
    """Escape Python identifiers that collide with Rust keywords."""
    if not isinstance(name, str):
        if hasattr(name, "name"):
            name = name.name
        else:
            name = str(name)
    if name == "__str__":
        return "__str__"
    return name + "_" if name in _RUST_KEYWORDS else name


def _get_var_name(expr) -> str | None:
    """Extract variable name from an expression."""
    if isinstance(expr, IRName):
        return expr.name
    if isinstance(expr, IRSelf):
        return "self"
    if isinstance(expr, IRStructAccess):
        return _get_var_name(expr.value)
    return None


def _get_names(target):
    """Recursively extract string names from a target (str, IRName, or IRTupleLit)."""
    if isinstance(target, str):
        return [target]
    if isinstance(target, IRName):
        return [target.name]
    if isinstance(target, IRTupleLit):
        names = []
        for e in target.elements:
            names.extend(_get_names(e))
        return names
    return []


def _collect_vars_from_expr(expr) -> set:
    """Collect all variable names used in an expression."""
    vars: set = set()
    if isinstance(expr, IRName):
        vars.add(expr.name)
    elif isinstance(expr, IRFileMethod):
        name = _get_var_name(expr.file)
        if name:
            vars.add(name)
    elif isinstance(expr, IRMethodCall):
        name = _get_var_name(expr.value)
        if name:
            vars.add(name)
    elif isinstance(expr, IRStructAccess):
        name = _get_var_name(expr.value)
        if name:
            vars.add(name)
    elif isinstance(expr, IRFileOpen):
        pass  # New variable, handled separately
    elif isinstance(expr, IRNew):
        pass  # New variable, handled separately
    # Recursively check nested expressions
    for attr in dir(expr):
        if attr.startswith("_"):
            continue
        try:
            val = getattr(expr, attr)
            if isinstance(val, (list, tuple)):
                for item in val:
                    if hasattr(item, "name") or isinstance(item, IRBinOp):
                        vars |= _collect_vars_from_expr(item)
            elif hasattr(val, "name") or isinstance(val, IRBinOp):
                vars |= _collect_vars_from_expr(val)
        except:
            pass
    return vars


def _get_reachable_if_branches(stmt: IRIf) -> list[tuple[Optional[IRExpr], list[IRStmt]]]:
    """
    Returns a list of reachable branches in the format (condition, body).
    If condition is None, it represents an unconditional body (like 'else').
    """
    reachable = []
    
    # Check main condition
    if isinstance(stmt.condition, IRBoolLit):
        if stmt.condition.value:
            # Main branch is always taken
            reachable.append((stmt.condition, stmt.then_body))
            return reachable
        else:
            # Main branch is never taken, move on to elif and else
            pass
    else:
        # Dynamic condition, main branch is reachable
        reachable.append((stmt.condition, stmt.then_body))
    
    # Check elif clauses
    for elif_cond, elif_body in stmt.elif_clauses:
        if isinstance(elif_cond, IRBoolLit):
            if elif_cond.value:
                # Elif branch is always taken
                reachable.append((elif_cond, elif_body))
                return reachable
            else:
                # Elif branch is never taken
                pass
        else:
            # Dynamic condition, elif is reachable
            reachable.append((elif_cond, elif_body))
            
    # Check else clause
    if stmt.else_body is not None:
        reachable.append((None, stmt.else_body))
        
    return reachable


def _collect_mutated_vars(stmts) -> set:
    """Recursively collect all variable names that are reassigned anywhere in the function."""
    mutated: set = set()
    assigned_vars: dict[str, int] = {}
    
    # Track variables declared in nested scopes that are used outside
    # (these will be pre-declared and thus need 'mut')
    _, pre_declare = _collect_decls(stmts)
    for p in pre_declare:
        mutated.add(p)

    def _visit(body, in_loop=False):
        for stmt in body:
            if isinstance(stmt, IRAssign):
                mutated.add(stmt.target)
                assigned_vars[stmt.target] = assigned_vars.get(stmt.target, 0) + 1
            elif isinstance(stmt, IRAugAssign):
                mutated.add(stmt.target)
                assigned_vars[stmt.target] = assigned_vars.get(stmt.target, 0) + 1
            elif isinstance(stmt, IRSubscriptAssign):
                name = _get_var_name(stmt.target)
                if name:
                    mutated.add(name)
            elif isinstance(stmt, IRDictDelete):
                name = _get_var_name(stmt.target)
                if name:
                    mutated.add(name)
            elif isinstance(stmt, IRTupleUnpack):
                for t in stmt.targets:
                    mutated.add(t)
                    assigned_vars[t] = assigned_vars.get(t, 0) + 1
            elif isinstance(stmt, IRFieldAssign):
                mutated.add("self")
            elif isinstance(stmt, IRVarDecl):
                assigned_vars[stmt.name] = assigned_vars.get(stmt.name, 0) + 1
                if assigned_vars[stmt.name] > 1 or in_loop:
                    mutated.add(stmt.name)
                
                # Check for mutating method calls
                if isinstance(stmt.value, IRMethodCall):
                    if stmt.value.mutates_self and isinstance(stmt.value.value, IRName):
                        mutated.add(stmt.value.value.name)
                elif isinstance(stmt.value, IRFileMethod):
                    if isinstance(stmt.value.file, IRName):
                        mutated.add(stmt.value.file.name)
            elif isinstance(stmt, IRForRange):
                for name in _get_names(stmt.target):
                    mutated.add(name)
                    assigned_vars[name] = assigned_vars.get(name, 0) + 1
                _visit(stmt.body, True)
            elif isinstance(stmt, IRForIter):
                for name in _get_names(stmt.target):
                    mutated.add(name)
                    assigned_vars[name] = assigned_vars.get(name, 0) + 1
                _visit(stmt.body, True)
            elif isinstance(stmt, IRWhile):
                _visit(stmt.body, True)
            elif isinstance(stmt, IRIf):
                for _, body in _get_reachable_if_branches(stmt):
                    _visit(body, in_loop)
            elif isinstance(stmt, IRTryExcept):
                _visit(stmt.body, in_loop)
                for h_type, h_name, h_body in stmt.handlers:
                    if h_name:
                        mutated.add(h_name)
                    _visit(h_body, in_loop)
            elif isinstance(stmt, IRWith):
                for item in stmt.items:
                    for name in _get_names(item.optional_vars):
                        mutated.add(name)
                        assigned_vars[name] = assigned_vars.get(name, 0) + 1
                _visit(stmt.body, in_loop)
            elif isinstance(stmt, IRAssert):
                pass
            elif isinstance(stmt, IRGlobal):
                pass
            elif isinstance(stmt, IRNonlocal):
                pass

    _visit(stmts)
    return mutated


def _collect_decls(stmts, uses_python_wrappers=False) -> tuple[dict[str, object], set[str]]:
    """Collect variable declarations for type tracking and pre-declaration."""
    decls: dict[str, object] = {}
    pre_declare: set[str] = set()

    def _recurse(body, depth=0):
        for stmt in body:
            if isinstance(stmt, IRVarDecl):
                decls[stmt.name] = stmt.type_
                if depth > 0:
                    pre_declare.add(stmt.name)
            elif isinstance(stmt, IRForRange):
                for name in _get_names(stmt.target):
                    decls[name] = IRIntType()
                    pre_declare.add(name)
                _recurse(stmt.body, depth + 1)
            elif isinstance(stmt, IRForIter):
                # Target type depends on iterable
                it_t = stmt.iterable_type
                names = _get_names(stmt.target)
                
                # Determine element types if it's a tuple
                if isinstance(it_t, IRListType) and isinstance(it_t.element_type, IRTupleType):
                    elem_types = it_t.element_type.element_types
                    for i, name in enumerate(names):
                        t = elem_types[i] if i < len(elem_types) else IRIntType()
                        decls[name] = t
                        pre_declare.add(name)
                else:
                    target_type = IRExternalPythonType(module="", name="") if uses_python_wrappers else IRIntType()
                    if isinstance(it_t, IRListType):
                        target_type = it_t.element_type
                    elif isinstance(it_t, IRDictType):
                        target_type = it_t.key_type
                    elif isinstance(it_t, IRStrType):
                        target_type = IRStrType()
                    elif isinstance(it_t, IRExternalPythonType):
                        target_type = IRExternalPythonType(module="", name="")
                    elif isinstance(it_t, IRUnknownType):
                        target_type = IRExternalPythonType(module="", name="")
                    
                    for name in names:
                        decls[name] = target_type
                        pre_declare.add(name)
                _recurse(stmt.body, depth + 1)
            elif isinstance(stmt, IRWhile):
                _recurse(stmt.body, depth + 1)
            elif isinstance(stmt, IRTryExcept):
                _recurse(stmt.body, depth + 1)
                for _, _, h_body in stmt.handlers:
                    _recurse(h_body, depth + 1)
            elif isinstance(stmt, IRWith):
                # Context managers variables are declarations
                for item in stmt.items:
                    for name in _get_names(item.optional_vars):
                        # Use ExternalObject in mock mode for context managers (like open())
                        decls[name] = IRExternalPythonType(module="", name="") if uses_python_wrappers else None
                _recurse(stmt.body, depth + 1)
            elif isinstance(stmt, IRAssert):
                pass
            elif isinstance(stmt, IRGlobal):
                pass
            elif isinstance(stmt, IRNonlocal):
                pass
            elif isinstance(stmt, IRIf):
                for _, body in _get_reachable_if_branches(stmt):
                    _recurse(body, depth + 1)

    _recurse(stmts, depth=0)
    return decls, pre_declare


def _vars_declared_in_loop(stmts) -> set:
    """Collect variable names that are declared inside while loops.

    Variables declared inside while loops are now pre-declared at function level
    with default values to match Python semantics where variables have function scope.
    This function is kept for compatibility but returns an empty set since we no longer
    exclude any variables from pre-declaration.
    """
    return set()  # All variables are pre-declared at function level now


class RustCodegen:
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

    def _capture_stmt_emit(self, stmt) -> str:
        original_lines = self._lines
        self._lines = []
        original_indent = self._indent
        self._indent = 0
        try:
            self._gen_stmt(stmt)
        finally:
            generated = "\n".join(self._lines)
            self._lines = original_lines
            self._indent = original_indent
        return generated

    def _has_yield(self, nodes) -> bool:
        if isinstance(nodes, (list, tuple)):
            return any(self._has_yield(node) for node in nodes)
        
        from py2rust.ir.ir_nodes import IRYield, IRYieldFrom
        if isinstance(nodes, (IRYield, IRYieldFrom)):
            return True
        
        from py2rust.ir.ir_nodes import IRIf, IRWhile, IRForRange, IRForIter, IRWith, IRVarDecl, IRAssign, IRAugAssign, IRReturn
        if isinstance(nodes, IRIf):
            if self._has_yield(nodes.then_body):
                return True
            for _, b in nodes.elif_clauses:
                if self._has_yield(b):
                    return True
            if nodes.else_body:
                if self._has_yield(nodes.else_body):
                    return True
            return False
        if isinstance(nodes, (IRWhile, IRForRange, IRForIter)):
            return self._has_yield(nodes.body)
        if isinstance(nodes, IRWith):
            return self._has_yield(nodes.body)
        if isinstance(nodes, (IRAssign, IRAugAssign, IRVarDecl)):
            return self._has_yield(nodes.value)
        if isinstance(nodes, IRReturn):
            return self._has_yield(nodes.value) if nodes.value else False
        
        return False

    def compile_block(self, stmts, current_state, next_state, next_free_state):
        if not stmts:
            return [(current_state, f"self.__state = {next_state};")], next_free_state

        # Find the first yielding/control flow statement
        yield_idx = -1
        for idx, stmt in enumerate(stmts):
            if self._has_yield(stmt):
                yield_idx = idx
                break

        if yield_idx == -1:
            # None of the statements yield!
            # Just generate them sequentially in current_state.
            code = []
            for stmt in stmts:
                if isinstance(stmt, IRReturn):
                    code.append("self.__state = 999999;")
                    code.append("return None;")
                    break
                else:
                    code.append(self._capture_stmt_emit(stmt))
            
            # If we didn't return, set self.__state = next_state
            if not any(isinstance(stmt, IRReturn) for stmt in stmts):
                code.append(f"self.__state = {next_state};")
                
            return [(current_state, "\n".join(code))], next_free_state

        # There is a yielding/control-flow statement at yield_idx!
        # First, compile any non-yielding statements before it.
        prefix_code = []
        if yield_idx > 0:
            for idx in range(yield_idx):
                stmt = stmts[idx]
                if isinstance(stmt, IRReturn):
                    prefix_code.append("self.__state = 999999;")
                    prefix_code.append("return None;")
                    break
                else:
                    prefix_code.append(self._capture_stmt_emit(stmt))
            
            if any(isinstance(stmts[idx], IRReturn) for idx in range(yield_idx)):
                # If we returned, just return the prefix blocks
                return [(current_state, "\n".join(prefix_code))], next_free_state

        # Now compile the yielding/control flow statement itself!
        yield_stmt = stmts[yield_idx]
        
        if yield_idx > 0:
            state_for_yield = next_free_state
            next_free_state += 1
            prefix_code.append(f"self.__state = {state_for_yield};")
            prefix_blocks = [(current_state, "\n".join(prefix_code))]
        else:
            state_for_yield = current_state
            prefix_blocks = []

        # Compile the rest of the statements after the yielding statement.
        state_after_yield = next_free_state
        next_free_state += 1

        # Compile yield_stmt
        yield_blocks, next_free_state = self.compile_yielding_stmt(
            yield_stmt, state_for_yield, state_after_yield, next_free_state
        )

        # Compile all subsequent statements starting from state_after_yield
        suffix_blocks, next_free_state = self.compile_block(
            stmts[yield_idx + 1:], state_after_yield, next_state, next_free_state
        )

        return prefix_blocks + yield_blocks + suffix_blocks, next_free_state

    def compile_yielding_stmt(self, stmt, current_state, next_state, next_free_state):
        from py2rust.ir.ir_nodes import IRYield, IRYieldFrom, IRIf, IRWhile, IRForRange, IRForIter, IRAssign
        
        if isinstance(stmt, IRAssign) and isinstance(stmt.value, (IRYield, IRYieldFrom)):
            stmt = stmt.value

        if isinstance(stmt, IRYield):
            val = self._gen_expr(stmt.value)
            code = f"self.__state = {next_state};\nreturn Some({val});"
            return [(current_state, code)], next_free_state

        elif isinstance(stmt, IRYieldFrom):
            val = self._gen_expr(stmt.value)
            code = f"""if self.__sub_iter.is_none() {{
    self.__sub_iter = Some(Box::new(({val}).into_iter()));
}}
if let Some(ref mut sub) = self.__sub_iter {{
    if let Some(val) = sub.next() {{
        return Some(val);
    }}
}}
self.__sub_iter = None;
self.__state = {next_state};"""
            return [(current_state, code)], next_free_state

        elif isinstance(stmt, IRIf):
            branch_states = []
            for _ in stmt.branches:
                branch_states.append(next_free_state)
                next_free_state += 1
                
            cond_lines = []
            for idx, (cond, _) in enumerate(stmt.branches):
                target_state = branch_states[idx]
                if cond is None:
                    cond_lines.append(f"else {{\n    self.__state = {target_state};\n}}")
                else:
                    cond_str = self._gen_expr(cond)
                    if idx == 0:
                        cond_lines.append(f"if {cond_str} {{\n    self.__state = {target_state};\n}}")
                    else:
                        cond_lines.append(f"else if {cond_str} {{\n    self.__state = {target_state};\n}}")
                        
            if not any(cond is None for cond, _ in stmt.branches):
                cond_lines.append(f"else {{\n    self.__state = {next_state};\n}}")
                
            current_block = (current_state, "\n".join(cond_lines))
            
            all_blocks = [current_block]
            for idx, (_, body_stmts) in enumerate(stmt.branches):
                body_state = branch_states[idx]
                body_blocks, next_free_state = self.compile_block(
                    body_stmts, body_state, next_state, next_free_state
                )
                all_blocks.extend(body_blocks)
                
            return all_blocks, next_free_state

        elif isinstance(stmt, IRWhile):
            cond_str = self._gen_expr(stmt.condition)
            body_state = next_free_state
            next_free_state += 1
            
            cond_code = f"""if {cond_str} {{
    self.__state = {body_state};
}} else {{
    self.__state = {next_state};
}}"""
            current_block = (current_state, cond_code)
            
            body_blocks, next_free_state = self.compile_block(
                stmt.body, body_state, current_state, next_free_state
            )
            
            return [current_block] + body_blocks, next_free_state

        elif isinstance(stmt, (IRForRange, IRForIter)):
            iter_name = f"__for_iter_{current_state}"
            
            if isinstance(stmt, IRForRange):
                start = self._gen_expr(stmt.start)
                stop = self._gen_expr(stmt.stop)
                if stmt.step is None:
                    iter_expr = f"({start}..{stop})"
                else:
                    step = self._gen_expr(stmt.step)
                    iter_expr = f"({start}..{stop}).step_by({step} as usize)"
                
                target_name = _mangle(stmt.target) if isinstance(stmt.target, (str, IRName)) else "unknown"
                if isinstance(stmt.target, (str, IRName)):
                    t_name = stmt.target.name if isinstance(stmt.target, IRName) else stmt.target
                    t_type = self._decl_types.get(t_name)
                    elem_type = self._get_rust_type(t_type) if t_type else "i32"
                else:
                    elem_type = "i32"
                
                self._generator_sub_iters[iter_name] = f"Option<Box<dyn Iterator<Item = {elem_type}>>>"
                
                cond_state = next_free_state
                body_state = next_free_state + 1
                next_free_state += 2
                
                init_code = f"""self.{iter_name} = Some(Box::new(({iter_expr}).into_iter()));
self.__state = {cond_state};"""
            else:
                iterable_str = self._gen_expr(stmt.iterable)
                target_name = _mangle(stmt.target) if isinstance(stmt.target, (str, IRName)) else "unknown"
                if isinstance(stmt.target, (str, IRName)):
                    t_name = stmt.target.name if isinstance(stmt.target, IRName) else stmt.target
                    t_type = self._decl_types.get(t_name)
                    elem_type = self._get_rust_type(t_type) if t_type else "i32"
                else:
                    elem_type = "i32"
                
                self._generator_sub_iters[iter_name] = f"Option<Box<dyn Iterator<Item = {elem_type}>>>"
                
                cond_state = next_free_state
                body_state = next_free_state + 1
                next_free_state += 2
                
                is_direct_iter = False
                if isinstance(stmt.iterable, IRFunctionCall):
                    if stmt.iterable.name in ("zip", "enumerate", "map", "reversed"):
                        is_direct_iter = True

                is_ext = False
                if isinstance(stmt.iterable_type, IRClassType) and stmt.iterable_type.name == "ExternalObject":
                    is_ext = True
                elif isinstance(stmt.iterable_type, IRExternalPythonType) and not stmt.iterable_type.is_local:
                    is_ext = True

                if isinstance(stmt.iterable_type, IRDictType):
                    iter_expr = f"{iterable_str}.keys()"
                elif isinstance(stmt.iterable_type, IRStrType):
                    iter_expr = f"{iterable_str}.chars().map(|c| c.to_string())"
                elif is_direct_iter:
                    iter_expr = iterable_str
                elif is_ext:
                    iter_expr = f"{iterable_str}.iter()?"
                else:
                    iter_expr = f"&{iterable_str}"
                
                if is_direct_iter or is_ext or isinstance(stmt.iterable_type, IRStrType):
                    init_code = f"""self.{iter_name} = Some(Box::new(({iter_expr}).into_iter()));
self.__state = {cond_state};"""
                else:
                    init_code = f"""self.{iter_name} = Some(Box::new((&{iterable_str}).into_iter().cloned()));
self.__state = {cond_state};"""

            init_block = (current_state, init_code)
            
            # If target is tuple unpack (e.g. key, val in dict or index, val in enumerate)
            if isinstance(stmt.target, IRTupleLit):
                temp_names = [f"__tmp_{i}" for i in range(len(stmt.target.elements))]
                temps_str = ", ".join(temp_names)
                unpack_lines = [f"let ({temps_str}) = val;"]
                for i, e in enumerate(stmt.target.elements):
                    if isinstance(e, IRName):
                        unpack_lines.append(f"self.{_mangle(e.name)} = {temp_names[i]};")
                unpack_str = "\n        ".join(unpack_lines)
                
                cond_code = f"""if let Some(ref mut iter) = self.{iter_name} {{
    if let Some(val) = iter.next() {{
        {unpack_str}
        self.__state = {body_state};
    }} else {{
        self.{iter_name} = None;
        self.__state = {next_state};
    }}
}} else {{
    self.__state = {next_state};
}}"""
            else:
                cond_code = f"""if let Some(ref mut iter) = self.{iter_name} {{
    if let Some(val) = iter.next() {{
        self.{target_name} = val;
        self.__state = {body_state};
    }} else {{
        self.{iter_name} = None;
        self.__state = {next_state};
    }}
}} else {{
    self.__state = {next_state};
}}"""
            cond_block = (cond_state, cond_code)
            
            body_blocks, next_free_state = self.compile_block(
                stmt.body, body_state, cond_state, next_free_state
            )
            
            return [init_block, cond_block] + body_blocks, next_free_state

        return [(current_state, f"self.__state = {next_state};")], next_free_state

    def _gen_generator_struct(self, func: IRFunction) -> None:
        self._uses_py_error = True
        self._mutated_vars = _collect_mutated_vars(func.body)
        decls, pre_declare = _collect_decls(func.body, self._uses_python_wrappers)
        self._decl_types = dict(decls)
        
        struct_name = "".join(part.capitalize() for part in func.name.split("_")) + "Generator"
        
        fields = {}
        for p in func.params:
            fields[_mangle(p.name)] = self._get_rust_type(p.type_)
        for name, type_ in self._decl_types.items():
            if name != "_":
                fields[_mangle(name)] = self._get_rust_type(type_)
                
        self._generator_fields = set(func.params[i].name for i in range(len(func.params))) | set(self._decl_types.keys())
        self._generator_sub_iters = {}
        
        from py2rust.ir.ir_nodes import IRGeneratorType, IRIteratorType, IRIterableType
        yield_type = "()"
        if isinstance(func.return_type, IRGeneratorType):
            yield_type = self._get_rust_type(func.return_type.yield_type)
        elif isinstance(func.return_type, (IRIteratorType, IRIterableType)):
            yield_type = self._get_rust_type(func.return_type.element_type)
            
        blocks, _ = self.compile_block(func.body, 0, 999999, 1)
        
        has_yield_from = False
        def check_yield_from(nodes):
            nonlocal has_yield_from
            if isinstance(nodes, (list, tuple)):
                for n in nodes:
                    check_yield_from(n)
                return
            from py2rust.ir.ir_nodes import IRYieldFrom
            if isinstance(nodes, IRYieldFrom):
                has_yield_from = True
            from py2rust.ir.ir_nodes import IRIf, IRWhile, IRForRange, IRForIter, IRWith, IRAssign, IRAugAssign, IRVarDecl
            if isinstance(nodes, IRIf):
                check_yield_from(nodes.then_body)
                for _, b in nodes.elif_clauses:
                    check_yield_from(b)
                if nodes.else_body:
                    check_yield_from(nodes.else_body)
            elif isinstance(nodes, (IRWhile, IRForRange, IRForIter, IRWith)):
                check_yield_from(nodes.body)
            elif isinstance(nodes, (IRAssign, IRAugAssign, IRVarDecl)):
                check_yield_from(nodes.value)
        check_yield_from(func.body)
        
        has_complex_flow = False
        def check_complex(nodes, in_loop=False):
            nonlocal has_complex_flow
            if isinstance(nodes, (list, tuple)):
                for n in nodes:
                    check_complex(n, in_loop)
                return
            from py2rust.ir.ir_nodes import IRYield, IRYieldFrom, IRBreak, IRContinue, IRIf, IRWhile, IRForRange, IRForIter, IRAssign, IRAugAssign, IRVarDecl
            if isinstance(nodes, (IRBreak, IRContinue)):
                has_complex_flow = True
            elif isinstance(nodes, (IRYield, IRYieldFrom)):
                if in_loop:
                    has_complex_flow = True
            elif isinstance(nodes, IRIf):
                check_complex(nodes.then_body, in_loop)
                for _, b in nodes.elif_clauses:
                    check_complex(b, in_loop)
                if nodes.else_body:
                    check_complex(nodes.else_body, in_loop)
            elif isinstance(nodes, (IRWhile, IRForRange, IRForIter)):
                check_complex(nodes.body, in_loop=True)
            elif isinstance(nodes, (IRAssign, IRAugAssign, IRVarDecl)):
                check_complex(nodes.value, in_loop)
        check_complex(func.body)
        
        if has_complex_flow:
            self._emit("// WARNING: Generator contains complex control flow (yield inside loop or break/continue)")
            
        self._emit(f"pub struct {struct_name} {{")
        self._indent += 1
        self._emit("__state: i32,")
        if has_yield_from:
            self._emit(f"__sub_iter: Option<Box<dyn Iterator<Item = {yield_type}>>>,")
        for name, rust_type in fields.items():
            self._emit(f"{name}: {rust_type},")
        for sub_iter_name, sub_iter_type in self._generator_sub_iters.items():
            self._emit(f"{sub_iter_name}: {sub_iter_type},")
        self._indent -= 1
        self._emit("}")
        self._emit_blank()
        
        param_strs = []
        for p in func.params:
            param_strs.append(f"{_mangle(p.name)}: {self._get_rust_type(p.type_)}")
        params_decl = ", ".join(param_strs)
        
        self._emit(f"impl {struct_name} {{")
        self._indent += 1
        self._emit(f"pub fn new({params_decl}) -> Self {{")
        self._indent += 1
        self._emit("Self {")
        self._indent += 1
        self._emit("__state: 0,")
        if has_yield_from:
            self._emit("__sub_iter: None,")
        for p in func.params:
            self._emit(f"{_mangle(p.name)},")
        for name, type_ in self._decl_types.items():
            if name != "_":
                m_name = _mangle(name)
                if m_name not in [p.name for p in func.params]:
                    default = self._default_value(type_)
                    self._emit(f"{m_name}: {default},")
        for sub_iter_name in self._generator_sub_iters:
            self._emit(f"{sub_iter_name}: None,")
        self._indent -= 1
        self._emit("}")
        self._indent -= 1
        self._emit("}")
        self._indent -= 1
        self._emit("}")
        self._emit_blank()
        
        self._emit(f"impl Iterator for {struct_name} {{")
        self._indent += 1
        self._emit(f"type Item = {yield_type};")
        self._emit("fn next(&mut self) -> Option<Self::Item> {")
        self._indent += 1
        self._emit("loop {")
        self._indent += 1
        self._emit("match self.__state {")
        self._indent += 1
        
        for state_id, code in blocks:
            self._emit(f"{state_id} => {{")
            self._indent += 1
            for line in code.split("\n"):
                if line.strip():
                    self._emit(line)
            self._indent -= 1
            self._emit("}")
            
        self._emit("999999 => return None,")
        self._emit("_ => return None,")
        
        self._indent -= 1
        self._emit("}")
        self._indent -= 1
        self._emit("}")
        self._indent -= 1
        self._emit("}")
        self._indent -= 1
        self._emit("}")
        self._emit_blank()
        
        self._generator_fields = set()

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
            # Always rename Python main to __py_main to avoid collision with Rust main entrypoint
            fn_name = "__py_main" 
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

    def _gen_expr(self, expr, expected_type=None) -> str:
        if isinstance(expr, IRIntLit):
            return str(expr.value)
        elif isinstance(expr, IRFloatLit):
            v = expr.value
            s = repr(v)
            if "." not in s and "e" not in s.lower():
                s += ".0"
            return s
        elif isinstance(expr, IRBoolLit):
            return "true" if expr.value else "false"
        elif isinstance(expr, IRStrLit):
            escaped = (
                expr.value.replace("\\", "\\\\")
                .replace('"', '\\"')
                .replace("\n", "\\n")
            )
            return f'"{escaped}".to_string()'
        elif isinstance(expr, IRName):
            if hasattr(self, "_generator_fields") and self._generator_fields and expr.name in self._generator_fields:
                return f"self.{_mangle(expr.name)}"
            # Check if this name refers to an external python module/object
            if isinstance(expr.result_type, IRExternalPythonType) and not expr.result_type.is_local:
                 # If it's a local variable, field, or parameter, use the name directly
                 if expr.name in self._decl_types or expr.name == "self":
                     return _mangle(expr.name)
                     
                 if expr.result_type.name is None:
                     return f'ExternalObject::load_module("{expr.result_type.module}")?'
                 else:
                     clean_name = expr.result_type.name
                     if clean_name.endswith("()"):
                         clean_name = clean_name[:-2]
                     return f'ExternalObject::from_module("{expr.result_type.module}", "{clean_name}")'
            return _mangle(expr.name)
        elif isinstance(expr, IRBinOp):
            return f"({self._gen_binop(expr)})"
        elif isinstance(expr, IRUnaryOpExpr):
            operand = self._gen_expr(expr.operand)
            if expr.op == "not":
                if isinstance(expr.operand.result_type, IROptionType):
                    return f"{operand}.is_none()"
                return f"(!({operand}))"
            if expr.op == "-":
                return f"(-({operand}))"
            return operand
        elif isinstance(expr, IRSome):
            val = self._gen_expr(expr.value)
            return f"Some({val})"
        elif isinstance(expr, IRSumWrap):
            enum_name = self._get_sum_type_name(expr.result_type)
            variant_rust_info = self._get_rust_type(expr.inner_type)
            variant_name = self._get_variant_name(variant_rust_info)
            val = self._gen_expr(expr.value)
            return f"{enum_name}::{variant_name}({val})"
        elif isinstance(expr, IRNoneLit):
            return "None"
        elif isinstance(expr, IRIsInstance):
            return self._gen_isinstance(expr)
        elif isinstance(expr, IRContains):
            item = self._gen_expr(expr.item)
            container = self._gen_expr(expr.container)
            if isinstance(expr.container_type, IRDictType):
                return f"{container}.contains_key(&{item})"
            elif isinstance(expr.container_type, IRStrType):
                # For strings, use .contains() which works with &str
                return f"{container}.contains({item}.as_str())"
            else:
                return f"{container}.contains(&{item})"
        elif isinstance(expr, IRCompare):
            left = self._gen_expr(expr.left)
            right = self._gen_expr(expr.right)
            
            # Special case for Optional: is None / is not None
            if isinstance(expr.left.result_type, IROptionType):
                if right == "None":
                    if expr.op in ("is", "=="):
                        return f"{left}.is_none()"
                    elif expr.op in ("is not", "!="):
                        return f"{left}.is_some()"
            elif isinstance(expr.right.result_type, IROptionType):
                if left == "None":
                    if expr.op in ("is", "=="):
                        return f"{right}.is_none()"
                    elif expr.op in ("is not", "!="):
                        return f"{right}.is_some()"

            # Map Python comparisons to Rust traits if applicable
            op = expr.op
            if op == "is": op = "=="
            if op == "is not": op = "!="
            
            if isinstance(expr.left.result_type, IRClassType):
                left = f"{left}.clone()"
                right = f"{right}.clone()"
                
            return f"{left} {op} {right}"
        elif isinstance(expr, IRBoolOp):
            parts = [self._gen_expr(v) for v in expr.values]
            return f"({(f' {expr.op} ').join(parts)})"
        elif isinstance(expr, IRListLit):
            is_proto = isinstance(expr.element_type, IRClassType) and self._is_protocol(expr.element_type.name)
            elem_t_str = self._get_rust_type(expr.element_type)
            
            if expr.result_type and isinstance(expr.result_type, IRDequeType):
                self._uses_vec_deque = True
                if not expr.elements:
                    return f"VecDeque::new()"
                elems = ", ".join(self._gen_expr(e) for e in expr.elements)
                return f"VecDeque::from(vec![{elems}])"
            elif expr.result_type and isinstance(expr.result_type, IRHeapType):
                self._uses_heap = True
                if not expr.elements:
                    return f"BinaryHeap::new()"
                elems = ", ".join(self._gen_expr(e) for e in expr.elements)
                return f"BinaryHeap::from(vec![{elems}].into_iter().map(Reverse).collect::<Vec<_>>())"

            if not expr.elements:
                res_t = f"Vec::<Box<dyn {expr.element_type.name}>>" if is_proto else f"Vec::<{elem_t_str}>"
                return f"{res_t}::new()"
            
            if is_proto:
                elems = ", ".join(f"Box::new({self._gen_expr(e)}) as Box<dyn {expr.element_type.name}>" for e in expr.elements)
            else:
                elems = ", ".join(self._gen_expr(e) for e in expr.elements)
            return f"vec![{elems}]"
        elif isinstance(expr, IRDictLit):
            self._uses_hashmap = True
            is_ext = False
            if (isinstance(expr.value_type, IRExternalPythonType) and not expr.value_type.is_local) or (isinstance(expr.value_type, IRClassType) and expr.value_type.name == "ExternalObject"):
                is_ext = True

            if is_ext:
                self._uses_python_wrappers = True
                pairs = ", ".join(f"({self._gen_expr(k)}, {self._gen_expr(v)})" for k, v in expr.pairs)
                return f"ExternalObject::new(Python::with_gil(|py| {{ let d = PyDict::new(py); {('; ').join(f'd.set_item({self._gen_expr(k)}, {self._gen_expr(v)}).unwrap()' for k, v in expr.pairs)}; d.to_object(py) }}))"

            key_t = self._get_rust_type(expr.key_type)
            val_t = self._get_rust_type(expr.value_type)
            if not expr.pairs:
                return f"HashMap::<{key_t}, {val_t}>::new()"
            pairs = ", ".join(f"({self._gen_expr(k)}, {self._gen_expr(v)})" for k, v in expr.pairs)
            return f"HashMap::from([{pairs}])"
        elif isinstance(expr, IRTupleLit):
            elems = ", ".join(self._gen_expr(e) for e in expr.elements)
            return f"({elems})"

        elif isinstance(expr, IRSlice):
            # standalone slice object, rare in our codegen but let's handle it
            lower = self._gen_expr(expr.lower) if expr.lower else "None"
            upper = self._gen_expr(expr.upper) if expr.upper else "None"
            step = self._gen_expr(expr.step) if expr.step else "None"
            return f"py2rust::Slice::new({lower}, {upper}, {step})"

        elif isinstance(expr, IRSubscript):
            val = self._gen_expr(expr.value)
            idx = self._gen_expr(expr.index)

            # Handle user-defined indexing via dunder methods
            if expr.trait_info and expr.trait_info[0] == "Index":
                return f"{val}.__getitem__({idx})?"

            # Handle dict subscript: d[key] -> __d.get(&key).unwrap().clone()
            if isinstance(expr.value_type, IRDictType):
                val_t = self._get_rust_type(expr.value_type.value_type)
                return f"{val}.get(&{idx}).unwrap().clone()"

            # Handle ExternalObject indexing (e.g., json data)
            is_ext = False
            if (isinstance(expr.value_type, IRClassType) and expr.value_type.name == "ExternalObject") or \
               (isinstance(expr.value_type, IRExternalPythonType) and not expr.value_type.is_local):
                is_ext = True
            
            if is_ext:
                return f"{val}.getitem({idx})?"

            # Handle slicing
            if isinstance(expr.index, IRSlice):
                slc = expr.index
                lower = self._strip_parens(self._gen_expr(slc.lower)) if slc.lower else "0"
                upper = self._strip_parens(self._gen_expr(slc.upper)) if slc.upper else (f"{val}.len() as i32" if not isinstance(expr.value_type, IRStrType) else f"{val}.chars().count() as i32")
                
                # Slicing creates a NEW collection usually in Python
                if isinstance(expr.value_type, IRListType):
                    # List slicing: l[start:stop] -> l[start as usize .. stop as usize].to_vec()
                    # We need to handle negative indices
                    return (
                        f"{{ let __coll = &({val}); let __len = __coll.len() as i32; "
                        f"let __start = if {lower} < 0 {{ {lower} + __len }} else {{ {lower} }};"
                        f"let __stop = if {upper} < 0 {{ {upper} + __len }} else {{ {upper} }};"
                        f"let __start = __start.clamp(0, __len) as usize; "
                        f"let __stop = __stop.clamp(__start as i32, __len) as usize; "
                        f"__coll[__start..__stop].to_vec() }}"
                    )
                elif isinstance(expr.value_type, IRStrType):
                    # String slicing: s[start:stop] -> s.chars().skip(start).take(stop-start).collect()
                    return (
                        f"{{ let __coll = &({val}); let __len = __coll.chars().count() as i32; "
                        f"let __start = if {lower} < 0 {{ {lower} + __len }} else {{ {lower} }};"
                        f"let __stop = if {upper} < 0 {{ {upper} + __len }} else {{ {upper} }};"
                        f"let __start = __start.clamp(0, __len) as usize; "
                        f"let __stop = __stop.clamp(__start as i32, __len) as usize; "
                        f"__coll.chars().skip(__start).take(__stop - __start).collect::<String>() }}"
                    )

            # Robust Python indexing: bind collection to a temp reference
            if isinstance(expr.value_type, IRStrType):
                len_expr = "__coll.chars().count() as i32"
                inner_expr = f"__coll.chars().nth(actual_idx).unwrap().to_string()"
            elif isinstance(expr.value_type, IRHeapType):
                # Heap only supports heap[0] reliably as peek()
                if idx == "0":
                    return f"{val}.peek().map(|r| r.0.clone()).ok_or(PyError::IndexError(\"heap index out of range\".to_string()))?"
                len_expr = "__coll.len() as i32"
                inner_expr = f"__coll.peek().map(|r| r.0.clone()).ok_or(PyError::IndexError(\"heap index out of range\".to_string()))?"
            else:
                len_expr = "__coll.len() as i32"
                inner_expr = f"__coll[actual_idx]"

            if isinstance(expr.result_type, (IRStrType, IRListType, IRTypeParam)) and not isinstance(
                expr.value_type, IRStrType
            ):
                inner_expr = f"{inner_expr}.clone()"

            return (
                f"{{ let __coll = &({val}); "
                f"let __idx_raw = {idx}; let actual_idx = if __idx_raw < 0 {{ (__idx_raw + ({len_expr}) as i32) as usize }} else {{ __idx_raw as usize }}; "
                f"{inner_expr} }}"
            )

        elif isinstance(expr, IRFunctionCall):
            if expr.name == "isinstance":
                obj = self._gen_expr(expr.args[0])
                obj_type = getattr(expr.args[0], "result_type", None)
                type_node = expr.args[1]
                
                if isinstance(obj_type, IRSumType):
                    enum_name = self._get_rust_type(obj_type)
                    # For simplicity, handle single type name. 
                    # If it's a tuple of types, we would need a more complex match or multiple matches!.
                    variant = "Unknown"
                    from ..frontend.ast_nodes import Name
                    if isinstance(type_node, Name):
                        typ_name = type_node.name
                        if typ_name == "int": variant = "Int"
                        elif typ_name == "float": variant = "Float"
                        elif typ_name == "str": variant = "Str"
                        elif typ_name == "bool": variant = "Bool"
                        else: variant = typ_name # Assume class name
                    
                    return f"matches!(&{obj}, {enum_name}::{variant}(_))"
                
                if isinstance(obj_type, IROptionType):
                    from ..frontend.ast_nodes import Name
                    if isinstance(type_node, Name) and type_node.name == "type(None)":
                         return f"{obj}.is_none()"
                    return f"{obj}.is_some()"
                
                # Fallback for normal objects/classes
                return f"true /* isinstance fallback for {obj} */"

            if expr.name == "len":
                arg = self._gen_expr(expr.args[0])
                return f"{arg}.len() as i32"

            if expr.name == "list" and len(expr.args) == 1:
                arg = self._gen_expr(expr.args[0])
                arg_t = getattr(expr.args[0], "result_type", None)
                if isinstance(arg_t, (IRIteratorType, IRGeneratorType)) or isinstance(expr.args[0], (IRMap, IRFilter)):
                    return f"{arg}.collect::<Vec<_>>()"
                return f"{arg}.clone()"

            if expr.name == "set" and len(expr.args) == 1:
                arg = self._gen_expr(expr.args[0])
                arg_t = getattr(expr.args[0], "result_type", None)
                if isinstance(arg_t, (IRIteratorType, IRGeneratorType)) or isinstance(expr.args[0], (IRMap, IRFilter)):
                    return f"{arg}.collect::<HashSet<_>>()"
                return f"{arg}.clone().into_iter().collect::<HashSet<_>>()"
            
            if expr.name == "zip":
                # zip(a, b)
                arg0 = self._gen_expr(expr.args[0])
                arg1 = self._gen_expr(expr.args[1])
                return f"(&{arg0}).iter().zip((&{arg1}).iter())"
            
            if expr.name == "enumerate":
                arg = self._gen_expr(expr.args[0])
                return f"(&{arg}).iter().enumerate().map(|(i, x)| (i as i32, x))"
                
            if expr.name == "map":
                func = self._gen_expr(expr.args[0])
                iterable = self._gen_expr(expr.args[1])
                return f"(&{iterable}).iter().map({func}).collect::<Vec<_>>()"
                
            if expr.name == "reversed":
                arg = self._gen_expr(expr.args[0])
                return f"(&{arg}).iter().rev()"

            if expr.name == "str":
                arg = self._gen_expr(expr.args[0])
                arg_t = getattr(expr.args[0], "result_type", None)
                if isinstance(arg_t, IRClassType):
                    return f"{arg}.__str__()?"
                return f"{arg}.to_string()"
            
            if expr.name == "int":
                arg = self._gen_expr(expr.args[0])
                arg_t = getattr(expr.args[0], "result_type", None)
                if isinstance(arg_t, IRStrType):
                    return f'{arg}.parse::<i32>().map_err(|e| PyError::ValueError(e.to_string()))?'
                if isinstance(arg_t, IRFloatType):
                    return f"({arg} as i32)"
                # Use a string conversion fallback
                return f"{arg}.to_string().parse::<i32>().map_err(|e| PyError::ValueError(e.to_string()))?"
            
            if expr.name == "float":
                arg = self._gen_expr(expr.args[0])
                arg_t = getattr(expr.args[0], "result_type", None)
                if isinstance(arg_t, IRStrType):
                    return f'{arg}.parse::<f64>().map_err(|e| PyError::ValueError(e.to_string()))?'
                if isinstance(arg_t, IRIntType):
                    return f"({arg} as f64)"
                return f"{arg}.to_string().parse::<f64>().map_err(|e| PyError::ValueError(e.to_string()))?"

            if expr.name == "bool":
                arg = self._gen_expr(expr.args[0])
                arg_t = getattr(expr.args[0], "result_type", None)
                if isinstance(arg_t, (IRIntType, IRFloatType)):
                    return f"({arg} != 0.0)"
                if isinstance(arg_t, (IRStrType, IRListType, IRDictType, IRSetType)):
                    return f"!{arg}.is_empty()"
                return "true"
            
            if expr.name in ("Exception", "ValueError", "TypeError", "KeyError", "IndexError"):
                # Exception constructor call
                arg_str = self._gen_expr(expr.args[0]) if expr.args else '""'.to_string()
                return f"PyError::{expr.name}({arg_str})"

            # Native JSON support
            if expr.name == "__py2rust_native_json_loads":
                self._uses_python_wrappers = True
                self._uses_serde_json = True
                self._uses_pythonize = True
                arg = self._gen_expr(expr.args[0])
                return f"Python::with_gil(|py| -> Result<ExternalObject, PyError> {{ let v: serde_json::Value = serde_json::from_str(&{arg}).map_err(|e| PyError::ValueError(e.to_string()))?; let obj = pythonize::pythonize(py, &v).map_err(|e| PyError::ValueError(e.to_string()))?; Ok(ExternalObject::new(obj)) }})?"
            
            if expr.name == "__py2rust_native_json_dumps":
                self._uses_python_wrappers = True
                self._uses_serde_json = True
                self._uses_pythonize = True
                arg = self._gen_expr(expr.args[0])
                arg_t = getattr(expr.args[0], "result_type", None)
                is_ext = (isinstance(arg_t, IRExternalPythonType) and not arg_t.is_local) or (isinstance(arg_t, IRClassType) and arg_t.name == "ExternalObject")
                if is_ext:
                    # Use Python's json.dumps for maximum compatibility with external objects
                    return f"Python::with_gil(|py| -> Result<String, PyError> {{ let json = py.import(\"json\")?; let res = json.getattr(\"dumps\")?.call1(({arg}.obj.as_ref(py),))?; Ok(res.extract()?) }})?"
                else:
                    return f"serde_json::to_string(&{arg}).map_err(|e| PyError::ValueError(e.to_string()))?"

            if expr.name in ("deque", "collections.deque"):
                self._uses_deque = True
                if not expr.args:
                    return "VecDeque::new()"
                arg = self._gen_expr(expr.args[0])
                # Match test expectation: VecDeque::from(vec![...])
                if ".to_vec()" in arg or "vec![" in arg:
                    return f"VecDeque::from({arg})"
                return f"VecDeque::from_iter({arg})"

            if expr.name in ("heappush", "heapq.heappush"):
                self._uses_heap = True
                heap = self._gen_expr(expr.args[0])
                item = self._gen_expr(expr.args[1])
                return f"{heap}.push(Reverse({item}))"
            
            if expr.name in ("heappop", "heapq.heappop"):
                self._uses_heap = True
                heap = self._gen_expr(expr.args[0])
                return f"{heap}.pop().ok_or(PyError::IndexError(\"index out of range\".to_string()))?.0"
            
            if expr.name in ("heapify", "heapq.heapify"):
                self._uses_heap = True
                lst = self._gen_expr(expr.args[0])
                return f"BinaryHeap::from({lst}.into_iter().map(Reverse).collect::<Vec<_>>())"

            # Native CSV support
            if expr.name == "__py2rust_native_csv_reader":
                self._uses_python_wrappers = True
                self._uses_csv = True
                # csv.reader(f) -> returns an iterator of rows
                arg = self._gen_expr(expr.args[0])
                # This is a bit complex as it needs to return something that behaves like an iterator of ExternalObjects
                return f"ExternalObject::new_csv_reader(&{arg})?"

            args = ", ".join(self._gen_expr(a) for a in expr.args)
            
            # Use call() if it's an external function
            if isinstance(expr.return_type, IRExternalPythonType) and not expr.return_type.is_local:
                func_name = self._gen_expr(IRName(name=expr.name, result_type=expr.return_type))
                if not args:
                    tuple_args = "()"
                else:
                    tuple_args = f"({args},)"
                return f"{func_name}.call({tuple_args})?"

            fn_name = _mangle(expr.name)
            if expr.name == "main":
                # Call the renamed user main
                fn_name = "__py_main"

            res = f"{fn_name}({args})"
            if expr.is_fallible:
                res = f"{res}?"
            return res
        elif isinstance(expr, IRFileOpen):
            path = self._gen_expr(expr.path)
            mode = self._gen_expr(expr.mode) if expr.mode else '"r".to_string()'
            if self._uses_python_wrappers:
                # In mock mode, use Python's open() for interoperability with other mock-mode libraries
                return f"ExternalObject::call_builtin(\"open\", ({path}, {mode}))?"
            self._uses_file_handle = True
            return f"FileHandle::open(&{path}, &{mode})?"
        elif isinstance(expr, IRFileMethod):
            file_val = self._gen_expr(expr.file)
            args = ", ".join(f"&{self._gen_expr(a)}" for a in expr.args)
            method = expr.method
            if method in ("read", "readline", "readlines"):
                return f"{file_val}.{method}()?"
            if method == "write":
                return f"{file_val}.write({args})?"
            if method == "close":
                return f"{file_val}.close()?"
            if method == "tell":
                return f"{file_val}.tell()?"
            if method == "seek":
                return f"{file_val}.seek({args})?"
            return f"{file_val}.{method}()?"
        elif isinstance(expr, IRSelf):
            return "self"
        elif isinstance(expr, IRStructAccess):
            if isinstance(expr.value, IRSelf):
                from py2rust.ir.ir_nodes import IRIntType, IRFloatType, IRBoolType, IRUnitType
                is_copy = isinstance(expr.result_type, (IRIntType, IRFloatType, IRBoolType, IRUnitType))
                if not is_copy:
                    return f"self.{_mangle(expr.field)}.clone()"
                return f"self.{_mangle(expr.field)}"
            val = self._gen_expr(expr.value)
            # Use :: for static enum variant access
            if isinstance(expr.result_type, IREnumType):
                return f"{val}::{_mangle(expr.field)}"
            
            v_type = getattr(expr.value, "result_type", None)
            if isinstance(v_type, IRExternalPythonType):
                if not v_type.is_local:
                    return f'{val}.getattr("{expr.field}")?'
                elif v_type.name is None:
                    return f"{val}::{_mangle(expr.field)}"

            return f"{val}.{_mangle(expr.field)}"
        elif isinstance(expr, IRMethodCall):
            val = self._gen_expr(expr.value)
            args = ", ".join(self._gen_expr(a) for a in expr.args)
            
            v_type = getattr(expr.value, "result_type", None)
            if isinstance(v_type, IRExternalPythonType):
                if v_type.is_local:
                    if v_type.name is None:
                        res = f"{val}::{_mangle(expr.method)}({args})"
                        if getattr(expr, "is_fallible", True):
                            res += "?"
                        return res
                else:
                    val_type = expr.value.result_type
                    if val_type.module == "heapq":
                        if expr.method == "heappush":
                            self._uses_heap = True
                            heap = self._gen_expr(expr.args[0])
                            item = self._gen_expr(expr.args[1])
                            return f"{heap}.push(Reverse({item}))"
                        if expr.method == "heappop":
                            self._uses_heap = True
                            heap = self._gen_expr(expr.args[0])
                            return f"{heap}.pop().ok_or(PyError::IndexError(\"index out of range\".to_string()))?.0"
                        if expr.method == "heapify":
                            self._uses_heap = True
                            lst = self._gen_expr(expr.args[0])
                            return f"BinaryHeap::from({lst}.into_iter().map(Reverse).collect::<Vec<_>>())"

                    if not args:
                        tuple_args = "()"
                    else:
                        tuple_args = f"({args},)"
                    return f'{val}.call_method("{expr.method}", {tuple_args})?'

            # Deque species methods
            if isinstance(getattr(expr, "value_type", getattr(expr.value, "result_type", None)), IRDequeType):
                self._uses_deque = True
                if expr.method == "append":
                    return f"{val}.push_back({args})"
                if expr.method == "appendleft":
                    return f"{val}.push_front({args})"
                if expr.method == "pop":
                    return f"{val}.pop_back().ok_or(PyError::IndexError(\"pop from an empty deque\".to_string()))?"
                if expr.method == "popleft":
                    return f"{val}.pop_front().ok_or(PyError::IndexError(\"pop from an empty deque\".to_string()))?"
                if expr.method == "extend":
                    return f"{val}.extend({args})"
                if expr.method == "extendleft":
                    # Python's extendleft reverses the iterable
                    return f"for __item in {args} {{ {val}.push_front(__item); }}"

            res = f"{val}.{_mangle(expr.method)}({args})"
            if getattr(expr, "is_fallible", True):
                res += "?"
            return res
        elif isinstance(expr, IRNew):
            args = ", ".join(self._gen_expr(a) for a in expr.args)
            return f"{expr.class_name}::new({args})?"
        elif isinstance(expr, IRAwait):
            self._uses_async = True
            val = self._gen_expr(expr.value)
            # If the inner expression was fallible (had a '?'), we need to await then '?' 
            # e.g. func().await?
            if val.endswith("?"):
                return f"{val[:-1]}.await?"
            return f"{val}.await"

        elif isinstance(expr, IRLambda):
            return self._gen_lambda(expr)

        elif isinstance(expr, IRMap):
            if isinstance(expr.func, IRLambda):
                func_str = self._gen_expr(expr.func)
            else:
                func_str = f"|x| ({self._gen_expr(expr.func)})(x).unwrap()"
            iter_expr = self._get_comp_iter_expr(expr.iterable, getattr(expr.iterable, "result_type", None))
            return f"Box::new({iter_expr}.map({func_str}))"

        elif isinstance(expr, IRFilter):
            if isinstance(expr.func, IRLambda):
                func_str = f"move |__x| {{ let x = __x.clone(); ({self._gen_expr(expr.func)})(x) }}"
            else:
                func_str = f"move |__x| {{ let x = __x.clone(); ({self._gen_expr(expr.func)})(x).unwrap() }}"
            iter_expr = self._get_comp_iter_expr(expr.iterable, getattr(expr.iterable, "result_type", None))
            return f"Box::new({iter_expr}.filter({func_str}))"

        elif isinstance(expr, IRSorted):
            iter_expr = self._get_comp_iter_expr(expr.iterable, getattr(expr.iterable, "result_type", None))
            if expr.key_func:
                if isinstance(expr.key_func, IRLambda):
                    key_str = f"|__x| {{ let x = __x.clone(); ({self._gen_expr(expr.key_func)})(x) }}"
                else:
                    key_str = f"|__x| {{ let x = __x.clone(); ({self._gen_expr(expr.key_func)})(x).unwrap() }}"
                return (
                    f"({{ let mut __tmp = {iter_expr}.collect::<Vec<_>>(); "
                    f"__tmp.sort_by_key({key_str}); "
                    f"__tmp }})"
                )
            else:
                return (
                    f"({{ let mut __tmp = {iter_expr}.collect::<Vec<_>>(); "
                    f"__tmp.sort(); "
                    f"__tmp }})"
                )

        elif isinstance(expr, IRReduce):
            iter_expr = self._get_comp_iter_expr(expr.iterable, getattr(expr.iterable, "result_type", None))
            if isinstance(expr.func, IRLambda):
                func_str = self._gen_expr(expr.func)
            else:
                func_str = f"|acc, x| ({self._gen_expr(expr.func)})(acc, x).unwrap()"
            if expr.initial is not None:
                initial_str = self._gen_expr(expr.initial)
                return f"{iter_expr}.fold({initial_str}, {func_str})"
            else:
                return f"{iter_expr}.reduce({func_str}).unwrap()"

        elif isinstance(expr, IRListComp):
            return self._gen_list_comp(expr)

        elif isinstance(expr, IRDictComp):
            return self._gen_dict_comp(expr)

        elif isinstance(expr, IRSetComp):
            return self._gen_set_comp(expr)

        elif isinstance(expr, IRGeneratorExp):
            return self._gen_generator_exp(expr)

        elif isinstance(expr, IRJoinedStr):
            fmt_parts = []
            args = []
            for v in expr.values:
                if isinstance(v, (IRStrLit, str)):
                    val = v.value if isinstance(v, IRStrLit) else v
                    # Escape braces for Rust format string
                    escaped = val.replace("{", "{{").replace("}", "}}")
                    fmt_parts.append(escaped)
                elif isinstance(v, IRFormattedValue):
                    spec = v.format_spec or ""
                    # Handle conversions: !r -> {:?}, !s -> {} (default)
                    if v.conversion == 114: # ord('r')
                        spec = f":?{spec}"
                    elif spec:
                        spec = f":{spec}"
                    
                    val_expr = self._gen_expr(v.value)
                    # For Optional types, we need a way to display them. 
                    # If it's an Option, we can't directly use {} in format! unless we wrap it.
                    if isinstance(getattr(v.value, "result_type", None), IROptionType):
                        val_expr = f"{val_expr}.as_ref().map(|v| format!(\"{{}}\", v)).unwrap_or(\"None\".to_string())"
                    elif isinstance(getattr(v.value, "result_type", None), IRSumType):
                         # For sum types, we probably want debug format if no special display
                         if ":" not in spec:
                             spec = f":?{spec}"
                             
                    fmt_parts.append(f"{{{spec}}}")
                    args.append(val_expr)
            
            fmt_str = "".join(fmt_parts)
            if not args:
                return f'"{fmt_str}".to_string()'
            args_str = ", ".join(args)
            return f'format!("{fmt_str}", {args_str})'

        return f"/* unknown expr {type(expr).__name__} */"

    def _gen_condition(self, expr: IRExpr) -> str:
        """Generate a boolean expression suitable for if/while conditions in Rust."""
        expr_str = self._gen_expr(expr)
        
        # Already boolean?
        if isinstance(expr.result_type, IRBoolType):
            return expr_str
            
        # Optional?
        if isinstance(expr.result_type, IROptionType):
            # Special case for 'not x' where x is Optional
            if isinstance(expr, IRUnaryOpExpr) and expr.op == "not":
                return expr_str # Already handled in _gen_expr for Optional
            return f"{expr_str}.is_some()"
            
        # List/Set/Dict/String? (Truthiness based on empty)
        if isinstance(expr.result_type, (IRListType, IRSetType, IRDictType, IRStrType)):
            return f"!{expr_str}.is_empty()"
            
        # Int? (Truthiness != 0)
        if isinstance(expr.result_type, IRIntType):
            return f"{expr_str} != 0"
            
        # Float? (Truthiness != 0.0)
        if isinstance(expr.result_type, IRFloatType):
            return f"{expr_str} != 0.0"
            
        return expr_str

    def _gen_lambda(self, expr: IRLambda) -> str:
        params = ", ".join(f"{p.name}" for p in expr.params)
        body = self._gen_expr(expr.body)
        return f"|{params}| {{ {body} }}"

    def _gen_list_comp(self, node: IRListComp) -> str:
        elem_t = self._get_rust_type(node.result_type.element_type)
        inner = f"let mut __res = Vec::<{elem_t}>::new(); "
        
        # Build nested loops for generators
        loop_code = ""
        close_braces = ""
        for gen in node.generators:
            target = self._gen_comp_target(gen.target)
            iterable = self._get_comp_iter_expr(gen.iterable, getattr(gen.iterable, "result_type", None))
            loop_code += f"for __tmp in {iterable} {{ let {target} = __tmp; "
            for if_expr in gen.ifs:
                cond = self._gen_expr(if_expr)
                loop_code += f"if {cond} {{ "
                close_braces += " } "
            close_braces += " } "
        
        elt = self._gen_expr(node.elt)
        push_code = f"__res.push({elt}); "
        
        return f"({{ {inner}{loop_code}{push_code}{close_braces} __res }})"

    def _gen_dict_comp(self, node: IRDictComp) -> str:
        self._uses_hashmap = True
        key_t = self._get_rust_type(node.result_type.key_type)
        val_t = self._get_rust_type(node.result_type.value_type)
        inner = f"let mut __res = HashMap::<{key_t}, {val_t}>::new(); "
        
        loop_code = ""
        close_braces = ""
        for gen in node.generators:
            target = self._gen_comp_target(gen.target)
            iterable = self._get_comp_iter_expr(gen.iterable, getattr(gen.iterable, "result_type", None))
            loop_code += f"for __tmp in {iterable} {{ let {target} = __tmp; "
            for if_expr in gen.ifs:
                cond = self._gen_expr(if_expr)
                loop_code += f"if {cond} {{ "
                close_braces += " } "
            close_braces += " } "
            
        key = self._gen_expr(node.key)
        val = self._gen_expr(node.value)
        insert_code = f"__res.insert({key}, {val}); "
        
        return f"({{ {inner}{loop_code}{insert_code}{close_braces} __res }})"

    def _gen_set_comp(self, node: IRSetComp) -> str:
        self._uses_hashmap = True
        elem_t = self._get_rust_type(node.result_type.element_type)
        inner = f"let mut __res = HashSet::<{elem_t}>::new(); "
        
        loop_code = ""
        close_braces = ""
        for gen in node.generators:
            target = self._gen_comp_target(gen.target)
            iterable = self._get_comp_iter_expr(gen.iterable, getattr(gen.iterable, "result_type", None))
            loop_code += f"for __tmp in {iterable} {{ let {target} = __tmp; "
            for if_expr in gen.ifs:
                cond = self._gen_expr(if_expr)
                loop_code += f"if {cond} {{ "
                close_braces += " } "
            close_braces += " } "
        
        elt = self._gen_expr(node.elt)
        insert_code = f"__res.insert({elt}); "
        
        return f"({{ {inner}{loop_code}{insert_code}{close_braces} __res }})"

    def _gen_generator_exp(self, node: IRGeneratorExp) -> str:
        chain = self._gen_comp_chain(node.generators, 0, node.elt)
        return f"Box::new({chain})"

    def _gen_comp_chain(self, generators, index, elt) -> str:
        gen = generators[index]
        target = self._gen_comp_target(gen.target)
        iterable = self._get_comp_iter_expr(gen.iterable, getattr(gen.iterable, "result_type", None))
        
        # Base iterator
        chain = iterable
        
        # Apply filters for this generator
        for if_expr in gen.ifs:
            cond = self._gen_expr(if_expr)
            chain = f"{chain}.filter(move |__tmp| {{ let {target} = __tmp.clone(); {cond} }})"
            
        # If there are more generators (inner loops)
        if index + 1 < len(generators):
            inner_chain = self._gen_comp_chain(generators, index + 1, elt)
            chain = f"{chain}.flat_map(move |__tmp| {{ let {target} = __tmp.clone(); {inner_chain} }})"
        else:
            elt_expr = self._gen_expr(elt)
            chain = f"{chain}.map(move |__tmp| {{ let {target} = __tmp.clone(); {elt_expr} }})"
            
        return chain

    def _get_comp_iter_expr(self, iterable, iterable_type) -> str:
        iterable_str = self._gen_expr(iterable)
        is_direct_iter = False
        if isinstance(iterable, IRFunctionCall):
            if iterable.name in ("zip", "enumerate", "map", "reversed"):
                is_direct_iter = True
        
        if isinstance(iterable_type, (IRIteratorType, IRGeneratorType)):
            is_direct_iter = True
            
        if isinstance(iterable_type, IRDictType):
            return f"{iterable_str}.clone().into_keys()"
        elif isinstance(iterable_type, IRStrType):
            return f"{iterable_str}.chars().map(|c| c.to_string())"
        elif is_direct_iter:
            return iterable_str
        else:
            return f"{iterable_str}.clone().into_iter()"

    def _gen_comp_target(self, target) -> str:
        if isinstance(target, IRName):
            return _mangle(target.name)
        if isinstance(target, IRTupleLit):
            elems = ", ".join(self._gen_comp_target(e) for e in target.elements)
            return f"({elems})"
        return "_"

    def _emit_async_runtime(self) -> None:
        # Instead of emitting a custom runtime, we now rely on tokio.
        # This method can be used to emit internal async helpers if needed.
        self._emit("// Using tokio as async runtime")
        self._emit("")

    def _gen_binop(self, expr) -> str:
        if expr.trait_info:
            trait_name, method_name = expr.trait_info
            left = self._gen_expr(expr.left)
            right = self._gen_expr(expr.right)
            
            # Prevent move errors for classes in binary ops
            if isinstance(getattr(expr.left, "result_type", None), IRClassType):
                left = f"{left}.clone()"
            if isinstance(getattr(expr.right, "result_type", None), IRClassType):
                right = f"{right}.clone()"
                
            return f"{left} {expr.op} {right}"

        if expr.op == "/":
            left = self._gen_expr_as_float(expr.left)
            right = self._gen_expr_as_float(expr.right)
            return f"{left} / {right}"
        if expr.op == "//":
            left = self._gen_expr(expr.left)
            right = self._gen_expr(expr.right)
            return f"({left} as f64 / {right} as f64).floor() as i32"
        if expr.op == "+" and isinstance(expr.result_type, IRStrType):
            left = self._gen_expr(expr.left)
            right = self._gen_expr(expr.right)
            return f"{left}.to_string() + &{right}"
        if expr.op == "+" and isinstance(expr.result_type, IRListType):
            left = self._gen_expr(expr.left)
            right = self._gen_expr(expr.right)
            elem_type = self._get_rust_type(expr.result_type.element_type)
            return f"({{ let mut __v: Vec<{elem_type}> = {left}.clone(); __v.extend({right}.clone()); __v }})"
        if expr.op == "*" and isinstance(expr.result_type, IRListType):
            left = self._gen_expr(expr.left)
            right = self._gen_expr(expr.right)
            return f"{left}.repeat({right} as usize)"
        if expr.op == "*" and isinstance(expr.result_type, IRStrType):
            if isinstance(expr.left, IRStrLit):
                left_str = self._gen_expr(expr.left)
                right_n = self._gen_expr(expr.right)
                return f"{left_str}.to_string().repeat({right_n})"
            elif isinstance(expr.right, IRStrLit):
                left_n = self._gen_expr(expr.left)
                right_str = self._gen_expr(expr.right)
                return f"{right_str}.to_string().repeat({left_n})"
            else:
                left = self._gen_expr(expr.left)
                right = self._gen_expr(expr.right)
                return f"{left}.repeat({right})"

        if isinstance(expr.result_type, IRFloatType):
            left = self._gen_expr_as_float(expr.left)
            right = self._gen_expr_as_float(expr.right)
        else:
            left = self._gen_expr(expr.left)
            right = self._gen_expr(expr.right)

        return f"{left} {expr.op} {right}"

    def _emit_python_boilerplate(self):
        self._lines.append("")
        self._lines.append("#[derive(Clone)]")
        self._lines.append("pub struct ExternalObject {")
        self._lines.append("    pub obj: PyObject,")
        self._lines.append("}")
        self._lines.append("")
        self._lines.append("impl From<PyErr> for PyError {")
        self._lines.append("    fn from(err: PyErr) -> Self {")
        self._lines.append("        PyError::Exception(err.to_string())")
        self._lines.append("    }")
        self._lines.append("}")
        self._lines.append("impl Default for ExternalObject {")
        self._lines.append("    fn default() -> Self {")
        self._lines.append("        Python::with_gil(|py| Self::new(py.None()))")
        self._lines.append("    }")
        self._lines.append("}")
        self._lines.append("")
        self._lines.append("impl ExternalObject {")
        self._lines.append("    pub fn new(obj: PyObject) -> Self {")
        self._lines.append("        Self { obj }")
        self._lines.append("    }")
        self._lines.append("")
        self._lines.append("    pub fn from_module(module: &str, name: &str) -> Self {")
        self._lines.append("        Python::with_gil(|py| {")
        self._lines.append("            let m = py.import(module).expect(\"Failed to import module\");")
        self._lines.append("            let attr = m.getattr(name).expect(\"Failed to get attribute from module\");")
        self._lines.append("            Self::new(attr.to_object(py))")
        self._lines.append("        })")
        self._lines.append("    }")
        self._lines.append("")
        self._lines.append("    pub fn load_module(module: &str) -> PyResult<Self> {")
        self._lines.append("        Python::with_gil(|py| {")
        self._lines.append("            Self::init_venv(py)?;")
        self._lines.append("            let m = py.import(module)?;")
        self._lines.append("            Ok(Self::new(m.to_object(py)))")
        self._lines.append("        })")
        self._lines.append("    }")
        self._lines.append("")
        self._lines.append("    fn init_venv(py: Python<'_>) -> PyResult<()> {")
        self._lines.append("        use std::env;")
        self._lines.append("        if let Ok(venv) = env::var(\"PY2RUST_VENV\") {")
        self._lines.append("            let sys = py.import(\"sys\")?;")
        self._lines.append("            let path = sys.getattr(\"path\")?;")
        self._lines.append("            ")
        self._lines.append("            let venv_path = std::path::PathBuf::from(venv);")
        self._lines.append("            #[cfg(target_os = \"windows\")]")
        self._lines.append("            {")
        self._lines.append("                let mut sp_path = venv_path.clone();")
        self._lines.append("                sp_path.push(\"Lib\");")
        self._lines.append("                sp_path.push(\"site-packages\");")
        self._lines.append("                let sp_str = sp_path.to_string_lossy().to_string();")
        self._lines.append("                path.call_method1(\"append\", (sp_str,))?;")
        self._lines.append("            }")
        self._lines.append("            #[cfg(not(target_os = \"windows\"))]")
        self._lines.append("            {")
        self._lines.append("                let lib_dir = venv_path.join(\"lib\");")
        self._lines.append("                if let Ok(entries) = std::fs::read_dir(lib_dir) {")
        self._lines.append("                    for entry in entries.flatten() {")
        self._lines.append("                        let p = entry.path();")
        self._lines.append("                        if p.is_dir() && p.file_name().unwrap_or_default().to_string_lossy().starts_with(\"python\") {")
        self._lines.append("                            let site_packages = p.join(\"site-packages\");")
        self._lines.append("                            if site_packages.exists() {")
        self._lines.append("                                let sp_str = site_packages.to_string_lossy().to_string();")
        self._lines.append("                                path.call_method1(\"append\", (sp_str,))?;")
        self._lines.append("                                break;")
        self._lines.append("                            }")
        self._lines.append("                        }")
        self._lines.append("                    }")
        self._lines.append("                }")
        self._lines.append("            }")
        self._lines.append("        }")
        self._lines.append("        Ok(())")
        self._lines.append("    }")
        self._lines.append("")
        self._lines.append("    pub fn getattr(&self, name: &str) -> PyResult<Self> {")
        self._lines.append("        Python::with_gil(|py| {")
        self._lines.append("            let attr = self.obj.getattr(py, name)?;")
        self._lines.append("            Ok(Self::new(attr.to_object(py)))")
        self._lines.append("        })")
        self._lines.append("    }")
        self._lines.append("")
        self._lines.append("    pub fn call(&self, args: impl IntoPy<Py<PyTuple>>) -> PyResult<Self> {")
        self._lines.append("        Python::with_gil(|py| {")
        self._lines.append("            let res = self.obj.call1(py, args)?;")
        self._lines.append("            Ok(Self::new(res.to_object(py)))")
        self._lines.append("        })")
        self._lines.append("    }")
        self._lines.append("")
        self._lines.append("    pub fn call_method(&self, method: &str, args: impl IntoPy<Py<PyTuple>>) -> PyResult<Self> {")
        self._lines.append("        Python::with_gil(|py| {")
        self._lines.append("            let res = self.obj.call_method1(py, method, args)?;")
        self._lines.append("            Ok(Self::new(res.to_object(py)))")
        self._lines.append("        })")
        self._lines.append("    }")
        self._lines.append("")
        self._lines.append("    pub fn setattr(&self, name: &str, value: impl IntoPy<PyObject>) -> PyResult<()> {")
        self._lines.append("        Python::with_gil(|py| {")
        self._lines.append("            let value = value.into_py(py);")
        self._lines.append("            self.obj.as_ref(py).setattr(name, value)?;")
        self._lines.append("            Ok(())")
        self._lines.append("        })")
        self._lines.append("    }")
        self._lines.append("")
        self._lines.append("    pub fn setitem(&self, key: impl IntoPy<PyObject>, value: impl IntoPy<PyObject>) -> PyResult<()> {")
        self._lines.append("        Python::with_gil(|py| {")
        self._lines.append("            let key = key.into_py(py);")
        self._lines.append("            let value = value.into_py(py);")
        self._lines.append("            self.obj.as_ref(py).set_item(key, value)?;")
        self._lines.append("            Ok(())")
        self._lines.append("        })")
        self._lines.append("    }")
        self._lines.append("")
        self._lines.append("    pub fn getitem(&self, key: impl IntoPy<PyObject>) -> PyResult<Self> {")
        self._lines.append("        Python::with_gil(|py| {")
        self._lines.append("            let key = key.into_py(py);")
        self._lines.append("            let item = self.obj.as_ref(py).get_item(key)?;")
        self._lines.append("            Ok(Self::new(item.to_object(py)))")
        self._lines.append("        })")
        self._lines.append("    }")
        self._lines.append("")
        self._lines.append("    pub fn call_builtin(name: &str, args: impl IntoPy<Py<PyTuple>>) -> PyResult<Self> {")
        self._lines.append("        Python::with_gil(|py| {")
        self._lines.append("            let builtins = py.import(\"builtins\")?;")
        self._lines.append("            let func = builtins.getattr(name)?;")
        self._lines.append("            let res = func.call1(args)?;")
        self._lines.append("            Ok(Self::new(res.to_object(py)))")
        self._lines.append("        })")
        self._lines.append("    }")
        self._lines.append("")
        self._lines.append("    pub fn read(&self) -> PyResult<String> {")
        self._lines.append("        Python::with_gil(|py| {")
        self._lines.append("            let res = self.obj.call_method0(py, \"read\")?;")
        self._lines.append("            res.extract(py)")
        self._lines.append("        })")
        self._lines.append("    }")
        self._lines.append("")
        self._lines.append("    pub fn write(&self, data: &str) -> PyResult<()> {")
        self._lines.append("        Python::with_gil(|py| {")
        self._lines.append("            self.obj.call_method1(py, \"write\", (data,))?;")
        self._lines.append("            Ok(())")
        self._lines.append("        })")
        self._lines.append("    }")
        self._lines.append("")
        self._lines.append("    pub fn close(&self) -> PyResult<()> {")
        self._lines.append("        Python::with_gil(|py| {")
        self._lines.append("            self.obj.call_method0(py, \"close\")?;")
        self._lines.append("            Ok(())")
        self._lines.append("        })")
        self._lines.append("    }")
        self._lines.append("")
        self._lines.append("    pub fn len(&self) -> usize {")
        self._lines.append("        Python::with_gil(|py| {")
        self._lines.append("            self.obj.as_ref(py).len().unwrap_or(0)")
        self._lines.append("        })")
        self._lines.append("    }")
        self._lines.append("")
        self._lines.append("    pub fn iter(&self) -> PyResult<Vec<Self>> {")
        self._lines.append("        Python::with_gil(|py| {")
        self._lines.append("            let iter = self.obj.as_ref(py).iter()?;")
        self._lines.append("            let mut res = Vec::new();")
        self._lines.append("            for item in iter {")
        self._lines.append("                res.push(Self::new(item?.to_object(py)));")
        self._lines.append("            }")
        self._lines.append("            Ok(res)")
        self._lines.append("        })")
        self._lines.append("    }")
        self._lines.append("")
        self._lines.append("    pub fn new_csv_reader(file_obj: &Self) -> PyResult<Self> {")
        self._lines.append("        Python::with_gil(|py| {")
        self._lines.append("            let csv = py.import(\"csv\")?;")
        self._lines.append("            let reader = csv.getattr(\"reader\")?.call1((file_obj.obj.as_ref(py),))?;")
        self._lines.append("            Ok(Self::new(reader.to_object(py)))")
        self._lines.append("        })")
        self._lines.append("    }")
        self._lines.append("}")
        self._lines.append("")
        self._lines.append("impl std::fmt::Display for ExternalObject {")
        self._lines.append("    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {")
        self._lines.append("        Python::with_gil(|py| {")
        self._lines.append("            let s = self.obj.as_ref(py).str().and_then(|s| s.extract::<String>()).unwrap_or_else(|_| \"<external object>\".to_string());")
        self._lines.append("            write!(f, \"{}\", s)")
        self._lines.append("        })")
        self._lines.append("    }")
        self._lines.append("}")
        self._lines.append("")
        self._lines.append("impl std::fmt::Debug for ExternalObject {")
        self._lines.append("    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {")
        self._lines.append("        Python::with_gil(|py| {")
        self._lines.append("            let r = self.obj.as_ref(py).repr().map(|r| r.to_string()).unwrap_or_else(|_| \"<external object>\".to_string());")
        self._lines.append("            write!(f, \"{:?}\", r)")
        self._lines.append("        })")
        self._lines.append("    }")
        self._lines.append("}")
        self._lines.append("")
        self._lines.append("impl IntoPy<PyObject> for ExternalObject {")
        self._lines.append("    fn into_py(self, _py: Python<'_>) -> PyObject {")
        self._lines.append("        self.obj")
        self._lines.append("    }")
        self._lines.append("}")
        self._lines.append("")

    def _gen_expr_as_float(self, expr) -> str:
        if isinstance(expr, IRIntLit):
            return f"{expr.value}.0_f64"
        if isinstance(expr, IRFloatLit):
            return self._gen_expr(expr)
        if isinstance(expr, IRName):
            return f"({expr.name} as f64)"
        inner = self._gen_expr(expr)
        if isinstance(expr, IRBinOp) and isinstance(expr.result_type, IRFloatType):
            return inner
        return f"({inner}) as f64"

    def _gen_isinstance(self, expr: IRIsInstance) -> str:
        obj_expr = self._gen_expr(expr.obj)
        obj_type = expr.obj.result_type
        check_type = expr.check_type

        # Handle None check (type(None) or known UnitType)
        if isinstance(check_type, IRUnitType):
            if isinstance(obj_type, IROptionType):
                return f"{obj_expr}.is_none()"
            return f"({obj_expr} == ())"

        # Handle SumType (Union) checks
        if isinstance(obj_type, IRSumType):
            enum_name = self._get_sum_type_name(obj_type)
            # Find the variant that matches check_type
            variant_rust_type = self._get_rust_type(check_type)
            variant_name = self._get_variant_name(variant_rust_type)
            return f"matches!({obj_expr}, {enum_name}::{variant_name}(_))"

        # Handle Option checks
        if isinstance(obj_type, IROptionType):
            # isinstance(x, Optional[T]) - always true if it matches checking T or being None
            if isinstance(check_type, IROptionType):
                return "true"
            # isinstance(x, T) where x is Optional[T]
            if self._get_rust_type(obj_type.inner_type) == self._get_rust_type(check_type):
                return f"{obj_expr}.is_some()"
            return "false"

        # Handle List/Dict/Set checks
        if isinstance(check_type, (IRListType, IRDictType, IRSetType)):
            if type(obj_type) == type(check_type):
                return "true"
            return "false"

        # Handle Class checks
        if isinstance(check_type, IRClassType):
            if isinstance(obj_type, IRClassType) and obj_type.name == check_type.name:
                return "true"
            return "false"

        # Default: if types match exactly in Rust
        if self._get_rust_type(obj_type) == self._get_rust_type(check_type):
            return "true"
        
        return "false"


def generate_rust(module: IRModule, dependency_manager=None, config: CompilerConfig = None) -> str:
    cg = RustCodegen(dependency_manager=dependency_manager, config=config)
    return cg.generate(module)
