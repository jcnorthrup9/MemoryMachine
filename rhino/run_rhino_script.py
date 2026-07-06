import sys, os, win32com.client, tempfile

def execute_script(script_path):
    try:
        rhino = win32com.client.dynamic.Dispatch("Rhino.Interface.8")
    except:
        rhino = win32com.client.dynamic.Dispatch("Rhino.Application")
    
    try:
        rs = rhino.GetScriptObject()
    except:
        rs = rhino

    full_path = os.path.abspath(script_path)
    print(f"Running script: {full_path}")
    
    # Using the same logic as the MCP server
    # Adding the optional 'echo' parameter for RunScript which might be causing the error
    if hasattr(rs, "RunScript"):
        result = rs.RunScript(f"_-ScriptEditor Run \"{full_path}\"", 1)
    else:
        result = rhino.RunScript(f"_-ScriptEditor Run \"{full_path}\"", 1)
        
    print("✅ Success" if result else "⚠️ Rhino was busy")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        execute_script(sys.argv[1])
    else:
        print("Usage: python run_rhino_script.py <path_to_script>")
