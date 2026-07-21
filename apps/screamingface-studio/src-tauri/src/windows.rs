use crate::state::{PendingUpdate, UpdateWindowState, UpdateWindowType};
use tauri::{webview::WebviewWindowBuilder, AppHandle, Emitter, Manager, WebviewUrl};
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

pub fn show_update_window(
  app: &AppHandle,
  update_window_type: UpdateWindowType,
  version: String,
  current_version: String,
  release_notes: String,
  error: String,
  progress: usize,
) {
  let state = UpdateWindowState {
    update_window_type,
    version,
    current_version,
    release_notes,
    error,
    progress,
  };

  *app.state::<PendingUpdate>().window_state.lock().unwrap() = Some(state.clone());

  if let Some(window) = app.get_webview_window("updates") {
    let _ = window.show();
    let _ = window.set_focus();
    let _ = app.emit_to("updates", "update-window-state", state);
    return;
  }

  match WebviewWindowBuilder::new(app, "updates", WebviewUrl::App("updates/".into()))
    .title("ScreamingFace Updates")
    .inner_size(760.0, 520.0)
    .min_inner_size(640.0, 440.0)
    .focused(true)
    .resizable(false)
    .decorations(false)
    .build()
  {
    Ok(_) => {
      let _ = app.emit_to("updates", "update-window-state", state);
    }
    Err(error) => log::error!("Failed to create update window: {error}"),
  }
}
