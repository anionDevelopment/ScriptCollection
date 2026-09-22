import json
import os
import tempfile
import unittest
from ..ScriptCollection.GeneralUtilities import GeneralUtilities
from ..ScriptCollection.TFCPS.NpmDependencies import NpmDependencies
from ..ScriptCollection.TFCPS.PubDependencies import PubDependencies
from ..ScriptCollection.TFCPS.Flutter.TFCPS_CodeUnitSpecific_Flutter import TFCPS_CodeUnitSpecific_Flutter_Functions
from ..ScriptCollection.TFCPS.NodeJS.TFCPS_CodeUnitSpecific_NodeJS import TFCPS_CodeUnitSpecific_NodeJS_Functions


def create_codeunit_functions(codeunit_type: type, codeunit_folder: str):
    """Returns an instance of the given codeunit-type which knows nothing but the folder of its codeunit.

    The regular constructor of a codeunit-type requires a whole repository on disk (a git-repository, a
    codeunit-file and the environment-variables the product declares), while reading and writing the dependencies
    of a codeunit only requires its folder. The instance is therefore created without running the constructor, the
    same way the other testcases of this repository use a stand-in instead of a real codeunit."""
    result = codeunit_type.__new__(codeunit_type)
    # pylint:disable=protected-access
    result._TFCPS_CodeUnitSpecific_Base__codeunit_folder = codeunit_folder
    return result


def write_package(package_folder: str, filename: str, content: str) -> None:
    GeneralUtilities.ensure_directory_exists(package_folder)
    GeneralUtilities.write_text_to_file(os.path.join(package_folder, filename), content)


def get_pubspec_content(package_name: str, dependencies: dict) -> str:
    """Returns the content of a package-file which declares the given dependencies."""
    declarations = GeneralUtilities.empty_string.join(f"  {name}: ^{version}\n" for name, version in dependencies.items())
    return f"name: {package_name}\nversion: 1.0.0\n\ndependencies:\n{declarations}"


def get_pubspec_content_of_a_package_which_uses_every_kind_of_dependency() -> str:
    """Returns the content of a package-file which declares one dependency of every kind a pubspec.yaml can
    contain, so that a test can state which of them an update has to consider and which of them it must not."""
    return """name: demo
version: 1.2.0

environment:
  sdk: ^3.13.1

dependencies:
  flutter:
    sdk: flutter
  cupertino_icons: ^1.0.8   # a dependency with a comment
  exactly_pinned: 2.3.4
  ranged: ">=1.0.0 <2.0.0"
  vendored:
    path: ../other_package
  hosted_somewhere_else:
    hosted: https://example.org
    version: ^9.9.9

dev_dependencies:
  flutter_test:
    sdk: flutter
  flutter_lints: ^6.0.0

flutter:
  uses-material-design: true
"""


def get_package_json_content_which_uses_every_kind_of_dependency() -> dict:
    """Returns the content of a package-file which declares one dependency of every kind a package.json can
    contain, so that a test can state which of them an update has to consider and which of them it must not."""
    return {
        "name": "demo",
        "version": "1.2.0",
        "dependencies": {
            "@angular/core": "22.1.1",
            "rxjs": "^7.8.1",
            "vendored": "file:../other_package",
            "from_a_repository": "github:example/demo",
            "tagged": "latest",
        },
        "devDependencies": {
            "eslint": "~9.21.0",
        },
    }


