from __future__ import annotations
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
    IRContains,
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
    IRForIter,
    IRTryExcept,
    IRRaise,
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
    IRTupleLit,
    IRTupleUnpack,
    IRClassDefinition,
)




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


def _get_var_name(expr) -> str | None:
    """Extract variable name from an expression."""
    if isinstance(expr, IRName):
        return expr.name
    if isinstance(expr, IRSelf):
        return "self"
    return None


def _collect_vars_from_expr(expr) -> set:
    """Collect all variable names used in an expression."""
    vars: set = set()
    if isinstance(expr, IRName):
        vars.add(expr.name)
    elif isinstance(expr, IRFileMethod):
        name = _get_var_name(expr.file)
        if name:
            vars.add(name)
    elif isinstance(expr, IRMethodCall):
        name = _get_var_name(expr.value)
        if name:
            vars.add(name)
    elif isinstance(expr, IRStructAccess):
        name = _get_var_name(expr.value)
        if name:
            vars.add(name)
    elif isinstance(expr, IRFileOpen):
        pass  # New variable, handled separately
    elif isinstance(expr, IRNew):
        pass  # New variable, handled separately
    # Recursively check nested expressions
    for attr in dir(expr):
        if attr.startswith("_"):
            continue
        try:
            val = getattr(expr, attr)
            if isinstance(val, (list, tuple)):
                for item in val:
                    if hasattr(item, "name") or isinstance(item, IRBinOp):
                        vars |= _collect_vars_from_expr(item)
            elif hasattr(val, "name") or isinstance(val, IRBinOp):
                vars |= _collect_vars_from_expr(val)
        except:
            pass
    return vars


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
            elif isinstance(stmt, IRName):
                mutated.add(stmt.target.name)
        elif isinstance(stmt, IRTupleUnpack):
            for t in stmt.targets:
                mutated.add(t)
        elif isinstance(stmt, IRFieldAssign):
            # If a field is assigned, self needs &mut
            mutated.add("self")
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
        elif isinstance(stmt, IRForIter):
            mutated.add(stmt.target)  # Loops always assign
            mutated |= _collect_mutated_vars(stmt.body)
        elif isinstance(stmt, IRVarDecl):
            # Check if the value is a method call that mutates self (e.g., file.write())
            vars_used = _collect_vars_from_expr(stmt.value)
            # All variables used in method calls need to be mutable
            mutated |= vars_used
    return mutated


def _collect_decls(stmts) -> tuple[dict[str, object], set[str]]:
    """Collect variable declarations for type tracking and pre-declaration."""
    decls: dict[str, object] = {}
    pre_declare: set[str] = set()

    def _recurse(body):
        for stmt in body:
            if isinstance(stmt, IRVarDecl):
                decls[stmt.name] = stmt.type_
            elif isinstance(stmt, IRForRange):
                decls[stmt.target] = IRIntType()
                pre_declare.add(stmt.target)
                _recurse(stmt.body)
            elif isinstance(stmt, IRForIter):
                # Target type depends on iterable
                target_type = IRIntType()  # Default
                it_t = stmt.iterable_type
                if isinstance(it_t, IRListType):
                    target_type = it_t.element_type
                elif isinstance(it_t, IRDictType):
                    target_type = it_t.key_type
                elif isinstance(it_t, IRStrType):
                    target_type = IRStrType()  # char in Rust is String-ish in our mapping for now

                decls[stmt.target] = target_type
                pre_declare.add(stmt.target)
                _recurse(stmt.body)
            elif isinstance(stmt, IRWhile):
                pre_declare.add("__dummy")  # Force pre-declaration block if needed
                _recurse(stmt.body)
            elif isinstance(stmt, IRIf):
                _recurse(stmt.then_body)
                for _, elif_body in stmt.elif_clauses:
                    _recurse(elif_body)
                if stmt.else_body:
                    _recurse(stmt.else_body)

    _recurse(stmts)
    return decls, pre_declare


def _vars_declared_in_loop(stmts) -> set:
    """Collect variable names that are declared inside while loops.

    Variables declared inside while loops are now pre-declared at function level
    with default values to match Python semantics where variables have function scope.
    This function is kept for compatibility but returns an empty set since we no longer
    exclude any variables from pre-declaration.
    """
    return set()  # All variables are pre-declared at function level now


