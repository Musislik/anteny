import subprocess
import sys
import os
import shutil

def run_palace():
    print("Spouštím solver Palace...")
    env = os.environ.copy()
    
    # Spuštění solveru přes Docker Compose (funguje z hostitele i z pipeline kontejneru přes docker.sock)
    docker_compose_bin = shutil.which("docker-compose") or shutil.which("docker-compose.exe")
    docker_bin = shutil.which("docker") or shutil.which("docker.exe")
    
    if not (docker_compose_bin or docker_bin):
        raise RuntimeError("Docker / Docker Compose nebyl nalezen! Simulace může běžet pouze přes Docker.")
        
    cmd = [docker_compose_bin, "run", "--rm", "palace"] if docker_compose_bin else [docker_bin, "compose", "run", "--rm", "palace"]
    
    print(f"Spouštím solver v Dockeru: {' '.join(cmd)}")
    # Odebráno capture_output=True -> logy z Palace se teď budou vypisovat živě do terminálu!
    result = subprocess.run(
        cmd,
        check=True,
        env=env,
        shell=(sys.platform == "win32")
    )
    print("Řešič proběhl úspěšně.")
