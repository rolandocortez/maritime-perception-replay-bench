from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    config_file = LaunchConfiguration("config_file")
    detections_topic = LaunchConfiguration("detections_topic")
    tracks_topic = LaunchConfiguration("tracks_topic")

    default_config = PathJoinSubstitution([
        FindPackageShare("tracker_node"),
        "config",
        "tracker.yaml",
    ])

    return LaunchDescription([
        DeclareLaunchArgument(
            "config_file",
            default_value=default_config,
            description="Path to tracker parameter YAML.",
        ),
        DeclareLaunchArgument(
            "detections_topic",
            default_value="/detections",
            description="Input Detection2DArray topic.",
        ),
        DeclareLaunchArgument(
            "tracks_topic",
            default_value="/tracks",
            description="Output Track2DArray topic.",
        ),
        LogInfo(msg=[
            "[tracker] starting with detections_topic=", detections_topic,
            " tracks_topic=", tracks_topic,
        ]),
        Node(
            package="tracker_node",
            executable="tracker_node",
            name="tracker_node",
            output="screen",
            parameters=[
                config_file,
                {
                    "detections_topic": detections_topic,
                    "tracks_topic": tracks_topic,
                },
            ],
        ),
    ])
