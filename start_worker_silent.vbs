Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' Get project directory where this script lives
rootDir = fso.GetParentFolderName(WScript.ScriptFullName)
venvPythonW = rootDir & "\.venv\Scripts\pythonw.exe"
workerPy = rootDir & "\laptop_worker.py"
cloudUrl = "https://brahma-cloud-brain.onrender.com"

' 1. Start Laptop Worker completely silently in background (window style 0, no wait)
If fso.FileExists(venvPythonW) Then
    shell.Run Chr(34) & venvPythonW & Chr(34) & " " & Chr(34) & workerPy & Chr(34), 0, False
Else
    shell.Run "pythonw.exe " & Chr(34) & workerPy & Chr(34), 0, False
End If

' 2. Brief pause for worker initialization
WScript.Sleep 1500

' 3. Open Chrome directly to the Render Web UI
chromeExe = "C:\Program Files\Google\Chrome\Application\chrome.exe"
chromeExe86 = "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
chromeLocal = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Google\Chrome\Application\chrome.exe"

If fso.FileExists(chromeExe) Then
    shell.Run Chr(34) & chromeExe & Chr(34) & " " & Chr(34) & cloudUrl & Chr(34), 1, False
ElseIf fso.FileExists(chromeExe86) Then
    shell.Run Chr(34) & chromeExe86 & Chr(34) & " " & Chr(34) & cloudUrl & Chr(34), 1, False
ElseIf fso.FileExists(chromeLocal) Then
    shell.Run Chr(34) & chromeLocal & Chr(34) & " " & Chr(34) & cloudUrl & Chr(34), 1, False
Else
    shell.Run cloudUrl, 1, False
End If
