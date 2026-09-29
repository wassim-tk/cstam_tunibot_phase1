import os
from ament_index_python.packages import get_package_share_directory, PackageNotFoundError
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, LogInfo
from launch.launch_description_sources import PythonLaunchDescriptionSource

def generate_launch_description():
    pkg_cstam_navigation = get_package_share_directory('cstam_navigation')

    try:
        pkg_nav2_bringup = get_package_share_directory('nav2_bringup')
    except PackageNotFoundError:
        return LaunchDescription([
            LogInfo(
                msg="[WARNING] Package 'nav2_bringup' not found. "
                    "To enable Nav2, install it via: "
                    "sudo apt update && sudo apt install -y ros-jazzy-navigation2 ros-jazzy-nav2-bringup"
            )
        ])

    map_yaml_file = os.path.join(pkg_cstam_navigation, 'maps', 'cstam_map.yaml')
    nav2_params_file = os.path.join(pkg_cstam_navigation, 'config', 'nav2_params.yaml')

    nav2_bringup_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(pkg_nav2_bringup, 'launch', 'bringup_launch.py')
        ),
        launch_arguments={
            'map': map_yaml_file,
            'params_file': nav2_params_file,
            'use_sim_time': 'true',
            'autostart': 'true',
            'use_composition': 'True',
            'use_respawn': 'False',
            'use_namespace': 'false',
            'namespace': '',
            'slam': 'False',
            'use_localization': 'True',
            'log_level': 'info',
        }.items()
    )

    return LaunchDescription([
        nav2_bringup_launch
    ])
