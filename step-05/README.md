# Step 5: Set up worker node to join the cluster

> NOTE: This step is done in worker node only.

In step 4, we have setup master node, and it prints a command line with the token so that worker node can join with:

```bash
kubeadm join 192.168.122.10:6443 --token k1sm62.fzh3kv9e6fq4tthm \
	--discovery-token-ca-cert-hash sha256:255560e9b1be155aafeb91fa8d7c204d14c39f946d75c429dd0bc01d14e9a15b
```

```bash
[lgao@k8s-worker ~]$ sudo kubeadm join k8s-master:6443 --token 8mwxmm.2ae43lv3bo60gqpj --discovery-token-ca-cert-hash sha256:71d5cfdf7b1f0aff0e3ea5eb2f2d30980688b340eb7f01944c938e3500609173 
[preflight] Running pre-flight checks
[preflight] Reading configuration from the "kubeadm-config" ConfigMap in namespace "kube-system"...
[preflight] Use 'kubeadm init phase upload-config --config your-config.yaml' to re-upload it.
[kubelet-start] Writing kubelet configuration to file "/var/lib/kubelet/config.yaml"
[kubelet-start] Writing kubelet environment file with flags to file "/var/lib/kubelet/kubeadm-flags.env"
[kubelet-start] Starting the kubelet
[kubelet-check] Waiting for a healthy kubelet at http://127.0.0.1:10248/healthz. This can take up to 4m0s
[kubelet-check] The kubelet is healthy after 1.003072471s
[kubelet-start] Waiting for the kubelet to perform the TLS Bootstrap

This node has joined the cluster:
* Certificate signing request was sent to apiserver and a response was received.
* The Kubelet was informed of the new secure connection details.

Run 'kubectl get nodes' on the control-plane to see this node join the cluster.

```
From the above log, we can see:

* In preflight phase, it reads kubeadm-config ConfigMap from control plane
* and upload the worker config information to control plane
* 

### Print the join command from master node

If you forgot the printed kubeadm command to join the cluster for the worker node, run the following command in master node to get it:

```bash
[lgao@k8s-master ~]$ kubeadm token create --print-join-command
kubeadm join k8s-master:6443 --token 8mwxmm.2ae43lv3bo60gqpj --discovery-token-ca-cert-hash sha256:71d5cfdf7b1f0aff0e3ea5eb2f2d30980688b340eb7f01944c938e3500609173
```

> NOTE: each time it will be different token and hash.


## What we have in the worker node so far

* containers:

```bash
[lgao@k8s-worker ~]$ sudo crictl ps
CONTAINER           IMAGE               CREATED             STATE               NAME                ATTEMPT             POD ID              POD                     NAMESPACE
636cef28037e4       30ea53e259332       45 seconds ago      Running             kube-flannel        0                   42cad98679dfa       kube-flannel-ds-ccr76   kube-flannel
f8f611efa5bdb       a1ae78fd2f9d8       7 minutes ago       Running             kube-proxy          0                   c799d3e856ae1       kube-proxy-f4pw2        kube-system
```

* pods

```bash
[lgao@k8s-worker ~]$ sudo crictl pods
POD ID              CREATED             STATE               NAME                    NAMESPACE           ATTEMPT             RUNTIME
c799d3e856ae1       9 minutes ago       Ready               kube-proxy-f4pw2        kube-system         0                   (default)
42cad98679dfa       9 minutes ago       Ready               kube-flannel-ds-ccr76   kube-flannel        0                   (default)

```

So there are 2 pods and 2 containers running with the basic setup.

all of them are for the network functionality.

Wait for about 10 minutes, you will see the worker node is ready:

```bash
[lgao@k8s-master ~]$ kubectl get nodes
NAME         STATUS   ROLES           AGE    VERSION
k8s-master   Ready    control-plane   110m   v1.32.3
k8s-worker   Ready    <none>          11m    v1.32.3
```