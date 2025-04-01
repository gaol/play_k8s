# Step 6: Deploy a sample application for a test

Now, a basic k8s cluster has been set up. it is time to test if it works as expected.

## Produce the hello world app bundled in a Docker image

I am using the following image as an example for the application deployment:
```bash
ghcr.io/gaol/helloworld:latest
```

> Source: https://github.com/gaol/helloworld/blob/main/src/main/java/io/gaol/demos/helloworld/Helloworld.java#L11

```java
@Route(path = "/hello", methods = Route.HttpMethod.GET)
void hello(RoutingContext rc) {
    rc.response().end(System.getenv()
    .getOrDefault("HOSTNAME", "default_hostname"));
}
```

## Deploy the container image to k8s cluster

```bash
kubectl apply -f deployment.yaml
```

Which will trigger the controller manager to dispatch the actions.
The worker node will be get notified to create the 2 pods because of replica: 2, and pull the images down, when it is ready, the pods get ready and moved to Running status.

## Set up the service for the deployments

```bash
kubectl apply -f service.yaml
```

after creation of the service, you can access the deployment within the master node:

```bash
[lgao@k8s-master ~]$ kubectl get services
NAME         TYPE        CLUSTER-IP      EXTERNAL-IP   PORT(S)   AGE
kubernetes   ClusterIP   10.96.0.1       <none>        443/TCP   21h
quarkus      ClusterIP   10.99.169.225   <none>        80/TCP    5m41s
[lgao@k8s-master ~]$ curl http://10.99.169.225/hello
quarkus-77cfc45698-rz
[lgao@k8s-master ~]$ curl http://10.99.169.225/hello
quarkus-77cfc45698-lt8tt
```

Now, the application works good, and we can easily access the application from within the cluster ndoes.

I need to make the application accessible from external cluster, like the host for the 2 VMs.

We need a `Ingress Controller` for that.

## Set up ingress controller (HAProxy)

```bash
kubectl apply -f https://github.com/haproxytech/kubernetes-ingress/raw/refs/tags/v3.1.4/deploy/haproxy-ingress.yaml
```

> NOTE: it requires memory to be `2560`, you may update it first before applying to k8s.

> NOTE: The haproxy ingress starts a NodePort service which has:

* NodePort: 31726 // port opened on the node
* Port:  80  // the port opened on the cluster wide, so that other services/pods inside of the cluster can access it
* TargetPort: 8080   // the haproxy-ingress pod runs in namespace: haproxy-controller is listening on this port.

This will create the following resources:

```bash
[lgao@k8s-master ~]$ kubectl get all -n haproxy-controller
NAME                                             READY   STATUS    RESTARTS   AGE
pod/haproxy-kubernetes-ingress-8d5b96597-jdgrr   1/1     Running   0          55m

NAME                                 TYPE       CLUSTER-IP       EXTERNAL-IP   PORT(S)                                     AGE
service/haproxy-kubernetes-ingress   NodePort   10.100.212.234   <none>        80:31726/TCP,443:30325/TCP,1024:31335/TCP   55m

NAME                                         READY   UP-TO-DATE   AVAILABLE   AGE
deployment.apps/haproxy-kubernetes-ingress   1/1     1            1           55m

NAME                                                   DESIRED   CURRENT   READY   AGE
replicaset.apps/haproxy-kubernetes-ingress-8d5b96597   1         1         1       55m
```

We see there is a `NodePort` service `service/haproxy-kubernetes-ingress` which bind several ports on the node to the cluster inside:

* node port: `31726` is forwarded to `80` inside of the cluster

In the `haproxy-ingress.yaml`, it specifies:

```yaml
apiVersion: v1
kind: Service
metadata:
  labels:
    run: haproxy-ingress
  name: haproxy-kubernetes-ingress
  namespace: haproxy-controller
spec:
  selector:
    run: haproxy-ingress
  type: NodePort
  ports:
  - name: http
    port: 80
    protocol: TCP
    targetPort: 8080
  - name: https
    port: 443
    protocol: TCP
    targetPort: 8443
  - name: stat
    port: 1024
    protocol: TCP
    targetPort: 1024
```
Which means the traffic to the service on port `80` are forwarded to `8080` for the behind pods.
It is up to the service to decide which pod to dispatch to. (not decided by haproxy I guess !?)

The `ingress.yaml` file specify which path will be routed to the application service:

```yaml
- host: k8s-worker
    http:
    paths:
        - path: /hello
        pathType: Exact
        backend:
            service:
            name:  quarkus
            port:
                number: 80
```
So the requests to `http://k8s-worker:31726/hello` will be routed to `haproxy-ingress` first, which in turn routes it to `quarkus` service on port: `80`, which in turns routes it to the backend pods.

The `haproxy-ingress` service becomes the front end facade, what is why it needs to run at the infrastruce node which has better hardware.

### Deploy the app

* kubectl apply -f deployment.yaml
* kubectl apply -f service.yaml
* kubectl apply -f ingress.yaml

Wait...

```bash
[🎩 lgao@lins-p1 helloworld]$  curl http://k8s-worker:31726/hello
quarkus-77cfc45698-lt8tt[🎩 lgao@lins-p1 helloworld]$ 
[🎩 lgao@lins-p1 helloworld]$ 
[🎩 lgao@lins-p1 helloworld]$  curl http://k8s-worker:31726/hello
quarkus-77cfc45698-rzvj6[🎩 lgao@lins-p1 helloworld]$ 
```