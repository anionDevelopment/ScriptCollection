import os
import json
import base64
import ssl
import uuid
import threading
import subprocess
import tarfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ..GeneralUtilities import GeneralUtilities
from ..ScriptCollectionCore import ScriptCollectionCore
from ..SCLog import LogLevel


class _RunnerJob:
    def __init__(self, workspace_folder: str, codeunit_name: str):
        self.workspace_folder = workspace_folder
        self.codeunit_name = codeunit_name
        self.state = "running"  # "running" | "completed" | "failed"
        self.exitcode = None
        self.log = GeneralUtilities.empty_string
        self.lock = threading.Lock()


class SCTaskRunnerServer:
    """HTTP-server that compiles operating-system-bound build-steps on behalf of a (remote) client (see TFCPS_RemoteBuild).
    Per job it extracts the received repository-archive into a fresh, empty workspace, runs the requested program on this
    machine's operating-system, and returns the codeunit-folder. The workspace is deleted as soon as the client deletes the
    job (immediately after fetching the result), so no repository-content remains on the runner."""

    def __init__(self, operating_system_name: str, username: str, password: str, work_folder: str = None, sc: ScriptCollectionCore = None):
        self.operating_system_name = operating_system_name
        self.__username = username
        self.__password = password
        self.work_folder = work_folder if work_folder is not None else os.path.join(GeneralUtilities.get_temp_folder(), "SCTaskRunner")
        self.__sc = sc if sc is not None else ScriptCollectionCore()
        self.__jobs: dict[str, _RunnerJob] = {}
        self.__jobs_lock = threading.Lock()

    @GeneralUtilities.check_arguments
    def run(self, host: str = "0.0.0.0", port: int = 8080, certificate_file: str = None, certificate_key_file: str = None) -> None:
        """Starts the HTTP-server. When both certificate_file and certificate_key_file are given the server is served over
        TLS (https); otherwise it is served over plain http (e.g. when TLS is terminated by a reverse-proxy in front of it)."""
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
    def __start_job(self, archive_bytes: bytes, codeunit_name: str, program: str, arguments: list[str], working_directory: str) -> str:
        job_id = str(uuid.uuid4())
        workspace_folder = os.path.join(self.work_folder, job_id)
        # Isolation: each job gets a fresh, empty workspace-folder.
        GeneralUtilities.ensure_directory_does_not_exist(workspace_folder)
        GeneralUtilities.ensure_directory_exists(workspace_folder)
        archive_file = os.path.join(self.work_folder, f"{job_id}.payload.tar.gz")
        GeneralUtilities.write_binary_to_file(archive_file, archive_bytes)
        try:
            with tarfile.open(archive_file, "r:gz") as tar:
                tar.extractall(workspace_folder, filter="fully_trusted")
        finally:
            GeneralUtilities.ensure_file_does_not_exist(archive_file)
        job = _RunnerJob(workspace_folder, codeunit_name)
        with self.__jobs_lock:
            self.__jobs[job_id] = job
        thread = threading.Thread(target=self.__run_job, args=(job, program, arguments, working_directory), daemon=True)
        thread.start()
        return job_id

    @GeneralUtilities.check_arguments
    def __run_job(self, job: _RunnerJob, program: str, arguments: list[str], working_directory: str) -> None:
        command_folder = os.path.join(job.workspace_folder, working_directory)
        try:
            self.__sc.log.log(f"Run '{program} {' '.join(arguments)}' in '{command_folder}'...")
            process = subprocess.Popen([program] + arguments, cwd=command_folder, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
            for line in process.stdout:
                with job.lock:
                    job.log = job.log + line
            process.wait()
            with job.lock:
                job.exitcode = process.returncode
                job.state = "completed" if process.returncode == 0 else "failed"
        except Exception as exception:
            with job.lock:
                job.log = job.log + f"\nException while running the program: {exception}\n"
                job.exitcode = -1
                job.state = "failed"

    @GeneralUtilities.check_arguments
    def __get_result_archive(self, job: _RunnerJob) -> bytes:
        codeunit_folder = os.path.join(job.workspace_folder, job.codeunit_name)
        archive_file = os.path.join(self.work_folder, f"{uuid.uuid4()}.result.tar.gz")
        try:
            with tarfile.open(archive_file, "w:gz") as tar:
                tar.add(codeunit_folder, arcname=".")
            return GeneralUtilities.read_binary_from_file(archive_file)
        finally:
            GeneralUtilities.ensure_file_does_not_exist(archive_file)

    @GeneralUtilities.check_arguments
    def __delete_job(self, job_id: str) -> None:
        with self.__jobs_lock:
            job = self.__jobs.pop(job_id, None)
        if job is not None:
            GeneralUtilities.ensure_directory_does_not_exist(job.workspace_folder)

    def __create_request_handler(self):
        outer = self

        class Handler(BaseHTTPRequestHandler):

            def log_message(self, format, *args):  # pylint:disable=redefined-builtin
                outer._SCTaskRunnerServer__sc.log.log((format % args), LogLevel.Debug)

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
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def __send_text(self, status: int, text: str) -> None:
                self.__send(status, text.encode("utf-8"), "text/plain; charset=utf-8")

            def __send_json(self, status: int, obj) -> None:
                self.__send(status, json.dumps(obj).encode("utf-8"), "application/json")

            def __get_job(self, job_id: str):
                with outer._SCTaskRunnerServer__jobs_lock:
                    return outer._SCTaskRunnerServer__jobs.get(job_id, None)

            def do_GET(self):  # pylint:disable=invalid-name
                if not self.__is_authorized():
                    self.__send_text(401, "Unauthorized")
                    return
                if self.path == "/os":
                    self.__send_text(200, outer.operating_system_name)
                    return
                parts = self.path.strip("/").split("/")
                if len(parts) >= 2 and parts[0] == "jobs":
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
                        self.__send(200, outer._SCTaskRunnerServer__get_result_archive(job))
                        return
                self.__send_text(404, "Not found")

            def do_POST(self):  # pylint:disable=invalid-name
                if not self.__is_authorized():
                    self.__send_text(401, "Unauthorized")
                    return
                if self.path != "/jobs":
                    self.__send_text(404, "Not found")
                    return
                content_length = int(self.headers.get("Content-Length", "0"))
                archive_bytes = self.rfile.read(content_length)
                codeunit_name = self.headers.get("X-Codeunit-Name")
                program = self.headers.get("X-Program")
                arguments = json.loads(base64.b64decode(self.headers.get("X-Arguments", "")).decode("utf-8"))
                working_directory = self.headers.get("X-Working-Directory", ".")
                job_id = outer._SCTaskRunnerServer__start_job(archive_bytes, codeunit_name, program, arguments, working_directory)
                self.__send_json(200, {"job_id": job_id})

            def do_DELETE(self):  # pylint:disable=invalid-name
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
