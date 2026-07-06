import sys
import argparse
import win32com.client
import traceback

def run_command(command_string: str):
    """
    Connects to a running Rhino instance and executes a given command string.
    """
    rhino = None
    print(f"📡 Dispatching command to Rhino: '{command_string}'")

    try:
        # Use the most reliable connection method we've found
        rhino = win32com.client.dynamic.Dispatch("Rhino.Interface.8")
        print("✅ Successfully dispatched Rhino.Interface.8")

        # Use '!' to cancel any prior command, and ensure it runs.
        # The '1' at the end tells RunScript to return when the command is complete.
        result = rhino.RunScript(f"! {command_string}", 1)
        
        if result:
            print("✅ Command executed successfully.")
        else:
            print("⚠️ Command sent, but Rhino did not confirm execution (may have been busy or command had no output).")

    except Exception as e:
        print("\n❌ FAILED: Could not connect to or execute command in Rhino.")
        print("   Please ensure Rhino 8 is running.")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send a command string to a running Rhino instance.")
    parser.add_argument(
        "--command",
        required=True,
        help="The Rhino command string to execute, e.g., '_Box 0,0,0 10 10 10'"
    )
    args = parser.parse_args()
    run_command(args.command)