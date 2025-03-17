# Step 4: Initialize master node

All configuration are set, we can initialize the master node now.

> NOTE: only do the cluster initialization on the master node


## Initial on master node

In the `k8s-master` node only, run:

```bash
sudo kubeadm init \
  --apiserver-advertise-address=192.168.122.10 \
  --pod-network-cidr=10.244.0.0/16 \
  --control-plane-endpoint=k8s-master
```

* `--apiserver-advertise-address=xxx`  tells the IP address broadcasted to the cluster where to find the ipserver
* `--pod-network-cidr=xxxx`  tells the network the pods will be running in.
* `--control-plane-endpoint=k8s-master` tells the hostname of the master node as the rest api endpoint.

Now you will get the similar logs:

```bash
[lgao@k8s-master ~]$ sudo kubeadm init \
  --apiserver-advertise-address=192.168.122.10 \
  --pod-network-cidr=10.244.0.0/16 \
  --control-plane-endpoint=k8s-master
[init] Using Kubernetes version: v1.32.3
[preflight] Running pre-flight checks
[preflight] Pulling images required for setting up a Kubernetes cluster
[preflight] This might take a minute or two, depending on the speed of your internet connection
[preflight] You can also perform this action beforehand using 'kubeadm config images pull'
W0317 01:19:01.610185    1035 checks.go:846] detected that the sandbox image "registry.k8s.io/pause:3.8" of the container runtime is inconsistent with that used by kubeadm.It is recommended to use "registry.k8s.io/pause:3.10" as the CRI sandbox image.
[certs] Using certificateDir folder "/etc/kubernetes/pki"
[certs] Generating "ca" certificate and key
[certs] Generating "apiserver" certificate and key
[certs] apiserver serving cert is signed for DNS names [k8s-master kubernetes kubernetes.default kubernetes.default.svc kubernetes.default.svc.cluster.local] and IPs [10.96.0.1 192.168.122.10]
[certs] Generating "apiserver-kubelet-client" certificate and key
[certs] Generating "front-proxy-ca" certificate and key
[certs] Generating "front-proxy-client" certificate and key
[certs] Generating "etcd/ca" certificate and key
[certs] Generating "etcd/server" certificate and key
[certs] etcd/server serving cert is signed for DNS names [k8s-master localhost] and IPs [192.168.122.10 127.0.0.1 ::1]
[certs] Generating "etcd/peer" certificate and key
[certs] etcd/peer serving cert is signed for DNS names [k8s-master localhost] and IPs [192.168.122.10 127.0.0.1 ::1]
[certs] Generating "etcd/healthcheck-client" certificate and key
[certs] Generating "apiserver-etcd-client" certificate and key
[certs] Generating "sa" key and public key
[kubeconfig] Using kubeconfig folder "/etc/kubernetes"
[kubeconfig] Writing "admin.conf" kubeconfig file
[kubeconfig] Writing "super-admin.conf" kubeconfig file
[kubeconfig] Writing "kubelet.conf" kubeconfig file
[kubeconfig] Writing "controller-manager.conf" kubeconfig file
[kubeconfig] Writing "scheduler.conf" kubeconfig file
[etcd] Creating static Pod manifest for local etcd in "/etc/kubernetes/manifests"
[control-plane] Using manifest folder "/etc/kubernetes/manifests"
[control-plane] Creating static Pod manifest for "kube-apiserver"
[control-plane] Creating static Pod manifest for "kube-controller-manager"
[control-plane] Creating static Pod manifest for "kube-scheduler"
[kubelet-start] Writing kubelet environment file with flags to file "/var/lib/kubelet/kubeadm-flags.env"
[kubelet-start] Writing kubelet configuration to file "/var/lib/kubelet/config.yaml"
[kubelet-start] Starting the kubelet
[wait-control-plane] Waiting for the kubelet to boot up the control plane as static Pods from directory "/etc/kubernetes/manifests"
[kubelet-check] Waiting for a healthy kubelet at http://127.0.0.1:10248/healthz. This can take up to 4m0s
[kubelet-check] The kubelet is healthy after 501.501966ms
[api-check] Waiting for a healthy API server. This can take up to 4m0s
[api-check] The API server is healthy after 11.002385172s
[upload-config] Storing the configuration used in ConfigMap "kubeadm-config" in the "kube-system" Namespace
[kubelet] Creating a ConfigMap "kubelet-config" in namespace kube-system with the configuration for the kubelets in the cluster
[upload-certs] Skipping phase. Please see --upload-certs
[mark-control-plane] Marking the node k8s-master as control-plane by adding the labels: [node-role.kubernetes.io/control-plane node.kubernetes.io/exclude-from-external-load-balancers]
[mark-control-plane] Marking the node k8s-master as control-plane by adding the taints [node-role.kubernetes.io/control-plane:NoSchedule]
[bootstrap-token] Using token: k1sm62.fzh3kv9e6fq4tthm
[bootstrap-token] Configuring bootstrap tokens, cluster-info ConfigMap, RBAC Roles
[bootstrap-token] Configured RBAC rules to allow Node Bootstrap tokens to get nodes
[bootstrap-token] Configured RBAC rules to allow Node Bootstrap tokens to post CSRs in order for nodes to get long term certificate credentials
[bootstrap-token] Configured RBAC rules to allow the csrapprover controller automatically approve CSRs from a Node Bootstrap Token
[bootstrap-token] Configured RBAC rules to allow certificate rotation for all node client certificates in the cluster
[bootstrap-token] Creating the "cluster-info" ConfigMap in the "kube-public" namespace
[kubelet-finalize] Updating "/etc/kubernetes/kubelet.conf" to point to a rotatable kubelet client certificate and key
[addons] Applied essential addon: CoreDNS
[addons] Applied essential addon: kube-proxy

Your Kubernetes control-plane has initialized successfully!

To start using your cluster, you need to run the following as a regular user:

  mkdir -p $HOME/.kube
  sudo cp -i /etc/kubernetes/admin.conf $HOME/.kube/config
  sudo chown $(id -u):$(id -g) $HOME/.kube/config

Alternatively, if you are the root user, you can run:

  export KUBECONFIG=/etc/kubernetes/admin.conf

You should now deploy a pod network to the cluster.
Run "kubectl apply -f [podnetwork].yaml" with one of the options listed at:
  https://kubernetes.io/docs/concepts/cluster-administration/addons/

You can now join any number of control-plane nodes by copying certificate authorities
and service account keys on each node and then running the following as root:

  kubeadm join k8s-master:6443 --token czmkp6.6lfc1rk4n4tf5r77 \
	--discovery-token-ca-cert-hash sha256:71d5cfdf7b1f0aff0e3ea5eb2f2d30980688b340eb7f01944c938e3500609173 \
	--control-plane

Then you can join any number of worker nodes by running the following on each as root:

kubeadm join 192.168.122.10:6443 --token czmkp6.6lfc1rk4n4tf5r77 \
	--discovery-token-ca-cert-hash sha256:71d5cfdf7b1f0aff0e3ea5eb2f2d30980688b340eb7f01944c938e3500609173

```

