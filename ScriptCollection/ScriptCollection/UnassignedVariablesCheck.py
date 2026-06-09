import ast
import os
from pathlib import Path
from .GeneralUtilities import GeneralUtilities


class UnassignedVariablesCheck:
    """Detects bare PEP 526 annotation occurrences (`name: Type` without `= ...`) at
    any scope in Python source files.

    Bare annotations produce inconsistent coverage between Python 3.13 (eager
    evaluation) and 3.14+ (PEP 749 deferred evaluation). Adding an explicit default
    (often `= None`) makes coverage deterministic across versions.

    Skips class bodies of @dataclass / TypedDict / NamedTuple / BaseModel / Protocol
    (where bare annotations have a defined field-semantic), and skips multi-line
    annotation statements."""

    @staticmethod
    @GeneralUtilities.check_arguments
    def find(folder: str) -> list[tuple[str, int, str]]:
        """Recursively walks every *.py file under `folder` and returns all bare
        annotation occurrences. Each tuple is (file_path, line_number, variable_name)."""
        special_decorators = {"dataclass", "attrs", "define", "frozen"}
        special_bases = {"TypedDict", "NamedTuple", "BaseModel", "Protocol"}
        results: list[tuple[str, int, str]] = []

        def get_name(node):
            if isinstance(node, ast.Name):
                return node.id
            if isinstance(node, ast.Attribute):
                return node.attr
            if isinstance(node, ast.Call):
                return get_name(node.func)
            return None

        def is_special_class(cls_node) -> bool:
            for decorator in cls_node.decorator_list:
                if get_name(decorator) in special_decorators:
                    return True
            for base in cls_node.bases:
                if get_name(base) in special_bases:
                    return True
            return False

        def walk(node, inside_special_class_body: bool, file_path_str: str):
            if isinstance(node, ast.AnnAssign):
                if not inside_special_class_body:
                    if node.value is None and isinstance(node.target, ast.Name):
                        if getattr(node, "end_lineno", node.lineno) == node.lineno:
                            results.append((file_path_str, node.lineno, node.target.id))
                return
            if isinstance(node, ast.ClassDef):
                is_special = is_special_class(node)
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        walk(child, False, file_path_str)
                    else:
                        walk(child, is_special, file_path_str)
                return
            for child in ast.iter_child_nodes(node):
                walk(child, False, file_path_str)

        for file_path in Path(folder).rglob("*.py"):
            if "__pycache__" in file_path.parts:
                continue
            try:
                source = file_path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            try:
                tree = ast.parse(source)
            except SyntaxError:
                continue
            walk(tree, False, str(file_path))

        return results

    @staticmethod
    @GeneralUtilities.check_arguments
    def assert_no_unassigned_variables_in_codeunit(codeunit_folder: str) -> None:
        """Convenience helper for testcases. Scans the codeunit's source package
        (`<codeunit_folder>/<codeunit_name>/`) and test package (`<codeunit_folder>/<codeunit_name>Tests/`)
        for bare PEP 526 annotations and raises AssertionError listing all violations
        if any are found."""
        codeunit_name = os.path.basename(codeunit_folder)
        violations: list[str] = []
        for package_name in (codeunit_name, f"{codeunit_name}Tests"):
            package_folder = os.path.join(codeunit_folder, package_name)
            GeneralUtilities.assert_folder_exists(package_folder)
            for file_path, lineno, name in UnassignedVariablesCheck.find(package_folder):
                violations.append(f"{file_path}:{lineno} bare annotation '{name}: Type' - add '= None' (or a real default)")
        if violations:
            raise AssertionError(f"Found {len(violations)} bare annotation(s) in the codebase:\n  - " + "\n  - ".join(violations))
