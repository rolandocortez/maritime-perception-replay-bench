from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    config_file = LaunchConfiguration("config_file")
    model_name = LaunchConfiguration("model_name")
    device = LaunchConfiguration("device")
    image_topic = LaunchConfiguration("image_topic")
    detections_topic = LaunchConfiguration("detections_topic")

    default_config = PathJoinSubstitution([
        FindPackageShare("detector_node"),
        "config",
        "detector.yaml",
    ])

    return LaunchDescription([
        DeclareLaunchArgument(
            "config_file",
            default_value=default_config,
            description="Path to detector parameter YAML.",
        ),
        DeclareLaunchArgument(
            "model_name",
            default_value="yolo11n.pt",
            description="Ultralytics model name or local model path.",
        ),
        DeclareLaunchArgument(
            "device",
            default_value="cpu",
            description="Inference device, for example cpu or cuda:0.",
        ),
        DeclareLaunchArgument(
            "image_topic",
            default_value="/camera/image_raw",
            description="Input image topic.",
        ),
        DeclareLaunchArgument(
            "detections_topic",
            default_value="/detections",
            description="Output Detection2DArray topic.",
        ),
        LogInfo(msg=[
            "[detector] starting with model=", model_name,
            " device=", device,
            " image_topic=", image_topic,
            " detections_topic=", detections_topic,
        ]),
        Node(
            package="detector_node",
            executable="detector_node",
            name="detector_node",
            output="screen",
            parameters=[
                config_file,
                {
                    "model_name": model_name,
                    "device": device,
                    "image_topic": image_topic,
                    "detections_topic": detections_topic,
                },
            ],
        ),
    ])
