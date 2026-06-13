<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Account, DashboardSummary, PostListItem, api, clearToken } from '../api/client'

const router = useRouter()
const summary = ref<DashboardSummary | null>(null)
const accounts = ref<Account[]>([])
const posts = ref<PostListItem[]>([])
const error = ref('')
const loading = ref(false)
const filter = ref('')

async function load() {
  error.value = ''
  loading.value = true
  try {
    const [summaryResult, accountsResult, postsResult] = await Promise.all([
      api.summary(),
      api.accounts(),
      api.posts(filter.value || undefined)
    ])
    summary.value = summaryResult
    accounts.value = accountsResult
    posts.value = postsResult
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to load dashboard'
  } finally {
    loading.value = false
  }
}

async function syncFirstAccount() {
  if (!accounts.value[0]) return
  await api.triggerSync(accounts.value[0].id)
  await load()
}

function logout() {
  clearToken()
  router.push('/login')
}

onMounted(load)
</script>

<template>
  <main class="shell">
    <header class="topbar">
      <div>
        <h1>Operations Dashboard</h1>
        <p>X sync, translation, media archival, and Feishu push status.</p>
      </div>
      <div class="actions">
        <button @click="syncFirstAccount">Manual sync</button>
        <button class="secondary" @click="load">Refresh</button>
        <button class="secondary" @click="logout">Logout</button>
      </div>
    </header>

    <p v-if="error" class="error">{{ error }}</p>
    <section v-if="summary" class="metrics">
      <article><span>Accounts</span><strong>{{ summary.accounts }}</strong></article>
      <article><span>Posts</span><strong>{{ summary.posts }}</strong></article>
      <article><span>Failed</span><strong>{{ summary.failed_posts }}</strong></article>
      <article><span>Pending</span><strong>{{ summary.pending_posts }}</strong></article>
      <article><span>SLA 24h</span><strong>{{ summary.sla_violations_24h }}</strong></article>
    </section>

    <section class="toolbar">
      <select v-model="filter" @change="load">
        <option value="">All posts</option>
        <option value="failed">Failed/retrying</option>
        <option value="pending">Pending push</option>
        <option value="succeeded">Pushed</option>
      </select>
      <span v-if="loading">Loading...</span>
    </section>

    <section class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Post</th>
            <th>Lifecycle</th>
            <th>Published</th>
            <th>Error</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="post in posts" :key="post.id" @click="router.push(`/posts/${post.id}`)">
            <td>
              <strong>{{ post.post_id }}</strong>
              <p>{{ post.original_text || '[No text]' }}</p>
            </td>
            <td>
              <span>{{ post.media_status }}</span>
              <span>{{ post.translation_status }}</span>
              <span>{{ post.push_status }}</span>
            </td>
            <td>{{ post.published_at || '-' }}</td>
            <td>{{ post.error_message || '-' }}</td>
          </tr>
        </tbody>
      </table>
    </section>
  </main>
</template>
