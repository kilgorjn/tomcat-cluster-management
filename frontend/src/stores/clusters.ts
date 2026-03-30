import { defineStore } from 'pinia'
import { ref } from 'vue'
import * as api from '@/api/clusters'
import type { Cluster, ClusterStatus } from '@/api/clusters'

export const useClusterStore = defineStore('clusters', () => {
  const clusters = ref<Cluster[]>([])
  const statuses = ref<Record<string, ClusterStatus>>({})
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchAll() {
    loading.value = true
    error.value = null
    try {
      const res = await api.getClusters()
      clusters.value = res.data.clusters
    } catch (e: any) {
      error.value = e.response?.data?.detail ?? 'Failed to load clusters'
    } finally {
      loading.value = false
    }
  }

  async function fetchStatus(id: string) {
    try {
      const res = await api.getClusterStatus(id)
      statuses.value[id] = res.data
    } catch {
      // status fetch is best-effort
    }
  }

  async function fetchAllStatuses() {
    await Promise.all(clusters.value.map((c) => fetchStatus(c.cluster_id)))
  }

  async function create(data: Cluster) {
    const res = await api.createCluster(data)
    clusters.value.push(res.data)
  }

  async function update(id: string, data: Cluster) {
    const res = await api.updateCluster(id, data)
    const idx = clusters.value.findIndex((c) => c.cluster_id === id)
    if (idx !== -1) clusters.value[idx] = res.data
  }

  async function remove(id: string) {
    await api.deleteCluster(id)
    clusters.value = clusters.value.filter((c) => c.cluster_id !== id)
  }

  async function updatePolicy(id: string, data: { mode: string; min_instances?: number; max_instances?: number }) {
    await api.updatePolicy(id, data)
    await fetchAll()
  }

  async function stopAll(id: string) {
    return api.stopAll(id)
  }

  async function startAll(id: string) {
    return api.startAll(id)
  }

  return { clusters, statuses, loading, error, fetchAll, fetchStatus, fetchAllStatuses, create, update, remove, updatePolicy, stopAll, startAll }
})
