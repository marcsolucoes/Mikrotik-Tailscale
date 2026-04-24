# Tailscale no MikroTik via Container

Configuração do Tailscale em roteadores MikroTik usando o recurso nativo de containers do RouterOS 7.

**Equipamento usado:** MikroTik hAP ax lite (L41G-2axD)  
**RouterOS:** 7.20.8 (long-term)  
**Arquitetura:** ARM  
**Imagem Docker:** `ghcr.io/fluent-networks/tailscale-mikrotik:latest`  
**Referência:** https://github.com/Fluent-networks/tailscale-mikrotik

---

## Pré-requisitos

- RouterOS 7.12 ou superior
- Arquitetura ARM, ARM64 ou x86
- Acesso SSH ao roteador (admin)
- Auth key do Tailscale (gerada em login.tailscale.com → Settings → Keys)
- Conexão com a internet no roteador

---

## Instalação manual passo a passo

### 1. Instalar o pacote Container

O pacote `container` não vem instalado por padrão. Baixe o bundle de pacotes extras do site da MikroTik correspondente à versão e arquitetura do seu roteador:

```
https://download.mikrotik.com/routeros/{versão}/all_packages-{arch}-{versão}.zip
```

Extraia o arquivo `container-{versão}-arm.npk` e envie para o roteador via SFTP (porta 22, usuário admin):

```bash
sftp admin@IP_DO_ROTEADOR
put container-7.20.8-arm.npk /container-7.20.8-arm.npk
```

Reinicie o roteador para instalar o pacote:

```routeros
/system reboot
```

Após o boot, confirme que o pacote foi instalado:

```routeros
/system package print
# Deve aparecer: container  7.20.8
```

---

### 2. Habilitar o modo Container (requer confirmação física)

Este passo exige que você esteja próximo ao equipamento, pois requer pressionar o botão reset físico.

Execute o comando no roteador:

```routeros
/system/device-mode/update container=yes
```

O roteador exibirá uma contagem regressiva de 5 minutos:

```
update: turn off power or reboot by pressing reset or mode button in 5m to activate changes
```

**Pressione brevemente o botão reset** (parte traseira do roteador) dentro do prazo. O roteador reiniciará automaticamente.

Após o boot, confirme que o modo foi ativado:

```routeros
/system/device-mode/print
# Deve mostrar: container: yes
```

---

### 3. Configurar a rede do container

Crie a interface virtual (veth) que conecta o container ao roteador:

```routeros
/interface/veth add name=veth1 address=172.17.0.2/16 gateway=172.17.0.1
```

Crie a bridge interna para o Docker:

```routeros
/interface/bridge add name=dockers
/ip/address add address=172.17.0.1/16 interface=dockers
/interface/bridge/port add bridge=dockers interface=veth1
```

Adicione a rota para o range de IPs do Tailscale (100.64.0.0/10):

```routeros
/ip/route add dst-address=100.64.0.0/10 gateway=172.17.0.2
```

---

### 4. Configurar variáveis de ambiente do container

Substitua os valores conforme seu ambiente:

```routeros
/container/envs add list=tailscale key=AUTH_KEY         value="tskey-auth-XXXXXXXXX"
/container/envs add list=tailscale key=ADVERTISE_ROUTES value="10.0.10.0/24"
/container/envs add list=tailscale key=CONTAINER_GATEWAY value="172.17.0.1"
/container/envs add list=tailscale key=LOGIN_SERVER     value="https://controlplane.tailscale.com"
/container/envs add list=tailscale key=PASSWORD         value="senha_root_container"
```

| Variável | Descrição |
|----------|-----------|
| `AUTH_KEY` | Chave de autenticação gerada no console do Tailscale |
| `ADVERTISE_ROUTES` | Sub-rede local a ser anunciada para outros peers (ex: sua LAN) |
| `CONTAINER_GATEWAY` | Gateway da bridge Docker (sempre `172.17.0.1` nesta configuração) |
| `LOGIN_SERVER` | URL do servidor de controle (padrão Tailscale ou Headscale) |
| `PASSWORD` | Senha do usuário root para acesso SSH ao container |

---

### 5. Criar e iniciar o container

Configure o registry para usar o GitHub Container Registry:

```routeros
/container/config set registry-url=https://ghcr.io tmpdir=disk1
```

> **Importante:** Use `ghcr.io` e não `registry-1.docker.io`. O Docker Hub requer autenticação para pull de imagens privadas/limitadas, o que causaria erro 401. A imagem está disponível publicamente no GHCR.

Crie o container:

```routeros
/container add \
  remote-image=fluent-networks/tailscale-mikrotik:latest \
  interface=veth1 \
  envlist=tailscale \
  root-dir=tailscale \
  start-on-boot=yes
```

O roteador iniciará o download e extração da imagem automaticamente (~30MB, leva 1-2 minutos). Acompanhe com:

```routeros
/container print
# Flags: E = EXTRACTING, S = STOPPED, R = RUNNING
```