### Check the master node

* What namespaces current k8s has:

```bash
[lgao@k8s-master ~]$ kubectl get namespace
NAME              STATUS   AGE
default           Active   23m
kube-node-lease   Active   23m
kube-public       Active   23m
kube-system       Active   23m
```

* What containers are running:

```bash
[lgao@k8s-master ~]$ sudo crictl ps | awk '{print $7, $10, $11}'
NAME           POD            NAMESPACE
kube-proxy kube-proxy-6h88v kube-system
kube-apiserver kube-apiserver-k8s-master kube-system
kube-scheduler kube-scheduler-k8s-master kube-system
etcd etcd-k8s-master kube-system
kube-controller-manager kube-controller-manager-k8s-master kube-system

```
We see `5` core kubernetes containers running

* All resources so far

```bash
[lgao@k8s-master ~]$ kubectl get all -n default
NAME                 TYPE        CLUSTER-IP   EXTERNAL-IP   PORT(S)   AGE
service/kubernetes   ClusterIP   10.96.0.1    <none>        443/TCP   39m
[lgao@k8s-master ~]$ kubectl get all -n kube-system
NAME                                     READY   STATUS    RESTARTS   AGE
pod/coredns-668d6bf9bc-j959r             0/1     Pending   0          39m
pod/coredns-668d6bf9bc-zpgdx             0/1     Pending   0          39m
pod/etcd-k8s-master                      1/1     Running   0          39m
pod/kube-apiserver-k8s-master            1/1     Running   0          39m
pod/kube-controller-manager-k8s-master   1/1     Running   0          39m
pod/kube-proxy-6h88v                     1/1     Running   0          39m
pod/kube-scheduler-k8s-master            1/1     Running   0          39m

NAME               TYPE        CLUSTER-IP   EXTERNAL-IP   PORT(S)                  AGE
service/kube-dns   ClusterIP   10.96.0.10   <none>        53/UDP,53/TCP,9153/TCP   39m

NAME                        DESIRED   CURRENT   READY   UP-TO-DATE   AVAILABLE   NODE SELECTOR            AGE
daemonset.apps/kube-proxy   1         1         1       1            1           kubernetes.io/os=linux   39m

NAME                      READY   UP-TO-DATE   AVAILABLE   AGE
deployment.apps/coredns   0/2     2            0           39m

NAME                                 DESIRED   CURRENT   READY   AGE
replicaset.apps/coredns-668d6bf9bc   2         2         0       39m

```

