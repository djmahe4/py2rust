# py2rust

A **Python-to-Rust subset compiler** built following formal compiler design principles: frontend, middle-end, and backend, with clear separation of concerns.

## Overview

`py2rust` translates a strictly defined, statically typed subset of Python into clean, safe, zero-unsafe Rust code.

**Pipeline:**
```
Python Source → Python AST → Custom AST → Symbol Table + Semantic Analysis
    → Type Checking & Inference → High-Level IR → Rust Code Generation → Formatted Rust
```

## Supported Python Subset

### ✅ Supported Features
- Function definitions with **mandatory** type hints on all parameters and return type
- Variable declarations with type annotations or inferable literals
- Primitive types: `int`, `float`, `bool`, `str`
- Arithmetic operators: `+`, `-`, `*`, `/`, `//`, `%`
- Comparison operators and boolean logic (`and`, `or`, `not`)
- `if` / `elif` / `else`
- `while` loops
- `for` loops in `range(start, stop)` or `range(start, stop, step)` form
- `return` statements
- Homogeneous lists: `list[int]`, `list[float]`, etc.
- `print(expr)` with simple arguments

### ❌ Forbidden Features (raises `UnsupportedFeatureError`)
- Classes, methods, inheritance
- Missing type hints on function parameters/returns
- Dynamic typing, `Any`, `typing.Any`
- `eval`, `exec`, `globals`, `locals`
- Decorators, lambdas, comprehensions
- Async, generators, `yield`
- Import statements
- Exception handling (`try`/`except`)

### Type Mapping
| Python    | Rust       |
|-----------|------------|
| `int`     | `i32`      |
| `float`   | `f64`      |
| `bool`    | `bool`     |
| `str`     | `String`   |
| `list[T]` | `Vec<T>`   |

## Installation

```bash
pip install -e .
```

Requires Python ≥ 3.11 and Rust/`rustc` (stable) for `--verify`.

## Usage

```bash
# Basic compilation (output to stdout)
py2rust input.py

# Compile to file
py2rust input.py -o output.rs

# Emit intermediate representations
py2rust input.py --emit-ast      # Print the custom AST
py2rust input.py --emit-ir       # Print the IR

# Type-check only, no code generation
py2rust input.py --check-only

# Verify generated Rust compiles with rustc
py2rust input.py -o output.rs --verify

# Verbose output
py2rust input.py -v

# Disable rustfmt formatting
py2rust input.py --no-format
```

## Example

**Input (`examples/simple_math.py`):**
```python
def add(x: int, y: int) -> int:
    return x + y

def multiply(x: int, y: int) -> int:
    return x * y

def main() -> int:
    a: int = 10
    b: int = 5
    sum_result: int = add(a, b)
    product: int = multiply(a, b)
    print(sum_result)
    print(product)
    return 0
```

**Output (`examples/simple_math.rs`):**
```rust
fn add(x: i32, y: i32) -> i32 {
    return x + y;
}

fn multiply(x: i32, y: i32) -> i32 {
    return x * y;
}

fn main() -> i32 {
    let a: i32 = 10;
    let b: i32 = 5;
    let sum_result: i32 = add(a, b);
    let product: i32 = multiply(a, b);
    println!("{}", sum_result);
    println!("{}", product);
    return 0;
}
```

## Project Structure

```
py2rust/
├── py2rust/
│   ├── __init__.py
│   ├── main.py              # compile_file() pipeline
│   ├── cli.py               # argparse CLI entry point
│   ├── config.py            # CompilerConfig dataclass
│   │
│   ├── frontend/
│   │   ├── ast_nodes.py     # Frozen dataclass AST nodes with source location
│   │   └── parser.py        # Python ast → custom AST, rejects unsupported nodes
│   │
│   ├── middleend/
│   │   ├── symbol_table.py  # Scoped symbol table
│   │   ├── type_checker.py  # Strict bidirectional type checker
│   │   ├── type_inferencer.py # Type inference from literals
│   │   └── ir_builder.py    # Custom AST → IR, final semantic validation
│   │
│   ├── ir/
│   │   └── ir_nodes.py      # Strongly-typed IR nodes (frozen dataclasses)
│   │
│   ├── backend/
│   │   ├── rust_codegen.py  # IR → idiomatic Rust code
│   │   └── rust_formatter.py # rustfmt integration
│   │
│   ├── utils/
│   │   ├── errors.py        # CompilerError hierarchy
│   │   ├── logger.py        # Logging setup
│   │   └── visitor.py       # Generic visitor pattern
│   │
│   └── tests/               # pytest test suite (66 tests)
│
├── examples/                # Input/output examples
└── pyproject.toml
```

## Running Tests

```bash
python -m pytest py2rust/tests/ -v
```

## Error Messages

`py2rust` provides rich error messages with file location, source snippet, and suggestions:

```
UnsupportedFeatureError: example.py:3:1: Classes are not supported
  | class Foo:
  | ^
  hint: Remove class definitions; only functions are supported
```
