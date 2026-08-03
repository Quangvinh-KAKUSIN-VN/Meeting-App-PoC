<template>
  <div class="control-strip">
    <div class="source-selector">
      <label
        class="source-option"
        :class="{
          active: audioSource === 'system',
          disabled: isRecording || isStarting
        }"
      >
        <input
          type="radio"
          value="system"
          :checked="audioSource === 'system'"
          :disabled="isRecording || isStarting"
          @change="$emit('update:audioSource', 'system')"
        />

        <span class="source-icon">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <rect x="3" y="4" width="18" height="13" rx="2" />
            <path d="M8 21h8M12 17v4" />
          </svg>
        </span>

        <span class="source-copy">
          <strong> Âm thanh máy tính </strong>

          <small> Zoom, Meet, YouTube </small>
        </span>

        <span class="source-check"></span>
      </label>

      <label
        class="source-option"
        :class="{
          active: audioSource === 'microphone',
          disabled: isRecording || isStarting
        }"
      >
        <input
          type="radio"
          value="microphone"
          :checked="audioSource === 'microphone'"
          :disabled="isRecording || isStarting"
          @change="$emit('update:audioSource', 'microphone')"
        />

        <span class="source-icon">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <rect x="8" y="3" width="8" height="12" rx="4" />
            <path d="M5 11a7 7 0 0 0 14 0M12 18v3M8 21h8" />
          </svg>
        </span>

        <span class="source-copy">
          <strong>Microphone</strong>

          <small> Người nói hoặc loa ngoài </small>
        </span>

        <span class="source-check"></span>
      </label>
    </div>

    <button
      v-if="!isRecording"
      class="primary-action start-action"
      type="button"
      :disabled="isStarting"
      @click="$emit('start-recording')"
    >
      <span class="action-icon play-icon" aria-hidden="true"></span>

      <span>{{ startButtonText }}</span>
    </button>

    <button
      v-else
      class="primary-action stop-action"
      type="button"
      @click="$emit('stop-recording')"
    >
      <span class="action-icon stop-icon" aria-hidden="true"></span>

      <span>Dừng phiên dịch</span>
    </button>
  </div>
</template>

<script setup>
defineProps({
  audioSource: {
    type: String,
    required: true
  },
  isRecording: {
    type: Boolean,
    required: true
  },
  isStarting: {
    type: Boolean,
    required: true
  },
  startButtonText: {
    type: String,
    required: true
  }
})

defineEmits(['update:audioSource', 'start-recording', 'stop-recording'])
</script>

<style scoped>
.control-strip {
  position: relative;
  z-index: 10;

  min-height: 72px;
  padding: 10px 12px;

  display: flex;
  align-items: stretch;
  gap: 10px;

  border-bottom: 1px solid rgba(168, 162, 158, 0.12);

  background: rgba(28, 25, 23, 0.2);
}

