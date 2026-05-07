# Baremetal K8s Cluster Provisioning via Redfish

**Date:** 2026-05-07
**Status:** Draft

## Overview

Add baremetal Kubernetes cluster provisioning to the play_k8s project, using Redfish BMC protocol and Ubuntu autoinstall ISOs mounted via Virtual Media. This sits alongside the existing `scripts/` directory (which handles libvirt VM-based clusters) as a new `baremetal/` directory following the same config-driven patterns.

## Architecture Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Directory | `baremetal/` at project root | Parallel to `scripts/`, self-contained |
| Orchestrator | Python provisioner + Taskfile | Proven pattern from VM setup; Taskfile provides CLI |
| Taskfile location | Inside `baremetal/` | Self-contained; `cd baremetal && task ...` |
| OS | Ubuntu 22.04 LTS | User requirement |
| Boot method | Redfish Virtual Media | No DHCP/TFTP infrastructure needed; simpler than PXE |
| ISO strategy | Custom per-node ISO with embedded autoinstall | Fully unattended, no network dependency during install |
| BMC vendor | Vendor-agnostic | Redfish paths configurable per-node with defaults |
| Container runtime | CRI-O (default) | Configurable: cri-o or containerd |
| CNI | Cilium (default) | Best for large clusters; configurable: cilium or calico |
| kube-proxy mode | IPVS (default) | O(1) lookups, required at 500+ node scale |
| HA control plane | 3 dedicated infra nodes (HAProxy + keepalived) | Standard production pattern; same as VM setup |
| Master count | 5 (default for 500-2000 nodes) | Etcd quorum tolerates 2 failures |
| Network sizing | 10.20.0.0/16 node subnet | Fits 2000+ nodes comfortably |
| Bootstrap host | Provisioned from scratch | Ansible role installs DNS, HTTP, ISO tools |

## Directory Structure

```
baremetal/
├── Taskfile.yml                        # Task definitions
├── provisioner.py                      # Python orchestrator
├── requirements.txt                    # Python deps: jinja2, pyyaml, requests
├── configs/
│   └── config.yaml                     # Single source of truth
├── templates/
│   ├── autoinstall-user-data.yaml.j2   # Ubuntu autoinstall (per-node)
│   ├── network-config.yaml.j2          # Netplan static IP
│   ├── dnsmasq.conf.j2                 # DNS config for bootstrap host
│   └── nginx-site.conf.j2             # HTTP server config
├── ansible/
│   ├── ansible.cfg
│   ├── inventory.ini                   # Auto-generated
│   ├── group_vars/
│   │   └── all.yml                     # Auto-generated K8s vars
│   ├── site.yml                        # Main playbook
│   └── roles/
│       ├── bootstrap-host/             # DNS + HTTP + ISO tools
│       │   └── tasks/main.yml
│       ├── common/                     # K8s prereqs on all nodes
│       │   └── tasks/main.yml
│       ├── ha-control-plane/           # HAProxy + keepalived
│       │   ├── tasks/main.yml
│       │   └── templates/
│       ├── master-init/                # kubeadm init
│       │   └── tasks/main.yml
│       ├── master-join/                # Additional masters
│       │   └── tasks/main.yml
│       ├── worker/                     # Worker join
│       │   └── tasks/main.yml
│       ├── cilium/                     # Cilium CNI
│       │   └── tasks/main.yml
│       ├── calico/                     # Calico CNI (alternative)
│       │   └── tasks/main.yml
│       └── operators/                  # Operator orchestrator
│           └── tasks/main.yml
├── scripts/
│   ├── redfish.sh                      # Redfish API helper
│   └── build-iso.sh                    # ISO build helper
├── operators/                          # Per-operator install scripts
│   └── (extensible)
└── run/                                # Generated files (ISOs, configs)
```

## Configuration Schema

