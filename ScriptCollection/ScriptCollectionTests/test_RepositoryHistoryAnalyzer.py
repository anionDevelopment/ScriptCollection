import os
import tempfile
import unittest
import uuid
from ..ScriptCollection.GeneralUtilities import GeneralUtilities
from ..ScriptCollection.ScriptCollectionCore import ScriptCollectionCore
from ..ScriptCollection.RepositoryHistoryAnalyzer import RepositoryHistoryAnalyzer, GitHistoryScale


class RepositoryHistoryAnalyzerTests(unittest.TestCase):

    def __create_test_repository(self) -> str:
        repository = os.path.join(tempfile.gettempdir(), str(uuid.uuid4()))
        GeneralUtilities.ensure_directory_exists(repository)
        sc = ScriptCollectionCore()
        sc.run_program_argsasarray("git", ["init"], repository)

        def commit(name: str, email: str, date: str, message: str) -> None:
            env_vars = {
                "GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email, "GIT_AUTHOR_DATE": date,
                "GIT_COMMITTER_NAME": name, "GIT_COMMITTER_EMAIL": email, "GIT_COMMITTER_DATE": date,
            }
            sc.run_program_argsasarray("git", ["commit", "--allow-empty", "-m", message], repository, env_vars=env_vars)

        # Alice: 2 commits on a Monday ("2026-01-05", ISO-week 2026-W02) and a Monday one ISO-week later
        # ("2026-01-12", 2026-W03), both at 10:xx (hour "10").
        commit("Alice", "alice@example.com", "2026-01-05T10:15:00+00:00", "c1")
        commit("Alice", "alice@example.com", "2026-01-12T10:30:00+00:00", "c2")
        # Bob: 1 commit on a Tuesday ("2026-01-06", also 2026-W02) at 15:00 (hour "15").
        commit("Bob", "bob@example.com", "2026-01-06T15:00:00+00:00", "c3")
        return repository

    def test_get_committers(self) -> None:
        # arrange
        repository = self.__create_test_repository()
        analyzer = RepositoryHistoryAnalyzer()

        # act
        committers = analyzer.get_committers(repository)

        # assert
        # Alice has 2 commits, Bob has 1, and "git shortlog -n -s" sorts descending by commit-count.
        assert committers == ["Alice", "Bob"]

    def test_get_committer_emails(self) -> None:
        # arrange
        repository = self.__create_test_repository()
        analyzer = RepositoryHistoryAnalyzer()

        # act
        committer_emails = analyzer.get_committer_emails(repository)

        # assert
        assert committer_emails == {"Alice": "alice@example.com", "Bob": "bob@example.com"}

    def test_get_git_history_data_with_week_scale(self) -> None:
        # arrange
        repository = self.__create_test_repository()
        analyzer = RepositoryHistoryAnalyzer()

        # act
        data = analyzer.get_git_history_data(repository, GitHistoryScale.Week)

        # assert
        assert data.committers == ["Alice", "Bob"]
        assert data.committer_emails == {"Alice": "alice@example.com", "Bob": "bob@example.com"}
        buckets = {(dp.committer, dp.bucket): dp.commit_count for dp in data.data_points}
        assert buckets == {
            ("Alice", "2026-W02"): 1,
            ("Alice", "2026-W03"): 1,
            ("Bob", "2026-W02"): 1,
        }

    def test_get_git_history_data_with_day_scale(self) -> None:
        # arrange
        repository = self.__create_test_repository()
        analyzer = RepositoryHistoryAnalyzer()

        # act
        data = analyzer.get_git_history_data(repository, GitHistoryScale.Day)

        # assert
        buckets = {(dp.committer, dp.bucket): dp.commit_count for dp in data.data_points}
        assert buckets == {
            ("Alice", "2026-01-05"): 1,
            ("Alice", "2026-01-12"): 1,
            ("Bob", "2026-01-06"): 1,
        }

    def test_get_git_history_data_with_month_scale_aggregates_same_month(self) -> None:
        # arrange
        repository = self.__create_test_repository()
        analyzer = RepositoryHistoryAnalyzer()

        # act
        data = analyzer.get_git_history_data(repository, GitHistoryScale.Month)

        # assert
        # Both of Alice's commits fall into January 2026, so they must be aggregated into a single "2026-01"-bucket.
        buckets = {(dp.committer, dp.bucket): dp.commit_count for dp in data.data_points}
        assert buckets == {
            ("Alice", "2026-01"): 2,
            ("Bob", "2026-01"): 1,
        }

    def test_get_git_history_data_with_year_scale_aggregates_same_year(self) -> None:
        # arrange
        repository = self.__create_test_repository()
        analyzer = RepositoryHistoryAnalyzer()

        # act
        data = analyzer.get_git_history_data(repository, GitHistoryScale.Year)

        # assert
        # Both of Alice's commits fall into 2026, so they must be aggregated into a single "2026"-bucket.
        buckets = {(dp.committer, dp.bucket): dp.commit_count for dp in data.data_points}
        assert buckets == {
            ("Alice", "2026"): 2,
            ("Bob", "2026"): 1,
        }

    def test_get_commits_per_weekday_data(self) -> None:
        # arrange
        repository = self.__create_test_repository()
        analyzer = RepositoryHistoryAnalyzer()

        # act
        data = analyzer.get_commits_per_weekday_data(repository)

        # assert
        buckets = {(dp.committer, dp.bucket): dp.commit_count for dp in data.data_points}
        assert buckets == {
            ("Alice", "Monday"): 2,
            ("Bob", "Tuesday"): 1,
        }

    def test_get_commits_per_hour_data(self) -> None:
        # arrange
        repository = self.__create_test_repository()
        analyzer = RepositoryHistoryAnalyzer()

        # act
        data = analyzer.get_commits_per_hour_data(repository)

        # assert
        buckets = {(dp.committer, dp.bucket): dp.commit_count for dp in data.data_points}
        assert buckets == {
            ("Alice", "10"): 2,
            ("Bob", "15"): 1,
        }


if __name__ == "__main__":
    unittest.main()
