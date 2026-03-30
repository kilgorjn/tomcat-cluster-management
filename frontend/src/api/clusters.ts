import api from './client'

export interface ClusterPolicy {
  mode: 'AUTO' | 'MANUAL'
  min_instances: number
  max_instances: number
}

export interface Cluster {
  cluster_id: string
  app_id: string
  nodes: string[]
  policy: ClusterPolicy
}

export interface ClusterStatus {
  cluster_id: string
  running: number
  stopped: number
  unhealthy: number
  policy_mode: string
}

export const getClusters = () => api.get<{ clusters: Cluster[] }>('/clusters')
export const getCluster = (id: string) => api.get<Cluster>(`/clusters/${id}`)
export const createCluster = (data: Cluster) => api.post<Cluster>('/clusters', data)
export const updateCluster = (id: string, data: Cluster) => api.put<Cluster>(`/clusters/${id}`, data)
export const deleteCluster = (id: string) => api.delete(`/clusters/${id}`)
export const getClusterStatus = (id: string) => api.get<ClusterStatus>(`/clusters/${id}/status`)
export const updatePolicy = (id: string, data: { mode: string; min_instances?: number; max_instances?: number }) =>
  api.post(`/clusters/${id}/policy`, data)
export const stopAll = (id: string) => api.post(`/clusters/${id}/stop-all`)
export const startAll = (id: string) => api.post(`/clusters/${id}/start-all`)
