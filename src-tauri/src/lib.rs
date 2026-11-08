use serde::Deserialize;
use std::io::{BufRead, BufReader, BufWriter, Write};
use std::path::PathBuf;
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use tauri::{Emitter, Manager, State};

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
    fn start(resource_dir: PathBuf) -> Result<Self, String> {
        let data_dir = std::env::var_os("CETHER_DATA_DIR")
            .map(PathBuf::from)
            .or_else(|| dirs_data_dir())
            .ok_or_else(|| "could not resolve application data directory".to_string())?;
        std::fs::create_dir_all(&data_dir).map_err(|e| e.to_string())?;
        let project_root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).parent()
            .ok_or_else(|| "could not resolve project root".to_string())?.to_path_buf();
        let bundled_python = resource_dir.join("python-runtime").join("cether-python.exe");
        let configured_python = std::env::var_os("CETHER_PYTHON").map(PathBuf::from);
        let local_python = project_root.join(".venv").join("Scripts").join("python.exe");
        let python = bundled_python.is_file().then_some(bundled_python)
            .or(configured_python)
            .or_else(|| local_python.is_file().then_some(local_python))
            .unwrap_or_else(|| PathBuf::from("python"));
        let frozen_runner = python.file_stem().and_then(|name| name.to_str()) == Some("cether-python");
        let mut command = Command::new(python);
        if frozen_runner {
            command.arg(&data_dir).current_dir(&resource_dir).env("CETHER_RESOURCE_DIR", &resource_dir);
        } else {
            command.args(["-m", "cether.desktop"]).arg(&data_dir)
                .current_dir(&project_root).env("PYTHONPATH", python_path());
        }
        let mut child = command
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
struct BridgeState(Arc<Mutex<PythonBridge>>, Arc<AtomicBool>);

#[tauri::command]
fn app_bootstrap(state: State<'_, BridgeState>) -> Result<serde_json::Value, String> {
    state.0.lock().map_err(|e| e.to_string())?.request("bootstrap", serde_json::json!({}))
}

#[tauri::command]
fn send_message(text: String, state: State<'_, BridgeState>) -> Result<serde_json::Value, String> {
    state.0.lock().map_err(|e| e.to_string())?.request("send_message", serde_json::json!({"text": text}))
}

