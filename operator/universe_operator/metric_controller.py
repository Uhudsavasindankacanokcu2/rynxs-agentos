import kopf
from kubernetes import client
import re


class MetricController:
    def __init__(self, namespace: str, logger):
        self.namespace = namespace
        self.logger = logger
        self.api = client.CustomObjectsApi()

    def process_metric(self, metric_name: str, spec: dict) -> dict:
        """
        Process and validate metric resource.

        Returns status dict (currently empty, but reserved for future use).
        """
        agent_name = spec.get("agent")
        period = spec.get("period")
        metrics = spec.get("metrics", {})

        if not agent_name:
            self.logger.error(f"Metric {metric_name}: Missing 'agent' field")
            return {}

        if not period:
            self.logger.error(f"Metric {metric_name}: Missing 'period' field")
            return {}

        if not self._agent_exists(agent_name):
            self.logger.warning(f"Metric {metric_name}: Agent {agent_name} does not exist")

        if not self._validate_period_format(period):
            self.logger.warning(f"Metric {metric_name}: Invalid period format '{period}' (expected YYYY-QN or YYYY-MM)")

        self._validate_metrics(metric_name, metrics)
        self._calculate_aggregates(metric_name, agent_name, period, metrics)

        return {}

    def _agent_exists(self, agent_name: str) -> bool:
        """Check if agent exists in namespace."""
        try:
            self.api.get_namespaced_custom_object(
                group="universe.ai",
                version="v1alpha1",
                namespace=self.namespace,
                plural="agents",
                name=agent_name
            )
            return True
        except client.exceptions.ApiException as e:
            if e.status == 404:
                return False
            raise

    def _validate_period_format(self, period: str) -> bool:
        """
        Validate period format.

        Valid formats:
        - YYYY-QN (e.g., 2024-Q1)
        - YYYY-MM (e.g., 2024-01)
        """
        quarterly_pattern = r'^\d{4}-Q[1-4]$'
        monthly_pattern = r'^\d{4}-(0[1-9]|1[0-2])$'

        return bool(re.match(quarterly_pattern, period) or re.match(monthly_pattern, period))

    def _validate_metrics(self, metric_name: str, metrics: dict):
        """Validate metric values."""
        tasks_completed = metrics.get("tasksCompleted")
        tasks_failed = metrics.get("tasksFailed")
        error_rate = metrics.get("errorRate")
        audit_score = metrics.get("auditScore")

        if tasks_completed is not None and tasks_completed < 0:
            self.logger.warning(f"Metric {metric_name}: tasksCompleted cannot be negative")

        if tasks_failed is not None and tasks_failed < 0:
            self.logger.warning(f"Metric {metric_name}: tasksFailed cannot be negative")

        if error_rate is not None:
            if not (0.0 <= error_rate <= 1.0):
                self.logger.warning(f"Metric {metric_name}: errorRate must be between 0.0 and 1.0")

        if audit_score is not None:
            if not (0.0 <= audit_score <= 1.0):
                self.logger.warning(f"Metric {metric_name}: auditScore must be between 0.0 and 1.0")

        if tasks_completed is not None and tasks_failed is not None:
            total = tasks_completed + tasks_failed
            if total > 0 and error_rate is not None:
                calculated_error_rate = tasks_failed / total
                if abs(calculated_error_rate - error_rate) > 0.01:
                    self.logger.warning(
                        f"Metric {metric_name}: errorRate mismatch "
                        f"(specified: {error_rate}, calculated: {calculated_error_rate:.3f})"
                    )

    def _calculate_aggregates(self, metric_name: str, agent_name: str, period: str, metrics: dict):
        """
        Calculate aggregate metrics for team/zone.

        This would aggregate metrics across all agents in a team or zone.
        For now, just log the calculation intent.
        """
        self.logger.debug(
            f"Metric {metric_name}: agent={agent_name} period={period} "
            f"completed={metrics.get('tasksCompleted', 0)} "
            f"failed={metrics.get('tasksFailed', 0)}"
        )

        try:
            agent = self.api.get_namespaced_custom_object(
                group="universe.ai",
                version="v1alpha1",
                namespace=self.namespace,
                plural="agents",
                name=agent_name
            )

            team = agent.get("spec", {}).get("team")
            if team:
                self.logger.debug(f"Metric {metric_name}: Contributing to team {team} metrics")

        except client.exceptions.ApiException:
            pass
