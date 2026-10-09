; FishShop Windows installer.
;
; Built by packaging/scripts/build_windows.ps1 step [8/8]:
;   ISCC.exe packaging\installer\FishShop.iss /O"release" /F"FishShopSetup-<version>"
;
; Expects packaging/dist/FishShopAdmin, packaging/dist/FishShopPOS, and
; packaging/dist/FishShopMigrate to already exist (built by PyInstaller in
; step [6/8]) and packaging/installer/version.iss to have been generated
; (step [2/8]) from version.iss.template.

#include "version.iss"

[Setup]
AppId={{5B6C9C1E-2C6B-4E1D-9B7B-2B6C7A8FBF2A}
AppName=FishShop
AppVersion={#MyAppVersion}
AppPublisher=FishShop
DefaultDirName={autopf}\FishShop
DefaultGroupName=FishShop
DisableProgramGroupPage=yes
OutputDir=..\..\release
OutputBaseFilename=FishShopSetup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
SetupIconFile=..\assets\icon\fishshop.ico
UninstallDisplayIcon={app}\Admin\FishShopAdmin.exe
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
LicenseFile=license.txt
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Types]
Name: "admin"; Description: "Admin PC (Admin + POS applications and PostgreSQL database)"
Name: "pos"; Description: "POS PC (Point of Sale terminal only)"
Name: "custom"; Description: "Custom"; Flags: iscustom

[Components]
Name: "adminapp"; Description: "FishShop Admin application"; Types: admin
Name: "posapp"; Description: "FishShop POS application"; Types: admin pos
Name: "database"; Description: "PostgreSQL database (required for Admin PC)"; Types: admin

[Tasks]
Name: "desktopicon_admin"; Description: "Create a desktop shortcut for FishShop Admin"; Components: adminapp; Flags: unchecked
Name: "desktopicon_pos"; Description: "Create a desktop shortcut for FishShop POS"; Components: posapp; Flags: unchecked
Name: "launch_admin"; Description: "Launch FishShop Admin after installation"; Components: adminapp; Flags: unchecked
Name: "launch_pos"; Description: "Launch FishShop POS after installation"; Components: posapp; Flags: unchecked
Name: "seedtestusers"; Description: "Create test accounts (test/test and test1/test) - TESTING ONLY, remove before production use"; Components: adminapp

[Files]
Source: "..\dist\FishShopAdmin\*"; DestDir: "{app}\Admin"; Components: adminapp; Flags: recursesubdirs ignoreversion
Source: "..\dist\FishShopMigrate\*"; DestDir: "{app}\Admin"; Components: adminapp; Flags: recursesubdirs ignoreversion
Source: "..\dist\FishShopPOS\*"; DestDir: "{app}\POS"; Components: posapp; Flags: recursesubdirs ignoreversion
Source: "..\scripts\*.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion

[Icons]
Name: "{group}\FishShop Admin"; Filename: "{app}\Admin\FishShopAdmin.exe"; Components: adminapp
Name: "{group}\FishShop POS"; Filename: "{app}\POS\FishShopPOS.exe"; Components: posapp
Name: "{group}\Uninstall FishShop"; Filename: "{uninstallexe}"
Name: "{autodesktop}\FishShop Admin"; Filename: "{app}\Admin\FishShopAdmin.exe"; Tasks: desktopicon_admin
Name: "{autodesktop}\FishShop POS"; Filename: "{app}\POS\FishShopPOS.exe"; Tasks: desktopicon_pos

[Run]
Filename: "{app}\Admin\FishShopAdmin.exe"; Description: "Launch FishShop Admin"; Tasks: launch_admin; Flags: postinstall nowait skipifsilent
Filename: "{app}\POS\FishShopPOS.exe"; Description: "Launch FishShop POS"; Tasks: launch_pos; Flags: postinstall nowait skipifsilent

; Database install, config, and migration steps run from [Code] below
; (ssPostInstall), not from here - a plain [Run] entry that fails does not
; stop Setup or reliably surface the real error, which is exactly what let
; a failed PostgreSQL install pass silently. Running them via Exec() in
; [Code] lets us check the exit code and show the operator an explicit,
; readable error immediately, and stop the install rather than continuing
; into a broken state.

; No [UninstallDelete] entries reference %ProgramData%\FishShop or PostgreSQL's
; own data directory - uninstalling FishShop removes only the {app} program
; files; configuration, receipts, and the database are preserved.

[Code]
var
  DbPasswordPage: TInputQueryWizardPage;
  PosConnectionPage: TInputQueryWizardPage;
  StoreDetailsPage: TInputQueryWizardPage;

function PosOnlyInstall(): Boolean;
begin
  { POS-only installs (no adminapp on this machine) need to be told where
    the Admin server is; an Admin PC that also has posapp checked already
    knows - it IS the Admin server, at 127.0.0.1. }
  Result := IsComponentSelected('posapp') and (not IsComponentSelected('adminapp'));
end;

procedure InitializeWizard();
begin
  DbPasswordPage := CreateInputQueryPage(wpSelectComponents,
    'Database Setup', 'Set the FishShop database password',
    'This password will be used for the shop_admin PostgreSQL role. Choose a strong password and record it somewhere safe.');
  DbPasswordPage.Add('New database password:', True);
  DbPasswordPage.Add('Confirm password:', True);

  StoreDetailsPage := CreateInputQueryPage(DbPasswordPage.ID,
    'Store Details', 'Enter store information for receipts',
    'This information is printed on POS receipts. It can be changed later by editing %ProgramData%\FishShop\config\.env.');
  StoreDetailsPage.Add('Store name:', False);
  StoreDetailsPage.Add('Store phone number(s) (comma-separated):', False);
  StoreDetailsPage.Add('Store address:', False);

  PosConnectionPage := CreateInputQueryPage(wpSelectComponents,
    'Admin Server Connection', 'Where is the FishShop Admin server?',
    'Enter the network address of the PC running FishShop Admin, and this terminal''s unique ID.');
  PosConnectionPage.Add('Admin server address:', False);
  PosConnectionPage.Add('Admin server port:', False);
  PosConnectionPage.Add('POS terminal ID (e.g. pos-1):', False);
  PosConnectionPage.Values[0] := '127.0.0.1';
  PosConnectionPage.Values[1] := '8765';
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
  if (PageID = DbPasswordPage.ID) or (PageID = StoreDetailsPage.ID) then
    Result := not IsComponentSelected('adminapp')
  else if PageID = PosConnectionPage.ID then
    Result := not PosOnlyInstall();
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = DbPasswordPage.ID then
  begin
    if DbPasswordPage.Values[0] = '' then
    begin
      MsgBox('Please enter a database password.', mbError, MB_OK);
      Result := False;
    end
    else if DbPasswordPage.Values[0] <> DbPasswordPage.Values[1] then
    begin
      MsgBox('Passwords do not match.', mbError, MB_OK);
      Result := False;
    end
    else if Pos('"', DbPasswordPage.Values[0]) > 0 then
    begin
      MsgBox('The database password cannot contain a double-quote (") character.', mbError, MB_OK);
      Result := False;
    end;
  end
  else if CurPageID = PosConnectionPage.ID then
  begin
    if (PosConnectionPage.Values[0] = '') or (PosConnectionPage.Values[1] = '') or (PosConnectionPage.Values[2] = '') then
    begin
      MsgBox('Admin server address, port, and terminal ID are all required.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

{ Runs one PowerShell script via Exec(), captures its real exit code, and
  shows the operator a clear, specific error dialog on failure instead of
  silently continuing - this is what let a failed PostgreSQL install pass
  unnoticed before. Returns True on success. }
function RunPowerShellStep(ScriptRelativePath, Args, StepLabel: String): Boolean;
var
  ResultCode: Integer;
  ScriptPath, FullParams: String;
begin
  ScriptPath := ExpandConstant('{app}\scripts\' + ScriptRelativePath);
  FullParams := Format('-NoProfile -ExecutionPolicy Bypass -File "%s" %s', [ScriptPath, Args]);
  WizardForm.StatusLabel.Caption := StepLabel;
  Result := Exec('powershell.exe', FullParams, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  if not Result then
  begin
    MsgBox(StepLabel + ' failed to start (could not launch powershell.exe).', mbCriticalError, MB_OK);
    Result := False;
  end
  else if ResultCode <> 0 then
  begin
    MsgBox(
      StepLabel + ' failed (exit code ' + IntToStr(ResultCode) + ').' + #13#10 + #13#10 +
      'You can re-run this step manually after Setup finishes: open an Administrator ' +
      'PowerShell window and run the corresponding script in "' + ExpandConstant('{app}') + '\scripts\".' + #13#10 + #13#10 +
      'The remaining setup steps below will be skipped since they depend on this one.',
      mbCriticalError, MB_OK);
    Result := False;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Args, PasswordFile, SeedFlag: String;
  ok: Boolean;
begin
  if CurStep <> ssPostInstall then
    Exit;

  ok := True;
  PasswordFile := '';

  { The database password is written to a temp file and only its PATH is
    passed on the command line. Interpolating the password itself into a
    PowerShell command line breaks (or is misread) whenever it contains
    characters special to the shell - $, `, ", % and friends - which is a
    real failure mode, not a hypothetical. The file is deleted below. }
  if IsComponentSelected('adminapp') or IsComponentSelected('database') then
  begin
    PasswordFile := ExpandConstant('{tmp}\fishshop-dbpass.tmp');
    if not SaveStringToFile(PasswordFile, DbPasswordPage.Values[0], False) then
    begin
      MsgBox('Could not write the temporary credentials file needed to configure the database.',
        mbCriticalError, MB_OK);
      Exit;
    end;
  end;

  if IsComponentSelected('database') then
  begin
    Args := Format('-SuperPasswordFile "%s" -AppPasswordFile "%s"', [PasswordFile, PasswordFile]);
    ok := RunPowerShellStep('install_database.ps1', Args, 'Installing PostgreSQL');
  end;

  if ok and IsComponentSelected('adminapp') then
  begin
    Args := Format('-Role Admin -AppPasswordFile "%s" -StoreName "%s" -StorePhoneNumbers "%s" -StoreAddress "%s"', [
      PasswordFile, StoreDetailsPage.Values[0], StoreDetailsPage.Values[1], StoreDetailsPage.Values[2]]);
    ok := RunPowerShellStep('configure_environment.ps1', Args, 'Writing Admin configuration');
  end;

  if ok and IsComponentSelected('adminapp') then
  begin
    if WizardIsTaskSelected('seedtestusers') then
      SeedFlag := ''
    else
      SeedFlag := ' -SkipSeed';
    Args := Format('-InstallDir "%s"%s', [ExpandConstant('{app}'), SeedFlag]);
    ok := RunPowerShellStep('migrate_database.ps1', Args, 'Applying database migrations');
  end;

  if ok and PosOnlyInstall() then
  begin
    Args := Format('-Role POS -AdminHost "%s" -AdminPort "%s" -TerminalId "%s"', [
      PosConnectionPage.Values[0], PosConnectionPage.Values[1], PosConnectionPage.Values[2]]);
    ok := RunPowerShellStep('configure_environment.ps1', Args, 'Writing POS configuration');
  end;

  if PasswordFile <> '' then
    DeleteFile(PasswordFile);

  if ok and IsComponentSelected('adminapp') and WizardIsTaskSelected('seedtestusers') then
    MsgBox('Setup created two test accounts:' + #13#10 + #13#10 +
      '  FishShop Admin:  username "test"   password "test"' + #13#10 +
      '  FishShop POS:    username "test1"  password "test"' + #13#10 + #13#10 +
      'These are for testing only - remove them before real production use.',
      mbInformation, MB_OK);
end;