#[tauri::command]
fn create_role(name: String, preset_id: Option<String>, state: State<'_, BridgeState>) -> Result<serde_json::Value, String> {
    state.0.lock().map_err(|e| e.to_string())?.request("create_role", serde_json::json!({"name": name, "preset_id": preset_id.unwrap_or_default()}))
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

#[tauri::command]
fn runtime_action(action: String, payload: Option<serde_json::Value>, state: State<'_, BridgeState>) -> Result<serde_json::Value, String> {
    state.0.lock().map_err(|e| e.to_string())?.request(action.as_str(), payload.unwrap_or_else(|| serde_json::json!({})))
}

#[tauri::command]
fn runtime_events_ready(state: State<'_, BridgeState>) {
    state.1.store(true, Ordering::Release);
}

#[tauri::command]
fn runtime_events(cursor: Option<u64>, limit: Option<u32>, state: State<'_, BridgeState>) -> Result<serde_json::Value, String> {
    state.0.lock().map_err(|e| e.to_string())?.request("runtime_events", serde_json::json!({"cursor": cursor.unwrap_or(0), "limit": limit.unwrap_or(100)}))
}

#[tauri::command]
fn config_read(name: String, state: State<'_, BridgeState>) -> Result<serde_json::Value, String> {
    state.0.lock().map_err(|e| e.to_string())?.request("config_read", serde_json::json!({"name": name}))
}

#[tauri::command]
fn config_write(name: String, values: serde_json::Value, state: State<'_, BridgeState>) -> Result<serde_json::Value, String> {
    state.0.lock().map_err(|e| e.to_string())?.request("config_write", serde_json::json!({"name": name, "values": values}))
}

#[tauri::command]
fn complete_onboarding(local_fallback: bool, state: State<'_, BridgeState>) -> Result<serde_json::Value, String> {
    state.0.lock().map_err(|e| e.to_string())?.request("complete_onboarding", serde_json::json!({"local_fallback": local_fallback}))
}

#[tauri::command]
fn set_expression_presentation(mode: String, state: State<'_, BridgeState>) -> Result<serde_json::Value, String> {
    state.0.lock().map_err(|e| e.to_string())?.request("set_expression_presentation", serde_json::json!({"mode": mode}))
}

#[tauri::command]
fn memory_starfield(state: State<'_, BridgeState>) -> Result<serde_json::Value, String> {
    state.0.lock().map_err(|e| e.to_string())?.request("memory_starfield", serde_json::json!({}))
}

#[tauri::command]
async fn pick_file(app: tauri::AppHandle) -> Result<Option<String>, String> {
    use tauri_plugin_dialog::DialogExt;
    let file = app.dialog().file().blocking_pick_file();
    Ok(file.map(|f| f.to_string()))
}

#[tauri::command]
async fn pick_folder(app: tauri::AppHandle) -> Result<Option<String>, String> {
    use tauri_plugin_dialog::DialogExt;
    let folder = app.dialog().file().blocking_pick_folder();
    Ok(folder.map(|f| f.to_string()))
}

#[tauri::command]
async fn save_file(app: tauri::AppHandle, default_name: Option<String>) -> Result<Option<String>, String> {
    use tauri_plugin_dialog::DialogExt;
    let mut builder = app.dialog().file();
    if let Some(name) = default_name {
        builder = builder.set_file_name(&name);
    }
    let file = builder.blocking_save_file();
    Ok(file.map(|f| f.to_string()))
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
    let event_ready = Arc::new(AtomicBool::new(false));
    tauri::Builder::default()
        .setup(move |app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(tauri_plugin_log::Builder::default().level(log::LevelFilter::Info).build())?;
            }
            let app_handle = app.handle().clone();
            let resource_dir = app.path().resource_dir().map_err(std::io::Error::other)?;
            let bridge = PythonBridge::start(resource_dir).map_err(std::io::Error::other)?;
            app.manage(BridgeState(Arc::new(Mutex::new(bridge)), event_ready.clone()));
            let event_state = app.state::<BridgeState>().inner().clone();
            let ready = event_state.1.clone();
            std::thread::spawn(move || {
                let mut cursor = 0u64;
                let mut role_id: Option<String> = None;
                let mut delay = std::time::Duration::from_millis(250);
                loop {
                    if !ready.load(Ordering::Acquire) {
                        std::thread::sleep(std::time::Duration::from_millis(50));
                        continue;
                    }
                    let result = event_state.0.lock().map_err(|error| error.to_string())
                        .and_then(|mut bridge| bridge.request("runtime_events", serde_json::json!({"cursor": cursor, "limit": 100})));
                    match result {
                        Ok(batch) => {
                            let next_role = batch.get("role_id").and_then(|value| value.as_str()).map(str::to_owned);
                            if next_role != role_id {
                                cursor = 0;
                                role_id = next_role;
                                continue;
                            }
                            cursor = batch.get("cursor").and_then(|value| value.as_u64()).unwrap_or(cursor);
                            let events = batch.get("events").cloned().unwrap_or_else(|| serde_json::json!([]));
                            if events.as_array().is_some_and(|rows| !rows.is_empty()) {
                                let _ = app_handle.emit("cether://runtime-events", events);
                            }
                            delay = std::time::Duration::from_millis(300);
                        }
                        Err(error) => {
                            let _ = app_handle.emit("cether://runtime-error", error);
                            delay = std::cmp::min(delay * 2, std::time::Duration::from_secs(15));
                        }
                    }
                    std::thread::sleep(delay);
                }
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![app_bootstrap, send_message, create_role, switch_role, ui_action, memory_timeline, runtime_action, runtime_events_ready, runtime_events, config_read, config_write, complete_onboarding, set_expression_presentation, memory_starfield, pick_file, pick_folder, save_file])
        .run(tauri::generate_context!())
        .expect("error while building tauri application");
}
