import shlex
from pathlib import Path

from pyinfra.operations import files
from pyinfra.operations import server
from pyinfra.operations import systemd

from cli.command_registry import SubCommand


class ServiceSubCommandBase(SubCommand):
    param_help = {
        "service_user": f"Username of the host user that will run the rootless container.",
        "service_home": f"Path to the home directory of the service user.",
    }

    def __init__(self, service_user: str, service_home: Path):
        self.service_user = service_user
        self.service_home = service_home

    def create_service_user(self):
        server.user(
            name=f"Ensure service user {self.service_user!r} exists",
            user=self.service_user,
            home=str(self.service_home),
            shell="/usr/sbin/nologin",
            create_home=True,
            ensure_home=True,
            _sudo=True,
        )

        server.shell(
            name=f"Enable lingering for {self.service_user!r}",
            commands=[f"loginctl enable-linger {shlex.quote(self.service_user)}"],
            _sudo=True,
        )

    def generate_quadlets(self, src_dir: Path, **template_kwargs):
        quadlets_config_dir = self.service_home / ".config/containers/systemd"

        files.directory(
            path=str(quadlets_config_dir),
            user=self.service_user,
            group=self.service_user,
            _sudo=True,
            _sudo_user=self.service_user,
        )

        for path in (src_dir / "quadlets").iterdir():
            if not path.is_file():
                continue

            if path.suffix == ".jinja":
                files.template(
                    src=str(path),
                    dest=str(quadlets_config_dir / path.stem),
                    user=self.service_user,
                    group=self.service_user,
                    _sudo=True,
                    _sudo_user=self.service_user,
                    **template_kwargs
                )
            else:
                files.put(
                    src=str(path),
                    dest=str(quadlets_config_dir / path.name),
                    user=self.service_user,
                    group=self.service_user,
                    _sudo=True,
                    _sudo_user=self.service_user,
                )

    def copy_systemd_files(self, src_dir: Path):
        systemd_config_dir = self.service_home / ".config/systemd/user"

        files.directory(
            path=str(systemd_config_dir),
            user=self.service_user,
            group=self.service_user,
            _sudo=True,
            _sudo_user=self.service_user,
        )

        for path in (src_dir / "systemd").iterdir():
            if not path.is_file():
                continue

            files.put(
                src=str(path),
                dest=str(systemd_config_dir / path.name),
                user=self.service_user,
                group=self.service_user,
                _sudo=True,
                _sudo_user=self.service_user,
            )

    def systemd_daemon_reload(self):
        systemd.daemon_reload(
            user_mode=True,
            user_name=self.service_user,
            _sudo=True,
        )

    def restart_service(self, service: str):
        systemd.service(
            service=service,
            running=True,
            restarted=True,
            user_mode=True,
            user_name=self.service_user,
            _sudo=True,
        )


def make_service_subcommand(default_service_user: str, default_service_home: Path):
    class ServiceSubCommand(ServiceSubCommandBase):
        def __init__(
                self,
                service_user: str = default_service_user,
                service_home: Path = default_service_home,
        ):
            super().__init__(service_user, service_home)

    return ServiceSubCommand
