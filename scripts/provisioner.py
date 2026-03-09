#!/usr/bin/env python3
"""K8s cluster Day-0 infrastructure provisioner.

Generates Terraform files and per-node cloud-init ISOs from a single YAML
config, then optionally drives the full terraform lifecycle.

Usage
-----
  python provisioner.py [--config PATH] <action> [options]

Actions
-------
  generate      Generate Terraform + cloud-init files in run/ (default)
  init          Run 'terraform init' (implies generate)
  plan          Run 'terraform plan'   (implies generate + init)
  apply         Run 'terraform apply'  (implies generate + init)
  destroy       Run 'terraform destroy'
  clean         Delete all generated files in run/
  add-node      Inject a new node then run plan/apply

Examples
--------
  python provisioner.py generate
  python provisioner.py apply --auto-approve
  python provisioner.py add-node --name k8s-worker4 --ip 192.168.122.24 \\
      --type worker --apply --auto-approve
  python provisioner.py apply --download-provider   # pre-download libvirt provider
"""

import argparse
import ipaddress
import os
import platform
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

# ---------------------------------------------------------------------------
# Directory layout
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
RUN_DIR = BASE_DIR / "run"
CONFIGS_DIR = BASE_DIR / "configs"
DEFAULT_CONFIG = CONFIGS_DIR / "config.yaml"


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def load_config(config_path: Path) -> dict:
    with open(config_path) as fh:
        return yaml.safe_load(fh)


def read_public_key(key_file: str) -> str:
    path = os.path.expanduser(key_file)
    with open(path) as fh:
        return fh.read().strip()


def generate_mac(ip: str) -> str:
    """Generate a deterministic MAC address from an IP address.

    Uses the KVM/QEMU locally-administered prefix ``52:54:00`` and
    derives the last three octets from the IP address.  For example,
    ``192.168.150.10`` becomes ``52:54:00:a8:96:0a``.

    This guarantees uniqueness as long as node IPs are unique (which
    they must be) and produces human-readable MACs that map back to IPs.
    """
    octets = ip.split(".")
    return f"52:54:00:{int(octets[1]):02x}:{int(octets[2]):02x}:{int(octets[3]):02x}"


def get_all_nodes(config: dict) -> list:
    """Return a flat list of all master and worker node dicts.

    Each node inherits values from ``nodes.defaults``; per-node values
    take precedence over defaults.  A deterministic MAC address is
    generated for any node that does not already specify one.
    """
    defaults = config["nodes"].get("defaults", {})
    nodes = []
    for node in config["nodes"].get("masters", []):
        merged = {**defaults, **node, "type": "master"}
        if "mac" not in merged:
            merged["mac"] = generate_mac(merged["ip"])
        nodes.append(merged)
    for node in config["nodes"].get("workers", []):
        merged = {**defaults, **node, "type": "worker"}
        if "mac" not in merged:
            merged["mac"] = generate_mac(merged["ip"])
        nodes.append(merged)
    for node in config["nodes"].get("infra", []):
        merged = {**defaults, **node, "type": "infra"}
        if "mac" not in merged:
            merged["mac"] = generate_mac(merged["ip"])
        nodes.append(merged)
    return nodes


# ---------------------------------------------------------------------------
# Provider preparation (optional — 'terraform init' usually handles this)
# ---------------------------------------------------------------------------

def _detect_platform() -> tuple:
    """Return (os_name, arch) matching Terraform provider release names."""
    system = platform.system().lower()
    machine = platform.machine().lower()
    os_name = "darwin" if system == "darwin" else "linux"
    arch = "arm64" if machine in ("arm64", "aarch64") else "amd64"
    return os_name, arch


def prepare_libvirt_provider(version: str):
    """Pre-download the dmacvicar/libvirt provider binary.

    Only needed when the Terraform registry is inaccessible.  In normal
    environments 'terraform init' downloads the provider automatically.

    Replaces the old prepare_terraform_provider_libvirt() which was
    hard-coded to linux_arm64; this version detects the current OS/arch.
    """
    os_name, arch = _detect_platform()
    plugin_dir = (
        Path.home()
        / ".terraform.d"
        / "plugins"
        / "registry.terraform.io"
        / "dmacvicar"
        / "libvirt"
        / version
        / f"{os_name}_{arch}"
    )

    # Provider binaries include a protocol-version suffix (_x5 for SDK v2,
    # _x6 for Plugin Framework).  0.9.x uses the Plugin Framework → _x6.
    # Check for any matching binary rather than a hard-coded name.
    existing = list(plugin_dir.glob(f"terraform-provider-libvirt_v{version}*"))
    if existing:
        print(f"Provider already cached: {existing[0]}")
        return

    plugin_dir.mkdir(parents=True, exist_ok=True)
    zip_name = f"terraform-provider-libvirt_{version}_{os_name}_{arch}.zip"
    url = (
        f"https://github.com/dmacvicar/terraform-provider-libvirt/releases/"
        f"download/v{version}/{zip_name}"
    )
    zip_path = plugin_dir / zip_name

    print(f"Downloading provider: {url}")
    urllib.request.urlretrieve(url, zip_path)

    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(plugin_dir)

    zip_path.unlink()

    # Make all extracted binaries executable
    for binary in plugin_dir.glob(f"terraform-provider-libvirt_v{version}*"):
        binary.chmod(0o755)
        print(f"Provider installed: {binary}")


