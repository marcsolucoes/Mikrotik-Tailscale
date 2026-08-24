#!/usr/bin/env python3
"""
Instala e configura o Tailscale em roteadores MikroTik via container Docker.
Uso: python3 setup_tailscale_mikrotik.py <AUTH_KEY> [opções]
"""

import argparse
import sys
import time
import json
import re
import urllib.request
import urllib.error

GITHUB_RAW = "https://raw.githubusercontent.com/marcsolucoes/Mikrotik-Tailscale/main"

try:
    import paramiko
except ImportError:
    print("[ERRO] Dependência ausente: instale com  pip install paramiko")
    sys.exit(1)


# ─── Cores no terminal ────────────────────────────────────────────────────────

def ok(msg):   print(f"\033[92m[✓]\033[0m {msg}")
def info(msg): print(f"\033[94m[→]\033[0m {msg}")
def warn(msg): print(f"\033[93m[!]\033[0m {msg}")
def err(msg):  print(f"\033[91m[✗]\033[0m {msg}")
def step(msg): print(f"\n\033[1m{'─'*60}\033[0m\n\033[1m  {msg}\033[0m\n{'─'*60}")


# ─── SSH helpers ──────────────────────────────────────────────────────────────

def connect(host, user, password, timeout=15):
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(host, port=22, username=user, password=password,
              timeout=timeout, look_for_keys=False, allow_agent=False)
    return c


def run(client, cmd, timeout=20):
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode().strip()
    err_out = stderr.read().decode().strip()
    return out, err_out


def wait_online(host, user, password, wait_first=20, retries=24, interval=10):
    info(f"Aguardando roteador reiniciar...")
    time.sleep(wait_first)
    for i in range(retries):
        try:
            c = connect(host, user, password, timeout=5)
            c.close()
            ok("Roteador online.")
            return True
        except Exception:
            print(f"    tentativa {i+1}/{retries}...", end="\r")
            time.sleep(interval)
    err("Roteador não voltou online no tempo esperado.")
    return False


# ─── Etapas ───────────────────────────────────────────────────────────────────

def get_router_info(client):
    out, _ = run(client, "/system resource print")
    info_map = {}
    for line in out.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            info_map[k.strip()] = v.strip()
    return info_map


def check_package_installed(client, name):
    out, _ = run(client, f"/system package print where name={name}")
    return name in out


def check_container_mode(client):
    out, _ = run(client, "/system/device-mode/print")
    return "container: yes" in out


def check_interface_exists(client, name):
    out, _ = run(client, f"/interface print where name={name}")
    return name in out


def check_bridge_exists(client, name):
    out, _ = run(client, f"/interface/bridge print where name={name}")
    return name in out


def check_ip_exists(client, address):
    out, _ = run(client, f"/ip/address print where address~\"{address.split('/')[0]}\"")
    return address.split("/")[0] in out


def check_route_exists(client, dst):
    out, _ = run(client, f"/ip/route print where dst-address={dst}")
    return dst in out


def check_snat_rule_exists(client, to_address):
    out, _ = run(client, '/ip/firewall/nat print where chain=srcnat and action=src-nat and out-interface=veth1')
    return to_address in out


def get_router_ip_in_subnet(client, subnet):
    """Retorna o IP do próprio router que pertence à sub-rede anunciada."""
    import ipaddress
    try:
        net = ipaddress.ip_network(subnet, strict=False)
    except ValueError:
        return None
    out, _ = run(client, "/ip/address print")
    for line in out.splitlines():
        m = re.search(r'(\d+\.\d+\.\d+\.\d+)/\d+', line)
        if m:
            try:
                if ipaddress.ip_address(m.group(1)) in net:
                    return m.group(1)
            except ValueError:
                continue
    return None


def check_container_exists(client):
    out, _ = run(client, "/container print")
    return "tailscale" in out.lower()


def get_container_status(client):
    out, _ = run(client, "/container print")
    if "R " in out:
        return "running"
    if "S " in out:
        return "stopped"
    if "E " in out:
        return "extracting"
    return "unknown"


