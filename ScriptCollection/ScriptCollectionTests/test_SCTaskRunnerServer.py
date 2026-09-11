import contextlib
import io
import os
import sys
import tarfile
import tempfile
import unittest
from ..ScriptCollection.GeneralUtilities import GeneralUtilities
from ..ScriptCollection.SCLog import LogLevel
from ..ScriptCollection.ScriptCollectionCore import ScriptCollectionCore
from ..ScriptCollection.TFCPS.SCTaskRunnerServer import SCTaskRunnerServer, _RunnerJob  # pylint:disable=protected-access

#These tests exercise the parts of the runner which handle a job. They deliberately do not run a server and do not do a
#request: what a server does with a connection is not what they are about, and a testcase must not depend on something
#which listens on a port.


def create_server(work_folder: str) -> SCTaskRunnerServer:
    """Returns a server which uses the given folder instead of the default-work-folder. The loglevel is set here,
    because a server raises it only for a ScriptCollectionCore it creates itself and keeps the configuration of one
    which is passed to it - which is what a test has to do to get a defined work-folder."""
    sc = ScriptCollectionCore()
    sc.log.loglevel = LogLevel.Information
    return SCTaskRunnerServer("Android", "TestUser", "TestPassword", work_folder, sc)


def create_job(work_folder: str, result_folder: str) -> _RunnerJob:
    """Returns a job whose workspace is below the given folder and which states the given folder (relative to that
    workspace) as the folder its result is in."""
    return _RunnerJob("job1", os.path.join(work_folder, "workspace"), result_folder)


def create_result_archive(server: SCTaskRunnerServer, job: _RunnerJob) -> str:
    """Calls the private SCTaskRunnerServer.__create_result_archive for a test, the same way the other tests of this
    repository access a private method."""
    # pylint:disable=protected-access
    return server._SCTaskRunnerServer__create_result_archive(job)


def create_payload_archive(work_folder: str, file_name: str, file_content: str) -> str:
    """Writes a repository which consists of one file into an archive of the shape a client submits, and returns that
    archive."""
    repository_folder = os.path.join(work_folder, "repository")
    GeneralUtilities.ensure_directory_exists(repository_folder)
    GeneralUtilities.write_text_to_file(os.path.join(repository_folder, file_name), file_content)
    archive_file = os.path.join(work_folder, "payload.tar.gz")
    with tarfile.open(archive_file, "w:gz") as tar:
        tar.add(repository_folder, arcname=".")
    return archive_file


def write_git_configuration(workspace_folder: str, content: str) -> None:
    """Writes the given content as the git-configuration of the repository in the given workspace."""
    git_folder = os.path.join(workspace_folder, ".git")
    GeneralUtilities.ensure_directory_exists(git_folder)
    GeneralUtilities.write_text_to_file(os.path.join(git_folder, "config"), content)


def extract_payload_and_run_job(server: SCTaskRunnerServer, job: _RunnerJob, archive_file: str, program: str, arguments: list[str]) -> None:
    """Calls the private SCTaskRunnerServer.__extract_payload_and_run_job for a test, the same way the other tests of
    this repository access a private method."""
    # pylint:disable=protected-access
    server._SCTaskRunnerServer__extract_payload_and_run_job(job, archive_file, program, arguments, ".")


def run_job(server: SCTaskRunnerServer, job: _RunnerJob, program: str, arguments: list[str]) -> None:
    """Calls the private SCTaskRunnerServer.__run_job for a test, the same way extract_payload_and_run_job above
    accesses another private method."""
    # pylint:disable=protected-access
    server._SCTaskRunnerServer__run_job(job, program, arguments, ".")


def get_origin_of_the_transferred_repository(server: SCTaskRunnerServer, workspace_folder: str) -> str:
    """Calls the private SCTaskRunnerServer.__get_origin_of_the_transferred_repository for a test, the same way
    extract_payload_and_run_job above accesses another private method."""
    # pylint:disable=protected-access
    return server._SCTaskRunnerServer__get_origin_of_the_transferred_repository(workspace_folder)


