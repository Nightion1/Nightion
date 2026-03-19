Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")

' Get the exact folder where this VBScript is located
strFolder = FSO.GetParentFolderName(WScript.ScriptFullName)

' 1. Start the Nightion Python server completely hidden, ensuring it triggers in the correct project folder
command = "cmd.exe /c cd /d """ & strFolder & """ && python server.py"
WshShell.Run command, 0, False

' 2. Wait 4 seconds for the backend FastAPI server to spin up and load the models
WScript.Sleep 4000

' 3. Open Microsoft Edge natively as an "App Window" without tabs or URL bars
' (If you prefer Chrome, change "msedge.exe" to "chrome.exe")
WshShell.Run "msedge.exe --app=http://localhost:8000", 1, False
