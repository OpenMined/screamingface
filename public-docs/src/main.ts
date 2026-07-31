import { createApp } from 'vue'
import { createPinia } from 'pinia'

import './style.css'
// Must follow style.css — these tokens resolve against the theme it defines.
import './components/nb/tokens.css'
import App from './App.vue'
import router from './router'

const app = createApp(App)

app.use(createPinia())
app.use(router)

app.mount('#app')
