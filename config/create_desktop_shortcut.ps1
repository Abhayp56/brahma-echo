$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut('C:\Users\Asus\Desktop\Brahma Echo.lnk')
$Shortcut.TargetPath = 'C:\Users\Asus\Desktop\Brahma-Echo-main\Brahma-Echo-main\.venv\Scripts\python.exe'
$Shortcut.Arguments = '"C:\Users\Asus\Desktop\Brahma-Echo-main\Brahma-Echo-main\main.py"'
$Shortcut.WorkingDirectory = 'C:\Users\Asus\Desktop\Brahma-Echo-main\Brahma-Echo-main'
$Shortcut.WindowStyle = 7
$Shortcut.Description = 'Launch Brahma Echo'
if ('C:\Users\Asus\Desktop\Brahma-Echo-main\Brahma-Echo-main\assets\Brahma_Lite_Logo.ico') { $Shortcut.IconLocation = 'C:\Users\Asus\Desktop\Brahma-Echo-main\Brahma-Echo-main\assets\Brahma_Lite_Logo.ico,0' }
$Shortcut.Save()