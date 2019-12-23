[![Build Status](https://travis-ci.org/better/kronjob.svg?branch=master)](https://travis-ci.org/better/kronjob) [![PyPI](https://img.shields.io/pypi/v/kronjob.svg)]()


# Kronjob

Generate Kubernetes Job/CronJob specs without the boilerplate.


## Features

* Expose an opinionated set of "the most useful" Job/CronJob properties as top level properties.
* Write the same specs for your Jobs and CronJobs by specifying a `schedule` in Cron format or as the string 'once'.
* Include a collection of embedded `jobs` that inherit the top level properties.

For a complete list of the available properties and commentary about their uses see [schema.json](./kronjob/schema.json).


## Installation

```bash
pip install kronjob
```


## Use

```bash
$ kronjob --help
usage: kronjob [-h] [--version] [abstract_job_spec] [k8s_job_spec]

Generate Kubernetes Job/CronJob specs without the boilerplate.

positional arguments:
  abstract_job_spec  File containing an abstract definition of Kubernetes
                     Job/CronJob specs. Defaults to stdin.
  k8s_job_spec       File kubernetes Job/CronJob specs will be written to.
                     Defaults to stdout.

optional arguments:
  -h, --help         show this help message and exit
  --version
```


## Examples

### Single Job

Input:

```yaml
image: example.com/base
name: example
namespace: test
schedule: 'once' # in order to output a Job and not a CronJob `schedule` must be 'once'
```

Output:

```yaml
apiVersion: batch/v2alpha1
kind: CronJob
metadata:
  labels:
    kronjob/job: example
  name: example
  namespace: test
spec:
  concurrencyPolicy: Forbid
  failedJobsHistoryLimit: 10
  jobTemplate:
    spec:
      template:
        metadata:
          labels:
            kronjob/job: example-example
        spec:
          containers:
          - image: example.com/base
            name: job
          restartPolicy: Never
  schedule: '* * * * *'
  successfulJobsHistoryLimit: 1
```

### Single CronJob

Input:

```yaml
image: example.com/base
name: example
namespace: test
schedule: '* * * * *'
```

Output:

```yaml
apiVersion: batch/v2alpha1
kind: CronJob
metadata:
  labels:
    kronjob/job: example
  name: example
  namespace: test
spec:
  concurrencyPolicy: Forbid
  failedJobsHistoryLimit: 10
  jobTemplate:
    spec:
      template:
        metadata:
          labels:
            kronjob/job: example
        spec:
          containers:
          - image: example.com/base
            name: job
          restartPolicy: Never
  schedule: '* * * * *'
  successfulJobsHistoryLimit: 1
```

### Job and CronJob sharing top level spec

Input:

```yaml
image: example.com/base
name: example
namespace: test
jobs:
  - schedule: '* * * * *'
  - schedule: once
```

Output:

```yaml
apiVersion: batch/v2alpha1
kind: CronJob
metadata:
  labels:
    kronjob/job: example
  name: example
  namespace: test
spec:
  concurrencyPolicy: Forbid
  failedJobsHistoryLimit: 10
  jobTemplate:
    spec:
      template:
        metadata:
          labels:
            kronjob/job: example
        spec:
          containers:
          - image: example.com/base
            name: job
          restartPolicy: Never
  schedule: '* * * * *'
  successfulJobsHistoryLimit: 1
---
apiVersion: batch/v1
kind: Job
metadata:
  labels:
    kronjob/job: example
  name: example
  namespace: test
spec:
  template:
    metadata:
      labels:
        kronjob/job: example
    spec:
      containers:
      - image: example.com/base
        name: job
      restartPolicy: Never
```

## Development

### Adding more kubernetes parameters

In general, to allow `kronjob` to take more parameters, the following must be done:

1.  Add the parameter to `schema.json` so that it is consumed from the `kronjob.yml`
2.  Find its appropriate mapping in the kubernetes models. This generally involves going through the `github.com/kubernetes-client/python` documentation and trying to find the appropriate model, depending on where the parameter is supposed to be surfaced
3.  Add the mapping inside the `build_k8s_object` function.
4.  Update tests to reflect that the kronjob can handle a new parameter, and that it maps appropriately. Note that `kronjob` abstracts both a CronJob and a Job
