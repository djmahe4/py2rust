from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Union


@dataclass
class IntType:
    def __str__(self):
        return "int"


@dataclass
class FloatType:
    def __str__(self):
        return "float"


@dataclass
class BoolType:
    def __str__(self):
        return "bool"


@dataclass
class StrType:
    def __str__(self):
        return "str"


@dataclass
class UnitType:
    def __str__(self):
        return "None"


@dataclass
class ListType:
    element_type: object

    def __str__(self):
        return f"list[{self.element_type}]"


@dataclass
class DequeType:
    element_type: object

    def __str__(self):
        return f"deque[{self.element_type}]"


@dataclass
class HeapType:
    element_type: object

    def __str__(self):
        return f"heap[{self.element_type}]"


@dataclass
class DictType:
    key_type: object
    value_type: object

    def __str__(self):
        return f"dict[{self.key_type}, {self.value_type}]"


@dataclass
class TupleType:
    element_types: tuple

    def __str__(self):
        types = ", ".join(str(t) for t in self.element_types)
        return f"tuple[{types}]"


@dataclass
class SliceType:
    def __str__(self):
        return "slice"


@dataclass
class FileType:
    def __str__(self):
        return "FileHandle"


@dataclass
class ClassType:
    name: str
    base: Optional[str] = None

    def __str__(self):
        if self.base:
            return f"{self.name} ({self.base})"
        return self.name


@dataclass
class EnumType:
    name: str

    def __str__(self):
        return f"Enum({self.name})"


@dataclass
class SetType:
    element_type: object

    def __str__(self):
        return f"set[{self.element_type}]"


@dataclass
class OptionalType:
    inner_type: object

    def __str__(self):
        return f"Optional[{self.inner_type}]"


@dataclass
class UnionType:
    variants: tuple

    def __str__(self):
        variants = ", ".join(str(v) for v in self.variants)
        return f"Union[{variants}]"


@dataclass
class FunctionType:
    param_types: tuple
    return_type: object

    def __str__(self):
        params = ", ".join(str(t) for t in self.param_types)
        return f"({params}) -> {self.return_type}"

@dataclass
class TypeVarType:
    name: str
    bound: Optional[object] = None

    def __str__(self):
        return self.name


@dataclass
class GenericType:
    base: object
    params: tuple

    def __str__(self):
        params = ", ".join(str(p) for p in self.params)
        return f"{self.base}[{params}]"

@dataclass
class UnknownType:
    def __str__(self):
        return "Unknown"


@dataclass
class ExternalPythonType:
    module: str
    name: Optional[str] = None
    is_local: bool = False

    def __str__(self):
        if self.name:
            return f"py({self.module}.{self.name})"
        return f"py({self.module})"


AnyType = Union[
    IntType,
    FloatType,
    BoolType,
    StrType,
    ListType,
    DictType,
    SetType,
    TupleType,
    FileType,
    ClassType,
    EnumType,
    UnknownType,
    FunctionType,
    ExternalPythonType,
    OptionalType,
    UnionType,
    SliceType,
    DequeType,
    HeapType,
]


@dataclass
class IntLiteral:
    value: int
    line: int = 0
    col: int = 0


@dataclass
class FloatLiteral:
    value: float
    line: int = 0
    col: int = 0


@dataclass
class BoolLiteral:
    value: bool
    line: int = 0
    col: int = 0


@dataclass
class StrLiteral:
    value: str
    line: int = 0
    col: int = 0


@dataclass
class Name:
    name: str
    inferred_type: Optional[AnyType] = None
    line: int = 0
    col: int = 0


@dataclass
class BinOp:
    op: str
    left: object
    right: object
    line: int = 0
    col: int = 0


@dataclass
class UnaryOp:
    op: str
    operand: object
    line: int = 0
    col: int = 0


@dataclass
class Comparison:
    op: str
    left: object
    right: object
    line: int = 0
    col: int = 0


@dataclass
class BoolOp:
    op: str
    values: tuple
    line: int = 0
    col: int = 0


@dataclass
class ListLiteral:
    elements: tuple  # tuple of Expr
    inferred_type: Optional[AnyType] = None
    line: int = 0
    col: int = 0


