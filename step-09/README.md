# Step 9: Create a cluster account and login with it.

It is not as easy as OpenShift to add a new account in a pure k8s cluster.

In the future, it would be great to setup a OIDC provider like Keycloak for the k8s cluster.

In k8s, user is authenticated using the certificate, so the basica idea is to produce a private|public key pair and ask the control plane to issue a certificate for this user.

The user name is the `CN` in the subject within certificate, the role is the `O` in the subject.

* Create a key pair:

```bash
openssl genrsa -out developer.key 2048
```
This creates a private key and saves to `developer.key` file.

* Create a CSR(Certificate Signing Request):

```bash
openssl req -new -key developer.key -out developer.csr -subj "/CN=developer/O=developers"
```
This creates a `developer.csr` file for the certificate signing request.
The user name is: `developer`
The group name is: `developers`

* Issue the certificate for the new account.

As there is a CA certificate in k8s control plan setup already, normally located at `/etc/kubernetes/pki/ca.crt`, we can either copy the csr file to the master node for the generation, or we can use the more k8s native way to issue the certificate.

   * k8s native way if you have admin access to k8s using kubectl

```bash
mycsr="$(cat developer.csr | base64 | tr -d '\n')"
```
   Create a `CertificateSigningRequest` resource:
```yaml
apiVersion: certificates.k8s.io/v1
kind: CertificateSigningRequest
metadata:
  name: developer-csr
spec:
  request: <from $mycsr>
  signerName: kubernetes.io/kube-apiserver-client
  usages:
  - client auth
```

```bash
[🎩 lgao@lins-p1 step-09]$ kubectl apply -f csr.yaml
certificatesigningrequest.certificates.k8s.io/developer-csr created
```

Then using admin role to check the request:
```bash
[🎩 lgao@lins-p1 step-09]$ kubectl get csr
NAME            AGE   SIGNERNAME                            REQUESTOR          REQUESTEDDURATION   CONDITION
developer-csr   30s   kubernetes.io/kube-apiserver-client   kubernetes-admin   <none>              Pending
```

You will see a pending for this, and approve it:
```bash
[🎩 lgao@lins-p1 step-09]$ kubectl certificate approve developer-csr
certificatesigningrequest.certificates.k8s.io/developer-csr approved
[🎩 lgao@lins-p1 step-09]$ kubectl get csr
NAME            AGE    SIGNERNAME                            REQUESTOR          REQUESTEDDURATION   CONDITION
developer-csr   107s   kubernetes.io/kube-apiserver-client   kubernetes-admin   <none>              Approved,Issued
```
   * Get the client certificate down
```bash
[🎩 lgao@lins-p1 step-09]$ kubectl get csr developer-csr -o jsonpath='{.status.certificate}' | base64 --decode > ~/.kube/developer.crt
```
Now, the `developer.crt` gets issued and downloaded to `~/.kube/developer.crt`

You can also use openssl to issue the developer.crt directly runningthis in the master node:

```bash
openssl x509 -req -in developer.csr -CA /etc/kubernetes/pki/ca.crt -CAkey /etc/kubernetes/pki/ca.key -CAcreateserial -out developer.crt -days 365
```

But using k8s native way is prefered because it provides the audit logs.

> NOTE: the CSR resources can be deleted from the cluster after you download the certificate.

* Create a `CusterRole` in k8s

Until now, we have setup the certificate based authentication, but no authorization yet.
As we need a developer role which can deploy the applications to the cluster, it would be better to have a ClusterRole instead of a Role within a namespace.

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: developers
rules:
- apiGroups: [""]
  resources: ["namespaces", "pods", "services", "configmaps", "secrets", "persistentvolumeclaims"]
  verbs: ["create", "get", "list", "watch", "update", "delete"]
- apiGroups: ["apps"]
  resources: ["deployments", "statefulsets", "daemonsets", "replicasets"]
  verbs: ["create", "get", "list", "watch", "update", "delete", "patch"]
- apiGroups: ["networking.k8s.io"]
  resources: ["ingresses"]
  verbs: ["create", "get", "list", "watch", "update", "delete"]
- apiGroups: ["autoscaling"]
  resources: ["horizontalpodautoscalers"]
  verbs: ["create", "get", "list", "watch", "update", "delete"]
- apiGroups: [""]
  resources: ["pods/exec"]
  verbs: ["create"]
```
`name: developers` needs to match the `-O=developers` in the certificate subject above.

As you can see, when you define the role, you define the permissions to each apiGroup as well.

There are existing roles as well, in case you can use directly:

```bash
kubectl get clusterrole
[🎩 lgao@lins-p1 step-09]$ kubectl describe clusterrole system:basic-user
Name:         system:basic-user
Labels:       kubernetes.io/bootstrapping=rbac-defaults
Annotations:  rbac.authorization.kubernetes.io/autoupdate: true
PolicyRule:
  Resources                                      Non-Resource URLs  Resource Names  Verbs
  ---------                                      -----------------  --------------  -----
  selfsubjectreviews.authentication.k8s.io       []                 []              [create]
  selfsubjectaccessreviews.authorization.k8s.io  []                 []              [create]
  selfsubjectrulesreviews.authorization.k8s.io   []                 []              [create]

```

Let's bind the `ClusterRole` to the `developer` user:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: developer-clusterrolebinding
subjects:
- kind: User
  name: developer
  apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: ClusterRole
  name: developers
  apiGroup: rbac.authorization.k8s.io
```
Now you have done all the configurations in the control plane

### Configure the kubectl to use the developer user

You can have multiple clusters, context and credentials set in your local `~/.kube/config` (default)

You can copy the crt and key files to `~/.kube/` directory.

Sets the cluster and context information:
```bash
[🎩 lgao@lins-p1 step-09]$ kubectl config set-cluster k8s-master --server=https://k8s-master:6443 --certificate-authority=~/.kube/k8s-ca.crt
Cluster "k8s-master" set.
```
Set the context for developer and make it current context

```bash
[🎩 lgao@lins-p1 step-09]$ kubectl config set-context developer --cluster k8s-master --user=developer
Context "developer" created.
[🎩 lgao@lins-p1 step-09]$ kubectl config use-context developer 
Switched to context "developer".

```

Sets the developer's certificate and key for the authentication to be used by kubectl:
```bash
[🎩 lgao@lins-p1 step-09]$ kubectl config set-credentials developer --client-certificate=~/.kube/developer.crt --client-key=~/.kube/developer.key
User "developer" set.
```

Now you are all set:

```bash

```
The content in `~/.kube/config` is like:
```yaml
apiVersion: v1
clusters:
- cluster:
    certificate-authority: /home/lgao/.kube/k8s-ca.crt
    server: https://k8s-master:6443
  name: k8s-master
contexts:
- context:
    cluster: k8s-master
    user: developer
  name: developer
current-context: developer
kind: Config
preferences: {}
users:
- name: developer
  user:
    client-certificate: /home/lgao/.kube/developer.crt
    client-key: /home/lgao/.kube/developer.key
```

So now, by default, the kubectl will use the developer context.
If you want to swith to kube-admin, set the environment:
```bash
export KUBECONFIG=~/.kube/admin.conf
```
