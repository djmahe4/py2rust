from __future__ import annotations
from ..frontend.ast_nodes import (
    IntType,
    FloatType,
    BoolType,
    StrType,
    UnitType,
    ListType,
    DictType,
    FileType,
    ClassType,
    ClassDef,
    AttributeExpr,
    MethodCall,
    SelfExpr,
    NewExpr,
)
from ..ir.ir_nodes import (
    IRModule,
    IRFunction,
    IRParam,
    IRIntType,
    IRFloatType,
    IRBoolType,
    IRStrType,
    IRUnitType,
    IRListType,
    IRDictType,
    IRFileType,
    IRClassType,
    IRIntLit,
    IRFloatLit,
    IRBoolLit,
    IRStrLit,
    IRName,
    IRBinOp,
    IRUnaryOpExpr,
    IRCompare,
    IRBoolOp,
    IRListLit,
    IRDictLit,
    IRDictContains,
    IRSubscript,
    IRSubscriptAssign,
    IRFunctionCall,
    IRFileOpen,
    IRFileMethod,
    IRVarDecl,
    IRAssign,
    IRFieldAssign,
    IRAugAssign,
    IRIf,
    IRWhile,
    IRForRange,
    IRReturn,
    IRPrint,
    IRBreak,
    IRContinue,
    IRDictDelete,
    IRStructLit,
    IRStructAccess,
    IRMethodCall,
    IRNew,
    IRSelf,
    IRClassDefinition,
)
from ..utils.errors import SemanticError
from .symbol_table import SymbolTable
from .type_inferencer import TypeInferencer
from .type_checker import TypeChecker


def _to_ir_type(t):
    if isinstance(t, IntType):
        return IRIntType()
    if isinstance(t, FloatType):
        return IRFloatType()
    if isinstance(t, BoolType):
        return IRBoolType()
    if isinstance(t, StrType):
        return IRStrType()
    if isinstance(t, UnitType):
        return IRUnitType()
    if isinstance(t, ListType):
        return IRListType(element_type=_to_ir_type(t.element_type))
    if isinstance(t, DictType):
        return IRDictType(
            key_type=_to_ir_type(t.key_type),
            value_type=_to_ir_type(t.value_type),
        )
    if isinstance(t, FileType):
        return IRFileType()
    if isinstance(t, ClassType):
        return IRClassType(name=t.name, base=t.base)
    raise SemanticError(f"Unknown type: {t}")


