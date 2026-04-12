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


def _collect_mutated_vars(stmts) -> set:
    """Recursively collect all variable names that are reassigned (not just declared)."""
    mutated: set = set()
    for stmt in stmts:
        if isinstance(stmt, IRAssign):
            mutated.add(stmt.target)
        elif isinstance(stmt, IRAugAssign):
            mutated.add(stmt.target)
        elif isinstance(stmt, IRIf):
            mutated |= _collect_mutated_vars(stmt.then_body)
            for _, elif_body in stmt.elif_clauses:
                mutated |= _collect_mutated_vars(elif_body)
            if stmt.else_body:
                mutated |= _collect_mutated_vars(stmt.else_body)
        elif isinstance(stmt, IRWhile):
            mutated |= _collect_mutated_vars(stmt.body)
        elif isinstance(stmt, IRForRange):
            mutated |= _collect_mutated_vars(stmt.body)
    return mutated


class RustCodegen:
    def __init__(self):
        self._indent = 0
        self._lines: list = []
        self._mutated_vars: set = set()
        self._in_main: bool = False

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
        # Collect all variables that are reassigned in this function body
        self._mutated_vars = _collect_mutated_vars(func.body)
        # Also collect for-loop variables that need mut if reassigned inside the loop body
        params = ", ".join(f"{p.name}: {_rust_type(p.type_)}" for p in func.params)

        # Special-case: Rust's `main` must return () or implement Termination.
        # If user wrote `def main() -> int`, emit `fn main()` with no return type.
        is_main = func.name == "main"
        self._in_main = is_main
        if is_main:
            self._emit(f"fn {func.name}({params}) {{")
        else:
            ret = _rust_type(func.return_type)
            self._emit(f"fn {func.name}({params}) -> {ret} {{")
        self._indent += 1
        for stmt in func.body:
            self._gen_stmt(stmt)
        self._indent -= 1
        self._emit("}")

    def _gen_stmt(self, stmt) -> None:
        if isinstance(stmt, IRVarDecl):
            val = self._gen_expr(stmt.value, stmt.type_)
            mut = "mut " if stmt.name in self._mutated_vars else ""
            self._emit(f"let {mut}{stmt.name}: {_rust_type(stmt.type_)} = {val};")

        elif isinstance(stmt, IRAssign):
            val = self._gen_expr(stmt.value)
            self._emit(f"{stmt.target} = {val};")

        elif isinstance(stmt, IRAugAssign):
            val = self._gen_expr(stmt.value)
            self._emit(f"{stmt.target} {stmt.op} {val};")

        elif isinstance(stmt, IRIf):
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

        elif isinstance(stmt, IRWhile):
            cond = self._gen_expr(stmt.condition)
            self._emit(f"while {cond} {{")
            self._indent += 1
            for s in stmt.body:
                self._gen_stmt(s)
            self._indent -= 1
            self._emit("}")

        elif isinstance(stmt, IRForRange):
            start = self._gen_expr(stmt.start)
            stop = self._gen_expr(stmt.stop)
            if stmt.step is not None:
                step_expr = self._gen_expr(stmt.step)
                
                # Try to determine if the step is a negative constant
                is_neg_const = False
                pos_step_val = None
                
                if isinstance(stmt.step, IRIntLit) and stmt.step.value < 0:
                    is_neg_const = True
                    pos_step_val = -stmt.step.value
                elif isinstance(stmt.step, IRUnaryOpExpr) and stmt.step.op == '-' and isinstance(stmt.step.operand, IRIntLit):
                    is_neg_const = True
                    pos_step_val = stmt.step.operand.value
                
                if is_neg_const:
                    # Python range(start, stop, -step) -> Rust (stop + 1..start + 1).rev().step_by(step)
                    self._emit(f"for {stmt.target} in (({stop}) + 1..({start}) + 1).rev().step_by({pos_step_val} as usize) {{")
                else:
                    self._emit(f"for {stmt.target} in ({start}..{stop}).step_by({step_expr} as usize) {{")
            else:
                self._emit(f"for {stmt.target} in {start}..{stop} {{")
            self._indent += 1
            for s in stmt.body:
                self._gen_stmt(s)
            self._indent -= 1
            self._emit("}")

        elif isinstance(stmt, IRReturn):
            if self._in_main:
                # Rust's main() returns (), so drop the return value
                self._emit("return;")
            elif stmt.value is not None:
                val = self._gen_expr(stmt.value)
                self._emit(f"return {val};")
            else:
                self._emit("return;")

        elif isinstance(stmt, IRPrint):
            val = self._gen_expr(stmt.value)
            # Use Debug formatting for Vec, Display for others
            fmt = "{:?}" if isinstance(stmt.value_type, IRListType) else "{}"
            self._emit(f'println!("{fmt}", {val});')

        else:
            self._emit(f"// unknown stmt: {type(stmt).__name__}")

    def _gen_expr(self, expr, expected_type=None) -> str:
        if isinstance(expr, IRIntLit):
            return str(expr.value)
        elif isinstance(expr, IRFloatLit):
            v = expr.value
            s = repr(v)
            if '.' not in s and 'e' not in s.lower():
                s += ".0"
            return s
        elif isinstance(expr, IRBoolLit):
            return "true" if expr.value else "false"
        elif isinstance(expr, IRStrLit):
            escaped = expr.value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
            return f'"{escaped}".to_string()'
        elif isinstance(expr, IRName):
            return expr.name
        elif isinstance(expr, IRBinOp):
            return f"({self._gen_binop(expr)})"
        elif isinstance(expr, IRUnaryOpExpr):
            operand = self._gen_expr(expr.operand)
            if expr.op == 'not':
                return f"(!({operand}))"
            if expr.op == '-':
                return f"(-({operand}))"
            return operand
        elif isinstance(expr, IRCompare):
            left = self._gen_expr(expr.left)
            right = self._gen_expr(expr.right)
            return f"({left} {expr.op} {right})"
        elif isinstance(expr, IRBoolOp):
            op = f" {expr.op} "
            parts = [self._gen_expr(v) for v in expr.values]
            return f"({op.join(parts)})"
        elif isinstance(expr, IRListLit):
            if not expr.elements:
                return f"Vec::<{_rust_type(expr.element_type)}>::new()"
            elems = ", ".join(self._gen_expr(e) for e in expr.elements)
            return f"vec![{elems}]"
        elif isinstance(expr, IRSubscript):
            val = self._gen_expr(expr.value)
            idx = self._gen_expr(expr.index)
            # idx as usize has high precedence, so wrap it
            return f"{val}[({idx}) as usize]"
        elif isinstance(expr, IRFunctionCall):
            args = ", ".join(self._gen_expr(a) for a in expr.args)
            return f"{expr.name}({args})"
        return f"/* unknown expr {type(expr).__name__} */"

    def _gen_binop(self, expr) -> str:
        if expr.op == '/':
            left = self._gen_expr_as_float(expr.left)
            right = self._gen_expr_as_float(expr.right)
            return f"{left} / {right}"
        if expr.op == '//':
            left = self._gen_expr(expr.left)
            right = self._gen_expr(expr.right)
            # Python floor division: (a as f64 / b as f64).floor() as i32
            return f"({left} as f64 / {right} as f64).floor() as i32"
        left = self._gen_expr(expr.left)
        right = self._gen_expr(expr.right)
        return f"{left} {expr.op} {right}"

    def _gen_expr_as_float(self, expr) -> str:
        if isinstance(expr, IRIntLit):
            return f"{expr.value}.0_f64"
        if isinstance(expr, IRFloatLit):
            return self._gen_expr(expr)
        if isinstance(expr, IRName):
            return f"({expr.name} as f64)"
        inner = self._gen_expr(expr)
        if isinstance(expr, IRBinOp) and isinstance(expr.result_type, IRFloatType):
            return inner
        return f"({inner}) as f64"


def generate_rust(module: IRModule) -> str:
    cg = RustCodegen()
    return cg.generate(module)
