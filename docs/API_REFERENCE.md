# API Reference

This document describes the Custom Resource Definitions (CRDs) in Rynxs.

## Agent CRD

API Group: `universe.ai/v1alpha1`
Kind: `Agent`
Scope: `Namespaced`

### Spec Fields

#### image

Container image configuration for the agent runtime.

```yaml
spec:
  image:
    repository: string  # Container registry and image name
    tag: string         # Image tag
    verify: boolean     # Enable cosign signature verification (default: false)
```

Example:
```yaml
image:
  repository: ghcr.io/your-org/rynxs-agent-runtime
  tag: v1.0.0
  verify: true
```

#### workspace

Persistent storage configuration for agent workspace.

```yaml
spec:
  workspace:
    size: string              # PVC size (default: "1Gi")
    storageClassName: string  # Storage class name (optional)
```

Example:
```yaml
workspace:
  size: "10Gi"
  storageClassName: "fast-ssd"
```

#### universeRef

Reference to parent Universe resource.

```yaml
spec:
  universeRef: string  # Universe name
```

Example:
```yaml
universeRef: u0
```

#### provider

LLM provider configuration (used by runtime).

```yaml
spec:
  provider:
    kind: string           # Provider type: "local", "openai", "anthropic"
    baseUrl: string        # API endpoint
    model: string          # Model name
    apiKeySecretRef: string  # Secret containing API key
```

Example:
```yaml
provider:
  kind: local
  baseUrl: "http://llm-proxy.universe.svc.cluster.local:8080"
  model: "gpt-4"
  apiKeySecretRef: "llm-api-key"
```

#### tools

Tool execution policy.

```yaml
spec:
  tools:
    allow: []string  # Allowed tool names
```

Available tools:
- `fs.read`: Read files from workspace
- `fs.write`: Write files to workspace
- `http.fetch`: HTTP requests (future)
- `sandbox.shell`: Execute shell commands in isolated Job
- `sandbox.browser`: Browser automation (future)

Example:
```yaml
tools:
  allow: ["fs.read", "fs.write", "sandbox.shell"]
```

#### network

Network egress policy.

```yaml
spec:
  network:
    allowEgressTo: []string  # Allowed destination hostnames/IPs
```

Example:
```yaml
network:
  allowEgressTo:
    - "minio.universe.svc.cluster.local"
    - "llm-proxy.universe.svc.cluster.local"
```

#### persona

Agent personality parameters (used by runtime for consciousness model).

```yaml
spec:
  persona:
    coreDominanceAlpha: float       # Core identity strength (0-1)
    personaFlexibilityBeta: float   # Adaptability (0-1)
    personaSeparationGamma: float   # Context separation (0-1)
```

Example:
```yaml
persona:
  coreDominanceAlpha: 0.85
  personaFlexibilityBeta: 0.35
  personaSeparationGamma: 0.25
```

#### cognition

Cognitive parameters (used by runtime for memory and learning).

```yaml
spec:
  cognition:
    recallStrength: float      # Memory recall ability (0-1)
    inferenceStrength: float   # Reasoning capability (0-1)
    learningRate: float        # Knowledge acquisition rate (0-1)
```

Example:
```yaml
cognition:
  recallStrength: 0.7
  inferenceStrength: 0.8
  learningRate: 0.6
```

#### role

Agent role in organizational hierarchy. Default: `worker`.

```yaml
spec:
  role: string  # worker, manager, director
```

Example:
```yaml
role: manager
```

#### team

Team this agent belongs to.

```yaml
spec:
  team: string  # Team name reference
```

Example:
```yaml
team: backend-team
```

#### manages

List of agent names this agent manages (for managers/directors).

```yaml
spec:
  manages:
    - agent-worker-001
    - agent-worker-002
```

#### permissions

Role-based permissions for agent capabilities.

