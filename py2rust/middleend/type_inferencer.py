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
    SetType,
    FunctionType,
    UnknownType,
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
            case "LambdaExpr":
                return self._infer_lambda(expr)
            case "ListComp":
                return self._infer_list_comp(expr)
            case "DictComp":
                return self._infer_dict_comp(expr)
            case "SetComp":
                return self._infer_set_comp(expr)
            case "JoinedStr":
                return StrType()
            case "FormattedValue":
                return StrType()
        return None

    def _infer_lambda(self, expr):
        # Infer return type from body.
        # Use UnknownType for params as they are not explicitly typed.
        param_types = tuple(UnknownType() for _ in expr.params)
        return_t = self.infer(expr.body)
        return FunctionType(param_types=param_types, return_type=return_t or UnknownType())

    def _infer_list_comp(self, expr):
        elt_t = self.infer(expr.elt)
        return ListType(element_type=elt_t) if elt_t else None

    def _infer_dict_comp(self, expr):
        key_t = self.infer(expr.key)
        val_t = self.infer(expr.value)
        return DictType(key_type=key_t, value_type=val_t) if (key_t and val_t) else None

    def _infer_set_comp(self, expr):
        elt_t = self.infer(expr.elt)
        return SetType(element_type=elt_t) if elt_t else None

    def _infer_binop(self, expr):
        lt = self.infer(expr.left)
        rt = self.infer(expr.right)
        if lt is None or rt is None:
            return None
        if isinstance(lt, UnknownType) or isinstance(rt, UnknownType):
            return UnknownType()
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
        
        element_types = [self.infer(e) for e in expr.elements]
        if not element_types or any(t is None for t in element_types):
            return None
        
        first_t = element_types[0]
        if all(type(t) is type(first_t) and getattr(t, "name", None) == getattr(first_t, "name", None) for t in element_types):
            return ListType(element_type=first_t)

        # Heterogeneous: find common protocols
        common = self._find_common_protocols(element_types)
        if common:
            # Pick first for now
            return ListType(element_type=ClassType(name=common[0]))

        return ListType(element_type=first_t)

    def _find_common_protocols(self, types):
        candidates = []
        for trait_name, trait_info in self.st._traits.items():
            if all(self._satisfies_protocol(t, trait_info) for t in types):
                candidates.append(trait_name)
        return candidates

    def _satisfies_protocol(self, t, trait_info):
        if not isinstance(t, ClassType):
            return False
        
        for m_name, arities in trait_info.methods.items():
            for arity, _ in arities.items():
                if not self.st.lookup_method(t.name, m_name, arity):
                    return False
        return True

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
            if isinstance(arg_type, (ListType, StrType, DictType, SetType)):
                return IntType()
        if expr.name == "open":
            return FileType()
        if expr.name == "zip":
            # zip(a, b) -> list[tuple[type_a, type_b]]
            types = []
            for arg in expr.args:
                it_t = self.infer(arg)
                if isinstance(it_t, ListType):
                    types.append(it_t.element_type)
                elif isinstance(it_t, StrType):
                    types.append(StrType())
                else:
                    types.append(UnknownType())
            return ListType(element_type=TupleType(element_types=tuple(types)))
        if expr.name == "str":
            return StrType()
        if expr.name == "int":
            return IntType()
        if expr.name == "float":
            return FloatType()
        if expr.name == "bool":
            return BoolType()
        if expr.name == "enumerate":
            # enumerate(a) -> list[tuple[int, type_a]]
            it_t = self.infer(expr.args[0])
            elem_t = UnknownType()
            if isinstance(it_t, ListType):
                elem_t = it_t.element_type
            elif isinstance(it_t, StrType):
                elem_t = StrType()
            return ListType(element_type=TupleType(element_types=(IntType(), elem_t)))
        if expr.name == "map":
            # map(f, a) -> list[return_type_f]
            # Simple heuristic for now
            return ListType(element_type=UnknownType())
        if expr.name == "reversed":
            return self.infer(expr.args[0])
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
