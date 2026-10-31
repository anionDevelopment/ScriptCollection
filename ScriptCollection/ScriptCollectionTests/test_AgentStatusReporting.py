import os
import subprocess
import tempfile
import unittest
from unittest import mock
from ..ScriptCollection.AgentStatusReporting.AgentStatus import AgentStatus
from ..ScriptCollection.AgentStatusReporting.AgentStatusEventChannel import AgentStatusEventChannel
from ..ScriptCollection.AgentStatusReporting.AgentStatusRelay import AgentStatusRelay
from ..ScriptCollection.AgentStatusReporting.AgentStatusReporter import AgentStatusReporter
from ..ScriptCollection.AgentStatusReporting.AgentStatusReportingSession import AgentStatusReportingSession
from ..ScriptCollection.AgentStatusReporting.HerdrAgentStatusReporter import HerdrAgentStatusReporter


HERDR_ENVIRONMENT: dict[str, str] = {"HERDR_ENV": "1", "HERDR_PANE_ID": "w1:p1", "HERDR_BIN_PATH": "herdr"}


class RecordingAgentStatusReporter(AgentStatusReporter):
    reports: list[AgentStatus] = None
    releases: int = 0

    def __init__(self):
        self.reports = []
        self.releases = 0

    def report(self, status: AgentStatus) -> None:
        self.reports.append(status)

    def release(self) -> None:
        self.releases = self.releases + 1


class AgentStatusTests(unittest.TestCase):

    def test_accepts_exactly_the_tokens(self) -> None:
        # act and assert
        self.assertEqual(AgentStatus.Working, AgentStatus.parse_token(b"working"))
        self.assertEqual(AgentStatus.Idle, AgentStatus.parse_token(b"idle"))
        self.assertEqual(AgentStatus.Blocked, AgentStatus.parse_token(b"blocked"))

    def test_rejects_everything_else(self) -> None:
        for line in [b"", b"ended", b"Working", b"WORKING", b" working", b"working ", b"working\r", b"idle; rm -rf /", b"$(reboot)", b"/etc/passwd", b"\xff\xfe"]:
            # act and assert
            self.assertIsNone(AgentStatus.parse_token(line), line)


class AgentStatusRelayTests(unittest.TestCase):

    def __append(self, events_file: str, content: bytes) -> None:
        with open(events_file, "ab") as file:
            file.write(content)

    def __process(self, content: bytes) -> RecordingAgentStatusReporter:
        reporter = RecordingAgentStatusReporter()
        with tempfile.TemporaryDirectory() as folder:
            events_file = os.path.join(folder, "events")
            self.__append(events_file, content)
            AgentStatusRelay(events_file, reporter, False).process_new_events()
        return reporter

    def test_keeps_order_across_reads(self) -> None:
        # arrange
        reporter = RecordingAgentStatusReporter()
        with tempfile.TemporaryDirectory() as folder:
            events_file = os.path.join(folder, "events")
            relay = AgentStatusRelay(events_file, reporter, False)

            # act
            for token in [b"working\n", b"blocked\n", b"working\n", b"idle\n"]:
                self.__append(events_file, token)
                relay.process_new_events()

        # assert
        self.assertEqual([AgentStatus.Working, AgentStatus.Blocked, AgentStatus.Working, AgentStatus.Idle], reporter.reports)

    def test_ignores_invalid_lines(self) -> None:
        # act
        reporter = self.__process(b"$(reboot)\nworking\n/etc/passwd\nended\n")

        # assert
        self.assertEqual([AgentStatus.Working], reporter.reports)

    def test_forwards_only_changes_of_the_state(self) -> None:
        # arrange
        reporter = RecordingAgentStatusReporter()
        with tempfile.TemporaryDirectory() as folder:
            events_file = os.path.join(folder, "events")
            relay = AgentStatusRelay(events_file, reporter, False)

            # act
            for _ in range(3):
                self.__append(events_file, b"working\n")
                relay.process_new_events()

        # assert
        self.assertEqual([AgentStatus.Working], reporter.reports)

    def test_one_read_results_in_one_report_of_the_latest_state(self) -> None:
        # act
        reporter = self.__process(b"working\nidle\n" * 1000 + b"blocked\n")

        # assert
        self.assertEqual([AgentStatus.Blocked], reporter.reports)

    def test_waits_for_the_end_of_an_unfinished_line(self) -> None:
        # arrange
        reporter = RecordingAgentStatusReporter()
        with tempfile.TemporaryDirectory() as folder:
            events_file = os.path.join(folder, "events")
            relay = AgentStatusRelay(events_file, reporter, False)
            self.__append(events_file, b"wor")

            # act
            relay.process_new_events()
            self.assertEqual([], reporter.reports)
            self.__append(events_file, b"king\n")
            relay.process_new_events()

        # assert
        self.assertEqual([AgentStatus.Working], reporter.reports)

    def test_ignores_an_oversized_line_which_spans_several_reads(self) -> None:
        # arrange
        reporter = RecordingAgentStatusReporter()
        with tempfile.TemporaryDirectory() as folder:
            events_file = os.path.join(folder, "events")
            relay = AgentStatusRelay(events_file, reporter, False)
            self.__append(events_file, b"x" * (AgentStatusRelay.maximal_line_length + 1))
            relay.process_new_events()
            self.__append(events_file, b"working\nidle\n")

            # act
            relay.process_new_events()

        # assert
        self.assertEqual([AgentStatus.Idle], reporter.reports)

    def test_read_size_is_limited(self) -> None:
        # arrange
        reporter = RecordingAgentStatusReporter()
        with tempfile.TemporaryDirectory() as folder:
            events_file = os.path.join(folder, "events")
            relay = AgentStatusRelay(events_file, reporter, False)
            self.__append(events_file, b"\n" * AgentStatusRelay.maximal_read_size + b"working\n")

            # act
            relay.process_new_events()
            self.assertEqual([], reporter.reports)
            relay.process_new_events()

        # assert
        self.assertEqual([AgentStatus.Working], reporter.reports)

    def test_stop_does_a_final_read(self) -> None:
        # arrange
        reporter = RecordingAgentStatusReporter()
        with tempfile.TemporaryDirectory() as folder:
            events_file = os.path.join(folder, "events")
            self.__append(events_file, b"")
            relay = AgentStatusRelay(events_file, reporter, False)
            self.assertFalse(relay.has_reported())
            self.__append(events_file, b"idle\n")

            # act
            relay.stop()

        # assert
        self.assertEqual([AgentStatus.Idle], reporter.reports)
        self.assertTrue(relay.has_reported())


