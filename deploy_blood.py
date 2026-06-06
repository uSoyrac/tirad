import paramiko
import sys

host = "45.143.11.97"
user = "root"
password = "icBuQb6jNtIJ"

try:
    print(f"Connecting to {host}...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(host, username=user, password=password, timeout=10)
    print("Connected successfully!")
    
    commands = [
        "cd /root/tirad && git pull",
        "tmux kill-session -t blood 2>/dev/null || true",
        "tmux kill-session -t paper_trader 2>/dev/null || true",
        "tmux new-session -d -s blood 'cd /root/tirad && ./run_blood_live.sh'",
        "tmux new-session -d -s paper_trader 'cd /root/tirad && python3 paper_trader.py'",
        "tmux ls"
    ]
    
    for cmd in commands:
        print(f"Running: {cmd}")
        stdin, stdout, stderr = client.exec_command(cmd)
        print(stdout.read().decode())
        err = stderr.read().decode()
        if err:
            print(f"Error: {err}")
            
    client.close()
    print("Deployed and started on VPS!")
    
except Exception as e:
    print(f"Failed: {e}")
