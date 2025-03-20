# Step 7: Add a new worker node

Add new yaml files in `step-01` folder"


```yaml
#cloud-config for worker
hostname: k8s-worker2
timezone: Asia/Shanghai
fqdn: k8s-worker2
manage_etc_hosts: false
users:
  - name: lgao
    ssh-authorized-keys:
      - ssh-rsa xxxx lgao@lins-p1
    sudo: ['ALL=(ALL) NOPASSWD:ALL']
    groups: wheel
    shell: /bin/bash
chpasswd:
  list: |
    lgao:password
  expire: False
runcmd:
  - systemctl enable cloud-init
  - hostnamectl set-hostname k8s-worker
  - systemctl restart NetworkManager
  - echo "192.168.122.10   k8s-master" >> /etc/hosts
  - echo "192.168.122.11   k8s-worker" >> /etc/hosts
  - echo "192.168.122.12   k8s-worker2" >> /etc/hosts
  - echo "Custom configuration complete!"
```

Now I specify the timezone to `Asia/Shanghai` to align to my local laptop date time.

The new worker ndoe has the same setup as the worker node previsouly done.
The new worker node has ip `192.168.1.12`

Runt the following command to init a new VM:
```bash
virt-install \
  --name k8s-worker2 \
  --ram 2048 \
  --vcpus 2 \
  --disk path=/home/lgao/images/k8s/k8s-worker2.qcow2,size=20 \
  --os-variant fedora40 \
  --network bridge=virbr0 \
  --graphics none \
  --console pty,target_type=serial \
  --import \
  --cloud-init user-data=cloud-init-worker2.yaml,network-config=network-config-worker2.yaml
```

After doing the `step 1 - step 3` , following the previous notes, try to join the new worker node.

## Generate a new token for the new worker node to join

In master node, run:

```bash
[lgao@k8s-master ~]$ kubeadm token create --print-join-command
kubeadm join k8s-master:6443 --token ruez7w.flkoc2qvhfvg3vyb --discovery-token-ca-cert-hash sha256:71d5cfdf7b1f0aff0e3ea5eb2f2d30980688b340eb7f01944c938e3500609173
```

Then copy the printed command and run in the new worker node:

```bash
[lgao@k8s-worker2 ~]$ sudo kubeadm join k8s-master:6443 --token ruez7w.flkoc2qvhfvg3vyb --discovery-token-ca-cert-hash sha256:71d5cfdf7b1f0aff0e3ea5eb2f2d30980688b340eb7f01944c938e3500609173
[preflight] Running pre-flight checks
[preflight] Reading configuration from the "kubeadm-config" ConfigMap in namespace "kube-system"...
[preflight] Use 'kubeadm init phase upload-config --config your-config.yaml' to re-upload it.
[kubelet-start] Writing kubelet configuration to file "/var/lib/kubelet/config.yaml"
[kubelet-start] Writing kubelet environment file with flags to file "/var/lib/kubelet/kubeadm-flags.env"
[kubelet-start] Starting the kubelet
[kubelet-check] Waiting for a healthy kubelet at http://127.0.0.1:10248/healthz. This can take up to 4m0s
[kubelet-check] The kubelet is healthy after 500.996625ms
[kubelet-start] Waiting for the kubelet to perform the TLS Bootstrap

This node has joined the cluster:
* Certificate signing request was sent to apiserver and a response was received.
* The Kubelet was informed of the new secure connection details.

Run 'kubectl get nodes' on the control-plane to see this node join the cluster.

```
Then, wait until it gets ready so that you see:

```bash
kubectl get node
```