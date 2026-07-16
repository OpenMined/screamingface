mod commands;
mod windows;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
  let builder = tauri::Builder::default();

  #[cfg(not(target_os = "macos"))]
  let builder = builder.plugin(tauri_plugin_decorum::init());

  builder
    .invoke_handler(tauri::generate_handler![commands::update_theme])
    .setup(|app| {
      if cfg!(debug_assertions) {
        app.handle().plugin(
          tauri_plugin_log::Builder::default()
            .level(log::LevelFilter::Info)
            .build(),
        )?;
      }
      windows::setup_main_window(app.handle())?;
      Ok(())
    })
    .run(tauri::generate_context!())
    .expect("error while running tauri application");
}
