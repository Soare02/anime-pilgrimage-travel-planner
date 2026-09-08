<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.65"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <template
      v-for="(path, index) in paths[name] || paths.compass"
      :key="index"
    >
      <path :d="path" />
    </template>
  </svg>
</template>

<script setup>
defineProps({
  name: { type: String, default: 'compass' },
  size: { type: [Number, String], default: 20 }
})

const paths = {
  compass: [
    'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z',
    'm16 8-2.5 5.5L8 16l2.5-5.5L16 8Z'
  ],
  map: ['m3 5 6-2 6 2 6-2v16l-6 2-6-2-6 2V5Z', 'M9 3v16M15 5v16'],
  bookmark: ['M6 4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v17l-6-4-6 4V4Z'],
  clock: ['M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z', 'M12 7v5l3 2'],
  settings: [
    'm10 3-.5 2-2 .9-1.9-.6-2 3.4 1.5 1.4v2.3l-1.5 1.4 2 3.5 2-.6 1.9 1 .5 2.3h4l.5-2.3 2-1 1.9.6 2-3.5-1.5-1.4v-2.3l1.5-1.4-2-3.4-2 .6-1.9-.9-.5-2h-4Z',
    'M15 11.5a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z'
  ],
  grid: ['M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z'],
  search: ['M17 10a7 7 0 1 1-14 0 7 7 0 0 1 14 0Z', 'm15 15 6 6'],
  arrow: ['M4 12h16m-6-6 6 6-6 6'],
  back: ['M20 12H4m6-6-6 6 6 6'],
  chevron: ['m9 5 7 7-7 7'],
  pin: [
    'M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 0 1 14 0Z',
    'M14.5 10a2.5 2.5 0 1 1-5 0 2.5 2.5 0 0 1 5 0Z'
  ],
  sparkles: [
    'm12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z',
    'M20 2v4m-2-2h4'
  ],
  plus: ['M12 5v14M5 12h14'],
  minus: ['M5 12h14'],
  close: ['m6 6 12 12M6 18 18 6'],
  check: ['m5 12 4 4L19 6'],
  target: [
    'M19 12a7 7 0 1 1-14 0 7 7 0 0 1 14 0Z',
    'M12 9v6m-3-3h6M12 2v3m0 14v3M2 12h3m14 0h3'
  ],
  layers: ['m12 3 10 5-10 5L2 8l10-5Z', 'm2 12 10 5 10-5M2 16l10 5 10-5'],
  camera: [
    'M4 7h3l2-3h6l2 3h3a1 1 0 0 1 1 1v11H3V8a1 1 0 0 1 1-1Z',
    'M16 12.5a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z'
  ],
  train: [
    'M6 16V5c0-3 12-3 12 0v11H6Z',
    'M6 10h12M9 16l-3 5m9-5 3 5M8 19h8M9 13h.01M15 13h.01'
  ],
  image: ['M3 3h18v18H3z', 'm3 16 5-5 4 4 3-3 6 6M15 7h.01'],
  sun: [
    'M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z',
    'M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1 1m12 12 1 1M5 19l1-1M18 6l1-1'
  ]
}
</script>
