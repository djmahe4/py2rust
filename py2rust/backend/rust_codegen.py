from __future__ import annotations
from ..ir.ir_nodes import (
    IRModule, IRFunction, IRParam,
    IRIntType, IRFloatType, IRBoolType, IRStrType, IRListType,
    IRIntLit, IRFloatLit, IRBoolLit, IRStrLit, IRName, IRBinOp, IRUnaryOpExpr,
    IRCompare, IRBoolOp, IRListLit, IRSubscript, IRFunctionCall,
    IRVarDecl, IRAssign, IRAugAssign, IRIf, IRWhile, IRForRange, IRReturn, IRPrint,
)


def _rust_type(t) -> str:
    if isinstance(t, IRIntType): return "i32"
    if isinstance(t, IRFloatType): return "f64"
    if isinstance(t, IRBoolType): return "bool"
    if isinstance(t, IRStrType): return "String"
    if isinstance(t, IRListType): return f"Vec<{_rust_type(t.element_type)}>"
    return "i32"


class RustCodegen:
    def __init__(self):
        self._indent = 0
        self._lines: list = []

    def _emit(self, line: str) -> None:
        self._lines.append("    " * self._indent + line)

    def _emit_blank(self) -> None:
        self._lines.append("")

    def generate(self, module: IRModule) -> str:
        for i, func in enumerate(module.functions):
            if i > 0:
                self._emit_blank()
            self._gen_function(func)
        return "\n".join(self._lines) + "\n"

    def _gen_function(self, func: IRFunction) -> None:
        params = ", ".join(f"{p.name}: {_rust_type(p.type_)}" for p in func.params)
        ret = _rust_type(func.return_type)
        self._emit(f"fn {func.name}({params}) -> {ret} {{")
        self._indent += 1
        for stmt in func.body:
            self._gen_stmt(stmt)
        self._indent -= 1
        self._emit("}")

    def _gen_stmt(self, stmt) -> None:
        name = type(stmt).__name__

        if name == 'IRVarDecl':
            val = self._gen_expr(stmt.value, stmt.type_)
            self._emit(f"let {stmt.name}: {_rust_type(stmt.type_)} = {val};")

        elif name == 'IRAssign':
            val = self._gen_expr(stmt.value)
            self._emit(f"{stmt.target} = {val};")

        elif name == 'IRAugAssign':
            val = self._gen_expr(stmt.value)
            self._emit(f"{stmt.target} {stmt.op} {val};")

        elif name == 'IRIf':
            cond = self._gen_expr(stmt.condition)
            self._emit(f"if {cond} {{")
            self._indent += 1
            for s in stmt.then_body:
                self._gen_stmt(s)
            self._indent -= 1
            for (elif_cond, elif_body) in stmt.elif_clauses:
                ec = self._gen_expr(elif_cond)
                self._emit(f"}} else if {ec} {{")
                self._indent += 1
                for s in elif_body:
                    self._gen_stmt(s)
                self._indent -= 1
            if stmt.else_body is not None:
                self._emit("} else {")
                self._indent += 1
                for s in stmt.else_body:
                    self._gen_stmt(s)
                self._indent -= 1
            self._emit("}")

        elif name == 'IRWhile':
            cond = self._gen_expr(stmt.condition)
            self._emit(f"while {cond} {{")
            self._indent += 1
            for s in stmt.body:
                self._gen_stmt(s)
            self._indent -= 1
            self._emit("}")

        elif name == 'IRForRange':
            start = self._gen_expr(stmt.start)
            stop = self._gen_expr(stmt.stop)
            if stmt.step is not None:
                step = self._gen_expr(stmt.step)
                self._emit(f"for {stmt.target} in ({start}..{stop}).step_by({step} as usize) {{")
            else:
                self._emit(f"for {stmt.target} in {start}..{stop} {{")
            self._indent += 1
            for s in stmt.body:
                self._gen_stmt(s)
            self._indent -= 1
            self._emit("}")

        elif name == 'IRReturn':
            if stmt.value is not None:
                val = self._gen_expr(stmt.value)
                self._emit(f"return {val};")
            else:
                self._emit("return;")

        elif name == 'IRPrint':
            val = self._gen_expr(stmt.value)
            self._emit(f'println!("{{}}", {val});')

        else:
            self._emit(f"// unknown stmt: {name}")

    def _gen_expr(self, expr, expected_type=None) -> str:
        name = type(expr).__name__

        if name == 'IRIntLit':
            return str(expr.value)
        elif name == 'IRFloatLit':
            v = expr.value
            s = repr(v)
            if '.' not in s and 'e' not in s.lower():
                s += ".0"
            return s
        elif name == 'IRBoolLit':
            return "true" if expr.value else "false"
        elif name == 'IRStrLit':
            escaped = expr.value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
            return f'"{escaped}".to_string()'
        elif name == 'IRName':
            return expr.name
        elif name == 'IRBinOp':
            return self._gen_binop(expr)
        elif name == 'IRUnaryOpExpr':
            operand = self._gen_expr(expr.operand)
            if expr.op == 'not':
                return f"!{operand}"
            if expr.op == '-':
                return f"-{operand}"
            return operand
        elif name == 'IRCompare':
            left = self._gen_expr(expr.left)
            right = self._gen_expr(expr.right)
            return f"{left} {expr.op} {right}"
        elif name == 'IRBoolOp':
            parts = [self._gen_expr(v) for v in expr.values]
            return f" {expr.op} ".join(parts)
        elif name == 'IRListLit':
            if not expr.elements:
                return f"Vec::<{_rust_type(expr.element_type)}>::new()"
            elems = ", ".join(self._gen_expr(e) for e in expr.elements)
            return f"vec![{elems}]"
        elif name == 'IRSubscript':
            val = self._gen_expr(expr.value)
            idx = self._gen_expr(expr.index)
            return f"{val}[{idx} as usize]"
        elif name == 'IRFunctionCall':
            args = ", ".join(self._gen_expr(a) for a in expr.args)
            return f"{expr.name}({args})"
        return f"/* unknown expr {name} */"

    def _gen_binop(self, expr) -> str:
        if expr.op == '/':
            left = self._gen_expr_as_float(expr.left)
            right = self._gen_expr_as_float(expr.right)
            return f"{left} / {right}"
        if expr.op == '//':
            left = self._gen_expr(expr.left)
            right = self._gen_expr(expr.right)
            return f"{left} / {right}"
        left = self._gen_expr(expr.left)
        right = self._gen_expr(expr.right)
        return f"{left} {expr.op} {right}"

    def _gen_expr_as_float(self, expr) -> str:
        name = type(expr).__name__
        if name == 'IRIntLit':
            return f"{expr.value}.0_f64"
        if name == 'IRFloatLit':
            return self._gen_expr(expr)
        if name == 'IRName':
            return f"{expr.name} as f64"
        inner = self._gen_expr(expr)
        if name == 'IRBinOp' and isinstance(expr.result_type, IRFloatType):
            return inner
        return f"({inner}) as f64"


def generate_rust(module: IRModule) -> str:
    cg = RustCodegen()
    return cg.generate(module)
