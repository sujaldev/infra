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
from pyinfra.facts.server import Users
from pyinfra.operations import files
from pyinfra.operations import server
from pyinfra.operations import systemd

from cli.utils import ServiceCommandRegistry

cli = ServiceCommandRegistry(
    name="erpnext",
    help_str="Manage ERPNext deployment."
)

DEFAULT_SERVICE_USER = "erpnext"
DEFAULT_SERVICE_HOME = Path("/srv") / DEFAULT_SERVICE_USER

SOURCE_DIR = Path(__file__).parent.resolve()
TEMPLATE_DOTENV_PATH = SOURCE_DIR / "template.env.jinja"


# noinspection method-may-be-static,method-overriding
class PodmanSecretExists(FactBase):
    def requires_command(self, secret_name: str) -> str:
        return "podman"

    def command(self, secret_name: str) -> str:
        return f'podman secret exists {shlex.quote(secret_name)} && echo true || echo false'

    def process(self, output: str) -> bool:
        return output[0].strip() == "true"


def create_service_user(service_user: str, service_home: Path):
    server.user(
        name=f"Ensure service user {service_user!r} exists",
        user=service_user,
        home=str(service_home),
        shell="/usr/sbin/nologin",
        create_home=True,
        ensure_home=True,
        _sudo=True,
    )

    server.shell(
        name=f"Enable lingering for {service_user!r}",
        commands=[f"loginctl enable-linger {shlex.quote(service_user)}"],
        _sudo=True,
    )


def render_dotenv_template(nginx_proxy_hosts: str, gunicorn_workers: int) -> str:
    with open(TEMPLATE_DOTENV_PATH) as file:
        env = Environment(loader=DictLoader({
            "template": file.read()
        }))
        return env.get_template("template").render(
            gunicorn_workers=gunicorn_workers,
            nginx_proxy_hosts=nginx_proxy_hosts,
        )


def generate_env(service_user: str, service_home: Path, nginx_proxy_hosts: str, gunicorn_workers: int):
    # noinspection bad-argument-type
    files.template(
        src=str(TEMPLATE_DOTENV_PATH),
        dest=str(service_home / ".env"),
        mode=600,
        user=service_user,
        group=service_user,
        _sudo=True,
        _sudo_user=service_user,

        gunicorn_workers=gunicorn_workers,
        nginx_proxy_hosts=nginx_proxy_hosts,
    )


def generate_db_password_secret(
        service_user: str, service_home: Path, db_password: str, secret_name: str = "DB_PASSWORD"
):
    secret_already_exists = host.get_fact(
        PodmanSecretExists,
        secret_name,
        _sudo=True,
        _sudo_user=service_user,
        _chdir=str(service_home),
    )
    if secret_already_exists:
        if db_password:
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
        if not db_password:
            logger.info(
                "DB_PASSWORD secret does not exist and no password was provided, "
                "will auto-generate a secure password value..."
            )
            db_password = secrets.token_urlsafe(32)

    # The reason to create the password using a file as the source instead of an env var is to prevent leaking the
    # password through process inspection.
    db_password_buffer = str(service_home / ".db_password_buffer")

    files.put(
        src=StringIO(db_password),
        dest=db_password_buffer,
        mode=400,
        user=service_user,
        group=service_user,
        _sudo=True,
    )

    server.shell(
        commands=[f"podman secret create --replace {shlex.quote(secret_name)} {shlex.quote(db_password_buffer)}"],
        _sudo=True,
        _sudo_user=service_user,
        _chdir=str(service_home),
    )

    files.file(
        path=db_password_buffer,
        present=False,
        _sudo=True,
    )


def generate_quadlets(service_user: str, service_home: Path, gunicorn_workers: int, nginx_proxy_hosts: str):
    systemd_config_dir = service_home / ".config/containers/systemd"

    files.directory(
        path=str(systemd_config_dir),
        user=service_user,
        group=service_user,
        _sudo=True,
        _sudo_user=service_user,
    )

    dotenv = dotenv_values(stream=StringIO(render_dotenv_template(
        gunicorn_workers=gunicorn_workers,
        nginx_proxy_hosts=nginx_proxy_hosts,
    )))

    for path in (SOURCE_DIR / "systemd").iterdir():
        if not path.is_file():
            continue

        if path.suffix == ".jinja":
            files.template(
                src=str(path),
                dest=str(systemd_config_dir / path.stem),
                user=service_user,
                group=service_user,
                _sudo=True,
                _sudo_user=service_user,
                **dotenv
            )
        else:
            files.put(
                src=str(path),
                dest=str(systemd_config_dir / path.name),
                user=service_user,
                group=service_user,
                _sudo=True,
                _sudo_user=service_user,
            )


def systemd_daemon_reload(service_user: str):
    uid = host.get_fact(Users)[service_user]["uid"]
    systemd.daemon_reload(
        user_mode=True,
        _sudo=True,
        _sudo_user=service_user,
        _env={
            "XDG_RUNTIME_DIR": f"/run/user/{uid}"
        }
    )


def sync_frappe_docker_repo(service_user: str, service_home: Path):
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
        commands=f"cp -a /tmp/frappe_docker {shlex.quote(str(service_home))}",
        _sudo=True,
        _sudo_user=service_user,
    )


def sync_apps_json(service_user: str, service_home: Path):
    files.put(
        src=str(SOURCE_DIR / "apps.json"),
        dest=str(service_home / "apps.json"),
        user=service_user,
        group=service_user,
        mode=600,
        _sudo=True,
        _sudo_user=service_user,
    )


def build_image(service_user: str):
    uid = host.get_fact(Users)[service_user]["uid"]
    systemd.service(
        service="erpnext-custom-build.service",
        running=True,
        user_mode=True,
        _sudo=True,
        _sudo_user=service_user,
        _env={
            "XDG_RUNTIME_DIR": f"/run/user/{uid}"
        }
    )


@cli.command(
    gunicorn_workers="Set to 0 to automatically calculate with the formula (2 x number of CPU cores) + 1.",
    db_password="Leave empty to generate a random password. "
                "An existing password file will only be overridden if a non-empty value is explicitly provided.",
    service_user=f"Username of the host user that will run the rootless container.",
    service_home=f"Path to the home directory of the service user.",
)
def setup(
        nginx_proxy_hosts: str,
        db_password: str,
        gunicorn_workers: int = 0,
        service_user: str = DEFAULT_SERVICE_USER,
        service_home: Path = DEFAULT_SERVICE_HOME
):
    """
    Performs initial setup required to deploy ERPNext on a fresh server.
    """
    create_service_user(service_user, service_home)

    if gunicorn_workers == 0:
        gunicorn_workers = host.get_fact(Cpus) * 2 + 1

    generate_env(service_user, service_home, nginx_proxy_hosts, gunicorn_workers)

    generate_db_password_secret(service_user, service_home, db_password)

    generate_quadlets(service_user, service_home, gunicorn_workers, nginx_proxy_hosts)

    systemd_daemon_reload(service_user)

    sync_frappe_docker_repo(service_user, service_home)

    sync_apps_json(service_user, service_home)

    build_image(service_user)


@cli.command()
def deploy():
    """
    Deploys ERPNext according to the current configuration.
    Requires that the setup command has run successfully at least once.
    """
    pass
