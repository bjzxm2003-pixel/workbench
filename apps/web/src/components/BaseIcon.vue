<script setup>
const props = defineProps({
  name: { type: String, required: true },
  size: { type: [Number, String], default: 20 },
})

const paths = {
  bolt: '<path d="M13 2 4.6 13.4h5.1L9.3 22 18.4 10.6h-5.1L13 2z" />',
  heart:
    '<path d="M12 20.6C6.9 16.5 2.8 13 2.8 9.1 2.8 6.4 4.9 4.4 7.3 4.4c1.7 0 3.2.9 4.2 2.4l.5.7.5-.7c1-1.5 2.5-2.4 4.2-2.4 2.4 0 4.5 2 4.5 4.7 0 3.9-4.1 7.4-9.2 11.5z" />',
  book: '<path d="M12 6.2C10.4 4.9 8 4.3 5.2 4.3v13.4c2.8 0 5.2.6 6.8 1.9 1.6-1.3 4-1.9 6.8-1.9V4.3c-2.8 0-5.2.6-6.8 1.9z"/><path d="M12 6.2v13.4" />',
  clock:
    '<circle cx="12" cy="12" r="8.2"/><path d="M12 7.4V12l3 2.2" />',
  upload: '<path d="M12 16V4.5"/><path d="m7.5 8.5 4.5-4 4.5 4"/><path d="M4.5 15.5v3a1.5 1.5 0 0 0 1.5 1.5h12a1.5 1.5 0 0 0 1.5-1.5v-3"/>',
  radar:
    '<circle cx="12" cy="12" r="8.4"/><circle cx="12" cy="12" r="3.2"/><path d="M12 3.6v4.4"/><path d="M12 16v4.4"/><path d="M3.6 12H8"/><path d="M16 12h4.4"/>',
  arrow: '<path d="M5 12h13"/><path d="m13 6 6 6-6 6"/>',
  check: '<path d="m4.5 12.5 4.8 4.8L19.5 7" />',
}
</script>

<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.6"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    v-html="paths[name] || ''"
  />
</template>
