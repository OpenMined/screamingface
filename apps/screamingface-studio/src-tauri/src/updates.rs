use crate::state::{AppState, PendingUpdate, UpdateWindowType};
use crate::windows::show_update_window;
use std::{sync::Mutex, time::Duration};
use tauri::{AppHandle, Manager};
use tauri_plugin_updater::UpdaterExt;

pub fn start_periodic_update_checks(app: &AppHandle) {
  let app = app.clone();
  tauri::async_runtime::spawn(async move {
    check_for_updates(&app, false).await;
    loop {
      tokio::time::sleep(Duration::from_secs(60 * 60)).await;
      check_for_updates(&app, false).await;
    }
  });
}

pub async fn check_for_updates(app: &AppHandle, manually_requested: bool) {
  let current_version = app.package_info().version.to_string();

  if manually_requested {
    show_update_window(
      app,
      UpdateWindowType::Checking,
      String::new(),
      current_version.clone(),
      String::new(),
      String::new(),
      0,
    );
  }

  let result = match app.updater() {
    Ok(updater) => updater.check().await,
    Err(error) => Err(error),
  };

  match result {
    Ok(Some(update)) => {
      let should_show = {
        let state = app.state::<Mutex<AppState>>();
        let state = state.lock().unwrap();
        manually_requested || state.dismissed_update_version != update.version
      };

      if !should_show {
        return;
      }

      show_update_window(
        app,
        UpdateWindowType::Available,
        update.version.clone(),
        update.current_version.clone(),
        update
          .body
          .clone()
          .unwrap_or_else(|| "No release notes were provided for this update.".to_string()),
        String::new(),
        0,
      );
      *app.state::<PendingUpdate>().update.lock().unwrap() = Some(update);
    }
    Ok(None) if manually_requested => show_update_window(
      app,
      UpdateWindowType::None,
      String::new(),
      current_version,
      String::new(),
      String::new(),
      0,
    ),
    Ok(None) => {}
    Err(error) if manually_requested => show_update_window(
      app,
      UpdateWindowType::Error,
      String::new(),
      current_version,
      String::new(),
      format!("Could not check for updates.\n\n{error}"),
      0,
    ),
    Err(error) => log::warn!("Automatic update check failed: {error}"),
  }
}