@dataclass
class TupleLiteral:
    elements: tuple
    line: int = 0
    col: int = 0


@dataclass
class DictLiteral:
    pairs: tuple
    line: int = 0
    col: int = 0


@dataclass
class Subscript:
    value: object
    index: object
    line: int = 0
    col: int = 0


@dataclass
class Slice:
    lower: Optional[object] = None
    upper: Optional[object] = None
    step: Optional[object] = None
    line: int = 0
    col: int = 0


@dataclass
class FunctionCall:
    name: str
    args: tuple
    line: int = 0
    col: int = 0


@dataclass
class AttributeExpr:
    value: object
    attr: str
    line: int = 0
    col: int = 0


@dataclass
class MethodCall:
    value: object
    method: str
    args: tuple
    line: int = 0
    col: int = 0


@dataclass
class NewExpr:
    class_name: str
    args: tuple
    line: int = 0
    col: int = 0


@dataclass
class SelfExpr:
    line: int = 0
    col: int = 0


@dataclass
class AwaitExpr:
    value:object
    line: int = 0
    col: int = 0

@dataclass
class LambdaExpr:
    params: tuple  # tuple of Param
    body: Expr
    line: int = 0
    col: int = 0


@dataclass
class Comprehension:
    target: object  # Name or TupleLiteral
    iterable: Expr
    ifs: tuple  # tuple of Expr
    is_async: bool = False
    line: int = 0
    col: int = 0


@dataclass
class ListComp:
    elt: Expr
    generators: tuple  # tuple of Comprehension
    line: int = 0
    col: int = 0


@dataclass
class DictComp:
    key: Expr
    value: Expr
    generators: tuple
    line: int = 0
    col: int = 0


@dataclass
class SetComp:
    elt: Expr
    generators: tuple
    line: int = 0
    col: int = 0


@dataclass
class FormattedValue:
    value: Expr
    conversion: int = -1
    format_spec: Optional[str] = None
    line: int = 0
    col: int = 0


@dataclass
class JoinedStr:
    values: tuple  # tuple of FormattedValue or StrLiteral
    line: int = 0
    col: int = 0


Expr = Union[
    IntLiteral,
    FloatLiteral,
    BoolLiteral,
    StrLiteral,
    Name,
    BinOp,
    UnaryOp,
    Comparison,
    BoolOp,
    ListLiteral,
    DictLiteral,
    Subscript,
    Slice,
    FunctionCall,
    AttributeExpr,
    MethodCall,
    NewExpr,
    SelfExpr,
    TupleLiteral,
    AwaitExpr,
    LambdaExpr,
    ListComp,
    DictComp,
    SetComp,
    JoinedStr,
    FormattedValue,
]


@dataclass
class MatchPattern:
    pass


@dataclass
class ValuePattern(MatchPattern):
    value: Expr
    line: int = 0
    col: int = 0


@dataclass
class NamePattern(MatchPattern):
    name: str
    line: int = 0
    col: int = 0


@dataclass
class ClassPattern(MatchPattern):
    class_name: str
    patterns: tuple  # tuple of MatchPattern
    line: int = 0
    col: int = 0


@dataclass
class WildcardPattern(MatchPattern):
    line: int = 0
    col: int = 0


@dataclass
class OrPattern(MatchPattern):
    patterns: tuple
    line: int = 0
    col: int = 0


@dataclass
class AsPattern(MatchPattern):
    pattern: MatchPattern
    name: str
    line: int = 0
    col: int = 0


@dataclass
class VarDecl:
    name: str
    type_annotation: object
    value: object
    line: int = 0
    col: int = 0


@dataclass
class Assign:
    target: Union[str, tuple]
    value: object
    line: int = 0
    col: int = 0


@dataclass
class AugAssign:
    target: str
    op: str
    value: object
    line: int = 0
    col: int = 0


@dataclass
class IfStmt:
    condition: object
    then_body: tuple
    elif_clauses: tuple
    else_body: object
    line: int = 0
    col: int = 0


@dataclass
class WhileStmt:
    condition: object
    body: tuple
    line: int = 0
    col: int = 0


@dataclass
class ForRange:
    target: str
    start: object
    stop: object
    step: object
    body: tuple
    line: int = 0
    col: int = 0


