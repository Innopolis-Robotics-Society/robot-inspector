from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    default_resnet = PathJoinSubstitution([
        FindPackageShare("iros_rust_detect_ros"), "onnx_models", "resnet_fp16.onnx"
    ])
    default_unet = PathJoinSubstitution([
        FindPackageShare("iros_rust_detect_ros"), "onnx_models", "unet_fp16.onnx"
    ])

    return LaunchDescription([
        DeclareLaunchArgument("image_topic", default_value="/image_raw"),
        DeclareLaunchArgument("camera_info_topic", default_value="/camera_info"),
        DeclareLaunchArgument("use_camera_info", default_value="false"),
        DeclareLaunchArgument("service_name", default_value="/rust_detect/run"),
        DeclareLaunchArgument("device", default_value="cpu"),
        DeclareLaunchArgument("resnet_onnx", default_value=default_resnet),
        DeclareLaunchArgument("unet_onnx", default_value=default_unet),
        DeclareLaunchArgument("warmup", default_value="0"),
        DeclareLaunchArgument("resnet_thr", default_value="0.5"),
        DeclareLaunchArgument("thr", default_value="0.35"),
        DeclareLaunchArgument("conf_thr", default_value="0.85"),
        DeclareLaunchArgument("mask_thr", default_value="0.5"),
        DeclareLaunchArgument("prob_vis_mode", default_value="invert_glow"),
        DeclareLaunchArgument("log_timing", default_value="true"),

        Node(
            package="iros_rust_detect_ros",
            executable="rust_detect_node",
            name="rust_detect_node",
            output="screen",
            parameters=[{
                "image_topic": LaunchConfiguration("image_topic"),
                "camera_info_topic": LaunchConfiguration("camera_info_topic"),
                "use_camera_info": LaunchConfiguration("use_camera_info"),
                "service_name": LaunchConfiguration("service_name"),
                "device": LaunchConfiguration("device"),
                "resnet_onnx": LaunchConfiguration("resnet_onnx"),
                "unet_onnx": LaunchConfiguration("unet_onnx"),
                "warmup": LaunchConfiguration("warmup"),
                "resnet_thr": LaunchConfiguration("resnet_thr"),
                "thr": LaunchConfiguration("thr"),
                "conf_thr": LaunchConfiguration("conf_thr"),
                "mask_thr": LaunchConfiguration("mask_thr"),
                "prob_vis_mode": LaunchConfiguration("prob_vis_mode"),
                "log_timing": LaunchConfiguration("log_timing"),
            }],
        ),
    ])
