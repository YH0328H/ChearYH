use serde::Deserialize;
use std::io::{BufRead, BufReader, BufWriter, Write};
use std::path::PathBuf;
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
use std::sync::{Arc, Mutex};
use tauri::State;

#[derive(Deserialize)]
struct BridgeResponse {
    id: u64,
    ok: bool,
    result: Option<serde_json::Value>,
    error: Option<String>,
}

struct PythonBridge {
    child: Child,
    input: BufWriter<ChildStdin>,
    output: BufReader<ChildStdout>,
    next_id: u64,
}

impl PythonBridge {
    fn start() -> Result<Self, String> {
        let data_dir = std::env::var_os("CETHER_DATA_DIR")
            .map(PathBuf::from)
            .or_else(|| dirs_data_dir())
            .ok_or_else(|| "could not resolve application data directory".to_string())?;
        std::fs::create_dir_all(&data_dir).map_err(|e| e.to_string())?;
        let python = std::env::var("CETHER_PYTHON").unwrap_or_else(|_| "python".to_string());
        let mut child = Command::new(python)
            .args(["-m", "cether.desktop"])
            .arg(&data_dir)
            .env("PYTHONPATH", python_path())
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .spawn()
            .map_err(|e| format!("failed to start Python runtime: {e}"))?;
        let input = child.stdin.take().ok_or("Python stdin unavailable")?;
        let output = child.stdout.take().ok_or("Python stdout unavailable")?;
        Ok(Self { child, input: BufWriter::new(input), output: BufReader::new(output), next_id: 1 })
    }

    fn request(&mut self, action: &str, payload: serde_json::Value) -> Result<serde_json::Value, String> {
        if self.child.try_wait().map_err(|e| e.to_string())?.is_some() {
            return Err("Python runtime has exited".to_string());
        }
        let id = self.next_id;
        self.next_id += 1;
        let mut value = payload.as_object().cloned().unwrap_or_default();
        value.insert("id".into(), id.into());
        value.insert("action".into(), action.into());
        serde_json::to_writer(&mut self.input, &value).map_err(|e| e.to_string())?;
        self.input.write_all(b"\n").map_err(|e| e.to_string())?;
        self.input.flush().map_err(|e| e.to_string())?;
        let mut line = String::new();
        self.output.read_line(&mut line).map_err(|e| e.to_string())?;
        if line.is_empty() { return Err("Python runtime closed its output".to_string()); }
        let response: BridgeResponse = serde_json::from_str(&line).map_err(|e| format!("invalid Python response: {e}"))?;
        if response.id != id { return Err("Python bridge response id mismatch".to_string()); }
        if !response.ok { return Err(response.error.unwrap_or_else(|| "Python runtime error".to_string())); }
        response.result.ok_or_else(|| "Python runtime returned no result".to_string())
    }
}

impl Drop for PythonBridge {
    fn drop(&mut self) { let _ = self.child.kill(); let _ = self.child.wait(); }
}

#[derive(Clone)]
struct BridgeState(Arc<Mutex<PythonBridge>>);

#[tauri::command]
fn app_bootstrap(state: State<'_, BridgeState>) -> Result<serde_json::Value, String> {
    state.0.lock().map_err(|e| e.to_string())?.request("bootstrap", serde_json::json!({}))
}

#[tauri::command]
fn send_message(text: String, state: State<'_, BridgeState>) -> Result<serde_json::Value, String> {
    state.0.lock().map_err(|e| e.to_string())?.request("send_message", serde_json::json!({"text": text}))
}

#[tauri::command]
fn create_role(name: String, state: State<'_, BridgeState>) -> Result<serde_json::Value, String> {
    state.0.lock().map_err(|e| e.to_string())?.request("create_role", serde_json::json!({"name": name}))
}

#[tauri::command]
fn switch_role(role_id: String, state: State<'_, BridgeState>) -> Result<serde_json::Value, String> {
    state.0.lock().map_err(|e| e.to_string())?.request("switch_role", serde_json::json!({"role_id": role_id}))
}

#[tauri::command]
fn ui_action(action: String, payload: Option<serde_json::Value>, state: State<'_, BridgeState>) -> Result<serde_json::Value, String> {
    state.0.lock().map_err(|e| e.to_string())?.request("ui_action", serde_json::json!({"ui_action": action, "payload": payload.unwrap_or_else(|| serde_json::json!({}))}))
}

#[tauri::command]
fn memory_timeline(cursor: Option<String>, limit: Option<u32>, state: State<'_, BridgeState>) -> Result<serde_json::Value, String> {
    state.0.lock().map_err(|e| e.to_string())?.request("memory_timeline", serde_json::json!({"cursor": cursor, "limit": limit.unwrap_or(100)}))
}

fn python_path() -> String {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).parent().unwrap().join("src");
    if let Some(existing) = std::env::var_os("PYTHONPATH") {
        format!("{};{}", root.display(), existing.to_string_lossy())
    } else { root.display().to_string() }
}

fn dirs_data_dir() -> Option<PathBuf> {
    std::env::var_os("APPDATA").map(PathBuf::from).map(|p| p.join("Cether"))
        .or_else(|| std::env::var_os("HOME").map(PathBuf::from).map(|p| p.join(".local/share/Cether")))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let bridge = PythonBridge::start().expect("failed to initialize Cether Python runtime");
    tauri::Builder::default()
        .manage(BridgeState(Arc::new(Mutex::new(bridge))))
        .setup(|app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(tauri_plugin_log::Builder::default().level(log::LevelFilter::Info).build())?;
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![app_bootstrap, send_message, create_role, switch_role, ui_action, memory_timeline])
        .run(tauri::generate_context!())
        .expect("error while building tauri application");
}
