from __future__ import annotations
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
    ClassDef,
    TryStmt,
    RaiseStmt,
    FunctionDef,
    AttributeExpr,
    MethodCall,
    SelfExpr,
    NewExpr,
    AwaitExpr,
    EnumType,
    SetType,
    FunctionType,
    UnknownType,
    EnumDef,
    MatchStmt,
    MatchCase,
    MatchPattern,
    ValuePattern,
    NamePattern,
    ClassPattern,
    WildcardPattern,
    OrPattern,
    AsPattern,
    LambdaExpr,
    ListComp,
    DictComp,
    SetComp,
    Name,
    TupleLiteral,
    TypeVarType,
    GenericType,
    Subscript,
    SubscriptAssign,
    Assign,
    AugAssign,
)
from ..ir.ir_nodes import (
    IRModule,
    IRFunction,
    IRParam,
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
    IRClassType,
    IRUnknownType,
    IRIntLit,
    IRFloatLit,
    IRBoolLit,
    IRStrLit,
    IRFormattedValue,
    IRJoinedStr,
    IRName,
    IRBinOp,
    IRUnaryOpExpr,
    IRCompare,
    IRBoolOp,
    IRListLit,
    IRDictLit,
    IRContains,
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
    IRComprehension,
    IRListComp,
    IRDictComp,
    IRSetComp,
)
from ..utils.errors import SemanticError
from .symbol_table import SymbolTable
from .type_inferencer import TypeInferencer
from .type_checker import TypeChecker


def _to_ir_type(t):
    if isinstance(t, str):
        return IRClassType(name=t)
    if t is None:
        return IRUnitType()
    # If already an IR type, return as is
    if isinstance(t, (IRIntType, IRFloatType, IRBoolType, IRStrType, IRUnitType, IRListType, IRDictType, IRTupleType, IRFileType, IRClassType, IREnumType, IRTypeParam, IRGenericType)):
        return t
        
    if isinstance(t, IntType):
        return IRIntType()
    if isinstance(t, FloatType):
        return IRFloatType()
    if isinstance(t, BoolType):
        return IRBoolType()
    if isinstance(t, StrType):
        return IRStrType()
    if isinstance(t, UnitType):
        return IRUnitType()
    if isinstance(t, ListType):
        return IRListType(element_type=_to_ir_type(t.element_type))
    if isinstance(t, DictType):
        return IRDictType(
            key_type=_to_ir_type(t.key_type),
            value_type=_to_ir_type(t.value_type),
        )
    if isinstance(t, FileType):
        return IRFileType()
    if isinstance(t, ClassType):
        return IRClassType(name=t.name, base=t.base)
    if isinstance(t, EnumType):
        return IREnumType(name=t.name)
    if isinstance(t, SetType):
        return IRSetType(element_type=_to_ir_type(t.element_type))
    if isinstance(t, FunctionType):
        return IRFunctionType(
            param_types=tuple(_to_ir_type(pt) for pt in t.param_types),
            return_type=_to_ir_type(t.return_type),
        )
    if isinstance(t, UnknownType):
        return IRIntType()  # Default to i32 for unknown types
    if isinstance(t, TupleType):
        return IRTupleType(element_types=tuple(_to_ir_type(et) for et in t.element_types))
    if isinstance(t, TypeVarType):
        return IRTypeParam(name=t.name)
    if isinstance(t, GenericType):
        return IRGenericType(base=_to_ir_type(t.base), params=tuple(_to_ir_type(p) for p in t.params))
    raise SemanticError(f"Unknown type: {t}")


