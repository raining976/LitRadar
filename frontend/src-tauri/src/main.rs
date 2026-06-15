// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::process::{Child, Command};
use std::thread;
use std::time::Duration;

fn spawn_backend() -> Option<Child> {
    if cfg!(debug_assertions) {
        return None;
    }

    let exe_dir = std::env::current_exe()
        .ok()?
        .parent()?
        .to_path_buf();
    let backend_path = exe_dir.join("litradar-backend");

    if !backend_path.exists() {
        eprintln!("Backend binary not found: {:?}", backend_path);
        return None;
    }

    println!("Starting backend: {:?}", backend_path);
    match Command::new(&backend_path).spawn() {
        Ok(child) => {
            println!("LitRadar backend started (PID {})", child.id());
            Some(child)
        }
        Err(e) => {
            eprintln!("Failed to start backend: {}", e);
            None
        }
    }
}

fn main() {
    // Spawn backend in background, don't block — frontend will retry
    let _child = spawn_backend();

    // Give backend a brief head start but don't wait
    thread::sleep(Duration::from_millis(500));

    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .run(tauri::generate_context!())
        .expect("failed to run LitRadar desktop app");
}
