from __future__ import annotations
from typing import Optional, Any
from ..ir.ir_nodes import (
    IRIntType,
    IRListType,
    IRDictType,
    IRStrType,
    IRExternalPythonType,
    IRUnknownType,
    IRTupleType,
    IRBoolLit,
    IRName,
    IRSelf,
    IRStructAccess,
    IRTupleLit,
    IRBinOp,
    IRFileMethod,
    IRMethodCall,
    IRFileOpen,
    IRNew,
    IRIf,
    IRStmt,
    IRExpr,
    IRAssign,
    IRAugAssign,
    IRSubscriptAssign,
    IRDictDelete,
    IRTupleUnpack,
    IRFieldAssign,
    IRVarDecl,
    IRForRange,
    IRForIter,
    IRWhile,
    IRTryExcept,
    IRWith,
    IRAssert,
    IRGlobal,
    IRNonlocal,
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


def _mangle(name) -> str:
    """Escape Python identifiers that collide with Rust keywords."""
    if not isinstance(name, str):
        if hasattr(name, "name"):
            name = name.name
        else:
            name = str(name)
    if name == "__str__":
        return "__str__"
    return name + "_" if name in _RUST_KEYWORDS else name


def _get_var_name(expr) -> str | None:
    """Extract variable name from an expression."""
    if isinstance(expr, IRName):
        return expr.name
    if isinstance(expr, IRSelf):
        return "self"
    if isinstance(expr, IRStructAccess):
        return _get_var_name(expr.value)
    return None


def _get_names(target):
    """Recursively extract string names from a target (str, IRName, or IRTupleLit)."""
    if isinstance(target, str):
        return [target]
    if isinstance(target, IRName):
        return [target.name]
    if isinstance(target, IRTupleLit):
        names = []
        for e in target.elements:
            names.extend(_get_names(e))
        return names
    return []


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


def _get_reachable_if_branches(stmt: IRIf) -> list[tuple[Optional[IRExpr], list[IRStmt]]]:
    """
    Returns a list of reachable branches in the format (condition, body).
    If condition is None, it represents an unconditional body (like 'else').
    """
    reachable = []
    
    # Check main condition
    if isinstance(stmt.condition, IRBoolLit):
        if stmt.condition.value:
            # Main branch is always taken
            reachable.append((stmt.condition, stmt.then_body))
            return reachable
        else:
            # Main branch is never taken, move on to elif and else
            pass
    else:
        # Dynamic condition, main branch is reachable
        reachable.append((stmt.condition, stmt.then_body))
    
    # Check elif clauses
    for elif_cond, elif_body in stmt.elif_clauses:
        if isinstance(elif_cond, IRBoolLit):
            if elif_cond.value:
                # Elif branch is always taken
                reachable.append((elif_cond, elif_body))
                return reachable
            else:
                # Elif branch is never taken
                pass
        else:
            # Dynamic condition, elif is reachable
            reachable.append((elif_cond, elif_body))
            
    # Check else clause
    if stmt.else_body is not None:
        reachable.append((None, stmt.else_body))
        
    return reachable


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
                for name in _get_names(stmt.target):
                    mutated.add(name)
                    assigned_vars[name] = assigned_vars.get(name, 0) + 1
                _visit(stmt.body, True)
            elif isinstance(stmt, IRForIter):
                for name in _get_names(stmt.target):
                    mutated.add(name)
                    assigned_vars[name] = assigned_vars.get(name, 0) + 1
                _visit(stmt.body, True)
            elif isinstance(stmt, IRWhile):
                _visit(stmt.body, True)
            elif isinstance(stmt, IRIf):
                for _, body in _get_reachable_if_branches(stmt):
                    _visit(body, in_loop)
            elif isinstance(stmt, IRTryExcept):
                _visit(stmt.body, in_loop)
                for h_type, h_name, h_body in stmt.handlers:
                    if h_name:
                        mutated.add(h_name)
                    _visit(h_body, in_loop)
            elif isinstance(stmt, IRWith):
                for item in stmt.items:
                    for name in _get_names(item.optional_vars):
                        mutated.add(name)
                        assigned_vars[name] = assigned_vars.get(name, 0) + 1
                _visit(stmt.body, in_loop)
            elif isinstance(stmt, IRAssert):
                pass
            elif isinstance(stmt, IRGlobal):
                pass
            elif isinstance(stmt, IRNonlocal):
                pass

    _visit(stmts)
    return mutated


def _collect_decls(stmts, uses_python_wrappers=False) -> tuple[dict[str, object], set[str]]:
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
                for name in _get_names(stmt.target):
                    decls[name] = IRIntType()
                    pre_declare.add(name)
                _recurse(stmt.body, depth + 1)
            elif isinstance(stmt, IRForIter):
                # Target type depends on iterable
                it_t = stmt.iterable_type
                names = _get_names(stmt.target)
                
                # Determine element types if it's a tuple
                if isinstance(it_t, IRListType) and isinstance(it_t.element_type, IRTupleType):
                    elem_types = it_t.element_type.element_types
                    for i, name in enumerate(names):
                        t = elem_types[i] if i < len(elem_types) else IRIntType()
                        decls[name] = t
                        pre_declare.add(name)
                else:
                    target_type = IRExternalPythonType(module="", name="") if uses_python_wrappers else IRIntType()
                    if isinstance(it_t, IRListType):
                        target_type = it_t.element_type
                    elif isinstance(it_t, IRDictType):
                        target_type = it_t.key_type
                    elif isinstance(it_t, IRStrType):
                        target_type = IRStrType()
                    elif isinstance(it_t, IRExternalPythonType):
                        target_type = IRExternalPythonType(module="", name="")
                    elif isinstance(it_t, IRUnknownType):
                        target_type = IRExternalPythonType(module="", name="")
                    
                    for name in names:
                        decls[name] = target_type
                        pre_declare.add(name)
                _recurse(stmt.body, depth + 1)
            elif isinstance(stmt, IRWhile):
                _recurse(stmt.body, depth + 1)
            elif isinstance(stmt, IRTryExcept):
                _recurse(stmt.body, depth + 1)
                for _, _, h_body in stmt.handlers:
                    _recurse(h_body, depth + 1)
            elif isinstance(stmt, IRWith):
                # Context managers variables are declarations
                for item in stmt.items:
                    for name in _get_names(item.optional_vars):
                        # Use ExternalObject in mock mode for context managers (like open())
                        decls[name] = IRExternalPythonType(module="", name="") if uses_python_wrappers else None
                _recurse(stmt.body, depth + 1)
            elif isinstance(stmt, IRAssert):
                pass
            elif isinstance(stmt, IRGlobal):
                pass
            elif isinstance(stmt, IRNonlocal):
                pass
            elif isinstance(stmt, IRIf):
                for _, body in _get_reachable_if_branches(stmt):
                    _recurse(body, depth + 1)

    _recurse(stmts, depth=0)
    return decls, pre_declare


def _vars_declared_in_loop(stmts) -> set:
    """Collect variable names that are declared inside while loops."""
    return set()


PYTHON_BOILERPLATE_LINES = [
    "",
    "#[derive(Clone)]",
    "pub struct ExternalObject {",
    "    pub obj: PyObject,",
    "}",
    "",
    "impl From<PyErr> for PyError {",
    "    fn from(err: PyErr) -> Self {",
    "        PyError::Exception(err.to_string())",
    "    }",
    "}",
    "impl Default for ExternalObject {",
    "    fn default() -> Self {",
    "        Python::with_gil(|py| Self::new(py.None()))",
    "    }",
    "}",
    "",
    "impl ExternalObject {",
    "    pub fn new(obj: PyObject) -> Self {",
    "        Self { obj }",
    "    }",
    "",
    "    pub fn from_module(module: &str, name: &str) -> Self {",
    "        Python::with_gil(|py| {",
    "            let m = py.import(module).expect(\"Failed to import module\");",
    "            let attr = m.getattr(name).expect(\"Failed to get attribute from module\");",
    "            Self::new(attr.to_object(py))",
    "        })",
    "    }",
    "",
    "    pub fn load_module(module: &str) -> PyResult<Self> {",
    "        Python::with_gil(|py| {",
    "            Self::init_venv(py)?;",
    "            let m = py.import(module)?;",
    "            Ok(Self::new(m.to_object(py)))",
    "        })",
    "    }",
    "",
    "    fn init_venv(py: Python<'_>) -> PyResult<()> {",
    "        use std::env;",
    "        if let Ok(venv) = env::var(\"PY2RUST_VENV\") {",
    "            let sys = py.import(\"sys\")?;",
    "            let path = sys.getattr(\"path\")?;",
    "            ",
    "            let venv_path = std::path::PathBuf::from(venv);",
    "            #[cfg(target_os = \"windows\")]",
    "            {",
    "                let mut sp_path = venv_path.clone();",
    "                sp_path.push(\"Lib\");",
    "                sp_path.push(\"site-packages\");",
    "                let sp_str = sp_path.to_string_lossy().to_string();",
    "                path.call_method1(\"append\", (sp_str,))?;",
    "            }",
    "            #[cfg(not(target_os = \"windows\"))]",
    "            {",
    "                let lib_dir = venv_path.join(\"lib\");",
    "                if let Ok(entries) = std::fs::read_dir(lib_dir) {",
    "                    for entry in entries.flatten() {",
    "                        let p = entry.path();",
    "                        if p.is_dir() && p.file_name().unwrap_or_default().to_string_lossy().starts_with(\"python\") {",
    "                            let site_packages = p.join(\"site-packages\");",
    "                            if site_packages.exists() {",
    "                                let sp_str = site_packages.to_string_lossy().to_string();",
    "                                path.call_method1(\"append\", (sp_str,))?;",
    "                                break;",
    "                            }",
    "                        }",
    "                    }",
    "                }",
    "            }",
    "        }",
    "        Ok(())",
    "    }",
    "",
    "    pub fn getattr(&self, name: &str) -> PyResult<Self> {",
    "        Python::with_gil(|py| {",
    "            let attr = self.obj.getattr(py, name)?;",
    "            Ok(Self::new(attr.to_object(py)))",
    "        })",
    "    }",
    "",
    "    pub fn call(&self, args: impl IntoPy<Py<PyTuple>>) -> PyResult<Self> {",
    "        Python::with_gil(|py| {",
    "            let res = self.obj.call1(py, args)?;",
    "            Ok(Self::new(res.to_object(py)))",
    "        })",
    "    }",
    "",
    "    pub fn call_method(&self, method: &str, args: impl IntoPy<Py<PyTuple>>) -> PyResult<Self> {",
    "        Python::with_gil(|py| {",
    "            let res = self.obj.call_method1(py, method, args)?;",
    "            Ok(Self::new(res.to_object(py)))",
    "        })",
    "    }",
    "",
    "    pub fn setattr(&self, name: &str, value: impl IntoPy<PyObject>) -> PyResult<()> {",
    "        Python::with_gil(|py| {",
    "            let value = value.into_py(py);",
    "            self.obj.as_ref(py).setattr(name, value)?;",
    "            Ok(())",
    "        })",
    "    }",
    "",
    "    pub fn setitem(&self, key: impl IntoPy<PyObject>, value: impl IntoPy<PyObject>) -> PyResult<()> {",
    "        Python::with_gil(|py| {",
    "            let key = key.into_py(py);",
    "            let value = value.into_py(py);",
    "            self.obj.as_ref(py).set_item(key, value)?;",
    "            Ok(())",
    "        })",
    "    }",
    "",
    "    pub fn getitem(&self, key: impl IntoPy<PyObject>) -> PyResult<Self> {",
    "        Python::with_gil(|py| {",
    "            let key = key.into_py(py);",
    "            let item = self.obj.as_ref(py).get_item(key)?;",
    "            Ok(Self::new(item.to_object(py)))",
    "        })",
    "    }",
    "",
    "    pub fn call_builtin(name: &str, args: impl IntoPy<Py<PyTuple>>) -> PyResult<Self> {",
    "        Python::with_gil(|py| {",
    "            let builtins = py.import(\"builtins\")?;",
    "            let func = builtins.getattr(name)?;",
    "            let res = func.call1(args)?;",
    "            Ok(Self::new(res.to_object(py)))",
    "        })",
    "    }",
    "",
    "    pub fn read(&self) -> PyResult<String> {",
    "        Python::with_gil(|py| {",
    "            let res = self.obj.call_method0(py, \"read\")?;",
    "            res.extract(py)",
    "        })",
    "    }",
    "",
    "    pub fn write(&self, data: &str) -> PyResult<()> {",
    "        Python::with_gil(|py| {",
    "            self.obj.call_method1(py, \"write\", (data,))?;",
    "            Ok(())",
    "        })",
    "    }",
    "",
    "    pub fn close(&self) -> PyResult<()> {",
    "        Python::with_gil(|py| {",
    "            self.obj.call_method0(py, \"close\")?;",
    "            Ok(())",
    "        })",
    "    }",
    "",
    "    pub fn len(&self) -> usize {",
    "        Python::with_gil(|py| {",
    "            self.obj.as_ref(py).len().unwrap_or(0)",
    "        })",
    "    }",
    "",
    "    pub fn iter(&self) -> PyResult<Vec<Self>> {",
    "        Python::with_gil(|py| {",
    "            let iter = self.obj.as_ref(py).iter()?;",
    "            let mut res = Vec::new();",
    "            for item in iter {",
    "                res.push(Self::new(item?.to_object(py)));",
    "            }",
    "            Ok(res)",
    "        })",
    "    }",
    "",
    "    pub fn new_csv_reader(file_obj: &Self) -> PyResult<Self> {",
    "        Python::with_gil(|py| {",
    "            let csv = py.import(\"csv\")?;",
    "            let reader = csv.getattr(\"reader\")?.call1((file_obj.obj.as_ref(py),))?;",
    "            Ok(Self::new(reader.to_object(py)))",
    "        })",
    "    }",
    "}",
    "",
    "impl std::fmt::Display for ExternalObject {",
    "    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {",
    "        Python::with_gil(|py| {",
    "            let s = self.obj.as_ref(py).str().and_then(|s| s.extract::<String>()).unwrap_or_else(|_| \"<external object>\".to_string());",
    "            write!(f, \"{}\", s)",
    "        })",
    "    }",
    "}",
    "",
    "impl std::fmt::Debug for ExternalObject {",
    "    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {",
    "        Python::with_gil(|py| {",
    "            let r = self.obj.as_ref(py).repr().map(|r| r.to_string()).unwrap_or_else(|_| \"<external object>\".to_string());",
    "            write!(f, \"{:?}\", r)",
    "        })",
    "    }",
    "}",
    "",
    "impl IntoPy<PyObject> for ExternalObject {",
    "    fn into_py(self, _py: Python<'_>) -> PyObject {",
    "        self.obj",
    "    }",
    "}",
]
