import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock
from ..ScriptCollection.GeneralUtilities import GeneralUtilities, VersionEcholon
from ..ScriptCollection.SCLog import LogLevel
from ..ScriptCollection.TFCPS.TFCPS_Tools_General import TFCPS_Tools_General
from ..ScriptCollection.TFCPS.TFCPS_CodeUnitSpecific_Base import TFCPS_CodeUnitSpecific_Base
from ..ScriptCollection.TFCPS.NpmDependencies import NpmDependencies
from ..ScriptCollection.TFCPS.PubDependencies import PubDependencies
from ..ScriptCollection.TFCPS.Flutter.TFCPS_CodeUnitSpecific_Flutter import TFCPS_CodeUnitSpecific_Flutter_Functions
from ..ScriptCollection.TFCPS.NodeJS.TFCPS_CodeUnitSpecific_NodeJS import TFCPS_CodeUnitSpecific_NodeJS_Functions
from ..ScriptCollection.TFCPS.DotNet.TFCPS_CodeUnitSpecific_DotNet import TFCPS_CodeUnitSpecific_DotNet_Functions
from ..ScriptCollection.TFCPS.Docker.TFCPS_CodeUnitSpecific_Docker import TFCPS_CodeUnitSpecific_Docker_Functions


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


def get_csproj_content_which_uses_several_kinds_of_package_reference() -> str:
    """Returns the content of a .csproj-file which declares its dependencies the way a real .NET-codeunit does:
    an unbracketed version and a version which is pinned exactly with brackets, so that a test can state how each of
    them has to be updated."""
    return """<Project Sdk="Microsoft.NET.Sdk">

  <PropertyGroup>
    <TargetFramework>net10.0</TargetFramework>
  </PropertyGroup>

  <ItemGroup>
    <PackageReference Include="DNTCaptcha.Core" Version="5.3.2" />
    <PackageReference Include="CommandLineParser" Version="[2.9.1]" />
  </ItemGroup>

</Project>
"""


class DotNetCodeUnitSetDependencyVersionTests(unittest.TestCase):

    def test_set_dependency_version_updates_an_unbracketed_version_without_adding_brackets(self) -> None:
        # arrange
        content = get_csproj_content_which_uses_several_kinds_of_package_reference()

        # act
        actual_result = TFCPS_CodeUnitSpecific_DotNet_Functions.set_dependency_version_in_csproj_content(content, "DNTCaptcha.Core", "5.3.4")

        # assert
        self.assertIn('<PackageReference Include="DNTCaptcha.Core" Version="5.3.4" />', actual_result)

    def test_set_dependency_version_keeps_the_brackets_of_an_exactly_pinned_dependency(self) -> None:
        # A version which is pinned exactly with brackets stays an exact pin after the update, so the brackets have to
        # be preserved.
        # arrange
        content = get_csproj_content_which_uses_several_kinds_of_package_reference()

        # act
        actual_result = TFCPS_CodeUnitSpecific_DotNet_Functions.set_dependency_version_in_csproj_content(content, "CommandLineParser", "2.9.2")

        # assert
        self.assertIn('<PackageReference Include="CommandLineParser" Version="[2.9.2]" />', actual_result)

    def test_set_dependency_version_changes_nothing_but_the_declaration_of_the_updated_dependency(self) -> None:
        # arrange
        content = get_csproj_content_which_uses_several_kinds_of_package_reference()

        # act
        actual_result = TFCPS_CodeUnitSpecific_DotNet_Functions.set_dependency_version_in_csproj_content(content, "DNTCaptcha.Core", "5.3.4")

        # assert
        changed_lines = [(former_line, new_line) for former_line, new_line in zip(content.splitlines(), actual_result.splitlines()) if former_line != new_line]
        self.assertEqual([('    <PackageReference Include="DNTCaptcha.Core" Version="5.3.2" />', '    <PackageReference Include="DNTCaptcha.Core" Version="5.3.4" />')], changed_lines)

    def test_set_dependency_version_leaves_the_content_unchanged_when_the_dependency_is_not_declared(self) -> None:
        # arrange
        content = get_csproj_content_which_uses_several_kinds_of_package_reference()

        # act
        actual_result = TFCPS_CodeUnitSpecific_DotNet_Functions.set_dependency_version_in_csproj_content(content, "A.Package.Which.Is.Not.Used", "1.0.0")

        # assert
        self.assertEqual(content, actual_result)

    def test_set_dependency_version_writes_the_new_version_into_the_project_file(self) -> None:
        # arrange
        with tempfile.TemporaryDirectory(dir=GeneralUtilities.get_temp_folder()) as folder:
            csproj_file = os.path.join(folder, "Demo.csproj")
            GeneralUtilities.write_text_to_file(csproj_file, get_csproj_content_which_uses_several_kinds_of_package_reference())
            codeunit_functions = TFCPS_CodeUnitSpecific_DotNet_Functions.__new__(TFCPS_CodeUnitSpecific_DotNet_Functions)
            codeunit_functions.csproj_file = csproj_file

            # act
            codeunit_functions.set_dependency_version("DNTCaptcha.Core", "5.3.4")

            # assert
            self.assertIn('<PackageReference Include="DNTCaptcha.Core" Version="5.3.4" />', GeneralUtilities.read_text_from_file(csproj_file))


