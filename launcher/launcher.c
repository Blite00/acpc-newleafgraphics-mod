/* AnimalCrossing.exe - launcher for the ACPC New Leaf graphics mod.
 *
 * First launch: asks for the player's own New Leaf ROM and ACGC-PC-Port 0.9.3 source folder, runs the
 * bundled conversion pipeline (mod\pipeline\setup_mod.py on runtime\python) which extracts the
 * New Leaf assets, converts them and builds newleaf_cache\game\AnimalCrossing-NL.exe.
 * Later launches start that build directly. Without a ROM, or if setup fails, the original
 * GameCube-graphics build (gc\AnimalCrossing-GC.exe) is started instead.
 *
 *   AnimalCrossing.exe            play (runs setup the first time)
 *   AnimalCrossing.exe --setup    run the New Leaf setup again
 *   AnimalCrossing.exe --vanilla  play with the original GameCube graphics
 * Every other argument is passed to the game.
 */
#define _WIN32_WINNT 0x0601
#define WIN32_LEAN_AND_MEAN
#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif
#include <windows.h>
#include <shellapi.h>
#include <commctrl.h>
#include <shlobj.h>
#include <shobjidl.h>
#include <wchar.h>
#include <stdio.h>

#define MOD_VERSION L"1.0.0"
#define APP_TITLE L"Animal Crossing - New Leaf graphics mod"

static wchar_t g_root[MAX_PATH];

static void path_join(wchar_t* out, const wchar_t* rel) {
    swprintf(out, MAX_PATH, L"%ls\\%ls", g_root, rel);
}

static int file_exists(const wchar_t* p) {
    DWORD a = GetFileAttributesW(p);
    return a != INVALID_FILE_ATTRIBUTES && !(a & FILE_ATTRIBUTE_DIRECTORY);
}

static int dir_exists(const wchar_t* p) {
    DWORD a = GetFileAttributesW(p);
    return a != INVALID_FILE_ATTRIBUTES && (a & FILE_ATTRIBUTE_DIRECTORY);
}

static int read_text(const wchar_t* rel, wchar_t* buf, int cap) {
    wchar_t p[MAX_PATH];
    char tmp[4096];
    FILE* f;
    size_t n;
    path_join(p, rel);
    f = _wfopen(p, L"rb");
    if (!f) return 0;
    n = fread(tmp, 1, sizeof(tmp) - 1, f);
    fclose(f);
    tmp[n] = 0;
    return MultiByteToWideChar(CP_UTF8, 0, tmp, -1, buf, cap) > 0;
}

static void write_text(const wchar_t* rel, const wchar_t* text) {
    wchar_t p[MAX_PATH];
    char tmp[2048];
    FILE* f;
    path_join(p, rel);
    WideCharToMultiByte(CP_UTF8, 0, text, -1, tmp, sizeof(tmp), NULL, NULL);
    f = _wfopen(p, L"wb");
    if (!f) return;
    fputs(tmp, f);
    fclose(f);
}

/* Build the command-line tail (everything after argv[0]) minus our own flags. */
static void game_args(wchar_t* out, int cap) {
    int argc, i;
    wchar_t** argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    out[0] = 0;
    for (i = 1; argv && i < argc; i++) {
        if (!wcscmp(argv[i], L"--setup") || !wcscmp(argv[i], L"--vanilla")) continue;
        wcsncat(out, L" \"", cap - wcslen(out) - 1);
        wcsncat(out, argv[i], cap - wcslen(out) - 1);
        wcsncat(out, L"\"", cap - wcslen(out) - 1);
    }
    if (argv) LocalFree(argv);
}

static int has_flag(const wchar_t* flag) {
    int argc, i, r = 0;
    wchar_t** argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    for (i = 1; argv && i < argc; i++)
        if (!wcscmp(argv[i], flag)) r = 1;
    if (argv) LocalFree(argv);
    return r;
}

