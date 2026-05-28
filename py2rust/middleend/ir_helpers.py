from __future__ import annotations
from typing import Optional

from ..frontend.ast_nodes import (
    IntType,
    FloatType,
    BoolType,
    StrType,
    UnitType,
    ListType,
    DictType,
    FileType,
    ClassType,
    TupleType,
    EnumType,
    SetType,
    FunctionType,
    UnknownType,
    ExternalPythonType,
    TypeVarType,
    GenericType,
    OptionalType,
    UnionType,
    SliceType,
    IteratorType,
    IterableType,
    GeneratorType,
    DequeType,
    HeapType,
)

from ..ir.ir_nodes import (
    IRIntType,
    IRFloatType,
    IRBoolType,
    IRStrType,
    IRUnitType,
    IRListType,
    IRDictType,
    IRTupleType,
    IRSetType,
    IRFunctionType,
    IRFileType,
    IROptionType,
    IRClassType,
    IRExternalPythonType,
    IRUnknownType,
    IRIntLit,
    IRFloatLit,
    IRBoolLit,
    IRStrLit,
    IRFormattedValue,
    IRJoinedStr,
    IRName,
    IRSome,
    IRSumWrap,
    IRSumType,
    IRNoneLit,
    IRBinOp,
    IRUnaryOpExpr,
    IRIsInstance,
    IRCompare,
    IRBoolOp,
    IRListLit,
    IRDictLit,
    IRContains,
    IRSlice,
    IRSliceType,
    IRDequeType,
    IRHeapType,
    IRSubscript,
    IRSubscriptAssign,
    IRFunctionCall,
    IRFileOpen,
    IRFileMethod,
    IRVarDecl,
    IRAssign,
    IRFieldAssign,
    IRAugAssign,
    IRIf,
    IRWhile,
    IRForRange,
    IRForIter,
    IRReturn,
    IRPrint,
    IRBreak,
    IRContinue,
    IRTraitDefinition,
    IRTraitImpl,
    IRTraitMethod,
    IRDictDelete,
    IRStructLit,
    IRStructAccess,
    IRMethodCall,
    IRNew,
    IRSelf,
    IRTupleLit,
    IRTupleUnpack,
    IRTypeParam,
    IRGenericType,
    IRTryExcept,
    IRRaise,
    IRClassDefinition,
    IRAwait,
    IREnumType,
    IREnumDef,
    IRMatchStmt,
    IRMatchCase,
    IRMatchPattern,
    IRValuePattern,
    IRNamePattern,
    IRClassPattern,
    IRWildcardPattern,
    IROrPattern,
    IRAsPattern,
    IRLambda,
    IRMap,
    IRFilter,
    IRSorted,
    IRReduce,
    IRComprehension,
    IRListComp,
    IRDictComp,
    IRSetComp,
    IRWith,
    IRWithItem,
    IRAssert,
    IRGlobal,
    IRNonlocal,
    IRExternalPythonType,
    IROptionType,
    IRSumType,
    IRType,
    IRYield,
    IRYieldFrom,
    IRGeneratorExp,
    IRIteratorType,
    IRIterableType,
    IRGeneratorType,
)

from ..utils.errors import SemanticError

from .type_mapping import map_type_to_ir

def _to_ir_type(t):
    try:
        return map_type_to_ir(t)
    except ValueError as e:
        raise SemanticError(str(e))

_MUTEX_NAMES = frozenset({
    "Mutex", "Lock", "RwLock", "Semaphore", "Condition",
    "threading.Lock", "threading.RLock", "threading.Semaphore",
    "threading.Condition", "asyncio.Lock", "asyncio.Semaphore"
})

def _is_mutex_like(name: str) -> bool:
    """Return True if the type name looks like a mutex/lock synchronisation primitive."""
    return name in _MUTEX_NAMES or any(
        name.endswith(suffix) for suffix in ("Lock", "Mutex", "RwLock", "Semaphore", "Guard")
    )

def _is_main_check(expr) -> bool:
    """Check if an expression is __name__ == '__main__'."""
    if type(expr).__name__ == "Comparison":
        if getattr(expr, "op", "") == "==":
            left = getattr(expr, "left", None)
            right = getattr(expr, "right", None)
            
            # Check for: __name__ == "__main__"
            if type(left).__name__ == "Name" and getattr(left, "name", "") == "__name__":
                if type(right).__name__ == "StrLiteral" and getattr(right, "value", "") == "__main__":
                    return True
            # Also check: "__main__" == __name__
            if type(right).__name__ == "Name" and getattr(right, "name", "") == "__name__":
                if type(left).__name__ == "StrLiteral" and getattr(left, "value", "") == "__main__":
                    return True
    return False

def _is_param_mutated(stmts, param_name) -> bool:
    """Check if a parameter is mutated anywhere in the function body."""
    for stmt in stmts:
        if _stmt_mutates(stmt, param_name):
            return True
    return False

def _stmt_mutates(stmt, var_name) -> bool:
    """Check if a statement mutates a variable."""
    if isinstance(stmt, IRAssign) and stmt.target == var_name:
        return True
    if isinstance(stmt, IRAugAssign) and stmt.target == var_name:
        return True
    if isinstance(stmt, IRSubscriptAssign):
        if isinstance(stmt.target, IRSubscript) and isinstance(stmt.target.value, IRName):
            if stmt.target.value.name == var_name:
                return True
        elif isinstance(stmt.target, IRName) and stmt.target.name == var_name:
            return True

    if isinstance(stmt, IRIf):
        return (
            _any_stmt_mutates(stmt.then_body, var_name)
            or any(_any_stmt_mutates(b, var_name) for _, b in stmt.elif_clauses)
            or (stmt.else_body and _any_stmt_mutates(stmt.else_body, var_name))
        )
    if isinstance(stmt, IRWhile):
        return _any_stmt_mutates(stmt.body, var_name)
    if isinstance(stmt, IRForRange):
        if stmt.target == var_name:
            return True
        return _any_stmt_mutates(stmt.body, var_name)
    if isinstance(stmt, IRForIter):
        if stmt.target == var_name:
            return True
        return _any_stmt_mutates(stmt.body, var_name)
    return False

def _any_stmt_mutates(stmts, var_name) -> bool:
    """Check if any statement in a list mutates a variable."""
    return any(_stmt_mutates(s, var_name) for s in stmts)
