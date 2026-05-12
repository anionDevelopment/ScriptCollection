import os
from datetime import datetime, date, timezone, timedelta
import unittest
from ..ScriptCollection.GeneralUtilities import GeneralUtilities


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
