<template>
  <div class="subtitle-overlay">
    <div class="subtitle-window">
      <div class="title-bar">
        <div class="drag-handle">
          <span class="drag-icon">⠿</span>
          <span>Dịch Nhật → Việt</span>
        </div>

        <div class="window-actions">
          <button class="action-btn" type="button" title="Giảm cỡ chữ" @click="decreaseFontSize">
            A−
          </button>

          <button class="action-btn" type="button" title="Tăng cỡ chữ" @click="increaseFontSize">
            A+
          </button>

          <button class="action-btn" type="button" title="Xóa phụ đề" @click="clearTranscripts">
            🗑
          </button>
        </div>
      </div>

      <div class="content">
        <div class="audio-source-selector">
          <label
            class="source-option"
            :class="{
              active: audioSource === 'system',
              disabled: isRecording || isStarting
            }"
          >
            <input
              v-model="audioSource"
              type="radio"
              value="system"
              :disabled="isRecording || isStarting"
            />

            <span class="source-icon">🖥</span>

            <span class="source-content">
              <strong>Âm thanh máy tính</strong>
              <small>Zoom, Meet, YouTube</small>
            </span>
          </label>

          <label
            class="source-option"
            :class="{
              active: audioSource === 'microphone',
              disabled: isRecording || isStarting
            }"
          >
            <input
              v-model="audioSource"
              type="radio"
              value="microphone"
              :disabled="isRecording || isStarting"
            />

            <span class="source-icon">🎤</span>

            <span class="source-content">
              <strong>Microphone</strong>
              <small>Người nói hoặc loa ngoài</small>
            </span>
          </label>
        </div>

        <div class="controls">
          <button
            v-if="!isRecording"
            class="btn start"
            type="button"
            :disabled="isStarting"
            @click="startRecording"
          >
            {{ startButtonText }}
          </button>

          <button v-else class="btn stop" type="button" @click="stopRecording">⏹ Dừng</button>
        </div>

        <div ref="subtitleBoxRef" class="subtitle-box">
          <p v-if="transcripts.length === 0" class="placeholder">
            {{ placeholderText }}
          </p>

          <div
            v-for="item in transcripts"
            :key="item.id"
            class="subtitle-line"
            :style="{
              fontSize: `${fontSize}px`
            }"
          >
            {{ item.text }}
          </div>
        </div>
      </div>

      <div class="resize-hint">◢</div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref } from 'vue'

import { AudioStreamer } from './audioStreamer'

const isRecording = ref(false)
const isStarting = ref(false)

const audioSource = ref('system')

const transcripts = ref([])
const subtitleBoxRef = ref(null)
const fontSize = ref(21)

let streamer = null
let transcriptId = 0
let lastTranscript = ''

const startButtonText = computed(() => {
  if (isStarting.value) {
    return '⏳ Đang khởi động...'
  }

  if (audioSource.value === 'microphone') {
    return '▶ Bật dịch Microphone'
  }

  return '▶ Bật dịch âm thanh máy tính'
})

const placeholderText = computed(() => {
  if (isStarting.value) {
    return 'Đang khởi động nguồn âm thanh...'
  }

  if (!isRecording.value) {
    return 'Chọn nguồn âm thanh và nhấn nút bắt đầu.'
  }

  if (audioSource.value === 'microphone') {
    return 'Đang nghe microphone hoặc âm thanh từ loa ngoài...'
  }

  return 'Đang nghe âm thanh đang phát trong máy tính...'
})

const scrollToLatestSubtitle = async () => {
  await nextTick()

  if (!subtitleBoxRef.value) {
    return
  }

  subtitleBoxRef.value.scrollTop = subtitleBoxRef.value.scrollHeight
}

