# Step 3: Install needed packages

Unless specified, all the following commands are done in all nodes.


## Install Container runtme: containerd

Install `containerd` as it is the industry standard container runtime for kubernetes environments.

```bash
sudo dnf install -y containerd
sudo systemctl enable --now containerd
```

### Configure `containerd` to enable CRI plugin:

```bash
sudo containerd config default | sudo tee /etc/containerd/config.toml
sudo sed -i 's/SystemdCgroup = false/SystemdCgroup = true/g' /etc/containerd/config.toml
sudo systemctl restart containerd
```

## Install kubeadm, kubelet, kubect

### Adds kubernetes yum repository:

```bash
cat <<EOF | sudo tee /etc/yum.repos.d/kubernetes.repo
[kubernetes]
name=Kubernetes
baseurl=https://pkgs.k8s.io/core:/stable:/v1.29/rpm/
enabled=1
gpgcheck=1
gpgkey=https://pkgs.k8s.io/core:/stable:/v1.29/rpm/repodata/repomd.xml.key
EOF
```

### Install the packages

```bash
sudo dnf install -y kubelet kubeadm kubectl
sudo systemctl enable --now kubelet
```

## Reboot

Reboot to do next step.

```bash
sudo reboot
```

