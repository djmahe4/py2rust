from __future__ import annotations
from typing import Optional
from ..frontend.ast_nodes import (
    IntType,
    FloatType,
    BoolType,
    StrType,
    ListType,
)
from .symbol_table import SymbolTable


class TypeInferencer:
    def __init__(self, symbol_table: SymbolTable):
        self.st = symbol_table
        self._literal_map = {
            "IntLiteral": IntType,
            "FloatLiteral": FloatType,
            "BoolLiteral": BoolType,
            "StrLiteral": StrType,
        }

    def infer(self, expr):
        node_name = type(expr).__name__
        if node_name in self._literal_map:
            return self._literal_map[node_name]()
        match node_name:
            case "Name":
                return self.st.lookup(expr.name)
            case "BinOp":
                return self._infer_binop(expr)
            case "UnaryOp":
                return self._infer_unaryop(expr)
            case "Comparison":
                return BoolType()
            case "BoolOp":
                return BoolType()
            case "ListLiteral":
                return self._infer_list(expr)
            case "Subscript":
                return self._infer_subscript(expr)
            case "FunctionCall":
                return self._infer_call(expr)
        return None

    def _infer_binop(self, expr):
        lt = self.infer(expr.left)
        rt = self.infer(expr.right)
        if lt is None or rt is None:
            return None
        if expr.op == "/":
            return FloatType()
        if isinstance(lt, FloatType) or isinstance(rt, FloatType):
            return FloatType()
        if isinstance(lt, StrType) and isinstance(rt, StrType) and expr.op == "+":
            return StrType()
        if expr.op == "*":
            if isinstance(lt, StrType) and isinstance(rt, IntType):
                return StrType()
            if isinstance(lt, IntType) and isinstance(rt, StrType):
                return StrType()
        if expr.op == "+":
            if isinstance(lt, ListType) and isinstance(rt, ListType):
                if type(lt.element_type) is type(rt.element_type):
                    return ListType(element_type=lt.element_type)
        return IntType()

    def _infer_unaryop(self, expr):
        if expr.op == "not":
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
        if isinstance(t, StrType):
            return StrType()
        return None

    def _infer_call(self, expr):
        if expr.name == "len" and len(expr.args) == 1:
            arg_type = self.infer(expr.args[0])
            if isinstance(arg_type, (ListType, StrType)):
                return IntType()
        sig = self.st.lookup_function(expr.name)
        if sig:
            _, ret = sig
            return ret
        return None
