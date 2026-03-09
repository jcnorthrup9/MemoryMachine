import win32com.client
import sys

def check_rhino():
    try:
        print("Attempting to connect to Rhino via COM...")
        rhino = win32com.client.dynamic.Dispatch("Rhino.Application")
        print("Successfully dispatched Rhino.Application")
        
        # Check if visible/ready
        version = rhino.Version
        print(f"Rhino Version: {version}")
        
        return True
    except Exception as e:
        print(f"FAILED: {str(e)}")
        return False

if __name__ == "__main__":
    if check_rhino():
        sys.exit(0)
    else:
        sys.exit(1)
