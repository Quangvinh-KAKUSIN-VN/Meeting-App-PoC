import { ref, watch } from 'vue'

import vi from './vi'
import en from './en'

/*
 * i18n tự viết thay vì vue-i18n: app chỉ có khoảng 100 chuỗi, 2 ngôn ngữ,
 * không cần số nhiều hay định dạng ngày theo locale.
 *
 * uiLanguage là ref dùng chung cho cả app, nên t() gọi trong template
 * hoặc computed sẽ tự render lại khi người dùng đổi ngôn ngữ.
 *
 * Thêm ngôn ngữ mới: tạo file từ điển cùng cấu trúc với vi.js,
 * đăng ký vào MESSAGES và UI_LANGUAGES.
 */
const MESSAGES = {
  vi,
  en
}

export const DEFAULT_UI_LANGUAGE = 'vi'

/*
 * label giữ nguyên tên gốc của từng ngôn ngữ, không dịch theo ngôn ngữ
 * đang chọn — người lỡ chọn nhầm vẫn nhận ra đường quay lại.
 */
export const UI_LANGUAGES = [
  {
    value: 'vi',
    label: 'Tiếng Việt'
  },
  {
    value: 'en',
    label: 'English'
  }
]

export const uiLanguage = ref(DEFAULT_UI_LANGUAGE)

export function isUiLanguage(value) {
  return typeof value === 'string' && Object.hasOwn(MESSAGES, value)
}

function lookup(dictionary, key) {
  return key.split('.').reduce((node, part) => node?.[part], dictionary)
}

/**
 * t('controls.start') -> 'Bắt đầu phiên dịch'
 * t('placeholder.systemText', { platform: 'Windows' }) -> thay {platform}
 *
 * Thiếu key ở ngôn ngữ đang chọn thì lấy tiếng Việt, thiếu cả hai thì
 * trả về chính key để lỗi lộ ra trên UI thay vì một chuỗi rỗng.
 */
export function t(key, params = {}) {
  const template =
    lookup(MESSAGES[uiLanguage.value], key) ?? lookup(MESSAGES[DEFAULT_UI_LANGUAGE], key)

  if (typeof template !== 'string') {
    console.warn(`Thiếu bản dịch cho key: ${key}`)

    return key
  }

  return template.replace(/\{(\w+)\}/g, (match, name) => {
    return Object.hasOwn(params, name) ? String(params[name]) : match
  })
}

// Để trình đọc màn hình và kiểm tra chính tả của Chromium dùng đúng ngôn ngữ
watch(
  uiLanguage,
  (language) => {
    document.documentElement.lang = language
  },
  {
    immediate: true
  }
)
