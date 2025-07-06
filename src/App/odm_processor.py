import subprocess
import os

def run_odm(image_dir):
    """Run OpenDroneMap in Docker."""
    try:
        # Convert Windows path to Docker-friendly path
        docker_path = image_dir.replace("\\", "/").replace("C:", "/c")
        
        subprocess.run([
            "docker", "run", "-it", "--rm",
            "-v", f"{docker_path}:/datasets/code",
            "opendronemap/odm",
            "--orthophoto-resolution", "5",
            "--feature-quality", "high"
        ], check=True)
    except subprocess.CalledProcessError as e:
        raise Exception(f"ODM Docker failed: {e}")
    