class RustCodegen:
    def __init__(self):
        self._indent = 0
        self._lines: list = []
        self._mutated_vars: set = set()
        self._in_main: bool = False
        self._at_top_level: bool = True
        self._loop_vars: set = set()
        self._uses_hashmap = False
        self._uses_file_handle = False
        self._uses_py_error = False

    def _get_rust_type(self, t) -> str:
        if isinstance(t, IRIntType):
            return "i32"
        if isinstance(t, IRFloatType):
            return "f64"
        if isinstance(t, IRBoolType):
            return "bool"
        if isinstance(t, IRStrType):
            return "String"
        if isinstance(t, IRUnitType):
            return "()"
        if isinstance(t, IRListType):
            return f"Vec<{self._get_rust_type(t.element_type)}>"
        if isinstance(t, IRDictType):
            self._uses_hashmap = True
            return f"HashMap<{self._get_rust_type(t.key_type)}, {self._get_rust_type(t.value_type)}>"
        if isinstance(t, IRFileType):
            self._uses_file_handle = True
            return "FileHandle"
        if isinstance(t, IRClassType):
            return t.name
        raise ValueError(f"Unknown type {type(t).__name__}")

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

    def generate(self, ir_mod: IRModule) -> str:
        # Reset state
        self._lines = []
        self._uses_hashmap = False
        self._uses_file_handle = False
        self._uses_py_error = False

        # First pass: Generate classes and functions to detect feature usage
        # We store them in separate buffers
        class_lines = []
        for cls in ir_mod.classes:
            self._gen_class(cls)
            class_lines.extend(self._lines)
            self._lines = []
            class_lines.append("")

        func_lines = []
        for i, func in enumerate(ir_mod.functions):
            self._gen_function(func)
            func_lines.extend(self._lines)
            self._lines = []
            if i < len(ir_mod.functions) - 1:
                func_lines.append("")

        # Second pass: Emit header and boilerplate based on detected usage
        final_lines = ["// Generated by py2rust"]
        
        # Imports
        imports = []
        if self._uses_hashmap:
            imports.append("use std::collections::HashMap;")
        if self._uses_file_handle:
            imports.append("use std::fs::{File, OpenOptions};")
            imports.append("use std::io::{self, Read, Write, BufRead, BufReader, Seek, SeekFrom};")
        
        if imports:
            final_lines.extend(imports)
            final_lines.append("")

        # Helper Structures
        if self._uses_py_error:
            final_lines.append("#[derive(Debug, Clone)]")
            final_lines.append("pub enum PyError {")
            final_lines.append("    Exception(String),")
            final_lines.append("    ValueError(String),")
            final_lines.append("    TypeError(String),")
            final_lines.append("    KeyError(String),")
            final_lines.append("    IndexError(String),")
            final_lines.append("}")
            final_lines.append("")
            final_lines.append("impl std::fmt::Display for PyError {")
            final_lines.append("    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {")
            final_lines.append("        match self {")
            final_lines.append('            PyError::Exception(s) => write!(f, "Exception: {}", s),')
            final_lines.append('            PyError::ValueError(s) => write!(f, "ValueError: {}", s),')
            final_lines.append('            PyError::TypeError(s) => write!(f, "TypeError: {}", s),')
            final_lines.append('            PyError::KeyError(s) => write!(f, "KeyError: {}", s),')
            final_lines.append('            PyError::IndexError(s) => write!(f, "IndexError: {}", s),')
            final_lines.append("        }")
            final_lines.append("    }")
            final_lines.append("}")
            final_lines.append("")

        if self._uses_file_handle:
            final_lines.append("struct FileHandle {")
            final_lines.append("    file: File,")
            final_lines.append("}")
            final_lines.append("")
            final_lines.append("impl FileHandle {")
            final_lines.append("    fn open(path: &str, mode: &str) -> std::io::Result<Self> {")
            final_lines.append("        let file = match mode {")
            final_lines.append('            "r" => File::open(path)?,')
            final_lines.append('            "w" => File::create(path)?,')
            final_lines.append('            "a" => OpenOptions::new().append(true).open(path)?,')
            final_lines.append('            "rb" => File::open(path)?,')
            final_lines.append('            "wb" => File::create(path)?,')
            final_lines.append('            "ab" => OpenOptions::new().append(true).open(path)?,')
            final_lines.append("            _ => File::open(path)?,")
            final_lines.append("        };")
            final_lines.append("        Ok(FileHandle { file })")
            final_lines.append("    }")
            final_lines.append("")
            final_lines.append("    fn read(&mut self) -> std::io::Result<String> {")
            final_lines.append("        let mut contents = String::new();")
            final_lines.append("        self.file.read_to_string(&mut contents)?;")
            final_lines.append("        Ok(contents)")
            final_lines.append("    }")
            final_lines.append("")
            final_lines.append("    fn readline(&mut self) -> std::io::Result<String> {")
            final_lines.append("        let mut reader = BufReader::new(&self.file);")
            final_lines.append("        let mut line = String::new();")
            final_lines.append("        reader.read_line(&mut line)?;")
            final_lines.append("        Ok(line)")
            final_lines.append("    }")
            final_lines.append("")
            final_lines.append("    fn write(&mut self, content: &str) -> std::io::Result<()> {")
            final_lines.append("        self.file.write_all(content.as_bytes())")
            final_lines.append("    }")
            final_lines.append("")
            final_lines.append("    fn close(self) -> std::io::Result<()> {")
            final_lines.append("        Ok(())")
            final_lines.append("    }")
            final_lines.append("")
            final_lines.append("    fn tell(&mut self) -> std::io::Result<u64> {")
            final_lines.append("        self.file.stream_position()")
            final_lines.append("    }")
            final_lines.append("")
            final_lines.append("    fn seek(&mut self, pos: u64) -> std::io::Result<u64> {")
            final_lines.append("        self.file.seek(SeekFrom::Start(pos))")
            final_lines.append("    }")
            final_lines.append("}")
            final_lines.append("")

        final_lines.extend(class_lines)
        final_lines.extend(func_lines)

        return "\n".join(final_lines) + "\n"

    def _gen_class(self, cls: IRClassDefinition) -> None:
        self._emit(f"#[derive(Clone, Debug)]")
        self._emit(f"struct {cls.name} {{")
        self._indent += 1
        for field_name, field_type in cls.fields:
            self._emit(f"{_mangle(field_name)}: {self._get_rust_type(field_type)},")
        self._indent -= 1
        self._emit("}")
        self._emit("")
        self._emit(f"impl {cls.name} {{")
        self._indent += 1
        for method in cls.methods:
            self._gen_method(method)
        for ctor in cls.constructors:
            self._gen_method(ctor, is_init=True)
        self._indent -= 1
        self._emit("}")

    def _gen_method(self, func: IRFunction, is_init: bool = False) -> None:
        self._uses_py_error = True
        self._mutated_vars = _collect_mutated_vars(func.body)
        decls, pre_declare = _collect_decls(func.body)

        if is_init:
            param_strs = []
        elif "self" in self._mutated_vars:
            param_strs = ["&mut self"]
        else:
            param_strs = ["&self"]
        for p in func.params:
            mut = "mut " if p.name in func.mutated_params else ""
            param_strs.append(f"{mut}{_mangle(p.name)}: {self._get_rust_type(p.type_)}")
        params = ", ".join(param_strs)

        if is_init:
            self._emit(f"fn new({params}) -> Result<Self, String> {{")
        else:
            ret = self._get_rust_type(func.return_type)
            self._emit(f"fn {_mangle(func.name)}({params}) -> Result<{ret}, String> {{")

        self._indent += 1

        self._decl_types = dict(decls)
        # Note: We no longer exclude loop vars - all variables are pre-declared at function level

        for name, type_ in decls.items():
            if name == "_":
                continue
            mut = "mut " if name in self._mutated_vars else ""
            default = self._default_value(type_)
            self._emit(f"let {mut}{_mangle(name)}: {self._get_rust_type(type_)} = {default};")

        if decls:
            self._emit_blank()

        if is_init:
            self._gen_init_body(func)
        else:
            self._at_top_level = True
            for stmt in func.body:
                self._gen_stmt(stmt)

        self._indent -= 1
        self._emit("}")

    def _gen_init_body(self, func: IRFunction) -> None:
        field_values = {}
        other_stmts = []
        for stmt in func.body:
            if isinstance(stmt, IRFieldAssign):
                field_values[_mangle(stmt.field)] = self._strip_parens(
                    self._gen_expr(stmt.value)
                )
            else:
                other_stmts.append(stmt)
        for stmt in other_stmts:
            self._gen_stmt(stmt)
        
        # Build the struct
        fields = ", ".join(f"{f}: {v}" for f, v in field_values.items())
        self._emit(f"Ok(Self {{ {fields} }})")

    def _gen_function(self, func: IRFunction) -> None:
        self._uses_py_error = True
        self._mutated_vars = _collect_mutated_vars(func.body)
        decls, pre_declare = _collect_decls(func.body)

        param_strs = []
        for p in func.params:
            mut = "mut " if p.name in func.mutated_params else ""
            param_strs.append(f"{mut}{_mangle(p.name)}: {self._get_rust_type(p.type_)}")
        params = ", ".join(param_strs)

        is_main = func.name == "main"
        self._in_main = is_main
        ret = self._get_rust_type(func.return_type)
        self._emit(f"fn {func.name}({params}) -> Result<{ret}, PyError> {{")

        self._indent += 1

        self._decl_types = dict(decls)
        # We need to track which variables have been pre-declared to avoid double-declaring
        self._pre_declared = set()

        # Pre-declare only for/while loop targets
        for name in pre_declare:
            if name == "_":
                continue
            if name not in self._decl_types:
                continue
            type_ = self._decl_types[name]
            mut = "mut " if name in self._mutated_vars else ""
            # For now, keep default values for safety (Python dynamic initialization)
            default = self._default_value(type_)
            self._emit(f"let {mut}{_mangle(name)}: {self._get_rust_type(type_)} = {default};")
            self._pre_declared.add(name)

        if self._pre_declared:
            self._emit_blank()

        self._at_top_level = True
        for stmt in func.body:
            self._gen_stmt(stmt)

        if not func.body or not isinstance(func.body[-1], IRReturn):
            dv = self._default_value(func.return_type)
            self._emit(f"Ok({dv})")

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
            return f"Vec::<{self._get_rust_type(ir_type.element_type)}>::new()"
        if isinstance(ir_type, IRDictType):
            return f"HashMap::<{self._get_rust_type(ir_type.key_type)}, {self._get_rust_type(ir_type.value_type)}>::new()"
        if isinstance(ir_type, IRClassType):
            return f"{self._get_rust_type(ir_type)}::new()"
        if isinstance(ir_type, IRFileType):
            return 'FileHandle::open("", "r").unwrap()'
        return "0"

    def _gen_stmt(self, stmt) -> None:
        if isinstance(stmt, IRVarDecl):
            # Skip if variable was pre-declared at function level
            if stmt.name in self._pre_declared:
                # Still need to perform the assignment if there is one
                val = self._strip_parens(self._gen_expr(stmt.value, stmt.type_))
                self._emit(f"{_mangle(stmt.name)} = {val};")
                return
            val = self._strip_parens(self._gen_expr(stmt.value, stmt.type_))
            if stmt.name == "_":
                self._emit(f"{val};")
            elif stmt.name in self._mutated_vars:
                self._emit(
                    f"let mut {_mangle(stmt.name)}: {self._get_rust_type(stmt.type_)} = {val};"
                )
            else:
                self._emit(
                    f"let {_mangle(stmt.name)}: {self._get_rust_type(stmt.type_)} = {val};"
                )

        elif isinstance(stmt, IRAssign):
            target_type = self._decl_types.get(stmt.target)
            if isinstance(target_type, IRFloatType):
                val = self._strip_parens(self._gen_expr_as_float(stmt.value))
            else:
                val = self._strip_parens(self._gen_expr(stmt.value))
            self._emit(f"{_mangle(stmt.target)} = {val};")

        elif isinstance(stmt, IRFieldAssign):
            val = self._strip_parens(self._gen_expr(stmt.value))
            obj_name = "self" if stmt.obj == "self" else _mangle(stmt.obj)
            self._emit(f"{obj_name}.{_mangle(stmt.field)} = {val};")

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
            step_is_one = stmt.step is None

            # Use a unique internal loop variable to avoid shadowing outer scope
            loop_var = f"__i_{id(stmt)}"

            if step_is_one:
                # Wrap in a block so the inner loop variable doesn't leak
                self._emit("{")
                self._indent += 1
                # DO NOT redeclare the target here if it already exists in parent scope
                self._emit(f"for {loop_var} in {start}..{stop} {{")
                self._indent += 1
                self._emit(f"{_mangle(stmt.target)} = {loop_var};")
                old_top_level = self._at_top_level
                self._at_top_level = False
                for s in stmt.body:
                    self._gen_stmt(s)
                self._at_top_level = old_top_level
                self._indent -= 1
                self._emit("}")
                self._indent -= 1
                self._emit("}")
            else:
                step = self._gen_expr(stmt.step)
                label = getattr(stmt, "label", "") or f"__loop_{id(stmt)}"
                self._emit("{")
                self._indent += 1
                self._emit(f"let __stop = {stop};")
                self._emit(f"let __step = {step};")
                # Update target directly instead of redeclaring
                self._emit(f"{_mangle(stmt.target)} = {start};")
                self._emit(
                    f"'{label}: while if (__step) > 0 {{ {_mangle(stmt.target)} < (__stop) }} else {{ {_mangle(stmt.target)} > (__stop) }} {{"
                )
                self._indent += 1
                old_top_level = self._at_top_level
                self._at_top_level = False
                for s in stmt.body:
                    self._gen_stmt(s)
                self._at_top_level = old_top_level
                self._emit(f"{_mangle(stmt.target)} += __step;")
                self._indent -= 1
                self._emit("}")
                self._indent -= 1
                self._emit("}")

        elif isinstance(stmt, IRTupleUnpack):
            val = self._gen_expr(stmt.value)
            targets = ", ".join(_mangle(t) for t in stmt.targets)
            self._emit(f"let ({targets}) = {val};")

        elif isinstance(stmt, IRForIter):
            iterable = self._gen_expr(stmt.iterable)
            iter_expr = iterable
            if isinstance(stmt.iterable_type, IRDictType):
                iter_expr = f"{iterable}.keys()"
            elif isinstance(stmt.iterable_type, IRStrType):
                iter_expr = f"{iterable}.chars().map(|c| c.to_string())"
            else:
                # Assuming list
                iter_expr = f"&{iterable}"

            label = getattr(stmt, "label", "") or f"__loop_{id(stmt)}"
            self._emit("{")
            self._indent += 1
            # Use a unique internal loop variable
            loop_var = f"__val_{id(stmt)}"
            self._emit(f"'{label}: for {loop_var} in {iter_expr} {{")
            self._indent += 1
            # Assign to target (cloning to avoid ownership issues in this subset)
            self._emit(f"{_mangle(stmt.target)} = {loop_var}.clone();")

            old_top_level = self._at_top_level
            self._at_top_level = False
            for s in stmt.body:
                self._gen_stmt(s)
            self._at_top_level = old_top_level

            self._indent -= 1
            self._emit("}")
            self._indent -= 1
            self._emit("}")

        elif isinstance(stmt, IRReturn):
            if stmt.value is None:
                # Use default value for the expected return type
                dv = self._default_value(stmt.result_type)
                self._emit(f"return Ok({dv});")
            else:
                if isinstance(stmt.result_type, IRFloatType):
                    val = self._strip_parens(self._gen_expr_as_float(stmt.value))
                else:
                    val = self._gen_expr(stmt.value)
                self._emit(f"return Ok({val});")

        elif isinstance(stmt, IRTryExcept):
            self._uses_py_error = True
            self._emit("{")
            self._indent += 1
            self._emit("let __result = (|| -> Result<(), PyError> {")
            self._indent += 1
            for s in stmt.body:
                self._gen_stmt(s)
            self._emit("Ok(())")
            self._indent -= 1
            self._emit("})();")
            
            self._emit("if let Err(__exc) = __result {")
            self._indent += 1
            # Simple catch-all for now
            if stmt.handlers:
                h_type, h_name, h_body = stmt.handlers[0]
                if h_name:
                    self._emit(f"let {_mangle(h_name)} = __exc.clone();")
                for s in h_body:
                    self._gen_stmt(s)
            self._indent -= 1
            self._emit("}")
            self._indent -= 1
            self._emit("}")

        elif isinstance(stmt, IRRaise):
            self._uses_py_error = True
            if stmt.value:
                val = self._gen_expr(stmt.value)
                if "PyError::" in val:
                    self._emit(f"return Err({val});")
                else:
                    self._emit(f"return Err(PyError::Exception({val}));")
            else:
                self._emit('return Err(PyError::Exception("Exception raised".to_string()));')

        elif isinstance(stmt, IRPrint):
            val = self._gen_expr(stmt.value)
            fmt = (
                "{:?}"
                if isinstance(stmt.value_type, (IRListType, IRDictType))
                else "{}"
            )
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
                    # For string replacement, we need byte indices for replace_range
                    # Convert character index to byte index
                    adjusted_idx = f"(if {idx_raw} < 0 {{ {idx_raw} + {target_val}.chars().count() as i32 }} else {{ {idx_raw} }})"
                    byte_start = f"{target_val}.chars().take({adjusted_idx} as usize).map(|c| c.len_utf8()).sum::<usize>()"
                    byte_end = f"{target_val}.chars().take(({adjusted_idx} + 1) as usize).map(|c| c.len_utf8()).sum::<usize>()"
                    self._emit(
                        f"{target_val}.replace_range({byte_start}..{byte_end}, &{value_val});"
                    )
                else:
                    self._emit(f"{target_val}[{idx_raw}] = {value_val};")
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

        elif isinstance(stmt, IRExpr):
            expr = self._gen_expr(stmt)
            self._emit(f"{expr};")

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
        elif isinstance(expr, IRContains):
            item = self._gen_expr(expr.item)
            container = self._gen_expr(expr.container)
            if isinstance(expr.container_type, IRDictType):
                return f"{container}.contains_key(&{item})"
            else:
                return f"{container}.contains(&{item})"
        elif isinstance(expr, IRCompare):
            left = self._gen_expr(expr.left)
            right = self._gen_expr(expr.right)
            return f"({left} {expr.op} {right})"
        elif isinstance(expr, IRBoolOp):
            parts = [self._gen_expr(v) for v in expr.values]
            return f"({(f' {expr.op} ').join(parts)})"
        elif isinstance(expr, IRListLit):
            if not expr.elements:
                return f"Vec::<{self._get_rust_type(expr.element_type)}>::new()"
            elems = ", ".join(self._gen_expr(e) for e in expr.elements)
            return f"vec![{elems}]"
        elif isinstance(expr, IRDictLit):
            self._uses_hashmap = True
            key_t = self._get_rust_type(expr.key_type)
            val_t = self._get_rust_type(expr.value_type)
            if not expr.pairs:
                return f"HashMap::<{key_t}, {val_t}>::new()"
            pairs = ", ".join(f"({self._gen_expr(k)}, {self._gen_expr(v)})" for k, v in expr.pairs)
            return f"HashMap::from([{pairs}])"
        elif isinstance(expr, IRTupleLit):
            elems = ", ".join(self._gen_expr(e) for e in expr.elements)
            return f"({elems})"
        elif isinstance(expr, IRContains):
            val = self._gen_expr(expr.value)
            container = self._gen_expr(expr.container)
            if isinstance(expr.container_type, IRDictType):
                return f"{container}.contains_key(&{val})"
            return f"{container}.contains(&{val})"
        elif isinstance(expr, IRSubscript):
            val = self._gen_expr(expr.value)
            idx = self._gen_expr(expr.index)

            # Handle dict subscript: d[key] -> __d.get(&key).unwrap().clone()
            if isinstance(expr.value_type, IRDictType):
                val_t = self._get_rust_type(expr.value_type.value_type)
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
            
            if expr.name in ("Exception", "ValueError", "TypeError", "KeyError", "IndexError"):
                # Exception constructor call
                arg_str = self._gen_expr(expr.args[0]) if expr.args else '""'.to_string()
                return f"PyError::{expr.name}({arg_str})"

            args = ", ".join(self._gen_expr(a) for a in expr.args)
            res = f"{_mangle(expr.name)}({args})"
            if expr.is_fallible:
                res = f"{res}?"
            return res
        elif isinstance(expr, IRFileOpen):
            path = self._gen_expr(expr.path)
            mode = self._gen_expr(expr.mode) if expr.mode else '"r"'
            return f"FileHandle::open({path}, {mode})"
        elif isinstance(expr, IRFileMethod):
            file_val = self._gen_expr(expr.file)
            args = ", ".join(self._gen_expr(a) for a in expr.args)
            method = expr.method
            if method in ("read", "readline", "readlines"):
                return f"{file_val}.{method}()"
            if method == "write":
                return f"{file_val}.write({args})"
            if method == "close":
                return f"{file_val}.close()"
            if method == "tell":
                return f"{file_val}.tell()"
            if method == "seek":
                return f"{file_val}.seek({args})"
            return f"{file_val}.{method}()"
        elif isinstance(expr, IRSelf):
            return "self"
        elif isinstance(expr, IRStructAccess):
            if isinstance(expr.value, IRSelf):
                return f"self.{_mangle(expr.field)}"
            val = self._gen_expr(expr.value)
            return f"{val}.{_mangle(expr.field)}"
        elif isinstance(expr, IRMethodCall):
            val = self._gen_expr(expr.value)
            args = ", ".join(self._gen_expr(a) for a in expr.args)
            return f"{val}.{_mangle(expr.method)}({args})?"
        elif isinstance(expr, IRNew):
            args = ", ".join(self._gen_expr(a) for a in expr.args)
            return f"{expr.class_name}::new({args})"
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
            elem_type = self._get_rust_type(expr.result_type.element_type)
            return f"({{ let mut __v: Vec<{elem_type}> = {left}.clone(); __v.extend({right}.clone()); __v }})"
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
