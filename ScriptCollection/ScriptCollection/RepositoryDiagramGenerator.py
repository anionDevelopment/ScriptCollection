import json
from .GeneralUtilities import GeneralUtilities
from .RepositoryHistoryAnalyzer import CommitterActivityData

_VEGA_LITE_SCHEMA = "https://vega.github.io/schema/vega-lite/v5.json"


class RepositoryDiagramGenerator:
    """Generates Vega-Lite diagram-specifications from committer-activity-data produced by
    RepositoryHistoryAnalyzer. This class only produces the diagram-specification (as json); rendering it into an
    image (for example svg or png) is out of scope of this class."""

    @GeneralUtilities.check_arguments
    def generate_committer_timeline(self, data: CommitterActivityData, target_file: str) -> None:
        """Generates a line-diagram-specification with one line per committer, showing that committer's
        commit-count over the calendar periods contained in "data" (see RepositoryHistoryAnalyzer.get_git_history_data)."""
        spec = self.__build_activity_line_spec(data, "Period", "Calendar period", "Commits per committer over time")
        self.__write_spec(spec, target_file)

    @GeneralUtilities.check_arguments
    def generate_commits_per_weekday_chart(self, data: CommitterActivityData, target_file: str) -> None:
        """Generates a line-diagram-specification with one line per committer, showing that committer's
        commit-count per weekday (see RepositoryHistoryAnalyzer.get_commits_per_weekday_data)."""
        weekday_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        spec = self.__build_activity_line_spec(data, "Weekday", "Weekday", "Commits per committer and weekday", weekday_order)
        self.__write_spec(spec, target_file)

    @GeneralUtilities.check_arguments
    def generate_commits_per_hour_chart(self, data: CommitterActivityData, target_file: str) -> None:
        """Generates a line-diagram-specification with one line per committer, showing that committer's
        commit-count per hour of day (see RepositoryHistoryAnalyzer.get_commits_per_hour_data)."""
        hour_order = [f"{hour:02d}" for hour in range(24)]
        spec = self.__build_activity_line_spec(data, "Hour", "Hour of day", "Commits per committer and hour of day", hour_order)
        self.__write_spec(spec, target_file)

    @GeneralUtilities.check_arguments
    def generate_committer_pie_chart(self, data: CommitterActivityData, target_file: str) -> None:
        """Generates a pie-chart-specification showing each committer's share of the total commit-count."""
        totals = {}
        for data_point in data.data_points:
            totals[data_point.committer] = totals.get(data_point.committer, 0) + data_point.commit_count
        values = [{"Committer": committer, "Commits": commit_count} for committer, commit_count in totals.items()]
        spec = {
            "$schema": _VEGA_LITE_SCHEMA,
            "description": "Share of commits per committer",
            "width": 400,
            "height": 400,
            "datasets": {"committerEmails": self.__committer_emails_dataset(data)},
            "data": {"values": values},
            "transform": [
                {"joinaggregate": [{"op": "sum", "field": "Commits", "as": "TotalCommits"}]},
                {"calculate": "datum.Commits / datum.TotalCommits", "as": "Share"},
            ],
            "mark": {"type": "arc", "tooltip": True},
            "encoding": {
                "theta": {"field": "Commits", "type": "quantitative", "stack": True},
                "color": {"field": "Committer", "type": "nominal", "title": "Committer", "legend": self.__legend_with_email_tooltip()},
                "tooltip": [
                    {"field": "Committer", "type": "nominal"},
                    {"field": "Commits", "type": "quantitative"},
                    {"field": "Share", "type": "quantitative", "format": ".1%", "title": "Share of commits"},
                ],
            },
        }
        self.__write_spec(spec, target_file)

    @GeneralUtilities.check_arguments
    def __build_activity_line_spec(self, data: CommitterActivityData, bucket_field_name: str, bucket_title: str, description: str, sort_order: list = None) -> dict:
        values = [{"Committer": data_point.committer, bucket_field_name: data_point.bucket, "Commits": data_point.commit_count} for data_point in data.data_points]
        x_encoding = {
            "field": bucket_field_name,
            "type": "ordinal",
            "title": bucket_title,
        }
        if sort_order is not None:
            x_encoding["sort"] = sort_order
        return {
            "$schema": _VEGA_LITE_SCHEMA,
            "description": description,
            "width": 800,
            "height": 400,
            "datasets": {"committerEmails": self.__committer_emails_dataset(data)},
            "data": {"values": values},
            "mark": {"type": "line", "point": True},
            "encoding": {
                "x": x_encoding,
                "y": {"field": "Commits", "type": "quantitative", "title": "Number of commits"},
                "color": {"field": "Committer", "type": "nominal", "title": "Committer", "legend": self.__legend_with_email_tooltip()},
                "tooltip": [
                    {"field": "Committer", "type": "nominal"},
                    {"field": bucket_field_name, "type": "ordinal", "title": bucket_title},
                    {"field": "Commits", "type": "quantitative"},
                ],
            },
        }

    @GeneralUtilities.check_arguments
    def __committer_emails_dataset(self, data: CommitterActivityData) -> list:
        return [{"Committer": committer, "Email": data.committer_emails.get(committer, GeneralUtilities.empty_string)} for committer in data.committers]

    @GeneralUtilities.check_arguments
    def __legend_with_email_tooltip(self) -> dict:
        # Vega-Lite's own tooltip-encoding only applies to marks, not to legend-entries. Showing the hovered
        # committer's email-address therefore needs this "legend.encode"-passthrough (a documented Vega-Lite
        # mechanism to customize legend-marks with raw Vega mark-encodings): "datum.value" is the hovered
        # legend-label (the committer-name), and "pluck"/"indexof" look its matching email up in the
        # "committerEmails"-dataset. Vega's expression-language has no lambda/".find()", so this
        # lambda-free array/index-lookup is used instead of a "filter"-callback.
        return {
            "encode": {
                "labels": {
                    "update": {
                        "tooltip": {
                            "signal": "pluck(data('committerEmails'), 'Email')[indexof(pluck(data('committerEmails'), 'Committer'), datum.value)]"
                        }
                    }
                }
            }
        }

    @GeneralUtilities.check_arguments
    def __write_spec(self, spec: dict, target_file: str) -> None:
        GeneralUtilities.ensure_file_exists(target_file)
        with open(target_file, "w", encoding="utf-8") as file_handle:
            json.dump(spec, file_handle, indent=2, sort_keys=False, ensure_ascii=False)
