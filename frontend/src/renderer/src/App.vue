<template>
  <div
    class="app-root"
    :class="[
      platformClass,
      {
        'is-maximized': isMaximized,
        'is-focus-mode': isFocusMode,
        'is-locked': isLocked
      }
    ]"
    :style="appearanceVariables"
  >
    <section class="translator-window">
      <TopBar
        :is-locked="isLocked"
        :direction-info="directionInfo"
        :status-class="statusClass"
        :status-label="statusLabel"
        :is-recording="isRecording"
        :is-starting="isStarting"
        :is-focus-mode="isFocusMode"
        :show-appearance-panel="showAppearancePanel"
        :has-history="hasHistory"
        :is-mac="isMac"
        :is-maximized="isMaximized"
        @toggle-direction="toggleDirection"
        @toggle-focus-mode="toggleFocusMode"
        @toggle-window-lock="toggleWindowLock"
        @toggle-appearance-panel="toggleAppearancePanel"
        @export-history="exportHistory"
        @clear-transcripts="clearTranscripts"
        @minimize-window="minimizeWindow"
        @toggle-maximize-window="toggleMaximizeWindow"
        @close-window="closeWindow"
      />

      <Transition name="panel-fade">
        <AppearancePanel
          v-if="showAppearancePanel"
          v-model:subtitle-color="subtitleColor"
          v-model:font-size="fontSize"
          v-model:panel-opacity="panelOpacity"
          v-model:outline-strength="outlineStrength"
          v-model:text-align="textAlign"
          :keep-on-top="keepOnTop"
          @close="showAppearancePanel = false"
          @set-always-on-top="setAlwaysOnTop"
          @reset-appearance="resetAppearance"
        />
      </Transition>

      <Transition name="control-slide">
        <ControlStrip
          v-if="!isFocusMode"
          v-model:audio-source="audioSource"
          :is-recording="isRecording"
          :is-starting="isStarting"
          :start-button-text="startButtonText"
          @start-recording="startRecording"
          @stop-recording="stopRecording"
        />
      </Transition>

      <main ref="subtitleBoxRef" class="transcript-stage">
        <TranscriptStage
          :transcripts="transcripts"
          :is-recording="isRecording"
          :placeholder-title="placeholderTitle"
          :placeholder-text="placeholderText"
        />
      </main>

      <FooterBar
        v-if="!isFocusMode"
        :is-recording="isRecording"
        :selected-source-label="selectedSourceLabel"
        :direction-info="directionInfo"
        :platform-label="platformLabel"
      />

      <ResizeHandles v-if="!isLocked && !isMaximized" @start-resize="startWindowResize" />
    </section>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { useAppearanceSettings } from './composables/useAppearanceSettings'

import { useWindowControls } from './composables/useWindowControls'

import { useTranscription } from './composables/useTranscription'

import TopBar from './components/TopBar.vue'
import AppearancePanel from './components/AppearancePanel.vue'
import ControlStrip from './components/ControlStrip.vue'
import TranscriptStage from './components/TranscriptStage.vue'
import FooterBar from './components/FooterBar.vue'
import ResizeHandles from './components/ResizeHandles.vue'

const {
  subtitleColor,
  fontSize,
  panelOpacity,
  outlineStrength,
  textAlign,
  translationDirection,
  isFocusMode,
  isLocked,
  directionInfo,
  appearanceVariables,
  resetAppearance
} = useAppearanceSettings()

const {
  audioSource,
  isRecording,
  isStarting,
  transcripts,
  sessionHistory,
  hasHistory,
  subtitleBoxRef,
  startRecording,
  stopRecording,
  clearTranscripts,
  exportHistory
} = useTranscription(translationDirection)

const {
  platform,
  isMaximized,
  keepOnTop,
  isMac,
  platformLabel,
  platformClass,
  setAlwaysOnTop,
  minimizeWindow,
  toggleMaximizeWindow,
  closeWindow,
  startWindowResize,
  stopWindowResize
} = useWindowControls({
  onBeforeClose: stopRecording
})

const showAppearancePanel = ref(false)

const statusLabel = computed(() => {
  if (isStarting.value) {
    return 'Đang kết nối'
  }

  if (isRecording.value) {
    return 'Đang dịch'
  }

  return 'Sẵn sàng'
})

