import win32com.client
import sys
import traceback

def check_rhino():
    rhino = None
    try:
        print("Attempting to connect to Rhino 8 via COM (Rhino.Interface.8)...")
        rhino = win32com.client.dynamic.Dispatch("Rhino.Interface.8")
        print("✅ Successfully dispatched Rhino.Interface.8")
    except Exception:
        print("⚠️ Could not dispatch Rhino.Interface.8. Falling back to generic Rhino.Application...")
        try:
            rhino = win32com.client.dynamic.Dispatch("Rhino.Application")
            print("✅ Successfully dispatched Rhino.Application")
        except Exception as e:
            print("\n❌ FAILED: Could not dispatch any Rhino COM object.")
            traceback.print_exc()
            return False

    if not rhino:
        print("\n❌ FAILED: Rhino COM object is null.")
        return False
        
    try:
        print("Verifying command execution using RunScript...")
        # Using '!' cancels any running command.
        # We use a completely harmless command (_SelNone) to prove the connection works
        # without accidentally triggering the document Print dialog!
        result = rhino.RunScript('! _SelNone', 0)
        print(f"✅ Command executed. Rhino returned: {result}")
        
        return True
    except Exception as e:
        print(f"\n❌ FAILED: Could not execute RunScript.")
        print(f"   The Rhino application may be busy, hung, or waiting for user input.")
        # Print the full traceback for detailed debugging
        traceback.print_exc()
        return False

if __name__ == "__main__":
    if check_rhino():
        print("\n🎉 Rhino COM connection test PASSED.")
        sys.exit(0)
    else:
        print("\n---\n🔴 Rhino COM connection test FAILED.")
        sys.exit(1)
