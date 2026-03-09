# Ansible Day-1 K8s Cluster Installation — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Automate HA Kubernetes cluster installation on pre-provisioned VMs using Ansible with CRI-O, Calico, keepalived/HAProxy, and extensible operator support.

**Architecture:** `provisioner.py` generates Ansible inventory and group_vars from `config.yaml`. Static Ansible playbooks (not templated) use roles executed in order: common packages on all nodes, HA control plane on masters, kubeadm init on first master, Calico CNI, additional master/worker joins, and operator installation.

**Tech Stack:** Ansible, CRI-O, kubeadm, Calico (Tigera operator), keepalived, HAProxy, TopoLVM (for LVM storage operator)

**Design doc:** `docs/plans/2026-03-09-ansible-k8s-day1-design.md`

---

### Task 1: Update config.yaml with K8s Day-1 settings

**Files:**
- Modify: `scripts/configs/config.yaml`

**Step 1: Add pod_network_cidr, service_cidr, and operators to k8s section**

Replace the existing `k8s:` section:

```yaml
k8s:
  container_runtime: "cri-o"
  cni: "Calico"
  k8s_version: "1.35"
  pod_network_cidr: "10.244.0.0/16"
  service_cidr: "10.96.0.0/12"
  operators:
    - lvm-operator
```

**Step 2: Commit**

```bash
git add scripts/configs/config.yaml
git commit -m "Add K8s Day-1 settings: pod/service CIDRs and operators list"
```

---

### Task 2: Add Ansible inventory and group_vars generation to provisioner.py

**Files:**
- Modify: `scripts/provisioner.py`

**Step 1: Add generate_ansible_inventory() function**

After the `generate_virt_install_cleanup_script()` function, add a new function that:
- Creates `scripts/ansible/` and `scripts/ansible/group_vars/` directories
- Writes `inventory.ini` with `[masters]` and `[workers]` groups from nodes list
- Each host line: `<name> ansible_host=<ip>`
- `[all:vars]` section with `ansible_user=<ssh.username>` and `ansible_become=yes`

```python
def generate_ansible_files(config: dict, nodes: list):
    """Generate Ansible inventory and group_vars from config.yaml."""
    ansible_dir = SCRIPT_DIR / "ansible"
    ansible_dir.mkdir(parents=True, exist_ok=True)
    group_vars_dir = ansible_dir / "group_vars"
    group_vars_dir.mkdir(parents=True, exist_ok=True)

    ssh_user = config["ssh"]["username"]
    net = config["network"]
    k8s = config.get("k8s", {})
    vip = config.get("k8s_api_vip", {})

    # --- inventory.ini ---
    masters = [n for n in nodes if n.get("type") == "master"]
    workers = [n for n in nodes if n.get("type") == "worker"]

    lines = ["[masters]"]
    for m in masters:
        lines.append(f'{m["name"]} ansible_host={m["ip"]}')
    lines.append("")
    lines.append("[workers]")
    for w in workers:
        lines.append(f'{w["name"]} ansible_host={w["ip"]}')
    lines.append("")
    lines.append("[all:vars]")
    lines.append(f"ansible_user={ssh_user}")
    lines.append("ansible_become=yes")
    lines.append("")

    inv_path = ansible_dir / "inventory.ini"
    inv_path.write_text("\n".join(lines))
    print(f"Generated {inv_path}")

    # --- group_vars/all.yml ---
    first_master = masters[0]["name"] if masters else ""
    domain = net.get("domain", "k8s.local")
    vip_hostname = vip.get("hostname", "k8s-api")

    group_vars = {
        "k8s_version": k8s.get("k8s_version", "1.35"),
        "container_runtime": k8s.get("container_runtime", "cri-o"),
        "pod_network_cidr": k8s.get("pod_network_cidr", "10.244.0.0/16"),
        "service_cidr": k8s.get("service_cidr", "10.96.0.0/12"),
        "cni": k8s.get("cni", "Calico"),
        "api_vip_ip": vip.get("ip", ""),
        "api_vip_hostname": vip_hostname,
        "api_endpoint": f"{vip_hostname}.{domain}:6443",
        "cluster_domain": domain,
        "first_master": first_master,
        "first_master_ip": masters[0]["ip"] if masters else "",
        "masters": [{"name": m["name"], "ip": m["ip"]} for m in masters],
        "operators": k8s.get("operators", []),
    }

    import yaml as pyyaml
    gv_path = group_vars_dir / "all.yml"
    gv_path.write_text(
        "# Auto-generated from config.yaml — do not edit manually\n"
        + pyyaml.dump(group_vars, default_flow_style=False, sort_keys=False)
    )
    print(f"Generated {gv_path}")
```

