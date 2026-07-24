// NativeLingo Tauri shell.
//
// On startup we spawn the Python FastAPI backend as a child process, bound to
// 127.0.0.1 with a random per-launch bearer token. The same token + backend URL
// are injected into the webview so the frontend can authenticate. The backend
// is killed when the app exits.

use std::fs::OpenOptions;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use tauri::{Manager, RunEvent};

struct BackendProcess(Mutex<Option<Child>>);

// Simple per-launch token: time + pid based, good enough to stop other local
// processes from driving the backend (it's bound to localhost anyway).
fn generate_token() -> String {
    use std::time::{SystemTime, UNIX_EPOCH};
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_nanos())
        .unwrap_or(0);
    format!("{:x}{:x}", nanos, std::process::id())
}

fn spawn_backend(
    token: &str,
    port: u16,
    resource_dir: &std::path::Path,
    data_dir: &std::path::Path,
    log_path: &std::path::Path,
) -> Option<Child> {
    // Bundled mode: the PyInstaller-frozen backend onedir lives under
    // Resources/resources/nativeLingoBackend/ (Tauri preserves the glob's
    // `resources/` prefix). In dev (no frozen binary present) we fall through
    // to running the venv python against the backend module.
    let resources = resource_dir.join("resources");
    let bundled_exe = resources.join("nativeLingoBackend").join("nativeLingoBackend");
    if bundled_exe.exists() {
        // A bundled app has no parent terminal; capture backend stdout/stderr to
        // a log file so "backend won't start" is diagnosable on user machines.
        // (Video/audio decode uses PyAV in-process — no PATH/ffmpeg setup needed.)
        let mut cmd = Command::new(&bundled_exe);
        cmd.env("NATIVELINGO_TOKEN", token)
            .env("NATIVELINGO_PORT", port.to_string())
            .env("NATIVELINGO_HOST", "127.0.0.1")
            .env("NATIVELINGO_DATA_DIR", data_dir);
        if let Ok(f) = OpenOptions::new().create(true).append(true).open(log_path) {
            cmd.stdout(Stdio::from(f));
        }
        if let Ok(f) = OpenOptions::new().create(true).append(true).open(log_path) {
            cmd.stderr(Stdio::from(f));
        }
        return cmd.spawn().ok();
    }

    // Dev mode: run the venv python against the backend module. Walk ancestors
    // for the project root (the dir holding backend/main.py).
    let project_root = resource_dir
        .ancestors()
        .find(|p| p.join("backend").join("main.py").exists())
        .map(|p| p.to_path_buf());

    let root = project_root.unwrap_or_else(|| std::path::PathBuf::from("."));
    let venv_python = root.join(".venv").join("bin").join("python");
    let python = if venv_python.exists() {
        venv_python
    } else {
        std::path::PathBuf::from("python3")
    };

    Command::new(python)
        .arg("-m")
        .arg("backend.main")
        .current_dir(&root)
        .env("NATIVELINGO_TOKEN", token)
        .env("NATIVELINGO_PORT", port.to_string())
        .env("NATIVELINGO_HOST", "127.0.0.1")
        .spawn()
        .ok()
}

fn main() {
    let token = generate_token();
    let port: u16 = 8756;
    let backend_url = format!("http://127.0.0.1:{}", port);

    let init_script = format!(
        "window.__NATIVELINGO_BACKEND__ = '{}'; window.__NATIVELINGO_TOKEN__ = '{}';",
        backend_url, token
    );

    let token_for_setup = token.clone();

    tauri::Builder::default()
        .manage(BackendProcess(Mutex::new(None)))
        .setup(move |app| {
            let resource_dir = app
                .path()
                .resource_dir()
                .unwrap_or_else(|_| std::path::PathBuf::from("."));
            // Per-app data dir (videos/ + user data) and log dir. Only the
            // bundled branch uses them, but computing them is harmless in dev.
            let data_dir = app
                .path()
                .app_data_dir()
                .unwrap_or_else(|_| std::path::PathBuf::from("."));
            let log_dir = app
                .path()
                .app_log_dir()
                .unwrap_or_else(|_| std::path::PathBuf::from("."));
            let _ = std::fs::create_dir_all(&data_dir);
            let _ = std::fs::create_dir_all(&log_dir);
            let log_path = log_dir.join("backend.log");
            let child =
                spawn_backend(&token_for_setup, port, &resource_dir, &data_dir, &log_path);
            *app.state::<BackendProcess>().0.lock().unwrap() = child;

            // inject backend url + token into the webview
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.eval(&init_script);
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| {
            if let RunEvent::ExitRequested { .. } = event {
                // kill the backend on exit
                if let Some(state) = app_handle.try_state::<BackendProcess>() {
                    if let Some(mut child) = state.0.lock().unwrap().take() {
                        let _ = child.kill();
                    }
                }
            }
        });
}
