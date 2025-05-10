# Preparation for OpenShift UPI Deployment

This project prepares:

- DNS and DHCP services for installing a local OpenShift cluster with User Provisioned Infrastructure (UPI), leveraging libvirt's built-in dnsmasq and system's systemd-resolved.
- install-config.yaml file to be used to generate manifests and ignition files

## Overview

The `prepare.py` script automates the setup of:

1. DNS resolution through libvirt's built-in dnsmasq service
2. Configuration of systemd-resolved on the host to properly resolve VM hostnames
3. DHCP services for IP address allocation to VMs via libvirt's network configurations

## Requirements

- libvirt/KVM environment
- systemd-resolved service on host
- Root or sudo access on the host

## Steps to install OCP 4.18 on UPI

- prepare dns/dhcp and the install-config.yaml file:

  > ./prepare.py

- Download the following files to the current directory:

  - openshift-install # The binary installer program
  - rhcos-live-initramfs.x86_64.img # the initramfs image
  - rhcos-live-kernel-x86_64 # The kernel for for the coreos
  - rhcos-live-rootfs.x86_64.img # The rootfs during the installation

- generate manifests

  > mkdir -p install-dir && rm -rf install-dir/\*
  > cp install-config.yaml install-dir/
  > ./openshift-install create manifests --dir=install-dir

NOTE: Check the manifests and do your customization there

- prepare ignition configs

  > ./openshift-install create ignition-configs --dir=install-dir
  > NOTE: the manifests will be used to generate the ignition configs, and the manifest files will be removed.

- Start http server to serve the assets:

  > sudo firewall-cmd --zone=libvirt --add-port=8080/tcp --permanent
  > sudo firewall-cmd --reload
  > python -m http.server 8080

- create bootstrap VM

  ```bash
  sudo bash -x install_bootstrap.ocp-cluster.ocp.lan.sh
  ```

- Create control-plane VMs
- Create worker VMs

```

```
