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
class IRUnitType:
    def __str__(self):
        return "()"


@dataclass(frozen=True)
class IRListType:
    element_type: object

    def __str__(self):
        return f"Vec<{self.element_type}>"


@dataclass(frozen=True)
class IRDictType:
    key_type: object
    value_type: object


@dataclass(frozen=True)
class IRTupleType:
    element_types: tuple

    def __str__(self):
        types = ", ".join(str(t) for t in self.element_types)
        return f"({types})"


@dataclass(frozen=True)
class IRFileType:
    def __str__(self):
        return "FileHandle"


@dataclass(frozen=True)
class IRClassType:
    name: str
    base: Optional[str] = None
    fields: tuple = ()
    methods: tuple = ()

    def __str__(self):
        return self.name


IRType = Union[
    IRIntType,
    IRFloatType,
    IRBoolType,
    IRStrType,
    IRListType,
    IRDictType,
    IRTupleType,
    IRFileType,
    IRClassType,
]


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
class IRContains:
    item: object
    container: object
    container_type: object
    element_type: object


@dataclass(frozen=True)
class IRListLit:
    elements: tuple
    element_type: object


@dataclass(frozen=True)
class IRDictLit:
    pairs: tuple
    key_type: object
    value_type: object


@dataclass(frozen=True)
class IRTupleLit:
    elements: tuple
    element_types: tuple


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
    is_fallible: bool = True


@dataclass(frozen=True)
class IRFileOpen:
    path: object
    mode: object


@dataclass(frozen=True)
class IRFileMethod:
    file: object
    method: str
    args: tuple


@dataclass(frozen=True)
class IRStructLit:
    class_name: str
    field_values: tuple


@dataclass(frozen=True)
class IRStructAccess:
    value: object
    field: str
    result_type: object


@dataclass(frozen=True)
class IRMethodCall:
    value: object
    method: str
    args: tuple
    result_type: object
    is_fallible: bool = True
    mutates_self: bool = False


@dataclass(frozen=True)
class IRNew:
    class_name: str
    args: tuple


@dataclass(frozen=True)
class IRSelf:
    pass


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
    IRDictLit,
    IRContains,
    IRSubscript,
    IRFunctionCall,
    IRFileOpen,
    IRFileMethod,
    IRStructLit,
    IRStructAccess,
    IRMethodCall,
    IRNew,
    IRSelf,
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
class IRTupleUnpack:
    targets: tuple
    value: object


@dataclass(frozen=True)
class IRFieldAssign:
    obj: str
    field: str
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
class IRForIter:
    target: str
    iterable: object
    iterable_type: object
    body: tuple
    label: str = ""


@dataclass(frozen=True)
class IRTryExcept:
    body: tuple
    handlers: tuple # List of (exc_type, exc_name, body)


@dataclass(frozen=True)
class IRRaise:
    value: object


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


@dataclass(frozen=True)
class IRDictDelete:
    target: object
    key: object


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
    IRDictDelete,
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
    is_method: bool = False
    defining_class: Optional[str] = None


@dataclass(frozen=True)
class IRTraitMethod:
    name: str
    params: tuple
    return_type: object
    mutates_self: bool = False


@dataclass(frozen=True)
class IRTraitDefinition:
    name: str
    bases: tuple = ()
    methods: tuple = ()


@dataclass(frozen=True)
class IRClassDefinition:
    name: str
    bases: tuple = ()
    fields: tuple = ()
    methods: tuple = ()
    constructors: tuple = ()


@dataclass(frozen=True)
class IRModule:
    functions: tuple
    classes: tuple = ()
    traits: tuple = ()
    filename: str = "<unknown>"
