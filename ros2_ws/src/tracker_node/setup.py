from glob import glob
from setuptools import find_packages, setup

package_name = "tracker_node"

setup(
    name=package_name,
    version="0.0.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
        (f"share/{package_name}/config", glob("config/*.yaml")),
        (f"share/{package_name}/launch", glob("launch/*.launch.py")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="rolando",
    maintainer_email="rolando@example.com",
    description="ROS2 tracker node for maritime perception replay.",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "tracker_node = tracker_node.node:main",
        ],
    },
)
