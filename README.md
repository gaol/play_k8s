# play_k8s
This is the repository recording my journey to k8s

I will start a study to setup a k8s cluster using `kubeadm` utility in my laptop which has:

* 1 master node
* 2 worker nodes: 1 of them `k8s-worker` acts also as the cluster front because HAProxy is installed there.

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

### core components summary

* CoreDNS:
   ```In Kubernetes, CoreDNS serves as the default DNS server, providing essential DNS-based service discovery and name resolution services for pods, services, and other resources within the cluster. It enables clients to access services using DNS names instead of IP addresses, simplifying cluster networking.```

* kube-proxy: Transport Layer, Layer 4 (service -> pods) `Run on Each Node`

    ```Kube-proxy is a Kubernetes networking component that runs on each node and maintains network rules to enable communication between pods and services, facilitating traffic routing and load balancing within the cluster```
    ```It makes sure a request to a service will be load balanced to different pods according to the replicaset.```

    ```Kube-Proxy takes these updates and translates them into Network Address Translation (NAT) rules within the node. Solving the issue of Pods' dynamic IP changes```

    * ```kube-proxy is responsible for Service abstraction and load balancing.```
    * ```Setting up rules to forward service traffic to the correct backend pods```
    * ```It does not handle pod-to-pod connectivity.```
    * ```It is a transport layer(4) network.```
    * ```kube-proxy assigns IP address for a CluterIP service. maybe NodePort too, all services ?```
    * ```kube-proxy configure the DNAT/SNAT rules using netfilter kernel either by iptables or ipvs```

    mode:  iptables(default, O(n) complecity) | ipvs ( O(1) complexity, best performance ) | Userspace | KernelSpace (Windows)

    *  iptables mode:
      ```kube-proxy uses the iptables command-line tool to add, update, or delete rules in the kernel's iptables chains```
    * ipvs mode:
      ```kube-proxy interacts with the IPVS subsystem in the Linux kernel directly using the netlink interface```

```bash
[lgao@k8s-master ~]$ kubectl get configmap kube-proxy -n kube-system -o yaml|grep mode
    mode: ""
```
 So my set up is using `iptables` as the default mode.

* CNI: (Network Layer, Layer 3) kube-flannel:(pods <-> pods) make it possible for pods in different nodes can connect to each other (a virtual subnet)  (`Run on Each Node`)

    ```In Kubernetes, kube-flannel's role is to provide a simple, lightweight layer 3 network fabric, enabling pods to communicate across different nodes within the cluster by assigning each node a subnet and using VXLAN for packet encapsulation```
    ```Flannel is a Container Network Interface (CNI) plugin. There are other plugins as well.```

    ```CNI provides a common interface to the underlying network```

   * ```CNI assigns IP addresses for the pods, kube-proxy does not. ```
   * ```CNI sets up network interfaces for Pods, kube-proxy does not. ```
   * ```CNI ensures pods can communitcate with others in different nodes via protocol like VXLan```


* HAProxy | ingress  :: external load distribution ; reverse proxy(TLS termination, routing traffic )
                  , haproxy -> |  service   ->   pods    |
                                    ( inside cluster )
   haproxy normally runs on a dedicated node ( `infrastructure node` )
   all external requests got to that infrastructure node

   External requests -- haproxy --> service  -- kube-proxy --> pod

   * https://seifrajhi.github.io/blog/kubernetes-networking/
   * https://medium.com/@rifewang/kubernetes-how-kube-proxy-and-cni-work-together-1255d273f291

   HAProxy works in `LoadBalance` and `NodePort` mode, on the local set up, we use `NodePort`, in public cloud env, it would be `LoadBalance`. The public cloud will provide an ADDRESS for HAProxy service so that it serve outside the cluster.

* kube-apiserver-k8s-master: brain
   - api server is the gateway for all cluster operations. It opens a REST endpoint with core apis and api groups.
   - core api is under `/api/`, like: `/api/v1`
   - extension api groups are under their own: `/apis/my-group/my-version`
   - kubectl talks with api-server, which will trigger other components via the watch endpoint
   - the configuration, the update gets persistented to the etcd pod.
   - The watch endpoint is subscribed by kubelet, controller-manager, scheduler.

* kube-controller-manager-k8s-master : fixer
   - Control loops that monitor the cluster's state and make changes to achieve the desired state defined in the cluster's configuration
   - It automates tasks like pod scaling, volume binding, and service endpoint updates
   - It hosts and manages multiple controllers, each responsible for specific aspects of cluster management, such as replication, endpoints, namespaces, and service accounts
   - Allows for the integration of custom controllers, enabling organizations to extend Kubernetes functionality for specific use cases
   - node controller | replication controller | deployment controller | job controller

* etcd-k8s-master : memory
   - acts as a distributed, reliable key-value store, storing and replicating the cluster's state, configuration, and metadata, ensuring consistency and high availability
   - etcd uses the `Raft consensus algorithm` to ensure high availability, meaning that the cluster can continue to operate even if some nodes fail.
   - A dedicated volume like ssd would be better for the performance, each etcd has it's own copy of data, so there is no need to share the data.
   - Use `etcdctl snapshot save | restore` for the backup and recovery for the etcd data migration.
   - specify `--initial-cluster=etcd1=http://<MASTER_1_IP>:2380,etcd2=http://<MASTER_2_IP>:2380,etcd3=http://<MASTER_3_IP>:2380` when startsup.
   - etcd is strong consistent, real-time consistency.

* kube-scheduler-k8s-master : planner
   - decide where to place Pods (containers) across your cluster’s worker nodes
   - evaluates Resource requirements (CPU, memory, etc.), Node availability (health, capacity), Constraints like node labels, taints/tolerations, affinity/anti-affinity rules. It then assigns the Pod to the "best-fit" node in the cluster
   - Eliminates nodes that don’t meet the Pod’s requirements
   - then Ranks remaining nodes to pick the optimal one (e.g., least utilized node)
   - It updates the nodeName of a pod, and the kubelet gets noticed to create and start the pod's containers.
   - basically it is a planner, not the executor. kubelet is the executor.

* kubelet: doer. this is a daemon service running on each node.
  - kubelet has client key, client certificate, apiserver's ca cert
  - kubelet has a long live connection to the watch endpoint in apiserver.
  - pod/containers creation, start|stop|restarting containers
  - monitor containers resource usage: cpu, memory
  - performing liveness and readiness check for the containers
  - reporting the pods and node status to api server

### Future thinkings

* Some app is quite big, duplicate each container image to different nodes waste lots of spaces, maybe there is a way to share the image without downloading to the nodes ?
* Will k8s purage the unused images in the node where the deployments have been deleted ?
* There is a no-proxy solution.

### TODO

- [ ] Configure kube-proxy to use `ipvs` mode explicitly.
- [ ] Create a developer user account and run against the cluster from the host.
- [x] Add another worker node  --> DONE in `step 07`
- [ ] Deloy Redis cluster on 2 worker nodes
- [ ] Deploy Kafka cluster on 2 worker ndoes
- [ ] Setup a private image registry.
- [ ] A customized operator
- [ ] A customized qcow2 template.
