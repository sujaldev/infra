import secrets
import shlex
from io import StringIO
from pathlib import Path

from dotenv import dotenv_values
from jinja2 import Environment
from jinja2 import DictLoader
from pyinfra import host
from pyinfra import logger
from pyinfra.api.facts import FactBase
from pyinfra.facts.hardware import Cpus
from pyinfra.operations import files
from pyinfra.operations import server
from pyinfra.operations import systemd

from cli.registry import Command
from cli.subcommand_helpers import make_service_subcommand

DEFAULT_SERVICE_USER = "erpnext"
DEFAULT_SERVICE_HOME = Path("/srv") / DEFAULT_SERVICE_USER

SOURCE_DIR = Path(__file__).parent.resolve()
TEMPLATE_DOTENV_PATH = SOURCE_DIR / "template.env.jinja"

ERPNextSubCommand = make_service_subcommand(DEFAULT_SERVICE_USER, DEFAULT_SERVICE_HOME)


# noinspection method-may-be-static,method-overriding
class PodmanSecretExists(FactBase):
    def requires_command(self, secret_name: str) -> str:
        return "podman"

    def command(self, secret_name: str) -> str:
        return f'podman secret exists {shlex.quote(secret_name)} && echo true || echo false'

    def process(self, output: str) -> bool:
        return output[0].strip() == "true"


class Setup(ERPNextSubCommand):
    """
    Performs initial setup required to deploy ERPNext on a fresh server.
    """

    param_help = {
        "sites": "Comma-separated list of sites to initialize using `bench new-site`.",
        "gunicorn_workers": "Set to 0 to automatically calculate with the formula (2 x number of CPU cores) + 1.",
        "db_password": "Leave empty to generate a random password. "
                       "An existing password file will only be overridden if a non-empty value is explicitly provided.",
        "podman_network_subnet": "Subnet to use for erpnext.network. "
                                 "The same value is passed to UPSTREAM_REAL_IP_ADDRESS to configure the public nginx "
                                 "instance as a trusted source."
    }

    def __init__(
            self,
            sites: str,
            nginx_proxy_hosts: str,
            db_password: str,
            gunicorn_workers: int = 0,
            podman_network_subnet: str = "10.80.0.0/24",  # The default podman allocation pool starts from 10.88.0.0/16
            *args,
            **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self.sites = sites
        self.nginx_proxy_hosts = nginx_proxy_hosts
        self.db_password = db_password
        self.gunicorn_workers = gunicorn_workers if gunicorn_workers != 0 else host.get_fact(Cpus) * 2 + 1
        self.podman_network_subnet = podman_network_subnet

    def render_dotenv_template(self) -> str:
        with open(TEMPLATE_DOTENV_PATH) as file:
            env = Environment(loader=DictLoader({
                "template": file.read()
            }))
            return env.get_template("template").render(
                gunicorn_workers=self.gunicorn_workers,
                nginx_proxy_hosts=self.nginx_proxy_hosts,
                podman_network_subnet=self.podman_network_subnet,
            )

    def generate_env(self):
        # noinspection bad-argument-type
        files.template(
            src=str(TEMPLATE_DOTENV_PATH),
            dest=str(self.service_home / ".env"),
            mode=600,
            user=self.service_user,
            group=self.service_user,
            _sudo=True,
            _sudo_user=self.service_user,

            gunicorn_workers=self.gunicorn_workers,
            nginx_proxy_hosts=self.nginx_proxy_hosts,
            podman_network_subnet=self.podman_network_subnet,
        )

    def generate_db_password_secret(self, secret_name: str = "DB_PASSWORD"):
        secret_already_exists = host.get_fact(
            PodmanSecretExists,
            secret_name,
            _sudo=True,
            _sudo_user=self.service_user,
            _chdir=str(self.service_home),
        )
        if secret_already_exists:
            if self.db_password:
                overwrite = input(
                    "An explicit non-empty DB_PASSWORD was provided, but a value already exists. "
                    "Overwrite the existing secret? [y/N]: "
                ).lower() == "y"

                if not overwrite:
                    return
            else:
                logger.info(
                    "DB_PASSWORD secret already exists and no password was provided, "
                    "will skip creation..."
                )
                return
        else:
            if not self.db_password:
                logger.info(
                    "DB_PASSWORD secret does not exist and no password was provided, "
                    "will auto-generate a secure password value..."
                )
                self.db_password = secrets.token_urlsafe(32)

        # The reason to create the password using a file as the source instead of an env var is to prevent leaking the
        # password through process inspection.
        db_password_buffer = str(self.service_home / ".db_password_buffer")

        files.put(
            src=StringIO(self.db_password),
            dest=db_password_buffer,
            mode=400,
            user=self.service_user,
            group=self.service_user,
            _sudo=True,
        )

        server.shell(
            commands=[
                f"podman secret create --replace {shlex.quote(secret_name)} {shlex.quote(db_password_buffer)}"],
            _sudo=True,
            _sudo_user=self.service_user,
            _chdir=str(self.service_home),
        )

        files.file(
            path=db_password_buffer,
            present=False,
            _sudo=True,
        )

    def sync_frappe_docker_repo(self):
        # TODO: rsync directly as service_user to final destination
        #       when https://github.com/pyinfra-dev/pyinfra/pull/1950 is released.
        files.rsync(
            src=str(SOURCE_DIR / "frappe_docker"),
            dest="/tmp",
            flags=["-rlpt", "--delete", "--exclude=.git"],
            # _sudo=True,
            # _sudo_user=service_user,
        )

        # `files.copy` cannot be used here because it will raise an exception if the source directory does not exist during
        # plan-time. On a fresh install, the directory does not exist yet because the preceding rsync operation executes
        # after this check.
        server.shell(
            commands=f"cp -a /tmp/frappe_docker {shlex.quote(str(self.service_home))}",
            _sudo=True,
            _sudo_user=self.service_user,
        )

    def sync_apps_json(self):
        files.put(
            src=str(SOURCE_DIR / "apps.json"),
            dest=str(self.service_home / "apps.json"),
            user=self.service_user,
            group=self.service_user,
            mode=600,
            _sudo=True,
            _sudo_user=self.service_user,
        )

    def build_image(self):
        systemd.service(
            service="erpnext-custom-build.service",
            user_mode=True,
            user_name=self.service_user,
            _sudo=True,
        )

    def init_sites(self):
        for site in self.sites.split(","):
            systemd.service(
                service=f"erpnext-init-site@{site}.service",
                running=True,
                user_mode=True,
                user_name=self.service_user,
                _sudo=True,
            )

    def run(self):
        self.create_service_user()
        self.generate_env()
        self.generate_db_password_secret()

        dotenv = dotenv_values(stream=StringIO(self.render_dotenv_template()))
        self.generate_quadlets(SOURCE_DIR, **dotenv)

        self.copy_systemd_files()
        self.systemd_daemon_reload()
        self.sync_frappe_docker_repo()
        self.sync_apps_json()
        self.build_image()
        self.restart_service("erpnext.target")
        self.init_sites()


class Deploy(ERPNextSubCommand):
    """
    Deploys ERPNext according to the current configuration.
    Requires that the setup command has run successfully at least once.
    """


class ERPNext(Command):
    """
    Manage ERPNext deployment.
    """
    subcommands = [
        Setup,
        Deploy,
    ]
