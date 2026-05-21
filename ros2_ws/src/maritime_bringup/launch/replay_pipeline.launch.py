from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.substitutions import LaunchConfiguration


def generate_launch_description():
    video_path = LaunchConfiguration("video_path")
    scenario_name = LaunchConfiguration("scenario_name")
    use_sim_time = LaunchConfiguration("use_sim_time")
    loop = LaunchConfiguration("loop")

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
            default_value="true",
            description="Whether nodes should use simulated time.",
        ),
        DeclareLaunchArgument(
            "loop",
            default_value="false",
            description="Whether the replay source should loop.",
        ),
        LogInfo(msg=[
            "[replay_pipeline] configured video_path=", video_path,
            " scenario_name=", scenario_name,
            " use_sim_time=", use_sim_time,
            " loop=", loop,
        ]),
        LogInfo(msg=[
            "[replay_pipeline] scaffold only: replay/detector/tracker nodes will be added in later milestones."
        ]),
    ])