These are all the core components needed to set up the k8s cluster.

There is `1` ClusterIP service in the default namespace
There are some pods, services, daemonset, deployment,replicaset resources in the kube-system namespace.


### Set up Network Plugin (Flannel)

As we are install the 2 nodes cluster, we need to make the pods in each node can communicate with other pods in different node, so we need a network plugin to work.

We see there are 2 coredns pods are in Pending status:
```bash
pod/coredns-668d6bf9bc-j959r             0/1     Pending   0          39m
pod/coredns-668d6bf9bc-zpgdx             0/1     Pending   0          39m
```

#### Install CNI Network Plugin

```bash
ARCH=$(uname -m)
  case $ARCH in
    armv7*) ARCH="arm";;
    aarch64) ARCH="arm64";;
    x86_64) ARCH="amd64";;
  esac
mkdir -p /opt/cni/bin
curl -O -L https://github.com/containernetworking/plugins/releases/download/v1.6.2/cni-plugins-linux-$ARCH-v1.6.2.tgz
tar -C /opt/cni/bin -xzf cni-plugins-linux-$ARCH-v1.6.2.tgz
```

#### Apply Flannel plugin

Flannel makes the pods in 2 nodes can communicate with each other without expose the ports to hosts.

The core component of `kube-proxy` is responsible for routing the requests of a service to the backend pods, like vxlan and iptables.

Try to apply the flannel resources:

```bash
kubectl apply -f https://github.com/flannel-io/flannel/releases/latest/download/kube-flannel.yml
```

> NOTE: if you are using differnet pod cidr than `--pod-network-cidr=10.244.0.0/16` when you initilize the cluster in above command, try to download it and modify the pod network range accordingly.

This will create a new namespace: `kube-flannel`, a ConfigMap with the network range set up, a DaemonSet running a pod to serve.


* Test master node status:
```bash
[lgao@k8s-master ~]$ kubectl get nodes
NAME         STATUS   ROLES           AGE   VERSION
k8s-master   Ready    control-plane   80m   v1.32.3
```


Let's see how to set up a worker node to join this cluster.