```yaml
# baremetal/configs/config.yaml

# Bootstrap host — runs DNS, HTTP, orchestrates Redfish calls
bootstrap_host:
  ip: "10.20.0.10"
  hostname: "bootstrap"
  interface: "eno1"
  dns_upstream: "8.8.8.8"
  http_port: 8080
  ssh:
    username: "admin"
    password: "password"
    public_key_file: "~/.ssh/id_rsa.pub"

# Network — sized for 500-2000 nodes
network:
  domain: "k8s.local"
  subnet: "10.20.0.0/16"
  gateway: "10.20.0.1"
  dns: "10.20.0.10"               # Bootstrap host dnsmasq

# K8s API VIP (managed by keepalived across infra nodes)
k8s_api_vip:
  ip: "10.20.0.200"
  hostname: "k8s-api"

# OS configuration
os:
  name: "ubuntu"
  version: "22.04"
  iso_url: "https://releases.ubuntu.com/22.04.4/ubuntu-22.04.4-live-server-amd64.iso"
  iso_dir: "/opt/baremetal/iso"

# Node definitions
nodes:
  defaults:
    interface: "eno1"
    disk: "/dev/sda"
    redfish:
      scheme: "https"
      base_uri: "/redfish/v1/Systems/1"
      manager_uri: "/redfish/v1/Managers/1"    # For VirtualMedia endpoints
      virtual_media_slot: "CD"                  # VirtualMedia slot name
      verify_ssl: false

  infra:   # 3 infra nodes — HAProxy + keepalived
    - name: "infra1"
      ip: "10.20.0.11"
      bmc:
        address: "10.20.100.11"
        username: "admin"
        password: "admin"
    - name: "infra2"
      ip: "10.20.0.12"
      bmc:
        address: "10.20.100.12"
        username: "admin"
        password: "admin"
    - name: "infra3"
      ip: "10.20.0.13"
      bmc:
        address: "10.20.100.13"
        username: "admin"
        password: "admin"

  masters:  # 5 masters — etcd quorum for large clusters
    - name: "master1"
      ip: "10.20.1.1"
      bmc:
        address: "10.20.100.21"
        username: "admin"
        password: "admin"
    - name: "master2"
      ip: "10.20.1.2"
      bmc:
        address: "10.20.100.22"
        username: "admin"
        password: "admin"
    - name: "master3"
      ip: "10.20.1.3"
      bmc:
        address: "10.20.100.23"
        username: "admin"
        password: "admin"
    - name: "master4"
      ip: "10.20.1.4"
      bmc:
        address: "10.20.100.24"
        username: "admin"
        password: "admin"
    - name: "master5"
      ip: "10.20.1.5"
      bmc:
        address: "10.20.100.25"
        username: "admin"
        password: "admin"

  workers:
    - name: "worker1"
      ip: "10.20.2.1"
      disk: "/dev/nvme0n1"          # Per-node override
      bmc:
        address: "10.20.100.31"
        username: "admin"
        password: "admin"
      redfish:                       # Per-node Redfish override (e.g., Dell iDRAC)
        base_uri: "/redfish/v1/Systems/System.Embedded.1"

# Kubernetes configuration
k8s:
  version: "1.31"
  container_runtime: "cri-o"
  cni: "cilium"                      # cilium or calico
  kube_proxy_mode: "ipvs"            # ipvs (recommended 500+ nodes) or iptables
  pod_network_cidr: "10.128.0.0/14"  # Supports 2000+ nodes with /24 per node
  service_cidr: "10.96.0.0/16"
  operators: []
```

### Per-node BMC and Redfish Fields

Each node requires:
- `bmc.address` — BMC/iDRAC/iLO management IP
- `bmc.username` / `bmc.password` — BMC credentials

