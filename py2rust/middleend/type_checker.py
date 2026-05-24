from __future__ import annotations
from typing import Optional, Union
from ..frontend.ast_nodes import (
    IntType,
    FloatType,
    BoolType,
    StrType,
    ListType,
    DictType,
    ClassType,
    TupleType,
    EnumType,
    OptionalType,
    UnionType,
    SliceType,
    UnitType,
    IteratorType,
    IterableType,
    GeneratorType,
    Yield,
    YieldFrom,
    GeneratorExp,
    EnumDef,
    MatchStmt,
    MatchCase,
    MatchPattern,
    ValuePattern,
    NamePattern,
    ClassPattern,
    WildcardPattern,
    OrPattern,
    AsPattern,
    ClassDef,
    FunctionDef,
    Assign,
    Name,
    BinOp,
    UnaryOp,
    Comparison,
    BoolOp,
    ListLiteral,
    DictLiteral,
    TupleLiteral,
    Subscript,
    FunctionCall,
    AttributeExpr,
    MethodCall,
    SelfExpr,
    NewExpr,
    AwaitExpr,
    LambdaExpr,
    Comprehension,
    ListComp,
    DictComp,
    SetComp,
    JoinedStr,
    FormattedValue,
    TypeVarType,
    PassStmt,
    SetType,
    UnknownType,
    FunctionType,
    Module,
    Import,
    ImportFrom,
    WithStmt,
    WithItem,
    AssertStmt,
    GlobalStmt,
    NonlocalStmt,
    FileType,
    ExternalPythonType,
)
from ..utils.errors import Py2RustTypeError, SemanticError
from .symbol_table import SymbolTable
from .type_inferencer import TypeInferencer


def _types_compatible(a, b, invariant=False) -> bool:
    if isinstance(a, UnknownType) or isinstance(b, UnknownType):
        return True
    if isinstance(a, TypeVarType) or isinstance(b, TypeVarType):
        return True

    # Handle OptionalType
    if isinstance(a, UnionType):
        # b matches Union[...] if b matches any variant
        return any(_types_compatible(v, b, invariant=invariant) for v in a.variants)
    if isinstance(b, UnionType):
        # a matches Union[...] if a matches any variant
        return any(_types_compatible(a, v, invariant=invariant) for v in b.variants)

    if isinstance(a, OptionalType):
        if isinstance(b, OptionalType):
            return _types_compatible(a.inner_type, b.inner_type, invariant=invariant)
        if isinstance(b, UnitType): # None matches Optional[T]
            return True
        return _types_compatible(a.inner_type, b, invariant=invariant)
    if isinstance(b, OptionalType):
        if isinstance(a, UnitType): # None matches Optional[T]
            return True
        # In general, T matches Optional[T] even for non-invariant contexts
        return _types_compatible(a, b.inner_type, invariant=invariant)

    if type(a) is type(b):
        if isinstance(a, ListType) and isinstance(b, ListType):
            # Collections are invariant in Rust (Vec<T>)
            return _types_compatible(a.element_type, b.element_type, invariant=True)
        if isinstance(a, DictType) and isinstance(b, DictType):
            return _types_compatible(
                a.key_type, b.key_type, invariant=True
            ) and _types_compatible(a.value_type, b.value_type, invariant=True)
        if isinstance(a, SetType) and isinstance(b, SetType):
            return _types_compatible(a.element_type, b.element_type, invariant=True)
        if isinstance(a, IteratorType) and isinstance(b, IteratorType):
            return _types_compatible(a.element_type, b.element_type, invariant=True)
        if isinstance(a, IterableType) and isinstance(b, IterableType):
            return _types_compatible(a.element_type, b.element_type, invariant=True)
        if isinstance(a, GeneratorType) and isinstance(b, GeneratorType):
            return (_types_compatible(a.yield_type, b.yield_type, invariant=True) and
                    _types_compatible(a.send_type, b.send_type, invariant=True) and
                    _types_compatible(a.return_type, b.return_type, invariant=True))
        return True

    # GeneratorType is compatible with IteratorType or IterableType in both directions
    if isinstance(a, IteratorType) and isinstance(b, GeneratorType):
        return _types_compatible(a.element_type, b.yield_type, invariant=True)
    if isinstance(a, IterableType) and isinstance(b, GeneratorType):
        return _types_compatible(a.element_type, b.yield_type, invariant=True)
    if isinstance(a, GeneratorType) and isinstance(b, IteratorType):
        return _types_compatible(a.yield_type, b.element_type, invariant=True)
    if isinstance(a, GeneratorType) and isinstance(b, IterableType):
        return _types_compatible(a.yield_type, b.element_type, invariant=True)
    if isinstance(a, IterableType) and isinstance(b, IteratorType):
        return _types_compatible(a.element_type, b.element_type, invariant=True)

    if isinstance(a, FloatType) and isinstance(b, IntType):
        # f64 accepts i32, but Vec<f64> does NOT accept Vec<i32>
        return not invariant
    if isinstance(a, ExternalPythonType) or isinstance(b, ExternalPythonType):
        return True
    if isinstance(a, (EnumType, ClassType)) and isinstance(b, (EnumType, ClassType)):
        return getattr(a, "name", None) == getattr(b, "name", None)
    return False


def _get_yield_item_type(expected_type):
    if isinstance(expected_type, IteratorType):
        return expected_type.element_type
    if isinstance(expected_type, IterableType):
        return expected_type.element_type
    if isinstance(expected_type, GeneratorType):
        return expected_type.yield_type
    return None


def _get_iterable_item_type(it_type):
    if isinstance(it_type, ListType):
        return it_type.element_type
    if isinstance(it_type, IteratorType):
        return it_type.element_type
    if isinstance(it_type, IterableType):
        return it_type.element_type
    if isinstance(it_type, GeneratorType):
        return it_type.yield_type
    if isinstance(it_type, StrType):
        return StrType()
    if isinstance(it_type, DictType):
        return it_type.key_type
    return None


_MUTEX_CLASS_NAMES = frozenset({"Mutex", "Lock", "RwLock", "Semaphore", "Condition",
                                  "threading.Lock", "threading.RLock", "threading.Semaphore"})


def _is_mutex_like_name(name: str) -> bool:
    """Return True if the class name is a known mutex/lock synchronisation primitive."""
    return name in _MUTEX_CLASS_NAMES or any(
        name.endswith(suffix) for suffix in ("Lock", "Mutex", "RwLock", "Semaphore", "Guard")
    )


