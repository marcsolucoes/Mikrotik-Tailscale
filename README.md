# Tailscale on MikroTik via Container

Automated Tailscale installation on MikroTik routers using the native container feature of RouterOS 7.

## Quick Start

```bash
# Install dependency
pip install paramiko

# Run the script (prompts for IP and password interactively)
python3 setup_tailscale_mikrotik.py tskey-auth-XXXXXXXXXXXXXXXX

# Or pass everything as arguments
python3 setup_tailscale_mikrotik.py tskey-auth-XXX \
  --host 192.168.1.1 \
  --password "yourpassword" \
  --routes 192.168.88.0/24
```

## Requirements

- Python 3.8+
- `pip install paramiko`
- RouterOS 7.12 or later
- SSH access to the router
- Tailscale auth key ([generate here](https://login.tailscale.com/admin/settings/keys))

## What the script does

| Step | Action |
|------|--------|
| 1 | Installs the `container` package on RouterOS |
| 2 | Enables container device-mode *(requires physical reset button press)* |
| 3 | Creates `veth1` interface, `dockers` bridge and Tailscale route |
| 4 | Configures environment variables |
| 5 | Pulls image and starts the container |
| 6 | Validates everything is working |

## Options

```
python3 setup_tailscale_mikrotik.py --help

positional arguments:
  auth_key         Tailscale auth key (tskey-auth-...)

options:
  --host HOST      MikroTik IP address
  --user USER      SSH username (default: admin)
  --password PASS  SSH password
  --routes ROUTES  LAN subnet to advertise (default: auto-detected)
  --skip-to N      Skip to step N (1-6)
```

## Available packages

Container NPK packages are pre-extracted in this repository:

```
packages/
└── 7.20.8/
    ├── arm/    container-7.20.8-arm.npk     (hAP ax lite, RB4011, etc.)
    ├── arm64/  container-7.20.8-arm64.npk   (64-bit devices)
    └── x86/    container-7.20.8-x86.npk     (CHR, x86)
```

## After installation

Go to the [Tailscale Admin Console](https://login.tailscale.com/admin/machines), find the MikroTik device and approve the advertised subnet route.

## References

- Docker image: [ghcr.io/marcsolucoes/tailscale-mikrotik](https://github.com/marcsolucoes/Mikrotik-Tailscale/pkgs/container/tailscale-mikrotik)
- MikroTik Containers docs: https://help.mikrotik.com/docs/display/ROS/Container

## Contributors

- [@marcsolucoes](https://github.com/marcsolucoes)
