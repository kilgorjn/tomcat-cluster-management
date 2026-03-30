import { defineStore } from 'pinia'
import { ref } from 'vue'
import * as api from '@/api/nodes'
import type { NodeSummary, Node } from '@/api/nodes'

export const useNodeStore = defineStore('nodes', () => {
  const nodes = ref<NodeSummary[]>([])
  // Cache of full node detail keyed by node_id, populated on poll/expand
  const nodeDetails = ref<Record<string, Node>>({})
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetchAll() {
    loading.value = true
    error.value = null
    try {
      const res = await api.getNodes()
      nodes.value = res.data.nodes
    } catch (e: any) {
      error.value = e.response?.data?.detail ?? 'Failed to load nodes'
    } finally {
      loading.value = false
    }
  }

  async function create(data: NodeSummary) {
    await api.createNode(data)
    await fetchAll()
  }

  async function update(id: string, data: NodeSummary) {
    await api.updateNode(id, data)
    await fetchAll()
  }

  async function remove(id: string) {
    await api.deleteNode(id)
    nodes.value = nodes.value.filter((n) => n.node_id !== id)
    delete nodeDetails.value[id]
  }

  async function poll(id: string) {
    const res = await api.pollNode(id)
    nodeDetails.value[id] = res.data
    // Sync summary agent_status from the polled detail
    const idx = nodes.value.findIndex((n) => n.node_id === id)
    if (idx !== -1) {
      nodes.value[idx] = { ...nodes.value[idx], agent_status: res.data.agent_status }
    }
  }

  return { nodes, nodeDetails, loading, error, fetchAll, create, update, remove, poll }
})