Optional per-node Redfish overrides (fall back to `nodes.defaults.redfish`):
- `redfish.scheme` — `https` (default) or `http`
- `redfish.base_uri` — System path (e.g., `/redfish/v1/Systems/System.Embedded.1` for Dell)
- `redfish.manager_uri` — Manager path (e.g., `/redfish/v1/Managers/iDRAC.Embedded.1` for Dell)
- `redfish.virtual_media_slot` — VirtualMedia slot name (e.g., `CD`, `2`)
- `redfish.verify_ssl` — Certificate verification (default: `false`)

The `network.prefix_length` used in autoinstall templates is derived from `network.subnet` at generation time (e.g., `10.20.0.0/16` → prefix_length `16`).

This makes the tooling vendor-agnostic: Dell iDRAC, HPE iLO, Supermicro, and generic Redfish BMCs all work by configuring the `base_uri` per node.

## Taskfile Tasks

```yaml
# baremetal/Taskfile.yml

tasks:
  generate:
    desc: Generate all files from config.yaml
    # Runs provisioner.py generate
    # Outputs: autoinstall YAMLs, ansible inventory, dnsmasq.conf, nginx.conf

  bootstrap:
    desc: Set up bootstrap host (DNS, HTTP, ISO tools)
    # Runs: generate → ansible-playbook -l bootstrap site.yml

  build-iso:
    desc: Build autoinstall ISOs (all nodes or NODE=xxx)
    # Runs provisioner.py build-iso [--node NODE]
    # On bootstrap host: download base ISO, extract, inject autoinstall, repack

  deploy:
    desc: Full cluster deployment from scratch
    # Runs: generate → bootstrap → build-iso → redfish-boot all → wait SSH → ansible site.yml
    # This is the "do everything" command

  add-node:
    desc: Add a single node to existing cluster
    vars: [NODE]
    # Runs: build-iso for NODE → redfish mount+boot → wait SSH → ansible --limit NODE
    # Determines role (master/worker) from config.yaml

  remove-node:
    desc: Drain and remove a node from the cluster
    vars: [NODE]
    # Runs: kubectl drain → kubectl delete node → redfish power off

  power:
    desc: Power control via Redfish
    vars: [NODE, ACTION]  # ACTION: on, off, status, cycle
    # Calls redfish.sh for the specified node

  reboot:
    desc: Reboot a node via Redfish
    vars: [NODE]
    # Redfish graceful restart
```

## Provisioning Workflows

### Full Deploy (`task deploy`)

```
1. provisioner.py generate
   ├── Read config.yaml
   ├── Read SSH public key
   ├── Generate run/autoinstall-<node>.yaml (per node, from template)
   ├── Generate run/network-config-<node>.yaml (per node)
   ├── Generate ansible/inventory.ini
   ├── Generate ansible/group_vars/all.yml
   ├── Generate run/dnsmasq.conf
   └── Generate run/nginx-site.conf

2. ansible-playbook site.yml --tags bootstrap
   ├── Install dnsmasq → DNS for *.k8s.local
   ├── Install nginx → HTTP on port 8080
   ├── Install xorriso, p7zip-full, genisoimage
   ├── Download Ubuntu 22.04 ISO (cached)
   └── Open firewall: DNS/53, HTTP/8080

3. provisioner.py build-iso (runs on bootstrap host via SSH/ansible)
   For each node:
   ├── Extract Ubuntu ISO
   ├── Inject autoinstall user-data + network-config into ISO
   ├── Repack as run/<node>.iso
   └── Copy to nginx served directory

4. provisioner.py boot-nodes (Redfish, sequential or parallel)
   For each node:
   ├── POST VirtualMedia.InsertMedia → mount http://bootstrap:8080/iso/<node>.iso
   ├── PATCH Boot → BootSourceOverrideTarget: Cd, BootSourceOverrideEnabled: Once
   ├── POST ComputerSystem.Reset → ResetType: On (or ForceRestart)
   ├── Poll: wait for Ubuntu autoinstall to complete (~10-20 min)
   └── Poll: wait for SSH to become available

5. ansible-playbook site.yml (K8s Day-1)
   ├── common (all nodes)         → CRI-O, kubelet, kubeadm
   ├── ha-control-plane (infra)   → HAProxy + keepalived
   ├── master-init (masters[0])   → kubeadm init
   ├── cilium (masters[0])        → Cilium CNI install
   ├── master-join (masters[1:])  → kubeadm join --control-plane (serial: 1)
   ├── worker (workers)           → kubeadm join
   └── operators (masters[0])     → configured operators
```

