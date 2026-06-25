from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    video_path = LaunchConfiguration("video_path")
    detector_model = LaunchConfiguration("detector_model")
    detector_device = LaunchConfiguration("detector_device")

    image_topic = LaunchConfiguration("image_topic")
    detections_topic = LaunchConfiguration("detections_topic")
    tracks_topic = LaunchConfiguration("tracks_topic")
    overlay_topic = LaunchConfiguration("overlay_topic")

    filtered_detections_topic = LaunchConfiguration("filtered_detections_topic")
    water_roi_topic = LaunchConfiguration("water_roi_topic")
    water_prior_overlay_topic = LaunchConfiguration("water_prior_overlay_topic")

    frame_id = LaunchConfiguration("frame_id")
    loop = LaunchConfiguration("loop")
    publish_rate_hz = LaunchConfiguration("publish_rate_hz")

    enable_tracker = LaunchConfiguration("enable_tracker")
    enable_overlay = LaunchConfiguration("enable_overlay")
    enable_water_prior = LaunchConfiguration("enable_water_prior")

    return LaunchDescription([
        DeclareLaunchArgument(
            "video_path",
            default_value="data/samples/harbor_sample.mp4",
            description="Input video path for ROS2 replay.",
        ),
        DeclareLaunchArgument(
            "detector_model",
            default_value="yolo11n.pt",
            description="Detector model path.",
        ),
        DeclareLaunchArgument(
            "detector_device",
            default_value="cpu",
            description="Detector device.",
        ),
        DeclareLaunchArgument(
            "image_topic",
            default_value="/camera/image_raw",
            description="Replay image topic.",
        ),
        DeclareLaunchArgument(
            "detections_topic",
            default_value="/detections",
            description="Structured detections topic.",
        ),
        DeclareLaunchArgument(
            "tracks_topic",
            default_value="/tracks",
            description="Tracking output topic.",
        ),
        DeclareLaunchArgument(
            "overlay_topic",
            default_value="/debug/overlay_image",
            description="Debug overlay image topic.",
        ),
        DeclareLaunchArgument(
            "filtered_detections_topic",
            default_value="/maritime/filtered_detections",
            description="Water-prior filtered detections topic.",
        ),
        DeclareLaunchArgument(
            "water_roi_topic",
            default_value="/maritime/water_roi",
            description="Water ROI topic.",
        ),
        DeclareLaunchArgument(
            "water_prior_overlay_topic",
            default_value="/debug/water_prior_overlay",
            description="Water prior debug overlay topic.",
        ),
        DeclareLaunchArgument(
            "frame_id",
            default_value="camera_frame",
            description="Frame id for replayed images.",
        ),
        DeclareLaunchArgument(
            "loop",
            default_value="true",
            description="Loop the replay video.",
        ),
        DeclareLaunchArgument(
            "publish_rate_hz",
            default_value="0.0",
            description="Replay publish rate. 0.0 means source FPS.",
        ),
        DeclareLaunchArgument(
            "enable_tracker",
            default_value="true",
            description="Enable tracker node.",
        ),
        DeclareLaunchArgument(
            "enable_overlay",
            default_value="true",
            description="Enable visual overlay node.",
        ),
        DeclareLaunchArgument(
            "enable_water_prior",
            default_value="true",
            description="Enable maritime water prior node.",
        ),

        LogInfo(msg=[
            "[perception_core] video_path=", video_path,
            " detector_model=", detector_model,
            " enable_tracker=", enable_tracker,
            " enable_overlay=", enable_overlay,
            " enable_water_prior=", enable_water_prior,
        ]),

        Node(
            package="replay_tools",
            executable="video_replay_node",
            name="video_replay_node",
            output="screen",
            parameters=[{
                "video_path": video_path,
                "loop": ParameterValue(loop, value_type=bool),
                "publish_rate_hz": ParameterValue(publish_rate_hz, value_type=float),
                "frame_id": frame_id,
                "scenario_name": "perception_core",
                "image_topic": image_topic,
                "debug_topic": "/debug/frame_info",
            }],
        ),

        Node(
            package="detector_node",
            executable="detector_node",
            name="detector_node",
            output="screen",
            parameters=[{
                "model_path": detector_model,
                "model": detector_model,
                "device": detector_device,
                "image_topic": image_topic,
                "detections_topic": detections_topic,
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
            condition=IfCondition(enable_tracker),
            parameters=[{
                "detections_topic": detections_topic,
                "tracks_topic": tracks_topic,
            }],
        ),

        Node(
            package="overlay_node",
            executable="overlay_node",
            name="overlay_node",
            output="screen",
            condition=IfCondition(enable_overlay),
            parameters=[{
                "image_topic": image_topic,
                "detections_topic": detections_topic,
                "tracks_topic": tracks_topic,
                "overlay_topic": overlay_topic,
                "draw_detections": True,
                "draw_tracks": True,
            }],
        ),

        Node(
            package="water_prior_node",
            executable="water_prior_node",
            name="water_prior_node",
            output="screen",
            condition=IfCondition(enable_water_prior),
            parameters=[{
                "image_topic": image_topic,
                "detections_topic": detections_topic,
                "filtered_detections_topic": filtered_detections_topic,
                "water_roi_topic": water_roi_topic,
                "water_prior_overlay_topic": water_prior_overlay_topic,
                "mode": "heuristic",
                "valid_y_min_ratio": 0.30,
                "valid_y_max_ratio": 1.00,
                "filter_policy": "soft",
                "soft_penalty": 0.25,
                "publish_overlay": True,
            }],
        ),
    ])
