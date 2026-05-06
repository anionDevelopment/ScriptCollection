import os
from typing import NoReturn
import unittest
from pathlib import Path
import tempfile
import uuid
from ..ScriptCollection.GeneralUtilities import GeneralUtilities
from ..ScriptCollection.ScriptCollectionCore import ScriptCollectionCore


class ScriptCollectionCoreTests(unittest.TestCase):

    encoding = "utf-8"
    testfileprefix = "testfile_"

    def test_export_filemetadata(self) -> None:
        # arrange
        sc = ScriptCollectionCore()
        tests_folder = tempfile.gettempdir()+os.path.sep+str(uuid.uuid4())
        try:
            GeneralUtilities.ensure_directory_exists(tests_folder)
            target_file = os.path.join(tests_folder, "test.csv")
            assert not os.path.isfile(target_file)
            dir_path = os.path.dirname(os.path.realpath(__file__))
            folder_for_export = GeneralUtilities.resolve_relative_path("../Other/Reference", dir_path)

            # act
            sc.export_filemetadata(folder_for_export, target_file)

            # assert
            assert os.path.isfile(target_file)
            # TODO add more assertions
        finally:
            GeneralUtilities.ensure_directory_does_not_exist(tests_folder)

    def test_ls_for_folder_content(self) -> None:
        # arrange
        sc = ScriptCollectionCore()
        tests_folder = tempfile.gettempdir()+os.path.sep+str(uuid.uuid4())
        try:
            GeneralUtilities.ensure_directory_exists(tests_folder)
            filename1 = "test1.csv"
            target_file1 = os.path.join(tests_folder, filename1)
            filename2 = "test2.csv"
            target_file2 = os.path.join(tests_folder, filename2)
            GeneralUtilities.ensure_file_exists(target_file1)
            GeneralUtilities.ensure_file_exists(target_file2)

            # act
            lines: list[str] = sc.run_ls_for_folder_content(tests_folder)

            # assert
            assert len(lines) == 2
            assert filename1 in lines[0]
            assert filename2 in lines[1]
        finally:
            GeneralUtilities.ensure_directory_does_not_exist(tests_folder)

    def test_ls_for_folder(self) -> None:
        # arrange
        sc = ScriptCollectionCore()
        tests_folder = tempfile.gettempdir()+os.path.sep+str(uuid.uuid4())
        try:
            GeneralUtilities.ensure_directory_exists(tests_folder)
            filename1 = "test1.csv"
            target_file = os.path.join(tests_folder, filename1)
            filename2 = "test2.csv"
            target_file = os.path.join(tests_folder, filename2)
            GeneralUtilities.ensure_file_exists(target_file)

            # act
            line: str = sc.run_ls_for_folder(tests_folder)

            # assert
            assert filename1 not in line
            assert filename2 not in line
            assert os.path.basename(tests_folder) in line
        finally:
            GeneralUtilities.ensure_directory_does_not_exist(tests_folder)

    def test_git_commit_is_ancestor(self) -> None:
        sc = ScriptCollectionCore()
        folder_of_this_file = os.path.dirname(__file__)
        repository = GeneralUtilities.resolve_relative_path("..\\..", folder_of_this_file)
        assert sc.git_commit_is_ancestor(repository, "d64bc41f9d818d665993758fcdf38477e7086c3f", "c5f8e93bd6f237297d8a75faba8ff5aa6eeb5c08")
        assert not sc.git_commit_is_ancestor(repository, "c5f8e93bd6f237297d8a75faba8ff5aa6eeb5c08", "d64bc41f9d818d665993758fcdf38477e7086c3f")

    def test_rename_git_repositories(self) -> None:
        # arrange
        folder = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))
        try:
            GeneralUtilities.ensure_directory_exists(folder)
            sc = ScriptCollectionCore()

            # folder
            # +-- a (folder)
            # |  +-- b1 (folder)
            # |  |   +-- .git (file)
            # |  +-- b2 (folder)
            # |      +-- .git (folder)
            # |          +-- head  (file)
            # +-- .git (folder)
            # |   +-- head (file)
            # +-- c
            #     +-- d1.gitd2.gitd3 (folder)
            # |       +-- head (file)

            folder_a = os.path.join(folder, "a")  # item 1
            folder_a_b1 = os.path.join(folder_a, "b1")  # item 2
            file_a_b1_git = os.path.join(folder_a_b1, ".git")  # item 3
            folder_a_b2 = os.path.join(folder_a, "b2")  # item 4
            folder_a_b2_git = os.path.join(folder_a_b2, ".git")  # item 5
            file_a_b2_git_head = os.path.join(folder_a_b2_git, "head")  # item 6
            folder_git = os.path.join(folder, ".git")  # item 7
            file_git_head = os.path.join(folder_git, "head")  # item 8
            folder_c = os.path.join(folder, "c")  # item 9
            folder_d = os.path.join(folder_c, "d.gitd.gitd")  # item 10
            file_c_d_head = os.path.join(folder_d, "head")  # item 11

            GeneralUtilities.ensure_directory_exists(folder_a)  # item 1
            GeneralUtilities.ensure_directory_exists(folder_a_b1)  # item 2
            GeneralUtilities.ensure_file_exists(file_a_b1_git)  # item 3
            GeneralUtilities.ensure_directory_exists(folder_a_b2)  # item 4
            GeneralUtilities.ensure_directory_exists(folder_a_b2_git)  # item 5
            GeneralUtilities.ensure_file_exists(file_a_b2_git_head)  # item 6
            GeneralUtilities.ensure_directory_exists(folder_git)  # item 7
            GeneralUtilities.ensure_file_exists(file_git_head)  # item 8
            GeneralUtilities.ensure_directory_exists(folder_c)  # item 9
            GeneralUtilities.ensure_directory_exists(folder_d)  # item 10
            GeneralUtilities.ensure_file_exists(file_c_d_head)  # item 11

            # act
            renamed_items = sc.escape_git_repositories_in_folder(folder)

            # assert
            assert os.path.isdir(folder_a)  # item 1
            assert os.path.isdir(folder_a_b1)  # item 2
            assert not os.path.isfile(file_a_b1_git)  # item 3
            assert os.path.isfile(file_a_b1_git+"x")  # item 3
            assert os.path.isdir(folder_a_b2)  # item 4
            assert not os.path.isdir(folder_a_b2_git)  # item 5
            assert os.path.isdir(folder_a_b2_git+"x")  # item 5
            assert not os.path.isfile(file_a_b2_git_head)  # item 6
            assert os.path.isfile(os.path.join(folder_a_b2_git+"x", "head"))  # item 6
            assert not os.path.isdir(folder_git)  # item 7
            assert os.path.isdir(folder_git+"x")  # item 7
            assert not os.path.isfile(file_git_head)  # item 8
            assert os.path.isfile(os.path.join(folder_git+"x", "head"))  # item 8
            assert os.path.isdir(folder_c)  # item 9
            assert not os.path.isdir(folder_d)  # item 10
            assert os.path.isdir(os.path.join(folder_c, "d.gitxd.gitxd"))  # item 10
            assert not os.path.isfile(file_c_d_head)  # item 11
            assert os.path.isfile(os.path.join(folder_c, "d.gitxd.gitxd", "head"))  # item 11

            # act
            sc.deescape_git_repositories_in_folder(renamed_items)

            # assert
            assert os.path.isdir(folder_a)  # item 1
            assert os.path.isdir(folder_a_b1)  # item 2
            assert os.path.isfile(file_a_b1_git)  # item 3
            assert not os.path.isfile(file_a_b1_git+"x")  # item 3
            assert os.path.isdir(folder_a_b2)  # item 4
            assert os.path.isdir(folder_a_b2_git)  # item 5
            assert not os.path.isdir(folder_a_b2_git+"x")  # item 5
            assert os.path.isfile(file_a_b2_git_head)  # item 6
            assert not os.path.isfile(os.path.join(folder_a_b2_git+"x", "head"))  # item 6
            assert os.path.isdir(folder_git)  # item 7
            assert not os.path.isdir(folder_git+"x")  # item 7
            assert os.path.isfile(file_git_head)  # item 8
            assert not os.path.isfile(os.path.join(folder_git+"x", "head"))  # item 8
            assert os.path.isdir(folder_c)  # item 9
            assert os.path.isdir(folder_d)  # item 10
            assert not os.path.isdir(os.path.join(folder_c, "d.gitxd.gitxd"))  # item 10
            assert os.path.isfile(file_c_d_head)  # item 11
            assert not os.path.isfile(os.path.join(folder_c, "d.gitxd.gitxd", "head"))  # item 11

        finally:
            GeneralUtilities.ensure_directory_exists(folder)

    def test_to_list_none(self):
        # arrange
        testinput = None
        expected = []

        # act
        actual = GeneralUtilities.to_list(testinput, ",")

        # assert
        assert expected == actual

    def test_to_list_empty(self):
        # arrange
        testinput = "   "
        expected = []

        # act
        actual = GeneralUtilities.to_list(testinput, ",")

        # assert
        assert expected == actual

    def test_to_list_one_item(self):
        # arrange
        testinput = " a "
        expected = ["a"]

        # act
        actual = GeneralUtilities.to_list(testinput, ",")

        # assert
        assert expected == actual

    def test_to_list_multiple_items(self):
        # arrange
        testinput = " a , b , c "
        expected = ["a", "b", "c"]

        # act
        actual = GeneralUtilities.to_list(testinput, ",")

        # assert
        assert expected == actual

    def test_get_advanced_errormessage_for_os_error_FileNotFoundError(self):
        # arrange
        filename = "somefile.txt"
        exception = FileNotFoundError()
        exception.filename = filename
        assert isinstance(exception, OSError)
        expected = f"Related path(s): {filename}"

        # act
        actual = GeneralUtilities.get_advanced_errormessage_for_os_error(exception)

        # assert
        assert expected == actual

    def test_get_advanced_errormessage_for_os_error_NotADirectoryError(self):
        # arrange
        filename = "somedirectory"
        exception = NotADirectoryError()
        exception.filename = filename
        assert isinstance(exception, OSError)
        expected = f"Related path(s): {filename}"

        # act
        actual = GeneralUtilities.get_advanced_errormessage_for_os_error(exception)

        # assert
        assert expected == actual

    def test_sc_organize_lines_in_file_test_basic(self) -> None:
        # arrange
        testfile = ScriptCollectionCoreTests.testfileprefix+"test_sc_organize_lines_in_file_test_basic.txt"
        try:
            example_input = ["line1", "line2", "line3"]
            expected_output = ["line1", "line2", "line3"]
            GeneralUtilities.write_lines_to_file(testfile, example_input)

            # act
            ScriptCollectionCore().sc_organize_lines_in_file(testfile, ScriptCollectionCoreTests.encoding, True, True, True, True)
            # arguments: sort ,remove_duplicated_lines, ignore_first_line, remove_empty_lines, ignored_character

            # assert
            assert expected_output == GeneralUtilities.read_lines_from_file(testfile)
        finally:
            os.remove(testfile)

    def test_sc_organize_lines_in_file_test_emptylineandignorefirstline(self) -> None:
        # arrange
        testfile = ScriptCollectionCoreTests.testfileprefix+"test_sc_organize_lines_in_file_test_emptylineandignorefirstline.txt"
        try:
            example_input = ["line1", GeneralUtilities.empty_string, "line3"]
            expected_output = ["line1", "line3"]
            GeneralUtilities.ensure_file_exists(testfile)
            GeneralUtilities.write_lines_to_file(testfile, example_input)

            # act
            ScriptCollectionCore().sc_organize_lines_in_file(testfile, ScriptCollectionCoreTests. encoding, True, True, True, True)
            # arguments: sort ,remove_duplicated_lines, ignore_first_line, remove_empty_lines, ignored_character

            # assert
            assert expected_output == GeneralUtilities.read_lines_from_file(testfile)
        finally:
            os.remove(testfile)

    def test_sc_organize_lines_in_file_test_emptyline(self) -> None:
        # arrange
        testfile = ScriptCollectionCoreTests.testfileprefix+"test_sc_organize_lines_in_file_test_emptyline.txt"
        try:
            example_input = ["line1", GeneralUtilities.empty_string, "line3"]
            expected_output = ["line1", "line3"]
            GeneralUtilities.ensure_file_exists(testfile)
            GeneralUtilities.write_lines_to_file(testfile, example_input)

            # act
            ScriptCollectionCore().sc_organize_lines_in_file(testfile, ScriptCollectionCoreTests.encoding, True, True, False, True, [])
            # arguments: sort ,remove_duplicated_lines, ignore_first_line, remove_empty_lines, ignored_character

            # assert
            assert expected_output == GeneralUtilities. read_lines_from_file(testfile)
        finally:
            os.remove(testfile)

    def test_sc_organize_lines_in_file_with_ignored_character(self) -> None:
        # arrange
        testfile = ScriptCollectionCoreTests.testfileprefix+"test_sc_organize_lines_in_file_test_emptyline.txt"
        try:
            example_input = ["line5", " line4", "line3", "#line2", "# line6", "line7", "line1"]
            expected_output = ["line1", "#line2", "line3", " line4", "line5", "# line6", "line7"]
            GeneralUtilities.write_lines_to_file(testfile, example_input)

            # act
            ScriptCollectionCore().sc_organize_lines_in_file(testfile,  ScriptCollectionCoreTests.encoding, True, True, False, True, ["#", " "])
            # arguments: sort ,remove_duplicated_lines, ignore_first_line, remove_empty_lines, ignored_character

            # assert
            assert expected_output == GeneralUtilities.read_lines_from_file(testfile)
        finally:
            os.remove(testfile)

    def test_simple_program_call_is_mockable(self) -> None:
        # arrange
        sc = ScriptCollectionCore()
        sc.mock_program_calls = True
        sc.register_mock_program_call("p", "a1", "/tmp", 0, "out 1", "err 1", 40)
        sc.register_mock_program_call("p", "a2", "/tmp", 0, "out 2", "err 2", 44)

        # act
        result1 = sc.run_program("p", "a1", "/tmp")
        result2 = sc.run_program("p", "a2", "/tmp")

        # assert
        assert result1 == (0, "out 1", "err 1", 40)
        assert result2 == (0, "out 2", "err 2", 44)
        sc.verify_no_pending_mock_program_calls()

    def test_simple_program_call(self) -> None:
        # arrange
        sc = ScriptCollectionCore()
        dir_path = os.path.dirname(os.path.realpath(__file__))

        # act
        (exit_code, stdout, stderr, _3) = sc.run_program("git", "rev-parse HEAD", dir_path)

        # assert
        assert exit_code == 0
        assert len(stdout) == 40
        assert stderr == GeneralUtilities.empty_string

    def test_file_is_git_ignored_1(self) -> None:

        # arrange
        sc = ScriptCollectionCore()
        repository = str(Path(__file__).parent.parent.parent.absolute())

        # act
        result = sc.file_is_git_ignored(os.path.join("ScriptCollection", "setup.cfg"), repository)

        # assert
        assert result is False

    def test_file_is_git_ignored_2(self) -> None:

        # arrange
        sc = ScriptCollectionCore()
        repository = str(Path(__file__).parent.parent.parent.absolute())

        # act
        result = sc.file_is_git_ignored(os.path.join("ScriptCollection", "ScriptCollection.egg-info", "entry_points.txt"), repository)

        # assert
        assert result is True

    def test_file_is_git_ignored_3(self) -> NoReturn:
        tests_folder = tempfile.gettempdir()+os.path.sep+str(uuid.uuid4())
        GeneralUtilities.ensure_directory_exists(tests_folder)
        sc = ScriptCollectionCore()
        sc.run_program("git", "init", tests_folder)

        ignored_logfolder_name = "logfolder"
        ignored_logfolder = tests_folder+os.path.sep+ignored_logfolder_name
        GeneralUtilities.ensure_directory_exists(ignored_logfolder)

        gitignore_file = tests_folder+os.path.sep+".gitignore"
        GeneralUtilities.ensure_file_exists(gitignore_file)
        GeneralUtilities.write_lines_to_file(gitignore_file, [ignored_logfolder_name+"/**", "!"+ignored_logfolder_name+"/.gitkeep"])

        gitkeep_file = ignored_logfolder+os.path.sep+".gitkeep"
        GeneralUtilities.ensure_file_exists(gitkeep_file)

        log_file = ignored_logfolder+os.path.sep+"logfile.log"
        GeneralUtilities.ensure_file_exists(log_file)

        assert not sc.file_is_git_ignored(".gitignore", tests_folder)
        assert not sc.file_is_git_ignored(".gitkeep", tests_folder)
        assert sc.file_is_git_ignored(ignored_logfolder_name+os.path.sep+"logfile.log", tests_folder)

        GeneralUtilities.ensure_directory_does_not_exist(tests_folder)

    def test_simple_program_call_argsasarray(self) -> None:
        # arrange
        sc = ScriptCollectionCore()
        dir_path = os.path.dirname(os.path.realpath(__file__))

        # act
        (exit_code, _, _2, _3) = sc.run_program_argsasarray("git", ["status"], dir_path)

        # assert
        assert exit_code == 0

    def test_format_html_content_trims_whitespace_in_text(self) -> None:
        # arrange
        sc = ScriptCollectionCore()
        input_content = "<b>  x  </b>"

        # act
        result = sc.format_html_content(input_content)

        # assert
        assert result == "<b>x</b>"

    def test_format_html_content_collapses_multiline_text(self) -> None:
        # arrange
        sc = ScriptCollectionCore()
        input_content = "<b>  \n   x  \n  </b>"

        # act
        result = sc.format_html_content(input_content)

        # assert
        assert result == "<b>x</b>"

    def test_format_html_content_collapses_multiline_text_with_inline_attribute(self) -> None:
        # arrange
        sc = ScriptCollectionCore()
        input_content = '<mat-checkbox formControlName="x">Can receive\n            ONVIF-commands.</mat-checkbox>'

        # act
        result = sc.format_html_content(input_content)

        # assert
        assert result == '<mat-checkbox formControlName="x">Can receive ONVIF-commands.</mat-checkbox>'

    def  test_format_html_content_trims_text_in_nested_elements(self) -> None:
        # arrange
        sc = ScriptCollectionCore()
        input_content = "<div>\n  <p>  hello   world  </p>\n  <span>  \n    test  \n  </span>\n</div>"

        # act
        result = sc.format_html_content(input_content)

        # assert
        assert result=="""<div>
  <p>hello world</p>
  <span>test</span>
</div>"""

    def test_format_html_content_adds_doctype_when_requested(self) -> None:
        # arrange
        sc = ScriptCollectionCore()
        input_content = "<html><body></body></html>"

        # act
        result = sc.format_html_content(input_content, add_html_declaration=True)

        # assert
        assert result.startswith("<!DOCTYPE html>")

    def test_format_html_content_does_not_add_doctype_by_default(self) -> None:
        # arrange
        sc = ScriptCollectionCore()
        input_content = "<html><body></body></html>"

        # act
        result = sc.format_html_content(input_content)

        # assert
        assert "DOCTYPE" not in result

    def test_format_html_content_indents_deeply_nested_elements(self) -> None:
        # arrange
        sc = ScriptCollectionCore()
        input_content = "<div><section><p>  hello  </p></section></div>"
        expected = "<div>\n  <section>\n    <p>hello</p>\n  </section>\n</div>"

        # act
        result = sc.format_html_content(input_content)

        # assert
        assert result == expected


# TODO all testcases should be independent of epew