# ---------------------------------------------------------------------------
# Base image
# ---------------------------------------------------------------------------

def resolve_base_image_source(config: dict) -> str:
    """Return the image source path/URL for the Terraform libvirt_volume.

    Behaviour:
    - file:// → strip scheme, return the bare path on the libvirt host.
    - http/https + local libvirt → download once to download_dir, return path.
    - http/https + remote libvirt → return URL; libvirt daemon fetches it.
    """
    url = config["os_base_url"]
    download_dir = os.path.expanduser(config.get("download_dir", "~/vms"))
    image_name = config["os_base_name"]

    if url.startswith("file://"):
        local_path = os.path.expanduser(url[len("file://"):])
        if not os.path.exists(local_path):
            print(
                f"WARNING: base image not found on libvirt host: {local_path}",
                file=sys.stderr,
            )
        return local_path

    # Remote URL — download to download_dir (separate from the libvirt pool)
    local_path = os.path.join(download_dir, f"{image_name}.qcow2")
    if os.path.exists(local_path):
        print(f"Base image already cached: {local_path}")
        return local_path

    libvirt_uri = config.get("libvirt_uri", "qemu:///session")
    is_local = not any(proto in libvirt_uri for proto in ("ssh", "tcp", "tls"))

    if is_local:
        os.makedirs(download_dir, exist_ok=True)
        print(f"Downloading base image: {url}")
        print(f"  → {local_path}")
        urllib.request.urlretrieve(url, local_path)
        print("Download complete.")
        return local_path

    # Remote libvirt: hand the URL directly to libvirt
    print(f"Remote libvirt — base image URL passed through: {url}")
    print("Ensure the image is reachable from the libvirt host.")
    return url


# ---------------------------------------------------------------------------
# File generation
# ---------------------------------------------------------------------------

def _make_jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        # trim_blocks: remove the first newline after a block tag so that
        # {% for %}, {% if %}, {% endif %}, {% endfor %} lines don't produce
        # empty lines in the rendered output.
        trim_blocks=True,
        # lstrip_blocks: strip leading whitespace from lines that begin with
        # a block tag (keeps indentation clean in generated YAML/HCL).
        lstrip_blocks=True,
    )


def generate_cloud_init_files(config: dict, env: Environment, nodes: list):
    """Write cloud-init user-data and network-config files to run/.

    Uses a single template (cloud-init.yaml.j2) that contains both documents
    separated by '---'.  The provisioner splits on that boundary and writes:
      run/cloud-init-user-data-<node>.yaml    → Terraform user_data
      run/cloud-init-network-config-<node>.yaml → Terraform network_config
    """
    RUN_DIR.mkdir(parents=True, exist_ok=True)

    net = config["network"]
    prefix = net["subnet"].split("/")[-1]
    gateway = net["gateway"]
    domain = net["domain"]

    tmpl = env.get_template("cloud-init.yaml.j2")

    for node in nodes:
        ctx = {
            "node": node,
            "all_nodes": nodes,
            "ssh": config["ssh"],
            "install_packages": config.get("install_packages", []),
            "run_once_commands": config.get("run_once_commands", []),
            "domain": domain,
            "subnet_prefix": prefix,
            "gateway": gateway,
            "k8s_api_vip": config.get("k8s_api_vip"),
        }
        rendered = tmpl.render(**ctx)

        # Split on the YAML document separator '---' that divides user-data
        # from network-config within the single template file.
        parts = rendered.split("\n---\n", 1)
        user_data = parts[0].strip() + "\n"
        network_config = parts[1].strip() + "\n" if len(parts) > 1 else ""

        (RUN_DIR / f"cloud-init-user-data-{node['name']}.yaml").write_text(user_data)
        (RUN_DIR / f"cloud-init-network-config-{node['name']}.yaml").write_text(
            network_config
        )

    print(f"Generated cloud-init files for {len(nodes)} nodes → {RUN_DIR}")


def generate_host_dns_conf(config: dict):
    """Write a systemd-resolved drop-in for the cluster domain.

    The libvirt network already runs its own dnsmasq on the bridge IP
    with DNS host entries for every VM.  This drop-in tells the host's
    systemd-resolved to route queries for the cluster domain to that
    bridge IP, so the host can resolve VM hostnames.

    This is host-side only and does not affect VM DNS resolution.
    """
    RUN_DIR.mkdir(parents=True, exist_ok=True)

    net = config["network"]
    domain = net["domain"]
    gateway = net["gateway"]
    net_name = net["name"]

    lines = [
        f"# Route {domain} queries to the libvirt dnsmasq on {net_name}",
        f"# The ~ prefix marks this as a routing domain only — it does not",
        f"# affect general DNS resolution on the host.",
        f"[Resolve]",
        f"DNS={gateway}",
        f"Domains=~{domain}",
        "",
    ]

    path = RUN_DIR / f"{net_name}-dns.conf"
    path.write_text("\n".join(lines))
    print(f"Generated {path}")


