use tauri::{webview::WebviewWindowBuilder, AppHandle, WebviewUrl};
use tauri_plugin_decorum::WebviewWindowExt;

#[cfg(target_os = "macos")]
use tauri::{TitleBarStyle, WindowEvent};

#[cfg(target_os = "macos")]
pub const MACOS_TRAFFIC_LIGHTS_INSET_X: f32 = 16.0;

#[cfg(target_os = "macos")]
pub const MACOS_TRAFFIC_LIGHTS_INSET_Y: f32 = 22.0;

pub fn setup_main_window(app: &AppHandle) -> tauri::Result<()> {
  let builder = WebviewWindowBuilder::new(app, "main", WebviewUrl::App("index.html".into()))
    .title("")
    .focused(true)
    .resizable(true)
    .min_inner_size(800.0, 600.0)
    .inner_size(1200.0, 720.0);

  #[cfg(target_os = "macos")]
  let builder = builder
    .title_bar_style(TitleBarStyle::Overlay)
    .hidden_title(true);

  let window = builder.build()?;
  window.create_overlay_titlebar().map_err(|error| tauri::Error::Anyhow(error.into()))?;

  #[cfg(target_os = "macos")]
  {
    let event_window = window.clone();
    let startup_window = window.clone();

    window
      .set_traffic_lights_inset(MACOS_TRAFFIC_LIGHTS_INSET_X, MACOS_TRAFFIC_LIGHTS_INSET_Y)
      .map_err(|error| tauri::Error::Anyhow(error.into()))?;

    window.on_window_event(move |event| {
      if matches!(event, WindowEvent::Resized(_) | WindowEvent::ThemeChanged(_) | WindowEvent::Focused(_)) {
        let _ = event_window.set_traffic_lights_inset(
          MACOS_TRAFFIC_LIGHTS_INSET_X,
          MACOS_TRAFFIC_LIGHTS_INSET_Y,
        );
      }
    });

    tauri::async_runtime::spawn(async move {
      for _ in 0..15 {
        let _ = startup_window.set_traffic_lights_inset(
          MACOS_TRAFFIC_LIGHTS_INSET_X,
          MACOS_TRAFFIC_LIGHTS_INSET_Y,
        );
        std::thread::sleep(std::time::Duration::from_secs(1));
      }
    });
  }

  Ok(())
}
