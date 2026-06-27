from glob import glob
import os

from setuptools import find_packages, setup


package_name = "metrics_node"

setup(
    name=package_name,
    version="0.0.1",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
        (os.path.join("share", package_name, "config"), glob("config/*.yaml")),
        (os.path.join("share", package_name, "launch"), glob("launch/*.launch.py")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Rolando",
    maintainer_email="rolscg@gmail.com",
    description="Runtime FPS, latency, drop, detection, and tracking metrics for the replay pipeline.",
    license="MIT",
    entry_points={
        "console_scripts": [
            "metrics_node = metrics_node.node:main",
        ],
    },
)
