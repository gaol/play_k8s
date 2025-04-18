#!/bin/bash

echo -e "Install a dependent package: iproute-tc"
sudo dnf install -y iproute-tc

echo -e "Install containerd package"
sudo dnf install -y containerd
sudo systemctl enable --now containerd

sudo containerd config default | sudo tee /etc/containerd/config.toml
# Set the cgroup to use systemd for containerd, the similar to docker is set to the daemon.json
sudo sed -i 's/SystemdCgroup = false/SystemdCgroup = true/g' /etc/containerd/config.toml
sudo systemctl restart containerd

cat <<EOF | sudo tee /etc/yum.repos.d/kubernetes.repo
[kubernetes]
name=Kubernetes
baseurl=https://pkgs.k8s.io/core:/stable:/v1.32/rpm/
enabled=1
gpgcheck=1
gpgkey=https://pkgs.k8s.io/core:/stable:/v1.32/rpm/repodata/repomd.xml.key
EOF

sudo dnf install -y kubelet kubeadm kubectl

# initialize the /etc/crictl.yaml file with the following configuration
# specify the sock file that crictl can communicate with containerd
sudo crictl config runtime-endpoint unix:///run/containerd/containerd.sock
sudo crictl config image-endpoint unix:///run/containerd/containerd.sock

sudo systemctl enable --now kubelet

ARCH=$(uname -m)
  case $ARCH in
    armv7*) ARCH="arm";;
    aarch64) ARCH="arm64";;
    x86_64) ARCH="amd64";;
  esac
sudo mkdir -p /opt/cni/bin
sudo curl -O -L https://github.com/containernetworking/plugins/releases/download/v1.6.2/cni-plugins-linux-$ARCH-v1.6.2.tgz
sudo tar -C /opt/cni/bin -xzf cni-plugins-linux-$ARCH-v1.6.2.tgz
