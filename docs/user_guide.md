# py2rust Developer & User Guide

Welcome to the **py2rust User Guide**! This document provides a clear, practical, and comprehensive guide to using the `py2rust` Python-to-Rust subset compiler. Whether you are a compiler enthusiast or a developer looking to compile performance-sensitive Python utilities into native, zero-overhead Rust binaries, this guide will get you up and running with absolute clarity.

---

## 🚀 Quick Start (60-Second Hello World)

Let's compile a simple Python function to Rust and run it.

### Step 1: Write your Python source
Create a file named `hello.py`:
```python
def greet(name: str) -> str:
    return "Hello, " + name + "!"

def main() -> int:
    message: str = greet("World")
    print(message)
    return 0
```

### Step 2: Compile to Rust
Run the `py2rust` compiler via command line:
```bash
py2rust hello.py -o hello.rs
```

### Step 3: View the generated Rust code
Open `hello.rs` to see the idiomatic Rust output:
```rust
fn greet(name: String) -> String {
    return format!("Hello, {}!", name);
}

fn main() -> i32 {
    let message: String = greet("World".to_string());
    println!("{}", message);
    return 0;
}
```

---

## 📦 Installation & Environment Setup

`py2rust` compiles static Python subsets into modern Rust. To set up your system, ensure you meet the following requirements:

