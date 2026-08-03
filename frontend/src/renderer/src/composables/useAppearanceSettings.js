import { computed, ref, watch } from 'vue'

import { SETTINGS_KEY, DEFAULT_APPEARANCE, LANGUAGE_DIRECTIONS } from '../constants/appearance'

function clampNumber(value, minimum, maximum, fallback) {
  const parsedValue = Number(value)

  if (!Number.isFinite(parsedValue)) {
    return fallback
  }

  return Math.min(Math.max(parsedValue, minimum), maximum)
}

function loadAppearanceSettings() {
  try {
    const savedValue = window.localStorage.getItem(SETTINGS_KEY)

    if (!savedValue) {
      return {
        ...DEFAULT_APPEARANCE
      }
    }

    const savedSettings = JSON.parse(savedValue)

    return {
      subtitleColor:
        typeof savedSettings.subtitleColor === 'string'
          ? savedSettings.subtitleColor
          : DEFAULT_APPEARANCE.subtitleColor,

      fontSize: clampNumber(savedSettings.fontSize, 14, 52, DEFAULT_APPEARANCE.fontSize),

      panelOpacity: clampNumber(
        savedSettings.panelOpacity,
        0.12,
        0.94,
        DEFAULT_APPEARANCE.panelOpacity
      ),

      outlineStrength: clampNumber(
        savedSettings.outlineStrength,
        0,
        5,
        DEFAULT_APPEARANCE.outlineStrength
      ),

      textAlign: ['left', 'center', 'right'].includes(savedSettings.textAlign)
        ? savedSettings.textAlign
        : DEFAULT_APPEARANCE.textAlign,

      translationDirection: ['ja-vi', 'vi-ja'].includes(savedSettings.translationDirection)
        ? savedSettings.translationDirection
        : DEFAULT_APPEARANCE.translationDirection,

      isFocusMode: Boolean(savedSettings.isFocusMode),

      isLocked: Boolean(savedSettings.isLocked)
    }
  } catch (error) {
    console.warn('Không thể đọc thiết lập giao diện:', error)

    return {
      ...DEFAULT_APPEARANCE
    }
  }
}

export function useAppearanceSettings() {
  const savedAppearance = loadAppearanceSettings()

  const subtitleColor = ref(savedAppearance.subtitleColor)

  const fontSize = ref(savedAppearance.fontSize)

  const panelOpacity = ref(savedAppearance.panelOpacity)

  const outlineStrength = ref(savedAppearance.outlineStrength)

  const textAlign = ref(savedAppearance.textAlign)

  const translationDirection = ref(savedAppearance.translationDirection)

  const isFocusMode = ref(savedAppearance.isFocusMode)

  const isLocked = ref(savedAppearance.isLocked)

  const directionInfo = computed(() => {
    return LANGUAGE_DIRECTIONS[translationDirection.value]
  })

  const appearanceVariables = computed(() => {
    const strokeWidth = outlineStrength.value * 0.35

    const shadowBlur = 3 + outlineStrength.value * 2

    const shadowSoft = Math.max(2, shadowBlur * 0.65)

    return {
      '--panel-opacity': panelOpacity.value,

      '--subtitle-color': subtitleColor.value,

      '--subtitle-font-size': `${fontSize.value}px`,

      '--subtitle-stroke': `${strokeWidth}px`,

      '--subtitle-shadow-blur': `${shadowBlur}px`,

      '--subtitle-shadow-soft': `${shadowSoft}px`,

      '--subtitle-align': textAlign.value
    }
  })

  function saveAppearanceSettings() {
    try {
      window.localStorage.setItem(
        SETTINGS_KEY,
        JSON.stringify({
          subtitleColor: subtitleColor.value,

          fontSize: fontSize.value,

          panelOpacity: panelOpacity.value,

          outlineStrength: outlineStrength.value,

          textAlign: textAlign.value,

          translationDirection: translationDirection.value,

          isFocusMode: isFocusMode.value,

          isLocked: isLocked.value
        })
      )
    } catch (error) {
      console.warn('Không thể lưu thiết lập giao diện:', error)
    }
  }

  watch(
    [
      subtitleColor,
      fontSize,
      panelOpacity,
      outlineStrength,
      textAlign,
      translationDirection,
      isFocusMode,
      isLocked
    ],
    saveAppearanceSettings
  )

  function resetAppearance() {
    subtitleColor.value = DEFAULT_APPEARANCE.subtitleColor

    fontSize.value = DEFAULT_APPEARANCE.fontSize

    panelOpacity.value = DEFAULT_APPEARANCE.panelOpacity

    outlineStrength.value = DEFAULT_APPEARANCE.outlineStrength

    textAlign.value = DEFAULT_APPEARANCE.textAlign
  }

  return {
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
  }
}
