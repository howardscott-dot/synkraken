use serde::Serialize;
use std::env;
use std::path::PathBuf;
use std::process::Command;
use tauri::Manager;

#[derive(Serialize)]
struct RuntimeRecovery {
    ok: bool,
    message: String,
}

#[tauri::command]
fn ensure_synkraken_runtime() -> RuntimeRecovery {
    let command = synkraken_command();
    let health = Command::new(&command).arg("health").arg("--json").output();
    if health.as_ref().is_ok_and(|output| output.status.success()) {
        return RuntimeRecovery { ok: true, message: "Connected.".into() };
    }
    match Command::new(&command).arg("start").output() {
        Ok(output) if output.status.success() => RuntimeRecovery {
            ok: true,
            message: "SynKraken started and connected.".into(),
        },
        Ok(output) => RuntimeRecovery {
            ok: false,
            message: String::from_utf8_lossy(&output.stderr).trim().to_string(),
        },
        Err(error) => RuntimeRecovery {
            ok: false,
            message: format!("SynKraken command is unavailable: {error}"),
        },
    }
}

fn synkraken_command() -> PathBuf {
    if let Some(path) = env::var_os("SYNKRAKEN_CLI") {
        return PathBuf::from(path);
    }
    if let Some(home) = env::var_os("HOME") {
        let home = PathBuf::from(home);
        for candidate in [
            home.join(".local/bin/synkraken"),
            home.join(".synkraken/venv/bin/synkraken"),
        ] {
            if candidate.is_file() {
                return candidate;
            }
        }
    }
    PathBuf::from("synkraken")
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_http::init())
        .setup(|app| {
            let daemon_url = std::env::var("SYNKRAKEN_URL")
                .unwrap_or_else(|_| "http://127.0.0.1:9460".to_string());

            if let Some(window) = app.get_webview_window("main") {
                window
                    .eval(&format!(
                        "window.__SYNKRAKEN_DAEMON_URL__ = '{}';",
                        daemon_url
                    ))
                    .ok();
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![ensure_synkraken_runtime])
        .run(tauri::generate_context!())
        .expect("failed to run SynKraken Console");
}