class PubDependenciesTests(unittest.TestCase):

    def test_get_dependency_entries_returns_every_dependency_which_declares_a_plain_version(self) -> None:
        # arrange
        content = get_pubspec_content_of_a_package_which_uses_every_kind_of_dependency()

        # act
        actual_result = PubDependencies.get_dependency_entries(content)

        # assert
        self.assertEqual([("cupertino_icons", "1.0.8"), ("exactly_pinned", "2.3.4"), ("flutter_lints", "6.0.0")], actual_result)

    def test_get_dependency_entries_does_not_return_a_key_which_belongs_to_the_declaration_of_a_dependency(self) -> None:
        # The "version"-key of a dependency which is hosted somewhere else stands one level deeper than the
        # dependencies themselves. It states the version of that dependency and is not a dependency which is named
        # "version".
        # arrange
        content = get_pubspec_content_of_a_package_which_uses_every_kind_of_dependency()

        # act
        actual_result = PubDependencies.get_dependency_entries(content)

        # assert
        self.assertNotIn("version", [name for name, _ in actual_result])
        self.assertNotIn("sdk", [name for name, _ in actual_result])
        self.assertNotIn("path", [name for name, _ in actual_result])

    def test_get_dependency_entries_does_not_return_the_sdk_of_the_environment(self) -> None:
        # The environment-section declares which sdk the package needs. That is not a dependency which is resolved
        # from pub.dev, although it looks exactly like one.
        # arrange
        content = get_pubspec_content_of_a_package_which_uses_every_kind_of_dependency()

        # act
        actual_result = PubDependencies.get_dependency_entries(content)

        # assert
        self.assertEqual([], [name for name, _ in actual_result if name == "sdk"])

    def test_set_dependency_version_in_lines_keeps_the_constraint_prefix_and_the_comment_of_the_line(self) -> None:
        # arrange
        lines = GeneralUtilities.string_to_lines(get_pubspec_content_of_a_package_which_uses_every_kind_of_dependency(), True, False)

        # act
        actual_result = PubDependencies.set_dependency_version_in_lines(lines, "cupertino_icons", "1.0.9")

        # assert
        self.assertIn("  cupertino_icons: ^1.0.9   # a dependency with a comment", actual_result)

    def test_set_dependency_version_in_lines_does_not_add_a_constraint_prefix_to_an_exactly_pinned_dependency(self) -> None:
        # arrange
        lines = GeneralUtilities.string_to_lines(get_pubspec_content_of_a_package_which_uses_every_kind_of_dependency(), True, False)

        # act
        actual_result = PubDependencies.set_dependency_version_in_lines(lines, "exactly_pinned", "2.4.0")

        # assert
        self.assertIn("  exactly_pinned: 2.4.0", actual_result)

    def test_set_dependency_version_in_lines_changes_nothing_but_the_line_of_the_dependency(self) -> None:
        # arrange
        lines = GeneralUtilities.string_to_lines(get_pubspec_content_of_a_package_which_uses_every_kind_of_dependency(), True, False)

        # act
        actual_result = PubDependencies.set_dependency_version_in_lines(lines, "flutter_lints", "6.1.0")

        # assert
        changed_lines = [(former_line, new_line) for former_line, new_line in zip(lines, actual_result) if former_line != new_line]
        self.assertEqual([("  flutter_lints: ^6.0.0", "  flutter_lints: ^6.1.0")], changed_lines)

    def test_set_dependency_version_in_lines_does_not_touch_a_dependency_which_declares_a_range(self) -> None:
        # A range states which versions the package accepts and not which version it uses, so there is no single
        # version in it which could be raised.
        # arrange
        lines = GeneralUtilities.string_to_lines(get_pubspec_content_of_a_package_which_uses_every_kind_of_dependency(), True, False)

        # act
        actual_result = PubDependencies.set_dependency_version_in_lines(lines, "ranged", "1.5.0")

        # assert
        self.assertEqual(lines, actual_result)

    def test_declares_dependency_states_whether_the_package_file_declares_the_dependency(self) -> None:
        # arrange
        lines = GeneralUtilities.string_to_lines(get_pubspec_content_of_a_package_which_uses_every_kind_of_dependency(), True, False)

        # act & assert
        self.assertTrue(PubDependencies.declares_dependency(lines, "cupertino_icons"))
        self.assertTrue(PubDependencies.declares_dependency(lines, "flutter_lints"))
        self.assertFalse(PubDependencies.declares_dependency(lines, "a_package_which_is_not_used"))

    def test_set_dependency_version_writes_the_new_version_into_the_package_file(self) -> None:
        # arrange
        with tempfile.TemporaryDirectory(dir=GeneralUtilities.get_temp_folder()) as folder:
            pubspec_file = os.path.join(folder, "pubspec.yaml")
            GeneralUtilities.write_text_to_file(pubspec_file, get_pubspec_content_of_a_package_which_uses_every_kind_of_dependency())

            # act
            actual_result = PubDependencies.set_dependency_version(pubspec_file, "cupertino_icons", "1.0.9")

            # assert
            self.assertTrue(actual_result)
            self.assertEqual([("cupertino_icons", "1.0.9"), ("exactly_pinned", "2.3.4"), ("flutter_lints", "6.0.0")], PubDependencies.get_dependency_entries(GeneralUtilities.read_text_from_file(pubspec_file)))

    def test_set_dependency_version_leaves_a_package_file_which_does_not_declare_the_dependency_untouched(self) -> None:
        # A codeunit can consist of several packages, and a dependency which is updated is usually not declared by
        # every one of them.
        # arrange
        with tempfile.TemporaryDirectory(dir=GeneralUtilities.get_temp_folder()) as folder:
            pubspec_file = os.path.join(folder, "pubspec.yaml")
            former_content = get_pubspec_content_of_a_package_which_uses_every_kind_of_dependency()
            GeneralUtilities.write_text_to_file(pubspec_file, former_content)

            # act
            actual_result = PubDependencies.set_dependency_version(pubspec_file, "a_package_which_is_not_used", "1.0.0")

            # assert
            self.assertFalse(actual_result)
            self.assertEqual(former_content, GeneralUtilities.read_text_from_file(pubspec_file))

    def test_get_dependencies_returns_the_dependencies_of_the_package_file(self) -> None:
        # arrange
        with tempfile.TemporaryDirectory(dir=GeneralUtilities.get_temp_folder()) as folder:
            pubspec_file = os.path.join(folder, "pubspec.yaml")
            GeneralUtilities.write_text_to_file(pubspec_file, get_pubspec_content_of_a_package_which_uses_every_kind_of_dependency())

            # act
            actual_result = PubDependencies.get_dependencies(pubspec_file)

            # assert
            self.assertEqual([("cupertino_icons", "1.0.8"), ("exactly_pinned", "2.3.4"), ("flutter_lints", "6.0.0")], [(dependency.dependencyname, dependency.current_version) for dependency in actual_result])


