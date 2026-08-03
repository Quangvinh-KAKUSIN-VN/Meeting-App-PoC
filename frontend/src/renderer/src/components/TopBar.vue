<template>
  <header class="top-bar">
    <div
      class="brand-zone"
      :class="{
        draggable: !isLocked
      }"
    >
      <div class="brand-symbol" aria-hidden="true">
        <span class="brand-bubble brand-bubble-ja"> 日 </span>

        <span class="brand-bubble brand-bubble-vi"> Vi </span>
      </div>

      <div class="brand-copy">
        <div class="brand-name">
          <span>KaTOBA</span>
          <strong>BridgeAI</strong>
        </div>

        <span class="brand-caption">
          {{ directionInfo.sourceName }} → {{ directionInfo.targetName }}
        </span>
      </div>
    </div>

    <div class="status-chip">
      <span class="status-dot" :class="statusClass"></span>

      <span>{{ statusLabel }}</span>
    </div>

    <button
      class="direction-switch"
      type="button"
      :disabled="isRecording || isStarting"
      :title="isRecording || isStarting ? 'Dừng phiên dịch để đổi chiều' : 'Đổi chiều dịch'"
      :aria-label="
        'Đổi chiều dịch, hiện tại ' + directionInfo.sourceCode + ' sang ' + directionInfo.targetCode
      "
      @click="$emit('toggle-direction')"
    >
      <span class="direction-code">
        {{ directionInfo.sourceCode }}
      </span>

      <svg class="direction-arrow" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M7 7h13M17 3l4 4-4 4M17 17H4M7 21l-4-4 4-4" />
      </svg>

      <span class="direction-code">
        {{ directionInfo.targetCode }}
      </span>
    </button>

    <div class="top-actions">
      <button
        class="tool-button"
        :class="{
          active: isFocusMode
        }"
        type="button"
        :title="isFocusMode ? 'Hiện bảng điều khiển' : 'Chỉ hiển thị phụ đề'"
        :aria-label="isFocusMode ? 'Hiện bảng điều khiển' : 'Chỉ hiển thị phụ đề'"
        @click="$emit('toggle-focus-mode')"
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path
            d="M4 8V5a1 1 0 0 1 1-1h3M16 4h3a1 1 0 0 1 1 1v3M20 16v3a1 1 0 0 1-1 1h-3M8 20H5a1 1 0 0 1-1-1v-3"
          />
        </svg>
      </button>

      <button
        class="tool-button"
        :class="{
          active: isLocked
        }"
        type="button"
        :title="isLocked ? 'Mở khóa cửa sổ' : 'Khóa vị trí và kích thước'"
        :aria-label="isLocked ? 'Mở khóa cửa sổ' : 'Khóa vị trí và kích thước'"
        @click="$emit('toggle-window-lock')"
      >
        <svg v-if="isLocked" viewBox="0 0 24 24" aria-hidden="true">
          <rect x="5" y="10" width="14" height="10" rx="2" />

          <path d="M8 10V7a4 4 0 0 1 8 0v3" />
        </svg>

        <svg v-else viewBox="0 0 24 24" aria-hidden="true">
          <rect x="5" y="10" width="14" height="10" rx="2" />

          <path d="M8 10V7a4 4 0 0 1 7.5-2" />
        </svg>
      </button>

      <button
        class="tool-button"
        :class="{
          active: showAppearancePanel
        }"
        type="button"
        title="Tùy chỉnh giao diện"
        aria-label="Tùy chỉnh giao diện"
        @click="$emit('toggle-appearance-panel')"
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path
            d="M12 3a9 9 0 1 0 0 18h1.3a2.2 2.2 0 0 0 0-4.4h-1.1a1.7 1.7 0 0 1 0-3.4H15A6 6 0 0 0 15 3h-3Z"
          />

          <circle cx="7.5" cy="9" r="0.8" />
          <circle cx="10" cy="6.5" r="0.8" />
          <circle cx="6.5" cy="13" r="0.8" />
        </svg>
      </button>

      <button
        class="tool-button"
        type="button"
        :disabled="!hasHistory"
        :title="hasHistory ? 'Xuất file lịch sử cuộc họp' : 'Chưa có nội dung để xuất'"
        :aria-label="'Xuất file lịch sử cuộc họp'"
        @click="$emit('export-history')"
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M12 3v12m0 0l-4-4m4 4l4-4M5 17v2a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-2" />
        </svg>
      </button>

      <button
        class="tool-button clear-button"
        type="button"
        title="Xóa phụ đề"
        aria-label="Xóa phụ đề"
        @click="$emit('clear-transcripts')"
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M4 7h16" />
          <path d="M9 7V4h6v3" />
          <path d="M7 7l1 13h8l1-13" />
          <path d="M10 11v5M14 11v5" />
        </svg>
      </button>

      <div v-if="!isMac" class="window-controls">
        <button
          class="window-button minimize-window"
          type="button"
          title="Thu nhỏ"
          aria-label="Thu nhỏ cửa sổ"
          @click="$emit('minimize-window')"
        >
          <span></span>
        </button>

        <button
          class="window-button maximize-window"
          type="button"
          :title="isMaximized ? 'Khôi phục kích thước' : 'Phóng to'"
          :aria-label="isMaximized ? 'Khôi phục kích thước' : 'Phóng to cửa sổ'"
          @click="$emit('toggle-maximize-window')"
        >
          <span
            :class="{
              restore: isMaximized
            }"
          ></span>
        </button>

        <button
          class="window-button close-window"
          type="button"
          title="Đóng"
          aria-label="Đóng cửa sổ"
          @click="$emit('close-window')"
        >
          <span></span>
        </button>
      </div>
    </div>
  </header>
