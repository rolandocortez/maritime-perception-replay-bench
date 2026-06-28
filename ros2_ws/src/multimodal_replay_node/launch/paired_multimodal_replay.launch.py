from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    manifest = LaunchConfiguration("manifest")
    loop = LaunchConfiguration("loop")

    return LaunchDescription([
        DeclareLaunchArgument(
            "manifest",
            default_value="data/multimodal/hearmyship/prepared/demo_001/manifest.yaml",
            description="Path to a paired audio/video replay manifest.",
        ),
        DeclareLaunchArgument(
            "loop",
            default_value="false",
            description="Loop the sample when it reaches the end.",
        ),
        Node(
            package="multimodal_replay_node",
            executable="paired_replay_node",
            name="paired_multimodal_replay",
            output="screen",
            parameters=[{
                "manifest": manifest,
                "loop": loop,
                "frame_id": "multimodal_replay",
                "raw_image_topic": "/multimodal/video/image_raw",
                "overlay_image_topic": "/multimodal/video/overlay",
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
    ])
