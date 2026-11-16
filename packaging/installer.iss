; Hanpaper (한페이퍼) installer (Inno Setup 6). Per-user install: no administrator rights needed.
#define AppName "한페이퍼"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppExe "Hanpaper.exe"

[Setup]
AppId={{51332D89-E554-4B46-B603-3C9DD1933B96}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Hanpaper
AppPublisherURL=https://github.com/Mingjaam/hanpaper
DefaultDirName={localappdata}\Programs\Hanpaper
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=Hanpaper-Setup
SetupIconFile=hanpaper.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "바탕 화면에 바로 가기 만들기"; GroupDescription: "바로 가기:"

[Files]
Source: "..\dist\Hanpaper\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "한페이퍼 실행"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
