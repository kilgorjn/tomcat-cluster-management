import api from './client'

export interface TomcatInstance {
  app_id: string
  instance_port: number
  ajp_port: number
  status: string
  pid?: number | null
  health?: string
}

// Summary returned by GET /nodes (no tomcats detail)
export interface NodeSummary {
  node_id: string
  hostname: string
  ip_address: string
  agent_port: number
  agent_status?: string
  tomcat_count?: number
}

// Full node detail returned by GET /nodes/{id}/status
export interface Node extends NodeSummary {
  last_heartbeat?: string | null
  tomcats: Record<string, TomcatInstance>
}

export const getNodes = () => api.get<{ nodes: NodeSummary[] }>('/nodes')
export const getNodeStatus = (id: string) => api.get<Node>(`/nodes/${id}/status`)
export const createNode = (data: NodeSummary) => api.post<NodeSummary>('/nodes', data)
export const updateNode = (id: string, data: NodeSummary) => api.put<NodeSummary>(`/nodes/${id}`, data)
export const deleteNode = (id: string) => api.delete(`/nodes/${id}`)
export const pollNode = (id: string) => api.get<Node>(`/nodes/${id}/status`)
