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

    drop_probability = LaunchConfiguration("drop_probability")
    deterministic = LaunchConfiguration("deterministic")
    random_seed = LaunchConfiguration("random_seed")

    return LaunchDescription([
        DeclareLaunchArgument(
            "drop_probability",
            default_value="0.15",
            description="Probability of dropping each incoming frame.",
        ),
        DeclareLaunchArgument(
            "deterministic",
            default_value="true",
            description="Use deterministic random seed.",
        ),
        DeclareLaunchArgument(
            "random_seed",
            default_value="42",
            description="Random seed for deterministic frame drops.",
        ),
        LogInfo(msg=[
            "[fault_injector] starting deterministic frame-drop injector",
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
                    "drop_probability": ParameterValue(drop_probability, value_type=float),
                    "deterministic": ParameterValue(deterministic, value_type=bool),
                    "random_seed": ParameterValue(random_seed, value_type=int),
                },
            ],
        ),
    ])
