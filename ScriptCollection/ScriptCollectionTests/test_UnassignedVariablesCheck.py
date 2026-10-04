import os
import tempfile
import unittest
from ..ScriptCollection.GeneralUtilities import GeneralUtilities
from ..ScriptCollection.UnassignedVariablesCheck import UnassignedVariablesCheck


class UnassignedVariablesCheckTests(unittest.TestCase):

    @staticmethod
    def __find_in_single_file(folder: str, content: str) -> list[tuple[str, int, str]]:
        GeneralUtilities.write_text_to_file(os.path.join(folder, "module.py"), content)
        return UnassignedVariablesCheck.find(folder)

    def test_find_detects_a_bare_annotation_at_module_level(self) -> None:
        # arrange
        with tempfile.TemporaryDirectory() as folder:
            file = os.path.join(folder, "module.py")
            GeneralUtilities.write_text_to_file(file, "x = 1\ny: int\n")

            # act
            actual = UnassignedVariablesCheck.find(folder)

        # assert
        assert actual == [(file, 2, "y")]

    def test_find_detects_a_bare_annotation_in_a_method_body(self) -> None:
        # arrange
        content = "class A:\n    def f(self):\n        value: str\n        return 1\n"
        with tempfile.TemporaryDirectory() as folder:

            # act
            actual = UnassignedVariablesCheckTests.__find_in_single_file(folder, content)

        # assert
        assert [(line, name) for _, line, name in actual] == [(3, "value")]

    def test_find_ignores_an_annotation_with_assignment(self) -> None:
        # arrange
        content = "def f():\n    value: str = None\n    return value\n"
        with tempfile.TemporaryDirectory() as folder:

            # act
            actual = UnassignedVariablesCheckTests.__find_in_single_file(folder, content)

        # assert
        assert len(actual) == 0, actual

    def test_find_ignores_a_bare_annotation_directly_in_a_class_body(self) -> None:
        # arrange
        content = "class A:\n    value: str\n"
        with tempfile.TemporaryDirectory() as folder:

            # act
            actual = UnassignedVariablesCheckTests.__find_in_single_file(folder, content)

        # assert
        assert len(actual) == 0, actual

    def test_find_ignores_files_with_syntax_errors(self) -> None:
        # arrange
        content = "def f(:\n    value: str\n"
        with tempfile.TemporaryDirectory() as folder:

            # act
            actual = UnassignedVariablesCheckTests.__find_in_single_file(folder, content)

        # assert
        assert len(actual) == 0, actual

    def test_find_ignores_files_in_pycache_folders(self) -> None:
        # arrange
        with tempfile.TemporaryDirectory() as folder:
            pycache_folder = os.path.join(folder, "__pycache__")
            GeneralUtilities.ensure_directory_exists(pycache_folder)
            GeneralUtilities.write_text_to_file(os.path.join(pycache_folder, "module.py"), "value: str\n")

            # act
            actual = UnassignedVariablesCheck.find(folder)

        # assert
        assert len(actual) == 0, actual

    def test_assert_no_unassigned_variables_in_codeunit_raises_assertion_error_for_a_bare_annotation_in_the_tests(self) -> None:
        # arrange
        with tempfile.TemporaryDirectory() as temp_folder:
            codeunit_folder = os.path.join(temp_folder, "MyCodeUnit")
            GeneralUtilities.ensure_directory_exists(os.path.join(codeunit_folder, "MyCodeUnit"))
            GeneralUtilities.ensure_directory_exists(os.path.join(codeunit_folder, "MyCodeUnitTests"))
            GeneralUtilities.write_text_to_file(os.path.join(codeunit_folder, "MyCodeUnitTests", "test_x.py"), "value: str\n")

            # act & assert
            with self.assertRaises(AssertionError):
                UnassignedVariablesCheck.assert_no_unassigned_variables_in_codeunit(codeunit_folder)

    def test_assert_no_unassigned_variables_in_codeunit_accepts_a_clean_codeunit(self) -> None:
        # arrange
        with tempfile.TemporaryDirectory() as temp_folder:
            codeunit_folder = os.path.join(temp_folder, "MyCodeUnit")
            GeneralUtilities.ensure_directory_exists(os.path.join(codeunit_folder, "MyCodeUnit"))
            GeneralUtilities.ensure_directory_exists(os.path.join(codeunit_folder, "MyCodeUnitTests"))
            GeneralUtilities.write_text_to_file(os.path.join(codeunit_folder, "MyCodeUnit", "module.py"), "value: str = None\n")

            # act
            UnassignedVariablesCheck.assert_no_unassigned_variables_in_codeunit(codeunit_folder)

        # assert
        # reaching this point without an AssertionError is the expected outcome.

    def test_assert_no_unassigned_variables_in_codeunit_rejects_a_codeunit_without_test_package(self) -> None:
        # arrange
        with tempfile.TemporaryDirectory() as temp_folder:
            codeunit_folder = os.path.join(temp_folder, "MyCodeUnit")
            GeneralUtilities.ensure_directory_exists(os.path.join(codeunit_folder, "MyCodeUnit"))

            # act & assert
            with self.assertRaises(ValueError):
                UnassignedVariablesCheck.assert_no_unassigned_variables_in_codeunit(codeunit_folder)
