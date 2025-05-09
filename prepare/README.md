# DNS and DHCP Preparation for OpenShift UPI Deployment

This project prepares DNS and DHCP services for installing a local OpenShift cluster with User Provisioned Infrastructure (UPI), leveraging libvirt's built-in dnsmasq and system's systemd-resolved.

## Overview

The `prepare.py` script automates the setup of:

1. DNS resolution through libvirt's built-in dnsmasq service
2. Configuration of systemd-resolved on the host to properly resolve VM hostnames
3. DHCP services for IP address allocation to VMs via libvirt's network configurations

## Requirements

- libvirt/KVM environment
- systemd-resolved service on host
- Root or sudo access on the host

## Usage

Run the preparation script to set up DNS and DHCP:

```bash
sudo python3 prepare.py
```

The script will:

- Configure libvirt's dnsmasq for DNS resolution and DHCP
- Update systemd-resolved configuration to forward VM domain queries to libvirt's dnsmasq
- Ensure proper hostname resolution between host and VMs

## Steps to install OCP 4.18 on UPI

- prepare dns/dhcp

  > ./prepare.py

- prepare the install-config.yaml

- generate manifests

- prepare ignition configs
  > openshift-install create install-config --dir=install_dir
  > or use a template instead of interaction mode
- create bootstrap VM

  > after creation of install-config.yaml file in the install_dir folder, run:
  > ./openshift-install create ignition-configs --dir=install_dir
  > NOTE: after generating the ignition files, the install-config.yaml file gets removed

- Create control-plane VMs
- Create worker VMs