const addTranscript = async (receivedText) => {
  if (typeof receivedText !== 'string') {
    return
  }

  const textVi = receivedText.trim()

  if (!textVi) {
    return
  }

  /*
   * Không thêm nếu câu mới giống hoàn toàn
   * câu vừa nhận trước đó.
   */
  if (textVi === lastTranscript) {
    return
  }

  lastTranscript = textVi
  transcriptId += 1

  transcripts.value.push({
    id: transcriptId,
    text: textVi
  })

  /*
   * Chỉ giữ lại 30 câu gần nhất
   * để tránh giao diện lưu quá nhiều dữ liệu.
   */
  if (transcripts.value.length > 30) {
    transcripts.value.splice(0, transcripts.value.length - 30)
  }

  await scrollToLatestSubtitle()
}

const addErrorMessage = (message) => {
  transcriptId += 1

  transcripts.value.push({
    id: transcriptId,
    text: message
  })
}

const startRecording = async () => {
  if (isRecording.value || isStarting.value) {
    return
  }

  transcripts.value = []
  lastTranscript = ''
  transcriptId = 0

  isStarting.value = true

  try {
    streamer = new AudioStreamer('ws://127.0.0.1:8000/ws/audio', addTranscript)

    await streamer.start(audioSource.value)

    isRecording.value = true
  } catch (error) {
    console.error('❌ Không thể bắt đầu dịch:', error)

    if (streamer) {
      try {
        await streamer.stop()
      } catch (stopError) {
        console.error('❌ Không thể dọn AudioStreamer:', stopError)
      }
    }

    streamer = null
    isRecording.value = false

    const sourceLabel = audioSource.value === 'microphone' ? 'microphone' : 'âm thanh máy tính'

    addErrorMessage(`Không thể mở ${sourceLabel}. Hãy kiểm tra quyền truy cập và backend.`)
  } finally {
    isStarting.value = false
  }
}

const stopRecording = async () => {
  isRecording.value = false
  isStarting.value = false

  if (streamer) {
    try {
      await streamer.stop()
    } catch (error) {
      console.error('❌ Lỗi khi dừng:', error)
    }
  }

  streamer = null
}

const clearTranscripts = () => {
  transcripts.value = []
  lastTranscript = ''
}

const increaseFontSize = () => {
  if (fontSize.value < 36) {
    fontSize.value += 2
  }
}

const decreaseFontSize = () => {
  if (fontSize.value > 14) {
    fontSize.value -= 2
  }
}

onBeforeUnmount(async () => {
  if (streamer) {
    await streamer.stop()
    streamer = null
  }
})
</script>

<style>
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

.subtitle-overlay {
  width: 100%;
  height: 100%;
  padding: 16px;

  display: flex;
  align-items: center;
  justify-content: center;

  pointer-events: none;
}

.subtitle-window {
  position: relative;

  width: min(780px, calc(100vw - 32px));
  height: 270px;

  min-width: 420px;
  min-height: 230px;

  max-width: calc(100vw - 16px);
  max-height: calc(100vh - 16px);

  display: flex;
  flex-direction: column;

  overflow: hidden;
  resize: both;

  border: 1px solid rgba(255, 255, 255, 0.18);
  border-radius: 14px;

  background: rgba(5, 5, 8, 0.88);
  backdrop-filter: blur(14px);

  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.4);

  pointer-events: auto;
}

.title-bar {
  height: 42px;
  min-height: 42px;
  padding: 0 10px 0 14px;

  display: flex;
  align-items: center;
  justify-content: space-between;

  border-bottom: 1px solid rgba(255, 255, 255, 0.1);

  background: rgba(255, 255, 255, 0.04);
}

.drag-handle {
  height: 100%;
  flex: 1;

  display: flex;
  align-items: center;
  gap: 8px;

  color: rgba(255, 255, 255, 0.78);

  font-family: Arial, sans-serif;
  font-size: 13px;
  font-weight: 600;

  cursor: move;

  -webkit-app-region: drag;
  user-select: none;
}

.drag-icon {
  color: rgba(255, 255, 255, 0.55);
  font-size: 18px;
}

.window-actions {
  display: flex;
  align-items: center;
  gap: 5px;

  -webkit-app-region: no-drag;
}

