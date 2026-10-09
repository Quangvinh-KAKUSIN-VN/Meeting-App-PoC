import { DEFAULT_UI_LANGUAGE } from '../i18n'

export const SETTINGS_KEY = 'katoba-bridge-ai-ui-v1'

export const DEFAULT_APPEARANCE = {
  subtitleColor: '#FFFFFF',
  fontSize: 24,
  panelOpacity: 0.62,
  outlineStrength: 3,
  textAlign: 'center',
  translationDirection: 'ja-vi',
  isFocusMode: false,
  isLocked: false,
  uiLanguage: DEFAULT_UI_LANGUAGE
}

/*
 * wsPath = ngôn ngữ NÓI (chọn ASR), target = ngôn ngữ đích (?target= gửi
 * cho backend). Thứ tự khai báo ở đây cũng là thứ tự nút đổi chiều xoay vòng.
 *
 * Chữ hiển thị (tên ngôn ngữ, câu gợi ý) nằm trong i18n/vi.js và i18n/en.js:
 * languages.<wsPath|target> và directions.<key>.
 */
export const LANGUAGE_DIRECTIONS = {
  'ja-vi': {
    wsPath: 'ja',
    target: 'vi',
    sourceCode: 'JA',
    targetCode: 'VI'
  },

  'vi-ja': {
    wsPath: 'vi',
    target: 'ja',
    sourceCode: 'VI',
    targetCode: 'JA'
  },

  'en-vi': {
    wsPath: 'en',
    target: 'vi',
    sourceCode: 'EN',
    targetCode: 'VI'
  },

  'vi-en': {
    wsPath: 'vi',
    target: 'en',
    sourceCode: 'VI',
    targetCode: 'EN'
  }
}

// key dùng để tra tên màu: colors.<key> trong i18n
export const colorPresets = [
  {
    key: 'white',
    value: '#FFFFFF'
  },
  {
    key: 'warmYellow',
    value: '#FFE082'
  },
  {
    key: 'cyan',
    value: '#67E8F9'
  },
  {
    key: 'green',
    value: '#86EFAC'
  },
  {
    key: 'orange',
    value: '#FDBA74'
  },
  {
    key: 'pink',
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
