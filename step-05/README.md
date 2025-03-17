# Step 5: Set up worker node to join the cluster

> NOTE: This step is done in worker node only.

In step 4, we have setup master node, and it prints a command line with the token so that worker node can join with:

```bash
kubeadm join 192.168.122.10:6443 --token k1sm62.fzh3kv9e6fq4tthm \
	--discovery-token-ca-cert-hash sha256:255560e9b1be155aafeb91fa8d7c204d14c39f946d75c429dd0bc01d14e9a15b
```

```bash
[lgao@k8s-worker ~]$ sudo kubeadm join 192.168.122.10:6443 --token k1sm62.fzh3kv9e6fq4tthm      --discovery-token-ca-cert-hash sha256:255560e9b1be155aafeb91fa8d7c204d14c39f946d75c429dd0bc01d14e9a15b
[preflight] Running pre-flight checks
	[WARNING Service-Kubelet]: kubelet service is not enabled, please run 'systemctl enable kubelet.service'
[preflight] Reading configuration from the "kubeadm-config" ConfigMap in namespace "kube-system"...
[preflight] Use 'kubeadm init phase upload-config --config your-config.yaml' to re-upload it.
[kubelet-start] Writing kubelet configuration to file "/var/lib/kubelet/config.yaml"
[kubelet-start] Writing kubelet environment file with flags to file "/var/lib/kubelet/kubeadm-flags.env"
[kubelet-start] Starting the kubelet
[kubelet-check] Waiting for a healthy kubelet at http://127.0.0.1:10248/healthz. This can take up to 4m0s
[kubelet-check] The kubelet is healthy after 501.326007ms
[kubelet-start] Waiting for the kubelet to perform the TLS Bootstrap

This node has joined the cluster:
* Certificate signing request was sent to apiserver and a response was received.
* The Kubelet was informed of the new secure connection details.

Run 'kubectl get nodes' on the control-plane to see this node join the cluster.
```