import re
import requests
from ..GeneralUtilities import GeneralUtilities, Dependency


class PubDependencies:
    """Reads and writes the dependencies which a pub-package-file ("pubspec.yaml") declares and asks pub.dev which
    versions of such a dependency exist.

    This is implemented here and not inside one of the codeunit-type-specific classes because a flutter-codeunit and
    a dart-codeunit declare their dependencies in exactly the same file-format and resolve them from exactly the
    same package-source. Only the location of the package-file differs between them, which is why every operation
    takes that file as its argument.

    The package-file is processed line by line and not by loading and dumping it as yaml: writing it back as yaml
    would drop its comments and normalize its whole formatting, while a pubspec.yaml is a file which is maintained
    by hand and in which an update of one version must not rewrite anything else."""

    __dependency_sections: tuple = ("dependencies", "dev_dependencies", "dependency_overrides")
    __version_regex: str = r"^\d+\.\d+\.\d+$"
    __version_constraint_regex: str = r"^(\^?)(\d+\.\d+\.\d+)$"

    @staticmethod
    @GeneralUtilities.check_arguments
    def get_dependencies(pubspec_file: str) -> list[Dependency]:
        """Returns the updatable dependencies which the given package-file declares."""
        content: str = GeneralUtilities.read_text_from_file(pubspec_file)
        return [Dependency(name, version) for name, version in PubDependencies.get_dependency_entries(content)]

    @staticmethod
    @GeneralUtilities.check_arguments
    def get_dependency_entries(pubspec_content: str) -> list[tuple[str, str]]:
        """Returns the updatable dependencies of the given package-file-content as tuples of their name and their
        version.

        Only a dependency which declares a plain version-constraint is returned: a dependency which is declared as a
        block (a sdk-, a path- or a git-dependency, for example) is not resolved from pub.dev at all, and a
        dependency which declares a version-range has no single version which an update could raise."""
        result: list[tuple[str, str]] = []
        for _, _, name, version_constraint in PubDependencies.__enumerate_entries(PubDependencies.__content_to_lines(pubspec_content)):
            constraint_match = re.match(PubDependencies.__version_constraint_regex, version_constraint)
            if constraint_match is not None:
                # A declared constraint usually carries the caret-prefix ("^1.2.3"), which is not part of the
                # version itself.
                result.append((name, constraint_match.group(2)))
        return result

    @staticmethod
    @GeneralUtilities.check_arguments
    def get_available_versions(dependencyname: str) -> list[str]:
        """Returns every published version of the given package which is a plain version-number.

        A retracted version is skipped, because its publisher declared it as a version which must not be used
        anymore. A pre-release carries a suffix ("1.2.3-beta.1") and is deliberately not returned either: an update
        which runs unattended must not move a codeunit onto a version which its publisher did not release as a
        regular one."""
        # The api of pub.dev answers with all published versions of a package.
        response = requests.get(f"https://pub.dev/api/packages/{dependencyname}", headers={"Accept": "application/vnd.pub.v2+json"}, timeout=60)
        response.raise_for_status()
        result: list[str] = []
        for published_version in response.json()["versions"]:
            if published_version.get("retracted", False):
                continue
            version_string: str = str(published_version["version"])
            if re.match(PubDependencies.__version_regex, version_string) is not None:
                result.append(version_string)
        return result

    @staticmethod
    @GeneralUtilities.check_arguments
    def set_dependency_version(pubspec_file: str, name: str, new_version: str) -> bool:
        """Sets the version of the dependency [name] in the given package-file and returns whether that package-file
        declares a dependency with that name at all."""
        lines: list[str] = GeneralUtilities.read_lines_from_file(pubspec_file)
        if not PubDependencies.declares_dependency(lines, name):
            return False
        GeneralUtilities.write_lines_to_file(pubspec_file, PubDependencies.set_dependency_version_in_lines(lines, name, new_version))
        return True

    @staticmethod
    @GeneralUtilities.check_arguments
    def declares_dependency(pubspec_lines: list[str], name: str) -> bool:
        """Returns whether the given lines of a package-file declare a dependency which is named [name]."""
        for _, _, entry_name, _ in PubDependencies.__enumerate_entries(pubspec_lines):
            if entry_name == name:
                return True
        return False

    @staticmethod
    @GeneralUtilities.check_arguments
    def set_dependency_version_in_lines(pubspec_lines: list[str], name: str, new_version: str) -> list[str]:
        """Returns the given lines of a package-file with the version of the dependency [name] set to [new_version].

        Only the version itself is replaced, so the indentation, the constraint-prefix and a comment of the line
        stay as they are. A dependency which does not declare a plain version-constraint is not touched, for the
        same reason for which get_dependency_entries does not return it."""
        result: list[str] = list(pubspec_lines)
        for index, _, entry_name, version_constraint in PubDependencies.__enumerate_entries(pubspec_lines):
            if entry_name != name:
                continue
            constraint_match = re.match(PubDependencies.__version_constraint_regex, version_constraint)
            if constraint_match is None:
                continue
            former_constraint: str = constraint_match.group(0)
            new_constraint: str = f"{constraint_match.group(1)}{new_version}"
            # The line is split into what stands in front of the constraint, the constraint itself and what stands
            # behind it (a comment), so that only the constraint is exchanged and the rest of the line is kept.
            line_match = re.match(r"^(\s*"+re.escape(entry_name)+r":\s*)"+re.escape(former_constraint)+r"(.*)$", result[index])
            GeneralUtilities.assert_condition(line_match is not None, f"The line \"{result[index]}\" does not declare the dependency \"{entry_name}\" in the way it was read from it.")
            result[index] = f"{line_match.group(1)}{new_constraint}{line_match.group(2)}"
        return result

    @staticmethod
    @GeneralUtilities.check_arguments
    def __enumerate_entries(pubspec_lines: list[str]) -> list[tuple[int, str, str, str]]:
        """Returns every dependency which the given lines of a package-file declare, as tuples of the index of the
        line which declares it, the section it is declared in, its name and the value it is declared with."""
        current_section: str = None
        entry_indentation: int = None
        result: list[tuple[int, str, str, str]] = []
        for index, line in enumerate(pubspec_lines):
            line_without_comment: str = PubDependencies.__remove_comment(line)
            if not GeneralUtilities.string_has_content(line_without_comment):
                continue
            if not line_without_comment.startswith(" "):
                # A line without indentation declares a new top-level key, so the section which was processed until
                # here has ended. Only a key without a value of its own opens a section which can contain
                # dependencies.
                section_match = re.match(r"^([A-Za-z0-9_]+):$", line_without_comment)
                current_section = section_match.group(1) if section_match is not None else None
                entry_indentation = None
                continue
            if current_section not in PubDependencies.__dependency_sections:
                continue
            indentation: int = len(line_without_comment)-len(line_without_comment.lstrip(" "))
            if entry_indentation is None:
                # The first indented line of a section states on which indentation the dependencies of that section
                # are declared. Everything which is indented deeper belongs to the declaration of one of them (the
                # "sdk"-key of a sdk-dependency or the "version"-key of a hosted dependency, for example) and is not
                # a dependency of its own.
                entry_indentation = indentation
            if indentation != entry_indentation:
                continue
            entry_match = re.match(r"^\s+([A-Za-z0-9_]+):\s*(\S.*)$", line_without_comment)
            if entry_match is not None:
                result.append((index, current_section, entry_match.group(1), entry_match.group(2)))
        return result

    @staticmethod
    @GeneralUtilities.check_arguments
    def __remove_comment(line: str) -> str:
        """Returns the given line without its comment and without its trailing whitespace. In yaml a "#" starts a
        comment when it stands at the beginning of a line or when a whitespace stands in front of it."""
        comment_match = re.search(r"(^|\s)#", line)
        if comment_match is None:
            return line.rstrip()
        return line[:comment_match.start()].rstrip()

    @staticmethod
    @GeneralUtilities.check_arguments
    def __content_to_lines(pubspec_content: str) -> list[str]:
        # The lines are taken as they are, because the indentation of a line is what states whether it declares a
        # dependency or a detail of one.
        return GeneralUtilities.string_to_lines(pubspec_content, True, False)
