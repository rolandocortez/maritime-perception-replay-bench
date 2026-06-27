import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, LogInfo
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    oak_launch = os.path.join(
        get_package_share_directory("oak_ingest"),
        "launch",
        "oak_ingest.launch.py",
    )

    metrics_launch = os.path.join(
        get_package_share_directory("metrics_node"),
        "launch",
        "metrics.launch.py",
    )

    detector_model = LaunchConfiguration("detector_model")
    detector_device = LaunchConfiguration("detector_device")
    image_topic = LaunchConfiguration("image_topic")
    camera_info_topic = LaunchConfiguration("camera_info_topic")
    enable_metrics = LaunchConfiguration("enable_metrics")
    rgb_resolution = LaunchConfiguration("rgb_resolution")
    fps = LaunchConfiguration("fps")

    return LaunchDescription([
        DeclareLaunchArgument("detector_model", default_value="yolo11n.pt"),
        DeclareLaunchArgument("detector_device", default_value="cpu"),
        DeclareLaunchArgument("image_topic", default_value="/oak/rgb/image_raw"),
        DeclareLaunchArgument("camera_info_topic", default_value="/oak/rgb/camera_info"),
        DeclareLaunchArgument("rgb_resolution", default_value="1080p"),
        DeclareLaunchArgument("fps", default_value="30.0"),
        DeclareLaunchArgument("enable_metrics", default_value="true"),

        LogInfo(msg=[
            "[oak_live_perception] starting live OAK perception pipeline",
            " image_topic=", image_topic,
            " detector_model=", detector_model,
            " detector_device=", detector_device,
        ]),

        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(oak_launch),
            launch_arguments={
                "rgb_resolution": rgb_resolution,
                "fps": fps,
                "remap_to_standard_camera_topics": "false",
            }.items(),
        ),

        Node(
            package="detector_node",
            executable="detector_node",
            name="detector_node",
            output="screen",
            parameters=[{
                "backend": "ultralytics",
                "model": detector_model,
                "device": detector_device,
                "image_topic": image_topic,
                "detections_topic": "/detections",
                "detections_debug_topic": "/detections/debug_json",
                "confidence_threshold": 0.25,
                "iou_threshold": 0.45,
            }],
        ),

        Node(
            package="tracker_node",
            executable="tracker_node",
            name="tracker_node",
            output="screen",
            parameters=[{
                "tracker_type": "iou",
                "detections_topic": "/detections",
                "tracks_topic": "/tracks",
                "iou_match_threshold": 0.3,
                "max_age_frames": 15,
                "min_hits": 2,
                "class_aware": True,
            }],
        ),

        Node(
            package="overlay_node",
            executable="overlay_node",
            name="overlay_node",
            output="screen",
            parameters=[{
                "image_topic": image_topic,
                "detections_topic": "/detections",
                "tracks_topic": "/tracks",
                "overlay_topic": "/debug/overlay_image",
                "draw_detections": True,
                "draw_tracks": True,
                "max_sync_delta_ms": 150.0,
            }],
        ),

        Node(
            package="water_prior_node",
            executable="water_prior_node",
            name="water_prior_node",
            output="screen",
            parameters=[{
                "mode": "heuristic",
                "image_topic": image_topic,
                "detections_topic": "/detections",
                "filtered_detections_topic": "/maritime/filtered_detections",
                "water_roi_topic": "/maritime/water_roi",
                "water_prior_overlay_topic": "/debug/water_prior_overlay",
                "valid_y_min_ratio": 0.3,
                "valid_y_max_ratio": 1.0,
                "filter_policy": "soft",
                "soft_penalty": 0.25,
            }],
        ),

        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(metrics_launch),
            launch_arguments={}.items(),
            condition=None,
        ),
    ])