static DWORD run(const wchar_t* exe, const wchar_t* args, int new_console, int wait) {
    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    wchar_t cmd[8192];
    DWORD code = 1;
    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    swprintf(cmd, 8192, L"\"%ls\"%ls", exe, args);
    if (!CreateProcessW(exe, cmd, NULL, NULL, FALSE, new_console ? CREATE_NEW_CONSOLE : 0, NULL, g_root, &si, &pi))
        return (DWORD)-1;
    if (wait) {
        WaitForSingleObject(pi.hProcess, INFINITE);
        GetExitCodeProcess(pi.hProcess, &code);
    } else {
        code = 0;
    }
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return code;
}

static int play_vanilla(const wchar_t* why) {
    wchar_t exe[MAX_PATH], args[4096];
    path_join(exe, L"gc\\AnimalCrossing-GC.exe");
    if (why) MessageBoxW(NULL, why, APP_TITLE, MB_ICONINFORMATION | MB_OK);
    if (!file_exists(exe)) {
        MessageBoxW(NULL,
            L"The original ACGC-PC-Port game executable is not included with this mod.\n\n"
            L"Download the original release from https://github.com/flyngmt/ACGC-PC-Port/releases and copy AnimalCrossing.exe to gc\\AnimalCrossing-GC.exe.\n"
            L"Copy the release's shaders folder beside this mod launcher.", APP_TITLE, MB_ICONERROR);
        return 1;
    }
    {
        wchar_t shader[MAX_PATH];
        path_join(shader, L"shaders\\default.frag");
        if (!file_exists(shader)) {
            MessageBoxW(NULL, L"The ACGC-PC-Port shaders folder is missing. Copy it from the original release into this folder.",
                        APP_TITLE, MB_ICONERROR);
            return 1;
        }
    }
    game_args(args, 4096);
    return (int)run(exe, args, 0, 1);
}

static int play_newleaf(void) {
    wchar_t exe[MAX_PATH], args[4096];
    path_join(exe, L"newleaf_cache\\game\\AnimalCrossing-NL.exe");
    game_args(args, 4096);
    return (int)run(exe, args, 0, 1);
}

static int cache_ready(void) {
    wchar_t exe[MAX_PATH], v[256];
    path_join(exe, L"newleaf_cache\\game\\AnimalCrossing-NL.exe");
    if (!file_exists(exe)) return 0;
    if (!read_text(L"newleaf_cache\\READY", v, 256)) return 0;
    return wcsstr(v, MOD_VERSION) != NULL;
}

static int has_gc_disc(void) {
    static const wchar_t* pats[] = { L"rom\\*.iso", L"rom\\*.gcm", L"rom\\*.ciso", L"*.iso", L"*.gcm", L"*.ciso" };
    int i;
    for (i = 0; i < 6; i++) {
        wchar_t p[MAX_PATH];
        WIN32_FIND_DATAW fd;
        HANDLE h;
        path_join(p, pats[i]);
        h = FindFirstFileW(p, &fd);
        if (h != INVALID_HANDLE_VALUE) { FindClose(h); return 1; }
    }
    return 0;
}

/* Returns 1 and fills out on success. folder = pick a directory instead of a file. */
static int pick_path(int folder, const wchar_t* folder_title, wchar_t* out) {
    IFileOpenDialog* dlg = NULL;
    IShellItem* item = NULL;
    PWSTR name = NULL;
    int ok = 0;
    if (FAILED(CoCreateInstance(&CLSID_FileOpenDialog, NULL, CLSCTX_INPROC_SERVER, &IID_IFileOpenDialog, (void**)&dlg)))
        return 0;
    if (folder) {
        DWORD opt;
        dlg->lpVtbl->GetOptions(dlg, &opt);
        dlg->lpVtbl->SetOptions(dlg, opt | FOS_PICKFOLDERS | FOS_FORCEFILESYSTEM);
        dlg->lpVtbl->SetTitle(dlg, folder_title);
    } else {
        COMDLG_FILTERSPEC spec[] = {
            { L"Decrypted 3DS ROM (*.3ds;*.cci;*.cxi;*.cia;*.app;*.romfs)", L"*.3ds;*.cci;*.cxi;*.cia;*.app;*.romfs" },
            { L"All files (*.*)", L"*.*" },
        };
        dlg->lpVtbl->SetFileTypes(dlg, 2, spec);
        dlg->lpVtbl->SetTitle(dlg, L"Select your Animal Crossing: New Leaf ROM");
    }
    if (SUCCEEDED(dlg->lpVtbl->Show(dlg, NULL)) && SUCCEEDED(dlg->lpVtbl->GetResult(dlg, &item)) &&
        SUCCEEDED(item->lpVtbl->GetDisplayName(item, SIGDN_FILESYSPATH, &name))) {
        wcsncpy(out, name, MAX_PATH - 1);
        out[MAX_PATH - 1] = 0;
        ok = 1;
        CoTaskMemFree(name);
    }
    if (item) item->lpVtbl->Release(item);
    dlg->lpVtbl->Release(dlg);
    return ok;
}

