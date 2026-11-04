import { createApp } from 'vue';
import App from './App.vue';
import TeacherDashboard from './components/TeacherDashboard.vue';
import './style.css';
createApp(new URLSearchParams(location.search).get('view') === 'teacher' ? TeacherDashboard : App).mount('#app');
