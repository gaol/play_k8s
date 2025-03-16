# Step 1: Prepare 2 KVM

My setup is a 2 nodes k8s cluster, 1 master node and 1 worker node.
Both run in my laptop.

It is important to make the 2 nodes to connect each other, better by hostnames.

## Set up information

### Master Node

* 2 vCPUs, 2GB memory, 20GB disk
* KVM OS: `Fedora 41 Cloud` minimal set up.
* Root password: `R0otPasswD`
* Static IP: `192.168.122.10`
* HostName: `k8s-master`
* Disk Path: `~/images/k8s/k8s-master.qcow2`, size: `20GB`
*

### Commands:

* Download the predefined qcow2 file:
```bash
wget -O ~/images/k8s/k8s-master.qcow2 https://ix-denver.mm.fcix.net/fedora/linux/releases/41/Cloud/x86_64/images/Fedora-Cloud-Base-Generic-41-1.4.x86_64.qcow2
```

or you can download it to a backup place, and copy it to `/home/lgao/images/k8s/k8s-master.qcow2` when needed.

* `cd play_k8s/step-01` to current directory, and run:

```bash
virt-install \
  --name k8s-master \
  --ram 2048 \
  --vcpus 2 \
  --disk path=/home/lgao/images/k8s/k8s-master.qcow2,size=20 \
  --os-variant fedora40 \
  --network bridge=virbr0 \
  --graphics none \
  --console pty,target_type=serial \
  --import \
  --cloud-init user-data=cloud-init-master.yaml,network-config=network-config-master.yaml
```


## Clean the VMs

```bash
virsh shutdown k8s-master
virsh undefine k8s-master
# do not remove the qcow2 file, because it was donwloaded from cloud, try download it again if it is corrupted.
# rm -rf ~/images/k8st/k8s-master.qcow2
```

### Notes

* It would be good to dig deeper on the cloud init to configure the server using Ansible.

