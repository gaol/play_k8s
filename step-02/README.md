# Step 2:  Configure Nodes

In future, this step can be merged into step 1 to make the configuraiton automatically.

But for now, I am focusing on the clear set up to not ignore them.

Unless specified, all the following commands are done in all nodes.

## Turn off swap

> NOTE: Swap needs to be turned off in k8s to make the metrics more accurate, and avoid OOM killing randomly even for the kubeadm processes.

```bash
# turn off swap
sudo swapoff -a

# turn if off permanently by editing the file `/etc/fstab`, commenting or deleting the line with swap
```

## Turn off SELinux

> NOTE: this is not mandatory, especially SELinux is required in OpenShift, I am turning it off to focus on the k8s setup without concerning the un expected security issues.

```bash
sudo setenforce 0
sudo sed -i 's/^SELINUX=enforcing/SELINUX=permissive/' /etc/selinux/config
```

## Configure kernel parameters

```bash
cat <<EOF | sudo tee /etc/modules-load.d/k8s.conf
overlay
br_netfilter
EOF

sudo modprobe overlay
sudo modprobe br_netfilter

cat <<EOF | sudo tee /etc/sysctl.d/k8s.conf
net.bridge.bridge-nf-call-ip6tables = 1
net.bridge.bridge-nf-call-iptables = 1
net.ipv4.ip_forward = 1
EOF

sudo sysctl --system

sudo reboot
```

Now, the system configurations of the nodes are done !

Let's move to next step.