```yaml
spec:
  permissions:
    canAssignTasks: boolean      # Can assign tasks to other agents
    canManageTeam: boolean        # Can manage team members
    canAccessAuditLogs: boolean   # Can access audit logs
```

Example:
```yaml
permissions:
  canAssignTasks: true
  canManageTeam: true
  canAccessAuditLogs: false
```

### Status Fields

#### conditions

Array of condition objects describing agent state.

```yaml
status:
  conditions:
    - type: string              # Condition type
      status: string            # "True", "False", or "Unknown"
      reason: string            # Machine-readable reason
      message: string           # Human-readable message
      lastTransitionTime: string  # ISO 8601 timestamp
```

Condition types:
- `ImageVerified`: Image signature verification result
- `Ready`: Agent is ready to accept tasks
- `Degraded`: Agent is experiencing issues

Example:
```yaml
status:
  conditions:
    - type: ImageVerified
      status: "True"
      reason: VerificationSucceeded
      message: "Image signature is valid and trusted."
      lastTransitionTime: "2024-02-24T10:15:30Z"
```

## Universe CRD

API Group: `universe.ai/v1alpha1`
Kind: `Universe`
Scope: `Cluster`

### Spec Fields

#### storage

Object storage configuration for agent snapshots.

```yaml
spec:
  storage:
    bucket:
      endpoint: string            # S3-compatible endpoint
      bucket: string              # Bucket name
      accessKeySecretRef: string  # Secret containing access key
      secretKeySecretRef: string  # Secret containing secret key
```

Example:
```yaml
storage:
  bucket:
    endpoint: "http://minio.universe.svc.cluster.local:9000"
    bucket: "universe"
    accessKeySecretRef: "minio-access"
    secretKeySecretRef: "minio-secret"
```

#### policies

Universe-level behavior policies.

```yaml
spec:
  policies:
    identityBleedRate: float  # Cross-universe identity transfer rate (0-1)
    macroLuck:
      min: float  # Minimum luck factor (0-1)
      max: float  # Maximum luck factor (0-1)
    physics:
      zonalJitterMin: float          # Minimum per-zone physics drift
      zonalJitterMax: float          # Maximum per-zone physics drift
      globalJitterRareEventRate: float  # Global physics event probability
    sleep:
      instantBackupEverySeconds: int  # Light sleep interval (RAM -> Volume)
      deepSleepEverySeconds: int     # Deep sleep interval (full snapshot)
      deepSleepMinSeconds: int       # Minimum deep sleep duration
```

Example:
```yaml
policies:
  identityBleedRate: 0.0005
  macroLuck: {min: 0.01, max: 0.10}
  physics:
    zonalJitterMin: 0.00001
    zonalJitterMax: 0.0001
    globalJitterRareEventRate: 0.000001
  sleep:
    instantBackupEverySeconds: 30
    deepSleepEverySeconds: 180
    deepSleepMinSeconds: 20
```

#### travel

Cross-universe travel configuration (Phase 3 feature).

```yaml
spec:
  travel:
    enabled: boolean  # Enable travel between universes
    universes:
      - id: string              # Destination universe ID
        zones: []string         # Available zones
        baseDilationLight: int  # Light sleep time dilation factor
        baseDilationDeep: int   # Deep sleep time dilation factor
```

Example:
```yaml
travel:
  enabled: true
  universes:
    - id: U1
      zones: ["family", "work", "friends"]
      baseDilationLight: 2
      baseDilationDeep: 40
```

### Status Fields

Universe status is currently not actively managed by the operator.

## Task CRD

API Group: `universe.ai/v1alpha1`
Kind: `Task`
Scope: `Namespaced`

### Spec Fields

#### title

Short task title (required).

```yaml
spec:
  title: "Q4 Sales Analysis"
```

#### description

Detailed task description (required).

```yaml
spec:
  description: "Analyze Q4 sales data and generate comprehensive report with trends and forecasts"
```

#### assignee

Agent name to assign task to. If not specified, operator auto-assigns.