class HerdrAgentStatusReporterTests(unittest.TestCase):

    def test_builds_the_report_command_as_argument_list(self) -> None:
        # arrange
        reporter = HerdrAgentStatusReporter("C:\\Program Files\\herdr\\herdr.exe", "w1:p1", "scrais-claude", False)

        # act
        command = reporter.get_report_command(AgentStatus.Blocked)

        # assert
        self.assertEqual(["C:\\Program Files\\herdr\\herdr.exe", "pane", "report-agent", "w1:p1", "--source", "scrais", "--agent", "scrais-claude", "--state", "blocked", "--seq"], command[:-1])
        self.assertTrue(command[-1].isdigit())

    def test_builds_the_release_command(self) -> None:
        # arrange
        reporter = HerdrAgentStatusReporter("herdr", "w1:p1", "scrais-vibe", False)

        # act
        command = reporter.get_release_command()

        # assert
        self.assertEqual(["herdr", "pane", "release-agent", "w1:p1", "--source", "scrais", "--agent", "scrais-vibe", "--seq"], command[:-1])

    def test_sequence_is_strictly_increasing_with_a_coarse_clock(self) -> None:
        # arrange
        reporter = HerdrAgentStatusReporter("herdr", "w1:p1", "scrais-claude", False)

        # act
        with mock.patch("time.time_ns", return_value=1000):
            first = int(reporter.get_report_command(AgentStatus.Working)[-1])
            second = int(reporter.get_report_command(AgentStatus.Idle)[-1])
            third = int(reporter.get_release_command()[-1])

        # assert
        self.assertLess(first, second)
        self.assertLess(second, third)

    def test_is_active_only_with_complete_environment(self) -> None:
        # act and assert
        self.assertIsNotNone(HerdrAgentStatusReporter.try_create(HERDR_ENVIRONMENT, "scrais-claude", False))
        self.assertIsNone(HerdrAgentStatusReporter.try_create({}, "scrais-claude", False))
        self.assertIsNone(HerdrAgentStatusReporter.try_create({**HERDR_ENVIRONMENT, "HERDR_ENV": "0"}, "scrais-claude", False))
        self.assertIsNone(HerdrAgentStatusReporter.try_create({**HERDR_ENVIRONMENT, "HERDR_PANE_ID": ""}, "scrais-claude", False))
        self.assertIsNone(HerdrAgentStatusReporter.try_create({"HERDR_ENV": "1", "HERDR_PANE_ID": "w1:p1"}, "scrais-claude", False))

    def test_runs_without_shell_and_detached_from_the_terminal(self) -> None:
        # arrange
        reporter = HerdrAgentStatusReporter("herdr", "w1:p1", "scrais-claude", False)

        # act
        with mock.patch("subprocess.run", return_value=subprocess.CompletedProcess([], 0)) as run:
            reporter.report(AgentStatus.Working)

        # assert
        self.assertIsInstance(run.call_args.args[0], list)
        self.assertNotIn("shell", run.call_args.kwargs)
        self.assertEqual(subprocess.DEVNULL, run.call_args.kwargs["stdin"])
        self.assertTrue(run.call_args.kwargs["capture_output"])
        self.assertEqual(HerdrAgentStatusReporter.timeout_in_seconds, run.call_args.kwargs["timeout"])

    def test_a_failing_report_does_not_raise(self) -> None:
        # arrange
        reporter = HerdrAgentStatusReporter("herdr", "w1:p1", "scrais-claude", False)

        for failure in [subprocess.TimeoutExpired("herdr", 5), FileNotFoundError("herdr")]:
            # act and assert
            with mock.patch("subprocess.run", side_effect=failure):
                reporter.report(AgentStatus.Working)
                reporter.release()

    def test_failures_are_only_shown_in_verbose_output(self) -> None:
        for verbose, expected_messages in [(False, 0), (True, 1)]:
            # arrange
            reporter = HerdrAgentStatusReporter("herdr", "w1:p1", "scrais-claude", verbose)

            # act
            with mock.patch("subprocess.run", return_value=subprocess.CompletedProcess([], 1)):
                with mock.patch("sys.stderr") as stderr:
                    reporter.report(AgentStatus.Working)

            # assert
            self.assertEqual(expected_messages, len([call for call in stderr.write.call_args_list if "herdr" in call.args[0]]))


