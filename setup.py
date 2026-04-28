import os
import subprocess
import shutil
from pathlib import Path
from setuptools import setup
from setuptools.command.build_py import build_py
from setuptools.command.sdist import sdist

dashboard_built = False

def build_dashboard():
    """Build the Next.js dashboard and copy to static directory."""
    global dashboard_built
    if dashboard_built:
        return
        
    print("Building Vorte Dashboard...")
    setup_dir = Path(__file__).parent
    vorte_dir = setup_dir.parent
    
    if not (vorte_dir / "package.json").exists():
        print(f"Warning: Could not find package.json in {vorte_dir}. Skipping dashboard build.")
        return

    # Run npm run build
    print("Running 'npm run build'...")
    try:
        # Use shell=True for cross-platform compatibility (especially Windows npm)
        subprocess.run(["npm", "run", "build"], cwd=vorte_dir, check=True, shell=True)
    except subprocess.CalledProcessError as e:
        print(f"Error: Dashboard build failed. {e}")
        return
        
    # Copy out/ to static/
    out_dir = vorte_dir / "out"
    static_dir = setup_dir / "vorte" / "modules" / "dashboard" / "static"
    
    if out_dir.exists():
        if static_dir.exists():
            shutil.rmtree(static_dir)
        shutil.copytree(out_dir, static_dir)
        print(f"Dashboard successfully built and copied to {static_dir}")
    else:
        print("Warning: out/ directory not found after build.")


# Run the build before setup() is called so setuptools sees the new files
build_dashboard()

setup()