.source-selector {
  min-width: 0;
  flex: 1;

  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.source-option {
  position: relative;

  min-width: 0;
  padding: 8px 34px 8px 9px;

  display: flex;
  align-items: center;
  gap: 8px;

  border: 1px solid rgba(168, 162, 158, 0.15);
  border-radius: 11px;

  color: rgba(214, 211, 209, 0.72);

  background: rgba(28, 25, 23, 0.45);

  cursor: pointer;

  transition:
    color 140ms ease,
    background 140ms ease,
    border-color 140ms ease,
    transform 140ms ease;
}

.source-option:hover {
  color: #fafaf9;

  border-color: rgba(212, 212, 216, 0.25);

  background: rgba(41, 37, 36, 0.65);

  transform: translateY(-1px);
}

.source-option.active {
  color: #ffffff;

  border-color: rgba(212, 212, 216, 0.58);

  background: linear-gradient(135deg, rgba(82, 82, 91, 0.22), rgba(113, 113, 122, 0.15));

  box-shadow: inset 0 0 0 1px rgba(212, 212, 216, 0.08);
}

.source-option.disabled {
  opacity: 0.5;
  cursor: not-allowed;
  pointer-events: none;
}

.source-option input {
  position: absolute;

  width: 1px;
  height: 1px;

  opacity: 0;
  pointer-events: none;
}

.source-icon {
  width: 29px;
  height: 29px;

  flex: 0 0 29px;

  display: grid;
  place-items: center;

  border-radius: 8px;

  color: #e4e4e7;

  background: rgba(39, 39, 42, 0.16);
}

.source-icon svg {
  width: 16px;
  height: 16px;

  fill: none;
  stroke: currentColor;
  stroke-width: 1.7;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.source-copy {
  min-width: 0;

  display: flex;
  flex-direction: column;
  gap: 2px;
}

.source-copy strong,
.source-copy small {
  overflow: hidden;

  text-overflow: ellipsis;
  white-space: nowrap;
}

.source-copy strong {
  font-size: 10px;
  font-weight: 650;
}

.source-copy small {
  color: rgba(168, 162, 158, 0.7);
  font-size: 8.5px;
}

.source-check {
  position: absolute;
  top: 50%;
  right: 11px;

  width: 14px;
  height: 14px;

  border: 1px solid rgba(168, 162, 158, 0.3);
  border-radius: 50%;

  transform: translateY(-50%);
}

.source-option.active .source-check {
  border: 4px solid #d4d4d8;
  background: #ffffff;
}

.primary-action {
  min-width: 162px;
  padding: 0 17px;

  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 9px;

  border: 1px solid transparent;
  border-radius: 11px;

  color: #ffffff;

  font-size: 10.5px;
  font-weight: 700;

  cursor: pointer;

  transition:
    transform 140ms ease,
    filter 140ms ease,
    opacity 140ms ease;
}

.primary-action:hover:not(:disabled) {
  filter: brightness(1.08);
  transform: translateY(-1px);
}

.primary-action:active:not(:disabled) {
  transform: translateY(0);
}

.primary-action:disabled {
  opacity: 0.58;
  cursor: wait;
}

.start-action {
  border-color: rgba(228, 228, 231, 0.26);

  background: linear-gradient(135deg, #52525b, #71717a);

  box-shadow: 0 8px 22px rgba(82, 82, 91, 0.2);
}

.stop-action {
  border-color: rgba(248, 113, 113, 0.28);

  background: linear-gradient(135deg, #dc2626, #b91c1c);

  box-shadow: 0 8px 22px rgba(220, 38, 38, 0.18);
}

.action-icon {
  position: relative;

  width: 16px;
  height: 16px;

  flex: 0 0 16px;

  display: inline-block;

  border-radius: 50%;

  background: rgba(255, 255, 255, 0.16);
}

.play-icon::after {
  content: '';

  position: absolute;
  top: 4px;
  left: 6px;

  border-top: 4px solid transparent;
  border-bottom: 4px solid transparent;
  border-left: 6px solid #ffffff;
}

.stop-icon::after {
  content: '';

  position: absolute;
  top: 5px;
  left: 5px;

  width: 6px;
  height: 6px;

  border-radius: 1px;

  background: #ffffff;
}

.control-slide-enter-active,
.control-slide-leave-active {
  transition:
    opacity 160ms ease,
    transform 160ms ease;
}

.control-slide-enter-from,
.control-slide-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}
@media (max-width: 720px) {
  .control-strip {
    flex-direction: column;
  }

  .primary-action {
    min-height: 38px;
  }
}

@media (max-width: 590px) {
  .source-copy small {
    display: none;
  }

  .source-option {
    padding-right: 29px;
  }
}

@media (max-height: 280px) {
  .control-strip {
    min-height: 58px;
    padding: 7px 10px;
  }

  .source-option {
    padding-top: 5px;
    padding-bottom: 5px;
  }

  .source-icon {
    width: 25px;
    height: 25px;

    flex-basis: 25px;
  }
}

@media (max-height: 220px) {
  .source-copy small {
    display: none;
  }
}
</style>
