from pathlib import Path

from pyinfra.operations import server

from cli.utils import ServiceCommandRegistry

cli = ServiceCommandRegistry(
    name="erpnext",
    help_str="Manage ERPNext deployment."
)

DEFAULT_SERVICE_USER = "erpnext"
DEFAULT_SERVICE_HOME = Path("/srv") / DEFAULT_SERVICE_USER


@cli.command(
    service_user=f"Username of the host user that will run the rootless container.",
    service_home=f"Path to the home directory of the service user.",
)
def setup(
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


@cli.command()
def deploy():
    """
    Deploys ERPNext according to the current configuration.
    Requires that the setup command has run successfully at least once.
    """
    pass