@dataclass
class ForIter:
    target: str
    iterable: object
    body: tuple
    line: int = 0
    col: int = 0


@dataclass
class ReturnStmt:
    value: object
    line: int = 0
    col: int = 0


@dataclass
class PrintStmt:
    values: tuple
    sep: Optional[object] = None # Expr
    end: Optional[object] = None # Expr
    line: int = 0
    col: int = 0


@dataclass
class SubscriptAssign:
    target: object
    index: object
    value: object
    line: int = 0
    col: int = 0


@dataclass
class BreakStmt:
    line: int = 0
    col: int = 0


@dataclass
class PassStmt:
    line: int = 0
    col: int = 0


@dataclass
class ContinueStmt:
    line: int = 0
    col: int = 0


@dataclass
class DelStmt:
    target: object
    key: object
    line: int = 0
    col: int = 0


@dataclass
class TryStmt:
    body: tuple
    handlers: tuple  # tuple of (type, name, body)
    line: int = 0
    col: int = 0


@dataclass
class RaiseStmt:
    value: object
    cause: object = None
    line: int = 0
    col: int = 0

@dataclass
class MatchStmt:
    subject: Expr
    cases: tuple  # tuple of MatchCase
    line: int = 0
    col: int = 0


@dataclass
class MatchCase:
    pattern: MatchPattern
    guard: Optional[Expr]
    body: tuple
    line: int = 0
    col: int = 0


@dataclass
class EnumDef:
    name: str
    variants: tuple  # tuple of (name, value)
    line: int = 0
    col: int = 0


@dataclass
class Alias:
    name: str
    asname: Optional[str] = None


@dataclass
class Import:
    names: tuple  # tuple of Alias
    line: int = 0
    col: int = 0


@dataclass
class ImportFrom:
    module: Optional[str]
    names: tuple  # tuple of Alias
    level: int = 0
    line: int = 0
    col: int = 0


@dataclass
class WithItem:
    context_expr: object # Expr
    optional_vars: Optional[object] = None # Name or Tuple/List of Name
    line: int = 0
    col: int = 0


@dataclass
class WithStmt:
    items: tuple # tuple of WithItem
    body: tuple # tuple of Stmt
    is_async: bool = False
    line: int = 0
    col: int = 0


@dataclass
class AssertStmt:
    test: object # Expr
    msg: Optional[object] = None # Expr
    line: int = 0
    col: int = 0


@dataclass
class GlobalStmt:
    names: tuple # tuple of str
    line: int = 0
    col: int = 0


@dataclass
class NonlocalStmt:
    names: tuple # tuple of str
    line: int = 0
    col: int = 0


Stmt = Union[
    VarDecl,
    Assign,
    AugAssign,
    IfStmt,
    WhileStmt,
    ForRange,
    ReturnStmt,
    PrintStmt,
    SubscriptAssign,
    BreakStmt,
    ContinueStmt,
    DelStmt,
    ForIter,
    TryStmt,
    RaiseStmt,
    MatchStmt,
    EnumDef,
    PassStmt,
    Import,
    ImportFrom,
    WithStmt,
    AssertStmt,
    GlobalStmt,
    NonlocalStmt,
]


@dataclass
class Param:
    name: str
    type_annotation: object
    line: int = 0
    col: int = 0


@dataclass
class FunctionDef:
    name: str
    params: tuple
    return_type: object
    body: tuple
    is_async: bool = False
    type_params: tuple = ()
    decorator_list: tuple = ()  # Wave 28: list of decorator name strings
    is_static: bool = False      # Wave 28: desugared from @staticmethod
    is_classmethod: bool = False # Wave 28: desugared from @classmethod
    line: int = 0
    col: int = 0


@dataclass
class ClassDef:
    name: str
    bases: tuple = ()
    body: tuple = ()
    type_params: tuple = ()
    decorator_list: tuple = ()  # Wave 28: list of decorator name strings
    line: int = 0
    col: int = 0



@dataclass
class Module:
    functions: tuple
    classes: tuple = ()
    enums: tuple = ()
    imports: tuple = ()
    statements: tuple = ()
    filename: str = "<unknown>"
