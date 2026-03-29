import api from './client'

export interface TomcatInstance {
  app_id: string
  instance_port: number
  ajp_port: number
  status: string
  pid?: number | null
  health_status?: string
}

export interface Node {
  node_id: string
  hostname: string
  ip_address: string
  agent_port: number
  agent_status?: string
  last_heartbeat?: string | null
  tomcats: Record<string, TomcatInstance>
}

export const getNodes = () => api.get<{ nodes: Node[] }>('/nodes')
export const getNode = (id: string) => api.get<Node>(`/nodes/${id}`)
export const createNode = (data: Node) => api.post<Node>('/nodes', data)
export const updateNode = (id: string, data: Node) => api.put<Node>(`/nodes/${id}`, data)
export const deleteNode = (id: string) => api.delete(`/nodes/${id}`)
export const pollNode = (id: string) => api.post(`/nodes/${id}/poll`)