class DotNetCodeUnitSynchronizeVersionsTests(unittest.TestCase):

    def test_synchronize_pins_a_shared_dependency_in_the_test_project_to_the_library_version_and_keeps_its_brackets(self) -> None:
        # The library-project uses NSwag.AspNetCore in version 14.7.1 and the test-project still pins it exactly to the
        # older 14.6.3. A shared dependency has to be pinned to the same version in both, because NuGet rejects a restore
        # in which the test-project pins it lower than the library-project requires (error NU1605).
        # arrange
        with tempfile.TemporaryDirectory(dir=GeneralUtilities.get_temp_folder()) as repository_folder:
            codeunit_folder = os.path.join(repository_folder, "Demo")
            main_csproj = os.path.join(codeunit_folder, "Demo", "Demo.csproj")
            test_csproj = os.path.join(codeunit_folder, "DemoTests", "DemoTests.csproj")
            GeneralUtilities.ensure_directory_exists(os.path.dirname(main_csproj))
            GeneralUtilities.ensure_directory_exists(os.path.dirname(test_csproj))
            GeneralUtilities.write_text_to_file(main_csproj, '<Project Sdk="Microsoft.NET.Sdk">\n  <ItemGroup>\n    <PackageReference Include="NSwag.AspNetCore" Version="14.7.1" />\n  </ItemGroup>\n</Project>\n')
            GeneralUtilities.write_text_to_file(test_csproj, '<Project Sdk="Microsoft.NET.Sdk">\n  <ItemGroup>\n    <PackageReference Include="NSwag.AspNetCore" Version="[14.6.3]" />\n    <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.11.1" />\n  </ItemGroup>\n</Project>\n')
            codeunit_functions = create_codeunit_functions(TFCPS_CodeUnitSpecific_DotNet_Functions, codeunit_folder)
            codeunit_functions.csproj_file = main_csproj

            # act
            codeunit_functions.synchronize_dependency_versions_across_project_files()

            # assert
            test_content = GeneralUtilities.read_text_from_file(test_csproj)
            self.assertIn('<PackageReference Include="NSwag.AspNetCore" Version="[14.7.1]" />', test_content)
            # a package which only the test-project uses stays untouched, because the library-project does not declare it.
            self.assertIn('<PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.11.1" />', test_content)

    def test_get_csproj_files_of_codeunit_returns_the_source_projects_and_excludes_build_output_and_the_other_folder(self) -> None:
        # arrange
        with tempfile.TemporaryDirectory(dir=GeneralUtilities.get_temp_folder()) as repository_folder:
            codeunit_folder = os.path.join(repository_folder, "Demo")
            main_csproj = os.path.join(codeunit_folder, "Demo", "Demo.csproj")
            test_csproj = os.path.join(codeunit_folder, "DemoTests", "DemoTests.csproj")
            build_output_csproj = os.path.join(codeunit_folder, "Demo", "obj", "Demo.csproj")
            artifact_csproj = os.path.join(codeunit_folder, "Other", "Artifacts", "Copy.csproj")
            for csproj_file in [main_csproj, test_csproj, build_output_csproj, artifact_csproj]:
                GeneralUtilities.ensure_directory_exists(os.path.dirname(csproj_file))
                GeneralUtilities.write_text_to_file(csproj_file, "<Project />")
            codeunit_functions = create_codeunit_functions(TFCPS_CodeUnitSpecific_DotNet_Functions, codeunit_folder)

            # act
            actual_result = codeunit_functions.get_csproj_files_of_codeunit()

            # assert
            self.assertEqual(sorted([main_csproj, test_csproj]), sorted(actual_result))


