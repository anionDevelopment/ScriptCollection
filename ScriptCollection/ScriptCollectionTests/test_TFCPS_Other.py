import os
import tempfile
import unittest
from unittest.mock import patch
from ..ScriptCollection.GeneralUtilities import GeneralUtilities
from ..ScriptCollection.ScriptCollectionCore import ScriptCollectionCore
from ..ScriptCollection.SCLog import LogLevel
from ..ScriptCollection.TFCPS.TFCPS_CodeUnitSpecific_Base import TFCPS_CodeUnitSpecific_Base
from ..ScriptCollection.TFCPS.TFCPS_CodeUnit_BuildCodeUnits import TFCPS_CodeUnit_BuildCodeUnits
from ..ScriptCollection.TFCPS.TFCPS_Tools_General import TFCPS_Tools_General


def generate_toc_md_file_content_for_toc_yml_content(toc_yml_content: str) -> str:
    """Writes the given toc.yml-content to a temporary file and returns the generated toc.md-content for it."""
    # pylint:disable=protected-access
    generate_toc_md_file_content = TFCPS_CodeUnitSpecific_Base._TFCPS_CodeUnitSpecific_Base__generate_toc_md_file_content
    with tempfile.TemporaryDirectory() as temporary_folder:
        toc_file = os.path.join(temporary_folder, "toc.yml")
        GeneralUtilities.write_text_to_file(toc_file, toc_yml_content)
        return generate_toc_md_file_content(toc_file)


def write_product_information_file(repository: str, required_environment_variable_names: list[str], declare_required_environment_variables: bool = True) -> str:
    """Writes a minimal '<repository>/.ScriptCollection/ProductInformation.xml' which declares the given environment-variables as required.
    The declaration-element is always written (empty when no variable is given), because it is required; only a test which verifies
    exactly that sets 'declare_required_environment_variables' to false."""
    scriptcollection_folder = os.path.join(repository, ".ScriptCollection")
    GeneralUtilities.ensure_directory_exists(scriptcollection_folder)
    product_information_file = os.path.join(scriptcollection_folder, "ProductInformation.xml")
    if declare_required_environment_variables:
        declarations = GeneralUtilities.empty_string.join(f"<cps:requiredenvironmentvariable>{name}</cps:requiredenvironmentvariable>" for name in required_environment_variable_names)
        required_environment_variables_element = f"<cps:requiredenvironmentvariables>{declarations}</cps:requiredenvironmentvariables>"
    else:
        required_environment_variables_element = GeneralUtilities.empty_string
    GeneralUtilities.write_text_to_file(product_information_file, f"""<?xml version="1.0" encoding="UTF-8"?>
<cps:productinformation xmlns:cps="https://projects.aniondev.de/PublicProjects/Common/ProjectTemplates/-/tree/main/Conventions/RepositoryStructure/CommonProjectStructure">
    <cps:producttitle>TestProduct</cps:producttitle>
    <cps:remoteaddress>https://example.com/TestProduct</cps:remoteaddress>
    {required_environment_variables_element}
</cps:productinformation>
""")
    return product_information_file


def create_build_codeunits_for_folder(repository: str) -> TFCPS_CodeUnit_BuildCodeUnits:
    """Returns a TFCPS_CodeUnit_BuildCodeUnits for the given folder. The folder is turned into something the constructor accepts as a
    git-repository by creating its '.git'-folder, which is sufficient here because the tests which use this only exercise a single
    build-step and therefore never run a git-command."""
    GeneralUtilities.ensure_directory_exists(os.path.join(repository, ".git"))
    return TFCPS_CodeUnit_BuildCodeUnits(repository, LogLevel.Information, "Development", None, True, False, False)


def update_openspec(build_codeunits: TFCPS_CodeUnit_BuildCodeUnits) -> None:
    """Runs the openspec-update-step of the given build."""
    # pylint:disable=protected-access
    build_codeunits._TFCPS_CodeUnit_BuildCodeUnits__update_openspec()