**Step 2: Call it from main()**

In the `main()` function, after the virt-install script generation calls, add:

```python
    generate_ansible_files(config, nodes)
```

**Step 3: Test generation**

```bash
python scripts/provisioner.py generate
cat scripts/ansible/inventory.ini
cat scripts/ansible/group_vars/all.yml
```

Verify inventory has correct hosts and group_vars has all k8s settings.

**Step 4: Commit**

```bash
git add scripts/provisioner.py
git commit -m "Add Ansible inventory and group_vars generation to provisioner"
```

---

### Task 3: Create site.yml and common role (CRI-O + K8s packages)

**Files:**
- Create: `scripts/ansible/site.yml`
- Create: `scripts/ansible/roles/common/tasks/main.yml`

**Step 1: Create site.yml**

```yaml
---
# K8s Day-1 cluster installation
# Run: ansible-playbook -i inventory.ini site.yml

- name: Install common packages on all nodes
  hosts: all
  roles:
    - common

- name: Configure HA control plane (keepalived + HAProxy)
  hosts: masters
  roles:
    - ha-control-plane

- name: Initialize first control plane node
  hosts: masters[0]
  roles:
    - master-init

- name: Install Calico CNI
  hosts: masters[0]
  roles:
    - calico

- name: Join additional control plane nodes
  hosts: masters[1:]
  serial: 1
  roles:
    - master-join

- name: Join worker nodes
  hosts: workers
  roles:
    - worker

- name: Install operators
  hosts: masters[0]
  roles:
    - operators
```

**Step 2: Create roles/common/tasks/main.yml**

This role installs CRI-O, kubelet, kubeadm, kubectl, and CNI plugins on all nodes.

```yaml
---
- name: Remove zram swap
  ansible.builtin.dnf:
    name: zram-generator-defaults
    state: absent

- name: Add CRI-O repository
  ansible.builtin.yum_repository:
    name: cri-o
    description: "CRI-O stable v{{ k8s_version }}"
    baseurl: "https://download.opensuse.org/repositories/isv:/cri-o:/stable:/v{{ k8s_version }}/rpm/"
    gpgcheck: true
    gpgkey: "https://download.opensuse.org/repositories/isv:/cri-o:/stable:/v{{ k8s_version }}/rpm/repodata/repomd.xml.key"

- name: Add Kubernetes repository
  ansible.builtin.yum_repository:
    name: kubernetes
    description: "Kubernetes stable v{{ k8s_version }}"
    baseurl: "https://pkgs.k8s.io/core:/stable:/v{{ k8s_version }}/rpm/"
    gpgcheck: true
    gpgkey: "https://pkgs.k8s.io/core:/stable:/v{{ k8s_version }}/rpm/repodata/repomd.xml.key"

- name: Install CRI-O and Kubernetes packages
  ansible.builtin.dnf:
    name:
      - cri-o
      - kubelet
      - kubeadm
      - kubectl
      - iproute-tc
    state: present

- name: Enable and start CRI-O
  ansible.builtin.systemd:
    name: crio
    enabled: true
    state: started

- name: Enable kubelet
  ansible.builtin.systemd:
    name: kubelet
    enabled: true

- name: Configure crictl to use CRI-O socket
  ansible.builtin.copy:
    dest: /etc/crictl.yaml
    content: |
      runtime-endpoint: unix:///var/run/crio/crio.sock
      image-endpoint: unix:///var/run/crio/crio.sock

- name: Create CNI plugin directory
  ansible.builtin.file:
    path: /opt/cni/bin
    state: directory
    mode: "0755"

- name: Detect architecture
  ansible.builtin.set_fact:
    cni_arch: "{{ 'amd64' if ansible_architecture == 'x86_64' else 'arm64' if ansible_architecture == 'aarch64' else ansible_architecture }}"

- name: Download CNI plugins
  ansible.builtin.get_url:
    url: "https://github.com/containernetworking/plugins/releases/download/v1.6.2/cni-plugins-linux-{{ cni_arch }}-v1.6.2.tgz"
    dest: /tmp/cni-plugins.tgz

- name: Extract CNI plugins
  ansible.builtin.unarchive:
    src: /tmp/cni-plugins.tgz
    dest: /opt/cni/bin
    remote_src: true
```

