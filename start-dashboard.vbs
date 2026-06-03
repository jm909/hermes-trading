Set objShell = CreateObject("WScript.Shell")
Do
    objShell.Run """C:\Users\User\hermes-trading\.venv\Scripts\python.exe"" -m hermes_trading.dashboard", 0, True
    WScript.Sleep 5000
Loop