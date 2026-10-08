import re
from pathlib import Path

from setuptools import find_namespace_packages, setup


HERE = Path(__file__).parent
REPOSITORY = "https://github.com/bjornhagstrom/ckanext-actor-registry/blob/master/"


def long_description():
    """The README for PyPI: no screenshots, and links that work outside the repository."""
    text = (HERE / "README.md").read_text(encoding="utf-8")
    text = re.sub(r"^!\[[^\]]*\]\([^)]*\)[ \t]*\n(?:[ \t]*\n)?", "", text, flags=re.MULTILINE)
    return re.sub(r"\]\((?!https?://|#|mailto:)([^)]+)\)", lambda m: "](" + REPOSITORY + m.group(1) + ")", text)


setup(
    name="ckanext-actor-registry",
    version="0.4.1",
    description="Reusable actors and contact points for CKAN metadata",
    long_description=long_description(),
    long_description_content_type="text/markdown",
    author="Bjorn Hagstrom",
    author_email="bjorn@hagstrom.nu",
    url="https://github.com/bjornhagstrom/ckanext-actor-registry",
    project_urls={
        "Changelog": "https://github.com/bjornhagstrom/ckanext-actor-registry/blob/master/CHANGELOG.md",
        "Issue Tracker": "https://github.com/bjornhagstrom/ckanext-actor-registry/issues",
    },
    packages=find_namespace_packages(include=["ckanext.*"]),
    include_package_data=True,
    license="MIT",
    python_requires=">=3.10",
    classifiers=[
        "Development Status :: 4 - Beta",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Internet :: WWW/HTTP :: Dynamic Content",
    ],
    entry_points={
        "ckan.plugins": [
            "actor_registry=ckanext.actor_registry.plugin:ActorRegistryPlugin",
        ],
        "ckan.rdf.profiles": [
            "actor_registry_euro_dcat_ap_3=ckanext.actor_registry.profiles:ActorRegistryEuropeanDCATAP3Profile",
        ],
    },
)