</template>

<script setup>
defineProps({
  isLocked: {
    type: Boolean,
    required: true
  },
  directionInfo: {
    type: Object,
    required: true
  },
  statusClass: {
    type: String,
    required: true
  },
  statusLabel: {
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
  isFocusMode: {
    type: Boolean,
    required: true
  },
  showAppearancePanel: {
    type: Boolean,
    required: true
  },
  hasHistory: {
    type: Boolean,
    required: true
  },
  isMac: {
    type: Boolean,
    required: true
  },
  isMaximized: {
    type: Boolean,
    required: true
  }
})

defineEmits([
  'toggle-direction',
  'toggle-focus-mode',
  'toggle-window-lock',
  'toggle-appearance-panel',
  'export-history',
  'clear-transcripts',
  'minimize-window',
  'toggle-maximize-window',
  'close-window'
])
</script>

<style scoped>
.top-bar {
  position: relative;
  z-index: 20;

  height: 52px;
  min-height: 52px;

  display: flex;
  align-items: center;

  border-bottom: 1px solid rgba(168, 162, 158, 0.14);

  background: rgba(12, 10, 9, 0.34);

  transition:
    opacity 160ms ease,
    transform 160ms ease;
}

.brand-zone {
  min-width: 0;
  height: 100%;
  flex: 1;

  padding: 0 12px;

  display: flex;
  align-items: center;
  gap: 10px;

  user-select: none;
}

.brand-zone.draggable {
  cursor: move;

  -webkit-app-region: drag;
}

.platform-mac .brand-zone {
  padding-left: 82px;
}

.brand-symbol {
  position: relative;

  width: 38px;
  height: 30px;

  flex: 0 0 38px;
}

.brand-bubble {
  --bubble-tail: #ffffff;

  position: absolute;

  width: 25px;
  height: 21px;

  display: grid;
  place-items: center;

  border-radius: 8px 8px 8px 3px;

  font-size: 9px;
  font-weight: 800;
  letter-spacing: -0.3px;

  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.24);
}

.brand-bubble::after {
  content: '';

  position: absolute;
  bottom: -4px;
  left: 5px;

  border-top: 6px solid var(--bubble-tail);
  border-right: 6px solid transparent;
}

.brand-bubble-ja {
  --bubble-tail: #ffffff;

  top: 0;
  left: 0;

  color: #ffffff;
  background: #ffffff;

  font-size: 0;
}

.brand-bubble-ja::before {
  content: '';

  position: absolute;

  width: 7px;
  height: 7px;

  border-radius: 50%;

  background: #ef4444;
}

.brand-bubble-vi {
  --bubble-tail: #ef4444;

  right: 0;
  bottom: 0;

  color: #fde047;
  background: #ef4444;

  border-radius: 8px 8px 3px 8px;
}

.brand-bubble-vi::after {
  right: 5px;
  left: auto;

  border-right: 0;
  border-left: 6px solid transparent;
}

.brand-copy {
  min-width: 0;

  display: flex;
  flex-direction: column;
  gap: 1px;
}

.brand-name {
  overflow: hidden;

  color: #fafaf9;

  font-size: 13px;
  font-weight: 700;
  line-height: 1.1;

  text-overflow: ellipsis;
  white-space: nowrap;
}

.brand-name span {
  letter-spacing: 0.1px;
}

.brand-name strong {
  margin-left: 4px;

  color: #d4d4d8;
}

.brand-caption {
  overflow: hidden;

  color: rgba(214, 211, 209, 0.58);

  font-size: 9px;
  font-weight: 500;
  letter-spacing: 0.35px;

  text-overflow: ellipsis;
  white-space: nowrap;
}

.status-chip {
  height: 28px;
  padding: 0 10px;

  display: flex;
  align-items: center;
  gap: 7px;

  border: 1px solid rgba(168, 162, 158, 0.16);

  border-radius: 999px;

  color: rgba(231, 229, 228, 0.76);

  background: rgba(28, 25, 23, 0.48);

  font-size: 10px;
  font-weight: 650;

  -webkit-app-region: no-drag;
}

.status-dot {
  width: 7px;
  height: 7px;

  border-radius: 50%;

  background: #78716c;
}

.status-dot.ready {
  background: #22c55e;

  box-shadow: 0 0 0 3px rgba(34, 197, 94, 0.11);
}

