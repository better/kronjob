from __future__ import print_function

import argparse
import copy
import json
import pkg_resources
import sys

import crontab
from kubernetes.client import models as k8s_models
from kubernetes import client as k8s_client
import marshmallow
import yaml


_K8S_API_CLIENT = k8s_client.ApiClient()
# Any defaults that differ from k8s should be added here
_DEFAULTS = {
    'concurrency_policy': 'Forbid',
    'failed_jobs_history_limit': 10,
    'restart_policy': 'Never',
    'successful_jobs_history_limit': 1
}


def _build_aggregate_jobs(abstract_jobs):
    base_job = copy.deepcopy(abstract_jobs)
    base_namespace = base_job.get('namespace')
    jobs = base_job.pop('jobs', None)
    namespaces = base_job.pop('namespaces', None)
    namespace_overrides = base_job.pop('namespace_overrides', {})

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

    if jobs is None and namespaces is None:
        return [_build_aggregate_job(abstract_jobs, None)]

    jobs = jobs if jobs is not None else [None]
    namespaces = namespaces if namespaces is not None else [None]
    return [_build_aggregate_job(job, namespace) for job in jobs for namespace in namespaces]


class _AbstractJobsSchema(marshmallow.Schema):
    _REQUIRED_FIELDS = ['name', 'image', 'namespace', 'schedule']

    args = marshmallow.fields.List(marshmallow.fields.String)
    concurrency_policy = marshmallow.fields.String(load_from='concurrencyPolicy')
    env = marshmallow.fields.List(marshmallow.fields.Raw)
    command = marshmallow.fields.List(marshmallow.fields.String)
    container_name = marshmallow.fields.String(load_from='containerName')
    failed_jobs_history_limit = marshmallow.fields.Int(
        load_from='failedJobsHistoryLimit', validate=marshmallow.validate.Range(min=1)
    )
    image = marshmallow.fields.String()
    label_key = marshmallow.fields.String(load_from='labelKey')
    name = marshmallow.fields.String()
    namespace = marshmallow.fields.String()
    node_selector = marshmallow.fields.Raw(load_from='nodeSelector')
    restart_policy = marshmallow.fields.String(load_from='restartPolicy')
    schedule = marshmallow.fields.String()
    successful_jobs_history_limit = marshmallow.fields.Int(
        load_from='successfulJobsHistoryLimit', validate=marshmallow.validate.Range(min=1)
    )
    suspend = marshmallow.fields.Boolean()

    jobs = marshmallow.fields.Nested(
        '_AbstractJobsSchema',
        many=True,
        exclude=('jobs', 'namespaces', 'namespace_overrides')
    )
    namespaces = marshmallow.fields.List(marshmallow.fields.String)
    namespace_overrides = marshmallow.fields.Dict(
        keys=marshmallow.fields.String(),
        values=marshmallow.fields.Nested(
            '_AbstractJobsSchema', exclude=('jobs', 'namespace', 'namespaces', 'namespace_overrides')
        ),
        load_from='namespaceOverrides'
    )

    @marshmallow.validates('schedule')
    def validate_schedule(self, data):
        if not (data == 'once' or crontab.CronSlices.is_valid(data)):
            raise marshmallow.ValidationError('schedule must be either once or a valid cron schedule')

    @marshmallow.validates_schema(pass_original=True)
    def validate_schema(self, data, orig):
        # only perform full schema validation on root node
        if not (isinstance(orig, dict) and orig.get('__root')):
            return

        required_keys = set(self._REQUIRED_FIELDS)
        for job in _build_aggregate_jobs(data):
            if not required_keys.issubset(job):
                raise marshmallow.ValidationError(
                    'Either the top level spec, namespace override, or embedded job must include '
                    'all of the following fields: {}.'.format(
                        ', '.join(self._REQUIRED_FIELDS)
                    )
                )


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
            key: aggregate_job.get(key, _DEFAULTS.get(key))
            for key in keys
        }

    labels = {aggregate_job.get('label_key', 'kronjob/job'): aggregate_job['name']}
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
                        env=env, name=aggregate_job.get('containerName', 'job'),
                        **_get_args('args', 'command', 'image')
                    )
                ],
                **_get_args('node_selector', 'restart_policy')
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
                    'concurrency_policy', 'failed_jobs_history_limit', 'schedule',
                    'successful_jobs_history_limit', 'suspend'
                )
            )
        )

    return k8s_object


def build_k8s_objects(abstract_jobs):
    abstract_jobs = copy.deepcopy(abstract_jobs)
    abstract_jobs['__root'] = True  # mark this as the root job
    abstract_jobs = _AbstractJobsSchema().load(abstract_jobs)
    aggregate_jobs = _build_aggregate_jobs(abstract_jobs)
    return [build_k8s_object(job) for job in aggregate_jobs]


def main():
    parser = argparse.ArgumentParser(description='Generate Kubernetes Job/CronJob specs without the boilerplate.')
    parser.add_argument(
        'jobs_description',
        nargs='?',
        type=argparse.FileType(),
        default=sys.stdin,
        help='File containing an abstract definition of Kubernetes Job/CronJob specs.'
    )
    parser.add_argument('outfile', nargs='?', type=argparse.FileType('w'), default=sys.stdout)
    parser.add_argument('--version', action='store_true')
    args = parser.parse_args()

    if args.version:
        dist = pkg_resources.get_distribution('kronjob')
        print(dist)
        return

    abstract_jobs = yaml.safe_load(args.jobs_description)
    k8s_objects = build_k8s_objects(abstract_jobs)
    print(serialize_k8s(k8s_objects), file=args.outfile)


if __name__ == '__main__':
    main()