const statusClass = computed(() => {
  if (isStarting.value) {
    return 'starting'
  }

  if (isRecording.value) {
    return 'recording'
  }

  return 'ready'
})

const selectedSourceLabel = computed(() => {
  return audioSource.value === 'microphone' ? 'Microphone' : 'Âm thanh máy tính'
})

const startButtonText = computed(() => {
  if (isStarting.value) {
    return 'Đang khởi động...'
  }

  return 'Bắt đầu phiên dịch'
})

const placeholderTitle = computed(() => {
  if (isStarting.value) {
    return 'Đang kết nối với AI'
  }

  if (isRecording.value) {
    return directionInfo.value.listeningLabel
  }

  return 'Phụ đề sẽ xuất hiện tại đây'
})

const placeholderText = computed(() => {
  if (isStarting.value) {
    return 'Đang chuẩn bị nguồn âm thanh và kết nối backend.'
  }

  if (!isRecording.value) {
    return directionInfo.value.hintText
  }

  if (audioSource.value === 'microphone') {
    return 'Hãy để microphone gần người nói hoặc loa ngoài.'
  }

  return `Đang nghe âm thanh máy tính trên ${platformLabel.value}.`
})

const toggleFocusMode = () => {
  isFocusMode.value = !isFocusMode.value
  showAppearancePanel.value = false
}

const toggleDirection = () => {
  if (isRecording.value || isStarting.value) {
    return
  }

  translationDirection.value = translationDirection.value === 'ja-vi' ? 'vi-ja' : 'ja-vi'
}

const toggleWindowLock = () => {
  isLocked.value = !isLocked.value

  if (isLocked.value) {
    stopWindowResize()
  }
}

const toggleAppearancePanel = () => {
  showAppearancePanel.value = !showAppearancePanel.value
}

const handleKeydown = (event) => {
  if (event.key === 'Escape') {
    showAppearancePanel.value = false
  }
}

onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeydown)
})
</script>

<style>
:root {
  color-scheme: dark;

  font-family: Inter, 'Segoe UI', Arial, sans-serif;
}

* {
  box-sizing: border-box;
}

html,
body,
#app {
  width: 100%;
  height: 100%;
  margin: 0;

  background: transparent;
  overflow: hidden;
}

button,
input,
label {
  font-family: inherit;
  -webkit-app-region: no-drag;
}

button {
  outline: none;
}

.app-root {
  width: 100%;
  height: 100%;
  padding: 8px;

  color: #fafaf9;

  background: transparent;

  user-select: none;
}

.translator-window {
  position: relative;

  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;

  display: flex;
  flex-direction: column;

  overflow: hidden;

  border: 1px solid rgba(168, 162, 158, 0.24);

  border-radius: 18px;

  background: linear-gradient(
    145deg,
    rgba(28, 25, 23, var(--panel-opacity)),
    rgba(12, 10, 9, var(--panel-opacity))
  );

  box-shadow:
    0 22px 60px rgba(0, 0, 0, 0.45),
    inset 0 1px 0 rgba(255, 255, 255, 0.08);

  pointer-events: auto;
}

.translator-window::before {
  content: '';

  position: absolute;
  inset: 0;

  border-radius: inherit;

  background:
    radial-gradient(circle at 15% 0%, rgba(212, 212, 216, 0.12), transparent 42%),
    radial-gradient(circle at 92% 100%, rgba(113, 113, 122, 0.09), transparent 45%);

  pointer-events: none;
}

.is-maximized {
  padding: 0;
}

.is-maximized .translator-window {
  border: 0;
  border-radius: 0;
}

.transcript-stage {
  position: relative;
  z-index: 5;

  min-height: 0;
  flex: 1;

  padding: 15px 20px;

  overflow-y: auto;
  scroll-behavior: smooth;

  -webkit-app-region: no-drag;
}

.transcript-stage::-webkit-scrollbar {
  width: 5px;
}

.transcript-stage::-webkit-scrollbar-track {
  background: transparent;
}

.transcript-stage::-webkit-scrollbar-thumb {
  border-radius: 99px;
  background: rgba(168, 162, 158, 0.25);
}

.is-focus-mode .transcript-stage {
  padding: 20px 26px;
}
@media (max-height: 280px) {
  .transcript-stage {
    padding-top: 10px;
    padding-bottom: 10px;
  }
}
</style>