class NpmDependenciesTests(unittest.TestCase):

    def test_get_dependency_entries_returns_every_dependency_which_declares_a_plain_version(self) -> None:
        # arrange
        content = get_package_json_content_which_uses_every_kind_of_dependency()

        # act
        actual_result = NpmDependencies.get_dependency_entries(content)

        # assert
        self.assertEqual([("@angular/core", "22.1.1"), ("rxjs", "7.8.1"), ("eslint", "9.21.0")], actual_result)

    def test_set_dependency_version_in_content_keeps_the_range_prefix_of_the_former_declaration(self) -> None:
        # The prefix states how the project wants to accept updates, which is not a decision of the update itself.
        # arrange
        content = get_package_json_content_which_uses_every_kind_of_dependency()

        # act
        actual_result = NpmDependencies.set_dependency_version_in_content(content, "rxjs", "7.9.0")

        # assert
        self.assertEqual("^7.9.0", actual_result["dependencies"]["rxjs"])

    def test_set_dependency_version_in_content_does_not_add_a_range_prefix_to_an_exactly_pinned_dependency(self) -> None:
        # arrange
        content = get_package_json_content_which_uses_every_kind_of_dependency()

        # act
        actual_result = NpmDependencies.set_dependency_version_in_content(content, "@angular/core", "22.1.7")

        # assert
        self.assertEqual("22.1.7", actual_result["dependencies"]["@angular/core"])

    def test_set_dependency_version_in_content_also_updates_a_development_dependency(self) -> None:
        # arrange
        content = get_package_json_content_which_uses_every_kind_of_dependency()

        # act
        actual_result = NpmDependencies.set_dependency_version_in_content(content, "eslint", "9.22.0")

        # assert
        self.assertEqual("~9.22.0", actual_result["devDependencies"]["eslint"])

    def test_declares_dependency_states_whether_the_package_file_declares_the_dependency(self) -> None:
        # arrange
        content = get_package_json_content_which_uses_every_kind_of_dependency()

        # act & assert
        self.assertTrue(NpmDependencies.declares_dependency(content, "rxjs"))
        self.assertTrue(NpmDependencies.declares_dependency(content, "eslint"))
        self.assertFalse(NpmDependencies.declares_dependency(content, "a_package_which_is_not_used"))

    def test_set_dependency_version_writes_the_new_version_into_the_package_file(self) -> None:
        # arrange
        with tempfile.TemporaryDirectory(dir=GeneralUtilities.get_temp_folder()) as folder:
            package_json_file = os.path.join(folder, "package.json")
            GeneralUtilities.write_text_to_file(package_json_file, json.dumps(get_package_json_content_which_uses_every_kind_of_dependency(), indent=2))

            # act
            actual_result = NpmDependencies.set_dependency_version(package_json_file, "rxjs", "7.9.0")

            # assert
            self.assertTrue(actual_result)
            self.assertEqual("^7.9.0", json.loads(GeneralUtilities.read_text_from_file(package_json_file))["dependencies"]["rxjs"])

    def test_set_dependency_version_leaves_a_package_file_which_does_not_declare_the_dependency_untouched(self) -> None:
        # arrange
        with tempfile.TemporaryDirectory(dir=GeneralUtilities.get_temp_folder()) as folder:
            package_json_file = os.path.join(folder, "package.json")
            former_content = json.dumps(get_package_json_content_which_uses_every_kind_of_dependency(), indent=2)
            GeneralUtilities.write_text_to_file(package_json_file, former_content)

            # act
            actual_result = NpmDependencies.set_dependency_version(package_json_file, "a_package_which_is_not_used", "1.0.0")

            # assert
            self.assertFalse(actual_result)
            self.assertEqual(former_content, GeneralUtilities.read_text_from_file(package_json_file))

    def test_get_dependencies_returns_the_dependencies_of_the_package_file(self) -> None:
        # arrange
        with tempfile.TemporaryDirectory(dir=GeneralUtilities.get_temp_folder()) as folder:
            package_json_file = os.path.join(folder, "package.json")
            GeneralUtilities.write_text_to_file(package_json_file, json.dumps(get_package_json_content_which_uses_every_kind_of_dependency(), indent=2))

            # act
            actual_result = NpmDependencies.get_dependencies(package_json_file)

            # assert
            self.assertEqual([("@angular/core", "22.1.1"), ("rxjs", "7.8.1"), ("eslint", "9.21.0")], [(dependency.dependencyname, dependency.current_version) for dependency in actual_result])


