; VisionInput Installer (Inno Setup 6.2+)
; Download Inno Setup: https://jrsoftware.org/isdl.php

#define MyAppName "VisionInput"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "RGU Capstone"
#define MyAppURL "https://github.com/MagixIsAvailable/rgu-capstone-mediapipe"
#define MyAppExeName "VisionInput.exe"

[Setup]
AppId={{99E6B7D4-5F8A-4A2D-9C1B-4E7F5D2C8A3B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
#ifexist "..\LICENSE"
LicenseFile=..\LICENSE
#endif
InfoBeforeFile=..\README.md
OutputDir=..\dist\installer
OutputBaseFilename=VisionInput_Setup_v{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
#ifexist "ViGEmBus-1.22.0-x64-dev.exe"
Name: "installvigem"; Description: "Install ViGEmBus Driver (required for controller output)"; GroupDescription: "Additional Setup"
#endif

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\VisionInput\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist
#ifexist "ViGEmBus-1.22.0-x64-dev.exe"
Source: "ViGEmBus-1.22.0-x64-dev.exe"; DestDir: "{app}\drivers"; Flags: ignoreversion
#endif
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: quicklaunchicon

[Run]
#ifexist "ViGEmBus-1.22.0-x64-dev.exe"
Filename: "{app}\drivers\ViGEmBus-1.22.0-x64-dev.exe"; Description: "Install ViGEmBus Driver"; Flags: nowait postinstall skipifsilent; Tasks: installvigem
#endif
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
