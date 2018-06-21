from __future__ import print_function

import argparse
import copy
import json
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


_K8S_API_CLIENT = k8s_client.ApiClient()
_REQUIRED_FIELDS = ['name', 'image', 'schedule']
_SCHEMA = json.loads(pkgutil.get_data('kronjob', 'schema.json').decode('utf-8'))


class ValidationException(Exception):
    pass


def _build_aggregate_jobs(abstract_jobs):
    base_job = copy.deepcopy(abstract_jobs)
    jobs = base_job.pop('jobs', [{}])

    def _build_aggregate_job(job):
        aggregate_job = copy.deepcopy(base_job)
        aggregate_job.update(job)
        if 'name' in aggregate_job:
            aggregate_job['name'] = '-'.join(filter(None, (base_job.get('name'), job.get('name'))))
        if 'env' in aggregate_job:
            aggregate_job['env'] = base_job.get('env', []) + job.get('env', [])
        return aggregate_job

    return [_build_aggregate_job(job) for job in jobs]


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


def build_k8s_object(aggregate_job, defaults=None):
    defaults = copy.deepcopy(defaults) if defaults is not None else {}
    if 'containerName' not in defaults:
        defaults['containerName'] = '{}-job'.format(aggregate_job['name'])
    if 'labels' not in defaults:
        defaults['labels'] = {}
    if 'labelKey' not in defaults:
        defaults['labelKey'] = 'kronjob/job'

    def _get_arg(key):
        return aggregate_job.get(key, defaults.get(key))

    def _get_args(*keys):
        return {
            inflection.underscore(key): _get_arg(key)
            for key in keys
        }

    labels = _get_arg('labels')
    labels[_get_arg('labelKey')] = _get_arg('name')
    metadata = k8s_models.V1ObjectMeta(labels=labels, **_get_args('name', 'namespace'))
    env = _deserialize_k8s(aggregate_job.get('env'), 'list[V1EnvVar]')
    job_spec = k8s_models.V1JobSpec(
        template=k8s_models.V1PodTemplateSpec(
            metadata=k8s_models.V1ObjectMeta(labels=labels, **_get_args('annotations')),
            spec=k8s_models.V1PodSpec(
                containers=[
                    k8s_models.V1Container(
                        env=env, name=_get_arg('containerName'),
                        resources=k8s_models.V1ResourceRequirements(
                            limits={'cpu': _get_arg('cpuLimit'), 'memory': _get_arg('memoryLimit')},
                            requests={'cpu': _get_arg('cpuRequest'), 'memory': _get_arg('memoryRequest')}
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
                    metadata=k8s_models.V1ObjectMeta(labels=labels),
                    spec=job_spec
                ),
                **_get_args(
                    'concurrencyPolicy', 'failedJobsHistoryLimit', 'schedule', 'successfulJobsHistoryLimit', 'suspend'
                )
            )
        )

    return k8s_object


def build_k8s_objects(abstract_jobs, defaults=None):
    jsonschema.validate(abstract_jobs, _SCHEMA)
    aggregate_jobs = _build_aggregate_jobs(abstract_jobs)
    for aggregate_job in aggregate_jobs:
        _validate_aggregate_job(aggregate_job)
    return [build_k8s_object(job, defaults=defaults) for job in aggregate_jobs]


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
    parser.add_argument(
        '--defaults-file',
        type=argparse.FileType('r'),
        help='File containing default properties which will be applied to any generated Job/CronJob specs that do specify them.'
    )
    parser.add_argument('--version', action='store_true')
    args = parser.parse_args()

    if args.version:
        dist = pkg_resources.get_distribution('kronjob')
        print(dist)
        return

    abstract_jobs = yaml.safe_load(args.abstract_job_spec)
    defaults = yaml.safe_load(args.defaults_file) if args.defaults_file is not None else None
    k8s_objects = build_k8s_objects(abstract_jobs, defaults=defaults)
    print(serialize_k8s(k8s_objects), file=args.k8s_job_spec)


if __name__ == '__main__':
    main()
