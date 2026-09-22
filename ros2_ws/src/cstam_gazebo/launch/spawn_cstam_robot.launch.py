import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, AppendEnvironmentVariable
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
import xacro

def generate_launch_description():
    pkg_cstam_gazebo = get_package_share_directory('cstam_gazebo')
    pkg_ros_gz_sim = get_package_share_directory('ros_gz_sim')

    # Launch Arguments
    world_arg = DeclareLaunchArgument(
        'world',
        default_value='restaurant.world',
        description='World file name (in worlds/ directory) or absolute path'
    )
    spawn_x_arg = DeclareLaunchArgument(
        'spawn_x',
        default_value='-14.0',
        description='X coordinate for robot spawn'
    )
    spawn_y_arg = DeclareLaunchArgument(
        'spawn_y',
        default_value='-2.0',
        description='Y coordinate for robot spawn'
    )
    spawn_z_arg = DeclareLaunchArgument(
        'spawn_z',
        default_value='0.1',
        description='Z coordinate for robot spawn'
    )

    # Ensure Gazebo Sim finds 3D models (both in installed share and source directories)
    installed_models_path = os.path.join(pkg_cstam_gazebo, 'models')
    src_models_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'models'))
    pkg_share_parent = os.path.dirname(pkg_cstam_gazebo)
    models_env = f"{installed_models_path}:{src_models_path}:{pkg_cstam_gazebo}:{pkg_share_parent}"

    set_env_action = AppendEnvironmentVariable(
        name='GZ_SIM_RESOURCE_PATH',
        value=models_env
    )

    xacro_file = os.path.join(pkg_cstam_gazebo, 'urdf', 'cstam_robot.urdf.xacro')
    doc = xacro.parse(open(xacro_file))
    xacro.process_doc(doc)
    robot_description_config = doc.toxml()

    robot_state_publisher_node = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        output='screen',
        parameters=[{
            'robot_description': robot_description_config,
            'use_sim_time': True
        }]
    )

    # Launch Gazebo Sim (Harmonic)
    gazebo_cmd = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(pkg_ros_gz_sim, 'launch', 'gz_sim.launch.py')
        ),
        launch_arguments={
            'gz_args': ['-r ', PathJoinSubstitution([pkg_cstam_gazebo, 'worlds', LaunchConfiguration('world')])]
        }.items()
    )

    # Spawn entity using ros_gz_sim create
    spawn_entity_node = Node(
        package='ros_gz_sim',
        executable='create',
        arguments=[
            '-topic', 'robot_description',
            '-name', 'cstam_robot',
            '-x', LaunchConfiguration('spawn_x'),
            '-y', LaunchConfiguration('spawn_y'),
            '-z', LaunchConfiguration('spawn_z')
        ],
        output='screen'
    )

    # ROS 2 <-> Gazebo Bridge
    bridge_node = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        arguments=[
            '/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock',
            '/cmd_vel@geometry_msgs/msg/Twist@gz.msgs.Twist',
            '/odom@nav_msgs/msg/Odometry[gz.msgs.Odometry',
            '/scan@sensor_msgs/msg/LaserScan[gz.msgs.LaserScan',
            '/tf@tf2_msgs/msg/TFMessage[gz.msgs.Pose_V',
        ],
        output='screen'
    )

    return LaunchDescription([
        world_arg,
        spawn_x_arg,
        spawn_y_arg,
        spawn_z_arg,
        set_env_action,
        gazebo_cmd,
        robot_state_publisher_node,
        spawn_entity_node,
        bridge_node
    ])
