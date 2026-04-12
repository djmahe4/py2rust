from __future__ import annotations
from typing import Optional
from ..frontend.ast_nodes import (
    IntType,
    FloatType,
    BoolType,
    StrType,
    ListType,
)
from ..utils.errors import Py2RustTypeError, SemanticError
from .symbol_table import SymbolTable
from .type_inferencer import TypeInferencer


def _types_compatible(a, b) -> bool:
    if type(a) is type(b):
        if isinstance(a, ListType) and isinstance(b, ListType):
            # Rust Vec<T> is invariant — element types must match exactly
            return type(a.element_type) is type(b.element_type)
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

    def check_module(self, module) -> None:
        for func in module.functions:
            param_types = [p.type_annotation for p in func.params]
            self.st.define_function(func.name, param_types, func.return_type)

        for func in module.functions:
            self.check_function(func)

    def check_function(self, func) -> None:
        self.st.enter_scope(func.name)
        self._current_return_type = func.return_type

        for param in func.params:
            self.st.define(param.name, param.type_annotation)

        for stmt in func.body:
            self.check_stmt(stmt)

        self.st.exit_scope()
        self._current_return_type = None

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
            Subscript,
            FunctionCall,
        )

        if isinstance(expr, Name):
            if self.st.lookup(expr.name) is None:
                raise self._err(
                    f"Undefined variable: '{expr.name}'",
                    expr.line,
                    expr.col,
                    cls=SemanticError,
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
        elif isinstance(expr, Subscript):
            self.check_expr(expr.value)
            self.check_expr(expr.index)
            it = self.inferencer.infer(expr.index)
            if not isinstance(it, IntType):
                raise self._err(
                    f"Subscript index must be int, got {it}", expr.line, expr.col
                )
        elif isinstance(expr, FunctionCall):
            sig = self.st.lookup_function(expr.name)
            if sig is None:
                raise self._err(
                    f"Undefined function: '{expr.name}'",
                    expr.line,
                    expr.col,
                    cls=SemanticError,
                )
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
            ForRangeStmt,
            ReturnStmt,
            PrintStmt,
            FunctionCall,
            Name,
        )

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
            if cond_type is None:
                raise self._err(
                    "Cannot infer type for 'if' condition", stmt.line, stmt.col
                )
            if not isinstance(cond_type, BoolType):
                raise self._err(
                    f"'if' condition must be bool, got {cond_type}", stmt.line, stmt.col
                )

            for s in stmt.then_body:
                self.check_stmt(s)
            for cond, body in stmt.elif_clauses:
                self.check_expr(cond)
                elif_cond_type = self.inferencer.infer(cond)
                if not isinstance(elif_cond_type, BoolType):
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

        elif isinstance(stmt, WhileStmt):
            self.check_expr(stmt.condition)
            cond_type = self.inferencer.infer(stmt.condition)
            if cond_type is None:
                raise self._err(
                    "Cannot infer type for 'while' condition", stmt.line, stmt.col
                )
            if not isinstance(cond_type, BoolType):
                raise self._err(
                    f"'while' condition must be bool, got {cond_type}",
                    stmt.line,
                    stmt.col,
                )

            for s in stmt.body:
                self.check_stmt(s)

        elif isinstance(stmt, ForRangeStmt):
            # Check that start, stop, and step are integers
            self.check_expr(stmt.start)
            start_type = self.inferencer.infer(stmt.start)
            if start_type is not None and not isinstance(start_type, IntType):
                raise self._err(
                    f"range() start must be int, got {start_type}", stmt.line, stmt.col
                )

            self.check_expr(stmt.stop)
            stop_type = self.inferencer.infer(stmt.stop)
            if stop_type is not None and not isinstance(stop_type, IntType):
                raise self._err(
                    f"range() stop must be int, got {stop_type}", stmt.line, stmt.col
                )

            if stmt.step is not None:
                self.check_expr(stmt.step)
                step_type = self.inferencer.infer(stmt.step)
                if step_type is not None and not isinstance(step_type, IntType):
                    raise self._err(
                        f"range() step must be int, got {step_type}",
                        stmt.line,
                        stmt.col,
                    )

            # Ensure loop target is consistent with IntType
            existing = self.st.lookup(stmt.target)
            if existing is not None and not isinstance(existing, IntType):
                raise self._err(
                    f"Cannot use '{stmt.target}' as loop target: already defined as {existing}",
                    stmt.line,
                    stmt.col,
                )

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
