from pathlib import Path

from pyinfra.operations import files

from cli.registry import Command
from cli.registry import step
from cli.subcommand_helpers import make_service_subcommand

DEFAULT_SERVICE_USER = "nginx"
DEFAULT_SERVICE_HOME = Path("/srv") / DEFAULT_SERVICE_USER

SOURCE_DIR = Path(__file__).parent.resolve()

NginxSubCommand = make_service_subcommand(DEFAULT_SERVICE_USER, DEFAULT_SERVICE_HOME)


class Setup(NginxSubCommand):
    """
    Performs initial setup required to deploy Nginx on a fresh server.
    """

    @step
    def ensure_conf_dir(self):
        # This is done to allow services to place their config files here `nginx deploy` has been run.
        files.directory(
            path=str(self.service_home / "conf.d"),
            user=self.service_user,
            group=self.service_user,
            _sudo=True,
            _sudo_user=self.service_user,
        )

    def run(self):
        self.create_service_user()
        self.ensure_conf_dir()


class Deploy(NginxSubCommand):
    """
    Deploys Nginx according to the current configuration.
    Requires that the setup command has run successfully at least once.
    Also requires `server-init setup` to have run successfully (to allow binding to ports 80 and 443).
    """

    @step
    def sync_certs(self):
        files.sync(
            src=str(SOURCE_DIR / "certs"),
            dest=str(self.service_home / "certs"),
            user=self.service_user,
            group=self.service_user,
            mode="400",
            dir_mode="700",
            delete=True,
            _sudo=True,
            _sudo_user=self.service_user,
        )

    @step
    def sync_conf_dir(self):
        files.sync(
            src=str(SOURCE_DIR / "conf.d"),
            dest=str(self.service_home / "conf.d"),
            user=self.service_user,
            group=self.service_user,
            # Do not set delete=True here, as it will delete configs placed by other services.
            _sudo=True,
            _sudo_user=self.service_user,
        )

    def run(self):
        self.sync_certs()
        self.sync_conf_dir()
        self.generate_quadlets(SOURCE_DIR, service_home=self.service_home)
        self.systemd_daemon_reload()
        self.restart_service("nginx.service")


class Nginx(Command):
    """Deploys Nginx."""
    subcommands = [
        Setup,
        Deploy,
    ]
