# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This repository documents a personal learning journey to set up a Kubernetes cluster using kubeadm on local KVM virtual machines. The project evolved from manual step-by-step setup to automated provisioning using Python, Terraform, and Ansible.

## Two Approaches to K8s Cluster Setup

### 1. Manual Setup (step-01 through step-10)
Each `step-XX/` directory contains documentation and configuration files for manual cluster setup stages:
- step-01: Initial KVM VM creation with virt-install
- step-02 through step-05: K8s cluster initialization and configuration
- step-06: Sample application deployment with HAProxy ingress
- step-07: Adding additional worker nodes
- step-08: Remote kubectl access configuration
- step-09: Developer user account setup
- step-10: Private image registry setup

These directories serve as reference documentation and history of the learning process.

### 2. Automated Provisioning (scripts/)
The `scripts/` directory contains automation to provision the entire cluster:
- **provisioner.py**: Main Python script that orchestrates the provisioning
- **configs/config.yaml**: Single source of truth for all cluster configuration
- **templates/**: Jinja2 templates for cloud-init configs and Terraform files
- **run/**: Generated scripts and files (created at runtime, may not exist in repo)

**Two VM provisioning approaches:**
- **virt-install (primary)**: Shell scripts using `virt-install` + `cloud-localds` for cloud-init ISOs. Reliable and straightforward.
- **Terraform (backup)**: Uses the `libvirt` provider. Kept as a backup approach since the Terraform libvirt provider is not yet stable.

## Cluster Architecture

**Infrastructure**:
- Runs on libvirt/KVM with Fedora 43 Cloud minimal images
- 3 master nodes + 3 worker nodes
- Static IP addresses (192.168.150.x subnet)
- VMs provisioned with cloud-init for initial configuration

**Kubernetes Stack**:
- Container Runtime: containerd or CRI-o (configurable in config.yaml)
- CNI Plugin: Flannel or Calico (configurable)
- kube-proxy mode: iptables (default) or ipvs
- Ingress Controller: HAProxy
- Image Registry: Private insecure registry on host (port 5000)

**Network Flow**:
```
External → HAProxy (NodePort) → Service (ClusterIP) → Pods
           (Layer 7)              (kube-proxy)         (CNI)
```

## Configuration

All cluster configuration is centralized in `scripts/configs/config.yaml`:
- libvirt connection URI and image directory
- SSH credentials and public key
- OS base image URL (Fedora 43 Cloud qcow2)
- Node definitions (name, IP, type, resources, labels)
- Kubernetes version and component choices (runtime, CNI)

Edit this file to customize the cluster before provisioning.

## Common Commands

### VM Management (libvirt)
```bash
# List all VMs
virsh list --all

# Start/stop VMs
virsh start <vm-name>
virsh shutdown <vm-name>

# Delete VM definition (does not remove disk)
virsh undefine <vm-name>

# SSH into VMs
ssh lgao@k8s-master1
ssh lgao@k8s-worker1
```

### Kubernetes Operations
```bash
# Basic cluster info
kubectl cluster-info
kubectl get nodes
kubectl get pods --all-namespaces

# Deploy application
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml
kubectl apply -f ingress.yaml

# Check kube-proxy mode
kubectl get configmap kube-proxy -n kube-system -o yaml | grep mode

# Access HAProxy stats (if configured)
# NodePort is dynamically assigned, check with:
kubectl get svc -n haproxy-controller
```

### Python Provisioner Workflow
```bash
# Install Python dependencies
pip install -r scripts/requirements.txt

# Generate all files (virt-install scripts + cloud-init + Terraform)
python scripts/provisioner.py generate

# virt-install workflow (primary)
cd scripts/run
./virt-install-setup-network.sh      # Create libvirt network
./virt-install-create-vms.sh         # Create cloud-init ISOs + VMs
./virt-install-cleanup.sh            # Destroy VMs when done

# Terraform workflow (backup — libvirt provider is unstable)
python scripts/provisioner.py init
python scripts/provisioner.py plan
python scripts/provisioner.py apply --auto-approve
python scripts/provisioner.py destroy --auto-approve
```

The provisioner workflow:
1. Loads `configs/config.yaml`
2. Reads the SSH public key file and injects the content into cloud-init
3. Downloads base OS image to `image_dir` if URL is remote and libvirt is local
4. Generates `run/cloud-init-user-data-<node>.yaml` and `run/cloud-init-network-config-<node>.yaml` for each node
5. Generates virt-install shell scripts (`setup-network.sh`, `create-vms.sh`, `cleanup.sh`)
6. Generates `run/main.tf` from `templates/main.tf.j2` (Terraform backup)
7. The `create-vms.sh` script uses `cloud-localds` to build persistent cloud-init ISOs, then `virt-install` to create VMs
8. Generates Ansible inventory (`scripts/ansible/inventory.ini`) and group_vars (`scripts/ansible/group_vars/all.yml`)

### Ansible Day-1 (K8s Installation)
```bash
# After VMs are provisioned and running:
cd scripts/ansible
ansible-playbook -i inventory.ini site.yml
```

The Ansible playbook executes roles in order:
1. **common** — CRI-O, kubelet, kubeadm, kubectl, CNI plugins (all nodes)
2. **ha-control-plane** — keepalived + HAProxy for API server VIP (masters)
3. **master-init** — kubeadm init on first master
4. **calico** — Calico CNI via Tigera operator
5. **master-join** — additional masters join control plane
6. **worker** — workers join cluster
7. **operators** — install configured operators (e.g., lvm-operator)

To add a new operator:
1. Create `scripts/ansible/operators/<name>/install.sh` (and any manifests)
2. Add the name to `k8s.operators` list in `config.yaml`
3. Re-run `provisioner.py generate` and the ansible playbook

### Image Registry
```bash
# Start local registry on host
docker run -d -p 5000:5000 --restart=always \
  -v ~/mnt/registry:/var/lib/registry \
  --name image-registry registry:2

# Push image to registry
docker tag <image> virt.lins-p1:5000/<image>
docker push virt.lins-p1:5000/<image>

# Use in K8s manifests
# image: virt.lins-p1:5000/helloworld:latest
```

## Important Implementation Notes

### Cloud-init Configuration
VMs are provisioned with cloud-init for initial setup:
- Creates SSH user with password and public key
- Configures static networking
- Sets hostname
- Cloud-init configs are in `step-01/` for manual setup or generated from templates for automated setup

### Containerd Configuration for Insecure Registry
To use the insecure image registry (virt.lins-p1:5000), add to `/etc/containerd/config.toml` on each node:
```ini
[plugins."io.containerd.grpc.v1.cri".registry.configs."virt.lins-p1:5000".tls]
  insecure_skip_verify = true

[plugins."io.containerd.grpc.v1.cri".registry.mirrors."virt.lins-p1:5000"]
  endpoint = ["http://virt.lins-p1:5000"]
```
Then `systemctl restart containerd`

### Kubernetes Networking Components
- **kube-proxy** (Layer 4): Service abstraction and load balancing via iptables/ipvs NAT rules
- **CNI plugin** (Layer 3): Pod-to-pod connectivity across nodes (assigns pod IPs, sets up network interfaces)
- **HAProxy Ingress** (Layer 7): External traffic routing to services, runs on infrastructure node

### Limitations and Assumptions
- SELinux is disabled (unlike OpenShift)
- No firewall enabled
- Static IP addresses (not DHCP)
- Insecure image registry (no TLS, no authentication)

## Key Architecture Decision: Templates + Python + Terraform

Terraform's HCL syntax can be complex for dynamic configurations. This project uses Python to:
1. Parse YAML config (more readable than HCL)
2. Render Jinja2 templates to generate Terraform files + per-node cloud-init ISOs
3. Execute Terraform commands programmatically
4. Optionally chain into Day-1 Ansible (not yet implemented)

This allows expressing the full cluster topology in a single YAML while leveraging Terraform's libvirt provider for idempotent VM lifecycle management.

## Terraform Resource Design

Key design decisions in `templates/main.tf.j2`:
- `libvirt_network` with per-node `dns.hosts` entries — libvirt's built-in dnsmasq resolves `<hostname>.k8s.local` within the cluster subnet and from the host (via NetworkManager auto-configuration)
- `libvirt_volume` base image with `lifecycle { prevent_destroy = true }` — shared read-only parent
- Per-node OS volumes use `base_volume_id` for COW thin-clones (efficient, no full copy)
- Data disks managed via `nodes_with_data_disk = { for k, v in local.all_nodes : k => v if v.data_disk_size > 0 }` — only nodes with `data_disk_size > 0` get a second disk
- Cloud-init ISOs reference `${path.module}/cloud-init-user-data-<node>.yaml` and `${path.module}/cloud-init-network-config-<node>.yaml` — both files live in `run/` alongside `main.tf`

## Cloud-init Split: user-data vs network-config

The `libvirt_cloudinit_disk` resource takes two separate files:
- **user-data** (`cloud-init-user-data.yaml.j2`): packages, users, sysctl, modules, disk setup, runcmds. Sets static `/etc/hosts` entries for all cluster nodes (pre-DNS fallback).
- **network-config** (`cloud-init-network-config.yaml.j2`): network v2 static IP config pointing DNS to the libvirt bridge IP.

## Node.js Dependencies

The repository includes `package.json` with a dependency on `qwen-code`. This is likely for AI-assisted code generation or analysis during development.
