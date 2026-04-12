from __future__ import annotations
from typing import Optional
from ..frontend.ast_nodes import (
    IntType, FloatType, BoolType, StrType, ListType,
)
from ..utils.errors import Py2RustTypeError, SemanticError
from .symbol_table import SymbolTable
from .type_inferencer import TypeInferencer


def _types_compatible(a, b) -> bool:
    if type(a) is type(b):
        if isinstance(a, ListType) and isinstance(b, ListType):
            return _types_compatible(a.element_type, b.element_type)
        return True
    if isinstance(a, FloatType) and isinstance(b, IntType):
        return True
    return False


class TypeChecker:
    def __init__(self, symbol_table: SymbolTable, filename: str = "<unknown>", source_lines: list = None):
        self.st = symbol_table
        self.inferencer = TypeInferencer(symbol_table)
        self.filename = filename
        self.source_lines = source_lines or []
        self._current_return_type = None

    def _err(self, msg: str, line: int = 0, col: int = 0, suggestion: str = None) -> Py2RustTypeError:
        return Py2RustTypeError(
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

    def check_stmt(self, stmt) -> None:
        from ..frontend.ast_nodes import (
            VarDecl, Assign, AugAssign, IfStmt, WhileStmt, ForRangeStmt, ReturnStmt, PrintStmt,
            FunctionCall, Name
        )
        if isinstance(stmt, VarDecl):
            inferred = self.inferencer.infer(stmt.value)
            ann = stmt.type_annotation
            if ann is not None and inferred is not None:
                if not _types_compatible(ann, inferred):
                    raise self._err(
                        f"Type mismatch: variable '{stmt.name}' declared as {ann} but value is {inferred}",
                        stmt.line, stmt.col
                    )
            actual_type = ann if ann is not None else inferred
            if actual_type is None:
                raise self._err(f"Cannot infer type for '{stmt.name}'", stmt.line, stmt.col)
            self.st.define(stmt.name, actual_type)

        elif isinstance(stmt, Assign):
            existing = self.st.lookup(stmt.target)
            inferred = self.inferencer.infer(stmt.value)
            if existing is None:
                if inferred is None:
                    raise self._err(f"Cannot infer type for '{stmt.target}'", stmt.line, stmt.col)
                self.st.define(stmt.target, inferred)
            else:
                if inferred is not None and not _types_compatible(existing, inferred):
                    raise self._err(
                        f"Type mismatch: cannot assign {inferred} to '{stmt.target}' (type {existing})",
                        stmt.line, stmt.col
                    )

        elif isinstance(stmt, AugAssign):
            existing = self.st.lookup(stmt.target)
            if existing is None:
                raise self._sem_err(f"Undefined variable '{stmt.target}'", stmt.line, stmt.col)
            inferred = self.inferencer.infer(stmt.value)
            if inferred is not None and not _types_compatible(existing, inferred):
                raise self._err(
                    f"Type mismatch in augmented assignment: cannot apply operation to {existing} and {inferred}",
                    stmt.line, stmt.col
                )

        elif isinstance(stmt, IfStmt):
            cond_type = self.inferencer.infer(stmt.condition)
            if cond_type is None:
                raise self._err("Cannot infer type for 'if' condition", stmt.line, stmt.col)
            if not isinstance(cond_type, BoolType):
                raise self._err(f"'if' condition must be bool, got {cond_type}", stmt.line, stmt.col)
            
            for s in stmt.then_body:
                self.check_stmt(s)
            for (cond, body) in stmt.elif_clauses:
                elif_cond_type = self.inferencer.infer(cond)
                if not isinstance(elif_cond_type, BoolType):
                    raise self._err(f"'elif' condition must be bool, got {elif_cond_type}", stmt.line, stmt.col)
                for s in body:
                    self.check_stmt(s)
            if stmt.else_body:
                for s in stmt.else_body:
                    self.check_stmt(s)

        elif isinstance(stmt, WhileStmt):
            cond_type = self.inferencer.infer(stmt.condition)
            if cond_type is None:
                raise self._err("Cannot infer type for 'while' condition", stmt.line, stmt.col)
            if not isinstance(cond_type, BoolType):
                raise self._err(f"'while' condition must be bool, got {cond_type}", stmt.line, stmt.col)
            
            for s in stmt.body:
                self.check_stmt(s)

        elif isinstance(stmt, ForRangeStmt):
            # Check that start, stop, and step are integers
            start_type = self.inferencer.infer(stmt.start)
            if start_type is not None and not isinstance(start_type, IntType):
                raise self._err(f"range() start must be int, got {start_type}", stmt.line, stmt.col)
            
            stop_type = self.inferencer.infer(stmt.stop)
            if stop_type is not None and not isinstance(stop_type, IntType):
                raise self._err(f"range() stop must be int, got {stop_type}", stmt.line, stmt.col)
            
            if stmt.step is not None:
                step_type = self.inferencer.infer(stmt.step)
                if step_type is not None and not isinstance(step_type, IntType):
                    raise self._err(f"range() step must be int, got {step_type}", stmt.line, stmt.col)

            self.st.define(stmt.target, IntType())
            for s in stmt.body:
                self.check_stmt(s)

        elif isinstance(stmt, ReturnStmt):
            if stmt.value is not None:
                ret_type = self.inferencer.infer(stmt.value)
                if ret_type is not None and self._current_return_type is not None:
                    if not _types_compatible(self._current_return_type, ret_type):
                        raise self._err(
                            f"Return type mismatch: expected {self._current_return_type}, got {ret_type}",
                            stmt.line, stmt.col
                        )

        elif isinstance(stmt, PrintStmt):
            pass
