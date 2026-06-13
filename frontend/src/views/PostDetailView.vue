<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { PostDetail, PostEvent, api } from '../api/client'

const route = useRoute()
const router = useRouter()
const post = ref<PostDetail | null>(null)
const events = ref<PostEvent[]>([])
const error = ref('')

async function load() {
  try {
    const postId = Number(route.params.id)
    const [postResult, eventResult] = await Promise.all([api.post(postId), api.postEvents(postId)])
    post.value = postResult
    events.value = eventResult
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to load post'
  }
}

async function retry() {
  if (!post.value) return
  await api.retryPost(post.value.id)
  await load()
}

async function skip() {
  if (!post.value) return
  await api.skipPost(post.value.id)
  await load()
}

onMounted(load)
</script>

<template>
  <main class="shell">
    <header class="topbar">
      <button class="secondary" @click="router.push('/')">Back</button>
      <div v-if="post">
        <h1>{{ post.post_id }}</h1>
        <p>{{ post.post_url }}</p>
      </div>
      <div class="actions">
        <button @click="retry">Retry</button>
        <button class="secondary" @click="skip">Skip</button>
      </div>
    </header>
    <p v-if="error" class="error">{{ error }}</p>
    <section v-if="post" class="detail-grid">
      <article>
        <h2>Original</h2>
        <p>{{ post.original_text || '[No text]' }}</p>
      </article>
      <article>
        <h2>Translation</h2>
        <p>{{ post.translated_text || '[No translation]' }}</p>
      </article>
      <article>
        <h2>Status</h2>
        <p>Fetch: {{ post.fetch_status }}</p>
        <p>Media: {{ post.media_status }}</p>
        <p>Translation: {{ post.translation_status }}</p>
        <p>Push: {{ post.push_status }}</p>
      </article>
      <article>
        <h2>Lifecycle</h2>
        <ul class="event-list">
          <li v-for="event in events" :key="`${event.event_type}-${event.created_at}`">
            <strong>{{ event.event_type }}</strong>
            <span>{{ event.status }}</span>
            <small>{{ event.created_at }}</small>
            <p v-if="event.message">{{ event.message }}</p>
          </li>
        </ul>
      </article>
      <article>
        <h2>Media</h2>
        <pre>{{ JSON.stringify(post.media_assets, null, 2) }}</pre>
      </article>
      <article>
        <h2>Translation Jobs</h2>
        <pre>{{ JSON.stringify(post.translation_jobs, null, 2) }}</pre>
      </article>
      <article>
        <h2>Push Logs</h2>
        <pre>{{ JSON.stringify(post.push_logs, null, 2) }}</pre>
      </article>
      <article>
        <h2>Task Attempts</h2>
        <pre>{{ JSON.stringify(post.task_attempts, null, 2) }}</pre>
      </article>
    </section>
  </main>
</template>
