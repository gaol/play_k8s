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