# Rynxs RBAC Permissions

This document explains the RBAC (Role-Based Access Control) permissions required by the rynxs operator.

## Principle: Least Privilege

The rynxs operator follows the **principle of least privilege**:
- **No wildcard permissions** (`*`) for resources or verbs
- **Minimal verb set** - only permissions required for core functionality
- **Explicit resource list** - no blanket access to all resources in an apiGroup
- **No cluster-admin** - operator runs with restricted ServiceAccount

This approach follows [Kubernetes RBAC Good Practices](https://kubernetes.io/docs/concepts/security/rbac-good-practices/).

## Permission Breakdown

### 1. Custom Resources (universe.ai API group)

**Resources**: `agents`, `sessions`  
**Verbs**: `get`, `list`, `watch`, `patch`

```yaml
- apiGroups: ["universe.ai"]
  resources: ["agents", "sessions"]
  verbs: ["get", "list", "watch", "patch"]
```

**Why these permissions?**
- `watch`: **Required** for event-driven reconciliation. Kopf (and all K8s operators) rely on watch to receive create/update/delete events for custom resources.
- `list`: Required for initial sync when operator starts (list all existing CRs).
- `get`: Required to fetch full CR details during reconciliation.
- `patch`: Required to update CR annotations, finalizers, and other metadata.

**Why no `create` or `delete`?**
- Operators typically don't create their own CRs (users do via kubectl/API).
- Delete is not needed for basic reconciliation. If cleanup/finalizers are added later, `delete` will be added with justification.

**Reference**: [Kubernetes RBAC API](https://kubernetes.io/docs/reference/access-authn-authz/rbac/#referring-to-resources)

### 2. Custom Resource Status

**Resources**: `agents/status`, `sessions/status`  
**Verbs**: `patch`

```yaml
- apiGroups: ["universe.ai"]
  resources: ["agents/status", "sessions/status"]
  verbs: ["patch"]
```

**Why?**
- Status subresource is updated separately from spec in Kubernetes.
- Operator updates `.status` field to reflect current state (e.g., "Ready", "Progressing", "Failed").
- `patch` is preferred over `update` to avoid conflicts (optimistic concurrency).

**Reference**: [Kubernetes API Conventions - Status](https://github.com/kubernetes/community/blob/master/contributors/devel/sig-architecture/api-conventions.md#spec-and-status)

### 3. Built-in Resources (Children)

The operator creates and manages Kubernetes built-in resources on behalf of Agent CRs:

#### ConfigMaps
**Verbs**: `create`, `get`, `list`, `patch`

```yaml
- apiGroups: [""]
  resources: ["configmaps"]
  verbs: ["create", "get", "list", "patch"]
```

**Why?**
- `create`: Operator creates ConfigMaps to store agent configuration (spec serialized as JSON).
- `get`, `list`: Read existing ConfigMaps to check if they exist and match desired state.
- `patch`: Update ConfigMaps when Agent spec changes (deterministic canonical JSON).

#### PersistentVolumeClaims
**Verbs**: `create`, `get`, `list`, `patch`

```yaml
- apiGroups: [""]
  resources: ["persistentvolumeclaims"]
  verbs: ["create", "get", "list", "patch"]
```

**Why?**
- `create`: Operator creates PVCs for agent workspace storage.
- `patch`: Resize PVCs if storage requirements change (K8s 1.24+ volume expansion).

#### Deployments
**Verbs**: `create`, `get`, `list`, `patch`

```yaml
- apiGroups: ["apps"]
  resources: ["deployments"]
  verbs: ["create", "get", "list", "patch"]
```

**Why?**
- `create`: Operator creates Deployments for agent pods.
- `patch`: Update Deployments when Agent spec changes (image, resources, env vars).

#### NetworkPolicies
**Verbs**: `create`, `get`, `list`, `patch`

```yaml
- apiGroups: ["networking.k8s.io"]
  resources: ["networkpolicies"]
  verbs: ["create", "get", "list", "patch"]
```

**Why?**
- `create`: Operator creates NetworkPolicies for agent isolation (sandbox deny-egress, director allow-egress).
- `patch`: Update NetworkPolicies when agent role changes.

**Reference**: [Kubernetes RBAC - Referring to Resources](https://kubernetes.io/docs/reference/access-authn-authz/rbac/#referring-to-resources)

## ClusterRole vs Role

**Current choice**: `ClusterRole` + `ClusterRoleBinding`

**Why ClusterRole?**
- Custom resources (`agents.universe.ai`, `sessions.universe.ai`) are **cluster-scoped** (not namespaced).
- Operator needs to watch agents across all namespaces (multi-tenant deployment pattern).
- ClusterRole allows single operator deployment to manage resources cluster-wide.

**Alternative**: Role + RoleBinding
- Use if you want to limit operator to a single namespace (smaller blast radius).
- Requires one operator deployment per namespace.
- Not suitable for cluster-scoped CRDs.

**Reference**: [Kubernetes RBAC - Role vs ClusterRole](https://kubernetes.io/docs/reference/access-authn-authz/rbac/#role-and-clusterrole)

## Disabling RBAC

Set `values.rbac.create: false` to skip RBAC resource creation:

```yaml
# values.yaml
rbac:
  create: false
  serviceAccountName: my-custom-sa
```

**Use cases**:
- Cluster admin provides custom RBAC setup.
- Testing with `cluster-admin` privileges (not recommended for production).
- Multi-tenant environments with external RBAC management.

When disabled, ensure the ServiceAccount specified in `serviceAccountName` has equivalent permissions.

## Auditing Permissions

If you see `Forbidden` errors in operator logs, follow these steps:

1. **Check the error message** for the specific resource/verb:
   ```
   Error: Forbidden: User "system:serviceaccount:rynxs:rynxs-operator" cannot patch resource "deployments" in API group "apps"
   ```

2. **Verify ClusterRole** has the permission:
   ```bash
   kubectl describe clusterrole rynxs-rynxs-operator
   ```

3. **Add minimal permission** - only the required verb + resource:
   ```yaml
   - apiGroups: ["apps"]
     resources: ["deployments"]
     verbs: ["patch"]  # Add only patch, not delete/update
   ```

4. **Document the reason** in this file and commit message.

**Never add wildcard permissions** (`*`) to fix Forbidden errors. Always identify the exact resource + verb needed.

## Future Permissions

If additional permissions are needed (e.g., for cleanup, finalizers, status updates), they will be added with:
- **Justification**: Why the permission is needed (feature requirement).
- **Minimal scope**: Exact resource + verb, no wildcards.
- **Documentation**: Update this file with reasoning.

### Examples of Future Additions

**Finalizer cleanup** (if implemented):
```yaml
- apiGroups: ["universe.ai"]
  resources: ["agents"]
  verbs: ["update"]  # Required to remove finalizers
```

**Resource deletion** (if implemented):
```yaml
- apiGroups: ["apps"]
  resources: ["deployments"]
  verbs: ["delete"]  # Required for cascade delete
```

## References

- [Kubernetes RBAC Documentation](https://kubernetes.io/docs/reference/access-authn-authz/rbac/)
- [Kubernetes RBAC Good Practices](https://kubernetes.io/docs/concepts/security/rbac-good-practices/)
- [Kubernetes API Conventions](https://github.com/kubernetes/community/blob/master/contributors/devel/sig-architecture/api-conventions.md)
- [Kopf Framework - RBAC Requirements](https://kopf.readthedocs.io/en/stable/deployment/#rbac)

## Summary Table

| Resource | API Group | Verbs | Reason |
|----------|-----------|-------|--------|
| agents, sessions | universe.ai | get, list, watch, patch | Watch CRs, update metadata |
| agents/status, sessions/status | universe.ai | patch | Update status subresource |
| configmaps | "" (core) | create, get, list, patch | Store agent config |
| persistentvolumeclaims | "" (core) | create, get, list, patch | Agent workspace storage |
| deployments | apps | create, get, list, patch | Agent pod management |
| networkpolicies | networking.k8s.io | create, get, list, patch | Agent isolation |

**Total permissions**: 6 resource types, 4-5 verbs each, **0 wildcards**.