**Step 3: Commit**

```bash
git add scripts/ansible/site.yml scripts/ansible/roles/common/
git commit -m "Add site.yml and common role: CRI-O, kubelet, kubeadm, CNI plugins"
```

---

### Task 4: Create ha-control-plane role (keepalived + HAProxy)

**Files:**
- Create: `scripts/ansible/roles/ha-control-plane/tasks/main.yml`
- Create: `scripts/ansible/roles/ha-control-plane/templates/keepalived.conf.j2`
- Create: `scripts/ansible/roles/ha-control-plane/templates/haproxy.cfg.j2`
- Create: `scripts/ansible/roles/ha-control-plane/templates/check_apiserver.sh.j2`

**Step 1: Create tasks/main.yml**

```yaml
---
- name: Install keepalived and haproxy
  ansible.builtin.dnf:
    name:
      - keepalived
      - haproxy
    state: present

- name: Set keepalived priority based on inventory position
  ansible.builtin.set_fact:
    keepalived_priority: "{{ 101 - groups['masters'].index(inventory_hostname) }}"
    keepalived_state: "{{ 'MASTER' if inventory_hostname == groups['masters'][0] else 'BACKUP' }}"

- name: Deploy HAProxy configuration
  ansible.builtin.template:
    src: haproxy.cfg.j2
    dest: /etc/haproxy/haproxy.cfg
    mode: "0644"
  notify: restart haproxy

- name: Deploy keepalived health check script
  ansible.builtin.template:
    src: check_apiserver.sh.j2
    dest: /etc/keepalived/check_apiserver.sh
    mode: "0755"

- name: Deploy keepalived configuration
  ansible.builtin.template:
    src: keepalived.conf.j2
    dest: /etc/keepalived/keepalived.conf
    mode: "0644"
  notify: restart keepalived

- name: Enable and start HAProxy
  ansible.builtin.systemd:
    name: haproxy
    enabled: true
    state: started

- name: Enable and start keepalived
  ansible.builtin.systemd:
    name: keepalived
    enabled: true
    state: started
```

**Step 2: Create handlers/main.yml**

Create `scripts/ansible/roles/ha-control-plane/handlers/main.yml`:

```yaml
---
- name: restart haproxy
  ansible.builtin.systemd:
    name: haproxy
    state: restarted

- name: restart keepalived
  ansible.builtin.systemd:
    name: keepalived
    state: restarted
```

**Step 3: Create templates/haproxy.cfg.j2**

```
# K8s API Server Load Balancer
global
    log /dev/log local0
    maxconn 2000
    daemon

defaults
    log     global
    mode    tcp
    option  tcplog
    timeout connect 5s
    timeout client  30s
    timeout server  30s

frontend k8s_api
    bind *:6443
    default_backend k8s_api_backend

backend k8s_api_backend
    balance roundrobin
    option tcp-check
{% for master in masters %}
    server {{ master.name }} {{ master.ip }}:6443 check fall 3 rise 2
{% endfor %}
```

Note: HAProxy binds on `*:6443` (all interfaces). When the VIP is on this node,
traffic arriving at `<VIP>:6443` hits HAProxy and gets forwarded to one of the
API servers. Traffic to `<node_ip>:6443` also works, which is fine.

**Step 4: Create templates/keepalived.conf.j2**

```
global_defs {
    enable_script_security
}

vrrp_script check_apiserver {
    script "/etc/keepalived/check_apiserver.sh"
    interval 3
    weight -2
    fall 10
    rise 2
}

vrrp_instance VI_1 {
    state {{ keepalived_state }}
    interface enp1s0
    virtual_router_id 51
    priority {{ keepalived_priority }}
    advert_int 1

    authentication {
        auth_type PASS
        auth_pass k8s-vip
    }

    virtual_ipaddress {
        {{ api_vip_ip }}/24
    }

    track_script {
        check_apiserver
    }
}
```

**Step 5: Create templates/check_apiserver.sh.j2**

