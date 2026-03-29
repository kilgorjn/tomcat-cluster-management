import api from './client'

export interface Application {
  app_id: string
  name: string
  war_filename: string
  context_path: string
}

export const getApplications = () => api.get<Application[]>('/applications')
export const createApplication = (data: Application) => api.post<Application>('/applications', data)
export const updateApplication = (id: string, data: Application) => api.put<Application>(`/applications/${id}`, data)
export const deleteApplication = (id: string) => api.delete(`/applications/${id}`)
