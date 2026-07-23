; Inno Setup script - packages the PyInstaller output (dist\run) into a single
; Setup.exe. End users need nothing: no Python, no pip, no Inno Setup - just
; run the Setup.exe and click through it.
;
; One-time requirement on the BUILD machine only: Inno Setup
; (https://jrsoftware.org/isinfo.php), free. Then either:
;   - open this file in Inno Setup and click Compile, or
;   - run build_installer.bat, which does the PyInstaller build AND this step.
;
; Requires dist\run\run.exe to already exist (run build.bat first).

#define MyAppName "AE MacroTerminal"
#define MyAppVersion "0.1.0-alpha"
#define MyAppExeName "run.exe"

[Setup]
AppId={{6F6E6E6D-4144-4145-8D4D-524F424C5458}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
; Installs under the user's own folder - no admin/UAC prompt needed, so a
; user without an admin account can still install and run it.
DefaultDirName={localappdata}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=AE_MacroTerminal_Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
; No source .exe is signed, so warn the installer itself may trip Defender
; the same way run.exe does - same as build.bat's note.

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: checkedonce

[Files]
; Whole PyInstaller output folder, recursively - includes run.exe, the Qt
; DLLs, config.example.yaml, profiles/, vision/templates/, everything
; build.bat already assembled into dist\run.
Source: "dist\run\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName} now"; Flags: nowait postinstall skipifsilent
