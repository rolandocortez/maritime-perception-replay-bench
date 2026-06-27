from glob import glob
import os

from setuptools import find_packages, setup

package_name = "annotation_miner"

setup(
    name=package_name,
    version="0.0.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
        (os.path.join("share", package_name, "config"), glob("config/*.yaml")),
        (os.path.join("share", package_name, "launch"), glob("launch/*.launch.py")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="rolando",
    maintainer_email="rolando@example.com",
    description="Annotation mining utilities for maritime perception replay.",
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "uncertain_frame_node = annotation_miner.uncertain_frame_node:main",
            "unstable_track_node = annotation_miner.unstable_track_node:main",
        ],
    },
)
