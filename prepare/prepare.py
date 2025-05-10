#!/usr/bin/env python3

import os
import click
import re
import jinja2
import uuid
from typing import List, Dict, Any

def validate_hostname(value):
    """Validate hostname format"""
    if value and not re.match(r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?$', value):
        raise click.BadParameter('Invalid hostname format')
    return value

def validate_ip_range(value):
    """Validate IP range format"""
    if not value:
        return value

    pattern = r'^(\d{1,3}\.){3}\d{1,3} - (\d{1,3}\.){3}\d{1,3}$'
    if not re.match(pattern, value):
        raise click.BadParameter('Invalid IP range format. Use format like "192.168.100.100 - 192.168.100.200"')
    return value

def get_network_template():
    return """<network>
  <name>{{ network_name }}</name>
  <uuid>{{ uuid }}</uuid>
  <bridge name="{{ bridge_name }}" />
  <forward mode="nat" />

  <dns>
  {% for vm in vms %}
    <host ip="{{ vm.ip }}">
      {% for hostname in vm.host_names %}<hostname>{{ hostname }}</hostname>
      {% endfor %}
    </host>
  {% endfor %}
  </dns>

  <ip address='{{ host_network_ip }}' netmask='255.255.255.0'>
    <dhcp>
      <range start="{{ dhcp_start }}" end="{{ dhcp_end }}"/>
      {% for vm in vms %}<host mac="{{ vm.mac }}" name="{{ vm.host_names | first }}" ip="{{ vm.ip }}"/>
      {% endfor %}
    </dhcp>
  </ip>
</network>
    """

def get_virt_install_vm_template():
    return """#!/bin/bash
kernel=http://{{ host_network_ip }}:8080/rhcos-live-kernel-x86_64
initrd=http://{{ host_network_ip }}:8080/rhcos-live-initramfs.x86_64.img
kernel_args='ip=dhcp rd.neednet=1 console=tty0 console=ttyS0 coreos.inst=yes coreos.inst.install_dev=/dev/vda coreos.live.rootfs_url=http://{{ host_network_ip }}:8080/rhcos-live-rootfs.x86_64.img coreos.inst.ignition_url=http://{{ host_network_ip }}:8080/install-dir/{{ vm.type }}.ign'

virt-install --name={{ vm.host_names | first }} \
  --memory=16384 --vcpus=4 \
  --disk path={{ libvirt_pool_dir }}/{{ vm.host_names | first }}.qcow2,size=10 \
  --network network={{ network_name }},mac={{ vm.mac }} \
  --os-variant rhel9.4 \
  --graphics=none \
  --install kernel=${kernel},initrd=${initrd},kernel_args_overwrite=yes,kernel_args="${kernel_args}"

"""

@click.command()
@click.option('--network_file', default='network.xml', help='Output file path for the libvirt network definition')
@click.option('--systemd-resolved-conf-file', default='libvirt_dnsmasq.conf', help='Output file path for the additional DNS aliases like the api.<cluster-name>.<base_domain>')
@click.option('--install-config', default="install-config.yaml", help='The install-config.yaml file to generate')
@click.option('--pull-secret-file', default="pull-secret.txt", help='The pull secret file where the pull secret is downloaded to')
@click.option('--ssh-public-key-file', default="~/.ssh/id_rsa.pub", help='The ssh public key file')
@click.option('--cluster-name', default=None, help='Cluster name')
@click.option('--base-domain', default=None, help='Base domain')
@click.option('--network-name', default=None, help='Network name for libvirt')
@click.option('--bridge-name', default=None, help='Bridge network name')
@click.option('--dhcp-start', default=None, help='DHCP start IP')
@click.option('--dhcp-end', default=None, help='DHCP end IP')
@click.option('--master-count', type=int, default=2, help='Number of master nodes')
@click.option('--worker-count', type=int, default=1, help='Number of worker nodes')
@click.option('--master-prefix', default="master", help='Master node prefix')
@click.option('--worker-prefix', default="worker", help='Worker node prefix')
@click.option('--libvirt-pool-dir', default="~/images/ocp", help='The libvirtd pool directory')
def main(network_file, systemd_resolved_conf_file, cluster_name, base_domain, network_name, bridge_name,
            dhcp_start, dhcp_end, master_count, worker_count, master_prefix, worker_prefix, install_config, pull_secret_file, ssh_public_key_file, libvirt_pool_dir):

    """ *** Prepare Kubernetes / OpenShift Cluster Configuration *** """
    click.echo(click.style("""
*** Welcome to Kubernetes / OpenShift Cluster Preparation Tool - DNS / DHCP ***
This script tries to generate the DNS and DHCP for the libvirt based VMs.
Libvirtd has the builtin dnsmasq employed to provide the DHCP and DNS services for the VMs, which listens on the bridge network.

This script will generate the libvirt network definition file to be used on defining the network for the VMs

As this is for OpenShift setup, it will generate the DNS entries for the following:
- bootstrap.<cluster-name>.<base_domain>
- ingress.<cluster-name>.<base_domain>
- api.<cluster-name>.<base_domain>
- api-int.<cluster-name>.<base_domain>
- *.apps.<cluster-name>.<base_domain>

This script assumes that you are running systemd-resolved on your host machine for the DNS resolution, and it will generate a drop-in conf file for the base domain to be used with systemd-resolved.

After the generation, you will see the an instruction printed to guide you for the next steps.
""", fg="green", bold=True))

    # Get cluster information
    cluster_name = cluster_name or click.prompt("Enter cluster name", default="ocp-cluster")
    base_domain = base_domain or click.prompt("Enter base domain", default="ocp.lan")

    # Get network information
    network_name = network_name or click.prompt("Enter network name for libvirt", default="ocp")
    bridge_name = bridge_name or click.prompt("Enter bridge network name", default="ocpbr0")
    # Get network IP information
    dhcp_start = dhcp_start or click.prompt("Enter DHCP start IP", default="192.168.100.100")
    dhcp_end = dhcp_end or click.prompt("Enter DHCP end IP", default="192.168.100.200")

    # Validate IP addresses
    ip_pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
    while not re.match(ip_pattern, dhcp_start):
        click.echo(click.style("Invalid IP format. Use format like '192.168.100.100'", fg="red"))
        dhcp_start = click.prompt("Enter DHCP start IP", default="192.168.100.100")

    while not re.match(ip_pattern, dhcp_end):
        click.echo(click.style("Invalid IP format. Use format like '192.168.100.200'", fg="red"))
        dhcp_end = click.prompt("Enter DHCP end IP", default="192.168.100.200")

    # Calculate host network IP (first three sections + ".1")
    ip_parts = dhcp_start.split('.')
    host_network_ip = f"{ip_parts[0]}.{ip_parts[1]}.{ip_parts[2]}.1"

    # Get VM count for masters and workers
    master_count = master_count if master_count is not None else click.prompt(
        "How many master nodes do you want to create?", type=click.IntRange(1, 10), default=2)
    worker_count = worker_count if worker_count is not None else click.prompt(
        "How many worker nodes do you want to create?", type=click.IntRange(0, 100), default=1)

    install_config = install_config or click.prompt("Which file to generate the install config", default="install-config.yaml")
    pull_secret_file = pull_secret_file or click.prompt("Which file to read the pull_secret from", default="pull-secret.txt")
    ssh_public_key_file = ssh_public_key_file or click.prompt("Which file to read the ssh public key", default="~/.ssh/id_rsa.pub")
    libvirt_pool_dir = libvirt_pool_dir or click.prompt("Where to put the VM qcow2 files ? ", default="~/images/ocp")
    libvirt_pool_dir = os.path.expanduser(libvirt_pool_dir)

    # This list will collect all VM configurations
    vms = []

    ip_base = ".".join(dhcp_start.split(".")[:3]) + "."  # Extract first three octets
    ip_start = int(dhcp_start.split(".")[-1])

    # Add bootstrap node
    vms.append({
        "host_names": [f"bootstrap.{cluster_name}.{base_domain}", f"api.{cluster_name}.{base_domain}", f"api-int.{cluster_name}.{base_domain}"],
        "ip": f"{ip_base}{ip_start}",
        "mac": "52:54:00:00:00:01",
        "type": "bootstrap"
    })
    # Increment IP start for the rest of the nodes
    ip_start += 1

    # Add ingress load balancer
    vms.append({
        "host_names": [f"ingress.{cluster_name}.{base_domain}", f"*.apps.{cluster_name}.{base_domain}"],
        "ip": f"{ip_base}{ip_start}",
        "mac": "52:54:00:00:00:02",
        "type": "worker"
    })
    # Increment IP start for the rest of the nodes
    ip_start += 1

    master_prefix = master_prefix or click.prompt("Enter master hostname prefix", default="master")
    worker_prefix = worker_prefix or click.prompt("Enter worker hostname prefix", default="worker")

    # Add master nodes
    for i in range(1, master_count + 1):
        hostname = f"{master_prefix}{i}"
        ip = f"{ip_base}{ip_start + i - 1}"
        mac = f"52:54:00:00:01:{i:02x}"  # Generate MAC with pattern
        vms.append({"host_names": [f"{hostname}.{cluster_name}.{base_domain}", f"api.{cluster_name}.{base_domain}", f"api-int.{cluster_name}.{base_domain}"], "ip": ip, "mac": mac, "type": "master"})

    # Add worker nodes
    for i in range(1, worker_count + 1):
        hostname = f"{worker_prefix}{i}"
        ip = f"{ip_base}{ip_start + master_count + i - 1}"
        mac = f"52:54:00:00:02:{i:02x}"  # Different pattern for workers
        vms.append({"host_names": [f"{hostname}.{cluster_name}.{base_domain}"], "ip": ip, "mac": mac, "type": "worker"})


    # Prepare data for template
    network_data = {
        "vms": vms,
        "cluster_name": cluster_name,
        "base_domain": base_domain,
        "network_name": network_name,
        "bridge_name": bridge_name,
        "dhcp_start": dhcp_start,
        "dhcp_end": dhcp_end,
        "uuid":  uuid.uuid4(),
        "host_network_ip": host_network_ip
    }

    # Apply network template
    try:
        # Get template from the get_template function
        template_content = get_network_template()
        template = jinja2.Template(template_content)
        result = template.render(**network_data)

        # Write to output file
        with open(network_file, 'w') as f:
            f.write(result)

        click.echo(click.style(f"Configuration successfully written to the libvirt network definition file: {network_file}", fg="green"))
    except Exception as e:
        click.echo(click.style(f"Error during template rendering: {str(e)}", fg="red"))

    # Prepare data for template
    drop_in_conf_data = {
        "base_domain": base_domain,
        "host_network_ip": host_network_ip
    }

    # Apply drop_in_conf_data template
    try:
        # Get template from the get_template function
        template_content = """
[Resolve]
DNS={{ host_network_ip }}
Domains=~{{ base_domain }}
"""
        template = jinja2.Template(template_content)
        result = template.render(**drop_in_conf_data)

        # Write to output file
        with open(systemd_resolved_conf_file, 'w') as f:
            f.write(result)

        click.echo(click.style(f"Configuration successfully written to the drop-in config file: {systemd_resolved_conf_file}", fg="green"))
    except Exception as e:
        click.echo(click.style(f"Error during template rendering: {str(e)}", fg="red"))

    click.echo(click.style(f"""
    Now you have generated network definition file at {network_file}, please review it first in case you won't override existing network definitions, and run the following command using root account:

    # copy the drop-in config file to systemd-resolved
    sudo cp {systemd_resolved_conf_file} /etc/systemd/resolved.conf.d/libvirt_{network_name}.conf
    sudo systemctl restart systemd-resolved

    # define the libvirt network
    sudo virsh net-define {network_file}
    sudo virsh net-start {network_name}
    sudo virsh net-autostart {network_name}

    Now you are finished with the network configuration, you can verify the network configuration using the following command:

    dig +noall +answer api.ocp-cluster.ocp.lan
    dig +noall +answer -x 192.168.100.102

    """, fg="green"))

    # Get the absolute path of the current .py file
    file_path = os.path.abspath(__file__)
    # Get the directory of the .py file
    directory = os.path.dirname(file_path)
    full_path = os.path.join(directory, "install-config.yaml.j2")
    try:
        with open(pull_secret_file, "r") as file:
            pull_secret = file.read().strip()
        with open(os.path.expanduser(ssh_public_key_file), "r") as file:
            ssh_public_key = file.read().strip()
        install_config_conf_data = {
            "cluster_name": cluster_name,
            "base_domain": base_domain,
            "master_count": master_count,
            "worker_count": worker_count,
            "pull_secret": pull_secret,
            "ssh_public_key": ssh_public_key
        }

        with open(full_path, "r") as file:
          template_content = file.read()

        template = jinja2.Template(template_content)
        result = template.render(**install_config_conf_data)

        # Write to output file
        with open(install_config, 'w') as f:
            f.write(result)

        click.echo(click.style(f"Configuration successfully written to the install-config.yaml file: {install_config}", fg="green"))
    except Exception as e:
        click.echo(click.style(f"Error during template rendering: {str(e)}", fg="red"))

    # generate shell scripts to install VMs
    for vm in vms:
        print(vm)
        try:
            libvirt_install_data = {
                "vm": vm,
                "libvirt_pool_dir": libvirt_pool_dir,
                "network_name": network_name,
                "host_network_ip": host_network_ip
            }
            template_content = get_virt_install_vm_template()
            template = jinja2.Template(template_content)
            result = template.render(**libvirt_install_data)

            # Write to output file
            with open(f"install_{vm["host_names"][0]}.sh", 'w') as f:
                f.write(result)

            click.echo(click.style(f"Configuration successfully written to the libvirt installation shell: install_{vm["host_names"][0]}.sh", fg="green"))
        except Exception as e:
            click.echo(click.style(f"Error during template rendering: {str(e)}", fg="red"))

if __name__ == '__main__':
    main()
