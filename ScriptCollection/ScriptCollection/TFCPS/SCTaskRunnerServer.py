import os
import json
import base64
import shutil
import ssl
import time
import uuid
import threading
import subprocess
import tarfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ..GeneralUtilities import GeneralUtilities
from ..ScriptCollectionCore import ScriptCollectionCore
from ..SCLog import LogLevel

#Size of the chunks in which the archives are copied between the network-connection and the disk. The archives are
#transferred chunk-wise instead of being held in memory as a whole because both of them are regularly large (the payload
#contains the whole repository of the client, the result contains the complete build-output of a codeunit),
#while a runner often runs in a container with a small memory-limit and needs that memory for the build itself.
_transfer_chunk_size_in_bytes: int = 1024*1024

#Interval in which a job which is still running states that in the log of the runner. The output of a job belongs to the
#job and is fetched by the client, so without such a line the log of the runner would state nothing at all between the
#start of a job and its result - which is an hour or more for an app-build.
_interval_between_two_progress_logs_in_seconds: int = 60

#Amount of lines of the output of a job which did not succeed that the runner logs. The complete output belongs to the
#job and is fetched by the client; this is what makes the log of the runner state why a build failed even when no client
#is connected any more when it ends.
_amount_of_logged_lines_of_a_failed_job: int = 25


class _RunnerJob:
    def __init__(self, job_id: str, workspace_folder: str, result_folder: str):
        self.job_id = job_id
        self.workspace_folder = workspace_folder
        #Folder whose content is the result of the job, relative to the workspace (which is the repository the client
        #sent). Only this folder is transferred back, because only it contains what the client asked the runner to
        #produce: everything else in the workspace is either the unchanged content the client sent or state of this
        #machine (its paths, its caches, its toolchain-configuration), which has no business in the repository of a
        #client.
        self.result_folder = result_folder
        self.state = "running"  # "running" | "completed" | "failed"
        self.exitcode = None
        self.log = GeneralUtilities.empty_string
        self.lock = threading.Lock()
        #Serializes the transfer of the result-archive against the deletion of the workspace. A client deletes the job as
        #soon as it stops waiting for the result - which also happens when it gives up on a still-running result-request,
        #for example because a reverse-proxy in front of the runner ran into its timeout. Without this lock that deletion
        #removes the workspace while it is being packed, which makes the transfer fail with a FileNotFoundError naming an
        #arbitrary file of the build-output and can leave a partially deleted workspace behind.
        self.transfer_lock = threading.Lock()

    def append_to_log(self, message: str) -> None:
        """Adds a line of the runner itself - as opposed to a line of the program which the job runs - to the log of the
        job. The client prints the log of a job as the output of the delegated build, so this is the place where the
        runner can state something about a job to the one who is waiting for it."""
        with self.lock:
            self.log = self.log+message+"\n"


