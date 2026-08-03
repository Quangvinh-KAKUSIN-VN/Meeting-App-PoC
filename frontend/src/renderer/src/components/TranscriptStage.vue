<template>
  <div v-if="transcripts.length === 0" class="empty-state">
    <div
      class="empty-wave"
      :class="{
        listening: isRecording
      }"
      aria-hidden="true"
    >
      <i v-for="index in 9" :key="index"></i>
    </div>

    <strong>{{ placeholderTitle }}</strong>

    <p>{{ placeholderText }}</p>
  </div>

  <div v-else class="transcript-list">
    <div v-for="item in transcripts" :key="item.id" class="subtitle-block">
      <div v-if="item.src" class="subtitle-source">
        {{ item.src }}
      </div>

      <div
        class="subtitle-line"
        :class="{
          error: item.type === 'error'
        }"
      >
        {{ item.text }}
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  transcripts: {
    type: Array,
    required: true
  },
  isRecording: {
    type: Boolean,
    required: true
  },
  placeholderTitle: {
    type: String,
    required: true
  },
  placeholderText: {
    type: String,
    required: true
  }
})
</script>

<style scoped>
.empty-state {
  width: 100%;
  height: 100%;
  min-height: 55px;

  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;

  text-align: center;
}

.empty-state strong {
  margin-top: 8px;

  color: rgba(245, 245, 244, 0.86);

  font-size: clamp(12px, 2vw, 15px);
}

.empty-state p {
  max-width: 520px;
  margin: 5px 0 0;

  color: rgba(168, 162, 158, 0.7);

  font-size: clamp(9px, 1.4vw, 11px);
  line-height: 1.45;
}

.empty-wave {
  height: 21px;

  display: flex;
  align-items: center;
  gap: 3px;
}

.empty-wave i {
  width: 3px;
  height: 5px;

  border-radius: 99px;

  background: rgba(212, 212, 216, 0.43);

  transform-origin: center;
}

.empty-wave.listening i {
  animation: wave-listening 1s ease-in-out infinite;
}

.empty-wave i:nth-child(2),
.empty-wave i:nth-child(8) {
  height: 9px;
  animation-delay: 80ms;
}

.empty-wave i:nth-child(3),
.empty-wave i:nth-child(7) {
  height: 14px;
  animation-delay: 160ms;
}

.empty-wave i:nth-child(4),
.empty-wave i:nth-child(6) {
  height: 19px;
  animation-delay: 240ms;
}

.empty-wave i:nth-child(5) {
  height: 12px;
  animation-delay: 320ms;
}

.transcript-list {
  min-height: 100%;

  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  gap: 14px;
}

.subtitle-block {
  width: 100%;

  display: flex;
  flex-direction: column;
  gap: 4px;

  animation: subtitle-enter 180ms ease-out;
}

.subtitle-source {
  width: 100%;

  color: rgba(231, 229, 228, 0.52);

  font-family: 'Segoe UI', 'Noto Sans', Arial, sans-serif;

  font-size: min(calc(var(--subtitle-font-size) * 0.55), 16px);

  font-weight: 600;
  font-style: italic;
  line-height: 1.35;
  text-align: var(--subtitle-align);

  letter-spacing: 0.01em;

  overflow-wrap: anywhere;
}

.subtitle-line {
  width: 100%;

  color: var(--subtitle-color);

  font-family: 'Segoe UI', 'Noto Sans', Arial, sans-serif;

  font-size: var(--subtitle-font-size);

  font-weight: 700;
  line-height: 1.42;
  text-align: var(--subtitle-align);

  letter-spacing: 0.01em;

  -webkit-text-stroke: var(--subtitle-stroke) rgba(0, 0, 0, 0.82);

  text-shadow:
    0 2px var(--subtitle-shadow-blur) rgba(0, 0, 0, 0.96),
    0 0 var(--subtitle-shadow-soft) rgba(0, 0, 0, 0.86);

  overflow-wrap: anywhere;
}

.subtitle-line.error {
  color: #fecaca;

  font-size: min(var(--subtitle-font-size), 18px);

  font-weight: 600;
}

.is-focus-mode .transcript-list {
  justify-content: center;
}

@keyframes wave-listening {
  0%,
  100% {
    transform: scaleY(0.45);
    opacity: 0.5;
  }

  50% {
    transform: scaleY(1.1);
    opacity: 1;
  }
}

@keyframes subtitle-enter {
  from {
    opacity: 0;
    transform: translateY(5px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}
@media (max-height: 220px) {
  .empty-state p {
    display: none;
  }
}
</style>
