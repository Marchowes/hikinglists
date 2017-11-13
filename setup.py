"""
hikinglists, script copyright (C) 2017
"""

from distutils.core import setup
with open('requirements.txt') as f:
    requires = [line.strip() for line in f if line.strip()]
with open('test-requirements.txt') as f:
    tests_requires = [line.strip() for line in f if line.strip()]

setup(
    name='hikinglists',
    version=1.0,
    keywords=['hikinglists'],
    long_description='a repository of standardized hiking lists.',
    description='hiking lists',
    author='Marc Howes',
    author_email='marc.h.howes@gmail.com',
    url='https://github.com/marchowes/hikinglists',
    packages=['hikinglists'],
    classifiers=[
        'Programming Language :: Python :: 3',
    ],
    install_requires=requires,
)