.action-btn {
  width: 31px;
  height: 28px;
  padding: 0;

  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 6px;

  color: white;
  font-size: 12px;
  font-weight: 700;

  background: rgba(255, 255, 255, 0.07);

  cursor: pointer;
}

.action-btn:hover {
  background: rgba(255, 255, 255, 0.16);
}

.content {
  min-height: 0;
  flex: 1;

  padding: 10px 14px 14px;

  display: flex;
  flex-direction: column;
}

.audio-source-selector {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;

  margin-bottom: 8px;

  -webkit-app-region: no-drag;
}

.source-option {
  min-width: 0;
  padding: 7px 9px;

  display: flex;
  align-items: center;
  gap: 8px;

  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 8px;

  color: rgba(255, 255, 255, 0.7);

  background: rgba(255, 255, 255, 0.04);

  cursor: pointer;
  user-select: none;

  -webkit-app-region: no-drag;
}

.source-option:hover {
  background: rgba(255, 255, 255, 0.09);
}

.source-option.active {
  border-color: rgba(94, 190, 255, 0.65);
  color: #ffffff;

  background: rgba(48, 132, 190, 0.24);
}

.source-option.disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.source-option input {
  position: absolute;

  width: 1px;
  height: 1px;

  opacity: 0;
  pointer-events: none;
}

.source-icon {
  flex-shrink: 0;
  font-size: 18px;
}

.source-content {
  min-width: 0;

  display: flex;
  flex-direction: column;
  gap: 1px;
}

.source-content strong {
  overflow: hidden;

  font-family: Arial, sans-serif;
  font-size: 12px;

  text-overflow: ellipsis;
  white-space: nowrap;
}

.source-content small {
  overflow: hidden;

  color: rgba(255, 255, 255, 0.5);

  font-family: Arial, sans-serif;
  font-size: 10px;

  text-overflow: ellipsis;
  white-space: nowrap;
}

.controls {
  display: flex;
  justify-content: center;

  margin-bottom: 8px;
}

.btn {
  min-width: 210px;
  padding: 8px 16px;

  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 9px;

  color: white;
  font-size: 13px;
  font-weight: 700;

  cursor: pointer;
}

.btn:disabled {
  opacity: 0.6;
  cursor: wait;
}

.start {
  background: rgba(26, 110, 72, 0.92);
}

.start:hover:not(:disabled) {
  background: rgba(32, 135, 88, 0.96);
}

.stop {
  background: rgba(195, 48, 58, 0.92);
}

.stop:hover {
  background: rgba(220, 54, 65, 0.96);
}

.subtitle-box {
  min-height: 0;
  flex: 1;

  padding: 8px 12px;

  display: flex;
  flex-direction: column;
  gap: 7px;

  overflow-y: auto;
  scroll-behavior: smooth;

  border-radius: 9px;

  background: rgba(0, 0, 0, 0.25);

  scrollbar-width: none;
}

.subtitle-box::-webkit-scrollbar {
  display: none;
}

.placeholder {
  margin: auto;

  color: rgba(255, 255, 255, 0.5);

  font-family: Arial, sans-serif;
  font-size: 16px;
  font-style: italic;
  text-align: center;
}

.subtitle-line {
  color: #ffffff;

  font-family: Arial, 'Segoe UI', sans-serif;
  font-weight: 600;

  line-height: 1.45;
  text-align: center;

  text-shadow:
    0 1px 2px rgba(0, 0, 0, 1),
    0 2px 7px rgba(0, 0, 0, 0.9);

  overflow-wrap: anywhere;

  animation: subtitle-appear 0.2s ease-out;
}

.resize-hint {
  position: absolute;
  right: 3px;
  bottom: 1px;

  color: rgba(255, 255, 255, 0.45);
  font-size: 14px;

  pointer-events: none;
  user-select: none;
}

@keyframes subtitle-appear {
  from {
    opacity: 0;
    transform: translateY(4px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@media (max-width: 520px) {
  .audio-source-selector {
    grid-template-columns: 1fr;
  }

  .subtitle-window {
    min-width: 300px;
    height: 320px;
  }
}
</style>
