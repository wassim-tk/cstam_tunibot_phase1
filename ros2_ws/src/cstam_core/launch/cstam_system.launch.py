import os
from typing import Any, List
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

    # Detect if Gazebo & xacro dependencies are installed
    try:
        import xacro  # noqa: F401
        get_package_share_directory('ros_gz_sim')
        get_package_share_directory('ros_gz_bridge')
        gazebo_available = True
    except (ImportError, PackageNotFoundError):
        gazebo_available = False

    default_gazebo = 'true' if gazebo_available else 'false'
    default_sim_time = 'true' if gazebo_available else 'false'

    # Declare Launch Arguments
    launch_gazebo_arg = DeclareLaunchArgument(
        'launch_gazebo',
        default_value=default_gazebo,
        description='Launch Gazebo Sim (Harmonic) simulation'
    )

    launch_nav_arg = DeclareLaunchArgument(
        'launch_nav',
        default_value=default_nav,
        description='Launch Nav2 navigation stack (requires ros-jazzy-nav2-bringup)'
    )

    launch_world_arg = DeclareLaunchArgument(
        'world',
        default_value='restaurant.world',
        description='World file name (in worlds/ directory) or absolute path'
    )

    launch_use_sim_time_arg = DeclareLaunchArgument(
        'use_sim_time',
        default_value=default_sim_time,
        description='Use simulation (Gazebo) clock if true'
    )

    launch_spawn_x_arg = DeclareLaunchArgument(
        'spawn_x',
        default_value='-14.0',
        description='X coordinate for robot spawn'
    )

    launch_spawn_y_arg = DeclareLaunchArgument(
        'spawn_y',
        default_value='-2.0',
        description='Y coordinate for robot spawn'
    )

    launch_spawn_z_arg = DeclareLaunchArgument(
        'spawn_z',
        default_value='0.1',
        description='Z coordinate for robot spawn'
    )

    # 1. Gazebo + Robot Spawn Launch (Modern Gazebo / Gz Sim)
    gazebo_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(pkg_cstam_gazebo, 'launch', 'spawn_cstam_robot.launch.py')
        ),
        launch_arguments={
            'world': LaunchConfiguration('world', default='restaurant.world'),
            'spawn_x': LaunchConfiguration('spawn_x', default='-14.0'),
            'spawn_y': LaunchConfiguration('spawn_y', default='-2.0'),
            'spawn_z': LaunchConfiguration('spawn_z', default='0.1'),
        }.items(),
        condition=IfCondition(LaunchConfiguration('launch_gazebo', default=default_gazebo))
    )

    # 2. Navigation Launch (Nav2 + Map Server)
    nav_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(pkg_cstam_navigation, 'launch', 'navigation.launch.py')
        ),
        condition=IfCondition(LaunchConfiguration('launch_nav', default=default_nav))
    )

    # 3. Battery Simulator Node
    battery_sim_node = Node(
        package='cstam_core',
        executable='battery_simulator',
        name='battery_simulator',
        parameters=[{'use_sim_time': LaunchConfiguration('use_sim_time')}],
        output='screen'
    )

    # 4. Delivery Task Manager Node
    task_manager_node = Node(
        package='cstam_core',
        executable='delivery_task_manager',
        name='delivery_task_manager',
        parameters=[{'use_sim_time': LaunchConfiguration('use_sim_time')}],
        output='screen'
    )

    # 5. Docking Controller Node
    docking_controller_node = Node(
        package='cstam_core',
        executable='docking_controller',
        name='docking_controller',
        parameters=[{'use_sim_time': LaunchConfiguration('use_sim_time')}],
        output='screen'
    )

    launch_items: List[Any] = [
        launch_world_arg,
        launch_gazebo_arg,
        launch_nav_arg,
        launch_use_sim_time_arg,
        launch_spawn_x_arg,
        launch_spawn_y_arg,
        launch_spawn_z_arg,
        gazebo_launch,
        nav_launch,
        battery_sim_node,
        task_manager_node,
        docking_controller_node
    ]

    if not gazebo_available:
        launch_items.insert(0, LogInfo(
            msg="[CSTAM NOTICE] Gazebo simulation dependencies ('xacro', 'ros_gz_sim', 'ros_gz_bridge') "
                "are not installed; skipping Gazebo bringup. "
                "To enable 3D simulation and robot spawning, install: "
                "sudo apt update && sudo apt install -y ros-jazzy-xacro ros-jazzy-ros-gz"
        ))

    if not nav2_available:
        launch_items.insert(2, LogInfo(
            msg="[CSTAM NOTICE] 'nav2_bringup' is not installed; skipping Nav2 bringup. "
                "To enable full autonomous navigation, install: "
                "sudo apt update && sudo apt install -y ros-jazzy-navigation2 ros-jazzy-nav2-bringup"
        ))

    return LaunchDescription(launch_items)
