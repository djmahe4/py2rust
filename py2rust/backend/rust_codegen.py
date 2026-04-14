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
    IRTupleType,
    IRFileType,
    IRSetType,
    IRFunctionType,
    IRClassType,
    IRIntLit,
    IRFloatLit,
    IRBoolLit,
    IRStrLit,
    IRTupleLit,
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
    IRTraitDefinition,
    IRTraitMethod,
    IRAwait,
    IREnumType,
    IREnumDef,
    IRMatchStmt,
    IRMatchCase,
    IRMatchPattern,
    IRValuePattern,
    IRNamePattern,
    IRClassPattern,
    IRWildcardPattern,
    IROrPattern,
    IRAsPattern,
    IRLambda,
    IRComprehension,
    IRListComp,
    IRDictComp,
    IRSetComp,
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
    assigned_vars: dict[str, int] = {}
    
    # Track variables declared in nested scopes that are used outside
    # (these will be pre-declared and thus need 'mut')
    _, pre_declare = _collect_decls(stmts)
    for p in pre_declare:
        mutated.add(p)

    def _visit(body, in_loop=False):
        for stmt in body:
            if isinstance(stmt, IRAssign):
                mutated.add(stmt.target)
                assigned_vars[stmt.target] = assigned_vars.get(stmt.target, 0) + 1
            elif isinstance(stmt, IRAugAssign):
                mutated.add(stmt.target)
                assigned_vars[stmt.target] = assigned_vars.get(stmt.target, 0) + 1
            elif isinstance(stmt, IRSubscriptAssign):
                name = _get_var_name(stmt.target)
                if name:
                    mutated.add(name)
            elif isinstance(stmt, IRDictDelete):
                name = _get_var_name(stmt.target)
                if name:
                    mutated.add(name)
            elif isinstance(stmt, IRTupleUnpack):
                for t in stmt.targets:
                    mutated.add(t)
                    assigned_vars[t] = assigned_vars.get(t, 0) + 1
            elif isinstance(stmt, IRFieldAssign):
                mutated.add("self")
            elif isinstance(stmt, IRVarDecl):
                assigned_vars[stmt.name] = assigned_vars.get(stmt.name, 0) + 1
                if assigned_vars[stmt.name] > 1 or in_loop:
                    mutated.add(stmt.name)
                
                # Check for mutating method calls
                if isinstance(stmt.value, IRMethodCall):
                    if stmt.value.mutates_self and isinstance(stmt.value.value, IRName):
                        mutated.add(stmt.value.value.name)
                elif isinstance(stmt.value, IRFileMethod):
                    if isinstance(stmt.value.file, IRName):
                        mutated.add(stmt.value.file.name)
            elif isinstance(stmt, IRForRange):
                mutated.add(stmt.target)
                assigned_vars[stmt.target] = assigned_vars.get(stmt.target, 0) + 1
                _visit(stmt.body, True)
            elif isinstance(stmt, IRForIter):
                mutated.add(stmt.target)
                assigned_vars[stmt.target] = assigned_vars.get(stmt.target, 0) + 1
                _visit(stmt.body, True)
            elif isinstance(stmt, IRWhile):
                _visit(stmt.body, True)
            elif isinstance(stmt, IRIf):
                _visit(stmt.then_body, in_loop)
                for _, elif_body in stmt.elif_clauses:
                    _visit(elif_body, in_loop)
                if stmt.else_body:
                    _visit(stmt.else_body, in_loop)
            elif isinstance(stmt, IRTryExcept):
                _visit(stmt.body, in_loop)
                for h_type, h_name, h_body in stmt.handlers:
                    if h_name:
                        mutated.add(h_name)
                    _visit(h_body, in_loop)

    _visit(stmts)
    return mutated


