import secrets
import shlex
from io import StringIO
from pathlib import Path

from dotenv import dotenv_values
from pyinfra import host
from pyinfra import logger
from pyinfra.api.facts import FactBase
from pyinfra.facts.files import File
from pyinfra.facts.hardware import Cpus
from pyinfra.operations import files
from pyinfra.operations import server

from cli.utils import ServiceCommandRegistry

cli = ServiceCommandRegistry(
    name="erpnext",
    help_str="Manage ERPNext deployment."
)

DEFAULT_SERVICE_USER = "erpnext"
DEFAULT_SERVICE_HOME = Path("/srv") / DEFAULT_SERVICE_USER

SOURCE_DIR = Path(__file__).parent.resolve()


# noinspection method-may-be-static,method-overriding
class DotenvConfig(FactBase):
    def requires_command(self, service_home: Path) -> str:
        return "cat"

    def command(self, service_home: Path):
        return f"cat {shlex.quote(str(service_home / '.env'))}"

    def process(self, output: str) -> dict:
        return dict(dotenv_values(stream=StringIO('\n'.join(output))))


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


def generate_env(service_user: str, service_home: Path, nginx_proxy_hosts: str, gunicorn_workers: int):
    # noinspection bad-argument-type
    files.template(
        src=str(SOURCE_DIR / "template.env.jinja"),
        dest=str(service_home / ".env"),
        mode=600,
        user=service_user,
        group=service_user,
        _sudo=True,
        _sudo_user=service_user,
        service_home=service_home,
        gunicorn_workers=gunicorn_workers,
        nginx_proxy_hosts=nginx_proxy_hosts,
    )


def generate_db_password_file(service_user: str, service_home: Path, db_password: str):
    db_password_file = host.get_fact(DotenvConfig, service_home, _sudo=True)["DB_PASSWORD_SECRETS_FILE"]

    password_file_already_exists = bool(host.get_fact(File, str(db_password_file), _sudo=True))
    if not db_password and not password_file_already_exists:
        db_password = secrets.token_urlsafe(32)

    if not db_password:
        logger.info("DB password file already exists and no password was provided, will skip creation...")
        return

    files.put(
        src=StringIO(db_password),
        dest=str(db_password_file),
        mode=400,
        user=service_user,
        group=service_user,
        _sudo=True,
    )


def generate_quadlets(service_user: str, service_home: Path):
    systemd_config_dir = service_home / ".config/containers/systemd"

    files.directory(
        path=str(systemd_config_dir),
        user=service_user,
        group=service_user,
        _sudo=True,
        _sudo_user=service_user,
    )

    dotenv = host.get_fact(DotenvConfig, service_home, _sudo=True)
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

    files.copy(
        src="/tmp/frappe_docker",
        dest=str(service_home),
        overwrite=True,
        _sudo=True,
        _sudo_user=service_user,
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

    generate_db_password_file(service_user, service_home, db_password)

    generate_quadlets(service_user, service_home)

    sync_frappe_docker_repo(service_user, service_home)


@cli.command()
def deploy():
    """
    Deploys ERPNext according to the current configuration.
    Requires that the setup command has run successfully at least once.
    """
    pass
