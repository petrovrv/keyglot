; Keyglot installer (Inno Setup 6). Built by build.ps1:  ISCC /DAppVersion=x.y.z installer\keyglot.iss
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{8C4B2E1A-5D7F-4A3B-9E6C-1F2D3A4B5C6D}
AppName=Keyglot
AppVersion={#AppVersion}
AppVerName=Keyglot {#AppVersion}
AppPublisher=Roman Petrov
AppPublisherURL=https://github.com/petrovrv/keyglot
AppSupportURL=https://github.com/petrovrv/keyglot/issues
AppUpdatesURL=https://github.com/petrovrv/keyglot/releases
DefaultDirName={localappdata}\Programs\Keyglot
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Keyglot-Setup-{#AppVersion}
SetupIconFile=..\assets\keyglot.ico
UninstallDisplayIcon={app}\Keyglot.exe
UninstallDisplayName=Keyglot
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=force
RestartApplications=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
VersionInfoVersion={#AppVersion}
VersionInfoProductName=Keyglot

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "ukrainian"; MessagesFile: "compiler:Languages\Ukrainian.isl"
Name: "dutch"; MessagesFile: "compiler:Languages\Dutch.isl"

[CustomMessages]
english.AutoStart=Start Keyglot with Windows
russian.AutoStart=Запускать Keyglot вместе с Windows
ukrainian.AutoStart=Запускати Keyglot разом з Windows
dutch.AutoStart=Keyglot starten met Windows
english.SettingsLink=Keyglot settings
russian.SettingsLink=Настройки Keyglot
ukrainian.SettingsLink=Налаштування Keyglot
dutch.SettingsLink=Keyglot-instellingen

[Tasks]
Name: "autostart"; Description: "{cm:AutoStart}"

[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\Keyglot\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Keyglot"; Filename: "{app}\Keyglot.exe"
Name: "{autoprograms}\{cm:SettingsLink}"; Filename: "{app}\Keyglot.exe"; Parameters: "--settings"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Keyglot"; ValueData: """{app}\Keyglot.exe"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\Keyglot.exe"; Description: "{cm:LaunchProgram,Keyglot}"; Flags: nowait postinstall skipifsilent
Filename: "{app}\Keyglot.exe"; Flags: nowait; Check: WizardSilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/IM Keyglot.exe /F"; Flags: runhidden; RunOnceId: "StopKeyglot"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
