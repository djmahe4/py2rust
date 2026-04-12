from __future__ import annotations
from ..frontend.ast_nodes import (
    IntType, FloatType, BoolType, StrType, ListType,
)
from ..ir.ir_nodes import (
    IRModule, IRFunction, IRParam,
    IRIntType, IRFloatType, IRBoolType, IRStrType, IRListType,
    IRIntLit, IRFloatLit, IRBoolLit, IRStrLit, IRName, IRBinOp, IRUnaryOpExpr,
    IRCompare, IRBoolOp, IRListLit, IRSubscript, IRFunctionCall,
    IRVarDecl, IRAssign, IRAugAssign, IRIf, IRWhile, IRForRange, IRReturn, IRPrint,
)
from ..utils.errors import SemanticError
from .symbol_table import SymbolTable
from .type_inferencer import TypeInferencer
from .type_checker import TypeChecker


def _to_ir_type(t):
    if isinstance(t, IntType): return IRIntType()
    if isinstance(t, FloatType): return IRFloatType()
    if isinstance(t, BoolType): return IRBoolType()
    if isinstance(t, StrType): return IRStrType()
    if isinstance(t, ListType): return IRListType(element_type=_to_ir_type(t.element_type))
    raise ValueError(f"Unknown type: {t}")


class IRBuilder:
    def __init__(self, filename: str = "<unknown>", source_lines: list = None):
        self.filename = filename
        self.source_lines = source_lines or []
        self.st = SymbolTable()
        self.inferencer = TypeInferencer(self.st)

    def _err(self, msg: str, line: int = 0, col: int = 0) -> SemanticError:
        return SemanticError(
            message=msg, filename=self.filename, line=line, column=col,
            source_lines=self.source_lines,
        )

    def build(self, module) -> IRModule:
        checker = TypeChecker(self.st, self.filename, self.source_lines)
        checker.check_module(module)

        ir_funcs = []
        for func in module.functions:
            ir_funcs.append(self._build_function(func))
        return IRModule(functions=tuple(ir_funcs), filename=module.filename)

    def _build_function(self, func) -> IRFunction:
        self.st.enter_scope(func.name)

        params = []
        for p in func.params:
            ir_t = _to_ir_type(p.type_annotation)
            self.st.define(p.name, p.type_annotation)
            params.append(IRParam(name=p.name, type_=ir_t))

        ret_type = _to_ir_type(func.return_type)
        body = self._build_stmts(func.body)

        self.st.exit_scope()
        return IRFunction(
            name=func.name,
            params=tuple(params),
            return_type=ret_type,
            body=tuple(body),
        )

    def _build_stmts(self, stmts) -> list:
        return [self._build_stmt(s) for s in stmts]

    def _build_stmt(self, stmt):
        name = type(stmt).__name__

        if name == 'VarDecl':
            inferred = self.inferencer.infer(stmt.value)
            ann = stmt.type_annotation
            actual_type = ann if ann is not None else inferred
            if actual_type is None:
                raise self._err(f"Cannot determine type for '{stmt.name}'", stmt.line, stmt.col)
            ir_type = _to_ir_type(actual_type)
            self.st.define(stmt.name, actual_type)
            ir_val = self._build_expr(stmt.value, expected_type=ir_type)
            return IRVarDecl(name=stmt.name, type_=ir_type, value=ir_val)

        elif name == 'Assign':
            existing = self.st.lookup(stmt.target)
            inferred = self.inferencer.infer(stmt.value)
            if existing is None:
                if inferred is None:
                    raise self._err(f"Cannot determine type for '{stmt.target}'", stmt.line, stmt.col)
                self.st.define(stmt.target, inferred)
                ir_type = _to_ir_type(inferred)
            else:
                ir_type = _to_ir_type(existing)
            ir_val = self._build_expr(stmt.value, expected_type=ir_type)
            return IRAssign(target=stmt.target, value=ir_val)

        elif name == 'AugAssign':
            existing = self.st.lookup(stmt.target)
            if existing is None:
                raise self._err(f"Undefined variable '{stmt.target}'", stmt.line, stmt.col)
            ir_type = _to_ir_type(existing)
            ir_val = self._build_expr(stmt.value, expected_type=ir_type)
            return IRAugAssign(target=stmt.target, op=stmt.op, value=ir_val)

        elif name == 'IfStmt':
            cond = self._build_expr(stmt.condition)
            then_body = tuple(self._build_stmts(stmt.then_body))
            elif_clauses = tuple(
                (self._build_expr(c), tuple(self._build_stmts(b)))
                for c, b in stmt.elif_clauses
            )
            else_body = tuple(self._build_stmts(stmt.else_body)) if stmt.else_body else None
            return IRIf(condition=cond, then_body=then_body, elif_clauses=elif_clauses, else_body=else_body)

        elif name == 'WhileStmt':
            cond = self._build_expr(stmt.condition)
            body = tuple(self._build_stmts(stmt.body))
            return IRWhile(condition=cond, body=body)

        elif name == 'ForRangeStmt':
            self.st.define(stmt.target, IntType())
            start = self._build_expr(stmt.start)
            stop = self._build_expr(stmt.stop)
            step = self._build_expr(stmt.step) if stmt.step else None
            body = tuple(self._build_stmts(stmt.body))
            return IRForRange(target=stmt.target, start=start, stop=stop, step=step, body=body)

        elif name == 'ReturnStmt':
            val = self._build_expr(stmt.value) if stmt.value else None
            return IRReturn(value=val)

        elif name == 'PrintStmt':
            val = self._build_expr(stmt.value)
            val_type = self.inferencer.infer(stmt.value)
            if val_type is None:
                val_type = IntType()
            return IRPrint(value=val, value_type=_to_ir_type(val_type))

        else:
            raise self._err(f"Unknown statement type: {name}")

    def _build_expr(self, expr, expected_type=None):
        name = type(expr).__name__

        if name == 'IntLiteral':
            if isinstance(expected_type, IRFloatType):
                return IRFloatLit(value=float(expr.value))
            return IRIntLit(value=expr.value)

        elif name == 'FloatLiteral':
            return IRFloatLit(value=expr.value)

        elif name == 'BoolLiteral':
            return IRBoolLit(value=expr.value)

        elif name == 'StrLiteral':
            return IRStrLit(value=expr.value)

        elif name == 'Name':
            return IRName(name=expr.name)

        elif name == 'BinOp':
            result_type = self.inferencer.infer(expr)
            if result_type is None:
                result_type = IntType()
            ir_result = _to_ir_type(result_type)
            left = self._build_expr(expr.left, ir_result)
            right = self._build_expr(expr.right, ir_result)
            return IRBinOp(op=expr.op, left=left, right=right, result_type=ir_result)

        elif name == 'UnaryOp':
            operand_type = self.inferencer.infer(expr.operand)
            if expr.op == 'not':
                ir_result = IRBoolType()
            else:
                ir_result = _to_ir_type(operand_type) if operand_type else IRIntType()
            operand = self._build_expr(expr.operand, ir_result)
            return IRUnaryOpExpr(op=expr.op, operand=operand, result_type=ir_result)

        elif name == 'Comparison':
            left_type = self.inferencer.infer(expr.left)
            ir_left_t = _to_ir_type(left_type) if left_type else IRIntType()
            left = self._build_expr(expr.left, ir_left_t)
            right = self._build_expr(expr.right, ir_left_t)
            return IRCompare(op=expr.op, left=left, right=right)

        elif name == 'BoolOp':
            op_map = {'and': '&&', 'or': '||'}
            values = tuple(self._build_expr(v) for v in expr.values)
            return IRBoolOp(op=op_map[expr.op], values=values)

        elif name == 'ListLiteral':
            if not expr.elements:
                elem_type = IRIntType()
                if isinstance(expected_type, IRListType):
                    elem_type = expected_type.element_type
                return IRListLit(elements=(), element_type=elem_type)
            elem_t = self.inferencer.infer(expr.elements[0])
            ir_elem_t = _to_ir_type(elem_t) if elem_t else IRIntType()
            elems = tuple(self._build_expr(e, ir_elem_t) for e in expr.elements)
            return IRListLit(elements=elems, element_type=ir_elem_t)

        elif name == 'Subscript':
            val = self._build_expr(expr.value)
            idx = self._build_expr(expr.index)
            val_type = self.inferencer.infer(expr.value)
            ir_val_type = _to_ir_type(val_type) if val_type else IRIntType()
            if isinstance(val_type, ListType):
                result_type = _to_ir_type(val_type.element_type)
            elif isinstance(val_type, StrType):
                result_type = IRStrType()
            else:
                result_type = IRIntType()
            return IRSubscript(value=val, index=idx, value_type=ir_val_type, result_type=result_type)

        elif name == 'FunctionCall':
            sig = self.st.lookup_function(expr.name)
            if sig is None:
                raise self._err(f"Undefined function '{expr.name}'", expr.line, expr.col)
            param_types, ret_type = sig
            ir_ret = _to_ir_type(ret_type)
            args = []
            for i, a in enumerate(expr.args):
                pt = _to_ir_type(param_types[i]) if i < len(param_types) else None
                args.append(self._build_expr(a, pt))
            return IRFunctionCall(name=expr.name, args=tuple(args), return_type=ir_ret)

        else:
            raise self._err(f"Unknown expression type: {name}")


def build_ir(module, filename: str = "<unknown>", source_lines: list = None):
    builder = IRBuilder(filename, source_lines)
    return builder.build(module)
