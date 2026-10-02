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

/*
 * wsPath = ngôn ngữ NÓI (chọn ASR), target = ngôn ngữ đích (?target= gửi
 * cho backend). Thứ tự khai báo ở đây cũng là thứ tự nút đổi chiều xoay vòng.
 */
export const LANGUAGE_DIRECTIONS = {
  'ja-vi': {
    wsPath: 'ja',
    target: 'vi',
    sourceCode: 'JA',
    targetCode: 'VI',
    sourceName: 'Japanese',
    targetName: 'Vietnamese',
    listeningLabel: 'Đang lắng nghe tiếng Nhật',
    hintText: 'Chọn nguồn âm thanh rồi bắt đầu phiên dịch Nhật → Việt.'
  },

  'vi-ja': {
    wsPath: 'vi',
    target: 'ja',
    sourceCode: 'VI',
    targetCode: 'JA',
    sourceName: 'Vietnamese',
    targetName: 'Japanese',
    listeningLabel: 'Đang lắng nghe tiếng Việt',
    hintText: 'Chọn nguồn âm thanh rồi bắt đầu phiên dịch Việt → Nhật.'
  },

  'en-vi': {
    wsPath: 'en',
    target: 'vi',
    sourceCode: 'EN',
    targetCode: 'VI',
    sourceName: 'English',
    targetName: 'Vietnamese',
    listeningLabel: 'Đang lắng nghe tiếng Anh',
    hintText: 'Chọn nguồn âm thanh rồi bắt đầu phiên dịch Anh → Việt.'
  },

  'vi-en': {
    wsPath: 'vi',
    target: 'en',
    sourceCode: 'VI',
    targetCode: 'EN',
    sourceName: 'Vietnamese',
    targetName: 'English',
    listeningLabel: 'Đang lắng nghe tiếng Việt',
    hintText: 'Chọn nguồn âm thanh rồi bắt đầu phiên dịch Việt → Anh.'
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
