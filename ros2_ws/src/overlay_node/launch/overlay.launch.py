from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    config_file = LaunchConfiguration("config_file")
    image_topic = LaunchConfiguration("image_topic")
    detections_topic = LaunchConfiguration("detections_topic")
    tracks_topic = LaunchConfiguration("tracks_topic")
    overlay_topic = LaunchConfiguration("overlay_topic")

    default_config = PathJoinSubstitution([
        FindPackageShare("overlay_node"),
        "config",
        "overlay.yaml",
    ])

    return LaunchDescription([
        DeclareLaunchArgument(
            "config_file",
            default_value=default_config,
            description="Path to overlay parameter YAML.",
        ),
        DeclareLaunchArgument(
            "image_topic",
            default_value="/camera/image_raw",
            description="Input image topic.",
        ),
        DeclareLaunchArgument(
            "detections_topic",
            default_value="/detections",
            description="Input Detection2DArray topic.",
        ),
        DeclareLaunchArgument(
            "tracks_topic",
            default_value="/tracks",
            description="Input Track2DArray topic.",
        ),
        DeclareLaunchArgument(
            "overlay_topic",
            default_value="/debug/overlay_image",
            description="Output overlay image topic.",
        ),
        LogInfo(msg=[
            "[overlay] starting with image_topic=", image_topic,
            " detections_topic=", detections_topic,
            " tracks_topic=", tracks_topic,
            " overlay_topic=", overlay_topic,
        ]),
        Node(
            package="overlay_node",
            executable="overlay_node",
            name="overlay_node",
            output="screen",
            parameters=[
                config_file,
                {
                    "image_topic": image_topic,
                    "detections_topic": detections_topic,
                    "tracks_topic": tracks_topic,
                    "overlay_topic": overlay_topic,
                },
            ],
        ),
    ])
