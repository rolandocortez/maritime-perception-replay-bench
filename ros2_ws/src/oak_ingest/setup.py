from glob import glob
from setuptools import setup

package_name = "oak_ingest"

setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
        (f"share/{package_name}/config", glob("config/*.yaml")),
        (f"share/{package_name}/launch", glob("launch/*.launch.py")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Rolando",
    maintainer_email="rolando@example.com",
    description="OAK/DepthAI camera ingest node for ROS2 image smoke testing.",
    license="MIT",
    entry_points={
        "console_scripts": [
            "oak_status_node = oak_ingest.oak_status_node:main",
        ],
    },
)
