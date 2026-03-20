#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys
import subprocess
import threading

def build_frontend():
    """Helper function to build the React frontend."""
    # Prevent building multiple times if the auto-reloader kicks in
    if os.environ.get('RUN_MAIN') != 'true':
        print("\n===========================================")
        print("Starting React Frontend Build (npm run build)...")
        print("===========================================\n")
        
        frontend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'frontend')
        
        try:
            # Use shell=True for npm to resolve correctly on Windows
            process = subprocess.Popen(
                "npm run build", 
                cwd=frontend_dir, 
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True
            )
            
            # Print output in real-time
            for line in process.stdout:
                print(f"[Frontend Build]: {line.strip()}")
                
            process.wait()
            
            if process.returncode == 0:
                print("\n===========================================")
                print("React Frontend Build Completed Successfully!")
                print("===========================================\n")
            else:
                print("\n!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
                print("React Frontend Build FAILED! Check the logs above.")
                print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n")
                
        except Exception as e:
            print(f"Error trying to build frontend: {e}")

def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
    
    # Intercept 'runserver' command to build the frontend first
    if len(sys.argv) > 1 and sys.argv[1] == 'runserver':
        build_frontend()

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
