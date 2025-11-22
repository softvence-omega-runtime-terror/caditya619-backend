import sys
import os
import subprocess

# Add current directory to Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)
os.chdir(current_dir)

print(f"Working directory: {os.getcwd()}")

# Test config import from app folder
try:
    from app.config import TORTOISE_ORM
    print("✓ Config imported successfully from app.config")
    print(f"✓ Database: {TORTOISE_ORM['connections']['default']}")
    print(f"✓ Apps: {list(TORTOISE_ORM['apps'].keys())}")
except Exception as e:
    print(f"✗ Config import failed: {e}")
    sys.exit(1)

# Run aerich commands
commands = [
    ["aerich", "init", "-t", "app.config.TORTOISE_ORM"],
    ["aerich", "init-db"],
    ["aerich", "migrate", "--name", "add_payment_models"],
    ["aerich", "upgrade"]
]

for cmd in commands:
    print(f"\n{'='*60}")
    print(f"Running: {' '.join(cmd)}")
    print('='*60)
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"✗ Command failed")
        break
    print(f"✓ Success")

