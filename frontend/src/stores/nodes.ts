import { defineStore } from 'pinia'
import { ref } from 'vue'
import * as api from '@/api/nodes'
import type { Node } from '@/api/nodes'

export const useNodeStore = defineStore('nodes', () => {
  const nodes = ref<Node[]>([])
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

  async function create(data: Node) {
    const res = await api.createNode(data)
    nodes.value.push(res.data)
  }

  async function update(id: string, data: Node) {
    const res = await api.updateNode(id, data)
    const idx = nodes.value.findIndex((n) => n.node_id === id)
    if (idx !== -1) nodes.value[idx] = res.data
  }

  async function remove(id: string) {
    await api.deleteNode(id)
    nodes.value = nodes.value.filter((n) => n.node_id !== id)
  }

  async function poll(id: string) {
    await api.pollNode(id)
    await fetchAll()
  }

  return { nodes, loading, error, fetchAll, create, update, remove, poll }
})
