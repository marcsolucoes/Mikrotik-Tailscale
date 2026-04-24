# Tailscale no MikroTik via Container

Instalação automatizada do Tailscale em roteadores MikroTik usando o recurso nativo de containers do RouterOS 7.

## Uso rápido

```bash
# Instalar dependência
pip install paramiko

# Rodar o script (pede IP e senha interativamente)
python3 setup_tailscale_mikrotik.py tskey-auth-XXXXXXXXXXXXXXXX

# Ou passando tudo via argumento
python3 setup_tailscale_mikrotik.py tskey-auth-XXX \
  --host 192.168.1.1 \
  --password "suasenha" \
  --routes 192.168.88.0/24
```

## Requisitos

- Python 3.8+
- `pip install paramiko`
- RouterOS 7.12 ou superior
- Acesso SSH ao roteador
- Auth key do Tailscale ([gerar aqui](https://login.tailscale.com/admin/settings/keys))

## O que o script faz

| Etapa | Ação |
|-------|------|
| 1 | Instala o pacote `container` no RouterOS |
| 2 | Habilita o device-mode container *(requer botão reset físico)* |
| 3 | Cria interface `veth1`, bridge `dockers` e rota Tailscale |
| 4 | Configura variáveis de ambiente |
| 5 | Baixa imagem e inicia o container |
| 6 | Valida funcionamento |

## Opções

```
python3 setup_tailscale_mikrotik.py --help

positional arguments:
  auth_key         Auth key do Tailscale (tskey-auth-...)

options:
  --host HOST      IP do MikroTik
  --user USER      Usuário SSH (padrão: admin)
  --password PASS  Senha SSH
  --routes ROUTES  Sub-rede LAN a anunciar (padrão: detecta automaticamente)
  --skip-to N      Pular para a etapa N (1-6)
```

## Pacotes disponíveis

Os pacotes NPK do container estão pré-extraídos neste repositório:

```
packages/
└── 7.20.8/
    ├── arm/    container-7.20.8-arm.npk     (hAP ax lite, RB4011, etc.)
    ├── arm64/  container-7.20.8-arm64.npk   (dispositivos 64-bit)
    └── x86/    container-7.20.8-x86.npk     (CHR, x86)
```

## Após a instalação

Acesse o [Tailscale Admin Console](https://login.tailscale.com/admin/machines), localize o dispositivo MikroTik e aprove a subnet route anunciada.

## Referências

- Imagem Docker: [fluent-networks/tailscale-mikrotik](https://github.com/Fluent-networks/tailscale-mikrotik)
- Documentação MikroTik Containers: https://help.mikrotik.com/docs/display/ROS/Container
