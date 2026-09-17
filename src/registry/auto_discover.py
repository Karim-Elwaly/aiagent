"""
UAOS Auto-Discovery

Automatically discovers and registers all tools from the tools/ directory
at startup. Convention: every module in tools/ exposes ToolSpec constants
ending with _SPEC (e.g., WEB_SEARCH_SPEC, CODE_EXECUTOR_SPEC).
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import pkgutil

from src.registry.tool_registry import ToolRegistry, ToolSpec

logger = logging.getLogger(__name__)


def register_all_tools(registry: ToolRegistry) -> int:
    """Auto-discover and register all tools from the tools/ package.

    Scans all modules in src.registry.tools and registers any module-level
    attributes that are ToolSpec instances (convention: name ends with _SPEC).

    This means adding a new tool is:
      1. Create src/registry/tools/my_tool.py
      2. Define MY_TOOL_SPEC = ToolSpec(...)
      3. Restart. Done.
    """
    import src.registry.tools as tools_pkg

    registered = 0
    errors = 0

    for importer, module_name, is_pkg in pkgutil.iter_modules(
        tools_pkg.__path__
    ):
        if is_pkg:
            continue  # skip sub-packages

        try:
            module = importlib.import_module(
                f"src.registry.tools.{module_name}"
            )
        except Exception as e:
            logger.error(
                "Failed to import tool module '%s': %s", module_name, e
            )
            errors += 1
            continue

        # Find all ToolSpec instances in the module
        for attr_name in dir(module):
            if not attr_name.endswith("_SPEC"):
                continue

            attr = getattr(module, attr_name)
            if isinstance(attr, ToolSpec):
                try:
                    registry.register(attr)
                    registered += 1
                except Exception as e:
                    logger.error(
                        "Failed to register tool '%s' from '%s': %s",
                        attr_name,
                        module_name,
                        e,
                    )
                    errors += 1

    logger.info(
        "Auto-discovery built-ins complete: %d tools registered, %d errors",
        registered,
        errors,
    )

    # Auto-discover user-generated tools from data/custom_tools/
    from src.core.config import ROOT_DIR

    custom_tools_dir = ROOT_DIR / "data" / "custom_tools"
    if custom_tools_dir.exists():
        for py_file in custom_tools_dir.glob("*.py"):
            if py_file.name.startswith("__"):
                continue
            module_name = f"custom_tool_{py_file.stem}"
            try:
                spec = importlib.util.spec_from_file_location(module_name, py_file)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    for attr_name in dir(mod):
                        if not attr_name.endswith("_SPEC"):
                            continue
                        attr = getattr(mod, attr_name)
                        if isinstance(attr, ToolSpec):
                            try:
                                registry.register(attr)
                                registered += 1
                                logger.info(
                                    "Discovered custom tool '%s' from %s",
                                    attr.name,
                                    py_file.name,
                                )
                            except Exception as re_err:
                                logger.warning(
                                    "Tool '%s' already registered or error: %s",
                                    attr.name,
                                    re_err,
                                )
            except Exception as e:
                logger.error("Failed to load custom tool file '%s': %s", py_file.name, e)
                errors += 1

    logger.info(
        "Total auto-discovery complete: %d tools registered, %d errors",
        registered,
        errors,
    )
    return registered