.status-dot.starting {
  background: #f59e0b;

  animation: status-pulse 1s ease-in-out infinite;
}

.status-dot.recording {
  background: #ef4444;

  box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.12);

  animation: status-pulse 1.15s ease-in-out infinite;
}

.direction-switch {
  flex: 0 0 auto;
  height: 28px;
  margin-left: 8px;
  padding: 0 9px;

  display: flex;
  align-items: center;
  gap: 5px;

  border: 1px solid rgba(212, 212, 216, 0.22);

  border-radius: 999px;

  color: #e4e4e7;

  background: rgba(212, 212, 216, 0.08);

  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.02em;

  cursor: pointer;

  transition:
    color 140ms ease,
    background 140ms ease,
    border-color 140ms ease,
    transform 140ms ease;

  -webkit-app-region: no-drag;
}

.direction-switch:hover:not(:disabled) {
  color: #fafaf9;

  border-color: rgba(212, 212, 216, 0.45);

  background: rgba(212, 212, 216, 0.16);
}

.direction-switch:active:not(:disabled) {
  transform: scale(0.96);
}

.direction-switch:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.direction-code {
  min-width: 15px;
  text-align: center;
}

.direction-arrow {
  width: 12px;
  height: 12px;

  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.top-actions {
  height: 100%;

  display: flex;
  align-items: center;
  gap: 3px;

  padding-left: 8px;

  -webkit-app-region: no-drag;
}

.tool-button {
  width: 32px;
  height: 32px;
  padding: 0;

  display: grid;
  place-items: center;

  border: 1px solid transparent;
  border-radius: 8px;

  color: rgba(214, 211, 209, 0.7);

  background: transparent;

  cursor: pointer;

  transition:
    color 140ms ease,
    background 140ms ease,
    border-color 140ms ease;
}

.tool-button svg {
  width: 16px;
  height: 16px;

  fill: none;
  stroke: currentColor;
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.tool-button:hover,
.tool-button.active {
  color: #fafaf9;

  border-color: rgba(212, 212, 216, 0.22);

  background: rgba(212, 212, 216, 0.11);
}

.tool-button:disabled {
  opacity: 0.38;

  cursor: not-allowed;
  pointer-events: none;
}

.window-controls {
  height: 52px;
  margin-left: 3px;

  display: flex;
  align-items: stretch;
}

.window-button {
  position: relative;

  width: 44px;
  height: 52px;
  padding: 0;

  border: 0;

  color: #d6d3d1;
  background: transparent;

  cursor: pointer;

  transition:
    color 120ms ease,
    background 120ms ease;
}

.window-button:hover {
  color: #ffffff;

  background: rgba(168, 162, 158, 0.13);
}

.minimize-window span {
  position: absolute;
  top: 26px;
  left: 17px;

  width: 11px;
  height: 1px;

  background: currentColor;
}

.maximize-window span {
  position: absolute;
  top: 20px;
  left: 17px;

  width: 11px;
  height: 10px;

  border: 1px solid currentColor;
}

.maximize-window span.restore::before {
  content: '';

  position: absolute;
  top: -4px;
  left: 3px;

  width: 8px;
  height: 7px;

  border: 1px solid currentColor;

  background: #1c1917;
}

.close-window span::before,
.close-window span::after {
  content: '';

  position: absolute;
  top: 25px;
  left: 16px;

  width: 13px;
  height: 1px;

  background: currentColor;
}

.close-window span::before {
  transform: rotate(45deg);
}

.close-window span::after {
  transform: rotate(-45deg);
}

.close-window:hover {
  color: #ffffff;
  background: #dc2626;
}

.is-locked .brand-zone {
  cursor: default;

  -webkit-app-region: no-drag;
}

.is-focus-mode .translator-window:not(:hover) .top-bar {
  opacity: 0;
  transform: translateY(-10px);

  pointer-events: none;
}

.platform-mac .top-actions {
  padding-right: 8px;
}

@keyframes status-pulse {
  0%,
  100% {
    opacity: 1;
  }

  50% {
    opacity: 0.38;
  }
}
@media (max-width: 720px) {
  .status-chip {
    display: none;
  }

  .direction-switch {
    margin-left: 0;
  }
}

@media (max-width: 590px) {
  .brand-caption {
    display: none;
  }

  .clear-button {
    display: none;
  }

  .brand-zone {
    padding-right: 4px;
  }
}

@media (max-height: 280px) {
  .top-bar {
    height: 46px;
    min-height: 46px;
  }

  .window-controls {
    height: 46px;
  }

  .window-button {
    height: 46px;
  }

  .minimize-window span {
    top: 23px;
  }

  .maximize-window span {
    top: 17px;
  }

  .close-window span::before,
  .close-window span::after {
    top: 22px;
  }
}

@media (max-height: 220px) {
  .brand-copy,
  .status-chip,
  .direction-switch,
  .tool-button:not(.active) {
    display: none;
  }
}
</style>
