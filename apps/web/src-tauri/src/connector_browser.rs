use tauri_plugin_opener::OpenerExt;

fn authorization_url(value: &str) -> Result<tauri::Url, String> {
    let url = tauri::Url::parse(value).map_err(|_| "Invalid authorization URL")?;
    let loopback = matches!(url.host_str(), Some("localhost" | "127.0.0.1" | "[::1]"));
    if !(url.scheme() == "https" || (url.scheme() == "http" && loopback))
        || !url.username().is_empty()
        || url.password().is_some()
        || url.path() != "/harbor/connectors/oauth/browser"
        || url.query().is_some()
        || !url.fragment().is_some_and(|ticket| {
            ticket.len() == 43
                && ticket
                    .bytes()
                    .all(|c| c.is_ascii_alphanumeric() || c == b'_' || c == b'-')
        })
    {
        return Err("Invalid connector browser URL".into());
    }
    Ok(url)
}

#[tauri::command]
pub fn open_connector_browser(
    app: tauri::AppHandle,
    window: tauri::WebviewWindow,
    url: String,
) -> Result<(), String> {
    if window.label() != "main" {
        return Err("Only the main window can start connector authorization".into());
    }
    let validated = authorization_url(&url)?;
    app.opener()
        .open_url(validated.as_str(), None::<&str>)
        .map_err(|_| "Unable to open the default browser".into())
}

#[cfg(test)]
mod tests {
    use super::authorization_url;

    #[test]
    fn only_accepts_browser_handoff_urls() {
        let ticket = "a".repeat(43);
        for origin in [
            "https://harbor.example",
            "http://127.0.0.1:8017",
            "http://localhost:8017",
            "http://[::1]:8017",
        ] {
            assert!(authorization_url(&format!(
                "{origin}/harbor/connectors/oauth/browser#{ticket}"
            ))
            .is_ok());
        }
        for value in [
            "file:///tmp/a",
            "javascript:alert(1)",
            "https://harbor.example/",
            "http://remote.example/harbor/connectors/oauth/browser",
            "https://user:pass@harbor.example/harbor/connectors/oauth/browser",
        ] {
            assert!(authorization_url(&format!("{value}#{ticket}")).is_err());
        }
        assert!(
            authorization_url("https://harbor.example/harbor/connectors/oauth/browser#short")
                .is_err()
        );
    }
}