class TypeChecker:
    def __init__(
        self,
        symbol_table: SymbolTable,
        filename: str = "<unknown>",
        source_lines: list = None,
    ):
        self.st = symbol_table
        self.inferencer = TypeInferencer(symbol_table)
        self.filename = filename
        self.source_lines = source_lines or []
        self._current_return_type = None
        self._within_async = False

    def _err(
        self,
        msg: str,
        line: int = 0,
        col: int = 0,
        suggestion: str = None,
        cls=Py2RustTypeError,
    ) -> Py2RustTypeError:
        return cls(
            message=msg,
            filename=self.filename,
            line=line,
            column=col,
            suggestion=suggestion,
            source_lines=self.source_lines,
        )

    def _sem_err(self, msg: str, line: int = 0, col: int = 0) -> SemanticError:
        return SemanticError(
            message=msg,
            filename=self.filename,
            line=line,
            column=col,
            source_lines=self.source_lines,
        )

    def _is_main_check(self, expr) -> bool:
        """Checks if an expression is __name__ == "__main__" or vice-versa."""
        if type(expr).__name__ == "Comparison":
            if getattr(expr, "op", "") == "==":
                left = getattr(expr, "left", None)
                right = getattr(expr, "right", None)
                
                # Check for: __name__ == "__main__"
                if type(left).__name__ == "Name" and getattr(left, "name", "") == "__name__":
                    if type(right).__name__ == "StrLiteral" and getattr(right, "value", "") == "__main__":
                        return True
                # Also check: "__main__" == __name__
                if type(right).__name__ == "Name" and getattr(right, "name", "") == "__name__":
                    if type(left).__name__ == "StrLiteral" and getattr(left, "value", "") == "__main__":
                        return True
        return False

    def check_module(self, module: Module) -> Module:
        from pathlib import Path
        from py2rust.project.import_resolver import ImportResolver

        # Initialize resolver if project context is available
        resolver = None
        repo_root = getattr(self.st.config, "repo_root", None)
        if repo_root:
            package_dir = getattr(self.st.config, "package_dir", None)
            from py2rust.project.project_config import ProjectConfig
            toml_path = Path(repo_root) / "pyproject.toml"
            proj_config = ProjectConfig.load_from_toml(toml_path)
            
            sys_path_resolved = []
            for p in proj_config.sys_path:
                p_path = Path(p)
                if not p_path.is_absolute():
                    p_path = (Path(repo_root) / p_path).resolve()
                else:
                    p_path = p_path.resolve()
                if p_path.exists():
                    sys_path_resolved.append(p_path)

            resolver = ImportResolver(
                repo_root=Path(repo_root),
                sys_path=sys_path_resolved,
                package_dir=package_dir
            )

        current_module = None
        if resolver and module.filename:
            current_module = resolver.get_module_for_file(Path(module.filename))

        # Process Imports first to load plugins or resolve intra-repo imports
        for imp in module.imports:
            plugin = None
            if isinstance(imp, Import):
                for alias in imp.names:
                    resolved_mod = alias.name
                    is_local = False
                    if resolver:
                        is_local = resolver.is_intra_repo(resolved_mod)
                    elif self.st.cross_module_table:
                        is_local = self.st.cross_module_table.has_module(resolved_mod)

                    if is_local:
                        alias_name = alias.asname if alias.asname else alias.name
                        self.st.define(alias_name, ExternalPythonType(module=resolved_mod, is_local=True))

                        if current_module and self.st.dependency_manager:
                            try:
                                self.st.dependency_manager.add_import_edge(current_module, resolved_mod)
                            except ValueError as e:
                                raise self._sem_err(str(e), imp.line, imp.col)

                            parts = resolved_mod.split(".")
                            rust_path = "::".join(parts)
                            if alias.asname:
                                use_stmt = f"use crate::{rust_path} as {alias.asname};"
                            else:
                                use_stmt = f"use crate::{rust_path};"
                            self.st.dependency_manager.add_module_import(current_module, use_stmt)
                    else:
                        plugin = self.st.pm.load_plugin(alias.name)
                        if plugin is None and not getattr(self.st.config, "mock_mode", False):
                            raise self._sem_err(f"Unsupported import: '{alias.name}'. No plugin found and mock_mode is disabled.", imp.line, imp.col)
                        
                        alias_name = alias.asname if alias.asname else alias.name
                        self.st.define(alias_name, ExternalPythonType(module=alias.name, is_local=False))

            elif isinstance(imp, ImportFrom):
                if imp.module or imp.level > 0:
                    if imp.level > 0:
                        if not current_module or not resolver:
                            raise self._sem_err(
                                "Relative imports require a project context with repository root configured.",
                                imp.line,
                                imp.col,
                            )
                        try:
                            base_mod_name = resolver.resolve_relative_import(current_module, imp.level, imp.module)
                        except ValueError as e:
                            raise self._sem_err(str(e), imp.line, imp.col)
                    else:
                        base_mod_name = imp.module

                    for alias in imp.names:
                        if base_mod_name:
                            full_target = f"{base_mod_name}.{alias.name}"
                        else:
                            full_target = alias.name

                        if resolver:
                            if full_target in resolver.local_modules:
                                resolved_mod = full_target
                                symbol_name = None
                            elif base_mod_name in resolver.local_modules:
                                resolved_mod = base_mod_name
                                symbol_name = alias.name
                            else:
                                resolved_mod = base_mod_name
                                symbol_name = alias.name
                        elif self.st.cross_module_table:
                            if self.st.cross_module_table.has_module(full_target):
                                resolved_mod = full_target
                                symbol_name = None
                            elif self.st.cross_module_table.has_module(base_mod_name):
                                resolved_mod = base_mod_name
                                symbol_name = alias.name
                            else:
                                resolved_mod = base_mod_name
                                symbol_name = alias.name
                        else:
                            resolved_mod = base_mod_name
                            symbol_name = alias.name

                        is_local = False
                        if resolver and resolved_mod:
                            is_local = resolver.is_intra_repo(resolved_mod)
                        elif self.st.cross_module_table and resolved_mod:
                            is_local = self.st.cross_module_table.has_module(resolved_mod)

                        if is_local:
                            if symbol_name and self.st.cross_module_table:
                                if self.st.cross_module_table.has_module(resolved_mod):
                                    symbol_val = self.st.cross_module_table.lookup_symbol(resolved_mod, symbol_name)
                                    if symbol_val is None:
                                        raise self._sem_err(
                                            f"cannot import name '{symbol_name}' from '{resolved_mod}'",
                                            imp.line,
                                            imp.col,
                                        )

                            alias_name = alias.asname if alias.asname else alias.name
                            self.st.define(alias_name, ExternalPythonType(module=resolved_mod, name=symbol_name, is_local=True))

                            if current_module and self.st.dependency_manager:
                                try:
                                    self.st.dependency_manager.add_import_edge(current_module, resolved_mod)
                                except ValueError as e:
                                    raise self._sem_err(str(e), imp.line, imp.col)

                                parts = resolved_mod.split(".")
                                rust_path = "::".join(parts)
                                if symbol_name:
                                    if alias.asname:
                                        use_stmt = f"use crate::{rust_path}::{symbol_name} as {alias.asname};"
                                    else:
                                        use_stmt = f"use crate::{rust_path}::{symbol_name};"
                                    self.st.dependency_manager.add_module_import(current_module, use_stmt)

                                    # If the symbol is a class, also import its Trait
                                    is_class = False
                                    if self.st.cross_module_table:
                                        symbol_val = self.st.cross_module_table.lookup_symbol(resolved_mod, symbol_name)
                                        if symbol_val and type(symbol_val).__name__ == "ClassInfo":
                                            is_class = True
                                    # Fallback: if name is capitalized and not found yet, also import it to be safe
                                    if not is_class and symbol_name and symbol_name[0].isupper():
                                        is_class = True

                                    if is_class:
                                        if alias.asname:
                                            use_stmt_trait = f"use crate::{rust_path}::{symbol_name}Trait as {alias.asname}Trait;"
                                        else:
                                            use_stmt_trait = f"use crate::{rust_path}::{symbol_name}Trait;"
                                        self.st.dependency_manager.add_module_import(current_module, use_stmt_trait)

                                        # Recursively import companion traits of all base classes
                                        if symbol_val and type(symbol_val).__name__ == "ClassInfo":
                                            def _add_base_traits(mod_name, class_info):
                                                for base in class_info.bases:
                                                    base_mod = mod_name
                                                    base_info = None
                                                    if self.st.cross_module_table:
                                                        # Try direct lookup in mod_name
                                                        base_val = self.st.cross_module_table.lookup_symbol(mod_name, base)
                                                        if base_val and type(base_val).__name__ == "ClassInfo":
                                                            base_info = base_val
                                                        else:
                                                            # Search all modules
                                                            for other_mod_name, other_st in self.st.cross_module_table.modules.items():
                                                                if base in other_st._classes:
                                                                    base_mod = other_mod_name
                                                                    base_info = other_st._classes[base]
                                                                    break
                                                    if base_info and base_mod != current_module:
                                                        base_parts = base_mod.split(".")
                                                        base_rust_path = "::".join(base_parts)
                                                        use_stmt_base_trait = f"use crate::{base_rust_path}::{base}Trait;"
                                                        self.st.dependency_manager.add_module_import(current_module, use_stmt_base_trait)
                                                        _add_base_traits(base_mod, base_info)

                                            _add_base_traits(resolved_mod, symbol_val)
                                else:
                                    if alias.asname:
                                        use_stmt = f"use crate::{rust_path} as {alias.asname};"
                                    else:
                                        use_stmt = f"use crate::{rust_path};"
                                    self.st.dependency_manager.add_module_import(current_module, use_stmt)

                        else:
                            plugin = self.st.pm.load_plugin(resolved_mod) if resolved_mod else None
                            if plugin is None and not getattr(self.st.config, "mock_mode", False):
                                raise self._sem_err(f"Unsupported import: '{resolved_mod}'. No plugin found and mock_mode is disabled.", imp.line, imp.col)
                            
                            alias_name = alias.asname if alias.asname else alias.name
                            self.st.define(alias_name, ExternalPythonType(module=resolved_mod or "", name=alias.name, is_local=False))

            self.st.pm.transform_ast(imp, self)

        # Allow plugins to transform the whole module (e.g. ClassDef -> EnumDef)
        module = self.st.pm.transform_module(module, self)

        # Pre-scan all classes (including nested ones)
        self._collect_all_classes(module.classes)
        self._collect_all_classes(module.functions)
        
        # Pre-scan all protocols
        self._collect_all_protocols(module.classes)
        self._collect_all_protocols(module.functions)

        # Check for circular class field layout cycles
        self._check_class_field_cycles()

        # Register top-level classes in global scope
        for cls in module.classes:
            self.st.define(cls.name, ClassType(name=cls.name))

        for cls in module.classes:
            self.check_class(cls)

        for enum_def in module.enums:
            self.check_enum(enum_def)

        for func in module.functions:
            param_types = [p.type_annotation for p in func.params]
            self.st.define_function(
                func.name,
                param_types,
                func.return_type,
                func.is_async,
                func.type_params,
            )
            from ..frontend.ast_nodes import FunctionType
            self.st.define(func.name, FunctionType(tuple(param_types), func.return_type))

        for func in module.functions:
            self.check_function(func)

        new_stmts = []
        for stmt in module.statements:
            transformed = self.st.pm.transform_ast(stmt, self)
            if transformed is not None:
                new_stmts.append(transformed)
                self.check_stmt(transformed)
        
        # Update module with potentially transformed statements
        import dataclasses
        module = dataclasses.replace(module, statements=tuple(new_stmts))

        return module

    def _collect_all_classes(self, items, prefix="") -> None:
        for item in items:
            if isinstance(item, ClassDef):
                full_name = f"{prefix}{item.name}"
                
                fields = {}
                methods = {}
                constructors = {}
                
                for sub_item in item.body:
                    if hasattr(sub_item, "__class__"):
                        item_name = type(sub_item).__name__
                        if item_name == "VarDecl":
                            fields[sub_item.name] = sub_item.type_annotation
                        elif item_name == "FunctionDef":
                            arity = len(sub_item.params)
                            if sub_item.name == "__init__":
                                constructors[arity] = sub_item
                                # Scan __init__ for self.attr = ... assignments to discover fields
                                for stmt in sub_item.body:
                                    if isinstance(stmt, Assign) and isinstance(stmt.target, tuple) and len(stmt.target) == 3 and stmt.target[0] == "attr" and stmt.target[1] == "self":
                                        attr_name = stmt.target[2]
                                        if attr_name not in fields:
                                            # Using a simple inferencer pass during collection
                                            inf_t = self.inferencer.infer(stmt.value)
                                            fields[attr_name] = inf_t or UnknownType()
                            else:
                                if sub_item.name not in methods:
                                    methods[sub_item.name] = {}
                                methods[sub_item.name][arity] = sub_item
                
                # Register class with mangled name
                self.st.define_class(full_name, item.bases, fields, methods, constructors, item.type_params)
                
                # Recurse into class body for nested classes
                self._collect_all_classes(item.body, prefix=f"{full_name}_")
            elif isinstance(item, EnumDef):
                full_name = f"{prefix}{item.name}"
                variants = {v[0]: v[1] for v in item.variants}
                self.st.define_enum(full_name, variants)
                self.st.define(full_name, EnumType(name=full_name))

    def _collect_all_protocols(self, items, prefix="") -> None:
        for item in items:
            if isinstance(item, ClassDef) and any(b == "Protocol" for b in item.bases):
                full_name = f"{prefix}{item.name}"
                methods = {}
                for sub_item in item.body:
                    if isinstance(sub_item, FunctionDef):
                        arity = len(sub_item.params)
                        arg_types = [p.type_annotation for p in sub_item.params]
                        methods[sub_item.name] = {arity: (sub_item, (arg_types, sub_item.return_type))}
                self.st.define_trait(full_name, item.bases, methods)
                
                # Recurse for nested items
                self._collect_all_protocols(item.body, prefix=f"{full_name}_")
            elif hasattr(item, "body") and isinstance(item.body, (list, tuple)):
                self._collect_all_protocols(item.body, prefix=prefix)
            
            elif isinstance(item, FunctionDef):
                # Recurse into function body for nested classes
                self._collect_all_classes(item.body, prefix=f"{prefix}{item.name}_")

    def check_class(self, cls: ClassDef, prefix="") -> None:
        full_name = f"{prefix}{cls.name}"
        prev_class = self.st.get_current_class()
        self.st.enter_scope(full_name)

        # Define type parameters in the class scope
        for tp in cls.type_params:
            self.st.define(tp, TypeVarType(name=tp))

        self.st.set_current_class(full_name)
        
        # Define nested items in this class scope
        for item in cls.body:
            if isinstance(item, ClassDef):
                self.st.define(item.name, ClassType(name=f"{full_name}_{item.name}"))
        
        for item in cls.body:
            if isinstance(item, FunctionDef):
                self.check_method(full_name, item)
            elif isinstance(item, ClassDef):
                self.check_class(item, prefix=f"{full_name}_")
        
        self.st.set_current_class(prev_class)
        self.st.exit_scope()

    def check_method(self, class_name: str, func: FunctionDef) -> None:
        self.st.enter_scope(f"{class_name}.{func.name}")
        # Define type parameters in the method scope
        for tp in func.type_params:
            self.st.define(tp, TypeVarType(name=tp))
        old_ret = self._current_return_type
        self._current_return_type = func.return_type
        old_async = self._within_async
        self._within_async = func.is_async
        # Wave 28: @staticmethod methods have no 'self' receiver
        if not getattr(func, "is_static", False):
            self.st.define("self", ClassType(name=class_name))

        for param in func.params:
            self.st.define(param.name, param.type_annotation)

        for stmt in func.body:
            self.check_stmt(stmt)

        self.st.exit_scope()
        self._current_return_type = old_ret
        self._within_async = old_async

    def check_function(self, func: FunctionDef) -> None:
        self.st.enter_scope(func.name)
        # Define type parameters in the function scope
        for tp in func.type_params:
            self.st.define(tp, TypeVarType(name=tp))
        old_ret = self._current_return_type
        self._current_return_type = func.return_type
        old_async = self._within_async
        self._within_async = func.is_async

        # Register local class fields/methods so attribute access resolves correctly.
        # Use a mangled prefix matching what check_class uses for nested classes.
        scope_name = self.st.current_scope.name
        local_classes = [item for item in func.body if isinstance(item, ClassDef)]
        if local_classes:
            self._collect_all_classes(local_classes, prefix=f"{scope_name}_")

        # Define local classes in this function scope
        for item in func.body:
            if isinstance(item, ClassDef):
                self.st.define(item.name, ClassType(name=f"{scope_name}_{item.name}"))

        for param in func.params:
            self.st.define(param.name, param.type_annotation)

        func.body = self._check_body(func.body)
        func.scope = self.st.current_scope
        self.st.exit_scope()
        self._current_return_type = old_ret
        self._within_async = old_async


    def check_expr(self, expr) -> None:
        from ..frontend.ast_nodes import (
            IntLiteral,
            FloatLiteral,
            BoolLiteral,
            StrLiteral,
            Name,
            BinOp,
            UnaryOp,
            Comparison,
            BoolOp,
            ListLiteral,
            DictLiteral,
            TupleLiteral,
            Subscript,
            FunctionCall,
            AttributeExpr,
            MethodCall,
            SelfExpr,
            NewExpr,
            AwaitExpr,
            LambdaExpr,
            ListComp,
            DictComp,
            SetComp,
            Yield,
            YieldFrom,
            GeneratorExp,
        )

        if isinstance(expr, Name):
            t = self.st.lookup(expr.name)
            if t is None:
                raise self._err(
                    f"Undefined variable: '{expr.name}'",
                    expr.line,
                    expr.col,
                    cls=SemanticError,
                )
            expr.inferred_type = t
        elif isinstance(expr, AwaitExpr):
            if not self._within_async:
                raise self._err(
                    "'await' used outside async function",
                    expr.line,
                    expr.col,
                )
            self.check_expr(expr.value)
        elif isinstance(expr, AttributeExpr):
            self.check_expr(expr.value)
            val_type = self.inferencer.infer(expr.value)
            if isinstance(val_type, ExternalPythonType) and val_type.is_local:
                if val_type.name is None:
                    if self.st.cross_module_table:
                        sym = self.st.cross_module_table.lookup_symbol(val_type.module, expr.attr)
                        if sym is None:
                            raise self._sem_err(
                                f"Module '{val_type.module}' has no attribute '{expr.attr}'",
                                expr.line,
                                expr.col,
                            )
                else:
                    cls_info = self.st.lookup_class(val_type.name)
                    if cls_info:
                        has_field = self.st.get_field_type(val_type.name, expr.attr) is not None
                        has_method = expr.attr in cls_info.methods
                        if not has_method:
                            for base_name in cls_info.bases:
                                base_cls = self.st.lookup_class(base_name)
                                if base_cls and expr.attr in base_cls.methods:
                                    has_method = True
                                    break
                        if not has_field and not has_method:
                            raise self._sem_err(
                                f"Class '{val_type.name}' has no attribute '{expr.attr}'",
                                expr.line,
                                expr.col,
                            )
        elif isinstance(expr, MethodCall):
            self.check_expr(expr.value)
            val_type = self.inferencer.infer(expr.value)
            self._propagate_call_lambda_types(expr.method, val_type, expr.args, expr.keywords)
            for arg in expr.args:
                self.check_expr(arg)
            for kw in expr.keywords:
                self.check_expr(kw.value)
            if isinstance(val_type, ClassType):
                arity = len(expr.args)
                method_info = self.st.lookup_method(val_type.name, expr.method, arity)
                if method_info is None:
                    raise self._err(
                        f"Method '{expr.method}' with {arity} args not found in class '{val_type.name}'",
                        expr.line,
                        expr.col,
                    )
            elif isinstance(val_type, ExternalPythonType):
                if val_type.is_local:
                    if val_type.name is None:
                        if self.st.cross_module_table:
                            cls = self.st.cross_module_table.lookup_symbol(val_type.module, expr.method, "classes")
                            sig = self.st.cross_module_table.lookup_symbol(val_type.module, expr.method, "functions")
                            if cls is None and sig is None:
                                raise self._sem_err(
                                    f"Module '{val_type.module}' has no function or class '{expr.method}'",
                                    expr.line,
                                    expr.col,
                                )
                            if sig:
                                param_types, ret_type, _is_async, _type_params = sig
                                if len(expr.args) != len(param_types):
                                    raise self._sem_err(
                                        f"Function '{expr.method}' expects {len(param_types)} arguments, got {len(expr.args)}",
                                        expr.line,
                                        expr.col,
                                    )
                            elif cls:
                                arity = len(expr.args)
                                if arity not in cls.constructors:
                                    raise self._sem_err(
                                        f"Class '{expr.method}' constructor expects arities {list(cls.constructors.keys())}, got {arity}",
                                        expr.line,
                                        expr.col,
                                    )
                    else:
                        arity = len(expr.args)
                        method_info = self.st.lookup_method(val_type.name, expr.method, arity)
                        if method_info is None:
                            raise self._sem_err(
                                f"Method '{expr.method}' with {arity} args not found in class '{val_type.name}'",
                                expr.line,
                                expr.col,
                            )
        elif isinstance(expr, SelfExpr):
            if self.st.get_current_class() is None:
                raise self._err(
                    "'self' can only be used inside a class method",
                    expr.line,
                    expr.col,
                )
        elif isinstance(expr, NewExpr):
            for arg in expr.args:
                self.check_expr(arg)
            cls = self.st.lookup_class(expr.class_name)
            if cls is None:
                raise self._err(
                    f"Unknown class: '{expr.class_name}'",
                    expr.line,
                    expr.col,
                )
            arity = len(expr.args)
            ctor = self.st.lookup_constructor(expr.class_name, arity)
            if ctor is None:
                raise self._err(
                    f"No constructor found for '{expr.class_name}' with {arity} arguments",
                    expr.line,
                    expr.col,
                )
        elif isinstance(expr, BinOp):
            self.check_expr(expr.left)
            self.check_expr(expr.right)
            lt = self.inferencer.infer(expr.left)
            rt = self.inferencer.infer(expr.right)
            if lt is None or rt is None:
                raise self._err(
                    "Cannot infer operand types for binary operation",
                    expr.line,
                    expr.col,
                )
            # Check for string concatenation
            if (isinstance(lt, StrType) or isinstance(lt, UnknownType)) and (isinstance(rt, StrType) or isinstance(rt, UnknownType)) and expr.op == "+":
                pass  # Valid string concatenation (or potentially valid if unknown)
            # Check for string repetition (str * int or int * str)
            elif expr.op == "*" and (
                (isinstance(lt, (StrType, UnknownType)) and isinstance(rt, (IntType, UnknownType)))
                or (isinstance(lt, (IntType, UnknownType)) and isinstance(rt, (StrType, UnknownType)))
            ):
                pass  # Valid string repetition
            # Check for list repetition (list * int or int * list)
            elif expr.op == "*" and (
                (isinstance(lt, (ListType, UnknownType)) and isinstance(rt, (IntType, UnknownType)))
                or (isinstance(lt, (IntType, UnknownType)) and isinstance(rt, (ListType, UnknownType)))
            ):
                pass  # Valid list repetition
            # Check for list concatenation
            elif (
                expr.op == "+" and isinstance(lt, (ListType, UnknownType)) and isinstance(rt, (ListType, UnknownType))
            ):
                if type(lt.element_type) is type(rt.element_type):
                    pass  # Valid list concatenation
                else:
                    raise self._err(
                        f"Invalid operand types for '{expr.op}': list[{lt.element_type}] and list[{rt.element_type}]",
                        expr.line,
                        expr.col,
                    )
            elif isinstance(lt, ClassType):
                # Check for operator overloading via dunder methods
                op_to_dunder = {
                    "+": "__add__",
                    "-": "__sub__",
                    "*": "__mul__",
                    "/": "__truediv__",
                    "//": "__floordiv__",
                    "%": "__mod__",
                    "**": "__pow__",
                }
                dunder = op_to_dunder.get(expr.op)
                if dunder and self.st.lookup_method(lt.name, dunder, arity=1):
                    pass # Valid via dunder method
                else:
                    raise self._err(
                        f"Invalid operand types for '{expr.op}': {lt} and {rt}",
                        expr.line,
                        expr.col,
                    )
            elif not (
                isinstance(lt, (IntType, FloatType, UnknownType))
                and isinstance(rt, (IntType, FloatType, UnknownType))
            ):
                raise self._err(
                    f"Invalid operand types for '{expr.op}': {lt} and {rt}",
                    expr.line,
                    expr.col,
                )
        elif isinstance(expr, UnaryOp):
            self.check_expr(expr.operand)
            t = self.inferencer.infer(expr.operand)
            if expr.op == "not":
                if t is None:
                    raise self._err(
                        "Cannot infer operand type for 'not'", expr.line, expr.col
                    )
            else:  # +, -
                if not isinstance(t, (IntType, FloatType)):
                    raise self._err(
                        f"Invalid operand type for '{expr.op}': {t}",
                        expr.line,
                        expr.col,
                    )
        elif isinstance(expr, Comparison):
            self.check_expr(expr.left)
            self.check_expr(expr.right)
        elif isinstance(expr, BoolOp):
            for val in expr.values:
                self.check_expr(val)
        elif isinstance(expr, ListLiteral):
            expr.inferred_type = self.inferencer.infer(expr)
            for e in expr.elements:
                self.check_expr(e)
        elif isinstance(expr, DictLiteral):
            for k, v in expr.pairs:
                self.check_expr(k)
                self.check_expr(v)
        elif isinstance(expr, TupleLiteral):
            for e in expr.elements:
                self.check_expr(e)
        elif isinstance(expr, Subscript):
            self.check_expr(expr.value)
            self.check_expr(expr.index)
            vt = self.inferencer.infer(expr.value)
            if isinstance(vt, ListType) or isinstance(vt, StrType):
                it = self.inferencer.infer(expr.index)
                if not isinstance(it, (IntType, SliceType)):
                    raise self._err(
                        f"Subscript index must be int or slice, got {it}", expr.line, expr.col
                    )
        elif isinstance(expr, FunctionCall):
            if expr.name == "open":
                if len(expr.args) < 1:
                    raise self._err(
                        "open() requires at least 1 argument (path)",
                        expr.line,
                        expr.col,
                    )
                self.check_expr(expr.args[0])
                path_type = self.inferencer.infer(expr.args[0])
                if not isinstance(path_type, StrType):
                    raise self._err(
                        f"open() path must be str, got {path_type}",
                        expr.line,
                        expr.col,
                    )
                if len(expr.args) > 1:
                    self.check_expr(expr.args[1])
                    mode_type = self.inferencer.infer(expr.args[1])
                    if not isinstance(mode_type, StrType):
                        raise self._err(
                            f"open() mode must be str, got {mode_type}",
                            expr.line,
                            expr.col,
                        )
            elif expr.name == "isinstance":
                if len(expr.args) != 2:
                    raise self._err(
                        f"isinstance() expected 2 arguments, got {len(expr.args)}",
                        expr.line,
                        expr.col,
                    )
                self.check_expr(expr.args[0])
            elif expr.name == "len":
                if len(expr.args) != 1:
                    raise self._err(
                        f"len() expected 1 argument, got {len(expr.args)}",
                        expr.line,
                        expr.col,
                    )
                self.check_expr(expr.args[0])
                arg_t = self.inferencer.infer(expr.args[0])
                if not isinstance(arg_t, (ListType, StrType, DictType, SetType)):
                    raise self._err(
                        f"len() argument must be list, str, dict, or set, got {arg_t}",
                        expr.line,
                        expr.col,
                    )
            elif expr.name in ("str", "int", "float", "bool"):
                if len(expr.args) != 1:
                    raise self._err(
                        f"{expr.name}() expected 1 argument, got {len(expr.args)}",
                        expr.line,
                        expr.col,
                    )
                self.check_expr(expr.args[0])
            elif expr.name in ("list", "set", "dict"):
                for arg in expr.args:
                    self.check_expr(arg)
            elif expr.name in ("zip", "enumerate", "map", "filter", "sorted", "reversed"):
                if expr.name in ("map", "filter", "sorted"):
                    self._propagate_call_lambda_types(expr.name, None, expr.args, expr.keywords)
                for arg in expr.args:
                    self.check_expr(arg)
                for kw in expr.keywords:
                    self.check_expr(kw.value)
            else:
                sig = self.st.lookup_function(expr.name)
                if sig is None:
                    curr_type = self.st.lookup(expr.name)
                    if isinstance(curr_type, ClassType):
                        cls_info = self.st.lookup_class(curr_type.name)
                        if cls_info:
                            self._check_constructor_arity(cls_info, expr.args, expr.line, expr.col, curr_type.name)
                            for arg in expr.args:
                                self.check_expr(arg)
                    elif isinstance(curr_type, FunctionType):
                        self._propagate_call_lambda_types(expr.name, curr_type, expr.args, expr.keywords)
                        if len(expr.args) != len(curr_type.param_types):
                            raise self._err(
                                f"Function '{expr.name}' expected {len(curr_type.param_types)} arguments, got {len(expr.args)}",
                                expr.line,
                                expr.col,
                            )
                        for i, arg in enumerate(expr.args):
                            self.check_expr(arg)
                            arg_t = self.inferencer.infer(arg)
                            if not _types_compatible(curr_type.param_types[i], arg_t):
                                raise self._err(
                                    f"Argument type mismatch for '{expr.name}': expected {curr_type.param_types[i]}, got {arg_t}",
                                    arg.line,
                                    arg.col,
                                )
                    elif isinstance(curr_type, UnknownType):
                        # Allow calls to unknown types (potential lambdas)
                        for arg in expr.args:
                            self.check_expr(arg)
                    elif isinstance(curr_type, ExternalPythonType):
                        is_class = False
                        if curr_type.is_local and self.st.cross_module_table:
                            cls_info = self.st.cross_module_table.lookup_symbol(curr_type.module, curr_type.name or expr.name, "classes")
                            if cls_info:
                                is_class = True
                                self._check_constructor_arity(cls_info, expr.args, expr.line, expr.col, curr_type.name or expr.name)
                                for arg in expr.args:
                                    self.check_expr(arg)
                        if not is_class:
                            # Always valid for external types (resolved at runtime)
                            self._propagate_call_lambda_types(expr.name, curr_type, expr.args, expr.keywords)
                            for arg in expr.args:
                                self.check_expr(arg)
                            for kw in expr.keywords:
                                self.check_expr(kw.value)
                    elif self.st.lookup_class(expr.name):
                        cls_info = self.st.lookup_class(expr.name)
                        self._check_constructor_arity(cls_info, expr.args, expr.line, expr.col, expr.name)
                        for arg in expr.args:
                            self.check_expr(arg)
                    else:
                        raise self._err(
                            f"Undefined function: '{expr.name}'",
                            expr.line,
                            expr.col,
                            cls=SemanticError,
                        )
                else:
                    params, _, _, _ = sig
                    func_type = FunctionType(param_types=tuple(params), return_type=UnknownType())
                    self._propagate_call_lambda_types(expr.name, func_type, expr.args, expr.keywords)
                    if len(expr.args) != len(params):
                        raise self._err(
                            f"Function '{expr.name}' expected {len(params)} arguments, got {len(expr.args)}",
                            expr.line,
                            expr.col,
                        )
                    for i, arg in enumerate(expr.args):
                        self.check_expr(arg)
                        arg_t = self.inferencer.infer(arg)
                        if not _types_compatible(params[i], arg_t):
                            raise self._err(
                                f"Argument type mismatch for '{expr.name}': expected {params[i]}, got {arg_t}",
                                arg.line,
                                arg.col,
                            )
        elif isinstance(expr, LambdaExpr):
            self._check_lambda(expr)
        elif isinstance(expr, (ListComp, DictComp, SetComp, GeneratorExp)):
            self._check_comprehension(expr)
        elif isinstance(expr, Yield):
            if expr.value:
                self.check_expr(expr.value)
                if self._current_return_type:
                    expected_yield_t = _get_yield_item_type(self._current_return_type)
                    if expected_yield_t:
                        yielded_t = self.inferencer.infer(expr.value)
                        if yielded_t and not _types_compatible(expected_yield_t, yielded_t):
                            raise self._err(
                                f"Yield type mismatch: expected {expected_yield_t}, got {yielded_t}",
                                expr.line,
                                expr.col,
                            )
        elif isinstance(expr, YieldFrom):
            self.check_expr(expr.value)
            if self._current_return_type:
                expected_yield_t = _get_yield_item_type(self._current_return_type)
                if expected_yield_t:
                    yielded_from_t = self.inferencer.infer(expr.value)
                    if yielded_from_t:
                        yielded_item_t = _get_iterable_item_type(yielded_from_t)
                        if yielded_item_t and not _types_compatible(expected_yield_t, yielded_item_t):
                            raise self._err(
                                f"Yield from type mismatch: expected elements compatible with {expected_yield_t}, got elements of {yielded_item_t}",
                                expr.line,
                                expr.col,
                            )
        elif isinstance(expr, JoinedStr):
            for v in expr.values:
                self.check_expr(v)
        elif isinstance(expr, FormattedValue):
            self.check_expr(expr.value)

    def _check_body(self, body):
        if not body:
            return body
        new_body = list(body)
        for i, stmt in enumerate(new_body):
            transformed = self.st.pm.transform_ast(stmt, self)
            new_body[i] = transformed
            self.check_stmt(transformed)
        return tuple(new_body) if isinstance(body, tuple) else new_body

    def check_stmt(self, stmt) -> None:
        from ..frontend.ast_nodes import (
            VarDecl,
            Assign,
            AugAssign,
            IfStmt,
            WhileStmt,
            ForRange,
            ReturnStmt,
            PrintStmt,
            SubscriptAssign,
            BreakStmt,
            ContinueStmt,
            DelStmt,
            ForIter,
            TryStmt,
            RaiseStmt,
            ClassDef,
            FunctionDef,
            WithStmt,
            AssertStmt,
            GlobalStmt,
            NonlocalStmt,
            MatchStmt,
            EnumDef,
            PassStmt,
        )

        # Plugins can also transform nested statements
        # But we must be careful not to recurse infinitely if the plugin doesn't change anything
        # The PluginManager should handle idempotency or specifically targeted nodes.

        if isinstance(stmt, ReturnStmt):
            if stmt.value:
                self.check_expr(stmt.value)
                val_type = self.inferencer.infer(stmt.value)
                if not _types_compatible(self._current_return_type, val_type):
                    raise self._err(
                        f"Returning '{val_type}' where '{self._current_return_type}' was expected",
                        stmt.line,
                        stmt.col,
                    )
        elif isinstance(stmt, ClassDef):
            prefix = f"{self.st.current_scope.name}_"
            self.check_class(stmt, prefix=prefix)

        elif isinstance(stmt, VarDecl):
            self.check_expr(stmt.value)
            inferred = self.inferencer.infer(stmt.value)
            ann = stmt.type_annotation
            if ann is not None and inferred is not None:
                if not _types_compatible(ann, inferred):
                    raise self._err(
                        f"Type mismatch: variable '{stmt.name}' declared as {ann} but value is {inferred}",
                        stmt.line,
                        stmt.col,
                    )
            actual_type = ann if ann is not None else inferred
            if actual_type is None:
                raise self._err(
                    f"Cannot infer type for '{stmt.name}'", stmt.line, stmt.col
                )
            self.st.define(stmt.name, actual_type)

        elif isinstance(stmt, Assign):
            self.check_expr(stmt.value)
            if stmt.target == "_":
                return
            if isinstance(stmt.target, tuple) and len(stmt.target) > 0 and stmt.target[0] == "attr":
                if len(stmt.target) == 3 and stmt.target[1] == "self":
                    class_name = self.st.get_current_class()
                    if class_name:
                        cls = self.st.lookup_class(class_name)
                        if cls and stmt.target[2] in cls.fields:
                            if isinstance(cls.fields[stmt.target[2]], UnknownType):
                                inferred = self.inferencer.infer(stmt.value)
                                if inferred is not None and not isinstance(inferred, UnknownType):
                                    cls.fields[stmt.target[2]] = inferred
                return
            if isinstance(stmt.target, tuple):
                val_t = self.inferencer.infer(stmt.value)
                if isinstance(val_t, TupleType):
                    for i, t_name in enumerate(stmt.target):
                        self.st.define(t_name, val_t.element_types[i])
                else:
                    for t_name in stmt.target:
                        self.st.define(t_name, IntType())
                return
            existing = self.st.lookup(stmt.target)
            inferred = self.inferencer.infer(stmt.value)
            if existing is None:
                if inferred is None:
                    raise self._err(
                        f"Cannot infer type for '{stmt.target}'", stmt.line, stmt.col
                    )
                self.st.define(stmt.target, inferred)
            else:
                if inferred is not None and not _types_compatible(existing, inferred):
                    raise self._err(
                        f"Type mismatch: cannot assign {inferred} to '{stmt.target}' (type {existing})",
                        stmt.line,
                        stmt.col,
                    )
        elif isinstance(stmt, AugAssign):
            self.check_expr(stmt.value)
            existing = self.st.lookup(stmt.target)
            if existing is None:
                raise self._err(
                    f"Undefined variable '{stmt.target}'", stmt.line, stmt.col
                )
            inferred = self.inferencer.infer(stmt.value)
            if inferred is not None and not _types_compatible(existing, inferred):
                raise self._err(
                    f"Type mismatch in augmented assignment: cannot apply operation to {existing} and {inferred}",
                    stmt.line,
                    stmt.col,
                )
        elif isinstance(stmt, IfStmt):
            self.check_expr(stmt.condition)
            cond_type = self.inferencer.infer(stmt.condition)
            if cond_type is not None and not isinstance(cond_type, BoolType):
                raise self._err(
                    f"'if' condition must be bool, got {cond_type}", stmt.line, stmt.col
                )
            stmt.then_body = self._check_body(stmt.then_body)
            new_elif = []
            for cond, body in stmt.elif_clauses:
                self.check_expr(cond)
                elif_cond_type = self.inferencer.infer(cond)
                if elif_cond_type is not None and not isinstance(elif_cond_type, BoolType):
                    raise self._err(
                        f"'elif' condition must be bool, got {elif_cond_type}",
                        stmt.line,
                        stmt.col,
                    )
                new_elif.append((cond, self._check_body(body)))
            stmt.elif_clauses = tuple(new_elif)
            if stmt.else_body:
                stmt.else_body = self._check_body(stmt.else_body)
        elif isinstance(stmt, WhileStmt):
            self.check_expr(stmt.condition)
            cond_type = self.inferencer.infer(stmt.condition)
            if cond_type is None:
                raise self._err(
                    "Cannot infer type for 'while' condition", stmt.line, stmt.col
                )
            stmt.body = self._check_body(stmt.body)
        elif isinstance(stmt, ForRange):
            self.check_expr(stmt.start)
            self.check_expr(stmt.stop)
            if stmt.step:
                self.check_expr(stmt.step)
            for arg_name, arg in [("start", stmt.start), ("stop", stmt.stop), ("step", stmt.step)]:
                if arg is not None:
                    arg_t = self.inferencer.infer(arg)
                    if arg_t is not None and not isinstance(arg_t, IntType):
                        raise self._err(f"range() {arg_name} must be int, got {arg_t}", stmt.line, stmt.col)
            from ..frontend.ast_nodes import Name
            target_name = stmt.target.name if isinstance(stmt.target, Name) else stmt.target
            existing = self.st.lookup(target_name)
            if existing is not None and not isinstance(existing, IntType):
                 raise self._err(f"Cannot use '{target_name}' as loop target: already defined as {existing}", stmt.line, stmt.col)
            self.st.define(target_name, IntType())
            stmt.body = self._check_body(stmt.body)
        elif isinstance(stmt, ForIter):
            self.check_expr(stmt.iterable)
            it_t = self.inferencer.infer(stmt.iterable)
            elem_t = IntType()
            if isinstance(it_t, ListType):
                elem_t = it_t.element_type
            elif isinstance(it_t, IteratorType):
                elem_t = it_t.element_type
            elif isinstance(it_t, IterableType):
                elem_t = it_t.element_type
            elif isinstance(it_t, GeneratorType):
                elem_t = it_t.yield_type
            elif isinstance(it_t, StrType):
                elem_t = StrType()
            elif isinstance(it_t, DictType):
                elem_t = it_t.key_type
            
            if isinstance(stmt.target, str):
                self.st.define(stmt.target, elem_t)
            else:
                self._bind_target(stmt.target, elem_t)
            stmt.body = self._check_body(stmt.body)
        elif isinstance(stmt, TryStmt):
            stmt.body = self._check_body(stmt.body)
            new_handlers = []
            for h_type, h_name, h_body in stmt.handlers:
                if h_name:
                    self.st.define(h_name, StrType())
                new_handlers.append((h_type, h_name, self._check_body(h_body)))
            stmt.handlers = tuple(new_handlers)
            if hasattr(stmt, "finally_body") and stmt.finally_body:
                stmt.finally_body = self._check_body(stmt.finally_body)
        elif isinstance(stmt, PrintStmt):
            for v in stmt.values:
                self.check_expr(v)
        elif isinstance(stmt, MatchStmt):
            self._check_match(stmt)
        elif isinstance(stmt, EnumDef):
            self.check_enum(stmt)
        elif isinstance(stmt, SubscriptAssign):
            self.check_expr(stmt.target)
            self.check_expr(stmt.index)
            self.check_expr(stmt.value)
        elif isinstance(stmt, DelStmt):
            self.check_expr(stmt.target)
            if stmt.key:
                self.check_expr(stmt.key)
        elif isinstance(stmt, (BreakStmt, ContinueStmt, PassStmt, GlobalStmt, NonlocalStmt)):
            pass
        elif isinstance(stmt, RaiseStmt):
            if stmt.value:
                self.check_expr(stmt.value)
            if getattr(stmt, "cause", None):
                self.check_expr(stmt.cause)
        elif isinstance(stmt, WithStmt):
            self.check_with(stmt)
        elif isinstance(stmt, AssertStmt):
            self.check_expr(stmt.test)
            if stmt.msg:
                self.check_expr(stmt.msg)
        elif isinstance(stmt, FunctionDef):
            # Already handled by top level module pass but if we encounter it inside check_stmt
            # (e.g. nested functions), handle it.
            self.check_func_def(stmt)
        else:
            raise self._err(
                f"Unsupported statement type: {type(stmt).__name__}",
                stmt.line,
                stmt.col,
                cls=SemanticError,
            )

    def check_enum(self, node: EnumDef) -> None:
        variants = {}
        for name, _ in node.variants:
            if name in variants:
                raise self._err(f"Duplicate enum variant: {name}", node.line, node.col, SemanticError)
            variants[name] = None
        self.st.define_enum(node.name, variants)
        self.st.define(node.name, EnumType(name=node.name))

    def _check_match(self, node: MatchStmt) -> None:
        subject_type = self.inferencer.infer(node.subject)
        if subject_type is None:
            raise self._err("Cannot infer subject type of match statement", node.line, node.col, Py2RustTypeError)

        for case in node.cases:
            # Each case should establish its own scope if it has bindings
            # But for simplicity we'll let patterns define in current scope for now
            # as Python pattern matching bindings persist after match block
            self._check_pattern(case.pattern, subject_type)
            if case.guard:
                guard_type = self.inferencer.infer(case.guard)
                if not isinstance(guard_type, BoolType):
                    raise self._err("Match guard must be a boolean expression", case.guard.line, case.guard.col, Py2RustTypeError)
            case.body = self._check_body(case.body)

    def _check_pattern(self, pattern: MatchPattern, subject_type: object) -> None:
        if isinstance(pattern, ValuePattern):
            val_type = self.inferencer.infer(pattern.value)
            if val_type and not _types_compatible(subject_type, val_type):
                raise self._err(f"Pattern type {val_type} incompatible with subject type {subject_type}", pattern.line, pattern.col, Py2RustTypeError)
        elif isinstance(pattern, NamePattern):
            self.st.define(pattern.name, subject_type)
        elif isinstance(pattern, WildcardPattern):
            pass
        elif isinstance(pattern, OrPattern):
            for p in pattern.patterns:
                self._check_pattern(p, subject_type)
        elif isinstance(pattern, AsPattern):
            self._check_pattern(pattern.pattern, subject_type)
            self.st.define(pattern.name, subject_type)
        elif isinstance(pattern, ClassPattern):
            # Handle both class matching and enum variant matching
            if isinstance(subject_type, EnumType):
                enum_info = self.st.lookup_enum(subject_type.name)
                if enum_info and pattern.class_name not in enum_info.variants:
                     raise self._err(f"Unknown variant {pattern.class_name} for enum {subject_type.name}", pattern.line, pattern.col, SemanticError)
            elif isinstance(subject_type, ClassType):
                if pattern.class_name != subject_type.name:
                     # For now, require exact class match
                     raise self._err(f"Class pattern {pattern.class_name} does not match subject type {subject_type.name}", pattern.line, pattern.col, Py2RustTypeError)
            else:
                raise self._err(f"Class pattern applied to non-ADT subject type {subject_type}", pattern.line, pattern.col, Py2RustTypeError)
            
            for p in pattern.patterns:
                 self._check_pattern(p, subject_type) # Recursive check for positional args?
        else:
            raise self._err(f"Unsupported pattern type: {type(pattern).__name__}", 0, 0, SemanticError)

    def _propagate_call_lambda_types(self, func_name: Optional[str], func_type: Optional[object], args: tuple, keywords: tuple) -> None:
        # 1. Built-in: map
        if func_name == "map" and len(args) >= 2:
            self.check_expr(args[1])
            it_type = self.inferencer.infer(args[1])
            elem_t = _get_iterable_item_type(it_type) or UnknownType()
            if isinstance(args[0], LambdaExpr):
                args[0].inferred_param_types = (elem_t,)
                
        # 2. Built-in: filter
        elif func_name == "filter" and len(args) >= 2:
            self.check_expr(args[1])
            it_type = self.inferencer.infer(args[1])
            elem_t = _get_iterable_item_type(it_type) or UnknownType()
            if isinstance(args[0], LambdaExpr):
                args[0].inferred_param_types = (elem_t,)
                
        # 3. Built-in: sorted
        elif func_name == "sorted" and len(args) >= 1:
            self.check_expr(args[0])
            it_type = self.inferencer.infer(args[0])
            elem_t = _get_iterable_item_type(it_type) or UnknownType()
            for kw in keywords:
                if kw.arg == "key":
                    if isinstance(kw.value, LambdaExpr):
                        kw.value.inferred_param_types = (elem_t,)
                    break
                    
        # 4. Built-in: reduce (either name "reduce" or imported)
        elif (func_name == "reduce" or 
              (isinstance(func_type, ExternalPythonType) and func_type.module == "functools")) and len(args) >= 2:
            self.check_expr(args[1])
            it_type = self.inferencer.infer(args[1])
            elem_t = _get_iterable_item_type(it_type) or UnknownType()
            initial_t = None
            if len(args) > 2:
                self.check_expr(args[2])
                initial_t = self.inferencer.infer(args[2])
            for kw in keywords:
                if kw.arg in ("initial", "initializer"):
                    self.check_expr(kw.value)
                    initial_t = self.inferencer.infer(kw.value)
                    break
            acc_t = initial_t if initial_t is not None else elem_t
            if isinstance(args[0], LambdaExpr):
                args[0].inferred_param_types = (acc_t, elem_t)
                
        # 5. User-defined / cross-module callable
        elif isinstance(func_type, FunctionType):
            for i, arg in enumerate(args):
                if i < len(func_type.param_types):
                    param_t = func_type.param_types[i]
                    if isinstance(param_t, FunctionType) and isinstance(arg, LambdaExpr):
                        arg.inferred_param_types = param_t.param_types

    def _check_lambda(self, expr: LambdaExpr) -> None:
        self.st.enter_scope("lambda")
        param_types = getattr(expr, "inferred_param_types", None)
        for i, param in enumerate(expr.params):
            p_type = param_types[i] if param_types and i < len(param_types) else UnknownType()
            self.st.define(param.name, p_type)
        self.check_expr(expr.body)
        self.st.exit_scope()

    def _check_comprehension(self, expr: Union[ListComp, DictComp, SetComp, GeneratorExp]) -> None:
        self.st.enter_scope("comprehension")
        for gen in expr.generators:
            self.check_expr(gen.iterable)
            it_t = self.inferencer.infer(gen.iterable)
            
            elem_t = IntType()
            if isinstance(it_t, ListType):
                elem_t = it_t.element_type
            elif isinstance(it_t, IteratorType):
                elem_t = it_t.element_type
            elif isinstance(it_t, IterableType):
                elem_t = it_t.element_type
            elif isinstance(it_t, GeneratorType):
                elem_t = it_t.yield_type
            elif isinstance(it_t, StrType):
                elem_t = StrType()
            elif isinstance(it_t, DictType):
                elem_t = it_t.key_type  # Iterating dict yields keys
            
            self._bind_target(gen.target, elem_t)
            for if_expr in gen.ifs:
                self.check_expr(if_expr)
        
        if isinstance(expr, ListComp):
            self.check_expr(expr.elt)
        elif isinstance(expr, SetComp):
            self.check_expr(expr.elt)
        elif isinstance(expr, GeneratorExp):
            self.check_expr(expr.elt)
        elif isinstance(expr, DictComp):
            self.check_expr(expr.key)
            self.check_expr(expr.value)
            
        self.st.exit_scope()

    def check_with(self, node: WithStmt) -> None:
        self.st.enter_scope("with")
        for item in node.items:
            self.check_expr(item.context_expr)
            if item.optional_vars:
                ctx_t = self.inferencer.infer(item.context_expr)
                res_t = UnknownType()
                # File handle: the bound var has file type
                if isinstance(ctx_t, FileType):
                    res_t = FileType()
                # Mutex/Lock: bound var is the guard (opaque → UnknownType)
                elif isinstance(ctx_t, ClassType) and _is_mutex_like_name(ctx_t.name):
                    res_t = UnknownType()
                # Custom context manager with __enter__/__exit__: still UnknownType
                elif isinstance(ctx_t, ClassType):
                    res_t = UnknownType()
                self._bind_target(item.optional_vars, res_t)
        node.body = self._check_body(node.body)
        node.scope = self.st.current_scope
        self.st.exit_scope()

    def _bind_target(self, target, target_type):
        from ..frontend.ast_nodes import Name, TupleLiteral
        if isinstance(target, Name):
            self.st.define(target.name, target_type)
        elif isinstance(target, str):
            self.st.define(target, target_type)
        elif isinstance(target, TupleLiteral):
            if isinstance(target_type, TupleType):
                for t, et in zip(target.elements, target_type.element_types):
                    self._bind_target(t, et)
            elif isinstance(target_type, ListType):
                # Unpacking list: assume all elements match list's element type
                for t in target.elements:
                    self._bind_target(t, target_type.element_type)
            else:
                # Default fallback
                for t in target.elements:
                    self._bind_target(t, UnknownType())

    def _check_constructor_arity(self, cls_info, expr_args, expr_line, expr_col, class_name):
        valid_arities = self._get_constructor_arities(cls_info)
        if not valid_arities:
            # Default constructor takes 0 arguments
            valid_arities.add(0)
            
        call_arity = len(expr_args)
        if call_arity not in valid_arities:
            raise self._sem_err(
                f"Class '{class_name}' constructor expects arities {sorted(list(valid_arities))}, got {call_arity}",
                expr_line,
                expr_col,
            )

    def _get_constructor_arities(self, cls_info) -> set[int]:
        valid_arities = set()
        if cls_info.constructors:
            for c_arity, c_def in cls_info.constructors.items():
                if c_def.params and c_def.params[0].name == "self":
                    valid_arities.add(c_arity - 1)
                else:
                    valid_arities.add(c_arity)
        else:
            for base in cls_info.bases:
                base_cls = self.st.lookup_class(base)
                if not base_cls and self.st.cross_module_table:
                    for mod_name, mod_st in self.st.cross_module_table.modules.items():
                        if base in mod_st._classes:
                            base_cls = mod_st._classes[base]
                            break
                if base_cls:
                    valid_arities.update(self._get_constructor_arities(base_cls))
            if not valid_arities:
                valid_arities.add(0)
                valid_arities.add(len(cls_info.fields))
        return valid_arities

    def _extract_class_names(self, t) -> list[str]:
        from ..frontend.ast_nodes import ClassType, OptionalType, UnionType, TupleType
        from py2rust.middleend.symbol_table import ExternalPythonType
        names = []
        if isinstance(t, ClassType):
            names.append(t.name)
        elif isinstance(t, ExternalPythonType) and t.is_local:
            if t.name:
                names.append(t.name)
        elif isinstance(t, OptionalType):
            names.extend(self._extract_class_names(t.inner_type))
        elif isinstance(t, UnionType):
            for et in t.variants:
                names.extend(self._extract_class_names(et))
        elif isinstance(t, TupleType):
            for et in t.element_types:
                names.extend(self._extract_class_names(et))
        return names

    def _check_class_field_cycles(self):
        for class_name, cls_info in list(self.st._classes.items()):
            visited = set()
            path = []
            
            def dfs(curr_cls_name, curr_cls_info):
                if curr_cls_name in path:
                    cycle = " -> ".join(path + [curr_cls_name])
                    raise self._sem_err(
                        f"Unsupported circular/recursive class field layout detected: {cycle}"
                    )
                if curr_cls_name in visited:
                    return
                
                path.append(curr_cls_name)
                for f_name, f_type in curr_cls_info.fields.items():
                    target_names = self._extract_class_names(f_type)
                    for target_cls_name in target_names:
                        target_cls_info = self.st.lookup_class(target_cls_name)
                        if not target_cls_info and self.st.cross_module_table:
                            for mod_name, mod_st in self.st.cross_module_table.modules.items():
                                if target_cls_name in mod_st._classes:
                                    target_cls_info = mod_st._classes[target_cls_name]
                                    break
                        
                        if target_cls_info:
                            dfs(target_cls_name, target_cls_info)
                
                path.pop()
                visited.add(curr_cls_name)

            dfs(class_name, cls_info)

