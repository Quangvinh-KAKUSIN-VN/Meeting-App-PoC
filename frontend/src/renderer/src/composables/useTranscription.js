import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'

import { AudioStreamer } from '../audioStreamer'

import { LANGUAGE_DIRECTIONS } from '../constants/appearance'

import { t } from '../i18n'

// Dự phòng khi IPC 'backend:get-endpoint' không khả dụng.
const FALLBACK_BACKEND_PORT = 8765

const MAX_VISIBLE_LINES = 30

// translationDirection: ref<key của LANGUAGE_DIRECTIONS> — quyết định endpoint và chiều ghi vào lịch sử.
export function useTranscription(translationDirection) {
  const audioSource = ref('system')
  const isRecording = ref(false)
  const isStarting = ref(false)

  const transcripts = ref([])
  const sessionHistory = ref([])
  const subtitleBoxRef = ref(null)

  let streamer = null
  let transcriptId = 0
  let historyId = 0
  let lastRawTranscript = ''

  // Backend đánh số msg_id lại từ 1 ở mỗi kết nối; nhân sessionKey để phiên mới không đè dòng phiên cũ.
  let sessionKey = 0

  // Dòng đã bị cắt khỏi màn hình; bản cập nhật muộn cho chúng bị bỏ qua.
  let retiredKeys = new Set()

  const hasHistory = computed(() => {
    return sessionHistory.value.length > 0
  })

  // BUG-012: đang chạy thì không cho đổi nguồn âm thanh.
  const canChangeSettings = computed(() => {
    return !isRecording.value && !isStarting.value
  })

  const scrollToLatestSubtitle = async () => {
    await nextTick()

    if (!subtitleBoxRef.value) {
      return
    }

    subtitleBoxRef.value.scrollTop = subtitleBoxRef.value.scrollHeight
  }

  // Lấy URL WebSocket từ main process (cổng: BACKEND_PORT trong electron/main/index.js).
  const resolveWebSocketUrl = async (wsPath, target) => {
    let host = '127.0.0.1'
    let port = FALLBACK_BACKEND_PORT

    try {
      const endpoint = await window.api?.getBackendEndpoint?.()

      if (endpoint?.host && endpoint?.port) {
        host = endpoint.host
        port = endpoint.port
      }
    } catch (error) {
      console.warn('Không lấy được endpoint từ main process:', error)
    }

    return `ws://${host}:${port}/ws/audio/${wsPath}?target=${encodeURIComponent(target)}`
  }

  /*
   * Giao thức: { id, src, dst, final, pending, dropped } — cùng id là cập nhật dòng cũ.
   *   final=false  bản nháp (vẽ mờ + nghiêng), sẽ bị bản final cùng id thay
   *   pending      đã có câu nguồn, chưa có bản dịch
   *   dropped      gỡ dòng chưa chốt
   * Vẫn chấp nhận text thuần và { src, dst } của giao thức cũ.
   */
  const parseIncomingMessage = (raw) => {
    const trimmedRaw = raw.trim()

    const asPlainText = {
      id: null,
      src: '',
      dst: trimmedRaw,
      final: true,
      pending: false,
      dropped: false
    }

    if (!trimmedRaw.startsWith('{')) {
      return asPlainText
    }

    try {
      const parsed = JSON.parse(trimmedRaw)

      if (!parsed || typeof parsed !== 'object') {
        return asPlainText
      }

      const dst =
        typeof parsed.dst === 'string'
          ? parsed.dst
          : typeof parsed.text === 'string'
            ? parsed.text
            : trimmedRaw

      return {
        id: Number.isFinite(parsed.id) ? parsed.id : null,
        src: typeof parsed.src === 'string' ? parsed.src.trim() : '',
        dst,
        final: typeof parsed.final === 'boolean' ? parsed.final : true,
        pending: parsed.pending === true,
        dropped: parsed.dropped === true
      }
    } catch {
      return asPlainText
    }
  }

  const addTranscript = async (receivedText) => {
    if (typeof receivedText !== 'string') {
      return
    }

    const {
      id: backendId,
      src: sourceText,
      dst,
      final,
      pending,
      dropped
    } = parseIncomingMessage(receivedText)

    const translatedText = dst.trim()

    if (dropped) {
      if (backendId !== null) {
        const droppedKey = `s${sessionKey}:${backendId}`

        // Chỉ gỡ dòng CHƯA chốt; câu đã chốt là của biên bản, không ai được gỡ
        transcripts.value = transcripts.value.filter((item) => {
          return item.key !== droppedKey || item.final
        })
      }

      return
    }

    const isPendingOnly = !translatedText && pending && Boolean(sourceText) && backendId !== null

    if (!translatedText && !isPendingOnly) {
      return
    }

    // Giao thức cũ không có id nên vẫn phải lọc trùng liên tiếp.
    if (backendId === null) {
      const dedupeKey = `${sourceText}|${translatedText}`

      if (dedupeKey === lastRawTranscript) {
        return
      }

      lastRawTranscript = dedupeKey
    }

    const lineKey =
      backendId === null ? `raw:${sessionKey}:${transcriptId + 1}` : `s${sessionKey}:${backendId}`

    if (retiredKeys.has(lineKey)) {
      return
    }

    const existingLine = transcripts.value.find((item) => item.key === lineKey)

    if (existingLine) {
      // Câu đã chốt thì cố định, bản nháp tới muộn không được ghi đè.
      if (existingLine.final && !final) {
        return
      }

      existingLine.src = sourceText
      existingLine.final = final

      // Message pending không mang bản dịch -> đừng xoá bản nháp đang hiện
      if (!isPendingOnly) {
        existingLine.text = translatedText
      }
    } else {
      transcriptId += 1

      transcripts.value.push({
        id: transcriptId,
        key: lineKey,
        src: sourceText,
        text: translatedText,
        final,
        type: 'translation'
      })
    }

    // Lịch sử xuất file chỉ ghi câu đã chốt.
    if (final) {
      const existingEntry = sessionHistory.value.find((entry) => entry.key === lineKey)

      if (existingEntry) {
        existingEntry.src = sourceText
        existingEntry.dst = translatedText
      } else {
        historyId += 1

        sessionHistory.value.push({
          id: historyId,
          key: lineKey,
          timestamp: new Date(),
          direction: translationDirection.value,
          src: sourceText,
          dst: translatedText
        })
      }
    }

    if (transcripts.value.length > MAX_VISIBLE_LINES) {
      const removed = transcripts.value.splice(0, transcripts.value.length - MAX_VISIBLE_LINES)

      for (const line of removed) {
        retiredKeys.add(line.key)
      }

      // Giữ Set khỏi phình vô hạn trong phiên họp dài
      if (retiredKeys.size > 500) {
        retiredKeys = new Set([...retiredKeys].slice(-200))
      }
    }

    await scrollToLatestSubtitle()
  }

  const addErrorMessage = (message) => {
    transcriptId += 1

    transcripts.value.push({
      id: transcriptId,
      key: `error:${sessionKey}:${transcriptId}`,
      text: message,
      final: true,
      type: 'error'
    })
  }

  // BUG-012: chặn đổi nguồn âm thanh khi đang chạy; trả false nếu bị từ chối.
  const setAudioSource = (nextSource) => {
    if (!canChangeSettings.value) {
      return false
    }

    audioSource.value = nextSource

    return true
  }

  const startRecording = async () => {
    if (isRecording.value || isStarting.value) {
      return
    }

    transcripts.value = []
    lastRawTranscript = ''
    transcriptId = 0
    retiredKeys = new Set()
    sessionKey += 1

    isStarting.value = true

    try {
      const { wsPath, target } = LANGUAGE_DIRECTIONS[translationDirection.value]

      const websocketUrl = await resolveWebSocketUrl(wsPath, target)

      streamer = new AudioStreamer(websocketUrl, addTranscript)

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

      const sourceLabel =
        audioSource.value === 'microphone' ? t('errors.sourceMicrophone') : t('errors.sourceSystem')

      addErrorMessage(
        t('errors.openSourceFailed', {
          source: sourceLabel,
          reason: error?.message || t('errors.unknown')
        })
      )
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

    // Chốt các dòng nháp đang dở, gỡ dòng chỉ có câu nguồn.
    transcripts.value = transcripts.value.filter((line) => line.text)

    for (const line of transcripts.value) {
      line.final = true
    }
  }

  // BUG-011: đổi chiều dịch giữa chừng làm phụ đề hai chiều lẫn vào nhau.
  watch(translationDirection, async (nextDirection, previousDirection) => {
    if (nextDirection === previousDirection) {
      return
    }

    if (!isRecording.value && !isStarting.value) {
      return
    }

    console.log(`🔄 Đổi chiều ${previousDirection} → ${nextDirection}, tạo lại phiên.`)

    await stopRecording()

    transcripts.value = []
    retiredKeys = new Set()

    await startRecording()
  })

  // BUG-026: báo cho renderer khi backend chết.
  if (typeof window !== 'undefined' && window.api?.onBackendDown) {
    window.api.onBackendDown(async ({ code }) => {
      console.error(`❌ Backend đã dừng (code=${code})`)

      if (isRecording.value || isStarting.value) {
        await stopRecording()
      }

      addErrorMessage(t('errors.backendDown', { code }))
    })
  }

  const clearTranscripts = () => {
    transcripts.value = []
    lastRawTranscript = ''
    retiredKeys = new Set()
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
      t('export.title'),
      t('export.exportedAt', { time: formatExportTimestamp(now) }),
      t('export.sentenceCount', { count: sessionHistory.value.length }),
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

    // BOM (BUG-013): thiếu thì Excel/Notepad cũ trên Windows đọc sai UTF-8.
    const fileContent = '\uFEFF' + lines.join('\r\n')

    const blob = new Blob([fileContent], {
      type: 'text/plain;charset=utf-8'
    })

    const objectUrl = URL.createObjectURL(blob)

    const pad = (value) => String(value).padStart(2, '0')

    const fileName =
      `${t('export.fileNamePrefix')}-${now.getFullYear()}` +
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
    canChangeSettings,
    transcripts,
    sessionHistory,
    hasHistory,
    subtitleBoxRef,
    setAudioSource,
    startRecording,
    stopRecording,
    clearTranscripts,
    exportHistory
  }
}
