// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::io::Write;
use std::process::Command as SysCommand;
use std::sync::Mutex;
use std::time::{Duration, Instant};
use tauri::{Emitter, Manager};
use tauri::menu::{MenuBuilder, MenuItemBuilder};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};

/// 写入调试日志文件（用于诊断 open/Spotlight 启动问题）
fn debug_log(msg: &str) {
    eprintln!("{}", msg);
    if let Ok(data_dir) = std::env::var("HOME") {
        let log_path = format!(
            "{}/Library/Application Support/com.zenflux.agent/sidecar-debug.log",
            data_dir
        );
        if let Ok(mut f) = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(&log_path)
        {
            let now = chrono::Local::now().format("%H:%M:%S%.3f");
            let _ = writeln!(f, "[{}] {}", now, msg);
        }
    }
}

// ============================================================================
// 常量
// ============================================================================

/// 打包模式下 sidecar 首选端口
const SIDECAR_PORT: u16 = 18900;

/// 端口搜索范围：如果首选端口被占用，依次尝试 +1, +2, ..., +RANGE
const SIDECAR_PORT_RANGE: u16 = 10;

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

/// 在指定范围内寻找可用端口
///
/// 从 preferred 端口开始，依次尝试绑定 preferred..preferred+range，
/// 返回第一个可用的端口。如果全部被占用，返回 preferred（sidecar 启动时会报错）。
fn find_available_port(preferred: u16, range: u16) -> u16 {
    for port in preferred..preferred.saturating_add(range) {
        if std::net::TcpListener::bind(("127.0.0.1", port)).is_ok() {
            return port;
        }
    }
    debug_log(&format!(
        "[sidecar] 端口 {}..{} 全部被占用，使用默认端口 {}",
        preferred,
        preferred.saturating_add(range),
        preferred
    ));
    preferred
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

/// 等待后端健康检查通过（备用，首次启动向导等场景可能需要）
#[allow(dead_code)]
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

/// 终止 sidecar 后端进程
fn kill_sidecar(app_handle: &tauri::AppHandle) {
    let state = app_handle.state::<Mutex<BackendState>>();
    let mut guard = match state.lock() {
        Ok(g) => g,
        Err(e) => {
            eprintln!("[sidecar] 获取锁失败: {}", e);
            return;
        }
    };

    if guard.is_sidecar {
        if let Some(child) = guard.child.take() {
            eprintln!("[sidecar] 正在终止后端进程 (port={})...", guard.port);
            match child.kill() {
                Ok(_) => eprintln!("[sidecar] 后端进程已终止"),
                Err(e) => {
                    eprintln!("[sidecar] kill 失败: {}", e);
                }
            }
        }
    }
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
    // 初始状态：dev 模式连 8000，release 模式动态分配端口
    let initial_port = if is_release_build() {
        find_available_port(SIDECAR_PORT, SIDECAR_PORT_RANGE)
    } else {
        DEV_PORT
    };

    debug_log(&format!(
        "[app] 启动模式: {} (后端端口: {})",
        if is_release_build() { "release/打包" } else { "dev/开发" },
        initial_port
    ));

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .manage(Mutex::new(BackendState {
            child: None,
            port: initial_port,
            is_sidecar: false,
        }))
        .setup(move |app| {
            let handle = app.handle().clone();

            if is_release_build() {
                // ============ 打包模式：启动 sidecar ============
                let data_dir = get_app_data_dir(app.handle());
                let actual_port = initial_port;

                // 确保数据目录存在
                let _ = std::fs::create_dir_all(&data_dir);

                debug_log(&format!(
                    "[sidecar] 启动后端 sidecar (port={}, data-dir={})",
                    actual_port, data_dir
                ));

                // 使用 Tauri shell plugin 的 sidecar API
                use tauri_plugin_shell::ShellExt;
                use tauri_plugin_shell::process::CommandEvent;
                use std::sync::Arc;
                use std::sync::atomic::{AtomicBool, Ordering};

                let sidecar_result = app.handle()
                    .shell()
                    .sidecar("zenflux-backend")
                    .map(|cmd| {
                        cmd.args([
                            "--port",
                            &actual_port.to_string(),
                            "--data-dir",
                            &data_dir,
                        ])
                    });

                match sidecar_result {
                    Ok(cmd) => {
                        match cmd.spawn() {
                            Ok((mut rx, child)) => {
                                debug_log("[sidecar] sidecar 进程已启动");

                                // 保存进程句柄
                                if let Ok(mut guard) = handle.state::<Mutex<BackendState>>().lock() {
                                    guard.child = Some(child);
                                    guard.is_sidecar = true;
                                }

                                // 共享标志：sidecar 是否已退出
                                let sidecar_exited = Arc::new(AtomicBool::new(false));
                                let sidecar_exited_for_log = sidecar_exited.clone();
                                let sidecar_exited_for_health = sidecar_exited.clone();

                                // 在后台线程读取 sidecar 输出
                                let log_handle = handle.clone();
                                tauri::async_runtime::spawn(async move {
                                    while let Some(event) = rx.recv().await {
                                        match event {
                                            CommandEvent::Stdout(line) => {
                                                let line = String::from_utf8_lossy(&line);
                                                let trimmed = line.trim();
                                                eprintln!("[sidecar:stdout] {}", trimmed);
                                                debug_log(&format!("[sidecar:stdout] {}", trimmed));
                                            }
                                            CommandEvent::Stderr(line) => {
                                                let line = String::from_utf8_lossy(&line);
                                                let trimmed = line.trim();
                                                eprintln!("[sidecar:stderr] {}", trimmed);
                                                debug_log(&format!("[sidecar:stderr] {}", trimmed));
                                            }
                                            CommandEvent::Terminated(status) => {
                                                debug_log(&format!("[sidecar] 进程已退出: {:?}", status));
                                                sidecar_exited_for_log.store(true, Ordering::SeqCst);
                                                // 立即通知前端：sidecar 意外退出
                                                let _ = log_handle.emit("backend-ready", false);
                                                let _ = log_handle.emit("backend-stopped", true);
                                                break;
                                            }
                                            _ => {}
                                        }
                                    }
                                });

                                // 在后台线程等待后端就绪
                                std::thread::spawn(move || {
                                    let start = Instant::now();
                                    let timeout = Duration::from_secs(BACKEND_STARTUP_TIMEOUT_SECS);
                                    let poll_interval = Duration::from_millis(BACKEND_HEALTH_POLL_MS);
                                    let url = health_url(actual_port);

                                    debug_log(&format!("[sidecar] 等待后端就绪 (port={})...", actual_port));

                                    // 向前端发送启动进度
                                    let _ = handle.emit("sidecar-status", "正在启动服务...");
                                    let mut poll_count: u32 = 0;

                                    loop {
                                        // 如果 sidecar 已经退出，立即失败
                                        if sidecar_exited_for_health.load(Ordering::SeqCst) {
                                            debug_log("[sidecar] sidecar 进程已退出，停止健康检查");
                                            let _ = handle.emit("sidecar-status", "服务启动失败");
                                            // backend-ready(false) 已由日志线程发出
                                            return;
                                        }

                                        if start.elapsed() > timeout {
                                            debug_log(&format!("[sidecar] 后端启动超时 ({}s)", BACKEND_STARTUP_TIMEOUT_SECS));
                                            let _ = handle.emit("sidecar-status", "启动超时，请重试");
                                            let _ = handle.emit("backend-ready", false);
                                            return;
                                        }

                                        // 根据等待时长更新进度提示
                                        poll_count += 1;
                                        if poll_count == 4 {
                                            let _ = handle.emit("sidecar-status", "正在加载模块...");
                                        } else if poll_count == 10 {
                                            let _ = handle.emit("sidecar-status", "正在初始化数据...");
                                        } else if poll_count == 20 {
                                            let _ = handle.emit("sidecar-status", "即将就绪...");
                                        }

                                        match ureq::get(&url)
                                            .timeout(Duration::from_secs(2))
                                            .call()
                                        {
                                            Ok(resp) if resp.status() == 200 => {
                                                let elapsed_ms = start.elapsed().as_millis();
                                                debug_log(&format!("[sidecar] 后端就绪 ({}ms)", elapsed_ms));
                                                let _ = handle.emit("sidecar-status", "准备就绪");
                                                let _ = handle.emit("backend-ready", true);
                                                return;
                                            }
                                            _ => {
                                                std::thread::sleep(poll_interval);
                                            }
                                        }
                                    }
                                });
                            }
                            Err(e) => {
                                debug_log(&format!("[sidecar] spawn 失败: {}", e));
                                let _ = handle.emit("backend-ready", false);
                            }
                        }
                    }
                    Err(e) => {
                        debug_log(&format!("[sidecar] sidecar 命令创建失败: {}", e));
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

            // ============ 系统托盘 ============
            let show_item = MenuItemBuilder::with_id("show", "显示窗口").build(app)?;
            let quit_item = MenuItemBuilder::with_id("quit", "退出").build(app)?;
            let tray_menu = MenuBuilder::new(app)
                .items(&[&show_item, &quit_item])
                .build()?;

            let _tray = TrayIconBuilder::new()
                .icon(tauri::include_image!("./icons/32x32.png"))
                .icon_as_template(true)
                .menu(&tray_menu)
                .tooltip("ZenFlux Agent")
                .on_menu_event(|app, event| match event.id().as_ref() {
                    "show" => {
                        if let Some(window) = app.get_webview_window("main") {
                            let _ = window.unminimize();
                            let _ = window.show();
                            let _ = window.set_focus();
                        }
                    }
                    "quit" => {
                        // 真正退出：先终止 sidecar，再退出应用
                        kill_sidecar(app);
                        app.exit(0);
                    }
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    // 左键单击托盘图标 → 显示窗口
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        let app = tray.app_handle();
                        if let Some(window) = app.get_webview_window("main") {
                            let _ = window.unminimize();
                            let _ = window.show();
                            let _ = window.set_focus();
                        }
                    }
                })
                .build(app)?;

            Ok(())
        })
        .on_window_event(|window, event| {
            match event {
                // 拦截窗口关闭请求 → 隐藏到托盘而非退出
                tauri::WindowEvent::CloseRequested { api, .. } => {
                    api.prevent_close();
                    let _ = window.hide();
                }
                // 窗口真正销毁时终止 sidecar（第一层防护）
                tauri::WindowEvent::Destroyed => {
                    kill_sidecar(window.app_handle());
                }
                _ => {}
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
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| {
            // 应用退出时终止 sidecar（第二层防护，最可靠）
            if let tauri::RunEvent::Exit = event {
                eprintln!("[app] 应用退出，执行清理...");
                kill_sidecar(app_handle);
            }
        });
}
