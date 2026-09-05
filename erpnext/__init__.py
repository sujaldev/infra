from pathlib import Path

from pyinfra import host
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


@cli.command(
    gunicorn_workers="Set to 0 to automatically calculate with the formula (2 x number of CPU cores) + 1.",
    service_user=f"Username of the host user that will run the rootless container.",
    service_home=f"Path to the home directory of the service user.",
)
def setup(
        nginx_proxy_hosts: str,
        gunicorn_workers: int = 0,
        service_user: str = DEFAULT_SERVICE_USER,
        service_home: Path = DEFAULT_SERVICE_HOME
):
    """
    Performs initial setup required to deploy ERPNext on a fresh server.
    """
    server.user(
        name=f"Ensure service user {service_user!r} exists",
        user=service_user,
        home=str(service_home),
        shell="/usr/sbin/nologin",
        create_home=True,
        ensure_home=True,
        _sudo=True,
    )

    if gunicorn_workers == 0:
        gunicorn_workers = host.get_fact(Cpus) * 2 + 1

    generate_env(service_user, service_home, nginx_proxy_hosts, gunicorn_workers)


@cli.command()
def deploy():
    """
    Deploys ERPNext according to the current configuration.
    Requires that the setup command has run successfully at least once.
    """
    pass