def generate_network_xml(config: dict, nodes: list):
    """Write a libvirt network XML definition to run/.

    The generated file can be used with ``virsh net-define`` to create
    the cluster network independently of Terraform.
    """
    RUN_DIR.mkdir(parents=True, exist_ok=True)

    net = config["network"]
    net_name = net["name"]
    domain = net["domain"]
    gateway = net["gateway"]
    subnet = ipaddress.ip_network(net["subnet"], strict=False)
    netmask = str(subnet.netmask)

    host_entries = []
    for node in nodes:
        host_entries.append(
            f'    <host ip="{node["ip"]}">\n'
            f'      <hostname>{node["name"]}</hostname>\n'
            f'      <hostname>{node["name"]}.{domain}</hostname>\n'
            f'    </host>'
        )

    # Add VIP DNS entry for HA control plane endpoint
    vip = config.get("k8s_api_vip")
    if vip:
        host_entries.append(
            f'    <host ip="{vip["ip"]}">\n'
            f'      <hostname>{vip["hostname"]}</hostname>\n'
            f'      <hostname>{vip["hostname"]}.{domain}</hostname>\n'
            f'    </host>'
        )

    dhcp_hosts = []
    for node in nodes:
        dhcp_hosts.append(
            f'      <host mac=\'{node["mac"]}\' name=\'{node["name"]}\''
            f' ip=\'{node["ip"]}\'/>'
        )

    xml = f"""\
<network>
  <name>{net_name}</name>
  <forward mode='nat'/>
  <domain name='{domain}' localOnly='yes'/>
  <bridge stp='on' delay='0'/>
  <dns>
{chr(10).join(host_entries)}
  </dns>
  <ip address='{gateway}' netmask='{netmask}'>
    <dhcp>
      <range start='{net["dhcp_range"]["start"]}' end='{net["dhcp_range"]["end"]}'/>
{chr(10).join(dhcp_hosts)}
    </dhcp>
  </ip>
</network>
"""

    path = RUN_DIR / f"{net_name}.xml"
    path.write_text(xml)
    print(f"Generated {path}")


def generate_terraform_files(
    config: dict, env: Environment, nodes: list, base_image_source: str
):
    """Write main.tf to run/."""
    RUN_DIR.mkdir(parents=True, exist_ok=True)

    ctx = {
        "libvirt_provider_version": config.get("libvirt_provider_version", "0.9.3"),
        "libvirt_uri": config.get("libvirt_uri", "qemu:///session"),
        "libvirt_arch": config.get("libvirt_arch", "x86_64"),
        "image_dir": os.path.expanduser(config["image_dir"]),
        "os_base_name": config["os_base_name"],
        "base_image_source": base_image_source,
        "network": config["network"],
        "nodes": nodes,
        "k8s_api_vip": config.get("k8s_api_vip"),
    }

    tf_path = RUN_DIR / "main.tf"
    tf_path.write_text(env.get_template("main.tf.j2").render(**ctx))
    print(f"Generated {tf_path}")


def generate_virt_install_network_script(config: dict):
    """Generate bash script to create the libvirt network with virsh.

    Uses the network XML file already generated by generate_network_xml().
    """
    RUN_DIR.mkdir(parents=True, exist_ok=True)

    net = config["network"]
    net_xml_file = f"{net['name']}.xml"

    script = f"""#!/bin/bash
# Auto-generated libvirt network setup script
# Network: {net['name']}
# Domain: {net['domain']}

set -e

SCRIPT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
NETWORK_NAME="{net['name']}"
NETWORK_XML="$SCRIPT_DIR/{net_xml_file}"

# Check if the network XML file exists
if [[ ! -f "$NETWORK_XML" ]]; then
    echo "Error: Network XML file not found: $NETWORK_XML"
    echo "Run 'python provisioner.py generate' first"
    exit 1
fi

# Check if network already exists
if virsh net-info "$NETWORK_NAME" &>/dev/null; then
    echo "Network $NETWORK_NAME already exists"
    if virsh net-info "$NETWORK_NAME" | grep -q "Active:.*yes"; then
        echo "Network is already active"
    else
        echo "Starting network $NETWORK_NAME..."
        virsh net-start "$NETWORK_NAME"
    fi
    exit 0
fi

echo "Creating libvirt network $NETWORK_NAME from $NETWORK_XML..."

# Define and start the network using the pre-generated XML
virsh net-define "$NETWORK_XML"
virsh net-start "$NETWORK_NAME"
virsh net-autostart "$NETWORK_NAME"

echo "Network $NETWORK_NAME created and started"
echo "You can check it with: virsh net-info $NETWORK_NAME"
"""

    output_file = RUN_DIR / "virt-install-setup-network.sh"
    output_file.write_text(script)
    output_file.chmod(0o755)
    print(f"Generated {output_file}")


