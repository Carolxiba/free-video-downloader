<script setup lang="ts">
import App from './App.vue'
import AuthGate from './components/AuthGate.vue'
</script>

<template>
  <AuthGate v-slot="{ user, logout }">
    <App :user="user" @logout="logout" />
  </AuthGate>
</template>
