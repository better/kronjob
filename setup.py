from setuptools import setup

setup(
    name='kronjob',
    version='0.0.1',
    description='Generate Kubernetes Job/CronJob specs without the boilerplate.',
    py_modules=['kronjob'],
    install_requires=[
        'kubernetes==4.0.0',
        'marshmallow==3.0.0b7',
        'python-crontab==2.2.8',
        'PyYAML==3.12'
    ],
    setup_requires=['pytest-runner'],
    tests_require=['pytest'],
    test_suite='test_kronjob',
    url='https://github.com/better/kronjob',
    author='Better Mortgage',
    author_email='accounts@better.com',
    keywords='kubernetes job cronjob schedule template',
    entry_points={
        'console_scripts': ['kronjob=kronjob:main']
    }
)