class IRBuilder:
    def __init__(self, filename: str = "<unknown>", source_lines: list = None, symbol_table: SymbolTable = None):
        self.filename = filename
        self.source_lines = source_lines or []
        self.st = symbol_table or SymbolTable()
        if symbol_table is None:
            # Add basic exception types if we created a new symbol table
            for exc in ["Exception", "ValueError", "TypeError", "KeyError", "IndexError"]:
                self.st.define_class(exc, (), {}, {}, {})
                # Also define as functions
                self.st.define_function(exc, [StrType()], ClassType(exc))
        
        self.inferencer = TypeInferencer(self.st)
        self._loop_stack: list = []
        self._mutating_methods: set = set()  # (class_name, method_name, arity)
        self._ir_traits: list = []
        self._ir_trait_impls: list = []
        self._ir_classes: list = []
        self._ir_enums: list = []

    def _err(self, msg: str, line: int = 0, col: int = 0) -> SemanticError:
        return SemanticError(
            message=msg,
            filename=self.filename,
            line=line,
            column=col,
            source_lines=self.source_lines,
        )

    def build(self, module) -> IRModule:
        checker = TypeChecker(self.st, self.filename, self.source_lines)
        checker.check_module(module)

        self._ir_classes = []
        self._ir_enums = []
        # Discovery all types
        self._build_all_types(module.classes)
        self._build_all_types(module.enums)
        for func in module.functions:
            self._build_all_types(func.body, prefix=f"{func.name}_")

        ir_funcs = []
        for func in module.functions:
            ir_funcs.append(self._build_function(func))
        return IRModule(
            functions=tuple(ir_funcs),
            classes=tuple(self._ir_classes),
            enums=tuple(self._ir_enums),
            traits=tuple(self._ir_traits),
            trait_impls=tuple(self._ir_trait_impls),
            filename=module.filename,
        )

    def _build_all_types(self, items, prefix="") -> None:
        for item in items:
            if isinstance(item, ClassDef):
                full_name = f"{prefix}{item.name}"
                is_protocol = any(b == "Protocol" for b in item.bases)
                if is_protocol:
                    self._build_protocol(item, prefix=prefix)
                else:
                    ir_cls = self._build_class(item, prefix=prefix)
                    self._ir_classes.append(ir_cls)
                self._build_all_types(item.body, prefix=f"{full_name}_")
            elif isinstance(item, EnumDef):
                ir_enum = self._build_enum(item, prefix=prefix)
                self._ir_enums.append(ir_enum)
            elif isinstance(item, FunctionDef):
                self._build_all_types(item.body, prefix=f"{prefix}{item.name}_")

    def _build_enum(self, node: EnumDef, prefix="") -> IREnumDef:
        full_name = f"{prefix}{node.name}"
        ir_variants = []
        for name, val_expr in node.variants:
            ir_val = self._build_expr(val_expr) if val_expr else None
            ir_variants.append((name, ir_val))
        return IREnumDef(name=full_name, variants=tuple(ir_variants))

    def _build_protocol(self, cls, prefix="") -> None:
        from ..frontend.ast_nodes import FunctionDef
        full_name = f"{prefix}{cls.name}"
        trait_methods = []
        st_methods = {}
        for item in cls.body:
            if type(item).__name__ == "FunctionDef":
                arity = len(item.params)
                ir_t_meth = self._build_trait_method(item)
                trait_methods.append(ir_t_meth)
                
                # Register in symbol table
                arg_types = [p.type_annotation for p in item.params]
                ret_type = item.return_type
                if item.name not in st_methods:
                    st_methods[item.name] = {}
                st_methods[item.name][arity] = (item, (arg_types, ret_type))
        
        self.st.define_trait(full_name, cls.bases, st_methods)
        self._ir_traits.append(IRTraitDefinition(
            name=full_name,
            bases=tuple(b for b in cls.bases if b != "Protocol"),
            methods=tuple(trait_methods)
        ))

    def _check_and_register_trait_impls(self, class_name: str, methods: dict) -> None:
        """Link a class to any traits it structurally implements."""
        for trait_name, trait_info in self.st._traits.items():
            if trait_name == "Protocol":
                continue
            
            # Check if class has all required methods with matching arity
            implements = True
            impl_methods = []
            for m_name, arities in trait_info.methods.items():
                if not any((m_name, arity) in methods for arity in arities):
                    implements = False
                    break
                else:
                    # Collect the actual IR functions for the impl block
                    for arity in arities:
                        if (m_name, arity) in methods:
                            impl_methods.append(methods[(m_name, arity)])

            if implements:
                self._ir_trait_impls.append(
                    IRTraitImpl(trait_name=trait_name, target_name=class_name, methods=tuple(impl_methods)),
                )

    def _build_class(self, cls: ClassDef, prefix="") -> IRClassDefinition:
        full_name = f"{prefix}{cls.name}"
        all_fields = {}
        all_methods = {}
        all_constructors = {}

        # 1. Gather all fields and methods from SymbolTable (includes discovered ones)
        info = self.st.lookup_class(full_name)
        if info:
            for f_name, f_type in info.fields.items():
                all_fields[f_name] = _to_ir_type(f_type)

        # 2. Inherit from base classes and local items
        for base_name in cls.bases:
            base_info = self.st.lookup_class(base_name)
            if base_info:
                # Fields
                for f_name, f_type in base_info.fields.items():
                    all_fields[f_name] = _to_ir_type(f_type)
                
                # Methods
                for m_name, arities in base_info.methods.items():
                    for arity, method_info in arities.items():
                        m_def, origin = method_info
                        # Rebuild in child context, preserving original defining class
                        all_methods[(m_name, arity)] = self._build_method(full_name, m_def, defining_class=origin)

                # Constructors
                for arity, c_def in base_info.constructors.items():
                    all_constructors[arity] = self._build_method(full_name, c_def)

        # 2. Add local items
        # Define nested classes in this scope for resolution
        for item in cls.body:
            if isinstance(item, ClassDef):
                self.st.define(item.name, ClassType(name=f"{full_name}_{item.name}"))

        for item in cls.body:
            if hasattr(item, "__class__"):
                item_name = type(item).__name__
                if item_name == "VarDecl":
                    all_fields[item.name] = _to_ir_type(item.type_annotation)
                elif item_name == "FunctionDef":
                    arity = len(item.params)
                    ir_func = self._build_method(full_name, item)
                    if item.name == "__init__":
                        all_constructors[arity] = ir_func
                    else:
                        # Override parent's method with same name and arity
                        all_methods[(item.name, arity)] = ir_func

        # 3. Generate Trait Definition
        trait_methods = []
        # Only include local non-init methods in the class's own trait?
        # No, for the Hybrid model, every class gets a trait.
        # But if it inherits, the trait should eventually include all methods?
        # Actually, let's make trait methods match local definitions.
        # Find which methods are already in the base traits to avoid re-defining them in the sub-trait
        base_trait_methods = set()
        for base_name in cls.bases:
            base_info = self.st.lookup_class(base_name)
            if base_info:
                # Recursively gather all inherited method names
                def gather_methods(c_info):
                    names = set(c_info.methods.keys())
                    for b_name in c_info.bases:
                        b_info = self.st.lookup_class(b_name)
                        if b_info: names.update(gather_methods(b_info))
                    return names
                base_trait_methods.update(gather_methods(base_info))

        for item in cls.body:
            if isinstance(item, FunctionDef) and item.name != "__init__":
                if item.name not in base_trait_methods:
                    trait_methods.append(self._build_trait_method(item))

        trait_def = IRTraitDefinition(
            name=f"{full_name}Trait",
            bases=tuple(f"{b}Trait" for b in cls.bases),
            methods=tuple(trait_methods)
        )
        self._ir_traits.append(trait_def)

        # 4. Ensure at least one constructor exists (default __init__)
        if not all_constructors:
            all_constructors[0] = IRFunction(
                name="__init__",
                params=(),
                return_type=IRUnitType(),
                body=(),
                is_method=True,
                defining_class=full_name
            )


        # Type params
        type_params = tuple(IRTypeParam(name=tp) for tp in cls.type_params)

        res = IRClassDefinition(
            name=full_name,
            bases=cls.bases,
            fields=tuple(all_fields.items()),
            methods=tuple(all_methods.values()),
            constructors=tuple(all_constructors.values()),
            type_params=type_params,
        )
        
        # Link to traits
        self._check_and_register_trait_impls(full_name, all_methods)
        
        return res

    def _build_trait_method(self, func) -> IRTraitMethod:
        from ..ir.ir_nodes import IRTraitMethod
        params = []
        for p in func.params:
            params.append(IRParam(name=p.name, type_=_to_ir_type(p.type_annotation)))
        
        # Check if it mutates self (approximation for trait signature)
        mutates = self._check_mutates_self(func.body)
        return IRTraitMethod(
            name=func.name,
            params=tuple(params),
            return_type=_to_ir_type(func.return_type),
            is_async=func.is_async,
            mutates_self=mutates
        )

    def _check_mutates_self(self, body) -> bool:
        """Check if any statement in a method mutates self."""
        for stmt in body:
            if isinstance(stmt, Assign):
                if (isinstance(stmt.target, AttributeExpr) and 
                    (isinstance(stmt.target.value, SelfExpr) or (isinstance(stmt.target.value, Name) and stmt.target.value.name == "self"))):
                    return True
                if isinstance(stmt.target, tuple) and len(stmt.target) > 0 and stmt.target[0] == "attr":
                    if stmt.target[1] == "self":
                        return True
            elif isinstance(stmt, AugAssign):
                if (isinstance(stmt.target, AttributeExpr) and 
                    (isinstance(stmt.target.value, SelfExpr) or (isinstance(stmt.target.value, Name) and stmt.target.value.name == "self"))):
                    return True
                if isinstance(stmt.target, tuple) and len(stmt.target) > 0 and stmt.target[0] == "attr":
                    if stmt.target[1] == "self":
                        return True
                # Simpler check for AugAssign target
                if isinstance(stmt.target, str) and stmt.target.startswith("self."):
                    return True

            elif isinstance(stmt, SubscriptAssign):
                # Check for deep targets
                curr = stmt.target
                if (isinstance(curr, AttributeExpr) and 
                    (isinstance(curr.value, SelfExpr) or (isinstance(curr.value, Name) and curr.value.name == "self"))):
                    return True
                while isinstance(curr, (AttributeExpr, Subscript)):
                    if isinstance(curr, AttributeExpr):
                        if isinstance(curr.value, SelfExpr) or (isinstance(curr.value, Name) and curr.value.name == "self"):
                            return True
                        curr = curr.value
                    elif isinstance(curr, Subscript):
                        curr = curr.value

            # Recursively check blocks
            if hasattr(stmt, "body") and stmt.body:
                if self._check_mutates_self(stmt.body):
                    return True
            if hasattr(stmt, "elif_clauses"):
                for _, elif_body in stmt.elif_clauses:
                    if self._check_mutates_self(elif_body):
                        return True
            if hasattr(stmt, "else_body") and stmt.else_body:
                if self._check_mutates_self(stmt.else_body):
                    return True
        return False

    def _build_method(self, class_name: str, func, defining_class: Optional[str] = None) -> IRFunction:
        self.st.enter_scope(f"{class_name}.{func.name}")
        self.st.define("self", ClassType(name=class_name))

        params = []
        for p in func.params:
            ir_t = _to_ir_type(p.type_annotation)
            self.st.define(p.name, p.type_annotation)
            params.append(IRParam(name=p.name, type_=ir_t))

        ret_type = _to_ir_type(func.return_type)
        body = self._build_stmts(func.body, ret_type)

        mutated_params = tuple(
            n for n in [p.name for p in func.params] if self._is_param_mutated(body, n)
        )

        if self._check_mutates_self(func.body):
            self._mutating_methods.add((class_name, func.name, len(func.params)))

        self.st.exit_scope()
        return IRFunction(
            name=func.name,
            params=tuple(params),
            return_type=ret_type,
            body=tuple(body),
            mutated_params=mutated_params,
            is_async=func.is_async,
            is_method=True,
            defining_class=defining_class or class_name
        )

    def _build_function(self, func) -> IRFunction:
        self.st.enter_scope(func.name)

        params = []
        param_names = []
        for p in func.params:
            ir_t = _to_ir_type(p.type_annotation)
            self.st.define(p.name, p.type_annotation)
            params.append(IRParam(name=p.name, type_=ir_t))
            param_names.append(p.name)

        ret_type = _to_ir_type(func.return_type)

        # Define local classes in this function scope for resolution
        for item in func.body:
            if isinstance(item, ClassDef):
                self.st.define(item.name, ClassType(name=f"{self.st.current_scope.name}_{item.name}"))

        body = self._build_stmts(func.body, ret_type)

        mutated_params = tuple(
            n for n in param_names if self._is_param_mutated(body, n)
        )

        # Type params
        type_params = tuple(IRTypeParam(name=tp) for tp in func.type_params)

        self.st.exit_scope()
        return IRFunction(
            name=func.name,
            params=tuple(params),
            return_type=ret_type,
            body=tuple(body),
            mutated_params=mutated_params,
            is_async=func.is_async,
            type_params=type_params,
        )

    def _is_param_mutated(self, stmts, param_name) -> bool:
        """Check if a parameter is mutated anywhere in the function body."""
        for stmt in stmts:
            if self._stmt_mutates(stmt, param_name):
                return True
        return False

    def _stmt_mutates(self, stmt, var_name) -> bool:
        """Check if a statement mutates a variable."""
        if isinstance(stmt, IRAssign) and stmt.target == var_name:
            return True
        if isinstance(stmt, IRAugAssign) and stmt.target == var_name:
            return True
        if isinstance(stmt, IRSubscriptAssign):
            # If target is indexing 'var_name', then 'var_name' is mutated
            if isinstance(stmt.target, IRSubscript) and isinstance(stmt.target.value, IRName):
                if stmt.target.value.name == var_name:
                    return True
            elif isinstance(stmt.target, IRName) and stmt.target.name == var_name:
                return True

        if isinstance(stmt, IRIf):
            return (
                self._any_stmt_mutates(stmt.then_body, var_name)
                or any(self._any_stmt_mutates(b, var_name) for _, b in stmt.elif_clauses)
                or (stmt.else_body and self._any_stmt_mutates(stmt.else_body, var_name))
            )
        if isinstance(stmt, IRWhile):
            return self._any_stmt_mutates(stmt.body, var_name)
        if isinstance(stmt, IRForRange):
            if stmt.target == var_name:
                return True
            return self._any_stmt_mutates(stmt.body, var_name)
        if isinstance(stmt, IRForIter):
            if stmt.target == var_name:
                return True
            return self._any_stmt_mutates(stmt.body, var_name)
        return False

    def _any_stmt_mutates(self, stmts, var_name) -> bool:
        """Check if any statement in a list mutates a variable."""
        return any(self._stmt_mutates(s, var_name) for s in stmts)

    def _build_stmts(self, stmts, return_type=None) -> list:
        res = [self._build_stmt(s, return_type) for s in stmts]
        return [r for r in res if r is not None]

    def _build_stmt(self, stmt, return_type=None):
        name = type(stmt).__name__

        if name == "VarDecl":
            inferred = self.inferencer.infer(stmt.value)
            ann = stmt.type_annotation
            actual_type = ann if ann is not None else inferred
            if actual_type is None:
                raise self._err(
                    f"Cannot determine type for '{stmt.name}'", stmt.line, stmt.col
                )
            ir_type = _to_ir_type(actual_type)
            self.st.define(stmt.name, actual_type)
            ir_val = self._build_expr(stmt.value, expected_type=ir_type)
            return IRVarDecl(name=stmt.name, type_=ir_type, value=ir_val)

        elif name == "Assign":
            if isinstance(stmt.target, tuple) and len(stmt.target) > 0 and stmt.target[0] == "attr":
                _, obj_name, field_name = stmt.target
                val = self._build_expr(stmt.value)
                return IRFieldAssign(obj=obj_name, field=field_name, value=val)
            
            if isinstance(stmt.target, tuple):
                # Unpacking assignment
                val = self._build_expr(stmt.value)
                val_t = self.inferencer.infer(stmt.value)
                
                # Define each target in symbol table
                if isinstance(val_t, TupleType):
                    for i, target_name in enumerate(stmt.target):
                        self.st.define(target_name, val_t.element_types[i])
                else:
                    # Best effort if type info is missing
                    for target_name in stmt.target:
                        self.st.define(target_name, IntType())
                
                return IRTupleUnpack(targets=stmt.target, value=val)

            if stmt.target == "_":
                ir_val = self._build_expr(stmt.value)
                return IRVarDecl(name="_", type_=IRIntType(), value=ir_val)
            existing = self.st.lookup(stmt.target)
            inferred = self.inferencer.infer(stmt.value)

            if existing is None:
                if inferred is None:
                    raise self._err(
                        f"Cannot determine type for '{stmt.target}'",
                        stmt.line,
                        stmt.col,
                    )
                self.st.define(stmt.target, inferred)
                ir_type = _to_ir_type(inferred)
                ir_val = self._build_expr(stmt.value, expected_type=ir_type)
                return IRVarDecl(name=stmt.target, type_=ir_type, value=ir_val)

            ir_type = _to_ir_type(existing)
            ir_val = self._build_expr(stmt.value, expected_type=ir_type)
            return IRAssign(target=stmt.target, value=ir_val)

        elif name == "AugAssign":
            existing = self.st.lookup(stmt.target)
            if existing is None:
                raise self._err(
                    f"Undefined variable '{stmt.target}'", stmt.line, stmt.col
                )
            ir_type = _to_ir_type(existing)
            ir_val = self._build_expr(stmt.value, expected_type=ir_type)
            return IRAugAssign(target=stmt.target, op=stmt.op, value=ir_val)

        elif name == "IfStmt":
            cond = self._build_expr(stmt.condition)
            then_body = tuple(self._build_stmts(stmt.then_body, return_type))
            elif_clauses = tuple(
                (self._build_expr(c), tuple(self._build_stmts(b, return_type)))
                for c, b in stmt.elif_clauses
            )
            else_body = (
                tuple(self._build_stmts(stmt.else_body, return_type))
                if stmt.else_body
                else None
            )
            return IRIf(
                condition=cond,
                then_body=then_body,
                elif_clauses=elif_clauses,
                else_body=else_body,
            )

        elif name == "WhileStmt":
            label = f"__loop_{len(self._loop_stack)}"
            self._loop_stack.append(label)
            cond = self._build_expr(stmt.condition)
            body = tuple(self._build_stmts(stmt.body, return_type))
            self._loop_stack.pop()
            return IRWhile(condition=cond, body=body, label=label)

        elif name == "ForRange":
            label = f"__loop_{len(self._loop_stack)}"
            self._loop_stack.append(label)
            
            # Extract name and define in symbol table
            target_name = stmt.target.name if isinstance(stmt.target, (Name, IRName)) else stmt.target
            self.st.define(target_name, IntType())
            
            # Create IR target (IRName)
            ir_target = self._build_comp_target(stmt.target)
            
            start = self._build_expr(stmt.start)
            stop = self._build_expr(stmt.stop)
            step = self._build_expr(stmt.step) if stmt.step else None
            body = tuple(self._build_stmts(stmt.body, return_type))
            self._loop_stack.pop()
            return IRForRange(
                target=ir_target,
                start=start,
                stop=stop,
                step=step,
                body=body,
                label=label,
            )

        elif name == "ForIter":
            label = f"__loop_{len(self._loop_stack)}"
            self._loop_stack.append(label)
            
            iterable_type = self.inferencer.infer(stmt.iterable)
            ir_iter_type = _to_ir_type(iterable_type) if iterable_type else None
            
            # Define target in symbol table
            elem_type = IntType() # Default
            if isinstance(iterable_type, ListType):
                elem_type = iterable_type.element_type
            elif isinstance(iterable_type, DictType):
                elem_type = iterable_type.key_type
            elif isinstance(iterable_type, StrType):
                elem_type = StrType()
            
            self._bind_target(stmt.target, elem_type)
            
            target = self._build_comp_target(stmt.target)
            iterable = self._build_expr(stmt.iterable)
            body = tuple(self._build_stmts(stmt.body, return_type))
            self._loop_stack.pop()
            
            return IRForIter(
                target=target,
                iterable=iterable,
                iterable_type=ir_iter_type,
                body=body,
                label=label,
            )

        elif name == "ReturnStmt":
            val = self._build_expr(stmt.value, return_type) if stmt.value else None
            return IRReturn(value=val, result_type=_to_ir_type(return_type))

        elif name == "PrintStmt":
            val = self._build_expr(stmt.value)
            val_type = self.inferencer.infer(stmt.value)
            if val_type is None:
                val_type = IntType()
            return IRPrint(value=val, value_type=_to_ir_type(val_type))

        elif name == "TryStmt":
            body = tuple(self._build_stmt(s) for s in stmt.body)
            handlers = []
            for h_type, h_name, h_body in stmt.handlers:
                # Define exception variable if present
                if h_name:
                    self.st.define(h_name, StrType()) # Simplifying exception objects to string for now
                
                ir_h_body = tuple(self._build_stmt(s) for s in h_body)
                handlers.append((_to_ir_type(h_type) if h_type else None, h_name, ir_h_body))
            return IRTryExcept(body=body, handlers=tuple(handlers))

        elif name == "RaiseStmt":
            val = self._build_expr(stmt.value) if stmt.value else None
            cause = self._build_expr(stmt.cause) if stmt.cause else None
            return IRRaise(value=val, cause=cause)

        elif name == "BreakStmt":
            if not self._loop_stack:
                raise self._err("'break' must be inside a loop", stmt.line, stmt.col)
            return IRBreak(label=self._loop_stack[-1])

        elif name == "ContinueStmt":
            if not self._loop_stack:
                raise self._err("'continue' must be inside a loop", stmt.line, stmt.col)
            return IRContinue(label=self._loop_stack[-1])

        elif name == "PassStmt":
            return None

        elif name == "DelStmt":
            target_val = self._build_expr(stmt.target)
            key_val = self._build_expr(stmt.key)
            return IRDictDelete(target=target_val, key=key_val)

        elif name == "SubscriptAssign":
            target_val = self._build_expr(stmt.target)
            index_val = self._build_expr(stmt.index)
            value = self._build_expr(stmt.value)
            target_type = self.inferencer.infer(stmt.target)
            if isinstance(target_type, ListType):
                value_type = _to_ir_type(target_type.element_type)
            target_type = self.inferencer.infer(stmt.target)
            trait_info = None
            if isinstance(target_type, DictType):
                value_type = _to_ir_type(target_type.value_type)
            elif isinstance(target_type, StrType):
                value_type = IRStrType()
            elif isinstance(target_type, ClassType):
                # Check for __setitem__
                if self.st.lookup_method(target_type.name, "__setitem__", 2):
                    trait_info = ("IndexMut", "index_mut")
                value_type = IRIntType() # Default
            else:
                value_type = IRIntType()
            
            return IRSubscriptAssign(
                target=target_val, index=index_val, value=value, value_type=value_type,
                trait_info=trait_info
            )

        elif name == "MatchStmt":
            return self._build_match(stmt, return_type)

        elif name == "EnumDef":
            return self._build_enum(stmt)

        elif name in ("ClassDef", "FunctionDef"):
            # Already handled in pre-scan or special build pass
            return None

        else:
            raise self._err(f"Unknown statement type: {name}")

    def _build_match(self, node: MatchStmt, return_type) -> IRMatchStmt:
        subject = self._build_expr(node.subject)
        ir_cases = []
        for case in node.cases:
            ir_pattern = self._build_pattern(case.pattern)
            ir_guard = self._build_expr(case.guard) if case.guard else None
            ir_body = tuple(self._build_stmts(case.body, return_type))
            ir_cases.append(IRMatchCase(pattern=ir_pattern, guard=ir_guard, body=ir_body))
        return IRMatchStmt(subject=subject, cases=tuple(ir_cases))

    def _build_pattern(self, pattern: MatchPattern) -> IRMatchPattern:
        if isinstance(pattern, ValuePattern):
            return IRValuePattern(value=self._build_expr(pattern.value))
        elif isinstance(pattern, NamePattern):
            return IRNamePattern(name=pattern.name)
        elif isinstance(pattern, WildcardPattern):
            return IRWildcardPattern()
        elif isinstance(pattern, OrPattern):
            return IROrPattern(patterns=tuple(self._build_pattern(p) for p in pattern.patterns))
        elif isinstance(pattern, AsPattern):
            return IRAsPattern(pattern=self._build_pattern(pattern.pattern), name=pattern.name)
        elif isinstance(pattern, ClassPattern):
            return IRClassPattern(
                class_name=pattern.class_name,
                patterns=tuple(self._build_pattern(p) for p in pattern.patterns)
            )
        else:
            raise self._err(f"Unsupported pattern type: {type(pattern).__name__}")

    def _build_expr(self, expr, expected_type=None):
        name = type(expr).__name__

        if name == "IntLiteral":
            if isinstance(expected_type, IRFloatType):
                return IRFloatLit(value=float(expr.value))
            return IRIntLit(value=expr.value)

        elif name == "FloatLiteral":
            return IRFloatLit(value=expr.value)

        elif name == "BoolLiteral":
            return IRBoolLit(value=expr.value)

        elif name == "StrLiteral":
            return IRStrLit(value=expr.value)

        elif name == "Name":
            expr_type = self.st.lookup(expr.name)
            ir_type = _to_ir_type(expr_type) if expr_type else None
            return IRName(name=expr.name, result_type=ir_type)

        elif name == "BinOp":
            result_type = self.inferencer.infer(expr)
            if result_type is None:
                result_type = IntType()
            ir_result = _to_ir_type(result_type)
            left_type = self.inferencer.infer(expr.left)
            
            trait_info = None
            if isinstance(left_type, ClassType):
                op_to_trait = {
                    "+": ("Add", "add"),
                    "-": ("Sub", "sub"),
                    "*": ("Mul", "mul"),
                    "/": ("Div", "div"),
                    "//": ("Div", "div"),
                    "%": ("Rem", "rem"),
                }
                if expr.op in op_to_trait:
                    trait_info = op_to_trait[expr.op]

            left = self._build_expr(expr.left, ir_result)
            right = self._build_expr(expr.right, ir_result)
            return IRBinOp(op=expr.op, left=left, right=right, result_type=ir_result, trait_info=trait_info)

        elif name == "UnaryOp":
            operand_type = self.inferencer.infer(expr.operand)
            if expr.op == "not":
                ir_result = IRBoolType()
            else:
                ir_result = _to_ir_type(operand_type) if operand_type else IRIntType()
            operand = self._build_expr(expr.operand, ir_result)
            return IRUnaryOpExpr(op=expr.op, operand=operand, result_type=ir_result)

        elif name == "Comparison":
            left_type = self.inferencer.infer(expr.left)
            right_type = self.inferencer.infer(expr.right)

            # Handle membership (in / not in)
            if expr.op in ("in", "not_in"):
                # Always build the expressions
                left = self._build_expr(expr.left)
                right = self._build_expr(expr.right)
                ir_right_type = _to_ir_type(right_type) if right_type else None
                
                contains_node = IRContains(
                    item=left,
                    container=right,
                    container_type=ir_right_type,
                    element_type=_to_ir_type(left_type) if left_type else None
                )
                
                if expr.op == "in":
                    return contains_node
                else:
                    return IRUnaryOpExpr(
                        op="not",
                        operand=contains_node,
                        result_type=IRBoolType()
                    )

            # Handle standard comparison
            ir_left_t = _to_ir_type(left_type) if left_type else IRIntType()
            left = self._build_expr(expr.left, ir_left_t)
            right = self._build_expr(expr.right, ir_left_t)
            return IRCompare(op=expr.op, left=left, right=right)

        elif name == "BoolOp":
            op_map = {"and": "&&", "or": "||"}
            values = tuple(self._build_expr(v) for v in expr.values)
            return IRBoolOp(op=op_map[expr.op], values=values)

        elif name == "ListLiteral":
            if not expr.elements:
                elem_type = IRIntType()
                if isinstance(expected_type, IRListType):
                    elem_type = expected_type.element_type
                return IRListLit(elements=(), element_type=elem_type)
            
            inferred_list_t = self.inferencer.infer(expr)
            if isinstance(inferred_list_t, ListType):
                elem_t = inferred_list_t.element_type
            else:
                elem_t = self.inferencer.infer(expr.elements[0]) or IntType()
            
            ir_elem_t = _to_ir_type(elem_t)
            elems = tuple(self._build_expr(e, ir_elem_t) for e in expr.elements)
            return IRListLit(elements=elems, element_type=ir_elem_t)

        elif name == "DictLiteral":
            if not expr.pairs:
                key_t = IRIntType()
                val_t = IRIntType()
                if isinstance(expected_type, IRDictType):
                    key_t = expected_type.key_type
                    val_t = expected_type.value_type
                return IRDictLit(pairs=(), key_type=key_t, value_type=val_t)
            first_key_t = self.inferencer.infer(expr.pairs[0][0])
            first_val_t = self.inferencer.infer(expr.pairs[0][1])
            ir_key_t = _to_ir_type(first_key_t) if first_key_t else IRIntType()
            ir_val_t = _to_ir_type(first_val_t) if first_val_t else IRIntType()
            pairs = tuple(
                (self._build_expr(k, ir_key_t), self._build_expr(v, ir_val_t))
                for k, v in expr.pairs
            )
            return IRDictLit(pairs=pairs, key_type=ir_key_t, value_type=ir_val_t)

        elif name == "TupleLiteral":
            elements = tuple(self._build_expr(e) for e in expr.elements)
            types = tuple(
                _to_ir_type(self.inferencer.infer(e)) for e in expr.elements
            )
            return IRTupleLit(elements=elements, element_types=types)

        elif name == "Subscript":
            val = self._build_expr(expr.value)
            idx = self._build_expr(expr.index)
            val_type = self.inferencer.infer(expr.value)
            ir_val_type = _to_ir_type(val_type) if val_type else IRIntType()
            trait_info = None
            if isinstance(val_type, ListType):
                result_type = _to_ir_type(val_type.element_type)
            elif isinstance(val_type, StrType):
                result_type = IRStrType()
            elif isinstance(val_type, DictType):
                result_type = _to_ir_type(val_type.value_type)
            elif isinstance(val_type, ClassType):
                # Check for __getitem__
                if self.st.lookup_method(val_type.name, "__getitem__", 1):
                    trait_info = ("Index", "index")
                    sig = self.st.lookup_method(val_type.name, "__getitem__", 1)
                    result_type = _to_ir_type(sig[1])
                else:
                    result_type = IRIntType()
            else:
                result_type = IRIntType()
            
            return IRSubscript(
                value=val, index=idx, value_type=ir_val_type, result_type=result_type,
                trait_info=trait_info
            )

        elif name == "FunctionCall":
            if expr.name == "len":
                arg = self._build_expr(expr.args[0])
                return IRFunctionCall(name="len", args=(arg,), return_type=IRIntType(), is_fallible=False)

            if expr.name in ("str", "int", "float", "bool"):
                arg = self._build_expr(expr.args[0])
                ret_t = {
                    "str": IRStrType(),
                    "int": IRIntType(),
                    "float": IRFloatType(),
                    "bool": IRBoolType()
                }[expr.name]
                return IRFunctionCall(name=expr.name, args=(arg,), return_type=ret_t, is_fallible=True)

            if expr.name in ("zip", "enumerate", "map", "reversed"):
                args = [self._build_expr(a) for a in expr.args]
                inferred = self.inferencer._infer_call(expr)
                ir_ret_t = _to_ir_type(inferred) if inferred else IRUnknownType()
                return IRFunctionCall(name=expr.name, args=tuple(args), return_type=ir_ret_t, is_fallible=False)

            if expr.name == "open":
                path = self._build_expr(expr.args[0])
                mode = self._build_expr(expr.args[1]) if len(expr.args) > 1 else None
                return IRFileOpen(path=path, mode=mode)

            sig = self.st.lookup_function(expr.name)
            if sig is None:
                # Check scope for class type (could be mangled)
                curr_type = self.st.lookup(expr.name)
                if isinstance(curr_type, ClassType):
                    args = []
                    for a in expr.args:
                        args.append(self._build_expr(a))
                    return IRNew(class_name=curr_type.name, args=tuple(args))
                elif isinstance(curr_type, (FunctionType, UnknownType)):
                    ret_t = curr_type.return_type if isinstance(curr_type, FunctionType) else UnknownType()
                    ir_ret = _to_ir_type(ret_t)
                    args = []
                    for a in expr.args:
                        args.append(self._build_expr(a))
                    return IRFunctionCall(name=expr.name, args=tuple(args), return_type=ir_ret, is_fallible=False)
                
                # Fallback to global class name if not in scope
                if self.st.lookup_class(expr.name):
                    args = []
                    for a in expr.args:
                        args.append(self._build_expr(a))
                    return IRNew(class_name=expr.name, args=tuple(args))
                raise self._err(
                    f"Undefined function '{expr.name}'", expr.line, expr.col
                )
            param_types, ret_type, _is_async, _type_params = sig
            ir_ret = _to_ir_type(ret_type)
            args = []
            for i, a in enumerate(expr.args):
                pt = _to_ir_type(param_types[i]) if i < len(param_types) else None
                args.append(self._build_expr(a, pt))
            return IRFunctionCall(name=expr.name, args=tuple(args), return_type=ir_ret, is_fallible=True)

        elif name == "AttributeExpr":
            val = self._build_expr(expr.value)
            field_type = self.inferencer.infer(expr)
            if field_type:
                ir_result = _to_ir_type(field_type)
                return IRStructAccess(
                    value=val, field=expr.attr, result_type=ir_result
                )
            raise self._err(
                f"Unknown field '{expr.attr}' in class",
                expr.line,
                expr.col,
            )

        elif name == "MethodCall":
            val = self._build_expr(expr.value)
            val_type = self.inferencer.infer(expr.value)
            if isinstance(val_type, ClassType):
                arity = len(expr.args)
                method_info = self.st.lookup_method(val_type.name, expr.method, arity)
                if method_info:
                    method, defining_class = method_info
                    ir_args = []
                    for i, arg in enumerate(expr.args):
                        if i < len(method.params):
                            pt = _to_ir_type(method.params[i].type_annotation)
                            ir_args.append(self._build_expr(arg, pt))
                        else:
                            ir_args.append(self._build_expr(arg))
                    ir_ret = _to_ir_type(method.return_type)
                    non_fallible_methods = {"push", "insert", "remove", "clone", "to_string", "chars", "count", "extend", "append", "get", "next"}
                    is_fallible = expr.method not in non_fallible_methods
                    
                    # Check if it mutates self
                    mutates_self = (val_type.name, expr.method, arity) in self._mutating_methods
                    # Core collection methods that mutate
                    if expr.method in {"append", "extend", "insert", "pop", "remove", "clear", "update"}:
                        mutates_self = True
                        
                    return IRMethodCall(
                        value=val,
                        method=expr.method,
                        args=tuple(ir_args),
                        result_type=ir_ret,
                        is_fallible=is_fallible,
                        mutates_self=mutates_self,
                    )
            if isinstance(val_type, FileType):
                file_val = self._build_expr(expr.value)
                ir_args = [self._build_expr(a) for a in expr.args]
                return IRFileMethod(
                    file=file_val, method=expr.method, args=tuple(ir_args)
                )
            raise self._err(
                f"Unknown method '{expr.method}' in class",
                expr.line,
                expr.col,
            )

        elif name == "SelfExpr":
            return IRSelf()

        elif name == "NewExpr":
            args = []
            for a in expr.args:
                args.append(self._build_expr(a))
            return IRNew(class_name=expr.class_name, args=tuple(args))

        elif name == "AwaitExpr":
            res_type = self.inferencer.infer(expr)
            ir_res_t = _to_ir_type(res_type) if res_type else IRIntType()
            val = self._build_expr(expr.value)
            return IRAwait(value=val, result_type=ir_res_t)

        elif name == "LambdaExpr":
            return self._build_lambda(expr)

        elif name == "ListComp":
            return self._build_list_comp(expr)

        elif name == "DictComp":
            return self._build_dict_comp(expr)

        elif name == "SetComp":
            return self._build_set_comp(expr)

        elif name == "JoinedStr":
            values = tuple(self._build_expr(v) for v in expr.values)
            return IRJoinedStr(values=values)

        elif name == "FormattedValue":
            val = self._build_expr(expr.value)
            return IRFormattedValue(
                value=val,
                conversion=expr.conversion,
                format_spec=expr.format_spec
            )

        else:
            raise self._err(f"Unknown expression type: {name}")

    def _build_lambda(self, expr: LambdaExpr) -> IRLambda:
        self.st.enter_scope("lambda")
        params = []
        for p in expr.params:
            self.st.define(p.name, None)
            params.append(IRParam(name=p.name, type_=IRIntType()))  # Generic type for lambda params
        
        body = self._build_expr(expr.body)
        res_type = self.inferencer.infer(expr)
        self.st.exit_scope()
        return IRLambda(
            params=tuple(params),
            body=body,
            result_type=_to_ir_type(res_type)
        )

    def _build_list_comp(self, node: ListComp) -> IRListComp:
        self.st.enter_scope("comprehension")
        generators = []
        for gen in node.generators:
            target = self._build_comp_target(gen.target)
            iterable = self._build_expr(gen.iterable)
            
            # Define target in symbol table for inner parts
            it_t = self.inferencer.infer(gen.iterable)
            elem_t = IntType()
            if isinstance(it_t, ListType):
                elem_t = it_t.element_type
            elif isinstance(it_t, StrType):
                elem_t = StrType()
            elif isinstance(it_t, DictType):
                elem_t = it_t.key_type

            self._bind_target(gen.target, elem_t)

            ifs = tuple(self._build_expr(i) for i in gen.ifs)
            generators.append(IRComprehension(target=target, iterable=iterable, ifs=ifs, is_async=gen.is_async))
        
        elt = self._build_expr(node.elt)
        elt_t = self.inferencer.infer(node.elt)
        ir_elt_t = _to_ir_type(elt_t) if elt_t else IRIntType()
        res_ir_t = IRListType(element_type=ir_elt_t)
        self.st.exit_scope()
        return IRListComp(elt=elt, generators=tuple(generators), result_type=res_ir_t)

    def _bind_target(self, target, target_type):
        import ast
        if isinstance(target, ast.Name):
            self.st.define(target.id, target_type)
        elif isinstance(target, str):
            self.st.define(target, target_type)
        elif isinstance(target, ast.Tuple):
            if isinstance(target_type, TupleType):
                for t, et in zip(target.elts, target_type.element_types):
                    self._bind_target(t, et)
            elif isinstance(target_type, ListType):
                for t in target.elts:
                    self._bind_target(t, target_type.element_type)
            else:
                for t in target.elts:
                    self._bind_target(t, IntType())
        elif isinstance(target, Name): # My AST Name
            self.st.define(target.name, target_type)
        elif isinstance(target, TupleLiteral): # My AST TupleLiteral
            if isinstance(target_type, TupleType):
                for t, et in zip(target.elements, target_type.element_types):
                    self._bind_target(t, et)
            else:
                for t in target.elements:
                    self._bind_target(t, IntType())

    def _build_dict_comp(self, node: DictComp) -> IRDictComp:
        self.st.enter_scope("comprehension")
        generators = []
        for gen in node.generators:
            target = self._build_comp_target(gen.target)
            iterable = self._build_expr(gen.iterable)
            # Define target logic (same as list comp)
            it_t = self.inferencer.infer(gen.iterable)
            elem_t = IntType()
            if isinstance(it_t, ListType):
                elem_t = it_t.element_type
            elif isinstance(it_t, StrType):
                elem_t = StrType()
            elif isinstance(it_t, DictType):
                elem_t = it_t.key_type

            self._bind_target(gen.target, elem_t)

            ifs = tuple(self._build_expr(i) for i in gen.ifs)
            generators.append(IRComprehension(target=target, iterable=iterable, ifs=ifs, is_async=gen.is_async))
        
        key = self._build_expr(node.key)
        value = self._build_expr(node.value)
        k_t = self.inferencer.infer(node.key)
        v_t = self.inferencer.infer(node.value)
        ir_k_t = _to_ir_type(k_t) if k_t else IRIntType()
        ir_v_t = _to_ir_type(v_t) if v_t else IRIntType()
        res_ir_t = IRDictType(key_type=ir_k_t, value_type=ir_v_t)
        self.st.exit_scope()
        return IRDictComp(key=key, value=value, generators=tuple(generators), result_type=res_ir_t)

    def _build_set_comp(self, node: SetComp) -> IRSetComp:
        self.st.enter_scope("comprehension")
        generators = []
        for gen in node.generators:
            target = self._build_comp_target(gen.target)
            iterable = self._build_expr(gen.iterable)
            
            it_t = self.inferencer.infer(gen.iterable)
            elem_t = IntType()
            if isinstance(it_t, ListType):
                elem_t = it_t.element_type
            elif isinstance(it_t, StrType):
                elem_t = StrType()
            elif isinstance(it_t, DictType):
                elem_t = it_t.key_type

            self._bind_target(gen.target, elem_t)

            ifs = tuple(self._build_expr(i) for i in gen.ifs)
            generators.append(IRComprehension(target=target, iterable=iterable, ifs=ifs, is_async=gen.is_async))
        
        elt = self._build_expr(node.elt)
        elt_t = self.inferencer.infer(node.elt)
        ir_elt_t = _to_ir_type(elt_t) if elt_t else IRIntType()
        res_ir_t = IRSetType(element_type=ir_elt_t)
        self.st.exit_scope()
        return IRSetComp(elt=elt, generators=tuple(generators), result_type=res_ir_t)

    def _build_comp_target(self, target):
        from ..frontend.ast_nodes import Name, TupleLiteral
        if isinstance(target, str):
            return IRName(name=target)
        if isinstance(target, Name):
            return IRName(name=target.name)
        if isinstance(target, TupleLiteral):
            elements = tuple(self._build_comp_target(e) for e in target.elements)
            types = tuple(IRIntType() for _ in elements) # Simplified
            return IRTupleLit(elements=elements, element_types=types)
        return IRName(name="unknown")


def build_ir(module, filename: str = "<unknown>", source_lines: list = None):
    builder = IRBuilder(filename, source_lines)
    return builder.build(module)
