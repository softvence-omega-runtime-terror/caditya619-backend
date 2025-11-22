import sys
import os
import subprocess

# Add current directory to Python path
current_dir = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, current_dir)

# Set PYTHONPATH environment variable
os.environ['PYTHONPATH'] = current_dir

print(f"Working directory: {current_dir}")
print(f"PYTHONPATH set to: {current_dir}")

# Test imports
print("\n" + "="*60)
print("Testing imports...")
print("="*60)

try:
    from applications.customer.models import Order
    print("✓ applications.customer.models")
except Exception as e:
    print(f"✗ applications.customer.models: {e}")
    sys.exit(1)

try:
    from applications.payment.models import Payment
    print("✓ applications.payment.models")
except Exception as e:
    print(f"✗ applications.payment.models: {e}")
    sys.exit(1)

try:
    from app.config import TORTOISE_ORM
    print("✓ app.config.TORTOISE_ORM")
except Exception as e:
    print(f"✗ app.config: {e}")
    sys.exit(1)

print("\n" + "="*60)
print("All imports successful! Running migrations...")
print("="*60 + "\n")

# Run aerich commands with proper environment
env = os.environ.copy()
env['PYTHONPATH'] = current_dir

commands = [
    ["aerich", "migrate", "--name", "add_payment_models"],
    ["aerich", "upgrade"]
]

for cmd in commands:
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, env=env, shell=True)
    if result.returncode != 0:
        print(f"✗ Command failed with exit code {result.returncode}")
        sys.exit(1)
    print(f"✓ Success\n")

print("="*60)
print("✅ All migrations completed successfully!")
print("="*60)
