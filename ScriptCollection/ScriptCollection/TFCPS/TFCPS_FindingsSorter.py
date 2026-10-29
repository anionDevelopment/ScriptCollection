import os
import re
from ..GeneralUtilities import GeneralUtilities


class TFCPS_FindingsSorter:
    """Sorts the rows of the findings-table in the section "## Findings" in "<repository>/Other/Reference/Reference.md".

    The findings-table is specified in the specification "common-projects-structure-findings".
    Only the rows of the table are moved; no row is edited and everything else in the file stays untouched.
    The rows of not completed findings come first, sorted by priority (descending, from "very high" to "low") and then by id (ascending).
    The rows of completed findings (state "fixed" or "accepted") come after that, sorted by id (ascending).
    If the file, the section or the table does not exist then nothing is done."""

    findings_section_heading: str = "## Findings"
    findings_table_columns: list[str] = ["Id", "Priority", "State", "Description", "Impact", "Notes"]
    completed_states: list[str] = ["fixed", "accepted"]
    priorities_in_sort_order: list[str] = ["very high", "high", "mid", "low"]

    @GeneralUtilities.check_arguments
    def sort_findings(self, repository_folder: str) -> None:
        reference_file = os.path.join(repository_folder, "Other", "Reference", "Reference.md")
        if not os.path.isfile(reference_file):
            return
        content = GeneralUtilities.read_text_from_file(reference_file)
        sorted_content = self.sort_findings_in_content(content)
        if sorted_content != content:
            GeneralUtilities.write_text_to_file(reference_file, sorted_content)

    @GeneralUtilities.check_arguments
    def sort_findings_in_content(self, content: str) -> str:
        """Returns the given markdown-content with sorted rows of the findings-table."""
        lines = content.split("\n")
        rows_range = self.__get_rows_range(lines)
        if rows_range is None:
            return content
        (first_row_index, end_index) = rows_range
        rows = lines[first_row_index:end_index]
        uncompleted_rows = [row for row in rows if not self.__is_completed(row)]
        completed_rows = [row for row in rows if self.__is_completed(row)]
        uncompleted_rows.sort(key=lambda row: (self.__get_priority_rank(row), self.__get_id_sort_key(row)))
        completed_rows.sort(key=self.__get_id_sort_key)
        lines[first_row_index:end_index] = uncompleted_rows+completed_rows
        return "\n".join(lines)

    def __get_rows_range(self, lines: list[str]) -> tuple[int, int] | None:
        """Returns the index of the first row and the index after the last row of the findings-table, or None if there is no findings-table."""
        section_start_index = None
        for index, line in enumerate(lines):
            if line.strip() == self.findings_section_heading:
                section_start_index = index
                break
        if section_start_index is None:
            return None
        index = section_start_index+1
        while index < len(lines) and not re.match(r"^#{1,2} ", lines[index]):
            if self.__is_table_line(lines[index]) and self.__get_cells(lines[index]) == self.findings_table_columns:
                first_row_index = index+2  # skip the header-line and the separator-line
                end_index = first_row_index
                while end_index < len(lines) and self.__is_table_line(lines[end_index]):
                    end_index = end_index+1
                return (first_row_index, end_index)
            index = index+1
        return None

    def __is_table_line(self, line: str) -> bool:
        return line.strip().startswith("|")

    def __get_cells(self, line: str) -> list[str]:
        # a "|" which is escaped as "\|" is part of the content of a cell and not a cell-separator
        cells = re.split(r"(?<!\\)\|", line.strip())
        return [cell.strip() for cell in cells[1:-1]]

    def __is_completed(self, row: str) -> bool:
        return self.__get_cells(row)[2] in self.completed_states

    def __get_priority_rank(self, row: str) -> int:
        priority = self.__get_cells(row)[1]
        if priority not in self.priorities_in_sort_order:
            raise ValueError(f"Finding \"{self.__get_cells(row)[0]}\" has the unknown priority \"{priority}\". Allowed priorities: {', '.join(self.priorities_in_sort_order)}")
        return self.priorities_in_sort_order.index(priority)

    def __get_id_sort_key(self, row: str) -> tuple[str, int]:
        # a fixed finding has a struck through id like "~~SEC-2~~"
        finding_id = self.__get_cells(row)[0].replace("~~", "")
        match = re.match(r"^([A-Za-z]+)-(\d+)$", finding_id)
        if match is None:
            raise ValueError(f"Finding-id \"{finding_id}\" does not have the format \"<prefix>-<number>\".")
        return (match.group(1), int(match.group(2)))
