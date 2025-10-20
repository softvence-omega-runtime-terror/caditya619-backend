from pathlib import Path

def get_module(base_dir="routes"):
    base_path = Path(base_dir)
    module = [
        p.name 
        for p in base_path.iterdir() 
        if p.is_dir() and not p.name.startswith("__") and not p.name.startswith(".")
    ]
    
    return module