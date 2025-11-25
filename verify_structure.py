import os
import sys

print("=" * 70)
print("PROJECT STRUCTURE VERIFICATION")
print("=" * 70)

current_dir = os.getcwd()
print(f"\n Current Directory: {current_dir}")
print(f"\n🐍 Python Executable: {sys.executable}")

print("\n📄 Checking Required Files:\n")

required_files = {
    "Config Files": [
        "config.py",
        "pyproject.toml",
        "main.py"
    ],
    "Applications Structure": [
        "applications/__init__.py",
        "applications/customer/__init__.py",
        "applications/customer/models.py",
        "applications/items/__init__.py",
        "applications/items/models.py",
        "applications/payment/__init__.py",
        "applications/payment/models.py",
        "applications/payment/schemas.py",
        "applications/payment/services.py"
    ]
}

all_exist = True

for category, files in required_files.items():
    print(f"\n{category}:")
    for file_path in files:
        exists = os.path.exists(file_path)
        symbol = "" if exists else ""
        print(f"   {symbol} {file_path}")
        if not exists:
            all_exist = False

print("\n  Checking Configuration:\n")
if os.path.exists("config.py"):
    try:
        if current_dir not in sys.path:
            sys.path.insert(0, current_dir)
        
        import config
        if hasattr(config, 'TORTOISE_ORM'):
            print("    TORTOISE_ORM found in config.py")
            models = config.TORTOISE_ORM.get('apps', {}).get('models', {}).get('models', [])
            print(f"    Models configured: {len(models)}")
            for model in models:
                print(f"      - {model}")
        else:
            print("    TORTOISE_ORM NOT found in config.py")
            all_exist = False
    except Exception as e:
        print(f"    Error loading config.py: {e}")
        all_exist = False
else:
    print("    config.py does not exist")

print("\n" + "=" * 70)
if all_exist:
    print(" PROJECT STRUCTURE IS CORRECT!")
else:
    print(" PROJECT STRUCTURE HAS ISSUES!")
print("=" * 70)
