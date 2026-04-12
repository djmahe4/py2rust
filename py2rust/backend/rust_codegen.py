from __future__ import annotations
from ..ir.ir_nodes import (
    IRModule,
    IRFunction,
    IRParam,
    IRIntType,
    IRFloatType,
    IRBoolType,
    IRStrType,
    IRListType,
    IRDictType,
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
    IRVarDecl,
    IRAssign,
    IRAugAssign,
    IRIf,
    IRWhile,
    IRForRange,
    IRReturn,
    IRPrint,
    IRBreak,
    IRContinue,
    IRDictDelete,
)


def _rust_type(t) -> str:
    if isinstance(t, IRIntType):
        return "i32"
    if isinstance(t, IRFloatType):
        return "f64"
    if isinstance(t, IRBoolType):
        return "bool"
    if isinstance(t, IRStrType):
        return "String"
    if isinstance(t, IRListType):
        return f"Vec<{_rust_type(t.element_type)}>"
    if isinstance(t, IRDictType):
        return f"HashMap<{_rust_type(t.key_type)}, {_rust_type(t.value_type)}>"
    raise ValueError(f"Unknown type {type(t).__name__}")


# Rust reserved keywords that must be escaped if used as variable names
_RUST_KEYWORDS = frozenset(
    {
        "as",
        "async",
        "await",
        "break",
        "const",
        "continue",
        "crate",
        "dyn",
        "else",
        "enum",
        "extern",
        "false",
        "fn",
        "for",
        "if",
        "impl",
        "in",
        "let",
        "loop",
        "match",
        "mod",
        "move",
        "mut",
        "pub",
        "ref",
        "return",
        "self",
        "Self",
        "static",
        "struct",
        "super",
        "trait",
        "true",
        "type",
        "union",
        "unsafe",
        "use",
        "where",
        "while",
    }
)


def _mangle(name: str) -> str:
    """Escape Python identifiers that collide with Rust keywords."""
    return name + "_" if name in _RUST_KEYWORDS else name


def _collect_mutated_vars(stmts) -> set:
    """Recursively collect all variable names that are reassigned anywhere in the function."""
    mutated: set = set()
    for stmt in stmts:
        if isinstance(stmt, IRAssign):
            mutated.add(stmt.target)
        elif isinstance(stmt, IRAugAssign):
            mutated.add(stmt.target)
        elif isinstance(stmt, IRSubscriptAssign):
            if isinstance(stmt.target, IRSubscript) and isinstance(
                stmt.target.value, IRName
            ):
                mutated.add(stmt.target.value.name)
            elif isinstance(stmt.target, IRName):
                mutated.add(stmt.target.name)
        elif isinstance(stmt, IRIf):
            mutated |= _collect_mutated_vars(stmt.then_body)
            for _, elif_body in stmt.elif_clauses:
                mutated |= _collect_mutated_vars(elif_body)
            if stmt.else_body:
                mutated |= _collect_mutated_vars(stmt.else_body)
        elif isinstance(stmt, IRWhile):
            mutated |= _collect_mutated_vars(stmt.body)
        elif isinstance(stmt, IRForRange):
            mutated.add(stmt.target)  # Loops always assign
            mutated |= _collect_mutated_vars(stmt.body)
    return mutated


def _collect_decls(stmts) -> dict[str, object]:
    """Collect variable declarations that need function-level pre-declaration."""
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
    return decls


def _vars_declared_in_loop(stmts) -> set:
    """Collect variable names that are declared inside while loops (not for loops).

    For loop targets need to be accessible after the loop (Python semantics),
    so they're handled separately in _collect_decls.
    """
    loop_vars: set = set()
    for stmt in stmts:
        if isinstance(stmt, IRVarDecl):
            loop_vars.add(stmt.name)
        elif isinstance(stmt, IRForRange):
            loop_vars |= _vars_declared_in_loop(stmt.body)
        elif isinstance(stmt, IRWhile):
            loop_vars |= _vars_declared_in_loop(stmt.body)
        elif isinstance(stmt, IRIf):
            loop_vars |= _vars_declared_in_loop(stmt.then_body)
            for _, elif_body in stmt.elif_clauses:
                loop_vars |= _vars_declared_in_loop(elif_body)
            if stmt.else_body:
                loop_vars |= _vars_declared_in_loop(stmt.else_body)
    return loop_vars


