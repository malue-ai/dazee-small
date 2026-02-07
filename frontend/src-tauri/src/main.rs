// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::process::Command as SysCommand;
use std::sync::Mutex;
use std::time::{Duration, Instant};
use tauri::{Emitter, Manager};

// ============================================================================
// 常量
// ============================================================================

/// 打包模式下 sidecar 使用的端口
const SIDECAR_PORT: u16 = 18900;

/// 开发模式下后端默认端口
const DEV_PORT: u16 = 8000;

/// 后端启动超时（秒）
const BACKEND_STARTUP_TIMEOUT_SECS: u64 = 60;

/// 健康检查轮询间隔（毫秒）
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

/// 后端运行状态
struct BackendState {
    /// sidecar 进程（仅打包模式）
    child: Option<tauri_plugin_shell::process::CommandChild>,
    /// 后端实际运行端口
    port: u16,
    /// 是否为 sidecar 模式（打包模式）
    is_sidecar: bool,
}

// ============================================================================
// Sidecar 管理
// ============================================================================

/// 获取应用数据目录
fn get_app_data_dir(app: &tauri::AppHandle) -> String {
    app.path()
        .app_data_dir()
        .unwrap_or_else(|_| std::path::PathBuf::from("."))
        .to_string_lossy()
        .to_string()
}

/// 健康检查 URL
fn health_url(port: u16) -> String {
    format!("http://127.0.0.1:{}/health", port)
}

