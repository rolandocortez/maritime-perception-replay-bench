from glob import glob
from setuptools import find_packages, setup

package_name = "multimodal_replay_node"

setup(
    name=package_name,
    version="0.0.1",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/launch", glob("launch/*.launch.py")),
        ("share/" + package_name + "/config", glob("config/*.yaml")),
    ],
    install_requires=["setuptools", "numpy", "PyYAML"],
    zip_safe=True,
    maintainer="maritime replay bench",
    maintainer_email="noreply@example.com",
    description="Paired acoustic-visual replay node for local maritime multimodal samples.",
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "paired_replay_node = multimodal_replay_node.paired_replay_node:main",
        ],
    },
)
