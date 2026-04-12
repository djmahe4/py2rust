from __future__ import annotations
from typing import Optional
from ..frontend.ast_nodes import (
    IntType, FloatType, BoolType, StrType, ListType,
)
from .symbol_table import SymbolTable


class TypeInferencer:
    def __init__(self, symbol_table: SymbolTable):
        self.st = symbol_table

    def infer(self, expr):
        name = type(expr).__name__
        if name == 'IntLiteral': return IntType()
        if name == 'FloatLiteral': return FloatType()
        if name == 'BoolLiteral': return BoolType()
        if name == 'StrLiteral': return StrType()
        if name == 'Name': return self.st.lookup(expr.name)
        if name == 'BinOp': return self._infer_binop(expr)
        if name == 'UnaryOp': return self._infer_unaryop(expr)
        if name == 'Comparison': return BoolType()
        if name == 'BoolOp': return BoolType()
        if name == 'ListLiteral': return self._infer_list(expr)
        if name == 'Subscript': return self._infer_subscript(expr)
        if name == 'FunctionCall': return self._infer_call(expr)
        return None

    def _infer_binop(self, expr):
        lt = self.infer(expr.left)
        rt = self.infer(expr.right)
        if lt is None or rt is None:
            return None
        if expr.op == '/':
            return FloatType()
        if isinstance(lt, FloatType) or isinstance(rt, FloatType):
            return FloatType()
        return IntType()

    def _infer_unaryop(self, expr):
        if expr.op == 'not':
            return BoolType()
        return self.infer(expr.operand)

    def _infer_list(self, expr):
        if not expr.elements:
            return None
        elem_t = self.infer(expr.elements[0])
        if elem_t is None:
            return None
        return ListType(element_type=elem_t)

    def _infer_subscript(self, expr):
        t = self.infer(expr.value)
        if isinstance(t, ListType):
            return t.element_type
        return None

    def _infer_call(self, expr):
        sig = self.st.lookup_function(expr.name)
        if sig:
            _, ret = sig
            return ret
        return None
