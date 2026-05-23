from __future__ import annotations
import sys
from pathlib import Path
from py2rust.config import CompilerConfig
from py2rust.project.project_config import ProjectConfig
from py2rust.project.import_resolver import ImportResolver
from py2rust.project.module_graph import ModuleGraph
from py2rust.frontend.parser import parse
from py2rust.middleend.ir_builder import build_ir
from py2rust.middleend.dependency_manager import DependencyManager
from py2rust.backend.rust_codegen import generate_rust
from py2rust.backend.rust_formatter import format_rust
from py2rust.backend.workspace_generator import WorkspaceGenerator
from py2rust.utils.logger import setup_logger
from py2rust.project.build_cache import BuildCache

def compile_repo(config: CompilerConfig) -> bool:
    logger = setup_logger(config.verbose)
    
    # repo_root can be inferred from input_file if it's a directory
    input_path = Path(config.input_file).resolve()
    if input_path.is_dir():
        repo_root = input_path
    else:
        repo_root = Path(config.repo_root or input_path.parent).resolve()
        
    toml_path = repo_root / "pyproject.toml"
    proj_config = ProjectConfig.load_from_toml(toml_path)
    
    package_dir = config.package_dir or proj_config.package_dir
    project_name = proj_config.name
    version = proj_config.version
    
    # Set the config's repo_root so TypeChecker can instantiate the resolver
    config.repo_root = str(repo_root)
    if package_dir:
        config.package_dir = package_dir
        
    from py2rust.utils.errors import SemanticError
    sys_path_resolved = []
    for p in proj_config.sys_path:
        p_path = Path(p)
        if not p_path.is_absolute():
            p_path = (repo_root / p_path).resolve()
        else:
            p_path = p_path.resolve()
        if not p_path.exists():
            raise SemanticError(f"sys_path directory does not exist: '{p}'")
        sys_path_resolved.append(p_path)

    resolver = ImportResolver(
        repo_root=repo_root,
        sys_path=sys_path_resolved,
        package_dir=package_dir,
        exclude_patterns=proj_config.exclude
    )
    
    graph = ModuleGraph(resolver)
    for mod_name, file_path in resolver.local_modules.items():
        graph.add_module(mod_name, file_path)
        
    graph.build_graph()
    
    try:
        sorted_modules = graph.topological_sort()
    except ValueError as e:
        print(f"Compilation failed: {str(e)}", file=sys.stderr)
        raise e
        
    compiled_modules: dict[str, str] = {}
    
    from py2rust.middleend.cross_module_symbol_table import CrossModuleSymbolTable
    cross_module_table = CrossModuleSymbolTable()
    
    # Accumulate all crate dependencies across all compiled modules
    global_dep_manager = DependencyManager()
    
    # Add any explicit dependencies from ProjectConfig
    if proj_config.dependencies:
        for crate, ver in proj_config.dependencies.items():
            if isinstance(ver, dict):
                global_dep_manager.add_dependency(crate, version=ver.get("version"), features=ver.get("features"))
            else:
                global_dep_manager.add_dependency(crate, version=ver)
                
    # Initialize incremental build cache
    cache_dir = repo_root / ".py2rust"
    cache_file = cache_dir / "cache.json"
    cache = BuildCache(cache_file)
    recompiled_modules: set[str] = set()

    for mod_name in sorted_modules:
        file_path = resolver.local_modules[mod_name]
        logger.info(f"Processing module: {mod_name} ({file_path})")
        
        try:
            source = file_path.read_text(encoding="utf-8")
            source_lines = source.splitlines()
            
            module = parse(source, filename=str(file_path))
            
            # Create a module-specific dependency manager to track this module's imports
            mod_dep_manager = DependencyManager()
            
            ir_module = build_ir(
                module,
                filename=str(file_path),
                source_lines=source_lines,
                config=config,
                dependency_manager=mod_dep_manager,
                cross_module_table=cross_module_table,
                module_name=mod_name
            )
            
            current_hash = BuildCache.get_file_hash(file_path)
            cache_entry = cache.get_entry(mod_name)
            
            recompile = False
            if config.force:
                recompile = True
            elif not cache_entry:
                recompile = True
            elif cache_entry.get("content_hash") != current_hash:
                recompile = True
            else:
                current_deps = graph.dependencies.get(mod_name, set())
                cached_deps = cache_entry.get("dependency_hashes", {})
                if set(current_deps) != set(cached_deps.keys()):
                    recompile = True
                else:
                    for dep in current_deps:
                        if dep in recompiled_modules:
                            recompile = True
                            break
                        dep_path = resolver.local_modules.get(dep)
                        if dep_path:
                            dep_current_hash = BuildCache.get_file_hash(dep_path)
                            if cached_deps.get(dep) != dep_current_hash:
                                recompile = True
                                break
                        else:
                            recompile = True
                            break
            
            if recompile:
                logger.info(f"Recompiling module: {mod_name}")
                rust_code = generate_rust(ir_module, dependency_manager=mod_dep_manager, config=config)
                if config.format_output:
                    rust_code = format_rust(rust_code)
                
                # Save cache entry
                dependency_hashes = {}
                for dep in graph.dependencies.get(mod_name, set()):
                    dep_path = resolver.local_modules.get(dep)
                    if dep_path:
                        dependency_hashes[dep] = BuildCache.get_file_hash(dep_path)
                cache.set_entry(
                    module_name=mod_name,
                    file_path=file_path,
                    content_hash=current_hash,
                    dependency_hashes=dependency_hashes,
                    rust_code=rust_code
                )
                recompiled_modules.add(mod_name)
            else:
                logger.info(f"Cache hit for module: {mod_name} - using cached Rust code")
                rust_code = cache_entry["rust_code"]
            
            compiled_modules[mod_name] = rust_code
            
            # Merge module dependencies into the global manager
            for crate, info in mod_dep_manager.dependencies.items():
                features = info.get("features", [])
                dep_ver = info.get("version")
                global_dep_manager.add_dependency(crate, version=dep_ver, features=features)
                
        except Exception as e:
            print(f"Error compiling module '{mod_name}': {str(e)}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            raise e
            
    # Write output to the workspace directory
    output_dir = Path(config.output_file or (repo_root / "dist")).resolve()
    
    workspace = WorkspaceGenerator(
        output_dir=output_dir,
        project_name=project_name,
        version=version
    )
    workspace.dep_manager = global_dep_manager
    
    # Generate the module hierarchy
    entry_point = proj_config.entry_point
    workspace.generate_mod_hierarchy(compiled_modules, entry_point=entry_point)
    
    logger.info(f"Workspace generated successfully at: {output_dir}")
    return True
