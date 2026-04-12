from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Union


@dataclass(frozen=True)
class IntType:
    def __str__(self):
        return "int"


@dataclass(frozen=True)
class FloatType:
    def __str__(self):
        return "float"


@dataclass(frozen=True)
class BoolType:
    def __str__(self):
        return "bool"


@dataclass(frozen=True)
class StrType:
    def __str__(self):
        return "str"


@dataclass(frozen=True)
class UnitType:
    def __str__(self):
        return "None"


@dataclass(frozen=True)
class ListType:
    element_type: object

    def __str__(self):
        return f"list[{self.element_type}]"


@dataclass(frozen=True)
class DictType:
    key_type: object
    value_type: object

    def __str__(self):
        return f"dict[{self.key_type}, {self.value_type}]"


@dataclass(frozen=True)
class FileType:
    def __str__(self):
        return "FileHandle"


@dataclass(frozen=True)
class ClassType:
    name: str
    base: Optional[str] = None

    def __str__(self):
        if self.base:
            return f"{self.name} ({self.base})"
        return self.name


AnyType = Union[
    IntType, FloatType, BoolType, StrType, ListType, DictType, FileType, ClassType
]


@dataclass(frozen=True)
class IntLiteral:
    value: int
    line: int = 0
    col: int = 0


@dataclass(frozen=True)
class FloatLiteral:
    value: float
    line: int = 0
    col: int = 0


@dataclass(frozen=True)
class BoolLiteral:
    value: bool
    line: int = 0
    col: int = 0


@dataclass(frozen=True)
class StrLiteral:
    value: str
    line: int = 0
    col: int = 0


@dataclass(frozen=True)
class Name:
    name: str
    line: int = 0
    col: int = 0


@dataclass(frozen=True)
class BinOp:
    op: str
    left: object
    right: object
    line: int = 0
    col: int = 0


@dataclass(frozen=True)
class UnaryOp:
    op: str
    operand: object
    line: int = 0
    col: int = 0


@dataclass(frozen=True)
class Comparison:
    op: str
    left: object
    right: object
    line: int = 0
    col: int = 0


@dataclass(frozen=True)
class BoolOp:
    op: str
    values: tuple
    line: int = 0
    col: int = 0


@dataclass(frozen=True)
class ListLiteral:
    elements: tuple
    line: int = 0
    col: int = 0


@dataclass(frozen=True)
class DictLiteral:
    pairs: tuple
    line: int = 0
    col: int = 0


@dataclass(frozen=True)
class Subscript:
    value: object
    index: object
    line: int = 0
    col: int = 0


@dataclass(frozen=True)
class FunctionCall:
    name: str
    args: tuple
    line: int = 0
    col: int = 0


@dataclass(frozen=True)
class AttributeExpr:
    value: object
    attr: str
    line: int = 0
    col: int = 0


@dataclass(frozen=True)
class MethodCall:
    value: object
    method: str
    args: tuple
    line: int = 0
    col: int = 0


@dataclass(frozen=True)
class NewExpr:
    class_name: str
    args: tuple
    line: int = 0
    col: int = 0


@dataclass(frozen=True)
class SelfExpr:
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
    FunctionCall,
    AttributeExpr,
    MethodCall,
    NewExpr,
    SelfExpr,
]


@dataclass(frozen=True)
class VarDecl:
    name: str
    type_annotation: object
    value: object
    line: int = 0
    col: int = 0


@dataclass(frozen=True)
class Assign:
    target: Union[str, tuple]
    value: object
    line: int = 0
    col: int = 0


@dataclass(frozen=True)
class AugAssign:
    target: str
    op: str
    value: object
    line: int = 0
    col: int = 0


@dataclass(frozen=True)
class IfStmt:
    condition: object
    then_body: tuple
    elif_clauses: tuple
    else_body: object
    line: int = 0
    col: int = 0


@dataclass(frozen=True)
class WhileStmt:
    condition: object
    body: tuple
    line: int = 0
    col: int = 0


@dataclass(frozen=True)
class ForRangeStmt:
    target: str
    start: object
    stop: object
    step: object
    body: tuple
    line: int = 0
    col: int = 0


@dataclass(frozen=True)
class ReturnStmt:
    value: object
    line: int = 0
    col: int = 0


@dataclass(frozen=True)
class PrintStmt:
    value: object
    line: int = 0
    col: int = 0


@dataclass(frozen=True)
class SubscriptAssign:
    target: object
    index: object
    value: object
    line: int = 0
    col: int = 0


@dataclass(frozen=True)
class BreakStmt:
    line: int = 0
    col: int = 0


@dataclass(frozen=True)
class ContinueStmt:
    line: int = 0
    col: int = 0


@dataclass(frozen=True)
class DelStmt:
    target: object
    key: object
    line: int = 0
    col: int = 0


Stmt = Union[
    VarDecl,
    Assign,
    AugAssign,
    IfStmt,
    WhileStmt,
    ForRangeStmt,
    ReturnStmt,
    PrintStmt,
    SubscriptAssign,
    BreakStmt,
    ContinueStmt,
    DelStmt,
]


@dataclass(frozen=True)
class Param:
    name: str
    type_annotation: object
    line: int = 0
    col: int = 0


@dataclass(frozen=True)
class FunctionDef:
    name: str
    params: tuple
    return_type: object
    body: tuple
    line: int = 0
    col: int = 0


@dataclass(frozen=True)
class ClassDef:
    name: str
    base: Optional[str] = None
    body: tuple = ()
    line: int = 0
    col: int = 0


@dataclass(frozen=True)
class Module:
    functions: tuple
    classes: tuple = ()
    filename: str = "<unknown>"
