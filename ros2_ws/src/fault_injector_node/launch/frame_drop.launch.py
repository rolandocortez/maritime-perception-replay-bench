import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    config_path = os.path.join(
        get_package_share_directory("fault_injector_node"),
        "config",
        "frame_drop.yaml",
    )

    mode = LaunchConfiguration("mode")
    visual_mode = LaunchConfiguration("visual_mode")
    drop_probability = LaunchConfiguration("drop_probability")
    deterministic = LaunchConfiguration("deterministic")
    random_seed = LaunchConfiguration("random_seed")
    blur_kernel = LaunchConfiguration("blur_kernel")
    jpeg_quality = LaunchConfiguration("jpeg_quality")
    brightness_delta = LaunchConfiguration("brightness_delta")
    contrast_alpha = LaunchConfiguration("contrast_alpha")
    glare_enabled = LaunchConfiguration("glare_enabled")
    glare_strength = LaunchConfiguration("glare_strength")
    noise_sigma = LaunchConfiguration("noise_sigma")
    delay_ms = LaunchConfiguration("delay_ms")
    jitter_ms = LaunchConfiguration("jitter_ms")
    max_delay_queue = LaunchConfiguration("max_delay_queue")
    delay_timer_period_ms = LaunchConfiguration("delay_timer_period_ms")

    return LaunchDescription([
        DeclareLaunchArgument("mode", default_value="frame_drop"),
        DeclareLaunchArgument("visual_mode", default_value="blur"),
        DeclareLaunchArgument("drop_probability", default_value="0.15"),
        DeclareLaunchArgument("deterministic", default_value="true"),
        DeclareLaunchArgument("random_seed", default_value="42"),
        DeclareLaunchArgument("blur_kernel", default_value="7"),
        DeclareLaunchArgument("jpeg_quality", default_value="45"),
        DeclareLaunchArgument("brightness_delta", default_value="20.0"),
        DeclareLaunchArgument("contrast_alpha", default_value="1.2"),
        DeclareLaunchArgument("glare_enabled", default_value="true"),
        DeclareLaunchArgument("glare_strength", default_value="0.25"),
        DeclareLaunchArgument("noise_sigma", default_value="8.0"),
        DeclareLaunchArgument("delay_ms", default_value="100.0"),
        DeclareLaunchArgument("jitter_ms", default_value="20.0"),
        DeclareLaunchArgument("max_delay_queue", default_value="500"),
        DeclareLaunchArgument("delay_timer_period_ms", default_value="5.0"),
        LogInfo(msg=[
            "[fault_injector] starting injector",
            " mode=", mode,
            " visual_mode=", visual_mode,
            " delay_ms=", delay_ms,
            " jitter_ms=", jitter_ms,
            " drop_probability=", drop_probability,
            " deterministic=", deterministic,
            " random_seed=", random_seed,
        ]),
        Node(
            package="fault_injector_node",
            executable="fault_injector_node",
            name="fault_injector_node",
            output="screen",
            parameters=[
                config_path,
                {
                    "mode": mode,
                    "visual_mode": visual_mode,
                    "drop_probability": ParameterValue(drop_probability, value_type=float),
                    "deterministic": ParameterValue(deterministic, value_type=bool),
                    "random_seed": ParameterValue(random_seed, value_type=int),
                    "blur_kernel": ParameterValue(blur_kernel, value_type=int),
                    "jpeg_quality": ParameterValue(jpeg_quality, value_type=int),
                    "brightness_delta": ParameterValue(brightness_delta, value_type=float),
                    "contrast_alpha": ParameterValue(contrast_alpha, value_type=float),
                    "glare_enabled": ParameterValue(glare_enabled, value_type=bool),
                    "glare_strength": ParameterValue(glare_strength, value_type=float),
                    "noise_sigma": ParameterValue(noise_sigma, value_type=float),
                    "delay_ms": ParameterValue(delay_ms, value_type=float),
                    "jitter_ms": ParameterValue(jitter_ms, value_type=float),
                    "max_delay_queue": ParameterValue(max_delay_queue, value_type=int),
                    "delay_timer_period_ms": ParameterValue(delay_timer_period_ms, value_type=float),
                },
            ],
        ),
    ])
