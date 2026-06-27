import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    config_path = os.path.join(
        get_package_share_directory("oak_ingest"),
        "config",
        "oak.yaml",
    )

    rgb_resolution = LaunchConfiguration("rgb_resolution")
    fps = LaunchConfiguration("fps")
    remap_to_standard_camera_topics = LaunchConfiguration("remap_to_standard_camera_topics")

    return LaunchDescription([
        DeclareLaunchArgument("rgb_resolution", default_value="1080p"),
        DeclareLaunchArgument("fps", default_value="30.0"),
        DeclareLaunchArgument("remap_to_standard_camera_topics", default_value="false"),
        LogInfo(msg=[
            "[oak_ingest] starting OAK ingest",
            " rgb_resolution=", rgb_resolution,
            " fps=", fps,
            " remap_to_standard_camera_topics=", remap_to_standard_camera_topics,
        ]),
        Node(
            package="oak_ingest",
            executable="oak_status_node",
            name="oak_status_node",
            output="screen",
            parameters=[
                config_path,
                {
                    "rgb_resolution": rgb_resolution,
                    "fps": ParameterValue(fps, value_type=float),
                    "remap_to_standard_camera_topics": ParameterValue(
                        remap_to_standard_camera_topics,
                        value_type=bool,
                    ),
                },
            ],
        ),
    ])
