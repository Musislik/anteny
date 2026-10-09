import subprocess
import sys

def run_palace():
    print("Spouštím solver Palace přes Docker Compose...")
    try:
        import os
        env = os.environ.copy()
        docker_path = r"C:\Program Files\Docker\Docker\resources\bin"
        if docker_path not in env["PATH"]:
            env["PATH"] += os.pathsep + docker_path
            
        # Voláme docker-compose up, protože kontejner je jednorázový (spustí command a skončí)
        result = subprocess.run([r"C:\Program Files\Docker\Docker\resources\bin\docker.exe", "compose", "up", "--build", "palace"], check=True, text=True, capture_output=True, env=env)
        print(result.stdout)
    except subprocess.CalledProcessError as e:
        print("Chyba při běhu Palace:")
        print(e.stderr)
        print(e.stdout)
        sys.exit(1)
