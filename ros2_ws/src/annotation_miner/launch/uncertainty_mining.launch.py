import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    config_path = os.path.join(
        get_package_share_directory("annotation_miner"),
        "config",
        "uncertainty_mining.yaml",
    )

    image_topic = LaunchConfiguration("image_topic")
    detections_topic = LaunchConfiguration("detections_topic")
    detections_type = LaunchConfiguration("detections_type")
    output_dir = LaunchConfiguration("output_dir")
    min_confidence = LaunchConfiguration("min_confidence")
    max_confidence = LaunchConfiguration("max_confidence")
    many_detections_count = LaunchConfiguration("many_detections_count")
    max_saved_frames = LaunchConfiguration("max_saved_frames")

    return LaunchDescription([
        DeclareLaunchArgument("image_topic", default_value="/camera/image_raw"),
        DeclareLaunchArgument("detections_topic", default_value="/detections"),
        DeclareLaunchArgument("detections_type", default_value="vision_msgs/msg/Detection2DArray"),
        DeclareLaunchArgument("output_dir", default_value="reports/annotation/uncertain_frames"),
        DeclareLaunchArgument("min_confidence", default_value="0.20"),
        DeclareLaunchArgument("max_confidence", default_value="0.45"),
        DeclareLaunchArgument("many_detections_count", default_value="5"),
        DeclareLaunchArgument("max_saved_frames", default_value="200"),

        LogInfo(msg=[
            "[annotation_miner] starting uncertain-frame mining",
            " image_topic=", image_topic,
            " detections_topic=", detections_topic,
            " output_dir=", output_dir,
        ]),

        Node(
            package="annotation_miner",
            executable="uncertain_frame_node",
            name="uncertain_frame_miner",
            output="screen",
            parameters=[
                config_path,
                {
                    "image_topic": image_topic,
                    "detections_topic": detections_topic,
                    "detections_type": detections_type,
                    "output_dir": output_dir,
                    "min_confidence": ParameterValue(min_confidence, value_type=float),
                    "max_confidence": ParameterValue(max_confidence, value_type=float),
                    "many_detections_count": ParameterValue(many_detections_count, value_type=int),
                    "max_saved_frames": ParameterValue(max_saved_frames, value_type=int),
                },
            ],
        ),
    ])
