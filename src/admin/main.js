import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import '../style.css'
import AdminApp from './AdminApp.vue'

createApp(AdminApp).use(ElementPlus).mount('#app')