```
#!/bin/bash
# Health check for keepalived — verifies HAProxy is alive
# If HAProxy is down, keepalived lowers this node's priority
# so another master takes over the VIP.

errorExit() {
    echo "*** $*" 1>&2
    exit 1
}

curl --silent --max-time 2 --insecure https://localhost:6443/healthz -o /dev/null || errorExit "Error GET https://localhost:6443/healthz"
```

**Step 6: Commit**

```bash
git add scripts/ansible/roles/ha-control-plane/
git commit -m "Add ha-control-plane role: keepalived + HAProxy for API server VIP"
```

---

### Task 5: Create master-init role (kubeadm init on first master)

**Files:**
- Create: `scripts/ansible/roles/master-init/tasks/main.yml`

**Step 1: Create tasks/main.yml**

```yaml
---
- name: Check if cluster is already initialized
  ansible.builtin.stat:
    path: /etc/kubernetes/admin.conf
  register: kubeadm_conf

- name: Initialize Kubernetes cluster
  ansible.builtin.command:
    cmd: >
      kubeadm init
      --control-plane-endpoint={{ api_endpoint }}
      --pod-network-cidr={{ pod_network_cidr }}
      --service-cidr={{ service_cidr }}
      --upload-certs
      --apiserver-advertise-address={{ ansible_host }}
  when: not kubeadm_conf.stat.exists
  register: kubeadm_init

- name: Create .kube directory for user
  ansible.builtin.file:
    path: "/home/{{ ansible_user }}/.kube"
    state: directory
    owner: "{{ ansible_user }}"
    group: "{{ ansible_user }}"
    mode: "0755"

- name: Copy admin kubeconfig for user
  ansible.builtin.copy:
    src: /etc/kubernetes/admin.conf
    dest: "/home/{{ ansible_user }}/.kube/config"
    remote_src: true
    owner: "{{ ansible_user }}"
    group: "{{ ansible_user }}"
    mode: "0600"

- name: Generate certificate key for control plane join
  ansible.builtin.command:
    cmd: kubeadm init phase upload-certs --upload-certs
  register: upload_certs_output

- name: Extract certificate key
  ansible.builtin.set_fact:
    certificate_key: "{{ upload_certs_output.stdout_lines[-1] }}"

- name: Generate join command
  ansible.builtin.command:
    cmd: kubeadm token create --print-join-command
  register: join_command_output

- name: Set join command fact
  ansible.builtin.set_fact:
    kubeadm_join_command: "{{ join_command_output.stdout }}"

- name: Store join facts for other plays
  ansible.builtin.add_host:
    name: k8s_join_info
    kubeadm_join_command: "{{ kubeadm_join_command }}"
    certificate_key: "{{ certificate_key }}"
```

**Step 2: Commit**

```bash
git add scripts/ansible/roles/master-init/
git commit -m "Add master-init role: kubeadm init with HA endpoint and cert upload"
```

---

### Task 6: Create calico role (Tigera operator + custom resources)

**Files:**
- Create: `scripts/ansible/roles/calico/tasks/main.yml`
- Create: `scripts/ansible/roles/calico/templates/calico-custom-resources.yaml.j2`

**Step 1: Create tasks/main.yml**

```yaml
---
- name: Apply Tigera operator manifest
  ansible.builtin.command:
    cmd: kubectl create -f https://raw.githubusercontent.com/projectcalico/calico/v3.29.3/manifests/tigera-operator.yaml
  become: false
  register: tigera_result
  changed_when: "'created' in tigera_result.stdout"
  failed_when: "tigera_result.rc != 0 and 'already exists' not in tigera_result.stderr"

- name: Wait for Tigera operator to be ready
  ansible.builtin.command:
    cmd: kubectl wait --for=condition=Available deployment/tigera-operator -n tigera-operator --timeout=120s
  become: false

- name: Deploy Calico custom resources
  ansible.builtin.template:
    src: calico-custom-resources.yaml.j2
    dest: /tmp/calico-custom-resources.yaml

- name: Apply Calico custom resources
  ansible.builtin.command:
    cmd: kubectl apply -f /tmp/calico-custom-resources.yaml
  become: false
  register: calico_result
  changed_when: "'created' in calico_result.stdout or 'configured' in calico_result.stdout"

- name: Wait for Calico to be ready
  ansible.builtin.command:
    cmd: kubectl wait --for=condition=Available tigerastatus/calico --timeout=300s
  become: false
  retries: 5
  delay: 30
  register: calico_ready
  until: calico_ready.rc == 0
```

