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
class IRSetType:
    element_type: object

@dataclass(frozen=True)
class IRUnknownType:
    def __str__(self):
        return "_"


@dataclass(frozen=True)
class IREnumType:
    name: str

    def __str__(self):
        return self.name


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


@dataclass(frozen=True)
class IRFunctionType:
    param_types: tuple
    return_type: object

    def __str__(self):
        params = ", ".join(str(t) for t in self.param_types)
        return f"fn({params}) -> {self.return_type}"


@dataclass(frozen=True)
class IRExternalPythonType:
    module: str
    name: Optional[str] = None

    def __str__(self):
        return f"PyObject({self.module}.{self.name if self.name else ''})"


@dataclass(frozen=True)
class IRTypeParam:
    name: str
    bound: Optional[object] = None

    def __str__(self):
        if self.bound:
            return f"{self.name}: {self.bound}"
        return self.name


@dataclass(frozen=True)
class IRGenericType:
    base: object
    params: tuple

    def __str__(self):
        params = ", ".join(str(p) for p in self.params)
        return f"{self.base}<{params}>"


IRType = Union[
    IRTypeParam,
    IRGenericType,
    IRIntType,
    IRFloatType,
    IRBoolType,
    IRStrType,
    IRListType,
    IRDictType,
    IRSetType,
    IRTupleType,
    IRFileType,
    IRClassType,
    IRFunctionType,
    IREnumType,
    IRUnknownType,
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
    result_type: Optional[IRType] = None


@dataclass(frozen=True)
class IRBinOp:
    op: str
    left: object
    right: object
    result_type: object
    # (trait_name, method_name) if it maps to a Rust trait (e.g., ("Add", "add"))
    trait_info: Optional[tuple[str, str]] = None


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
    result_type: Optional[object] = None


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
    # (trait_name, method_name) if it maps to a Rust trait (e.g., ("Index", "index"))
    trait_info: Optional[tuple[str, str]] = None


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


@dataclass(frozen=True)
class IRAwait:
    value: object
    result_type: object

@dataclass(frozen=True)
class IRLambda:
    params: tuple  # tuple of IRParam
    body: IRExpr
    result_type: object  # Functional type


@dataclass(frozen=True)
class IRComprehension:
    target: object  # IRName or IRTupleLit
    iterable: IRExpr
    ifs: tuple  # tuple of IRExpr
    is_async: bool = False


@dataclass(frozen=True)
class IRListComp:
    elt: IRExpr
    generators: tuple  # tuple of IRComprehension
    result_type: object


@dataclass(frozen=True)
class IRDictComp:
    key: IRExpr
    value: IRExpr
    generators: tuple
    result_type: object


@dataclass(frozen=True)
class IRSetComp:
    elt: IRExpr
    generators: tuple
    result_type: object


@dataclass(frozen=True)
class IRMatchPattern:
    pass


@dataclass(frozen=True)
class IRValuePattern(IRMatchPattern):
    value: IRExpr


@dataclass(frozen=True)
class IRNamePattern(IRMatchPattern):
    name: str


@dataclass(frozen=True)
class IRClassPattern(IRMatchPattern):
    class_name: str
    patterns: tuple


@dataclass(frozen=True)
class IRWildcardPattern(IRMatchPattern):
    pass


@dataclass(frozen=True)
class IROrPattern(IRMatchPattern):
    patterns: tuple


@dataclass(frozen=True)
class IRAsPattern(IRMatchPattern):
    pattern: IRMatchPattern
    name: str


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
    target: object
    start: object
    stop: object
    step: object
    body: tuple
    label: str = ""


@dataclass(frozen=True)
class IRForIter:
    target: object
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
    cause: object = None


@dataclass(frozen=True)
class IRReturn:
    value: object
    result_type: object = None


@dataclass(frozen=True)
class IRPrint:
    values: tuple
    value_types: tuple
    sep: Optional[object] = None # IRExpr
    end: Optional[object] = None # IRExpr


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


@dataclass(frozen=True)
class IRWithItem:
    context_expr: IRExpr
    optional_vars: Optional[IRExpr] = None


@dataclass(frozen=True)
class IRWith:
    items: tuple  # tuple of IRWithItem
    body: tuple  # tuple of IRStmt
    is_async: bool = False


@dataclass(frozen=True)
class IRAssert:
    test: IRExpr
    msg: Optional[IRExpr] = None


@dataclass(frozen=True)
class IRGlobal:
    names: tuple  # tuple of str


@dataclass(frozen=True)
class IRNonlocal:
    names: tuple  # tuple of str


@dataclass(frozen=True)
class IRMatchStmt:
    subject: IRExpr
    cases: tuple


@dataclass(frozen=True)
class IRMatchCase:
    pattern: IRMatchPattern
    guard: Optional[IRExpr]
    body: tuple


@dataclass(frozen=True)
class IREnumDef:
    name: str
    variants: tuple


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
    # (trait_name, method_name) if it maps to a Rust trait (e.g., ("IndexMut", "index_mut"))
    trait_info: Optional[tuple[str, str]] = None


@dataclass(frozen=True)
class IRFunction:
    name: str
    params: tuple
    return_type: object
    body: tuple
    mutated_params: tuple = ()
    is_async: bool = False
    is_method: bool = False
    defining_class: Optional[str] = None
    type_params: tuple = ()


@dataclass(frozen=True)
class IRTraitMethod:
    name: str
    params: tuple
    return_type: object
    is_async: bool = False
    mutates_self: bool = False


@dataclass(frozen=True)
class IRFormattedValue:
    value: object # IRExpr
    conversion: int = -1
    format_spec: Optional[str] = None


@dataclass(frozen=True)
class IRJoinedStr:
    values: tuple  # tuple of IRFormattedValue or IRStrLit


@dataclass(frozen=True)
class IRTraitDefinition:
    name: str
    bases: tuple = ()
    methods: tuple = ()
    type_params: tuple = ()


@dataclass(frozen=True)
class IRTraitImpl:
    trait_name: str
    target_name: str
    methods: tuple = ()
    type_params: tuple = ()


@dataclass(frozen=True)
class IRClassDefinition:
    name: str
    bases: tuple = ()
    fields: tuple = ()
    methods: tuple = ()
    constructors: tuple = ()
    type_params: tuple = ()


@dataclass(frozen=True)
class IRModule:
    functions: tuple
    classes: tuple = ()
    enums: tuple = ()
    traits: tuple = ()
    trait_impls: tuple = ()
    statements: tuple = ()
    filename: str = "<unknown>"


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
    IRTupleLit,
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
    IRAwait,
    IRLambda,
    IRListComp,
    IRDictComp,
    IRSetComp,
    IRJoinedStr,
    IRFormattedValue,
    IRExternalPythonType,
]

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
    IRMatchStmt,
    IREnumDef,
    IRTryExcept,
    IRRaise,
    IRWith,
    IRAssert,
    IRGlobal,
    IRNonlocal,
]
