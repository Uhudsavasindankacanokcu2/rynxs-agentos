# Rynxs Dashboard

Web-based control panel for monitoring and managing Rynxs AI workforce.

## Features

- Real-time agent status monitoring
- Task queue visualization
- Team management overview
- Kubernetes API integration

## Local Development

### Option 1: Static Server

```bash
cd dashboard/public
python3 -m http.server 8080
```

Open http://localhost:8080

### Option 2: kubectl Proxy

```bash
kubectl proxy --port=8001
```

Then open dashboard with API proxy enabled.

## Docker Build

```bash
cd dashboard
docker build -t rynxs-dashboard:latest .
docker run -p 8080:80 rynxs-dashboard:latest
```

## Kubernetes Deployment

```bash
kubectl apply -f ../deploy/dashboard/
```

This deploys:
- Dashboard Deployment (nginx serving static files)
- Service (ClusterIP or LoadBalancer)
- ServiceAccount with RBAC for API access

## Configuration

### API Endpoint

The dashboard automatically detects:
- **Local dev**: http://localhost:8001/apis/universe.ai/v1alpha1
- **In-cluster**: /apis/universe.ai/v1alpha1 (via service account)

### RBAC Permissions

Dashboard requires read access to:
- agents.universe.ai
- tasks.universe.ai
- teams.universe.ai
- metrics.universe.ai

## Access

After deployment:

```bash
kubectl port-forward -n universe svc/rynxs-dashboard 8080:80
```

Open http://localhost:8080

## Production Deployment

For production:
1. Enable TLS/HTTPS
2. Configure ingress controller
3. Add authentication (OAuth2 proxy)
4. Set resource limits
5. Enable monitoring

## Architecture

```
Browser → Dashboard (Static HTML/JS)
         → Kubernetes API Server
         → universe.ai CRDs
```

No backend required - direct API calls via service account.
