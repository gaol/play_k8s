# Step 8: Configure local laptop to access control plane remotely.

With 3 nodes set up, I want to start developing and deploying my apps from my laptop directly, so I need the remote access to the control plane node.


* Install the `kubectl`, `kubeadm` CLI in local:

```bash
cat <<EOF | sudo tee /etc/yum.repos.d/kubernetes.repo
[kubernetes]
name=Kubernetes
baseurl=https://pkgs.k8s.io/core:/stable:/v1.32/rpm/
enabled=1
gpgcheck=1
gpgkey=https://pkgs.k8s.io/core:/stable:/v1.32/rpm/repodata/repomd.xml.key
EOF

sudo dnf install -y kubeadm kubectl
```
we don't need to install `kubelet` as we use the CLI tools only.

* Configure kubetenets acess in local:

normally the config file is at: `~/.kube/config`

```bash
[🎩 lgao@lins-p1 play_k8s]$ scp k8s-master:/etc/kubernetes/admin.conf /home/lgao/.kube/admin.conf
scp: remote open "/etc/kubernetes/admin.conf": Permission denied
[🎩 lgao@lins-p1 play_k8s]$ scp k8s-master:.kube/config /home/lgao/.kube/admin.conf
```

```yaml
apiVersion: v1
clusters:
- cluster:
    certificate-authority-data: xxxx-ca-data
    server: https://k8s-master:6443
  name: kubernetes
contexts:
- context:
    cluster: kubernetes
    user: kubernetes-admin
  name: kubernetes-admin@kubernetes
current-context: kubernetes-admin@kubernetes
kind: Config
preferences: {}
users:
- name: kubernetes-admin
  user:
    client-certificate-data: xxx-client-certificate-data
    client-key-data: xxxx-my-key-data

```

Then set the environment: `export KUBECONFIG=~/.kube/admin.conf`:

```bash
[🎩 lgao@lins-p1 play_k8s]$ export KUBECONFIG=~/.kube/admin.conf
[🎩 lgao@lins-p1 play_k8s]$ kubectl get node
NAME          STATUS   ROLES           AGE     VERSION
k8s-master    Ready    control-plane   2d21h   v1.32.3
k8s-worker    Ready    infra,worker    2d19h   v1.32.3
k8s-worker2   Ready    worker          95m     v1.32.3
[🎩 lgao@lins-p1 play_k8s]$ kubeadm token list
TOKEN                     TTL         EXPIRES                USAGES                   DESCRIPTION                                                EXTRA GROUPS
ruez7w.flkoc2qvhfvg3vyb   22h         2025-03-21T02:21:21Z   authentication,signing   <none>                                                     system:bootstrappers:kubeadm:default-node-token
```

Now both kubectl and kubeadm work from laptop where is outside of the k8s cluster.

You can also create another account and set up a different context to login with different user.