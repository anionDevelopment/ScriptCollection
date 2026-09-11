import unittest
from unittest.mock import patch
from ..ScriptCollection.ScriptCollectionCore import ScriptCollectionCore
from ..ScriptCollection.SCLog import LogLevel
from ..ScriptCollection.TFCPS import TFCPS_RemoteBuild as remote_build_module
from ..ScriptCollection.TFCPS.TFCPS_RemoteBuild import TFCPS_RemoteBuild, RunnerEndpoint, RunnerOperatingSystem, RunnerNotReachableError, RunnerRequestFailedError


class FakeClock:
    """Replaces the time-module of TFCPS_RemoteBuild in a test, so that a test which exercises how long the client waits
    does not have to wait itself: sleeping moves this clock forward instead of the test."""

    def __init__(self):
        self.current_time = 0.0

    def time(self) -> float:
        return self.current_time

    def sleep(self, seconds: float) -> None:
        self.current_time = self.current_time+seconds


def create_remote_build_with_answers(answers: list) -> tuple:
    """Returns a TFCPS_RemoteBuild whose requests are answered by the given answers instead of by a real runner, together
    with the list which collects the requests which were done. Each answer is used for one request: an answer which is an
    exception is raised, every other answer is returned as the answer of the runner."""
    sc = ScriptCollectionCore()
    #Quiet, because the client logs that a runner is not reachable - which is the expected behaviour here and therefore
    #must not appear in the output of the testrun.
    sc.log.loglevel = LogLevel.Quiet
    remote_build = TFCPS_RemoteBuild(sc)
    done_requests: list = []

    def answer_request(endpoint: RunnerEndpoint, method: str, path: str, timeout_in_seconds: int):
        done_requests.append((method, path))
        answer = answers[len(done_requests)-1]
        if isinstance(answer, Exception):
            raise answer
        return answer

    # pylint:disable=protected-access
    setattr(remote_build, "_TFCPS_RemoteBuild__http", answer_request)
    return remote_build, done_requests


def http_of_running_job(remote_build: TFCPS_RemoteBuild, method: str, path: str, retry_interval_in_seconds: int) -> tuple:
    """Calls the private TFCPS_RemoteBuild.__http_of_running_job for a test, the same way the other tests of this
    repository access a private method."""
    # pylint:disable=protected-access
    return remote_build._TFCPS_RemoteBuild__http_of_running_job(create_endpoint(), method, path, 300, retry_interval_in_seconds)


def get_job_status(remote_build: TFCPS_RemoteBuild, job_id: str) -> dict:
    """Calls the private TFCPS_RemoteBuild.__get_job_status for a test, the same way http_of_running_job above accesses
    another private method."""
    # pylint:disable=protected-access
    return remote_build._TFCPS_RemoteBuild__get_job_status(create_endpoint(), job_id, RunnerOperatingSystem.Android, 0)


def http(remote_build: TFCPS_RemoteBuild, method: str, path: str) -> tuple:
    """Calls the private TFCPS_RemoteBuild.__http for a test, the same way http_of_running_job above accesses another
    private method."""
    # pylint:disable=protected-access
    return remote_build._TFCPS_RemoteBuild__http(create_endpoint(), method, path, 300)


def create_endpoint() -> RunnerEndpoint:
    """Returns a runner-endpoint which is never really contacted by these tests."""
    return RunnerEndpoint("https://runner.example.com", "TestUser", "TestPassword")


class TFCPS_RemoteBuildTests(unittest.TestCase):

    def test_http_of_running_job_returns_the_answer_of_the_runner(self) -> None:
        # arrange
        remote_build, done_requests = create_remote_build_with_answers([(200, b"content-of-the-log")])

        # act
        actual_result = http_of_running_job(remote_build, "GET", "/jobs/job1/logs", 0)

        # assert
        self.assertEqual((200, b"content-of-the-log"), actual_result)
        self.assertEqual([("GET", "/jobs/job1/logs")], done_requests)

    def test_http_of_running_job_repeats_the_request_while_the_runner_is_not_reachable(self) -> None:
        # arrange
        remote_build, done_requests = create_remote_build_with_answers([RunnerNotReachableError("Not reachable."), RunnerNotReachableError("Not reachable."), (200, b"content-of-the-log")])

        # act
        with patch.object(remote_build_module, "time", FakeClock()):
            actual_result = http_of_running_job(remote_build, "GET", "/jobs/job1/logs", 60)

        # assert
        self.assertEqual((200, b"content-of-the-log"), actual_result)
        self.assertEqual(3, len(done_requests))

    def test_http_of_running_job_gives_up_when_the_runner_is_not_reachable_for_too_long(self) -> None:
        # arrange
        amount_of_answers = 7  # the amount of requests which fit into the tolerated interruption when 60 seconds are waited between them
        remote_build, done_requests = create_remote_build_with_answers([RunnerNotReachableError("Not reachable.") for _ in range(amount_of_answers)])

        # act
        with patch.object(remote_build_module, "time", FakeClock()):
            with self.assertRaises(RunnerNotReachableError) as raised:
                http_of_running_job(remote_build, "GET", "/jobs/job1/logs", 60)

        # assert
        self.assertIn("may still be running on the runner", str(raised.exception))
        self.assertEqual(amount_of_answers, len(done_requests))

    def test_http_of_running_job_does_not_repeat_a_request_which_the_runner_answered(self) -> None:
        # arrange
        remote_build, done_requests = create_remote_build_with_answers([RunnerRequestFailedError("The runner-request failed with status 500.", 500)])

        # act
        with self.assertRaises(RunnerRequestFailedError):
            http_of_running_job(remote_build, "GET", "/jobs/job1/logs", 0)

        # assert
        self.assertEqual(1, len(done_requests))

    def test_get_job_status_returns_the_state_of_the_job(self) -> None:
        # arrange
        remote_build, _ = create_remote_build_with_answers([(200, b'{"state": "running", "exitcode": null}')])

        # act
        actual_result = get_job_status(remote_build, "job1")

        # assert
        self.assertEqual("running", actual_result["state"])

    def test_get_job_status_states_that_the_build_has_no_result_when_the_runner_does_not_know_the_job(self) -> None:
        # arrange
        remote_build, _ = create_remote_build_with_answers([RunnerRequestFailedError("The runner-request failed with status 404: Unknown job", 404)])

        # act
        with self.assertRaises(ValueError) as raised:
            get_job_status(remote_build, "job1")

        # assert
        self.assertIn("does not know the job 'job1'", str(raised.exception))

    def test_http_states_which_request_could_not_reach_which_runner(self) -> None:
        # arrange
        sc = ScriptCollectionCore()
        sc.log.loglevel = LogLevel.Quiet
        remote_build = TFCPS_RemoteBuild(sc)
        connection_error = ConnectionResetError(10054, "An existing connection was forcibly closed by the remote host")

        # act
        with patch.object(remote_build_module.urllib.request, "urlopen", side_effect=connection_error):
            with self.assertRaises(RunnerNotReachableError) as raised:
                http(remote_build, "GET", "/jobs/job1/logs")

        # assert
        self.assertIn("https://runner.example.com", str(raised.exception))
        self.assertIn("GET /jobs/job1/logs", str(raised.exception))