def write_openspec_configuration_file(repository: str) -> str:
    """Writes the file whose existence declares that the repository uses openspec."""
    openspec_folder = os.path.join(repository, "openspec")
    GeneralUtilities.ensure_directory_exists(openspec_folder)
    configuration_file = os.path.join(openspec_folder, "config.yaml")
    GeneralUtilities.write_text_to_file(configuration_file, "schema: spec-driven\n")
    return configuration_file


def write_environment_variables_configuration_file(configuration_folder: str, lines: list[str]) -> str:
    """Writes the file which defines where the values of the required environment-variables come from into the given
    configuration-folder (which a test uses instead of the configuration-folder of the current user)."""
    file = os.path.join(configuration_folder, "TFCPS", "EnvironmentVariables.csv")
    GeneralUtilities.ensure_directory_exists(os.path.dirname(file))
    GeneralUtilities.write_lines_to_file(file, ["EnvVariableName;Kind;Value"]+lines)
    return file


def write_additional_required_environment_variables_file(configuration_folder: str, lines: list[str]) -> str:
    """Writes the file which declares the environment-variables which are additionally required for every codeunit-build on the
    machine into the given configuration-folder (which a test uses instead of the configuration-folder of the current user)."""
    file = os.path.join(configuration_folder, "TFCPS", "AdditionalRequiredEnvironmentVariables.txt")
    GeneralUtilities.ensure_directory_exists(os.path.dirname(file))
    GeneralUtilities.write_lines_to_file(file, lines)
    return file


