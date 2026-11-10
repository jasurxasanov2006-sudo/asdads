#define AppName "DataFlow AI"
#define AppVersion "1.0.0"

[Setup]
AppId={{5B11A8CE-5AD5-4C7A-BDB5-34E05E2A3D82}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={autopf}\DataFlow AI
DefaultGroupName=DataFlow AI
OutputDir=..\..\dist
OutputBaseFilename=DataFlowAI-Setup
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=lowest
WizardStyle=modern

[Files]
Source: "..\..\dist\DataFlowAI.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\DataFlow AI"; Filename: "{app}\DataFlowAI.exe"
Name: "{autodesktop}\DataFlow AI"; Filename: "{app}\DataFlowAI.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Run]
Filename: "{app}\DataFlowAI.exe"; Description: "Launch DataFlow AI"; Flags: nowait postinstall skipifsilent