def step1_install_package(client, host, user, password, ros_version, arch):
    step("ETAPA 1 — Instalar pacote Container")

    if check_package_installed(client, "container"):
        ok("Pacote container já instalado. Pulando etapa.")
        return client

    npk_name = f"container-{ros_version}-{arch}.npk"
    url = f"{GITHUB_RAW}/packages/{ros_version}/{arch}/{npk_name}"

    info(f"Baixando {npk_name} do repositório GitHub...")
    info(f"  {url}")
    try:
        with urllib.request.urlopen(url, timeout=60) as resp:
            npk_data = resp.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            err(f"Pacote não encontrado no repositório: {url}")
            err(f"Arquiteturas disponíveis: arm, arm64, x86")
            err(f"Versões disponíveis: verifique {GITHUB_RAW}/packages/")
        else:
            err(f"Falha ao baixar pacote: HTTP {e.code}")
        sys.exit(1)

    info(f"Enviando {npk_name} para o roteador via SFTP ({len(npk_data)//1024} KB)...")
    sftp = client.open_sftp()
    with sftp.file(f"/{npk_name}", "wb") as f:
        f.write(npk_data)
    sftp.close()
    ok("Upload concluído.")

    info("Reiniciando para instalar o pacote...")
    run(client, "/system reboot")
    client.close()

    if not wait_online(host, user, password):
        sys.exit(1)

    client = connect(host, user, password)

    if check_package_installed(client, "container"):
        ok("Pacote container instalado com sucesso.")
    else:
        err("Pacote container não aparece após reboot. Verifique manualmente.")
        sys.exit(1)

    return client


def step2_enable_container_mode(client, host, user, password):
    step("ETAPA 2 — Habilitar modo Container (requer botão físico)")

    if check_container_mode(client):
        ok("Modo container já habilitado. Pulando etapa.")
        return client

    out, _ = run(client, "/system/device-mode/update container=yes", timeout=5)
    print()
    warn("O roteador aguarda confirmação FÍSICA.")
    warn("Pressione o botão RESET (toque breve) no roteador agora.")
    warn("Você tem até 5 minutos. O roteador reiniciará automaticamente.")
    print()
    input("    Pressione ENTER aqui após apertar o botão reset no roteador...")

    client.close()

    if not wait_online(host, user, password):
        sys.exit(1)

    client = connect(host, user, password)

    if check_container_mode(client):
        ok("Modo container habilitado com sucesso.")
    else:
        err("device-mode container=yes não está ativo. Tente a etapa novamente.")
        sys.exit(1)

    return client


def step3_configure_network(client, lan_subnet):
    step("ETAPA 3 — Configurar rede do container")

    if not check_interface_exists(client, "veth1"):
        info("Criando interface veth1...")
        run(client, "/interface/veth add name=veth1 address=172.17.0.2/16 gateway=172.17.0.1")
        ok("veth1 criada.")
    else:
        ok("Interface veth1 já existe.")

    if not check_bridge_exists(client, "dockers"):
        info("Criando bridge dockers...")
        run(client, "/interface/bridge add name=dockers")
        ok("Bridge dockers criada.")
    else:
        ok("Bridge dockers já existe.")

    if not check_ip_exists(client, "172.17.0.1/16"):
        info("Atribuindo IP 172.17.0.1/16 à bridge dockers...")
        run(client, "/ip/address add address=172.17.0.1/16 interface=dockers")
        ok("IP atribuído.")
    else:
        ok("IP 172.17.0.1/16 já configurado.")

    # Verificar se veth1 já está na bridge
    out, _ = run(client, "/interface/bridge/port print where interface=veth1")
    if "veth1" not in out:
        info("Adicionando veth1 à bridge dockers...")
        run(client, "/interface/bridge/port add bridge=dockers interface=veth1")
        ok("veth1 adicionada à bridge.")
    else:
        ok("veth1 já está na bridge dockers.")

    if not check_route_exists(client, "100.64.0.0/10"):
        info("Adicionando rota Tailscale 100.64.0.0/10...")
        run(client, "/ip/route add dst-address=100.64.0.0/10 gateway=172.17.0.2")
        ok("Rota Tailscale adicionada.")
    else:
        ok("Rota 100.64.0.0/10 já existe.")

    # O iptables dentro do container falha ao criar o MASQUERADE do Tailscale
    # ("Module is wrong version"), então tráfego originado no próprio router
    # sai com origem 172.17.0.1 e os peers não sabem responder. Corrige-se
    # reescrevendo a origem para o IP do router na sub-rede anunciada.
    router_ip = get_router_ip_in_subnet(client, lan_subnet)
    if router_ip:
        if not check_snat_rule_exists(client, router_ip):
            info(f"Adicionando SNAT (origem local → {router_ip}) para tráfego ao Tailscale...")
            run(client,
                "/ip/firewall/nat add chain=srcnat action=src-nat"
                " dst-address=100.64.0.0/10 out-interface=veth1"
                f" to-addresses={router_ip}"
                " comment=\"tailscale-snat-router-traffic\"")
            ok("Regra SNAT adicionada.")
        else:
            ok("Regra SNAT para o Tailscale já existe.")
    else:
        warn(f"Não foi possível determinar o IP do router em {lan_subnet}; pulei a regra SNAT.")
        warn("Ping/traceroute originados no próprio router podem falhar sem Src. Address manual.")


