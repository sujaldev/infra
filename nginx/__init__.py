import shlex
from pathlib import Path

from pyinfra.operations import files
from pyinfra.operations import server
from pyinfra.operations import systemd

from cli.command_registry import Command
from cli.subcommand_helpers import make_service_subcommand

DEFAULT_SERVICE_USER = "nginx"
DEFAULT_SERVICE_HOME = Path("/srv") / DEFAULT_SERVICE_USER

SOURCE_DIR = Path(__file__).parent.resolve()

NginxSubCommand = make_service_subcommand(DEFAULT_SERVICE_USER, DEFAULT_SERVICE_HOME)


class Setup(NginxSubCommand):
    """
    Performs initial setup required to deploy Nginx on a fresh server.
    """
    param_help = {
        "erpnext_sites": "Comma-separated list of hosts to proxy to the ERPNext frontend container.",
    }

    def __init__(self, erpnext_sites: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.erpnext_sites = erpnext_sites

    def generate_site_configs(self):
        erpnext_sites = [site.strip() for site in self.erpnext_sites.split(",") if site.strip()]

        conf_dir = self.service_home / "conf.d"
        src_conf_dir = SOURCE_DIR / "conf.d"

        files.directory(
            path=str(conf_dir),
            user=self.service_user,
            group=self.service_user,
            _sudo=True,
            _sudo_user=self.service_user,
        )

        for site in erpnext_sites:
            # noinspection bad-argument-type
            files.template(
                src=str(src_conf_dir / "erpnext.conf.jinja"),
                dest=str(conf_dir / f"erpnext-{site}.conf"),
                user=self.service_user,
                group=self.service_user,
                _sudo=True,
                _sudo_user=self.service_user,
                server_name=site,
            )

        for path in src_conf_dir.iterdir():
            if not path.is_file() or path.suffix != ".conf":
                continue

            files.put(
                src=str(path),
                dest=str(conf_dir / path.name),
                user=self.service_user,
                group=self.service_user,
                _sudo=True,
                _sudo_user=self.service_user,
            )

    def run(self):
        self.create_service_user()
        self.generate_site_configs()


class Deploy(NginxSubCommand):
    """
    Deploys Nginx according to the current configuration.
    Requires that the setup command has run successfully at least once.
    """

    def copy_certs(self):
        certs_dir = self.service_home / "certs"

        files.directory(
            path=str(certs_dir),
            user=self.service_user,
            group=self.service_user,
            mode=700,
            _sudo=True,
            _sudo_user=self.service_user,
        )

        for path in (SOURCE_DIR / "certs").iterdir():
            if not path.is_file() or path.suffix != ".pem":
                continue

            files.put(
                src=str(path),
                dest=str(certs_dir / path.name),
                user=self.service_user,
                group=self.service_user,
                mode=400,
                _sudo=True,
            )

    def run(self):
        self.copy_certs()
        self.generate_quadlets(SOURCE_DIR, service_home=self.service_home)
        self.systemd_daemon_reload()
        self.restart_service("nginx.service")


class Nginx(Command):
    """Manage Nginx deployment."""
    subcommands = [
        Setup,
        Deploy,
    ]
