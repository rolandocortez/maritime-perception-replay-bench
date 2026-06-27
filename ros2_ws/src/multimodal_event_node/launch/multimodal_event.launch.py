import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import LogInfo
from launch_ros.actions import Node


def generate_launch_description():
    config_path = os.path.join(
        get_package_share_directory("multimodal_event_node"),
        "config",
        "multimodal_event.yaml",
    )

    return LaunchDescription([
        LogInfo(msg="[multimodal_event] starting temporal multimodal interface node"),
        Node(
            package="multimodal_event_node",
            executable="multimodal_event_node",
            name="multimodal_event_node",
            output="screen",
            parameters=[config_path],
        ),
    ])
