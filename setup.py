from setuptools import setup

setup(
    name='kronjob',
    version='2.0.1',
    description='Generate Kubernetes Job/CronJob specs without the boilerplate.',
    install_requires=[
        'kubernetes==4.0.0',
        'inflection==0.3.1',
        'jsonschema==2.6.0',
        'crontab==0.22.1',
        'PyYAML==3.12'
    ],
    url='https://github.com/better/kronjob',
    author='Better Mortgage',
    author_email='accounts@better.com',
    keywords='kubernetes job cronjob schedule template',
    entry_points={'console_scripts': ['kronjob=kronjob:main']},
    license='MIT',
    packages=['kronjob'],
    package_data={'kronjob': ['schema.json']}
)