```yaml
spec:
  assignee: agent-analyst
```

#### priority

Task priority level. Default: `normal`.

```yaml
spec:
  priority: high  # low, normal, high, critical
```

#### deadline

Task deadline in ISO 8601 format.

```yaml
spec:
  deadline: "2024-12-31T23:59:59Z"
```

#### requiredTools

List of tools the agent must have access to.

```yaml
spec:
  requiredTools:
    - "fs.read"
    - "fs.write"
    - "sandbox.shell"
```

#### zone

Zone/department the task belongs to. Used for agent matching.

```yaml
spec:
  zone: "analytics"
```

#### dependencies

List of task names that must complete before this task starts.

```yaml
spec:
  dependencies:
    - data-collection
    - data-cleaning
```

#### input

Structured input data for the task.

```yaml
spec:
  input:
    dataPath: "/workspace/data/sales.csv"
    outputFormat: "pdf"
    metrics:
      - "total_revenue"
      - "growth_rate"
```

### Status Fields

#### phase

Current task phase: `Pending`, `Assigned`, `InProgress`, `Completed`, `Failed`, `Cancelled`.

#### assignedAgent

Agent currently assigned to this task.

#### startTime

When task execution started (ISO 8601).

#### completionTime

When task completed or failed (ISO 8601).

#### attempts

Number of execution attempts.

#### result

Task execution result (arbitrary JSON object).

```yaml
status:
  result:
    total_revenue: 1500000
    growth_rate: 15.3
    report_path: "/workspace/reports/sales-q4.pdf"
```

#### error

Error message if task failed.

```yaml
status:
  error: "Tool execution failed: permission denied"
```

## Team CRD

API Group: `universe.ai/v1alpha1`
Kind: `Team`
Scope: `Namespaced`

### Spec Fields

#### name

Team display name (required).

```yaml
spec:
  name: "Backend Engineering"
```

#### zone

Zone/department this team belongs to (required).

```yaml
spec:
  zone: "engineering"
```

#### lead

Agent name who leads this team.

```yaml
spec:
  lead: "agent-manager-001"
```

#### members

List of agent names in this team.

```yaml
spec:
  members:
    - agent-worker-001
    - agent-worker-002
    - agent-worker-003
```

#### resources

Team shared resources.

```yaml
spec:
  resources:
    sharedWorkspace: string    # Shared PVC name for team collaboration
    sharedKnowledge: string    # Shared knowledge base location
```

Example:
```yaml
resources:
  sharedWorkspace: "backend-pvc"
  sharedKnowledge: "/mnt/knowledge/backend"
```

#### communication

Communication policies.

```yaml
spec:
  communication:
    allowInternalChat: boolean    # Allow team members to communicate
    allowCrossTeam: []string      # Teams this team can communicate with
```

Example:
```yaml
communication:
  allowInternalChat: true
  allowCrossTeam:
    - frontend-team
    - devops-team
```

### Status Fields

#### phase

Team operational status: `Active`, `Inactive`, `Dissolved`.

#### memberCount

Current number of team members.

#### activeMembers

Number of currently active agents.

## Metric CRD

API Group: `universe.ai/v1alpha1`
Kind: `Metric`
Scope: `Namespaced`

### Spec Fields

#### agent

Agent name (required).

```yaml
spec:
  agent: "agent-worker-001"
```

#### period

Reporting period (required). Format: YYYY-QN or YYYY-MM.

```yaml
spec:
  period: "2024-Q1"
```

#### metrics

Performance metrics.

```yaml
spec:
  metrics:
    tasksCompleted: int           # Number of tasks completed
    tasksFailed: int              # Number of tasks failed
    averageCompletionTime: string # Average task completion time
    errorRate: float              # Error rate (0.0-1.0)
    uptime: string                # Agent uptime percentage
    auditScore: float             # Compliance score (0.0-1.0)
```

