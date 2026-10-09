import kopf
from kubernetes import client, config
from kubernetes.client.rest import ApiException


config.load_incluster_config()

apps_api = client.AppsV1Api()
core_api = client.CoreV1Api()


GROUP = "otus.homework"
VERSION = "v1"
PLURAL = "mysqls"


def resource_name(name):
    return name


def create_deployment(name, namespace, spec):
    deployment = client.V1Deployment(
        metadata=client.V1ObjectMeta(
            name=name,
            namespace=namespace,
        ),
        spec=client.V1DeploymentSpec(
            replicas=1,
            selector=client.V1LabelSelector(
                match_labels={"app": name}
            ),
            template=client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(
                    labels={"app": name}
                ),
                spec=client.V1PodSpec(
                    containers=[
                        client.V1Container(
                            name="mysql",
                            image=spec["image"],
                            ports=[
                                client.V1ContainerPort(
                                    container_port=3306
                                )
                            ],
                            env=[
                                client.V1EnvVar(
                                    name="MYSQL_ROOT_PASSWORD",
                                    value=spec["password"],
                                ),
                                client.V1EnvVar(
                                    name="MYSQL_DATABASE",
                                    value=spec["database"],
                                ),
                            ],
                            volume_mounts=[
                                client.V1VolumeMount(
                                    name="mysql-data",
                                    mount_path="/var/lib/mysql",
                                )
                            ],
                        )
                    ],
                    volumes=[
                        client.V1Volume(
                            name="mysql-data",
                            persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                                claim_name=f"{name}-pvc",
                            ),
                        )
                    ],
                ),
            ),
        ),
    )

    apps_api.create_namespaced_deployment(
        namespace=namespace,
        body=deployment,
    )

def create_service(name, namespace):
    service = client.V1Service(
        metadata=client.V1ObjectMeta(
            name=name,
            namespace=namespace,
        ),
        spec=client.V1ServiceSpec(
            type="ClusterIP",
            selector={"app": name},
            ports=[
                client.V1ServicePort(
                    port=3306,
                    target_port=3306,
                )
            ],
        ),
    )

    core_api.create_namespaced_service(
        namespace=namespace,
        body=service,
    )


def create_pv(name, storage_size):
    pv_name = f"{name}-pv"

    pv = client.V1PersistentVolume(
        metadata=client.V1ObjectMeta(
            name=pv_name,
            labels={
                "pv-usage": name,
            },
        ),
        spec=client.V1PersistentVolumeSpec(
            capacity={
                "storage": storage_size,
            },
            access_modes=["ReadWriteOnce"],
            persistent_volume_reclaim_policy="Delete",
            storage_class_name="standard",
            host_path=client.V1HostPathVolumeSource(
                path=f"/tmp/hostpath_pv/{pv_name}",
            ),
        ),
    )

    core_api.create_persistent_volume(body=pv)


def create_pvc(name, namespace, storage_size):
    pvc_name = f"{name}-pvc"

    pvc = client.V1PersistentVolumeClaim(
        metadata=client.V1ObjectMeta(
            name=pvc_name,
            namespace=namespace,
        ),
        spec=client.V1PersistentVolumeClaimSpec(
            access_modes=["ReadWriteOnce"],
            storage_class_name="standard",
            resources=client.V1ResourceRequirements(
                requests={
                    "storage": storage_size,
                }
            ),
            volume_name=f"{name}-pv",
        ),
    )

    core_api.create_namespaced_persistent_volume_claim(
        namespace=namespace,
        body=pvc,
    )


@kopf.on.create(GROUP, VERSION, PLURAL)
def mysql_on_create(spec, name, namespace, **kwargs):
    storage_size = spec["storage_size"]

    create_pv(
        name=name,
        storage_size=storage_size,
    )

    create_pvc(
        name=name,
        namespace=namespace,
        storage_size=storage_size,
    )

    create_service(
        name=name,
        namespace=namespace,
    )

    create_deployment(
        name=name,
        namespace=namespace,
        spec=spec,
    )

    return {
        "message": "MySQL resources created",
        "deployment": name,
        "service": name,
        "pvc": f"{name}-pvc",
        "pv": f"{name}-pv",
    }


@kopf.on.delete(GROUP, VERSION, PLURAL)
def mysql_on_delete(name, namespace, **kwargs):
    try:
        apps_api.delete_namespaced_deployment(
            name=name,
            namespace=namespace,
        )
    except ApiException as e:
        if e.status != 404:
            raise

    try:
        core_api.delete_namespaced_service(
            name=name,
            namespace=namespace,
        )
    except ApiException as e:
        if e.status != 404:
            raise

    try:
        core_api.delete_namespaced_persistent_volume_claim(
            name=f"{name}-pvc",
            namespace=namespace,
        )
    except ApiException as e:
        if e.status != 404:
            raise

    try:
        core_api.delete_persistent_volume(
            name=f"{name}-pv",
        )
    except ApiException as e:
        if e.status != 404:
            raise

    return {
        "message": "MySQL resources deleted",
    }