class DotNetCodeUnitAvailableVersionsTests(unittest.TestCase):

    def test_select_updatable_versions_keeps_only_three_part_versions_sorted_from_latest_to_oldest(self) -> None:
        # NuGet lists the versions of a package in exactly this shape: besides the plain three-part-versions it also
        # contains four-part-versions and pre-release-versions. The four-part- and pre-release-versions must be dropped,
        # because the rest of the update-logic only handles three-part-versions.
        # arrange
        nuget_versions = ["2.7.0", "2.8.0-preview4", "2.8.0", "1.8.0.7", "2.9.1-preview1", "2.9.1", "2.9.2-ci-210"]

        # act
        actual_result = TFCPS_CodeUnitSpecific_DotNet_Functions.select_updatable_versions_from_nuget_versions(nuget_versions)

        # assert
        self.assertEqual(["2.9.1", "2.8.0", "2.7.0"], actual_result)

    def test_select_updatable_versions_does_not_discard_the_whole_list_because_of_an_unparseable_version(self) -> None:
        # The version-string "2.9.2-ci-210" (which the CommandLineParser-package really publishes) passes a loose
        # three-part-prefix-check but can not be parsed by packaging.version.Version. Sorting the list with that version
        # as a key would raise and - because the caller catches every exception - discard every version, which made the
        # update fail with "Version-list can not be empty" although usable versions existed.
        # arrange
        nuget_versions = ["2.9.1", "2.9.2-ci-210"]

        # act
        actual_result = TFCPS_CodeUnitSpecific_DotNet_Functions.select_updatable_versions_from_nuget_versions(nuget_versions)

        # assert
        self.assertEqual(["2.9.1"], actual_result)


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


class LogNewerMajorVersionsOfDependencyTests(unittest.TestCase):

    def __log_newer_major_versions(self, available_versions: list[str], used_version: str) -> MagicMock:
        """Runs the function under test with a stand-in for the ScriptCollectionCore and returns the stand-in of its log."""
        sc = MagicMock()
        tools = TFCPS_Tools_General(sc)
        tools.log_newer_major_versions_of_dependency("OpenSpec", available_versions, used_version)
        return sc.log

    def test_nothing_is_logged_if_the_latest_major_version_is_used(self) -> None:
        # arrange
        available_versions = ["1.16.0", "1.17.0"]

        # act
        log = self.__log_newer_major_versions(available_versions, "1.17.0")

        # assert
        log.log.assert_not_called()

    def test_an_information_is_logged_if_one_newer_major_version_exists(self) -> None:
        # arrange
        available_versions = ["1.16.0", "1.17.0", "2.0.0"]

        # act
        log = self.__log_newer_major_versions(available_versions, "1.17.0")

        # assert
        log.log.assert_called_once()
        self.assertEqual(LogLevel.Information, log.log.call_args[0][1])
        self.assertIn("2.0.0", log.log.call_args[0][0])

    def test_a_warning_is_logged_if_two_newer_major_versions_exist(self) -> None:
        # arrange
        available_versions = ["1.17.0", "1.18.0", "2.0.0", "3.0.0"]

        # act
        log = self.__log_newer_major_versions(available_versions, "1.18.0")

        # assert
        log.log.assert_called_once()
        self.assertEqual(LogLevel.Warning, log.log.call_args[0][1])
        self.assertIn("3.0.0", log.log.call_args[0][0])


class CodeUnitWithStaticDependencies(TFCPS_CodeUnitSpecific_Base):
    """A codeunit-type whose dependencies and available versions are fixed, so that the generic dependency-update of the
    base-class can be tested without a codeunit on disk."""

    available_versions: dict[str, list[str]] = None
    dependencies: dict[str, set[str]] = None

    def get_dependencies(self) -> dict[str, set[str]]:
        return self.dependencies

    def get_available_versions(self, dependencyname: str) -> list[str]:
        return self.available_versions[dependencyname]

    def set_dependency_version(self, name: str, new_version: str) -> None:
        self.dependencies[name] = {new_version}

    def get_codeunit_name(self) -> str:
        return "Demo"