class SCTaskRunnerServer:
    """HTTP-server that compiles operating-system-bound build-steps on behalf of a (remote) client (see TFCPS_RemoteBuild).
    Per job it extracts the received repository-archive into a fresh, empty workspace, runs the requested program on this
    machine's operating-system, and returns the folder the client stated its result is in. The workspace is deleted as
    soon as the client deletes the job (immediately after fetching the result), so no repository-content remains on the
    runner."""

    def __init__(self, operating_system_name: str, username: str, password: str, work_folder: str = None, sc: ScriptCollectionCore = None):
        self.operating_system_name = operating_system_name
        self.__username = username  # pylint:disable=unused-private-member  # accessed via name-mangling inside the nested request-handler
        self.__password = password  # pylint:disable=unused-private-member  # accessed via name-mangling inside the nested request-handler
        self.work_folder = work_folder if work_folder is not None else os.path.join(GeneralUtilities.get_temp_folder(), "SCTaskRunner")
        if sc is None:
            #The default-loglevel of a ScriptCollectionCore is Warning, while everything this server logs about its
            #lifecycle and its jobs is logged as Information. A runner which uses that default therefore produces no
            #output at all - neither its start nor the jobs it ran become visible in the console-output of the process,
            #which is the only log a permanently running server has. Hence the loglevel is raised here. A caller which
            #passes its own ScriptCollectionCore keeps the loglevel it configured there.
            self.__sc = ScriptCollectionCore()
            self.__sc.log.loglevel = LogLevel.Information
        else:
            self.__sc = sc
        self.__jobs: dict[str, _RunnerJob] = {}
        self.__jobs_lock = threading.Lock()

    @GeneralUtilities.check_arguments
    def run(self, host: str = "0.0.0.0", port: int = 8080, certificate_file: str = None, certificate_key_file: str = None) -> None:
        """Starts the HTTP-server. When both certificate_file and certificate_key_file are given the server is served over
        TLS (https); otherwise it is served over plain http (e.g. when TLS is terminated by a reverse-proxy in front of it)."""
        #Logged before anything else happens, so that the log of the runner also shows a start which did not get as far
        #as listening (for example because the port is occupied or because the certificate can not be loaded).
        self.__sc.log.log(f"Start the SCTaskRunner for operating-system '{self.operating_system_name}' (work-folder: '{self.work_folder}').")
        GeneralUtilities.ensure_directory_exists(self.work_folder)
        server = ThreadingHTTPServer((host, port), self.__create_request_handler())
        protocol = "http"
        if certificate_file is not None and certificate_key_file is not None:
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ssl_context.load_cert_chain(certfile=certificate_file, keyfile=certificate_key_file)
            server.socket = ssl_context.wrap_socket(server.socket, server_side=True)
            protocol = "https"
        self.__sc.log.log(f"SCTaskRunner for operating-system '{self.operating_system_name}' is listening on {protocol}://{host}:{port}.")
        server.serve_forever()

    @GeneralUtilities.check_arguments
    def __start_job(self, archive_stream, archive_size: int, codeunit_name: str, program: str, arguments: list[str], working_directory: str, result_folder: str) -> str:  # pylint:disable=unused-private-member  # accessed via name-mangling inside the nested request-handler
        """Starts a job for the repository-archive which can be read from archive_stream (the body of the request which
        submitted the job; archive_size is its announced length). The archive is taken as a stream instead of as bytes
        because it contains the complete repository of the client and is therefore regularly several hundred megabytes,
        which must not be held in memory in addition to the build which runs afterwards. Only the transfer of the archive
        happens here (it can only be read from the request which brought it); everything which follows belongs to the
        job-thread, see __extract_payload_and_run_job."""
        job_id = str(uuid.uuid4())
        workspace_folder = os.path.join(self.work_folder, job_id)
        # Isolation: each job gets a fresh, empty workspace-folder.
        GeneralUtilities.ensure_directory_does_not_exist(workspace_folder)
        GeneralUtilities.ensure_directory_exists(workspace_folder)
        archive_file = os.path.join(self.work_folder, f"{job_id}.payload.tar.gz")
        try:
            self.__copy_stream_to_file(archive_stream, archive_size, archive_file)
        except Exception:
            #A transfer which did not complete leaves no job behind, so the workspace and the incomplete archive are
            #removed here - the job-thread which would do that is not started in this case.
            GeneralUtilities.ensure_file_does_not_exist(archive_file)
            GeneralUtilities.ensure_directory_does_not_exist(workspace_folder)
            raise
        job = _RunnerJob(job_id, workspace_folder, result_folder)
        with self.__jobs_lock:
            self.__jobs[job_id] = job
        thread = threading.Thread(target=self.__extract_payload_and_run_job, args=(job, archive_file, program, arguments, working_directory), daemon=True)
        thread.start()
        self.__sc.log.log(f"Accepted job '{job_id}': run '{program} {' '.join(arguments)}' in '{working_directory}' of codeunit '{codeunit_name}', result-folder '{result_folder}' ({archive_size} transferred bytes of repository-content).")
        return job_id

    @GeneralUtilities.check_arguments
    def __extract_payload_and_run_job(self, job: _RunnerJob, archive_file: str, program: str, arguments: list[str], working_directory: str) -> None:
        """Extracts the transferred repository-archive into the workspace of the job and runs the requested program
        afterwards. The extraction happens here - in the thread of the job - and not in the request which submitted the
        job, because extracting the repository of a large codeunit takes minutes during which no data flows: the client
        which waits for the answer of its submit, and a reverse-proxy between it and the runner, would run into their
        timeouts although the job is being prepared correctly. Because the job already exists while this runs, the state
        of that preparation is what a client sees and what a failure of it is reported as."""
        try:
            job.append_to_log("Extract the transferred repository into the workspace of the job...")
            with tarfile.open(archive_file, "r:gz") as tar:
                tar.extractall(job.workspace_folder, filter="fully_trusted")
        except Exception as exception:
            self.__end_job_as_failed_because_of_an_internal_error(job, "the transferred repository could not be extracted", exception)
            return
        finally:
            GeneralUtilities.ensure_file_does_not_exist(archive_file)
        self.__sc.log.log(f"Job '{job.job_id}' works on the repository '{self.__get_origin_of_the_transferred_repository(job.workspace_folder)}'.")
        self.__run_job(job, program, arguments, working_directory)

    @GeneralUtilities.check_arguments
    def __get_origin_of_the_transferred_repository(self, workspace_folder: str) -> str:
        """Returns the address of the git-remote 'origin' of the transferred repository. This states which repository a
        job builds without requiring the client to send anything in addition: the repository is transferred including
        its .git-folder anyway. The address is not always available (a repository does not have to have a remote), which
        is stated instead of being treated as an error - this is information for the log and nothing a job depends on."""
        configuration_file = os.path.join(workspace_folder, ".git", "config")
        if not os.path.isfile(configuration_file):
            return "unknown: the transferred content has no git-configuration"
        #Read line-wise and not with configparser, because git indents the entries of a section, which configparser reads
        #as continuations of the value of the previous entry.
        section_is_the_origin_remote = False
        for line in GeneralUtilities.read_lines_from_file(configuration_file):
            stripped_line = line.strip()
            if stripped_line.startswith("["):
                section_is_the_origin_remote = stripped_line.replace(" ", GeneralUtilities.empty_string) == '[remote"origin"]'
            elif section_is_the_origin_remote and stripped_line.startswith("url"):
                return self.__remove_credentials_from_address(stripped_line.split("=", 1)[1].strip())
        return "unknown: the transferred content has no git-remote 'origin'"

    @GeneralUtilities.check_arguments
    def __remove_credentials_from_address(self, address: str) -> str:
        """Removes the user-information of an address like 'https://user:token@host/repository.git'. An address which is
        written to a log must not contain a credential. An address without a scheme is returned unchanged: it is the
        ssh-notation 'user@host:path', whose user is part of the address and not a credential."""
        scheme_separator = "://"
        if scheme_separator not in address:
            return address
        host_and_path = address.split(scheme_separator, 1)[1]
        end_of_the_host = host_and_path.find("/")
        host = host_and_path if end_of_the_host < 0 else host_and_path[:end_of_the_host]
        if "@" not in host:
            return address
        return address.replace(host, host.split("@", 1)[1], 1)

    @GeneralUtilities.check_arguments
    def __copy_stream_to_file(self, stream, amount_of_bytes: int, target_file: str) -> None:
        """Copies exactly amount_of_bytes bytes from stream into target_file, chunk-wise (see
        _transfer_chunk_size_in_bytes for why the content is not read into memory as a whole). A stream which ends early
        is reported as an error instead of resulting in a truncated file which would fail later as an unspecific
        archive-error."""
        remaining_amount_of_bytes = amount_of_bytes
        with open(target_file, "wb") as target_file_object:
            while 0 < remaining_amount_of_bytes:
                chunk = stream.read(min(_transfer_chunk_size_in_bytes, remaining_amount_of_bytes))
                if not chunk:
                    raise ValueError(f"The transferred content ended after {amount_of_bytes-remaining_amount_of_bytes} bytes although {amount_of_bytes} bytes were announced.")
                target_file_object.write(chunk)
                remaining_amount_of_bytes = remaining_amount_of_bytes-len(chunk)

    @GeneralUtilities.check_arguments
    def __run_job(self, job: _RunnerJob, program: str, arguments: list[str], working_directory: str) -> None:
        command_folder = os.path.join(job.workspace_folder, working_directory)
        try:
            self.__sc.log.log(f"Job '{job.job_id}' runs '{program} {' '.join(arguments)}' in '{command_folder}'...")
            moment_of_the_start = time.time()
            moment_of_the_last_progress_log = moment_of_the_start
            amount_of_lines = 0
            with subprocess.Popen([program] + arguments, cwd=command_folder, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace") as process:
                for line in process.stdout:
                    with job.lock:
                        job.log = job.log + line
                    amount_of_lines = amount_of_lines+1
                    if time.time()-moment_of_the_last_progress_log > _interval_between_two_progress_logs_in_seconds:
                        moment_of_the_last_progress_log = time.time()
                        self.__sc.log.log(f"Job '{job.job_id}' is still running (since {round(time.time()-moment_of_the_start)} seconds, {amount_of_lines} lines of output so far).")
                process.wait()
                with job.lock:
                    job.exitcode = process.returncode
                    job.state = "completed" if process.returncode == 0 else "failed"
                    state_of_the_job = job.state
                    exitcode_of_the_job = job.exitcode
                #Logged so that the log of the runner states the result of every job it ran, also when no client is
                #waiting for it any more: a connection to the client can break while a job runs, but the job keeps
                #running and therefore has to end with a stated result on this side too.
                self.__sc.log.log(f"Job '{job.job_id}' is {state_of_the_job} (exitcode: {exitcode_of_the_job}) after {round(time.time()-moment_of_the_start)} seconds.")
                if exitcode_of_the_job != 0:
                    self.__log_the_end_of_the_output_of_the_job(job)
        except Exception as exception:
            self.__end_job_as_failed_because_of_an_internal_error(job, "the program could not be run", exception)

    @GeneralUtilities.check_arguments
    def __log_the_end_of_the_output_of_the_job(self, job: _RunnerJob) -> None:
        """Logs the last lines of the output of a job which did not succeed. The complete output belongs to the job and
        is fetched by the client, but the log of the runner has to state why a build failed too: a client is not
        necessarily still connected when a job ends, and its output is gone with the job."""
        with job.lock:
            lines = GeneralUtilities.string_to_lines(job.log)
        last_lines = lines[-_amount_of_logged_lines_of_a_failed_job:]
        self.__sc.log.log(f"The last {len(last_lines)} of the {len(lines)} lines of the output of job '{job.job_id}' are:")
        for line in last_lines:
            self.__sc.log.log(f"  {line}")

    @GeneralUtilities.check_arguments
    def __end_job_as_failed_because_of_an_internal_error(self, job: _RunnerJob, what_did_not_work: str, exception: Exception) -> None:
        """Ends a job which failed because of the runner itself and not because of what it was asked to build. The
        details of such a failure - stacktraces and paths inside this runner - go to the log of the runner only: they
        state something about the internals of the runner, and the one who waits for the build can not act on them. The
        client gets the statement that the runner failed plus the error-id under which the details are logged, so that
        both sides can be brought together. The output of the program of a job is something else: it is what the client
        asked for and is transferred in full, so that a build which does not compile states why."""
        error_id = str(uuid.uuid4())
        self.__sc.log.log_exception(f"Internal error '{error_id}': job '{job.job_id}' failed because {what_did_not_work}.", exception)
        self.__end_job_as_failed(job, f"The runner could not run this job because {what_did_not_work}. This is a problem of the runner itself; its details are in the log of the runner under the error-id '{error_id}'.")

    @GeneralUtilities.check_arguments
    def __end_job_as_failed(self, job: _RunnerJob, message: str) -> None:
        """Ends a job which could not be run at all with the same shape of result a program which returned a non-zero
        exitcode produces, so that a client always gets a state and an exitcode and does not have to distinguish the
        two cases."""
        job.append_to_log(message)
        with job.lock:
            job.exitcode = -1
            job.state = "failed"

    @GeneralUtilities.check_arguments
    def __create_result_archive(self, job: _RunnerJob) -> str:  # pylint:disable=unused-private-member  # accessed via name-mangling inside the nested request-handler
        """Packs the result-folder of the job and returns the file the archive was written to. The archive is returned
        as a file (and not as bytes) because the build-output of a codeunit regularly has a size of several gigabytes,
        which must not be held in memory. The caller is responsible for deleting the returned file after it was
        transferred."""
        archive_file = os.path.join(self.work_folder, f"{uuid.uuid4()}.result.tar.gz")
        try:
            with tarfile.open(archive_file, "w:gz") as tar:
                tar.add(self.__get_result_folder_of_the_job(job), arcname=".")
        except Exception:
            GeneralUtilities.ensure_file_does_not_exist(archive_file)
            raise
        return archive_file

    @GeneralUtilities.check_arguments
    def __get_result_folder_of_the_job(self, job: _RunnerJob) -> str:  # pylint:disable=unused-private-member  # accessed via name-mangling inside the nested request-handler
        """Returns the folder whose content is the result of the job. A folder outside of the workspace of the job is
        refused: what a runner returns is what the job produced and never something else of this machine."""
        result_folder = os.path.realpath(os.path.join(job.workspace_folder, job.result_folder))
        workspace_folder = os.path.realpath(job.workspace_folder)
        if result_folder != workspace_folder and not result_folder.startswith(workspace_folder+os.sep):
            raise ValueError(f"The result-folder '{job.result_folder}' of job '{job.job_id}' is not inside the workspace of that job.")
        return result_folder

    @GeneralUtilities.check_arguments
    def __delete_job(self, job_id: str) -> None:  # pylint:disable=unused-private-member  # accessed via name-mangling inside the nested request-handler
        with self.__jobs_lock:
            job = self.__jobs.pop(job_id, None)
        if job is not None:
            # The job was already removed from the job-list above, so no further result-request can start for it. This
            # waits for one which is still running (see _RunnerJob.transfer_lock) before the workspace is removed.
            with job.transfer_lock:
                GeneralUtilities.ensure_directory_does_not_exist(job.workspace_folder)

    def __create_request_handler(self):
        outer = self

        class Handler(BaseHTTPRequestHandler):

            #Whether the answer of the request which is currently handled was already begun. After that point the
            #status-line is already on the connection, so a failure can not be answered with a status-code any more.
            __answer_was_begun: bool = False

            def log_message(self, format, *args):  # pylint:disable=redefined-builtin
                outer._SCTaskRunnerServer__sc.log.log((format % args), LogLevel.Debug)

            def __handle(self, handle_request) -> None:
                """Runs the handling of a request and turns everything which it did not handle itself into a defined
                answer. An unexpected exception here is a problem of the runner itself, so its details go to the log of
                the runner only - they state something about the internals of this runner, which the one who waits for a
                build can not act on - while the client gets a 500 naming the error-id under which they are logged.
                Without this the request would stay unanswered completely, which a client sees as a broken connection
                and not as a statement about what happened."""
                self.__answer_was_begun = False
                try:
                    handle_request()
                except Exception as exception:
                    error_id = str(uuid.uuid4())
                    outer._SCTaskRunnerServer__sc.log.log_exception(f"Internal error '{error_id}' while handling '{self.command} {self.path}'.", exception)
                    if not self.__answer_was_begun:
                        self.__send_text(500, f"Internal error of the runner. Its details are in the log of the runner under the error-id '{error_id}'.")

            def __is_authorized(self) -> bool:
                header = self.headers.get("Authorization", GeneralUtilities.empty_string)
                if not header.startswith("Basic "):
                    return False
                try:
                    decoded = base64.b64decode(header[len("Basic "):]).decode("utf-8")
                except Exception:
                    return False
                expected = f"{outer._SCTaskRunnerServer__username}:{outer._SCTaskRunnerServer__password}"
                return decoded == expected

            def __send(self, status: int, body: bytes, content_type: str = "application/octet-stream") -> None:
                self.__answer_was_begun = True
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def __send_file(self, status: int, file: str) -> None:
                """Sends the content of a file without reading it into memory as a whole (see
                _transfer_chunk_size_in_bytes)."""
                self.__answer_was_begun = True
                self.send_response(status)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(os.path.getsize(file)))
                self.end_headers()
                with open(file, "rb") as file_object:
                    shutil.copyfileobj(file_object, self.wfile, _transfer_chunk_size_in_bytes)

            def __send_text(self, status: int, text: str) -> None:
                self.__send(status, text.encode("utf-8"), "text/plain; charset=utf-8")

            def __send_json(self, status: int, obj) -> None:
                self.__send(status, json.dumps(obj).encode("utf-8"), "application/json")

            def __get_job(self, job_id: str):
                with outer._SCTaskRunnerServer__jobs_lock:
                    return outer._SCTaskRunnerServer__jobs.get(job_id, None)

            def do_GET(self):  # pylint:disable=invalid-name
                self.__handle(self.__get)

            def __get(self) -> None:
                if not self.__is_authorized():
                    self.__send_text(401, "Unauthorized")
                    return
                if self.path == "/os":
                    self.__send_text(200, outer.operating_system_name)
                    return
                parts = self.path.strip("/").split("/")
                if len(parts) >= 2 and parts[0] == "jobs":
                    self.__handle_job_get(parts)
                    return
                self.__send_text(404, "Not found")

            def __handle_job_get(self, parts: list[str]) -> None:
                job = self.__get_job(parts[1])
                if job is None:
                    self.__send_text(404, "Unknown job")
                    return
                if len(parts) == 2:
                    with job.lock:
                        self.__send_json(200, {"state": job.state, "exitcode": job.exitcode})
                    return
                if len(parts) == 3 and parts[2] == "logs":
                    with job.lock:
                        self.__send_text(200, job.log)
                    return
                if len(parts) == 3 and parts[2] == "result":
                    with job.lock:
                        ready = job.state == "completed"
                    if not ready:
                        self.__send_text(409, "Job is not completed")
                        return
                    self.__send_result_archive(job)
                    return
                self.__send_text(404, "Not found")

            def __send_result_archive(self, job: _RunnerJob) -> None:
                # The transfer-lock is held while the archive is created and sent, so a DELETE for this job waits instead
                # of removing the workspace while it is being packed (see _RunnerJob.transfer_lock).
                with job.transfer_lock:
                    if not os.path.isdir(outer._SCTaskRunnerServer__get_result_folder_of_the_job(job)):
                        #A job which ran successfully but produced no result-folder is a defined outcome and not an
                        #error of the runner: what a build-step produces is stated by the client which submitted it.
                        self.__send_text(409, f"The job did not produce its result-folder '{job.result_folder}'.")
                        return
                    archive_file = outer._SCTaskRunnerServer__create_result_archive(job)
                    try:
                        self.__send_file(200, archive_file)
                    finally:
                        GeneralUtilities.ensure_file_does_not_exist(archive_file)

            def do_POST(self):  # pylint:disable=invalid-name
                self.__handle(self.__post)

            def __post(self) -> None:
                if not self.__is_authorized():
                    self.__send_text(401, "Unauthorized")
                    return
                if self.path != "/jobs":
                    self.__send_text(404, "Not found")
                    return
                #A request which does not state what is to be run is a defect of the client and not of the runner, so it
                #is answered with what is missing instead of with the 500 of an unexpected failure.
                missing_headers = [header for header in ("Content-Length", "X-Codeunit-Name", "X-Program", "X-Arguments", "X-Result-Folder") if self.headers.get(header) is None]
                if len(missing_headers) > 0:
                    self.__send_text(400, f"The request does not contain the required header(s) {', '.join(missing_headers)}.")
                    return
                content_length = int(self.headers.get("Content-Length"))
                codeunit_name = self.headers.get("X-Codeunit-Name")
                program = self.headers.get("X-Program")
                arguments = json.loads(base64.b64decode(self.headers.get("X-Arguments")).decode("utf-8"))
                working_directory = self.headers.get("X-Working-Directory", ".")
                result_folder = self.headers.get("X-Result-Folder")
                #the body is handed over as a stream (and not read here) so the archive is written to disk chunk-wise, see __start_job.
                job_id = outer._SCTaskRunnerServer__start_job(self.rfile, content_length, codeunit_name, program, arguments, working_directory, result_folder)
                self.__send_json(200, {"job_id": job_id})

            def do_DELETE(self):  # pylint:disable=invalid-name
                self.__handle(self.__delete)

            def __delete(self) -> None:
                if not self.__is_authorized():
                    self.__send_text(401, "Unauthorized")
                    return
                parts = self.path.strip("/").split("/")
                if len(parts) == 2 and parts[0] == "jobs":
                    outer._SCTaskRunnerServer__delete_job(parts[1])
                    self.__send_text(200, "Deleted")
                    return
                self.__send_text(404, "Not found")

        return Handler
