from setuptools import setup, find_packages


def parse_requirements(filename):
    with open(filename) as f:
        return f.read().splitlines()

setup(
    name="openhens",
    version="0.5",
    packages=find_packages(),
    install_requires=parse_requirements('requirements.txt'),
)
