<script setup lang="ts">
import { onMounted } from 'vue'
import { useClusterStore } from '@/stores/clusters'
import { useNodeStore } from '@/stores/nodes'
import { useApplicationStore } from '@/stores/applications'

const clusterStore = useClusterStore()
const nodeStore = useNodeStore()
const appStore = useApplicationStore()

onMounted(async () => {
  await Promise.all([clusterStore.fetchAll(), nodeStore.fetchAll(), appStore.fetchAll()])
  await clusterStore.fetchAllStatuses()
})

function statusType(status: string) {
  if (status === 'online') return 'success'
  if (status === 'offline') return 'danger'
  return 'info'
}
</script>

<template>
  <div>
    <div class="grid grid-cols-3 gap-4 mb-6">
      <el-card shadow="never">
        <div class="flex items-center gap-3">
          <el-icon size="32" color="#409eff"><Connection /></el-icon>
          <div>
            <div class="text-2xl font-bold text-gray-800">{{ clusterStore.clusters.length }}</div>
            <div class="text-sm text-gray-500">Clusters</div>
          </div>
        </div>
      </el-card>
      <el-card shadow="never">
        <div class="flex items-center gap-3">
          <el-icon size="32" color="#67c23a"><Cpu /></el-icon>
          <div>
            <div class="text-2xl font-bold text-gray-800">{{ nodeStore.nodes.length }}</div>
            <div class="text-sm text-gray-500">Nodes</div>
          </div>
        </div>
      </el-card>
      <el-card shadow="never">
        <div class="flex items-center gap-3">
          <el-icon size="32" color="#e6a23c"><Files /></el-icon>
          <div>
            <div class="text-2xl font-bold text-gray-800">{{ appStore.applications.length }}</div>
            <div class="text-sm text-gray-500">Applications</div>
          </div>
        </div>
      </el-card>
    </div>

    <el-card shadow="never" header="Cluster Health">
      <el-table :data="clusterStore.clusters" stripe>
        <el-table-column prop="cluster_id" label="Cluster" />
        <el-table-column prop="app_id" label="Application" />
        <el-table-column prop="policy.mode" label="Mode">
          <template #default="{ row }">
            <el-tag :type="row.policy.mode === 'AUTO' ? 'success' : 'info'" size="small">
              {{ row.policy.mode }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="Running">
          <template #default="{ row }">
            {{ clusterStore.statuses[row.cluster_id]?.running ?? '—' }}
          </template>
        </el-table-column>
        <el-table-column label="Stopped">
          <template #default="{ row }">
            {{ clusterStore.statuses[row.cluster_id]?.stopped ?? '—' }}
          </template>
        </el-table-column>
        <el-table-column label="Unhealthy">
          <template #default="{ row }">
            <span :class="(clusterStore.statuses[row.cluster_id]?.unhealthy ?? 0) > 0 ? 'text-red-500 font-semibold' : ''">
              {{ clusterStore.statuses[row.cluster_id]?.unhealthy ?? '—' }}
            </span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" header="Node Status" class="mt-4">
      <el-table :data="nodeStore.nodes" stripe>
        <el-table-column prop="node_id" label="Node" />
        <el-table-column prop="hostname" label="Hostname" />
        <el-table-column prop="ip_address" label="IP Address" />
        <el-table-column prop="agent_status" label="Agent">
          <template #default="{ row }">
            <el-tag :type="statusType(row.agent_status ?? 'unknown')" size="small">
              {{ row.agent_status ?? 'unknown' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="Instances">
          <template #default="{ row }">
            {{ Object.keys(row.tomcats).length }}
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>
