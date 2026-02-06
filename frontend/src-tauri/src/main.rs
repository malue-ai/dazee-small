// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::process::Command as SysCommand;
use std::time::Instant;

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

// ============================================================================
// Tauri 命令
// ============================================================================

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
    let result = run_command(vec!["which".to_string(), executable], None, None, Some(5000)).await?;
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
            "camera" => "x-apple.systempreferences:com.apple.preference.security?Privacy_Camera",
            "screen" => "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture",
            "location" => "x-apple.systempreferences:com.apple.preference.security?Privacy_LocationServices",
            "accessibility" => "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
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
        .invoke_handler(tauri::generate_handler![
            run_command,
            which_command,
            get_node_info,
            open_system_preferences,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
