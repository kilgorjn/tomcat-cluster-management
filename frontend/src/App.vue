<script setup lang="ts">
import { useRoute } from 'vue-router'
const route = useRoute()
</script>

<template>
  <el-container class="min-h-screen">
    <el-aside width="220px" class="bg-gray-900 text-white">
      <div class="px-6 py-5 border-b border-gray-700">
        <div class="text-lg font-semibold tracking-wide text-white">TCM Console</div>
        <div class="text-xs text-gray-400 mt-0.5">Tomcat Cluster Manager</div>
      </div>
      <el-menu
        :default-active="route.path"
        router
        background-color="#111827"
        text-color="#d1d5db"
        active-text-color="#ffffff"
        class="border-none mt-2"
      >
        <el-menu-item index="/dashboard">
          <el-icon><Monitor /></el-icon>
          <span>Dashboard</span>
        </el-menu-item>
        <el-menu-item index="/applications">
          <el-icon><Files /></el-icon>
          <span>Applications</span>
        </el-menu-item>
        <el-menu-item index="/clusters">
          <el-icon><Connection /></el-icon>
          <span>Clusters</span>
        </el-menu-item>
        <el-menu-item index="/nodes">
          <el-icon><Cpu /></el-icon>
          <span>Nodes</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="bg-white border-b border-gray-200 flex items-center px-6" height="56px">
        <h1 class="text-base font-semibold text-gray-700 m-0">{{ route.meta.title }}</h1>
      </el-header>
      <el-main class="bg-gray-50 p-6">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>