def generate_virt_install_create_vms_script(config: dict, nodes: list):
    """Generate bash script with virt-install commands for all VMs.

    Uses backing_store (COW) approach:
    - Single read-only base image (cloud-init compatible OS image)
    - Per-VM writable delta disks created as qcow2 with backing_file
    - virt-install imports the delta disk with --import flag
    """
    RUN_DIR.mkdir(parents=True, exist_ok=True)

    image_dir = os.path.expanduser(config["image_dir"])
    libvirt_uri = config.get("libvirt_uri", "qemu:///system")
    net_name = config["network"]["name"]
    ssh_user = config["ssh"]["username"]

    # Determine base image path from config
    base_url = config["os_base_url"]
    if base_url.startswith("file://"):
        base_image_path = os.path.expanduser(base_url.replace("file://", ""))
    else:
        # For HTTP URLs, assume it should be downloaded to image_dir
        base_image_path = f"{image_dir}/{config['os_base_name']}.qcow2"

    script = f"""#!/bin/bash
# Auto-generated virt-install VM creation script
# Generated from config.yaml
#
# Architecture: Copy-on-Write (COW) thin provisioning
#   - Base image: Read-only cloud-init compatible OS image
#   - VM disks: Thin writable layers (backing_file pointing to base)
#   - Benefits: Fast creation, space efficient, easy VM rebuild
#
# Supported OS: Any cloud image with cloud-init support
#   - Fedora Cloud
#   - Ubuntu Cloud
#   - CentOS/Rocky/AlmaLinux Cloud
#   - Debian Cloud

set -e

NETWORK="{net_name}"
IMAGE_DIR="{image_dir}"
BASE_IMAGE="{base_image_path}"
SCRIPT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"

# Colors for output
GREEN='\\033[0;32m'
YELLOW='\\033[1;33m'
RED='\\033[0;31m'
NC='\\033[0m' # No Color

echo "=================================================="
echo "K8s Cluster VM Creation with virt-install"
echo "=================================================="
echo "Network: $NETWORK"
echo "Image Dir: $IMAGE_DIR"
echo "Base Image: $BASE_IMAGE"
echo "Architecture: COW (Copy-on-Write) backing_store"
echo ""

# Ensure image directory exists
mkdir -p "$IMAGE_DIR"

# Check if network exists
if ! virsh net-info "$NETWORK" &>/dev/null; then
    echo "${{RED}}Error: Network $NETWORK does not exist!${{NC}}"
    echo "Run ./virt-install-setup-network.sh first"
    exit 1
fi

# Ensure base image exists
if [[ ! -f "$BASE_IMAGE" ]]; then
    echo "${{RED}}Error: Base image not found: $BASE_IMAGE${{NC}}"
    echo ""
    echo "Please download the base OS cloud image before running this script."
    echo "Expected location: $BASE_IMAGE"
    echo ""
    echo "Common cloud image sources:"
    echo "  Fedora Cloud: https://fedoraproject.org/cloud/download"
    echo "  Ubuntu Cloud: https://cloud-images.ubuntu.com/"
    echo "  Rocky Linux:  https://rockylinux.org/download"
    exit 1
fi

echo ""
echo "Step 1: Creating cloud-init ISOs..."
echo ""

# Check for cloud-localds (from cloud-utils package)
if ! command -v cloud-localds &>/dev/null; then
    echo "${{RED}}Error: cloud-localds not found!${{NC}}"
    echo "Install it with: sudo dnf install cloud-utils"
    exit 1
fi

"""

    # Build node configuration arrays for bash script
    defaults = config["nodes"].get("defaults", {})

    names = []
    macs = []
    memories = []
    vcpus = []
    disk_sizes = []
    data_disk_sizes = []

    for node in nodes:
        names.append(node['name'])
        macs.append(node['mac'])
        memories.append(str(node.get("memory", defaults.get("memory", "8192"))))
        vcpus.append(str(node.get("vcpu", defaults.get("vcpu", "4"))))
        disk_sizes.append(str(node.get("disk_size", defaults.get("disk_size", "40"))))
        data_disk_sizes.append(str(node.get("data_disk_size", defaults.get("data_disk_size", "0"))))

    script += f"""# Define node configuration arrays
NAMES=({" ".join(names)})
MACS=({" ".join(macs)})
MEMORY=({" ".join(memories)})
VCPU=({" ".join(vcpus)})
DISK_SIZE=({" ".join(disk_sizes)})
DATA_DISK_SIZE=({" ".join(data_disk_sizes)})

# Create persistent cloud-init ISOs in IMAGE_DIR
for i in "${{!NAMES[@]}}"; do
    NODE_NAME="${{NAMES[$i]}}"
    ISO_PATH="$IMAGE_DIR/${{NODE_NAME}}-cloudinit.iso"

    if [[ -f "$ISO_PATH" ]]; then
        echo "${{YELLOW}}  ${{NODE_NAME}}-cloudinit.iso already exists. Skipping.${{NC}}"
        continue
    fi

    echo "  Creating ${{NODE_NAME}}-cloudinit.iso"
    cloud-localds \\
        --network-config="$SCRIPT_DIR/cloud-init-network-config-${{NODE_NAME}}.yaml" \\
        "$ISO_PATH" \\
        "$SCRIPT_DIR/cloud-init-user-data-${{NODE_NAME}}.yaml"
done

echo ""
echo "Step 2: Creating VM disks and domains..."
echo ""

# Create VMs in a loop
for i in "${{!NAMES[@]}}"; do
    NODE_NAME="${{NAMES[$i]}}"
    NODE_MAC="${{MACS[$i]}}"
    NODE_MEMORY="${{MEMORY[$i]}}"
    NODE_VCPU="${{VCPU[$i]}}"
    NODE_DISK_SIZE="${{DISK_SIZE[$i]}}"
    NODE_DATA_DISK_SIZE="${{DATA_DISK_SIZE[$i]}}"

    echo "${{GREEN}}Creating $NODE_NAME...${{NC}}"

    # Check if VM already exists
    if virsh dominfo "$NODE_NAME" &>/dev/null; then
        echo "${{YELLOW}}$NODE_NAME already exists. Skipping.${{NC}}"
        continue
    fi

    # Create OS disk as COW (copy-on-write) delta on top of base image
    if [[ ! -f "$IMAGE_DIR/${{NODE_NAME}}-os.qcow2" ]]; then
        echo "  Creating OS disk: ${{NODE_NAME}}-os.qcow2 (${{NODE_DISK_SIZE}}G, COW delta)"
        qemu-img create -f qcow2 \\
            -F qcow2 \\
            -b "$BASE_IMAGE" \\
            "$IMAGE_DIR/${{NODE_NAME}}-os.qcow2" \\
            "${{NODE_DISK_SIZE}}G"
    fi

    # Create data disk if configured (data_disk_size > 0)
    if [[ "$NODE_DATA_DISK_SIZE" -gt 0 ]]; then
        if [[ ! -f "$IMAGE_DIR/${{NODE_NAME}}-data.qcow2" ]]; then
            echo "  Creating data disk: ${{NODE_NAME}}-data.qcow2 (${{NODE_DATA_DISK_SIZE}}G)"
            qemu-img create -f qcow2 \\
                "$IMAGE_DIR/${{NODE_NAME}}-data.qcow2" \\
                "${{NODE_DATA_DISK_SIZE}}G"
        fi
    fi

    # Build disk parameter (conditionally add data disk)
    DISK_PARAMS="--disk path=$IMAGE_DIR/${{NODE_NAME}}-os.qcow2,device=disk,bus=virtio"
    if [[ "$NODE_DATA_DISK_SIZE" -gt 0 ]]; then
        DISK_PARAMS="$DISK_PARAMS --disk path=$IMAGE_DIR/${{NODE_NAME}}-data.qcow2,device=disk,bus=virtio"
    fi

    # Import the disk image and attach persistent cloud-init ISO
    # --import tells virt-install to use the existing disk (not install an OS)
    echo "  Defining VM and attaching cloud-init ISO..."
    virt-install \\
        --connect {libvirt_uri} \\
        --name "$NODE_NAME" \\
        --memory "$NODE_MEMORY" \\
        --vcpu "$NODE_VCPU" \\
        --cpu host-passthrough \\
        --machine q35 \\
        $DISK_PARAMS \\
        --disk path=$IMAGE_DIR/${{NODE_NAME}}-cloudinit.iso,device=cdrom,bus=sata \\
        --network network=$NETWORK,model=virtio,mac=$NODE_MAC \\
        --os-variant fedora-unknown \\
        --graphics none \\
        --console pty,target_type=serial \\
        --import \\
        --noautoconsole \\
        --autostart

    echo "${{GREEN}}$NODE_NAME created successfully${{NC}}"
done

"""

    script += f"""
echo ""
echo "${{GREEN}}All VMs created!${{NC}}"
echo ""
echo "Check VM status with:"
echo "  virsh list --all"
echo ""
echo "Connect to VMs via console:"
"""

    for node in nodes:
        script += f"""echo "  virsh console {node['name']}"
"""

    script += f"""echo ""
echo "Or via SSH (after cloud-init completes, ~30-60 seconds):"
"""

    for node in nodes:
        script += f"""echo "  ssh {ssh_user}@{node['ip']}"
"""

    script += """
"""

    output_file = RUN_DIR / "virt-install-create-vms.sh"
    output_file.write_text(script)
    output_file.chmod(0o755)
    print(f"Generated {output_file}")


