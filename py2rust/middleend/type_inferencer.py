from __future__ import annotations
from typing import Optional
from ..frontend.ast_nodes import (
    IntType,
    FloatType,
    BoolType,
    StrType,
    ListType,
    DictType,
    FileType,
    ClassType,
    TupleType,
    EnumType,
    Name,
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
            case "TupleLiteral":
                return TupleType(
                    element_types=tuple(self.infer(e) for e in expr.elements)
                )
            case "DictLiteral":
                return self._infer_dict(expr)
            case "Subscript":
                return self._infer_subscript(expr)
            case "FunctionCall":
                return self._infer_call(expr)
            case "AttributeExpr":
                return self._infer_attribute(expr)
            case "MethodCall":
                return self._infer_method_call(expr)
            case "SelfExpr":
                return self._infer_self(expr)
            case "AwaitExpr":
                return self.infer(expr.value)
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

    def _infer_dict(self, expr):
        if not expr.pairs:
            return None
        key_t = self.infer(expr.pairs[0][0])
        val_t = self.infer(expr.pairs[0][1])
        if key_t is None or val_t is None:
            return None
        return DictType(key_type=key_t, value_type=val_t)

    def _infer_subscript(self, expr):
        t = self.infer(expr.value)
        if isinstance(t, ListType):
            return t.element_type
        if isinstance(t, StrType):
            return StrType()
        if isinstance(t, DictType):
            return t.value_type
        return None

    def _infer_call(self, expr):
        if expr.name == "len" and len(expr.args) == 1:
            arg_type = self.infer(expr.args[0])
            if isinstance(arg_type, (ListType, StrType, DictType)):
                return IntType()
        if expr.name == "open":
            return FileType()
        # Check scope first (for nested/mangled classes)
        curr_type = self.st.lookup(expr.name)
        if isinstance(curr_type, ClassType):
            return curr_type

        sig = self.st.lookup_function(expr.name)
        if sig:
            # sig: (params, return_type, is_async)
            return sig[1]

        cls = self.st.lookup_class(expr.name)
        if cls:
            return ClassType(name=expr.name)
        return None

    def _infer_attribute(self, expr):
        # Handle Enum member access (e.g., Color.RED)
        if isinstance(expr.value, Name):
            enum_info = self.st.lookup_enum(expr.value.name)
            if enum_info and expr.attr in enum_info.variants:
                return EnumType(name=expr.value.name)

        val_type = self.infer(expr.value)
        if isinstance(val_type, ClassType):
            field_type = self.st.get_field_type(val_type.name, expr.attr)
            if field_type:
                return field_type
        return None

    def _infer_method_call(self, expr):
        val_type = self.infer(expr.value)
        if isinstance(val_type, ClassType):
            arity = len(expr.args)
            method_info = self.st.lookup_method(val_type.name, expr.method, arity)
            if method_info:
                method, _ = method_info
                return method.return_type
        if isinstance(val_type, FileType):
            return self.infer_file_method(expr.method)
        return None

    def _infer_self(self, expr):
        current_class = self.st.get_current_class()
        if current_class:
            return ClassType(name=current_class)
        return None

    def infer_dict_contains(self, key_expr, dict_expr):
        """Infer type for dict membership check. Returns BoolType."""
        return BoolType()

    def infer_file_method(self, method_name):
        """Infer return type for file handle methods."""
        if method_name in ("read", "readline"):
            return StrType()
        if method_name in ("tell", "seek"):
            return IntType()
        if method_name == "close":
            return None
        return None

    def infer_open_call(self, args):
        """Infer type for open() call. Returns FileType."""
        return FileType()
