import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from .GeneralUtilities import GeneralUtilities
from .ScriptCollectionCore import ScriptCollectionCore


class GitHistoryScale(Enum):
    Day = 0
    Week = 1
    Month = 2
    Year = 3


@dataclass(frozen=True)
class CommitterActivityDataPoint:
    committer: str
    bucket: str
    commit_count: int


@dataclass(frozen=True)
class CommitterActivityData:
    committers: list = field(default_factory=list)
    committer_emails: dict = field(default_factory=dict)
    data_points: list = field(default_factory=list)


class RepositoryHistoryAnalyzer:
    """Analyzes the git history of a repository into structured committer-activity-data.
    A "committer" is, throughout this class, exactly an identity as "git shortlog -n -s" reports it."""

    __weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    __committer_and_email_pattern = re.compile(r"^(.*?)\s*<([^<>]*)>")

    def __init__(self):
        self.sc = ScriptCollectionCore()

    @GeneralUtilities.check_arguments
    def get_committers(self, repository_path: str) -> list:
        """Returns the committer-names, in the same order as "git shortlog -n -s" lists them."""
        result = self.sc.run_program_argsasarray("git", ["shortlog", "-n", "-s", "HEAD"], repository_path)
        committers = []
        for line in result[1].splitlines():
            if GeneralUtilities.string_has_content(line):
                committers.append(line.split("\t", 1)[1].strip())
        return committers

    @GeneralUtilities.check_arguments
    def get_committer_emails(self, repository_path: str) -> dict:
        """Returns a mapping of committer-name to email-address, based on "git shortlog -n -s -e"."""
        result = self.sc.run_program_argsasarray("git", ["shortlog", "-n", "-s", "-e", "HEAD"], repository_path)
        committer_emails = {}
        for line in result[1].splitlines():
            if not GeneralUtilities.string_has_content(line):
                continue
            name_and_email = line.split("\t", 1)[1]
            match = RepositoryHistoryAnalyzer.__committer_and_email_pattern.match(name_and_email)
            if match is not None:
                committer_emails[match.group(1)] = match.group(2)
        return committer_emails

    @GeneralUtilities.check_arguments
    def __get_commits(self, repository_path: str) -> list:
        """Returns a list of (committer-name, committer-date)-tuples for all commits, in the committer-date's
        own recorded utc-offset."""
        result = self.sc.run_program_argsasarray("git", ["log", "--pretty=format:%cI%x09%cn"], repository_path)
        commits = []
        for line in result[1].splitlines():
            if not GeneralUtilities.string_has_content(line):
                continue
            date_as_string, committer = line.split("\t", 1)
            commits.append((committer, datetime.fromisoformat(date_as_string)))
        return commits

    @GeneralUtilities.check_arguments
    def __to_bucket(self, moment: datetime, scale: GitHistoryScale) -> str:
        if scale == GitHistoryScale.Day:
            return moment.strftime("%Y-%m-%d")
        if scale == GitHistoryScale.Week:
            iso_calendar = moment.isocalendar()
            return f"{iso_calendar[0]}-W{iso_calendar[1]:02d}"
        if scale == GitHistoryScale.Month:
            return moment.strftime("%Y-%m")
        if scale == GitHistoryScale.Year:
            return moment.strftime("%Y")
        raise ValueError(f"Unknown GitHistoryScale: {scale}")

    @GeneralUtilities.check_arguments
    def __aggregate(self, repository_path: str, bucket_selector) -> CommitterActivityData:
        committers = self.get_committers(repository_path)
        committer_emails = self.get_committer_emails(repository_path)
        counts = {}
        for committer, moment in self.__get_commits(repository_path):
            bucket = bucket_selector(moment)
            key = (committer, bucket)
            counts[key] = counts.get(key, 0) + 1
        data_points = [CommitterActivityDataPoint(committer, bucket, commit_count) for (committer, bucket), commit_count in counts.items()]
        return CommitterActivityData(committers, committer_emails, data_points)

    @GeneralUtilities.check_arguments
    def get_git_history_data(self, repository_path: str, scale: GitHistoryScale) -> CommitterActivityData:
        """Returns, per committer and per calendar period (day/week/year, depending on "scale"), the amount of
        commits that committer made in that calendar period. Only calendar periods with at least one commit are
        contained in the result."""
        return self.__aggregate(repository_path, lambda moment: self.__to_bucket(moment, scale))

    @GeneralUtilities.check_arguments
    def get_commits_per_weekday_data(self, repository_path: str) -> CommitterActivityData:
        """Returns, per committer and per weekday (Monday..Sunday), the amount of commits that committer made on
        that weekday, summed across the whole history. Only weekdays with at least one commit are contained in
        the result."""
        return self.__aggregate(repository_path, lambda moment: RepositoryHistoryAnalyzer.__weekdays[moment.weekday()])

    @GeneralUtilities.check_arguments
    def get_commits_per_hour_data(self, repository_path: str) -> CommitterActivityData:
        """Returns, per committer and per hour of day ("00"..."23"), the amount of commits that committer made in
        that hour, summed across the whole history. Only hours with at least one commit are contained in the
        result."""
        return self.__aggregate(repository_path, lambda moment: f"{moment.hour:02d}")
