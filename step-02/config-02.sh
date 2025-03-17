#!/bin/bash

echo -e "Turn off swap"
sudo swapoff -a
echo -e "remove the swap package: zram-generator-defaults"
sudo dnf remove -y zram-generator-defaults

echo -e "Disable SELinux"
sudo setenforce 0
sudo sed -i 's/^SELINUX=enforcing/SELINUX=permissive/' /etc/selinux/config

echo -e "Set up kernerl modules: overlay and br_netfilter"
cat <<EOF | sudo tee /etc/modules-load.d/k8s.conf
overlay
br_netfilter
EOF

sudo modprobe overlay
sudo modprobe br_netfilter

echo -e "Set up system on network"
cat <<EOF | sudo tee /etc/sysctl.d/k8s.conf
net.bridge.bridge-nf-call-ip6tables = 1
net.bridge.bridge-nf-call-iptables = 1
net.ipv4.ip_forward = 1
EOF

sudo sysctl --system