### Add Node (`task add-node NODE=worker4`)

```
1. provisioner.py lookup-node worker4
   └── Find in config.yaml → IP, BMC, disk, redfish settings

2. provisioner.py build-iso --node worker4
   └── Build single autoinstall ISO for worker4

3. Redfish sequence for worker4:
   ├── InsertMedia → mount ISO
   ├── Set boot override → Cd, Once
   ├── Reset → power on
   └── Wait for SSH

4. ansible-playbook site.yml --limit worker4
   ├── common role → CRI-O, kubelet, kubeadm
   └── worker role → kubeadm join (fetch token from existing master)
```

## Redfish API Reference

All calls use HTTP Basic Auth: `curl -k -u $USER:$PASS`

### Power Management

```
# Power on
POST {scheme}://{bmc_address}{base_uri}/Actions/ComputerSystem.Reset
Body: {"ResetType": "On"}

# Power off (graceful)
POST {scheme}://{bmc_address}{base_uri}/Actions/ComputerSystem.Reset
Body: {"ResetType": "GracefulShutdown"}

# Force restart
POST {scheme}://{bmc_address}{base_uri}/Actions/ComputerSystem.Reset
Body: {"ResetType": "ForceRestart"}

# Get power state
GET {scheme}://{bmc_address}{base_uri}
Response: .PowerState → "On" | "Off"
```

### Virtual Media

```
# Mount ISO
POST {scheme}://{bmc_address}{manager_uri}/VirtualMedia/{slot}/Actions/VirtualMedia.InsertMedia
Body: {"Image": "http://10.20.0.10:8080/iso/worker1.iso", "TransferProtocolType": "HTTP"}

# Eject ISO
POST {scheme}://{bmc_address}{manager_uri}/VirtualMedia/{slot}/Actions/VirtualMedia.EjectMedia
Body: {}

# Check virtual media state
GET {scheme}://{bmc_address}{manager_uri}/VirtualMedia/{slot}
Response: .Inserted → true | false
```

Where `{manager_uri}` and `{slot}` come from the node's redfish config (defaults: `/redfish/v1/Managers/1` and `CD`).

### Boot Override

```
# Set one-time boot to virtual CD
PATCH {scheme}://{bmc_address}{base_uri}
Body: {"Boot": {"BootSourceOverrideTarget": "Cd", "BootSourceOverrideEnabled": "Once"}}

# Set one-time boot to PXE (if ever needed)
PATCH {scheme}://{bmc_address}{base_uri}
Body: {"Boot": {"BootSourceOverrideTarget": "Pxe", "BootSourceOverrideEnabled": "Once"}}
```

Note: Dell iDRAC example overrides: `manager_uri: /redfish/v1/Managers/iDRAC.Embedded.1`, `virtual_media_slot: CD`. HPE iLO example: `manager_uri: /redfish/v1/Managers/1`, `virtual_media_slot: 2`.

## Ansible Roles Detail

### bootstrap-host

**Target:** bootstrap host
**Purpose:** Make the bootstrap machine ready to serve DNS, HTTP, and build ISOs

Tasks:
1. Install packages: `dnsmasq`, `nginx`, `xorriso`, `p7zip-full`, `genisoimage`, `python3-pip`
2. Deploy `dnsmasq.conf` from template — resolve `*.k8s.local` to node IPs, forward upstream
3. Deploy `nginx` site config — serve `/opt/baremetal/iso/` on HTTP port
4. Download Ubuntu 22.04 base ISO to `iso_dir` (skip if cached)
5. Enable and start dnsmasq + nginx services
6. Configure firewall (ufw: allow 53/udp, 53/tcp, 8080/tcp)

