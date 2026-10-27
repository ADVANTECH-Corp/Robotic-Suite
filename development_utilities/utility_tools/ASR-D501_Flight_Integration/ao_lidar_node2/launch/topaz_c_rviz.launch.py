import os
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory

def generate_launch_description():
    included_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                get_package_share_directory('ao_lidar_node2'), 
                'launch', 
                'topaz_c.launch.py'
                )
            )
        )
    
    my_package_dir = os.path.join (
                get_package_share_directory('ao_lidar_node2'),   
                'rviz',    
                'aolidar.rviz'
        )
                    
    return LaunchDescription([
        included_launch,
        Node(
                package='rviz2',
                executable='rviz2',
                name='rviz2',
                arguments=['-d',    my_package_dir],
                output='screen'),
    ])