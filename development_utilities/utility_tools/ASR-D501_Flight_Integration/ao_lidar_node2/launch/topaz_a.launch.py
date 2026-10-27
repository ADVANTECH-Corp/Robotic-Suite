from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument(
            name='topic_name', 
            default_value='/scan',
            description='Topaz_A Topic'
        ),
        DeclareLaunchArgument(
            name='lidar_frame', 
            default_value='laser',
            description='Lidar Frame ID'
        ),
        DeclareLaunchArgument(
            name='serial_port', 
            default_value='/dev/ttyACM0',
            description='Lidar Serial Port'
        ),
        DeclareLaunchArgument(
            name='baudrate', 
            default_value='921600',
            description='Lidar Serial Baudrate'
        ),
        DeclareLaunchArgument(
            name='scanning_frequency', 
            default_value='10.0',
            description='Lidar Scanning Frequency'
        ),
        DeclareLaunchArgument(
            name='points_per_second', 
            default_value='10800',
            description='Points Per Second'
        ),
        DeclareLaunchArgument(
            name='angle_min', 
            default_value='-180.0',
            description='Angle Min'
        ),
        DeclareLaunchArgument(
            name='angle_max', 
            default_value='180.0',
            description='Angle Max'
        ),
        DeclareLaunchArgument(
            name='range_min', 
            default_value='0.06',
            description='Range Min'
        ),
        DeclareLaunchArgument(
            name='range_max', 
            default_value='15.0',
            description='Range Max'
        ),
        DeclareLaunchArgument(
            name='angle_align', 
            default_value='0.0',
            description='Angle Align'
        ),
        DeclareLaunchArgument(
            name='intensity_on', 
            default_value='1',
            description='Intensity On'
        ),
        Node(
            package='ao_lidar_node2',
            executable='ao_topaz_lidar',
            name='aolidar',
            output='screen',
            emulate_tty=True,
            parameters=[
                {'topic_name': LaunchConfiguration("topic_name")},
                {'lidar_frame': LaunchConfiguration("lidar_frame")},
                {'serial_port': LaunchConfiguration("serial_port")},
                {'baudrate': LaunchConfiguration("baudrate")},
                {'scanning_frequency': LaunchConfiguration("scanning_frequency")},
                {'points_per_second': LaunchConfiguration("points_per_second")},
                {'angle_min': LaunchConfiguration("angle_min")},
                {'angle_max': LaunchConfiguration("angle_max")},
                {'range_min': LaunchConfiguration("range_min")},
                {'range_max': LaunchConfiguration("range_max")},
                {'angle_align': LaunchConfiguration("angle_align")},
                {'intensity_on': LaunchConfiguration("intensity_on")},
            ]
        )
    ])