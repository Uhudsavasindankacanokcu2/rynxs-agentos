"""Task controller for task assignment and execution tracking."""

import json
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional
from kubernetes import client


class TaskController:
    """Manages task assignment and lifecycle."""

    def __init__(self, namespace: str, logger):
        self.namespace = namespace
        self.logger = logger
        self.core_api = client.CoreV1Api()
        self.custom_api = client.CustomObjectsApi()
        self.apps_api = client.AppsV1Api()

    def find_available_agent(
        self,
        required_tools: List[str],
        zone: Optional[str] = None
    ) -> Optional[str]:
        """Find an agent that meets task requirements.

        Args:
            required_tools: Tools the agent must have access to
            zone: Preferred zone for the agent

        Returns:
            Agent name if found, None otherwise
        """
        try:
            agents = self.custom_api.list_namespaced_custom_object(
                group="universe.ai",
                version="v1alpha1",
                namespace=self.namespace,
                plural="agents"
            )

            for agent in agents.get("items", []):
                agent_name = agent["metadata"]["name"]
                spec = agent.get("spec", {})

                allowed_tools = set(spec.get("tools", {}).get("allow", []))
                if not all(tool in allowed_tools for tool in required_tools):
                    continue

                if zone:
                    agent_zone = spec.get("zone")
                    if agent_zone != zone:
                        continue

                pod = self._get_agent_pod(agent_name)
                if pod and pod.status.phase == "Running":
                    return agent_name

            return None

        except client.exceptions.ApiException as e:
            self.logger.error(f"Failed to list agents: {e}")
            return None

    def _get_agent_pod(self, agent_name: str) -> Optional[client.V1Pod]:
        """Get the running pod for an agent.

        Args:
            agent_name: Name of the agent

        Returns:
            Pod object if found and running, None otherwise
        """
        try:
            pods = self.core_api.list_namespaced_pod(
                namespace=self.namespace,
                label_selector=f"app=universe-agent,agent={agent_name}"
            )

            for pod in pods.items:
                if pod.status.phase == "Running":
                    return pod

            return None

        except client.exceptions.ApiException as e:
            self.logger.error(f"Failed to get agent pod: {e}")
            return None

    def assign_task(self, task_name: str, spec: Dict) -> bool:
        """Assign task to an agent.

        Args:
            task_name: Name of the task
            spec: Task specification

        Returns:
            True if assignment successful, False otherwise
        """
        assignee = spec.get("assignee")
        if not assignee:
            assignee = self.find_available_agent(
                required_tools=spec.get("requiredTools", []),
                zone=spec.get("zone")
            )

            if not assignee:
                self.logger.warning(f"No available agent for task {task_name}")
                self._update_task_status(
                    task_name,
                    phase="Pending",
                    error="No available agent found"
                )
                return False

        success = self._write_to_agent_inbox(assignee, task_name, spec)
        if success:
            self._update_task_status(
                task_name,
                phase="Assigned",
                assigned_agent=assignee,
                start_time=datetime.now(timezone.utc).isoformat()
            )
            self.logger.info(f"Task {task_name} assigned to {assignee}")
            return True

        return False

    def _write_to_agent_inbox(
        self,
        agent_name: str,
        task_name: str,
        spec: Dict
    ) -> bool:
        """Write task to agent's inbox.jsonl file.

        Args:
            agent_name: Name of the agent
            task_name: Name of the task
            spec: Task specification

        Returns:
            True if write successful, False otherwise
        """
        pod = self._get_agent_pod(agent_name)
        if not pod:
            self.logger.error(f"Agent {agent_name} pod not running")
            return False

        inbox_entry = {
            "task_id": task_name,
            "title": spec.get("title"),
            "text": spec.get("description"),
            "priority": spec.get("priority", "normal"),
            "deadline": spec.get("deadline"),
            "input": spec.get("input", {})
        }

        try:
            exec_command = [
                "sh",
                "-c",
                f"echo '{json.dumps(inbox_entry)}' >> /workspace/inbox.jsonl"
            ]

            response = client.stream(
                self.core_api.connect_get_namespaced_pod_exec,
                pod.metadata.name,
                self.namespace,
                command=exec_command,
                stderr=True,
                stdin=False,
                stdout=True,
                tty=False
            )

            self.logger.debug(f"Wrote task {task_name} to {agent_name} inbox")
            return True

        except client.exceptions.ApiException as e:
            self.logger.error(f"Failed to write to inbox: {e}")
            return False

    def _update_task_status(
        self,
        task_name: str,
        phase: Optional[str] = None,
        assigned_agent: Optional[str] = None,
        start_time: Optional[str] = None,
        completion_time: Optional[str] = None,
        result: Optional[Dict] = None,
        error: Optional[str] = None
    ):
        """Update task status.

        Args:
            task_name: Name of the task
            phase: New phase
            assigned_agent: Agent assigned to task
            start_time: Task start time
            completion_time: Task completion time
            result: Task result
            error: Error message
        """
        status_update = {"status": {}}

        if phase:
            status_update["status"]["phase"] = phase
        if assigned_agent:
            status_update["status"]["assignedAgent"] = assigned_agent
        if start_time:
            status_update["status"]["startTime"] = start_time
        if completion_time:
            status_update["status"]["completionTime"] = completion_time
        if result:
            status_update["status"]["result"] = result
        if error:
            status_update["status"]["error"] = error

        try:
            self.custom_api.patch_namespaced_custom_object_status(
                group="universe.ai",
                version="v1alpha1",
                namespace=self.namespace,
                plural="tasks",
                name=task_name,
                body=status_update
            )
            self.logger.info(f"Updated task {task_name} status: {phase}")
        except client.exceptions.ApiException as e:
            self.logger.error(f"Failed to update task status: {e}")

    def check_dependencies(self, task_name: str, dependencies: List[str]) -> bool:
        """Check if all task dependencies are completed.

        Args:
            task_name: Name of the task
            dependencies: List of dependency task names

        Returns:
            True if all dependencies completed, False otherwise
        """
        if not dependencies:
            return True

        try:
            for dep_name in dependencies:
                dep_task = self.custom_api.get_namespaced_custom_object(
                    group="universe.ai",
                    version="v1alpha1",
                    namespace=self.namespace,
                    plural="tasks",
                    name=dep_name
                )

                phase = dep_task.get("status", {}).get("phase")
                if phase != "Completed":
                    self.logger.debug(
                        f"Task {task_name} waiting for dependency {dep_name} "
                        f"(status: {phase})"
                    )
                    return False

            return True

        except client.exceptions.ApiException as e:
            self.logger.error(f"Failed to check dependencies: {e}")
            return False