def generate_virt_install_cleanup_script(config: dict, nodes: list):
    """Generate bash script to destroy all VMs and clean up disk images."""
    RUN_DIR.mkdir(parents=True, exist_ok=True)

    image_dir = os.path.expanduser(config["image_dir"])
    net_name = config["network"]["name"]
    os_base_name = config["os_base_name"]

    script = f"""#!/bin/bash
# Auto-generated cleanup script
# WARNING: This will destroy all VMs and delete their disks!

set -e

IMAGE_DIR="{image_dir}"

echo "=================================================="
echo "CLEANUP: Destroying K8s Cluster VMs"
echo "=================================================="
echo ""
echo "WARNING: This will:"
echo "  - Shutdown and destroy all VMs"
echo "  - Delete VM disk images"
echo "  - Keep the base image and network"
echo ""
read -p "Continue? (yes/no): " confirm

if [[ "$confirm" != "yes" ]]; then
    echo "Aborted."
    exit 0
fi

echo ""

# Define node names array
"""

    # Build node names array
    names = [node['name'] for node in nodes]

    script += f"""NAMES=({" ".join(names)})

# Destroy VMs in a loop
for NODE_NAME in "${{NAMES[@]}}"; do
    if virsh dominfo "$NODE_NAME" &>/dev/null; then
        echo "Destroying $NODE_NAME..."
        virsh destroy "$NODE_NAME" 2>/dev/null || true
        virsh undefine "$NODE_NAME" --nvram 2>/dev/null || true
        rm -f "$IMAGE_DIR/${{NODE_NAME}}-os.qcow2"
        rm -f "$IMAGE_DIR/${{NODE_NAME}}-data.qcow2"
        rm -f "$IMAGE_DIR/${{NODE_NAME}}-cloudinit.iso"
        echo "  ✓ $NODE_NAME removed"
    else
        echo "  - $NODE_NAME does not exist"
    fi
done

echo ""
echo "Cleanup complete!"
echo ""
echo "To also remove the network, run:"
echo "  virsh net-destroy {net_name}"
echo "  virsh net-undefine {net_name}"
echo ""
echo "To remove the base image:"
echo "  rm -f $IMAGE_DIR/{os_base_name}.qcow2"
"""

    output_file = RUN_DIR / "virt-install-cleanup.sh"
    output_file.write_text(script)
    output_file.chmod(0o755)
    print(f"Generated {output_file}")


