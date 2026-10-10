import os
import json
import tempfile
from pathlib import Path
from datetime import datetime, date, timezone, timedelta
import unittest
from ..ScriptCollection.GeneralUtilities import GeneralUtilities, VersionEcholon, Dependency


class GeneralUtilitiesTests(unittest.TestCase):
    testfileprefix = "testfile_"

    def test_string_to_lines(self) -> None:

        # arrange
        test_string = "a\r\nb\n"
        expected = ["a", "b", GeneralUtilities.empty_string]

        # act
        actual = GeneralUtilities.string_to_lines(test_string)

        # assert
        assert actual == expected

    def test_datetime_to_string_to_datetime(self) -> None:
        # arrange
        expected = datetime(2022, 10, 6, 19, 26, 1)

        # act
        actual = GeneralUtilities.string_to_datetime(GeneralUtilities.datetime_to_string(expected))

        # assert
        assert actual == expected

    def test_datetime_to_string_to_datetime_with_milliseconds(self) -> None:
        # arrange
        input_value = datetime(2022, 10, 6, 19, 26, 1, 123)
        expected = datetime(2022, 10, 6, 19, 26, 1)

        # act
        actual = GeneralUtilities.string_to_datetime(GeneralUtilities.datetime_to_string(input_value))

        # assert
        assert actual == expected

    def test_string_to_datetime_to_string(self) -> None:
        # arrange
        expected = "2022-10-06T19:26:01"

        # act
        actual = GeneralUtilities.datetime_to_string(GeneralUtilities.string_to_datetime(expected))

        # assert
        assert actual == expected

    def test_string_to_datetime_to_string_with_milliseconds(self) -> None:
        # arrange
        inputvalue = "2022-10-06T19:26:01.123"
        expected = "2022-10-06T19:26:01"

        # act
        actual = GeneralUtilities.datetime_to_string(GeneralUtilities.string_to_datetime(inputvalue))

        # assert
        assert actual == expected

    def test_datetime_to_string(self) -> None:
        # arrange
        expected = "2022-10-06T19:26:01"
        test_input = datetime(2022, 10, 6, 19, 26, 1)

        # act
        actual = GeneralUtilities.datetime_to_string(test_input)

        # assert
        assert actual == expected

    def test_string_to_datetime(self) -> None:
        # arrange
        expected = datetime(2022, 10, 6, 19, 26, 1)
        test_input = "2022-10-06T19:26:01"

        # act
        actual = GeneralUtilities.string_to_datetime(test_input)

        # assert
        assert actual == expected

    def test_date_to_string_to_date(self) -> None:
        # arrange
        expected = date(2022, 10, 6)

        # act
        actual = GeneralUtilities.string_to_date(GeneralUtilities.date_to_string(expected))

        # assert
        assert actual == expected

    def test_string_to_date_to_string(self) -> None:
        # arrange
        expected = "2022-10-06"

        # act
        actual = GeneralUtilities.date_to_string(GeneralUtilities.string_to_date(expected))

        # assert
        assert actual == expected

    def test_date_to_string(self) -> None:
        # arrange
        expected = "2022-10-06"
        test_input = date(2022, 10, 6)

        # act
        actual = GeneralUtilities.date_to_string(test_input)

        # assert
        assert actual == expected

    def test_string_to_date(self) -> None:
        # arrange
        expected = date(2022, 10, 6)
        test_input = "2022-10-06"

        # act
        actual = GeneralUtilities.string_to_date(test_input)

        # assert
        assert actual == expected

    def test_string_is_none_or_whitespace(self) -> None:
        assert GeneralUtilities.string_is_none_or_whitespace(None)
        assert GeneralUtilities.string_is_none_or_whitespace(GeneralUtilities.empty_string)
        assert GeneralUtilities.string_is_none_or_whitespace(" ")
        assert GeneralUtilities.string_is_none_or_whitespace("   ")
        assert not GeneralUtilities.string_is_none_or_whitespace("not empty string")

    def test_string_is_none_or_empty(self) -> None:
        assert GeneralUtilities.string_is_none_or_empty(None)
        assert GeneralUtilities.string_is_none_or_empty(GeneralUtilities.empty_string)
        assert not GeneralUtilities.string_is_none_or_empty(" ")
        assert not GeneralUtilities.string_is_none_or_empty("   ")
        assert not GeneralUtilities.string_is_none_or_empty("not empty string")

    def test_write_read_file(self) -> None:
        # arrange
        testfile = GeneralUtilitiesTests.testfileprefix+"test_write_read_file.txt"
        try:
            expected = ["a", "bö", "testß\\testend"]

            # act
            GeneralUtilities.write_lines_to_file(testfile, expected)
            actual = GeneralUtilities.read_lines_from_file(testfile)

            # assert
            assert expected == actual
        finally:
            os.remove(testfile)

    def test_get_next_square_number_0(self) -> None:
        assert GeneralUtilities.get_next_square_number(0) == 1

    def test_get_next_square_number_1(self) -> None:
        assert GeneralUtilities.get_next_square_number(1) == 1

    def test_get_next_square_number_2(self) -> None:
        assert GeneralUtilities.get_next_square_number(2) == 4

    def test_get_next_square_number_3(self) -> None:
        assert GeneralUtilities.get_next_square_number(3) == 4

    def test_get_next_square_number_15(self) -> None:
        assert GeneralUtilities.get_next_square_number(15) == 16

    def test_get_next_square_number_16(self) -> None:
        assert GeneralUtilities.get_next_square_number(16) == 16

    def test_get_next_square_number_17(self) -> None:
        assert GeneralUtilities.get_next_square_number(17) == 25

    def test_internal_ends_with_newline_character_empty_string(self) -> None:
        # pylint: disable=W0212
        assert GeneralUtilities.ends_with_newline_character(GeneralUtilities.empty_string.encode()) is False

    def test_internal_ends_with_newline_character_nonempty_string_true(self) -> None:
        # pylint: disable=W0212
        assert GeneralUtilities.ends_with_newline_character("a\n".encode()) is True

    def test_internal_ends_with_newline_character_nonempty_string_false(self) -> None:
        # pylint: disable=W0212
        assert GeneralUtilities.ends_with_newline_character("ab".encode()) is False

    def test_to_pascal_case(self) -> None:
        assert GeneralUtilities.to_pascal_case("ab: Cd-ef_ghIj") == "AbCdEfGhij"

    def test_to_snake_case(self) -> None:
        assert GeneralUtilities.to_snake_case("ab: Cd-ef_ghIj") == "ab_cd_ef_ghij"

    def test_to_camel_case(self) -> None:
        assert GeneralUtilities.to_camel_case("ab: Cd-ef_ghIj") == "abCdEfGhij"

    def test_to_kebab_case(self) -> None:
        assert GeneralUtilities.to_kebab_case("ab: Cd-ef_ghIj") == "ab-cd-ef-ghij"

    def test_find_between(self) -> None:
        assert GeneralUtilities.find_between("a(bc)de", "(", ")") == "bc"

    def test_int_to_string(self) -> None:
        assert GeneralUtilities.int_to_string(2, 2, 5) == "02.00000"

    def test_float_to_string(self) -> None:
        assert GeneralUtilities.float_to_string(2.39, 2, 5) == "02.39000"

    @unittest.skipUnless(GeneralUtilities.current_system_is_windows(), "Windows only")
    def test_normalize_path_collapses_repeated_separators_but_preserves_unc_prefix_windows(self) -> None:
        # arrange
        test_input = "//server//path/"
        expected = "\\\\server\\path\\"

        # act
        actual = GeneralUtilities.normalize_path(test_input)

        # assert
        assert actual == expected

    @unittest.skipUnless(not GeneralUtilities.current_system_is_windows(), "Linux only")
    def test_normalize_path_collapses_repeated_separators_but_preserves_unc_prefix_linux(self) -> None:
        # arrange
        test_input = "\\\\server\\\\path\\"
        expected = "//server/path/"

        # act
        actual = GeneralUtilities.normalize_path(test_input)

        # assert
        assert actual == expected

    def test_datetime_to_string_for_logfile_name_with_milliseconds(self) -> None:
        # arrange
        input_value = datetime(2025, 9, 2, 20, 30, 5, 123, tzinfo=timezone(timedelta(hours=2)))
        expected = "2025-09-02T20-30-05.000123+02-00"

        # act
        actual = GeneralUtilities.datetime_to_string_for_logfile_name(input_value, True)

        # assert
        assert actual == expected

    def test_datetime_to_string_for_logfile_name_without_milliseconds(self) -> None:
        # arrange
        input_value = datetime(2025, 9, 2, 20, 30, 5, 123, tzinfo=timezone(timedelta(hours=2)))
        expected = "2025-09-02T20-30-05+02-00"

        # act
        actual = GeneralUtilities.datetime_to_string_for_logfile_name(input_value, False)

        # assert
        assert actual == expected

    def test_datetime_to_string_for_logfile_entry_with_milliseconds(self) -> None:
        # arrange
        input_value = datetime(2025, 9, 2, 20, 30, 5, 123, tzinfo=timezone(timedelta(hours=2)))
        expected = "2025-09-02T20:30:05.000123+02:00"

        # act
        actual = GeneralUtilities.datetime_to_string_for_logfile_entry(input_value, True)

        # assert
        assert actual == expected

    def test_datetime_to_string_for_logfile_entry_without_milliseconds(self) -> None:
        # arrange
        input_value = datetime(2025, 9, 2, 20, 30, 5, 123, tzinfo=timezone(timedelta(hours=2)))
        expected = "2025-09-02T20:30:05+02:00"

        # act
        actual = GeneralUtilities.datetime_to_string_for_logfile_entry(input_value, False)

        # assert
        assert actual == expected

    def test_datetime_to_string_for_readable_entry_with_milliseconds(self) -> None:
        # arrange
        input_value = datetime(2025, 9, 2, 20, 30, 5, 123, tzinfo=timezone(timedelta(hours=2)))
        expected = "2025-09-02 20:30:05.000123 +02:00"

        # act
        actual = GeneralUtilities.datetime_to_string_for_readable_entry(input_value, True)

        # assert
        assert actual == expected

    def test_datetime_to_string_for_readable_entry_without_milliseconds(self) -> None:
        # arrange
        input_value = datetime(2025, 9, 2, 20, 30, 5, 123, tzinfo=timezone(timedelta(hours=2)))
        expected = "2025-09-02 20:30:05 +02:00"

        # act
        actual = GeneralUtilities.datetime_to_string_for_readable_entry(input_value, False)

        # assert
        assert actual == expected

    def test_is_ignored_by_glob_pattern(self) -> None:
        assert True==GeneralUtilities.is_ignored_by_glob_pattern("/folder/src", "/folder/src/a/b/c.txt", ["**/b/**"])
        assert False==GeneralUtilities.is_ignored_by_glob_pattern("/folder/src", "/folder/src/a/b/c.txt", ["**/x/**"])

    def get_latest_version(self)->None:
        assert "3.1.0"==GeneralUtilities.get_latest_version(["2.3.4","3.1.0","16.5"])

    def test_replace_xmltag_in_file(self) -> None:
        # arrange
        testfile = GeneralUtilitiesTests.testfileprefix+"test_replace_xmltag_in_file.xml"
        try:
            GeneralUtilities.write_lines_to_file(testfile, ["<Version>1.0.0</Version>"])

            # act
            GeneralUtilities.replace_xmltag_in_file(testfile, "Version", "2.0.0")
            actual = GeneralUtilities.read_lines_from_file(testfile)

            # assert
            assert actual == ["<Version>2.0.0</Version>"]
        finally:
            os.remove(testfile)

    def test_retry_action_if_retries_a_retryable_exception_until_the_action_succeeds(self) -> None:
        # arrange
        amount_of_executions: list[int] = []

        def action_which_fails_in_the_first_two_attempts() -> str:
            amount_of_executions.append(1)
            if len(amount_of_executions) < 3:
                raise ValueError("retryable")
            return "result"

        # act
        actual = GeneralUtilities.retry_action_if(action_which_fails_in_the_first_two_attempts, lambda exception: str(exception) == "retryable", 5, None, 0)

        # assert
        assert actual == "result"
        assert len(amount_of_executions) == 3

    def test_retry_action_if_does_not_retry_an_exception_which_is_not_retryable(self) -> None:
        # arrange
        amount_of_executions: list[int] = []

        def action_which_always_fails() -> None:
            amount_of_executions.append(1)
            raise ValueError("not-retryable")

        # act & assert
        with self.assertRaises(ValueError):
            GeneralUtilities.retry_action_if(action_which_always_fails, lambda exception: str(exception) == "retryable", 5, None, 0)
        assert len(amount_of_executions) == 1

    def test_get_version_parts_returns_the_numeric_parts_of_a_valid_version(self) -> None:
        # arrange
        version = "10.20.300"

        # act
        actual = GeneralUtilities.get_version_parts(version)

        # assert
        assert actual == (10, 20, 300)

    def test_get_version_parts_rejects_a_version_with_only_two_parts(self) -> None:
        # arrange
        version = "1.2"

        # act & assert
        with self.assertRaises(ValueError):
            GeneralUtilities.get_version_parts(version)

    def test_get_version_parts_rejects_a_version_with_four_parts(self) -> None:
        # arrange
        version = "1.2.3.4"

        # act & assert
        with self.assertRaises(ValueError):
            GeneralUtilities.get_version_parts(version)

    def test_get_version_parts_rejects_a_version_with_a_prefix(self) -> None:
        # arrange
        version = "v1.2.3"

        # act & assert
        with self.assertRaises(ValueError):
            GeneralUtilities.get_version_parts(version)

    def test_get_major_minor_and_patch_part_of_version(self) -> None:
        # arrange
        version = "4.5.6"

        # act
        actual = (GeneralUtilities.get_major_part_of_version(version), GeneralUtilities.get_minor_part_of_version(version), GeneralUtilities.get_patch_part_of_version(version))

        # assert
        assert actual == (4, 5, 6)

    def test_get_latest_version_compares_versions_numerically_and_not_lexicographically(self) -> None:
        # arrange
        versions = ["1.9.0", "1.10.0", "1.2.0"]

        # act
        actual = GeneralUtilities.get_latest_version(versions)

        # assert
        assert actual == "1.10.0"

    def test_get_latest_version_rejects_an_empty_list(self) -> None:
        # arrange
        versions = []

        # act & assert
        with self.assertRaises(ValueError):
            GeneralUtilities.get_latest_version(versions)

    def test_choose_version_latest_patch_stays_in_the_current_minor_version(self) -> None:
        # arrange
        available_versions = ["1.1.2", "1.1.9", "1.10.5", "1.2.0", "2.0.0"]

        # act
        actual = GeneralUtilities.choose_version(available_versions, "1.1.0", VersionEcholon.LatestPatch)

        # assert
        # "1.10.5" shares the textual prefix "1.1" but belongs to another minor version, so it must not be chosen.
        assert actual == "1.1.9"

    def test_choose_version_latest_patch_or_latest_minor_stays_in_the_current_major_version(self) -> None:
        # arrange
        available_versions = ["1.1.2", "1.10.5", "2.0.0", "10.0.0"]

        # act
        actual = GeneralUtilities.choose_version(available_versions, "1.1.0", VersionEcholon.LatestPatchOrLatestMinor)

        # assert
        assert actual == "1.10.5"

    def test_choose_version_latest_version_returns_the_highest_available_version(self) -> None:
        # arrange
        available_versions = ["1.1.2", "10.0.0", "2.0.0"]

        # act
        actual = GeneralUtilities.choose_version(available_versions, "1.1.0", VersionEcholon.LatestVersion)

        # assert
        assert actual == "10.0.0"

    def test_choose_version_no_update_returns_the_current_version(self) -> None:
        # arrange
        available_versions = ["1.1.2", "10.0.0"]

        # act
        actual = GeneralUtilities.choose_version(available_versions, "1.1.0", VersionEcholon.NoUpdate)

        # assert
        assert actual == "1.1.0"

    def test_string_to_boolean_accepts_true_values_case_insensitive_and_with_surrounding_whitespace(self) -> None:
        # arrange
        values = ["yes", "Y", " true ", "T", "1"]

        # act
        actual = [GeneralUtilities.string_to_boolean(value) for value in values]

        # assert
        assert actual == [True, True, True, True, True]

    def test_string_to_boolean_accepts_false_values_case_insensitive_and_with_surrounding_whitespace(self) -> None:
        # arrange
        values = ["no", "N", " false ", "F", "0"]

        # act
        actual = [GeneralUtilities.string_to_boolean(value) for value in values]

        # assert
        assert actual == [False, False, False, False, False]

    def test_string_to_boolean_rejects_an_unknown_value(self) -> None:
        # arrange
        value = "maybe"

        # act & assert
        with self.assertRaises(ValueError):
            GeneralUtilities.string_to_boolean(value)

    def test_to_list_returns_empty_list_for_none(self) -> None:
        # act
        actual = GeneralUtilities.to_list(None)

        # assert
        assert len(actual) == 0, actual

    def test_to_list_returns_empty_list_for_whitespace(self) -> None:
        # act
        actual = GeneralUtilities.to_list("   ")

        # assert
        assert len(actual) == 0, actual

    def test_to_list_returns_one_item_when_the_separator_is_not_contained(self) -> None:
        # act
        actual = GeneralUtilities.to_list(" a ")

        # assert
        assert actual == ["a"]

    def test_to_list_splits_by_custom_separator_and_trims_the_items(self) -> None:
        # act
        actual = GeneralUtilities.to_list("a ; b;c", ";")

        # assert
        assert actual == ["a", "b", "c"]

    def test_strip_new_line_character_removes_mixed_line_breaks_at_both_ends_but_keeps_inner_ones(self) -> None:
        # arrange
        value = "\r\n\r\na\nb\n\r"

        # act
        actual = GeneralUtilities.strip_new_line_character(value)

        # assert
        assert actual == "a\nb"

    def test_write_lines_to_file_and_read_lines_from_file_roundtrip(self) -> None:
        # arrange
        lines = ["first", "", "third with spaces "]
        with tempfile.TemporaryDirectory() as folder:
            file = os.path.join(folder, "file.txt")
            GeneralUtilities.write_lines_to_file(file, lines)

            # act
            actual = GeneralUtilities.read_lines_from_file(file)

        # assert
        assert actual == lines

    def test_read_lines_from_file_returns_empty_list_for_an_empty_file(self) -> None:
        # arrange
        with tempfile.TemporaryDirectory() as folder:
            file = os.path.join(folder, "file.txt")
            GeneralUtilities.write_text_to_file(file, GeneralUtilities.empty_string)

            # act
            actual = GeneralUtilities.read_lines_from_file(file)

        # assert
        assert len(actual) == 0, actual

    def test_read_lines_from_file_removes_carriage_returns_of_crlf_line_endings(self) -> None:
        # arrange
        with tempfile.TemporaryDirectory() as folder:
            file = os.path.join(folder, "file.txt")
            GeneralUtilities.write_text_to_file(file, "a\r\nb")

            # act
            actual = GeneralUtilities.read_lines_from_file(file)

        # assert
        assert actual == ["a", "b"]

    def test_read_text_from_file_rejects_a_file_which_does_not_exist(self) -> None:
        # arrange
        with tempfile.TemporaryDirectory() as folder:
            file = os.path.join(folder, "missing.txt")

            # act & assert
            with self.assertRaises(ValueError):
                GeneralUtilities.read_text_from_file(file)

    def test_ensure_path_is_not_quoted_removes_double_quotes(self) -> None:
        # act
        actual = GeneralUtilities.ensure_path_is_not_quoted('"C:/some folder/file.txt"')

        # assert
        assert actual == "C:/some folder/file.txt"

    def test_ensure_path_is_not_quoted_removes_single_quotes(self) -> None:
        # act
        actual = GeneralUtilities.ensure_path_is_not_quoted("'/some folder/file.txt'")

        # assert
        assert actual == "/some folder/file.txt"

    def test_ensure_path_is_not_quoted_keeps_a_path_with_mismatching_quotes_unchanged(self) -> None:
        # arrange
        path = "\"/some folder/file.txt'"

        # act
        actual = GeneralUtilities.ensure_path_is_not_quoted(path)

        # assert
        assert actual == path

    def test_resolve_relative_path_resolves_parent_folder_references_against_the_base_path(self) -> None:
        # arrange
        with tempfile.TemporaryDirectory() as base_folder:
            expected = str(Path(os.path.join(base_folder, "c")).resolve())

            # act
            actual = GeneralUtilities.resolve_relative_path(os.path.join("a", "..", "b", "..", "c"), base_folder)

        # assert
        assert actual == expected

    def test_resolve_relative_path_returns_an_absolute_path_unchanged(self) -> None:
        # arrange
        with tempfile.TemporaryDirectory() as folder:
            absolute_path = os.path.join(folder, "x")

            # act
            actual = GeneralUtilities.resolve_relative_path(absolute_path, os.path.join(folder, "other"))

        # assert
        assert actual == absolute_path

    def test_replace_variable_in_string_replaces_every_occurrence(self) -> None:
        # act
        actual = GeneralUtilities.replace_variable_in_string("a __[name]__ b __[name]__", "name", "value")

        # assert
        assert actual == "a value b value"

    def test_replace_variable_in_string_rejects_a_variable_name_containing_the_control_sequence(self) -> None:
        # act & assert
        with self.assertRaises(ValueError):
            GeneralUtilities.replace_variable_in_string("a __[x__y]__ b", "x__y", "value")

    def test_replace_variable_replaces_prefix_variable_and_suffix_including_whitespace(self) -> None:
        # act
        actual = GeneralUtilities.replace_variable("${{", "version", "}}", "1.2.3", "v=${{ __version__ }};")

        # assert
        assert actual == "v=1.2.3;"

    def test_replace_variable_throws_exception_when_the_variable_is_not_surrounded_by_the_expected_prefix(self) -> None:
        # act & assert
        with self.assertRaises(ValueError):
            GeneralUtilities.replace_variable("${{", "version", "}}", "1.2.3", "v=__version__;")

    def test_replace_variable_rejects_a_variable_name_containing_the_control_sequence(self) -> None:
        # act & assert
        with self.assertRaises(ValueError):
            GeneralUtilities.replace_variable("", "a__b", "", "1", "__a__b__")

    def test_replace_underscores_in_text_resolves_a_value_which_contains_another_placeholder(self) -> None:
        # arrange
        replacements = {"outer": "<__inner__>", "inner": "value"}

        # act
        actual = GeneralUtilities.replace_underscores_in_text("x __outer__ y", replacements)

        # assert
        assert actual == "x <value> y"

    def test_escape_json_string_value_escapes_quotes_backslashes_and_line_breaks(self) -> None:
        # arrange
        value = 'a"b\\c\nd'

        # act
        actual = GeneralUtilities.escape_json_string_value(value)

        # assert
        assert actual == 'a\\"b\\\\c\\nd'
        assert json.loads(f'"{actual}"') == value

    def test_escape_json_property_value_removes_characters_which_are_not_allowed(self) -> None:
        # act
        actual = GeneralUtilities.escape_json_property_value("my-property name!")

        # assert
        assert actual == "mypropertyname"

    def test_escape_json_property_value_rejects_a_value_starting_with_a_digit(self) -> None:
        # act & assert
        with self.assertRaises(ValueError):
            GeneralUtilities.escape_json_property_value("1abc")

    def test_escape_json_property_value_rejects_a_value_without_any_allowed_character(self) -> None:
        # act & assert
        with self.assertRaises(ValueError):
            GeneralUtilities.escape_json_property_value("\"; --")

    def test_platform_short_str_roundtrip_for_all_platforms(self) -> None:
        # arrange
        platforms = GeneralUtilities.get_all_platforms()

        # act
        actual = [GeneralUtilities.platform_from_short_str(GeneralUtilities.platform_to_short_str(p)) for p in platforms]

        # assert
        assert actual == platforms

    def test_platform_dash_str_roundtrip_for_all_platforms(self) -> None:
        # arrange
        platforms = GeneralUtilities.get_all_platforms()

        # act
        actual = [GeneralUtilities.platform_from_dash_str(GeneralUtilities.platform_to_dash_str(p)) for p in platforms]

        # assert
        assert actual == platforms

    def test_platform_from_short_str_rejects_an_unknown_platform(self) -> None:
        # act & assert
        with self.assertRaises(ValueError):
            GeneralUtilities.platform_from_short_str("win-arm64")

    def test_platform_from_dash_str_rejects_an_unknown_platform(self) -> None:
        # act & assert
        with self.assertRaises(ValueError):
            GeneralUtilities.platform_from_dash_str("windows-x64")

    def test_internal_extract_log_file_number_returns_the_number_of_a_rotated_log_file(self) -> None:
        # act
        actual = GeneralUtilities._internal_extract_log_file_number("Log.archive.12.log")

        # assert
        assert actual == 12

    def test_internal_extract_log_file_number_rejects_a_filename_which_is_no_rotated_log_file(self) -> None:
        # act & assert
        with self.assertRaises(ValueError):
            GeneralUtilities._internal_extract_log_file_number("Log.archive.12.log.bak")

    def test_get_only_item_from_list_returns_the_only_item(self) -> None:
        # act
        actual = GeneralUtilities.get_only_item_from_list(["x"])

        # assert
        assert actual == "x"

    def test_get_only_item_from_list_rejects_an_empty_list(self) -> None:
        # act & assert
        with self.assertRaises(ValueError):
            GeneralUtilities.get_only_item_from_list([])

    def test_get_only_item_from_list_rejects_a_list_with_two_items(self) -> None:
        # act & assert
        with self.assertRaises(ValueError):
            GeneralUtilities.get_only_item_from_list(["x", "y"])

    def test_remove_duplicates_keeps_the_order_of_the_first_occurrences(self) -> None:
        # act
        actual = GeneralUtilities.remove_duplicates(["b", "a", "b", "c", "a"])

        # assert
        assert actual == ["b", "a", "c"]

    def test_args_array_surround_with_quotes_if_required_quotes_only_unquoted_arguments_with_whitespace(self) -> None:
        # act
        actual = GeneralUtilities.args_array_surround_with_quotes_if_required(["a", "b c", '"d e"'])

        # assert
        assert actual == ["a", '"b c"', '"d e"']

    def test_arguments_to_array_returns_empty_list_for_none_and_whitespace(self) -> None:
        # act
        actual = (GeneralUtilities.arguments_to_array(None), GeneralUtilities.arguments_to_array("  "))

        # assert
        assert actual == ([], [])

    def test_arguments_to_array_splits_by_space(self) -> None:
        # act
        actual = GeneralUtilities.arguments_to_array("build --configuration Release")

        # assert
        assert actual == ["build", "--configuration", "Release"]

    def test_read_csv_file_ignores_comments_and_empty_lines_and_trims_values(self) -> None:
        # arrange
        with tempfile.TemporaryDirectory() as folder:
            file = os.path.join(folder, "file.csv")
            GeneralUtilities.write_lines_to_file(file, ["# comment", " a ; b ", "", "c;d"])

            # act
            actual = GeneralUtilities.read_csv_file(file)

        # assert
        assert actual == [["a", "b"], ["c", "d"]]

    def test_read_csv_file_ignores_the_first_line_when_requested(self) -> None:
        # arrange
        with tempfile.TemporaryDirectory() as folder:
            file = os.path.join(folder, "file.csv")
            GeneralUtilities.write_lines_to_file(file, ["header1;header2", "a;b"])

            # act
            actual = GeneralUtilities.read_csv_file(file, ignore_first_line=True)

        # assert
        assert actual == [["a", "b"]]

    def test_read_csv_file_removes_surrounding_quotes_and_unescapes_doubled_quotes(self) -> None:
        # arrange
        with tempfile.TemporaryDirectory() as folder:
            file = os.path.join(folder, "file.csv")
            GeneralUtilities.write_lines_to_file(file, ['"a ""quoted"" value";"b"'])

            # act
            actual = GeneralUtilities.read_csv_file(file, values_are_surrounded_by_quotes=True)

        # assert
        assert actual == [['a "quoted" value', "b"]]

    def test_is_ignored_by_glob_pattern_returns_false_when_no_patterns_are_given(self) -> None:
        # act
        actual = GeneralUtilities.is_ignored_by_glob_pattern("/folder/src", "/folder/src/a/b/c.txt", None)

        # assert
        assert actual is False

    def test_is_ignored_by_glob_pattern_rejects_a_path_outside_of_the_source_directory(self) -> None:
        # act & assert
        with self.assertRaises(ValueError):
            GeneralUtilities.is_ignored_by_glob_pattern("/folder/src", "/other/a.txt", ["**"])

    def test_float_to_string_pads_leading_and_trailing_zeros(self) -> None:
        # act
        actual = GeneralUtilities.float_to_string(1.5, 3, 2)

        # assert
        assert actual == "001.50"

    def test_generate_password_uses_default_length_and_alphanumeric_alphabet(self) -> None:
        # arrange
        allowed_characters = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")

        # act
        actual = GeneralUtilities.generate_password()

        # assert
        assert len(actual) == 16
        assert set(actual) <= allowed_characters

    def test_generate_password_uses_only_characters_of_the_given_alphabet(self) -> None:
        # act
        actual = GeneralUtilities.generate_password(64, "ab")

        # assert
        assert len(actual) == 64
        assert set(actual) <= {"a", "b"}

    def test_generate_password_with_length_zero_returns_empty_string(self) -> None:
        # act
        actual = GeneralUtilities.generate_password(0)

        # assert
        assert actual == GeneralUtilities.empty_string

    def test_generate_password_does_not_return_the_same_password_twice(self) -> None:
        # act
        first = GeneralUtilities.generate_password()
        second = GeneralUtilities.generate_password()

        # assert
        assert first != second

    def test_filter_versions_by_prefix_keeps_only_versions_which_start_with_the_prefix(self) -> None:
        # arrange
        # "1.10.5" shares the textual prefix "1.1" but not "1.1.", so it must not be kept for prefix "1.1.".
        versions = ["1.1.2", "1.1.9", "1.10.5", "1.2.0", "2.0.0"]

        # act
        actual = GeneralUtilities.filter_versions_by_prefix(versions, "1.1.")

        # assert
        assert actual == ["1.1.2", "1.1.9"]

    def test_filter_versions_by_prefix_returns_an_empty_list_when_nothing_matches(self) -> None:
        # arrange
        versions = ["1.1.2", "2.0.0"]

        # act
        actual = GeneralUtilities.filter_versions_by_prefix(versions, "3.")

        # assert
        assert actual == []

    def test_filter_versions_by_prefix_returns_all_versions_for_an_empty_prefix(self) -> None:
        # arrange
        versions = ["1.1.2", "2.0.0"]

        # act
        actual = GeneralUtilities.filter_versions_by_prefix(versions, "")

        # assert
        assert actual == versions

    def test_merge_dependency_lists_groups_versions_per_dependency_and_deduplicates_them(self) -> None:
        # arrange
        first_list = [Dependency("a", "1.0.0"), Dependency("b", "2.0.0")]
        second_list = [Dependency("a", "1.1.0"), Dependency("a", "1.0.0")]

        # act
        actual = GeneralUtilities.merge_dependency_lists([first_list, second_list])

        # assert
        # "a" occurs three times (once with a duplicated version), so the set must collapse the duplicate.
        assert actual == {"a": {"1.0.0", "1.1.0"}, "b": {"2.0.0"}}

    def test_merge_dependency_lists_returns_an_empty_dict_for_no_lists(self) -> None:
        # act
        actual = GeneralUtilities.merge_dependency_lists([])

        # assert
        assert len(actual) == 0, actual

    def test_contains_line_matches_at_the_beginning_of_a_line(self) -> None:
        # arrange
        lines = ["hello world", "foo bar"]

        # act
        actual = GeneralUtilities.contains_line(lines, "hello")

        # assert
        assert actual is True

    def test_contains_line_does_not_match_in_the_middle_of_a_line_because_the_match_is_anchored_at_the_start(self) -> None:
        # arrange
        # re.match anchors at the start of the string, so "world" does not match "hello world".
        lines = ["hello world"]

        # act
        actual = GeneralUtilities.contains_line(lines, "world")

        # assert
        assert actual is False

    def test_contains_line_returns_false_for_an_empty_line_list(self) -> None:
        # act
        actual = GeneralUtilities.contains_line([], "anything")

        # assert
        assert actual is False

    def test_string_has_content_distinguishes_real_content_from_none_and_whitespace(self) -> None:
        # act & assert
        assert GeneralUtilities.string_has_content(None) is False
        assert GeneralUtilities.string_has_content("") is False
        assert GeneralUtilities.string_has_content("   ") is False
        assert GeneralUtilities.string_has_content("x") is True
        assert GeneralUtilities.string_has_content("  x  ") is True

    def test_str_none_safe_converts_none_to_an_empty_string_and_otherwise_uses_str(self) -> None:
        # act & assert
        assert GeneralUtilities.str_none_safe(None) == ""
        assert GeneralUtilities.str_none_safe(123) == "123"
        assert GeneralUtilities.str_none_safe("already a string") == "already a string"

    def test_trim_newlines_removes_only_leading_and_trailing_newlines(self) -> None:
        # arrange
        value = "\n\nabc\n\n"

        # act
        actual = GeneralUtilities.trim_newlines(value)

        # assert
        assert actual == "abc"

    def test_trim_newlines_keeps_internal_newlines_and_surrounding_spaces(self) -> None:
        # arrange
        # strip("\n") removes newline-characters only, so spaces and internal newlines must survive.
        value = " a\nb "

        # act
        actual = GeneralUtilities.trim_newlines(value)

        # assert
        assert actual == " a\nb "

    def test_bytes_to_string_decodes_utf8_and_ignores_invalid_bytes(self) -> None:
        # act & assert
        assert GeneralUtilities.bytes_to_string(b"abc") == "abc"
        # 0xff is not a valid utf-8 byte on its own and is dropped because the decoding uses errors="ignore".
        assert GeneralUtilities.bytes_to_string(b"a\xffb") == "ab"

    def test_string_to_bytes_encodes_utf8_and_ignores_characters_the_encoding_can_not_represent(self) -> None:
        # act & assert
        assert GeneralUtilities.string_to_bytes("abc") == b"abc"
        # "é" can not be represented in ascii and is dropped because the encoding uses errors="ignore".
        assert GeneralUtilities.string_to_bytes("aé", "ascii") == b"a"

    def test_string_to_bytes_and_bytes_to_string_roundtrip_for_non_ascii_utf8(self) -> None:
        # arrange
        value = "héllo wörld"

        # act
        actual = GeneralUtilities.bytes_to_string(GeneralUtilities.string_to_bytes(value))

        # assert
        assert actual == value

    def test_timedelta_to_simple_string_formats_as_hours_minutes_seconds(self) -> None:
        # act & assert
        assert GeneralUtilities.timedelta_to_simple_string(timedelta(0)) == "00:00:00"
        assert GeneralUtilities.timedelta_to_simple_string(timedelta(hours=1, minutes=2, seconds=3)) == "01:02:03"

    def test_timedelta_to_simple_string_does_not_represent_whole_days(self) -> None:
        # arrange
        # The implementation formats an offset from a fixed date with "%H:%M:%S", so the day-part is not shown.
        delta = timedelta(days=1, hours=1)

        # act
        actual = GeneralUtilities.timedelta_to_simple_string(delta)

        # assert
        assert actual == "01:00:00"

    def test_read_nonempty_lines_from_file_skips_empty_and_whitespace_only_lines(self) -> None:
        # arrange
        with tempfile.TemporaryDirectory() as folder:
            file = os.path.join(folder, "file.txt")
            GeneralUtilities.write_text_to_file(file, "a\n\n   \nb\n")

            # act
            actual = GeneralUtilities.read_nonempty_lines_from_file(file)

        # assert
        assert actual == ["a", "b"]

    def test_file_is_empty_distinguishes_an_empty_file_from_a_non_empty_one(self) -> None:
        # arrange
        with tempfile.TemporaryDirectory() as folder:
            empty_file = os.path.join(folder, "empty.txt")
            non_empty_file = os.path.join(folder, "nonempty.txt")
            GeneralUtilities.write_text_to_file(empty_file, GeneralUtilities.empty_string)
            GeneralUtilities.write_text_to_file(non_empty_file, "content")

            # act
            empty_result = GeneralUtilities.file_is_empty(empty_file)
            non_empty_result = GeneralUtilities.file_is_empty(non_empty_file)

        # assert
        assert empty_result is True
        assert non_empty_result is False

    def test_folder_is_empty_is_true_only_when_there_is_neither_a_file_nor_a_subfolder(self) -> None:
        # arrange
        with tempfile.TemporaryDirectory() as folder:
            empty_folder = os.path.join(folder, "empty")
            folder_with_file = os.path.join(folder, "with_file")
            folder_with_subfolder = os.path.join(folder, "with_subfolder")
            GeneralUtilities.ensure_directory_exists(empty_folder)
            GeneralUtilities.ensure_directory_exists(folder_with_file)
            GeneralUtilities.ensure_directory_exists(folder_with_subfolder)
            GeneralUtilities.write_text_to_file(os.path.join(folder_with_file, "file.txt"), "x")
            GeneralUtilities.ensure_directory_exists(os.path.join(folder_with_subfolder, "sub"))

            # act
            empty_result = GeneralUtilities.folder_is_empty(empty_folder)
            file_result = GeneralUtilities.folder_is_empty(folder_with_file)
            subfolder_result = GeneralUtilities.folder_is_empty(folder_with_subfolder)

        # assert
        assert empty_result is True
        assert file_result is False
        assert subfolder_result is False
