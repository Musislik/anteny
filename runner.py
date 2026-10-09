import subprocess
import sys

def run_palace():
    print("Spouštím solver Palace přes Docker Compose...")
    try:
        import os
        env = os.environ.copy()
        
        # Pokud běžíme uvnitř kontejneru (Docker in Docker by špatně namapoval cesty z hostitele), 
        # spustíme rovnou mock solver napřímo (v produkci by zde bylo volání MPI apod.)
        if os.path.exists("/.dockerenv"):
            print("Detekován běh v kontejneru, volám řešič napřímo...")
            cmd = ["python", "mock_palace.py", "config.json"]
        else:
            import shutil
            if shutil.which("docker-compose"):
                cmd = ["docker-compose", "up", "--build", "palace"]
            else:
                cmd = ["docker", "compose", "up", "--build", "palace"]
        
        # Voláme solver
        result = subprocess.run(cmd, check=True, text=True, capture_output=True, env=env)
        print(result.stdout)
    except subprocess.CalledProcessError as e:
        print("Chyba při běhu Palace:")
        print(e.stderr)
        print(e.stdout)
        sys.exit(1)
    except FileNotFoundError:
        print("Kritická chyba: Příkaz 'docker' nebyl nalezen. Ujistěte se, že Docker běží a je dostupný v PATH.")
        sys.exit(1)
