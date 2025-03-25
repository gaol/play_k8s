# Step 10: Set up an image registry for local usage

In this setup:

* it does not need authentication
* no tls required
* Running on the host where the VMs are running on.
* It is accessible for all 3 nodes, the port is `5000`


## Start the image registry docker container in host:

```bash
docker run -d -p 5000:5000 --restart=always  -v ~/mnt/registry:/var/lib/registry --name image-registry registry:2
```

That is all !

Now there is an image registry running on the host with port `5000` exposed.

> NOTE: the image registry can be running inside of the k8s cluster, and with user/password setup, which deserves an extra step for that.

I also add an item to my `/etc/hosts` in the host and all 3 nodes:

```bash
192.168.122.1 virt.lins-p1
```

## Configure nodes to be able to use this insecure image

Since there is no TLS, no authentication set up, we need to configure the containerd in all 3 nodes to be able to access this image registry.

On each node:

Add the following to `/etc/containerd/config.toml` file:

```ini
      [plugins."io.containerd.grpc.v1.cri".registry.configs]
        [plugins."io.containerd.grpc.v1.cri".registry.configs."virt.lins-p1:5000".tls]
          insecure_skip_verify = true

      [plugins."io.containerd.grpc.v1.cri".registry.headers]

      [plugins."io.containerd.grpc.v1.cri".registry.mirrors]
        [plugins."io.containerd.grpc.v1.cri".registry.mirrors."virt.lins-p1:5000"]
          endpoint = ["http://virt.lins-p1:5000"]

```
then restart containerd

```bash
sudo systemctl restart containerd
```

Now all set, you can use the image registry now in the k8s cluster:

```yaml
apiVersion: v1
kind: Pod
  labels:
    app: quarkus
  name: quarkus-app
  namespace: default
spec:
  containers:
  - image: virt.lins-p1:5000/helloworld:latest  # <-- specify the image in the new registry.
    imagePullPolicy: Always
    name: quarkus-app
    ports:
    - containerPort: 8080
      protocol: TCP
```
