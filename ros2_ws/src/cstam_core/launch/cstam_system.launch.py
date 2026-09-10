import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, DeclareLaunchArgument, ExecuteProcess
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node

def generate_launch_description():
    pkg_cstam_gazebo = get_package_share_directory('cstam_gazebo')
    pkg_cstam_navigation = get_package_share_directory('cstam_navigation')
    
    # 1. Gazebo + Robot Spawn Launch
    gazebo_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(pkg_cstam_gazebo, 'launch', 'spawn_cstam_robot.launch.py')
        )
    )

    # 2. Navigation Launch (Nav2 + Map Server)
    nav_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(pkg_cstam_navigation, 'launch', 'navigation.launch.py')
        )
    )

    # 3. Battery Simulator Node
    battery_sim_node = Node(
        package='cstam_core',
        executable='battery_simulator',
        name='battery_simulator',
        output='screen'
    )

    # 4. Delivery Task Manager Node
    task_manager_node = Node(
        package='cstam_core',
        executable='delivery_task_manager',
        name='delivery_task_manager',
        output='screen'
    )

    # 5. Docking Controller Node
    docking_controller_node = Node(
        package='cstam_core',
        executable='docking_controller',
        name='docking_controller',
        output='screen'
    )

    return LaunchDescription([
        gazebo_launch,
        nav_launch,
        battery_sim_node,
        task_manager_node,
        docking_controller_node
    ])
