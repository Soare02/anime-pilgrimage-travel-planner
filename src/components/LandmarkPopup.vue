<template>
  <div class="landmark-popup">
    <div class="popup-title">{{ point.name }}</div>
    <img
      v-if="point.image"
      :src="getImageUrl(point.image)"
      :alt="point.name"
      class="popup-image"
    />
    <div class="popup-info">
      <span v-if="point.ep">EP{{ point.ep }}</span>
      <span v-if="point.s">{{ formatTime(point.s) }}</span>
      <span v-if="point.day" class="popup-day">第{{ point.day }}天</span>
    </div>
    <div v-if="point.origin" class="popup-origin">
      来源: <a v-if="point.originURL" :href="point.originURL" target="_blank" rel="noopener">{{ point.origin }}</a>
      <span v-else>{{ point.origin }}</span>
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  point: {
    type: Object,
    required: true
  }
})

function getImageUrl(image) {
  if (!image) return ''
  if (image.includes('?')) return image
  return image + '?plan=h360'
}

function formatTime(seconds) {
  if (!seconds) return ''
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  if (h > 0) {
    return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  }
  return `${m}:${String(s).padStart(2, '0')}`
}
</script>

<style scoped>
.landmark-popup {
  min-width: 180px;
  max-width: 260px;
}

.popup-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-color);
  margin-bottom: 8px;
}

.popup-image {
  width: 100%;
  max-height: 160px;
  object-fit: cover;
  border-radius: 6px;
  margin-bottom: 8px;
}

.popup-info {
  display: flex;
  gap: 10px;
  font-size: 13px;
  color: var(--text-secondary);
}

.popup-day {
  color: var(--primary-color);
  font-weight: 500;
}

.popup-origin {
  margin-top: 6px;
  font-size: 11px;
  color: var(--text-secondary);
}

.popup-origin a {
  color: var(--primary-color);
  text-decoration: none;
}

.popup-origin a:hover {
  text-decoration: underline;
}
</style>
