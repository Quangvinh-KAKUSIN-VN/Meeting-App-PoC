import { computed, nextTick, onBeforeUnmount, ref } from 'vue'

import { AudioStreamer } from '../audioStreamer'

import { LANGUAGE_DIRECTIONS } from '../constants/appearance'

/**
 * translationDirection: ref<'ja-vi' | 'vi-ja'> lấy từ
 * useAppearanceSettings(), truyền vào để biết nên gọi
 * endpoint nào và ghi chiều dịch vào lịch sử.
 */
export function useTranscription(translationDirection) {
  const audioSource = ref('system')
  const isRecording = ref(false)
  const isStarting = ref(false)

  const transcripts = ref([])
  const sessionHistory = ref([])
  const subtitleBoxRef = ref(null)

  let streamer = null
  let transcriptId = 0
  let lastTranscript = ''

  const hasHistory = computed(() => {
    return sessionHistory.value.length > 0
  })

  const scrollToLatestSubtitle = async () => {
    await nextTick()

    if (!subtitleBoxRef.value) {
      return
    }

    subtitleBoxRef.value.scrollTop = subtitleBoxRef.value.scrollHeight
  }

  const parseIncomingMessage = (raw) => {
    const trimmedRaw = raw.trim()

    /*
     * Backend có thể gửi text thuần (bản dịch)
     * hoặc JSON { src, dst } khi có câu gốc.
     * Tự nhận diện để không phá vỡ dữ liệu cũ.
     */
    if (!trimmedRaw.startsWith('{')) {
      return {
        src: '',
        dst: trimmedRaw
      }
    }

    try {
      const parsed = JSON.parse(trimmedRaw)

      if (!parsed || typeof parsed !== 'object') {
        return {
          src: '',
          dst: trimmedRaw
        }
      }

      const dst =
        typeof parsed.dst === 'string'
          ? parsed.dst
          : typeof parsed.text === 'string'
            ? parsed.text
            : trimmedRaw

      const src = typeof parsed.src === 'string' ? parsed.src.trim() : ''

      return {
        src,
        dst
      }
    } catch (error) {
      return {
        src: '',
        dst: trimmedRaw
      }
    }
  }

  const addTranscript = async (receivedText) => {
    if (typeof receivedText !== 'string') {
      return
    }

    const { src: sourceText, dst: translatedRaw } = parseIncomingMessage(receivedText)

    const translatedText = translatedRaw.trim()

    if (!translatedText) {
      return
    }

    const dedupeKey = `${sourceText}|${translatedText}`

    if (dedupeKey === lastTranscript) {
      return
    }

    lastTranscript = dedupeKey
    transcriptId += 1

    transcripts.value.push({
      id: transcriptId,
      src: sourceText,
      text: translatedText,
      type: 'translation'
    })

    sessionHistory.value.push({
      id: transcriptId,
      timestamp: new Date(),
      direction: translationDirection.value,
      src: sourceText,
      dst: translatedText
    })

    if (transcripts.value.length > 30) {
      transcripts.value.splice(0, transcripts.value.length - 30)
    }

    await scrollToLatestSubtitle()
  }

  const addErrorMessage = (message) => {
    transcriptId += 1

    transcripts.value.push({
      id: transcriptId,
      text: message,
      type: 'error'
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
      const wsPath = LANGUAGE_DIRECTIONS[translationDirection.value].wsPath

      streamer = new AudioStreamer(`ws://127.0.0.1:8000/ws/audio/${wsPath}`, addTranscript)

      await streamer.start(audioSource.value)

      isRecording.value = true
    } catch (error) {
      console.error('❌ Không thể bắt đầu dịch:', error)

      if (streamer) {
        try {
          await streamer.stop()
        } catch (stopError) {
          console.error('Không thể dọn AudioStreamer:', stopError)
        }
      }

      streamer = null
      isRecording.value = false

      const sourceLabel = audioSource.value === 'microphone' ? 'microphone' : 'âm thanh máy tính'

      addErrorMessage(`Không thể mở ${sourceLabel}: ${error?.message || 'Lỗi không xác định'}`)
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

  const formatEntryTimestamp = (date) => {
    const pad = (value) => String(value).padStart(2, '0')

    return `${pad(date.getHours())}:` + `${pad(date.getMinutes())}:` + `${pad(date.getSeconds())}`
  }

  const formatExportTimestamp = (date) => {
    const pad = (value) => String(value).padStart(2, '0')

    return (
      `${date.getFullYear()}-` +
      `${pad(date.getMonth() + 1)}-` +
      `${pad(date.getDate())} ` +
      `${pad(date.getHours())}:` +
      `${pad(date.getMinutes())}`
    )
  }

  const exportHistory = () => {
    if (sessionHistory.value.length === 0) {
      return
    }

    const now = new Date()

    const lines = [
      'BIÊN BẢN PHIÊN DỊCH CUỘC HỌP',
      `Xuất lúc: ${formatExportTimestamp(now)}`,
      `Số câu đã dịch: ${sessionHistory.value.length}`,
      '',
      '='.repeat(50),
      ''
    ]

    for (const entry of sessionHistory.value) {
      const info = LANGUAGE_DIRECTIONS[entry.direction] || LANGUAGE_DIRECTIONS['ja-vi']

      lines.push(`[${formatEntryTimestamp(entry.timestamp)}]`)

      if (entry.src) {
        lines.push(`${info.sourceCode}: ${entry.src}`)
      }

      lines.push(`${info.targetCode}: ${entry.dst}`)

      lines.push('')
    }

    const fileContent = lines.join('\n')

    const blob = new Blob([fileContent], {
      type: 'text/plain;charset=utf-8'
    })

    const objectUrl = URL.createObjectURL(blob)

    const pad = (value) => String(value).padStart(2, '0')

    const fileName =
      `bien-ban-hop-${now.getFullYear()}` +
      `${pad(now.getMonth() + 1)}` +
      `${pad(now.getDate())}-` +
      `${pad(now.getHours())}` +
      `${pad(now.getMinutes())}.txt`

    const downloadLink = document.createElement('a')

    downloadLink.href = objectUrl
    downloadLink.download = fileName

    document.body.appendChild(downloadLink)
    downloadLink.click()
    document.body.removeChild(downloadLink)

    URL.revokeObjectURL(objectUrl)
  }

  onBeforeUnmount(async () => {
    if (streamer) {
      await streamer.stop()
      streamer = null
    }
  })

  return {
    audioSource,
    isRecording,
    isStarting,
    transcripts,
    sessionHistory,
    hasHistory,
    subtitleBoxRef,
    startRecording,
    stopRecording,
    clearTranscripts,
    exportHistory
  }
}
