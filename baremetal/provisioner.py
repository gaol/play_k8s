#!/usr/bin/env python3
"""Baremetal K8s cluster provisioner.

Generates autoinstall configs, Ansible inventory, and service configs
from a single YAML config, then orchestrates ISO builds and Redfish
boot operations.

Usage
-----
  python provisioner.py [--config PATH] <action> [options]

Actions
-------
  generate      Generate all files in run/ and ansible/
  build-iso     Build autoinstall ISOs (all or --node NAME)
  boot-node     Redfish: mount ISO + set boot + power on (--node NAME)
  boot-all      Redfish: boot all nodes
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
RUN_DIR = BASE_DIR / "run"
CONFIGS_DIR = BASE_DIR / "configs"
DEFAULT_CONFIG = CONFIGS_DIR / "config.yaml"
ANSIBLE_DIR = BASE_DIR / "ansible"


def load_config(config_path: Path) -> dict:
    with open(config_path) as fh:
        return yaml.safe_load(fh)


def read_public_key(key_file: str) -> str:
    path = os.path.expanduser(key_file)
    with open(path) as fh:
        return fh.read().strip()


def get_all_nodes(config: dict) -> list:
    """Return a flat list of all node dicts with defaults merged.

    Each node inherits from nodes.defaults. Per-node values override.
    Redfish settings are deep-merged (node redfish overrides only the
    keys it specifies, keeping remaining defaults).
    """
    defaults = config["nodes"].get("defaults", {})
    default_redfish = defaults.get("redfish", {})
    nodes = []

    for node_type in ("infra", "masters", "workers"):
        role = node_type.rstrip("s") if node_type != "infra" else "infra"
        for node in config["nodes"].get(node_type, []):
            node_redfish = {**default_redfish, **node.get("redfish", {})}
            merged = {**defaults, **node, "type": role, "redfish": node_redfish}
            nodes.append(merged)

    return nodes


def get_node_by_name(nodes: list, name: str) -> dict:
    for node in nodes:
        if node["name"] == name:
            return node
    print(f"ERROR: Node '{name}' not found in config.", file=sys.stderr)
    sys.exit(1)


def get_network_prefix(config: dict) -> str:
    return config["network"]["subnet"].split("/")[-1]


def _make_jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def generate_autoinstall_files(config: dict, env: Environment, nodes: list):
    RUN_DIR.mkdir(parents=True, exist_ok=True)

    net = config["network"]
    prefix = get_network_prefix(config)
    ssh = config["bootstrap_host"]["ssh"]
    ssh_public_key = read_public_key(ssh["public_key_file"])

    user_data_tmpl = env.get_template("autoinstall-user-data.yaml.j2")
    network_tmpl = env.get_template("network-config.yaml.j2")

    all_nodes = nodes
    vip = config.get("k8s_api_vip", {})
    bootstrap = config["bootstrap_host"]

    for node in nodes:
        ctx = {
            "node": node,
            "all_nodes": all_nodes,
            "ssh": ssh,
            "ssh_public_key": ssh_public_key,
            "network": net,
            "prefix_length": prefix,
            "k8s_api_vip": vip,
            "bootstrap_host": bootstrap,
        }

        user_data = user_data_tmpl.render(**ctx)
        network_cfg = network_tmpl.render(**ctx)

        (RUN_DIR / f"autoinstall-{node['name']}.yaml").write_text(user_data)
        (RUN_DIR / f"network-config-{node['name']}.yaml").write_text(network_cfg)

    print(f"Generated autoinstall files for {len(nodes)} nodes → {RUN_DIR}")


def generate_dnsmasq_conf(config: dict, env: Environment, nodes: list):
    RUN_DIR.mkdir(parents=True, exist_ok=True)

    tmpl = env.get_template("dnsmasq.conf.j2")
    rendered = tmpl.render(
        bootstrap_host=config["bootstrap_host"],
        network=config["network"],
        k8s_api_vip=config.get("k8s_api_vip", {}),
        all_nodes=nodes,
    )
    path = RUN_DIR / "dnsmasq.conf"
    path.write_text(rendered)
    print(f"Generated {path}")


def generate_nginx_conf(config: dict, env: Environment):
    RUN_DIR.mkdir(parents=True, exist_ok=True)

    tmpl = env.get_template("nginx-site.conf.j2")
    rendered = tmpl.render(
        bootstrap_host=config["bootstrap_host"],
        os=config["os"],
    )
    path = RUN_DIR / "nginx-site.conf"
    path.write_text(rendered)
    print(f"Generated {path}")


def generate_ansible_files(config: dict, nodes: list):
    group_vars_dir = ANSIBLE_DIR / "group_vars"
    group_vars_dir.mkdir(parents=True, exist_ok=True)

    ssh = config["bootstrap_host"]["ssh"]
    net = config["network"]
    k8s = config.get("k8s", {})
    vip = config.get("k8s_api_vip", {})
    bootstrap = config["bootstrap_host"]

    masters = [n for n in nodes if n["type"] == "master"]
    workers = [n for n in nodes if n["type"] == "worker"]
    infra = [n for n in nodes if n["type"] == "infra"]

    lines = [
        "[bootstrap]",
        f"{bootstrap['hostname']} ansible_host={bootstrap['ip']}",
        "",
        "[infra]",
    ]
    for n in infra:
        lines.append(f"{n['name']} ansible_host={n['ip']}")
    lines.append("")
    lines.append("[masters]")
    for n in masters:
        lines.append(f"{n['name']} ansible_host={n['ip']}")
    lines.append("")
    lines.append("[workers]")
    for n in workers:
        lines.append(f"{n['name']} ansible_host={n['ip']}")
    lines.append("")
    lines.append("[all:vars]")
    lines.append(f"ansible_user={ssh['username']}")
    lines.append("ansible_become=yes")
    lines.append("ansible_python_interpreter=/usr/bin/python3")
    lines.append("")

    inv_path = ANSIBLE_DIR / "inventory.ini"
    inv_path.write_text("\n".join(lines))
    print(f"Generated {inv_path}")

    domain = net["domain"]
    prefix = get_network_prefix(config)
    first_master = masters[0] if masters else {}

    group_vars = {
        "k8s_version": k8s.get("version", "1.31"),
        "container_runtime": k8s.get("container_runtime", "cri-o"),
        "cni": k8s.get("cni", "cilium"),
        "kube_proxy_mode": k8s.get("kube_proxy_mode", "ipvs"),
        "pod_network_cidr": k8s.get("pod_network_cidr", "10.128.0.0/14"),
        "service_cidr": k8s.get("service_cidr", "10.96.0.0/16"),
        "api_vip_ip": vip.get("ip", ""),
        "api_vip_hostname": vip.get("hostname", ""),
        "api_endpoint": f"{vip.get('hostname', '')}:6443",
        "cluster_domain": domain,
        "prefix_length": prefix,
        "first_master": first_master.get("name", ""),
        "first_master_ip": first_master.get("ip", ""),
        "masters": [{"name": n["name"], "ip": str(n["ip"])} for n in masters],
        "workers": [{"name": n["name"], "ip": str(n["ip"])} for n in workers],
        "infra_nodes": [{"name": n["name"], "ip": str(n["ip"])} for n in infra],
        "bootstrap_host_ip": bootstrap["ip"],
        "bootstrap_http_port": bootstrap.get("http_port", 8080),
        "operators": k8s.get("operators", []),
    }

    gv_path = group_vars_dir / "all.yml"
    gv_path.write_text(yaml.dump(group_vars, default_flow_style=False, sort_keys=False))
    print(f"Generated {gv_path}")


def main():
    parser = argparse.ArgumentParser(description="Baremetal K8s provisioner")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG,
                        help="Path to config.yaml")
    parser.add_argument("action", choices=[
        "generate", "build-iso", "boot-node", "boot-all", "deploy",
    ])
    parser.add_argument("--node", help="Node name (for build-iso, boot-node)")

    args = parser.parse_args()
    config = load_config(args.config)
    nodes = get_all_nodes(config)
    env = _make_jinja_env()

    if args.action == "generate":
        generate_autoinstall_files(config, env, nodes)
        generate_dnsmasq_conf(config, env, nodes)
        generate_nginx_conf(config, env)
        generate_ansible_files(config, nodes)
        print("\nAll files generated successfully.")

    elif args.action == "build-iso":
        target_nodes = [get_node_by_name(nodes, args.node)] if args.node else nodes
        generate_autoinstall_files(config, env, target_nodes)
        bootstrap = config["bootstrap_host"]
        ssh_user = bootstrap["ssh"]["username"]
        iso_dir = config["os"]["iso_dir"]
        base_iso = f"{iso_dir}/{os.path.basename(config['os']['iso_url'])}"
        scripts_dir = BASE_DIR / "scripts"

        for node in target_nodes:
            print(f"\nBuilding ISO for {node['name']}...")
            # Copy autoinstall configs to bootstrap host
            subprocess.run([
                "scp",
                str(RUN_DIR / f"autoinstall-{node['name']}.yaml"),
                str(RUN_DIR / f"network-config-{node['name']}.yaml"),
                f"{ssh_user}@{bootstrap['ip']}:{iso_dir}/",
            ], check=True)
            # Copy build-iso.sh to bootstrap host and run it
            subprocess.run([
                "scp", str(scripts_dir / "build-iso.sh"),
                f"{ssh_user}@{bootstrap['ip']}:/tmp/build-iso.sh",
            ], check=True)
            subprocess.run([
                "ssh", f"{ssh_user}@{bootstrap['ip']}",
                "bash", "/tmp/build-iso.sh",
                "--base-iso", base_iso,
                "--output", f"{iso_dir}/{node['name']}.iso",
                "--user-data", f"{iso_dir}/autoinstall-{node['name']}.yaml",
                "--network-config", f"{iso_dir}/network-config-{node['name']}.yaml",
                "--label", f"AUTOINSTALL-{node['name'].upper()}",
            ], check=True)

    elif args.action in ("boot-node", "boot-all"):
        target_nodes = [get_node_by_name(nodes, args.node)] if args.node else nodes
        scripts_dir = BASE_DIR / "scripts"
        bootstrap = config["bootstrap_host"]

        for node in target_nodes:
            rf = node["redfish"]
            bmc = node["bmc"]
            iso_url = f"http://{bootstrap['ip']}:{bootstrap.get('http_port', 8080)}/iso/{node['name']}.iso"

            print(f"\nBooting {node['name']} via Redfish...")
            subprocess.run([
                "bash", str(scripts_dir / "redfish.sh"),
                "boot",
                bmc["address"], bmc["username"], bmc["password"],
                rf["scheme"], rf["base_uri"], rf["manager_uri"],
                rf["virtual_media_slot"], iso_url,
                "true" if rf.get("verify_ssl", False) else "false",
            ], check=True)

    elif args.action == "deploy":
        generate_autoinstall_files(config, env, nodes)
        generate_dnsmasq_conf(config, env, nodes)
        generate_nginx_conf(config, env)
        generate_ansible_files(config, nodes)

        print("\n>>> Step 1/5: Setting up bootstrap host...")
        subprocess.run([
            "ansible-playbook", "-i", "inventory.ini",
            "site.yml", "--tags", "bootstrap",
        ], cwd=ANSIBLE_DIR, check=True)

        print("\n>>> Step 2/5: Building ISOs...")
        subprocess.run([
            sys.executable, __file__, "--config", str(args.config),
            "build-iso",
        ], check=True)

        print("\n>>> Step 3/5: Booting all nodes via Redfish...")
        subprocess.run([
            sys.executable, __file__, "--config", str(args.config),
            "boot-all",
        ], check=True)

        print("\n>>> Step 4/5: Waiting for SSH on all nodes...")
        ssh_user = config["bootstrap_host"]["ssh"]["username"]
        all_ips = [str(n["ip"]) for n in nodes]
        for ip in all_ips:
            for attempt in range(1, 121):
                result = subprocess.run(
                    ["ssh", "-o", "StrictHostKeyChecking=no",
                     "-o", "UserKnownHostsFile=/dev/null",
                     "-o", "ConnectTimeout=5",
                     "-o", "LogLevel=ERROR",
                     f"{ssh_user}@{ip}", "true"],
                    capture_output=True,
                )
                if result.returncode == 0:
                    print(f"  {ip} is reachable")
                    break
                if attempt % 10 == 0:
                    print(f"  Waiting for {ip}... ({attempt}/120)")
                time.sleep(10)
            else:
                print(f"ERROR: Timed out waiting for {ip}", file=sys.stderr)
                sys.exit(1)

        print("\n>>> Step 5/5: Running Ansible K8s playbook...")
        subprocess.run([
            "ansible-playbook", "-i", "inventory.ini", "site.yml",
        ], cwd=ANSIBLE_DIR, check=True)

        print("\n" + "=" * 60)
        print("Deploy complete! Baremetal K8s cluster is ready.")
        print("=" * 60)


if __name__ == "__main__":
    main()