def step4_configure_envs(client, auth_key, lan_subnet, password):
    step("ETAPA 4 — Configurar variáveis de ambiente")

    # Verificar se já existem
    out, _ = run(client, "/container/envs print where list=tailscale")
    if "AUTH_KEY" in out:
        ok("Variáveis de ambiente já configuradas.")
        return

    vars_ = [
        ("AUTH_KEY",          auth_key),
        ("ADVERTISE_ROUTES",  lan_subnet),
        ("TAILSCALE_ARGS",    "--accept-routes"),
        ("CONTAINER_GATEWAY", "172.17.0.1"),
        ("LOGIN_SERVER",      "https://controlplane.tailscale.com"),
        ("PASSWORD",          password),
    ]
    for key, value in vars_:
        run(client, f'/container/envs add list=tailscale key={key} value="{value}"')
        info(f"  {key} = {'*' * 8 if 'KEY' in key or 'PASSWORD' in key else value}")

    ok("Variáveis de ambiente configuradas.")


def step5_create_container(client):
    step("ETAPA 5 — Criar e iniciar container Tailscale")

    if check_container_exists(client):
        status = get_container_status(client)
        if status == "running":
            ok("Container já existe e está RUNNING.")
            return
        elif status == "stopped":
            warn("Container existe mas está parado. Iniciando...")
            run(client, "/container start 0")
            time.sleep(5)
            ok("Container iniciado.")
            return
        else:
            warn(f"Container em estado: {status}. Aguardando...")

    # Configurar registry
    info("Configurando registry ghcr.io...")
    run(client, "/container/config set registry-url=https://ghcr.io tmpdir=disk1")

    info("Criando container (iniciará download da imagem ~30MB)...")
    run(client,
        "/container add"
        " remote-image=marcsolucoes/tailscale-mikrotik:latest"
        " interface=veth1"
        " envlist=tailscale"
        " root-dir=tailscale"
        " start-on-boot=yes"
    )

    # Aguardar extração
    info("Aguardando download e extração da imagem...")
    dots = 0
    for _ in range(60):
        status = get_container_status(client)
        if status == "stopped":
            break
        if status == "running":
            break
        print(f"    [{status}]{'.' * dots}   ", end="\r")
        dots = (dots + 1) % 4
        time.sleep(10)
    print()

    status = get_container_status(client)
    if status == "stopped":
        info("Iniciando container...")
        run(client, "/container start 0")
        time.sleep(8)
        status = get_container_status(client)

    if status == "running":
        ok("Container está RUNNING.")
    else:
        err(f"Container em estado inesperado: {status}")
        warn("Verifique: /log print where topics~\"container\"")
        sys.exit(1)


def step6_verify(client):
    step("ETAPA 6 — Verificação final")

    # Ping no container
    out, _ = run(client, "/ping address=172.17.0.2 count=3")
    if "packet-loss=0%" in out:
        ok("Ping 172.17.0.2 → OK (container responde)")
    else:
        warn("Ping 172.17.0.2 falhou — verifique a interface veth1")

    # Rota ativa
    out, _ = run(client, "/ip/route print where dst-address~\"100.64\"")
    if "100.64.0.0/10" in out and "As" in out:
        ok("Rota 100.64.0.0/10 → ATIVA")
    else:
        warn("Rota Tailscale não está ativa")

    # Container running
    status = get_container_status(client)
    if status == "running":
        ok("Container status → RUNNING")
    else:
        warn(f"Container status: {status}")

    # Aguardar Tailscale autenticar (state file pode demorar ~15s para aparecer)
    info("Aguardando Tailscale autenticar...")
    sftp = client.open_sftp()
    state_ok = False
    for _ in range(18):
        try:
            sftp.stat("/tailscale/var/lib/tailscale/tailscaled.state")
            state_ok = True
            break
        except OSError:
            time.sleep(5)
    sftp.close()

    if state_ok:
        ok("tailscaled.state existe → Tailscale autenticou com sucesso")

        # Extrair conta do state
        try:
            sftp = client.open_sftp()
            with sftp.file("/tailscale/var/lib/tailscale/tailscaled.state", "rb") as f:
                state = json.loads(f.read())
            sftp.close()

            profiles = state.get("_profiles", "")
            if profiles:
                import base64
                pd = json.loads(base64.b64decode(profiles))
                for pid, pdata in pd.items():
                    name = pdata.get("Name", "")
                    network = pdata.get("NetworkProfile", {})
                    domain = network.get("DomainName", "")
                    magic  = network.get("MagicDNSName", "")
                    if name:
                        ok(f"Conta: {name}")
                    if domain:
                        ok(f"Rede Tailscale: {domain} ({magic})")
        except Exception:
            pass
    else:
        warn("tailscaled.state ainda não criado — Tailscale pode estar iniciando")

    print()
    print("─" * 60)
    print("\033[1m  PRÓXIMO PASSO OBRIGATÓRIO\033[0m")
    print("─" * 60)
    print("  Acesse o console do Tailscale e aprove a rota anunciada:")
    print("  \033[94mhttps://login.tailscale.com/admin/machines\033[0m")
    print("  → Encontre o dispositivo MikroTik")
    print("  → Clique em '...' → 'Edit route settings'")
    print("  → Habilite a subnet route")
    print("─" * 60)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Configura Tailscale em MikroTik via container Docker.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
