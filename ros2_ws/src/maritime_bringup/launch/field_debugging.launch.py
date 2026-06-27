import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, LogInfo, OpaqueFunction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


TRUE_VALUES = {"1", "true", "yes", "on"}

FAULT_PROFILES = {
    "frame_drop_15": {
        "mode": "frame_drop",
        "drop_probability": 0.15,
    },
    "blur_medium": {
        "mode": "visual_degradation",
        "visual_mode": "blur",
        "blur_kernel": 7,
    },
    "delay_100ms": {
        "mode": "delay",
        "delay_ms": 100.0,
        "jitter_ms": 20.0,
    },
    "glare_approx": {
        "mode": "visual_degradation",
        "visual_mode": "glare",
        "brightness_delta": 20.0,
        "contrast_alpha": 1.2,
        "glare_enabled": True,
        "glare_strength": 0.30,
    },
}


def as_bool(value):
    return str(value).lower() in TRUE_VALUES


def launch_setup(context, *args, **kwargs):
    video_path = LaunchConfiguration("video_path").perform(context)
    detector_model = LaunchConfiguration("detector_model").perform(context)
    detector_device = LaunchConfiguration("detector_device").perform(context)
    enable_faults = as_bool(LaunchConfiguration("enable_faults").perform(context))
    enable_metrics = as_bool(LaunchConfiguration("enable_metrics").perform(context))
    enable_acoustic = as_bool(LaunchConfiguration("enable_acoustic").perform(context))
    fault_profile = LaunchConfiguration("fault_profile").perform(context)

    actions = []

    profile = FAULT_PROFILES.get(fault_profile, {})
    effective_faults = enable_faults and fault_profile != "none" and bool(profile)

    perception_launch = os.path.join(
        get_package_share_directory("maritime_bringup"),
        "launch",
        "perception_core.launch.py",
    )

    actions.append(
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(perception_launch),
            launch_arguments={
                "video_path": video_path,
                "detector_model": detector_model,
                "detector_device": detector_device,
                "enable_faults": "true" if effective_faults else "false",
            }.items(),
        )
    )

    if effective_faults:
        fault_params = {
            "input_image_topic": "/camera/image_raw",
            "output_image_topic": "/faults/image_raw",
            "status_topic": "/debug/fault_injection_status",
            "mode": profile.get("mode", "frame_drop"),
            "visual_mode": profile.get("visual_mode", "blur"),
            "drop_probability": float(profile.get("drop_probability", 0.15)),
            "blur_kernel": int(profile.get("blur_kernel", 7)),
            "jpeg_quality": int(profile.get("jpeg_quality", 45)),
            "brightness_delta": float(profile.get("brightness_delta", 20.0)),
            "contrast_alpha": float(profile.get("contrast_alpha", 1.2)),
            "glare_enabled": bool(profile.get("glare_enabled", True)),
            "glare_strength": float(profile.get("glare_strength", 0.25)),
            "noise_sigma": float(profile.get("noise_sigma", 8.0)),
            "delay_ms": float(profile.get("delay_ms", 100.0)),
            "jitter_ms": float(profile.get("jitter_ms", 20.0)),
            "deterministic": True,
            "random_seed": 42,
        }

        actions.append(
            LogInfo(msg=f"[field_debugging] fault_profile={fault_profile} params={fault_params}")
        )
        actions.append(
            Node(
                package="fault_injector_node",
                executable="fault_injector_node",
                name="fault_injector_node",
                output="screen",
                parameters=[fault_params],
            )
        )
    else:
        actions.append(LogInfo(msg="[field_debugging] running clean pipeline without fault injector"))

    if enable_metrics:
        metrics_launch = os.path.join(
            get_package_share_directory("metrics_node"),
            "launch",
            "metrics.launch.py",
        )
        actions.append(
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(metrics_launch),
            )
        )

    if enable_acoustic:
        actions.append(LogInfo(msg="[field_debugging] optional acoustic lane requested"))
        actions.append(
            Node(
                package="spectrogram_node",
                executable="spectrogram_node",
                name="spectrogram_node",
                output="screen",
            )
        )

    return actions


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument(
            "video_path",
            default_value="data/samples/harbor_sample.mp4",
            description="Replay video path.",
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
            "enable_faults",
            default_value="false",
            description="Enable fault injector and route perception through /faults/image_raw.",
        ),
        DeclareLaunchArgument(
            "fault_profile",
            default_value="none",
            description="Fault profile: none, frame_drop_15, blur_medium, delay_100ms, glare_approx.",
        ),
        DeclareLaunchArgument(
            "enable_metrics",
            default_value="true",
            description="Start runtime/timing metrics node.",
        ),
        DeclareLaunchArgument(
            "enable_acoustic",
            default_value="false",
            description="Start optional acoustic lane components.",
        ),
        OpaqueFunction(function=launch_setup),
    ])
