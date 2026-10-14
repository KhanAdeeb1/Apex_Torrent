; ApexTorrent installer (Inno Setup 6.3 or newer).
; Build:  ISCC.exe /DMyAppVersion=1.1.0 installer.iss      (build_installer.bat does this for you)
; Input:  dist\ApexTorrent\   (PyInstaller one-directory output)     Output: dist\ApexTorrent_Setup.exe

#define MyAppName      "ApexTorrent"
#ifndef MyAppVersion
  #define MyAppVersion "1.1.0"
#endif
#define MyAppPublisher "Adeeb Khan"
#define MyAppURL       "https://github.com/KhanAdeeb1/Apex_Torrent"
#define MyAppExeName   "ApexTorrent.exe"
#define MyAppMutex     "ApexTorrentSingleInstanceMutex"
#define MyTorrentProgId "ApexTorrent.torrent"
#define MyMagnetProgId  "ApexTorrent.magnet"

[Setup]
; Never change this GUID after your first public release: it identifies the app for upgrades/uninstall.
AppId={{8F3C2B54-6A1E-4D7B-9C0A-5E2D7B1F4A93}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} Setup
VersionInfoProductName={#MyAppName}

; Installs to C:\Program Files\ApexTorrent for all users (admin). The user can switch to a per-user install
; in the startup dialog (-> %LOCALAPPDATA%\Programs\ApexTorrent, no admin rights needed; no firewall rule then).
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
DisableWelcomePage=no
UsePreviousAppDir=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0

LicenseFile=LICENSE.txt
SetupIconFile=assets\apextorrent.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
WizardStyle=modern
WizardImageFile=assets\wizard_large.bmp
WizardSmallImageFile=assets\wizard_small.bmp

OutputDir=dist
OutputBaseFilename=ApexTorrent_Setup
Compression=lzma2/ultra64
SolidCompression=yes

; Needed so Explorer refreshes icons/associations after install and uninstall.
ChangesAssociations=yes
; Detects a running ApexTorrent (the app creates this mutex) and asks to close it instead of failing on locked files.
AppMutex={#MyAppMutex}
SetupMutex=ApexTorrentSetupMutex
CloseApplications=yes
RestartApplications=no

#ifdef SignTool
; Code signing: pass  /DSignTool=1 "/Sapexsign=<your signtool command ending in $f>"  to ISCC (see README).
SignTool=apexsign
SignedUninstaller=yes
#endif

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
WelcomeLabel2=This will install [name/ver] on your computer.%n%nApexTorrent only downloads what you tell it to download, and scans every finished download for threats. You are responsible for having the right to download and share that content.%n%nIt is recommended that you close other applications before continuing.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "startup"; Description: "Launch {#MyAppName} when Windows starts (minimized)"; GroupDescription: "Startup:"; Flags: unchecked
Name: "assoc_torrent"; Description: "Open .torrent files with {#MyAppName}"; GroupDescription: "File associations:"
Name: "assoc_magnet"; Description: "Open magnet: links from web browsers with {#MyAppName}"; GroupDescription: "File associations:"
Name: "firewall"; Description: "Allow {#MyAppName} through Windows Defender Firewall (recommended, needed for incoming peers)"; GroupDescription: "Network:"; Check: IsAdminInstallMode

[Files]
Source: "dist\{#MyAppName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "assets\torrent.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "THIRD_PARTY_NOTICES.txt"; DestDir: "{app}"; Flags: ignoreversion

[InstallDelete]
; On upgrade, remove the old bundled libraries first so stale DLLs never mix with the new ones.
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; ---- .torrent file association (HKA = HKLM for all-users installs, HKCU for per-user installs) ----
Root: HKA; Subkey: "Software\Classes\.torrent"; ValueType: string; ValueName: ""; ValueData: "{#MyTorrentProgId}"; Flags: uninsdeletevalue; Tasks: assoc_torrent
Root: HKA; Subkey: "Software\Classes\.torrent\OpenWithProgids"; ValueType: string; ValueName: "{#MyTorrentProgId}"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\{#MyTorrentProgId}"; ValueType: string; ValueName: ""; ValueData: "BitTorrent File"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\{#MyTorrentProgId}\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\torrent.ico"
Root: HKA; Subkey: "Software\Classes\{#MyTorrentProgId}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""

; ---- magnet: URI protocol handler ----
Root: HKA; Subkey: "Software\Classes\magnet"; ValueType: string; ValueName: ""; ValueData: "URL:Magnet Link"; Flags: uninsdeletekey; Tasks: assoc_magnet
Root: HKA; Subkey: "Software\Classes\magnet"; ValueType: string; ValueName: "URL Protocol"; ValueData: ""; Tasks: assoc_magnet
Root: HKA; Subkey: "Software\Classes\magnet\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"; Tasks: assoc_magnet
Root: HKA; Subkey: "Software\Classes\magnet\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; Tasks: assoc_magnet
Root: HKA; Subkey: "Software\Classes\{#MyMagnetProgId}"; ValueType: string; ValueName: ""; ValueData: "URL:Magnet Link"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\{#MyMagnetProgId}"; ValueType: string; ValueName: "URL Protocol"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\{#MyMagnetProgId}\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"
Root: HKA; Subkey: "Software\Classes\{#MyMagnetProgId}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""

; ---- Default Apps registration: makes ApexTorrent selectable in Windows Settings > Default apps ----
Root: HKA; Subkey: "Software\{#MyAppName}\Capabilities"; ValueType: string; ValueName: "ApplicationName"; ValueData: "{#MyAppName}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\{#MyAppName}\Capabilities"; ValueType: string; ValueName: "ApplicationDescription"; ValueData: "Fast, ad-free BitTorrent client with automatic malware scanning"
Root: HKA; Subkey: "Software\{#MyAppName}\Capabilities\FileAssociations"; ValueType: string; ValueName: ".torrent"; ValueData: "{#MyTorrentProgId}"
Root: HKA; Subkey: "Software\{#MyAppName}\Capabilities\URLAssociations"; ValueType: string; ValueName: "magnet"; ValueData: "{#MyMagnetProgId}"
Root: HKA; Subkey: "Software\RegisteredApplications"; ValueType: string; ValueName: "{#MyAppName}"; ValueData: "Software\{#MyAppName}\Capabilities"; Flags: uninsdeletevalue

; ---- optional: launch at Windows startup ----
Root: HKA; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#MyAppName}"; ValueData: """{app}\{#MyAppExeName}"" --minimized"; Flags: uninsdeletevalue; Tasks: startup

[Run]
; Remove any rule left by a previous install, then add a fresh inbound allow rule for this exe (admin installs only).
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""{#MyAppName}"" program=""{app}\{#MyAppExeName}"""; Flags: runhidden waituntilterminated; Tasks: firewall; Check: IsAdminInstallMode; StatusMsg: "Configuring Windows Firewall..."
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""{#MyAppName}"" dir=in action=allow program=""{app}\{#MyAppExeName}"" enable=yes profile=any"; Flags: runhidden waituntilterminated; Tasks: firewall; Check: IsAdminInstallMode; StatusMsg: "Configuring Windows Firewall..."
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent runasoriginaluser

[UninstallRun]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""{#MyAppName}"" program=""{app}\{#MyAppExeName}"""; Flags: runhidden waituntilterminated; RunOnceId: "DeleteFirewallRule"; Check: IsAdminInstallMode

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
// After the program files are gone, offer to remove the per-user data folder as well.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{userprofile}\.apextorrent');
    if DirExists(DataDir) and (not UninstallSilent) then
    begin
      if MsgBox('Also delete your ApexTorrent settings, resume data, scan logs and quarantine records?' + #13#10 + #13#10 +
                DataDir + #13#10 + #13#10 +
                'Your downloaded files (including any quarantined files in your download folders) are not touched.',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
    end;
  end;
end;
