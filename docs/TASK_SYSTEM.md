# Task Queue System

The Task system enables work assignment and tracking for AI agents in Rynxs.

## Overview

Tasks are Kubernetes custom resources that define work to be done by agents. The operator automatically assigns tasks to available agents based on requirements and priorities.

## Task Lifecycle

```
Pending → Assigned → InProgress → Completed
                                 → Failed
                                 → Cancelled
```

- **Pending**: Task created, waiting for assignment
- **Assigned**: Task assigned to an agent, written to inbox
- **InProgress**: Agent is actively working on the task
- **Completed**: Task finished successfully
- **Failed**: Task execution failed
- **Cancelled**: Task cancelled by user

## Creating Tasks

### Basic Task

```yaml
apiVersion: universe.ai/v1alpha1
kind: Task
metadata:
  name: simple-task
  namespace: universe
spec:
  title: "Process customer data"
  description: "Extract and transform customer records from CSV"
  priority: normal
```

### Task with Requirements

```yaml
apiVersion: universe.ai/v1alpha1
kind: Task
metadata:
  name: data-analysis
  namespace: universe
spec:
  title: "Sales Data Analysis"
  description: "Analyze Q4 sales data and generate report"
  priority: high
  deadline: "2024-12-31T23:59:59Z"
  requiredTools:
    - "fs.read"
    - "fs.write"
    - "sandbox.shell"
  zone: "analytics"
  input:
    dataPath: "/workspace/data/sales.csv"
    outputFormat: "pdf"
```

### Task with Dependencies

```yaml
apiVersion: universe.ai/v1alpha1
kind: Task
metadata:
  name: generate-report
  namespace: universe
spec:
  title: "Generate Monthly Report"
  description: "Compile data from all analysis tasks"
  dependencies:
    - data-collection
    - data-cleaning
    - data-analysis
  priority: normal
```

### Manual Assignment

```yaml
apiVersion: universe.ai/v1alpha1
kind: Task
metadata:
  name: urgent-fix
  namespace: universe
spec:
  title: "Fix Critical Bug"
  description: "Debug and fix production issue"
  assignee: agent-senior-dev
  priority: critical
```

## Priority Levels

- **low**: Background tasks, batch processing
- **normal**: Standard operations (default)
- **high**: Important tasks, deadline-driven
- **critical**: Urgent issues, production problems

## Task Assignment

### Automatic Assignment

The operator automatically assigns tasks based on:
1. Agent availability (pod running)
2. Required tools (agent has access)
3. Zone preference (agent in specified zone)
4. Priority (higher priority tasks first)

### Assignment Algorithm

```python
for each task in pending_tasks:
    if task.dependencies_met():
        agent = find_agent(
            tools=task.required_tools,
            zone=task.zone,
            available=True
        )
        if agent:
            assign(task, agent)
```

## Monitoring Tasks

### List Tasks

```bash
kubectl get tasks -n universe
```

Output:
```
NAME              STATUS      AGENT            PRIORITY   AGE
data-analysis     Completed   agent-analyst    high       2h
report-gen        InProgress  agent-writer     normal     1h
cleanup           Pending                      low        5m
```

### Describe Task

```bash
kubectl describe task data-analysis -n universe
```

### Watch Task Status

```bash
kubectl get task data-analysis -n universe -w
```

### View Task Result

```bash
kubectl get task data-analysis -n universe -o jsonpath='{.status.result}'
```

## Task Failures

When a task fails, the status includes error details:

```yaml
status:
  phase: Failed
  assignedAgent: agent-worker-1
  attempts: 3
  error: "Tool execution failed: fs.read permission denied"
  completionTime: "2024-02-24T15:30:00Z"
```

### Retry Failed Tasks

Delete and recreate the task:

```bash
kubectl delete task failed-task -n universe
kubectl apply -f task.yaml
```

## Task Cancellation

Cancel a running task:

```bash
kubectl patch task running-task -n universe --type=merge -p '{"status":{"phase":"Cancelled"}}'
```

## Best Practices

### Task Design

- Keep tasks atomic and focused
- Use clear, descriptive titles
- Provide detailed descriptions
- Specify all required tools
- Set realistic deadlines
- Include structured input data

### Dependency Management

- Avoid circular dependencies
- Keep dependency chains short
- Use task names consistently
- Verify dependencies exist before creating tasks

### Priority Management

- Reserve critical for true emergencies
- Use high for deadline-driven work
- Default to normal for standard operations
- Use low for background processing

### Input Data

Structure input data for clarity:

```yaml
spec:
  input:
    source:
      type: "file"
      path: "/workspace/data/input.csv"
    config:
      delimiter: ","
      encoding: "utf-8"
    output:
      format: "json"
      path: "/workspace/results/output.json"
```

## Integration with Agents

### Agent Inbox

Tasks are written to agent inbox.jsonl:

```json
{
  "task_id": "data-analysis",
  "title": "Sales Data Analysis",
  "text": "Analyze Q4 sales data and generate report",
  "priority": "high",
  "deadline": "2024-12-31T23:59:59Z",
  "input": {
    "dataPath": "/workspace/data/sales.csv"
  }
}
```

### Agent Processing

Agents read inbox, process tasks, write results to outbox.jsonl:

```json
{
  "task_id": "data-analysis",
  "status": "completed",
  "result": {
    "total_revenue": 1500000,
    "growth_rate": 15.3,
    "report_path": "/workspace/reports/sales-q4.pdf"
  }
}
```

### Result Tracking

The operator watches agent outbox and updates task status based on results.

## Advanced Usage

### Bulk Task Creation

```bash
for i in {1..10}; do
  cat <<EOF | kubectl apply -f -
apiVersion: universe.ai/v1alpha1
kind: Task
metadata:
  name: batch-task-$i
  namespace: universe
spec:
  title: "Batch Task $i"
  description: "Process batch $i"
  priority: low
EOF
done
```

### Task Templates

Create reusable task templates:

```yaml
apiVersion: universe.ai/v1alpha1
kind: Task
metadata:
  name: data-processing-template
  namespace: universe
spec:
  title: "Data Processing"
  description: "Process data file"
  requiredTools: ["fs.read", "fs.write"]
  zone: "data-engineering"
  input:
    source: "${DATA_PATH}"
    output: "${OUTPUT_PATH}"
```

### Programmatic Task Creation

Using kubectl:

```bash
kubectl create -f - <<EOF
apiVersion: universe.ai/v1alpha1
kind: Task
metadata:
  name: dynamic-task-$(date +%s)
  namespace: universe
spec:
  title: "Dynamic Task"
  description: "Created programmatically"
  priority: normal
EOF
```

## Troubleshooting

### Task Stuck in Pending

Possible causes:
- No agents available
- Agent lacks required tools
- Dependencies not met
- Zone has no agents

Check:
```bash
kubectl get agents -n universe
kubectl describe task stuck-task -n universe
```

### Task Assigned but Not Starting

Check agent pod:
```bash
kubectl logs -n universe -l app=universe-agent
```

Verify inbox write:
```bash
kubectl exec -n universe agent-pod -- cat /workspace/inbox.jsonl
```

### High Task Failure Rate

Review agent logs and task error messages:
```bash
kubectl get tasks -n universe --field-selector status.phase=Failed
```

## Future Enhancements

Planned features:
- Task retry policies
- Task timeout enforcement
- Agent workload balancing
- Task scheduling (cron-like)
- Task result webhooks
- Task priority queues
