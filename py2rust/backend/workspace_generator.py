from __future__ import annotations
from pathlib import Path
from ..middleend.dependency_manager import DependencyManager

class WorkspaceGenerator:
    def __init__(self, output_dir: Path, project_name: str = "compiled_project", version: str = "0.1.0") -> None:
        self.output_dir = output_dir.resolve()
        self.project_name = project_name
        self.version = version
        self.dep_manager = DependencyManager()

    def add_project_dependencies(self, extra_deps: dict[str, str]) -> None:
        for crate, ver in extra_deps.items():
            # If version has features or other structured details, handle them
            if isinstance(ver, dict):
                self.dep_manager.add_dependency(
                    crate,
                    version=ver.get("version"),
                    features=ver.get("features")
                )
            else:
                self.dep_manager.add_dependency(crate, version=ver)

    def write_cargo_toml(self, is_bin: bool = True) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        cargo_path = self.output_dir / "Cargo.toml"
        
        # Let's ensure minimal dependencies are registered if needed
        # (e.g. pyo3 if there is python interop)
        cargo_content = [
            "[package]",
            f'name = "{self.project_name}"',
            f'version = "{self.version}"',
            'edition = "2021"',
            ""
        ]
        
        if is_bin:
            # We can have [[bin]] entry or default src/main.rs
            pass
            
        cargo_content.append(self.dep_manager.get_cargo_dependencies())
        cargo_path.write_text("\n".join(cargo_content) + "\n")

    def generate_mod_hierarchy(self, modules: dict[str, str], entry_point: str | None = None) -> None:
        """
        Creates the directory hierarchy and mod.rs / lib.rs files for modules.
        modules: dict of { 'foo.bar': 'rust source code', 'foo': '...' }
        """
        src_dir = self.output_dir / "src"
        src_dir.mkdir(parents=True, exist_ok=True)

        # Write common errors module
        errors_content = [
            "#[derive(Debug, Clone)]",
            "pub enum PyError {",
            "    Exception(String),",
            "    ValueError(String),",
            "    TypeError(String),",
            "    KeyError(String),",
            "    IndexError(String),",
            "    IOError(String),",
            "}",
            "",
            "impl std::fmt::Display for PyError {",
            "    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {",
            "        match self {",
            '            PyError::Exception(s) => write!(f, "Exception: {}", s),',
            '            PyError::ValueError(s) => write!(f, "ValueError: {}", s),',
            '            PyError::TypeError(s) => write!(f, "TypeError: {}", s),',
            '            PyError::KeyError(s) => write!(f, "KeyError: {}", s),',
            '            PyError::IndexError(s) => write!(f, "IndexError: {}", s),',
            '            PyError::IOError(s) => write!(f, "IOError: {}", s),',
            "        }",
            "    }",
            "}",
            "",
            "impl From<std::io::Error> for PyError {",
            "    fn from(err: std::io::Error) -> Self {",
            "        PyError::IOError(err.to_string())",
            "    }",
            "}",
            "",
            "impl From<std::num::ParseIntError> for PyError {",
            "    fn from(err: std::num::ParseIntError) -> Self {",
            "        PyError::ValueError(err.to_string())",
            "    }",
            "}",
            "",
            "impl From<std::num::ParseFloatError> for PyError {",
            "    fn from(err: std::num::ParseFloatError) -> Self {",
            "        PyError::ValueError(err.to_string())",
            "    }",
            "}",
            ""
        ]

        if "pyo3" in self.dep_manager.dependencies:
            errors_content.extend([
                "impl From<PyError> for pyo3::PyErr {",
                "    fn from(err: PyError) -> Self {",
                "        match err {",
                "            PyError::Exception(s) => pyo3::exceptions::PyException::new_err(s),",
                "            PyError::ValueError(s) => pyo3::exceptions::PyValueError::new_err(s),",
                "            PyError::TypeError(s) => pyo3::exceptions::PyTypeError::new_err(s),",
                "            PyError::KeyError(s) => pyo3::exceptions::PyKeyError::new_err(s),",
                "            PyError::IndexError(s) => pyo3::exceptions::PyIndexError::new_err(s),",
                "            PyError::IOError(s) => pyo3::exceptions::PyOSError::new_err(s),",
                "        }",
                "    }",
                "}",
                ""
            ])

        errors_content.extend([
            "pub enum TryResult<T> {",
            "    Normal,",
            "    Return(T),",
            "    Break,",
            "    Continue,",
            "}",
            ""
        ])

        (src_dir / "errors.rs").write_text("\n".join(errors_content))

        # Identify all logical module paths and create respective files
        module_structure: dict[tuple[str, ...], str] = {}
        for mod_name, code in modules.items():
            parts = tuple(mod_name.split("."))
            module_structure[parts] = code

        # Determine the matched entry key
        top_level_mods = sorted(set(parts[0] for parts in module_structure))
        matched_entry_key = None
        if entry_point:
            entry_parts = tuple(entry_point.split("."))
            if entry_parts in module_structure:
                matched_entry_key = entry_parts
            else:
                # Try stripping the first part (e.g. package_dir prefix) if it doesn't match
                if len(entry_parts) > 1 and entry_parts[1:] in module_structure:
                    matched_entry_key = entry_parts[1:]
        elif len(top_level_mods) == 1 and not any(len(parts) > 1 for parts in module_structure):
            matched_entry_key = (top_level_mods[0],)

        # First, write all individual module files
        for parts, code in module_structure.items():
            if parts == matched_entry_key and len(parts) == 1:
                # This is the top-level entry point module, its code will be written directly to main.rs / lib.rs
                continue
                
            if len(parts) == 1:
                # This is a top-level module that is NOT the entry point.
                # It must be written to its own file, e.g. src/math_utils.rs
                mod_file = src_dir / f"{parts[0]}.rs"
                mod_file.write_text(code)
                continue
                
            # Nested module, e.g. (foo, bar, baz)
            parent_dir = src_dir.joinpath(*parts[:-1])
            parent_dir.mkdir(parents=True, exist_ok=True)
            
            # Write nested module file, e.g. src/foo/bar/baz.rs
            mod_file = parent_dir / f"{parts[-1]}.rs"
            mod_file.write_text(code)

        # Build parent declarations dynamically.
        # Include all intermediate module paths to make sure empty parent modules still exist and declare children.
        all_parent_paths = set(parts[:-1] for parts in module_structure if len(parts) > 1)
        all_mods = set(module_structure.keys()) | all_parent_paths

        # For each parent path, write child module declarations.
        # Ensure we also create empty files for parent paths if they don't have explicit code.
        for parent_parts in sorted(all_parent_paths, key=len):
            # Find all child modules of this parent path
            children = [parts[-1] for parts in all_mods if len(parts) > 1 and parts[:-1] == parent_parts]
            
            mod_decls = "\n".join(f"pub mod {child};" for child in sorted(children)) + "\n"
            
            parent_code = module_structure.get(parent_parts, "")
            combined_code = mod_decls + "\n" + parent_code
            
            # Write to parent file, e.g. src/foo/bar.rs
            parent_file = src_dir.joinpath(*parent_parts).with_suffix(".rs")
            parent_file.write_text(combined_code)

        # Write top-level modules declaration in lib.rs or main.rs
        top_level_mods = sorted(set(parts[0] for parts in all_mods) | {"errors"})
        if matched_entry_key and len(matched_entry_key) == 1:
            if matched_entry_key[0] in top_level_mods:
                top_level_mods.remove(matched_entry_key[0])
                
        top_level_decls = "\n".join(f"pub mod {mod};" for mod in top_level_mods) + "\n" if top_level_mods else ""
        
        entry_code = ""
        if matched_entry_key:
            entry_code = module_structure[matched_entry_key]
            
        combined_entry = top_level_decls + "\n" + entry_code
        
        # Decide lib.rs vs main.rs based on entry_point or presence of a main-like function
        is_bin = bool(entry_point) or "fn main(" in combined_entry or "pub fn main(" in combined_entry
        entry_file = src_dir / ("main.rs" if is_bin else "lib.rs")
        entry_file.write_text(combined_entry)
        
        self.write_cargo_toml(is_bin=is_bin)

