import kopf
from kubernetes import client


class TeamController:
    def __init__(self, namespace: str, logger):
        self.namespace = namespace
        self.logger = logger
        self.api = client.CustomObjectsApi()
        self.core_api = client.CoreV1Api()

    def reconcile_team(self, team_name: str, spec: dict) -> dict:
        """
        Reconcile team resource.

        Returns status dict to be updated.
        """
        status = {
            "memberCount": 0,
            "activeMembers": 0,
            "phase": "Active"
        }

        members = spec.get("members", [])
        lead = spec.get("lead")

        if lead:
            if not self._agent_exists(lead):
                self.logger.warning(f"Team {team_name}: Lead agent {lead} does not exist")
                status["phase"] = "Inactive"

        valid_members = []
        active_count = 0

        for member in members:
            if self._agent_exists(member):
                valid_members.append(member)
                if self._is_agent_active(member):
                    active_count += 1
            else:
                self.logger.warning(f"Team {team_name}: Member agent {member} does not exist")

        status["memberCount"] = len(valid_members)
        status["activeMembers"] = active_count

        if status["memberCount"] == 0 and members:
            status["phase"] = "Inactive"

        shared_workspace = spec.get("resources", {}).get("sharedWorkspace")
        if shared_workspace:
            self._ensure_shared_pvc(shared_workspace, team_name)

        return status

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

    def _is_agent_active(self, agent_name: str) -> bool:
        """Check if agent is in Running state."""
        try:
            agent = self.api.get_namespaced_custom_object(
                group="universe.ai",
                version="v1alpha1",
                namespace=self.namespace,
                plural="agents",
                name=agent_name
            )
            phase = agent.get("status", {}).get("phase", "")
            return phase == "Running"
        except client.exceptions.ApiException:
            return False

    def _ensure_shared_pvc(self, pvc_name: str, team_name: str):
        """Ensure shared workspace PVC exists."""
        try:
            self.core_api.read_namespaced_persistent_volume_claim(
                name=pvc_name,
                namespace=self.namespace
            )
            self.logger.debug(f"PVC {pvc_name} already exists for team {team_name}")
        except client.exceptions.ApiException as e:
            if e.status == 404:
                self.logger.info(f"Creating shared PVC {pvc_name} for team {team_name}")
                pvc = client.V1PersistentVolumeClaim(
                    metadata=client.V1ObjectMeta(
                        name=pvc_name,
                        namespace=self.namespace,
                        labels={"team": team_name, "app": "universe-team"}
                    ),
                    spec=client.V1PersistentVolumeClaimSpec(
                        access_modes=["ReadWriteMany"],
                        resources=client.V1ResourceRequirements(
                            requests={"storage": "10Gi"}
                        )
                    )
                )
                try:
                    self.core_api.create_namespaced_persistent_volume_claim(
                        namespace=self.namespace,
                        body=pvc
                    )
                except client.exceptions.ApiException as create_error:
                    self.logger.error(f"Failed to create PVC {pvc_name}: {create_error}")
            else:
                raise