class GenericDependencyUpdateTests(unittest.TestCase):

    def test_update_logs_the_newer_major_versions_of_every_dependency(self) -> None:
        # arrange
        codeunit = CodeUnitWithStaticDependencies.__new__(CodeUnitWithStaticDependencies)
        codeunit.dependencies = {"a": {"1.16.0"}, "b": {"2.0.0"}}
        codeunit.available_versions = {"a": ["1.16.0", "1.17.0", "2.0.0"], "b": ["2.0.0", "2.1.0"]}
        codeunit.tfcps_Tools_General = MagicMock()
        codeunit.tfcps_Tools_General.get_dependencies_which_are_ignored_from_updates.return_value = []
        codeunit._protected_sc = MagicMock()
        # pylint:disable=protected-access
        codeunit._TFCPS_CodeUnitSpecific_Base__codeunit_folder = "Demo"

        # act
        codeunit.update_dependencies_with_specific_echolon(VersionEcholon.LatestPatchOrLatestMinor)

        # assert
        log_function = codeunit.tfcps_Tools_General.log_newer_major_versions_of_dependency
        self.assertEqual(2, log_function.call_count)
        log_function.assert_any_call("a", ["1.16.0", "1.17.0", "2.0.0"], "1.17.0")
        log_function.assert_any_call("b", ["2.0.0", "2.1.0"], "2.1.0")


class DockerDependencyUpdateTests(unittest.TestCase):

    def __create_docker_codeunit(self, codeunit_folder: str, versions: dict[str, str], ignored_dependencies: list[str]) -> TFCPS_CodeUnitSpecific_Docker_Functions:
        """Returns a docker-codeunit whose dependencies are pinned in "Other/Resources/Dependencies" of the given folder."""
        for dependency_name, version in versions.items():
            write_package(os.path.join(codeunit_folder, "Other", "Resources", "Dependencies", dependency_name), "Version.txt", version)
        result = create_codeunit_functions(TFCPS_CodeUnitSpecific_Docker_Functions, codeunit_folder)
        # pylint:disable=protected-access
        result._TFCPS_CodeUnitSpecific_Docker_Functions__available_versions_functions = {}
        result._protected_sc = MagicMock()
        result.tfcps_Tools_General = TFCPS_Tools_General(result._protected_sc)
        result.tfcps_Tools_General.get_dependencies_which_are_ignored_from_updates = MagicMock(return_value=ignored_dependencies)
        return result

    def __read_version(self, codeunit_folder: str, dependency_name: str) -> str:
        return GeneralUtilities.read_text_from_file(os.path.join(codeunit_folder, "Other", "Resources", "Dependencies", dependency_name, "Version.txt"))

    def test_get_dependencies_returns_the_versions_of_the_resources_folder(self) -> None:
        with tempfile.TemporaryDirectory() as codeunit_folder:
            # arrange
            codeunit = self.__create_docker_codeunit(codeunit_folder, {"OpenSpec": "1.16.0", "Node": "22"}, [])

            # act
            actual = codeunit.get_dependencies()

            # assert
            self.assertEqual({"Node": {"22"}, "OpenSpec": {"1.16.0"}}, actual)

    def test_get_available_versions_passes_the_current_version_to_the_registered_function(self) -> None:
        with tempfile.TemporaryDirectory() as codeunit_folder:
            # arrange
            codeunit = self.__create_docker_codeunit(codeunit_folder, {"OpenSpec": "1.16.0"}, [])
            codeunit.register_available_versions_function("OpenSpec", lambda current_version: [current_version, "1.17.0"])

            # act
            actual = codeunit.get_available_versions("OpenSpec")

            # assert
            self.assertEqual(["1.16.0", "1.17.0"], actual)

    def test_get_available_versions_rejects_a_dependency_without_registered_function(self) -> None:
        with tempfile.TemporaryDirectory() as codeunit_folder:
            # arrange
            codeunit = self.__create_docker_codeunit(codeunit_folder, {"OpenSpec": "1.16.0"}, [])

            # act & assert
            with self.assertRaises(ValueError):
                codeunit.get_available_versions("OpenSpec")

    def test_update_updates_the_registered_dependencies_and_skips_the_ignored_ones(self) -> None:
        with tempfile.TemporaryDirectory() as codeunit_folder:
            # arrange
            codeunit = self.__create_docker_codeunit(codeunit_folder, {"OpenSpec": "1.16.0", "Node": "22"}, ["Node"])
            codeunit.register_available_versions_function("OpenSpec", lambda current_version: ["1.16.0", "1.17.0", "2.0.0"])

            # act
            codeunit.update_dependencies()

            # assert
            self.assertEqual("1.17.0", self.__read_version(codeunit_folder, "OpenSpec"))
            self.assertEqual("22", self.__read_version(codeunit_folder, "Node"))
            # pylint:disable=protected-access
            codeunit._protected_sc.log.log.assert_any_call("Dependency OpenSpec is used in version 1.17.0, which is 1 major-version(s) behind the latest available version 2.0.0. A new major-version has to be taken over deliberately.", LogLevel.Information)
