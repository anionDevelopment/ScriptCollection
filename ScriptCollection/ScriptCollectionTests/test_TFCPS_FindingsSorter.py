import os
import tempfile
import unittest
from ..ScriptCollection.GeneralUtilities import GeneralUtilities
from ..ScriptCollection.TFCPS.TFCPS_FindingsSorter import TFCPS_FindingsSorter


HEADER: str = "| Id | Priority | State | Description | Impact | Notes |\n| -- | -------- | ----- | ----------- | ------ | ----- |\n"


class TFCPS_FindingsSorterTests(unittest.TestCase):

    def test_sorts_uncompleted_by_priority_and_id_and_completed_by_id(self) -> None:
        # arrange
        rows = [
            "| ~~SEC-3~~ | very high | fixed | d | i | n |",
            "| SEC-10 | high | open | d | i | n |",
            "| BUG-1 | low | open | d | i | n |",
            "| SEC-2 | high | not verifiable | d | i | n |",
            "| BUG-2 | mid | accepted | d | i | n |",
            "| SEC-1 | very high | open | `a \\| b` | i | n |",
        ]
        content = "# Title\n\n## Findings\n\nText\n\n" + HEADER + "\n".join(rows) + "\n\n## Other\n\n| Id | x |\n"

        # act
        result = TFCPS_FindingsSorter().sort_findings_in_content(content)

        # assert
        expected_rows = [
            "| SEC-1 | very high | open | `a \\| b` | i | n |",
            "| SEC-2 | high | not verifiable | d | i | n |",
            "| SEC-10 | high | open | d | i | n |",
            "| BUG-1 | low | open | d | i | n |",
            "| BUG-2 | mid | accepted | d | i | n |",
            "| ~~SEC-3~~ | very high | fixed | d | i | n |",
        ]
        self.assertEqual("# Title\n\n## Findings\n\nText\n\n" + HEADER + "\n".join(expected_rows) + "\n\n## Other\n\n| Id | x |\n", result)

    def test_content_without_findings_section_is_unchanged(self) -> None:
        # arrange
        content = "# Title\n\n## Other\n\n" + HEADER + "| SEC-2 | low | open | d | i | n |\n| SEC-1 | high | open | d | i | n |\n"

        # act
        result = TFCPS_FindingsSorter().sort_findings_in_content(content)

        # assert
        self.assertEqual(content, result)

    def test_content_without_findings_table_is_unchanged(self) -> None:
        # arrange
        content = "# Title\n\n## Findings\n\nNo findings yet.\n\n## Other\n\n" + HEADER + "| SEC-2 | low | open | d | i | n |\n| SEC-1 | high | open | d | i | n |\n"

        # act
        result = TFCPS_FindingsSorter().sort_findings_in_content(content)

        # assert
        self.assertEqual(content, result)

    def test_unknown_priority_raises_error(self) -> None:
        # arrange
        content = "## Findings\n\n" + HEADER + "| SEC-1 | urgent | open | d | i | n |\n| SEC-2 | low | open | d | i | n |\n"

        # act & assert
        with self.assertRaises(ValueError):
            TFCPS_FindingsSorter().sort_findings_in_content(content)

    def test_sort_findings_without_reference_file_does_nothing(self) -> None:
        # arrange
        with tempfile.TemporaryDirectory() as repository_folder:

            # act
            TFCPS_FindingsSorter().sort_findings(repository_folder)

            # assert
            self.assertFalse(os.path.exists(os.path.join(repository_folder, "Other")))

    def test_sort_findings_writes_sorted_reference_file(self) -> None:
        # arrange
        with tempfile.TemporaryDirectory() as repository_folder:
            reference_folder = os.path.join(repository_folder, "Other", "Reference")
            GeneralUtilities.ensure_directory_exists(reference_folder)
            reference_file = os.path.join(reference_folder, "Reference.md")
            GeneralUtilities.write_text_to_file(reference_file, "## Findings\n\n" + HEADER + "| SEC-2 | low | open | d | i | n |\n| SEC-1 | high | open | d | i | n |\n")

            # act
            TFCPS_FindingsSorter().sort_findings(repository_folder)

            # assert
            self.assertEqual("## Findings\n\n" + HEADER + "| SEC-1 | high | open | d | i | n |\n| SEC-2 | low | open | d | i | n |\n", GeneralUtilities.read_text_from_file(reference_file))


if __name__ == "__main__":
    unittest.main()
