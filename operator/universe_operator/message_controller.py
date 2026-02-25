import kopf
from kubernetes import client
from datetime import datetime


class MessageController:
    def __init__(self, namespace: str, logger):
        self.namespace = namespace
        self.logger = logger
        self.api = client.CustomObjectsApi()

    def process_message(self, message_name: str, spec: dict) -> dict:
        """
        Process message delivery.

        Returns status dict to be updated.
        """
        status = {
            "delivered": False,
            "deliveredAt": None,
            "read": False,
            "readAt": None
        }

        from_agent = spec.get("from")
        to_agent = spec.get("to")
        channel = spec.get("channel")
        content = spec.get("content", "")

        if not from_agent:
            self.logger.error(f"Message {message_name}: Missing 'from' field")
            return status

        if not self._agent_exists(from_agent):
            self.logger.warning(f"Message {message_name}: Sender agent {from_agent} does not exist")
            return status

        if to_agent:
            if not self._agent_exists(to_agent):
                self.logger.warning(f"Message {message_name}: Recipient agent {to_agent} does not exist")
                return status

            delivered = self._deliver_to_agent(to_agent, message_name, spec)
            if delivered:
                status["delivered"] = True
                status["deliveredAt"] = datetime.utcnow().isoformat() + "Z"

        elif channel:
            delivered = self._deliver_to_channel(channel, message_name, spec)
            if delivered:
                status["delivered"] = True
                status["deliveredAt"] = datetime.utcnow().isoformat() + "Z"
        else:
            self.logger.warning(f"Message {message_name}: No recipient (to/channel) specified")

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

    def _deliver_to_agent(self, agent_name: str, message_name: str, spec: dict) -> bool:
        """
        Deliver message to agent inbox.

        In production, this would write to agent's workspace PVC or message queue.
        For now, just log the delivery.
        """
        self.logger.info(f"Delivering message {message_name} to agent {agent_name}")

        try:
            agent = self.api.get_namespaced_custom_object(
                group="universe.ai",
                version="v1alpha1",
                namespace=self.namespace,
                plural="agents",
                name=agent_name
            )

            self.logger.debug(
                f"Message delivery: from={spec.get('from')} "
                f"to={agent_name} priority={spec.get('priority', 'normal')} "
                f"content_length={len(spec.get('content', ''))}"
            )

            return True
        except Exception as e:
            self.logger.error(f"Failed to deliver message to {agent_name}: {e}")
            return False

    def _deliver_to_channel(self, channel: str, message_name: str, spec: dict) -> bool:
        """
        Deliver message to channel (broadcast to team).

        Find all agents in the team and deliver to each.
        """
        self.logger.info(f"Broadcasting message {message_name} to channel {channel}")

        try:
            teams = self.api.list_namespaced_custom_object(
                group="universe.ai",
                version="v1alpha1",
                namespace=self.namespace,
                plural="teams"
            )

            target_team = None
            for team in teams.get("items", []):
                if team.get("metadata", {}).get("name") == channel:
                    target_team = team
                    break

            if not target_team:
                self.logger.warning(f"Channel/team {channel} not found")
                return False

            members = target_team.get("spec", {}).get("members", [])
            delivered_count = 0

            for member in members:
                if self._deliver_to_agent(member, message_name, spec):
                    delivered_count += 1

            self.logger.info(f"Broadcast to {channel}: delivered to {delivered_count}/{len(members)} members")
            return delivered_count > 0

        except Exception as e:
            self.logger.error(f"Failed to broadcast to channel {channel}: {e}")
            return False
