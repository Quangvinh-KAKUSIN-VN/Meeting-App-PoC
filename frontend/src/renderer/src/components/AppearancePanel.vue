<template>
  <aside class="appearance-panel" @mousedown.stop>
    <div class="appearance-header">
      <div>
        <strong>Hiển thị phụ đề</strong>
        <span>Tùy chỉnh và tự động lưu</span>
      </div>

      <button
        class="panel-close"
        type="button"
        aria-label="Đóng bảng tùy chỉnh"
        @click="$emit('close')"
      >
        ×
      </button>
    </div>

    <div class="setting-group">
      <div class="setting-label">
        <span>Màu chữ</span>

        <code>{{ subtitleColor }}</code>
      </div>

      <div class="color-row">
        <button
          v-for="preset in colorPresets"
          :key="preset.value"
          class="color-preset"
          :class="{
            selected: subtitleColor.toLowerCase() === preset.value.toLowerCase()
          }"
          type="button"
          :title="preset.label"
          :aria-label="preset.label"
          :style="{
            backgroundColor: preset.value
          }"
          @click="$emit('update:subtitleColor', preset.value)"
        ></button>

        <label class="custom-color" title="Chọn màu khác">
          <input
            :value="subtitleColor"
            type="color"
            @input="$emit('update:subtitleColor', $event.target.value)"
          />

          <span>+</span>
        </label>
      </div>
    </div>

    <div class="setting-group">
      <div class="setting-label">
        <span>Cỡ chữ</span>

        <strong>{{ fontSize }} px</strong>
      </div>

      <input
        :value="fontSize"
        class="range-input"
        type="range"
        min="14"
        max="52"
        step="1"
        @input="$emit('update:fontSize', Number($event.target.value))"
      />
    </div>

    <div class="setting-group">
      <div class="setting-label">
        <span>Độ trong suốt nền</span>

        <strong> {{ Math.round(panelOpacity * 100) }}% </strong>
      </div>

      <input
        :value="panelOpacity"
        class="range-input"
        type="range"
        min="0.12"
        max="0.94"
        step="0.02"
        @input="$emit('update:panelOpacity', Number($event.target.value))"
      />
    </div>

    <div class="setting-group">
      <div class="setting-label">
        <span>Viền chữ</span>

        <strong>{{ outlineStrength }}</strong>
      </div>

      <input
        :value="outlineStrength"
        class="range-input"
        type="range"
        min="0"
        max="5"
        step="1"
        @input="$emit('update:outlineStrength', Number($event.target.value))"
      />
    </div>

    <div class="setting-group">
      <span class="setting-label"> Căn chỉnh phụ đề </span>

      <div class="segment-control">
        <button
          type="button"
          :class="{
            active: textAlign === 'left'
          }"
          @click="$emit('update:textAlign', 'left')"
        >
          Trái
        </button>

        <button
          type="button"
          :class="{
            active: textAlign === 'center'
          }"
          @click="$emit('update:textAlign', 'center')"
        >
          Giữa
        </button>

        <button
          type="button"
          :class="{
            active: textAlign === 'right'
          }"
          @click="$emit('update:textAlign', 'right')"
        >
          Phải
        </button>
      </div>
    </div>

    <label class="switch-row">
      <span>
        <strong>Luôn nổi trên cùng</strong>
        <small> Giữ phụ đề phía trên Zoom hoặc Meet </small>
      </span>

      <input
        type="checkbox"
        :checked="keepOnTop"
        @change="$emit('set-always-on-top', $event.target.checked)"
      />

      <i></i>
    </label>

    <button class="reset-appearance" type="button" @click="$emit('reset-appearance')">
      Khôi phục giao diện mặc định
    </button>
  </aside>
</template>

<script setup>
import { colorPresets } from '../constants/appearance'

defineProps({
  subtitleColor: {
    type: String,
    required: true
  },
  fontSize: {
    type: Number,
    required: true
  },
  panelOpacity: {
    type: Number,
    required: true
  },
  outlineStrength: {
    type: Number,
    required: true
  },
  textAlign: {
    type: String,
    required: true
  },
  keepOnTop: {
    type: Boolean,
    required: true
  }
})

defineEmits([
  'close',
  'update:subtitleColor',
  'update:fontSize',
  'update:panelOpacity',
  'update:outlineStrength',
  'update:textAlign',
  'set-always-on-top',
  'reset-appearance'
])
</script>

<style scoped>
.appearance-panel {
  position: absolute;
  z-index: 40;
  top: 58px;
  right: 12px;

  width: min(320px, calc(100% - 24px));
  max-height: calc(100% - 70px);
  padding: 14px;

  overflow-y: auto;

  border-radius: 14px;

  background: rgba(15, 13, 12, 0.96);

  box-shadow: 0 20px 48px rgba(0, 0, 0, 0.48);

  -webkit-app-region: no-drag;
}

.appearance-panel::-webkit-scrollbar {
  width: 5px;
}

