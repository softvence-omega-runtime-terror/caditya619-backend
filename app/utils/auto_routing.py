from pathlib import Path
from typing import Dict

def get_module(base_dir="routes"):
    base_path = Path(base_dir)
    module = [
        p.name 
        for p in base_path.iterdir() 
        if p.is_dir() and not p.name.startswith("__") and not p.name.startswith(".")
    ]
    
    return module

def get_apps_structure(base_dir: str = "applications") -> Dict[str, dict]:
    base_path = Path(base_dir)
    app_configs = {}

    # Loop through all subdirectories under applications/
    for app_dir in base_path.iterdir():
        if not app_dir.is_dir():
            continue

        # Collect all *.py files inside this app directory
        model_files = [
            f"{base_dir}.{app_dir.name}.{file.stem}"
            for file in app_dir.glob("*.py")
            if file.is_file() and not file.name.startswith("__") and not file.name == "signals.py"
        ]

        # Only add apps that actually contain model files
        if model_files:
            app_configs[app_dir.name] = {
                "models": model_files,
                "default_connection": "default",
            }

    return app_configs