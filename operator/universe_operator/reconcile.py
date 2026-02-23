import json
from kubernetes import client
from .controllers.binding import BindingController

def ensure_agent_runtime(agent_name: str, namespace: str, agent_spec: dict, logger):
    core = client.CoreV1Api()
    apps = client.AppsV1Api()
    
    # Initialize controllers
    binding_ctrl = BindingController(logger)
    
    # Resolve consciousness
    consciousness = binding_ctrl.resolve_consciousness(agent_spec)


    cm_name = f"{agent_name}-spec"
    cm = client.V1ConfigMap(
        metadata=client.V1ObjectMeta(name=cm_name, namespace=namespace),
        data={"agent.json": json.dumps(agent_spec, indent=2)},
    )
    try:
        core.create_namespaced_config_map(namespace, cm)
        logger.info(f"Created ConfigMap {cm_name}")
    except client.exceptions.ApiException as e:
        if e.status != 409:
            raise
        core.patch_namespaced_config_map(cm_name, namespace, cm)

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
        if e.status != 409:
            raise

    dep_name = f"{agent_name}-runtime"
    image = agent_spec.get("runtimeImage", "universe-agent-runtime:dev")

    dep = client.V1Deployment(
        metadata=client.V1ObjectMeta(name=dep_name, namespace=namespace, labels={"app": "universe-agent", "agent": agent_name}),
        spec=client.V1DeploymentSpec(
            replicas=1,
            selector=client.V1LabelSelector(match_labels={"app": "universe-agent", "agent": agent_name}),
            template=client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(labels={"app": "universe-agent", "agent": agent_name}),
                spec=client.V1PodSpec(
                    containers=[
                        client.V1Container(
                            name="runtime",
                            image=image,
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

    # Apply binding to pod spec
    binding_ctrl.apply_binding_to_spec(dep.spec.template.spec, consciousness)

    try:
        apps.create_namespaced_deployment(namespace, dep)

        logger.info(f"Created Deployment {dep_name}")
    except client.exceptions.ApiException as e:
        if e.status != 409:
            raise
        apps.patch_namespaced_deployment(dep_name, namespace, dep)