**Step 2: Create templates/calico-custom-resources.yaml.j2**

```yaml
apiVersion: operator.tigera.io/v1
kind: Installation
metadata:
  name: default
spec:
  calicoNetwork:
    ipPools:
      - name: default-ipv4-ippool
        blockSize: 26
        cidr: {{ pod_network_cidr }}
        encapsulation: VXLANCrossSubnet
        natOutgoing: Enabled
        nodeSelector: all()
---
apiVersion: operator.tigera.io/v1
kind: APIServer
metadata:
  name: default
spec: {}
```

**Step 3: Commit**

```bash
git add scripts/ansible/roles/calico/
git commit -m "Add calico role: Tigera operator with custom pod network CIDR"
```

---

### Task 7: Create master-join and worker roles

**Files:**
- Create: `scripts/ansible/roles/master-join/tasks/main.yml`
- Create: `scripts/ansible/roles/worker/tasks/main.yml`

**Step 1: Create master-join/tasks/main.yml**

```yaml
---
- name: Check if node is already part of a cluster
  ansible.builtin.stat:
    path: /etc/kubernetes/kubelet.conf
  register: kubelet_conf

- name: Join cluster as control plane node
  ansible.builtin.command:
    cmd: >
      {{ hostvars['k8s_join_info']['kubeadm_join_command'] }}
      --control-plane
      --certificate-key {{ hostvars['k8s_join_info']['certificate_key'] }}
      --apiserver-advertise-address={{ ansible_host }}
  when: not kubelet_conf.stat.exists

- name: Create .kube directory for user
  ansible.builtin.file:
    path: "/home/{{ ansible_user }}/.kube"
    state: directory
    owner: "{{ ansible_user }}"
    group: "{{ ansible_user }}"
    mode: "0755"

- name: Copy admin kubeconfig for user
  ansible.builtin.copy:
    src: /etc/kubernetes/admin.conf
    dest: "/home/{{ ansible_user }}/.kube/config"
    remote_src: true
    owner: "{{ ansible_user }}"
    group: "{{ ansible_user }}"
    mode: "0600"
```

**Step 2: Create worker/tasks/main.yml**

```yaml
---
- name: Check if node is already part of a cluster
  ansible.builtin.stat:
    path: /etc/kubernetes/kubelet.conf
  register: kubelet_conf

- name: Join cluster as worker node
  ansible.builtin.command:
    cmd: "{{ hostvars['k8s_join_info']['kubeadm_join_command'] }}"
  when: not kubelet_conf.stat.exists
```

**Step 3: Commit**

```bash
git add scripts/ansible/roles/master-join/ scripts/ansible/roles/worker/
git commit -m "Add master-join and worker roles: kubeadm join for control plane and workers"
```

---

### Task 8: Create operators role and lvm-operator

**Files:**
- Create: `scripts/ansible/roles/operators/tasks/main.yml`
- Create: `scripts/ansible/operators/lvm-operator/install.sh`
- Create: `scripts/ansible/operators/lvm-operator/storageclass.yaml`

**Step 1: Create roles/operators/tasks/main.yml**

```yaml
---
- name: Create operators staging directory on master
  ansible.builtin.file:
    path: /tmp/k8s-operators
    state: directory
    mode: "0755"

- name: Copy operator directories to master
  ansible.builtin.copy:
    src: "{{ playbook_dir }}/operators/{{ item }}/"
    dest: "/tmp/k8s-operators/{{ item }}/"
    mode: "0755"
  loop: "{{ operators }}"

- name: Run operator install scripts
  ansible.builtin.command:
    cmd: bash /tmp/k8s-operators/{{ item }}/install.sh
    chdir: /tmp/k8s-operators/{{ item }}
  become: false
  loop: "{{ operators }}"
  register: operator_results

- name: Show operator install results
  ansible.builtin.debug:
    msg: "{{ item.stdout_lines }}"
  loop: "{{ operator_results.results }}"
  loop_control:
    label: "{{ item.item }}"
```

**Step 2: Create operators/lvm-operator/install.sh**

TopoLVM is the vanilla K8s equivalent of OpenShift's LVMS operator. It uses LVM
volume groups on each node and provides dynamic PV provisioning via CSI.

