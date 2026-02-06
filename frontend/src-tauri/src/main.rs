// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::process::Command as SysCommand;
use std::sync::Mutex;
use std::time::{Duration, Instant};
use tauri::Manager;

// ============================================================================
// 常量
// ============================================================================

const BACKEND_PORT: u16 = 18900;
const BACKEND_HEALTH_URL: &str = "http://localhost:18900/health";
const BACKEND_STARTUP_TIMEOUT_SECS: u64 = 60;
const BACKEND_HEALTH_POLL_MS: u64 = 500;

// ============================================================================
// 数据结构定义
// ============================================================================

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NodeInfo {
    pub node_id: String,
    pub display_name: String,
    pub platform: String,
    pub version: String,
    pub capabilities: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ShellResult {
    pub success: bool,
    pub stdout: String,
    pub stderr: String,
    pub exit_code: i32,
    pub elapsed_ms: u64,
    pub timed_out: bool,
}

/// Sidecar 进程状态
struct SidecarState {
    child: Option<std::process::Child>,
}

// ============================================================================
// Sidecar 管理
// ============================================================================

/// 获取应用数据目录（平台标准路径）
fn get_app_data_dir(app: &tauri::AppHandle) -> String {
    app.path()
        .app_data_dir()
        .unwrap_or_else(|_| std::path::PathBuf::from("."))
        .to_string_lossy()
        .to_string()
}

/// 启动 Python 后端 sidecar 进程
fn start_sidecar(app: &tauri::AppHandle) -> Option<std::process::Child> {
    let data_dir = get_app_data_dir(app);

    // 解析 sidecar 二进制路径
    let sidecar_path = app
        .path()
        .resource_dir()
        .ok()
        .map(|dir| {
            let binary_name = if cfg!(target_os = "windows") {
                "zenflux-backend.exe"
            } else {
                "zenflux-backend"
            };
            dir.join("binaries").join(binary_name)
        });

    let sidecar_path = match sidecar_path {
        Some(p) if p.exists() => p,
        _ => {
            eprintln!("[sidecar] 二进制文件不存在，跳过 sidecar 启动（开发模式）");
            return None;
        }
    };

    eprintln!(
        "[sidecar] 启动后端: {} --port {} --data-dir {}",
        sidecar_path.display(),
        BACKEND_PORT,
        data_dir
    );

    // 确保数据目录存在
    let _ = std::fs::create_dir_all(&data_dir);

    match SysCommand::new(&sidecar_path)
        .args([
            "--port",
            &BACKEND_PORT.to_string(),
            "--data-dir",
            &data_dir,
        ])
        .spawn()
    {
        Ok(child) => {
            eprintln!("[sidecar] 进程已启动, PID: {}", child.id());
            Some(child)
        }
        Err(e) => {
            eprintln!("[sidecar] 启动失败: {}", e);
            None
        }
    }
}

/// 等待后端健康检查通过
fn wait_for_backend_ready() -> bool {
    let start = Instant::now();
    let timeout = Duration::from_secs(BACKEND_STARTUP_TIMEOUT_SECS);
    let poll_interval = Duration::from_millis(BACKEND_HEALTH_POLL_MS);

    eprintln!("[sidecar] 等待后端就绪...");

    loop {
        if start.elapsed() > timeout {
            eprintln!("[sidecar] 后端启动超时 ({}s)", BACKEND_STARTUP_TIMEOUT_SECS);
            return false;
        }

        // 尝试 HTTP 健康检查
        match ureq::get(BACKEND_HEALTH_URL)
            .timeout(Duration::from_secs(2))
            .call()
        {
            Ok(resp) if resp.status() == 200 => {
                let elapsed_ms = start.elapsed().as_millis();
                eprintln!("[sidecar] 后端就绪 ({}ms)", elapsed_ms);
                return true;
            }
            _ => {
                std::thread::sleep(poll_interval);
            }
        }
    }
}

// ============================================================================
// Tauri 命令
// ============================================================================

/// 获取后端 API 基础 URL
#[tauri::command]
async fn get_backend_url() -> Result<String, String> {
    Ok(format!("http://localhost:{}/api", BACKEND_PORT))
}

/// 获取后端 WebSocket URL
#[tauri::command]
async fn get_backend_ws_url() -> Result<String, String> {
    Ok(format!("ws://localhost:{}/api", BACKEND_PORT))
}

/// 检查后端是否就绪
#[tauri::command]
async fn is_backend_ready() -> Result<bool, String> {
    match ureq::get(BACKEND_HEALTH_URL)
        .timeout(Duration::from_secs(2))
        .call()
    {
        Ok(resp) if resp.status() == 200 => Ok(true),
        _ => Ok(false),
    }
}

/// 执行 Shell 命令
#[tauri::command]
async fn run_command(
    command: Vec<String>,
    cwd: Option<String>,
    env: Option<HashMap<String, String>>,
    timeout_ms: Option<u64>,
) -> Result<ShellResult, String> {
    if command.is_empty() {
        return Err("Command cannot be empty".to_string());
    }

    let start = Instant::now();
    let _timeout = timeout_ms.unwrap_or(30000);

    let mut cmd = SysCommand::new(&command[0]);
    if command.len() > 1 {
        cmd.args(&command[1..]);
    }

    if let Some(dir) = cwd {
        cmd.current_dir(dir);
    }

    if let Some(env_vars) = env {
        for (key, value) in env_vars {
            if !is_blocked_env_key(&key) {
                cmd.env(key, value);
            }
        }
    }

    match cmd.output() {
        Ok(output) => {
            let elapsed_ms = start.elapsed().as_millis() as u64;
            let stdout = String::from_utf8_lossy(&output.stdout).to_string();
            let stderr = String::from_utf8_lossy(&output.stderr).to_string();

            let max_len = 200000;
            let stdout = if stdout.len() > max_len {
                format!("{}...(truncated)", &stdout[..max_len])
            } else {
                stdout
            };
            let stderr = if stderr.len() > max_len {
                format!("{}...(truncated)", &stderr[..max_len])
            } else {
                stderr
            };

            Ok(ShellResult {
                success: output.status.success(),
                stdout,
                stderr,
                exit_code: output.status.code().unwrap_or(-1),
                elapsed_ms,
                timed_out: false,
            })
        }
        Err(e) => Err(format!("Failed to execute command: {}", e)),
    }
}

#[tauri::command]
async fn which_command(executable: String) -> Result<Option<String>, String> {
    let result =
        run_command(vec!["which".to_string(), executable], None, None, Some(5000)).await?;
    if result.success {
        Ok(Some(result.stdout.trim().to_string()))
    } else {
        Ok(None)
    }
}

#[tauri::command]
async fn get_node_info() -> Result<NodeInfo, String> {
    let node_id = format!("node-{}", &uuid::Uuid::new_v4().to_string()[..8]);
    let hostname = hostname::get()
        .map(|h| h.to_string_lossy().to_string())
        .unwrap_or_else(|_| "Unknown".to_string());

    let platform = if cfg!(target_os = "macos") {
        "darwin"
    } else if cfg!(target_os = "windows") {
        "win32"
    } else if cfg!(target_os = "linux") {
        "linux"
    } else {
        "unknown"
    };

    let mut capabilities = vec![
        "system.run".to_string(),
        "system.which".to_string(),
        "system.notify".to_string(),
    ];

    #[cfg(target_os = "macos")]
    {
        capabilities.push("camera.snap".to_string());
        capabilities.push("screen.record".to_string());
        capabilities.push("location.get".to_string());
    }

    Ok(NodeInfo {
        node_id,
        display_name: hostname,
        platform: platform.to_string(),
        version: env!("CARGO_PKG_VERSION").to_string(),
        capabilities,
    })
}

#[tauri::command]
async fn open_system_preferences(pane: String) -> Result<(), String> {
    #[cfg(target_os = "macos")]
    {
        let url = match pane.as_str() {
            "camera" => {
                "x-apple.systempreferences:com.apple.preference.security?Privacy_Camera"
            }
            "screen" => {
                "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
            }
            "location" => {
                "x-apple.systempreferences:com.apple.preference.security?Privacy_LocationServices"
            }
            "accessibility" => {
                "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
            }
            _ => return Err(format!("Unknown preference pane: {}", pane)),
        };

        SysCommand::new("open")
            .arg(url)
            .spawn()
            .map_err(|e| e.to_string())?;
    }

    #[cfg(not(target_os = "macos"))]
    {
        let _ = pane;
        return Err("System preferences not supported on this platform".to_string());
    }

    Ok(())
}

// ============================================================================
// 辅助函数
// ============================================================================

fn is_blocked_env_key(key: &str) -> bool {
    let blocked_keys = ["NODE_OPTIONS", "PYTHONHOME", "PYTHONPATH", "LD_PRELOAD"];
    let blocked_prefixes = ["DYLD_", "LD_"];

    if blocked_keys.contains(&key) {
        return true;
    }

    for prefix in blocked_prefixes {
        if key.starts_with(prefix) {
            return true;
        }
    }

    false
}

// ============================================================================
// 主函数
// ============================================================================

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_notification::init())
        .manage(Mutex::new(SidecarState { child: None }))
        .setup(|app| {
            let handle = app.handle().clone();

            // 在后台线程启动 sidecar（避免阻塞 UI）
            std::thread::spawn(move || {
                if let Some(child) = start_sidecar(&handle) {
                    // 保存进程句柄
                    let state = handle.state::<Mutex<SidecarState>>();
                    if let Ok(mut guard) = state.lock() {
                        guard.child = Some(child);
                    }

                    // 等待后端就绪
                    let ready = wait_for_backend_ready();
                    if !ready {
                        eprintln!("[sidecar] 警告: 后端未在预期时间内就绪");
                    }

                    // 通知前端后端已就绪
                    let _ = handle.emit("backend-ready", ready);
                } else {
                    // 开发模式：假设后端已手动启动
                    let _ = handle.emit("backend-ready", true);
                }
            });

            Ok(())
        })
        .on_window_event(|window, event| {
            // 应用关闭时终止 sidecar
            if let tauri::WindowEvent::Destroyed = event {
                let state = window.app_handle().state::<Mutex<SidecarState>>();
                if let Ok(mut guard) = state.lock() {
                    if let Some(ref mut child) = guard.child {
                        eprintln!("[sidecar] 正在终止后端进程...");
                        let _ = child.kill();
                        let _ = child.wait();
                        eprintln!("[sidecar] 后端进程已终止");
                    }
                }
            }
        })
        .invoke_handler(tauri::generate_handler![
            get_backend_url,
            get_backend_ws_url,
            is_backend_ready,
            run_command,
            which_command,
            get_node_info,
            open_system_preferences,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
