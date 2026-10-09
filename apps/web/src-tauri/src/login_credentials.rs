use keyring::{Entry, Error};
use serde::{Deserialize, Serialize};

#[derive(Serialize, Deserialize)]
pub struct SavedLogin {
    email: String,
    password: String,
}

fn entry(server: &str) -> Result<Entry, String> {
    if server.is_empty() || server.len() > 1024 {
        return Err("Invalid server address".into());
    }
    Entry::new("com.agentharbor.desktop.login", server)
        .map_err(|_| "Unable to access Windows credential storage".into())
}

#[tauri::command]
pub fn load_saved_login(server: String) -> Result<Option<SavedLogin>, String> {
    match entry(&server)?.get_password() {
        Ok(value) => serde_json::from_str(&value)
            .map(Some)
            .map_err(|_| "Unable to read saved login".into()),
        Err(Error::NoEntry) => Ok(None),
        Err(_) => Err("Unable to read Windows credential storage".into()),
    }
}

#[tauri::command]
pub fn save_login(server: String, email: String, password: String) -> Result<(), String> {
    if email.is_empty() || email.chars().count() > 254 || password.is_empty() || password.chars().count() > 128 {
        return Err("Invalid login credentials".into());
    }
    let value = serde_json::to_string(&SavedLogin { email, password })
        .map_err(|_| "Unable to prepare saved login".to_string())?;
    entry(&server)?.set_password(&value)
        .map_err(|_| "Unable to save login in Windows credential storage".into())
}

#[tauri::command]
pub fn clear_saved_login(server: String) -> Result<(), String> {
    match entry(&server)?.delete_credential() {
        Ok(()) | Err(Error::NoEntry) => Ok(()),
        Err(_) => Err("Unable to remove saved login from Windows credential storage".into()),
    }
}
