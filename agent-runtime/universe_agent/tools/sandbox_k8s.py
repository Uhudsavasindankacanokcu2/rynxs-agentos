import uuid
import time
from kubernetes import client, config

class SandboxK8s:
    def __init__(self, namespace: str):
        self.namespace = namespace
        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()
        self.batch = client.BatchV1Api()
        self.core = client.CoreV1Api()

    def run_shell(self, cmd: str):
        job_name = f"sandbox-shell-{uuid.uuid4().hex[:8]}"
        
        container = client.V1Container(
            name="shell",
            image="alpine",
            command=["sh", "-c", cmd],
        )
        
        template = client.V1PodTemplateSpec(
            metadata=client.V1ObjectMeta(labels={"app": "sandbox-shell"}),
            spec=client.V1PodSpec(restart_policy="Never", containers=[container])
        )
        
        spec = client.V1JobSpec(
            template=template, 
            backoff_limit=0,
            ttl_seconds_after_finished=3600
        )
        job = client.V1Job(
            api_version="batch/v1",
            kind="Job",
            metadata=client.V1ObjectMeta(name=job_name),
            spec=spec
        )
        
        self.batch.create_namespaced_job(namespace=self.namespace, body=job)
        
        # Wait for pod to finish (wait for at most 30s)
        pod_name = None
        for _ in range(30):
            pods = self.core.list_namespaced_pod(self.namespace, label_selector=f"job-name={job_name}")
            if pods.items:
                pod_name = pods.items[0].metadata.name
                if pods.items[0].status.phase in ["Succeeded", "Failed"]:
                    break
            time.sleep(1)
        
        if not pod_name:
            return job_name, ""

        return job_name, (self.core.read_namespaced_pod_log(pod_name, self.namespace) or "")
