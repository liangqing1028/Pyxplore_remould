[Setup]
AppId=PyWPEMDesktop
AppName=PyWPEM Desktop
AppVersion=0.1.2
DefaultDirName={autopf}\PyWPEM Desktop
DefaultGroupName=PyWPEM Desktop
OutputDir=..\dist
OutputBaseFilename=PyWPEMDesktop-Windows-x64-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
WizardStyle=modern
UninstallDisplayIcon={app}\PyWPEMDesktop.exe

[Files]
Source: "..\dist\PyWPEMDesktop\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\PyWPEM Desktop"; Filename: "{app}\PyWPEMDesktop.exe"
Name: "{autodesktop}\PyWPEM Desktop"; Filename: "{app}\PyWPEMDesktop.exe"

[Run]
Filename: "{app}\PyWPEMDesktop.exe"; Description: "Launch PyWPEM Desktop"; Flags: nowait postinstall skipifsilent
