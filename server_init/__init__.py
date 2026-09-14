from pathlib import Path

from pyinfra.operations import dnf
from pyinfra.operations import files
from pyinfra.operations import server
from pyinfra.operations import systemd

from cli.command_registry import Command
from cli.command_registry import SubCommand

SOURCE_DIR = Path(__file__).parent.resolve()


class Setup(SubCommand):
    """
    Performs common setup required to deploy services on a fresh server.
    """

    @staticmethod
    def install_required_packages():
        dnf.packages(
            packages=[
                "acl",
                "podman",
                "firewalld",
            ],
            present=True,
            latest=True,
            update=True,

        )

    @staticmethod
    def configure_journald():
        journald_conf_dir = "/etc/systemd/journald.conf.d"

        files.directory(
            path="/etc/systemd/journald.conf.d",
            mode=755,
            _sudo=True,
        )

        files.put(
            src=str(SOURCE_DIR / "journald.conf"),
            dest=f"{journald_conf_dir}/journald.conf",
            _sudo=True,
        )

        systemd.service(
            service="systemd-journald.service",
            restarted=True,
            _sudo=True,
        )

        server.shell(
            commands="journalctl --flush",
            _sudo=True,
        )

    @staticmethod
    def set_unprivileged_port_start(start: int):
        server.sysctl(
            key="net.ipv4.ip_unprivileged_port_start",
            value=start,
            persist=True,
            persist_file="/etc/sysctl.d/99-unprivileged-port-start.conf",
            _sudo=True,
        )

        server.shell(
            commands="sysctl --system",
            _sudo=True,
        )

    @staticmethod
    def expose_http_and_https_ports():
        server.shell(
            commands=[
                "firewall-cmd --add-service=http --add-service=https --permanent",
                "firewall-cmd --reload",
            ],
            _sudo=True,
        )

    def run(self):
        self.install_required_packages()
        self.configure_journald()
        self.set_unprivileged_port_start(80)
        self.expose_http_and_https_ports()


# noinspection pep8-naming
class Server_Init(Command):
    """
    Manage server-wide configuration.
    """
    subcommands = [
        Setup,
    ]
