from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    pkg_share = Path(get_package_share_directory("annotation_miner"))
    default_config = str(pkg_share / "config" / "unstable_track_mining.yaml")

    return LaunchDescription(
        [
            DeclareLaunchArgument("config", default_value=default_config),
            DeclareLaunchArgument("tracks_topic", default_value="/tracks"),
            DeclareLaunchArgument("image_topic", default_value="/camera/image_raw"),
            DeclareLaunchArgument("output_dir", default_value="reports/annotation/unstable_tracks"),
            DeclareLaunchArgument("min_track_age_for_stability", default_value="5"),
            DeclareLaunchArgument("max_missed_frames", default_value="3"),
            DeclareLaunchArgument("max_saved_events", default_value="200"),
            Node(
                package="annotation_miner",
                executable="unstable_track_node",
                name="unstable_track_miner",
                output="screen",
                parameters=[
                    LaunchConfiguration("config"),
                    {
                        "tracks_topic": LaunchConfiguration("tracks_topic"),
                        "image_topic": LaunchConfiguration("image_topic"),
                        "output_dir": LaunchConfiguration("output_dir"),
                        "min_track_age_for_stability": LaunchConfiguration("min_track_age_for_stability"),
                        "max_missed_frames": LaunchConfiguration("max_missed_frames"),
                        "max_saved_events": LaunchConfiguration("max_saved_events"),
                    },
                ],
            ),
        ]
    )
