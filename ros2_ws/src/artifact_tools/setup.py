from glob import glob
import os

from setuptools import find_packages, setup

package_name = "artifact_tools"

setup(
    name=package_name,
    version="0.0.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
        (os.path.join("share", package_name, "config"), glob("config/*.yaml")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="rolando",
    maintainer_email="rolando@example.com",
    description="Run manifest and artifact lineage utilities.",
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "create_run_manifest = artifact_tools.manifest:main_create",
            "validate_run_manifest = artifact_tools.manifest:main_validate",
        ],
    },
)
