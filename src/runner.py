import subprocess
import sys
import os
import shutil

def run_palace():
    print("Starting Palace solver...")
    env = os.environ.copy()
    
    # Run the solver via Docker Compose (works from host as well as pipeline container via docker.sock)
    docker_compose_bin = shutil.which("docker-compose") or shutil.which("docker-compose.exe")
    docker_bin = shutil.which("docker") or shutil.which("docker.exe")
    
    if not (docker_compose_bin or docker_bin):
        raise RuntimeError("Docker / Docker Compose not found! Simulation can only run via Docker.")
        
    cmd = (
        [docker_compose_bin, "--profile", "worker", "run", "--rm", "palace"]
        if docker_compose_bin
        else [docker_bin, "compose", "--profile", "worker", "run", "--rm", "palace"]
    )
    
    print(f"Starting solver in Docker: {' '.join(cmd)}")
    # Removed capture_output=True -> Palace logs will now stream live to the terminal!
    result = subprocess.run(
        cmd,
        check=True,
        env=env,
        shell=(sys.platform == "win32")
    )
    print("Solver finished successfully.")
