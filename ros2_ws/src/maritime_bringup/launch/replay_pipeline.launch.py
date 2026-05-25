from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    video_path = LaunchConfiguration("video_path")
    scenario_name = LaunchConfiguration("scenario_name")
    use_sim_time = LaunchConfiguration("use_sim_time")
    loop = LaunchConfiguration("loop")
    publish_rate_hz = LaunchConfiguration("publish_rate_hz")
    frame_id = LaunchConfiguration("frame_id")

    return LaunchDescription([
        DeclareLaunchArgument(
            "video_path",
            default_value="data/samples/harbor_sample.mp4",
            description="Path to the local video file used by the replay pipeline.",
        ),
        DeclareLaunchArgument(
            "scenario_name",
            default_value="clean_replay",
            description="Scenario name attached to replay/debug metadata.",
        ),
        DeclareLaunchArgument(
            "use_sim_time",
            default_value="false",
            description="Whether nodes should use simulated time.",
        ),
        DeclareLaunchArgument(
            "loop",
            default_value="false",
            description="Whether the replay source should loop.",
        ),
        DeclareLaunchArgument(
            "publish_rate_hz",
            default_value="0.0",
            description="Override publish rate. Use 0.0 to use the source video FPS.",
        ),
        DeclareLaunchArgument(
            "frame_id",
            default_value="camera_frame",
            description="Frame id used in published image headers.",
        ),
        LogInfo(msg=[
            "[replay_pipeline] starting video replay: video_path=", video_path,
            " scenario_name=", scenario_name,
            " use_sim_time=", use_sim_time,
            " loop=", loop,
            " publish_rate_hz=", publish_rate_hz,
            " frame_id=", frame_id,
        ]),
        Node(
            package="replay_tools",
            executable="video_replay_node",
            name="video_replay_node",
            output="screen",
            parameters=[{
                "video_path": video_path,
                "scenario_name": scenario_name,
                "use_sim_time": use_sim_time,
                "loop": loop,
                "publish_rate_hz": publish_rate_hz,
                "frame_id": frame_id,
            }],
        ),
    ])