static int pick_acpc_source(wchar_t* out) {
    static const wchar_t* url = L"https://github.com/flyngmt/ACGC-PC-Port/tree/4099d246c927e75b4fd342ca13f4ac4395c55af5";
    MessageBoxW(NULL,
        L"This mod is an add-on for FlyingMeta's ACGC-PC-Port 0.9.3. It does not include that project.\n\n"
        L"The browser will open the pinned source page. Choose Code > Download ZIP, extract it, then select the folder containing pc, src and include.",
        APP_TITLE, MB_OK | MB_ICONINFORMATION);
    ShellExecuteW(NULL, L"open", url, NULL, NULL, SW_SHOWNORMAL);
    return pick_path(1, L"Select the extracted ACGC-PC-Port folder (contains pc, src and include)", out);
}

enum { CHOICE_FILE = 1001, CHOICE_FOLDER, CHOICE_VANILLA };

static int ask_choice(void) {
    TASKDIALOGCONFIG c;
    TASKDIALOG_BUTTON b[3] = {
        { CHOICE_FILE, L"Choose my New Leaf ROM file\nA decrypted .3ds, .cci, .cxi or .cia dump of your own cartridge or digital copy" },
        { CHOICE_FOLDER, L"Choose an extracted RomFS folder\nThe folder that contains Bg, Item, Strc ... (code.bin from exefs is used if it is next to it)" },
        { CHOICE_VANILLA, L"Play with the original GameCube graphics\nYou can set up the mod later with \"Set up New Leaf graphics\"" },
    };
    int pressed = CHOICE_VANILLA;
    ZeroMemory(&c, sizeof(c));
    c.cbSize = sizeof(c);
    c.dwFlags = TDF_USE_COMMAND_LINKS | TDF_ALLOW_DIALOG_CANCELLATION;
    c.pszWindowTitle = APP_TITLE;
    c.pszMainInstruction = L"Set up New Leaf graphics";
    c.pszContent = L"This mod replaces the GameCube graphics with ones converted from Animal Crossing: New Leaf. "
                   L"The ACGC-PC-Port source is not bundled; setup opens FlyingMeta's pinned source page so you can download it. "
                   L"The mod applies its changes to that source and converts graphics from your own ROMs.\n\n"
                   L"Setup runs once. It needs several GB of free space and takes several minutes. "
                   L"A console window shows its progress.";
    c.pButtons = b;
    c.cButtons = 3;
    c.nDefaultButton = CHOICE_FILE;
    if (FAILED(TaskDialogIndirect(&c, &pressed, NULL, NULL))) {
        int r = MessageBoxW(NULL, L"Set up New Leaf graphics now?\n\nYes = choose your New Leaf ROM file\nNo = play with the original GameCube graphics",
                            APP_TITLE, MB_YESNO | MB_ICONQUESTION);
        pressed = r == IDYES ? CHOICE_FILE : CHOICE_VANILLA;
    }
    if (pressed == IDCANCEL) pressed = CHOICE_VANILLA;
    return pressed;
}

