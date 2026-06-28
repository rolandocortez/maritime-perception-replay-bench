from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    manifest = LaunchConfiguration("manifest")
    loop = LaunchConfiguration("loop")
    detector_model = LaunchConfiguration("detector_model")
    detector_device = LaunchConfiguration("detector_device")
    confidence_threshold = LaunchConfiguration("confidence_threshold")
    iou_threshold = LaunchConfiguration("iou_threshold")

    image_topic = LaunchConfiguration("image_topic")
    detections_topic = LaunchConfiguration("detections_topic")
    detections_debug_topic = LaunchConfiguration("detections_debug_topic")
    tracks_topic = LaunchConfiguration("tracks_topic")
    perception_overlay_topic = LaunchConfiguration("perception_overlay_topic")
    status_overlay_topic = LaunchConfiguration("status_overlay_topic")

    return LaunchDescription([
        DeclareLaunchArgument(
            "manifest",
            default_value="data/multimodal/hearmyship/prepared/demo_001/manifest.yaml",
            description="Path to a paired HearMyShip manifest.",
        ),
        DeclareLaunchArgument("loop", default_value="true"),
        DeclareLaunchArgument("detector_model", default_value="yolo11n.pt"),
        DeclareLaunchArgument("detector_device", default_value="cpu"),
        DeclareLaunchArgument(
            "confidence_threshold",
            default_value="0.10",
            description="Lower than normal because HearMyShip demo boats can be small in frame.",
        ),
        DeclareLaunchArgument("iou_threshold", default_value="0.45"),
        DeclareLaunchArgument("image_topic", default_value="/multimodal/video/image_raw"),
        DeclareLaunchArgument("detections_topic", default_value="/multimodal/detections"),
        DeclareLaunchArgument("detections_debug_topic", default_value="/multimodal/detections/debug_json"),
        DeclareLaunchArgument("tracks_topic", default_value="/multimodal/tracks"),
        DeclareLaunchArgument("perception_overlay_topic", default_value="/multimodal/video/perception_overlay"),
        DeclareLaunchArgument("status_overlay_topic", default_value="/multimodal/video/status_overlay"),

        LogInfo(msg=[
            "[paired_multimodal_perception] manifest=", manifest,
            " image_topic=", image_topic,
            " detections_topic=", detections_topic,
            " tracks_topic=", tracks_topic,
            " detector_model=", detector_model,
            " confidence_threshold=", confidence_threshold,
        ]),

        Node(
            package="multimodal_replay_node",
            executable="paired_replay_node",
            name="paired_multimodal_replay",
            output="screen",
            parameters=[{
                "manifest": manifest,
                "loop": ParameterValue(loop, value_type=bool),
                "frame_id": "multimodal_replay",
                "raw_image_topic": image_topic,
                "overlay_image_topic": status_overlay_topic,
                "waveform_topic": "/acoustic/waveform",
                "activity_topic": "/acoustic/activity",
                "fusion_debug_topic": "/fusion/debug_json",
                "contact_candidates_topic": "/fusion/contact_candidates",
                "audio_window_sec": 0.25,
                "degradation_start_sec": 4.0,
                "degradation_end_sec": 7.0,
                "normal_visual_confidence": 0.92,
                "degraded_visual_confidence": 0.35,
                "apply_visual_degradation": True,
            }],
        ),

        Node(
            package="detector_node",
            executable="detector_node",
            name="multimodal_detector_node",
            output="screen",
            parameters=[{
                "model_name": detector_model,
                "model": detector_model,
                "model_path": detector_model,
                "device": detector_device,
                "image_topic": image_topic,
                "detections_topic": detections_topic,
                "detections_debug_topic": detections_debug_topic,
                "confidence_threshold": ParameterValue(confidence_threshold, value_type=float),
                "iou_threshold": ParameterValue(iou_threshold, value_type=float),
                "publish_debug_json": True,
                "max_detections": 100,
                "class_filter_enabled": False,
                "log_every_n_frames": 25,
            }],
        ),

        Node(
            package="tracker_node",
            executable="tracker_node",
            name="multimodal_tracker_node",
            output="screen",
            parameters=[{
                "detections_topic": detections_topic,
                "tracks_topic": tracks_topic,
                "tracker_type": "iou",
                "iou_match_threshold": 0.3,
                "max_age_frames": 15,
                "min_hits": 2,
                "class_aware": True,
                "log_every_n_frames": 25,
            }],
        ),

        Node(
            package="overlay_node",
            executable="overlay_node",
            name="multimodal_perception_overlay_node",
            output="screen",
            parameters=[{
                "image_topic": image_topic,
                "detections_topic": detections_topic,
                "tracks_topic": tracks_topic,
                "overlay_topic": perception_overlay_topic,
                "draw_detections": True,
                "draw_tracks": True,
                "draw_confidence": True,
                "draw_track_age": True,
                "max_sync_delta_ms": 300.0,
                "publish_on_image": True,
                "log_every_n_frames": 25,
            }],
        ),
    ])