Quando a flag mudar para `S` (stopped), inicie o container:

```routeros
/container start 0
```

---

### 6. Aprovar rotas no console do Tailscale

Após o container iniciar, acesse o [Admin Console do Tailscale](https://login.tailscale.com/admin/machines), localize o dispositivo TESTADO e **aprove a subnet route** (`10.0.10.0/24`).

Sem essa aprovação, outros dispositivos da rede Tailscale não conseguirão rotear tráfego para a LAN do MikroTik.

---

## Validação do funcionamento

### Verificar se o container está rodando

```routeros
/container print
# Flags: R - RUNNING  → container ativo
# MEMORY-CURRENT: ~38-40MiB → consumo normal
```

### Verificar conectividade com o container

```routeros
/ping address=172.17.0.2 count=3
# Deve responder com TTL=64 e latência < 1ms
```

### Verificar rota Tailscale ativa

```routeros
/ip/route print where dst-address~"100.64"
# Deve mostrar: As 100.64.0.0/10  172.17.0.2  main  (A = ACTIVE)
```

### Verificar logs do container

```routeros
/log print where topics~"container"
```

Logs esperados durante inicialização bem-sucedida:

```
*** importing remote image: registry:ghcr.io ...
*** import done
*** start
*** started PATH=... AUTH_KEY=... /usr/local/bin/tailscale.sh
```

### Verificar arquivos de estado do Tailscale

```routeros
/file print where name~"tailscale"
```

Os arquivos abaixo confirmam autenticação bem-sucedida:

```
tailscale/var/lib/tailscale/tailscaled.state   → estado e perfil autenticado
tailscale/var/lib/tailscale/derpmap.cached.json → mapa de relays DERP baixado
```

### Acessar o container via SSH (para diagnóstico avançado)

O container roda um servidor SSH na porta 22 (172.17.0.2). Acesse a partir de um host na rede 172.17.0.0/16 ou via tunnel pelo próprio roteador:

```bash
ssh root@172.17.0.2
# Senha: valor definido na variável PASSWORD
```

Comandos úteis dentro do container:

```bash
tailscale status          # status da conexão e peers
tailscale ip -4           # IP atribuído pelo Tailscale (100.x.x.x)
tailscale ping <peer>     # testar conectividade com outro peer
tailscaled --version      # versão do daemon
```

---

## Topologia de rede configurada

```
Internet
   │
   ▼
ether1 (172.31.2.251/25)  ← WAN
   │
[MikroTik hAP ax lite]
   │
   ├── bridge1 (10.0.10.1/24)  ← LAN (anunciada via Tailscale)
   │      └── ether3, ether4, wifi1
   │
   └── dockers bridge (172.17.0.1/16)  ← rede interna Docker
          └── veth1 → container Tailscale (172.17.0.2)
                         │
                         └── tailscale0 (100.x.x.x)  ← IP Tailscale
```

Rota adicionada no MikroTik:
```
100.64.0.0/10  →  172.17.0.2  (via container Tailscale)
```

---

## Configuração persistente (após reboot)

A configuração é totalmente persistente:

- O container tem `start-on-boot=yes` — inicia automaticamente com o roteador
- As variáveis de ambiente e rotas ficam salvas na config do RouterOS
- O estado de autenticação do Tailscale é salvo em `tailscale/var/lib/tailscale/tailscaled.state`

Não é necessário re-autenticar após reinicializações.

---

## Solução de problemas

### Container não inicia / fica em STOPPED

```routeros
/log print where topics~"container"
```

Causas comuns:
- `could not load config.json` → imagem não foi baixada corretamente. Remova e recrie o container.
- `fetch manifest failed: http code: 401` → registry errado. Use `ghcr.io`, não `registry-1.docker.io`.
- Espaço insuficiente → verifique com `/system resource print` (precisa de ~50MB livres).

### Tailscale não conecta

1. Verifique se a `AUTH_KEY` está correta e não expirou no console do Tailscale
2. Confirme que o container consegue acesso à internet: o roteador deve ter rota default e DNS funcionando
3. Verifique se `tailscaled.state` foi criado em `tailscale/var/lib/tailscale/`

### Peers não conseguem acessar a LAN (10.0.10.0/24)

1. Acesse login.tailscale.com/admin/machines
2. Encontre o dispositivo MikroTik
3. Clique em "..." → "Edit route settings"
4. Habilite a rota `10.0.10.0/24`

### Device-mode container=yes não persiste

O comando `/system/device-mode/update container=yes` requer confirmação física (botão reset). Se não foi confirmado no prazo de 5 minutos, execute novamente e pressione o botão a tempo.

---

## Referências

- Repositório do container: https://github.com/Fluent-networks/tailscale-mikrotik
- Documentação MikroTik Containers: https://help.mikrotik.com/docs/display/ROS/Container
- Tailscale Admin Console: https://login.tailscale.com/admin
- Download pacotes MikroTik: https://mikrotik.com/download
