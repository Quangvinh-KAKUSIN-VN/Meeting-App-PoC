<template>
  <footer class="footer-bar">
    <div class="footer-item">
      <span
        class="footer-indicator"
        :class="{
          active: isRecording
        }"
      ></span>

      <span>{{ selectedSourceLabel }}</span>
    </div>

    <span class="footer-divider"></span>

    <div class="footer-item">
      <span>{{ directionInfo.sourceCode }}</span>
      <b>→</b>
      <span>{{ directionInfo.targetCode }}</span>
    </div>

    <span class="footer-divider"></span>

    <div class="footer-item footer-platform">
      {{ platformLabel }}
    </div>

    <div class="footer-spacer"></div>

    <span class="resize-helper"> Kéo cạnh hoặc góc để đổi kích thước </span>
  </footer>
</template>

<script setup>
defineProps({
  isRecording: {
    type: Boolean,
    required: true
  },
  selectedSourceLabel: {
    type: String,
    required: true
  },
  directionInfo: {
    type: Object,
    required: true
  },
  platformLabel: {
    type: String,
    required: true
  }
})
</script>

<style scoped>
.footer-bar {
  position: relative;
  z-index: 10;

  min-height: 31px;
  padding: 0 13px;

  display: flex;
  align-items: center;
  gap: 8px;

  border-top: 1px solid rgba(168, 162, 158, 0.11);

  color: rgba(168, 162, 158, 0.72);

  background: rgba(12, 10, 9, 0.28);

  font-size: 8.5px;
  font-weight: 600;
}

.footer-item {
  display: flex;
  align-items: center;
  gap: 5px;
}

.footer-item b {
  color: #d4d4d8;
  font-weight: 700;
}

.footer-indicator {
  width: 6px;
  height: 6px;

  border-radius: 50%;

  background: #78716c;
}

.footer-indicator.active {
  background: #ef4444;

  animation: status-pulse 1.15s ease-in-out infinite;
}

.footer-divider {
  width: 1px;
  height: 12px;

  background: rgba(168, 162, 158, 0.18);
}

.footer-spacer {
  flex: 1;
}

.resize-helper {
  color: rgba(168, 162, 158, 0.42);
}
@media (max-width: 590px) {
  .resize-helper,
  .footer-platform {
    display: none;
  }
}

@media (max-height: 280px) {
  .footer-bar {
    display: none;
  }
}
</style>
