import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

def generate_launch_description():
    pkg_cstam_gazebo = get_package_share_directory('cstam_gazebo')
    pkg_cstam_navigation = get_package_share_directory('cstam_navigation')

    rviz_config_file = os.path.join(pkg_cstam_navigation, 'config', 'slam_demo.rviz')

    # 1. Launch Gazebo Simulation with Restaurant World & BellaBot Robot
    gazebo_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(pkg_cstam_gazebo, 'launch', 'spawn_cstam_robot.launch.py')
        ),
        launch_arguments={
            'world': 'restaurant.world',
            'spawn_x': '7.06',
            'spawn_y': '-12.0',
            'spawn_yaw': '1.57'
        }.items()
    )

    # 2. Launch SLAM Toolbox
    slam_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(pkg_cstam_navigation, 'launch', 'slam.launch.py')
        )
    )

    # 3. Launch RViz2 with SLAM Demo configuration
    rviz_node = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        arguments=['-d', rviz_config_file],
        parameters=[{'use_sim_time': True}],
        output='screen'
    )

    return LaunchDescription([
        gazebo_launch,
        slam_launch,
        rviz_node
    ])
