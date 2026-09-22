import json
import re
import requests
from ..GeneralUtilities import GeneralUtilities, Dependency


class NpmDependencies:
    """Reads and writes the dependencies which a npm-package-file ("package.json") declares and asks the
    npm-registry which versions of such a dependency exist.

    This is implemented here and not inside one of the codeunit-type-specific classes because a nodejs-codeunit and
    a typescript-codeunit declare their dependencies in exactly the same file-format and resolve them from exactly
    the same registry. Only the location of the package-file differs between them, which is why every operation
    takes that file as its argument."""

    __dependency_sections: tuple = ("dependencies", "devDependencies")
    __version_regex: str = r"^\d+\.\d+\.\d+$"
    __range_prefixes: tuple = ("^", "~")

    @staticmethod
    @GeneralUtilities.check_arguments
    def get_dependencies(package_json_file: str) -> list[Dependency]:
        """Returns the updatable dependencies which the given package-file declares."""
        content: dict = NpmDependencies.__read_package_file(package_json_file)
        return [Dependency(name, version) for name, version in NpmDependencies.get_dependency_entries(content)]

    @staticmethod
    @GeneralUtilities.check_arguments
    def get_dependency_entries(package_json_content: dict) -> list[tuple[str, str]]:
        """Returns the updatable dependencies of the given package-file-content as tuples of their name and their
        version.

        Only a dependency whose version is a plain version-number is returned, because a dependency which points to
        a file, a repository or a tag has no version on the registry which could be updated, and a dependency which
        declares a version-range has no single version which an update could raise."""
        result: list[tuple[str, str]] = []
        for section in NpmDependencies.__dependency_sections:
            for name, declared_version in package_json_content.get(section, {}).items():
                # A declared version usually carries a range-prefix ("^1.2.3" or "~1.2.3"), which is not part of
                # the version itself.
                version_without_prefix: str = NpmDependencies.__remove_range_prefix(declared_version)
                if re.match(NpmDependencies.__version_regex, version_without_prefix) is not None:
                    result.append((name, version_without_prefix))
        return result

    @staticmethod
    @GeneralUtilities.check_arguments
    def get_available_versions(dependencyname: str) -> list[str]:
        """Returns every published version of the given package which is a plain version-number.

        A pre-release carries a suffix ("1.2.3-beta.1") and is deliberately not returned: an update which runs
        unattended must not move a codeunit onto a version which its publisher did not release as a regular one."""
        # The registry of npm answers with all published versions of a package. The abbreviated metadata-format is
        # requested because the full document additionally contains the readme of every single version, which is a
        # multiple of the amount of data which is needed here.
        response = requests.get(f"https://registry.npmjs.org/{dependencyname}", headers={"Accept": "application/vnd.npm.install-v1+json"}, timeout=60)
        response.raise_for_status()
        result: list[str] = []
        for version_string in response.json().get("versions", {}).keys():
            if re.match(NpmDependencies.__version_regex, version_string) is not None:
                result.append(version_string)
        return result

    @staticmethod
    @GeneralUtilities.check_arguments
    def set_dependency_version(package_json_file: str, name: str, new_version: str) -> bool:
        """Sets the version of the dependency [name] in the given package-file and returns whether that package-file
        declares a dependency with that name at all."""
        content: dict = NpmDependencies.__read_package_file(package_json_file)
        if not NpmDependencies.declares_dependency(content, name):
            return False
        new_content: dict = NpmDependencies.set_dependency_version_in_content(content, name, new_version)
        GeneralUtilities.write_text_to_file(package_json_file, json.dumps(new_content, indent=2, ensure_ascii=False)+"\n")
        return True

    @staticmethod
    @GeneralUtilities.check_arguments
    def declares_dependency(package_json_content: dict, name: str) -> bool:
        """Returns whether the given package-file-content declares a dependency which is named [name]."""
        for section in NpmDependencies.__dependency_sections:
            if name in package_json_content.get(section, {}):
                return True
        return False

    @staticmethod
    @GeneralUtilities.check_arguments
    def set_dependency_version_in_content(package_json_content: dict, name: str, new_version: str) -> dict:
        """Returns the given package-file-content with the version of the dependency [name] set to [new_version].
        The content is returned unchanged when it does not declare a dependency with that name."""
        for section in NpmDependencies.__dependency_sections:
            if name in package_json_content.get(section, {}):
                # The range-prefix of the former declaration is kept, because it states how the project wants to
                # accept updates and that is not a decision of this function.
                former_declaration: str = package_json_content[section][name]
                prefix: str = former_declaration[0] if former_declaration[0] in NpmDependencies.__range_prefixes else GeneralUtilities.empty_string
                package_json_content[section][name] = f"{prefix}{new_version}"
        return package_json_content

    @staticmethod
    @GeneralUtilities.check_arguments
    def __remove_range_prefix(declared_version: str) -> str:
        if declared_version.startswith(NpmDependencies.__range_prefixes):
            return declared_version[1:]
        return declared_version

    @staticmethod
    @GeneralUtilities.check_arguments
    def __read_package_file(package_json_file: str) -> dict:
        return json.loads(GeneralUtilities.read_text_from_file(package_json_file))