class IRBuilder:
    def __init__(self, filename: str = "<unknown>", source_lines: list = None):
        self.filename = filename
        self.source_lines = source_lines or []
        self.st = SymbolTable()
        self.inferencer = TypeInferencer(self.st)
        self._loop_stack: list = []

    def _err(self, msg: str, line: int = 0, col: int = 0) -> SemanticError:
        return SemanticError(
            message=msg,
            filename=self.filename,
            line=line,
            column=col,
            source_lines=self.source_lines,
        )

    def build(self, module) -> IRModule:
        checker = TypeChecker(self.st, self.filename, self.source_lines)
        checker.check_module(module)

        ir_classes = []
        for cls in module.classes:
            ir_classes.append(self._build_class(cls))

        ir_funcs = []
        for func in module.functions:
            ir_funcs.append(self._build_function(func))
        return IRModule(
            functions=tuple(ir_funcs),
            classes=tuple(ir_classes),
            filename=module.filename,
        )

    def _build_class(self, cls: ClassDef) -> IRClassDefinition:
        fields = []
        methods = []
        constructors = []
        for item in cls.body:
            if hasattr(item, "__class__"):
                item_name = type(item).__name__
                if item_name == "VarDecl":
                    ir_type = _to_ir_type(item.type_annotation)
                    fields.append((item.name, ir_type))
                elif item_name == "FunctionDef":
                    ir_func = self._build_method(cls.name, item)
                    if item.name == "__init__":
                        constructors.append(ir_func)
                    else:
                        methods.append(ir_func)
        return IRClassDefinition(
            name=cls.name,
            base=cls.base,
            fields=tuple(fields),
            methods=tuple(methods),
            constructors=tuple(constructors),
        )

    def _build_method(self, class_name: str, func) -> IRFunction:
        self.st.enter_scope(f"{class_name}.{func.name}")
        self.st.define("self", ClassType(name=class_name))

        params = []
        for p in func.params:
            ir_t = _to_ir_type(p.type_annotation)
            self.st.define(p.name, p.type_annotation)
            params.append(IRParam(name=p.name, type_=ir_t))

        ret_type = _to_ir_type(func.return_type)
        body = self._build_stmts(func.body, ret_type)

        mutated_params = tuple(
            n for n in [p.name for p in func.params] if self._is_param_mutated(body, n)
        )

        self.st.exit_scope()
        return IRFunction(
            name=func.name,
            params=tuple(params),
            return_type=ret_type,
            body=tuple(body),
            mutated_params=mutated_params,
            is_method=True,
        )

    def _build_function(self, func) -> IRFunction:
        self.st.enter_scope(func.name)

        params = []
        param_names = []
        for p in func.params:
            ir_t = _to_ir_type(p.type_annotation)
            self.st.define(p.name, p.type_annotation)
            params.append(IRParam(name=p.name, type_=ir_t))
            param_names.append(p.name)

        ret_type = _to_ir_type(func.return_type)
        body = self._build_stmts(func.body, ret_type)

        mutated_params = tuple(
            n for n in param_names if self._is_param_mutated(body, n)
        )

        self.st.exit_scope()
        return IRFunction(
            name=func.name,
            params=tuple(params),
            return_type=ret_type,
            body=tuple(body),
            mutated_params=mutated_params,
        )

    def _is_param_mutated(self, stmts, param_name) -> bool:
        """Check if a parameter is mutated anywhere in the function body."""
        for stmt in stmts:
            if self._stmt_mutates(stmt, param_name):
                return True
        return False

    def _stmt_mutates(self, stmt, name) -> bool:
        """Check if a statement mutates a variable."""
        if isinstance(stmt, IRAssign) and stmt.target == name:
            return True
        if isinstance(stmt, IRAugAssign) and stmt.target == name:
            return True
        if isinstance(stmt, IRSubscriptAssign):
            # If target is indexing 'name', then 'name' is mutated
            if isinstance(stmt.target, IRSubscript) and isinstance(stmt.target.value, IRName):
                if stmt.target.value.name == name:
                    return True
            elif isinstance(stmt.target, IRName) and stmt.target.name == name:
                return True

        if isinstance(stmt, IRIf):
            return (
                self._any_stmt_mutates(stmt.then_body, name)
                or any(self._any_stmt_mutates(b, name) for _, b in stmt.elif_clauses)
                or (stmt.else_body and self._any_stmt_mutates(stmt.else_body, name))
            )
        if isinstance(stmt, IRWhile):
            return self._any_stmt_mutates(stmt.body, name)
        if isinstance(stmt, IRForRange):
            if stmt.target == name:
                return True
            return self._any_stmt_mutates(stmt.body, name)
        return False

    def _any_stmt_mutates(self, stmts, name) -> bool:
        """Check if any statement in a list mutates a variable."""
        return any(self._stmt_mutates(s, name) for s in stmts)

    def _build_stmts(self, stmts, return_type=None) -> list:
        return [self._build_stmt(s, return_type) for s in stmts]

    def _build_stmt(self, stmt, return_type=None):
        name = type(stmt).__name__

        if name == "VarDecl":
            inferred = self.inferencer.infer(stmt.value)
            ann = stmt.type_annotation
            actual_type = ann if ann is not None else inferred
            if actual_type is None:
                raise self._err(
                    f"Cannot determine type for '{stmt.name}'", stmt.line, stmt.col
                )
            ir_type = _to_ir_type(actual_type)
            self.st.define(stmt.name, actual_type)
            ir_val = self._build_expr(stmt.value, expected_type=ir_type)
            return IRVarDecl(name=stmt.name, type_=ir_type, value=ir_val)

        elif name == "Assign":
            if isinstance(stmt.target, tuple) and stmt.target[0] == "attr":
                _, obj_name, field_name = stmt.target
                val = self._build_expr(stmt.value)
                return IRFieldAssign(obj=obj_name, field=field_name, value=val)
            if stmt.target == "_":
                ir_val = self._build_expr(stmt.value)
                return IRVarDecl(name="_", type_=IRIntType(), value=ir_val)
            existing = self.st.lookup(stmt.target)
            inferred = self.inferencer.infer(stmt.value)

            if existing is None:
                if inferred is None:
                    raise self._err(
                        f"Cannot determine type for '{stmt.target}'",
                        stmt.line,
                        stmt.col,
                    )
                self.st.define(stmt.target, inferred)
                ir_type = _to_ir_type(inferred)
                ir_val = self._build_expr(stmt.value, expected_type=ir_type)
                return IRVarDecl(name=stmt.target, type_=ir_type, value=ir_val)

            ir_type = _to_ir_type(existing)
            ir_val = self._build_expr(stmt.value, expected_type=ir_type)
            return IRAssign(target=stmt.target, value=ir_val)

        elif name == "AugAssign":
            existing = self.st.lookup(stmt.target)
            if existing is None:
                raise self._err(
                    f"Undefined variable '{stmt.target}'", stmt.line, stmt.col
                )
            ir_type = _to_ir_type(existing)
            ir_val = self._build_expr(stmt.value, expected_type=ir_type)
            return IRAugAssign(target=stmt.target, op=stmt.op, value=ir_val)

        elif name == "IfStmt":
            cond = self._build_expr(stmt.condition)
            then_body = tuple(self._build_stmts(stmt.then_body, return_type))
            elif_clauses = tuple(
                (self._build_expr(c), tuple(self._build_stmts(b, return_type)))
                for c, b in stmt.elif_clauses
            )
            else_body = (
                tuple(self._build_stmts(stmt.else_body, return_type))
                if stmt.else_body
                else None
            )
            return IRIf(
                condition=cond,
                then_body=then_body,
                elif_clauses=elif_clauses,
                else_body=else_body,
            )

        elif name == "WhileStmt":
            label = f"__loop_{len(self._loop_stack)}"
            self._loop_stack.append(label)
            cond = self._build_expr(stmt.condition)
            body = tuple(self._build_stmts(stmt.body, return_type))
            self._loop_stack.pop()
            return IRWhile(condition=cond, body=body, label=label)

        elif name == "ForRangeStmt":
            label = f"__loop_{len(self._loop_stack)}"
            self._loop_stack.append(label)
            self.st.define(stmt.target, IntType())
            start = self._build_expr(stmt.start)
            stop = self._build_expr(stmt.stop)
            step = self._build_expr(stmt.step) if stmt.step else None
            body = tuple(self._build_stmts(stmt.body, return_type))
            self._loop_stack.pop()
            return IRForRange(
                target=stmt.target,
                start=start,
                stop=stop,
                step=step,
                body=body,
                label=label,
            )

        elif name == "ReturnStmt":
            val = self._build_expr(stmt.value, return_type) if stmt.value else None
            return IRReturn(value=val, result_type=return_type)

        elif name == "PrintStmt":
            val = self._build_expr(stmt.value)
            val_type = self.inferencer.infer(stmt.value)
            if val_type is None:
                val_type = IntType()
            return IRPrint(value=val, value_type=_to_ir_type(val_type))

        elif name == "BreakStmt":
            if not self._loop_stack:
                raise self._err("'break' must be inside a loop", stmt.line, stmt.col)
            return IRBreak(label=self._loop_stack[-1])

        elif name == "ContinueStmt":
            if not self._loop_stack:
                raise self._err("'continue' must be inside a loop", stmt.line, stmt.col)
            return IRContinue(label=self._loop_stack[-1])

        elif name == "DelStmt":
            target_val = self._build_expr(stmt.target)
            key_val = self._build_expr(stmt.key)
            return IRDictDelete(target=target_val, key=key_val)

        elif name == "SubscriptAssign":
            target_val = self._build_expr(stmt.target)
            index_val = self._build_expr(stmt.index)
            value = self._build_expr(stmt.value)
            target_type = self.inferencer.infer(stmt.target)
            if isinstance(target_type, ListType):
                value_type = _to_ir_type(target_type.element_type)
            elif isinstance(target_type, DictType):
                value_type = _to_ir_type(target_type.value_type)
            elif isinstance(target_type, StrType):
                value_type = IRStrType()
            else:
                value_type = IRIntType()
            return IRSubscriptAssign(
                target=target_val, index=index_val, value=value, value_type=value_type
            )

        else:
            raise self._err(f"Unknown statement type: {name}")

    def _build_expr(self, expr, expected_type=None):
        name = type(expr).__name__

        if name == "IntLiteral":
            if isinstance(expected_type, IRFloatType):
                return IRFloatLit(value=float(expr.value))
            return IRIntLit(value=expr.value)

        elif name == "FloatLiteral":
            return IRFloatLit(value=expr.value)

        elif name == "BoolLiteral":
            return IRBoolLit(value=expr.value)

        elif name == "StrLiteral":
            return IRStrLit(value=expr.value)

        elif name == "Name":
            return IRName(name=expr.name)

        elif name == "BinOp":
            result_type = self.inferencer.infer(expr)
            if result_type is None:
                result_type = IntType()
            ir_result = _to_ir_type(result_type)
            left = self._build_expr(expr.left, ir_result)
            right = self._build_expr(expr.right, ir_result)
            return IRBinOp(op=expr.op, left=left, right=right, result_type=ir_result)

        elif name == "UnaryOp":
            operand_type = self.inferencer.infer(expr.operand)
            if expr.op == "not":
                ir_result = IRBoolType()
            else:
                ir_result = _to_ir_type(operand_type) if operand_type else IRIntType()
            operand = self._build_expr(expr.operand, ir_result)
            return IRUnaryOpExpr(op=expr.op, operand=operand, result_type=ir_result)

        elif name == "Comparison":
            left_type = self.inferencer.infer(expr.left)
            right_type = self.inferencer.infer(expr.right)

            # Handle dict membership: key in dict
            if expr.op == "in" and isinstance(right_type, DictType):
                key = self._build_expr(expr.left)
                dict_val = self._build_expr(expr.right)
                return IRDictContains(key=key, dict=dict_val)

            # Handle dict non-membership: key not in dict
            if expr.op == "not_in" and isinstance(right_type, DictType):
                key = self._build_expr(expr.left)
                dict_val = self._build_expr(expr.right)
                return IRUnaryOpExpr(
                    op="not",
                    operand=IRDictContains(key=key, dict=dict_val),
                    result_type=IRBoolType(),
                )

            ir_left_t = _to_ir_type(left_type) if left_type else IRIntType()
            left = self._build_expr(expr.left, ir_left_t)
            right = self._build_expr(expr.right, ir_left_t)
            return IRCompare(op=expr.op, left=left, right=right)

        elif name == "BoolOp":
            op_map = {"and": "&&", "or": "||"}
            values = tuple(self._build_expr(v) for v in expr.values)
            return IRBoolOp(op=op_map[expr.op], values=values)

        elif name == "ListLiteral":
            if not expr.elements:
                elem_type = IRIntType()
                if isinstance(expected_type, IRListType):
                    elem_type = expected_type.element_type
                return IRListLit(elements=(), element_type=elem_type)
            elem_t = self.inferencer.infer(expr.elements[0])
            ir_elem_t = _to_ir_type(elem_t) if elem_t else IRIntType()
            elems = tuple(self._build_expr(e, ir_elem_t) for e in expr.elements)
            return IRListLit(elements=elems, element_type=ir_elem_t)

        elif name == "DictLiteral":
            if not expr.pairs:
                key_t = IRIntType()
                val_t = IRIntType()
                if isinstance(expected_type, IRDictType):
                    key_t = expected_type.key_type
                    val_t = expected_type.value_type
                return IRDictLit(pairs=(), key_type=key_t, value_type=val_t)
            first_key_t = self.inferencer.infer(expr.pairs[0][0])
            first_val_t = self.inferencer.infer(expr.pairs[0][1])
            ir_key_t = _to_ir_type(first_key_t) if first_key_t else IRIntType()
            ir_val_t = _to_ir_type(first_val_t) if first_val_t else IRIntType()
            pairs = tuple(
                (self._build_expr(k, ir_key_t), self._build_expr(v, ir_val_t))
                for k, v in expr.pairs
            )
            return IRDictLit(pairs=pairs, key_type=ir_key_t, value_type=ir_val_t)

        elif name == "Subscript":
            val = self._build_expr(expr.value)
            idx = self._build_expr(expr.index)
            val_type = self.inferencer.infer(expr.value)
            ir_val_type = _to_ir_type(val_type) if val_type else IRIntType()
            if isinstance(val_type, ListType):
                result_type = _to_ir_type(val_type.element_type)
            elif isinstance(val_type, StrType):
                result_type = IRStrType()
            elif isinstance(val_type, DictType):
                result_type = _to_ir_type(val_type.value_type)
            else:
                result_type = IRIntType()
            return IRSubscript(
                value=val, index=idx, value_type=ir_val_type, result_type=result_type
            )

        elif name == "FunctionCall":
            if expr.name == "len":
                arg = self._build_expr(expr.args[0])
                return IRFunctionCall(name="len", args=(arg,), return_type=IRIntType())

            if expr.name == "open":
                path = self._build_expr(expr.args[0])
                mode = self._build_expr(expr.args[1]) if len(expr.args) > 1 else None
                return IRFileOpen(path=path, mode=mode)

            sig = self.st.lookup_function(expr.name)
            if sig is None:
                if self.st.lookup_class(expr.name):
                    args = []
                    for a in expr.args:
                        args.append(self._build_expr(a))
                    return IRNew(class_name=expr.name, args=tuple(args))
                raise self._err(
                    f"Undefined function '{expr.name}'", expr.line, expr.col
                )
            param_types, ret_type = sig
            ir_ret = _to_ir_type(ret_type)
            args = []
            for i, a in enumerate(expr.args):
                pt = _to_ir_type(param_types[i]) if i < len(param_types) else None
                args.append(self._build_expr(a, pt))
            return IRFunctionCall(name=expr.name, args=tuple(args), return_type=ir_ret)

        elif name == "AttributeExpr":
            val = self._build_expr(expr.value)
            val_type = self.inferencer.infer(expr.value)
            if isinstance(val_type, ClassType):
                field_type = self.st.get_field_type(val_type.name, expr.attr)
                if field_type:
                    ir_result = _to_ir_type(field_type)
                    return IRStructAccess(
                        value=val, field=expr.attr, result_type=ir_result
                    )
            raise self._err(
                f"Unknown field '{expr.attr}' in class",
                expr.line,
                expr.col,
            )

        elif name == "MethodCall":
            val = self._build_expr(expr.value)
            val_type = self.inferencer.infer(expr.value)
            if isinstance(val_type, ClassType):
                arity = len(expr.args)
                method = self.st.lookup_method(val_type.name, expr.method, arity)
                if method:
                    ir_args = []
                    for i, arg in enumerate(expr.args):
                        if i < len(method.params):
                            pt = _to_ir_type(method.params[i].type_annotation)
                            ir_args.append(self._build_expr(arg, pt))
                        else:
                            ir_args.append(self._build_expr(arg))
                    ir_ret = _to_ir_type(method.return_type)
                    return IRMethodCall(
                        value=val,
                        method=expr.method,
                        args=tuple(ir_args),
                        result_type=ir_ret,
                    )
            if isinstance(val_type, FileType):
                file_val = self._build_expr(expr.value)
                ir_args = [self._build_expr(a) for a in expr.args]
                return IRFileMethod(
                    file=file_val, method=expr.method, args=tuple(ir_args)
                )
            raise self._err(
                f"Unknown method '{expr.method}' in class",
                expr.line,
                expr.col,
            )

        elif name == "SelfExpr":
            return IRSelf()

        elif name == "NewExpr":
            args = []
            for a in expr.args:
                args.append(self._build_expr(a))
            return IRNew(class_name=expr.class_name, args=tuple(args))

        else:
            raise self._err(f"Unknown expression type: {name}")


def build_ir(module, filename: str = "<unknown>", source_lines: list = None):
    builder = IRBuilder(filename, source_lines)
    return builder.build(module)
