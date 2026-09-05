from cli.utils import ServiceCommandRegistry

cli = ServiceCommandRegistry(
    name="erpnext",
    help_str="Manage ERPNext deployment."
)


@cli.command()
def setup():
    """
    Performs initial setup required to deploy ERPNext on a fresh server.
    """
    pass


@cli.command()
def deploy():
    """
    Deploys ERPNext according to the current configuration.
    Requires that the setup command has run successfully at least once.
    """
    pass
