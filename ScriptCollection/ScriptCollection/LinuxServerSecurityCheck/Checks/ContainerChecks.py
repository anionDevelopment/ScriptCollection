import json
from ..SecurityCheckBase import SecurityCheckBase
from ..SecurityFinding import SecurityFinding, SecurityFindingSeverity
from ..SystemAccessBase import SystemAccessBase


class PrivilegedDockerContainersCheck(SecurityCheckBase):
    """A privileged container, a container in the pid-namespace of the host or a container with the root-folder of the host mounted
    has full access to the host. Attackers who can access the docker-daemon use such containers to get root on the host."""

    def run(self, system: SystemAccessBase) -> list[SecurityFinding]:
        if not system.program_is_available("docker"):
            return []
        container_ids_result = system.run_program("docker", ["ps", "--quiet", "--no-trunc"])
        if container_ids_result.exit_code != 0:
            return [self.create_finding(SecurityFindingSeverity.Low, f"Docker-containers can not be checked because \"docker ps\" failed: {container_ids_result.stderr.strip()}")]
        container_ids = [line.strip() for line in container_ids_result.stdout.splitlines() if line.strip() != ""]
        if len(container_ids) == 0:
            return []
        inspect_result = system.run_program("docker", ["inspect"] + container_ids)
        if inspect_result.exit_code != 0:
            raise ValueError(f"\"docker inspect\" failed with exitcode {inspect_result.exit_code}: {inspect_result.stderr.strip()}")
        result: list[SecurityFinding] = []
        for container in json.loads(inspect_result.stdout):
            name = str(container.get("Name", "")).lstrip("/")
            host_configuration = container.get("HostConfig") or {}
            if host_configuration.get("Privileged") is True:
                result.append(self.create_finding(SecurityFindingSeverity.Low, f"Docker-container \"{name}\" runs privileged."))
            if host_configuration.get("PidMode") == "host":
                result.append(self.create_finding(SecurityFindingSeverity.Low, f"Docker-container \"{name}\" runs in the pid-namespace of the host."))
            for mount in container.get("Mounts") or []:
                if mount.get("Source") == "/":
                    result.append(self.create_finding(SecurityFindingSeverity.Mid, f"Docker-container \"{name}\" has the root-folder of the host mounted at \"{mount.get('Destination')}\"."))
        return result
