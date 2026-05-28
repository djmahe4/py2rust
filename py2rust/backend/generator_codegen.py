# generator_codegen.py - Generator and yielding state-machine code generation mixin for Rust codegen
from __future__ import annotations
from py2rust.ir.ir_nodes import (
    IRFunction, IRParam, IRYield, IRYieldFrom, IRIf, IRWhile, IRForRange, IRForIter,
    IRWith, IRVarDecl, IRAssign, IRAugAssign, IRReturn, IRName, IRTupleLit,
    IRClassType, IRExternalPythonType, IRDictType, IRStrType, IRFunctionCall
)
from .codegen_helpers import _mangle, _collect_mutated_vars, _collect_decls

class GeneratorCodegenMixin:
    def _capture_stmt_emit(self, stmt) -> str:
        original_lines = self._lines
        self._lines = []
        original_indent = self._indent
        self._indent = 0
        try:
            self._gen_stmt(stmt)
        finally:
            generated = "\n".join(self._lines)
            self._lines = original_lines
            self._indent = original_indent
        return generated

    def _has_yield(self, nodes) -> bool:
        if isinstance(nodes, (list, tuple)):
            return any(self._has_yield(node) for node in nodes)
        
        from py2rust.ir.ir_nodes import IRYield, IRYieldFrom
        if isinstance(nodes, (IRYield, IRYieldFrom)):
            return True
        
        from py2rust.ir.ir_nodes import IRIf, IRWhile, IRForRange, IRForIter, IRWith, IRVarDecl, IRAssign, IRAugAssign, IRReturn
        if isinstance(nodes, IRIf):
            if self._has_yield(nodes.then_body):
                return True
            for _, b in nodes.elif_clauses:
                if self._has_yield(b):
                    return True
            if nodes.else_body:
                if self._has_yield(nodes.else_body):
                    return True
            return False
        if isinstance(nodes, (IRWhile, IRForRange, IRForIter)):
            return self._has_yield(nodes.body)
        if isinstance(nodes, IRWith):
            return self._has_yield(nodes.body)
        if isinstance(nodes, (IRAssign, IRAugAssign, IRVarDecl)):
            return self._has_yield(nodes.value)
        if isinstance(nodes, IRReturn):
            return self._has_yield(nodes.value) if nodes.value else False
        
        return False

    def compile_block(self, stmts, current_state, next_state, next_free_state):
        if not stmts:
            return [(current_state, f"self.__state = {next_state};")], next_free_state

        # Find the first yielding/control flow statement
        yield_idx = -1
        for idx, stmt in enumerate(stmts):
            if self._has_yield(stmt):
                yield_idx = idx
                break

        if yield_idx == -1:
            # None of the statements yield!
            # Just generate them sequentially in current_state.
            code = []
            for stmt in stmts:
                if isinstance(stmt, IRReturn):
                    code.append("self.__state = 999999;")
                    code.append("return None;")
                    break
                else:
                    code.append(self._capture_stmt_emit(stmt))
            
            # If we didn't return, set self.__state = next_state
            if not any(isinstance(stmt, IRReturn) for stmt in stmts):
                code.append(f"self.__state = {next_state};")
                
            return [(current_state, "\n".join(code))], next_free_state

        # There is a yielding/control-flow statement at yield_idx!
        # First, compile any non-yielding statements before it.
        prefix_code = []
        if yield_idx > 0:
            for idx in range(yield_idx):
                stmt = stmts[idx]
                if isinstance(stmt, IRReturn):
                    prefix_code.append("self.__state = 999999;")
                    prefix_code.append("return None;")
                    break
                else:
                    prefix_code.append(self._capture_stmt_emit(stmt))
            
            if any(isinstance(stmts[idx], IRReturn) for idx in range(yield_idx)):
                # If we returned, just return the prefix blocks
                return [(current_state, "\n".join(prefix_code))], next_free_state

        # Now compile the yielding/control flow statement itself!
        yield_stmt = stmts[yield_idx]
        
        if yield_idx > 0:
            state_for_yield = next_free_state
            next_free_state += 1
            prefix_code.append(f"self.__state = {state_for_yield};")
            prefix_blocks = [(current_state, "\n".join(prefix_code))]
        else:
            state_for_yield = current_state
            prefix_blocks = []

        # Compile the rest of the statements after the yielding statement.
        state_after_yield = next_free_state
        next_free_state += 1

        # Compile yield_stmt
        yield_blocks, next_free_state = self.compile_yielding_stmt(
            yield_stmt, state_for_yield, state_after_yield, next_free_state
        )

        # Compile all subsequent statements starting from state_after_yield
        suffix_blocks, next_free_state = self.compile_block(
            stmts[yield_idx + 1:], state_after_yield, next_state, next_free_state
        )

        return prefix_blocks + yield_blocks + suffix_blocks, next_free_state

    def compile_yielding_stmt(self, stmt, current_state, next_state, next_free_state):
        from py2rust.ir.ir_nodes import IRYield, IRYieldFrom, IRIf, IRWhile, IRForRange, IRForIter, IRAssign
        
        if isinstance(stmt, IRAssign) and isinstance(stmt.value, (IRYield, IRYieldFrom)):
            stmt = stmt.value

        if isinstance(stmt, IRYield):
            val = self._gen_expr(stmt.value)
            code = f"self.__state = {next_state};\nreturn Some({val});"
            return [(current_state, code)], next_free_state

        elif isinstance(stmt, IRYieldFrom):
            val = self._gen_expr(stmt.value)
            code = f"""if self.__sub_iter.is_none() {{
    self.__sub_iter = Some(Box::new(({val}).into_iter()));
}}
if let Some(ref mut sub) = self.__sub_iter {{
    if let Some(val) = sub.next() {{
        return Some(val);
    }}
}}
self.__sub_iter = None;
self.__state = {next_state};"""
            return [(current_state, code)], next_free_state

        elif isinstance(stmt, IRIf):
            branch_states = []
            for _ in stmt.branches:
                branch_states.append(next_free_state)
                next_free_state += 1
                
            cond_lines = []
            for idx, (cond, _) in enumerate(stmt.branches):
                target_state = branch_states[idx]
                if cond is None:
                    cond_lines.append(f"else {{\n    self.__state = {target_state};\n}}")
                else:
                    cond_str = self._gen_expr(cond)
                    if idx == 0:
                        cond_lines.append(f"if {cond_str} {{\n    self.__state = {target_state};\n}}")
                    else:
                        cond_lines.append(f"else if {cond_str} {{\n    self.__state = {target_state};\n}}")
                        
            if not any(cond is None for cond, _ in stmt.branches):
                cond_lines.append(f"else {{\n    self.__state = {next_state};\n}}")
                
            current_block = (current_state, "\n".join(cond_lines))
            
            all_blocks = [current_block]
            for idx, (_, body_stmts) in enumerate(stmt.branches):
                body_state = branch_states[idx]
                body_blocks, next_free_state = self.compile_block(
                    body_stmts, body_state, next_state, next_free_state
                )
                all_blocks.extend(body_blocks)
                
            return all_blocks, next_free_state

        elif isinstance(stmt, IRWhile):
            cond_str = self._gen_expr(stmt.condition)
            body_state = next_free_state
            next_free_state += 1
            
            cond_code = f"""if {cond_str} {{
    self.__state = {body_state};
}} else {{
    self.__state = {next_state};
}}"""
            current_block = (current_state, cond_code)
            
            body_blocks, next_free_state = self.compile_block(
                stmt.body, body_state, current_state, next_free_state
            )
            
            return [current_block] + body_blocks, next_free_state

        elif isinstance(stmt, (IRForRange, IRForIter)):
            iter_name = f"__for_iter_{current_state}"
            
            if isinstance(stmt, IRForRange):
                start = self._gen_expr(stmt.start)
                stop = self._gen_expr(stmt.stop)
                if stmt.step is None:
                    iter_expr = f"({start}..{stop})"
                else:
                    step = self._gen_expr(stmt.step)
                    iter_expr = f"({start}..{stop}).step_by({step} as usize)"
                
                target_name = _mangle(stmt.target) if isinstance(stmt.target, (str, IRName)) else "unknown"
                if isinstance(stmt.target, (str, IRName)):
                    t_name = stmt.target.name if isinstance(stmt.target, IRName) else stmt.target
                    t_type = self._decl_types.get(t_name)
                    elem_type = self._get_rust_type(t_type) if t_type else "i32"
                else:
                    elem_type = "i32"
                
                self._generator_sub_iters[iter_name] = f"Option<Box<dyn Iterator<Item = {elem_type}>>>"
                
                cond_state = next_free_state
                body_state = next_free_state + 1
                next_free_state += 2
                
                init_code = f"""self.{iter_name} = Some(Box::new(({iter_expr}).into_iter()));
self.__state = {cond_state};"""
            else:
                iterable_str = self._gen_expr(stmt.iterable)
                target_name = _mangle(stmt.target) if isinstance(stmt.target, (str, IRName)) else "unknown"
                if isinstance(stmt.target, (str, IRName)):
                    t_name = stmt.target.name if isinstance(stmt.target, IRName) else stmt.target
                    t_type = self._decl_types.get(t_name)
                    elem_type = self._get_rust_type(t_type) if t_type else "i32"
                else:
                    elem_type = "i32"
                
                self._generator_sub_iters[iter_name] = f"Option<Box<dyn Iterator<Item = {elem_type}>>>"
                
                cond_state = next_free_state
                body_state = next_free_state + 1
                next_free_state += 2
                
                is_direct_iter = False
                if isinstance(stmt.iterable, IRFunctionCall):
                    if stmt.iterable.name in ("zip", "enumerate", "map", "reversed"):
                        is_direct_iter = True

                is_ext = False
                if isinstance(stmt.iterable_type, IRClassType) and stmt.iterable_type.name == "ExternalObject":
                    is_ext = True
                elif isinstance(stmt.iterable_type, IRExternalPythonType) and not stmt.iterable_type.is_local:
                    is_ext = True

                if isinstance(stmt.iterable_type, IRDictType):
                    iter_expr = f"{iterable_str}.keys()"
                elif isinstance(stmt.iterable_type, IRStrType):
                    iter_expr = f"{iterable_str}.chars().map(|c| c.to_string())"
                elif is_direct_iter:
                    iter_expr = iterable_str
                elif is_ext:
                    iter_expr = f"{iterable_str}.iter()?"
                else:
                    iter_expr = f"&{iterable_str}"
                
                if is_direct_iter or is_ext or isinstance(stmt.iterable_type, IRStrType):
                    init_code = f"""self.{iter_name} = Some(Box::new(({iter_expr}).into_iter()));
self.__state = {cond_state};"""
                else:
                    init_code = f"""self.{iter_name} = Some(Box::new((&{iterable_str}).into_iter().cloned()));
self.__state = {cond_state};"""

            init_block = (current_state, init_code)
            
            # If target is tuple unpack (e.g. key, val in dict or index, val in enumerate)
            if isinstance(stmt.target, IRTupleLit):
                temp_names = [f"__tmp_{i}" for i in range(len(stmt.target.elements))]
                temps_str = ", ".join(temp_names)
                unpack_lines = [f"let ({temps_str}) = val;"]
                for i, e in enumerate(stmt.target.elements):
                    if isinstance(e, IRName):
                        unpack_lines.append(f"self.{_mangle(e.name)} = {temp_names[i]};")
                unpack_str = "\n        ".join(unpack_lines)
                
                cond_code = f"""if let Some(ref mut iter) = self.{iter_name} {{
    if let Some(val) = iter.next() {{
        {unpack_str}
        self.__state = {body_state};
    }} else {{
        self.{iter_name} = None;
        self.__state = {next_state};
    }}
}} else {{
    self.__state = {next_state};
}}"""
            else:
                cond_code = f"""if let Some(ref mut iter) = self.{iter_name} {{
    if let Some(val) = iter.next() {{
        self.{target_name} = val;
        self.__state = {body_state};
    }} else {{
        self.{iter_name} = None;
        self.__state = {next_state};
    }}
}} else {{
    self.__state = {next_state};
}}"""
            cond_block = (cond_state, cond_code)
            
            body_blocks, next_free_state = self.compile_block(
                stmt.body, body_state, cond_state, next_free_state
            )
            
            return [init_block, cond_block] + body_blocks, next_free_state

        return [(current_state, f"self.__state = {next_state};")], next_free_state

    def _gen_generator_struct(self, func: IRFunction) -> None:
        self._uses_py_error = True
        self._mutated_vars = _collect_mutated_vars(func.body)
        decls, pre_declare = _collect_decls(func.body, self._uses_python_wrappers)
        self._decl_types = dict(decls)
        
        struct_name = "".join(part.capitalize() for part in func.name.split("_")) + "Generator"
        
        fields = {}
        for p in func.params:
            fields[_mangle(p.name)] = self._get_rust_type(p.type_)
        for name, type_ in self._decl_types.items():
            if name != "_":
                fields[_mangle(name)] = self._get_rust_type(type_)
                
        self._generator_fields = set(func.params[i].name for i in range(len(func.params))) | set(self._decl_types.keys())
        self._generator_sub_iters = {}
        
        from py2rust.ir.ir_nodes import IRGeneratorType, IRIteratorType, IRIterableType
        yield_type = "()"
        if isinstance(func.return_type, IRGeneratorType):
            yield_type = self._get_rust_type(func.return_type.yield_type)
        elif isinstance(func.return_type, (IRIteratorType, IRIterableType)):
            yield_type = self._get_rust_type(func.return_type.element_type)
            
        blocks, _ = self.compile_block(func.body, 0, 999999, 1)
        
        has_yield_from = False
        def check_yield_from(nodes):
            nonlocal has_yield_from
            if isinstance(nodes, (list, tuple)):
                for n in nodes:
                    check_yield_from(n)
                return
            from py2rust.ir.ir_nodes import IRYieldFrom
            if isinstance(nodes, IRYieldFrom):
                has_yield_from = True
            from py2rust.ir.ir_nodes import IRIf, IRWhile, IRForRange, IRForIter, IRWith, IRAssign, IRAugAssign, IRVarDecl
            if isinstance(nodes, IRIf):
                check_yield_from(nodes.then_body)
                for _, b in nodes.elif_clauses:
                    check_yield_from(b)
                if nodes.else_body:
                    check_yield_from(nodes.else_body)
            elif isinstance(nodes, (IRWhile, IRForRange, IRForIter, IRWith)):
                check_yield_from(nodes.body)
            elif isinstance(nodes, (IRAssign, IRAugAssign, IRVarDecl)):
                check_yield_from(nodes.value)
        check_yield_from(func.body)
        
        has_complex_flow = False
        def check_complex(nodes, in_loop=False):
            nonlocal has_complex_flow
            if isinstance(nodes, (list, tuple)):
                for n in nodes:
                    check_complex(n, in_loop)
                return
            from py2rust.ir.ir_nodes import IRYield, IRYieldFrom, IRBreak, IRContinue, IRIf, IRWhile, IRForRange, IRForIter, IRAssign, IRAugAssign, IRVarDecl
            if isinstance(nodes, (IRBreak, IRContinue)):
                has_complex_flow = True
            elif isinstance(nodes, (IRYield, IRYieldFrom)):
                if in_loop:
                    has_complex_flow = True
            elif isinstance(nodes, IRIf):
                check_complex(nodes.then_body, in_loop)
                for _, b in nodes.elif_clauses:
                    check_complex(b, in_loop)
                if nodes.else_body:
                    check_complex(nodes.else_body, in_loop)
            elif isinstance(nodes, (IRWhile, IRForRange, IRForIter)):
                check_complex(nodes.body, in_loop=True)
            elif isinstance(nodes, (IRAssign, IRAugAssign, IRVarDecl)):
                check_complex(nodes.value, in_loop)
        check_complex(func.body)
        
        if has_complex_flow:
            self._emit("// WARNING: Generator contains complex control flow (yield inside loop or break/continue)")
            
        self._emit(f"pub struct {struct_name} {{")
        self._indent += 1
        self._emit("__state: i32,")
        if has_yield_from:
            self._emit(f"__sub_iter: Option<Box<dyn Iterator<Item = {yield_type}>>>,")
        for name, rust_type in fields.items():
            self._emit(f"{name}: {rust_type},")
        for sub_iter_name, sub_iter_type in self._generator_sub_iters.items():
            self._emit(f"{sub_iter_name}: {sub_iter_type},")
        self._indent -= 1
        self._emit("}")
        self._emit_blank()
        
        param_strs = []
        for p in func.params:
            param_strs.append(f"{_mangle(p.name)}: {self._get_rust_type(p.type_)}")
        params_decl = ", ".join(param_strs)
        
        self._emit(f"impl {struct_name} {{")
        self._indent += 1
        self._emit(f"pub fn new({params_decl}) -> Self {{")
        self._indent += 1
        self._emit("Self {")
        self._indent += 1
        self._emit("__state: 0,")
        if has_yield_from:
            self._emit("__sub_iter: None,")
        for p in func.params:
            self._emit(f"{_mangle(p.name)},")
        for name, type_ in self._decl_types.items():
            if name != "_":
                m_name = _mangle(name)
                if m_name not in [p.name for p in func.params]:
                    default = self._default_value(type_)
                    self._emit(f"{m_name}: {default},")
        for sub_iter_name in self._generator_sub_iters:
            self._emit(f"{sub_iter_name}: None,")
        self._indent -= 1
        self._emit("}")
        self._indent -= 1
        self._emit("}")
        self._indent -= 1
        self._emit("}")
        self._emit_blank()
        
        self._emit(f"impl Iterator for {struct_name} {{")
        self._indent += 1
        self._emit(f"type Item = {yield_type};")
        self._emit("fn next(&mut self) -> Option<Self::Item> {")
        self._indent += 1
        self._emit("loop {")
        self._indent += 1
        self._emit("match self.__state {")
        self._indent += 1
        
        for state_id, code in blocks:
            self._emit(f"{state_id} => {{")
            self._indent += 1
            for line in code.split("\n"):
                if line.strip():
                    self._emit(line)
            self._indent -= 1
            self._emit("}")
            
        self._emit("999999 => return None,")
        self._emit("_ => return None,")
        
        self._indent -= 1
        self._emit("}")
        self._indent -= 1
        self._emit("}")
        self._indent -= 1
        self._emit("}")
        self._indent -= 1
        self._emit("}")
        self._emit_blank()
        
        self._generator_fields = set()
