from __future__ import print_function

import argparse
import copy
import json
import os
import pkg_resources
import pkgutil
import sys

import crontab
import inflection
import jsonschema
from kubernetes.client import models as k8s_models
from kubernetes import client as k8s_client
import yaml


__all__ = ['build_k8s_objects', 'main', 'serialize_k8s']


_ALTERNATE_DEFAULTS = {
    # non standard k8s defaults
    'concurrencyPolicy': 'Forbid',
    'containerName': 'job',
    'cpuLimit': '1',
    'cpuRequest': '1',
    'failedJobsHistoryLimit': 10,
    'memoryLimit': '1Gi',
    'memoryRequest': '1Gi',
    'restartPolicy': 'Never',
    'successfulJobsHistoryLimit': 1,
    'nodeSelector': {'group': 'jobs'}
}
_K8S_API_CLIENT = k8s_client.ApiClient()
_REQUIRED_FIELDS = ['name', 'image', 'namespace', 'schedule']
_SCHEMA = json.loads(pkgutil.get_data('kronjob', 'schema.json').decode('utf-8'))


class ValidationException(Exception):
    pass


def _build_aggregate_jobs(abstract_jobs):
    base_job = copy.deepcopy(abstract_jobs)
    base_namespace = base_job.get('namespace')
    jobs = base_job.pop('jobs', [None])
    namespaces = base_job.pop('namespaces', [None])
    namespace_overrides = base_job.pop('namespaceOverrides', {})

    def _build_aggregate_job(job, namespace):
        _job = job if job is not None else {}
        _namespace = _job.get('namespace', namespace if namespace is not None else base_namespace)
        _namespace_override = namespace_overrides.get(_namespace, {})
        aggregate_job = copy.deepcopy(base_job)
        aggregate_job.update(_namespace_override)
        aggregate_job.update(_job)
        if _namespace is not None:
            aggregate_job['namespace'] = _namespace
        if 'name' in aggregate_job:
            _name_parts = list(filter(None, (base_job.get('name'), _namespace_override.get('name'), _job.get('name'))))
            aggregate_job['name'] = '-'.join(_name_parts)
        if 'env' in aggregate_job:
            aggregate_job['env'] = base_job.get('env', []) + _namespace_override.get('env', []) + _job.get('env', [])
        return aggregate_job

    return [_build_aggregate_job(job, namespace) for job in jobs for namespace in namespaces]


def _cron_is_valid(cron_schedule):
    try:
        crontab.CronTab(cron_schedule)
        return True
    except:
        return False

def _validate_aggregate_job(job):
    if not set(job).issuperset(_REQUIRED_FIELDS):
        raise ValidationException('each generated job must contain all of: {}'.format(_REQUIRED_FIELDS))
    if not (job['schedule'] == 'once' or _cron_is_valid(job['schedule'])):
        raise ValidationException('schedule must be either "once" or a valid cron schedule')


def _deserialize_k8s(data, type):
    """
    It'd be nice if this was less hacky but it's not worth building a
    complete deserializer ourselves and we shouldn't rely on the internal
    API of the python k8s client.
    """
    class FakeResp:
        def __init__(self, obj):
            self.data = json.dumps(obj)

    return _K8S_API_CLIENT.deserialize(FakeResp(data), type)


def serialize_k8s(k8s_object):
    return yaml.dump_all(
        _K8S_API_CLIENT.sanitize_for_serialization(k8s_object),
        default_flow_style=False
    )


def build_k8s_object(aggregate_job):
    def _get_args(*keys):
        return {
            inflection.underscore(key): aggregate_job.get(key, _ALTERNATE_DEFAULTS.get(key))
            for key in keys
        }

    labels = {aggregate_job.get('labelKey', 'kronjob/job'): aggregate_job['name']}
    metadata = k8s_models.V1ObjectMeta(
        labels=labels,
        **_get_args('name', 'namespace')
    )
    env = _deserialize_k8s(aggregate_job.get('env'), 'list[V1EnvVar]')
    job_spec = k8s_models.V1JobSpec(
        template=k8s_models.V1PodTemplateSpec(
            metadata=k8s_models.V1ObjectMeta(labels=labels),
            spec=k8s_models.V1PodSpec(
                containers=[
                    k8s_models.V1Container(
                        env=env, name=_get_args('containerName')['container_name'],
                        resources=k8s_models.V1ResourceRequirements(
                            limits={'cpu': _get_args('cpuLimit')['cpu_limit'], 'memory': _get_args('memoryLimit')['memory_limit']},
                            requests={'cpu': _get_args('cpuRequest')['cpu_request'], 'memory': _get_args('memoryRequest')['memory_request']}
                        ),
                        **_get_args('args', 'command', 'image', 'imagePullPolicy')
                    )
                ],
                **_get_args('nodeSelector', 'restartPolicy', 'volumes')
            )
        )
    )
    if aggregate_job['schedule'] == 'once':
        k8s_object = k8s_models.V1Job(
            api_version='batch/v1',
            kind='Job',
            metadata=metadata,
            spec=job_spec
        )
    else:
        k8s_object = k8s_models.V2alpha1CronJob(
            api_version='batch/v2alpha1',
            kind='CronJob',
            metadata=metadata,
            spec=k8s_models.V2alpha1CronJobSpec(
                job_template=k8s_models.V2alpha1JobTemplateSpec(
                    spec=job_spec
                ),
                **_get_args(
                    'concurrencyPolicy', 'failedJobsHistoryLimit', 'schedule',
                    'successfulJobsHistoryLimit', 'suspend'
                )
            )
        )

    return k8s_object


def build_k8s_objects(abstract_jobs):
    jsonschema.validate(abstract_jobs, _SCHEMA)
    aggregate_jobs = _build_aggregate_jobs(abstract_jobs)
    for aggregate_job in aggregate_jobs:
        _validate_aggregate_job(aggregate_job)
    return [build_k8s_object(job) for job in aggregate_jobs]


def main():
    parser = argparse.ArgumentParser(description='Generate Kubernetes Job/CronJob specs without the boilerplate.')
    parser.add_argument(
        'abstract_job_spec',
        nargs='?',
        type=argparse.FileType(),
        default=sys.stdin,
        help='File containing an abstract definition of Kubernetes Job/CronJob specs. Defaults to stdin.'
    )
    parser.add_argument(
        'k8s_job_spec',
        nargs='?',
        type=argparse.FileType('w'),
        default=sys.stdout,
        help='File kubernetes Job/CronJob specs will be written to. Defaults to stdout.'
    )
    parser.add_argument('--version', action='store_true')
    args = parser.parse_args()

    if args.version:
        dist = pkg_resources.get_distribution('kronjob')
        print(dist)
        return

    abstract_jobs = yaml.safe_load(args.abstract_job_spec)
    k8s_objects = build_k8s_objects(abstract_jobs)
    print(serialize_k8s(k8s_objects), file=args.k8s_job_spec)


if __name__ == '__main__':
    main()
