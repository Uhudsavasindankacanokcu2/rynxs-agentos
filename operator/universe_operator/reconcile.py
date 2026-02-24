
import json
import subprocess
from datetime import datetime, timezone
from kubernetes import client

from .controllers.binding import BindingController

def update_agent_status(namespace, agent_name, condition, logger):
    """Updates the status of an Agent custom resource."""
    custom_api = client.CustomObjectsApi()
    
    # Ensure lastTransitionTime is set
    if "lastTransitionTime" not in condition:
        condition["lastTransitionTime"] = datetime.now(timezone.utc).isoformat()

    status_patch = {
        "status": {
            "conditions": [condition]
        }
    }
    
    try:
        custom_api.patch_namespaced_custom_object_status(
            group="universe.ai",
            version="v1alpha1",
            name=agent_name,
            namespace=namespace,
            plural="agents",
            body=status_patch,
        )
        logger.info(f"Patched status for Agent {namespace}/{agent_name} with condition {condition['type']}: {condition['status']}")
    except client.exceptions.ApiException as e:
        logger.error(f"Failed to patch agent status for {namespace}/{agent_name}: {e}")

def verify_image_signature(image_uri, logger):
    """Verifies the image signature using cosign."""
    # In a real-world scenario, the public key should be managed securely,
    # for example, via a ConfigMap mounted into the operator.
    cosign_pub_key = "/etc/cosign/cosign.pub"
    command = ["cosign", "verify", "--key", cosign_pub_key, image_uri]
    
    logger.info(f"Running image verification: {' '.join(command)}")
    try:
        # The COSIGN_EXPERIMENTAL=1 env var might be needed for keyless, but we use a key.
        result = subprocess.run(command, capture_output=True, text=True, check=True, env={"COSIGN_EXPERIMENTAL": "1"})
        logger.info(f"Image {image_uri} verified successfully.")
        logger.debug(f"Cosign output: {result.stderr}")
        return True, "VerificationSucceeded", "Image signature is valid and trusted."
    except FileNotFoundError:
        logger.error("`cosign` binary not found. Please ensure it is installed in the operator's container.")
        return False, "VerificationFailed", "`cosign` binary not found in operator container."
    except subprocess.CalledProcessError as e:
        error_message = e.stderr.strip().split('\n')[-1] # Get the most relevant error line
        logger.error(f"Image verification failed for {image_uri}: {error_message}")
        return False, "VerificationFailed", error_message

def ensure_agent_runtime(agent_name: str, namespace: str, agent_spec: dict, logger):
    core = client.CoreV1Api()
    apps = client.AppsV1Api()
    
    binding_ctrl = BindingController(logger)
    consciousness = binding_ctrl.resolve_consciousness(agent_spec)

    # --- Image Verification Logic ---
    image_spec = agent_spec.get("image", {})
    should_verify = image_spec.get("verify", False)
    image_repo = image_spec.get("repository", "rynxs/universal-agent-runtime")
    image_tag = image_spec.get("tag", "latest")
    image = f"{image_repo}:{image_tag}"

    if should_verify:
        logger.info(f"Image signature verification is enabled for {image}")
        is_verified, reason, message = verify_image_signature(image, logger)
        
        condition = {
            "type": "ImageVerified",
            "status": "True" if is_verified else "False",
            "reason": reason,
            "message": message,
        }
        update_agent_status(namespace, agent_name, condition, logger)

        if not is_verified:
            logger.error(f"Halting reconciliation for agent {agent_name} due to image verification failure.")
            return  # Stop processing

    # --- ConfigMap for Agent Spec ---
    cm_name = f"{agent_name}-spec"
    cm = client.V1ConfigMap(
        metadata=client.V1ObjectMeta(name=cm_name, namespace=namespace),
        data={"agent.json": json.dumps(agent_spec, indent=2)},
    )
    try:
        core.create_namespaced_config_map(namespace, cm)
        logger.info(f"Created ConfigMap {cm_name}")
    except client.exceptions.ApiException as e:
        if e.status != 409: raise
        core.patch_namespaced_config_map(cm_name, namespace, cm)

    # --- PVC for Workspace ---
    pvc_name = f"{agent_name}-workspace"
    size = agent_spec.get("workspace", {}).get("size", "1Gi")
    pvc = client.V1PersistentVolumeClaim(
        metadata=client.V1ObjectMeta(name=pvc_name, namespace=namespace),
        spec=client.V1PersistentVolumeClaimSpec(
            access_modes=["ReadWriteOnce"],
            resources=client.V1ResourceRequirements(requests={"storage": size})
        )
    )
    try:
        core.create_namespaced_persistent_volume_claim(namespace, pvc)
        logger.info(f"Created PVC {pvc_name}")
    except client.exceptions.ApiException as e:
        if e.status != 409: raise

    # --- Deployment for Agent Runtime ---
    dep_name = f"{agent_name}-runtime"
    dep = client.V1Deployment(
        metadata=client.V1ObjectMeta(name=dep_name, namespace=namespace, labels={"app": "universe-agent", "agent": agent_name}),
        spec=client.V1DeploymentSpec(
            replicas=1,
            selector=client.V1LabelSelector(match_labels={"app": "universe-agent", "agent": agent_name}),
            template=client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(labels={"app": "universe-agent", "agent": agent_name}),
                spec=client.V1PodSpec(
                    runtime_class_name="gvisor",
                    containers=[
                        client.V1Container(
                            name="runtime",
                            image=image, # Use the verified or unverified image
                            env=[
                                client.V1EnvVar(name="AGENT_NAME", value=agent_name),
                                client.V1EnvVar(name="AGENT_NAMESPACE", value=namespace),
                            ],
                            volume_mounts=[
                                client.V1VolumeMount(name="workspace", mount_path="/workspace"),
                                client.V1VolumeMount(name="agent-spec", mount_path="/config", read_only=True),
                            ],
                            security_context=client.V1SecurityContext(
                                run_as_non_root=True,
                                read_only_root_filesystem=True,
                                allow_privilege_escalation=False,
                                capabilities=client.V1Capabilities(drop=["ALL"]),
                            ),
                        )
                    ],
                    volumes=[
                        client.V1Volume(name="workspace", persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(claim_name=pvc_name)),
                        client.V1Volume(name="agent-spec", config_map=client.V1ConfigMapVolumeSource(name=cm_name)),
                    ],
                )
            )
        )
    )

    binding_ctrl.apply_binding_to_spec(dep.spec.template.spec, consciousness)

    try:
        apps.create_namespaced_deployment(namespace, dep)
        logger.info(f"Created Deployment {dep_name}")
    except client.exceptions.ApiException as e:
        if e.status != 409: raise
        apps.patch_namespaced_deployment(dep_name, namespace, dep)
