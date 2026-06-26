import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import LogInfo
from launch_ros.actions import Node


def generate_launch_description():
    config_path = os.path.join(
        get_package_share_directory("spectrogram_node"),
        "config",
        "spectrogram.yaml",
    )

    return LaunchDescription([
        LogInfo(msg="[spectrogram] starting spectrogram and acoustic event stub node"),
        Node(
            package="spectrogram_node",
            executable="spectrogram_node",
            name="spectrogram_node",
            output="screen",
            parameters=[config_path],
        ),
    ])