class AgentStatusEventChannelTests(unittest.TestCase):

    def test_creates_the_event_file_and_removes_it(self) -> None:
        # arrange
        channel = AgentStatusEventChannel()
        events_file = channel.get_events_file()

        # act and assert
        self.assertTrue(os.path.isfile(events_file))
        channel.remove()
        self.assertFalse(os.path.exists(os.path.dirname(events_file)))

    def test_every_container_user_can_write(self) -> None:
        # arrange
        chmod_calls: list[int] = []

        # act
        with mock.patch("os.chmod", side_effect=lambda _, mode: chmod_calls.append(mode)):
            channel = AgentStatusEventChannel()
        channel.remove()

        # assert
        self.assertEqual([0o777, 0o666], chmod_calls)

    def test_converts_the_path_of_the_mount(self) -> None:
        # arrange
        channel = AgentStatusEventChannel()

        # act
        volume_arguments = channel.get_volume_arguments()
        host_folder = os.path.dirname(channel.get_events_file())
        channel.remove()

        # assert
        self.assertEqual(["--volume", f"{host_folder.replace(os.sep, '/')}:/Workspace/Temp/AgentStatus"], volume_arguments)
        self.assertNotIn("\\", volume_arguments[1])

    def test_start_line_can_not_stop_an_entrypoint_with_set_e(self) -> None:
        # arrange
        channel = AgentStatusEventChannel()

        # act
        line = channel.get_start_report_line(AgentStatus.Working)
        channel.remove()

        # assert
        self.assertEqual("command -v scrais-agent-status >/dev/null 2>&1 && scrais-agent-status working || true", line)


class AgentStatusReportingSessionTests(unittest.TestCase):

    def test_is_not_created_outside_of_herdr(self) -> None:
        # act and assert
        self.assertIsNone(AgentStatusReportingSession.try_create({}, "scrais-claude", False))

    def test_is_not_created_if_the_channel_fails(self) -> None:
        # act
        with mock.patch("tempfile.mkdtemp", side_effect=PermissionError("denied")):
            session = AgentStatusReportingSession.try_create(HERDR_ENVIRONMENT, "scrais-claude", False)

        # assert
        self.assertIsNone(session)

    def test_releases_after_a_report_and_removes_the_channel(self) -> None:
        # arrange
        reporter = RecordingAgentStatusReporter()
        channel = AgentStatusEventChannel()
        session = AgentStatusReportingSession(channel, AgentStatusRelay(channel.get_events_file(), reporter, False), reporter, False)
        with open(channel.get_events_file(), "ab") as file:
            file.write(b"working\n")

        # act
        session.stop()

        # assert
        self.assertEqual([AgentStatus.Working], reporter.reports)
        self.assertEqual(1, reporter.releases)
        self.assertFalse(os.path.exists(channel.get_events_file()))

    def test_does_not_release_without_a_report(self) -> None:
        # arrange
        reporter = RecordingAgentStatusReporter()
        channel = AgentStatusEventChannel()
        session = AgentStatusReportingSession(channel, AgentStatusRelay(channel.get_events_file(), reporter, False), reporter, False)

        # act
        session.start()
        session.stop()

        # assert
        self.assertEqual([], reporter.reports)
        self.assertEqual(0, reporter.releases)
        self.assertFalse(os.path.exists(channel.get_events_file()))

    def test_informs_once_in_verbose_output_if_no_status_was_received(self) -> None:
        # arrange
        reporter = RecordingAgentStatusReporter()
        channel = AgentStatusEventChannel()
        session = AgentStatusReportingSession(channel, AgentStatusRelay(channel.get_events_file(), reporter, True), reporter, True)

        # act
        with mock.patch("sys.stderr") as stderr:
            session.stop()

        # assert
        self.assertEqual(1, len([call for call in stderr.write.call_args_list if "scrais-agent-status" in call.args[0]]))

    def test_a_failing_stop_does_not_raise_and_still_removes_the_channel(self) -> None:
        # arrange
        reporter = RecordingAgentStatusReporter()
        channel = AgentStatusEventChannel()
        session = AgentStatusReportingSession(channel, AgentStatusRelay(os.path.join(os.path.dirname(channel.get_events_file()), "missing"), reporter, False), reporter, False)

        # act
        session.stop()

        # assert
        self.assertFalse(os.path.exists(channel.get_events_file()))
