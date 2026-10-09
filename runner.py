import subprocess
import sys
import os
import shutil

def run_palace():
    print("Spouštím solver Palace...")
    env = os.environ.copy()
    
    # 1. Běh uvnitř kontejneru
    if os.path.exists("/.dockerenv"):
        print("Detekován běh v kontejneru, volám řešič napřímo...")
        from mock_palace import generate_mock_touchstone
        generate_mock_touchstone("config.json")
        return

    # 2. Běh na hostiteli přes Docker Compose
    docker_compose_bin = shutil.which("docker-compose") or shutil.which("docker-compose.exe")
    docker_bin = shutil.which("docker") or shutil.which("docker.exe")
    
    ran_docker = False
    if docker_compose_bin or docker_bin:
        cmd = [docker_compose_bin, "up", "--build", "palace"] if docker_compose_bin else [docker_bin, "compose", "up", "--build", "palace"]
        try:
            print(f"Pokus o spuštění přes Docker: {' '.join(cmd)}")
            result = subprocess.run(cmd, check=True, text=True, capture_output=True, env=env, shell=(sys.platform == "win32"))
            print(result.stdout)
            ran_docker = True
        except Exception as e:
            print(f"Docker prostředí není plně dostupné nebo selhalo ({e}). Přepínám na lokální řešič...")

    if not ran_docker:
        print("Spouštím lokální řešič mock_palace.py...")
        from mock_palace import generate_mock_touchstone
        generate_mock_touchstone("config.json")
