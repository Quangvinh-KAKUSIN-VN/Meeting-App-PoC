export const SETTINGS_KEY = 'katoba-bridge-ai-ui-v1'

export const DEFAULT_APPEARANCE = {
  subtitleColor: '#FFFFFF',
  fontSize: 24,
  panelOpacity: 0.62,
  outlineStrength: 3,
  textAlign: 'center',
  translationDirection: 'ja-vi',
  isFocusMode: false,
  isLocked: false
}

export const LANGUAGE_DIRECTIONS = {
  'ja-vi': {
    wsPath: 'ja',
    sourceCode: 'JA',
    targetCode: 'VI',
    sourceName: 'Japanese',
    targetName: 'Vietnamese',
    listeningLabel: 'Đang lắng nghe tiếng Nhật',
    hintText: 'Chọn nguồn âm thanh rồi bắt đầu phiên dịch Nhật → Việt.'
  },

  'vi-ja': {
    wsPath: 'vi',
    sourceCode: 'VI',
    targetCode: 'JA',
    sourceName: 'Vietnamese',
    targetName: 'Japanese',
    listeningLabel: 'Đang lắng nghe tiếng Việt',
    hintText: 'Chọn nguồn âm thanh rồi bắt đầu phiên dịch Việt → Nhật.'
  }
}

export const colorPresets = [
  {
    label: 'Trắng',
    value: '#FFFFFF'
  },
  {
    label: 'Vàng ấm',
    value: '#FFE082'
  },
  {
    label: 'Xanh cyan',
    value: '#67E8F9'
  },
  {
    label: 'Xanh lá',
    value: '#86EFAC'
  },
  {
    label: 'Cam',
    value: '#FDBA74'
  },
  {
    label: 'Hồng',
    value: '#F9A8D4'
  }
]

export const resizeEdges = [
  'top',
  'right',
  'bottom',
  'left',
  'top-left',
  'top-right',
  'bottom-left',
  'bottom-right'
]
