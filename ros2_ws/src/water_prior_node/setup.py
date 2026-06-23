from glob import glob
from setuptools import find_packages, setup

package_name = "water_prior_node"

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
    description="ROS2 maritime water prior node for detection filtering.",
    license="MIT",
    entry_points={
        "console_scripts": [
            "water_prior_node = water_prior_node.node:main",
        ],
    },
)
