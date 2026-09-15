# Infra

Pyinfra-based IaC tool with a comfy CLI to deploy various services using rootless Podman containers managed by systemd
via Quadlets, with each service running as a separate user on the host.

Only tested to work with AlmaLinux hosts (will likely work with other RHEL-family distributions too).

## Setup

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), and run:

```bash
git clone https://github.com/sujaldev/infra --recurse-submodules
cd infra
uv venv .venv
source .venv/bin/activate
uv sync
```

Enable bash completion by running this at the root of the repo:

```bash
source bash-completion.sh
```

To make your life easier, I suggest appending the `bash-completion.sh` script to `.venv/bin/activate`. This will
automatically enable bash completion when you activate the venv:

```
cat bash-completion.sh >> .venv/bin/activate
```

> [!WARNING]
> You'll have to repeat this step every time you (re)create your virtual environment.
> It would be nice if uv provided a way to do this via a hook script, but it doesn't seem to do so at the moment.

## Usage

1. **Specify a target** to operate on. This can be a host defined in `~/.ssh/config`:
    ```bash
    # Single host
    infra -s host
    # Multiple hosts
    infra -s host1,host2
    # Local host
    infra -s @local
    ```

2. **Specify a module** (run `infra -h` to list all modules):
   ```bash
   infra -s my-server erpnext
   ```

3. **Specify a command** to execute for the module (run `infra <module> -h` to list all commands for that module):
   ```bash
   # Executes the "setup" command for the "nginx" module on target "my-server".
   infra -s my-server nginx setup
   ```
   Commands can also accept options. Run `infra <module> <command> -h` for more help.

   > [!TIP]
   > Each command accepts two special options, `--include-steps` and `--exclude-steps`, which can be used to include or
   > exclude individual steps within a command. Shell completion is available for step names, tab away!

## Modules

### server-init

Performs common server-wide configuration.

### ERPNext

Deploys the [frappe_docker](https://github.com/frappe/frappe_docker) repository with the following apps:

* [frappe/erpnext](https://github.com/frappe/erpnext)
* [frappe/hrms](https://github.com/frappe/hrms)
* [resilient-tech/india-compliance](https://github.com/resilient-tech/india-compliance)

### Nginx

Deploys nginx with `--network=host`.

