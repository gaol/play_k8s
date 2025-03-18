# play_k8s
This is the repository recording my journey to k8s

I will start a study to setup a k8s cluster using `kubeadm` utility in my laptop which has:

* 1 master node
* 1 worker node

I will use Fedora 40 cloud minimal installation for both master and worker node as I am a Fedora user.

The final goal is to set up a full feature k8s cluster step by step.

I will record what I do in each step in a separate directory, and may adding some notes (make sense or nonsense) just for the record what I am thinking during the set up process.

## Limitations

* Static IP : I will set up static IP for both master node and worker node. maybe to update it later to DHCP but not gurranteed.
* Disable SELinux  : I know OpenShift needs it up, but for now, I focus on pure k8s setup. and for simplicity, I just disable it.
* No firewall : there is no firewall enabled in this setup.

## Read Future

* cloud init doc: `https://cloudinit.readthedocs.io/en/latest/index.html`
* containerd full configuration `/etc/containerd/config.toml`
* crictl configuration: `/etc/crictl.yaml`
* kubelet service

### core components summary

* CoreDNS:
   ```In Kubernetes, CoreDNS serves as the default DNS server, providing essential DNS-based service discovery and name resolution services for pods, services, and other resources within the cluster. It enables clients to access services using DNS names instead of IP addresses, simplifying cluster networking.```

* kube-proxy: (service -> pods) `Run on Each Node`

    ```Kube-proxy is a Kubernetes networking component that runs on each node and maintains network rules to enable communication between pods and services, facilitating traffic routing and load balancing within the cluster```
    ```It makes sure a request to a service will be load balanced to different pods according to the replicaset.```

* kube-flannel:(pods <-> pods) make it possible for pods in different nodes can connect to each other (a virtual subnet)  (`Run on Each Node`)
    ```In Kubernetes, kube-flannel's role is to provide a simple, lightweight layer 3 network fabric, enabling pods to communicate across different nodes within the cluster by assigning each node a subnet and using VXLAN for packet encapsulation```
    ```Flannel is a Container Network Interface (CNI) plugin. There are other plugins as well.```

* HAProxy | ingress  :: external load distribution ; reverse proxy(TLS termination, routing traffic )
                  , haproxy -> |  service   ->   pods    |
                                    ( inside cluster )
   haproxy normally runs on a dedicated node ( `infrastructure node` )
   all external requests got to that infrastructure node

   External requests -- haproxy --> service  -- kube-proxy --> pod

   * https://seifrajhi.github.io/blog/kubernetes-networking/
   * https://medium.com/@rifewang/kubernetes-how-kube-proxy-and-cni-work-together-1255d273f291

   HAProxy works in `LoadBalance` and `NodePort` mode, on the local set up, we use `NodePort`, in public cloud env, it would be `LoadBalance`. The public cloud will provide an ADDRESS for HAProxy service so that it serve outside the cluster.

* kube-apiserver-k8s-master

* kube-controller-manager-k8s-master

* etcd-k8s-master

* kube-scheduler-k8s-master

### Future thinkings

* Some app is quite big, duplicate each container image to different nodes waste lots of spaces, maybe there is a way to share the image without downloading to the nodes ?
* Will k8s purage the unused images in the node where the deployments have been deleted ?
* 