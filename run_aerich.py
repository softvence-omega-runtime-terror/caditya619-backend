import sys
import os

# Add current directory to Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

# Now run aerich commands
if __name__ == "__main__":
    import subprocess
    
    # Test if config can be imported
    try:
        import config
        print("✓ Config imported successfully!")
        print(f"Database URL: {config.settings.DATABASE_URL}")
    except Exception as e:
        print(f"✗ Error: {e}")
        sys.exit(1)
    
    # Run aerich
    cmd = ["aerich"] + sys.argv[1:]
    subprocess.run(cmd)
