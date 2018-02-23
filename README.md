# Kronjob

[![Build Status](https://travis-ci.org/better/kronjob.svg?branch=master)](https://travis-ci.org/better/kronjob)

## Installation

```bash
pip install kronjob
```

## Use

For a complete list of the available fields and commentary about their use see [schema.json](./schema.json).

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

For a complete list of the available fields and commentary about their use see [schema.json](./schema.json).

## Examples


```bash
$ cat example_job.yml
name: example
image: 'example.com/base'
schedule: '* * * * *'
env:
  - name: ENV
    value: MARS
namespace: test
jobs:
  - name: first
  - name: second
  - name: only-once
    schedule: once
    env:
      - name: SECRET
        valueFrom:
          secretKeyRef:
            name: fake
            key: secret
```

```bash
$ kronjob example_job.yml
apiVersion: batch/v2alpha1
kind: CronJob
metadata:
  name: first
  namespace: test
spec:
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - env:
            - name: ENV
              value: MARS
            image: example.com/base
            name: job
  schedule: '* * * * *'
---
apiVersion: batch/v2alpha1
kind: CronJob
metadata:
  name: second
  namespace: test
spec:
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - env:
            - name: ENV
              value: MARS
            image: example.com/base
            name: job
  schedule: '* * * * *'
---
apiVersion: batch/v1
kind: Job
metadata:
  name: only-once
  namespace: test
spec:
  template:
    spec:
      containers:
      - env:
        - name: SECRET
          valueFrom:
            secretKeyRef:
              key: secret
              name: fake
        image: example.com/base
        name: job
```