class TasksForCommonProjectStructureTests(unittest.TestCase):

    def test_sort_codenits_1(self) -> None:
        # arrange
        t = TFCPS_Tools_General(ScriptCollectionCore())
        function_input = {}
        expected_result = []

        # act
        actual_result = t._internal_get_sorted_codeunits_by_dict(function_input)

        # assert
        assert expected_result == actual_result

    def test_sort_codenits_2(self) -> None:
        # arrange
        t = TFCPS_Tools_General(ScriptCollectionCore())
        function_input = {
            'codeunit_01': {}
        }
        expected_result = ['codeunit_01']

        # act
        actual_result = t._internal_get_sorted_codeunits_by_dict(function_input)

        # assert
        assert expected_result == actual_result

    def test_sort_codenits_3(self) -> None:
        # arrange
        t = TFCPS_Tools_General(ScriptCollectionCore())
        function_input = {
            'codeunit_01': {},
            'codeunit_02': {'codeunit_01'}
        }
        expected_result = ['codeunit_01', 'codeunit_02']

        # act
        actual_result = t._internal_get_sorted_codeunits_by_dict(function_input)

        # assert
        assert expected_result == actual_result

    def test_sort_codenits_4(self) -> None:
        # arrange
        t = TFCPS_Tools_General(ScriptCollectionCore())
        function_input = {
            'codeunit_01': {},
            'codeunit_02': {'codeunit_03', 'codeunit_01'},
            'codeunit_04': {'codeunit_01'},
            'codeunit_03': {'codeunit_04'}
        }
        expected_result = ['codeunit_01', 'codeunit_04', 'codeunit_03', 'codeunit_02']

        # act
        actual_result = t._internal_get_sorted_codeunits_by_dict(function_input)

        # assert
        assert expected_result == actual_result

    def test_sort_reference_folder(self) -> None:
        assert TFCPS_Tools_General.sort_reference_folder("/folder/Latest", "/folder/Latest") == 0
        assert TFCPS_Tools_General.sort_reference_folder("/folder/v1.1.1", "/folder/Latest") > 0
        assert TFCPS_Tools_General.sort_reference_folder("/folder/Latest", "/folder/v1.1.1") < 0
        assert TFCPS_Tools_General.sort_reference_folder("/folder/v3.5.7", "/folder/v4.6.8") < 0
        assert TFCPS_Tools_General.sort_reference_folder("/folder/v4.6.8", "/folder/v3.5.7") > 0
        assert TFCPS_Tools_General.sort_reference_folder("/folder/v3.3.5", "/folder/v3.3.4") > 0
        assert TFCPS_Tools_General.sort_reference_folder("/folder/v3.3.5", "/folder/v3.3.5") == 0
        assert TFCPS_Tools_General.sort_reference_folder("/folder/v3.3.5", "/folder/v3.3.6") < 0
        assert TFCPS_Tools_General.sort_reference_folder("/folder/v3.3.5", "/folder/v3.3.17") < 0
        assert TFCPS_Tools_General.sort_reference_folder("/folder/v3.3.5", "/folder/v3.8.0") < 0
        assert TFCPS_Tools_General.sort_reference_folder("/folder/v3.3.5", "/folder/v3.3.05") == 0
        assert TFCPS_Tools_General.sort_reference_folder("/folder/v3.0.0", "/folder/v4.0.0") < 0
        assert TFCPS_Tools_General.sort_reference_folder("/folder/v4.0.0", "/folder/v3.0.0") > 0
        assert TFCPS_Tools_General.sort_reference_folder("/folder/v4.0.0", "/folder/v4.0.0") == 0

    def test_generate_toc_md_file_content_with_empty_toc(self) -> None:
        # arrange
        function_input = "### YamlMime:TableOfContent\nitems: []\n"
        expected_result = "# Table of contents\n"

        # act
        actual_result = generate_toc_md_file_content_for_toc_yml_content(function_input)

        # assert
        assert expected_result == actual_result

    def test_generate_toc_md_file_content_with_namespaces_and_types(self) -> None:
        # arrange
        function_input = """### YamlMime:TableOfContent
items:
- uid: Example.Core
  name: Example.Core
  type: Namespace
  items:
  - uid: Example.Core.Generic
    name: Generic
    type: Class
  - uid: Example.Core.GenericXMLSerializer`1
    name: GenericXMLSerializer<T>
    type: Class
- uid: Example.Core.Misc
  name: Example.Core.Misc
  type: Namespace
  items:
  - uid: Example.Core.Misc.Utilities
    name: Utilities
    type: Class
"""
        expected_result = """# Table of contents

## Example.Core

- [Generic](./Example.Core.Generic.yml)
- [GenericXMLSerializer&lt;T&gt;](./Example.Core.GenericXMLSerializer-1.yml)

## Example.Core.Misc

- [Utilities](./Example.Core.Misc.Utilities.yml)
"""

        # act
        actual_result = generate_toc_md_file_content_for_toc_yml_content(function_input)

        # assert
        assert expected_result == actual_result

    def test_generate_toc_md_file_content_with_namespace_without_types(self) -> None:
        # arrange
        function_input = """### YamlMime:TableOfContent
items:
- uid: Example.Core
  name: Example.Core
  type: Namespace
"""
        expected_result = """# Table of contents

## Example.Core

(This namespace does not contain any documented type.)
"""

        # act
        actual_result = generate_toc_md_file_content_for_toc_yml_content(function_input)

        # assert
        assert expected_result == actual_result

    def test_get_required_environment_variable_names_returns_empty_list_when_nothing_is_declared(self) -> None:
        # arrange
        t = TFCPS_Tools_General(ScriptCollectionCore())
        #the configuration-folder is isolated from the real one of the machine which runs this test: otherwise a machine-local
        #"AdditionalRequiredEnvironmentVariables.txt" (see get_additional_required_environment_variable_names_for_this_machine) would leak
        #into the result and make this test non-deterministic depending on the machine it runs on.
        with tempfile.TemporaryDirectory() as repository, tempfile.TemporaryDirectory() as configuration_folder:
            write_product_information_file(repository, [])
            with patch.object(GeneralUtilities, "get_scriptcollection_configuration_folder", return_value=configuration_folder):

                # act
                actual_result = t.get_required_environment_variable_names(repository)

                # assert
                assert not actual_result

    def test_get_required_environment_variable_names_returns_declared_names(self) -> None:
        # arrange
        t = TFCPS_Tools_General(ScriptCollectionCore())
        #the configuration-folder is isolated from the real one of the machine which runs this test: otherwise a machine-local
        #"AdditionalRequiredEnvironmentVariables.txt" (see get_additional_required_environment_variable_names_for_this_machine) would leak
        #into the result and make this test non-deterministic depending on the machine it runs on.
        with tempfile.TemporaryDirectory() as repository, tempfile.TemporaryDirectory() as configuration_folder:
            write_product_information_file(repository, ["MyFirstVariable", "MySecondVariable"])
            with patch.object(GeneralUtilities, "get_scriptcollection_configuration_folder", return_value=configuration_folder):

                # act
                actual_result = t.get_required_environment_variable_names(repository)

                # assert
                assert actual_result == ["MyFirstVariable", "MySecondVariable"]

    def test_get_required_environment_variable_names_throws_exception_when_the_declaration_is_missing(self) -> None:
        # arrange
        t = TFCPS_Tools_General(ScriptCollectionCore())
        with tempfile.TemporaryDirectory() as repository:
            write_product_information_file(repository, [], declare_required_environment_variables=False)

            # act & assert
            #a missing declaration is a mistake and must not be treated like the statement "this product does not need any environment-variable".
            with self.assertRaises(ValueError):
                t.get_required_environment_variable_names(repository)

    def test_get_required_environment_variable_names_includes_the_machine_local_additional_names(self) -> None:
        # arrange
        t = TFCPS_Tools_General(ScriptCollectionCore())
        with tempfile.TemporaryDirectory() as repository, tempfile.TemporaryDirectory() as configuration_folder:
            write_product_information_file(repository, ["MyFirstVariable"])
            #comments and blank lines must be ignored, and a name which is already declared by the repository must not be duplicated.
            write_additional_required_environment_variables_file(configuration_folder, ["# a comment", "", "MyMachineLocalVariable", "MyFirstVariable"])
            with patch.object(GeneralUtilities, "get_scriptcollection_configuration_folder", return_value=configuration_folder):

                # act
                actual_result = t.get_required_environment_variable_names(repository)

                # assert
                #the names declared for the machine are required in addition to (not instead of) the ones declared by the repository, because they
                #are needed by machine-local tooling instead of by the repository itself.
                assert actual_result == ["MyFirstVariable", "MyMachineLocalVariable"]

    def test_get_required_environment_variable_names_does_not_require_a_machine_local_additional_names_file(self) -> None:
        # arrange
        t = TFCPS_Tools_General(ScriptCollectionCore())
        with tempfile.TemporaryDirectory() as repository, tempfile.TemporaryDirectory() as configuration_folder:
            write_product_information_file(repository, ["MyFirstVariable"])
            with patch.object(GeneralUtilities, "get_scriptcollection_configuration_folder", return_value=configuration_folder):

                # act
                #the file which declares the machine-local additional names is optional: a machine which does not have any does not have to create an empty one.
                actual_result = t.get_required_environment_variable_names(repository)

                # assert
                assert actual_result == ["MyFirstVariable"]

    def test_get_required_environment_variables_returns_empty_dict_when_nothing_is_declared(self) -> None:
        # arrange
        t = TFCPS_Tools_General(ScriptCollectionCore())
        #the configuration-folder is isolated from the real one of the machine which runs this test: otherwise a machine-local
        #"AdditionalRequiredEnvironmentVariables.txt" (see get_additional_required_environment_variable_names_for_this_machine) would leak
        #into the result and make this test non-deterministic depending on the machine it runs on.
        with tempfile.TemporaryDirectory() as repository, tempfile.TemporaryDirectory() as configuration_folder:
            write_product_information_file(repository, [])
            with patch.object(GeneralUtilities, "get_scriptcollection_configuration_folder", return_value=configuration_folder):

                # act
                actual_result = t.get_required_environment_variables(repository)

                # assert
                assert not actual_result

    def test_ensure_required_environment_variables_are_set_does_nothing_when_nothing_is_declared(self) -> None:
        # arrange
        t = TFCPS_Tools_General(ScriptCollectionCore())
        #the configuration-folder is isolated from the real one of the machine which runs this test: otherwise a machine-local
        #"AdditionalRequiredEnvironmentVariables.txt" (see get_additional_required_environment_variable_names_for_this_machine) would leak
        #into the result and make this test non-deterministic depending on the machine it runs on.
        with tempfile.TemporaryDirectory() as repository, tempfile.TemporaryDirectory() as configuration_folder:
            write_product_information_file(repository, [])
            with patch.object(GeneralUtilities, "get_scriptcollection_configuration_folder", return_value=configuration_folder):

                # act
                t.ensure_required_environment_variables_are_set(repository)

                # assert
                assert "MyVariable" not in os.environ

    def test_get_required_environment_variables_resolves_the_configured_kinds(self) -> None:
        # arrange
        t = TFCPS_Tools_General(ScriptCollectionCore())
        with tempfile.TemporaryDirectory() as repository, tempfile.TemporaryDirectory() as configuration_folder:
            write_product_information_file(repository, ["MyLiteralVariable", "MyHostVariable", "MySecretVariable"])
            write_environment_variables_configuration_file(configuration_folder, [
                "MyLiteralVariable;literal;MyLiteralValue",
                "MyHostVariable;hostenvvariable;MY_HOST_ENV_VARIABLE",
                "MySecretVariable;file;Secrets/MySecret.txt",
            ])
            secret_file = os.path.join(configuration_folder, "TFCPS", "Secrets", "MySecret.txt")
            GeneralUtilities.ensure_directory_exists(os.path.dirname(secret_file))
            GeneralUtilities.write_text_to_file(secret_file, "MySecretValue\n")
            with patch.object(GeneralUtilities, "get_scriptcollection_configuration_folder", return_value=configuration_folder), patch.dict(os.environ, {"MY_HOST_ENV_VARIABLE": "MyHostValue"}):

                # act
                actual_result = t.get_required_environment_variables(repository)

                # assert
                #a relative path of a secret-file is resolved against the configuration-folder, so it also resolves when that folder is mounted into a build-container.
                assert actual_result == {"MyLiteralVariable": "MyLiteralValue", "MyHostVariable": "MyHostValue", "MySecretVariable": "MySecretValue"}

    def test_get_required_environment_variables_prefers_the_configuration_file_over_the_environment(self) -> None:
        # arrange
        t = TFCPS_Tools_General(ScriptCollectionCore())
        with tempfile.TemporaryDirectory() as repository, tempfile.TemporaryDirectory() as configuration_folder:
            write_product_information_file(repository, ["MyVariable"])
            write_environment_variables_configuration_file(configuration_folder, ["MyVariable;literal;ValueFromTheConfigurationFile"])
            with patch.object(GeneralUtilities, "get_scriptcollection_configuration_folder", return_value=configuration_folder), patch.dict(os.environ, {"MyVariable": "ValueFromTheEnvironment"}):

                # act
                actual_result = t.get_required_environment_variables(repository)

                # assert
                #the configuration-file has precedence so a resolved value does not depend on what happens to be set in the environment of the caller.
                assert actual_result == {"MyVariable": "ValueFromTheConfigurationFile"}

    def test_get_required_environment_variables_takes_the_value_from_the_environment_when_it_is_not_configured(self) -> None:
        # arrange
        t = TFCPS_Tools_General(ScriptCollectionCore())
        with tempfile.TemporaryDirectory() as repository, tempfile.TemporaryDirectory() as configuration_folder:
            write_product_information_file(repository, ["MyVariableFromThePipeline"])
            with patch.object(GeneralUtilities, "get_scriptcollection_configuration_folder", return_value=configuration_folder), patch.dict(os.environ, {"MyVariableFromThePipeline": "MyValue"}):

                # act
                #this is the case in a build-pipeline which provides the value from its own secret-store and has no configuration-file at all.
                actual_result = t.get_required_environment_variables(repository)

                # assert
                assert actual_result == {"MyVariableFromThePipeline": "MyValue"}

    def test_get_required_environment_variables_throws_exception_when_the_value_is_neither_configured_nor_set(self) -> None:
        # arrange
        t = TFCPS_Tools_General(ScriptCollectionCore())
        with tempfile.TemporaryDirectory() as repository, tempfile.TemporaryDirectory() as configuration_folder:
            write_product_information_file(repository, ["MyUnknownVariable"])
            with patch.object(GeneralUtilities, "get_scriptcollection_configuration_folder", return_value=configuration_folder):
                os.environ.pop("MyUnknownVariable", None)

                # act & assert
                with self.assertRaises(ValueError):
                    t.get_required_environment_variables(repository)

    def test_ensure_required_environment_variables_are_set_sets_the_resolved_values(self) -> None:
        # arrange
        t = TFCPS_Tools_General(ScriptCollectionCore())
        with tempfile.TemporaryDirectory() as repository, tempfile.TemporaryDirectory() as configuration_folder:
            write_product_information_file(repository, ["MyVariableWhichHasToBeSet"])
            write_environment_variables_configuration_file(configuration_folder, ["MyVariableWhichHasToBeSet;literal;MyValue"])
            with patch.object(GeneralUtilities, "get_scriptcollection_configuration_folder", return_value=configuration_folder), patch.dict(os.environ, {}):

                # act
                t.ensure_required_environment_variables_are_set(repository)

                # assert
                #the value is set in the environment of the current process so every sub-process of the build inherits it.
                assert os.environ["MyVariableWhichHasToBeSet"] == "MyValue"

    def test_get_declared_package_sources_returns_empty_list_when_nothing_is_declared(self) -> None:
        # arrange
        t = TFCPS_Tools_General(ScriptCollectionCore())
        #cleared so that package-sources which are declared in the real environment (for example inside a build-container which
        #declares real package-sources for its own dependency-resolution) do not leak into this test and make it non-deterministic.
        with patch.dict(os.environ, {"Dependency_CSharp_Incomplete_Username": "MyUser"}, clear=True):

            # act
            actual_result = t.get_declared_package_sources("CSharp")

            # assert
            #a source is declared by its url; a lonely username does not declare anything.
            assert not actual_result

    def test_get_declared_package_sources_returns_declared_sources(self) -> None:
        # arrange
        t = TFCPS_Tools_General(ScriptCollectionCore())
        declarations = {
            "Dependency_CSharp_MyPrivateFeed_URL": "https://example.com/nuget/index.json",
            "Dependency_CSharp_MyPrivateFeed_Username": "MyUser",
            "Dependency_CSharp_MyPrivateFeed_Password": "MyPassword",
            "Dependency_CSharp_MyPublicFeed_URL": "https://example.com/public/index.json",
            "Dependency_Python_MyPythonFeed_URL": "https://example.com/pypi",
        }
        #cleared so that package-sources which are declared in the real environment (for example inside a build-container which
        #declares real package-sources for its own dependency-resolution) do not leak into this test and make it non-deterministic.
        with patch.dict(os.environ, declarations, clear=True):

            # act
            actual_result = t.get_declared_package_sources("CSharp")

            # assert
            #the names are normalized to lowercase because the case of the name of an environment-variable can not be preserved on all operating-systems.
            assert [package_source.name for package_source in actual_result] == ["myprivatefeed", "mypublicfeed"]
            assert actual_result[0].url == "https://example.com/nuget/index.json"
            assert actual_result[0].username == "MyUser"
            assert actual_result[0].password == "MyPassword"
            assert actual_result[0].has_credentials()
            #the source of another technology must not be returned and a source without credentials must be usable.
            assert not actual_result[1].has_credentials()

    def test_run_custom_script_if_available_does_nothing_when_script_does_not_exist(self) -> None:
        # arrange
        t = TFCPS_Tools_General(ScriptCollectionCore())
        with tempfile.TemporaryDirectory() as folder:

            # act
            t.run_custom_script_if_available(os.path.join(folder, "NotExisting.py"), ["--repository", folder])

            # assert
            assert not os.listdir(folder)

    def test_run_custom_script_if_available_runs_script_in_its_own_folder_with_the_given_arguments(self) -> None:
        # arrange
        t = TFCPS_Tools_General(ScriptCollectionCore())
        with tempfile.TemporaryDirectory() as folder:
            script_file = os.path.join(folder, "CustomScript.py")
            #the script writes its arguments and its working-directory into a file, so the test can verify both without mocking the program-runner.
            GeneralUtilities.write_text_to_file(script_file, "import os,sys\nopen('Result.txt','w',encoding='utf-8').write(os.getcwd()+'\\n'+' '.join(sys.argv[1:]))\n")

            # act
            t.run_custom_script_if_available(script_file, ["--repository", "MyRepository"])

            # assert
            result_lines = GeneralUtilities.read_lines_from_file(os.path.join(folder, "Result.txt"))
            assert os.path.realpath(result_lines[0]) == os.path.realpath(folder)
            assert result_lines[1] == "--repository MyRepository"

    def test_update_openspec_does_nothing_when_the_repository_does_not_use_openspec(self) -> None:
        # arrange
        with tempfile.TemporaryDirectory() as repository:
            build_codeunits = create_build_codeunits_for_folder(repository)
            with patch.object(build_codeunits.sc, "run_with_epew") as run_program:

                # act
                update_openspec(build_codeunits)

                # assert
                #a repository without "openspec/config.yaml" does not use openspec, so nothing may be run for it.
                run_program.assert_not_called()

    def test_update_openspec_updates_the_openspec_files_in_the_repository(self) -> None:
        # arrange
        with tempfile.TemporaryDirectory() as repository:
            write_openspec_configuration_file(repository)
            build_codeunits = create_build_codeunits_for_folder(repository)
            with patch.object(build_codeunits.sc, "run_with_epew") as run_program:

                # act
                update_openspec(build_codeunits)

                # assert
                #"--force" is required because openspec skips the update when it considers the generated files up-to-date, and the update
                #must run in the repository because that is the folder whose openspec-files are meant. The openspec-cli is started using epew
                #because on windows it is a ".cmd"-file, which the direct process-start can not resolve.
                run_program.assert_called_once_with("openspec", "update --force", repository)

    def test_get_expected_schemalocation_references_the_xsd_of_the_given_version(self) -> None:
        # act
        actual_result = TFCPS_CodeUnitSpecific_Base.get_expected_schemalocation("3.0.0")

        # assert
        #the schema-location consists of the namespace of the codeunit-file and the address of the xsd-file of exactly the
        #codeunit-specification-version which the codeunit-file declares.
        expected_result = "https://projects.aniondev.de/PublicProjects/Common/ProjectTemplates/-/tree/main/Conventions/RepositoryStructure/CommonProjectStructure "\
            "https://projects.aniondev.de/PublicProjects/Common/ProjectTemplates/-/raw/v3.0.0/Conventions/RepositoryStructure/CommonProjectStructure/codeunit.xsd"
        self.assertEqual(expected_result, actual_result)

    def test_get_expected_xsd_address_is_the_second_part_of_the_expected_schemalocation(self) -> None:
        # act
        actual_result = TFCPS_CodeUnitSpecific_Base.get_expected_xsd_address("3.0.0")

        # assert
        #the xsd-address must be usable as schema-source on its own, means it must not contain the namespace which the schema-location
        #additionally contains, because a validator which gets the whole schema-location would try to parse the namespace-uri as xsd-file.
        expected_result = "https://projects.aniondev.de/PublicProjects/Common/ProjectTemplates/-/raw/v3.0.0/Conventions/RepositoryStructure/CommonProjectStructure/codeunit.xsd"
        self.assertEqual(expected_result, actual_result)
        self.assertEqual(f"{TFCPS_CodeUnitSpecific_Base.codeunit_namespace} {actual_result}", TFCPS_CodeUnitSpecific_Base.get_expected_schemalocation("3.0.0"))

    def test_get_expected_schemalocation_of_another_version_references_another_xsd(self) -> None:
        # act
        actual_result = TFCPS_CodeUnitSpecific_Base.get_expected_schemalocation("4.1.2")

        # assert
        self.assertIn("/-/raw/v4.1.2/", actual_result)
        self.assertNotIn("/-/raw/v3.0.0/", actual_result)

    def test_generate_toc_md_file_content_with_toc_without_items_property(self) -> None:
        # arrange
        function_input = """- uid: Example.Core
  name: Example.Core
  items:
  - uid: Example.Core.Utilities
    name: Utilities
"""
        expected_result = """# Table of contents

## Example.Core

- [Utilities](./Example.Core.Utilities.yml)
"""

        # act
        actual_result = generate_toc_md_file_content_for_toc_yml_content(function_input)

        # assert
        assert expected_result == actual_result
