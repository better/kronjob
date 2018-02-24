import kronjob

from kubernetes.client import models as k8s_models
import pytest


def test_single_cronjob():
    abstract_jobs = {
        'image': 'example.com/base',
        'namespace': 'test',
        'schedule': '* * * * *',
        'jobs': [{'name': 'test'}]
    }
    k8s_objects = kronjob.build_k8s_objects(abstract_jobs)
    assert len(k8s_objects) == 1
    assert isinstance(k8s_objects[0], k8s_models.V2alpha1CronJob)


def test_single_job():
    abstract_jobs = {
        'image': 'example.com/base',
        'namespace': 'test',
        'schedule': 'once',
        'jobs': [{'name': 'test'}]
    }
    k8s_objects = kronjob.build_k8s_objects(abstract_jobs)
    assert len(k8s_objects) == 1
    assert isinstance(k8s_objects[0], k8s_models.V1Job)


def test_multiple():
    abstract_jobs = {
        'image': 'example.com/base',
        'namespace': 'test',
        'jobs': [
            {'name': 'once', 'schedule': 'once'},
            {'name': 'recurring', 'schedule': '* * * * *'}
        ]
    }
    k8s_objects = kronjob.build_k8s_objects(abstract_jobs)
    assert len(k8s_objects) == 2
    assert isinstance(k8s_objects[0], k8s_models.V1Job)
    assert isinstance(k8s_objects[1], k8s_models.V2alpha1CronJob)


def test_missing_schedule():
    abstract_jobs = {
        'image': 'example.com/base',
        'namespace': 'test',
        'jobs': [
            {'name': 'test'}
        ]
    }
    with pytest.raises(Exception):
        kronjob.build_k8s_objects(abstract_jobs)


def test_image():
    abstract_jobs = {
        'image': 'example.com/base',
        'namespace': 'test',
        'jobs': [
            {'name': 'once', 'schedule': 'once'},
            {'name': 'recurring', 'schedule': '* * * * *', 'image': 'example.com/base:v2'}
        ]
    }
    k8s_objects = kronjob.build_k8s_objects(abstract_jobs)
    assert len(k8s_objects) == 2
    assert k8s_objects[0].spec.template.spec.containers[0].image == 'example.com/base'
    assert k8s_objects[1].spec.job_template.spec.template.spec.containers[0].image == 'example.com/base:v2'


def test_namespaced_names():
    abstract_jobs = {
        'image': 'example.com/base',
        'name': 'parent',
        'namespace': 'test',
        'schedule': 'once',
        'jobs': [
            {'name': 'child'}
        ]
    }
    k8s_objects = kronjob.build_k8s_objects(abstract_jobs)
    assert len(k8s_objects) == 1
    assert k8s_objects[0].metadata.name == 'parent-child'


def test_namespace_overrides():
    abstract_jobs = {
        'image': 'example.com/base',
        'namespace': 'test',
        'schedule': '* * * * *',
        'namespaceOverrides': {'test': {'schedule': 'once'}},
        'jobs': [{'name': 'once'}]
    }
    k8s_objects = kronjob.build_k8s_objects(abstract_jobs)
    assert len(k8s_objects) == 1
    assert isinstance(k8s_objects[0], k8s_models.V1Job)


def test_namespace_overrides_validation():
    abstract_jobs = {
        'image': 'example.com/base',
        'namespace': 'test',
        'schedule': '* * * * *',
        'namespaceOverrides': {'test': {'schedule': 'invalid-schedule'}},
        'jobs': [{'name': 'once'}]
    }
    with pytest.raises(Exception):
        kronjob.build_k8s_objects(abstract_jobs)


def test_top_level_job():
    abstract_jobs = {
        'image': 'example.com/base',
        'namespace': 'test',
        'schedule': 'once',
        'name': 'once'
    }
    k8s_objects = kronjob.build_k8s_objects(abstract_jobs)
    assert len(k8s_objects) == 1
    assert isinstance(k8s_objects[0], k8s_models.V1Job)
    assert k8s_objects[0].metadata.name == 'once'


def test_namespaces():
    abstract_jobs = {
        'image': 'example.com/base',
        'schedule': 'once',
        'name': 'once',
        'namespaces': ['testa', 'testb']
    }
    k8s_objects = kronjob.build_k8s_objects(abstract_jobs)
    assert len(k8s_objects) == 2
    assert sorted(k.metadata.namespace for k in k8s_objects) == ['testa', 'testb']


def test_namespaces_and_jobs():
    abstract_jobs = {
        'image': 'example.com/base',
        'schedule': 'once',
        'namespaces': ['testa', 'testb'],
        'jobs': [{'name': 'joba'}, {'name': 'jobb'}]
    }
    k8s_objects = kronjob.build_k8s_objects(abstract_jobs)
    assert len(k8s_objects) == 4
    actual = sorted((k.metadata.name, k.metadata.namespace) for k in k8s_objects)
    expected = [('joba', 'testa'), ('joba', 'testb'), ('jobb', 'testa'), ('jobb', 'testb')]
    assert actual == expected


def test_default_concurrency_policy():
    abstract_jobs = {
        'image': 'example.com/base',
        'schedule': '* * * * *',
        'namespace': 'test',
        'jobs': [{'name': 'test'}]
    }
    k8s_objects = kronjob.build_k8s_objects(abstract_jobs)
    assert len(k8s_objects) == 1
    assert k8s_objects[0].spec.concurrency_policy == 'Forbid'


def test_failed_jobs_history_limit_validation():
    abstract_jobs = {
        'image': 'example.com/base',
        'schedule': '* * * * *',
        'namespace': 'test',
        'failedJobsHistoryLimit': 0,
        'jobs': [{'name': 'test'}]
    }
    with pytest.raises(Exception):
        kronjob.build_k8s_objects(abstract_jobs)