exemplos:
  python3 setup_tailscale_mikrotik.py tskey-auth-XXXX
  python3 setup_tailscale_mikrotik.py tskey-auth-XXXX --host 192.168.1.1 --password admin
  python3 setup_tailscale_mikrotik.py tskey-auth-XXXX --routes 192.168.88.0/24
        """
    )
    parser.add_argument("auth_key",
                        help="Auth key do Tailscale (tskey-auth-...)")
    parser.add_argument("--host",
                        help="IP do MikroTik (padrão: solicita interativamente)")
    parser.add_argument("--user",     default="admin",
                        help="Usuário SSH (padrão: admin)")
    parser.add_argument("--password",
                        help="Senha SSH (padrão: solicita interativamente)")
    parser.add_argument("--routes",   default=None,
                        help="Sub-rede LAN a anunciar (padrão: detecta automaticamente)")
    parser.add_argument("--skip-to",  type=int, default=1, metavar="ETAPA",
                        help="Pular para etapa N (1-6)")
    args = parser.parse_args()

    print()
    print("╔══════════════════════════════════════════════════════╗")
    print("║     Instalação Tailscale → MikroTik via Container    ║")
    print("╚══════════════════════════════════════════════════════╝")
    print()

    # Coletar dados interativamente se não passados como argumento
    host = args.host
    if not host:
        host = input("  IP do MikroTik: ").strip()

    password = args.password
    if not password:
        import getpass
        password = getpass.getpass(f"  Senha SSH para {args.user}@{host}: ")

    print()
    info(f"Conectando em {args.user}@{host}...")
    try:
        client = connect(host, args.user, password)
    except Exception as e:
        err(f"Falha na conexão SSH: {e}")
        sys.exit(1)
    ok("Conexão SSH estabelecida.")

    # Detectar versão e arquitetura do RouterOS
    router_info = get_router_info(client)
    ros_version = router_info.get("version", "").split(" ")[0]
    arch        = router_info.get("architecture-name", "arm")
    board       = router_info.get("board-name", "")
    identity, _ = run(client, "/system identity print")
    identity    = re.search(r'name:\s*(\S+)', identity)
    identity    = identity.group(1) if identity else host

    print()
    info(f"Roteador:    {board} ({identity})")
    info(f"RouterOS:    {ros_version}")
    info(f"Arquitetura: {arch}")

    # Detectar sub-rede LAN automaticamente se não fornecida
    lan_subnet = args.routes
    if not lan_subnet:
        out, _ = run(client, "/ip/address print where interface~\"bridge\" or interface~\"lan\" or interface~\"ether\"")
        for line in out.splitlines():
            m = re.search(r'(\d+\.\d+\.\d+\.\d+/\d+)', line)
            if m:
                addr = m.group(1)
                if not addr.startswith("172.") and not addr.startswith("100."):
                    # Converter para endereço de rede
                    import ipaddress
                    net = str(ipaddress.ip_interface(addr).network)
                    lan_subnet = net
                    break

    if not lan_subnet:
        lan_subnet = input("  Sub-rede LAN a anunciar (ex: 10.0.10.0/24): ").strip()

    info(f"Sub-rede LAN: {lan_subnet}")
    print()

    skip = args.skip_to

    # ── Executar etapas ──────────────────────────────────────────────────────

    if skip <= 1:
        client = step1_install_package(client, host, args.user, password, ros_version, arch)

    if skip <= 2:
        client = step2_enable_container_mode(client, host, args.user, password)

    if skip <= 3:
        step3_configure_network(client, lan_subnet)

    if skip <= 4:
        step4_configure_envs(client, args.auth_key, lan_subnet, password)

    if skip <= 5:
        step5_create_container(client)

    step6_verify(client)

    client.close()
    print()
    ok("Script finalizado.")
    print()


if __name__ == "__main__":
    main()