class RustCodegen:
    def __init__(self):
        self._indent = 0
        self._lines: list = []
        self._mutated_vars: set = set()
        self._in_main: bool = False
        self._at_top_level: bool = True
        self._loop_vars: set = set()

    def _emit(self, line: str) -> None:
        self._lines.append("    " * self._indent + line)

    def _emit_blank(self) -> None:
        self._lines.append("")

    def _strip_parens(self, s: str) -> str:
        """Strip outer parentheses from an expression string."""
        s = s.strip()
        if s.startswith("(") and s.endswith(")"):
            count = 1
            for i in range(1, len(s) - 1):
                if s[i] == "(":
                    count += 1
                elif s[i] == ")":
                    count -= 1
                    if count == 0:
                        return s
            return s[1:-1]
        return s

    def generate(self, module: IRModule) -> str:
        for i, func in enumerate(module.functions):
            if i > 0:
                self._emit_blank()
            self._gen_function(func)
        return "\n".join(self._lines) + "\n"

    def _gen_function(self, func: IRFunction) -> None:
        self._mutated_vars = _collect_mutated_vars(func.body)
        decls = _collect_decls(func.body)

        param_strs = []
        for p in func.params:
            mut = "mut " if p.name in func.mutated_params else ""
            param_strs.append(f"{mut}{p.name}: {_rust_type(p.type_)}")
        params = ", ".join(param_strs)

        is_main = func.name == "main"
        self._in_main = is_main
        if is_main:
            self._emit(f"fn {func.name}({params}) {{")
        else:
            ret = _rust_type(func.return_type)
            self._emit(f"fn {func.name}({params}) -> {ret} {{")

        self._indent += 1

        self._decl_types = dict(decls)
        self._loop_vars = _vars_declared_in_loop(func.body)

        for name, type_ in decls.items():
            if name == "_":
                continue
            if name in self._loop_vars:
                continue
            mut = "mut " if name in self._mutated_vars else ""
            default = self._default_value(type_)
            self._emit(f"let {mut}{_mangle(name)}: {_rust_type(type_)} = {default};")

        if any(name not in self._loop_vars for name in decls):
            self._emit_blank()

        self._at_top_level = True
        for stmt in func.body:
            self._gen_stmt(stmt)

        self._indent -= 1
        self._emit("}")

    def _default_value(self, ir_type) -> str:
        if isinstance(ir_type, IRIntType):
            return "0"
        if isinstance(ir_type, IRFloatType):
            return "0.0"
        if isinstance(ir_type, IRBoolType):
            return "false"
        if isinstance(ir_type, IRStrType):
            return "String::new()"
        if isinstance(ir_type, IRListType):
            return f"Vec::<{_rust_type(ir_type.element_type)}>::new()"
        if isinstance(ir_type, IRDictType):
            return f"HashMap::<{_rust_type(ir_type.key_type)}, {_rust_type(ir_type.value_type)}>::new()"
        return "0"

    def _gen_stmt(self, stmt) -> None:
        if isinstance(stmt, IRVarDecl):
            val = self._strip_parens(self._gen_expr(stmt.value, stmt.type_))
            if stmt.name in self._decl_types and stmt.name not in self._loop_vars:
                self._emit(f"{_mangle(stmt.name)} = {val};")
            elif stmt.name in self._mutated_vars:
                self._emit(f"let mut {_mangle(stmt.name)} = {val};")
            else:
                self._emit(f"let {_mangle(stmt.name)} = {val};")

        elif isinstance(stmt, IRAssign):
            target_type = self._decl_types.get(stmt.target)
            if isinstance(target_type, IRFloatType):
                val = self._strip_parens(self._gen_expr_as_float(stmt.value))
            else:
                val = self._strip_parens(self._gen_expr(stmt.value))
            self._emit(f"{_mangle(stmt.target)} = {val};")

        elif isinstance(stmt, IRAugAssign):
            val = self._strip_parens(self._gen_expr(stmt.value))
            self._emit(f"{_mangle(stmt.target)} {stmt.op} {val};")

        elif isinstance(stmt, IRIf):
            cond = self._strip_parens(self._gen_expr(stmt.condition))
            self._emit(f"if {cond} {{")
            self._indent += 1
            old_top_level = self._at_top_level
            self._at_top_level = False
            for s in stmt.then_body:
                self._gen_stmt(s)
            self._at_top_level = old_top_level
            self._indent -= 1
            for elif_cond, elif_body in stmt.elif_clauses:
                ec = self._strip_parens(self._gen_expr(elif_cond))
                self._emit(f"}} else if {ec} {{")
                self._indent += 1
                self._at_top_level = False
                for s in elif_body:
                    self._gen_stmt(s)
                self._at_top_level = old_top_level
                self._indent -= 1
            if stmt.else_body is not None:
                self._emit("} else {")
                self._indent += 1
                self._at_top_level = False
                for s in stmt.else_body:
                    self._gen_stmt(s)
                self._at_top_level = old_top_level
                self._indent -= 1
            self._emit("}")

        elif isinstance(stmt, IRWhile):
            cond = self._strip_parens(self._gen_expr(stmt.condition))
            label = getattr(stmt, "label", "") or f"__loop_{id(stmt)}"
            self._emit(f"'{label}: while {cond} {{")
            self._indent += 1
            old_top_level = self._at_top_level
            self._at_top_level = False
            for s in stmt.body:
                self._gen_stmt(s)
            self._at_top_level = old_top_level
            self._indent -= 1
            self._emit("}")

        elif isinstance(stmt, IRForRange):
            start = self._gen_expr(stmt.start)
            stop = self._gen_expr(stmt.stop)
            step = self._gen_expr(stmt.step) if stmt.step is not None else "1"
            label = getattr(stmt, "label", "") or f"__loop_{id(stmt)}"

            self._emit("{")
            self._indent += 1

            self._emit(f"let __stop = {stop};")
            self._emit(f"let __step = {step};")
            self._emit(f"{stmt.target} = {start};")

            self._emit(
                f"'{label}: while if (__step) > 0 {{ {stmt.target} < (__stop) }} else {{ {stmt.target} > (__stop) }} {{"
            )
            self._indent += 1
            old_top_level = self._at_top_level
            self._at_top_level = False
            for s in stmt.body:
                self._gen_stmt(s)
            self._at_top_level = old_top_level
            self._emit(f"{stmt.target} += __step;")
            self._indent -= 1
            self._emit("}")

            self._indent -= 1
            self._emit("}")

        elif isinstance(stmt, IRReturn):
            if self._in_main:
                self._emit("return;")
            elif stmt.value is not None:
                if isinstance(stmt.result_type, IRFloatType):
                    val = self._strip_parens(self._gen_expr_as_float(stmt.value))
                else:
                    val = self._strip_parens(self._gen_expr(stmt.value))
                self._emit(f"return {val};")

        elif isinstance(stmt, IRPrint):
            val = self._gen_expr(stmt.value)
            fmt = "{:?}" if isinstance(stmt.value_type, IRListType) else "{}"
            self._emit(f'println!("{fmt}", {val});')

        elif isinstance(stmt, IRBreak):
            label = stmt.label if hasattr(stmt, "label") and stmt.label else None
            if label:
                self._emit(f"break '{label};")
            else:
                self._emit("break;")

        elif isinstance(stmt, IRContinue):
            label = stmt.label if hasattr(stmt, "label") and stmt.label else None
            if label:
                self._emit(f"continue '{label};")
            else:
                self._emit("continue;")

        elif isinstance(stmt, IRDictDelete):
            target = self._gen_expr(stmt.target)
            key = self._gen_expr(stmt.key)
            self._emit(f"{target}.remove(&{key});")

        elif isinstance(stmt, IRSubscriptAssign):
            if isinstance(stmt.target, IRSubscript):
                target_val = self._gen_expr(stmt.target.value)
                idx_raw = self._gen_expr(stmt.index)
                value_val = self._gen_expr(stmt.value)

                # Handle dict assignment: d[key] = value -> d.insert(key, value)
                if isinstance(stmt.target.value_type, IRDictType):
                    self._emit(f"{target_val}.insert({idx_raw}, {value_val});")
                    if isinstance(stmt.target.value, IRName):
                        self._mutated_vars.add(stmt.target.value.name)
                    return

                if isinstance(stmt.target.value_type, IRStrType):
                    len_expr = f"{target_val}.chars().count() as i32"
                else:
                    len_expr = f"{target_val}.len() as i32"
                index_expr = f"(if {idx_raw} < 0 {{ {idx_raw} + {len_expr} }} else {{ {idx_raw} }}) as usize"

                if isinstance(stmt.value_type, IRStrType):
                    self._emit(
                        f"{target_val}.replace_range({index_expr}..={index_expr}, &{value_val});"
                    )
                else:
                    self._emit(f"{target_val}[{index_expr}] = {value_val};")
                if isinstance(stmt.target.value, IRName):
                    self._mutated_vars.add(stmt.target.value.name)
            else:
                target = self._gen_expr(stmt.target)
                index = self._gen_expr(stmt.index)
                value = self._gen_expr(stmt.value)
                # Check if target is a dict by looking up its declaration type
                target_type = (
                    self._decl_types.get(stmt.target.name)
                    if isinstance(stmt.target, IRName)
                    else None
                )
                if isinstance(target_type, IRDictType):
                    self._emit(f"{target}.insert({index}, {value});")
                else:
                    self._emit(f"{target}[{index}] = {value};")
                if isinstance(stmt.target, IRName):
                    self._mutated_vars.add(stmt.target.name)

        else:
            raise ValueError(f"Unsupported IR statement: {type(stmt).__name__}")

    def _gen_expr(self, expr, expected_type=None) -> str:
        if isinstance(expr, IRIntLit):
            return str(expr.value)
        elif isinstance(expr, IRFloatLit):
            v = expr.value
            s = repr(v)
            if "." not in s and "e" not in s.lower():
                s += ".0"
            return s
        elif isinstance(expr, IRBoolLit):
            return "true" if expr.value else "false"
        elif isinstance(expr, IRStrLit):
            escaped = (
                expr.value.replace("\\", "\\\\")
                .replace('"', '\\"')
                .replace("\n", "\\n")
            )
            return f'"{escaped}".to_string()'
        elif isinstance(expr, IRName):
            return expr.name
        elif isinstance(expr, IRBinOp):
            return f"({self._gen_binop(expr)})"
        elif isinstance(expr, IRUnaryOpExpr):
            operand = self._gen_expr(expr.operand)
            if expr.op == "not":
                return f"(!({operand}))"
            if expr.op == "-":
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
        elif isinstance(expr, IRDictLit):
            key_t = _rust_type(expr.key_type)
            val_t = _rust_type(expr.value_type)
            if not expr.pairs:
                return f"HashMap::<{key_t}, {val_t}>::new()"
            pairs = []
            for k, v in expr.pairs:
                key_str = self._gen_expr(k)
                val_str = self._gen_expr(v)
                pairs.append(f"({key_str}, {val_str})")
            return f"({{ let mut __d: HashMap<{key_t}, {val_t}> = HashMap::new(); {''.join(f'__d.insert({p}); ' for p in pairs)} __d }})"
        elif isinstance(expr, IRDictContains):
            key = self._gen_expr(expr.key)
            dict_val = self._gen_expr(expr.dict)
            return f"{dict_val}.contains_key(&{key})"
        elif isinstance(expr, IRSubscript):
            val = self._gen_expr(expr.value)
            idx = self._gen_expr(expr.index)

            # Handle dict subscript: d[key] -> __d.get(&key).unwrap().clone()
            if isinstance(expr.value_type, IRDictType):
                val_t = _rust_type(expr.value_type.value_type)
                return f"({val}.get(&{idx}).unwrap().clone())"

            # Robust Python indexing: bind collection to a temp reference to avoid redundant evaluations
            # and then calculate actual usize index relative to length if negative.

            if isinstance(expr.value_type, IRStrType):
                len_expr = "__coll.chars().count() as i32"
                inner_expr = f"__coll.chars().nth(actual_idx).unwrap().to_string()"
            else:
                len_expr = "__coll.len() as i32"
                inner_expr = f"__coll[actual_idx]"

            if isinstance(expr.result_type, (IRStrType, IRListType)) and not isinstance(
                expr.value_type, IRStrType
            ):
                inner_expr = f"({inner_expr}).clone()"

            # Use an immediately-invoked block to isolate the temporary collection reference
            return (
                f"({{ let __coll = &({val}); "
                f"let __idx_raw = {idx}; let actual_idx = if __idx_raw < 0 {{ (__idx_raw + ({len_expr}) as i32) as usize }} else {{ __idx_raw as usize }}; "
                f"{inner_expr} }})"
            )

        elif isinstance(expr, IRFunctionCall):
            if expr.name == "len":
                arg = self._gen_expr(expr.args[0])
                return f"{arg}.len() as i32"
            args = ", ".join(self._gen_expr(a) for a in expr.args)
            return f"{expr.name}({args})"
        return f"/* unknown expr {type(expr).__name__} */"

    def _gen_binop(self, expr) -> str:
        if expr.op == "/":
            left = self._gen_expr_as_float(expr.left)
            right = self._gen_expr_as_float(expr.right)
            return f"{left} / {right}"
        if expr.op == "//":
            left = self._gen_expr(expr.left)
            right = self._gen_expr(expr.right)
            return f"({left} as f64 / {right} as f64).floor() as i32"
        if expr.op == "+" and isinstance(expr.result_type, IRStrType):
            left = self._gen_expr(expr.left)
            right = self._gen_expr(expr.right)
            return f"{left}.to_string() + &{right}"
        if expr.op == "+" and isinstance(expr.result_type, IRListType):
            left = self._gen_expr(expr.left)
            right = self._gen_expr(expr.right)
            elem_type = _rust_type(expr.result_type.element_type)
            return f"({{ let mut __v: Vec<{elem_type}> = {left}.clone(); __v.extend({right}); __v }})"
        if expr.op == "*" and isinstance(expr.result_type, IRStrType):
            if isinstance(expr.left, IRStrLit):
                left_str = self._gen_expr(expr.left)
                right_n = self._gen_expr(expr.right)
                return f"{left_str}.to_string().repeat({right_n})"
            elif isinstance(expr.right, IRStrLit):
                left_n = self._gen_expr(expr.left)
                right_str = self._gen_expr(expr.right)
                return f"{right_str}.to_string().repeat({left_n})"
            else:
                left = self._gen_expr(expr.left)
                right = self._gen_expr(expr.right)
                return f"{left}.repeat({right})"

        if isinstance(expr.result_type, IRFloatType):
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
