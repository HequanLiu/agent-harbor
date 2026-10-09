#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod login_credentials;

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_http::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .invoke_handler(tauri::generate_handler![
            login_credentials::load_saved_login,
            login_credentials::save_login,
            login_credentials::clear_saved_login,
        ])
        .run(tauri::generate_context!())
        .expect("Unable to start AgentHarbor");
}