# ---------------------------------------------------------------------------
# Ansible inventory / group_vars generation
# ---------------------------------------------------------------------------

def generate_ansible_files(config: dict, nodes: list):
    """Write Ansible inventory and group_vars derived from config.yaml.

    Creates:
      scripts/ansible/inventory.ini       — host groups for masters and workers
      scripts/ansible/group_vars/all.yml  — variables consumed by Ansible roles
    """
    ansible_dir = BASE_DIR / "ansible"
    group_vars_dir = ansible_dir / "group_vars"
    group_vars_dir.mkdir(parents=True, exist_ok=True)

    ssh = config["ssh"]
    net = config["network"]
    k8s = config.get("k8s", {})
    vip = config.get("k8s_api_vip", {})

    # -- inventory.ini --
    masters = [n for n in nodes if n.get("type") == "master"]
    workers = [n for n in nodes if n.get("type") == "worker"]
    infra = [n for n in nodes if n.get("type") == "infra"]

    lines = ["[masters]"]
    for n in masters:
        lines.append(f"{n['name']} ansible_host={n['ip']}")
    lines.append("")
    lines.append("[workers]")
    for n in workers:
        lines.append(f"{n['name']} ansible_host={n['ip']}")
    lines.append("")
    lines.append("[infra]")
    for n in infra:
        lines.append(f"{n['name']} ansible_host={n['ip']}")
    lines.append("")
    lines.append("[all:vars]")
    lines.append(f"ansible_user={ssh['username']}")
    lines.append("ansible_become=yes")
    lines.append("ansible_python_interpreter=/usr/bin/python3")
    lines.append("")

    inv_path = ansible_dir / "inventory.ini"
    inv_path.write_text("\n".join(lines))
    print(f"Generated {inv_path}")

    # -- group_vars/all.yml --
    domain = net["domain"]
    first_master = masters[0] if masters else {}

    group_vars = {
        "k8s_version": k8s.get("k8s_version", "1.35"),
        "container_runtime": k8s.get("container_runtime", "cri-o"),
        "pod_network_cidr": k8s.get("pod_network_cidr", "10.244.0.0/16"),
        "service_cidr": k8s.get("service_cidr", "10.96.0.0/12"),
        "cni": k8s.get("cni", "Calico"),
        "api_vip_ip": vip.get("ip", ""),
        "api_vip_hostname": vip.get("hostname", ""),
        "api_endpoint": f"{vip.get('hostname', '')}.{domain}:6443" if vip else "",
        "cluster_domain": domain,
        "first_master": first_master.get("name", ""),
        "first_master_ip": first_master.get("ip", ""),
        "masters": [{"name": n["name"], "ip": str(n["ip"])} for n in masters],
        "cni_plugins_version": k8s.get("cni_plugins_version", "1.9.0"),
        "calico_version": k8s.get("calico_version", "3.31.4"),
        "operators": k8s.get("operators", []),
    }

    gv_path = group_vars_dir / "all.yml"
    gv_path.write_text(yaml.dump(group_vars, default_flow_style=False, sort_keys=False))
    print(f"Generated {gv_path}")