class FlutterCodeUnitDependenciesTests(unittest.TestCase):

    def test_get_dependencies_returns_the_dependencies_of_every_package_of_the_codeunit(self) -> None:
        # A flutter-codeunit can consist of several packages, and the dependencies of all of them together are the
        # dependencies of the codeunit.
        # arrange
        with tempfile.TemporaryDirectory(dir=GeneralUtilities.get_temp_folder()) as repository_folder:
            codeunit_folder = os.path.join(repository_folder, "DemoCodeUnit")
            write_package(os.path.join(codeunit_folder, "demo_app"), "pubspec.yaml", get_pubspec_content("demo_app", {"cupertino_icons": "1.0.8", "shared": "3.0.0"}))
            write_package(os.path.join(codeunit_folder, "demo_library"), "pubspec.yaml", get_pubspec_content("demo_library", {"shared": "3.0.0"}))
            codeunit_functions = create_codeunit_functions(TFCPS_CodeUnitSpecific_Flutter_Functions, codeunit_folder)

            # act
            actual_result = codeunit_functions.get_dependencies()

            # assert
            self.assertEqual({"cupertino_icons": {"1.0.8"}, "shared": {"3.0.0"}}, actual_result)

    def test_set_dependency_version_sets_the_version_in_every_package_which_declares_the_dependency(self) -> None:
        # arrange
        with tempfile.TemporaryDirectory(dir=GeneralUtilities.get_temp_folder()) as repository_folder:
            codeunit_folder = os.path.join(repository_folder, "DemoCodeUnit")
            write_package(os.path.join(codeunit_folder, "demo_app"), "pubspec.yaml", get_pubspec_content("demo_app", {"cupertino_icons": "1.0.8", "shared": "3.0.0"}))
            write_package(os.path.join(codeunit_folder, "demo_library"), "pubspec.yaml", get_pubspec_content("demo_library", {"shared": "3.0.0"}))
            codeunit_functions = create_codeunit_functions(TFCPS_CodeUnitSpecific_Flutter_Functions, codeunit_folder)

            # act
            codeunit_functions.set_dependency_version("shared", "3.1.0")

            # assert
            self.assertEqual({"cupertino_icons": {"1.0.8"}, "shared": {"3.1.0"}}, codeunit_functions.get_dependencies())

    def test_set_dependency_version_throws_exception_when_no_package_of_the_codeunit_declares_the_dependency(self) -> None:
        # arrange
        with tempfile.TemporaryDirectory(dir=GeneralUtilities.get_temp_folder()) as repository_folder:
            codeunit_folder = os.path.join(repository_folder, "DemoCodeUnit")
            write_package(os.path.join(codeunit_folder, "demo_app"), "pubspec.yaml", get_pubspec_content("demo_app", {"cupertino_icons": "1.0.8"}))
            codeunit_functions = create_codeunit_functions(TFCPS_CodeUnitSpecific_Flutter_Functions, codeunit_folder)

            # act & assert
            with self.assertRaises(ValueError):
                codeunit_functions.set_dependency_version("a_package_which_is_not_used", "1.0.0")


class NodeJSCodeUnitDependenciesTests(unittest.TestCase):

    def test_get_dependencies_returns_the_dependencies_of_the_package_file_of_the_codeunit(self) -> None:
        # arrange
        with tempfile.TemporaryDirectory(dir=GeneralUtilities.get_temp_folder()) as repository_folder:
            codeunit_folder = os.path.join(repository_folder, "DemoCodeUnit")
            write_package(codeunit_folder, "package.json", json.dumps(get_package_json_content_which_uses_every_kind_of_dependency(), indent=2))
            codeunit_functions = create_codeunit_functions(TFCPS_CodeUnitSpecific_NodeJS_Functions, codeunit_folder)

            # act
            actual_result = codeunit_functions.get_dependencies()

            # assert
            self.assertEqual({"@angular/core": {"22.1.1"}, "rxjs": {"7.8.1"}, "eslint": {"9.21.0"}}, actual_result)
