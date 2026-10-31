import shlex
import shutil
from pathlib import Path

from jinja2 import Environment
from jinja2 import DictLoader
from pyinfra.operations import files
from pyinfra.operations import python
from pyinfra.operations import server
from pyinfra.operations import systemd

from cli.registry import step
from cli.registry import SubCommand


class ServiceSubCommandBase(SubCommand):
    param_help = {
        "service_user": f"Username of the host user that will run the rootless container.",
        "service_home": f"Path to the home directory of the service user.",
    }

    def __init__(self, service_user: str, service_home: Path, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.service_user = service_user
        self.service_home = service_home

    @step
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

    @staticmethod
    def render_template_file(path: Path | str, **template_kwargs):
        if isinstance(path, str):
            path = Path(path)

        env = Environment(loader=DictLoader({
            "template": path.read_text()
        }))
        template = env.get_template("template")
        return template.render(**template_kwargs)

    def sync_template_directory(self, src_dir: Path, remote_dir: Path, **template_kwargs):
        # Renders all *.jinja files in a local directory and then syncs the resulting directory to the remote.

        build_dir = Path("./build").resolve() / src_dir.name
        if build_dir.exists():
            shutil.rmtree(build_dir)
        build_dir.mkdir(parents=True, exist_ok=True)

        shutil.copytree(src_dir, build_dir, dirs_exist_ok=True)
        for path in build_dir.iterdir():
            if path.is_file() and path.suffix in (".jinja", ".j2"):
                new_file = path.parent / path.stem
                new_file.write_text(self.render_template_file(path, **template_kwargs))
                path.unlink()

        files.sync(
            src=str(build_dir),
            dest=str(remote_dir),
            user=self.service_user,
            group=self.service_user,
            delete=True,
            _sudo=True,
        )

    @step
    def systemd_daemon_reload(self):
        systemd.daemon_reload(
            user_mode=True,
            user_name=self.service_user,
            _sudo=True,
        )

    @step
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
                *args,
                **kwargs,
        ):
            super().__init__(service_user, service_home, *args, **kwargs)

    return ServiceSubCommand
