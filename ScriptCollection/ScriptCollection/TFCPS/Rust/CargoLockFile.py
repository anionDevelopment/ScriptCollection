import os
import re
import tomllib
from ...GeneralUtilities import GeneralUtilities


class CargoLockFile:
    """Synchronizes the versions of the local packages in a "Cargo.lock"-file with the versions which their
    "Cargo.toml"-files declare.

    A local package is a package which is not resolved from a registry or a git-repository: the cargo-project itself
    and every path-dependency (directly or transitively). Cargo writes such a package into the lock-file without a
    "source"-entry, together with the version its cargo-file declared at the time the lock-file was written. When the
    version in a cargo-file changes (which happens on every new version of a codeunit), the lock-file is outdated and
    a build with "--locked" fails. Cargo can not update the lock-file without being allowed to resolve the dependencies
    again, so the versions of the local packages are adjusted textually here: everything else in the lock-file stays
    exactly as it is, no network-access is required and running it again does not change anything anymore."""

    __dependency_sections: tuple = ("dependencies", "dev-dependencies", "build-dependencies")
    # Cargo uses this version for a package whose cargo-file does not declare a version
    # (see https://doc.rust-lang.org/cargo/reference/manifest.html#the-version-field).
    __version_of_package_without_declared_version: str = "0.0.0"

    @staticmethod
    @GeneralUtilities.check_arguments
    def synchronize_versions_of_local_packages(cargo_file: str) -> None:
        """Sets the version of every local package in the lock-file next to the given cargo-file to the version
        which the cargo-file of that package declares. A cargo-project without lock-file (for example a library,
        which usually does not commit its lock-file) is left as it is."""
        lock_file = os.path.join(os.path.dirname(cargo_file), "Cargo.lock")
        if os.path.isfile(lock_file):
            CargoLockFile.set_versions_of_local_packages(lock_file, CargoLockFile.get_versions_of_local_packages(cargo_file))

    @staticmethod
    @GeneralUtilities.check_arguments
    def get_versions_of_local_packages(cargo_file: str) -> dict[str, str]:
        """Returns the names and the versions of the package of the given cargo-file and of all of its (also
        transitive) path-dependencies, read from their cargo-files."""
        result: dict[str, str] = {}
        CargoLockFile.__add_versions_of_local_packages(os.path.abspath(cargo_file), result, set())
        return result

    @staticmethod
    @GeneralUtilities.check_arguments
    def __add_versions_of_local_packages(cargo_file: str, result: dict[str, str], visited_cargo_files: set[str]) -> None:
        if cargo_file in visited_cargo_files:
            return
        visited_cargo_files.add(cargo_file)
        GeneralUtilities.assert_file_exists(cargo_file, f'The cargo-file "{cargo_file}" does not exist. If it belongs to a dependent codeunit, then this codeunit must be built before.')
        content: dict = tomllib.loads(GeneralUtilities.read_text_from_file(cargo_file))
        package: dict = content.get("package")
        GeneralUtilities.assert_condition(package is not None, f'The cargo-file "{cargo_file}" does not contain a package-section.')
        version = package.get("version", CargoLockFile.__version_of_package_without_declared_version)
        GeneralUtilities.assert_condition(isinstance(version, str), f'The version of the package in "{cargo_file}" is not declared as plain version-string, which is not supported.')
        result[package["name"]] = version
        cargo_project_folder = os.path.dirname(cargo_file)
        for relative_path in CargoLockFile.__get_paths_of_path_dependencies(content):
            dependency_cargo_file = os.path.abspath(os.path.join(cargo_project_folder, relative_path, "Cargo.toml"))
            CargoLockFile.__add_versions_of_local_packages(dependency_cargo_file, result, visited_cargo_files)

    @staticmethod
    @GeneralUtilities.check_arguments
    def __get_paths_of_path_dependencies(cargo_file_content: dict) -> list[str]:
        # Dependencies can be declared in the top-level-sections and in the target-specific sections
        # (for example "[target.'cfg(windows)'.dependencies]").
        dependency_tables: list[dict] = [cargo_file_content.get(section, {}) for section in CargoLockFile.__dependency_sections]
        for target_content in cargo_file_content.get("target", {}).values():
            dependency_tables.extend(target_content.get(section, {}) for section in CargoLockFile.__dependency_sections)
        result: list[str] = []
        for dependency_table in dependency_tables:
            for declaration in dependency_table.values():
                if isinstance(declaration, dict) and "path" in declaration:
                    result.append(declaration["path"])
        return result

    @staticmethod
    @GeneralUtilities.check_arguments
    def set_versions_of_local_packages(lock_file: str, versions_of_local_packages: dict[str, str]) -> None:
        """Sets the version of every package of the lock-file which has no source and whose name is contained in
        the given dictionary to the version stated there. A package of the lock-file which is not contained in the
        dictionary is not changed. The line-endings and all other lines of the lock-file are preserved."""
        lines: list[str] = GeneralUtilities.read_text_from_file(lock_file).splitlines(keepends=True)
        packages = CargoLockFile.__parse_packages(lines)
        changed_references: dict[str, str] = {}
        for package in packages:
            name: str = package["name"]
            if package["has_source"] or name not in versions_of_local_packages or package["version_line_index"] is None:
                continue
            old_version: str = package["version"]
            new_version: str = versions_of_local_packages[name]
            if old_version != new_version:
                line_index: int = package["version_line_index"]
                lines[line_index] = CargoLockFile.__replace_quoted_value(lines[line_index], old_version, new_version)
                # A dependency is referenced as "<name> <version>" instead of "<name>" when the lock-file contains
                # several packages with this name. Such a reference must be changed together with the version. When a
                # package from a registry has the same name and the same old version, then the reference can not be
                # assigned unambiguously to the local package, so it is not changed.
                if not any(other["has_source"] and other["name"] == name and other["version"] == old_version for other in packages):
                    changed_references[f"{name} {old_version}"] = f"{name} {new_version}"
        if len(changed_references) > 0:
            for package in packages:
                for line_index in range(package["start_line_index"], package["end_line_index"]):
                    lines[line_index] = CargoLockFile.__replace_dependency_reference(lines[line_index], changed_references)
        GeneralUtilities.write_text_to_file(lock_file, "".join(lines))

    @staticmethod
    @GeneralUtilities.check_arguments
    def __parse_packages(lines: list[str]) -> list[dict]:
        """Returns the "[[package]]"-entries of the lines of a lock-file with their name, their version, the index of
        the line which contains the version, the information whether they have a source and the range of their
        lines (the end-index is exclusive)."""
        result: list[dict] = []
        current_package: dict = None
        for line_index, line in enumerate(lines):
            stripped_line = line.strip()
            if stripped_line.startswith("["):
                if current_package is not None:
                    current_package["end_line_index"] = line_index
                    result.append(current_package)
                    current_package = None
                if stripped_line == "[[package]]":
                    current_package = {"name": None, "version": None, "version_line_index": None, "has_source": False, "start_line_index": line_index}
                continue
            if current_package is None:
                continue
            match = re.match(r'^(name|version|source)\s*=\s*"([^"]*)"$', stripped_line)
            if match is not None:
                key = match.group(1)
                if key == "source":
                    current_package["has_source"] = True
                else:
                    current_package[key] = match.group(2)
                    if key == "version":
                        current_package["version_line_index"] = line_index
        if current_package is not None:
            current_package["end_line_index"] = len(lines)
            result.append(current_package)
        return result

    @staticmethod
    @GeneralUtilities.check_arguments
    def __replace_quoted_value(line: str, old_value: str, new_value: str) -> str:
        return line.replace(f'"{old_value}"', f'"{new_value}"', 1)

    @staticmethod
    @GeneralUtilities.check_arguments
    def __replace_dependency_reference(line: str, changed_references: dict[str, str]) -> str:
        match = re.match(r'^(\s*)"([^"]+)"(.*)$', line, re.DOTALL)
        if match is not None and match.group(2) in changed_references:
            return f'{match.group(1)}"{changed_references[match.group(2)]}"{match.group(3)}'
        return line
