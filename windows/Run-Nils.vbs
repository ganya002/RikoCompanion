Set shell = CreateObject("WScript.Shell")
scriptDir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
pythonw = scriptDir & "\.venv\Scripts\pythonw.exe"
mainPy = scriptDir & "\main.py"

If Not CreateObject("Scripting.FileSystemObject").FileExists(pythonw) Then
    MsgBox "Virtual environment not found. Run Install-Nils-Windows.bat first.", vbExclamation, "Nils Companion"
    WScript.Quit 1
End If

shell.CurrentDirectory = scriptDir
shell.Run """" & pythonw & """ """ & mainPy & """", 0, False
