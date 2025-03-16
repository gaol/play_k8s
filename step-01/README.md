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

#### Commands:

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


#### Clean the master VM

```bash
virsh shutdown k8s-master
virsh undefine k8s-master
# do not remove the qcow2 file, because it was donwloaded from cloud, try download it again if it is corrupted.
# rm -rf ~/images/k8st/k8s-master.qcow2
```

### Worker Node

* 2 vCPUs, 2GB memory, 10GB disk
* KVM OS: `Fedora 41 Cloud` minimal set up.
* Root password: `R0otPasswD`
* Static IP: `192.168.122.11`
* HostName: `k8s-worker`
* Disk Path: `~/images/k8s/k8s-worker.qcow2`, size: `20GB`
*

#### Commands:

* Download the predefined qcow2 file:
```bash
wget -O ~/images/k8s/k8s-worker.qcow2 https://ix-denver.mm.fcix.net/fedora/linux/releases/41/Cloud/x86_64/images/Fedora-Cloud-Base-Generic-41-1.4.x86_64.qcow2
```

or you can download it to a backup place, and copy it to `/home/lgao/images/k8s/k8s-worker.qcow2` when needed.

* `cd play_k8s/step-01` to current directory, and run:

```bash
virt-install \
  --name k8s-worker \
  --ram 2048 \
  --vcpus 2 \
  --disk path=/home/lgao/images/k8s/k8s-worker.qcow2,size=20 \
  --os-variant fedora40 \
  --network bridge=virbr0 \
  --graphics none \
  --console pty,target_type=serial \
  --import \
  --cloud-init user-data=cloud-init-worker.yaml,network-config=network-config-worker.yaml
```


#### Clean the worker VM

```bash
virsh shutdown k8s-worker
virsh undefine k8s-worker
# do not remove the qcow2 file, because it was donwloaded from cloud, try download it again if it is corrupted.
# rm -rf ~/images/k8st/k8s-worker.qcow2
```

## Verification

When both VMs created, run them:

```bash
virsh start k8s-master
virsh start k8s-worker
```

and log into the vms from host:
(adds the ip to /etc/hosts in host machine)

```bash
ssh lgao@k8s-master
ssh lgao@k8s-worker
```

In k8s-master, run:
```bash
[lgao@k8s-master ~]$ ping -c 3 k8s-worker
PING k8s-worker (192.168.122.11) 56(84) bytes of data.
64 bytes from k8s-worker (192.168.122.11): icmp_seq=1 ttl=64 time=0.416 ms
64 bytes from k8s-worker (192.168.122.11): icmp_seq=2 ttl=64 time=0.716 ms
64 bytes from k8s-worker (192.168.122.11): icmp_seq=3 ttl=64 time=0.773 ms

--- k8s-worker ping statistics ---
3 packets transmitted, 3 received, 0% packet loss, time 2050ms
rtt min/avg/max/mdev = 0.416/0.635/0.773/0.156 ms
```

In k8s-worker, run:

```bash
[lgao@k8s-worker ~]$ ping -c 3 k8s-master
PING k8s-master (192.168.122.10) 56(84) bytes of data.
64 bytes from k8s-master (192.168.122.10): icmp_seq=1 ttl=64 time=0.404 ms
64 bytes from k8s-master (192.168.122.10): icmp_seq=2 ttl=64 time=0.221 ms
64 bytes from k8s-master (192.168.122.10): icmp_seq=3 ttl=64 time=0.760 ms

--- k8s-master ping statistics ---
3 packets transmitted, 3 received, 0% packet loss, time 2079ms
rtt min/avg/max/mdev = 0.221/0.461/0.760/0.223 ms
```

Now, the 2 nodes are configured.

Let's move to the next step.

## Notes

* It would be good to dig deeper on the cloud init to configure the server using Ansible.

