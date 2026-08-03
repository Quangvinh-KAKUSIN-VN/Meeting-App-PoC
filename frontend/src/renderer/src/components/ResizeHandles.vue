<template>
  <div
    v-for="edge in resizeEdges"
    :key="edge"
    class="resize-handle"
    :class="`resize-${edge}`"
    @mousedown.prevent="$emit('start-resize', edge)"
  ></div>

  <div class="resize-corner-visual" aria-hidden="true">
    <i></i>
    <i></i>
    <i></i>
  </div>
</template>

<script setup>
import { resizeEdges } from '../constants/appearance'

defineEmits(['start-resize'])
</script>

<style scoped>
.resize-handle {
  position: absolute;
  z-index: 60;

  -webkit-app-region: no-drag;
}

.resize-top,
.resize-bottom {
  right: 10px;
  left: 10px;

  height: 7px;
}

.resize-top {
  top: 0;
  cursor: ns-resize;
}

.resize-bottom {
  bottom: 0;
  cursor: ns-resize;
}

.resize-left,
.resize-right {
  top: 10px;
  bottom: 10px;

  width: 7px;
}

.resize-left {
  left: 0;
  cursor: ew-resize;
}

.resize-right {
  right: 0;
  cursor: ew-resize;
}

.resize-top-left,
.resize-top-right,
.resize-bottom-left,
.resize-bottom-right {
  width: 15px;
  height: 15px;
}

.resize-top-left {
  top: 0;
  left: 0;

  cursor: nwse-resize;
}

.resize-top-right {
  top: 0;
  right: 0;

  cursor: nesw-resize;
}

.resize-bottom-left {
  bottom: 0;
  left: 0;

  cursor: nesw-resize;
}

.resize-bottom-right {
  right: 0;
  bottom: 0;

  cursor: nwse-resize;
}

.resize-corner-visual {
  position: absolute;
  z-index: 50;
  right: 5px;
  bottom: 5px;

  width: 13px;
  height: 13px;

  display: flex;
  flex-direction: column;
  align-items: flex-end;
  justify-content: flex-end;
  gap: 2px;

  opacity: 0.42;

  pointer-events: none;
}

.resize-corner-visual i {
  height: 1px;

  border-radius: 99px;
  background: #a8a29e;

  transform: rotate(-45deg);
  transform-origin: right center;
}

.resize-corner-visual i:nth-child(1) {
  width: 5px;
}

.resize-corner-visual i:nth-child(2) {
  width: 8px;
}

.resize-corner-visual i:nth-child(3) {
  width: 11px;
}
</style>
