import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import LogInfo
from launch_ros.actions import Node


def generate_launch_description():
    config_path = os.path.join(
        get_package_share_directory("metrics_node"),
        "config",
        "metrics.yaml",
    )

    return LaunchDescription([
        LogInfo(msg="[metrics] starting runtime metrics node"),
        Node(
            package="metrics_node",
            executable="metrics_node",
            name="metrics_node",
            output="screen",
            parameters=[config_path],
        ),
    ])
