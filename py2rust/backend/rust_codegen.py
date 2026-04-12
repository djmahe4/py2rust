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
            decls[stmt.target] = IRIntType()
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
            # Only use mut if the variable is modified after initialization or is a loop target
            mut = "mut " if name in self._mutated_vars else ""
            # Omit default value to avoid unnecessary work and enable better Rust optimization
            self._emit(f"let {mut}{name}: {_rust_type(type_)};")
        
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
            step = self._gen_expr(stmt.step) if stmt.step is not None else "1"
            
            # Use a block to properly scope loop-control temporaries and prevent shadowing
            self._emit("{")
            self._indent += 1
            
            # Evaluate bounds exactly once to match Python range() semantics
            self._emit(f"let __stop = {stop};")
            self._emit(f"let __step = {step};")
            self._emit(f"{stmt.target} = {start};")
            
            self._emit(f"while if (__step) > 0 {{ {stmt.target} < (__stop) }} else {{ {stmt.target} > (__stop) }} {{")
            self._indent += 1
            for s in stmt.body:
                self._gen_stmt(s)
            self._emit(f"{stmt.target} += __step;")
            self._indent -= 1
            self._emit("}")
            
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
            
            # Robust Python indexing: bind collection to a temp reference to avoid redundant evaluations
            # and then calculate actual usize index relative to length if negative.
            
            if isinstance(expr.value_type, IRStrType):
                len_expr = "__coll.chars().count() as i32"
                inner_expr = f"__coll.chars().nth(actual_idx).unwrap().to_string()"
            else:
                len_expr = "__coll.len() as i32"
                inner_expr = f"__coll[actual_idx]"
            
            if isinstance(expr.result_type, (IRStrType, IRListType)) and not isinstance(expr.value_type, IRStrType):
                inner_expr = f"({inner_expr}).clone()"
            
            # Use an immediately-invoked block to isolate the temporary collection reference
            return (
                f"({{ let __coll = &({val}); "
                f"let actual_idx = ({{ let i = {idx}; if i < 0 {{ (i + ({len_expr})) as usize }} else {{ i as usize }} }}); "
                f"{inner_expr} }})"
            )

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
            
        if isinstance(expr.result_type, IRFloatType):
            # Enforce explicit casting for arithmetic involving mixed types
            left = self._gen_expr_as_float(expr.left)
            right = self._gen_expr_as_float(expr.right)
        else:
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