Example:
```yaml
metrics:
  tasksCompleted: 127
  tasksFailed: 3
  averageCompletionTime: "2h15m"
  errorRate: 0.023
  uptime: "99.8%"
  auditScore: 0.95
```

#### toolUsage

Tool usage count (tool name to count mapping).

```yaml
spec:
  toolUsage:
    kubectl: 450
    python: 320
    git: 280
```

#### zoneContributions

Contribution by zone (zone name to percentage mapping).

```yaml
spec:
  zoneContributions:
    engineering: 0.85
    operations: 0.15
```

## Message CRD

API Group: `universe.ai/v1alpha1`
Kind: `Message`
Scope: `Namespaced`

### Spec Fields

#### from

Sender agent name (required).

```yaml
spec:
  from: "agent-manager-001"
```

#### to

Recipient agent name (optional for broadcasts).

```yaml
spec:
  to: "agent-worker-001"
```

#### channel

Channel/team name for group messages.

```yaml
spec:
  channel: "backend-team"
```

#### content

Message content (required).

```yaml
spec:
  content: "Task assigned: Implement authentication module"
```

#### priority

Message priority level. Default: `normal`.

```yaml
spec:
  priority: high  # low, normal, high, urgent
```

#### thread

Thread ID for conversation grouping.

```yaml
spec:
  thread: "task-123"
```

#### metadata

Additional message metadata.

```yaml
spec:
  metadata:
    taskRef: "task-auth-feature"
    deadline: "2024-03-15T18:00:00Z"
```

### Status Fields

#### delivered

Whether message was delivered.

#### deliveredAt

Delivery timestamp (ISO 8601).

#### read

Whether message was read.

#### readAt

Read timestamp (ISO 8601).

## Session CRD

API Group: `universe.ai/v1alpha1`
Kind: `Session`
Scope: `Namespaced`

Session resources are used for cross-universe travel sessions (Phase 3 feature).

### Spec Fields

```yaml
spec:
  agentRef: string      # Reference to Agent
  sourceUniverse: string  # Origin universe
  targetUniverse: string  # Destination universe
  duration: int         # Session duration in seconds
```

### Status Fields

```yaml
status:
  phase: string        # "Pending", "Active", "Completed", "Failed"
  startTime: string    # ISO 8601 timestamp
  endTime: string      # ISO 8601 timestamp
  bridgeData: object   # Transferred memory data
```

## Labels

Standard labels applied by operator:

- `app: universe-agent`: Agent runtime pods
- `agent: <name>`: Specific agent identifier
- `sandbox-job: <id>`: Sandbox execution Jobs

## Annotations

No custom annotations are currently used.

## RBAC

The operator requires the following permissions:

### Cluster-scoped:
- `universe.ai/agents`: get, list, watch, create, update, patch, delete
- `universe.ai/tasks`: get, list, watch, create, update, patch, delete
- `universe.ai/teams`: get, list, watch, create, update, patch, delete
- `universe.ai/metrics`: get, list, watch, create, update, patch, delete
- `universe.ai/messages`: get, list, watch, create, update, patch, delete
- `universe.ai/sessions`: get, list, watch, create, update, patch, delete
- `universe.ai/universes`: get, list, watch, create, update, patch, delete
- `universe.ai/agents/status`: get, update, patch
- `universe.ai/tasks/status`: get, update, patch
- `universe.ai/teams/status`: get, update, patch

### Namespace-scoped (universe):
- `pods`: get, list, watch, create, delete
- `services`: get, list, watch, create, delete
- `configmaps`: get, list, watch, create, delete
- `persistentvolumeclaims`: get, list, watch, create
- `deployments`: get, list, watch, create, patch, update
- `jobs`: get, list, watch, create, delete
- `events`: get, list, create, patch

## Webhook Validation

Currently no admission webhooks are implemented. Future versions may add:

- Validating webhook for Agent spec validation
- Mutating webhook for default value injection
- Conversion webhook for CRD version migration
