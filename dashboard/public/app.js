// Rynxs Dashboard - Kubernetes API Integration

const API_BASE = window.location.hostname === 'localhost'
    ? 'http://localhost:8001/apis/universe.ai/v1alpha1'
    : '/apis/universe.ai/v1alpha1';

async function fetchResource(resource) {
    try {
        const response = await fetch(`${API_BASE}/namespaces/universe/${resource}`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return await response.json();
    } catch (error) {
        console.error(`Failed to fetch ${resource}:`, error);
        return { items: [] };
    }
}

async function loadDashboard() {
    const [agents, tasks, teams] = await Promise.all([
        fetchResource('agents'),
        fetchResource('tasks'),
        fetchResource('teams')
    ]);

    updateAgentStats(agents);
    updateTaskStats(tasks);
    updateTeamStats(teams);
    updateTasksTable(tasks);
}

function updateAgentStats(data) {
    const items = data.items || [];
    const active = items.filter(a => a.status?.phase === 'Running').length;

    document.getElementById('total-agents').textContent = items.length;
    document.getElementById('active-agents').textContent = active;
    document.getElementById('idle-agents').textContent = items.length - active;
}

function updateTaskStats(data) {
    const items = data.items || [];
    const completed = items.filter(t => t.status?.phase === 'Completed').length;
    const inProgress = items.filter(t => t.status?.phase === 'InProgress').length;

    document.getElementById('total-tasks').textContent = items.length;
    document.getElementById('completed-tasks').textContent = completed;
    document.getElementById('inprogress-tasks').textContent = inProgress;
}

function updateTeamStats(data) {
    const items = data.items || [];
    const active = items.filter(t => t.status?.phase === 'Active').length;

    document.getElementById('total-teams').textContent = items.length;
    document.getElementById('active-teams').textContent = active;
}

function updateTasksTable(data) {
    const tbody = document.querySelector('#tasks-table tbody');
    const items = (data.items || []).slice(0, 10);

    if (items.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: #7f8c8d;">No tasks found</td></tr>';
        return;
    }

    tbody.innerHTML = items.map(task => {
        const name = task.metadata.name;
        const agent = task.status?.assignedAgent || '-';
        const phase = task.status?.phase || 'Pending';
        const priority = task.spec?.priority || 'normal';

        let statusClass = 'pending';
        if (phase === 'Completed') statusClass = 'active';
        if (phase === 'Failed') statusClass = 'failed';

        return `
            <tr>
                <td>${name}</td>
                <td>${agent}</td>
                <td><span class="status ${statusClass}">${phase}</span></td>
                <td>${priority}</td>
                <td class="actions">
                    <button class="btn btn-primary" onclick="viewTask('${name}')">View</button>
                </td>
            </tr>
        `;
    }).join('');
}

function viewTask(name) {
    alert(`Task details: ${name}\n\nView full details via:\nkubectl get task ${name} -n universe -o yaml`);
}

loadDashboard();
setInterval(loadDashboard, 5000);
