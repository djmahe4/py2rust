from __future__ import annotations
import ast
from typing import Optional

from ..utils.errors import ParseError, UnsupportedFeatureError
from .ast_nodes import (
    Module,
    FunctionDef,
    ClassDef,
    Param,
    VarDecl,
    Assign,
    AugAssign,
    SubscriptAssign,
    BreakStmt,
    ContinueStmt,
    DelStmt,
    IfStmt,
    WhileStmt,
    ForRange,
    ReturnStmt,
    PrintStmt,
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
    NewExpr,
    SelfExpr,
    ForIter,
    TryStmt,
    RaiseStmt,
    AwaitExpr,
    IntType,
    FloatType,
    BoolType,
    StrType,
    UnitType,
    ListType,
    DictType,
    TupleType,
    ClassType,
    EnumType,
    MatchStmt,
    MatchCase,
    ValuePattern,
    NamePattern,
    ClassPattern,
    WildcardPattern,
    OrPattern,
    AsPattern,
    EnumDef,
)

_BINOP_MAP = {
    ast.Add: "+",
    ast.Sub: "-",
    ast.Mult: "*",
    ast.Div: "/",
    ast.FloorDiv: "//",
    ast.Mod: "%",
}

_CMP_MAP = {
    ast.Eq: "==",
    ast.NotEq: "!=",
    ast.Lt: "<",
    ast.LtE: "<=",
    ast.Gt: ">",
    ast.GtE: ">=",
}

_AUGOP_MAP = {
    ast.Add: "+=",
    ast.Sub: "-=",
    ast.Mult: "*=",
    ast.Div: "/=",
    ast.FloorDiv: "//=",
    ast.Mod: "%=",
}


