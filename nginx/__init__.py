import shlex
from pathlib import Path

from pyinfra.operations import files
from pyinfra.operations import server
from pyinfra.operations import systemd

from cli.utils import ServiceCommandRegistry

cli = ServiceCommandRegistry(
    name="nginx",
    help_str="Manage Nginx deployment."
)

DEFAULT_SERVICE_USER = "nginx"
DEFAULT_SERVICE_HOME = Path("/srv") / DEFAULT_SERVICE_USER

SOURCE_DIR = Path(__file__).parent.resolve()


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


def generate_quadlets(service_user: str, service_home: Path):
    quadlets_config_dir = service_home / ".config/containers/systemd"

    files.directory(
        path=str(quadlets_config_dir),
        user=service_user,
        group=service_user,
        _sudo=True,
        _sudo_user=service_user,
    )

    for path in (SOURCE_DIR / "quadlets").iterdir():
        if not path.is_file():
            continue

        if path.suffix == ".jinja":
            # noinspection bad-argument-type
            files.template(
                src=str(path),
                dest=str(quadlets_config_dir / path.stem),
                user=service_user,
                group=service_user,
                _sudo=True,
                _sudo_user=service_user,
                service_home=service_home,
            )
        else:
            files.put(
                src=str(path),
                dest=str(quadlets_config_dir / path.name),
                user=service_user,
                group=service_user,
                _sudo=True,
                _sudo_user=service_user,
            )


def systemd_daemon_reload(service_user: str):
    systemd.daemon_reload(
        user_mode=True,
        user_name=service_user,
        _sudo=True,
    )


def generate_site_configs(service_user: str, service_home: Path, erpnext_sites: str):
    erpnext_sites = [site.strip() for site in erpnext_sites.split(",") if site.strip()]

    conf_dir = service_home / "conf.d"
    src_conf_dir = SOURCE_DIR / "conf.d"

    files.directory(
        path=str(conf_dir),
        user=service_user,
        group=service_user,
        _sudo=True,
        _sudo_user=service_user,
    )

    for site in erpnext_sites:
        # noinspection bad-argument-type
        files.template(
            src=str(src_conf_dir / "erpnext.conf.jinja"),
            dest=str(conf_dir / f"erpnext-{site}.conf"),
            user=service_user,
            group=service_user,
            _sudo=True,
            _sudo_user=service_user,
            server_name=site,
        )

    for path in src_conf_dir.iterdir():
        if not path.is_file() or path.suffix != ".conf":
            continue

        files.put(
            src=str(path),
            dest=str(conf_dir / path.name),
            user=service_user,
            group=service_user,
            _sudo=True,
            _sudo_user=service_user,
        )


def copy_certs(service_user: str, service_home: Path):
    certs_dir = service_home / "certs"

    files.directory(
        path=str(certs_dir),
        user=service_user,
        group=service_user,
        mode=700,
        _sudo=True,
        _sudo_user=service_user,
    )

    for path in (SOURCE_DIR / "certs").iterdir():
        if not path.is_file() or path.suffix != ".pem":
            continue

        files.put(
            src=str(path),
            dest=str(certs_dir / path.name),
            user=service_user,
            group=service_user,
            mode=400,
            _sudo=True,
        )


def restart_nginx(service_user: str):
    systemd.service(
        service="nginx.service",
        running=True,
        restarted=True,
        user_mode=True,
        user_name=service_user,
        _sudo=True,
    )


@cli.command(
    erpnext_sites="Comma-separated list of hosts to proxy to the ERPNext frontend container.",
    service_user=f"Username of the host user that will run the rootless container.",
    service_home=f"Path to the home directory of the service user.",
)
def setup(
        erpnext_sites: str,
        service_user: str = DEFAULT_SERVICE_USER,
        service_home: Path = DEFAULT_SERVICE_HOME
):
    """
    Performs initial setup required to deploy Nginx on a fresh server.
    """
    create_service_user(service_user, service_home)

    generate_site_configs(service_user, service_home, erpnext_sites)


@cli.command(
    service_user=f"Username of the host user that will run the rootless container.",
    service_home=f"Path to the home directory of the service user.",
)
def deploy(service_user: str = DEFAULT_SERVICE_USER, service_home: Path = DEFAULT_SERVICE_HOME):
    """
    Deploys Nginx according to the current configuration.
    Requires that the setup command has run successfully at least once.
    """
    copy_certs(service_user, service_home)

    generate_quadlets(service_user, service_home)

    systemd_daemon_reload(service_user)

    restart_nginx(service_user)
