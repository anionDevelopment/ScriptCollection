import os
import subprocess
import tempfile
import uuid
from ..GeneralUtilities import GeneralUtilities


class SandboxEgressProxy:
    """Enforces an allowlist of domains for the agent-sandbox. For one run it creates an internal docker-network (which has no route to the outside)
    and a Squid-container which is attached to this network and to the default bridge-network, so only the proxy can reach the outside.
    The proxy only allows CONNECT to port 443 of the allowed domains (TLS is tunneled, not intercepted).
    The sandbox is attached only to the internal network, gets the proxy announced by the usual proxy-environment-variables and has no DNS-server
    for external names, so the restriction is enforced outside of the sandbox and can not be lifted from inside of it."""
    proxy_port: int = 3128
    squid_configuration_file_in_container: str = "/etc/squid/squid.conf"
    access_log_file_in_container: str = "/var/log/squid/access.log"
    __allowed_domains: list[str] = None
    __image: str = None
    __verbose: bool = None
    __network_name: str = None
    __proxy_container_name: str = None
    __configuration_file: str = None
    __network_was_created: bool = None
    __proxy_container_was_created: bool = None

    @GeneralUtilities.check_arguments
    def __init__(self, allowed_domains: list[str], image: str, verbose: bool):
        # allowed_domains must already be validated (see SandboxNetworkConfiguration). image is the image-address including tag.
        GeneralUtilities.assert_condition(len(allowed_domains) > 0, "The egress-proxy requires at least one allowed domain.")
        self.__allowed_domains = allowed_domains
        self.__image = image
        self.__verbose = verbose
        # The run-id makes the names unique, so parallel runs do not collide. The prefix "scrais-" makes leftovers of a killed run recognizable.
        run_id = uuid.uuid4().hex[:12]
        self.__network_name = f"scrais-{run_id}"
        self.__proxy_container_name = f"scrais-proxy-{run_id}"
        self.__network_was_created = False
        self.__proxy_container_was_created = False

    @staticmethod
    @GeneralUtilities.check_arguments
    def get_squid_configuration(allowed_domains: list[str]) -> str:
        # "dstdomain" uses the same syntax as the allowlist (a leading dot includes the subdomains). "-n" disables reverse-DNS-lookups, so a CONNECT to an
        # IP-address can not match because of its reverse name. Plain HTTP and every port except 443 are denied. Nothing is cached. The access-log is
        # written unbuffered to a file in the container, so the denied requests can be read with "docker exec" (the output of Squid does not reach
        # "docker logs" when the image runs Squid under a service-manager like pebble). The pinger is disabled because it needs the capability NET_RAW,
        # which the proxy-container does not get.
        lines = [
            f"http_port {SandboxEgressProxy.proxy_port}",
            f"acl allowed_domains dstdomain -n {' '.join(allowed_domains)}",
            "acl https_port port 443",
            "http_access deny !CONNECT",
            "http_access deny CONNECT !https_port",
            "http_access allow CONNECT allowed_domains",
            "http_access deny all",
            "cache deny all",
            f"access_log stdio:{SandboxEgressProxy.access_log_file_in_container}",
            "buffered_logs off",
            "pinger_enable off",
        ]
        return "\n".join(lines) + "\n"

    @GeneralUtilities.check_arguments
    def start(self) -> None:
        # stop() must be called afterwards in any case (also if this function fails), because it removes everything which was created until then.
        with tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False, newline="\n", encoding="utf-8") as configuration_file_handle:
            self.__configuration_file = configuration_file_handle.name
            configuration_file_handle.write(SandboxEgressProxy.get_squid_configuration(self.__allowed_domains))
        # The configuration-file must be readable by the (unprivileged) user of squid in the container.
        os.chmod(self.__configuration_file, 0o644)
        self.__run_docker(["network", "create", "--internal", self.__network_name])
        self.__network_was_created = True
        # The container is marked as created before "docker run", because a failing start can leave a created container behind.
        self.__proxy_container_was_created = True
        # Squid runs as an unprivileged user in the image and needs no capability, so the proxy-container gets none.
        self.__run_docker(["run", "--detach", "--name", self.__proxy_container_name, "--network", self.__network_name, "--cap-drop", "all", "--security-opt", "no-new-privileges:true", "--volume", f"{self.__configuration_file.replace(os.sep, '/')}:{SandboxEgressProxy.squid_configuration_file_in_container}:ro", self.__image])
        self.__run_docker(["network", "connect", "bridge", self.__proxy_container_name])

    @GeneralUtilities.check_arguments
    def get_sandbox_docker_arguments(self) -> list[str]:
        # The proxy is announced in both spellings because tools differ in which one they read. The address is no secret, so the values are passed as arguments.
        # "--dns 127.0.0.1" lets the resolution of external names fail (nothing listens there); the name of the proxy-container is still resolved by the
        # embedded DNS of docker.
        proxy_address = f"http://{self.__proxy_container_name}:{SandboxEgressProxy.proxy_port}"
        result = ["--network", self.__network_name, "--dns", "127.0.0.1"]
        for environment_variable_name in ["HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy"]:
            result = result + ["--env", f"{environment_variable_name}={proxy_address}"]
        return result

    @GeneralUtilities.check_arguments
    def stop(self) -> None:
        # Removes everything which start() created. A failure of the removal does not hide the result of the run; it is reported with the name of the
        # resource, so it can be removed manually.
        if self.__proxy_container_was_created:
            if self.__verbose:
                self.__print_denied_requests()
            self.__remove(["rm", "--force", self.__proxy_container_name], f"proxy-container '{self.__proxy_container_name}'")
            self.__proxy_container_was_created = False
        if self.__network_was_created:
            self.__remove(["network", "rm", self.__network_name], f"network '{self.__network_name}'")
            self.__network_was_created = False
        if self.__configuration_file is not None:
            GeneralUtilities.ensure_file_does_not_exist(self.__configuration_file)
            self.__configuration_file = None

    @GeneralUtilities.check_arguments
    def __print_denied_requests(self) -> None:
        access_log = subprocess.run(["docker", "exec", self.__proxy_container_name, "cat", SandboxEgressProxy.access_log_file_in_container], capture_output=True, text=True, check=False)
        denied_requests = [line for line in access_log.stdout.splitlines() if "TCP_DENIED" in line]
        if len(denied_requests) == 0:
            GeneralUtilities.write_message_to_stderr("The egress-proxy denied no request.")
        else:
            GeneralUtilities.write_message_to_stderr("The egress-proxy denied the following requests:")
            for denied_request in denied_requests:
                GeneralUtilities.write_message_to_stderr(f"  {denied_request}")

    @GeneralUtilities.check_arguments
    def __remove(self, docker_arguments: list[str], resource_description: str) -> None:
        result = subprocess.run(["docker"] + docker_arguments, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            GeneralUtilities.write_message_to_stderr(f"Warning: The {resource_description} of the sandbox could not be removed and must be removed manually: {result.stderr.strip()}")

    @GeneralUtilities.check_arguments
    def __run_docker(self, docker_arguments: list[str]) -> None:
        result = subprocess.run(["docker"] + docker_arguments, capture_output=True, text=True, check=False)
        GeneralUtilities.assert_condition(result.returncode == 0, f"\"docker {' '.join(docker_arguments)}\" failed with exit-code {result.returncode}: {result.stderr.strip()}")
