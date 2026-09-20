import os
from ament_index_python.packages import get_package_share_directory, PackageNotFoundError
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, DeclareLaunchArgument, LogInfo
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

def generate_launch_description():
    pkg_cstam_gazebo = get_package_share_directory('cstam_gazebo')
    pkg_cstam_navigation = get_package_share_directory('cstam_navigation')

    # Detect if nav2_bringup is installed
    try:
        get_package_share_directory('nav2_bringup')
        nav2_available = True
    except PackageNotFoundError:
        nav2_available = False

    default_nav = 'true' if nav2_available else 'false'

    # Declare Launch Arguments
    launch_gazebo_arg = DeclareLaunchArgument(
        'launch_gazebo',
        default_value='true',
        description='Launch Gazebo Sim (Harmonic) simulation'
    )

    launch_nav_arg = DeclareLaunchArgument(
        'launch_nav',
        default_value=default_nav,
        description='Launch Nav2 navigation stack (requires ros-jazzy-nav2-bringup)'
    )

    # 1. Gazebo + Robot Spawn Launch (Modern Gazebo / Gz Sim)
    gazebo_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(pkg_cstam_gazebo, 'launch', 'spawn_cstam_robot.launch.py')
        ),
        condition=IfCondition(LaunchConfiguration('launch_gazebo'))
    )

    # 2. Navigation Launch (Nav2 + Map Server)
    nav_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(pkg_cstam_navigation, 'launch', 'navigation.launch.py')
        ),
        condition=IfCondition(LaunchConfiguration('launch_nav'))
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

    launch_items = [
        launch_gazebo_arg,
        launch_nav_arg,
        gazebo_launch,
        nav_launch,
        battery_sim_node,
        task_manager_node,
        docking_controller_node
    ]

    if not nav2_available:
        launch_items.insert(2, LogInfo(
            msg="[CSTAM NOTICE] 'nav2_bringup' is not installed; skipping Nav2 bringup. "
                "To enable full autonomous navigation, install: "
                "sudo apt update && sudo apt install -y ros-jazzy-navigation2 ros-jazzy-nav2-bringup"
        ))

    return LaunchDescription(launch_items)
