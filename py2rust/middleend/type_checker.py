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
        return True
    if isinstance(a, FloatType) and isinstance(b, IntType):
        # f64 accepts i32, but Vec<f64> does NOT accept Vec<i32>
        return not invariant
    if isinstance(a, ExternalPythonType) or isinstance(b, ExternalPythonType):
        return True
    if isinstance(a, (EnumType, ClassType)) and isinstance(b, (EnumType, ClassType)):
        return getattr(a, "name", None) == getattr(b, "name", None)
    return False


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
        # Process Imports first to load plugins
        for imp in module.imports:
            plugin = None
            if isinstance(imp, Import):
                for alias in imp.names:
                    if plugin is None and not getattr(self.st.config, "mock_mode", False):
                        raise self._sem_err(f"Unsupported import: '{alias.name}'. No plugin found and mock_mode is disabled.", imp.line, imp.col)
                    
                    # Register alias in symbol table
                    alias_name = alias.asname if alias.asname else alias.name
                    self.st.define(alias_name, ExternalPythonType(module=alias.name))
            elif isinstance(imp, ImportFrom):
                if imp.module:
                    plugin = self.st.pm.load_plugin(imp.module)
                    if plugin is None and not getattr(self.st.config, "mock_mode", False):
                        raise self._sem_err(f"Unsupported import: '{imp.module}'. No plugin found and mock_mode is disabled.", imp.line, imp.col)
                    
                    for alias in imp.names:
                        alias_name = alias.asname if alias.asname else alias.name
                        self.st.define(alias_name, ExternalPythonType(module=imp.module, name=alias.name))
            # Call transform_ast to allow plugins to register aliases/members
            self.st.pm.transform_ast(imp, self)

        # Allow plugins to transform the whole module (e.g. ClassDef -> EnumDef)
        module = self.st.pm.transform_module(module, self)

        # Pre-scan all classes (including nested ones)
        self._collect_all_classes(module.classes)
        self._collect_all_classes(module.functions)

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

        for func in module.functions:
            self.check_function(func)

        new_stmts = []
        for stmt in module.statements:
            if type(stmt).__name__ == "IfStmt" and self._is_main_check(stmt.condition):
                # Stop type checking subsequent top-level code
                break
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

        # Define local classes in this function scope
        for item in func.body:
            if isinstance(item, ClassDef):
                self.st.define(item.name, ClassType(name=f"{self.st.current_scope.name}_{item.name}"))

        for param in func.params:
            self.st.define(param.name, param.type_annotation)

        for stmt in func.body:
            self.check_stmt(stmt)

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
        )

        if isinstance(expr, Name):
            if self.st.lookup(expr.name) is None:
                raise self._err(
                    f"Undefined variable: '{expr.name}'",
                    expr.line,
                    expr.col,
                    cls=SemanticError,
                )
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
        elif isinstance(expr, MethodCall):
            self.check_expr(expr.value)
            for arg in expr.args:
                self.check_expr(arg)
            val_type = self.inferencer.infer(expr.value)
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
                # Always valid for external types (resolved at runtime)
                pass
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
            for elem in expr.elements:
                self.check_expr(elem)
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
                if not isinstance(it, IntType):
                    raise self._err(
                        f"Subscript index must be int, got {it}", expr.line, expr.col
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
            elif expr.name in ("zip", "enumerate", "map", "reversed"):
                for arg in expr.args:
                    self.check_expr(arg)
            else:
                sig = self.st.lookup_function(expr.name)
                if sig is None:
                    curr_type = self.st.lookup(expr.name)
                    if isinstance(curr_type, ClassType):
                        cls_info = self.st.lookup_class(curr_type.name)
                        if cls_info:
                            pass
                    elif isinstance(curr_type, FunctionType):
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
                        # Always valid for external types (resolved at runtime)
                        for arg in expr.args:
                            self.check_expr(arg)
                    elif self.st.lookup_class(expr.name):
                        pass
                    else:
                        raise self._err(
                            f"Undefined function: '{expr.name}'",
                            expr.line,
                            expr.col,
                            cls=SemanticError,
                        )
                else:
                    params, _, _, _ = sig
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
        elif isinstance(expr, (ListComp, DictComp, SetComp)):
            self._check_comprehension(expr)
        elif isinstance(expr, JoinedStr):
            for v in expr.values:
                self.check_expr(v)
        elif isinstance(expr, FormattedValue):
            self.check_expr(expr.value)

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
        )

        node_name = type(stmt).__name__
        if node_name == "ReturnStmt":
            if stmt.value:
                self.check_expr(stmt.value)
                val_type = self.inferencer.infer(stmt.value)
                if not _types_compatible(self._current_return_type, val_type):
                    raise self._err(
                        f"Returning '{val_type}' where '{self._current_return_type}' was expected",
                        stmt.line,
                        stmt.col,
                    )
        elif node_name == "ClassDef":
            prefix = f"{self.st.current_scope.name}_"
            self.check_class(stmt, prefix=prefix)

        if isinstance(stmt, VarDecl):
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
            for s in stmt.then_body:
                self.check_stmt(s)
            for cond, body in stmt.elif_clauses:
                self.check_expr(cond)
                elif_cond_type = self.inferencer.infer(cond)
                if elif_cond_type is not None and not isinstance(elif_cond_type, BoolType):
                    raise self._err(
                        f"'elif' condition must be bool, got {elif_cond_type}",
                        stmt.line,
                        stmt.col,
                    )
                for s in body:
                    self.check_stmt(s)
            if stmt.else_body:
                for s in stmt.else_body:
                    self.check_stmt(s)
        elif isinstance(stmt, ForIter):
            self.check_expr(stmt.iterable)
            it_t = self.inferencer.infer(stmt.iterable)
            elem_t = IntType()
            if isinstance(it_t, ListType):
                elem_t = it_t.element_type
            elif isinstance(it_t, StrType):
                elem_t = StrType()
            elif isinstance(it_t, DictType):
                elem_t = it_t.key_type
            
            if isinstance(stmt.target, str):
                self.st.define(stmt.target, elem_t)
            else:
                self._bind_target(stmt.target, elem_t)
            for s in stmt.body:
                self.check_stmt(s)
        elif isinstance(stmt, TryStmt):
            for s in stmt.body:
                self.check_stmt(s)
            for _, h_name, h_body in stmt.handlers:
                if h_name:
                    self.st.define(h_name, StrType())
                for s in h_body:
                    self.check_stmt(s)
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
        elif isinstance(stmt, GlobalStmt):
            pass
        elif isinstance(stmt, NonlocalStmt):
            pass
        elif isinstance(stmt, WhileStmt):
            self.check_expr(stmt.condition)
            cond_type = self.inferencer.infer(stmt.condition)
            if cond_type is None:
                raise self._err(
                    "Cannot infer type for 'while' condition", stmt.line, stmt.col
                )
            for s in stmt.body:
                self.check_stmt(s)
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
            for s in stmt.body:
                self.check_stmt(s)
        elif isinstance(stmt, ReturnStmt):
            if stmt.value is not None:
                self.check_expr(stmt.value)
                ret_type = self.inferencer.infer(stmt.value)
                if ret_type is not None and self._current_return_type is not None:
                    if not _types_compatible(self._current_return_type, ret_type):
                        raise self._err(
                            f"Return type mismatch: expected {self._current_return_type}, got {ret_type}",
                            stmt.line,
                            stmt.col,
                        )
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
            self.check_expr(stmt.key)
        elif isinstance(stmt, (BreakStmt, ContinueStmt)):
            pass
        elif isinstance(stmt, (ClassDef, FunctionDef, ReturnStmt, PassStmt)):
            pass
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
            for stmt in case.body:
                self.check_stmt(stmt)

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

    def _check_lambda(self, expr: LambdaExpr) -> None:
        self.st.enter_scope("lambda")
        for param in expr.params:
            # Lambda params are untyped in Python; default to UnknownType
            self.st.define(param.name, UnknownType())
        self.check_expr(expr.body)
        self.st.exit_scope()

    def _check_comprehension(self, expr: Union[ListComp, DictComp, SetComp]) -> None:
        self.st.enter_scope("comprehension")
        for gen in expr.generators:
            self.check_expr(gen.iterable)
            it_t = self.inferencer.infer(gen.iterable)
            
            elem_t = IntType()
            if isinstance(it_t, ListType):
                elem_t = it_t.element_type
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
                # File handle special case
                if isinstance(ctx_t, FileType):
                    res_t = FileType()
                self._bind_target(item.optional_vars, res_t)
        for s in node.body:
            self.check_stmt(s)
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