class Parser:
    def __init__(self, source: str, filename: str = "<unknown>"):
        self.source = source
        self.filename = filename
        self.source_lines = source.splitlines()

    def _err(self, msg: str, node, cls=ParseError, suggestion: str = None):
        line = getattr(node, "lineno", 0)
        col = getattr(node, "col_offset", 0) + 1
        return cls(
            message=msg,
            filename=self.filename,
            line=line,
            column=col,
            suggestion=suggestion,
            source_lines=self.source_lines,
        )

    def _get_attr_parts(self, attr_node):
        """Recursively extract attribute chain from AST."""
        if isinstance(attr_node, ast.Name):
            return [attr_node.id]
        elif isinstance(attr_node, ast.Attribute):
            parts = self._get_attr_parts(attr_node.value)
            if parts:
                return parts + [attr_node.attr]
        return None

    def parse(self) -> Module:
        try:
            tree = ast.parse(self.source, filename=self.filename)
        except SyntaxError as e:
            raise ParseError(
                message=str(e.msg),
                filename=self.filename,
                line=e.lineno or 0,
                column=e.offset or 0,
                source_lines=self.source_lines,
            )

        functions = []
        classes = []
        enums = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(self._parse_funcdef(node))
            elif isinstance(node, ast.ClassDef):
                res = self._parse_classdef(node)
                if isinstance(res, ClassDef):
                    classes.append(res)
                else:
                    enums.append(res)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                raise self._err(
                    "Import statements are not supported", node, UnsupportedFeatureError
                )
            else:
                raise self._err(
                    f"Top-level {type(node).__name__} is not supported",
                    node,
                    UnsupportedFeatureError,
                )

        return Module(
            functions=tuple(functions),
            classes=tuple(classes),
            enums=tuple(enums),
            filename=self.filename,
        )

    def _parse_funcdef(
        self, node: Union[ast.FunctionDef, ast.AsyncFunctionDef], is_method: bool = False
    ) -> FunctionDef:
        is_async = isinstance(node, ast.AsyncFunctionDef)
        if node.decorator_list:
            raise self._err(
                "Decorators are not supported", node, UnsupportedFeatureError
            )

        params = []
        args = list(node.args.args)
        start_idx = 0
        if is_method and args and args[0].arg == "self":
            start_idx = 1

        for arg in args[start_idx:]:
            if arg.annotation is None:
                raise self._err(
                    f"Parameter '{arg.arg}' is missing a type annotation",
                    arg,
                    UnsupportedFeatureError,
                    suggestion="Add a type hint like: def f(x: int) -> int:",
                )
            ann = self._parse_type(arg.annotation)
            params.append(
                Param(
                    name=arg.arg,
                    type_annotation=ann,
                    line=arg.lineno,
                    col=arg.col_offset + 1,
                )
            )

        if node.returns is None:
            raise self._err(
                f"Function '{node.name}' is missing a return type annotation",
                node,
                UnsupportedFeatureError,
                suggestion="Add a return type like: def f() -> int:",
            )
        return_type = self._parse_type(node.returns)

        body = self._parse_stmts(node.body)

        return FunctionDef(
            name=node.name,
            params=tuple(params),
            return_type=return_type,
            body=tuple(body),
            is_async=is_async,
            line=node.lineno,
            col=node.col_offset + 1,
        )

    def _parse_classdef(self, node: ast.ClassDef) -> Union[ClassDef, EnumDef]:
        bases = []
        is_enum = False
        for base_node in node.bases:
            if isinstance(base_node, ast.Name):
                bases.append(base_node.id)
                if base_node.id == "Enum":
                    is_enum = True

        if is_enum:
            variants = []
            for s in node.body:
                if isinstance(s, ast.Assign) and len(s.targets) == 1:
                    target = s.targets[0]
                    if isinstance(target, ast.Name):
                        val = self._parse_expr(s.value)
                        variants.append((target.id, val))
            return EnumDef(
                name=node.name,
                variants=tuple(variants),
                line=node.lineno,
                col=node.col_offset + 1,
            )

        body = self._parse_class_body(node.body)

        return ClassDef(
            name=node.name,
            bases=tuple(bases),
            body=tuple(body),
            line=node.lineno,
            col=node.col_offset + 1,
        )

    def _parse_class_body(self, stmts: list) -> list:
        result = []
        for s in stmts:
            if isinstance(s, ast.AnnAssign):
                if s.value is None:
                    raise self._err(
                        "Field declaration without value not supported",
                        s,
                        UnsupportedFeatureError,
                    )
                if not isinstance(s.target, ast.Name):
                    raise self._err(
                        "Only simple field declarations supported",
                        s,
                        UnsupportedFeatureError,
                    )
                ann = self._parse_type(s.annotation)
                val = self._parse_expr(s.value)
                result.append(
                    VarDecl(
                        name=s.target.id,
                        type_annotation=ann,
                        value=val,
                        line=s.lineno,
                        col=s.col_offset + 1,
                    )
                )
            elif isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef)):
                result.append(self._parse_funcdef(s, is_method=True))
            elif isinstance(s, ast.ClassDef):
                result.append(self._parse_classdef(s))
            elif isinstance(s, ast.Expr):
                if isinstance(s.value, ast.Call):
                    call = s.value
                    if isinstance(call.func, ast.Name) and call.func.id == "print":
                        if len(call.args) != 1 or call.keywords:
                            raise self._err(
                                "print() must have exactly one argument",
                                s,
                                UnsupportedFeatureError,
                            )
                        val = self._parse_expr(call.args[0])
                        result.append(
                            PrintStmt(value=val, line=s.lineno, col=s.col_offset + 1)
                        )
                    else:
                        raise self._err(
                            "Expression statements not allowed in class body",
                            s,
                            UnsupportedFeatureError,
                        )
                else:
                    raise self._err(
                        "Expression statements not allowed in class body",
                        s,
                        UnsupportedFeatureError,
                    )
            elif isinstance(s, ast.Pass):
                pass
            elif isinstance(s, ast.Return):
                raise self._err(
                    "Return statements not allowed in class body (except in methods)",
                    s,
                    UnsupportedFeatureError,
                )
            else:
                raise self._err(
                    f"Unsupported class body statement: {type(s).__name__}",
                    s,
                    UnsupportedFeatureError,
                )
        return result

    def _parse_type(self, node):
        if isinstance(node, ast.Name):
            match node.id:
                case "int":
                    return IntType()
                case "float":
                    return FloatType()
                case "bool":
                    return BoolType()
                case "str":
                    return StrType()
                case _:
                    return ClassType(name=node.id)
        elif isinstance(node, ast.Subscript):
            if isinstance(node.value, ast.Name) and node.value.id == "list":
                elem_type = self._parse_type(node.slice)
                return ListType(element_type=elem_type)
            if isinstance(node.value, ast.Name) and node.value.id == "dict":
                if isinstance(node.slice, ast.Tuple):
                    key_type = self._parse_type(node.slice.elts[0])
                    value_type = self._parse_type(node.slice.elts[1])
                    return DictType(key_type=key_type, value_type=value_type)
                raise self._err(
                    "dict type requires two type arguments: dict[K, V]",
                    node,
                    UnsupportedFeatureError,
                )
            if isinstance(node.value, ast.Name) and node.value.id == "tuple":
                if isinstance(node.slice, ast.Tuple):
                    types = tuple(self._parse_type(e) for e in node.slice.elts)
                    return TupleType(element_types=types)
                elif isinstance(node.slice, ast.Constant) and node.slice.value is Ellipsis:
                    raise self._err("Variadic tuples not supported", node, UnsupportedFeatureError)
                else:
                    return TupleType(element_types=(self._parse_type(node.slice),))
            raise self._err("Unsupported generic type", node, UnsupportedFeatureError)
        elif isinstance(node, ast.Constant) and node.value is None:
            return UnitType()  # Use unit type for None return types
        raise self._err(
            f"Unsupported type annotation: {ast.dump(node)}",
            node,
            UnsupportedFeatureError,
        )

    def _parse_stmts(self, stmts: list) -> list:
        return [self._parse_stmt(s) for s in stmts]

    def _parse_stmt(self, node):
        if isinstance(node, ast.Return):
            val = self._parse_expr(node.value) if node.value else None
            return ReturnStmt(value=val, line=node.lineno, col=node.col_offset + 1)

        if isinstance(node, ast.Match):
            return self._parse_match(node)

        if isinstance(node, ast.AnnAssign):
            if node.value is None:
                raise self._err(
                    "Variable declaration without value not supported",
                    node,
                    UnsupportedFeatureError,
                )
            if not isinstance(node.target, ast.Name):
                raise self._err(
                    "Only simple variable declarations supported",
                    node,
                    UnsupportedFeatureError,
                )
            ann = self._parse_type(node.annotation)
            val = self._parse_expr(node.value)
            return VarDecl(
                name=node.target.id,
                type_annotation=ann,
                value=val,
                line=node.lineno,
                col=node.col_offset + 1,
            )

        if isinstance(node, ast.Assign):
            if len(node.targets) != 1:
                raise self._err(
                    "Only single-target assignments supported",
                    node,
                    UnsupportedFeatureError,
                )
            target = node.targets[0]
            if isinstance(target, ast.Name):
                val = self._parse_expr(node.value)
                return Assign(
                    target=target.id,
                    value=val,
                    line=node.lineno,
                    col=node.col_offset + 1,
                )
            elif isinstance(target, (ast.Tuple, ast.List)):
                targets = []
                for elt in target.elts:
                    if not isinstance(elt, ast.Name):
                        raise self._err("Only simple names allowed in unpacking", elt, UnsupportedFeatureError)
                    targets.append(elt.id)
                val = self._parse_expr(node.value)
                return Assign(
                    target=tuple(targets),
                    value=val,
                    line=node.lineno,
                    col=node.col_offset + 1,
                )
            elif isinstance(target, ast.Subscript):
                target_expr = self._parse_expr(target.value)
                index_expr = self._parse_expr(target.slice)
                val = self._parse_expr(node.value)
                return SubscriptAssign(
                    target=target_expr,
                    index=index_expr,
                    value=val,
                    line=node.lineno,
                    col=node.col_offset + 1,
                )
            elif isinstance(target, ast.Attribute):
                parts = self._get_attr_parts(target)
                if parts and len(parts) == 2:
                    val = self._parse_expr(node.value)
                    return Assign(
                        target=("attr", parts[0], parts[1]),
                        value=val,
                        line=node.lineno,
                        col=node.col_offset + 1,
                    )
                raise self._err(
                    "Nested attribute assignment not supported",
                    target,
                    UnsupportedFeatureError,
                )
            else:
                raise self._err(
                    "Only simple assignments supported", node, UnsupportedFeatureError
                )

        if isinstance(node, ast.AugAssign):
            if not isinstance(node.target, ast.Name):
                raise self._err(
                    "Only simple augmented assignments supported",
                    node,
                    UnsupportedFeatureError,
                )
            op = _AUGOP_MAP.get(type(node.op))
            if op is None:
                raise self._err(
                    "Unsupported augmented assignment operator",
                    node,
                    UnsupportedFeatureError,
                )
            val = self._parse_expr(node.value)
            return AugAssign(
                target=node.target.id,
                op=op,
                value=val,
                line=node.lineno,
                col=node.col_offset + 1,
            )

        if isinstance(node, ast.ClassDef):
            return self._parse_classdef(node)

        if isinstance(node, ast.If):
            cond = self._parse_expr(node.test)
            then_body = tuple(self._parse_stmts(node.body))
            elif_clauses = []
            else_body = None
            orelse = node.orelse
            while orelse:
                if len(orelse) == 1 and isinstance(orelse[0], ast.If):
                    elif_node = orelse[0]
                    elif_clauses.append(
                        (
                            self._parse_expr(elif_node.test),
                            tuple(self._parse_stmts(elif_node.body)),
                        )
                    )
                    orelse = elif_node.orelse
                else:
                    else_body = tuple(self._parse_stmts(orelse))
                    break
            return IfStmt(
                condition=cond,
                then_body=then_body,
                elif_clauses=tuple(elif_clauses),
                else_body=else_body,
                line=node.lineno,
                col=node.col_offset + 1,
            )

        if isinstance(node, ast.While):
            cond = self._parse_expr(node.test)
            body = tuple(self._parse_stmts(node.body))
            return WhileStmt(
                condition=cond, body=body, line=node.lineno, col=node.col_offset + 1
            )

        if isinstance(node, ast.For):
            return self._parse_for(node)

        if isinstance(node, ast.Break):
            return BreakStmt(line=node.lineno, col=node.col_offset + 1)

        if isinstance(node, ast.Continue):
            return ContinueStmt(line=node.lineno, col=node.col_offset + 1)

        if isinstance(node, ast.Delete):
            if len(node.targets) != 1:
                raise self._err(
                    "Only single-target delete supported",
                    node,
                    UnsupportedFeatureError,
                )
            target = node.targets[0]
            if isinstance(target, ast.Subscript):
                return DelStmt(
                    target=self._parse_expr(target.value),
                    key=self._parse_expr(target.slice),
                    line=node.lineno,
                    col=node.col_offset + 1,
                )
            raise self._err(
                "Only subscript deletion supported (del d[key])",
                node,
                UnsupportedFeatureError,
            )

        if isinstance(node, ast.Expr):
            if isinstance(node.value, ast.Call):
                call = node.value
                if isinstance(call.func, ast.Name) and call.func.id == "print":
                    if len(call.args) != 1 or call.keywords:
                        raise self._err(
                            "print() must have exactly one argument",
                            node,
                            UnsupportedFeatureError,
                        )
                    val = self._parse_expr(call.args[0])
                    return PrintStmt(
                        value=val, line=node.lineno, col=node.col_offset + 1
                    )

                # Support general function calls as statements by treating them as assignment to discard
                # We'll re-use _parse_stmt by creating a synthetic assignment node
                fake_assign = ast.Assign(
                    targets=[
                        ast.Name(
                            id="_",
                            ctx=ast.Store(),
                            lineno=node.lineno,
                            col_offset=node.col_offset,
                        )
                    ],
                    value=node.value,
                    lineno=node.lineno,
                    col_offset=node.col_offset,
                )
                return self._parse_stmt(fake_assign)

            raise self._err(
                "Unsupported expression statement", node, UnsupportedFeatureError
            )

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            raise self._err(
                "Nested function definitions are not supported",
                node,
                UnsupportedFeatureError,
            )
        if isinstance(node, ast.ClassDef):
            raise self._err("Classes are not supported", node, UnsupportedFeatureError)
        if isinstance(node, ast.ClassDef):
            raise self._err("Classes are not supported", node, UnsupportedFeatureError)
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise self._err(
                "Import statements are not supported", node, UnsupportedFeatureError
            )
        if isinstance(node, ast.Try):
            body = tuple(self._parse_stmts(node.body))
            handlers = []
            for h in node.handlers:
                h_type = self._parse_type(h.type) if h.type else None
                h_name = h.name if h.name else None
                h_body = tuple(self._parse_stmts(h.body))
                handlers.append((h_type, h_name, h_body))
            return TryStmt(
                body=body,
                handlers=tuple(handlers),
                line=node.lineno,
                col=node.col_offset + 1,
            )

        if isinstance(node, ast.Raise):
            exc = self._parse_expr(node.exc) if node.exc else None
            return RaiseStmt(
                value=exc,
                line=node.lineno,
                col=node.col_offset + 1,
            )
        if isinstance(node, ast.With):
            raise self._err(
                "with statements are not supported", node, UnsupportedFeatureError
            )

        raise self._err(
            f"Unsupported statement: {type(node).__name__}",
            node,
            UnsupportedFeatureError,
        )

    def _parse_for(self, node: ast.For):
        if not isinstance(node.target, ast.Name):
            raise self._err(
                "For loop target must be a simple name", node, UnsupportedFeatureError
            )
        target = node.target.id

        if (
            isinstance(node.iter, ast.Call)
            and isinstance(node.iter.func, ast.Name)
            and node.iter.func.id == "range"
        ):
            args = node.iter.args
            if len(args) == 1:
                start = IntLiteral(value=0, line=node.lineno, col=node.col_offset + 1)
                stop = self._parse_expr(args[0])
                step = None
            elif len(args) == 2:
                start = self._parse_expr(args[0])
                stop = self._parse_expr(args[1])
                step = None
            elif len(args) == 3:
                start = self._parse_expr(args[0])
                stop = self._parse_expr(args[1])
                step = self._parse_expr(args[2])
            else:
                raise self._err(
                    "range() must have 1, 2 or 3 arguments", node, UnsupportedFeatureError
                )

            return ForRange(
                target=target,
                start=start,
                stop=stop,
                step=step,
                body=[self._parse_stmt(s) for s in node.body],
                line=node.lineno,
                col=node.col_offset + 1,
            )
        else:
            # General iteration (for x in lst, etc.)
            iterable = self._parse_expr(node.iter)
            return ForIter(
                target=target,
                iterable=iterable,
                body=[self._parse_stmt(s) for s in node.body],
                line=node.lineno,
                col=node.col_offset + 1,
            )

    def _parse_expr(self, node):
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool):
                return BoolLiteral(
                    value=node.value, line=node.lineno, col=node.col_offset + 1
                )
            if isinstance(node.value, int):
                return IntLiteral(
                    value=node.value, line=node.lineno, col=node.col_offset + 1
                )
            if isinstance(node.value, float):
                return FloatLiteral(
                    value=node.value, line=node.lineno, col=node.col_offset + 1
                )
            if isinstance(node.value, str):
                return StrLiteral(
                    value=node.value, line=node.lineno, col=node.col_offset + 1
                )
            raise self._err(
                f"Unsupported constant type: {type(node.value)}",
                node,
                UnsupportedFeatureError,
            )

        if isinstance(node, ast.Name):
            return Name(name=node.id, line=node.lineno, col=node.col_offset + 1)

        if isinstance(node, ast.BinOp):
            op = _BINOP_MAP.get(type(node.op))
            if op is None:
                raise self._err(
                    f"Unsupported binary operator: {type(node.op).__name__}",
                    node,
                    UnsupportedFeatureError,
                )
            left = self._parse_expr(node.left)
            right = self._parse_expr(node.right)
            return BinOp(
                op=op, left=left, right=right, line=node.lineno, col=node.col_offset + 1
            )

        if isinstance(node, ast.Tuple):
            elements = [self._parse_expr(e) for e in node.elts]
            return TupleLiteral(
                elements=elements,
                line=node.lineno,
                col=node.col_offset + 1,
            )

        if isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.Not):
                operand = self._parse_expr(node.operand)
                return UnaryOp(
                    op="not", operand=operand, line=node.lineno, col=node.col_offset + 1
                )
            if isinstance(node.op, ast.USub):
                operand = self._parse_expr(node.operand)
                return UnaryOp(
                    op="-", operand=operand, line=node.lineno, col=node.col_offset + 1
                )
            if isinstance(node.op, ast.UAdd):
                operand = self._parse_expr(node.operand)
                return UnaryOp(
                    op="+", operand=operand, line=node.lineno, col=node.col_offset + 1
                )
            raise self._err("Unsupported unary operator", node, UnsupportedFeatureError)

        if isinstance(node, ast.Compare):
            if len(node.comparators) != 1 or len(node.ops) != 1:
                raise self._err(
                    "Only simple comparisons supported (a op b)",
                    node,
                    UnsupportedFeatureError,
                )
            op_node = node.ops[0]
            op = _CMP_MAP.get(type(op_node))
            if op is None:
                # Handle 'in' and 'not in' operators for dict membership
                if isinstance(op_node, ast.In):
                    left = self._parse_expr(node.left)
                    right = self._parse_expr(node.comparators[0])
                    return Comparison(
                        op="in",
                        left=left,
                        right=right,
                        line=node.lineno,
                        col=node.col_offset + 1,
                    )
                if isinstance(op_node, ast.NotIn):
                    left = self._parse_expr(node.left)
                    right = self._parse_expr(node.comparators[0])
                    return Comparison(
                        op="not_in",
                        left=left,
                        right=right,
                        line=node.lineno,
                        col=node.col_offset + 1,
                    )
                raise self._err(
                    f"Unsupported comparison operator: {type(op_node).__name__}",
                    node,
                    UnsupportedFeatureError,
                )
            left = self._parse_expr(node.left)
            right = self._parse_expr(node.comparators[0])
            return Comparison(
                op=op, left=left, right=right, line=node.lineno, col=node.col_offset + 1
            )

        if isinstance(node, ast.BoolOp):
            op = "and" if isinstance(node.op, ast.And) else "or"
            values = tuple(self._parse_expr(v) for v in node.values)
            return BoolOp(
                op=op, values=values, line=node.lineno, col=node.col_offset + 1
            )

        if isinstance(node, ast.List):
            elems = tuple(self._parse_expr(e) for e in node.elts)
            return ListLiteral(
                elements=elems, line=node.lineno, col=node.col_offset + 1
            )

        if isinstance(node, ast.Dict):
            pairs = tuple(
                (self._parse_expr(k), self._parse_expr(v))
                for k, v in zip(node.keys, node.values)
            )
            return DictLiteral(pairs=pairs, line=node.lineno, col=node.col_offset + 1)

        if isinstance(node, ast.Subscript):
            value = self._parse_expr(node.value)
            index = self._parse_expr(node.slice)
            return Subscript(
                value=value, index=index, line=node.lineno, col=node.col_offset + 1
            )

        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                value = self._parse_expr(node.func.value)
                method = node.func.attr
                if node.keywords:
                    raise self._err(
                        "Keyword arguments are not supported",
                        node,
                        UnsupportedFeatureError,
                    )
                args = tuple(self._parse_expr(a) for a in node.args)
                return MethodCall(
                    value=value,
                    method=method,
                    args=args,
                    line=node.lineno,
                    col=node.col_offset + 1,
                )
            if isinstance(node.func, ast.Name):
                if node.func.id in ("eval", "exec", "globals", "locals"):
                    raise self._err(
                        f"'{node.func.id}' is not allowed",
                        node,
                        UnsupportedFeatureError,
                    )
                if node.keywords:
                    raise self._err(
                        "Keyword arguments are not supported",
                        node,
                        UnsupportedFeatureError,
                    )
                args = tuple(self._parse_expr(a) for a in node.args)
                return FunctionCall(
                    name=node.func.id,
                    args=args,
                    line=node.lineno,
                    col=node.col_offset + 1,
                )
            raise self._err(
                "Only simple function calls supported",
                node,
                UnsupportedFeatureError,
            )

        if isinstance(node, ast.Attribute):
            value = self._parse_expr(node.value)
            return AttributeExpr(
                value=value, attr=node.attr, line=node.lineno, col=node.col_offset + 1
            )

        if isinstance(node, ast.Name):
            if node.id == "self":
                return SelfExpr(line=node.lineno, col=node.col_offset + 1)
            return Name(name=node.id, line=node.lineno, col=node.col_offset + 1)

        if isinstance(node, ast.Lambda):
            raise self._err("Lambdas are not supported", node, UnsupportedFeatureError)
        if isinstance(
            node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
        ):
            raise self._err(
                "Comprehensions are not supported", node, UnsupportedFeatureError
            )
        if isinstance(node, ast.IfExp):
            raise self._err(
                "Ternary expressions are not supported", node, UnsupportedFeatureError
            )

        if isinstance(node, ast.Await):
            val = self._parse_expr(node.value)
            return AwaitExpr(value=val, line=node.lineno, col=node.col_offset + 1)

        raise self._err(
            f"Unsupported expression: {type(node).__name__}",
            node,
            UnsupportedFeatureError,
        )

    def _parse_match(self, node: ast.Match) -> MatchStmt:
        subject = self._parse_expr(node.subject)
        cases = []
        for c in node.cases:
            pattern = self._parse_pattern(c.pattern)
            guard = self._parse_expr(c.guard) if c.guard else None
            body = self._parse_stmts(c.body)
            cases.append(
                MatchCase(
                    pattern=pattern,
                    guard=guard,
                    body=tuple(body),
                    line=c.pattern.lineno,
                    col=c.pattern.col_offset + 1,
                )
            )
        return MatchStmt(
            subject=subject,
            cases=tuple(cases),
            line=node.lineno,
            col=node.col_offset + 1,
        )

    def _parse_pattern(self, node: ast.pattern) -> MatchPattern:
        line = getattr(node, "lineno", 0)
        col = getattr(node, "col_offset", 0) + 1

        if isinstance(node, ast.MatchValue):
            return ValuePattern(value=self._parse_expr(node.value), line=line, col=col)
        elif isinstance(node, ast.MatchAs):
            if node.pattern is None:
                if node.name is None:
                    return WildcardPattern(line=line, col=col)
                return NamePattern(name=node.name, line=line, col=col)
            return AsPattern(
                pattern=self._parse_pattern(node.pattern), name=node.name, line=line, col=col
            )
        elif isinstance(node, ast.MatchOr):
            patterns = [self._parse_pattern(p) for p in node.patterns]
            return OrPattern(patterns=tuple(patterns), line=line, col=col)
        elif isinstance(node, ast.MatchClass):
            if node.kwd_attrs:
                raise self._err(
                    "Keyword patterns in match not supported", node, UnsupportedFeatureError
                )
            patterns = [self._parse_pattern(p) for p in node.patterns]
            return ClassPattern(
                class_name=self._get_name(node.cls),
                patterns=tuple(patterns),
                line=line,
                col=col,
            )
        elif isinstance(node, ast.MatchSingleton):
            if node.value is None:
                return ValuePattern(
                    value=Name(name="None", line=line, col=col), line=line, col=col
                )
            return ValuePattern(
                value=BoolLiteral(value=node.value, line=line, col=col),
                line=line,
                col=col,
            )
        else:
            raise self._err(
                f"Unsupported match pattern: {type(node).__name__}",
                node,
                UnsupportedFeatureError,
            )

    def _get_name(self, node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return node.attr
        return "Unknown"


def parse(source: str, filename: str = "<unknown>") -> Module:
    return Parser(source, filename).parse()