### common

**Target:** all K8s nodes (masters + workers)
**Purpose:** Prepare OS for Kubernetes

Tasks:
1. Disable swap (`swapoff -a`, remove from fstab)
2. Load kernel modules: `overlay`, `br_netfilter`
3. Set sysctl: `net.bridge.bridge-nf-call-iptables=1`, `net.ipv4.ip_forward=1`
4. Add CRI-O repository (for Ubuntu 22.04)
5. Install CRI-O and start service
6. Add Kubernetes apt repository
7. Install kubeadm, kubelet, kubectl (pinned to `k8s.version`)
8. Hold packages to prevent auto-upgrade
9. Configure crictl to use CRI-O socket

### ha-control-plane

**Target:** infra nodes (3)
**Purpose:** Load balance K8s API server traffic

Tasks:
1. Install HAProxy and keepalived
2. Deploy HAProxy config — frontend on `:6443`, backends are all master IPs on `:6443`
3. Deploy keepalived config — VRRP instance with VIP, priority-based (infra1=101, infra2=100, infra3=99)
4. Enable health check: TCP connect to localhost:6443
5. Start and enable both services

### master-init

**Target:** masters[0] only
**Purpose:** Initialize the Kubernetes control plane

Tasks:
1. Check if `/etc/kubernetes/admin.conf` exists (skip if already initialized)
2. Run `kubeadm init` with:
   - `--control-plane-endpoint=k8s-api:6443`
   - `--upload-certs`
   - `--pod-network-cidr` from config
   - `--service-cidr` from config
3. Copy kubeconfig to user's `~/.kube/config`
4. Generate join commands (control-plane + worker) and register as Ansible facts
5. Store certificate key for master joins

### cilium

**Target:** masters[0]
**Purpose:** Install Cilium CNI

Tasks:
1. Install Cilium CLI (latest stable)
2. Run `cilium install --set cluster.name=k8s --set ipam.operator.clusterPoolIPv4PodCIDRList=<pod_cidr>`
3. Wait for `cilium status` to report all components ready
4. Validate connectivity with `cilium connectivity test` (optional, can be slow)

### calico (alternative)

**Target:** masters[0]
**Purpose:** Install Calico CNI via Tigera operator (same as VM setup)

### master-join

**Target:** masters[1:], serial: 1
**Purpose:** Join additional control plane nodes

Tasks:
1. Run `kubeadm join` with `--control-plane` flag using token from master-init
2. Wait for node to become Ready

### worker

**Target:** workers
**Purpose:** Join worker nodes to the cluster

Tasks:
1. Run `kubeadm join` using token from master-init
2. Wait for node to become Ready

### operators

**Target:** masters[0]
**Purpose:** Install configured operators

Same extensible pattern as VM setup:
- Each operator has `operators/{name}/install.sh`
- Role loops through `k8s.operators` list and runs each install script

## Ubuntu Autoinstall ISO Build Process

The provisioner builds per-node ISOs on the bootstrap host:

1. **Download** Ubuntu 22.04 live server ISO (once, cached in `iso_dir`)
2. **Extract** ISO contents to a temp directory using `7z x` or mount+copy
3. **Inject** autoinstall config:
   - Create `autoinstall/user-data` from rendered Jinja2 template
   - Create `autoinstall/meta-data` (empty or minimal)
   - Modify `grub.cfg` boot entry to add `autoinstall ds=nocloud;` kernel parameter
4. **Repack** ISO using `xorriso` with EFI and BIOS boot support
5. **Place** resulting `<node>.iso` in nginx served directory

### Autoinstall user-data template (key sections)

