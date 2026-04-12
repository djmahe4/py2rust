from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Union


@dataclass(frozen=True)
class IRIntType:
    def __str__(self):
        return "i32"


@dataclass(frozen=True)
class IRFloatType:
    def __str__(self):
        return "f64"


@dataclass(frozen=True)
class IRBoolType:
    def __str__(self):
        return "bool"


@dataclass(frozen=True)
class IRStrType:
    def __str__(self):
        return "String"


@dataclass(frozen=True)
class IRListType:
    element_type: object

    def __str__(self):
        return f"Vec<{self.element_type}>"


IRType = Union[IRIntType, IRFloatType, IRBoolType, IRStrType, IRListType]


@dataclass(frozen=True)
class IRIntLit:
    value: int


@dataclass(frozen=True)
class IRFloatLit:
    value: float


@dataclass(frozen=True)
class IRBoolLit:
    value: bool


@dataclass(frozen=True)
class IRStrLit:
    value: str


@dataclass(frozen=True)
class IRName:
    name: str


@dataclass(frozen=True)
class IRBinOp:
    op: str
    left: object
    right: object
    result_type: object


@dataclass(frozen=True)
class IRUnaryOpExpr:
    op: str
    operand: object
    result_type: object


@dataclass(frozen=True)
class IRCompare:
    op: str
    left: object
    right: object


@dataclass(frozen=True)
class IRBoolOp:
    op: str
    values: tuple


@dataclass(frozen=True)
class IRListLit:
    elements: tuple
    element_type: object


@dataclass(frozen=True)
class IRSubscript:
    value: object
    index: object
    value_type: object
    result_type: object


@dataclass(frozen=True)
class IRFunctionCall:
    name: str
    args: tuple
    return_type: object


IRExpr = Union[
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
    IRSubscript,
    IRFunctionCall,
]


@dataclass(frozen=True)
class IRVarDecl:
    name: str
    type_: object
    value: object


@dataclass(frozen=True)
class IRAssign:
    target: str
    value: object


@dataclass(frozen=True)
class IRAugAssign:
    target: str
    op: str
    value: object


@dataclass(frozen=True)
class IRIf:
    condition: object
    then_body: tuple
    elif_clauses: tuple
    else_body: object


@dataclass(frozen=True)
class IRWhile:
    condition: object
    body: tuple
    label: str = ""


@dataclass(frozen=True)
class IRForRange:
    target: str
    start: object
    stop: object
    step: object
    body: tuple
    label: str = ""


@dataclass(frozen=True)
class IRReturn:
    value: object
    result_type: object = None


@dataclass(frozen=True)
class IRPrint:
    value: object
    value_type: object


@dataclass(frozen=True)
class IRBreak:
    label: str = ""


@dataclass(frozen=True)
class IRContinue:
    label: str = ""


IRStmt = Union[
    IRVarDecl,
    IRAssign,
    IRAugAssign,
    IRIf,
    IRWhile,
    IRForRange,
    IRReturn,
    IRPrint,
    IRBreak,
    IRContinue,
]


@dataclass(frozen=True)
class IRParam:
    name: str
    type_: object


@dataclass(frozen=True)
class IRSubscriptAssign:
    target: object
    index: object
    value: object
    value_type: object


@dataclass(frozen=True)
class IRFunction:
    name: str
    params: tuple
    return_type: object
    body: tuple
    mutated_params: tuple = ()


@dataclass(frozen=True)
class IRModule:
    functions: tuple
    filename: str = "<unknown>"
