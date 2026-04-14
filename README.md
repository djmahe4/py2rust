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

#### Basic Constructs
- Function definitions with **mandatory** type hints on all parameters and return type
- Variable declarations with type annotations or inferable literals
- `async def` and `await` for asynchronous programming
- `return` statements
- `print(expr)` supports simple arguments and interpolated strings
- f-strings: `f"Value: {val:.2f}"` mapped to Rust `format!` macro
- `pass` statements and `...` (Ellipsis)
- Limited imports: `typing` and `enum` modules are ignored to support standard Python type declarations

#### Primitive Types
- `int` → `i32`
- `float` → `f64`
- `bool` → `bool`
- `str` → `String`

#### Operators
- Arithmetic: `+`, `-`, `*`, `/`, `//`, `%`
- Comparison: `==`, `!=`, `<`, `<=`, `>`, `>=`
- Boolean logic: `and`, `or`, `not`
- Augmented assignment: `+=`, `-=`, `*=`, `/=`, `//=`, `%=`

#### Control Flow
- `if` / `elif` / `else`
- `while` loops
- `for` loops in `range(start, stop)` or `range(start, stop, step)` form
- `break` and `continue`

#### Collections
- Homogeneous lists: `list[int]`, `list[float]`, etc. → `Vec<T>`
- Dicts: `dict[K, V]` → `HashMap<K, V>`
- String indexing and slicing
- Dict membership: `key in dict`, `key not in dict`

#### File Operations
- `open(path)` and `open(path, mode)` → `FileHandle`
- Methods: `.read()`, `.readline()`, `.write()`, `.close()`, `.tell()`, `.seek()`

#### Classes (with limitations)
- Class definitions with type-annotated fields
- `__init__` constructors
- Instance methods with `self` parameter
- Field access via `self.field`
- Method calls via `obj.method(args)`
- Single inheritance (base class)
- Multiple inheritance (discovery and member flattening)
- Protocols: `typing.Protocol` mapped to Rust `trait`
- Method overloading by argument count
- Automatic structural matching for trait implementations

### ❌ Forbidden Features (raises `UnsupportedFeatureError`)

#### Language Features
- Missing type hints on function parameters/returns
- Dynamic typing, `Any`, `typing.Any`
- `eval`, `exec`, `globals`, `locals`
- Decorators
- Generators, `yield`
- Custom module imports (only `typing` and `enum` are ignored)
- Context managers (`with`)
- Ternary expressions (`x if cond else y`)
- Multiple inheritance

#### Class Features
- `self` without type annotation on first parameter (Python requirement)
- Property decorators
- Class methods (`@classmethod`)
- Static methods (`@staticmethod`)
- `__new__` constructor
- Multiple constructors with same arity
- Keyword arguments in function/method calls

#### Syntax Restrictions
- Only single-target assignments
- Only `range()` in for loops
- Only simple comparisons (no chained comparisons)
- No walrus operator (`:=`)

## Type Mapping

| Python         | Rust                |
|----------------|---------------------|
| `int`          | `i32`               |
| `float`        | `f64`               |
| `bool`         | `bool`              |
| `str`          | `String`            |
| `list[T]`      | `Vec<T>`            |
| `dict[K, V]`   | `HashMap<K, V>`     |
| `ClassName`    | `ClassName` (struct)|

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

## Examples

To test examples:
```bash
for f in examples/*.py; do echo "Processing $f..."; PYTHONPATH=. python3 -m py2rust.cli "$f" -o "${f%.py}.rs" --verify || { echo "FAILED: $f"; break; }; done
```

### Simple Math

**Input (`examples/simple_math.py`):**
```python
def add(x: int, y: int) -> int:
    return x + y

def main() -> int:
    a: int = 10
    b: int = 5
    result: int = add(a, b)
    print(result)
    return 0
```

**Output (`examples/simple_math.rs`):**
```rust
fn add(x: i32, y: i32) -> i32 {
    return x + y;
}

fn main() -> i32 {
    let a: i32 = 10;
    let b: i32 = 5;
    let result: i32 = add(a, b);
    println!("{}", result);
    return 0;
}
```

### Fibonacci

**Input (`examples/fibonacci.py`):**
```python
def fibonacci(n: int) -> int:
    if n <= 0:
        return 0
    elif n == 1:
        return 1
    else:
        a: int = 0
        b: int = 1
        for i in range(2, n):
            temp: int = a + b
            a = b
            b = temp
        return b

def main() -> int:
    print(fibonacci(10))
    return 0
```

### Classes

**Input (`examples/classes.py`):**
```python
class Point:
    x: int = 0
    y: int = 0
    
    def __init__(self, x: int, y: int) -> None:
        self.x = x
        self.y = y
    
    def get_x(self) -> int:
        return self.x
    
    def distance_to(self, other: int) -> int:
        dx: int = self.x - other
        dy: int = self.y - 0
        return dx + dy

def main() -> int:
    p: Point = Point(3, 4)
    x: int = p.get_x()
    d: int = p.distance_to(0)
    return x + d
```

**Output (`examples/classes.rs`):**
```rust
struct Point {
    x: i32,
    y: i32,
}

impl Point {
    fn new(x: i32, y: i32) -> Self {
        Point { x, y }
    }
    fn get_x(self) -> i32 {
        self.x
    }
    fn distance_to(self, other: i32) -> i32 {
        let dx: i32 = self.x - other;
        let dy: i32 = self.y - 0;
        return dx + dy;
    }
}

fn main() -> i32 {
    let p: Point = Point::new(3, 4);
    let x: i32 = p.get_x();
    let d: i32 = p.distance_to(0);
    return x + d;
}
```

### Lists

**Input (`examples/lists.py`):**
```python
def sum_list(nums: list[int]) -> int:
    total: int = 0
    for n in range(len(nums)):
        total = total + nums[n]
    return total

def main() -> int:
    numbers: list[int] = [1, 2, 3, 4, 5]
    result: int = sum_list(numbers)
    print(result)
    return 0
```

### Dictionaries

**Input (`examples/dicts.py`):**
```python
def main() -> int:
    scores: dict[str, int] = {"alice": 90, "bob": 85}
    scores["charlie"] = 95
    alice_score: int = scores["alice"]
    print(alice_score)
    return 0
```

### File Operations

**Input (`examples/files.py`):**
```python
def main() -> int:
    f = open("test.txt", "w")
    f.write("Hello, World!")
    f.close()
    
    f = open("test.txt", "r")
    contents = f.read()
    print(contents)
    f.close()
    return 0
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
│   │   ├── symbol_table.py  # Scoped symbol table with class support
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
│   └── tests/               # pytest test suite (151 tests)
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
UnsupportedFeatureError: example.py:3:1: Keyword arguments not supported
  | def foo(x=1)
  |           ^
  hint: Use positional arguments instead
```

```
SemanticError: example.py:5:10: Undefined variable: 'y'
  |     return y
  |          ^
```
