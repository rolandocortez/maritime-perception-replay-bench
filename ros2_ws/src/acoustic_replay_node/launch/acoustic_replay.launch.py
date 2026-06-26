import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    wav_path = LaunchConfiguration("wav_path")
    config_path = os.path.join(
        get_package_share_directory("acoustic_replay_node"),
        "config",
        "acoustic_replay.yaml",
    )

    return LaunchDescription([
        DeclareLaunchArgument(
            "wav_path",
            default_value="data/acoustic/sample.wav",
            description="Path to local WAV file.",
        ),
        LogInfo(msg=["[acoustic_replay] wav_path=", wav_path]),
        Node(
            package="acoustic_replay_node",
            executable="acoustic_replay_node",
            name="acoustic_replay_node",
            output="screen",
            parameters=[
                config_path,
                {"wav_path": wav_path},
            ],
        ),
    ])
