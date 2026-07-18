import os
import tempfile
import unittest
from ..ScriptCollection.GeneralUtilities import GeneralUtilities
from ..ScriptCollection.ScriptCollectionCore import ScriptCollectionCore
from ..ScriptCollection.TFCPS.TFCPS_CodeUnitSpecific_Base import TFCPS_CodeUnitSpecific_Base
from ..ScriptCollection.TFCPS.TFCPS_Tools_General import TFCPS_Tools_General


def generate_toc_md_file_content_for_toc_yml_content(toc_yml_content: str) -> str:
    """Writes the given toc.yml-content to a temporary file and returns the generated toc.md-content for it."""
    # pylint:disable=protected-access
    generate_toc_md_file_content = TFCPS_CodeUnitSpecific_Base._TFCPS_CodeUnitSpecific_Base__generate_toc_md_file_content
    with tempfile.TemporaryDirectory() as temporary_folder:
        toc_file = os.path.join(temporary_folder, "toc.yml")
        GeneralUtilities.write_text_to_file(toc_file, toc_yml_content)
        return generate_toc_md_file_content(toc_file)


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

    def test_get_required_env_variables_returns_empty_dict_when_file_does_not_exist(self) -> None:
        # arrange
        t = TFCPS_Tools_General(ScriptCollectionCore())
        with tempfile.TemporaryDirectory() as repository:

            # act
            actual_result = t.get_required_env_variables(repository)

            # assert
            assert not actual_result

    def test_get_required_env_variables_resolves_all_kinds(self) -> None:
        # arrange
        t = TFCPS_Tools_General(ScriptCollectionCore())
        with tempfile.TemporaryDirectory() as repository:
            value_file = os.path.join(repository, "MySecretVariable.txt")
            GeneralUtilities.write_text_to_file(value_file, "ValueFromFile\n")
            required_env_variables_file = t.get_required_env_variables_file(repository)
            GeneralUtilities.ensure_directory_exists(os.path.dirname(required_env_variables_file))
            GeneralUtilities.ensure_file_exists(required_env_variables_file)
            GeneralUtilities.write_text_to_file(required_env_variables_file, "EnvVariableName;Kind;Value\n"
                                                 "MyLiteralVariable;literal;MyValue\n"
                                                 "MyHostVariable;hostenvvariable;MY_HOST_ENV_VARIABLE_FOR_TEST\n"
                                                 "MySecretVariable;file;MySecretVariable.txt\n")
            os.environ["MY_HOST_ENV_VARIABLE_FOR_TEST"] = "ValueFromHost"
            expected_result = {
                "MyLiteralVariable": "MyValue",
                "MyHostVariable": "ValueFromHost",
                "MySecretVariable": "ValueFromFile",
            }

            try:
                # act
                actual_result = t.get_required_env_variables(repository)
            finally:
                del os.environ["MY_HOST_ENV_VARIABLE_FOR_TEST"]

            # assert
            assert actual_result == expected_result

    def test_get_required_env_variables_throws_when_host_env_variable_is_not_set(self) -> None:
        # arrange
        t = TFCPS_Tools_General(ScriptCollectionCore())
        with tempfile.TemporaryDirectory() as repository:
            required_env_variables_file = t.get_required_env_variables_file(repository)
            GeneralUtilities.ensure_directory_exists(os.path.dirname(required_env_variables_file))
            GeneralUtilities.ensure_file_exists(required_env_variables_file)
            GeneralUtilities.write_text_to_file(required_env_variables_file, "EnvVariableName;Kind;Value\n"
                                                 "MyHostVariable;hostenvvariable;MY_NOT_EXISTING_HOST_ENV_VARIABLE_FOR_TEST\n")
            os.environ.pop("MY_NOT_EXISTING_HOST_ENV_VARIABLE_FOR_TEST", None)

            # act/assert
            with self.assertRaises(ValueError):
                t.get_required_env_variables(repository)

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
