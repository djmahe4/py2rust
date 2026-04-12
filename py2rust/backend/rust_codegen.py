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
    return f"/* unknown type {type(t).__name__} */"


def _default_value(t) -> str:
    if isinstance(t, IRIntType): return "0"
    if isinstance(t, IRFloatType): return "0.0"
    if isinstance(t, IRBoolType): return "false"
    if isinstance(t, IRStrType): return '"".to_string()'
    if isinstance(t, IRListType): return "vec![]"
    return "/* unknown */"


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
            mutated.add(stmt.target) # Loops always assign
            mutated |= _collect_mutated_vars(stmt.body)
    return mutated


def _collect_decls(stmts) -> dict[str, object]:
    """Collect all variables that are declared in the function body."""
    decls: dict[str, object] = {}
    for stmt in stmts:
        if isinstance(stmt, IRVarDecl):
            decls[stmt.name] = stmt.type_
        elif isinstance(stmt, IRIf):
            decls.update(_collect_decls(stmt.then_body))
            for _, elif_body in stmt.elif_clauses:
                decls.update(_collect_decls(elif_body))
            if stmt.else_body:
                decls.update(_collect_decls(stmt.else_body))
        elif isinstance(stmt, IRWhile):
            decls.update(_collect_decls(stmt.body))
        elif isinstance(stmt, IRForRange):
            # IRBuilder defines the target in symbol table, so it should be in VarDecls
            # if it was used before. In our subset, loop targets are often implicit.
            # But let's assume IRVarDecl handles most. Loop target is handled separately.
            decls.update(_collect_decls(stmt.body))
    return decls


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
        # Collect all variables that are reassigned or used as loop targets
        self._mutated_vars = _collect_mutated_vars(func.body)
        
        # Emulate Python function scoping by pre-declaring all variables at the top
        decls = _collect_decls(func.body)
        
        params = ", ".join(f"{p.name}: {_rust_type(p.type_)}" for p in func.params)

        is_main = func.name == "main"
        self._in_main = is_main
        if is_main:
            self._emit(f"fn {func.name}({params}) {{")
        else:
            ret = _rust_type(func.return_type)
            self._emit(f"fn {func.name}({params}) -> {ret} {{")
        
        self._indent += 1
        
        # Emit pre-declarations
        for name, type_ in decls.items():
            mut = "mut " # Pre-declared vars must be mut if we assign them later
            self._emit(f"let {mut}{name}: {_rust_type(type_)} = {_default_value(type_)};")
        
        if decls:
            self._emit_blank()

        for stmt in func.body:
            self._gen_stmt(stmt)
            
        self._indent -= 1
        self._emit("}")

    def _gen_stmt(self, stmt) -> None:
        if isinstance(stmt, IRVarDecl):
            val = self._gen_expr(stmt.value, stmt.type_)
            # Already declared at top, so just assign
            self._emit(f"{stmt.name} = {val};")

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
            # Loop target in Rust is local to loop. Python loop target is function-scoped.
            # We can't easily fix this without making loop target a manual increment,
            # but for-loop itself can have mut target if reassigned inside.
            mut = "mut " if stmt.target in self._mutated_vars else ""
            
            if stmt.step is not None:
                step_expr = self._gen_expr(stmt.step)
                is_neg_const = False
                pos_step_val = None
                if isinstance(stmt.step, IRIntLit) and stmt.step.value < 0:
                    is_neg_const = True
                    pos_step_val = -stmt.step.value
                elif isinstance(stmt.step, IRUnaryOpExpr) and stmt.step.op == '-' and isinstance(stmt.step.operand, IRIntLit):
                    is_neg_const = True
                    pos_step_val = stmt.step.operand.value
                
                if is_neg_const:
                    self._emit(f"for {mut}{stmt.target} in (({stop}) + 1..({start}) + 1).rev().step_by({pos_step_val} as usize) {{")
                else:
                    self._emit(f"for {mut}{stmt.target} in ({start}..{stop}).step_by({step_expr} as usize) {{")
            else:
                self._emit(f"for {mut}{stmt.target} in {start}..{stop} {{")
            
            self._indent += 1
            for s in stmt.body:
                self._gen_stmt(s)
            self._indent -= 1
            self._emit("}")

        elif isinstance(stmt, IRReturn):
            if self._in_main:
                self._emit("return;")
            elif stmt.value is not None:
                val = self._gen_expr(stmt.value)
                self._emit(f"return {val};")
            else:
                self._emit("return;")

        elif isinstance(stmt, IRPrint):
            val = self._gen_expr(stmt.value)
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
            parts = [self._gen_expr(v) for v in expr.values]
            return f"({(f' {expr.op} ').join(parts)})"
        elif isinstance(expr, IRListLit):
            if not expr.elements:
                return f"Vec::<{_rust_type(expr.element_type)}>::new()"
            elems = ", ".join(self._gen_expr(e) for e in expr.elements)
            return f"vec![{elems}]"
        elif isinstance(expr, IRSubscript):
            val = self._gen_expr(expr.value)
            idx = self._gen_expr(expr.index)
            if isinstance(expr.value_type, IRStrType):
                return f"({val}.chars().nth(({idx}) as usize).unwrap().to_string())"
            
            res = f"{val}[({idx}) as usize]"
            if isinstance(expr.result_type, (IRStrType, IRListType)):
                return f"({res}).clone()"
            return res
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