### Prerequisites
*   **Python**: Version $\ge$ 3.11
*   **Rust / Cargo**: Standard stable toolchain (install via [rustup.rs](https://rustup.rs/))

### Installation
Clone the repository and install it in editable/developer mode:
```bash
# From the root of the py2rust project
pip install -e .
```

To verify the installation:
```bash
py2rust --help
```

---

## 🛠️ CLI Command Reference

The `py2rust` command-line utility provides rich parameters for debugging, optimization, verification, and interoperability.

| Option | Shorthand | Description | Example |
| :--- | :--- | :--- | :--- |
| `--output` | `-o` | Specify output file path (defaults to stdout if omitted). | `py2rust main.py -o main.rs` |
| `--check-only` | | Performs symbol resolution and type-checking without writing Rust code. | `py2rust main.py --check-only` |
| `--verify` | | Invokes `rustc` on the generated code to guarantee it compiles. | `py2rust main.py -o main.rs --verify` |
| `--no-format` | | Disables automatic code formatting with `rustfmt`. | `py2rust main.py --no-format` |
| `--emit-ast` | | Dumps the custom Python AST to stdout. | `py2rust main.py --emit-ast` |
| `--emit-ir` | | Dumps the intermediate representation (IR) to stdout. | `py2rust main.py --emit-ir` |
| `--mock-mode` | | Ignores external library imports, generating mock bindings. | `py2rust main.py --mock-mode` |
| `--validate` | | Runs the LLM closed-loop equivalence validator on output. | `py2rust main.py --validate` |
| `--strict-validation` | | Aborts compiler process immediately if LLM validation fails. | `py2rust main.py --validate --strict-validation` |
| `--learn-patterns` | | Extracts and learns patterns from semantic validation failures. | `py2rust main.py --validate --learn-patterns` |
| `--apply-learned-patterns` | | Automatically applies learned pattern suggestions to output. | `py2rust main.py --apply-learned-patterns` |
| `--review-failures` | | Halts compilation on errors to present a detailed LLM-backed terminal dashboard. | `py2rust main.py --validate --review-failures` |
| `--verbose` | `-v` | Enables detailed logging of semantic and compilation phases. | `py2rust main.py -v` |

---

## 📝 Writing Valid Code (The Supported Subset)

`py2rust` is a **statically typed** subset compiler. Unlike standard Python, which is dynamic and permissive, `py2rust` strictly validates types and structures at compile-time to maintain Rust's safety and performance guarantees.

### 1. Mandatory Type Annotations
Every function parameter, return type, and declared variable **must** have an explicit, compile-time resolvable type annotation.

> [!IMPORTANT]
> Dynamic types like `Any` are strictly forbidden. Unannotated function parameters will trigger an `UnsupportedFeatureError`.

```python
# ❌ INVALID
def add(x, y):
    return x + y

# ✅ VALID
def add(x: int, y: int) -> int:
    return x + y
```

### 2. Supported Standard Types & Collections
The compiler automatically maps standard Python types to their high-performance Rust equivalents:

*   **Primitives**:
    *   `int` $\rightarrow$ `i32`
    *   `float` $\rightarrow$ `f64`
    *   `bool` $\rightarrow$ `bool`
    *   `str` $\rightarrow$ `String`
*   **Data Structures**:
    *   `list[T]` $\rightarrow$ `Vec<T>`
    *   `dict[K, V]` $\rightarrow$ `HashMap<K, V>`
    *   `set[T]` $\rightarrow$ `HashSet<T>`
    *   `tuple[T1, T2]` $\rightarrow$ `(T1, T2)`
    *   `deque[T]` $\rightarrow$ `VecDeque<T>` (Double-ended queue, importable from `collections`)
    *   `heap` $\rightarrow$ `BinaryHeap<Reverse<T>>` (Min-heap representation using `heapq` patterns)

```python
from collections import deque
import heapq

def manage_collections() -> int:
    # Double-ended Queue lowering
    queue: deque[int] = deque([1, 2, 3])
    queue.append(4)
    val: int = queue.popleft()
    
    # List and Dict lowering
    elements: list[str] = ["A", "B"]
    mapping: dict[str, int] = {"A": 100}
    
    return val
```

### 3. Suspending Coroutines & Generators (`yield` / `yield from`)
Suspendible generator functions containing `yield` or `yield from` are automatically compiled into custom state-machine structs implementing Rust’s standard `Iterator` trait.

```python
from typing import Generator

def countdown(start: int) -> Generator[int, None, None]:
    current: int = start
    while current > 0:
        yield current
        current -= 1
```

### 4. Automatic Scoped Resource Management (`with` / `async with`)
Context managers are lowered directly into scoped lexical blocks `{ ... }` in Rust, taking advantage of Rust's robust **RAII (Resource Acquisition Is Initialization)** drop mechanics for files, locks, and network handles.

```python
def read_config(path: str) -> str:
    # This is lowered to a scoped block, auto-closing the descriptor on drop
    with open(path, "r") as f:
        content: str = f.read()
    return content
```

### 5. Classes & Object-Oriented Patterns
`py2rust` supports structured OOP paradigms with explicit mapping to Rust `struct` and `impl` patterns.

*   **Classes & Constructor**: Translated to structs with associated `new()` functions.
*   **Protocols (`typing.Protocol`)**: Lowered directly to Rust `trait` declarations.
*   **Overloading**: Multiple methods can share a name, provided their parameter arity (argument count) is distinct.
*   **Decorators**: Supports standard built-in indicators:
    *   `@dataclass`: Generates fields and standard constructors.
    *   `@staticmethod`: Lowers to associated functions without `self`.
    *   `@classmethod`: Maps to associated constructor/builder functions.
    *   `@property`: Lowers to readable getter methods.

```python
from typing import Protocol

class Drawable(Protocol):
    def draw(self) -> None:
        ...

class Circle:
    radius: float
    
    def __init__(self, r: float) -> None:
        self.radius = r
        
    def draw(self) -> None:
        print("Drawing Circle")
```

---

## 🗂️ Workspace Imports & Module Resolution

`py2rust` supports enterprise, repository-scale multi-module compilation. 

### Module Search Path (`sys.path`)
By default, the compiler scans the active workspace. If you rely on external directories, you can define them in your environment or supply them to the compiler:
```bash
py2rust src/main.py --plugin-path ./custom_libs
```

### Circular Dependencies
> [!WARNING]
> Circular or recursive imports (e.g., `Module A` imports `Module B`, which imports `Module A`) will trigger an immediate dependency cycle exception during graph resolution. Keep your imports strictly hierarchical (directed acyclic graphs).

---

## 🔌 Interoperability with CPython Libraries (Plugins)

Want to run standard CPython libraries like `numpy` or `cv2` within your compiled Rust code? `py2rust` accomplishes this via a dedicated plugin layer.

By compiling with `--mock-mode`, `py2rust` automatically embeds Python runtimes into the target binary (using PyO3 bindings) to execute external dynamic Python scripts inside a secure, virtualized context.

### Usage Example
```python
import numpy as np

def calculate_mean() -> None:
    # Translated to PyO3 dynamic bindings
    arr = np.array([1.0, 2.0, 3.0])
    print(np.mean(arr))
```
Compile and run with a specific virtual environment:
```bash
# Compile wrapping foreign imports
py2rust compute.py -o compute.rs --mock-mode

# Execute with the virtual environment configuration
export PY2RUST_VENV=/home/user/my_project/.venv
cargo run
```

---

## 🤖 LLM Validator & Pattern Learning System

To ensure that your generated Rust matches the exact semantics of your input Python, `py2rust` offers an advanced **Closed-Loop Equivalence Validator** backed by local LLM orchestration, AST analysis, and interactive developer feedback.

```bash
py2rust input.py -o output.rs --validate --learn-patterns --apply-learned-patterns --review-failures
```

### 1. High-Performance SQLite Validation Cache (`validations.db`)
Equivalence checks on complex functions using LLMs can introduce latency. To prevent this, `py2rust` automatically maintains a durable SQLite database at `.py2rust/validations.db`.
* **Compound Hashing Strategy**: Instantly resolves hits by computing a compound SHA-256 hash from three inputs:
  $$\text{id} = \text{SHA-256}(\text{SHA-256}(\text{python\_source}) + \text{SHA-256}(\text{generated\_rust}) + \text{SHA-256}(\text{compiler\_config}))$$
* **High-Concurrency Modes**: Employs Write-Ahead Logging (WAL) journal mode to ensure thread-safe, fast cache queries and concurrent compilation steps.
* **Force Recompilation**: You can bypass the cache entirely to force a live LLM re-evaluation using the `--force` / `-f` CLI flag.

### 2. Neo Reasoning Patterns (`Qname`, `Qglobal_flow`, `Qcall`)
During lowered compilation, Python names are mangled, helper variables are added, and functions are adapted to support Rust’s ownership rules (e.g. `Result`-wrapping). To prevent the validator from flagging these safe transformations as errors, `py2rust` extracts AST-based metadata from your source code and injects steering patterns:
* `Qname(variable)`: Identifies variable references inside scopes to track rename mappings.
* `Qglobal_flow(symbol)`: Outlines scope modifications, ensuring function bounds remain structurally equivalent.
* `Qcall(function)`: Tracks function calls and signatures rewritten to match safe Rust implementations.

These indicators guide the local validator model (e.g., `deepseek-coder`) to recognize planned, correct modifications.

### 3. Human-in-the-Loop (HITL) Triage Dashboard
If a function fails semantic validation, the compiler can guide you through a live terminal dashboard to review the discrepancy and decide how to proceed. To activate it, pass the `--review-failures` flag during validation.

#### Available Actions:
* **`[a] Accept`**: Manually overrides and approves the current Rust code. It writes the result to the SQLite validation database with a special `is_hitl = 1` flag, preventing the compiler from flagging or asking about this function again in future builds.
* **`[e] Edit`**: Opens your system's default text editor (configured via `EDITOR`, e.g. `nano` or `vim`) with a temporary copy of the function segment so you can fix annotations or source logic immediately without terminating the pipeline.
* **`[r] Retry`**: Instantly triggers a fresh, live semantic evaluation from the validation model.
* **`[s] Skip`**: Safely bypasses the warning and proceeds with compilation.
* **`[q] Quit`**: Immediately terminates the compilation process.

### 4. 🛠️ Compiler & Cargo Error Recovery with Ollama Analysis
To assist developers during compilation and downstream verification, `py2rust` features robust, automated error recovery and semantic diagnostics analyzing systems when `--review-failures` is enabled and Ollama is available.

* **Downstream Cargo Check Failures**: If the generated Rust code fails `cargo check` validation (e.g. lifetime borrowing mismatch or syntax errors), the compiler intercepts `stderr`, packages the source and rust output, and queries Ollama. The local LLM explains the root cause in simple terms and provides a suggested Rust fix snippet.
* **Frontend Compilation Failures**: If `py2rust` encounters parsing, semantic validation, or type unification errors (`CompilerError`), the compiler intercepts the exception, gets the context, and queries the local LLM. Ollama suggests a valid, statically-compliant Python alternative to bypass the subset restriction.
* **Active Triage Console**: On interception, compilation halts and prints a clear markdown card with the LLM analysis, prompting you to either open `$EDITOR` on the fly to correct the python code (`[e] Edit`), retry the compilation step (`[r] Retry`), or exit.

---

## 🔍 Troubleshooting Compiler Errors

`py2rust` provides rich, readable diagnostics modeled after Rust's compiler output to help you quickly identify and fix issues.

### 1. `UnsupportedFeatureError`
Occurs when you attempt to compile a Python construct that is not supported by the static subset, such as ternary expressions:
```
UnsupportedFeatureError: math_utils.py:12:15: Ternary expressions (x if cond else y) are strictly rejected
  |     val = 10 if flag else 20
  |              ^
  hint: Replace with an explicit 'if/else' block statement
```

### 2. `SemanticError`
Occurs due to variable scoping, undefined names, or invalid imports:
```
SemanticError: solver.py:5:10: Undefined variable: 'data'
  |     print(data)
  |           ^
```

### 3. `TypeError`
Occurs when types cannot be unified:
```
TypeError: main.py:8:14: Mismatch: Cannot assign 'str' to variable declared as 'int'
  |     val: int = "hello"
  |                ^
```

---

## 💡 Pro Tips for Clean Compilation

1.  **Enable `--verify` Early**: Always run the compiler with the `--verify` flag when testing new code. This runs `rustc` to ensure that generated borrowing and lifetimes satisfy the borrow checker.
2.  **Explicit Scope Blocks**: When managing locks or files, wrap them in clean blocks `with open(...)` to control exactly when drop-mechanics free up resources.
3.  **Prefer Lists over Tuples for Modification**: Python tuples map to fixed-size Rust tuples. If you need dynamic resizing, append support, or index mutations, always use annotated `list[T]`.
4.  **Use `.rs` Code Formatting**: Let `rustfmt` format your code. Do not use `--no-format` unless you are debugging the raw, raw compiler generator.
