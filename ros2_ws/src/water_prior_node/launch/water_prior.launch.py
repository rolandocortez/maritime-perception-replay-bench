from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    config_file = LaunchConfiguration("config_file")
    image_topic = LaunchConfiguration("image_topic")
    detections_topic = LaunchConfiguration("detections_topic")
    filtered_detections_topic = LaunchConfiguration("filtered_detections_topic")

    default_config = PathJoinSubstitution([
        FindPackageShare("water_prior_node"),
        "config",
        "water_prior.yaml",
    ])

    return LaunchDescription([
        DeclareLaunchArgument(
            "config_file",
            default_value=default_config,
            description="Path to water prior parameter YAML.",
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
            "filtered_detections_topic",
            default_value="/maritime/filtered_detections",
            description="Output filtered Detection2DArray topic.",
        ),
        LogInfo(msg=[
            "[water_prior] starting with image_topic=", image_topic,
            " detections_topic=", detections_topic,
            " filtered_detections_topic=", filtered_detections_topic,
        ]),
        Node(
            package="water_prior_node",
            executable="water_prior_node",
            name="water_prior_node",
            output="screen",
            parameters=[
                config_file,
                {
                    "image_topic": image_topic,
                    "detections_topic": detections_topic,
                    "filtered_detections_topic": filtered_detections_topic,
                },
            ],
        ),
    ])