```yaml
#cloud-config
autoinstall:
  version: 1
  locale: en_US.UTF-8
  keyboard:
    layout: us
  identity:
    hostname: {{ node.name }}
    username: {{ ssh.username }}
    password: {{ ssh.password | password_hash }}
  ssh:
    install-server: true
    authorized-keys:
      - {{ ssh_public_key }}
  storage:
    layout:
      name: direct
      match:
        path: {{ node.disk }}
  network:
    version: 2
    ethernets:
      {{ node.interface }}:
        addresses:
          - {{ node.ip }}/{{ network.prefix_length }}
        gateway4: {{ network.gateway }}
        nameservers:
          addresses:
            - {{ network.dns }}
        search:
          - {{ network.domain }}
  packages:
    - openssh-server
    - curl
    - apt-transport-https
    - ca-certificates
  late-commands:
    - echo '{{ node.name }}' > /target/etc/hostname
```

## Network Architecture

```
                    ┌──────────────────────────────┐
                    │     External Network          │
                    │       10.20.0.0/16            │
                    └──────────┬───────────────────-┘
                               │
              ┌────────────────┼────────────────────┐
              │                │                     │
     ┌────────▼──────┐  ┌─────▼──────────┐   ┌─────▼──────────┐
     │  Bootstrap    │  │  Infra Nodes   │   │  BMC Network   │
     │  10.20.0.10   │  │  10.20.0.11-13 │   │  10.20.100.x   │
     │  DNS + HTTP   │  │  HAProxy+KVIP  │   │  (management)  │
     └───────────────┘  │  VIP:10.20.0.200│   └────────────────┘
                        └────────┬────────┘
                                 │ :6443
              ┌──────────────────┼──────────────────┐
              │                  │                   │
     ┌────────▼──────┐  ┌───────▼───────┐  ┌───────▼───────┐
     │  Masters      │  │  Masters      │  │  Workers      │
     │  10.20.1.1-5  │  │  (cont.)      │  │  10.20.2.x    │
     │  etcd + API   │  │               │  │  workloads    │
     └───────────────┘  └───────────────┘  └───────────────┘
```

- **Bootstrap host** (10.20.0.10): DNS (dnsmasq for *.k8s.local), HTTP (nginx serving ISOs), control point for Redfish calls
- **Infra nodes** (10.20.0.11-13): HAProxy + keepalived, VIP at 10.20.0.200
- **Masters** (10.20.1.1-5): etcd + K8s API server, 5-node quorum
- **Workers** (10.20.2.x+): application workloads
- **BMC network** (10.20.100.x): out-of-band management, Redfish API access

## Scale Considerations (500-2000 nodes)

| Concern | Solution |
|---------|----------|
| kube-proxy iptables O(n²) | Default to IPVS mode (hash-table, O(1)) |
| Pod CIDR exhaustion | `10.128.0.0/14` = 4096 nodes × 256 pods/node |
| Node subnet exhaustion | `10.20.0.0/16` = 65k addresses |
| etcd performance | 5 masters for quorum at scale |
| API server load | 3 infra nodes with HAProxy |
| ARP broadcast storms | Document: use VLANs/L3 switching for physical network |
| Cilium IPAM | cluster-scope IPAM handles large clusters natively |

## Implementation Order

1. **Config & templates** — config.yaml, Jinja2 templates (autoinstall, dnsmasq, nginx)
2. **provisioner.py** — Config loading, template rendering, ISO build orchestration, Redfish client
3. **Redfish helper** — `scripts/redfish.sh` for power, boot, virtual media operations
4. **Ansible roles** — bootstrap-host → common → ha-control-plane → master-init → cilium → calico → master-join → worker → operators
5. **Taskfile** — Wire up all tasks (generate, bootstrap, build-iso, deploy, add-node, etc.)
6. **Testing** — Validate with a small cluster (1 infra + 1 master + 1 worker) before scaling
