# Step 3: Install needed packages

Unless specified, all the following commands are done in all nodes.


## Install Container runtme: containerd

Install `containerd` as it is the industry standard container runtime for kubernetes environments.

```bash
sudo dnf install -y containerd
sudo systemctl enable --now containerd
```
Now, the file `/etc/containerd/config.toml` was created.

### Configure `containerd` to use systemd cgroup:

```bash
# the following line will generate default configs to the confi.toml file
sudo containerd config default | sudo tee /etc/containerd/config.toml
# Set the cgroup to use systemd for containerd, the similar to docker is set to the daemon.json
sudo sed -i 's/SystemdCgroup = false/SystemdCgroup = true/g' /etc/containerd/config.toml
sudo systemctl restart containerd

# NOTE: do not install cri-tools now, installation of kubelet will bring the newer version of cri-tools.
# sudo dnf install -y cri-tools
# initialize the /etc/crictl.yaml file with the following configuration
# specify the sock file that crictl can communicate with containerd
#sudo crictl config runtime-endpoint unix:///run/containerd/containerd.sock
#sudo crictl config image-endpoint unix:///run/containerd/containerd.sock

```
### Set up proxy for containerd

It happens often that you cannot pull docker images from docker hub in China, so you can add a proxy to the containerd service:

```bash
# In file: /usr/lib/systemd/system/containerd.service
[Service]
ExecStartPre=-/sbin/modprobe overlay
ExecStart=/usr/bin/containerd
Environment="HTTP_PROXY=http://squid.xxx.xxx:3128/" # specify your squid setup here
```

Or you can add a mirror to it.

## Install kubeadm, kubelet, kubect

### Adds kubernetes yum repository:

```bash
cat <<EOF | sudo tee /etc/yum.repos.d/kubernetes.repo
[kubernetes]
name=Kubernetes
baseurl=https://pkgs.k8s.io/core:/stable:/v1.32/rpm/
enabled=1
gpgcheck=1
gpgkey=https://pkgs.k8s.io/core:/stable:/v1.32/rpm/repodata/repomd.xml.key
EOF
```

### Install the packages

```bash
sudo dnf install -y kubelet kubeadm kubectl

# initialize the /etc/crictl.yaml file with the following configuration
# specify the sock file that crictl can communicate with containerd
sudo crictl config runtime-endpoint unix:///run/containerd/containerd.sock
sudo crictl config image-endpoint unix:///run/containerd/containerd.sock

sudo systemctl enable --now kubelet
```

Now, there are no yaml files generated yet before the kubeadm init command.


### appendx after some kubeadm init warnings/errors:

The following package needs to be installed in Fedora 41:

```bash
sudo dnf install -y iproute-tc
```

## Reboot

Reboot to do next step.

```bash
sudo reboot
```