```bash
#!/bin/bash
# Install TopoLVM — LVM-based CSI storage for Kubernetes
# This is the vanilla K8s equivalent of OpenShift's LVMS operator.
#
# Prerequisites: each worker node needs an LVM volume group named "topolvm-vg".
# Create it with: sudo pvcreate /dev/vdb && sudo vgcreate topolvm-vg /dev/vdb

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Installing TopoLVM (LVM CSI driver) ==="

# Install via helm
if ! command -v helm &>/dev/null; then
    echo "Installing helm..."
    curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
fi

# Add TopoLVM helm repo
helm repo add topolvm https://topolvm.github.io/topolvm
helm repo update

# Install TopoLVM
if helm status topolvm -n topolvm-system &>/dev/null; then
    echo "TopoLVM already installed. Upgrading..."
    helm upgrade topolvm topolvm/topolvm -n topolvm-system
else
    echo "Installing TopoLVM..."
    kubectl create namespace topolvm-system --dry-run=client -o yaml | kubectl apply -f -
    helm install topolvm topolvm/topolvm -n topolvm-system
fi

# Wait for TopoLVM controller to be ready
echo "Waiting for TopoLVM controller..."
kubectl wait --for=condition=Available deployment/topolvm-controller \
    -n topolvm-system --timeout=120s

# Apply custom StorageClass
echo "Applying StorageClass..."
kubectl apply -f "$SCRIPT_DIR/storageclass.yaml"

echo "=== TopoLVM installation complete ==="
echo ""
echo "NOTE: Each worker node needs an LVM volume group named 'topolvm-vg'."
echo "Create it with: sudo pvcreate /dev/vdb && sudo vgcreate topolvm-vg /dev/vdb"
echo ""
echo "Verify with: kubectl get sc"
```

**Step 3: Create operators/lvm-operator/storageclass.yaml**

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: topolvm-provisioner
  annotations:
    storageclass.kubernetes.io/is-default-class: "true"
provisioner: topolvm.io
volumeBindingMode: WaitForFirstConsumer
allowVolumeExpansion: true
```

**Step 4: Commit**

```bash
git add scripts/ansible/roles/operators/ scripts/ansible/operators/
git commit -m "Add operators role and lvm-operator: TopoLVM with default StorageClass"
```

---

### Task 9: Wire up provisioner.py generate to produce Ansible files

**Files:**
- Modify: `scripts/provisioner.py`

**Step 1: Call generate_ansible_files() from main() and update output messages**

In `main()`, after the existing generation calls, add:

```python
    generate_ansible_files(config, nodes)
```

Update the generate output to include Ansible workflow:

```python
        print(f"\n🤖 Ansible Day-1 (install K8s):")
        print(f"  cd {SCRIPT_DIR / 'ansible'}")
        print(f"  ansible-playbook -i inventory.ini site.yml")
```

**Step 2: Test full generation**

```bash
python scripts/provisioner.py generate
```

Verify output includes Ansible section and files are generated correctly.

**Step 3: Commit**

```bash
git add scripts/provisioner.py
git commit -m "Wire up Ansible inventory/group_vars generation in provisioner output"
```

---

### Task 10: Update CLAUDE.md with Day-1 Ansible documentation

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Add Ansible Day-1 section**

Add after the Python Provisioner Workflow section:

```markdown
### Ansible Day-1 (K8s Installation)
\`\`\`bash
# After VMs are provisioned and running:
cd scripts/ansible
ansible-playbook -i inventory.ini site.yml
\`\`\`

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
```

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "Document Ansible Day-1 K8s installation workflow in CLAUDE.md"
```

---

## Summary of all tasks

| Task | Description | Files |
|------|-------------|-------|
| 1 | Update config.yaml with K8s Day-1 settings | config.yaml |
| 2 | Add Ansible inventory/group_vars generation | provisioner.py |
| 3 | Create site.yml and common role | site.yml, roles/common/ |
| 4 | Create ha-control-plane role | roles/ha-control-plane/ |
| 5 | Create master-init role | roles/master-init/ |
| 6 | Create calico role | roles/calico/ |
| 7 | Create master-join and worker roles | roles/master-join/, roles/worker/ |
| 8 | Create operators role and lvm-operator | roles/operators/, operators/lvm-operator/ |
| 9 | Wire up provisioner.py and update output | provisioner.py |
| 10 | Update CLAUDE.md documentation | CLAUDE.md |
