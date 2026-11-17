from ..SecurityCheckBase import SecurityCheckBase
from ..SecurityFinding import SecurityFinding, SecurityFindingSeverity
from ..SystemAccessBase import SystemAccessBase
from ..SystemEntities import SocketInformation, ProcessInformation


def _describe_socket(socket_information: SocketInformation, processes_by_inode: dict[int, list[ProcessInformation]]) -> str:
    processes = processes_by_inode.get(socket_information.inode, [])
    owner = "; ".join(process.describe() for process in processes) if len(processes) > 0 else "unknown process"
    return f"{socket_information.protocol} {socket_information.local_address}:{socket_information.local_port} -> {socket_information.remote_address}:{socket_information.remote_port} (owner: {owner})"


class PromiscuousNetworkInterfacesCheck(SecurityCheckBase):
    """A network-interface in promiscuous mode receives all packets, which is used for sniffing.
    Interfaces which are ports of a bridge (for example the veth-interfaces of docker) are promiscuous by design and therefore ignored."""

    __flag_promiscuous: int = 0x100

    def run(self, system: SystemAccessBase) -> list[SecurityFinding]:
        result: list[SecurityFinding] = []
        for interface in sorted(system.list_folder("/sys/class/net") or []):
            flags = system.read_text(f"/sys/class/net/{interface}/flags")
            if flags is None or system.path_exists(f"/sys/class/net/{interface}/brport"):
                continue
            if int(flags.strip(), 16) & PromiscuousNetworkInterfacesCheck.__flag_promiscuous != 0:
                result.append(self.create_finding(SecurityFindingSeverity.Mid, f"Network-interface \"{interface}\" is in promiscuous mode (possible sniffing)."))
        return result


class SuspiciousListeningPortsCheck(SecurityCheckBase):
    """Ports which are typically used by backdoors and botnets."""

    suspicious_ports: set[int] = {1337, 1524, 4444, 6666, 6667, 12345, 27374, 31337, 54321}
    __state_tcp_listening: str = "0A"
    __state_udp_unconnected: str = "07"

    def run(self, system: SystemAccessBase) -> list[SecurityFinding]:
        processes_by_inode: dict[int, list[ProcessInformation]] | None = None
        result: list[SecurityFinding] = []
        for socket_information in system.get_sockets():
            is_listening = (socket_information.protocol.startswith("tcp") and socket_information.state == SuspiciousListeningPortsCheck.__state_tcp_listening) or (socket_information.protocol.startswith("udp") and socket_information.state == SuspiciousListeningPortsCheck.__state_udp_unconnected)
            if is_listening and socket_information.local_port in SuspiciousListeningPortsCheck.suspicious_ports:
                if processes_by_inode is None:
                    processes_by_inode = system.get_processes_by_socket_inode()
                result.append(self.create_finding(SecurityFindingSeverity.Mid, f"Listening on a port which is typical for backdoors: {_describe_socket(socket_information, processes_by_inode)}"))
        return result


class ConnectionsToMiningPoolPortsCheck(SecurityCheckBase):
    """Established outgoing connections to ports which are typically used by crypto-mining-pools."""

    mining_pool_ports: set[int] = {3333, 3334, 4444, 5555, 7777, 14433, 14444, 45560, 45700}
    __state_tcp_established: str = "01"
    __state_tcp_listening: str = "0A"

    def run(self, system: SystemAccessBase) -> list[SecurityFinding]:
        processes_by_inode: dict[int, list[ProcessInformation]] | None = None
        result: list[SecurityFinding] = []
        sockets = system.get_sockets()
        # a connection whose local port is a listening port is an incoming connection, so its remote port is only the ephemeral port of the client.
        listening_ports = {socket_information.local_port for socket_information in sockets if socket_information.protocol.startswith("tcp") and socket_information.state == ConnectionsToMiningPoolPortsCheck.__state_tcp_listening}
        for socket_information in sockets:
            if socket_information.protocol.startswith("tcp") and socket_information.state == ConnectionsToMiningPoolPortsCheck.__state_tcp_established and socket_information.remote_port in ConnectionsToMiningPoolPortsCheck.mining_pool_ports and socket_information.local_port not in listening_ports:
                if processes_by_inode is None:
                    processes_by_inode = system.get_processes_by_socket_inode()
                result.append(self.create_finding(SecurityFindingSeverity.Mid, f"Connection to a port which is typical for crypto-mining-pools: {_describe_socket(socket_information, processes_by_inode)}"))
        return result
