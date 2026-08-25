; installer.iss — script Inno Setup cho KaTOBA
; Cách dùng: cài Inno Setup -> mở file này bằng Inno Setup Compiler -> bấm Compile (hoặc F9)
; Kết quả: Output\KaTOBA-Setup.exe

#define MyAppName "KaTOBA"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "KaTOBA"
#define MyAppExeName "KaTOBA.exe"

; Thư mục chứa app đã build (win-unpacked). Sửa nếu đặt project chỗ khác.
#define SourceDir "C:\Users\NguyenQuangVinh\Meeting-App-PoC\frontend\dist\win-unpacked"

[Setup]
AppId={{2F7A91C4-6B3D-4E18-A5F2-KATOBAAPP001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=Output
OutputBaseFilename=KaTOBA-Setup
Compression=lzma2/max
SolidCompression=no
WizardStyle=modern
; Chưa có logo -> KHÔNG khai SetupIconFile, Inno Setup dùng icon mặc định.
; Khi có file .ico, bỏ comment dòng dưới và trỏ đúng đường dẫn:
; SetupIconFile=D:\AI_Translator\Meeting-App-PoC\frontend\build\icon.ico
DisableProgramGroupPage=yes

[Languages]
Name: "vietnamese"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Tạo biểu tượng ngoài Desktop"; GroupDescription: "Tùy chọn:"; Flags: checkedonce

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\Gỡ cài đặt {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Mở {#MyAppName} ngay bây giờ"; Flags: nowait postinstall skipifsilent
