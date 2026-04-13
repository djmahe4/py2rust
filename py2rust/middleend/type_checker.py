from __future__ import annotations
from typing import Optional
from ..frontend.ast_nodes import (
    IntType,
    FloatType,
    BoolType,
    StrType,
    ListType,
    DictType,
    ClassType,
    TupleType,
    ClassDef,
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
)
from ..utils.errors import Py2RustTypeError, SemanticError
from .symbol_table import SymbolTable
from .type_inferencer import TypeInferencer


def _types_compatible(a, b) -> bool:
    if type(a) is type(b):
        if isinstance(a, ListType) and isinstance(b, ListType):
            # Rust Vec<T> is invariant — element types must match exactly
            return type(a.element_type) is type(b.element_type)
        if isinstance(a, DictType) and isinstance(b, DictType):
            # HashMap<K, V> requires exact key/value type match
            return type(a.key_type) is type(b.key_type) and type(a.value_type) is type(
                b.value_type
            )
        return True
    if isinstance(a, FloatType) and isinstance(b, IntType):
        return True
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

    def check_module(self, module: Module) -> None:
        # Pre-scan all classes (including nested ones)
        self._collect_all_classes(module.classes)
        self._collect_all_classes(module.functions)
        
        # Register top-level classes in global scope
        from ..frontend.ast_nodes import ClassType
        for cls in module.classes:
            self.st.define(cls.name, ClassType(name=cls.name))

        for cls in module.classes:
            self.check_class(cls)

        for func in module.functions:
            param_types = [p.type_annotation for p in func.params]
            self.st.define_function(func.name, param_types, func.return_type)

        for func in module.functions:
            self.check_function(func)

    def _collect_all_classes(self, items, prefix="") -> None:
        from ..frontend.ast_nodes import ClassDef, FunctionDef
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
                            else:
                                if sub_item.name not in methods:
                                    methods[sub_item.name] = {}
                                methods[sub_item.name][arity] = sub_item
                
                # Register class with mangled name
                self.st.define_class(full_name, item.bases, fields, methods, constructors)
                
                # Recurse into class body for nested classes
                self._collect_all_classes(item.body, prefix=f"{full_name}_")
            
            elif isinstance(item, FunctionDef):
                # Recurse into function body for nested classes
                # Note: Functional nesting prefix could be more complex, but let's use '_' for simplicity
                self._collect_all_classes(item.body, prefix=f"{prefix}{item.name}_")

    def check_class(self, cls: ClassDef, prefix="") -> None:
        full_name = f"{prefix}{cls.name}"
        prev_class = self.st.get_current_class()
        self.st.set_current_class(full_name)
        
        # Define nested items in this class scope
        from ..frontend.ast_nodes import ClassType
        for item in cls.body:
            if hasattr(item, "__class__"):
                item_name = type(item).__name__
                if item_name == "ClassDef":
                    # Register nested class in THIS scope
                    self.st.define(item.name, ClassType(name=f"{full_name}_{item.name}"))
        
        for item in cls.body:
            if hasattr(item, "__class__"):
                item_name = type(item).__name__
                if item_name == "FunctionDef":
                    self.check_method(full_name, item)
                elif item_name == "ClassDef":
                    self.check_class(item, prefix=f"{full_name}_")
        self.st.set_current_class(prev_class)

    def check_method(self, class_name: str, func) -> None:
        self.st.enter_scope(f"{class_name}.{func.name}")
        old_ret = self._current_return_type
        self._current_return_type = func.return_type
        self.st.define("self", ClassType(name=class_name))

        for param in func.params:
            self.st.define(param.name, param.type_annotation)

        for stmt in func.body:
            self.check_stmt(stmt)

        self.st.exit_scope()
        self._current_return_type = old_ret

    def check_function(self, func) -> None:
        self.st.enter_scope(func.name)
        old_ret = self._current_return_type
        self._current_return_type = func.return_type

        # Define local classes in this function scope
        from ..frontend.ast_nodes import ClassType, ClassDef
        for item in func.body:
            if isinstance(item, ClassDef):
                self.st.define(item.name, ClassType(name=f"{self.st.current_scope.name}_{item.name}"))

        for param in func.params:
            self.st.define(param.name, param.type_annotation)

        for stmt in func.body:
            self.check_stmt(stmt)

        self.st.exit_scope()
        self._current_return_type = old_ret

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
            Subscript,
            FunctionCall,
            AttributeExpr,
            MethodCall,
            SelfExpr,
            NewExpr,
        )

        if isinstance(expr, Name):
            if self.st.lookup(expr.name) is None:
                raise self._err(
                    f"Undefined variable: '{expr.name}'",
                    expr.line,
                    expr.col,
                    cls=SemanticError,
                )
        elif isinstance(expr, AttributeExpr):
            self.check_expr(expr.value)
        elif isinstance(expr, MethodCall):
            self.check_expr(expr.value)
            for arg in expr.args:
                self.check_expr(arg)
            val_type = self.inferencer.infer(expr.value)
            if isinstance(val_type, ClassType):
                arity = len(expr.args)
                method = self.st.lookup_method(val_type.name, expr.method, arity)
                if method is None:
                    raise self._err(
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
            if isinstance(lt, StrType) and isinstance(rt, StrType) and expr.op == "+":
                pass  # Valid string concatenation
            # Check for string repetition (str * int or int * str)
            elif expr.op == "*" and (
                (isinstance(lt, StrType) and isinstance(rt, IntType))
                or (isinstance(lt, IntType) and isinstance(rt, StrType))
            ):
                pass  # Valid string repetition
            # Check for list concatenation
            elif (
                expr.op == "+" and isinstance(lt, ListType) and isinstance(rt, ListType)
            ):
                if type(lt.element_type) is type(rt.element_type):
                    pass  # Valid list concatenation
                else:
                    raise self._err(
                        f"Invalid operand types for '{expr.op}': list[{lt.element_type}] and list[{rt.element_type}]",
                        expr.line,
                        expr.col,
                    )
            elif not (
                isinstance(lt, (IntType, FloatType))
                and isinstance(rt, (IntType, FloatType))
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
                # Optional: could enforce bool, but Python is loose.
                # Let's just ensure it's inferrable.
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
            # For dicts, index can be any hashable type (int, str, float, bool)
            # For lists/strings, index must be int
            if isinstance(vt, ListType) or isinstance(vt, StrType):
                it = self.inferencer.infer(expr.index)
                if not isinstance(it, IntType):
                    raise self._err(
                        f"Subscript index must be int, got {it}", expr.line, expr.col
                    )
            # For dicts, any key type is allowed (type checking happens at runtime)
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
                if not isinstance(arg_t, (ListType, StrType, DictType)):
                    raise self._err(
                        f"len() argument must be list, str, or dict, got {arg_t}",
                        expr.line,
                        expr.col,
                    )
            else:
                sig = self.st.lookup_function(expr.name)
                if sig is None:
                    # Check if it's a class (could be mangled or local)
                    curr_type = self.st.lookup(expr.name)
                    if isinstance(curr_type, ClassType):
                        cls_info = self.st.lookup_class(curr_type.name)
                        if cls_info:
                            # It's a constructor call
                            pass
                        else:
                            raise self._err(f"Unknown class: '{curr_type.name}'", expr.line, expr.col)
                    elif self.st.lookup_class(expr.name):
                        pass  # It's a top-level or absolute class name
                    else:
                        raise self._err(
                            f"Undefined function: '{expr.name}'",
                            expr.line,
                            expr.col,
                            cls=SemanticError,
                        )
                else:
                    params, _ = sig
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
            # Nested class in function/loop
            # Prefix with current scope name to avoid collisions
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
                 # Attribute assignment
                 return

            if isinstance(stmt.target, tuple):
                # Tuple unpacking
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
            
            self.st.define(stmt.target, elem_t)
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
            
            # Validation
            for arg_name, arg in [("start", stmt.start), ("stop", stmt.stop), ("step", stmt.step)]:
                if arg is not None:
                    arg_t = self.inferencer.infer(arg)
                    if arg_t is not None and not isinstance(arg_t, IntType):
                        raise self._err(f"range() {arg_name} must be int, got {arg_t}", stmt.line, stmt.col)

            existing = self.st.lookup(stmt.target)
            if existing is not None and not isinstance(existing, IntType):
                 raise self._err(f"Cannot use '{stmt.target}' as loop target: already defined as {existing}", stmt.line, stmt.col)

            self.st.define(stmt.target, IntType())
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
            self.check_expr(stmt.value)
            inferred = self.inferencer.infer(stmt.value)
            if inferred is None:
                raise self._err(
                    "Cannot infer type for expression in print()", stmt.line, stmt.col
                )
