import { defineStore } from 'pinia'
import { ref } from 'vue'
import * as api from '@/api/applications'
import type { Application } from '@/api/applications'

export const useApplicationStore = defineStore('applications', () => {
  const applications = ref<Application[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchAll() {
    loading.value = true
    error.value = null
    try {
      const res = await api.getApplications()
      applications.value = res.data
    } catch (e: any) {
      error.value = e.response?.data?.detail ?? 'Failed to load applications'
    } finally {
      loading.value = false
    }
  }

  async function create(data: Application) {
    const res = await api.createApplication(data)
    applications.value.push(res.data)
  }

  async function update(id: string, data: Application) {
    const res = await api.updateApplication(id, data)
    const idx = applications.value.findIndex((a) => a.app_id === id)
    if (idx !== -1) applications.value[idx] = res.data
  }

  async function remove(id: string) {
    await api.deleteApplication(id)
    applications.value = applications.value.filter((a) => a.app_id !== id)
  }

  return { applications, loading, error, fetchAll, create, update, remove }
})