.appearance-panel::-webkit-scrollbar-thumb {
  border-radius: 99px;
  background: rgba(168, 162, 158, 0.3);
}

.appearance-header {
  margin-bottom: 15px;

  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.appearance-header > div {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.appearance-header strong {
  font-size: 13px;
}

.appearance-header span {
  color: rgba(168, 162, 158, 0.72);
  font-size: 10px;
}

.panel-close {
  width: 25px;
  height: 25px;
  padding: 0;

  border: 0;
  border-radius: 6px;

  color: #a8a29e;
  background: transparent;

  font-size: 20px;
  line-height: 1;

  cursor: pointer;
}

.panel-close:hover {
  color: #ffffff;
  background: rgba(168, 162, 158, 0.12);
}

.setting-group {
  margin-top: 14px;
}

.setting-label {
  margin-bottom: 8px;

  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;

  color: rgba(231, 229, 228, 0.83);

  font-size: 11px;
  font-weight: 600;
}

.setting-label code {
  color: #e4e4e7;

  font-family: 'SFMono-Regular', Consolas, monospace;

  font-size: 9px;
}

.setting-label strong {
  color: #e4e4e7;
  font-size: 10px;
}

.color-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.color-preset,
.custom-color {
  width: 27px;
  height: 27px;
  padding: 0;

  display: grid;
  place-items: center;

  border: 2px solid rgba(255, 255, 255, 0.16);
  border-radius: 50%;

  cursor: pointer;

  transition:
    transform 120ms ease,
    border-color 120ms ease;
}

.color-preset:hover,
.custom-color:hover {
  transform: scale(1.08);
}

.color-preset.selected {
  border-color: #d4d4d8;

  box-shadow: 0 0 0 3px rgba(212, 212, 216, 0.13);
}

.custom-color {
  position: relative;

  color: #e7e5e4;

  background: conic-gradient(#ef4444, #f59e0b, #22c55e, #06b6d4, #3b82f6, #a855f7, #ef4444);

  font-size: 18px;
  font-weight: 400;
}

.custom-color input {
  position: absolute;
  inset: 0;

  opacity: 0;
  cursor: pointer;
}

.custom-color span {
  width: 17px;
  height: 17px;

  display: grid;
  place-items: center;

  border-radius: 50%;

  color: #ffffff;
  background: rgba(12, 10, 9, 0.8);

  line-height: 1;
}

.range-input {
  width: 100%;
  height: 4px;

  border-radius: 99px;

  accent-color: #d4d4d8;
  cursor: pointer;
}

.segment-control {
  padding: 3px;

  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 3px;

  border: 1px solid rgba(168, 162, 158, 0.15);
  border-radius: 9px;

  background: rgba(28, 25, 23, 0.7);
}

.segment-control button {
  height: 27px;

  border: 0;
  border-radius: 6px;

  color: rgba(214, 211, 209, 0.66);
  background: transparent;

  font-size: 10px;
  font-weight: 600;

  cursor: pointer;
}

.segment-control button.active {
  color: #ffffff;
  background: rgba(212, 212, 216, 0.18);
}

.switch-row {
  position: relative;

  min-height: 52px;
  margin-top: 16px;
  padding: 10px 48px 10px 11px;

  display: flex;
  align-items: center;

  border: 1px solid rgba(168, 162, 158, 0.14);
  border-radius: 10px;

  background: rgba(28, 25, 23, 0.52);

  cursor: pointer;
}

.switch-row > span {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.switch-row strong {
  font-size: 11px;
}

.switch-row small {
  color: rgba(168, 162, 158, 0.68);
  font-size: 9px;
}

.switch-row input {
  position: absolute;

  width: 1px;
  height: 1px;

  opacity: 0;
}

.switch-row i {
  position: absolute;
  top: 17px;
  right: 12px;

  width: 30px;
  height: 17px;

  border-radius: 99px;

  background: #44403c;

  transition: background 140ms ease;
}

.switch-row i::after {
  content: '';

  position: absolute;
  top: 3px;
  left: 3px;

  width: 11px;
  height: 11px;

  border-radius: 50%;

  background: #fafaf9;

  transition: transform 140ms ease;
}

.switch-row input:checked + i {
  background: #52525b;
}

.switch-row input:checked + i::after {
  transform: translateX(13px);
}

.reset-appearance {
  width: 100%;
  height: 34px;
  margin-top: 13px;

  border: 1px solid rgba(168, 162, 158, 0.17);
  border-radius: 9px;

  color: #d6d3d1;
  background: rgba(28, 25, 23, 0.58);

  font-size: 10px;
  font-weight: 650;

  cursor: pointer;
}

.reset-appearance:hover {
  color: #ffffff;
  border-color: rgba(212, 212, 216, 0.3);
}

.panel-fade-enter-active,
.panel-fade-leave-active {
  transition:
    opacity 140ms ease,
    transform 140ms ease;
}

.panel-fade-enter-from,
.panel-fade-leave-to {
  opacity: 0;

  transform: translateY(-6px) scale(0.98);
}
</style>
