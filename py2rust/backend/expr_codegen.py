# expr_codegen.py - Expression code generation mixin for Rust codegen
from py2rust.ir.ir_nodes import (
    IRExpr, IRIntLit, IRFloatLit, IRBoolLit, IRStrLit, IRName, IRBinOp, IRUnaryOpExpr,
    IRSome, IRSumWrap, IRNoneLit, IRIsInstance, IRContains, IRCompare, IRBoolOp,
    IRListLit, IRDictLit, IRTupleLit, IRSlice, IRSubscript, IRFunctionCall,
    IRFileOpen, IRFileMethod, IRSelf, IRStructAccess, IRMethodCall, IRNew, IRAwait,
    IRLambda, IRMap, IRFilter, IRSorted, IRReduce, IRListComp, IRDictComp, IRSetComp,
    IRGeneratorExp, IRJoinedStr, IRFormattedValue, IRClassType, IRExternalPythonType,
    IROptionType, IRDictType, IRStrType, IRDequeType, IRHeapType, IRListType,
    IRTypeParam, IRFloatType, IRIntType, IRSetType, IREnumType, IRSumType, IRUnitType,
    IRIteratorType, IRGeneratorType, IRBoolType
)
from .codegen_helpers import _mangle

class ExprCodegenMixin:
    def _gen_expr(self, expr, expected_type=None) -> str:
        if isinstance(expr, IRIntLit):
            return str(expr.value)
        elif isinstance(expr, IRFloatLit):
            v = expr.value
            s = repr(v)
            if "." not in s and "e" not in s.lower():
                s += ".0"
            return s
        elif isinstance(expr, IRBoolLit):
            return "true" if expr.value else "false"
        elif isinstance(expr, IRStrLit):
            escaped = (
                expr.value.replace("\\", "\\\\")
                .replace('"', '\\"')
                .replace("\n", "\\n")
            )
            return f'"{escaped}".to_string()'
        elif isinstance(expr, IRName):
            if hasattr(self, "_generator_fields") and self._generator_fields and expr.name in self._generator_fields:
                mangled = _mangle(expr.name)
                if mangled != expr.name and hasattr(self.config, "translation_context") and self.config.translation_context:
                    self.config.translation_context.add_name_mapping(expr.name, mangled)
                return f"self.{mangled}"
            # Check if this name refers to an external python module/object
            if isinstance(expr.result_type, IRExternalPythonType) and not expr.result_type.is_local:
                 # If it's a local variable, field, or parameter, use the name directly
                 if expr.name in self._decl_types or expr.name == "self":
                     mangled = _mangle(expr.name)
                     if mangled != expr.name and hasattr(self.config, "translation_context") and self.config.translation_context:
                         self.config.translation_context.add_name_mapping(expr.name, mangled)
                     return mangled
                     
                 if expr.result_type.name is None:
                     return f'ExternalObject::load_module("{expr.result_type.module}")?'
                 else:
                     clean_name = expr.result_type.name
                     if clean_name.endswith("()"):
                         clean_name = clean_name[:-2]
                     return f'ExternalObject::from_module("{expr.result_type.module}", "{clean_name}")'
            mangled = _mangle(expr.name)
            if mangled != expr.name and hasattr(self.config, "translation_context") and self.config.translation_context:
                self.config.translation_context.add_name_mapping(expr.name, mangled)
            return mangled
        elif isinstance(expr, IRBinOp):
            return f"({self._gen_binop(expr)})"
        elif isinstance(expr, IRUnaryOpExpr):
            operand = self._gen_expr(expr.operand)
            if expr.op == "not":
                if isinstance(expr.operand.result_type, IROptionType):
                    return f"{operand}.is_none()"
                return f"(!({operand}))"
            if expr.op == "-":
                return f"(-({operand}))"
            return operand
        elif isinstance(expr, IRSome):
            val = self._gen_expr(expr.value)
            return f"Some({val})"
        elif isinstance(expr, IRSumWrap):
            enum_name = self._get_sum_type_name(expr.result_type)
            variant_rust_info = self._get_rust_type(expr.inner_type)
            variant_name = self._get_variant_name(variant_rust_info)
            val = self._gen_expr(expr.value)
            return f"{enum_name}::{variant_name}({val})"
        elif isinstance(expr, IRNoneLit):
            return "None"
        elif isinstance(expr, IRIsInstance):
            return self._gen_isinstance(expr)
        elif isinstance(expr, IRContains):
            item = self._gen_expr(expr.item)
            container = self._gen_expr(expr.container)
            if isinstance(expr.container_type, IRDictType):
                return f"{container}.contains_key(&{item})"
            elif isinstance(expr.container_type, IRStrType):
                # For strings, use .contains() which works with &str
                return f"{container}.contains({item}.as_str())"
            else:
                return f"{container}.contains(&{item})"
        elif isinstance(expr, IRCompare):
            left = self._gen_expr(expr.left)
            right = self._gen_expr(expr.right)
            
            # Special case for Optional: is None / is not None
            if isinstance(expr.left.result_type, IROptionType):
                if right == "None":
                    if expr.op in ("is", "=="):
                        return f"{left}.is_none()"
                    elif expr.op in ("is not", "!="):
                        return f"{left}.is_some()"
            elif isinstance(expr.right.result_type, IROptionType):
                if left == "None":
                    if expr.op in ("is", "=="):
                        return f"{right}.is_none()"
                    elif expr.op in ("is not", "!="):
                        return f"{right}.is_some()"

            # Map Python comparisons to Rust traits if applicable
            op = expr.op
            if op == "is": op = "=="
            if op == "is not": op = "!="
            
            if isinstance(expr.left.result_type, IRClassType):
                left = f"{left}.clone()"
                right = f"{right}.clone()"
                
            return f"{left} {op} {right}"
        elif isinstance(expr, IRBoolOp):
            parts = [self._gen_expr(v) for v in expr.values]
            return f"({(f' {expr.op} ').join(parts)})"
        elif isinstance(expr, IRListLit):
            is_proto = isinstance(expr.element_type, IRClassType) and self._is_protocol(expr.element_type.name)
            elem_t_str = self._get_rust_type(expr.element_type)
            
            if expr.result_type and isinstance(expr.result_type, IRDequeType):
                self._uses_vec_deque = True
                if not expr.elements:
                    return f"VecDeque::new()"
                elems = ", ".join(self._gen_expr(e) for e in expr.elements)
                return f"VecDeque::from(vec![{elems}])"
            elif expr.result_type and isinstance(expr.result_type, IRHeapType):
                self._uses_heap = True
                if not expr.elements:
                    return f"BinaryHeap::new()"
                elems = ", ".join(self._gen_expr(e) for e in expr.elements)
                return f"BinaryHeap::from(vec![{elems}].into_iter().map(Reverse).collect::<Vec<_>>())"

            if not expr.elements:
                res_t = f"Vec::<Box<dyn {expr.element_type.name}>>" if is_proto else f"Vec::<{elem_t_str}>"
                return f"{res_t}::new()"
            
            if is_proto:
                elems = ", ".join(f"Box::new({self._gen_expr(e)}) as Box<dyn {expr.element_type.name}>" for e in expr.elements)
            else:
                elems = ", ".join(self._gen_expr(e) for e in expr.elements)
            return f"vec![{elems}]"
        elif isinstance(expr, IRDictLit):
            self._uses_hashmap = True
            is_ext = False
            if (isinstance(expr.value_type, IRExternalPythonType) and not expr.value_type.is_local) or (isinstance(expr.value_type, IRClassType) and expr.value_type.name == "ExternalObject"):
                is_ext = True

            if is_ext:
                self._uses_python_wrappers = True
                pairs = ", ".join(f"({self._gen_expr(k)}, {self._gen_expr(v)})" for k, v in expr.pairs)
                return f"ExternalObject::new(Python::with_gil(|py| {{ let d = PyDict::new(py); {('; ').join(f'd.set_item({self._gen_expr(k)}, {self._gen_expr(v)}).unwrap()' for k, v in expr.pairs)}; d.to_object(py) }}))"

            key_t = self._get_rust_type(expr.key_type)
            val_t = self._get_rust_type(expr.value_type)
            if not expr.pairs:
                return f"HashMap::<{key_t}, {val_t}>::new()"
            pairs = ", ".join(f"({self._gen_expr(k)}, {self._gen_expr(v)})" for k, v in expr.pairs)
            return f"HashMap::from([{pairs}])"
        elif isinstance(expr, IRTupleLit):
            elems = ", ".join(self._gen_expr(e) for e in expr.elements)
            return f"({elems})"

        elif isinstance(expr, IRSlice):
            # standalone slice object, rare in our codegen but let's handle it
            lower = self._gen_expr(expr.lower) if expr.lower else "None"
            upper = self._gen_expr(expr.upper) if expr.upper else "None"
            step = self._gen_expr(expr.step) if expr.step else "None"
            return f"py2rust::Slice::new({lower}, {upper}, {step})"

        elif isinstance(expr, IRSubscript):
            val = self._gen_expr(expr.value)
            idx = self._gen_expr(expr.index)

            # Handle user-defined indexing via dunder methods
            if expr.trait_info and expr.trait_info[0] == "Index":
                return f"{val}.__getitem__({idx})?"

            # Handle dict subscript: d[key] -> __d.get(&key).unwrap().clone()
            if isinstance(expr.value_type, IRDictType):
                val_t = self._get_rust_type(expr.value_type.value_type)
                return f"{val}.get(&{idx}).unwrap().clone()"

            # Handle ExternalObject indexing (e.g., json data)
            is_ext = False
            if (isinstance(expr.value_type, IRClassType) and expr.value_type.name == "ExternalObject") or \
               (isinstance(expr.value_type, IRExternalPythonType) and not expr.value_type.is_local):
                is_ext = True
            
            if is_ext:
                return f"{val}.getitem({idx})?"

            # Handle slicing
            if isinstance(expr.index, IRSlice):
                slc = expr.index
                lower = self._strip_parens(self._gen_expr(slc.lower)) if slc.lower else "0"
                upper = self._strip_parens(self._gen_expr(slc.upper)) if slc.upper else (f"{val}.len() as i32" if not isinstance(expr.value_type, IRStrType) else f"{val}.chars().count() as i32")
                
                # Slicing creates a NEW collection usually in Python
                if isinstance(expr.value_type, IRListType):
                    # List slicing: l[start:stop] -> l[start as usize .. stop as usize].to_vec()
                    # We need to handle negative indices
                    return (
                        f"{{ let __coll = &({val}); let __len = __coll.len() as i32; "
                        f"let __start = if {lower} < 0 {{ {lower} + __len }} else {{ {lower} }};"
                        f"let __stop = if {upper} < 0 {{ {upper} + __len }} else {{ {upper} }};"
                        f"let __start = __start.clamp(0, __len) as usize; "
                        f"let __stop = __stop.clamp(__start as i32, __len) as usize; "
                        f"__coll[__start..__stop].to_vec() }}"
                    )
                elif isinstance(expr.value_type, IRStrType):
                    # String slicing: s[start:stop] -> s.chars().skip(start).take(stop-start).collect()
                    return (
                        f"{{ let __coll = &({val}); let __len = __coll.chars().count() as i32; "
                        f"let __start = if {lower} < 0 {{ {lower} + __len }} else {{ {lower} }};"
                        f"let __stop = if {upper} < 0 {{ {upper} + __len }} else {{ {upper} }};"
                        f"let __start = __start.clamp(0, __len) as usize; "
                        f"let __stop = __stop.clamp(__start as i32, __len) as usize; "
                        f"__coll.chars().skip(__start).take(__stop - __start).collect::<String>() }}"
                    )

            # Robust Python indexing: bind collection to a temp reference
            if isinstance(expr.value_type, IRStrType):
                len_expr = "__coll.chars().count() as i32"
                inner_expr = f"__coll.chars().nth(actual_idx).unwrap().to_string()"
            elif isinstance(expr.value_type, IRHeapType):
                # Heap only supports heap[0] reliably as peek()
                if idx == "0":
                    return f"{val}.peek().map(|r| r.0.clone()).ok_or(PyError::IndexError(\"heap index out of range\".to_string()))?"
                len_expr = "__coll.len() as i32"
                inner_expr = f"__coll.peek().map(|r| r.0.clone()).ok_or(PyError::IndexError(\"heap index out of range\".to_string()))?"
            else:
                len_expr = "__coll.len() as i32"
                inner_expr = f"__coll[actual_idx]"

            if isinstance(expr.result_type, (IRStrType, IRListType, IRTypeParam)) and not isinstance(
                expr.value_type, IRStrType
            ):
                inner_expr = f"{inner_expr}.clone()"

            return (
                f"{{ let __coll = &({val}); "
                f"let __idx_raw = {idx}; let actual_idx = if __idx_raw < 0 {{ (__idx_raw + ({len_expr}) as i32) as usize }} else {{ __idx_raw as usize }}; "
                f"{inner_expr} }}"
            )

        elif isinstance(expr, IRFunctionCall):
            if expr.name == "isinstance":
                obj = self._gen_expr(expr.args[0])
                obj_type = getattr(expr.args[0], "result_type", None)
                type_node = expr.args[1]
                
                if isinstance(obj_type, IRSumType):
                    enum_name = self._get_rust_type(obj_type)
                    # For simplicity, handle single type name. 
                    # If it's a tuple of types, we would need a more complex match or multiple matches!.
                    variant = "Unknown"
                    from ..frontend.ast_nodes import Name
                    if isinstance(type_node, Name):
                        typ_name = type_node.name
                        if typ_name == "int": variant = "Int"
                        elif typ_name == "float": variant = "Float"
                        elif typ_name == "str": variant = "Str"
                        elif typ_name == "bool": variant = "Bool"
                        else: variant = typ_name # Assume class name
                    
                    return f"matches!(&{obj}, {enum_name}::{variant}(_))"
                
                if isinstance(obj_type, IROptionType):
                    from ..frontend.ast_nodes import Name
                    if isinstance(type_node, Name) and type_node.name == "type(None)":
                         return f"{obj}.is_none()"
                    return f"{obj}.is_some()"
                
                # Fallback for normal objects/classes
                return f"true /* isinstance fallback for {obj} */"

            if expr.name == "len":
                arg = self._gen_expr(expr.args[0])
                return f"{arg}.len() as i32"

            if expr.name == "list" and len(expr.args) == 1:
                arg = self._gen_expr(expr.args[0])
                arg_t = getattr(expr.args[0], "result_type", None)
                if isinstance(arg_t, (IRIteratorType, IRGeneratorType)) or isinstance(expr.args[0], (IRMap, IRFilter)):
                    return f"{arg}.collect::<Vec<_>>()"
                return f"{arg}.clone()"

            if expr.name == "set" and len(expr.args) == 1:
                arg = self._gen_expr(expr.args[0])
                arg_t = getattr(expr.args[0], "result_type", None)
                if isinstance(arg_t, (IRIteratorType, IRGeneratorType)) or isinstance(expr.args[0], (IRMap, IRFilter)):
                    return f"{arg}.collect::<HashSet<_>>()"
                return f"{arg}.clone().into_iter().collect::<HashSet<_>>()"
            
            if expr.name == "zip":
                # zip(a, b)
                arg0 = self._gen_expr(expr.args[0])
                arg1 = self._gen_expr(expr.args[1])
                return f"(&{arg0}).iter().zip((&{arg1}).iter())"
            
            if expr.name == "enumerate":
                arg = self._gen_expr(expr.args[0])
                return f"(&{arg}).iter().enumerate().map(|(i, x)| (i as i32, x))"
                
            if expr.name == "map":
                func = self._gen_expr(expr.args[0])
                iterable = self._gen_expr(expr.args[1])
                return f"(&{iterable}).iter().map({func}).collect::<Vec<_>>()"
                
            if expr.name == "reversed":
                arg = self._gen_expr(expr.args[0])
                return f"(&{arg}).iter().rev()"

            if expr.name == "str":
                arg = self._gen_expr(expr.args[0])
                arg_t = getattr(expr.args[0], "result_type", None)
                if isinstance(arg_t, IRClassType):
                    return f"{arg}.__str__()?"
                return f"{arg}.to_string()"
            
            if expr.name == "int":
                arg = self._gen_expr(expr.args[0])
                arg_t = getattr(expr.args[0], "result_type", None)
                if isinstance(arg_t, IRStrType):
                    return f'{arg}.parse::<i32>().map_err(|e| PyError::ValueError(e.to_string()))?'
                if isinstance(arg_t, IRFloatType):
                    return f"({arg} as i32)"
                # Use a string conversion fallback
                return f"{arg}.to_string().parse::<i32>().map_err(|e| PyError::ValueError(e.to_string()))?"
            
            if expr.name == "float":
                arg = self._gen_expr(expr.args[0])
                arg_t = getattr(expr.args[0], "result_type", None)
                if isinstance(arg_t, IRStrType):
                    return f'{arg}.parse::<f64>().map_err(|e| PyError::ValueError(e.to_string()))?'
                if isinstance(arg_t, IRIntType):
                    return f"({arg} as f64)"
                return f"{arg}.to_string().parse::<f64>().map_err(|e| PyError::ValueError(e.to_string()))?"

            if expr.name == "bool":
                arg = self._gen_expr(expr.args[0])
                arg_t = getattr(expr.args[0], "result_type", None)
                if isinstance(arg_t, (IRIntType, IRFloatType)):
                    return f"({arg} != 0.0)"
                if isinstance(arg_t, (IRStrType, IRListType, IRDictType, IRSetType)):
                    return f"!{arg}.is_empty()"
                return "true"
            
            if expr.name in ("Exception", "ValueError", "TypeError", "KeyError", "IndexError"):
                # Exception constructor call
                arg_str = self._gen_expr(expr.args[0]) if expr.args else '""'.to_string()
                return f"PyError::{expr.name}({arg_str})"

            # Native JSON support
            if expr.name == "__py2rust_native_json_loads":
                self._uses_python_wrappers = True
                self._uses_serde_json = True
                self._uses_pythonize = True
                arg = self._gen_expr(expr.args[0])
                return f"Python::with_gil(|py| -> Result<ExternalObject, PyError> {{ let v: serde_json::Value = serde_json::from_str(&{arg}).map_err(|e| PyError::ValueError(e.to_string()))?; let obj = pythonize::pythonize(py, &v).map_err(|e| PyError::ValueError(e.to_string()))?; Ok(ExternalObject::new(obj)) }})?"
            
            if expr.name == "__py2rust_native_json_dumps":
                self._uses_python_wrappers = True
                self._uses_serde_json = True
                self._uses_pythonize = True
                arg = self._gen_expr(expr.args[0])
                arg_t = getattr(expr.args[0], "result_type", None)
                is_ext = (isinstance(arg_t, IRExternalPythonType) and not arg_t.is_local) or (isinstance(arg_t, IRClassType) and arg_t.name == "ExternalObject")
                if is_ext:
                    # Use Python's json.dumps for maximum compatibility with external objects
                    return f"Python::with_gil(|py| -> Result<String, PyError> {{ let json = py.import(\"json\")?; let res = json.getattr(\"dumps\")?.call1(({arg}.obj.as_ref(py),))?; Ok(res.extract()?) }})?"
                else:
                    return f"serde_json::to_string(&{arg}).map_err(|e| PyError::ValueError(e.to_string()))?"

            if expr.name in ("deque", "collections.deque"):
                self._uses_deque = True
                if not expr.args:
                    return "VecDeque::new()"
                arg = self._gen_expr(expr.args[0])
                # Match test expectation: VecDeque::from(vec![...])
                if ".to_vec()" in arg or "vec![" in arg:
                    return f"VecDeque::from({arg})"
                return f"VecDeque::from_iter({arg})"

            if expr.name in ("heappush", "heapq.heappush"):
                self._uses_heap = True
                heap = self._gen_expr(expr.args[0])
                item = self._gen_expr(expr.args[1])
                return f"{heap}.push(Reverse({item}))"
            
            if expr.name in ("heappop", "heapq.heappop"):
                self._uses_heap = True
                heap = self._gen_expr(expr.args[0])
                return f"{heap}.pop().ok_or(PyError::IndexError(\"index out of range\".to_string()))?.0"
            
            if expr.name in ("heapify", "heapq.heapify"):
                self._uses_heap = True
                lst = self._gen_expr(expr.args[0])
                return f"BinaryHeap::from({lst}.into_iter().map(Reverse).collect::<Vec<_>>())"

            # Native CSV support
            if expr.name == "__py2rust_native_csv_reader":
                self._uses_python_wrappers = True
                self._uses_csv = True
                # csv.reader(f) -> returns an iterator of rows
                arg = self._gen_expr(expr.args[0])
                # This is a bit complex as it needs to return something that behaves like an iterator of ExternalObjects
                return f"ExternalObject::new_csv_reader(&{arg})?"

            args = ", ".join(self._gen_expr(a) for a in expr.args)
            
            # Use call() if it's an external function
            if isinstance(expr.return_type, IRExternalPythonType) and not expr.return_type.is_local:
                func_name = self._gen_expr(IRName(name=expr.name, result_type=expr.return_type))
                if not args:
                    tuple_args = "()"
                else:
                    tuple_args = f"({args},)"
                return f"{func_name}.call({tuple_args})?"

            fn_name = _mangle(expr.name)
            if expr.name == "main":
                # Call the renamed user main
                fn_name = "__py_main"

            res = f"{fn_name}({args})"
            if expr.is_fallible:
                res = f"{res}?"
            return res
        elif isinstance(expr, IRFileOpen):
            path = self._gen_expr(expr.path)
            mode = self._gen_expr(expr.mode) if expr.mode else '"r".to_string()'
            if self._uses_python_wrappers:
                # In mock mode, use Python's open() for interoperability with other mock-mode libraries
                return f"ExternalObject::call_builtin(\"open\", ({path}, {mode}))?"
            self._uses_file_handle = True
            return f"FileHandle::open(&{path}, &{mode})?"
        elif isinstance(expr, IRFileMethod):
            file_val = self._gen_expr(expr.file)
            args = ", ".join(f"&{self._gen_expr(a)}" for a in expr.args)
            method = expr.method
            if method in ("read", "readline", "readlines"):
                return f"{file_val}.{method}()?"
            if method == "write":
                return f"{file_val}.write({args})?"
            if method == "close":
                return f"{file_val}.close()?"
            if method == "tell":
                return f"{file_val}.tell()?"
            if method == "seek":
                return f"{file_val}.seek({args})?"
            return f"{file_val}.{method}()?"
        elif isinstance(expr, IRSelf):
            return "self"
        elif isinstance(expr, IRStructAccess):
            if isinstance(expr.value, IRSelf):
                from py2rust.ir.ir_nodes import IRIntType, IRFloatType, IRBoolType, IRUnitType
                is_copy = isinstance(expr.result_type, (IRIntType, IRFloatType, IRBoolType, IRUnitType))
                if not is_copy:
                    return f"self.{_mangle(expr.field)}.clone()"
                return f"self.{_mangle(expr.field)}"
            val = self._gen_expr(expr.value)
            # Use :: for static enum variant access
            if isinstance(expr.result_type, IREnumType):
                return f"{val}::{_mangle(expr.field)}"
            
            v_type = getattr(expr.value, "result_type", None)
            if isinstance(v_type, IRExternalPythonType):
                if not v_type.is_local:
                    return f'{val}.getattr("{expr.field}")?'
                elif v_type.name is None:
                    return f"{val}::{_mangle(expr.field)}"

            return f"{val}.{_mangle(expr.field)}"
        elif isinstance(expr, IRMethodCall):
            val = self._gen_expr(expr.value)
            args = ", ".join(self._gen_expr(a) for a in expr.args)
            
            v_type = getattr(expr.value, "result_type", None)
            if isinstance(v_type, IRExternalPythonType):
                if v_type.is_local:
                    if v_type.name is None:
                        res = f"{val}::{_mangle(expr.method)}({args})"
                        if getattr(expr, "is_fallible", True):
                            res += "?"
                        return res
                else:
                    val_type = expr.value.result_type
                    if val_type.module == "heapq":
                        if expr.method == "heappush":
                            self._uses_heap = True
                            heap = self._gen_expr(expr.args[0])
                            item = self._gen_expr(expr.args[1])
                            return f"{heap}.push(Reverse({item}))"
                        if expr.method == "heappop":
                            self._uses_heap = True
                            heap = self._gen_expr(expr.args[0])
                            return f"{heap}.pop().ok_or(PyError::IndexError(\"index out of range\".to_string()))?.0"
                        if expr.method == "heapify":
                            self._uses_heap = True
                            lst = self._gen_expr(expr.args[0])
                            return f"BinaryHeap::from({lst}.into_iter().map(Reverse).collect::<Vec<_>>())"

                    if not args:
                        tuple_args = "()"
                    else:
                        tuple_args = f"({args},)"
                    return f'{val}.call_method("{expr.method}", {tuple_args})?'

            # Deque species methods
            if isinstance(getattr(expr, "value_type", getattr(expr.value, "result_type", None)), IRDequeType):
                self._uses_deque = True
                if expr.method == "append":
                    return f"{val}.push_back({args})"
                if expr.method == "appendleft":
                    return f"{val}.push_front({args})"
                if expr.method == "pop":
                    return f"{val}.pop_back().ok_or(PyError::IndexError(\"pop from an empty deque\".to_string()))?"
                if expr.method == "popleft":
                    return f"{val}.pop_front().ok_or(PyError::IndexError(\"pop from an empty deque\".to_string()))?"
                if expr.method == "extend":
                    return f"{val}.extend({args})"
                if expr.method == "extendleft":
                    # Python's extendleft reverses the iterable
                    return f"for __item in {args} {{ {val}.push_front(__item); }}"

            res = f"{val}.{_mangle(expr.method)}({args})"
            is_fallible = getattr(expr, "is_fallible", True)
            if is_fallible:
                res += "?"
            if hasattr(self.config, "translation_context") and self.config.translation_context:
                py_sig = f".{expr.method}(...)"
                rust_sig = f".{_mangle(expr.method)}(...)"
                if is_fallible:
                    rust_sig += "?"
                self.config.translation_context.add_call_mapping(py_sig, rust_sig)
            return res
        elif isinstance(expr, IRNew):
            args = ", ".join(self._gen_expr(a) for a in expr.args)
            return f"{expr.class_name}::new({args})?"
        elif isinstance(expr, IRAwait):
            self._uses_async = True
            val = self._gen_expr(expr.value)
            # If the inner expression was fallible (had a '?'), we need to await then '?' 
            # e.g. func().await?
            if val.endswith("?"):
                return f"{val[:-1]}.await?"
            return f"{val}.await"

        elif isinstance(expr, IRLambda):
            return self._gen_lambda(expr)

        elif isinstance(expr, IRMap):
            if isinstance(expr.func, IRLambda):
                func_str = self._gen_expr(expr.func)
            else:
                func_str = f"|x| ({self._gen_expr(expr.func)})(x).unwrap()"
            iter_expr = self._get_comp_iter_expr(expr.iterable, getattr(expr.iterable, "result_type", None))
            return f"Box::new({iter_expr}.map({func_str}))"

        elif isinstance(expr, IRFilter):
            if isinstance(expr.func, IRLambda):
                func_str = f"move |__x| {{ let x = __x.clone(); ({self._gen_expr(expr.func)})(x) }}"
            else:
                func_str = f"move |__x| {{ let x = __x.clone(); ({self._gen_expr(expr.func)})(x).unwrap() }}"
            iter_expr = self._get_comp_iter_expr(expr.iterable, getattr(expr.iterable, "result_type", None))
            return f"Box::new({iter_expr}.filter({func_str}))"

        elif isinstance(expr, IRSorted):
            iter_expr = self._get_comp_iter_expr(expr.iterable, getattr(expr.iterable, "result_type", None))
            if expr.key_func:
                if isinstance(expr.key_func, IRLambda):
                    key_str = f"|__x| {{ let x = __x.clone(); ({self._gen_expr(expr.key_func)})(x) }}"
                else:
                    key_str = f"|__x| {{ let x = __x.clone(); ({self._gen_expr(expr.key_func)})(x).unwrap() }}"
                return (
                    f"({{ let mut __tmp = {iter_expr}.collect::<Vec<_>>(); "
                    f"__tmp.sort_by_key({key_str}); "
                    f"__tmp }})"
                )
            else:
                return (
                    f"({{ let mut __tmp = {iter_expr}.collect::<Vec<_>>(); "
                    f"__tmp.sort(); "
                    f"__tmp }})"
                )

        elif isinstance(expr, IRReduce):
            iter_expr = self._get_comp_iter_expr(expr.iterable, getattr(expr.iterable, "result_type", None))
            if isinstance(expr.func, IRLambda):
                func_str = self._gen_expr(expr.func)
            else:
                func_str = f"|acc, x| ({self._gen_expr(expr.func)})(acc, x).unwrap()"
            if expr.initial is not None:
                initial_str = self._gen_expr(expr.initial)
                return f"{iter_expr}.fold({initial_str}, {func_str})"
            else:
                return f"{iter_expr}.reduce({func_str}).unwrap()"

        elif isinstance(expr, IRListComp):
            return self._gen_list_comp(expr)

        elif isinstance(expr, IRDictComp):
            return self._gen_dict_comp(expr)

        elif isinstance(expr, IRSetComp):
            return self._gen_set_comp(expr)

        elif isinstance(expr, IRGeneratorExp):
            return self._gen_generator_exp(expr)

        elif isinstance(expr, IRJoinedStr):
            fmt_parts = []
            args = []
            for v in expr.values:
                if isinstance(v, (IRStrLit, str)):
                    val = v.value if isinstance(v, IRStrLit) else v
                    # Escape braces for Rust format string
                    escaped = val.replace("{", "{{").replace("}", "}}")
                    fmt_parts.append(escaped)
                elif isinstance(v, IRFormattedValue):
                    spec = v.format_spec or ""
                    # Handle conversions: !r -> {:?}, !s -> {} (default)
                    if v.conversion == 114: # ord('r')
                        spec = f":?{spec}"
                    elif spec:
                        spec = f":{spec}"
                    
                    val_expr = self._gen_expr(v.value)
                    # For Optional types, we need a way to display them. 
                    # If it's an Option, we can't directly use {} in format! unless we wrap it.
                    if isinstance(getattr(v.value, "result_type", None), IROptionType):
                        val_expr = f"{val_expr}.as_ref().map(|v| format!(\"{{}}\", v)).unwrap_or(\"None\".to_string())"
                    elif isinstance(getattr(v.value, "result_type", None), IRSumType):
                         # For sum types, we probably want debug format if no special display
                         if ":" not in spec:
                             spec = f":?{spec}"
                             
                    fmt_parts.append(f"{{{spec}}}")
                    args.append(val_expr)
            
            fmt_str = "".join(fmt_parts)
            if not args:
                return f'"{fmt_str}".to_string()'
            args_str = ", ".join(args)
            return f'format!("{fmt_str}", {args_str})'

        return f"/* unknown expr {type(expr).__name__} */"

    def _gen_condition(self, expr: IRExpr) -> str:
        """Generate a boolean expression suitable for if/while conditions in Rust."""
        expr_str = self._gen_expr(expr)
        
        # Already boolean?
        if isinstance(expr.result_type, IRBoolType):
            return expr_str
            
        # Optional?
        if isinstance(expr.result_type, IROptionType):
            # Special case for 'not x' where x is Optional
            if isinstance(expr, IRUnaryOpExpr) and expr.op == "not":
                return expr_str # Already handled in _gen_expr for Optional
            return f"{expr_str}.is_some()"
            
        # List/Set/Dict/String? (Truthiness based on empty)
        if isinstance(expr.result_type, (IRListType, IRSetType, IRDictType, IRStrType)):
            return f"!{expr_str}.is_empty()"
            
        # Int? (Truthiness != 0)
        if isinstance(expr.result_type, IRIntType):
            return f"{expr_str} != 0"
            
        # Float? (Truthiness != 0.0)
        if isinstance(expr.result_type, IRFloatType):
            return f"{expr_str} != 0.0"
            
        return expr_str

    def _gen_lambda(self, expr: IRLambda) -> str:
        params = ", ".join(f"{p.name}" for p in expr.params)
        body = self._gen_expr(expr.body)
        return f"|{params}| {{ {body} }}"

    def _gen_list_comp(self, node: IRListComp) -> str:
        elem_t = self._get_rust_type(node.result_type.element_type)
        inner = f"let mut __res = Vec::<{elem_t}>::new(); "
        
        # Build nested loops for generators
        loop_code = ""
        close_braces = ""
        for gen in node.generators:
            target = self._gen_comp_target(gen.target)
            iterable = self._get_comp_iter_expr(gen.iterable, getattr(gen.iterable, "result_type", None))
            loop_code += f"for __tmp in {iterable} {{ let {target} = __tmp; "
            for if_expr in gen.ifs:
                cond = self._gen_expr(if_expr)
                loop_code += f"if {cond} {{ "
                close_braces += " } "
            close_braces += " } "
        
        elt = self._gen_expr(node.elt)
        push_code = f"__res.push({elt}); "
        
        return f"({{ {inner}{loop_code}{push_code}{close_braces} __res }})"

    def _gen_dict_comp(self, node: IRDictComp) -> str:
        self._uses_hashmap = True
        key_t = self._get_rust_type(node.result_type.key_type)
        val_t = self._get_rust_type(node.result_type.value_type)
        inner = f"let mut __res = HashMap::<{key_t}, {val_t}>::new(); "
        
        loop_code = ""
        close_braces = ""
        for gen in node.generators:
            target = self._gen_comp_target(gen.target)
            iterable = self._get_comp_iter_expr(gen.iterable, getattr(gen.iterable, "result_type", None))
            loop_code += f"for __tmp in {iterable} {{ let {target} = __tmp; "
            for if_expr in gen.ifs:
                cond = self._gen_expr(if_expr)
                loop_code += f"if {cond} {{ "
                close_braces += " } "
            close_braces += " } "
            
        key = self._gen_expr(node.key)
        val = self._gen_expr(node.value)
        insert_code = f"__res.insert({key}, {val}); "
        
        return f"({{ {inner}{loop_code}{insert_code}{close_braces} __res }})"

    def _gen_set_comp(self, node: IRSetComp) -> str:
        self._uses_hashmap = True
        elem_t = self._get_rust_type(node.result_type.element_type)
        inner = f"let mut __res = HashSet::<{elem_t}>::new(); "
        
        loop_code = ""
        close_braces = ""
        for gen in node.generators:
            target = self._gen_comp_target(gen.target)
            iterable = self._get_comp_iter_expr(gen.iterable, getattr(gen.iterable, "result_type", None))
            loop_code += f"for __tmp in {iterable} {{ let {target} = __tmp; "
            for if_expr in gen.ifs:
                cond = self._gen_expr(if_expr)
                loop_code += f"if {cond} {{ "
                close_braces += " } "
            close_braces += " } "
        
        elt = self._gen_expr(node.elt)
        insert_code = f"__res.insert({elt}); "
        
        return f"({{ {inner}{loop_code}{insert_code}{close_braces} __res }})"

    def _gen_generator_exp(self, node: IRGeneratorExp) -> str:
        chain = self._gen_comp_chain(node.generators, 0, node.elt)
        return f"Box::new({chain})"

    def _gen_comp_chain(self, generators, index, elt) -> str:
        gen = generators[index]
        target = self._gen_comp_target(gen.target)
        iterable = self._get_comp_iter_expr(gen.iterable, getattr(gen.iterable, "result_type", None))
        
        # Base iterator
        chain = iterable
        
        # Apply filters for this generator
        for if_expr in gen.ifs:
            cond = self._gen_expr(if_expr)
            chain = f"{chain}.filter(move |__tmp| {{ let {target} = __tmp.clone(); {cond} }})"
            
        # If there are more generators (inner loops)
        if index + 1 < len(generators):
            inner_chain = self._gen_comp_chain(generators, index + 1, elt)
            chain = f"{chain}.flat_map(move |__tmp| {{ let {target} = __tmp.clone(); {inner_chain} }})"
        else:
            elt_expr = self._gen_expr(elt)
            chain = f"{chain}.map(move |__tmp| {{ let {target} = __tmp.clone(); {elt_expr} }})"
            
        return chain

    def _get_comp_iter_expr(self, iterable, iterable_type) -> str:
        iterable_str = self._gen_expr(iterable)
        is_direct_iter = False
        if isinstance(iterable, IRFunctionCall):
            if iterable.name in ("zip", "enumerate", "map", "reversed"):
                is_direct_iter = True
        
        if isinstance(iterable_type, (IRIteratorType, IRGeneratorType)):
            is_direct_iter = True
            
        if isinstance(iterable_type, IRDictType):
            return f"{iterable_str}.clone().into_keys()"
        elif isinstance(iterable_type, IRStrType):
            return f"{iterable_str}.chars().map(|c| c.to_string())"
        elif is_direct_iter:
            return iterable_str
        else:
            return f"{iterable_str}.clone().into_iter()"

    def _gen_comp_target(self, target) -> str:
        if isinstance(target, IRName):
            return _mangle(target.name)
        if isinstance(target, IRTupleLit):
            elems = ", ".join(self._gen_comp_target(e) for e in target.elements)
            return f"({elems})"
        return "_"

    def _gen_binop(self, expr) -> str:
        if expr.trait_info:
            trait_name, method_name = expr.trait_info
            left = self._gen_expr(expr.left)
            right = self._gen_expr(expr.right)
            
            # Prevent move errors for classes in binary ops
            if isinstance(getattr(expr.left, "result_type", None), IRClassType):
                left = f"{left}.clone()"
            if isinstance(getattr(expr.right, "result_type", None), IRClassType):
                right = f"{right}.clone()"
                
            return f"{left} {expr.op} {right}"

        if expr.op == "/":
            left = self._gen_expr_as_float(expr.left)
            right = self._gen_expr_as_float(expr.right)
            return f"{left} / {right}"
        if expr.op == "//":
            left = self._gen_expr(expr.left)
            right = self._gen_expr(expr.right)
            return f"({left} as f64 / {right} as f64).floor() as i32"
        if expr.op == "+" and isinstance(expr.result_type, IRStrType):
            left = self._gen_expr(expr.left)
            right = self._gen_expr(expr.right)
            return f"{left}.to_string() + &{right}"
        if expr.op == "+" and isinstance(expr.result_type, IRListType):
            left = self._gen_expr(expr.left)
            right = self._gen_expr(expr.right)
            elem_type = self._get_rust_type(expr.result_type.element_type)
            return f"({{ let mut __v: Vec<{elem_type}> = {left}.clone(); __v.extend({right}.clone()); __v }})"
        if expr.op == "*" and isinstance(expr.result_type, IRListType):
            left = self._gen_expr(expr.left)
            right = self._gen_expr(expr.right)
            return f"{left}.repeat({right} as usize)"
        if expr.op == "*" and isinstance(expr.result_type, IRStrType):
            if isinstance(expr.left, IRStrLit):
                left_str = self._gen_expr(expr.left)
                right_n = self._gen_expr(expr.right)
                return f"{left_str}.to_string().repeat({right_n})"
            elif isinstance(expr.right, IRStrLit):
                left_n = self._gen_expr(expr.left)
                right_str = self._gen_expr(expr.right)
                return f"{right_str}.to_string().repeat({left_n})"
            else:
                left = self._gen_expr(expr.left)
                right = self._gen_expr(expr.right)
                return f"{left}.repeat({right})"

        if isinstance(expr.result_type, IRFloatType):
            left = self._gen_expr_as_float(expr.left)
            right = self._gen_expr_as_float(expr.right)
        else:
            left = self._gen_expr(expr.left)
            right = self._gen_expr(expr.right)

        return f"{left} {expr.op} {right}"

    def _gen_expr_as_float(self, expr) -> str:
        if isinstance(expr, IRIntLit):
            return f"{expr.value}.0_f64"
        if isinstance(expr, IRFloatLit):
            return self._gen_expr(expr)
        if isinstance(expr, IRName):
            return f"({expr.name} as f64)"
        inner = self._gen_expr(expr)
        if isinstance(expr, IRBinOp) and isinstance(expr.result_type, IRFloatType):
            return inner
        return f"({inner}) as f64"

    def _gen_isinstance(self, expr: IRIsInstance) -> str:
        obj_expr = self._gen_expr(expr.obj)
        obj_type = expr.obj.result_type
        check_type = expr.check_type

        # Handle None check (type(None) or known UnitType)
        if isinstance(check_type, IRUnitType):
            if isinstance(obj_type, IROptionType):
                return f"{obj_expr}.is_none()"
            return f"({obj_expr} == ())"

        # Handle SumType (Union) checks
        if isinstance(obj_type, IRSumType):
            enum_name = self._get_sum_type_name(obj_type)
            # Find the variant that matches check_type
            variant_rust_type = self._get_rust_type(check_type)
            variant_name = self._get_variant_name(variant_rust_type)
            return f"matches!({obj_expr}, {enum_name}::{variant_name}(_))"

        # Handle Option checks
        if isinstance(obj_type, IROptionType):
            # isinstance(x, Optional[T]) - always true if it matches checking T or being None
            if isinstance(check_type, IROptionType):
                return "true"
            # isinstance(x, T) where x is Optional[T]
            if self._get_rust_type(obj_type.inner_type) == self._get_rust_type(check_type):
                return f"{obj_expr}.is_some()"
            return "false"

        # Handle List/Dict/Set checks
        if isinstance(check_type, (IRListType, IRDictType, IRSetType)):
            if type(obj_type) == type(check_type):
                return "true"
            return "false"

        # Handle Class checks
        if isinstance(check_type, IRClassType):
            if isinstance(obj_type, IRClassType) and obj_type.name == check_type.name:
                return "true"
            return "false"

        # Default: if types match exactly in Rust
        if self._get_rust_type(obj_type) == self._get_rust_type(check_type):
            return "true"
        
        return "false"