/// 等待后端健康检查通过
fn wait_for_backend_ready(port: u16) -> bool {
    let start = Instant::now();
    let timeout = Duration::from_secs(BACKEND_STARTUP_TIMEOUT_SECS);
    let poll_interval = Duration::from_millis(BACKEND_HEALTH_POLL_MS);
    let url = health_url(port);

    eprintln!("[sidecar] 等待后端就绪 (port={})...", port);

    loop {
        if start.elapsed() > timeout {
            eprintln!("[sidecar] 后端启动超时 ({}s)", BACKEND_STARTUP_TIMEOUT_SECS);
            return false;
        }

        match ureq::get(&url)
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
async fn get_backend_url(state: tauri::State<'_, Mutex<BackendState>>) -> Result<String, String> {
    let port = state.lock().map_err(|e| e.to_string())?.port;
    Ok(format!("http://127.0.0.1:{}/api", port))
}

/// 获取后端 WebSocket URL
#[tauri::command]
async fn get_backend_ws_url(state: tauri::State<'_, Mutex<BackendState>>) -> Result<String, String> {
    let port = state.lock().map_err(|e| e.to_string())?.port;
    Ok(format!("ws://127.0.0.1:{}/api", port))
}

/// 检查后端是否就绪
#[tauri::command]
async fn is_backend_ready(state: tauri::State<'_, Mutex<BackendState>>) -> Result<bool, String> {
    let port = state.lock().map_err(|e| e.to_string())?.port;
    let url = health_url(port);
    match ureq::get(&url)
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

/// 判断当前是否为 release 构建（打包模式）
fn is_release_build() -> bool {
    // cfg!(debug_assertions) 在 debug 构建（cargo run / tauri dev）时为 true
    // 在 release 构建（tauri build）时为 false
    !cfg!(debug_assertions)
}

// ============================================================================
// 主函数
// ============================================================================

fn main() {
    // 初始状态：dev 模式连 8000，release 模式连 18900
    let initial_port = if is_release_build() { SIDECAR_PORT } else { DEV_PORT };

    eprintln!(
        "[app] 启动模式: {} (后端端口: {})",
        if is_release_build() { "release/打包" } else { "dev/开发" },
        initial_port
    );

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_notification::init())
        .manage(Mutex::new(BackendState {
            child: None,
            port: initial_port,
            is_sidecar: false,
        }))
        .setup(|app| {
            let handle = app.handle().clone();

            if is_release_build() {
                // ============ 打包模式：启动 sidecar ============
                let data_dir = get_app_data_dir(app.handle());

                // 确保数据目录存在
                let _ = std::fs::create_dir_all(&data_dir);

                eprintln!(
                    "[sidecar] 启动后端 sidecar (port={}, data-dir={})",
                    SIDECAR_PORT, data_dir
                );

                // 使用 Tauri shell plugin 的 sidecar API
                use tauri_plugin_shell::ShellExt;
                use tauri_plugin_shell::process::CommandEvent;

                let sidecar_result = app.handle()
                    .shell()
                    .sidecar("zenflux-backend")
                    .map(|cmd| {
                        cmd.args([
                            "--port",
                            &SIDECAR_PORT.to_string(),
                            "--data-dir",
                            &data_dir,
                        ])
                    });

                match sidecar_result {
                    Ok(cmd) => {
                        match cmd.spawn() {
                            Ok((mut rx, child)) => {
                                eprintln!("[sidecar] sidecar 进程已启动");

                                // 保存进程句柄
                                if let Ok(mut guard) = handle.state::<Mutex<BackendState>>().lock() {
                                    guard.child = Some(child);
                                    guard.is_sidecar = true;
                                }

                                // 在后台线程读取 sidecar 输出
                                let log_handle = handle.clone();
                                tauri::async_runtime::spawn(async move {
                                    while let Some(event) = rx.recv().await {
                                        match event {
                                            CommandEvent::Stdout(line) => {
                                                let line = String::from_utf8_lossy(&line);
                                                eprintln!("[sidecar:stdout] {}", line.trim());
                                            }
                                            CommandEvent::Stderr(line) => {
                                                let line = String::from_utf8_lossy(&line);
                                                eprintln!("[sidecar:stderr] {}", line.trim());
                                            }
                                            CommandEvent::Terminated(status) => {
                                                eprintln!("[sidecar] 进程已退出: {:?}", status);
                                                let _ = log_handle.emit("backend-stopped", true);
                                                break;
                                            }
                                            _ => {}
                                        }
                                    }
                                });

                                // 在后台线程等待后端就绪
                                std::thread::spawn(move || {
                                    let ready = wait_for_backend_ready(SIDECAR_PORT);
                                    if !ready {
                                        eprintln!("[sidecar] 警告: 后端未在预期时间内就绪");
                                    }
                                    let _ = handle.emit("backend-ready", ready);
                                });
                            }
                            Err(e) => {
                                eprintln!("[sidecar] spawn 失败: {}", e);
                                let _ = handle.emit("backend-ready", false);
                            }
                        }
                    }
                    Err(e) => {
                        eprintln!("[sidecar] sidecar 命令创建失败: {}", e);
                        let _ = handle.emit("backend-ready", false);
                    }
                }
            } else {
                // ============ 开发模式：假设后端已手动启动在 8000 端口 ============
                eprintln!(
                    "[dev] 开发模式，请确保后端已在 localhost:{} 启动",
                    DEV_PORT
                );

                // 在后台线程检查开发后端是否可用
                std::thread::spawn(move || {
                    let url = health_url(DEV_PORT);
                    match ureq::get(&url)
                        .timeout(Duration::from_secs(3))
                        .call()
                    {
                        Ok(resp) if resp.status() == 200 => {
                            eprintln!("[dev] 开发后端已就绪 (port={})", DEV_PORT);
                            let _ = handle.emit("backend-ready", true);
                        }
                        _ => {
                            eprintln!(
                                "[dev] 警告: 开发后端未就绪 (port={})，请手动启动",
                                DEV_PORT
                            );
                            // 仍然通知前端，让页面能显示
                            let _ = handle.emit("backend-ready", true);
                        }
                    }
                });
            }

            Ok(())
        })
        .on_window_event(|window, event| {
            // 应用关闭时终止 sidecar
            if let tauri::WindowEvent::Destroyed = event {
                let state = window.app_handle().state::<Mutex<BackendState>>();
                let mut guard = match state.lock() {
                    Ok(g) => g,
                    Err(_) => return,
                };
                if guard.is_sidecar {
                    if let Some(child) = guard.child.take() {
                        eprintln!("[sidecar] 正在终止后端进程...");
                        let _ = child.kill();
                        eprintln!("[sidecar] 后端进程已终止");
                    }
                }
                drop(guard);
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