# ---------------------------------------------------------------------------
# Terraform execution
# ---------------------------------------------------------------------------

def _run_terraform(args: list, check: bool = True) -> int:
    result = subprocess.run(["terraform"] + args, cwd=RUN_DIR)
    if check and result.returncode != 0:
        sys.exit(result.returncode)
    return result.returncode


def _ensure_initialized():
    if not (RUN_DIR / ".terraform").exists():
        print("Running: terraform init")
        _run_terraform(["init"])


def clean_run_dir():
    """Remove generated files in run/, preserving Terraform state."""
    if not RUN_DIR.exists():
        print(f"Nothing to clean — {RUN_DIR} does not exist.")
        return

    preserved = {"terraform.tfstate", "terraform.tfstate.backup"}
    for entry in list(RUN_DIR.iterdir()):
        if entry.name in preserved:
            continue
        if entry.is_dir():
            shutil.rmtree(entry)
        else:
            entry.unlink()
        print(f"  Removed {entry.name}")

    print(f"Cleaned {RUN_DIR} (terraform state preserved)")


# ---------------------------------------------------------------------------
# Node addition helper
# ---------------------------------------------------------------------------

def _add_network_dns_entry(config: dict, name: str, ip: str):
    """Add a DNS host entry to the running libvirt network via virsh.

    Uses --live to update dnsmasq immediately (no network restart) and
    --config to persist across network restarts.  If the network is not
    running or the entry already exists, the error is logged but not fatal
    — Terraform will reconcile the state on the next apply.
    """
    network_name = config["network"]["name"]
    libvirt_uri = config.get("libvirt_uri", "qemu:///session")
    host_xml = f'<host ip="{ip}"><hostname>{name}</hostname></host>'

    cmd = [
        "virsh", "-c", libvirt_uri, "net-update", network_name,
        "add", "dns-host", host_xml, "--live", "--config",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print(f"Added DNS entry to live network: {name} → {ip}")
    else:
        print(f"NOTE: Could not update network DNS live: {result.stderr.strip()}")
        print("  Terraform will handle this when it applies the network config.")


def add_node_to_config(config_path: Path, config: dict, name: str, ip: str,
                       node_type: str, memory: str, vcpu: str,
                       disk_size: str, data_disk_size: str = "0") -> dict:
    """Append a new node to config and persist it back to the YAML file.

    Only fields that differ from ``nodes.defaults`` are written so the
    config stays concise.
    """
    existing = get_all_nodes(config)
    for node in existing:
        if node["name"] == name:
            print(f"ERROR: node with name '{name}' already exists.", file=sys.stderr)
            sys.exit(1)
        if node["ip"] == ip:
            print(f"ERROR: node with IP '{ip}' already exists ({node['name']}).",
                  file=sys.stderr)
            sys.exit(1)

    defaults = config["nodes"].get("defaults", {})

    new_node: dict = {"name": name, "ip": ip}

    # Only store values that differ from the node defaults
    for key, value in [("memory", memory), ("vcpu", vcpu),
                       ("disk_size", disk_size),
                       ("data_disk_size", data_disk_size)]:
        if str(value) != str(defaults.get(key, "")):
            new_node[key] = value

    type_to_list = {"master": "masters", "worker": "workers", "infra": "infra"}
    target_list = type_to_list.get(node_type, "workers")
    config["nodes"].setdefault(target_list, []).append(new_node)

    with open(config_path, "w") as fh:
        yaml.dump(config, fh, default_flow_style=False, sort_keys=False)
    print(f"Updated {config_path} with new node: {name}")

    return config


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="K8s cluster Day-0 provisioner (Terraform + libvirt + cloud-init)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG),
        metavar="PATH",
        help=f"Config YAML file (default: {DEFAULT_CONFIG})",
    )
    parser.add_argument(
        "action",
        nargs="?",
        default="generate",
        choices=["generate", "init", "plan", "apply", "destroy", "clean", "add-node"],
        help="Action to perform (default: generate)",
    )
    parser.add_argument(
        "--libvirt-uri",
        metavar="URI",
        help="Override libvirt_uri from config (e.g. qemu:///session for macOS)",
    )
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Pass -auto-approve to terraform apply/destroy",
    )
    parser.add_argument(
        "--download-provider",
        action="store_true",
        help="Pre-download the libvirt provider binary (normally handled by terraform init)",
    )

    grp = parser.add_argument_group("add-node options")
    grp.add_argument("--name", help="New node hostname")
    grp.add_argument("--ip", help="New node static IP address")
    grp.add_argument("--type", choices=["master", "worker"], help="Node role")
    grp.add_argument("--memory", default="8192", metavar="MB",
                     help="RAM in MB (default: 8192)")
    grp.add_argument("--vcpu", default="4", help="vCPU count (default: 4)")
    grp.add_argument("--disk-size", default="40", metavar="GB",
                     help="OS disk size in GB (default: 40)")
    grp.add_argument("--data-disk-size", default="0", metavar="GB",
                     help="Data disk size in GB, 0=none (default: 0)")
    grp.add_argument("--apply", action="store_true",
                     help="Run terraform apply after generating (add-node only)")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.action == "clean":
        clean_run_dir()
        return

    config = load_config(Path(args.config))
    config["ssh"]["public_key"] = read_public_key(config["ssh"]["public_key_file"])

    if args.libvirt_uri:
        config["libvirt_uri"] = args.libvirt_uri

    if args.download_provider:
        prepare_libvirt_provider(config.get("libvirt_provider_version", "0.9.3"))

    config_path = Path(args.config)

    if args.action == "add-node":
        if not all([args.name, args.ip, args.type]):
            parser.error("add-node requires --name, --ip, and --type")
        config = add_node_to_config(
            config_path,
            config,
            name=args.name,
            ip=args.ip,
            node_type=args.type,
            memory=args.memory,
            vcpu=args.vcpu,
            disk_size=args.disk_size,
            data_disk_size=args.data_disk_size,
        )
        print(f"Added new {args.type} node: {args.name} ({args.ip})")
        _add_network_dns_entry(config, args.name, args.ip)

    nodes = get_all_nodes(config)
    if not nodes:
        print("ERROR: No nodes defined in config.", file=sys.stderr)
        sys.exit(1)

    base_image_source = resolve_base_image_source(config)

    env = _make_jinja_env()
    generate_cloud_init_files(config, env, nodes)
    generate_network_xml(config, nodes)
    generate_host_dns_conf(config)

    # Generate virt-install scripts (primary workflow)
    generate_virt_install_network_script(config)
    generate_virt_install_create_vms_script(config, nodes)
    generate_virt_install_cleanup_script(config, nodes)

    # Also generate Terraform files (backup approach — libvirt provider is unstable)
    generate_terraform_files(config, env, nodes, base_image_source)

    # Generate Ansible inventory and group_vars for Day-1 K8s installation
    generate_ansible_files(config, nodes)

    if args.action == "generate":
        net_name = config["network"]["name"]
        dns_conf = f"{net_name}-dns.conf"
        print("\n" + "=" * 60)
        print("Files generated successfully!")
        print("=" * 60)
        print(f"\n🔧 virt-install workflow (primary):")
        print(f"  cd {RUN_DIR}")
        print(f"  ./virt-install-setup-network.sh      # Create network first")
        print(f"  ./virt-install-create-vms.sh         # Create all VMs")
        print(f"  ./virt-install-cleanup.sh            # Cleanup when done")
        print(f"\n📦 Terraform workflow (backup — libvirt provider is unstable):")
        print(f"  cd {RUN_DIR}")
        print("  terraform init && terraform plan && terraform apply")
        print(f"  # or: python {Path(__file__).name} apply --auto-approve")
        print(f"\n🤖 Ansible Day-1 (install K8s):")
        print(f"  cd {BASE_DIR / 'ansible'}")
        print(f"  ansible-playbook -i inventory.ini site.yml")
        print(f"\n🌐 To resolve VM hostnames from the host (one-time setup):")
        print(f"  sudo mkdir -p /etc/systemd/resolved.conf.d")
        print(f"  sudo cp {RUN_DIR}/{dns_conf} /etc/systemd/resolved.conf.d/")
        print(f"  sudo systemctl restart systemd-resolved")
        return

    if args.action == "init":
        _run_terraform(["init"])
        return

    _ensure_initialized()

    if args.action == "plan":
        _run_terraform(["plan"])

    elif args.action == "apply":
        tf_args = ["apply"] + (["-auto-approve"] if args.auto_approve else [])
        _run_terraform(tf_args)

    elif args.action == "destroy":
        tf_args = ["destroy"] + (["-auto-approve"] if args.auto_approve else [])
        _run_terraform(tf_args)

    elif args.action == "add-node":
        if args.apply:
            tf_args = ["apply"] + (["-auto-approve"] if args.auto_approve else [])
        else:
            print("Tip: pass --apply to actually provision the new node.")
            tf_args = ["plan"]
        _run_terraform(tf_args)


if __name__ == "__main__":
    main()
