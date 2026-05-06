$paths = @(
    "C:\ProgramData\Microsoft\Windows\Start Menu\Programs",
    "$env:APPDATA\Microsoft\Windows\Start Menu\Programs"
)
$files = Get-ChildItem -Path $paths -Filter "*.lnk" -Recurse -ErrorAction SilentlyContinue
$apps = [ordered]@{}

$wshShell = New-Object -ComObject WScript.Shell
$shellApp = New-Object -ComObject Shell.Application

$commonAliases = @{
    "7-zip file manager" = @("7zip", "zip", "extract", "archive manager")
    "google chrome" = @("chrome", "browser", "internet")
    "firefox" = @("firefox", "browser", "internet")
    "firefox private browsing" = @("firefox private", "private browser", "incognito")
    "microsoft edge" = @("edge", "browser", "internet")
    "word" = @("microsoft word", "document", "doc")
    "excel" = @("microsoft excel", "spreadsheet", "xls")
    "powerpoint" = @("microsoft powerpoint", "presentation", "ppt", "power point")
    "notepad" = @("text editor", "txt", "notes")
    "task manager" = @("taskmgr", "system monitor")
    "remote desktop connection" = @("rdp", "remote desktop", "mstsc")
    "registry editor" = @("regedit", "registry")
    "command prompt" = @("cmd", "terminal")
    "windows powershell" = @("powershell", "terminal")
    "windows powershell ise" = @("powershell ise", "script editor")
    "git bash" = @("bash", "git terminal")
}

foreach ($file in $files) {
    $appName = $file.Name -replace '(?i)\.lnk$', ''
    $appName = $appName.ToLower().Trim()
    
    if (-not $apps.Contains($appName)) {
        
        $folder = $shellApp.NameSpace($file.DirectoryName)
        $folderItem = $folder.ParseName($file.Name)
        
        $appId = $folderItem.ExtendedProperty("System.AppUserModel.ID")
        if ([string]::IsNullOrWhiteSpace($appId)) {
            $appId = $null
        }

        $wshShortcut = $wshShell.CreateShortcut($file.FullName)
        $launchCmd = $wshShortcut.TargetPath
        
        if ([string]::IsNullOrWhiteSpace($launchCmd)) {
            $launchCmd = $folderItem.ExtendedProperty("System.Link.TargetParsingPath")
        }
        
        if ([string]::IsNullOrWhiteSpace($launchCmd)) {
            $launchCmd = $file.FullName
        }
        
        $appAliases = @()
        if ($commonAliases.ContainsKey($appName)) {
            $appAliases = $commonAliases[$appName]
        }
        
        $apps[$appName] = [ordered]@{
            app_id = $appId
            shortcut = $file.FullName
            launch_command = $launchCmd
            aliases = $appAliases
        }
    }
}

# Fetch UWP and modern Windows Apps (like WhatsApp from the Microsoft Store)
$startApps = Get-StartApps
foreach ($app in $startApps) {
    if ([string]::IsNullOrWhiteSpace($app.Name)) { continue }
    
    $appName = $app.Name.ToLower().Trim()
    
    if (-not $apps.Contains($appName)) {
        $appId = $app.AppID
        # UWP apps can be safely launched via explorer shell:AppsFolder
        $launchCmd = "explorer shell:AppsFolder\$appId"
        
        $appAliases = @()
        if ($commonAliases.ContainsKey($appName)) {
            $appAliases = $commonAliases[$appName]
        }
        
        $apps[$appName] = [ordered]@{
            app_id = $appId
            shortcut = $null
            launch_command = $launchCmd
            aliases = $appAliases
        }
    }
}

$jsonOutput = $apps | ConvertTo-Json -Depth 3

# Save as clean UTF-8 WITHOUT BOM so Python reads it perfectly without errors.
$utf8NoBom = New-Object System.Text.UTF8Encoding $False
$outFile = Join-Path $PWD "apps.json"
[System.IO.File]::WriteAllText($outFile, $jsonOutput, $utf8NoBom)
