<script setup lang="ts">
import { onMounted, ref, reactive } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useNodeStore } from '@/stores/nodes'
import type { NodeSummary } from '@/api/nodes'

const store = useNodeStore()
onMounted(() => store.fetchAll())

const dialogVisible = ref(false)
const isEdit = ref(false)
const submitting = ref(false)

const emptyForm = (): NodeSummary => ({
  node_id: '',
  hostname: '',
  ip_address: '',
  agent_port: 9001,
})
const form = reactive<NodeSummary>(emptyForm())

function openCreate() {
  Object.assign(form, emptyForm())
  isEdit.value = false
  dialogVisible.value = true
}

function openEdit(node: NodeSummary) {
  // Only copy connection fields — never send live tomcat runtime state back to the backend
  Object.assign(form, {
    node_id: node.node_id,
    hostname: node.hostname,
    ip_address: node.ip_address,
    agent_port: node.agent_port,
  })
  isEdit.value = true
  dialogVisible.value = true
}

async function handleDelete(node: NodeSummary) {
  try {
    await ElMessageBox.confirm(`Delete node "${node.node_id}"?`, 'Confirm', { type: 'warning' })
  } catch {
    return // user cancelled
  }
  try {
    await store.remove(node.node_id)
    ElMessage.success('Node deleted')
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? 'Delete failed')
  }
}

async function handlePoll(id: string) {
  try {
    await store.poll(id)
    ElMessage.success('Node polled')
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? 'Poll failed')
  }
}

async function handleSubmit() {
  submitting.value = true
  try {
    if (isEdit.value) {
      await store.update(form.node_id, { ...form })
      ElMessage.success('Node updated')
    } else {
      await store.create({ ...form })
      ElMessage.success('Node created')
    }
    dialogVisible.value = false
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? 'Save failed')
  } finally {
    submitting.value = false
  }
}

function statusTagType(status: string) {
  if (status === 'running') return 'success'
  if (status === 'stopped') return 'info'
  return 'warning'
}

function agentTagType(status: string | undefined) {
  if (status === 'online') return 'success'
  if (status === 'offline') return 'danger'
  return 'info'
}

async function handleRowExpand(row: NodeSummary) {
  if (!store.nodeDetails[row.node_id]) {
    await store.poll(row.node_id)
  }
}
</script>

<template>
  <div>
    <div class="flex justify-between items-center mb-4">
      <span class="text-sm text-gray-500">{{ store.nodes.length }} node(s)</span>
      <el-button type="primary" @click="openCreate">
        <el-icon><Plus /></el-icon> New Node
      </el-button>
    </div>

    <el-card shadow="never">
      <el-table
        :data="store.nodes"
        stripe
        v-loading="store.loading"
        @expand-change="(row: NodeSummary) => handleRowExpand(row)"
      >
        <el-table-column type="expand">
          <template #default="{ row }">
            <div class="px-4 py-2">
              <div v-if="!store.nodeDetails[row.node_id]" class="text-sm text-gray-400 py-2">
                Loading instance details...
              </div>
              <el-table
                v-else
                :data="Object.values(store.nodeDetails[row.node_id].tomcats)"
                size="small"
                class="w-full"
              >
                <el-table-column prop="app_id" label="App ID" />
                <el-table-column label="Status" width="100">
                  <template #default="{ row: tc }">
                    <el-tag :type="statusTagType(tc.status)" size="small">{{ tc.status }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="pid" label="PID" width="80" />
                <el-table-column label="Health" width="100">
                  <template #default="{ row: tc }">
                    <el-tag :type="tc.health === 'healthy' ? 'success' : 'warning'" size="small">
                      {{ tc.health ?? 'unknown' }}
                    </el-tag>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="node_id" label="Node ID" width="140" />
        <el-table-column prop="hostname" label="Hostname" />
        <el-table-column prop="ip_address" label="IP Address" />
        <el-table-column prop="agent_port" label="Agent Port" width="110" />
        <el-table-column label="Agent" width="90">
          <template #default="{ row }">
            <el-tag :type="agentTagType(row.agent_status)" size="small">
              {{ row.agent_status ?? 'unknown' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="Instances" width="90">
          <template #default="{ row }">{{ row.tomcat_count ?? 0 }}</template>
        </el-table-column>
        <el-table-column label="Actions" width="200" align="right">
          <template #default="{ row }">
            <el-button size="small" @click="handlePoll(row.node_id)">Poll</el-button>
            <el-button size="small" @click="openEdit(row)">Edit</el-button>
            <el-button size="small" type="danger" @click="handleDelete(row)">Delete</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="isEdit ? 'Edit Node' : 'New Node'" width="460px">
      <el-form :model="form" label-width="120px">
        <el-form-item label="Node ID">
          <el-input v-model="form.node_id" :disabled="isEdit" placeholder="e.g. node-01" />
        </el-form-item>
        <el-form-item label="Hostname">
          <el-input v-model="form.hostname" placeholder="e.g. tomcat01.internal" />
        </el-form-item>
        <el-form-item label="IP Address">
          <el-input v-model="form.ip_address" placeholder="e.g. 10.0.1.10" />
        </el-form-item>
        <el-form-item label="Agent Port">
          <el-input-number v-model="form.agent_port" :min="1" :max="65535" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">Cancel</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">Save</el-button>
      </template>
    </el-dialog>
  </div>
</template>
