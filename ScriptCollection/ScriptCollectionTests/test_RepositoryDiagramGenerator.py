import json
import os
import tempfile
import unittest
import uuid
from ..ScriptCollection.RepositoryDiagramGenerator import RepositoryDiagramGenerator
from ..ScriptCollection.RepositoryHistoryAnalyzer import CommitterActivityData, CommitterActivityDataPoint

_EMAIL_TOOLTIP_SIGNAL = "pluck(data('committerEmails'), 'Email')[indexof(pluck(data('committerEmails'), 'Committer'), datum.value)]"


class RepositoryDiagramGeneratorTests(unittest.TestCase):

    def __sample_data(self) -> CommitterActivityData:
        return CommitterActivityData(
            committers=["Alice", "Bob"],
            committer_emails={"Alice": "alice@example.com", "Bob": "bob@example.com"},
            data_points=[
                CommitterActivityDataPoint("Alice", "2026-W02", 3),
                CommitterActivityDataPoint("Alice", "2026-W03", 5),
                CommitterActivityDataPoint("Bob", "2026-W02", 2),
            ],
        )

    def __target_file(self) -> str:
        return os.path.join(tempfile.gettempdir(), str(uuid.uuid4()) + ".json")

    def __assert_legend_email_tooltip(self, spec: dict, expected_committer_emails: list) -> None:
        assert spec["datasets"]["committerEmails"] == expected_committer_emails
        legend = spec["encoding"]["color"]["legend"]
        assert legend["encode"]["labels"]["update"]["tooltip"]["signal"] == _EMAIL_TOOLTIP_SIGNAL

    def test_generate_committer_timeline(self) -> None:
        # arrange
        data = self.__sample_data()
        target_file = self.__target_file()
        generator = RepositoryDiagramGenerator()

        # act
        generator.generate_committer_timeline(data, target_file)

        # assert
        with open(target_file, "r", encoding="utf-8") as file_handle:
            spec = json.load(file_handle)
        assert spec["mark"]["type"] == "line"
        assert spec["mark"]["point"] is True
        assert spec["encoding"]["x"]["field"] == "Period"
        assert spec["encoding"]["y"]["field"] == "Commits"
        assert spec["encoding"]["color"]["field"] == "Committer"
        tooltip_fields = [t["field"] for t in spec["encoding"]["tooltip"]]
        assert tooltip_fields == ["Committer", "Period", "Commits"]
        values = spec["data"]["values"]
        assert {"Committer": "Alice", "Period": "2026-W03", "Commits": 5} in values
        self.__assert_legend_email_tooltip(spec, [
            {"Committer": "Alice", "Email": "alice@example.com"},
            {"Committer": "Bob", "Email": "bob@example.com"},
        ])

    def test_generate_commits_per_weekday_chart_has_fixed_weekday_order(self) -> None:
        # arrange
        data = CommitterActivityData(
            committers=["Alice"],
            committer_emails={"Alice": "alice@example.com"},
            data_points=[CommitterActivityDataPoint("Alice", "Monday", 4)],
        )
        target_file = self.__target_file()
        generator = RepositoryDiagramGenerator()

        # act
        generator.generate_commits_per_weekday_chart(data, target_file)

        # assert
        with open(target_file, "r", encoding="utf-8") as file_handle:
            spec = json.load(file_handle)
        assert spec["encoding"]["x"]["field"] == "Weekday"
        assert spec["encoding"]["x"]["sort"] == ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        self.__assert_legend_email_tooltip(spec, [{"Committer": "Alice", "Email": "alice@example.com"}])

    def test_generate_commits_per_hour_chart_has_fixed_hour_order(self) -> None:
        # arrange
        data = CommitterActivityData(
            committers=["Alice"],
            committer_emails={"Alice": "alice@example.com"},
            data_points=[CommitterActivityDataPoint("Alice", "09", 1)],
        )
        target_file = self.__target_file()
        generator = RepositoryDiagramGenerator()

        # act
        generator.generate_commits_per_hour_chart(data, target_file)

        # assert
        with open(target_file, "r", encoding="utf-8") as file_handle:
            spec = json.load(file_handle)
        assert spec["encoding"]["x"]["field"] == "Hour"
        assert spec["encoding"]["x"]["sort"][:3] == ["00", "01", "02"]
        assert len(spec["encoding"]["x"]["sort"]) == 24
        self.__assert_legend_email_tooltip(spec, [{"Committer": "Alice", "Email": "alice@example.com"}])

    def test_generate_committer_pie_chart(self) -> None:
        # arrange
        data = self.__sample_data()  # Alice: 3+5=8 commits, Bob: 2 commits, total 10
        target_file = self.__target_file()
        generator = RepositoryDiagramGenerator()

        # act
        generator.generate_committer_pie_chart(data, target_file)

        # assert
        with open(target_file, "r", encoding="utf-8") as file_handle:
            spec = json.load(file_handle)
        assert spec["mark"]["type"] == "arc"
        assert spec["encoding"]["theta"]["field"] == "Commits"
        values = spec["data"]["values"]
        assert {"Committer": "Alice", "Commits": 8} in values
        assert {"Committer": "Bob", "Commits": 2} in values
        share_field = next(t for t in spec["encoding"]["tooltip"] if t["field"] == "Share")
        assert share_field["format"] == ".1%"
        transform_fields = [list(t.keys())[0] for t in spec["transform"]]
        assert transform_fields == ["joinaggregate", "calculate"]
        self.__assert_legend_email_tooltip(spec, [
            {"Committer": "Alice", "Email": "alice@example.com"},
            {"Committer": "Bob", "Email": "bob@example.com"},
        ])


if __name__ == "__main__":
    unittest.main()
