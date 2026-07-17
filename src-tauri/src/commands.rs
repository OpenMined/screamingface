use tauri::{AppHandle, Manager, Theme};

#[cfg(target_os = "macos")]
use {
  crate::windows::{MACOS_TRAFFIC_LIGHTS_INSET_X, MACOS_TRAFFIC_LIGHTS_INSET_Y},
  tauri_plugin_decorum::WebviewWindowExt,
};

#[tauri::command]
pub fn update_theme(app: AppHandle, theme: Option<String>) {
  let native_theme = match theme.as_deref() {
    None => None,
    Some("dark") => Some(Theme::Dark),
    Some("light") => Some(Theme::Light),
    Some(theme) => {
      log::error!("Ignoring unsupported native window theme: {theme}");
      return;
    }
  };

  for (_, window) in app.webview_windows() {
    if let Err(error) = window.set_theme(native_theme) {
      log::error!("Failed to update native window theme: {error}");
    }
  }

  #[cfg(target_os = "macos")]
  if let Some(window) = app.get_webview_window("main") {
    let _ = window.set_traffic_lights_inset(
      MACOS_TRAFFIC_LIGHTS_INSET_X,
      MACOS_TRAFFIC_LIGHTS_INSET_Y,
    );
  }
}
