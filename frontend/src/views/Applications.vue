<script setup lang="ts">
import { onMounted, ref, reactive } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useApplicationStore } from '@/stores/applications'
import type { Application } from '@/api/applications'

const store = useApplicationStore()
onMounted(() => store.fetchAll())

const dialogVisible = ref(false)
const isEdit = ref(false)
const submitting = ref(false)

const emptyForm = (): Application => ({ app_id: '', name: '', war_filename: '', context_path: '' })
const form = reactive<Application>(emptyForm())

function openCreate() {
  Object.assign(form, emptyForm())
  isEdit.value = false
  dialogVisible.value = true
}

function openEdit(app: Application) {
  Object.assign(form, { ...app })
  isEdit.value = true
  dialogVisible.value = true
}

async function handleDelete(app: Application) {
  await ElMessageBox.confirm(`Delete application "${app.app_id}"?`, 'Confirm', { type: 'warning' })
  try {
    await store.remove(app.app_id)
    ElMessage.success('Application deleted')
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? 'Delete failed')
  }
}

async function handleSubmit() {
  submitting.value = true
  try {
    if (isEdit.value) {
      await store.update(form.app_id, { ...form })
      ElMessage.success('Application updated')
    } else {
      await store.create({ ...form })
      ElMessage.success('Application created')
    }
    dialogVisible.value = false
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail ?? 'Save failed')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div>
    <div class="flex justify-between items-center mb-4">
      <span class="text-sm text-gray-500">{{ store.applications.length }} application(s)</span>
      <el-button type="primary" @click="openCreate">
        <el-icon><Plus /></el-icon> New Application
      </el-button>
    </div>

    <el-card shadow="never">
      <el-table :data="store.applications" stripe v-loading="store.loading">
        <el-table-column prop="app_id" label="App ID" width="160" />
        <el-table-column prop="name" label="Name" />
        <el-table-column prop="war_filename" label="WAR Filename" />
        <el-table-column prop="context_path" label="Context Path" />
        <el-table-column label="Actions" width="140" align="right">
          <template #default="{ row }">
            <el-button size="small" @click="openEdit(row)">Edit</el-button>
            <el-button size="small" type="danger" @click="handleDelete(row)">Delete</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="isEdit ? 'Edit Application' : 'New Application'" width="480px">
      <el-form :model="form" label-width="120px">
        <el-form-item label="App ID">
          <el-input v-model="form.app_id" :disabled="isEdit" placeholder="e.g. brokerage-mobile" />
        </el-form-item>
        <el-form-item label="Name">
          <el-input v-model="form.name" placeholder="e.g. Brokerage Mobile Web" />
        </el-form-item>
        <el-form-item label="WAR Filename">
          <el-input v-model="form.war_filename" placeholder="e.g. BrokerageMobileWeb.war" />
        </el-form-item>
        <el-form-item label="Context Path">
          <el-input v-model="form.context_path" placeholder="e.g. /BMW" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">Cancel</el-button>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">Save</el-button>
      </template>
    </el-dialog>
  </div>
</template>
