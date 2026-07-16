use tauri::{AppHandle, Manager, Theme};

#[cfg(target_os = "macos")]
use {
  crate::windows::{MACOS_TRAFFIC_LIGHTS_INSET_X, MACOS_TRAFFIC_LIGHTS_INSET_Y},
  tauri_plugin_decorum::WebviewWindowExt,
};

#[tauri::command]
pub fn update_theme(app: AppHandle, is_dark: bool) {
  for (_, window) in app.webview_windows() {
    if let Err(error) = window.set_theme(Some(if is_dark { Theme::Dark } else { Theme::Light })) {
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