def _collect_decls(stmts) -> tuple[dict[str, object], set[str]]:
    """Collect variable declarations for type tracking and pre-declaration."""
    decls: dict[str, object] = {}
    pre_declare: set[str] = set()

    def _recurse(body, depth=0):
        for stmt in body:
            if isinstance(stmt, IRVarDecl):
                decls[stmt.name] = stmt.type_
                if depth > 0:
                    pre_declare.add(stmt.name)
            elif isinstance(stmt, IRForRange):
                decls[stmt.target] = IRIntType()
                pre_declare.add(stmt.target)
                _recurse(stmt.body, depth + 1)
            elif isinstance(stmt, IRForIter):
                # Target type depends on iterable
                target_type = IRIntType()  # Default
                it_t = stmt.iterable_type
                if isinstance(it_t, IRListType):
                    target_type = it_t.element_type
                elif isinstance(it_t, IRDictType):
                    target_type = it_t.key_type
                elif isinstance(it_t, IRStrType):
                    target_type = IRStrType()
                
                decls[stmt.target] = target_type
                pre_declare.add(stmt.target)
                _recurse(stmt.body, depth + 1)
            elif isinstance(stmt, IRWhile):
                _recurse(stmt.body, depth + 1)
            elif isinstance(stmt, IRIf):
                _recurse(stmt.then_body, depth + 1)
                for _, elif_body in stmt.elif_clauses:
                    _recurse(elif_body, depth + 1)
                if stmt.else_body:
                    _recurse(stmt.else_body, depth + 1)

    _recurse(stmts, depth=0)
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
        self._uses_async = False
        self._inside_try = 0
        self._loop_depth = 0
        self._current_fn_return_type = "()"
        self._uses_try_result = False

    def _get_rust_type(self, t) -> str:
        if t is None:
            return "()"
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
        if isinstance(t, IRTupleType):
            types = ", ".join(self._get_rust_type(et) for et in t.element_types)
            return f"({types})"
        if isinstance(t, IRSetType):
            self._uses_hashset = True
            return f"HashSet<{self._get_rust_type(t.element_type)}>"
        if isinstance(t, IRFunctionType):
            return "_"  # Let Rust infer closure types
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
        self._current_module = ir_mod
        self._lines = []
        self._uses_hashmap = False
        self._uses_hashset = False
        self._uses_file_handle = False
        self._uses_py_error = False
        self._uses_async = False

        # Pre-pass: Generate Traits
        trait_lines = []
        for trait in ir_mod.traits:
            trait_lines.append(self._gen_trait(trait))
            trait_lines.append("")

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

        # Generate Enums
        enum_lines = []
        for enum_def in ir_mod.enums:
            self._gen_enum(enum_def)
            enum_lines.extend(self._lines)
            self._lines = []
            enum_lines.append("")

        # Second pass: Emit header and boilerplate based on detected usage
        final_lines = ["// Generated by py2rust"]
        
        # Imports
        imports = []
        if self._uses_hashmap:
            imports.append("use std::collections::HashMap;")
        if self._uses_hashset:
            imports.append("use std::collections::HashSet;")
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
            final_lines.append("    IOError(String),")
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
            final_lines.append('            PyError::IOError(s) => write!(f, "IOError: {}", s),')
            final_lines.append("        }")
            final_lines.append("    }")
            final_lines.append("}")
            final_lines.append("")
            final_lines.append("impl From<std::io::Error> for PyError {")
            final_lines.append("    fn from(err: std::io::Error) -> Self {")
            final_lines.append("        PyError::IOError(err.to_string())")
            final_lines.append("    }")
            final_lines.append("}")
            final_lines.append("")
            final_lines.append("impl From<std::num::ParseIntError> for PyError {")
            final_lines.append("    fn from(err: std::num::ParseIntError) -> Self {")
            final_lines.append("        PyError::ValueError(err.to_string())")
            final_lines.append("    }")
            final_lines.append("}")
            final_lines.append("")
            final_lines.append("impl From<std::num::ParseFloatError> for PyError {")
            final_lines.append("    fn from(err: std::num::ParseFloatError) -> Self {")
            final_lines.append("        PyError::ValueError(err.to_string())")
            final_lines.append("    }")
            final_lines.append("}")
            final_lines.append("")

        if self._uses_try_result:
            final_lines.append("pub enum TryResult<T> {")
            final_lines.append("    Normal,")
            final_lines.append("    Return(T),")
            final_lines.append("    Break,")
            final_lines.append("    Continue,")
            final_lines.append("}")
            final_lines.append("")

        if self._uses_file_handle:
            final_lines.append("struct FileHandle {")
            final_lines.append("    file: File,")
            final_lines.append("}")
            final_lines.append("")

        # Traits
        if self._uses_async:
            self._emit_async_runtime()
            final_lines.extend(self._lines)
            self._lines = []
            final_lines.append("")

        final_lines.extend(trait_lines)

        if self._uses_file_handle:
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
        final_lines.extend(enum_lines)
        final_lines.extend(func_lines)

        return "\n".join(final_lines) + "\n"

    def _gen_trait(self, trait: IRTraitDefinition) -> str:
        bases_str = " + ".join(trait.bases) if trait.bases else ""
        header = f"pub trait {trait.name}"
        if bases_str:
            header += f": {bases_str}"
        
        res = [f"{header} {{"]
        for method in trait.methods:
            params_str = ", ".join(
                f"{p.name}: {self._get_rust_type(p.type_)}" for p in method.params
            )
            self_ref = "&mut self" if method.mutates_self else "&self"
            if method.is_async:
                self._uses_async = True
            async_kw = "async " if method.is_async else ""
            sig = f"    {async_kw}fn {method.name}({self_ref}"
            if params_str:
                sig += f", {params_str}"
            # Traits always return Result<T, PyError> for Python-to-Rust mapping
            ret = self._get_rust_type(method.return_type)
            sig += f") -> Result<{ret}, PyError>;"
            res.append(sig)
        res.append("}")
        return "\n".join(res)

    def _gen_class(self, cls: IRClassDefinition) -> None:
        self._emit(f"#[derive(Clone, Debug)]")
        self._emit(f"struct {cls.name} {{")
        self._indent += 1
        for field_name, field_type in cls.fields:
            self._emit(f"{_mangle(field_name)}: {self._get_rust_type(field_type)},")
        self._indent -= 1
        self._emit("}")
        self._emit("")

        # Inherent Impl (Constructors)
        if cls.constructors:
            self._emit(f"impl {cls.name} {{")
            self._indent += 1
            for ctor in cls.constructors:
                self._gen_method(ctor, is_init=True)
            self._indent -= 1
            self._emit("}")
            self._emit("")

        # Trait Impls (Implement all traits in the hierarchy)
        # 1. Map trait names to their definitions for easy lookup
        all_trait_defs = {t.name: t for t in self._current_module.traits}
        
        # 2. Get all traits this class must implement (recursively)
        traits_to_impl = []
        queue = [f"{cls.name}Trait"]
        visited = set()
        while queue:
            t_name = queue.pop(0)
            if t_name in visited: continue
            visited.add(t_name)
            if t_name in all_trait_defs:
                traits_to_impl.append(all_trait_defs[t_name])
                queue.extend(all_trait_defs[t_name].bases)
        
        # 3. For each trait, find implementing methods in the class
        # Map method names in this class for easy lookup
        class_methods = {m.name: m for m in cls.methods}
        
        for trait in traits_to_impl:
            self._emit(f"impl {trait.name} for {cls.name} {{")
            self._indent += 1
            for tm in trait.methods:
                if tm.name in class_methods:
                    self._gen_method(class_methods[tm.name])
            self._indent -= 1
            self._emit("}")
            self._emit("")

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
            self._emit(f"fn new({params}) -> Result<Self, PyError> {{")
        else:
            ret = self._get_rust_type(func.return_type)
            if func.is_async:
                self._uses_async = True
            async_kw = "async " if func.is_async else ""
            self._emit(f"{async_kw}fn {_mangle(func.name)}({params}) -> Result<{ret}, PyError> {{")

        self._indent += 1

        self._decl_types = dict(decls)
        # We need to track which variables have been pre-declared to avoid double-declaring
        self._pre_declared = set()

        # Pre-declare only variables that need it (nested definitions)
        for name in pre_declare:
            if name == "_":
                continue
            if name not in self._decl_types:
                continue
            type_ = self._decl_types[name]
            mut = "mut " if name in self._mutated_vars else ""
            default = self._default_value(type_)
            self._emit(f"let {mut}{_mangle(name)}: {self._get_rust_type(type_)} = {default};")
            self._pre_declared.add(name)

        if self._pre_declared:
            self._emit_blank()

        if is_init:
            self._gen_init_body(func)
        else:
            self._at_top_level = True
            for stmt in func.body:
                self._gen_stmt(stmt)
            
            if not func.body or not isinstance(func.body[-1], IRReturn):
                dv = self._default_value(func.return_type)
                self._emit(f"Ok({dv})")

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
        if is_main:
            ret_type_str = "()"
            self._current_fn_return_type = ret_type_str
            if func.is_async:
                self._uses_async = True
                self._emit(f"fn {func.name}({params}) -> Result<{ret_type_str}, PyError> {{")
                self._indent += 1
                self._emit("py_async::block_on(async {")
            else:
                self._emit(f"fn {func.name}({params}) -> Result<{ret_type_str}, PyError> {{")
        else:
            ret_type_str = self._get_rust_type(func.return_type)
            self._current_fn_return_type = ret_type_str
            if func.is_async:
                self._uses_async = True
            async_kw = "async " if func.is_async else ""
            self._emit(f"{async_kw}fn {func.name}({params}) -> Result<{ret_type_str}, PyError> {{")

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
            if self._in_main:
                self._emit("Ok(())")
            else:
                dv = self._default_value(func.return_type)
                self._emit(f"Ok({dv})")

        if is_main and func.is_async:
            self._indent -= 1
            self._emit("})")

        self._indent -= 1
        self._emit("}")

    def _default_value(self, ir_type) -> str:
        if isinstance(ir_type, IRUnitType):
            return "()"
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
                val = self._gen_expr(stmt.value, stmt.type_)
                self._emit(f"{_mangle(stmt.name)} = {val};")
                return
            val = self._gen_expr(stmt.value, stmt.type_)
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
                val = self._gen_expr_as_float(stmt.value)
            else:
                val = self._gen_expr(stmt.value)
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
            self._loop_depth += 1
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
            self._loop_depth -= 1

        elif isinstance(stmt, IRForRange):
            start = self._gen_expr(stmt.start)
            stop = self._gen_expr(stmt.stop)
            step_is_one = stmt.step is None

            # Use a unique internal loop variable to avoid shadowing outer scope
            loop_var = f"__i_{id(stmt)}"

            if step_is_one:
                # Wrap in a block so the inner loop variable doesn't leak
                self._emit("{")
                self._loop_depth += 1
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
                self._loop_depth -= 1
                self._indent -= 1
                self._emit("}")
            else:
                step = self._gen_expr(stmt.step)
                label = getattr(stmt, "label", "") or f"__loop_{id(stmt)}"
                self._emit("{")
                self._loop_depth += 1
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
                self._loop_depth -= 1
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
            self._loop_depth += 1
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
            self._loop_depth -= 1
            self._indent -= 1
            self._emit("}")

        elif isinstance(stmt, IRReturn):
            val_str = ""
            if self._in_main:
                if stmt.value is not None:
                    val = self._gen_expr(stmt.value)
                    val_str = f"{{ {val}; () }}"
                else:
                    val_str = "()"
            elif stmt.value is None:
                val_str = self._default_value(stmt.result_type)
            else:
                if isinstance(stmt.result_type, IRFloatType):
                    val_str = self._gen_expr_as_float(stmt.value)
                else:
                    val_str = self._gen_expr(stmt.value)
            
            if self._inside_try > 0:
                self._emit(f"return Ok(TryResult::Return({val_str}));")
            else:
                self._emit(f"return Ok({val_str});")

        elif isinstance(stmt, IRTryExcept):
            self._uses_py_error = True
            self._uses_try_result = True
            self._emit("{")
            self._indent += 1
            self._emit(f"let __result = (|| -> Result<TryResult<{self._current_fn_return_type}>, PyError> {{")
            self._inside_try += 1
            self._indent += 1
            for s in stmt.body:
                self._gen_stmt(s)
            self._emit("Ok(TryResult::Normal)")
            self._indent -= 1
            self._inside_try -= 1
            self._emit("})();")
            
            self._emit("match __result {")
            self._indent += 1
            self._emit("Ok(TryResult::Return(v)) => return Ok(v),")
            if self._loop_depth > 0:
                self._emit("Ok(TryResult::Break) => break,")
                self._emit("Ok(TryResult::Continue) => continue,")
            else:
                self._emit('Ok(TryResult::Break) => panic!("break outside loop"),')
                self._emit('Ok(TryResult::Continue) => panic!("continue outside loop"),')
            self._emit("Ok(TryResult::Normal) => {}")
            
            # Catch-all for now
            if stmt.handlers:
                h_type, h_name, h_body = stmt.handlers[0]
                binder = _mangle(h_name) if h_name else "_"
                self._emit(f"Err({binder}) => {{")
                self._indent += 1
                if h_name:
                    self._emit(f"let {binder} = {binder}.clone();")
                for s in h_body:
                    self._gen_stmt(s)
                self._indent -= 1
                self._emit("}")
            else:
                self._emit("Err(e) => return Err(e),")
                
            self._indent -= 1
            self._emit("}")
            self._indent -= 1
            self._emit("}")

        elif isinstance(stmt, IRRaise):
            self._uses_py_error = True
            if stmt.value:
                val = self._gen_expr(stmt.value)
                if getattr(stmt, "cause", None):
                    cause_val = self._gen_expr(stmt.cause)
                    if "PyError::" in val:
                        self._emit(f"return Err({val}); /* warning: cause lost */")
                    else:
                        self._emit(f'return Err(PyError::Exception(format!("{{}} (caused by {{}})", {val}, {cause_val})));')
                else:
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
            if self._inside_try > 0:
                self._emit("return Ok(TryResult::Break);")
            else:
                if label:
                    self._emit(f"break '{label};")
                else:
                    self._emit("break;")

        elif isinstance(stmt, IRContinue):
            label = stmt.label if hasattr(stmt, "label") and stmt.label else None
            if self._inside_try > 0:
                self._emit("return Ok(TryResult::Continue);")
            else:
                if label:
                    self._emit(f"continue '{label};")
                else:
                    self._emit("continue;")

        elif isinstance(stmt, IRDictDelete):
            target = self._gen_expr(stmt.target)
            key = self._gen_expr(stmt.key)
            self._emit(f"{target}.remove(&{key});")

        elif isinstance(stmt, IRSubscriptAssign):
            final_idx = self._strip_parens(self._gen_expr(stmt.index))
            value_val = self._gen_expr(stmt.value)
            
            # Recursive target generation for deep updates
            def get_mut_target(node):
                if isinstance(node, IRName):
                    self._mutated_vars.add(node.name)
                    return _mangle(node.name)
                if isinstance(node, IRSubscript):
                    inner = get_mut_target(node.value)
                    idx = self._strip_parens(self._gen_expr(node.index))
                    if isinstance(node.value_type, IRDictType):
                        return f"({inner}.get_mut(&{idx}).unwrap())"
                    return f"(&mut {inner}[{idx} as usize])"
                return self._gen_expr(node)

            target_expr = get_mut_target(stmt.target)
            
            # Check the type of the IMMEDIATE container being updated
            container_type = stmt.value_type # This is set in IRBuilder to the container's element/value type?
            # Wait, IRSubscriptAssign.value_type is the type of the VALUE being assigned?
            # No, let's check IR node definition.

            # Actually, we can check the target's type if it's a subscript
            target_is_dict = False
            if isinstance(stmt.target, IRSubscript):
                # If target is d[k], and we assign d[k][final_idx] = v, 
                # then target_expr refers to d[k] (mutably).
                # We need to know if d[k] is a dict.
                if isinstance(stmt.value_type, IRDictType):
                     # This is confusing. Let's use a simpler check.
                     pass

            # Fallback: if we are assigning to a dict, use .insert()
            # We can use the type info from the IR builder if available.
            # For now, let's check if the target expr "looks like" a call that returns a dict.
            # Better: IRSubscriptAssign should carry information about whether the target is a dict.
            
            # Re-evaluating: let's use the same logic as existing shallow assignment but recursive
            if isinstance(stmt.target, IRSubscript):
                # Target is d[k], so we are doing d[k][final_idx] = value
                # get_mut_target(stmt.target) returns "d.get_mut(&k).unwrap()"
                # We need to know if d[k] is a dict to use .insert()
                # IRSubscript has result_type.
                if isinstance(stmt.target.result_type, IRDictType):
                    self._emit(f"{target_expr}.insert({final_idx}, {value_val});")
                elif isinstance(stmt.target.result_type, IRStrType):
                    adjusted_idx = f"(if {final_idx} < 0 {{ {final_idx} + {target_expr}.chars().count() as i32 }} else {{ {final_idx} }})"
                    byte_start = f"{target_expr}.chars().take({adjusted_idx} as usize).map(|c| c.len_utf8()).sum::<usize>()"
                    byte_end = f"{target_expr}.chars().take(({adjusted_idx} + 1) as usize).map(|c| c.len_utf8()).sum::<usize>()"
                    self._emit(f"{target_expr}.replace_range({byte_start}..{byte_end}, &{value_val});")
                else:
                    self._emit(f"{target_expr}[{final_idx} as usize] = {value_val};")
            else:
                # Shallow assignment: d[final_idx] = value
                target_name = _mangle(stmt.target.name)
                self._mutated_vars.add(stmt.target.name)
                target_type = self._decl_types.get(stmt.target.name)
                if isinstance(target_type, IRDictType):
                    self._emit(f"{target_name}.insert({final_idx}, {value_val});")
                else:
                    self._emit(f"{target_name}[{final_idx} as usize] = {value_val};")

        elif isinstance(stmt, IRMatchStmt):
            self._gen_match_stmt(stmt)

        elif isinstance(stmt, IREnumDef):
            # Already handled in top-level generation
            pass

        elif isinstance(stmt, IRExpr):
            expr = self._gen_expr(stmt)
            self._emit(f"{expr};")

        else:
            raise ValueError(f"Unsupported IR statement: {type(stmt).__name__}")

    def _gen_enum(self, enum_def: IREnumDef):
        self._emit("#[derive(Debug, Clone, PartialEq)]")
        self._emit(f"pub enum {enum_def.name} {{")
        self._indent += 1
        for name, _ in enum_def.variants:
            self._emit(f"{name},")
        self._indent -= 1
        self._emit("}")
        self._emit("")

    def _gen_match_stmt(self, match_stmt: IRMatchStmt):
        subject = self._gen_expr(match_stmt.subject)
        self._emit(f"match {subject} {{")
        self._indent += 1
        has_catch_all = False
        for case in match_stmt.cases:
            pattern = self._gen_match_pattern(case.pattern)
            # Check if this case is a catch-all (no guard and wildcard/name pattern)
            if not case.guard and isinstance(
                case.pattern, (IRWildcardPattern, IRNamePattern)
            ):
                has_catch_all = True

            guard = f" if {self._gen_expr(case.guard)}" if case.guard else ""
            self._emit(f"{pattern}{guard} => {{")
            self._indent += 1
            for stmt in case.body:
                self._gen_stmt(stmt)
            self._indent -= 1
            self._emit("},")

        # Ensure exhaustiveness if no catch-all was found
        if not has_catch_all:
            self._emit("_ => {},")

        self._indent -= 1
        self._emit("}")

    def _gen_match_pattern(self, pattern: IRMatchPattern) -> str:
        if isinstance(pattern, IRValuePattern):
            return self._gen_expr(pattern.value)
        elif isinstance(pattern, IRNamePattern):
            return _mangle(pattern.name)
        elif isinstance(pattern, IRWildcardPattern):
            return "_"
        elif isinstance(pattern, IROrPattern):
            return " | ".join(self._gen_match_pattern(p) for p in pattern.patterns)
        elif isinstance(pattern, IRAsPattern):
            inner = self._gen_match_pattern(pattern.pattern)
            return f"{inner} @ {_mangle(pattern.name)}"
        elif isinstance(pattern, IRClassPattern):
            # For ADTs (Enums), it's variant name
            return f"{pattern.class_name}"
        return "_"

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
            return f"{left} {expr.op} {right}"
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
            self._uses_file_handle = True  # Ensure this is set
            path = self._gen_expr(expr.path)
            mode = self._gen_expr(expr.mode) if expr.mode else '"r".to_string()'
            return f"FileHandle::open(&{path}, &{mode})?"
        elif isinstance(expr, IRFileMethod):
            file_val = self._gen_expr(expr.file)
            args = ", ".join(f"&{self._gen_expr(a)}" for a in expr.args)
            method = expr.method
            if method in ("read", "readline", "readlines"):
                return f"{file_val}.{method}()?"
            if method == "write":
                return f"{file_val}.write({args})?"
            if method == "close":
                return f"{file_val}.close()?"
            if method == "tell":
                return f"{file_val}.tell()?"
            if method == "seek":
                return f"{file_val}.seek({args})?"
            return f"{file_val}.{method}()?"
        elif isinstance(expr, IRSelf):
            return "self"
        elif isinstance(expr, IRStructAccess):
            if isinstance(expr.value, IRSelf):
                return f"self.{_mangle(expr.field)}"
            val = self._gen_expr(expr.value)
            # Use :: for static enum variant access
            if isinstance(expr.result_type, IREnumType):
                return f"{val}::{_mangle(expr.field)}"
            return f"{val}.{_mangle(expr.field)}"
        elif isinstance(expr, IRMethodCall):
            val = self._gen_expr(expr.value)
            args = ", ".join(self._gen_expr(a) for a in expr.args)
            res = f"{val}.{_mangle(expr.method)}({args})"
            if getattr(expr, "is_fallible", True):
                res += "?"
            return res
        elif isinstance(expr, IRNew):
            args = ", ".join(self._gen_expr(a) for a in expr.args)
            return f"{expr.class_name}::new({args})?"
        elif isinstance(expr, IRAwait):
            self._uses_async = True
            val = self._gen_expr(expr.value)
            # If the inner expression was fallible (had a '?'), we need to await then '?' 
            # e.g. func().await?
            if val.endswith("?"):
                return f"{val[:-1]}.await?"
            return f"{val}.await"

        elif isinstance(expr, IRLambda):
            return self._gen_lambda(expr)

        elif isinstance(expr, IRListComp):
            return self._gen_list_comp(expr)

        elif isinstance(expr, IRDictComp):
            return self._gen_dict_comp(expr)

        elif isinstance(expr, IRSetComp):
            return self._gen_set_comp(expr)

        return f"/* unknown expr {type(expr).__name__} */"

    def _gen_lambda(self, expr: IRLambda) -> str:
        params = ", ".join(f"{p.name}" for p in expr.params)
        body = self._gen_expr(expr.body)
        return f"|{params}| {{ {body} }}"

    def _gen_list_comp(self, node: IRListComp) -> str:
        elem_t = self._get_rust_type(node.result_type.element_type)
        inner = f"let mut __res = Vec::<{elem_t}>::new(); "
        
        # Build nested loops for generators
        loop_code = ""
        close_braces = ""
        for gen in node.generators:
            target = self._gen_comp_target(gen.target)
            iterable = self._gen_expr(gen.iterable)
            loop_code += f"for &{target} in &{iterable} {{ "
            for if_expr in gen.ifs:
                cond = self._gen_expr(if_expr)
                loop_code += f"if {cond} {{ "
                close_braces += " } "
            close_braces += " } "
        
        elt = self._gen_expr(node.elt)
        push_code = f"__res.push({elt}); "
        
        return f"({{ {inner}{loop_code}{push_code}{close_braces} __res }})"

    def _gen_dict_comp(self, node: IRDictComp) -> str:
        self._uses_hashmap = True
        key_t = self._get_rust_type(node.result_type.key_type)
        val_t = self._get_rust_type(node.result_type.value_type)
        inner = f"let mut __res = HashMap::<{key_t}, {val_t}>::new(); "
        
        loop_code = ""
        close_braces = ""
        for gen in node.generators:
            target = self._gen_comp_target(gen.target)
            iterable = self._gen_expr(gen.iterable)
            loop_code += f"for &{target} in &{iterable} {{ "
            for if_expr in gen.ifs:
                cond = self._gen_expr(if_expr)
                loop_code += f"if {cond} {{ "
                close_braces += " } "
            close_braces += " } "
            
        key = self._gen_expr(node.key)
        val = self._gen_expr(node.value)
        insert_code = f"__res.insert({key}, {val}); "
        
        return f"({{ {inner}{loop_code}{insert_code}{close_braces} __res }})"

    def _gen_set_comp(self, node: IRSetComp) -> str:
        # In Rust, HashSet is usually used for Python set
        # Check if uses_hashmap or dedicated flag is needed
        self._uses_hashmap = True # Standard lib for HashSet too
        elem_t = self._get_rust_type(node.result_type.element_type)
        inner = f"let mut __res = HashSet::<{elem_t}>::new(); "
        
        loop_code = ""
        close_braces = ""
        for gen in node.generators:
            target = self._gen_comp_target(gen.target)
            iterable = self._gen_expr(gen.iterable)
            loop_code += f"for &{target} in &{iterable} {{ "
            for if_expr in gen.ifs:
                cond = self._gen_expr(if_expr)
                loop_code += f"if {cond} {{ "
                close_braces += " } "
            close_braces += " } "
        
        elt = self._gen_expr(node.elt)
        insert_code = f"__res.insert({elt}); "
        
        return f"({{ {inner}{loop_code}{insert_code}{close_braces} __res }})"

    def _gen_comp_target(self, target) -> str:
        if isinstance(target, IRName):
            return _mangle(target.name)
        if isinstance(target, IRTupleLit):
            elems = ", ".join(self._gen_comp_target(e) for e in target.elements)
            return f"({elems})"
        return "_"

    def _emit_async_runtime(self) -> None:
        self._emit("mod py_async {")
        self._indent += 1
        self._emit("use std::future::Future;")
        self._emit("use std::pin::Pin;")
        self._emit("use std::task::{Context, Poll, RawWaker, RawWakerVTable, Waker};")
        self._emit("")
        self._emit("pub fn block_on<F: Future>(mut future: F) -> F::Output {")
        self._indent += 1
        self._emit("let mut future = unsafe { Pin::new_unchecked(&mut future) };")
        self._emit("let waker = unsafe { Waker::from_raw(null_waker()) };")
        self._emit("let mut cx = Context::from_waker(&waker);")
        self._emit("loop {")
        self._indent += 1
        self._emit("match future.as_mut().poll(&mut cx) {")
        self._indent += 1
        self._emit("Poll::Ready(val) => return val,")
        self._emit("Poll::Pending => {}")
        self._indent -= 1
        self._emit("}")
        self._indent -= 1
        self._emit("}")
        self._indent -= 1
        self._emit("}")
        self._emit("")
        self._emit("fn null_waker() -> RawWaker {")
        self._indent += 1
        self._emit("fn clone(_: *const ()) -> RawWaker { null_waker() }")
        self._emit("fn wake(_: *const ()) {}")
        self._emit("fn wake_by_ref(_: *const ()) {}")
        self._emit("fn drop(_: *const ()) {}")
        self._emit("static VTABLE: RawWakerVTable = RawWakerVTable::new(clone, wake, wake_by_ref, drop);")
        self._emit("RawWaker::new(std::ptr::null(), &VTABLE)")
        self._indent -= 1
        self._emit("}")
        self._indent -= 1
        self._emit("}")

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
