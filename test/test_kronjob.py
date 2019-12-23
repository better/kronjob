import kronjob

from kubernetes.client import models as k8s_models
import pytest
import yaml


def test_single_cronjob():
    abstract_jobs = {
        'image': 'example.com/base',
        'schedule': '* * * * *',
        'jobs': [{'name': 'test'}]
    }
    k8s_objects = kronjob.build_k8s_objects(abstract_jobs)
    assert len(k8s_objects) == 1
    assert isinstance(k8s_objects[0], k8s_models.V1beta1CronJob)


def test_single_job():
    abstract_jobs = {
        'image': 'example.com/base',
        'schedule': 'once',
        'jobs': [{'name': 'test'}]
    }
    k8s_objects = kronjob.build_k8s_objects(abstract_jobs)
    assert len(k8s_objects) == 1
    assert isinstance(k8s_objects[0], k8s_models.V1Job)


def test_top_level_job():
    abstract_jobs = {
        'image': 'example.com/base',
        'schedule': 'once',
        'name': 'once'
    }
    k8s_objects = kronjob.build_k8s_objects(abstract_jobs)
    assert len(k8s_objects) == 1
    assert isinstance(k8s_objects[0], k8s_models.V1Job)
    assert k8s_objects[0].metadata.name == 'once'


def test_multiple():
    abstract_jobs = {
        'image': 'example.com/base',
        'jobs': [
            {'name': 'once', 'schedule': 'once'},
            {'name': 'recurring', 'schedule': '* * * * *'}
        ]
    }
    k8s_objects = kronjob.build_k8s_objects(abstract_jobs)
    assert len(k8s_objects) == 2
    assert isinstance(k8s_objects[0], k8s_models.V1Job)
    assert isinstance(k8s_objects[1], k8s_models.V1beta1CronJob)


def test_missing_schedule():
    abstract_jobs = {
        'image': 'example.com/base',
        'jobs': [{'name': 'test'}]
    }
    with pytest.raises(Exception):
        kronjob.build_k8s_objects(abstract_jobs)


def test_property_overrides():
    abstract_jobs = {
        'image': 'example.com/base',
        'jobs': [
            {'name': 'once', 'schedule': 'once'},
            {'name': 'recurring', 'schedule': '* * * * *', 'image': 'example.com/base:v2'}
        ]
    }
    k8s_objects = kronjob.build_k8s_objects(abstract_jobs)
    assert len(k8s_objects) == 2
    assert k8s_objects[0].spec.template.spec.containers[0].image == 'example.com/base'
    assert k8s_objects[1].spec.job_template.spec.template.spec.containers[0].image == 'example.com/base:v2'


def test_name_concatenation():
    abstract_jobs = {
        'image': 'example.com/base',
        'name': 'parent',
        'schedule': 'once',
        'jobs': [{'name': 'child'}]
    }
    k8s_objects = kronjob.build_k8s_objects(abstract_jobs)
    assert len(k8s_objects) == 1
    assert k8s_objects[0].metadata.name == 'parent-child'


def test_json_schema_property_validation():
    abstract_jobs = {
        'image': 'example.com/base',
        'schedule': '* * * * *',
        'failedJobsHistoryLimit': 0,
        'jobs': [{'name': 'test'}]
    }
    with pytest.raises(Exception):
        kronjob.build_k8s_objects(abstract_jobs)


def test_labels():
    abstract_jobs = {
        'image': 'example.com/base',
        'schedule': 'once',
        'name': 'test',
        'labelKey': 'testKey',
        'labels': {'another': 'label'}
    }
    job = kronjob.build_k8s_objects(abstract_jobs)[0]
    assert job.metadata.labels == {'another': 'label', 'testKey': 'test'}


def test_job_properties():
    abstract_jobs = {
        'schedule': 'once',
        'name': 'once'
    }
    properties = (
        ('annotations', '["spec"]["template"]["metadata"]["annotations"]', {'test': 'annotation'}),
        ('args', '["spec"]["template"]["spec"]["containers"][0]["args"]', ['some', 'test', 'args']),
        ('backoffLimit', '["spec"]["backoffLimit"]', 5),
        ('command', '["spec"]["template"]["spec"]["containers"][0]["command"]', ['a', 'test', 'command']),
        ('containerName', '["spec"]["template"]["spec"]["containers"][0]["name"]', 'name'),
        ('cpuLimit', '["spec"]["template"]["spec"]["containers"][0]["resources"]["limits"]["cpu"]', '100m'),
        ('cpuRequest', '["spec"]["template"]["spec"]["containers"][0]["resources"]["requests"]["cpu"]', '100m'),
        ('image', '["spec"]["template"]["spec"]["containers"][0]["image"]', 'example.com/base'),
        ('imagePullPolicy', '["spec"]["template"]["spec"]["containers"][0]["imagePullPolicy"]', 'Always'),
        ('memoryLimit', '["spec"]["template"]["spec"]["containers"][0]["resources"]["limits"]["memory"]', '100m'),
        ('memoryRequest', '["spec"]["template"]["spec"]["containers"][0]["resources"]["requests"]["memory"]', '100m'),
        ('namespace', '["metadata"]["namespace"]', 'default'),
        ('nodeSelector', '["spec"]["template"]["spec"]["nodeSelector"]', {'group': 'jobs'}),
        ('restartPolicy', '["spec"]["template"]["spec"]["restartPolicy"]', 'Never'),
        ('volumes', '["spec"]["template"]["spec"]["volumes"]', [{'name': 'test', 'emptyDir': {}}]),
        ('volumeMounts', '["spec"]["template"]["spec"]["containers"][0]["volumeMounts"]', [{'name': 'test-volume', 'mountPath': '/opt/mount', 'readOnly': True}])
    )
    for input_path, _, value in properties:
        abstract_jobs[input_path] = value
    k8s_job = kronjob.build_k8s_objects(abstract_jobs)
    serialized_job = list(yaml.safe_load_all(kronjob.serialize_k8s(k8s_job)))[0]
    for _, output_path, value in properties:
        assert eval('serialized_job{}'.format(output_path)) == value


def test_cronjob_properties():
    abstract_jobs = {
        'image': 'example.com/base',
        'name': 'test'
    }
    properties = (
        ('concurrencyPolicy', '["spec"]["concurrencyPolicy"]', 'Forbid'),
        ('failedJobsHistoryLimit', '["spec"]["failedJobsHistoryLimit"]', 3),
        ('schedule', '["spec"]["schedule"]', '* * * * *'),
        ('successfulJobsHistoryLimit', '["spec"]["successfulJobsHistoryLimit"]', 1),
        ('suspend', '["spec"]["suspend"]', True),
        ('startingDeadlineSeconds', '["spec"]["startingDeadlineSeconds"]', 5000)
    )
    for input_path, _, value in properties:
        abstract_jobs[input_path] = value
    k8s_job = kronjob.build_k8s_objects(abstract_jobs)
    serialized_job = list(yaml.safe_load_all(kronjob.serialize_k8s(k8s_job)))[0] # noqa
    for _, output_path, value in properties:
        assert eval('serialized_job{}'.format(output_path)) == value
