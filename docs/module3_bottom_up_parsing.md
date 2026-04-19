# Module 3: Bottom-Up Parsing

> A technical study guide grounded in the **py2rust** compiler implementation  
> _Compiler Design — Academic Reference Document_

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [The Compiler Frontend in py2rust](#the-compiler-frontend-in-py2rust)
3. [Handle Pruning](#1-handle-pruning)
4. [Shift-Reduce Parsing](#2-shift-reduce-parsing)
5. [Operator Precedence Parsing (Concept)](#3-operator-precedence-parsing)
6. [LR Parsing — Core Concepts](#4-lr-parsing--core-concepts)
   - [LR(0) Items and Closure](#41-lr0-items-and-closure)
   - [Constructing SLR Parsing Tables](#42-simple-lr-slr-parsing)
   - [Constructing LALR Parsing Tables](#43-lookahead-lr-lalr-parsing)
   - [Constructing Canonical LR(1) Tables](#44-canonical-lr1-parsing)
   - [Comparing SLR, LALR, and Canonical LR](#45-comparison-slr-vs-lalr-vs-canonical-lr1)
7. [py2rust Frontend: Where Bottom-Up Theory Is Applied](#py2rust-frontend-where-bottom-up-theory-is-applied)
8. [Summary Table](#summary-table)
9. [Glossary](#glossary)

---

## Executive Summary

Bottom-up parsing is the backbone of industrial-strength compiler front-ends. It constructs the parse tree from leaves to root — the exact reverse of derivation — and is the basis of all LR-family parsers that power real-world languages (C, C++, Java, and Python itself).

In **py2rust**, the frontend (`py2rust/frontend/parser.py`) does **not** manually implement an LR parser. Instead, it delegates tokenization and parsing entirely to **Python's built-in `ast` module**, which internally uses CPython's own LALR(1)-based parser (`pegen`). The `py2rust` `Parser` class is therefore a **semantic translator** built *on top of* the AST that CPython's bottom-up parser already produced.

This module studies the theoretical machinery — handles, shift-reduce automata, and LR table construction — that underlies this whole pipeline, and anchors each concept to where py2rust benefits from or interfaces with it.

---

## The Compiler Frontend in py2rust

```
Python Source File
       │
       ▼
  [CPython pegen]         ← LALR(1) bottom-up parser (built into Python)
       │  produces
       ▼
  Python AST (ast.Module)
       │
       ▼
  py2rust Parser           ← py2rust/frontend/parser.py
  (AST → py2rust AST)      Recursive-descent translator over CPython AST
       │  produces
       ▼
  py2rust Module           ← py2rust/frontend/ast_nodes.py
  (Module, FunctionDef, ClassDef, …)
       │
       ▼  IRBuilder
  IRModule                 ← py2rust/ir/ir_nodes.py
       │
       ▼  RustCodegen
  Rust Source Code
```

> [!IMPORTANT]
> CPython's `pegen` is an LR/PEG hybrid. When you write `ast.parse(source)` in `parser.py:153`, you are invoking a highly optimised bottom-up parser that has already handled all of Python's precedence, associativity, and shift-reduce conflicts for you.

---

## 1. Handle Pruning

### Theory

**Handle pruning** is the fundamental operation of bottom-up parsing. A **handle** is a specific substring `β` in the right-sentential form `αβδ` that matches the right-hand side of some production `A → β`, and reducing it to `A` is a valid step in the reverse rightmost derivation.

Formally, a handle is the triple `(A → β, k)` where `β` appears ending at position `k` in the current sentential form.

**Pruning** means:
1. Identify the handle `β`
2. Replace it with `A` (reduce)
3. Continue until you reach the start symbol

### Example

Grammar for arithmetic:
```
E → E + T  |  T
T → T * F  |  F
F → ( E )  |  id
```

Parsing `id + id * id` bottom-up:

| Stack          | Input           | Action |
|----------------|-----------------|--------|
| `$`            | `id + id * id$` | Shift `id` |
| `$ id`         | `+ id * id$`    | Reduce `F → id` |
| `$ F`          | `+ id * id$`    | Reduce `T → F` |
| `$ T`          | `+ id * id$`    | Reduce `E → T` |
| `$ E`          | `+ id * id$`    | Shift `+` |
| `$ E +`        | `id * id$`      | Shift `id` |
| `$ E + id`     | `* id$`         | Reduce `F → id` |
| `$ E + F`      | `* id$`         | Reduce `T → F` |
| `$ E + T`      | `* id$`         | Shift `*` (precedence: `*` > `+`) |
| `$ E + T *`    | `id$`           | Shift `id` |
| `$ E + T * id` | `$`             | Reduce `F → id` |
| `$ E + T * F`  | `$`             | Reduce `T → T * F` |
| `$ E + T`      | `$`             | Reduce `E → E + T` |
| `$ E`          | `$`             | **Accept** |

**The handle at each reduce step is identified by the parser's state machine**, not by searching the string.

### py2rust Connection

When CPython's parser processes:
```python
x: int = 2 + 3 * 4
```
It performs exactly this handle-pruning sequence on Python's grammar, reducing `3 * 4` (the handle matching `expr → expr * expr`) before `2 + ...`. The resulting AST node is:

```python
# What ast.parse delivers to py2rust Parser._parse_expr:
ast.BinOp(
    left=ast.Constant(2),
    op=ast.Add(),
    right=ast.BinOp(              # 3*4 was reduced first → nested deeper
        left=ast.Constant(3),
        op=ast.Mult(),
        right=ast.Constant(4)
    )
)
```

py2rust's `_parse_expr` at `parser.py:833` simply reads this already-reduced tree:
```python
if isinstance(node, ast.BinOp):
    op = _BINOP_MAP.get(type(node.op))   # {ast.Add: "+", ast.Mult: "*", ...}
    left  = self._parse_expr(node.left)
    right = self._parse_expr(node.right)
    return BinOp(op=op, left=left, right=right, ...)
```

The operator precedence is **baked into the tree structure** by the bottom-up parser; py2rust does not need to re-implement it.

---

## 2. Shift-Reduce Parsing

### Theory

A **shift-reduce parser** uses a stack and an input buffer. At each step it chooses between:

| Action | Description |
|--------|-------------|
| **Shift** | Push the next input token onto the stack |
| **Reduce** | Pop the handle off the stack, replace with the LHS non-terminal |
| **Accept** | Input is consumed, stack has only start symbol |
| **Error** | No valid action — syntax error |

The parser is guided by a **goto/action table** built from the grammar's LR automaton.

### Conflicts

Two fundamental conflict types arise in shift-reduce parsing:

| Conflict | When it occurs | Classic example |
|----------|---------------|-----------------|
| **Shift-Reduce conflict** | Parser can either shift or reduce at the same state | Dangling `else` |
| **Reduce-Reduce conflict** | Two different reductions are valid at same state | Ambiguous grammar |

**Dangling `else` example:**
```
if (cond1) if (cond2) stmt1 else stmt2
```
Should `else` be matched to the inner or outer `if`? — a classic shift-reduce conflict.

### Resolution: Shift Preference Policy

The standard resolution (used by all practical parsers including CPython's) is:
- **Prefer shift over reduce** in shift-reduce conflicts
- This correctly associates `else` with the nearest `if`

### py2rust Connection — `if`/`elif`/`else` Parsing

py2rust's `_parse_stmt` models the same resolution for Python's `if`/`elif`/`else` chains. The nested `orelse` attribute of `ast.If` encodes CPython's shift-preference: each `elif` is represented as a nested `ast.If` inside the outer `orelse`, mirroring how the LR parser shifted rather than reduced at each `elif` token.

```python
# parser.py:589-620
if isinstance(node, ast.If):
    cond      = self._parse_expr(node.test)
    then_body = tuple(self._parse_stmts(node.body))
    elif_clauses = []
    orelse = node.orelse                          # This nesting IS the
    while orelse:                                 # shift-preference result:
        if len(orelse) == 1 and isinstance(orelse[0], ast.If):
            elif_node = orelse[0]                 # each elif is a subtree
            elif_clauses.append((
                self._parse_expr(elif_node.test),
                tuple(self._parse_stmts(elif_node.body))
            ))
            orelse = elif_node.orelse             # walk the chain
        else:
            else_body = tuple(self._parse_stmts(orelse))
            break
```

The `while orelse` loop "unrolls" the left-to-right shift chain that CPython's parser produced.

---

## 3. Operator Precedence Parsing (Concept)

Operator precedence parsing is a simplified form of shift-reduce parsing for expression grammars. It only works for **operator grammars** (no two adjacent non-terminals in any production).

Three **precedence relations** are defined between terminal pairs `(a, b)`:

| Relation | Meaning |
|----------|---------|
| `a ⋖ b` | `a` **yields** precedence to `b` (shift `b`) |
| `a ≐ b` | `a` has the **same** precedence as `b` |
| `a ⋗ b` | `a` **takes** precedence over `b` (reduce on `a`) |

The **precedence table** for arithmetic:

|     | `+` | `-` | `*` | `/` | `(` | `)` | `id` | `$` |
|-----|-----|-----|-----|-----|-----|-----|------|-----|
| `+` | ⋗   | ⋗   | ⋖   | ⋖   | ⋖   | ⋗   | ⋖    | ⋗   |
| `*` | ⋗   | ⋗   | ⋗   | ⋗   | ⋖   | ⋗   | ⋖    | ⋗   |
| `(` | ⋖   | ⋖   | ⋖   | ⋖   | ⋖   | ≐   | ⋖    | —   |

### Limitations

- Cannot handle all grammars (only operator grammars)
- No explicit grammar is used; errors may be accepted silently
- **Not used in py2rust** — Python's full grammar requires the power of LR parsing

### py2rust Connection — `_BINOP_MAP`

The precedence of Python's binary operators is encoded in CPython's grammar productions themselves. py2rust only needs a flat **mapping** from CPython's already-precedence-resolved AST operator nodes to py2rust operator strings:

```python
# parser.py:92-99
_BINOP_MAP = {
    ast.Add:      "+",
    ast.Sub:      "-",
    ast.Mult:     "*",
    ast.Div:      "/",
    ast.FloorDiv: "//",
    ast.Mod:      "%",
}
```

No precedence table is needed in py2rust because operator precedence parsing was already done by CPython's LALR(1) parser. The nested AST structure *is* the precedence information.

---

## 4. LR Parsing — Core Concepts

**LR(k)** means: **L**eft-to-right scan, **R**ightmost derivation in reverse, **k** tokens of lookahead.

All LR parsers work with the same basic machinery:

1. A **deterministic finite automaton (DFA)** whose states are sets of **LR items**
2. An **ACTION table**: `(state, terminal) → shift | reduce | accept | error`
3. A **GOTO table**: `(state, non-terminal) → state` (for after a reduce)

### 4.1 LR(0) Items and Closure

An **LR(0) item** is a production with a **dot** marking how far parsing has progressed:
```
A → α • β
```
- Dot at the start `A → • α β` means: "We haven't started matching this production."
- Dot at the end `A → α β •` means: "We have completed this production — reduce!"

**CLOSURE** of a set of items: if `A → α • B β` is in the set, add all productions `B → • γ` (with dot at start).

**GOTO(I, X)**: Move the dot past `X` for every item in `I` where the dot precedes `X`.

These two operations construct the **canonical collection of LR(0) item sets** — the states of the LR automaton.

#### Example — Building States

Grammar:
```
S' → S
S  → C C
C  → c C | d
```

**State I₀** (start):
```
S' → • S
S  → • C C          (closure of S' → • S)
C  → • c C          (closure of S  → • C C)
C  → • d
```

**State I₁** = GOTO(I₀, S):
```
S' → S •            (ACCEPT)
```

**State I₂** = GOTO(I₀, C):
```
S  → C • C
C  → • c C
C  → • d
```

And so on. The full automaton produces all reachable states.

### 4.2 Simple LR (SLR) Parsing

**SLR** is the simplest, most space-efficient LR variant. It uses LR(0) items for state construction and resolves reduce decisions using **FOLLOW sets**.

#### Table Construction Algorithm

1. Build the canonical collection of LR(0) item sets {I₀, I₁, ..., Iₙ}
2. For each state Iᵢ:
   - If `A → α • a β ∈ Iᵢ` (a is terminal): `ACTION[i, a] = shift j` where `j = GOTO(i, a)`
   - If `A → α • ∈ Iᵢ` (reduce item) and `A ≠ S'`: `ACTION[i, a] = reduce A → α` for all `a ∈ FOLLOW(A)`
   - If `S' → S • ∈ Iᵢ`: `ACTION[i, $] = accept`
3. For each state and non-terminal: `GOTO[i, A] = j` if `GOTO(Iᵢ, A) = Iⱼ`

#### Weakness of SLR

SLR uses **FOLLOW(A)** — every terminal that can appear after `A` in *any* sentential form — as the lookahead for reductions. This is too broad and causes spurious reduce-reduce conflicts in grammars where the grammar is LR(1) but not SLR.

**Example of SLR inadequacy:**
```
S → L = R | R
L → * R | id
R → L
```
State Iχ contains:
- `R → L •`  (wants to reduce when `=` in FOLLOW(R)? Yes! But...)
- `S → L • = R`  (wants to shift `=`)

`=` ∈ FOLLOW(R) causes a **shift-reduce conflict** in SLR. The grammar IS LR(1) — LALR resolves this correctly.

### 4.3 Lookahead LR (LALR) Parsing

**LALR(1)** merges LR(1) states that have the same LR(0) core (ignoring lookaheads) but keeps the **lookaheads** to make finer reduce decisions.

#### Key Insight

LALR uses **LOOKAHEAD sets** per item, not the global FOLLOW set. For a reduce item `[A → α •, a]`:
- Reduce only when the current token equals `a`, not any token in FOLLOW(A)
- Lookahead `a` is propagated through the LR automaton precisely

#### LALR Table vs SLR

| Aspect | SLR | LALR |
|--------|-----|------|
| States | Same LR(0) states | Merged LR(1) states (same count as SLR) |
| Lookahead precision | FOLLOW(A) | Exact per-item lookahead sets |
| Grammar class | SLR(1) ⊂ LALR(1) | Most practical grammars |
| Table size | Identical to SLR | Identical to SLR (same state count) |

**CPython's `pegen` parser uses an LALR(1) strategy** (augmented with PEG memoization). This is why `ast.parse()` handles all valid Python without conflicts.

#### LALR Example — Fixing the C Grammar Conflict

The declaration/statement ambiguity in C:
```c
T → int | float
D → T id
S → T id = expr | expr
```
SLR would conflict when deciding whether `int id` starts a declaration or an assignment. LALR resolves this with exact lookaheads: `=` after seeing `int id` means shift (expression path); `;` or `)` means reduce (declaration path). The lookahead `=` is NOT in FOLLOW(D) globally but IS in the precise LALR lookahead set.

### 4.4 Canonical LR(1) Parsing

**Canonical LR(1)** uses **LR(1) items** — each item carries an explicit lookahead terminal:
```
[A → α • β, a]    -- reduce only when current token = a
```

The closure and GOTO operations are extended to propagate lookaheads precisely.

#### State Count vs LALR

Canonical LR(1) does **not merge states** with different lookaheads, so it may produce exponentially more states than LALR. For Python's grammar, this would be impractical.

| Feature | LALR(1) | Canonical LR(1) |
|---------|---------|-----------------|
| State count | = LR(0) states | Can be >> LALR |
| Grammar power | ≥ SLR, < LR(1) | Maximum LR power |
| Conflicts avoided | More than SLR | Zero for any LR(1) grammar |
| Practical use | **Industry standard** (yacc, bison, Python) | Rare (too many states) |

#### When Canonical LR(1) is needed

Only for grammars that are LR(1) but not LALR(1). In practice, language designers avoid this by restructuring the grammar.

### 4.5 Comparison: SLR vs LALR vs Canonical LR(1)

```
Grammar classes (power hierarchy):

    SLR(1) ⊂ LALR(1) ⊂ Canonical-LR(1) ⊂ All Context-Free Grammars

```

| Property | SLR(1) | LALR(1) | Canonical LR(1) |
|----------|--------|---------|-----------------|
| Lookahead source | FOLLOW(A) | Per-item propagation | Per-item exact |
| State count | Small | Small | Large |
| Conflicts | More | Fewer | Fewest in LR class |
| Tool examples | Simple parsers | yacc, bison, CPython pegen | GLR, Elkhound |
| Grammar coverage | Moderate | Most practical languages | Maximum |

---

## py2rust Frontend: Where Bottom-Up Theory Is Applied

The py2rust `Parser` class sits one level *above* the LR machinery. But every structural decision in `parser.py` reflects the theory:

### How py2rust Exploits CPython's LR Parser

**1. Precedence is structural, not explicit**

Because CPython's LALR(1) parser applied operator precedence during parsing, the `ast.BinOp` tree already encodes it. py2rust reads the pre-reduced tree:

```python
# parser.py:833-845
if isinstance(node, ast.BinOp):
    op = _BINOP_MAP.get(type(node.op))
    left  = self._parse_expr(node.left)   # deeper = higher precedence (reduced first)
    right = self._parse_expr(node.right)
    return BinOp(op=op, left=left, right=right, ...)
```

**2. Shift-preference for `elif`/`else`**

The AST's nested `orelse` chain is the direct output of CPython's shift-reduce automaton:

```python
# parser.py:595-609
orelse = node.orelse
while orelse:
    if len(orelse) == 1 and isinstance(orelse[0], ast.If):
        # CPython shifted the `elif` → nested ast.If
        elif_node = orelse[0]
        ...
```

**3. Type annotation parsing as operator grammar**

Type subscripts like `dict[str, list[int]]` are parsed as nested `ast.Subscript` nodes. py2rust handles this with a recursive descent that mirrors the structure produced by CPython's LR automaton:

```python
# parser.py:411-445
elif isinstance(node, ast.Subscript):
    if isinstance(node.value, ast.Name) and node.value.id in ("dict", "Dict"):
        if isinstance(node.slice, ast.Tuple):             # dict[K, V]
            key_type   = self._parse_type(node.slice.elts[0])
            value_type = self._parse_type(node.slice.elts[1])
            return DictType(key_type=key_type, value_type=value_type)
    if isinstance(node.value, ast.Name) and node.value.id in ("Optional",):
        inner = self._parse_type(node.slice)              # Optional[T]
        return OptionalType(inner_type=inner)
```

This recursive traversal is only possible because CPython's LALR parser already correctly handled the `[` and `]` bracket matching for subscript expressions.

**4. Error reporting with positions**

py2rust propagates line and column numbers from CPython AST nodes into its own AST nodes — metadata that CPython's parser recorded during the bottom-up scan:

```python
# parser.py:129-139
def _err(self, msg, node, cls=ParseError, suggestion=None):
    line = getattr(node, "lineno", 0)        # line number from LR scan
    col  = getattr(node, "col_offset", 0) + 1
    return cls(message=msg, filename=self.filename,
               line=line, column=col, ...)
```

### Full Pipeline State Machine (Conceptual LR DFA for Python Expressions)

```
States (conceptual):

I₀: S' → • expr $
    expr → • expr + term
    expr → • term
    term → • term * factor
    term → • factor
    factor → • ( expr )
    factor → • id
    factor → • IntLit
         ↓ shift id/int
I₁: factor → id •          ← REDUCE: F → id

         ↓ shift (
I₂: factor → ( • expr )
    [... inner expression states ...]
         ↓ shift )
I₃: factor → ( expr ) •    ← REDUCE: F → (E)

I₄: expr → expr • + term   ← SHIFT '+' ; else REDUCE
     ...
```

Python's operator precedence (`*` before `+`) emerges naturally: the state for `term → term • * factor` will shift `*` even when `+` is in the lookahead, because `*` appears in `term` productions (deeper level) than `+` which appears in `expr` (shallower). The LALR table encodes this automatically.

---

## Summary Table

| Concept | Theory | py2rust Mapping |
|---------|--------|-----------------|
| **Handle Pruning** | Identify & reduce rightmost handle in sentential form | Done by CPython's pegen; `_parse_expr` reads already-reduced tree |
| **Shift-Reduce Parsing** | Stack-based, choose shift or reduce at each step | `elif`/`else` nesting in parsed AST reflects shift-preference |
| **Shift-Reduce Conflict** | Same state allows both shift and reduce | `dangling else` — resolved by preferring shift (CPython) |
| **Operator Precedence** | Precedence table guides shift vs reduce for expressions | Encoded in Python grammar; `_BINOP_MAP` just names operators |
| **LR(0) Items** | Dot notation tracks parse progress in a production | States of CPython's internal DFA |
| **FOLLOW Set (SLR)** | All terminals that can follow A in sentential forms | Too coarse; Python uses LALR lookaheads instead |
| **SLR Parsing** | LR(0) states + FOLLOW for reduce decisions | Not used in CPython (LALR has fewer conflicts) |
| **LALR(1) Parsing** | Merge LR(1) states with same core; propagate lookaheads | **CPython pegen** — parses all Python source that py2rust receives |
| **Canonical LR(1)** | Full LR(1) items, no state merging — maximum power | Not needed for Python (LALR(1) suffices) |
| **Type annotation grammar** | Subscript productions `T → id '[' T ']'` | `_parse_type` processes the already-reduced `ast.Subscript` |

---

## Glossary

| Term | Definition |
|------|-----------|
| **Bottom-Up Parsing** | Constructing the parse tree from leaves to root — reducing handles until start symbol is reached |
| **Handle** | A substring of a right-sentential form that matches a production RHS, whose reduction is a step in reverse rightmost derivation |
| **Shift** | Push the next token onto the parser stack |
| **Reduce** | Pop the handle from the stack and replace with the production's LHS |
| **Viable Prefix** | A prefix of a right-sentential form that can appear on the LR parser stack without error |
| **LR(0) Item** | A production with a dot indicating parsing progress: `A → α • β` |
| **LR(1) Item** | LR(0) item with an explicit lookahead terminal: `[A → α • β, a]` |
| **CLOSURE** | Operation extending a set of items by adding items for symbols after the dot |
| **GOTO(I, X)** | Set of items reached by consuming symbol X from state I |
| **SLR** | Simple LR — uses FOLLOW sets for reduce decisions; simplest LR variant |
| **LALR** | Lookahead LR — merges LR(1) states with same core; used by yacc/bison/CPython |
| **Canonical LR(1)** | Full LR(1) parsing — maximum grammar power, but larger tables |
| **ACTION Table** | (state, terminal) → shift/reduce/accept/error |
| **GOTO Table** | (state, non-terminal) → new state after a reduce |
| **FOLLOW(A)** | Set of terminals that can appear immediately after non-terminal A in any sentential form |
| **Operator Grammar** | Grammar with no two adjacent non-terminals in any production; enables operator precedence parsing |
| **Dangling Else** | Classic shift-reduce conflict: `if C1 if C2 S1 else S2` — resolved by preferring shift |
| **pegen** | CPython's PEG-based parser generator (LALR-like); produces the `ast` module output |
| **`ast.parse()`** | Python stdlib function that invokes pegen and returns a fully-parsed AST |