class CapturedLog:
    """Captures what the runner logs while something runs, so that a test can state what has to be in that log without
    the log of the testcase appearing in the output of the testrun. The runner logs to the console, which is the only
    log a permanently running server has."""

    def __init__(self):
        self.__standard_output = io.StringIO()
        self.__error_output = io.StringIO()
        self.__redirections = None

    def __enter__(self):
        self.__redirections = contextlib.ExitStack()
        self.__redirections.enter_context(contextlib.redirect_stdout(self.__standard_output))
        self.__redirections.enter_context(contextlib.redirect_stderr(self.__error_output))
        return self

    def __exit__(self, exception_type, exception_value, traceback) -> None:
        self.__redirections.close()

    def get_content(self) -> str:
        return self.__standard_output.getvalue()+self.__error_output.getvalue()


class SCTaskRunnerServerTests(unittest.TestCase):

    def test_the_program_of_a_job_runs_in_the_extracted_repository(self) -> None:
        # arrange
        with tempfile.TemporaryDirectory() as work_folder:
            server = create_server(work_folder)
            archive_file = create_payload_archive(work_folder, "TransferredFile.txt", "content-of-the-transferred-file")
            job = create_job(work_folder, ".")

            # act
            with CapturedLog():
                extract_payload_and_run_job(server, job, archive_file, sys.executable, ["-c", "print(open('TransferredFile.txt').read())"])

            # assert
            self.assertEqual("completed", job.state)
            self.assertEqual(0, job.exitcode)
            self.assertIn("content-of-the-transferred-file", job.log)
            self.assertFalse(os.path.isfile(archive_file), "The payload-archive has to be removed after it was extracted.")

    def test_a_job_whose_repository_can_not_be_extracted_ends_as_failed(self) -> None:
        # arrange
        with tempfile.TemporaryDirectory() as work_folder:
            server = create_server(work_folder)
            damaged_archive_file = os.path.join(work_folder, "payload.tar.gz")
            GeneralUtilities.write_text_to_file(damaged_archive_file, "this is not an archive")
            job = create_job(work_folder, ".")

            # act
            with CapturedLog():
                extract_payload_and_run_job(server, job, damaged_archive_file, sys.executable, ["-c", "print('this must not run')"])

            # assert
            self.assertEqual("failed", job.state)
            self.assertEqual(-1, job.exitcode)
            self.assertNotIn("this must not run", job.log)

    def test_the_details_of_an_internal_error_are_logged_but_are_not_part_of_the_result_of_the_job(self) -> None:
        # arrange
        with tempfile.TemporaryDirectory() as work_folder:
            server = create_server(work_folder)
            damaged_archive_file = os.path.join(work_folder, "payload.tar.gz")
            GeneralUtilities.write_text_to_file(damaged_archive_file, "this is not an archive")
            job = create_job(work_folder, ".")

            # act
            with CapturedLog() as captured_log:
                extract_payload_and_run_job(server, job, damaged_archive_file, sys.executable, ["-c", "print('this must not run')"])
            logged_by_the_runner = captured_log.get_content()

            # assert
            self.assertIn("This is a problem of the runner itself", job.log)
            self.assertNotIn("Traceback", job.log)
            self.assertIn("Traceback", logged_by_the_runner)
            self.assertIn("Internal error", logged_by_the_runner)

    def test_the_end_of_the_output_of_a_failed_job_is_logged(self) -> None:
        # arrange
        with tempfile.TemporaryDirectory() as work_folder:
            server = create_server(work_folder)
            job = create_job(work_folder, ".")
            GeneralUtilities.ensure_directory_exists(job.workspace_folder)

            # act
            with CapturedLog() as captured_log:
                run_job(server, job, sys.executable, ["-c", "import sys;[print('line'+str(number)) for number in range(40)];sys.exit(3)"])
            logged_by_the_runner = captured_log.get_content()

            # assert
            self.assertEqual("failed", job.state)
            self.assertEqual(3, job.exitcode)
            self.assertIn("line39", logged_by_the_runner)
            self.assertNotIn("line0", logged_by_the_runner)
            self.assertIn("line0", job.log)

    def test_the_output_of_a_successful_job_is_not_logged(self) -> None:
        # arrange
        with tempfile.TemporaryDirectory() as work_folder:
            server = create_server(work_folder)
            job = create_job(work_folder, ".")
            GeneralUtilities.ensure_directory_exists(job.workspace_folder)

            # act
            #The program composes what it prints, so that the searched text is not part of the command - which the
            #runner logs and which would therefore contain it regardless of what the program printed.
            with CapturedLog() as captured_log:
                run_job(server, job, sys.executable, ["-c", "print('output-of-'+'the-program')"])
            logged_by_the_runner = captured_log.get_content()

            # assert
            self.assertEqual("completed", job.state)
            self.assertNotIn("output-of-the-program", logged_by_the_runner)
            self.assertIn("output-of-the-program", job.log)

    def test_the_repository_of_a_job_is_taken_from_the_transferred_git_configuration(self) -> None:
        # arrange
        with tempfile.TemporaryDirectory() as work_folder:
            server = create_server(work_folder)
            write_git_configuration(work_folder, '[core]\n\tbare = false\n[remote "origin"]\n\turl = https://example.com/Product.git\n\tfetch = +refs/heads/*:refs/remotes/origin/*\n')

            # act
            actual_result = get_origin_of_the_transferred_repository(server, work_folder)

            # assert
            self.assertEqual("https://example.com/Product.git", actual_result)

    def test_a_credential_of_the_repository_is_not_part_of_its_stated_address(self) -> None:
        # arrange
        with tempfile.TemporaryDirectory() as work_folder:
            server = create_server(work_folder)
            write_git_configuration(work_folder, '[remote "origin"]\n\turl = https://TestUser:TestToken@example.com/Product.git\n')

            # act
            actual_result = get_origin_of_the_transferred_repository(server, work_folder)

            # assert
            self.assertEqual("https://example.com/Product.git", actual_result)
            self.assertNotIn("TestToken", actual_result)

    def test_the_address_of_a_repository_which_is_addressed_over_ssh_stays_unchanged(self) -> None:
        # arrange
        with tempfile.TemporaryDirectory() as work_folder:
            server = create_server(work_folder)
            write_git_configuration(work_folder, '[remote "origin"]\n\turl = git@example.com:Group/Product.git\n')

            # act
            actual_result = get_origin_of_the_transferred_repository(server, work_folder)

            # assert
            self.assertEqual("git@example.com:Group/Product.git", actual_result)

    def test_a_transferred_repository_without_a_remote_is_stated_as_unknown(self) -> None:
        # arrange
        with tempfile.TemporaryDirectory() as work_folder:
            server = create_server(work_folder)
            write_git_configuration(work_folder, "[core]\n\tbare = false\n")

            # act
            actual_result = get_origin_of_the_transferred_repository(server, work_folder)

            # assert
            self.assertIn("unknown", actual_result)

    def test_only_the_result_folder_of_a_job_is_transferred_back(self) -> None:
        # arrange
        with tempfile.TemporaryDirectory() as work_folder:
            server = create_server(work_folder)
            job = create_job(work_folder, "build/output")
            GeneralUtilities.ensure_directory_exists(os.path.join(job.workspace_folder, "build", "output"))
            GeneralUtilities.ensure_directory_exists(os.path.join(job.workspace_folder, "android"))
            GeneralUtilities.write_text_to_file(os.path.join(job.workspace_folder, "build", "output", "TheArtifact.aab"), "the-artifact")
            GeneralUtilities.write_text_to_file(os.path.join(job.workspace_folder, "SourceFile.dart"), "the-sourcecode")
            #A file which the build of the runner created outside of the result-folder and which states a path of the
            #runner: exactly what must not reach the repository of the client.
            GeneralUtilities.write_text_to_file(os.path.join(job.workspace_folder, "android", "local.properties"), "a-path-of-the-runner")

            # act
            archive_file = create_result_archive(server, job)

            # assert
            with tarfile.open(archive_file, "r:gz") as tar:
                transferred_files = [name for name in tar.getnames() if not tar.getmember(name).isdir()]
            self.assertEqual(["./TheArtifact.aab"], transferred_files)

    def test_a_result_folder_outside_of_the_workspace_of_the_job_is_refused(self) -> None:
        # arrange
        with tempfile.TemporaryDirectory() as work_folder:
            server = create_server(work_folder)
            job = create_job(work_folder, os.path.join("..", "..", "somewhere-else"))

            # act
            with self.assertRaises(ValueError) as raised:
                create_result_archive(server, job)

            # assert
            self.assertIn("is not inside the workspace", str(raised.exception))
