<script setup lang="ts">
import { onMounted, ref, reactive } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useClusterStore } from '@/stores/clusters'
import { useApplicationStore } from '@/stores/applications'
import { useNodeStore } from '@/stores/nodes'
import type { Cluster } from '@/api/clusters'

const clusterStore = useClusterStore()
const appStore = useApplicationStore()
const nodeStore = useNodeStore()

onMounted(async () => {
  await Promise.all([clusterStore.fetchAll(), appStore.fetchAll(), nodeStore.fetchAll()])
  await clusterStore.fetchAllStatuses()
})

// Cluster CRUD dialog
const dialogVisible = ref(false)
const isEdit = ref(false)
const submitting = ref(false)

const emptyForm = (): Cluster => ({
  cluster_id: '',
  app_id: '',
  nodes: [],
  policy: { mode: 'MANUAL', min_instances: 1, max_instances: 4 },
})
const form = reactive<Cluster>(emptyForm())

function openCreate() {
  Object.assign(form, emptyForm())
  isEdit.value = false
  dialogVisible.value = true
}

function openEdit(c: Cluster) {
  Object.assign(form, JSON.parse(JSON.stringify(c)))
  isEdit.value = true
  dialogVisible.value = true
}

async function handleDelete(c: Cluster) {
  await ElMessageBox.confirm(`Delete cluster "${c.cluster_id}"?`, 'Confirm', { type: 'warning' })
  try {
    await clusterStore.remove(c.cluster_id)
    ElMessage.success('Cluster deleted')
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? 'Delete failed')
  }
}

async function handleSubmit() {
  submitting.value = true
  try {
    if (isEdit.value) {
      await clusterStore.update(form.cluster_id, JSON.parse(JSON.stringify(form)))
      ElMessage.success('Cluster updated')
    } else {
      await clusterStore.create(JSON.parse(JSON.stringify(form)))
      ElMessage.success('Cluster created')
    }
    await clusterStore.fetchAllStatuses()
    dialogVisible.value = false
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? 'Save failed')
  } finally {
    submitting.value = false
  }
}

// Cluster actions
async function handleStop(id: string) {
  try {
    const res = await clusterStore.stopAll(id)
    ElMessage.success(`Stopped ${res.data.stopped} instance(s)`)
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? 'Stop failed')
  }
}

async function handleStart(id: string) {
  try {
    const res = await clusterStore.startAll(id)
    ElMessage.success(`Started ${res.data.started} instance(s)`)
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? 'Start failed')
  }
}
</script>

<template>
  <div>
    <div class="flex justify-between items-center mb-4">
      <span class="text-sm text-gray-500">{{ clusterStore.clusters.length }} cluster(s)</span>
      <el-button type="primary" @click="openCreate">
        <el-icon><Plus /></el-icon> New Cluster
      </el-button>
    </div>

    <el-card shadow="never">
      <el-table :data="clusterStore.clusters" stripe v-loading="clusterStore.loading">
        <el-table-column prop="cluster_id" label="Cluster ID" width="160" />
        <el-table-column prop="app_id" label="Application" />
        <el-table-column label="Policy" width="100">
          <template #default="{ row }">
            <el-tag :type="row.policy.mode === 'AUTO' ? 'success' : 'info'" size="small">
              {{ row.policy.mode }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="Min/Max" width="90">
          <template #default="{ row }">
            {{ row.policy.min_instances }}/{{ row.policy.max_instances }}
          </template>
        </el-table-column>
        <el-table-column label="Running" width="90">
          <template #default="{ row }">
            {{ clusterStore.statuses[row.cluster_id]?.running ?? '—' }}
          </template>
        </el-table-column>
        <el-table-column label="Nodes" width="80">
          <template #default="{ row }">{{ row.nodes.length }}</template>
        </el-table-column>
        <el-table-column label="Actions" width="260" align="right">
          <template #default="{ row }">
            <el-button size="small" type="success" @click="handleStart(row.cluster_id)">Start</el-button>
            <el-button size="small" type="warning" @click="handleStop(row.cluster_id)">Stop</el-button>
            <el-button size="small" @click="openEdit(row)">Edit</el-button>
            <el-button size="small" type="danger" @click="handleDelete(row)">Delete</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="isEdit ? 'Edit Cluster' : 'New Cluster'" width="520px">
      <el-form :model="form" label-width="130px">
        <el-form-item label="Cluster ID">
          <el-input v-model="form.cluster_id" :disabled="isEdit" placeholder="e.g. prod-bmw" />
        </el-form-item>
        <el-form-item label="Application">
          <el-select v-model="form.app_id" placeholder="Select application" class="w-full">
            <el-option
              v-for="app in appStore.applications"
              :key="app.app_id"
              :label="app.name"
              :value="app.app_id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="Nodes">
          <el-select v-model="form.nodes" multiple placeholder="Select nodes" class="w-full">
            <el-option
              v-for="node in nodeStore.nodes"
              :key="node.node_id"
              :label="`${node.node_id} (${node.hostname})`"
              :value="node.node_id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="Policy Mode">
          <el-radio-group v-model="form.policy.mode">
            <el-radio value="MANUAL">Manual</el-radio>
            <el-radio value="AUTO">Auto</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="Min Instances">
          <el-input-number v-model="form.policy.min_instances" :min="0" :max="form.policy.max_instances" />
        </el-form-item>
        <el-form-item label="Max Instances">
          <el-input-number v-model="form.policy.max_instances" :min="form.policy.min_instances" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">Cancel</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">Save</el-button>
      </template>
    </el-dialog>
  </div>
</template>
