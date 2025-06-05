#!/bin/bash

set -e


echo "This script tries to set up an image registry in the management cluster so that the hosted cluster can use it"

NAMESPACE="myireg"
DEPLOYMENT_NAME="myireg"
PULL_SECRET_NAME="registry-pull-secret"
TLS_SECRET_NAME="registry-tls-secret"

username="image-username"
password="image-password"
image_secret=$(echo -n "$username:$password" |base64)
wd="$(pwd)/tmp"
pull_secret_file="$wd/pull-secret.json"
htpasswd_file="$wd/htpasswd"
secret_name="image-registry-htpasswd"

echo -e "Getting current OpenShift Cluster Info"
apps_domain="$(oc get ingresses.config.openshift.io cluster -o jsonpath='{.spec.domain}{"\n"}')"
image_registry_route="$DEPLOYMENT_NAME.$NAMESPACE.$apps_domain"

echo -e "Apps Domain: $apps_domain"
echo -e "Image Registry Route Host will be: $image_registry_route"

echo -e "Creating tmp directory at $wd for materials during set up"
mkdir -p $wd

echo -e "Generating htpasswd file to $htpasswd_file"
[ -f $htpasswd_file ] || htpasswd -Bbn $username $password > $htpasswd_file

# Create namespace if not exists
echo -e "Make sure namespace: $NAMESPACE exists"
oc get namespace $NAMESPACE >/dev/null 2>&1 || oc create namespace $NAMESPACE

echo -e "Creates http secret secret for image registry"
http_secret="$(openssl rand -hex 32)"
oc get secret http-secret -n $NAMESPACE >/dev/null 2>&1 || oc create secret generic http-secret \
  --from-literal=http-secret="$http_secret" -n $NAMESPACE

echo -e "Creates htpasswd secret $secret_name for image registry"
oc get secret $secret_name -n $NAMESPACE >/dev/null 2>&1 || oc create secret generic $secret_name --from-file="htpasswd=$htpasswd_file" -n $NAMESPACE

echo -e "Creates tls key and certificate if it does not exist"
[ -f $wd/tls.crt ] || openssl req -newkey rsa:4096 -nodes -sha256 -keyout $wd/tls.key \
  -x509 -days 365 -out $wd/tls.crt \
  -subj "/C=US/ST=OpenShift/L=City/O=HyperShift/CN=$image_registry_route"

echo -e "Creates tls secret if it does not exist"
oc get secret $TLS_SECRET_NAME -n $NAMESPACE >/dev/null 2>&1 || oc create secret tls $TLS_SECRET_NAME \
    --cert=$wd/tls.crt \
    --key=$wd/tls.key \
    -n $NAMESPACE --dry-run=client -o yaml | oc apply -f -

# Create Deployment Service and Route
echo -e "Now creates the registry deployment, service and route"
oc apply -f- <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
    name: $DEPLOYMENT_NAME
    namespace: $NAMESPACE
spec:
    replicas: 1
    selector:
        matchLabels:
            app: $DEPLOYMENT_NAME
    template:
        metadata:
            labels:
                app: $DEPLOYMENT_NAME
            name: $DEPLOYMENT_NAME
        spec:
            containers:
            - name: registry
              image: "registry:2"
              ports:
              - containerPort: 5000
              env:
              - name: REGISTRY_HTTP_SECRET
                valueFrom:
                  secretKeyRef:
                    name: http-secret
                    key: http-secret
              - name: REGISTRY_AUTH
                value: htpasswd
              - name: REGISTRY_AUTH_HTPASSWD_REALM
                value: "Registry Realm"
              - name: REGISTRY_AUTH_HTPASSWD_PATH
                value: /auth/htpasswd
              - name: REGISTRY_HTTP_TLS_CERTIFICATE
                value: "/certs/tls.crt"
              - name: REGISTRY_HTTP_TLS_KEY
                value: "/certs/tls.key"
              volumeMounts:
              - name: tls
                mountPath: /certs
              - name: htpasswd
                mountPath: /auth
            volumes:
            - name: http-secret
              secret:
                secretName: http-secret
            - name: tls
              secret:
                secretName: $TLS_SECRET_NAME
            - name: htpasswd
              secret:
                secretName: $secret_name
---
apiVersion: v1
kind: Service
metadata:
    name: $DEPLOYMENT_NAME
    namespace: $NAMESPACE
spec:
    selector:
        app: $DEPLOYMENT_NAME
    ports:
    - protocol: TCP
      port: 5000
      targetPort: 5000
---
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: $DEPLOYMENT_NAME
  namespace: $NAMESPACE
spec:
  host: $image_registry_route
  to:
    kind: Service
    name: $DEPLOYMENT_NAME
  port:
    targetPort: 5000
  tls:
    termination: edge
EOF

## wait until it is accessible
echo -e "Wait until the pod is ready"
oc rollout status deployment/$DEPLOYMENT_NAME -n $NAMESPACE --timeout=300s

echo -e "registry was set up"
oc get route $DEPLOYMENT_NAME -n $NAMESPACE -o yaml



echo -e "OK, now the image registry has been started."
