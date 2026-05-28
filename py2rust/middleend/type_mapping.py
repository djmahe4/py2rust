from __future__ import annotations
from typing import Dict, Type, Any

from ..frontend.ast_nodes import (
    IntType, FloatType, BoolType, StrType, UnitType, ListType, DictType, SetType,
    FileType, ClassType, EnumType, TupleType, TypeVarType, GenericType,
    ExternalPythonType, OptionalType, UnionType, SliceType, IteratorType,
    IterableType, GeneratorType, DequeType, HeapType, UnknownType, FunctionType
)

from ..ir.ir_nodes import (
    IRIntType, IRFloatType, IRBoolType, IRStrType, IRUnitType, IRListType,
    IRDictType, IRSetType, IRFileType, IRClassType, IREnumType, IRTupleType,
    IRTypeParam, IRGenericType, IRExternalPythonType, IROptionType, IRSumType,
    IRSliceType, IRIteratorType, IRIterableType, IRGeneratorType, IRDequeType,
    IRHeapType, IRFunctionType
)

# Central mapping of AST type classes to IR type classes
AST_TO_IR_CLASSES: Dict[Type, Type] = {
    IntType: IRIntType,
    FloatType: IRFloatType,
    BoolType: IRBoolType,
    StrType: IRStrType,
    UnitType: IRUnitType,
    FileType: IRFileType,
    SliceType: IRSliceType,
    ListType: IRListType,
    DequeType: IRDequeType,
    HeapType: IRHeapType,
    SetType: IRSetType,
    IteratorType: IRIteratorType,
    IterableType: IRIterableType,
    DictType: IRDictType,
    ClassType: IRClassType,
    EnumType: IREnumType,
    TupleType: IRTupleType,
    TypeVarType: IRTypeParam,
    GenericType: IRGenericType,
    ExternalPythonType: IRExternalPythonType,
    OptionalType: IROptionType,
    UnionType: IRSumType,
    GeneratorType: IRGeneratorType,
    FunctionType: IRFunctionType
}

# Reverse mapping for symmetry
IR_TO_AST_CLASSES: Dict[Type, Type] = {v: k for k, v in AST_TO_IR_CLASSES.items()}

# Set of all known IR type classes for quick checks
ALL_IR_TYPE_CLASSES = frozenset(AST_TO_IR_CLASSES.values())

def map_type_to_ir(t: Any) -> Any:
    """
    Centralized resolver that converts any frontend AST Type representation
    to its corresponding middleend IR Type representation.
    """
    if isinstance(t, str):
        return IRClassType(name=t)
    if t is None:
        return IRUnitType()
    
    # If it's already an IR type or subclass of it, return it directly
    if type(t) in ALL_IR_TYPE_CLASSES:
        return t
        
    t_type = type(t)
    if t_type in AST_TO_IR_CLASSES:
        ir_class = AST_TO_IR_CLASSES[t_type]
        
        # Dispatch based on structural parameters
        if t_type in (IntType, FloatType, BoolType, StrType, UnitType, FileType, SliceType):
            return ir_class()
        elif t_type in (ListType, DequeType, HeapType, SetType, IteratorType, IterableType):
            return ir_class(element_type=map_type_to_ir(t.element_type))
        elif t_type is DictType:
            return ir_class(
                key_type=map_type_to_ir(t.key_type),
                value_type=map_type_to_ir(t.value_type)
            )
        elif t_type is ClassType:
            return ir_class(name=t.name, base=t.base)
        elif t_type is EnumType:
            return ir_class(name=t.name)
        elif t_type is TupleType:
            return ir_class(element_types=tuple(map_type_to_ir(et) for et in t.element_types))
        elif t_type is TypeVarType:
            return ir_class(name=t.name)
        elif t_type is GenericType:
            return ir_class(
                base=map_type_to_ir(t.base),
                params=tuple(map_type_to_ir(p) for p in t.params)
            )
        elif t_type is ExternalPythonType:
            return ir_class(module=t.module, name=t.name, is_local=t.is_local)
        elif t_type is OptionalType:
            return ir_class(inner_type=map_type_to_ir(t.inner_type))
        elif t_type is UnionType:
            return ir_class(variants=tuple(map_type_to_ir(v) for v in t.variants))
        elif t_type is GeneratorType:
            return ir_class(
                yield_type=map_type_to_ir(t.yield_type),
                send_type=map_type_to_ir(t.send_type),
                return_type=map_type_to_ir(t.return_type)
            )
        elif t_type is FunctionType:
            return ir_class(
                param_types=tuple(map_type_to_ir(pt) for pt in t.param_types),
                return_type=map_type_to_ir(t.return_type)
            )
            
    if isinstance(t, UnknownType):
        return IRIntType()
        
    raise ValueError(f"Unknown type: {t}")