static int run_setup(const wchar_t* rom, const wchar_t* base) {
    wchar_t py[MAX_PATH], args[4096], err[2048];
    DWORD code;
    path_join(py, L"runtime\\python\\python.exe");
    if (!file_exists(py)) {
        MessageBoxW(NULL, L"runtime\\python\\python.exe is missing. Please re-extract the release zip.", APP_TITLE, MB_ICONERROR);
        return 0;
    }
    swprintf(args, 4096, L" -s -X utf8 \"%ls\\mod\\pipeline\\setup_mod.py\" --root \"%ls\" --nl-rom \"%ls\" --base-source \"%ls\"", g_root, g_root, rom, base);
    code = run(py, args, 1, 1);
    if (code == 0 && cache_ready()) return 1;
    {
        wchar_t p[MAX_PATH];
        path_join(p, L"newleaf_cache\\acpc_source.txt");
        DeleteFileW(p); /* a rejected source must be selected again on the next setup attempt */
    }
    if (!read_text(L"newleaf_cache\\setup_error.txt", err, 2048))
        swprintf(err, 2048, L"The setup stopped with code %d. See newleaf_cache\\setup.log.", (int)code);
    {
        wchar_t msg[4096];
        swprintf(msg, 4096, L"New Leaf graphics could not be set up:\n\n%ls\n\nThe game will start with the original GameCube graphics. "
                            L"Run \"Set up New Leaf graphics\" to try again.", err);
        MessageBoxW(NULL, msg, APP_TITLE, MB_ICONWARNING | MB_OK);
    }
    return 0;
}

int WINAPI wWinMain(HINSTANCE inst, HINSTANCE prev, PWSTR cmdline, int show) {
    wchar_t rom[MAX_PATH], base[MAX_PATH];
    wchar_t* slash;
    int force_setup, choice;
    (void)inst; (void)prev; (void)cmdline; (void)show;
    GetModuleFileNameW(NULL, g_root, MAX_PATH);
    slash = wcsrchr(g_root, L'\\');
    if (slash) *slash = 0;
    SetCurrentDirectoryW(g_root);
    CoInitializeEx(NULL, COINIT_APARTMENTTHREADED | COINIT_DISABLE_OLE1DDE);
    {
        INITCOMMONCONTROLSEX icc = { sizeof(icc), ICC_STANDARD_CLASSES };
        InitCommonControlsEx(&icc);
    }

    if (has_flag(L"--vanilla")) return play_vanilla(NULL);
    force_setup = has_flag(L"--setup");
    if (!force_setup && cache_ready()) return play_newleaf();
    if (!force_setup) {
        wchar_t p[MAX_PATH];
        path_join(p, L"newleaf_cache\\SKIPPED");
        if (file_exists(p)) return play_vanilla(NULL);
    }
    if (!has_gc_disc()) {
        MessageBoxW(NULL, L"Place your Animal Crossing GameCube disc image (.iso, .gcm or .ciso) in the \"rom\" folder first. "
                          L"The game and the New Leaf setup both need it.", APP_TITLE, MB_ICONINFORMATION);
        return 1;
    }
    choice = ask_choice();
    if (choice == CHOICE_VANILLA) {
        wchar_t d[MAX_PATH];
        path_join(d, L"newleaf_cache");
        CreateDirectoryW(d, NULL);
        write_text(L"newleaf_cache\\SKIPPED", L"The player chose the GameCube graphics. Run AnimalCrossing.exe --setup to set up the mod.\r\n");
        return play_vanilla(NULL);
    }
    if (!pick_path(choice == CHOICE_FOLDER, L"Select the extracted New Leaf RomFS folder", rom)) return play_vanilla(NULL);
    {
        wchar_t saved[MAX_PATH];
        if (!read_text(L"newleaf_cache\\acpc_source.txt", saved, MAX_PATH) || !dir_exists(saved)) {
            if (!pick_acpc_source(base)) return play_vanilla(NULL);
            path_join(saved, L"newleaf_cache");
            CreateDirectoryW(saved, NULL);
            write_text(L"newleaf_cache\\acpc_source.txt", base);
        } else {
            wcsncpy(base, saved, MAX_PATH - 1);
            base[MAX_PATH - 1] = 0;
        }
    }
    {
        wchar_t p[MAX_PATH];
        path_join(p, L"newleaf_cache\\SKIPPED");
        DeleteFileW(p);
    }
    if (run_setup(rom, base)) return play_newleaf();
    return play_vanilla(NULL);
}
